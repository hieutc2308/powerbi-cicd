# Portal v6 Integration Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Generate the approved v6 workspace UI in `dist/index.html` while retaining the existing portal's analysis and inspection capabilities.

**Architecture:** Move the approved HTML, CSS, embedded font, and JavaScript into packaged generator assets. Embed the existing complete portal payload once, derive all UI state from it, and retain a standalone offline output. Keep the public generator function and pipeline unchanged.

**Tech Stack:** Python 3.11+, HTML/CSS, vanilla JavaScript, pytest, Node.js runtime tests.

**Spec:** User-approved `docs/mockups/lineage-canvas-v6.html` and the existing generator's functionality.

## Global Constraints

- All code comments are English.
- Checks and generation must not modify `.SemanticModel` or `.Report` inputs.
- Do not commit generated `dist/` artifacts or binary Power BI files.
- Preserve CRLF in TMDL and BPA configuration files.
- No network dependencies in the generated HTML.
- Work in place: the repository has no HEAD commit from which to create a worktree.

## Review Focus

- Non-demo project names, absent objects, empty graphs, and cyclic dependencies must not break initialization.
- BPA findings not attached to graph nodes and BPA evaluation errors must remain visible with the real Advisory Gate.
- Project and code strings containing HTML or placeholder-like tokens must remain inert and intact.
- Wheel/installed-package generation must find all template assets without consulting `docs/mockups` or `dist`.
- Source M/DAX whitespace, measure folder/expression search, report bindings, partitions, and relationships must remain available.

## Tasks

- [x] Add failing generator contract tests for v6 navigation, complete payload, hostile strings, arbitrary/empty models, and packaged assets.
- [x] Extract v6 into `scripts/pbi_cicd/portal/` assets and replace the old inline Python template with a safe bundler.
- [x] Generalize project identity, initial selection, Home, model layout, empty/cyclic graphs, and persistent preferences.
- [x] Restore complete BPA/gate reporting, DAX/folder filtering, visual filtering, partition/source and binding inspection within the approved UI.
- [x] Add meaningful JavaScript runtime regression coverage for data-driven behavior and retained interactions.
- [x] Run tests, verify package assets, regenerate `dist/index.html`, and compare source input hashes.
- [x] Review the final change and update README with the new portal organization and validation instructions.

## Verification record

- Full pytest suite: 15 passed, using an authorized fresh temporary directory because sandboxed pytest could not access its own temp/cache paths.
- Independent review: no important actionable findings.
- Wheel built in `dist/` and smoke-tested directly from ZIP with isolated Python; all portal assets are included.
- Production pipeline regenerated `dist/index.html`; embedded BPA/lineage match the sibling JSON artifacts.
- All 199 model/report source files match their pre-change SHA-256 hashes.
- Advisory Gate remains FAIL with S3=16, S2=42, S1=57. Findings were preserved rather than suppressed.
- Existing VertiPaq rule configuration was normalized from LF to mandatory CRLF; rule content was not changed.
- Browser visual verification remains outstanding; runtime tests use DOM stubs and do not establish browser rendering correctness.
