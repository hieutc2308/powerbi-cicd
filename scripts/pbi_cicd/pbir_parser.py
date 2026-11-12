"""Parser for Power BI Enhanced Report Format (PBIR) pages, visuals, filters, and field bindings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _strip_dax_literal(val: Any) -> str:
    """Unwrap a PBIR Literal.Value string such as \"'Title Text'\"."""
    if not isinstance(val, str):
        return ""
    if len(val) >= 2 and val.startswith("'") and val.endswith("'"):
        return val[1:-1].replace("''", "'")
    return val


def _extract_visual_title(visual_obj: dict[str, Any], visual_id: str, visual_type: str) -> str:
    """Extract human-readable visual title from visualContainerObjects if defined."""
    vco = visual_obj.get("visualContainerObjects", {})
    title_entries = vco.get("title", [])
    if isinstance(title_entries, list):
        for entry in title_entries:
            props = entry.get("properties", {}) if isinstance(entry, dict) else {}
            lit = props.get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
            text = _strip_dax_literal(lit)
            if text:
                return text
    return f"{visual_type} ({visual_id[:8]})"


def _resolve_entity(expr_node: Any, alias_map: dict[str, str]) -> str:
    """Resolve Entity name from a PBIR Expression.SourceRef node using active From aliases."""
    if not isinstance(expr_node, dict):
        return ""
    src_ref = expr_node.get("SourceRef")
    if isinstance(src_ref, dict):
        if isinstance(src_ref.get("Entity"), str):
            return src_ref["Entity"]
        alias = src_ref.get("Source")
        if isinstance(alias, str) and alias in alias_map:
            return alias_map[alias]
    return ""


def _walk_pbir_expr(
    node: Any,
    alias_map: dict[str, str],
    context_label: str,
    refs: list[dict[str, str]],
    seen: set[tuple[str, str, str, str]],
) -> None:
    """Recursively traverse PBIR JSON nodes to collect bound Measure and Column references."""
    if isinstance(node, list):
        for item in node:
            _walk_pbir_expr(item, alias_map, context_label, refs, seen)
        return
    if not isinstance(node, dict):
        return

    # Extend alias scope whenever a Query / Subquery declares From bindings.
    local_aliases = alias_map
    from_list = node.get("From")
    if isinstance(from_list, list):
        local_aliases = dict(alias_map)
        for entry in from_list:
            if isinstance(entry, dict):
                alias_name = entry.get("Name")
                entity_name = entry.get("Entity")
                if isinstance(alias_name, str) and isinstance(entity_name, str):
                    local_aliases[alias_name] = entity_name

    for kind in ("Measure", "Column"):
        binding = node.get(kind)
        if isinstance(binding, dict):
            expr = binding.get("Expression")
            prop = binding.get("Property")
            # Dynamic textbox subqueries wrap an inner Measure/Column with a synthetic outer
            # Column referencing {"Subquery": ...}; recurse into the Subquery and skip the wrapper.
            if isinstance(expr, dict) and "Subquery" in expr:
                _walk_pbir_expr(expr["Subquery"], local_aliases, context_label, refs, seen)
            elif isinstance(prop, str):
                entity = _resolve_entity(expr, local_aliases)
                if entity:
                    key = (kind, entity, prop, context_label)
                    if key not in seen:
                        seen.add(key)
                        refs.append(
                            {
                                "kind": kind,
                                "table": entity,
                                "name": prop,
                                "usage": context_label,
                            }
                        )

    for key, val in node.items():
        if key in ("From", "Measure", "Column"):
            if key in ("Measure", "Column") and isinstance(val, dict):
                # Also inspect nested expressions (e.g., Aggregation or Filter wrappers).
                _walk_pbir_expr(val.get("Expression"), local_aliases, context_label, refs, seen)
            continue
        _walk_pbir_expr(val, local_aliases, context_label, refs, seen)


def _extract_visual_refs(visual_json: dict[str, Any]) -> list[dict[str, str]]:
    """Extract all semantic model Measure/Column references bound by a visual."""
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    visual = visual_json.get("visual", {})

    _walk_pbir_expr(visual.get("query", {}).get("queryState"), {}, "query", refs, seen)
    _walk_pbir_expr(visual.get("query", {}).get("sortDefinition"), {}, "sort", refs, seen)
    _walk_pbir_expr(visual.get("objects"), {}, "visualObject", refs, seen)
    _walk_pbir_expr(visual.get("visualContainerObjects"), {}, "containerObject", refs, seen)
    _walk_pbir_expr(visual_json.get("filterConfig"), {}, "visualFilter", refs, seen)
    return refs


