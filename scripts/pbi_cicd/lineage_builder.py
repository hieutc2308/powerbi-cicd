"""End-to-end 4-tier lineage DAG builder connecting Data Sources -> PQ -> Model -> Report."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def _safe_id(prefix: str, name: str) -> str:
    """Create a stable deterministic node ID for DAG nodes."""
    return f"{prefix}:{name}"


def _build_bpa_index(bpa_report: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index BPA violations by (objectType, objectName) for quick attachment to DAG nodes."""
    idx: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for v in bpa_report.get("violations", []):
        idx[(v["objectType"], v["objectName"])].append(
            {
                "ruleId": v["ruleId"],
                "ruleName": v["ruleName"],
                "severity": v["severity"],
                "category": v["category"],
            }
        )
    return idx


def build_lineage_graph(
    model_meta: dict[str, Any],
    report_meta: dict[str, Any],
    bpa_report: dict[str, Any],
) -> dict[str, Any]:
    """Construct the 4-tier lineage graph JSON consumed by docs and the interactive HTML portal."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    bpa_index = _build_bpa_index(bpa_report)

    def add_node(node: dict[str, Any]) -> None:
        nid = node["id"]
        if nid not in nodes:
            nodes[nid] = node

    def add_edge(src: str, tgt: str, edge_type: str, label: str = "") -> None:
        if src == tgt or src not in nodes or tgt not in nodes:
            return
        key = (src, tgt, edge_type)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "type": edge_type, "label": label})

    # Tier 0 & Tier 1: NamedExpressions and their upstream external/inline data sources.
    for expr in model_meta.get("expressions", []):
        e_name = expr["name"]
        pq_id = _safe_id("pq", e_name)
        pq_bpa = bpa_index.get(("NamedExpression", e_name), [])
        add_node(
            {
                "id": pq_id,
                "tier": 1,
                "kind": "pq",
                "label": e_name,
                "subtitle": f"M Query ({expr.get('queryGroup') or 'Default'})",
                "expression": expr.get("expression", ""),
                "transformations": expr.get("transformations", []),
                "bpa": pq_bpa,
            }
        )
        for src in expr.get("sources", []):
            src_key = f"{src['sourceKind']}::{src['location']}"
            src_id = _safe_id("src", src_key)
            short_loc = src["location"].replace("\\", "/").split("/")[-1] or src["location"]
            add_node(
                {
                    "id": src_id,
                    "tier": 0,
                    "kind": "source",
                    "label": short_loc,
                    "subtitle": src["sourceKind"],
                    "connector": src["connector"],
                    "location": src["location"],
                    "isLocalPath": src.get("isLocalPath", False),
                    "bpa": [],
                }
            )
            add_edge(src_id, pq_id, "SOURCE_TO_PQ", src["connector"])

    for expr in model_meta.get("expressions", []):
        pq_id = _safe_id("pq", expr["name"])
        for ref_name in expr.get("referencedExpressions", []):
            ref_id = _safe_id("pq", ref_name)
            add_edge(ref_id, pq_id, "PQ_REF", "M reference")

    # Tier 2a: Semantic Model Tables (plus direct partition/calculated sources & PQ edges).
    measure_name_to_id: dict[str, str] = {}
    table_names = {t["name"] for t in model_meta.get("tables", [])}

    for tbl in model_meta.get("tables", []):
        t_name = tbl["name"]
        tbl_id = _safe_id("tbl", t_name)
        tbl_bpa = list(bpa_index.get(("Table", t_name), []))
        for col in tbl.get("columns", []):
            tbl_bpa.extend(bpa_index.get(("Column", f"'{t_name}'[{col['name']}]"), []))
            tbl_bpa.extend(bpa_index.get(("Column", f"{t_name}[{col['name']}]"), []))

        is_calc = tbl.get("tableType") == "CalculatedTable"
        calc_kind = tbl.get("calculatedTableKind", "")
        subtitle = calc_kind if is_calc and calc_kind else f"Table ({len(tbl.get('columns', []))} cols, {len(tbl.get('measures', []))} measures)"

        add_node(
            {
                "id": tbl_id,
                "tier": 2,
                "kind": "table",
                "label": t_name,
                "subtitle": subtitle,
                "isHidden": bool(tbl.get("isHidden", False)),
                "tableType": tbl.get("tableType", "Table"),
                "columnCount": len(tbl.get("columns", [])),
                "measureCount": len(tbl.get("measures", [])),
                "partitions": tbl.get("partitions", []),
                "columns": [
                    {
                        "name": c["name"],
                        "dataType": c.get("dataType", ""),
                        "columnType": c.get("columnType", "Data"),
                        "isHidden": bool(c.get("isHidden", False)),
                        "formatString": c.get("formatString", ""),
                        "expression": c.get("expression", ""),
                    }
                    for c in tbl.get("columns", [])
                ],
                "bpa": tbl_bpa,
            }
        )

        # Link NamedExpressions -> Table
        for pq_ref in tbl.get("mExpressionRefs", []):
            add_edge(_safe_id("pq", pq_ref), tbl_id, "M_REF", "Partition source")

        # Link direct M sources (e.g., DateTimeZone.UtcNow or inline #table on Measure table)
        for src in tbl.get("directSources", []):
            src_key = f"{src['sourceKind']}::{src['location']}"
            src_id = _safe_id("src", src_key)
            add_node(
                {
                    "id": src_id,
                    "tier": 0,
                    "kind": "source",
                    "label": src["location"] if len(src["location"]) < 36 else src["connector"],
                    "subtitle": src["sourceKind"],
                    "connector": src["connector"],
                    "location": src["location"],
                    "isLocalPath": src.get("isLocalPath", False),
                    "bpa": [],
                }
            )
            add_edge(src_id, tbl_id, "SOURCE_TO_TABLE", src["connector"])

        # Calculated tables without upstream table references get an inline Tier 0 origin node.
        if is_calc and not tbl.get("mExpressionRefs") and not tbl.get("directSources"):
            # Check if partition DAX depends on other tables (e.g., DimCalendar uses FactActivity_Events).
            calc_expr = " ".join(p.get("expression", "") for p in tbl.get("partitions", []))
            referenced_tables = [other for other in table_names if other != t_name and other in calc_expr]
            if referenced_tables:
                for other in referenced_tables:
                    add_edge(_safe_id("tbl", other), tbl_id, "CALC_TABLE_DEP", "CALENDAR / DAX")
            else:
                src_key = f"{calc_kind or 'DAX'}::{t_name}"
                src_id = _safe_id("src", src_key)
                add_node(
                    {
                        "id": src_id,
                        "tier": 0,
                        "kind": "source",
                        "label": f"{t_name} (DATATABLE)" if "DATATABLE" in calc_kind else t_name,
                        "subtitle": calc_kind or "DAX Inline Table",
                        "connector": "DAX",
                        "location": "Model Definition (TMDL)",
                        "isLocalPath": False,
                        "bpa": [],
                    }
                )
                add_edge(src_id, tbl_id, "SOURCE_TO_TABLE", "DATATABLE")

    # Calculated column cross-table DAX dependencies (e.g., RELATED).
    for tbl in model_meta.get("tables", []):
        t_name = tbl["name"]
        tbl_id = _safe_id("tbl", t_name)
        for col in tbl.get("columns", []):
            for dep in col.get("dependsOn", []):
                dep_tbl = dep.get("table")
                if dep_tbl and dep_tbl != t_name and dep_tbl in table_names:
                    add_edge(_safe_id("tbl", dep_tbl), tbl_id, "DAX_COL_DEP", f"Column [{col['name']}]")

    # Relationships between Semantic Model Tables.
    for rel in model_meta.get("relationships", []):
        f_t = rel.get("fromTable", "")
        t_t = rel.get("toTable", "")
        if f_t in table_names and t_t in table_names:
            rel_label = f"{rel.get('fromColumn', '')} -> {rel.get('toColumn', '')}"
            add_edge(_safe_id("tbl", f_t), _safe_id("tbl", t_t), "REL", rel_label)

    # Tier 2b: Measures and their DAX dependencies.
    for tbl in model_meta.get("tables", []):
        t_name = tbl["name"]
        for meas in tbl.get("measures", []):
            m_name = meas["name"]
            m_id = _safe_id("meas", m_name)
            measure_name_to_id[m_name] = m_id
            m_bpa = bpa_index.get(("Measure", m_name), [])
            add_node(
                {
                    "id": m_id,
                    "tier": 2,
                    "kind": "measure",
                    "label": m_name,
                    "subtitle": f"Measure • {meas.get('displayFolder') or t_name}",
                    "table": t_name,
                    "displayFolder": meas.get("displayFolder", ""),
                    "formatString": meas.get("formatString", ""),
                    "description": meas.get("description", ""),
                    "expression": meas.get("expression", ""),
                    "isHidden": bool(meas.get("isHidden", False)),
                    "bpa": m_bpa,
                }
            )

    for tbl in model_meta.get("tables", []):
        for meas in tbl.get("measures", []):
            m_id = measure_name_to_id.get(meas["name"])
            if not m_id:
                continue
            for dep in meas.get("dependsOn", []):
                obj_type = dep.get("objectType", "")
                dep_name = dep.get("name", "")
                dep_tbl = dep.get("table", "")
                if obj_type == "Measure" and dep_name in measure_name_to_id:
                    add_edge(measure_name_to_id[dep_name], m_id, "DAX_DEP", "DAX [Measure]")
                elif dep_tbl and dep_tbl in table_names:
                    add_edge(_safe_id("tbl", dep_tbl), m_id, "TABLE_TO_MEASURE", dep.get("daxObjectFullName", ""))

    # Tier 3: Report Pages & Visuals.
    for page in report_meta.get("pages", []):
        p_id = page["id"]
        page_node_id = _safe_id("page", p_id)
        add_node(
            {
                "id": page_node_id,
                "tier": 3,
                "kind": "page",
                "label": page["displayName"],
                "subtitle": f"Report Page • {len(page.get('visuals', []))} visuals",
                "pageId": p_id,
                "visualCount": len(page.get("visuals", [])),
                "bpa": [],
            }
        )
        for ref in page.get("pageFilterRefs", []):
            _attach_pbir_ref_edge(ref, page_node_id, measure_name_to_id, table_names, add_edge)

        for vis in page.get("visuals", []):
            v_id = vis["id"]
            vis_node_id = _safe_id("vis", f"{p_id}/{v_id}")
            field_refs = vis.get("fieldRefs", [])
            vis_bpa = [
                v
                for v in bpa_report.get("violations", [])
                if v.get("objectType") == "Visual" and vis["title"] in v.get("objectName", "")
            ]
            add_node(
                {
                    "id": vis_node_id,
                    "tier": 3,
                    "kind": "visual",
                    "label": vis["title"],
                    "subtitle": f"{vis['visualType']} • {page['displayName']}",
                    "visualType": vis["visualType"],
                    "pageId": p_id,
                    "pageName": page["displayName"],
                    "isDataBound": len(field_refs) > 0,
                    "fieldRefs": field_refs,
                    "bpa": vis_bpa,
                }
            )
            add_edge(page_node_id, vis_node_id, "PAGE_CONTAINS", "")
            for ref in field_refs:
                _attach_pbir_ref_edge(ref, vis_node_id, measure_name_to_id, table_names, add_edge)

    # Precompute cycle-guarded upstream/downstream adjacency summary counts per node.
    adj_out: dict[str, list[str]] = defaultdict(list)
    adj_in: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["type"] in ("REL", "PAGE_CONTAINS"):
            continue
        adj_out[e["source"]].append(e["target"])
        adj_in[e["target"]].append(e["source"])

    node_list = list(nodes.values())
    for n in node_list:
        nid = n["id"]
        n["upstreamCount"] = len(_bfs_reachable(nid, adj_in))
        n["downstreamCount"] = len(_bfs_reachable(nid, adj_out))
        n["maxSeverity"] = max((b["severity"] for b in n.get("bpa", [])), default=0)

    tier_counts = {str(t): sum(1 for n in node_list if n["tier"] == t) for t in range(4)}
    return {
        "summary": {
            "totalNodes": len(node_list),
            "totalEdges": len(edges),
            "tierCounts": tier_counts,
            "dataBoundVisuals": sum(1 for n in node_list if n["kind"] == "visual" and n.get("isDataBound")),
            "decorativeVisuals": sum(1 for n in node_list if n["kind"] == "visual" and not n.get("isDataBound")),
        },
        "nodes": node_list,
        "edges": edges,
    }


def _attach_pbir_ref_edge(
    ref: dict[str, Any],
    target_node_id: str,
    measure_name_to_id: dict[str, str],
    table_names: set[str],
    add_edge: Any,
) -> None:
    """Create BIND_MEASURE or BIND_COLUMN edge from semantic model object to report node."""
    name = ref.get("name", "")
    t_name = ref.get("table", "")
    kind = ref.get("kind", "")
    usage = ref.get("usage", "query")

    if name in measure_name_to_id and (kind == "Measure" or t_name in table_names):
        add_edge(measure_name_to_id[name], target_node_id, "BIND_MEASURE", usage)
    elif t_name in table_names:
        add_edge(_safe_id("tbl", t_name), target_node_id, "BIND_COLUMN", f"{t_name}[{name}] ({usage})")


def _bfs_reachable(start: str, adj: dict[str, list[str]]) -> set[str]:
    """Cycle-safe BFS returning all reachable nodes excluding the start node."""
    visited: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in adj.get(cur, ()):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
    visited.discard(start)
    return visited

