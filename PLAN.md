# Power BI CI/CD — Consolidated Plan

Updated: 2026-11-13. This file is the project roadmap and progress record. README.md contains setup and operating instructions.

## Direction and progress

| Phase | Purpose | Status |
| --- | --- | --- |
| 1 | Prove the workflow using a personal GitHub repository | Done |
| 2 | Move the validated workflow to the target GitLab environment | Planned; environment discovery required |
| 3 | Integrate Power BI / Fabric deployment pipelines and Jira ticket details | Planned; depends on Phase 2 |

Phase 1 completion means the analyzer, documentation, CI, artifacts, and portal have been exercised on GitHub. Initial TEST-001 validation had 16 blocking findings; CI correctly reported the failed Gate and preserved documentation. The PR #1 follow-up fixes the underlying stale bindings and measure references and distinguishes unresolved offline types from proven mismatches; see the verification record below.

## Shared architecture and rules

- One ticket owns exactly one PBIP project under `reports/<JIRA-ID>/`, including its local `.Report` and `.SemanticModel` folders. Current samples are TEST-001 and TEST-002.
- Global settings and BPA rules live in `config/`. Analyzer and TE2 extraction remain read-only against report/model definitions.
- Each ticket produces isolated output in `dist/<JIRA-ID>/`. A repository catalog links to the current tickets; clean site staging contains only the standalone portal files and manifest.
- Use fresh TE2 extraction in CI and validate artifact provenance before reuse. Never reuse another ticket's metadata or silently publish stale results after an infrastructure failure.
- Generate and retain documentation before enforcing the Gate. Rule errors, broken references, and configured blocking severity must remain visible.
- Preserve the approved v6 UI: Home is the entry page; Catalog, model-only Lineage, Data model, code/details, usage drill-down, BPA filters, and light/dark themes remain available.
- Exclude generated `dist/`, Python caches/environments, PBIX backups, and Power BI runtime caches from Git. Keep configuration JSON and TMDL in CRLF. Code comments must be English.

## Phase 1 — GitHub validation: done

### Delivered

- [x] Read-only TE2 metadata extraction and BPA analysis, with Python TMDL/PBIR and cross-layer checks.
- [x] Standalone HTML and Markdown documentation, lineage, relationship canvas, and full finding details.
- [x] Multi-ticket discovery, path validation, isolated outputs, and source/provenance checks.
- [x] GitHub CI selects changed tickets; shared pipeline/rule changes analyze all tickets. Ticket moves and deletions are handled.
- [x] Per-ticket artifacts upload before Gate enforcement; same-repository PR summaries and a stable aggregate CI status are configured.
- [x] Synthetic fixture tests cover the analyzer and portal without depending on sample report counts.
- [x] Create and push the personal GitHub repository, then make it public with user approval.
- [x] Deploy the catalog and TEST-001 portal through GitHub Pages; verify the published portal opens on Home.
- [x] Add direct portal links and explain publication freshness in README.md.
- [x] Consolidate the roadmap and remove superseded design/plan files and temporary build outputs.

### Evidence and current behavior

The counts and failures below record the initial consolidation snapshot. The later PR #1 correction record supersedes those Gate results; both ticket Gates subsequently passed.

- Repository: https://github.com/hieutc2308/powerbi-cicd
- Portal: https://hieutc2308.github.io/powerbi-cicd/
- Sample: https://hieutc2308.github.io/powerbi-cicd/TEST-001/
- Successful Home-default deployment: https://github.com/hieutc2308/powerbi-cicd/actions/runs/43250094398
- Latest validated local regression suite at consolidation: 37 tests passed.
- TEST-001 extraction produces 8 tables, 62 measures, 5 report pages, and 130 visuals. The last checked Gate has 16 blocking findings and zero rule evaluation errors.
- CI uploads `report-<TICKET>` artifacts before failing the Gate. Artifacts are retained for 30 days and downloaded as ZIP files on GitHub.
- The Pages workflow separately builds every current ticket from `main`. Deployment is enabled using repository variable `ENABLE_GITHUB_PAGES=true`.
- Current GitHub Pages publication proceeds even when the report's BPA Gate fails. Build/extraction/deployment errors prevent a new publication. This was used to test and review the sample findings.
- The public portal represents the latest successfully deployed snapshot of `main`, not uncommitted work or unmerged branches. Browser/CDN caching can briefly show the previous version.
- GitHub PR summary behavior was initially covered by tests; PR #1 subsequently completed the real PR/merge exercise.

