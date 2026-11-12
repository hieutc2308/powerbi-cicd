"""BPA violation parser, cross-layer PBIR/PBIP rule engine, and Advisory Gate evaluator."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

# Pattern matching Tabular Editor CLI -AX -G lines with optional ::error:: or ::warning:: prefix.
_TE2_LINE_RE = re.compile(
    r'^(?P<prefix>::(?P<level>error|warning)::\s*)?(?P<object>.+?)\s+violates rule\s+"(?P<rule>.+)"\s*$'
)
_TE2_ERR_RE = re.compile(r"^::error::\s*Error on rule\s+'(?P<rule>[^']+)':\s*(?P<msg>.+)$")


def load_bpa_rules_catalog(rules_path: Path) -> dict[str, dict[str, Any]]:
    """Load BPA rule definitions indexed by rule Name."""
    if not rules_path.exists():
        return {}
    rules = json.loads(rules_path.read_text(encoding="utf-8-sig"))
    return {r["Name"]: r for r in rules if isinstance(r, dict) and r.get("Name")}


def _classify_te2_object(raw_obj: str) -> tuple[str, str]:
    """Extract normalized (objectType, objectName) from a TE2 BPA object label."""
    s = raw_obj.strip()
    if s.startswith("Measure [") and s.endswith("]"):
        return "Measure", s[len("Measure ") :].strip("[]")
    if s.startswith("Column "):
        return "Column", s[len("Column ") :]
    if s.startswith("Calculated Table "):
        return "Table", s[len("Calculated Table ") :].strip("'")
    if s.startswith("Table "):
        return "Table", s[len("Table ") :].strip("'")
    if s.startswith("Relationship "):
        return "Relationship", s[len("Relationship ") :]
    if s.startswith("Expression "):
        return "NamedExpression", s[len("Expression ") :].strip()
    if s.startswith("Model "):
        return "Model", "Model"
    return "ModelObject", s


def parse_te2_bpa_output(
    bpa_txt_path: Path,
    rules_by_name: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse dist/te2-bpa.txt (-AX -G) into structured violations and rule evaluation errors."""
    if not bpa_txt_path.exists():
        return [], []

    violations: list[dict[str, Any]] = []
    rule_errors: list[dict[str, Any]] = []

    for line in bpa_txt_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        err_match = _TE2_ERR_RE.match(text)
        if err_match:
            rule_name = err_match.group("rule")
            rule_errors.append(
                {
                    "ruleName": rule_name,
                    "message": err_match.group("msg"),
                }
            )
            continue

        m = _TE2_LINE_RE.match(text)
        if not m:
            continue

        level = (m.group("level") or "").lower()
        severity = 3 if level == "error" else (2 if level == "warning" else 1)
        rule_name = m.group("rule")
        rule_meta = rules_by_name.get(rule_name, {})
        obj_raw = m.group("object").strip()
        obj_type, obj_name = _classify_te2_object(obj_raw)

        violations.append(
            {
                "ruleId": rule_meta.get("ID", _slugify_rule(rule_name)),
                "ruleName": rule_name,
                "category": rule_meta.get("Category", "Tabular Editor BPA"),
                "description": rule_meta.get("Description", ""),
                "severity": int(rule_meta.get("Severity", severity)),
                "layer": "SemanticModel",
                "objectType": obj_type,
                "objectName": obj_name,
                "objectDisplay": obj_raw,
            }
        )
    return violations, rule_errors


