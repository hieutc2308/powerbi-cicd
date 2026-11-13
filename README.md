# Power BI PBIP CI/CD — Multi-ticket

**Open the documentation portal:** [Lineage Studio](https://hieutc2308.github.io/powerbi-cicd/) · [TEST-001](https://hieutc2308.github.io/powerbi-cicd/TEST-001/)

## Explain this project to stakeholders

Start with the English [Workflow Guide](docs/workflow.html): a workflow diagram and in-page navigation, responsibilities, ticket selection, pass/fail decisions, evidence and the three-phase rollout. The [BPA Rulebook](docs/bpa-rulebook.html) explains every configured check, its intent, severity, detection logic, limitations and customization points. Both standalone HTML files include light/dark themes, bundled fonts and Print / PDF; download the files and open them in Chrome or Edge if GitHub shows source code.

The Pages bundle includes these guides under `guides/`, with links from the report catalog. After deploying this revision, use the [online Workflow Guide](https://hieutc2308.github.io/powerbi-cicd/guides/workflow.html) and [online BPA Rulebook](https://hieutc2308.github.io/powerbi-cicd/guides/bpa-rulebook.html) for sharing. These URLs require that revision to be published first.

The operating flow is: **ticket → report branch → pull request → automated checks and documentation → quality Gate → human review → merge → published documentation**. A failing Gate still leaves its generated artifact available for review. The current Pages workflow runs independently of the Gate and can publish a FAIL result; it does not deploy reports to Power BI Service.

The portal is regenerated from all ticket projects on `main` when the Pages workflow runs successfully. Pull request branches and uncommitted local changes are not included; if a build or deployment fails, the previous published version remains available. Check [workflow runs](https://github.com/hieutc2308/powerbi-cicd/actions/workflows/pages.yml) to confirm the latest deployment.

See [PLAN.md](PLAN.md) for the consolidated roadmap: Phase 1 GitHub validation (done), Phase 2 GitLab migration, and Phase 3 Power BI/Fabric deployment pipelines with Jira ticket details.

Each Jira ticket owns one independent Power BI project under `reports/<TICKET>/`. The examples are Admin Monitoring dashboard in `reports/TEST-001/` and Hardware sales report in `reports/TEST-002/`. Analysis reads the report and model definitions without changing them. These synthetic ticket keys do not imply a working Jira integration.

## Repository layout

```text
reports/
  TEST-001/
    Admin Monitoring dashboard.pbip
    Admin Monitoring dashboard.Report/
    Admin Monitoring dashboard.SemanticModel/
  DATA-123/
    Sales.pbip
    Sales.Report/
    Sales.SemanticModel/
config/                      Shared pipeline settings and BPA rules
scripts/                     Analyzer, TE2 extraction, and approved v6 UI
tests/                      Independent synthetic PBIP fixtures
docs/                       English standalone workflow and BPA guides
dist/                       Generated locally and ignored by Git
  index.html                 Ticket catalog
  projects.json
  TEST-001/                  Separate output for each ticket
    index.html               Standalone v6 workspace
    project-summary.json
    te2-metadata.json
    te2-bpa.txt
    te2-source.json
    bpa-report.json
    lineage-graph.json
    MODEL_DESIGN.md
    MEASURES.md
    BPA_REPORT.md
    pr-summary.md
  site/                      Clean HTML-only Pages publication bundle
```

Ticket IDs must use an uppercase Jira-style key such as `TEST-001` or `DATA-123`. Each ticket folder must contain exactly one `.pbip`, referencing a report and a local semantic model within the same folder. Remote `byConnection` models and cross-ticket model references are not supported.

## Local setup and analysis

Install Python, uv, Node.js (for portal regression tests), and Tabular Editor 2. Then, from the repository root:

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"

# Analyze one ticket and open its v6 workspace.
.\scripts\run-local.ps1 -Ticket TEST-001 -OpenHtml

# Analyze all tickets and open the ticket catalog.
.\scripts\run-local.ps1 -OpenHtml

# Specify a local TE2 installation when automatic detection cannot find it.
.\scripts\run-local.ps1 -Ticket TEST-001 -Te2Exe 'C:\Program Files (x86)\Tabular Editor\TabularEditor.exe'

# Return a failing exit code when the Advisory Gate fails.
.\scripts\run-local.ps1 -Ticket TEST-001 -EnforceGate
```

By default, local analysis generates all outputs and reports the Gate without failing the process on BPA findings. `-EnforceGate` returns exit code 1 for Gate failure; infrastructure or configuration failures stop the run. CI uploads ticket artifacts before enforcing the Gate.

`-SkipTe2` permits an offline Python/TMDL run. It reuses TE2 files only when their provenance matches the selected ticket, source definitions, configuration, and BPA rules; otherwise it falls back to TMDL parsing. A fallback run does not provide the full TE2 BPA evaluation. Normal local and CI runs extract fresh TE2 metadata and require valid provenance. Old root-level `dist/te2-*` files are not reused.

Use `-Dist <directory>` to change the output base; ticket IDs are always appended. Output directories must remain separate from report sources.

The equivalent Python commands are:

```powershell
$env:PYTHONPATH = 'scripts'
.venv\Scripts\python.exe -m pbi_cicd.cli --list-projects
.venv\Scripts\python.exe -m pbi_cicd.cli --ticket TEST-001
.venv\Scripts\python.exe -m pbi_cicd.cli --all
.venv\Scripts\python.exe -m pbi_cicd.cli --ticket TEST-001 --check-gates
.venv\Scripts\python.exe -m pbi_cicd.cli --build-index --site dist/site
```

`--check-gates` checks existing results against the current input fingerprint before enforcing the Gate. `--build-index` lists only tickets currently in the repository. Site staging requires up-to-date results for every current ticket, replaces the previous staged site, and copies only the catalog, font-bundled standalone HTML workspaces, the two allowlisted HTML guides, manifest, and `.nojekyll`. Raw metadata, test fixtures, caches, and tools are excluded.

Open `dist/index.html` in Chrome or Edge to select a ticket, or open `dist/TEST-001/index.html` directly. Do not open `scripts/pbi_cicd/portal/index.html`: it is a generator template. Each ticket keeps the approved v6 interface, including light/dark themes, Catalog, model-only lineage, relationship canvas, M/DAX/code details, usage drill-down, and BPA filters. The root catalog is an additional entry point.

## Add or change a report

1. Create a branch for the Jira ticket, for example `feature/DATA-123`.
2. Save the PBIP project into `reports/DATA-123/`, including the `.pbip`, `.Report`, and `.SemanticModel` folders. Keep descriptor paths relative to that ticket folder.
3. Run `.\scripts\run-local.ps1 -Ticket DATA-123 -OpenHtml` and inspect its Gate and workspace.
4. Run the test suite, commit the source files and any intentional shared changes, then push the branch and open a pull request to `main`.
5. Review the `report-DATA-123` Actions artifact and the combined PR summary. Merge after the required `PBIP CI status` check passes.

For changes to an existing report, edit its existing ticket folder. For a new report, create a new ticket folder. Moving or removing a ticket is detected from both sides of the Git diff. Removing a folder removes it from the next published catalog and staged site.

Never commit `.pbix`, `.pbi/cache.abf`, `.pbi/localSettings.json`, or `dist/`. Global BPA rules and configuration stay under `config/`; keep their JSON and all TMDL files in CRLF as specified by `.gitattributes`.

## GitHub Actions and Pages

`pbi-ci.yml` runs fixture tests on every push/PR to `main` and on manual dispatch. It discovers affected tickets and runs each in a separate Windows matrix job with fresh TE2 extraction and a ticket-specific artifact. Shared changes under `scripts/`, `config/`, `tests/`, or `.github/`, and changes to `pyproject.toml`, `.gitattributes`, `.gitignore`, or `AGENTS.md`, analyze all tickets. Manual and initial pushes analyze all tickets. Documentation-only changes do not analyze reports.

| Event | CI ticket analysis | Pages publication |
| --- | --- | --- |
| Open, update or reopen PR targeting main | Diff-selected tickets; all for shared changes | None |
| Push branch without an open PR | None | None |
| Push main after merge | Diff-selected tickets | Separate workflow rebuilds all tickets |
| Manual workflow dispatch | CI: all tickets | Pages: all tickets from the selected ref |
| README / docs / plan-only PR | Tests run; ticket jobs skipped | None until a main push |

In a PR's Checks tab, open the matching Actions run and download `report-<TICKET>`. Its ZIP contains `index.html`, model/measure/BPA Markdown, analysis JSON, TE2 metadata/provenance and BPA extraction output. Extract before opening HTML; GitHub does not serve an uploaded artifact as an interactive branch website. Retention is 30 days. If extraction fails before generation, some or all output may be missing; inspect the failed job logs.

PR summaries contain the tickets selected from that PR's diff, not every report with an existing failure. A report-only PR for `reports/TEST-002/` analyzes TEST-002; shared pipeline/rule changes analyze all current tickets. Any selected ticket's failed Gate fails the aggregate check. The PR comment links to that run's documentation artifacts; its published portal link points to the latest deployed `main` snapshot. Branch pushes without a PR do not trigger this workflow; opening or updating a PR targeting `main` does. Pages runs separately after a push to `main` and rebuilds all current tickets.

Offline TE2 may report calculated-table column types as Unknown because no processed model is attached. A relationship type mismatch blocks only when both endpoint types are known. Unresolved endpoint types produce the visible `RELATIONSHIP_COLUMN_TYPE_UNRESOLVED` warning and require verification in a processed model; a passing static Gate does not certify runtime type compatibility. A TE2 integration fixture verifies that a real known-type mismatch still blocks.

Severity 3 findings, invalid references, and rule evaluation errors fail the configured Advisory Gate; lower-severity findings remain visible. The stable **PBIP CI status** job combines test/discovery/matrix results, including changes with no affected tickets. Use this check for branch protection. PR summaries are posted only for same-repository pull requests; fork PRs still receive checks and artifacts without write access.

`pages.yml` runs on `main` and manual dispatch. It tests the analyzer, freshly analyzes every current ticket, and uploads the standalone `portal-site` artifact. Download and extract it to open `index.html` locally. Deployment to GitHub Pages is disabled by default; BPA Gate failures remain visible in the portal, while extraction/build failures stop the build. Pages publishes documentation, not reports to Power BI Service.

To activate this in GitHub:

1. Push this repository and its workflow files to a GitHub repository with a `main` branch.
2. To publish the portal, first verify your GitHub plan supports Pages for this repository and review the site's audience. Under **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**, then set repository variable `ENABLE_GITHUB_PAGES` to `true` under **Settings → Secrets and variables → Actions → Variables**. GitHub Pages may expose the generated portal publicly even when source access is restricted; the portal includes model definitions and other report metadata.
3. Enable Actions as required by your organization and configure `PBIP CI status` as a required branch check after its first run.
4. Push a test report branch and inspect the CI artifact before merging. Download `portal-site` from the portal workflow, or, when Pages deployment is enabled, check the URL shown by the deployment job. The root lists tickets; each ticket links to its own v6 workspace.

These workflows do not deploy to Fabric/Power BI Service or write to Jira. Ticket keys currently organize folders, jobs, outputs, and links.

## Tests and customization

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

Tests use independent PBIP fixtures and cover ticket discovery, path isolation, metadata provenance, selection, generated outputs, clean site staging, PowerShell syntax, workflow contracts, and Node-based portal runtime regression tests. Node tests supplement browser review. Production report names and counts are not required by the fixtures.

Configure `pbip.reports_root`, `output.dist_dir`, BPA severity overrides, ignored rules, and the shared rules file in `config/cicd-config.json`. Update `config/bpa-rules.json` for shared TE2 rules. Local VertiPaq rules remain separate in `config/bpa-rules-vertipaq.json`.

See the [BPA Rulebook](docs/bpa-rulebook.html) for 40 default TE2 rules, four Python checks and five optional VertiPaq rules. The optional rules need measured annotations and are not executed by the default pipeline. To update the guides after changing rules or workflow explanations:

```powershell
.venv\Scripts\python.exe scripts/build_guides.py
```

Commit the guide builder and regenerated `docs/*.html` together. Tests check that the committed guides match their sources and preserve every configured rule's expression; Pages also regenerates the guides before staging. Human explanations live in `scripts/build_guides.py`; the build rejects rule IDs without matching explanations. Rule changes need independent finding/non-finding tests, with actual TE2 validation where relevant. Changes to severity, ignores or thresholds are policy decisions; they do not fix a report.

The report UI source lives in `scripts/pbi_cicd/portal/`. Superseded mockups and implementation plans have been consolidated into the source UI and root PLAN.md. Generated artifacts are disposable and rebuilt from source. Local PBIX backups live in the ignored `local-backups/` directory; `.venv/` remains local development tooling.
