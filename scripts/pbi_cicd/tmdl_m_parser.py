"""Parser for Tabular Editor TOM metadata, TMDL definitions, and Power Query M expressions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Regex patterns for Power Query M source functions and connectors.
_M_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("Local File", "File.Contents", re.compile(r'File\.Contents\s*\(\s*"([^"]+)"', re.IGNORECASE)),
    ("SharePoint", "SharePoint.Files/Tables", re.compile(r'SharePoint\.(?:Files|Tables|Contents)\s*\(\s*"([^"]+)"', re.IGNORECASE)),
    ("Web / REST API", "Web.Contents", re.compile(r'Web\.Contents\s*\(\s*"([^"]+)"', re.IGNORECASE)),
    ("SQL Server", "Sql.Database", re.compile(r'Sql\.Database\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', re.IGNORECASE)),
    ("Azure Data Lake", "AzureStorage.DataLake", re.compile(r'AzureStorage\.DataLake\s*\(\s*"([^"]+)"', re.IGNORECASE)),
    ("Fabric Lakehouse", "Lakehouse.Contents", re.compile(r'Lakehouse\.Contents\s*\(', re.IGNORECASE)),
    ("OData", "OData.Feed", re.compile(r'OData\.Feed\s*\(\s*"([^"]+)"', re.IGNORECASE)),
    ("System Clock (M)", "DateTimeZone.UtcNow / LocalNow", re.compile(r'DateTime(?:Zone)?\.(?:UtcNow|LocalNow)\s*\(', re.IGNORECASE)),
    ("Inline M Table", "#table", re.compile(r'#table\s*\(', re.IGNORECASE)),
]

# M transformation steps used to summarize query transformations in docs and lineage drawer.
_M_TRANSFORMS: list[str] = [
    "Csv.Document",
    "Excel.Workbook",
    "Json.Document",
    "Table.PromoteHeaders",
    "Table.TransformColumnTypes",
    "Table.SelectColumns",
    "Table.RemoveColumns",
    "Table.RenameColumns",
    "Table.SelectRows",
    "Table.AddColumn",
    "Table.TransformColumns",
    "Table.ExpandRecordColumn",
    "Table.ExpandTableColumn",
    "Table.NestedJoin",
    "Table.Join",
    "Table.Distinct",
    "Table.RemoveDuplicates",
    "Table.Group",
    "Table.Combine",
]


def extract_m_sources(expression: str) -> list[dict[str, Any]]:
    """Identify external/inline data sources referenced by a Power Query M expression."""
    if not expression:
        return []
    found: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for source_kind, connector, pattern in _M_PATTERNS:
        matches = list(pattern.finditer(expression))
        if not matches:
            continue
        if pattern.groups == 0:
            key = (source_kind, connector)
            if key not in seen_keys:
                seen_keys.add(key)
                found.append(
                    {
                        "sourceKind": source_kind,
                        "connector": connector,
                        "location": connector,
                        "isLocalPath": False,
                    }
                )
            continue
        for match in matches:
            location = " / ".join(g for g in match.groups() if g)
            is_local = bool(
                source_kind == "Local File"
                or re.search(r"^[A-Za-z]:[\\/]|^\\\\", location)
            )
            key = (source_kind, location)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            found.append(
                {
                    "sourceKind": source_kind,
                    "connector": connector,
                    "location": location,
                    "isLocalPath": is_local,
                }
            )
    return found


def extract_m_transformations(expression: str) -> list[str]:
    """Return ordered list of standard Power Query M functions present in an expression."""
    if not expression:
        return []
    return [fn for fn in _M_TRANSFORMS if fn in expression]


def find_m_expression_refs(partition_expr: str, expression_names: list[str]) -> list[str]:
    """Find NamedExpression identifiers referenced inside an M partition expression."""
    if not partition_expr or not expression_names:
        return []
    refs: list[str] = []
    for name in expression_names:
        # Match either bare identifier or M quoted #"Name" syntax.
        bare_pat = re.compile(rf'(?<![A-Za-z0-9_"]){re.escape(name)}(?![A-Za-z0-9_])')
        quoted_pat = re.compile(rf'#"{re.escape(name)}"')
        if bare_pat.search(partition_expr) or quoted_pat.search(partition_expr):
            refs.append(name)
    return refs


def classify_calculated_table_source(expression: str) -> str:
    """Classify the origin construct of a DAX calculated table."""
    upper = (expression or "").upper()
    if "CALENDARAUTO" in upper or "CALENDAR(" in upper or "CALENDAR (" in upper:
        return "DAX Calculated Calendar"
    if "DATATABLE" in upper:
        return "DAX Inline Table (DATATABLE)"
    if "GENERATESERIES" in upper:
        return "DAX Generated Series"
    return "DAX Calculated Table"


def _unquote_tmdl_name(raw: str) -> str:
    """Strip surrounding single quotes and unescape doubled quotes in a TMDL object name."""
    text = raw.strip()
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    return text


def parse_tmdl_fallback(semantic_model_dir: Path) -> dict[str, Any]:
    """Lightweight pure-Python TMDL parser used when te2-metadata.json is unavailable."""
    defn_dir = semantic_model_dir / "definition"
    expressions: list[dict[str, Any]] = []
    expr_file = defn_dir / "expressions.tmdl"
    if expr_file.exists():
        expressions = _parse_expressions_tmdl(expr_file.read_text(encoding="utf-8-sig"))

    relationships: list[dict[str, Any]] = []
    rel_file = defn_dir / "relationships.tmdl"
    if rel_file.exists():
        relationships = _parse_relationships_tmdl(rel_file.read_text(encoding="utf-8-sig"))

    tables: list[dict[str, Any]] = []
    tables_dir = defn_dir / "tables"
    if tables_dir.exists():
        for tmdl_path in sorted(tables_dir.glob("*.tmdl")):
            tables.append(_parse_table_tmdl(tmdl_path.read_text(encoding="utf-8-sig")))

    return {
        "model": {
            "name": "Model",
            "culture": "en-US",
            "compatibilityLevel": 1550,
            "annotationCount": 0,
        },
        "tables": tables,
        "relationships": relationships,
        "roles": [],
        "expressions": expressions,
    }


def _parse_expressions_tmdl(text: str) -> list[dict[str, Any]]:
    """Parse NamedExpression blocks from expressions.tmdl."""
    results: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*expression\s+('(?:''|[^'])+'|[^\s=]+)\s*=\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        name = _unquote_tmdl_name(m.group(1))
        inline = m.group(2).strip()
        expr_lines: list[str] = []
        if inline == "let":
            expr_lines.append("let")
            i += 1
            while i < len(lines) and (lines[i].startswith("\t\t") or lines[i].strip() == ""):
                expr_lines.append(lines[i].lstrip("\t"))
                i += 1
        else:
            expr_lines.append(inline)
            i += 1
        kind = "M"
        query_group = ""
        while i < len(lines) and not lines[i].startswith("expression "):
            stripped = lines[i].strip()
            if stripped.startswith("queryGroup:"):
                query_group = stripped.split(":", 1)[1].strip()
            i += 1
        results.append(
            {
                "name": name,
                "kind": kind,
                "expression": "\n".join(expr_lines).strip(),
                "description": "",
                "queryGroup": query_group,
                "lineageTag": "",
            }
        )
    return results


def _parse_relationships_tmdl(text: str) -> list[dict[str, Any]]:
    """Parse relationships from relationships.tmdl."""
    rels: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        m = re.match(r"^\s*relationship\s+(.+)$", line)
        if m:
            if current:
                rels.append(current)
            current = {
                "name": m.group(1).strip(),
                "fromTable": "",
                "fromColumn": "",
                "toTable": "",
                "toColumn": "",
                "isActive": True,
                "crossFilteringBehavior": "OneDirection",
                "fromCardinality": "Many",
                "toCardinality": "One",
            }
            continue
        if not current:
            continue
        stripped = line.strip()
        if stripped.startswith("fromColumn:"):
            t, c = _split_table_col(stripped.split(":", 1)[1])
            current["fromTable"], current["fromColumn"] = t, c
        elif stripped.startswith("toColumn:"):
            t, c = _split_table_col(stripped.split(":", 1)[1])
            current["toTable"], current["toColumn"] = t, c
        elif stripped.startswith("crossFilteringBehavior:"):
            val = stripped.split(":", 1)[1].strip()
            current["crossFilteringBehavior"] = "BothDirections" if "both" in val.lower() else "OneDirection"
        elif stripped.startswith("toCardinality:"):
            val = stripped.split(":", 1)[1].strip()
            current["toCardinality"] = "Many" if "many" in val.lower() else "One"
        elif stripped.startswith("fromCardinality:"):
            val = stripped.split(":", 1)[1].strip()
            current["fromCardinality"] = "Many" if "many" in val.lower() else "One"
        elif stripped.startswith("isActive:"):
            current["isActive"] = stripped.split(":", 1)[1].strip().lower() != "false"
    if current:
        rels.append(current)
    return rels


def _split_table_col(ref: str) -> tuple[str, str]:
    """Split a TMDL Table.Column or 'Table Name'.Column reference."""
    s = ref.strip()
    if s.startswith("'"):
        end_q = s.find("'.", 1)
        if end_q != -1:
            return _unquote_tmdl_name(s[: end_q + 1]), _unquote_tmdl_name(s[end_q + 2 :])
    if "." in s:
        t, c = s.split(".", 1)
        return _unquote_tmdl_name(t), _unquote_tmdl_name(c)
    return s, ""


def _parse_table_tmdl(text: str) -> dict[str, Any]:
    """Parse table columns, measures, and partitions from a single *.tmdl file."""
    lines = text.splitlines()
    table_name = "Unknown"
    for line in lines:
        m = re.match(r"^\s*table\s+(.+)$", line)
        if m:
            table_name = _unquote_tmdl_name(m.group(1))
            break

    columns: list[dict[str, Any]] = []
    measures: list[dict[str, Any]] = []
    partitions: list[dict[str, Any]] = []

    pending_doc: list[str] = []
    current_kind = ""
    current_obj: dict[str, Any] | None = None
    expr_buf: list[str] = []
    in_backticks = False

    def flush() -> None:
        nonlocal current_kind, current_obj, expr_buf
        if not current_obj:
            return
        if expr_buf and not current_obj.get("expression"):
            current_obj["expression"] = "\n".join(expr_buf).strip()
        if current_kind == "column":
            columns.append(current_obj)
        elif current_kind == "measure":
            measures.append(current_obj)
        elif current_kind == "partition":
            partitions.append(current_obj)
        current_kind = ""
        current_obj = None
        expr_buf = []

    for line in lines:
        stripped = line.strip()
        if in_backticks:
            if stripped == "```":
                in_backticks = False
            else:
                expr_buf.append(line.lstrip("\t"))
            continue

        if stripped.startswith("///"):
            pending_doc.append(stripped[3:].strip())
            continue

        col_m = re.match(r"^\tcolumn\s+('(?:''|[^'])+'|[^\s=]+)(?:\s*=\s*(.*))?$", line)
        if col_m:
            flush()
            cname = _unquote_tmdl_name(col_m.group(1))
            inline = (col_m.group(2) or "").strip()
            is_calc = "=" in line.split(col_m.group(1), 1)[1]
            current_kind = "column"
            current_obj = {
                "name": cname,
                "daxObjectFullName": f"'{table_name}'[{cname}]",
                "columnType": "Calculated" if is_calc else "Data",
                "dataType": "Unknown",
                "isHidden": False,
                "displayFolder": "",
                "formatString": "",
                "summarizeBy": "Default",
                "description": "\n".join(pending_doc).strip(),
                "expression": "" if inline == "```" else inline,
                "dependsOn": [],
            }
            if inline == "```":
                in_backticks = True
            pending_doc = []
            continue

        meas_m = re.match(r"^\tmeasure\s+('(?:''|[^'])+'|[^\s=]+)\s*=\s*(.*)$", line)
        if meas_m:
            flush()
            mname = _unquote_tmdl_name(meas_m.group(1))
            inline = meas_m.group(2).strip()
            current_kind = "measure"
            current_obj = {
                "name": mname,
                "daxObjectFullName": f"[{mname}]",
                "expression": "" if inline == "```" else inline,
                "description": "\n".join(pending_doc).strip(),
                "displayFolder": "",
                "formatString": "",
                "isHidden": False,
                "dataCategory": "",
                "dependsOn": [],
            }
            if inline == "```":
                in_backticks = True
            pending_doc = []
            continue

        part_m = re.match(r"^\tpartition\s+('(?:''|[^'])+'|[^\s=]+)\s*=\s*(.+)$", line)
        if part_m:
            flush()
            pname = _unquote_tmdl_name(part_m.group(1))
            ptype = part_m.group(2).strip()
            current_kind = "partition"
            current_obj = {
                "name": pname,
                "sourceType": "Calculated" if ptype.lower() == "calculated" else "M",
                "mode": "Import",
                "expression": "",
                "queryGroup": "",
            }
            pending_doc = []
            continue

        if current_obj is None:
            pending_doc = []
            continue

        if stripped.startswith("source ="):
            rhs = stripped.split("=", 1)[1].strip()
            if rhs == "```":
                in_backticks = True
            else:
                expr_buf.append(rhs)
        elif line.startswith("\t\t\t") and current_kind in ("measure", "column", "partition"):
            expr_buf.append(line.lstrip("\t"))
        elif stripped.startswith("dataType:"):
            current_obj["dataType"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("formatString:"):
            current_obj["formatString"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("displayFolder:"):
            current_obj["displayFolder"] = stripped.split(":", 1)[1].strip()
        elif stripped == "isHidden":
            current_obj["isHidden"] = True
        elif stripped.startswith("summarizeBy:"):
            current_obj["summarizeBy"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("mode:"):
            current_obj["mode"] = stripped.split(":", 1)[1].strip().capitalize()

    flush()
    return {
        "name": table_name,
        "isHidden": False,
        "description": "",
        "dataCategory": "",
        "tableType": "CalculatedTable"
        if any(p.get("sourceType") == "Calculated" for p in partitions)
        else "Table",
        "partitions": partitions,
        "columns": columns,
        "measures": measures,
    }


def load_semantic_model(semantic_model_dir: Path, metadata_json_path: Path | None = None) -> dict[str, Any]:
    """Load semantic model metadata from TE2 JSON (preferred) or TMDL fallback, and enrich M/DAX lineage."""
    if metadata_json_path and metadata_json_path.exists():
        raw = json.loads(metadata_json_path.read_text(encoding="utf-8-sig"))
        source_mode = "te2"
    else:
        raw = parse_tmdl_fallback(semantic_model_dir)
        source_mode = "tmdl_fallback"

    expressions = raw.get("expressions", [])
    expr_names = [e["name"] for e in expressions if e.get("name")]

    enriched_expressions: list[dict[str, Any]] = []
    for expr in expressions:
        m_code = expr.get("expression", "")
        enriched_expressions.append(
            {
                **expr,
                "sources": extract_m_sources(m_code),
                "transformations": extract_m_transformations(m_code),
                "referencedExpressions": [
                    ref for ref in find_m_expression_refs(m_code, expr_names) if ref != expr.get("name")
                ],
            }
        )

    enriched_tables: list[dict[str, Any]] = []
    for tbl in raw.get("tables", []):
        partitions = tbl.get("partitions", [])
        table_expr_refs: list[str] = []
        table_direct_sources: list[dict[str, Any]] = []
        table_transforms: list[str] = []
        calc_table_kind = ""

        for part in partitions:
            p_expr = part.get("expression", "")
            p_type = part.get("sourceType", "")
            if p_type == "M":
                for ref in find_m_expression_refs(p_expr, expr_names):
                    if ref not in table_expr_refs:
                        table_expr_refs.append(ref)
                for src in extract_m_sources(p_expr):
                    if src not in table_direct_sources:
                        table_direct_sources.append(src)
                for tr in extract_m_transformations(p_expr):
                    if tr not in table_transforms:
                        table_transforms.append(tr)
            elif p_type == "Calculated":
                calc_table_kind = classify_calculated_table_source(p_expr)

        enriched_tables.append(
            {
                **tbl,
                "mExpressionRefs": table_expr_refs,
                "directSources": table_direct_sources,
                "mTransformations": table_transforms,
                "calculatedTableKind": calc_table_kind,
            }
        )

    return {
        "sourceMode": source_mode,
        "model": raw.get("model", {}),
        "expressions": enriched_expressions,
        "tables": enriched_tables,
        "relationships": raw.get("relationships", []),
        "roles": raw.get("roles", []),
    }

