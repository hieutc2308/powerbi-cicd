# Multi-ticket PBIP Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Analyze independent `reports/<JIRA-ID>/*.pbip` projects, moving the current project to `reports/TEST-001/`, with isolated ticket outputs and unchanged v6 report UI.

**Architecture:** Keep repository-wide rules/configuration at the root. Discover exactly one local-model PBIP per ticket and pass explicit ticket paths through the analyzer and TE2 launcher. Keep outputs under a shared dist base plus ticket ID; build a repository-level report catalog and a clean Pages staging directory.

**Tech Stack:** Python, PowerShell, pytest/Node, GitHub Actions matrix jobs.

**Spec:** User-approved multi-ticket layout and existing v6 portal.

## Constraints

- English code comments only; CRLF for configuration JSON and TMDL.
- Source migration changes paths only; verify hashes of PBIP/model/report inputs.
- Do not alter the report-level v6 HTML/CSS/JavaScript assets.
- No remote GitHub/Jira writes, commits, or deployment during implementation.
- Never select an arbitrary first PBIP when a ticket is ambiguous.
- Keep TE2 metadata and BPA outputs isolated and verify provenance before reuse.
- Reject source/output path overlap and paths escaping the selected ticket.
- Work in place; this repository has no HEAD from which to create a worktree.

## Review Focus

- Changed-ticket selection includes both sides of renames/deletions and all projects for shared code/rule changes.
- Tests must use synthetic fixtures rather than production report names or counts.
- Empty repositories/deleted tickets must not leave stale entries on the published catalog.
- Gate failures must retain analysis artifacts and PR summaries; infrastructure failures must not publish stale results.
- Clean Pages staging must exclude caches, build products, TE2 tools, and test artifacts from dist.

## Tasks

- [x] Add failing tests for discovery, ticket/path validation, source/output isolation, changed-file selection, and metadata provenance.
- [x] Implement ticket resolution, CLI selection/discovery, isolated pipeline outputs, provenance, and the aggregate catalog/staging.
- [x] Replace production-specific tests with minimal independent PBIP fixtures and cover multi-project execution.
- [x] Migrate the current report to TEST-001 and verify byte-identical source content.
- [x] Update the local PowerShell launcher and CI matrix/Pages workflows.
- [x] Run the full suite and real read-only analysis, check unchanged v6 assets, and document the new workflow.
- [x] Obtain fresh review, fix important findings, and regenerate final ticket and catalog outputs.

## Verification evidence

- Full pytest suite: 37 passed, including Node portal runtime, workflow YAML, PowerShell AST, multi-ticket fixtures, and both review regression cases.
- Fresh read-only TE2 extraction and Python analysis succeeded for TEST-001: 8 tables, 62 measures, 5 pages, 130 visuals.
- Advisory Gate remains FAIL with 16 blocking findings and no rule evaluation errors; generated artifacts remain available.
- All 200 migrated PBIP/model/report files match the pre-migration SHA-256 baseline; all 5 v6 portal assets match their original hashes.
- Configuration JSON and TMDL CRLF checks passed.
- Pages staging contains only index.html, projects.json, .nojekyll, and TEST-001/index.html.
- Review findings fixed: final ticket output redirection rejected; configured source paths normalized before Git-diff selection.
- GitHub Actions execution and Pages deployment require the user's first push; neither was performed locally.
