"""Exercise relationship rules against an actual offline TE2 model."""

import json
import os
import subprocess
from pathlib import Path

import pytest


def test_offline_relationship_types_distinguish_unknown_from_mismatch(tmp_path: Path) -> None:
    executable = Path(os.environ.get("TE2_EXE", r"C:\Program Files (x86)\Tabular Editor\TabularEditor.exe"))
    if not executable.is_file():
        pytest.skip("TE2 is required for the offline type integration check")
    definition = tmp_path / "Model/definition"
    tables = definition / "tables"
    tables.mkdir(parents=True)
    (definition / "database.tmdl").write_text("database Model\n\tcompatibilityLevel: 1600\n", encoding="utf-8")
    (definition / "model.tmdl").write_text("model Model\n\tculture: en-US\n", encoding="utf-8")
    for name, data_type in [("Numbers", "int64"), ("Dates", "dateTime"), ("OtherNumbers", "int64")]:
        (tables / f"{name}.tmdl").write_text(
            f"table {name}\n\tcolumn Id\n\t\tdataType: {data_type}\n\t\tsourceColumn: Id\n"
            f"\tpartition {name} = m\n\t\tmode: import\n\t\tsource = #table({{\"Id\"}}, {{}})\n", encoding="utf-8")
    (tables / "Inferred.tmdl").write_text(
        'table Inferred\n\tcolumn Id\n\t\tisNameInferred\n\t\tsourceColumn: [Id]\n'
        '\tpartition Inferred = calculated\n\t\tmode: import\n\t\tsource = DATATABLE("Id", INTEGER, {{1}})\n', encoding="utf-8")
    (definition / "relationships.tmdl").write_text(
        "relationship mismatch\n\tfromColumn: Numbers.Id\n\ttoColumn: Dates.Id\n"
        "relationship unresolved\n\tfromColumn: Inferred.Id\n\ttoColumn: Numbers.Id\n"
        "relationship matching\n\tfromColumn: OtherNumbers.Id\n\ttoColumn: Numbers.Id\n", encoding="utf-8")
    catalog = json.loads((Path(__file__).resolve().parents[1] / "config/bpa-rules.json").read_text(encoding="utf-8"))
    rules = [r for r in catalog if r["ID"] in {"RELATIONSHIP_COLUMNS_SAME_DATA_TYPE", "RELATIONSHIP_COLUMN_TYPE_UNRESOLVED"}]
    rule_file = tmp_path / "rules.json"
    rule_file.write_text(json.dumps(rules), encoding="utf-8")
    result = subprocess.run([str(executable), str(definition), "-AX", str(rule_file), "-G"], capture_output=True, timeout=60)
    output = result.stdout.decode("utf-8-sig", errors="replace")
    assert "Error on rule" not in output, output
    violations = [line for line in output.splitlines() if "violates rule" in line]
    assert len(violations) == 2, output
    assert any("::error::" in line and "Numbers'[Id]" in line and "Dates'[Id]" in line and 'same data type' in line for line in violations), output
    assert any("::warning::" in line and "Inferred'[Id]" in line and 'unresolved' in line.lower() for line in violations), output
    assert not any("OtherNumbers" in line for line in violations), output
