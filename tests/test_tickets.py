"""Ticket discovery, isolation, selection, and metadata provenance contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbi_cicd.config_loader import discover_projects, load_config, resolve_project_paths
from pbi_cicd.cli import run_pipeline
from pbi_cicd.metadata_provenance import record_te2_provenance, te2_provenance_status
from pbi_cicd.ticket_selection import select_changed_tickets


def test_discover_and_resolve_multiple_tickets(tmp_path: Path, make_ticket) -> None:
    make_ticket(tmp_path, "DATA-12", "Sales")
    make_ticket(tmp_path, "DATA-13", "Inventory", "Stock")
    assert list(discover_projects(tmp_path)) == ["DATA-12", "DATA-13"]
    paths = resolve_project_paths(root=tmp_path, ticket="DATA-13")
    assert paths.root == tmp_path
    assert paths.project_dir == tmp_path / "reports/DATA-13"
    assert paths.pbip_file.name == "Inventory.pbip"
    assert paths.dist_dir == tmp_path / "dist/DATA-13"
    with pytest.raises(ValueError, match="ticket"):
        resolve_project_paths(root=tmp_path)


def test_reject_ambiguous_ticket(tmp_path: Path, make_ticket) -> None:
    project = make_ticket(tmp_path)
    (project / "Duplicate.pbip").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        discover_projects(tmp_path)


@pytest.mark.parametrize("ticket", ["../DATA-1", "data-1", "DATA", "DATA-1/other"])
def test_reject_invalid_ticket(tmp_path: Path, make_ticket, ticket: str) -> None:
    make_ticket(tmp_path)
    with pytest.raises(ValueError, match="ticket"):
        resolve_project_paths(root=tmp_path, ticket=ticket)


def test_reject_cross_ticket_model_reference(tmp_path: Path, make_ticket) -> None:
    project = make_ticket(tmp_path, "DATA-1")
    make_ticket(tmp_path, "DATA-2")
    reference = project / "Sales.Report/definition.pbir"
    reference.write_text(json.dumps({"datasetReference": {"byPath": {"path": "../../DATA-2/Sales.SemanticModel"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="ticket"):
        resolve_project_paths(root=tmp_path, ticket="DATA-1")


def test_reject_output_overlapping_inputs(tmp_path: Path, make_ticket) -> None:
    make_ticket(tmp_path)
    config = load_config(root=tmp_path)
    config["output"]["dist_dir"] = "reports"
    with pytest.raises(ValueError, match="overlap"):
        resolve_project_paths(root=tmp_path, config=config, ticket="FIX-1")


def test_reject_ticket_output_redirected_to_source(fixture_repo: Path, monkeypatch) -> None:
    original = Path.resolve
    output = fixture_repo / "dist/FIX-1"

    def redirected(path, *args, **kwargs):
        if path == output:
            return fixture_repo / "reports/FIX-1"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    with pytest.raises(ValueError, match="Output"):
        resolve_project_paths(root=fixture_repo, ticket="FIX-1")


@pytest.mark.parametrize("directory", ["./reports", "reports/", ".\\reports"])
def test_cli_normalizes_reports_directory(fixture_repo: Path, monkeypatch, capsys, directory: str) -> None:
    from pbi_cicd.cli import main
    config_file = fixture_repo / "config/cicd-config.json"
    config = json.loads(config_file.read_text(encoding="utf-8"))
    config["pbip"]["reports_root"] = directory
    config_file.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr("pbi_cicd.ticket_selection.git_changed_paths", lambda *args: ["reports/FIX-1/Sales.pbip"])
    assert main(["--root", str(fixture_repo), "--matrix", "--base", "base"]) == 0
    assert json.loads(capsys.readouterr().out)["include"] == [{"ticket": "FIX-1"}]


def test_changed_ticket_selection() -> None:
    projects = {"DATA-1": Path("a.pbip"), "DATA-2": Path("b.pbip")}
    assert select_changed_tickets(["reports/DATA-1/Sales.pbip"], projects)["tickets"] == ["DATA-1"]
    assert select_changed_tickets(["reports/DATA-1/A.pbip", "reports/DATA-2/B.pbip"], projects)["tickets"] == ["DATA-1", "DATA-2"]
    assert select_changed_tickets(["config/bpa-rules.json"], projects)["tickets"] == list(projects)
    assert select_changed_tickets(["scripts/pbi_cicd/portal/app.js"], projects)["tickets"] == list(projects)
    assert select_changed_tickets(["reports/DATA-3/Old.pbip"], projects)["deleted"] == ["DATA-3"]
    assert select_changed_tickets(["docs/readme.md"], projects)["tickets"] == []


def test_metadata_requires_matching_provenance(fixture_repo: Path) -> None:
    paths = resolve_project_paths(root=fixture_repo, ticket="FIX-1")
    paths.dist_dir.mkdir(parents=True)
    (paths.dist_dir / "te2-metadata.json").write_text('{"tables": [], "relationships": [], "expressions": []}', encoding="utf-8")
    (paths.dist_dir / "te2-bpa.txt").write_text("", encoding="utf-8")
    assert te2_provenance_status(paths) != "valid"
    record_te2_provenance(paths)
    assert te2_provenance_status(paths) == "valid"
    source = next(paths.semantic_model_dir.rglob("*.tmdl"))
    source.write_bytes(source.read_bytes() + b"\r\n")
    assert te2_provenance_status(paths) == "stale"
    with pytest.raises(ValueError, match="TE2"):
        run_pipeline(root=fixture_repo, ticket="FIX-1", require_te2=True)


def test_ticket_outputs_do_not_mix(tmp_path: Path, make_ticket) -> None:
    make_ticket(tmp_path, "DATA-1", "Sales", "Transactions")
    make_ticket(tmp_path, "DATA-2", "Inventory", "Stock")
    first = run_pipeline(root=tmp_path, ticket="DATA-1")
    second = run_pipeline(root=tmp_path, ticket="DATA-2")
    assert first["paths"].dist_dir != second["paths"].dist_dir
    assert first["model"]["tables"][0]["name"] == "Transactions"
    assert second["model"]["tables"][0]["name"] == "Stock"
    assert (tmp_path / "dist/DATA-1/index.html").exists()
    assert (tmp_path / "dist/DATA-2/index.html").exists()