### Follow-up carried into the next phases

- [x] Review TEST-001's original 9 report reference findings, 5 measure-reference findings, and 2 relationship-type findings. Corrections and verification are recorded below.
- Preserve a downloadable/viewable failed-branch snapshot when introducing stricter publication rules.

### Security and PR exercise — 2026-11-13

- Codex Security static review found one low-severity privacy issue: saved TEST-001 bookmark state retained real identity/customer/environment metadata. Source code, workflows, model tables and renderers were reviewed; remaining generated JSON and binary resources were broadly screened rather than exhaustively audited. No complete-security guarantee is implied.
- The approved correction substitutes synthetic literals in four bookmarks and their linked visual selections while retaining JSON keys, array order, operation tokens and query references. Twenty-six literal changes were structurally verified. Existing Git history still contains the earlier source; history rewriting is a separate decision.
- Obsolete mockups and plans are deleted from the feature branch. All `.pbi/` editor/runtime state is ignored; previously tracked editor state is removed from version control while kept locally.
- Hardware sales report is added under TEST-002. Fresh TE2 extraction and documentation generation succeed for both tickets; 37 fixture/runtime tests pass.
- At this initial scan TEST-002 had two blocking relationship-type findings: Dates.Date was Unknown in the unprocessed calculated table while its relationship partners were DateTime. The following root-cause correction resolves this false positive without guessing a type.
- The exercise on `codex/test-002-hardware-sales` completed with PR #1 merged after successful checks. Gate failures remained visible until corrected.

### BPA root-cause corrections — PR #1 follow-up

- Reproduced the type-check false positive using real TE2 and an independent fixture: an inferred calculated-table column is Unknown offline and was incorrectly treated as a proven mismatch against a known type. The mismatch rule now requires two resolved endpoint types; a separate severity-2 coverage warning preserves every unresolved case for processed-model verification. A genuine Int64/DateTime mismatch still produces a severity-3 blocker.
- TEST-001 measure expressions now reference the LastNdays measure without a table qualifier, preserving the referenced object and calculation.
- Rebound obsolete PBIR columns/table names to FactActivity_Events.is_success, FactActivity_Events.item_name and DimRefreshables.refresh_failures, including linked saved bookmark/query metadata. Title textboxes now use the existing Model Refresh measure for their "Updated until" value.
- Fresh read-only TE2 extraction and local `-EnforceGate` succeed for TEST-001 and TEST-002, each with zero blockers and zero rule evaluation errors. Unresolved type warnings remain; no calculated-column types were guessed or source data refreshed.
- CI and Pages test jobs install TE2 before pytest so the known/unknown/matching relationship integration fixture is exercised on GitHub too.
- PR summaries now link to exact-run per-ticket artifacts and explicitly label the Pages link as the published main snapshot. Selection remains diff-based; shared changes analyze all tickets.

### Stakeholder documentation

- English standalone Workflow Guide: workflow diagram, in-page navigation, ownership, selection, Gates, evidence and current publication behavior, with the GitLab and service/Jira phases explicitly marked as planned.
- BPA Rulebook: all 49 catalog checks (40 default TE2, four Python, five optional VertiPaq), exact configured expressions, human explanations, implementation limitations and customization guidance.
- README links both guides; clean Pages staging allowlists them under `guides/` and the catalog links to them. The Pages workflow regenerates guides from current rule sources. Publication follows the Pages workflow; deployment results are recorded in GitHub Actions.
- The approved ticket UI v6 and report/model definitions are unchanged by this documentation work.

