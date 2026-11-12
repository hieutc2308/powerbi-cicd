"""Independent PBIP fixtures for repository-wide pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def make_ticket():
    """Create a minimal PBIP ticket without depending on a production report."""
    def create(root: Path, ticket: str = "FIX-1", name: str = "Sales", table: str = "Transactions") -> Path:
        project = root / "reports" / ticket
        report = project / f"{name}.Report"
        model = project / f"{name}.SemanticModel"

        def write_json(path: Path, value: dict | list) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")

        write_json(project / f"{name}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": report.name}}]})
        write_json(report / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{model.name}"}}})
        write_json(report / "definition/pages/overview/page.json", {"name": "overview", "displayName": "Overview"})
        write_json(report / "definition/pages/overview/visuals/card/visual.json", {
            "name": "card", "visual": {"visualType": "card", "query": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": "Total"}}},
        })
        write_json(model / "definition.pbism", {"version": "4.0"})
        table_file = model / "definition/tables/Transactions.tmdl"
        table_file.parent.mkdir(parents=True, exist_ok=True)
        tmdl = (
            f"table '{table}'\n"
            "\tcolumn Amount\n\t\tdataType: int64\n\t\tsourceColumn: Amount\n"
            f"\tmeasure Total = SUM('{table}'[Amount])\n\t\tformatString: 0\n\t\tdisplayFolder: KPI\n"
            f"\tpartition '{table}' = m\n\t\tmode: import\n\t\tsource =\n"
            "\t\t\tlet\n\t\t\t    Source = #table(type table [Amount = number], {{1}})\n\t\t\tin\n\t\t\t    Source\n"
        )
        table_file.write_bytes(tmdl.replace("\n", "\r\n").encode("utf-8"))
        config = root / "config"
        config.mkdir(exist_ok=True)
        if not (config / "cicd-config.json").exists():
            write_json(config / "cicd-config.json", {"pbip": {"reports_root": "reports"}, "output": {"dist_dir": "dist"}})
            (config / "bpa-rules.json").write_text("[]", encoding="utf-8")
        return project

    return create


@pytest.fixture
def fixture_repo(tmp_path: Path, make_ticket) -> Path:
    make_ticket(tmp_path)
    return tmp_path
