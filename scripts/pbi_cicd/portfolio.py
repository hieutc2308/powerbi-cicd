"""Build a ticket catalog and a clean, standalone GitHub Pages publication tree."""

from __future__ import annotations

import html
import json
import shutil
import uuid
from importlib.resources import files
from pathlib import Path

from pbi_cicd.config_loader import discover_projects, load_config, reports_directory, resolve_project_paths
from pbi_cicd.metadata_provenance import source_fingerprint

GUIDES = {"workflow.html": "Workflow guide", "bpa-rulebook.html": "BPA rulebook"}


def _output_base(root: Path, config: dict, override: Path | None) -> Path:
    target = (root / (override or Path(config["output"]["dist_dir"]))).resolve()
    source = reports_directory(root, config)
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("Output and source directories must not overlap")
    return target


def collect_projects(root: Path, config_path: Path | None = None, dist_override: Path | None = None) -> list[dict]:
    """Ignore deleted ticket directories and detect ungenerated or outdated outputs."""
    config = load_config(root=root, config_path=config_path)
    projects = []
    for ticket in discover_projects(root, config):
        paths = resolve_project_paths(root, config, dist_override, ticket, config_path)
        entry = {"ticket": ticket, "pbipName": paths.pbip_file.stem, "ready": False, "status": "Not generated"}
        summary = paths.dist_dir / "project-summary.json"
        if summary.is_file():
            try:
                data = json.loads(summary.read_text(encoding="utf-8"))
                current = data.get("ticket") == ticket and data.get("pbip") == paths.pbip_file.relative_to(root).as_posix() and data.get("sourceFingerprint") == source_fingerprint(paths)
                if current and (paths.dist_dir / "index.html").is_file():
                    entry.update(data, ready=True, status=data.get("gate", {}).get("status", "Not evaluated"))
                else:
                    entry["status"] = "Needs regeneration"
            except (OSError, ValueError, TypeError):
                entry["status"] = "Needs regeneration"
        projects.append(entry)
    return projects