## Phase 2 — GitLab migration: planned

### 2.1 Discover the target environment

- [ ] Confirm GitLab.com versus Self-Managed, version, license tier, target group/project, and required project visibility.
- [ ] Confirm a Windows runner for the current TE2 executable, PowerShell, Python, Node.js, tool download access, and dependency installation. Do not assume the current TE2 wrapper runs on Linux.
- [ ] Confirm Pages availability, domain/TLS, Pages Access Control, artifact HTML preview, retention limits, and merge approval/protected-branch requirements with the GitLab administrator.
- [ ] Confirm authentication for pipeline/API operations using the least necessary scope. Fork/untrusted MR jobs must not receive deployment or Jira credentials.

### 2.2 Port CI while preserving analysis behavior

- [ ] Add `.gitlab-ci.yml` using the existing CLI and local launcher; keep analysis logic independent of the CI provider.
- [ ] Select tickets using the correct MR base/head revisions and push revisions; test initial pushes, manual runs, shared changes, ticket renames/deletions, and empty selections.
- [ ] Run fixture tests and analyze each affected ticket independently. Use a dynamic child pipeline or explicit parallel-job strategy supported by the target GitLab instance.
- [ ] Separate documentation generation/artifact retention from Gate enforcement so a Gate failure retains the generated portal.
- [ ] Attach each result to its ticket, pipeline ID, branch/MR, commit SHA, and source fingerprint. Link to the exact pipeline output, not a moving latest-branch artifact.
- [ ] Post or expose one MR summary containing Gate status and per-ticket documentation links. Make repeated pipeline updates replace the existing summary rather than create duplicates.

### 2.3 Make failed-branch documentation easy to inspect

- [ ] Baseline: keep per-ticket HTML, Markdown, analysis JSON, and extraction logs as artifacts even when the Gate fails; start with 30-day retention subject to company policy.
- [ ] Verify that the full standalone HTML portal, including JavaScript, works through GitLab artifact preview. Artifact browsing alone does not guarantee interactive HTML preview.
- [ ] Add a direct HTML artifact link to the MR summary when the instance supports preview. Otherwise provide the artifact download link and clear local-open instructions.
- [ ] Optional: evaluate Pages parallel deployments for one preview URL per MR. Confirm tier/version support, permissions, URL isolation, expiry, and cleanup before implementation.
- [ ] Ensure the preview audience matches the intended project audience. A private source repository alone must not be treated as proof that a Pages URL is private.

### 2.4 Publish the GitLab main portal

- [ ] Proposed target policy: publish the primary portal only from the protected default branch after tests, required ticket Gates, and complete-site freshness checks pass. Confirm whether all current tickets must pass or only affected tickets before implementation.
- [ ] Keep failed-MR documentation accessible through artifacts/preview independently of primary-site publication.
- [ ] Build the catalog from all current tickets, remove deleted-ticket entries, and stage only the intended website files.
- [ ] Serialize deployments or reject outdated jobs so an older pipeline cannot replace a newer site.
- [ ] Configure Pages Access Control where required and verify access with both an authorized and an unauthorized account.
- [ ] Keep the previous published site available if the new build or deployment fails; expose the published commit and pipeline so freshness can be assessed.

### Acceptance and cutover

- [ ] Exercise a passing MR, a Gate-failing MR, an extraction-failing MR, and a multi-ticket MR; verify artifacts, summaries, exit codes, and merge blocking.
- [ ] Exercise a successful main deployment and a blocked deployment; verify failed-branch docs remain available and the main site stays at its previous valid version.
- [ ] Verify moves/deletions, stale-metadata rejection, preview expiry/access, and deployment ordering.
- [ ] Document adding a ticket, reviewing failed results, rerunning jobs, and opening the latest portal in README.md.
- [ ] Agree which host is authoritative; migrate remotes and disable duplicate production publication only after GitLab acceptance. Do not remove the working GitHub route before the cutover is verified.

