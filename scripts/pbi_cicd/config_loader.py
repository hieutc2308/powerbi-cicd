"""Project discovery and configuration loading utilities for pbi_cicd."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved filesystem paths for a PBIP project and CI/CD outputs."""

    root: Path
    pbip_file: Path
    report_dir: Path
    semantic_model_dir: Path
    dist_dir: Path
    config_file: Path
    ticket: str
    project_dir: Path
    dist_base: Path
    rules_file: Path


def load_config(config_path: Path | None = None, root: Path | None = None) -> dict[str, Any]:
    """Load config/cicd-config.json with safe defaults."""
    base = (root or Path.cwd()).resolve()
    target = Path(config_path) if config_path else Path("config/cicd-config.json")
    target = target if target.is_absolute() else base / target
    defaults: dict[str, Any] = {
        "pbip": {"reports_root": "reports"},
        "bpa": {
            "rules_file": "config/bpa-rules.json",
            "fail_severity": 3,
            "ignored_rule_ids": [],
            "severity_overrides": {},
        },
        "output": {"dist_dir": "dist"},
    }
    if not target.exists():
        return defaults
    raw = json.loads(target.read_text(encoding="utf-8-sig"))
    for section in ("pbip", "bpa", "output"):
        if isinstance(raw.get(section), dict):
            defaults[section].update(raw[section])
    for k, v in raw.items():
        if k not in defaults:
            defaults[k] = v
    return defaults


TICKET_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")


def validate_ticket(ticket: str) -> str:
    """Reject identifiers that cannot safely name a Jira project output directory."""
    if len(ticket) > 80 or not TICKET_PATTERN.fullmatch(ticket):
        raise ValueError(f"Invalid ticket ID: {ticket!r}; expected a value such as TEST-001")
    return ticket


def reports_directory(root: Path, config: dict[str, Any]) -> Path:
    """Resolve the configured source directory without escaping the repository."""
    configured = str(config.get("pbip", {}).get("reports_root", "reports")).replace("\\", "/")
    target = (root / configured).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("reports_root must be a directory inside the repository")
    return target


def discover_projects(root: Path | None = None, config: dict[str, Any] | None = None) -> dict[str, Path]:
    """Find exactly one PBIP at reports/<ticket>/*.pbip for each ticket."""
    base = (root or Path.cwd()).resolve()
    directory = reports_directory(base, config or load_config(root=base))
    projects: dict[str, Path] = {}
    if not directory.exists():
        return projects
    for folder in sorted(directory.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        ticket = validate_ticket(folder.name)
        if folder.resolve() != folder or not folder.resolve().is_relative_to(directory):
            raise ValueError(f"Source directory escapes ticket root: {ticket}")
        candidates = sorted(folder.glob("*.pbip"))
        if len(candidates) != 1:
            raise ValueError(f"Ticket {ticket} must contain exactly one .pbip file; found {len(candidates)}")
        project = candidates[0].resolve()
        if not project.is_relative_to(folder.resolve()):
            raise ValueError(f"PBIP path escapes ticket {ticket}")
        projects[ticket] = project
    return projects


def resolve_project_paths(
    root: Path | None = None,
    config: dict[str, Any] | None = None,
    dist_override: Path | None = None,
    ticket: str | None = None,
    config_path: Path | None = None,
) -> ProjectPaths:
    """Resolve one explicit ticket and isolate its outputs from all source projects."""
    base = (root or Path.cwd()).resolve()
    cfg = config or load_config(config_path=config_path, root=base)
    projects = discover_projects(base, cfg)
    if ticket is None:
        if len(projects) != 1:
            raise ValueError("Specify a ticket when the repository does not contain exactly one project")
        ticket = next(iter(projects))
    validate_ticket(ticket)
    if ticket not in projects:
        raise ValueError(f"Unknown ticket: {ticket}")
    pbip_file = projects[ticket]
    project_dir = pbip_file.parent
    pbip_json = json.loads(pbip_file.read_text(encoding="utf-8-sig"))
    artifacts = pbip_json.get("artifacts", [])
    if len(artifacts) != 1 or "report" not in artifacts[0]:
        raise ValueError(f"Ticket {ticket} must reference exactly one report")
    report_dir = (project_dir / artifacts[0]["report"]["path"]).resolve()
    if not report_dir.is_relative_to(project_dir) or report_dir == project_dir:
        raise ValueError(f"Report path escapes ticket {ticket}")
    pbir_file = report_dir / "definition.pbir"
    if not pbir_file.is_file():
        raise FileNotFoundError(f"Missing definition.pbir for ticket {ticket}: {pbir_file}")
    pbir_json = json.loads(pbir_file.read_text(encoding="utf-8-sig"))
    by_path = pbir_json.get("datasetReference", {}).get("byPath", {}).get("path")
    if not by_path:
        raise ValueError(f"Ticket {ticket} requires a local byPath semantic model")
    semantic_model_dir = (report_dir / by_path).resolve()
    if not semantic_model_dir.is_relative_to(project_dir) or semantic_model_dir == project_dir:
        raise ValueError(f"Semantic model path escapes ticket {ticket}")
    if not semantic_model_dir.is_dir():
        raise FileNotFoundError(f"Semantic model not found for ticket {ticket}: {semantic_model_dir}")
    output = dist_override or Path(cfg["output"]["dist_dir"])
    dist_base = (base / output).resolve()
    source_root = reports_directory(base, cfg)
    if dist_base.is_relative_to(source_root) or source_root.is_relative_to(dist_base):
        raise ValueError("Output and ticket source directories must not overlap")
    dist_dir = (dist_base / ticket).resolve()
    if dist_dir != dist_base / ticket or not dist_dir.is_relative_to(dist_base):
        raise ValueError("Output ticket directory must not be redirected outside its assigned path")
    if dist_dir.is_relative_to(source_root) or source_root.is_relative_to(dist_dir):
        raise ValueError("Output and ticket source directories must not overlap")
    rules_file = (base / cfg["bpa"]["rules_file"]).resolve()
    if not rules_file.is_relative_to(base):
        raise ValueError("BPA rules must be inside the repository")
    configuration = Path(config_path) if config_path else base / "config/cicd-config.json"
    return ProjectPaths(
        root=base, pbip_file=pbip_file, report_dir=report_dir,
        semantic_model_dir=semantic_model_dir, dist_dir=dist_dir,
        config_file=(base / configuration).resolve(), ticket=ticket,
        project_dir=project_dir, dist_base=dist_base, rules_file=rules_file,
    )
