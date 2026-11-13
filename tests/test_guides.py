"""Stakeholder documentation must cover the actual policy and remain offline-readable."""

import html
import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_guides", ROOT / "scripts/build_guides.py")
guides = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guides)


def test_rulebook_preserves_configured_detection_and_explains_every_rule(tmp_path: Path) -> None:
    guides.build(tmp_path)
    document = (tmp_path / "bpa-rulebook.html").read_text(encoding="utf-8")
    for filename in ("bpa-rules.json", "bpa-rules-vertipaq.json"):
        for rule in json.loads((ROOT / "config" / filename).read_text(encoding="utf-8-sig")):
            assert f'id="{rule["ID"]}"' in document
            assert html.escape(rule["Expression"]) in document
            assert html.escape(rule["Scope"]) in document
    assert document.count('<tr class="rule"') == 49
    assert document.count('<dialog class="rule-dialog"') == 49
    controls = re.findall(r'aria-controls="([^"]+)"', document)
    assert len(set(controls)) == 49
    assert all(f'<dialog class="rule-dialog" id="{target}" aria-labelledby=' in document for target in controls)
    severities = [int(value) for value in re.findall(r'<tr class="rule"[^>]+data-severity="(\d+)"', document)]
    assert severities == sorted(severities, reverse=True)
    sort_keys = []
    for row in re.findall(r'<tr class="rule".*?</tr>', document, re.S):
        cells = row.split('</td>')
        category = html.unescape(re.sub('<[^>]+>', '', cells[2])).casefold()
        engine = html.unescape(re.sub('<[^>]+>', '', cells[3])).casefold()
        sort_keys.append((-int(re.search(r'data-severity="(\d+)"', row)[1]), category, engine))
    assert sort_keys == sorted(sort_keys)
    assert '<th>Definition</th>' in document and '<th>Scope</th>' not in document
    assert '<code class="rule-id technical-id">' in document
    assert "PBIR_BROKEN_FIELD_REF" in document
    assert "PBIP_RUNTIME_CACHE_COMMITTED" in document
    assert "not enabled by default" in document
    for filename in ("workflow.html", "bpa-rulebook.html"):
        content = (tmp_path / filename).read_text(encoding="utf-8")
        assert '<html lang="en">' in content
        assert '<script src=' not in content and '<link rel="stylesheet"' not in content
        assert 'href="workflow.html"' in content and 'href="bpa-rulebook.html"' in content
        assert 'const selectControllers=new WeakMap()' in content
        assert '.select-popover{' in content and 'i-moon' in content
        assert 'min-height:calc(100svh - 150px)' not in content


def test_guides_separate_page_navigation_and_inpage_landmarks(tmp_path: Path) -> None:
    guides.build(tmp_path)
    for name in ("workflow.html", "bpa-rulebook.html"):
        document = (tmp_path / name).read_text(encoding="utf-8")
        sidebar = document.split('<aside class="side">')[1].split('</aside>')[0]
        assert 'class="section-link"' not in sidebar
        assert sidebar.count('class="page-link') == 2
        assert 'class="inpage-nav" aria-label="On this page"' in document
        targets = re.findall(r'class="section-link" href="#([^"]+)"', document)
        assert targets and all(f'<section id="{target}">' in document for target in targets)
    workflow = (tmp_path / "workflow.html").read_text(encoding="utf-8")
    diagram = re.search(r'<svg viewBox=.*?</svg>', workflow, re.S).group()
    ET.fromstring(diagram)
    assert 'marker-end="url(#arrow)"' in diagram
    assert 'FAIL / RULE ERROR' in diagram and 'PASS' in diagram


def test_committed_guides_match_current_sources(tmp_path: Path) -> None:
    guides.build(tmp_path)
    for name in ("workflow.html", "bpa-rulebook.html"):
        assert (ROOT / "docs" / name).read_text(encoding="utf-8") == (tmp_path / name).read_text(encoding="utf-8")
