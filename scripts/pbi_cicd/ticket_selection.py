"""Select affected ticket jobs from a Git diff without shell interpolation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pbi_cicd.config_loader import TICKET_PATTERN

SHARED_PREFIXES = ("scripts/", "config/", "tests/", ".github/")
SHARED_FILES = {"pyproject.toml", ".gitattributes", ".gitignore", "AGENTS.md"}


def select_changed_tickets(changed_paths: list[str], projects: dict[str, Path], reports_root: str = "reports") -> dict:
    """Include surviving sides of moves and record deletions separately."""
    changed = [p.replace("\\", "/") for p in changed_paths]
    shared = any(p in SHARED_FILES or p.startswith(SHARED_PREFIXES) for p in changed)
    prefix = reports_root.strip("/") + "/"
    affected: set[str] = set()
    for path in changed:
        if path.startswith(prefix):
            candidate = path[len(prefix):].split("/", 1)[0]
            if TICKET_PATTERN.fullmatch(candidate):
                affected.add(candidate)
    tickets = sorted(projects if shared else affected.intersection(projects))
    return {"tickets": tickets, "deleted": sorted(affected.difference(projects)), "all": shared}


def git_changed_paths(root: Path, base: str, head: str = "HEAD") -> list[str]:
    """Disable rename collapsing so old and new ticket paths are both selected."""
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", "-z", base, head, "--"],
        cwd=root, capture_output=True, check=True,
    )
    return [p for p in result.stdout.decode("utf-8").split("\0") if p]
