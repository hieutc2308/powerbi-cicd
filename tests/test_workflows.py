"""Static workflow and PowerShell contracts for multi-ticket CI."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


def workflow(name: str) -> dict:
    return yaml.load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_ci_matrix_is_scoped_and_keeps_gate_artifacts() -> None:
    ci = workflow("pbi-ci.yml")
    jobs = ci["jobs"]
    assert "--matrix" in jobs["discover"]["steps"][-1]["run"]
    assert jobs["analyze-and-gate"]["strategy"]["fail-fast"] == "false"
    steps = jobs["analyze-and-gate"]["steps"]
    upload = next(i for i, step in enumerate(steps) if "actions/upload-artifact" in step.get("uses", ""))
    gate = next(i for i, step in enumerate(steps) if "--check-gates" in step.get("run", ""))
    assert upload < gate
    assert "matrix.ticket" in steps[upload]["with"]["path"]
    assert "head.repo.full_name == github.repository" in jobs["pr-summary"]["if"]
    status = jobs["ci-status"]
    assert status["name"] == "PBIP CI status"
    assert status["if"] == "always()"
    assert set(status["needs"]) == {"discover", "tests", "analyze-and-gate"}
    assert 'test "$ANALYSIS_RESULT" = success' in status["steps"][0]["run"]


def test_pages_uses_a_clean_complete_site() -> None:
    pages = workflow("pages.yml")
    steps = pages["jobs"]["build-portal"]["steps"]
    assert any("--site dist/site" in step.get("run", "") for step in steps)
    upload = next(s for s in steps if "actions/upload-pages-artifact" in s.get("uses", ""))
    assert upload["with"]["path"] == "dist/site/"
    for step in steps:
        if "run-local.ps1" in step.get("run", ""):
            assert "-Ticket" not in step["run"]


def test_powershell_launchers_parse() -> None:
    shell = shutil.which("pwsh")
    if shell is None:
        pytest.skip("PowerShell is not installed")
    for relative in ("scripts/run-local.ps1", "scripts/te2/run-te2.ps1"):
        script = ROOT / relative
        # Read the trusted file path through an argument rather than interpolating it as code.
        runner = ROOT / "tests/check-powershell.ps1"
        result = subprocess.run([shell, "-NoProfile", "-File", str(runner), str(script)], capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stdout + result.stderr
