"""Repository catalog and clean publication staging contracts."""

import json
from pathlib import Path

import pytest

from pbi_cicd.cli import main, run_pipeline
from pbi_cicd.portfolio import stage_site, write_repository_index


def test_index_links_ticket_portals_and_ignores_deleted_tickets(tmp_path: Path, make_ticket) -> None:
    make_ticket(tmp_path, "DATA-1", "Sales")
    make_ticket(tmp_path, "DATA-2", "Inventory")
    for ticket in ("DATA-1", "DATA-2"):
        run_pipeline(root=tmp_path, ticket=ticket)
    stale = tmp_path / "dist/REMOVED-3"
    stale.mkdir()
    (stale / "index.html").write_text("stale", encoding="utf-8")
    write_repository_index(tmp_path)
    text = (tmp_path / "dist/index.html").read_text(encoding="utf-8")
    assert "DATA-1/index.html" in text and "DATA-2/index.html" in text
    assert "REMOVED-3" not in text
    records = json.loads((tmp_path / "dist/projects.json").read_text(encoding="utf-8"))
    assert [r["ticket"] for r in records] == ["DATA-1", "DATA-2"]


def test_stage_only_publishes_current_html(fixture_repo: Path) -> None:
    run_pipeline(root=fixture_repo, ticket="FIX-1")
    hidden = fixture_repo / "dist/uv-cache"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("not a website", encoding="utf-8")
    site = fixture_repo / "dist/site"
    stage_site(fixture_repo, site)
    assert (site / "index.html").exists()
    assert (site / "FIX-1/index.html").exists()
    assert not (site / "uv-cache").exists()
    assert not (site / "FIX-1/te2-metadata.json").exists()
    with pytest.raises(ValueError):
        stage_site(fixture_repo, fixture_repo / "reports")
    with pytest.raises(ValueError):
        stage_site(fixture_repo, fixture_repo / "dist/FIX-1")


def test_stage_refuses_stale_source(fixture_repo: Path) -> None:
    run_pipeline(root=fixture_repo, ticket="FIX-1")
    table = next((fixture_repo / "reports").rglob("*.tmdl"))
    table.write_bytes(table.read_bytes() + b"\r\n")
    with pytest.raises(ValueError, match="regenerate"):
        stage_site(fixture_repo, fixture_repo / "dist/site")


def test_cli_all_and_matrix(fixture_repo: Path, capsys) -> None:
    assert main(["--root", str(fixture_repo), "--all"]) == 0
    assert (fixture_repo / "dist/FIX-1/index.html").exists()
    assert (fixture_repo / "dist/index.html").exists()
    assert main(["--root", str(fixture_repo), "--matrix"]) == 0
    output = capsys.readouterr().out.splitlines()[-1]
    assert json.loads(output)["include"] == [{"ticket": "FIX-1"}]
