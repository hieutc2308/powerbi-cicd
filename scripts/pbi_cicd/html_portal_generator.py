"""Bundle the offline Lineage Studio workspace with the complete pipeline payload."""

from __future__ import annotations

import html
import json
import re
from importlib.resources import files
from typing import Any


def generate_html_portal(
    pbip_name: str,
    model_meta: dict[str, Any],
    report_meta: dict[str, Any],
    bpa_report: dict[str, Any],
    lineage_graph: dict[str, Any],
) -> str:
    """Render the approved workspace without external assets or source mutations."""
    payload = {
        "pbipName": pbip_name,
        "model": model_meta,
        "report": report_meta,
        "bpa": bpa_report,
        "lineage": lineage_graph,
    }
    serialized = json.dumps(payload, ensure_ascii=True)
    # Keep user-controlled markup inert in the HTML raw-text script element.
    for character, escaped in (("<", r"\u003c"), (">", r"\u003e"), ("&", r"\u0026")):
        serialized = serialized.replace(character, escaped)

    assets = files("pbi_cicd").joinpath("portal")
    substitutions = {
        "__PORTAL_TITLE__": html.escape(pbip_name),
        "__PORTAL_DATA_JSON__": serialized,
        "__PORTAL_FONT__": assets.joinpath("geist.css").read_text(encoding="utf-8"),
        "__PORTAL_STYLES__": assets.joinpath("styles.css").read_text(encoding="utf-8"),
        "__PORTAL_APP__": assets.joinpath("app.js").read_text(encoding="utf-8"),
        "__PORTAL_LICENSE__": html.escape(assets.joinpath("GEIST-OFL.txt").read_text(encoding="utf-8")),
    }
    template = assets.joinpath("index.html").read_text(encoding="utf-8")
    # Substitute in one pass so placeholder-like source text is never interpreted.
    pattern = re.compile("|".join(re.escape(key) for key in substitutions))
    return pattern.sub(lambda match: substitutions[match.group(0)], template)
