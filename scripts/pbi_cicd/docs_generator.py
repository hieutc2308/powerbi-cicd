"""Markdown documentation and PR summary generator for PBIP CI/CD artifacts."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any


def _mermaid_id(raw: str, prefix: str = "N") -> str:
    """Sanitize an arbitrary identifier into an alphanumeric Mermaid node ID."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_")
    return f"{prefix}_{cleaned or 'node'}"


def _md_escape(text: str) -> str:
    """Escape pipe characters for Markdown table cells."""
    return (text or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def generate_model_design_md(
    pbip_name: str,
    model_meta: dict[str, Any],
    report_meta: dict[str, Any],
    lineage_graph: dict[str, Any],
) -> str:
    """Generate dist/MODEL_DESIGN.md with architecture, ER diagram, and ingestion inventory."""
    tables = model_meta.get("tables", [])
    rels = model_meta.get("relationships", [])
    exprs = model_meta.get("expressions", [])
    pages = report_meta.get("pages", [])
    total_cols = sum(len(t.get("columns", [])) for t in tables)
    total_meas = sum(len(t.get("measures", [])) for t in tables)

    lines: list[str] = [
        f"# Model & Report Design — {pbip_name}",
        "",
        "## Overview",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Semantic Model Tables | {len(tables)} |",
        f"| Columns | {total_cols} |",
        f"| Measures | {total_meas} |",
        f"| Relationships | {len(rels)} |",
        f"| Shared M Expressions (`expressions.tmdl`) | {len(exprs)} |",
        f"| Report Pages | {len(pages)} |",
        f"| Report Visuals | {report_meta.get('totalVisuals', 0)} |",
        f"| Bookmarks | {len(report_meta.get('bookmarks', []))} |",
        "",
        "## End-to-End Ingestion Lineage (Tier 0 -> Tier 2)",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    tier0_nodes = [n for n in lineage_graph.get("nodes", []) if n["tier"] == 0]
    tier1_nodes = [n for n in lineage_graph.get("nodes", []) if n["tier"] == 1]
    tier2_tables = [n for n in lineage_graph.get("nodes", []) if n["kind"] == "table"]

    for n in tier0_nodes:
        lines.append(f'    {_mermaid_id(n["id"], "S")}["{n["label"]} ({n["subtitle"]})"]')
    for n in tier1_nodes:
        lines.append(f'    {_mermaid_id(n["id"], "Q")}["{n["label"]} (PQ)"]')
    for n in tier2_tables:
        lines.append(f'    {_mermaid_id(n["id"], "T")}["{n["label"]}"]')

    id_prefix = {n["id"]: ("S" if n["tier"] == 0 else ("Q" if n["tier"] == 1 else "T")) for n in tier0_nodes + tier1_nodes + tier2_tables}
    for edge in lineage_graph.get("edges", []):
        if edge["type"] in ("SOURCE_TO_PQ", "M_REF", "PQ_REF", "SOURCE_TO_TABLE", "CALC_TABLE_DEP"):
            sp = id_prefix.get(edge["source"])
            tp = id_prefix.get(edge["target"])
            if sp and tp:
                lines.append(f'    {_mermaid_id(edge["source"], sp)} -->|"{edge["type"]}"| {_mermaid_id(edge["target"], tp)}')
    lines.extend(["```", ""])

    if rels:
        lines.extend(["## Star Schema Relationships", "", "```mermaid", "erDiagram"])
        for rel in rels:
            f_tbl = _mermaid_id(rel["fromTable"], "TBL")
            t_tbl = _mermaid_id(rel["toTable"], "TBL")
            card = "}o--o{" if rel.get("toCardinality") == "Many" else "}o--||"
            lines.append(f'    {t_tbl} {card} {f_tbl} : "{rel.get("toColumn", "")} -> {rel.get("fromColumn", "")}"')
        lines.extend(
            [
                "```",
                "",
                "| From Table[Column] | To Table[Column] | Cardinality | Cross-Filter | Active |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for rel in rels:
            fc = f"`{rel['fromTable']}[{rel['fromColumn']}]`"
            tc = f"`{rel['toTable']}[{rel['toColumn']}]`"
            card = f"{rel.get('fromCardinality', 'Many')}:{rel.get('toCardinality', 'One')}"
            lines.append(
                f"| {fc} | {tc} | {card} | {rel.get('crossFilteringBehavior', '')} | {rel.get('isActive', True)} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Tables Inventory",
            "",
            "| Table | Type | Columns | Measures | Hidden | Upstream Sources / Partitions |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for tbl in tables:
        src_parts = list(tbl.get("mExpressionRefs", [])) + [s["location"] for s in tbl.get("directSources", [])]
        if tbl.get("calculatedTableKind"):
            src_parts.append(tbl["calculatedTableKind"])
        src_summary = ", ".join(src_parts) if src_parts else "Model partition"
        lines.append(
            f"| `{tbl['name']}` | {tbl.get('tableType', 'Table')} | {len(tbl.get('columns', []))} | {len(tbl.get('measures', []))} | {tbl.get('isHidden', False)} | {_md_escape(src_summary)} |"
        )
    lines.append("")

    if exprs:
        lines.extend(["## Shared Power Query Expressions", ""])
        for expr in exprs:
            srcs = ", ".join(f"{s['connector']}: `{s['location']}`" for s in expr.get("sources", [])) or "None"
            transforms = ", ".join(expr.get("transformations", [])) or "None"
            lines.extend(
                [
                    f"### `{expr['name']}`",
                    f"- **Query Group**: {expr.get('queryGroup') or 'Default'}",
                    f"- **Detected Sources**: {srcs}",
                    f"- **Transformations**: {transforms}",
                    "",
                    "```powerquery",
                    expr.get("expression", "").strip(),
                    "```",
                    "",
                ]
            )

    lines.extend(
        [
            "## Report Pages & Visual Breakdown",
            "",
            "| Page | Canvas | Visuals | Data-Bound Refs |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for page in pages:
        bound_count = sum(1 for v in page.get("visuals", []) if v.get("fieldRefs"))
        lines.append(
            f"| {_md_escape(page['displayName'])} | {page.get('width', 1280)}x{page.get('height', 720)} | {len(page.get('visuals', []))} | {bound_count} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_measures_md(
    pbip_name: str,
    model_meta: dict[str, Any],
    lineage_graph: dict[str, Any],
) -> str:
    """Generate dist/MEASURES.md grouped by Display Folder with DAX and downstream consumers."""
    meas_nodes = {n["label"]: n for n in lineage_graph.get("nodes", []) if n["kind"] == "measure"}
    visual_consumers: dict[str, list[str]] = defaultdict(list)
    node_lookup = {n["id"]: n for n in lineage_graph.get("nodes", [])}

    for edge in lineage_graph.get("edges", []):
        if edge["type"] == "BIND_MEASURE":
            m_node = node_lookup.get(edge["source"])
            v_node = node_lookup.get(edge["target"])
            if m_node and v_node:
                visual_consumers[m_node["label"]].append(v_node["label"])

    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for tbl in model_meta.get("tables", []):
        for meas in tbl.get("measures", []):
            folder = meas.get("displayFolder") or "(Unassigned)"
            grouped[folder].append((tbl["name"], meas))

    lines: list[str] = [
        f"# DAX Measures Catalog — {pbip_name}",
        "",
        f"Total measures: **{sum(len(v) for v in grouped.values())}** across **{len(grouped)}** display folders.",
        "",
    ]

    for folder in sorted(grouped):
        lines.extend([f"## Folder: {folder}", ""])
        for tbl_name, meas in sorted(grouped[folder], key=lambda item: item[1]["name"]):
            m_name = meas["name"]
            consumers = sorted(set(visual_consumers.get(m_name, [])))
            deps = [d.get("daxObjectFullName") or d.get("name", "") for d in meas.get("dependsOn", [])]
            bpa_count = len(meas_nodes.get(m_name, {}).get("bpa", []))

            lines.extend(
                [
                    f"### `[{m_name}]`",
                    f"- **Table**: `{tbl_name}` | **Format**: `{meas.get('formatString') or 'None'}` | **Hidden**: {meas.get('isHidden', False)} | **BPA Hits**: {bpa_count}",
                    f"- **Description**: {_md_escape(meas.get('description') or '_No description_')}",
                    f"- **Depends On**: {', '.join(f'`{d}`' for d in sorted(set(deps))) if deps else '_None_'}",
                    f"- **Report Consumers ({len(consumers)})**: {', '.join(f'`{c}`' for c in consumers[:8])}{' ...' if len(consumers) > 8 else ''}"
                    if consumers
                    else "- **Report Consumers (0)**: _Unused directly in report visuals_",
                    "",
                    "```dax",
                    (meas.get("expression") or "").strip(),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines)


def generate_bpa_report_md(pbip_name: str, bpa_report: dict[str, Any]) -> str:
    """Generate dist/BPA_REPORT.md with Advisory Gate summary and findings."""
    gate = bpa_report.get("gate", {})
    summary = bpa_report.get("summary", {})
    sev_counts = summary.get("severityCounts", {})
    violations = bpa_report.get("violations", [])

    lines: list[str] = [
        f"# Best Practice Analyzer (BPA) Report — {pbip_name}",
        "",
        f"**Advisory Gate**: **{gate.get('status', 'PASS')}** (Fail threshold: Severity >= {gate.get('failSeverity', 3)})",
        "",
        "| Severity | Meaning | Count |",
        "| --- | --- | ---: |",
        f"| Severity 3 | Blocking Error | {sev_counts.get('3', 0)} |",
        f"| Severity 2 | Warning | {sev_counts.get('2', 0)} |",
        f"| Severity 1 | Informational | {sev_counts.get('1', 0)} |",
        f"| **Total** | | **{summary.get('totalViolations', 0)}** |",
        "",
        "## Rule Summary",
        "",
        "| Severity | Rule ID | Layer | Category | Rule Name | Count |",
        "| ---: | --- | --- | --- | --- | ---: |",
    ]
    for r in bpa_report.get("ruleSummary", []):
        lines.append(
            f"| {r['severity']} | `{r['ruleId']}` | {r['layer']} | {r['category']} | {_md_escape(r['ruleName'])} | {r['count']} |"
        )
    lines.append("")

    for sev, label in ((3, "Severity 3 — Blocking"), (2, "Severity 2 — Warnings"), (1, "Severity 1 — Informational")):
        subset = [v for v in violations if v["severity"] == sev]
        if not subset:
            continue
        lines.extend(
            [
                f"## {label} ({len(subset)})",
                "",
                "| Layer | Category | Rule | Object |",
                "| --- | --- | --- | --- |",
            ]
        )
        for v in subset:
            lines.append(
                f"| {v['layer']} | {v['category']} | `{v['ruleId']}` | {_md_escape(v['objectDisplay'])} |"
            )
        lines.append("")

    return "\n".join(lines)


def generate_pr_summary_md(
    pbip_name: str,
    model_meta: dict[str, Any],
    report_meta: dict[str, Any],
    bpa_report: dict[str, Any],
) -> str:
    """Generate dist/pr-summary.md designed for GitHub Actions PR sticky comments."""
    gate = bpa_report.get("gate", {})
    sev = bpa_report.get("summary", {}).get("severityCounts", {})
    tables = model_meta.get("tables", [])
    total_meas = sum(len(t.get("measures", [])) for t in tables)

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pages_link = ""
    if "/" in repo:
        owner, name = repo.split("/", 1)
        pages_link = f"https://{owner}.github.io/{name}/"

    status_icon = "✅ PASS" if gate.get("passed") else "❌ FAIL"
    lines: list[str] = [
        f"## Power BI PBIP CI Summary — `{pbip_name}`",
        "",
        f"**Advisory Gate**: **{status_icon}** (blocks only on Severity >= {gate.get('failSeverity', 3)})",
        "",
        "| Tables | Measures | Pages | Visuals | S3 Errors | S2 Warnings | S1 Info |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {len(tables)} | {total_meas} | {len(report_meta.get('pages', []))} | {report_meta.get('totalVisuals', 0)} | {sev.get('3', 0)} | {sev.get('2', 0)} | {sev.get('1', 0)} |",
        "",
    ]

    if pages_link:
        lines.append(f"📊 **Published main portal (not this PR preview)**: [{pages_link}]({pages_link})")
        lines.append("")

    top_rules = bpa_report.get("ruleSummary", [])[:8]
    if top_rules:
        lines.extend(
            [
                "### Top BPA Rules Triggered",
                "",
                "| Severity | Rule | Hits |",
                "| ---: | --- | ---: |",
            ]
        )
        for r in top_rules:
            lines.append(f"| {r['severity']} | {_md_escape(r['ruleName'])} | {r['count']} |")
        lines.append("")

    lines.append("_Generated automatically by `pbi-cicd` (Tabular Editor 2 + PBIR/TMDL analyzer)._")
    return "\n".join(lines)

