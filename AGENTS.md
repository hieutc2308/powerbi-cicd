# Workspace Rules — Power BI CI/CD Project

These instructions apply to all agents and contributors working in this repository.

## Mandatory Rule: Code Comments Language
- **NEVER write comments inside code in any language other than English.**
- All code comments across all languages (DAX, Power Query M, Python, C#, PowerShell, YAML, HTML/JS) MUST be written exclusively in English.

## Power Query M Formatting Convention
- Use 4 spaces per indentation level, never tabs. Keep root `let` and `in` aligned and steps indented 4 spaces.
- Give steps clear, descriptive English names, such as `RemovedHeaderRows` or `RenamedColumns`.
- Preserve query behavior during formatting-only changes.

## PBIP & CI/CD Hygiene
- Never commit `.pbi/cache.abf`, `.pbi/localSettings.json`, `.pbix` binaries, or `dist/` generated build artifacts.
- Keep `config/*.json` BPA rule files and `*.tmdl` files using Windows `CRLF` line endings (enforced via `.gitattributes`).
- All automated checks (`run-te2.ps1`, `pbi_cicd`) must remain strictly read-only against `*.SemanticModel` and `*.Report`.

