"""CLI entrypoint for the Power BI PBIP CI/CD analyzer, documentation, and lineage portal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pbi_cicd.bpa_analyzer import analyze_bpa
from pbi_cicd.config_loader import discover_projects, load_config, reports_directory, resolve_project_paths
from pbi_cicd.docs_generator import (
    generate_bpa_report_md,
    generate_measures_md,
    generate_model_design_md,
    generate_pr_summary_md,
)
from pbi_cicd.html_portal_generator import generate_html_portal
from pbi_cicd.lineage_builder import build_lineage_graph
from pbi_cicd.pbir_parser import parse_pbir_report
from pbi_cicd.tmdl_m_parser import load_semantic_model
from pbi_cicd.metadata_provenance import record_te2_provenance, source_fingerprint, te2_provenance_status


def run_pipeline(
    root: Path | None = None,
    config_path: Path | None = None,
    dist_override: Path | None = None,
    te2_metadata_path: Path | None = None,
    te2_bpa_path: Path | None = None,
    ticket: str | None = None,
    require_te2: bool = False,
) -> dict[str, Any]:
    """Execute the full metadata, PBIR, BPA, lineage, Markdown, and HTML portal generation pipeline."""
    base = (root or Path.cwd()).resolve()
    config = load_config(config_path=config_path, root=base)
    paths = resolve_project_paths(root=base, config=config, dist_override=dist_override, ticket=ticket, config_path=config_path)
    paths.dist_dir.mkdir(parents=True, exist_ok=True)

    meta_file = te2_metadata_path or (paths.dist_dir / "te2-metadata.json")
    bpa_file = te2_bpa_path or (paths.dist_dir / "te2-bpa.txt")
    if meta_file.resolve() != (paths.dist_dir / "te2-metadata.json").resolve() or bpa_file.resolve() != (paths.dist_dir / "te2-bpa.txt").resolve():
        raise ValueError("TE2 artifacts must belong to the selected ticket output directory")
    provenance = te2_provenance_status(paths)
    if require_te2 and provenance != "valid":
        raise ValueError(f"TE2 metadata is {provenance} for {paths.ticket}; run fresh ticket extraction first")
    model_meta = load_semantic_model(paths.semantic_model_dir, metadata_json_path=meta_file if provenance == "valid" else None)
    report_meta = parse_pbir_report(paths.report_dir)
    bpa_report = analyze_bpa(paths.root, config, model_meta, report_meta, bpa_txt_path=bpa_file if provenance == "valid" else None, project_scope=paths.project_dir)
    lineage_graph = build_lineage_graph(model_meta, report_meta, bpa_report)

    pbip_name = paths.pbip_file.stem
    (paths.dist_dir / "bpa-report.json").write_text(
        json.dumps(bpa_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (paths.dist_dir / "lineage-graph.json").write_text(
        json.dumps(lineage_graph, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (paths.dist_dir / "MODEL_DESIGN.md").write_text(
        generate_model_design_md(pbip_name, model_meta, report_meta, lineage_graph), encoding="utf-8"
    )
    (paths.dist_dir / "MEASURES.md").write_text(
        generate_measures_md(pbip_name, model_meta, lineage_graph), encoding="utf-8"
    )
    (paths.dist_dir / "BPA_REPORT.md").write_text(
        generate_bpa_report_md(pbip_name, bpa_report), encoding="utf-8"
    )
    (paths.dist_dir / "pr-summary.md").write_text(
        generate_pr_summary_md(pbip_name, model_meta, report_meta, bpa_report), encoding="utf-8"
    )
    (paths.dist_dir / "index.html").write_text(
        generate_html_portal(pbip_name, model_meta, report_meta, bpa_report, lineage_graph), encoding="utf-8"
    )
    summary = {
        "ticket": paths.ticket, "pbipName": pbip_name,
        "pbip": paths.pbip_file.relative_to(paths.root).as_posix(),
        "sourceFingerprint": source_fingerprint(paths),
        "sourceMode": model_meta["sourceMode"], "te2Status": provenance,
        "gate": bpa_report["gate"], "counts": {
            "tables": len(model_meta["tables"]), "measures": sum(len(t.get("measures", [])) for t in model_meta["tables"]),
            "pages": len(report_meta["pages"]), "visuals": report_meta["totalVisuals"],
            "findings": bpa_report["summary"]["totalViolations"],
        },
    }
    (paths.dist_dir / "project-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return {
        "paths": paths,
        "model": model_meta,
        "report": report_meta,
        "bpa": bpa_report,
        "lineage": lineage_graph,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    """Run selected tickets or emit discovery data for a CI matrix."""
    import subprocess

    from pbi_cicd.portfolio import stage_site, write_repository_index
    from pbi_cicd.ticket_selection import git_changed_paths, select_changed_tickets

    parser = argparse.ArgumentParser(description="Multi-ticket Power BI PBIP analysis and portal generation.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dist", type=Path, help="Output base; each ticket gets its own subdirectory.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--ticket", help="Jira ticket ID, such as TEST-001.")
    selection.add_argument("--all", action="store_true", help="Run every discovered ticket (the default).")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--list-projects", action="store_true")
    modes.add_argument("--matrix", action="store_true")
    modes.add_argument("--record-te2-source", action="store_true")
    modes.add_argument("--check-gates", action="store_true")
    modes.add_argument("--build-index", action="store_true")
    parser.add_argument("--base", default="", help="Git base revision for changed-ticket selection.")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--site", type=Path, help="Stage standalone HTML under this output-base subdirectory.")
    parser.add_argument("--te2-metadata", type=Path)
    parser.add_argument("--te2-bpa", type=Path)
    parser.add_argument("--require-te2", action="store_true")
    parser.add_argument("--enforce-gate", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        config = load_config(args.config, root)
        projects = discover_projects(root, config)
        tickets = [args.ticket] if args.ticket else sorted(projects)
        if args.matrix:
            if not args.base or set(args.base) == {"0"}:
                chosen = {"tickets": sorted(projects), "deleted": [], "all": True}
            else:
                directory = reports_directory(root, config).relative_to(root).as_posix()
                chosen = select_changed_tickets(git_changed_paths(root, args.base, args.head), projects, directory)
            matrix = {"include": [{"ticket": ticket} for ticket in chosen["tickets"]]}
            encoded = json.dumps(matrix, separators=(",", ":"))
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as stream:
                    stream.write("matrix=" + encoded + "\nhas_projects=" + str(bool(chosen["tickets"])).lower() + "\ndeleted=" + json.dumps(chosen["deleted"]) + "\n")
            print(encoded)
            return 0
        paths = [resolve_project_paths(root, config, args.dist, ticket, args.config) for ticket in tickets]
        if args.list_projects:
            print(json.dumps([{"ticket": p.ticket, "pbip": str(p.pbip_file), "report_dir": str(p.report_dir), "semantic_model_dir": str(p.semantic_model_dir), "dist_dir": str(p.dist_dir), "rules_file": str(p.rules_file)} for p in paths]))
            return 0
        if args.record_te2_source:
            if not args.ticket:
                raise ValueError("Recording TE2 provenance requires --ticket")
            record_te2_provenance(paths[0])
            return 0
        if args.check_gates:
            for project in paths:
                summary = json.loads((project.dist_dir / "project-summary.json").read_text(encoding="utf-8"))
                if summary.get("sourceFingerprint") != source_fingerprint(project):
                    raise ValueError(f"Regenerate stale analysis for {project.ticket} before checking its gate")
            return int(any(not json.loads((p.dist_dir / "bpa-report.json").read_text(encoding="utf-8"))["gate"]["passed"] for p in paths))
        if not args.build_index:
            if len(paths) > 1 and (args.te2_metadata or args.te2_bpa):
                raise ValueError("Explicit TE2 artifacts require a single --ticket")
            failed = False
            for project in paths:
                result = run_pipeline(root, args.config, args.dist, args.te2_metadata, args.te2_bpa, project.ticket, args.require_te2)
                gate = result["bpa"]["gate"]
                failed |= not gate["passed"]
                print(f"{project.ticket}: {project.pbip_file.name} | {result['model']['sourceMode']} | TE2 {result['summary']['te2Status']} | Gate {gate['status']} | {project.dist_dir / 'index.html'}")
            write_repository_index(root, args.config, args.dist)
            if args.site:
                stage_site(root, args.site, args.config, args.dist)
            return int(args.enforce_gate and failed)
        write_repository_index(root, args.config, args.dist)
        if args.site:
            stage_site(root, args.site, args.config, args.dist)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"PBIP pipeline error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