def parse_pbir_report(report_dir: Path) -> dict[str, Any]:
    """Parse all pages, visuals, filters, and bookmarks from a PBIR Report/definition folder."""
    defn_dir = report_dir / "definition"
    pages_dir = defn_dir / "pages"
    pages_meta_path = pages_dir / "pages.json"

    page_order: list[str] = []
    active_page = ""
    if pages_meta_path.exists():
        pages_meta = json.loads(pages_meta_path.read_text(encoding="utf-8-sig"))
        page_order = pages_meta.get("pageOrder", [])
        active_page = pages_meta.get("activePageName", "")

    discovered_dirs = {p.name: p for p in pages_dir.iterdir() if p.is_dir()} if pages_dir.exists() else {}
    ordered_ids = [pid for pid in page_order if pid in discovered_dirs]
    for pid in sorted(discovered_dirs):
        if pid not in ordered_ids:
            ordered_ids.append(pid)

    pages: list[dict[str, Any]] = []
    all_field_refs: list[dict[str, Any]] = []
    visual_type_counts: dict[str, int] = {}

    for page_id in ordered_ids:
        p_dir = discovered_dirs[page_id]
        page_json_path = p_dir / "page.json"
        page_json = json.loads(page_json_path.read_text(encoding="utf-8-sig")) if page_json_path.exists() else {}
        page_name = page_json.get("displayName") or page_json.get("name") or page_id

        page_filter_refs: list[dict[str, str]] = []
        _walk_pbir_expr(page_json.get("filterConfig"), {}, "pageFilter", page_filter_refs, set())
        for ref in page_filter_refs:
            all_field_refs.append({**ref, "pageId": page_id, "pageName": page_name, "visualId": "", "visualTitle": ""})

        visuals: list[dict[str, Any]] = []
        visuals_dir = p_dir / "visuals"
        if visuals_dir.exists():
            for v_dir in sorted(visuals_dir.iterdir()):
                v_file = v_dir / "visual.json"
                if not v_file.exists():
                    continue
                v_json = json.loads(v_file.read_text(encoding="utf-8-sig"))
                v_obj = v_json.get("visual", {})
                v_type = v_obj.get("visualType", "unknown")
                v_id = v_json.get("name") or v_dir.name
                v_title = _extract_visual_title(v_obj, v_id, v_type)
                visual_type_counts[v_type] = visual_type_counts.get(v_type, 0) + 1

                refs = _extract_visual_refs(v_json)
                for ref in refs:
                    all_field_refs.append(
                        {
                            **ref,
                            "pageId": page_id,
                            "pageName": page_name,
                            "visualId": v_id,
                            "visualTitle": v_title,
                        }
                    )

                visuals.append(
                    {
                        "id": v_id,
                        "title": v_title,
                        "visualType": v_type,
                        "pageId": page_id,
                        "pageName": page_name,
                        "position": v_json.get("position", {}),
                        "parentGroupName": v_json.get("parentGroupName", ""),
                        "isHidden": bool(v_json.get("isHidden", False)),
                        "fieldRefs": refs,
                    }
                )

        pages.append(
            {
                "id": page_id,
                "displayName": page_name,
                "width": page_json.get("width", 1280),
                "height": page_json.get("height", 720),
                "isHidden": page_json.get("visibility") == "HiddenInViewMode",
                "pageFilterRefs": page_filter_refs,
                "visuals": visuals,
            }
        )

    report_json_path = defn_dir / "report.json"
    report_filter_refs: list[dict[str, str]] = []
    if report_json_path.exists():
        report_json = json.loads(report_json_path.read_text(encoding="utf-8-sig"))
        _walk_pbir_expr(report_json.get("filterConfig"), {}, "reportFilter", report_filter_refs, set())
        for ref in report_filter_refs:
            all_field_refs.append({**ref, "pageId": "", "pageName": "Report Filter", "visualId": "", "visualTitle": ""})

    bookmarks_file = defn_dir / "bookmarks" / "bookmarks.json"
    bookmarks: list[dict[str, str]] = []
    if bookmarks_file.exists():
        b_meta = json.loads(bookmarks_file.read_text(encoding="utf-8-sig"))
        for item in b_meta.get("items", []):
            if isinstance(item, dict) and item.get("name"):
                bookmarks.append({"name": item["name"], "displayName": item.get("displayName", item["name"])})

    return {
        "reportName": report_dir.name,
        "activePageId": active_page,
        "pages": pages,
        "bookmarks": bookmarks,
        "reportFilterRefs": report_filter_refs,
        "allFieldRefs": all_field_refs,
        "visualTypeCounts": dict(sorted(visual_type_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "totalVisuals": sum(len(p["visuals"]) for p in pages),
    }