def write_repository_index(root: Path, config_path: Path | None = None, dist_override: Path | None = None) -> list[dict]:
    """Render a repository landing page while leaving each v6 ticket portal intact."""
    root = root.resolve()
    config = load_config(root=root, config_path=config_path)
    output = _output_base(root, config, dist_override)
    entries = collect_projects(root, config_path, dist_override)
    cards = []
    for entry in entries:
        ticket, name = html.escape(entry["ticket"]), html.escape(entry["pbipName"])
        status = html.escape(entry["status"])
        counts = entry.get("counts", {})
        detail = f"{counts.get('tables', 0)} tables · {counts.get('measures', 0)} measures · {counts.get('pages', 0)} pages" if entry["ready"] else "Generate this ticket to inspect its report."
        tag, attributes = ("a", f'href="{ticket}/index.html"') if entry["ready"] else ("article", "")
        color = "good" if status == "PASS" else "bad" if status == "FAIL" else "neutral"
        cards.append(f'<{tag} class="ticket-card" {attributes} data-search="{ticket} {name}"><div class="ticket-card-top"><span class="pill link">{ticket}</span><span class="pill {color}">{status}</span></div><h2>{name}</h2><p>{detail}</p><span class="small muted">{"Open report workspace" if entry["ready"] else "Not ready"}</span></{tag}>')
    assets = files("pbi_cicd").joinpath("portal")
    styles = assets.joinpath("geist.css").read_text(encoding="utf-8") + assets.joinpath("styles.css").read_text(encoding="utf-8")
    body = "".join(cards) or '<div class="empty">No report tickets have been added yet.</div>'
    guide_links = ''.join(f'<a class="btn" href="guides/{name}">{label}</a>' for name, label in GUIDES.items() if (root / "docs" / name).is_file())
    document = '''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Report tickets — Lineage Studio</title><style>''' + styles + '''
body{overflow:auto;background:var(--subtle)}.ticket-shell{max-width:1240px;padding:34px 28px;margin:auto}.ticket-header{display:flex;align-items:center;gap:15px;margin-bottom:40px}.ticket-header strong{font-size:18px}.ticket-card{display:block;text-decoration:none;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:22px}.ticket-card[hidden]{display:none}.ticket-card[href]:hover{border-color:var(--accent-border);background:var(--hover)}.ticket-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:23px}.ticket-card h2{font-size:18px;margin-bottom:12px;overflow-wrap:anywhere}.ticket-card p{font-size:11px;color:var(--muted);margin-bottom:28px}.tickets{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:17px;margin-top:25px}.ticket-search{max-width:380px;margin-top:23px}
</style></head><body><main class="ticket-shell"><div class="ticket-header"><strong>Lineage Studio</strong><span class="pill">Report tickets</span><span class="grow"></span><button class="btn" id="ticket-theme">Switch theme</button></div><div class="eyebrow">Power BI workspace</div><h1>Find your report.</h1><p class="muted small" style="margin-top:12px">Each Jira ticket has its own model, quality checks, and v6 workspace.</p><div class="search ticket-search"><input id="ticket-search" aria-label="Find ticket or report" placeholder="Search a ticket or report…"></div><div class="tickets">''' + body + '''</div></main><script>
const root=document.documentElement;try{root.dataset.theme=localStorage.getItem('lineage-ticket-theme')||'light';}catch{}
document.getElementById('ticket-theme').onclick=()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('lineage-ticket-theme',root.dataset.theme);}catch{}};
document.getElementById('ticket-search').oninput=e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('[data-search]').forEach(card=>card.hidden=!card.dataset.search.toLowerCase().includes(q));};
</script><pre hidden>''' + html.escape(assets.joinpath("GEIST-OFL.txt").read_text(encoding="utf-8")) + "</pre></body></html>"
    document = document.replace('<div class="search ticket-search">', '<nav aria-label="Project guides" style="display:flex;gap:10px;flex-wrap:wrap;margin-top:22px">' + guide_links + '</nav><div class="search ticket-search">')
    output.mkdir(parents=True, exist_ok=True)
    for name in GUIDES:
        source = root / "docs" / name
        if source.is_file():
            (output / "guides").mkdir(exist_ok=True)
            shutil.copyfile(source, output / "guides" / name)
    (output / "index.html").write_text(document, encoding="utf-8")
    (output / "projects.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return entries


def stage_site(root: Path, destination: Path, config_path: Path | None = None, dist_override: Path | None = None) -> Path:
    """Publish only current HTML, never unrelated caches or raw build artifacts."""
    root = root.resolve()
    output = _output_base(root, load_config(root=root, config_path=config_path), dist_override)
    target = (root / destination).resolve()
    if target == output or not target.is_relative_to(output) or target.name.startswith("."):
        raise ValueError("Site staging must be a separate directory under the output base")
    config = load_config(root=root, config_path=config_path)
    for ticket in discover_projects(root, config):
        project_output = output / ticket
        if target.is_relative_to(project_output) or project_output.is_relative_to(target):
            raise ValueError("Site staging must not overlap a ticket output directory")
    entries = write_repository_index(root, config_path, dist_override)
    if any(not entry["ready"] for entry in entries):
        raise ValueError("Please regenerate every current ticket before staging the site")
    staging = output / (".site-stage-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        shutil.copyfile(output / "index.html", staging / "index.html")
        shutil.copyfile(output / "projects.json", staging / "projects.json")
        (staging / ".nojekyll").touch()
        for name in GUIDES:
            source = root / "docs" / name
            if source.is_file():
                (staging / "guides").mkdir(exist_ok=True)
                shutil.copyfile(source, staging / "guides" / name)
        for entry in entries:
            folder = staging / entry["ticket"]
            folder.mkdir()
            shutil.copyfile(output / entry["ticket"] / "index.html", folder / "index.html")
        # Both recursive targets are resolved and constrained to the generated output tree.
        if target.exists():
            if not target.is_dir() or target.is_symlink() or not target.resolve().is_relative_to(output):
                raise ValueError("Unsafe site staging target")
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(target)
    finally:
        if staging.exists() and staging.resolve().is_relative_to(output):
            shutil.rmtree(staging)
    return target
