"""Automated test suite for the Power BI PBIP CI/CD pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pbi_cicd.bpa_analyzer import analyze_bpa, parse_te2_bpa_output, run_cross_layer_checks
from pbi_cicd.cli import run_pipeline
from pbi_cicd.config_loader import load_config, resolve_project_paths
from pbi_cicd.lineage_builder import build_lineage_graph
from pbi_cicd.pbir_parser import _extract_visual_refs, parse_pbir_report
from pbi_cicd.tmdl_m_parser import extract_m_sources, find_m_expression_refs, load_semantic_model

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_bpa_rules_schema_and_crlf() -> None:
    """Verify BPA rule JSON files use CRLF, unique uppercase IDs, and required keys."""
    required = {"ID", "Name", "Category", "Description", "Severity", "Scope", "Expression"}
    for rel in ("config/bpa-rules.json", "config/bpa-rules-vertipaq.json"):
        path = REPO_ROOT / rel
        raw_bytes = path.read_bytes()
        assert b"\r\n" in raw_bytes, f"{rel} must use CRLF line endings for TE2 compatibility"
        rules = json.loads(raw_bytes.decode("utf-8-sig"))
        assert isinstance(rules, list) and len(rules) > 0
        seen_ids: set[str] = set()
        for rule in rules:
            assert required.issubset(rule.keys()), f"Missing keys in {rule}"
            rid = rule["ID"]
            assert re.match(r"^[A-Z0-9_]+$", rid), f"Invalid BPA rule ID: {rid}"
            assert rid not in seen_ids, f"Duplicate BPA rule ID: {rid}"
            seen_ids.add(rid)
            assert rule["Severity"] in (1, 2, 3)


def test_resolve_project_paths(fixture_repo: Path) -> None:
    """Verify .pbip, .Report, and .SemanticModel paths resolve cleanly."""
    cfg = load_config(root=fixture_repo)
    paths = resolve_project_paths(root=fixture_repo, config=cfg)
    assert paths.ticket == "FIX-1"
    assert paths.pbip_file.parent == fixture_repo / "reports/FIX-1"
    assert paths.report_dir.exists()
    assert paths.semantic_model_dir.exists()


def test_m_source_and_expression_ref_extraction() -> None:
    """Verify Power Query M connector detection and NamedExpression reference matching."""
    expr = '''
    let
        Source = Csv.Document(File.Contents("C:\\Users\\demo\\data.csv")),
        Clock = DateTimeZone.UtcNow()
    in
        Table.TransformColumnTypes(Source, {})
    '''
    sources = extract_m_sources(expr)
    kinds = {s["sourceKind"] for s in sources}
    assert "Local File" in kinds
    assert "System Clock (M)" in kinds
    assert any(s["isLocalPath"] for s in sources if s["sourceKind"] == "Local File")

    refs = find_m_expression_refs("let Source = activity_event_synthetic in Source", ["activity_event_synthetic", "other"])
    assert refs == ["activity_event_synthetic"]


def test_pbir_subquery_alias_resolution() -> None:
    """Verify textbox Subquery alias resolution skips synthetic outer Column wrappers."""
    sample_visual = {
        "visual": {
            "visualType": "textbox",
            "objects": {
                "values": [
                    {
                        "properties": {
                            "expr": {
                                "Column": {
                                    "Expression": {
                                        "Subquery": {
                                            "Query": {
                                                "From": [{"Name": "m", "Entity": "Measure", "Type": 0}],
                                                "Select": [
                                                    {
                                                        "Measure": {
                                                            "Expression": {"SourceRef": {"Source": "m"}},
                                                            "Property": "Active Users",
                                                        }
                                                    }
                                                ],
                                            }
                                        }
                                    },
                                    "Property": "Measure.Active Users",
                                }
                            }
                        }
                    }
                ]
            },
        }
    }
    refs = _extract_visual_refs(sample_visual)
    assert len(refs) == 1
    assert refs[0] == {"kind": "Measure", "table": "Measure", "name": "Active Users", "usage": "visualObject"}


def test_pbir_and_tmdl_fallback_parsing(fixture_repo: Path) -> None:
    """Verify pure-Python TMDL fallback and real PBIR parsing agree on object counts."""
    paths = resolve_project_paths(root=fixture_repo)
    model_fallback = load_semantic_model(paths.semantic_model_dir, metadata_json_path=None)
    assert model_fallback["sourceMode"] == "tmdl_fallback"
    assert len(model_fallback["tables"]) == 1
    total_measures = sum(len(t["measures"]) for t in model_fallback["tables"])
    assert total_measures == 1

    report = parse_pbir_report(paths.report_dir)
    assert len(report["pages"]) == 1
    assert report["totalVisuals"] == 1
    assert len(report["bookmarks"]) == 0


def test_te2_bpa_parser_and_advisory_gate(tmp_path: Path) -> None:
    """Verify TE2 -AX -G line parsing and Advisory Gate pass/fail thresholds."""
    log_file = tmp_path / "te2-bpa.txt"
    log_file.write_text(
        "\n".join(
            [
                '::error:: Measure [Bad Measure] violates rule "[DAX Expressions] Measure references should be unqualified"',
                '::warning:: Column \'T\'[C] violates rule "[Formatting] Hide foreign key columns"',
                'Measure [Uncommented] violates rule "[Metadata] Visible measures should have a description"',
            ]
        ),
        encoding="utf-8",
    )
    rules_catalog = load_config(root=REPO_ROOT)
    from pbi_cicd.bpa_analyzer import load_bpa_rules_catalog

    by_name = load_bpa_rules_catalog(REPO_ROOT / "config" / "bpa-rules.json")
    violations, errors = parse_te2_bpa_output(log_file, by_name)
    assert not errors
    assert [v["severity"] for v in violations] == [3, 2, 1]

    # Cross-layer broken reference check
    mock_model = {
        "tables": [{"name": "Sales", "isHidden": False, "columns": [{"name": "Amount", "dependsOn": []}], "measures": []}],
        "relationships": [],
    }
    mock_report = {
        "allFieldRefs": [
            {"kind": "Column", "table": "Sales", "name": "Amount", "pageName": "P1", "visualTitle": "V1", "visualId": "v1"},
            {"kind": "Measure", "table": "Sales", "name": "MissingMeasure", "pageName": "P1", "visualTitle": "V2", "visualId": "v2"},
        ]
    }
    cross = run_cross_layer_checks(tmp_path, mock_model, mock_report)
    broken = [c for c in cross if c["ruleId"] == "PBIR_BROKEN_FIELD_REF"]
    assert len(broken) == 1
    assert broken[0]["severity"] == 3

    bpa_report = analyze_bpa(REPO_ROOT, rules_catalog, mock_model, mock_report, bpa_txt_path=log_file)
    assert bpa_report["gate"]["passed"] is False
    assert bpa_report["gate"]["blockingCount"] >= 2


def test_lineage_cycle_safety() -> None:
    """Ensure cyclic DAX_DEP references do not cause infinite loops in BFS counts."""
    model = {
        "expressions": [],
        "relationships": [],
        "tables": [
            {
                "name": "M",
                "isHidden": False,
                "tableType": "Table",
                "partitions": [],
                "columns": [],
                "measures": [
                    {
                        "name": "A",
                        "expression": "[B]",
                        "dependsOn": [{"objectType": "Measure", "table": "M", "name": "B", "daxObjectFullName": "[B]"}],
                    },
                    {
                        "name": "B",
                        "expression": "[A]",
                        "dependsOn": [{"objectType": "Measure", "table": "M", "name": "A", "daxObjectFullName": "[A]"}],
                    },
                ],
            }
        ],
    }
    graph = build_lineage_graph(model, {"pages": [], "allFieldRefs": []}, {"violations": []})
    meas_nodes = [n for n in graph["nodes"] if n["kind"] == "measure"]
    assert len(meas_nodes) == 2
    assert all(n["upstreamCount"] == 1 and n["downstreamCount"] == 1 for n in meas_nodes)


def test_end_to_end_pipeline_outputs(tmp_path: Path, fixture_repo: Path) -> None:
    """Run the full pipeline into an isolated dist directory and verify all outputs."""
    out_dir = tmp_path / "dist"
    res = run_pipeline(
        root=fixture_repo,
        dist_override=out_dir,
        ticket="FIX-1",
    )
    out_dir = res["paths"].dist_dir
    expected = [
        "bpa-report.json",
        "lineage-graph.json",
        "MODEL_DESIGN.md",
        "MEASURES.md",
        "BPA_REPORT.md",
        "pr-summary.md",
        "index.html",
    ]
    for name in expected:
        assert (out_dir / name).exists(), f"Missing generated artifact: {name}"

    html_text = (out_dir / "index.html").read_text(encoding="utf-8")
    assert '<script id="portal-data" type="application/json">' in html_text
    assert res["lineage"]["summary"]["tierCounts"]["0"] >= 1
    assert res["lineage"]["summary"]["tierCounts"]["3"] == 2

