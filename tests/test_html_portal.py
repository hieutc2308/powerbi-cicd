"""Contracts for the self-contained v6 portal and its packaged assets."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pbi_cicd.html_portal_generator import generate_html_portal
from pbi_cicd.lineage_builder import build_lineage_graph


def portal_inputs() -> tuple[dict, dict, dict, dict]:
    model = {
        "tables": [{
            "name": "Orders", "tableType": "Table (Import)", "isHidden": False,
            "columns": [{"name": "Key", "dataType": "Int64", "columnType": "Data"}],
            "measures": [{"name": "Net amount", "displayFolder": "Finance", "expression": "\nVAR x = 1\nRETURN\n\tx", "dependsOn": []}],
            "partitions": [{"name": "Orders", "sourceType": "M", "expression": "let\n    Source = #table({}, {})\nin\n    Source"}],
        }],
        "expressions": [], "relationships": [], "roles": [], "sourceMode": "fixture",
    }
    report = {"pages": [], "allFieldRefs": [], "bookmarks": [], "totalVisuals": 0}
    bpa = {
        "gate": {"passed": False, "status": "FAIL", "blockingCount": 1, "failSeverity": 3, "ruleErrorCount": 1},
        "summary": {"totalViolations": 1, "severityCounts": {"3": 1}},
        "violations": [{"ruleId": "PROJECT_POLICY", "ruleName": "Project policy check", "severity": 3, "category": "Governance", "layer": "Repository", "objectType": "GitArtifact", "objectName": "cache.abf", "objectDisplay": "Committed cache.abf"}],
        "ruleErrors": [{"ruleName": "Invalid rule", "message": "Evaluation failed"}],
    }
    return model, report, bpa, build_lineage_graph(model, report, bpa)


def embedded_payload(document: str) -> dict:
    match = re.search(r'<script id="portal-data" type="application/json">(.*?)</script>', document, re.S)
    assert match is not None
    return json.loads(match.group(1))


def test_portal_uses_approved_v6_workspace_with_complete_payload() -> None:
    inputs = portal_inputs()
    document = generate_html_portal("Northwind", *inputs)
    for page in ("home", "catalog", "lineage", "model", "detail", "checks"):
        assert f'id="page-{page}"' in document
    assert 'id="select-tool"' not in document
    assert 'id="hand-tool"' not in document
    assert "data:font/woff2" in document
    assert "var(--surface)-space" not in document
    assert not re.search(r'<(?:script|link)\b[^>]*(?:src|href)=', document)
    assert "Admin Monitoring" not in document
    assert "meas:Active Users" not in document
    payload = embedded_payload(document)
    assert payload == dict(zip(("pbipName", "model", "report", "bpa", "lineage"), ("Northwind", *inputs)))


def test_embedded_source_is_inert_and_placeholder_text_survives() -> None:
    model, report, bpa, graph = portal_inputs()
    name = 'North <img src=x onerror=alert(1)> __PORTAL_APP__'
    expression = '\n\t"</script><script>alert(1)</script> & <!-- __PORTAL_DATA_JSON__"'
    model["tables"][0]["measures"][0]["expression"] = expression
    document = generate_html_portal(name, model, report, bpa, graph)
    payload = embedded_payload(document)
    assert payload["model"]["tables"][0]["measures"][0]["expression"] == expression
    assert payload["pbipName"] == name
    assert f"<title>{html.escape(name)}" in document
    assert "<script>alert(1)</script>" not in document
    assert len(re.findall(r"<script\b", document)) == 2


@pytest.mark.parametrize("scenario", ["arbitrary", "empty", "cycle"])
def test_generated_portal_runtime(tmp_path: Path, scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the portal runtime regression checks")
    model, report, bpa, graph = portal_inputs()
    if scenario == "empty":
        model = {"tables": [], "expressions": [], "relationships": [], "roles": []}
        graph = build_lineage_graph(model, report, bpa)
    elif scenario == "cycle":
        model["tables"][0]["measures"] = [
            {"name": "First", "expression": "[Second]", "dependsOn": [{"objectType": "Measure", "name": "Second"}]},
            {"name": "Second", "expression": "[First]", "dependsOn": [{"objectType": "Measure", "name": "First"}]},
        ]
        graph = build_lineage_graph(model, report, bpa)
    output = tmp_path / "index.html"
    output.write_text(generate_html_portal("Northwind", model, report, bpa, graph), encoding="utf-8")
    result = subprocess.run([node, str(Path(__file__).with_name("portal_runtime.cjs")), str(output)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_portal_assets_are_packaged() -> None:
    from importlib.resources import files

    root = files("pbi_cicd").joinpath("portal")
    for name in ("index.html", "styles.css", "app.js", "geist.css", "GEIST-OFL.txt"):
        assert root.joinpath(name).is_file(), name


def test_project_runtime_and_read_only_generation(tmp_path: Path, fixture_repo: Path) -> None:
    import hashlib

    from pbi_cicd.cli import run_pipeline

    root = fixture_repo
    inputs = [p for p in (root / "reports").rglob("*") if p.is_file()]
    before = {p: hashlib.sha256(p.read_bytes()).digest() for p in inputs}
    result = run_pipeline(root=root, dist_override=tmp_path / "output", ticket="FIX-1")
    output = result["paths"].dist_dir
    assert {p: hashlib.sha256(p.read_bytes()).digest() for p in inputs} == before
    assert embedded_payload((output / "index.html").read_text(encoding="utf-8"))["bpa"] == result["bpa"]
    node = shutil.which("node")
    if node:
        process = subprocess.run([node, str(Path(__file__).with_name("portal_runtime.cjs")), str(output / "index.html")], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert process.returncode == 0, process.stdout + process.stderr