## Phase 3 — Deployment pipelines and Jira details: planned

### 3.1 Choose the deployment mechanism

- [ ] Confirm whether the organization will use Power BI deployment pipelines, Fabric deployment pipelines, or a supported API/CLI/library path for the required item types.
- [ ] Verify current API capabilities, workspace/capacity/license requirements, tenant settings, model/report formats, and service identity permissions in the actual tenant.
- [ ] Map Dev/Test/Prod workspaces, pipeline stages, item identities, report/model bindings, parameters, connection rules, and environment-specific settings.
- [ ] Prefer supported workload identity/OIDC where available; otherwise manage approved credentials as protected CI secrets. Keep deployment credentials out of analyzer/MR jobs.

### 3.2 Implement controlled deployment

- [ ] Add a separate deployment stage after required tests and Gate success; protect Test/Prod promotion using the agreed approvals.
- [ ] Deploy a designated test ticket to Dev and verify report/model bindings, permissions, parameter/connection settings, refresh requirements, and a smoke test.
- [ ] Record each deployment's source SHA, ticket, pipeline run, target workspace/stage, item IDs, and outcome.
- [ ] Define behavior for partial failure, retries, re-running the same commit, and dependencies shared by multiple tickets. Decide how long-lived deployed reports relate to ticket folders.
- [ ] Define and test rollback/recovery, including whether an earlier artifact/version is redeployed and how data refresh affects recovery.
- [ ] Promote through Test and Prod only after the sandbox acceptance exercise succeeds.

### 3.3 Integrate Jira ticket details

- [ ] Agree which Jira instance/projects and fields are needed: key, summary, description/acceptance criteria, status, assignee, and related links as permitted.
- [ ] Resolve and validate the ticket from its folder; handle TEST-001 or other synthetic examples without pretending they are real Jira issues.
- [ ] Show ticket context in the portal with useful links and provenance. Clearly mark unavailable fields and permission/API failures.
- [ ] Prevent restricted Jira content from entering a public portal. Decide the portal audience, allowed fields, sanitization, and retention before publishing ticket details.
- [ ] With explicit authorization, write idempotent Jira updates containing Gate/docs/deployment links; define allowed comments and status transitions rather than assuming every successful build closes a ticket.
- [ ] Handle rate limits, transient errors, duplicate runs, revoked access, and ticket moves without obscuring the analysis/deployment outcome.

### Acceptance

- [ ] Verify an end-to-end ticket: PBIP change → CI/docs → Gate → approved Dev/Test/Prod deployment → Jira traceability.
- [ ] Verify Gate failure blocks deployment while preserving documentation; verify deployment failure is visible in both CI and the authorized Jira update.
- [ ] Verify unauthorized users cannot retrieve protected portal/Jira data or trigger protected promotions.
- [ ] Publish an operating runbook covering owners, approvals, credential rotation, troubleshooting, recovery, and retention.

## Current boundaries

Phase 2 and Phase 3 describe intended work; GitLab CI, authenticated GitLab previews, deployment automation, and Jira reads/writes have not been implemented. Existing configuration hooks are placeholders, not working integrations. Keep this roadmap updated as decisions are confirmed and acceptance evidence becomes available.

## Reference documentation

Verify these against the target GitLab and Microsoft environments during implementation:

- GitLab artifact browsing and HTML preview: https://docs.gitlab.com/ci/jobs/job_artifacts/
- GitLab Pages access control: https://docs.gitlab.com/user/project/pages/pages_access_control/
- GitLab Pages previews/parallel deployments: https://docs.gitlab.com/user/project/pages/getting_started/pages_from_scratch/