def _slugify_rule(name: str) -> str:
    """Create a stable uppercase ID fallback when a rule is missing from config."""
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def _check_runtime_cache_committed(root_dir: Path, project_scope: Path | None = None) -> list[dict[str, Any]]:
    """Detect whether Power BI Desktop runtime .pbi cache artifacts are tracked in Git."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "*.pbi/*", "**/.pbi/*", "*.abf"],
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if proc.returncode != 0:
        return []
    tracked = [line.strip() for line in proc.stdout.splitlines() if line.strip() and not line.endswith("editorSettings.json")]
    findings: list[dict[str, Any]] = []
    for path in tracked:
        if project_scope is not None and not (root_dir / path).resolve().is_relative_to(project_scope.resolve()):
            continue
        if "/.pbi/" in f"/{path}" and (path.endswith("localSettings.json") or path.endswith("cache.abf") or path.endswith(".abf")):
            findings.append(
                {
                    "ruleId": "PBIP_RUNTIME_CACHE_COMMITTED",
                    "ruleName": "[PBIP Hygiene] Runtime .pbi cache/localSettings must not be committed",
                    "category": "PBIP Hygiene",
                    "description": "Power BI Desktop runtime files (.pbi/localSettings.json, *.abf) cause noisy diffs and bloat the repo.",
                    "severity": 3,
                    "layer": "PBIP",
                    "objectType": "File",
                    "objectName": path,
                    "objectDisplay": path,
                }
            )
    return findings


def _compute_used_measures(
    directly_used_measures: set[str],
    measure_deps: dict[str, set[str]],
) -> set[str]:
    """Transitively collect helper measures referenced by visuals or other used measures."""
    visited: set[str] = set()
    stack = list(directly_used_measures)
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for dep in measure_deps.get(current, ()):
            if dep not in visited:
                stack.append(dep)
    return visited


def run_cross_layer_checks(
    root_dir: Path,
    model_meta: dict[str, Any],
    report_meta: dict[str, Any],
    project_scope: Path | None = None,
) -> list[dict[str, Any]]:
    """Evaluate cross-layer PBIR/SemanticModel integrity and unused object rules."""
    findings: list[dict[str, Any]] = []

    tables_by_name: dict[str, dict[str, Any]] = {t["name"]: t for t in model_meta.get("tables", [])}
    valid_columns: set[tuple[str, str]] = set()
    all_measures: dict[str, dict[str, Any]] = {}
    visible_measures: list[tuple[str, dict[str, Any]]] = []
    measure_deps: dict[str, set[str]] = {}
    tables_used_by_dax: set[str] = set()

    for tbl in model_meta.get("tables", []):
        t_name = tbl["name"]
        for col in tbl.get("columns", []):
            valid_columns.add((t_name, col["name"]))
            for dep in col.get("dependsOn", []):
                if dep.get("table"):
                    tables_used_by_dax.add(dep["table"])
        for meas in tbl.get("measures", []):
            m_name = meas["name"]
            all_measures[m_name] = {**meas, "table": t_name}
            if not tbl.get("isHidden") and not meas.get("isHidden"):
                visible_measures.append((t_name, meas))
            deps_set: set[str] = set()
            for dep in meas.get("dependsOn", []):
                if dep.get("objectType") == "Measure" and dep.get("name"):
                    deps_set.add(dep["name"])
                if dep.get("table"):
                    tables_used_by_dax.add(dep["table"])
            measure_deps[m_name] = deps_set

    directly_used_measures: set[str] = set()
    used_tables: set[str] = set()
    seen_broken: set[tuple[str, str, str, str]] = set()

    for ref in report_meta.get("allFieldRefs", []):
        kind = ref["kind"]
        t_name = ref["table"]
        field_name = ref["name"]
        location = f"{ref.get('pageName', '')} / {ref.get('visualTitle') or ref.get('usage', '')}".strip(" /")

        if kind == "Measure":
            if field_name not in all_measures:
                key = ("Measure", t_name, field_name, ref.get("visualId") or location)
                if key not in seen_broken:
                    seen_broken.add(key)
                    findings.append(
                        {
                            "ruleId": "PBIR_BROKEN_FIELD_REF",
                            "ruleName": "[Cross-Layer] Visual/filter references missing semantic model measure or column",
                            "category": "Cross-Layer Integrity",
                            "description": "PBIR visual or filter binds to a column or measure missing from the SemanticModel.",
                            "severity": 3,
                            "layer": "Report",
                            "objectType": "Visual",
                            "objectName": f"{location} -> [{field_name}]",
                            "objectDisplay": f"{location} -> [{field_name}]",
                        }
                    )
            else:
                directly_used_measures.add(field_name)
                used_tables.add(all_measures[field_name]["table"])
        elif kind == "Column":
            if (t_name, field_name) not in valid_columns:
                # Some PBIR visuals reference Table[Measure] using Column node syntax in older schemas.
                if t_name in tables_by_name and field_name in all_measures:
                    directly_used_measures.add(field_name)
                    used_tables.add(t_name)
                    continue
                key = ("Column", t_name, field_name, ref.get("visualId") or location)
                if key not in seen_broken:
                    seen_broken.add(key)
                    findings.append(
                        {
                            "ruleId": "PBIR_BROKEN_FIELD_REF",
                            "ruleName": "[Cross-Layer] Visual/filter references missing semantic model measure or column",
                            "category": "Cross-Layer Integrity",
                            "description": "PBIR visual or filter binds to a column or measure missing from the SemanticModel.",
                            "severity": 3,
                            "layer": "Report",
                            "objectType": "Visual",
                            "objectName": f"{location} -> '{t_name}'[{field_name}]",
                            "objectDisplay": f"{location} -> '{t_name}'[{field_name}]",
                        }
                    )
            else:
                used_tables.add(t_name)

    used_measures = _compute_used_measures(directly_used_measures, measure_deps)
    for m_name in used_measures:
        m_info = all_measures.get(m_name)
        if m_info:
            for dep in m_info.get("dependsOn", []):
                if dep.get("table"):
                    used_tables.add(dep["table"])

    for t_name, meas in visible_measures:
        m_name = meas["name"]
        if m_name not in used_measures:
            findings.append(
                {
                    "ruleId": "PBIR_UNUSED_MEASURE",
                    "ruleName": "[Cross-Layer] Visible measure is not used by any report visual or downstream measure",
                    "category": "Maintenance",
                    "description": "Measures orphaned from both PBIR visuals/filters and downstream DAX calculations add clutter.",
                    "severity": 2,
                    "layer": "Cross-Layer",
                    "objectType": "Measure",
                    "objectName": m_name,
                    "objectDisplay": f"Measure [{m_name}] ({t_name})",
                }
            )

    # Expand used tables along active relationships and DAX dependencies.
    rel_neighbors: dict[str, set[str]] = {}
    for rel in model_meta.get("relationships", []):
        f_t, t_t = rel.get("fromTable", ""), rel.get("toTable", "")
        if f_t and t_t:
            rel_neighbors.setdefault(f_t, set()).add(t_t)
            rel_neighbors.setdefault(t_t, set()).add(f_t)
    stack = list(used_tables | tables_used_by_dax)
    reachable_tables: set[str] = set()
    while stack:
        cur = stack.pop()
        if cur in reachable_tables:
            continue
        reachable_tables.add(cur)
        for nxt in rel_neighbors.get(cur, ()):
            if nxt not in reachable_tables:
                stack.append(nxt)

    for tbl in model_meta.get("tables", []):
        t_name = tbl["name"]
        if not tbl.get("isHidden") and t_name not in reachable_tables:
            findings.append(
                {
                    "ruleId": "PBIR_UNUSED_TABLE",
                    "ruleName": "[Cross-Layer] Visible table has no columns or measures referenced by report or model DAX",
                    "category": "Maintenance",
                    "description": "Unreferenced visible tables inflate model size and confuse self-service report authors.",
                    "severity": 2,
                    "layer": "Cross-Layer",
                    "objectType": "Table",
                    "objectName": t_name,
                    "objectDisplay": f"Table '{t_name}'",
                }
            )

    findings.extend(_check_runtime_cache_committed(root_dir, project_scope))
    return findings


def analyze_bpa(
    root_dir: Path,
    config: dict[str, Any],
    model_meta: dict[str, Any],
    report_meta: dict[str, Any],
    bpa_txt_path: Path | None,
    project_scope: Path | None = None,
) -> dict[str, Any]:
    """Combine TE2 BPA results and cross-layer checks, then evaluate the Advisory Gate."""
    bpa_cfg = config.get("bpa", {})
    rules_path = root_dir / bpa_cfg.get("rules_file", "config/bpa-rules.json")
    rules_by_name = load_bpa_rules_catalog(rules_path)
    ignored_ids = set(bpa_cfg.get("ignored_rule_ids", []))
    overrides = {str(k): int(v) for k, v in bpa_cfg.get("severity_overrides", {}).items()}
    fail_severity = int(bpa_cfg.get("fail_severity", 3))

    te2_violations: list[dict[str, Any]] = []
    te2_rule_errors: list[dict[str, Any]] = []
    if bpa_txt_path and bpa_txt_path.exists():
        te2_violations, te2_rule_errors = parse_te2_bpa_output(bpa_txt_path, rules_by_name)

    cross_violations = run_cross_layer_checks(root_dir, model_meta, report_meta, project_scope)
    combined = te2_violations + cross_violations

    final_violations: list[dict[str, Any]] = []
    for item in combined:
        rid = item["ruleId"]
        if rid in ignored_ids:
            continue
        if rid in overrides:
            item = {**item, "severity": overrides[rid]}
        final_violations.append(item)

    final_violations.sort(key=lambda x: (-x["severity"], x["category"], x["ruleId"], x["objectDisplay"]))

    severity_counts = {"3": 0, "2": 0, "1": 0}
    category_counts: dict[str, int] = {}
    rule_summary: dict[str, dict[str, Any]] = {}

    for v in final_violations:
        sev_key = str(v["severity"])
        severity_counts[sev_key] = severity_counts.get(sev_key, 0) + 1
        cat = v["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        rid = v["ruleId"]
        if rid not in rule_summary:
            rule_summary[rid] = {
                "ruleId": rid,
                "ruleName": v["ruleName"],
                "category": cat,
                "severity": v["severity"],
                "layer": v["layer"],
                "count": 0,
            }
        rule_summary[rid]["count"] += 1

    blocking_count = sum(1 for v in final_violations if v["severity"] >= fail_severity)
    passed = blocking_count == 0 and len(te2_rule_errors) == 0

    return {
        "gate": {
            "mode": "advisory",
            "failSeverity": fail_severity,
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
            "blockingCount": blocking_count,
            "ruleErrorCount": len(te2_rule_errors),
        },
        "summary": {
            "totalViolations": len(final_violations),
            "severityCounts": severity_counts,
            "byCategory": dict(sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "totalRulesCatalog": len(rules_by_name),
        },
        "ruleSummary": sorted(rule_summary.values(), key=lambda r: (-r["severity"], -r["count"], r["ruleId"])),
        "ruleErrors": te2_rule_errors,
        "violations": final_violations,
    }

