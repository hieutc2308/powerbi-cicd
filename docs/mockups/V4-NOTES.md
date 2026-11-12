# Workspace concept 04

Open `lineage-canvas-v4.html` in a local browser. This remains a standalone mockup; the portal generator, BPA configuration, semantic model, and report definitions are unchanged.

## Review paths

- Lineage: select a card, inspect the upstream/downstream labels in the navigator, then use Focus selection to change the graph root. Browse all supports type filtering and searching; clicking a visible object selects and centers it.
- BPA findings: search by the friendly title, original title, explanation, or rule ID. Original rule names and IDs remain available under each title.
- Data model: click a relationship to inspect cardinality, active state, cross-filter direction, and security filtering. Switch Keys / All columns, show disconnected tables, drag table headers, or search a table/column and press Enter to jump.

## Snapshot details

The data model uses the eight table nodes from `dist/lineage-graph.json` and the three relationships from `dist/te2-metadata.json` at authoring time. Cardinality and filter direction come from metadata rather than assumptions about table names. One relationship is many-to-many with filtering in both directions; two are many-to-one with filtering from the dimension to the fact table.

Friendly BPA titles are presentation aliases only. They do not change rule IDs, expressions, severity, or evaluation results. Explanations are review guidance, not automatic remediation.

Button feedback was informed by [Dagster's Button styles](https://github.com/dagster-io/dagster/blob/master/js_modules/ui-components/src/components/css/Button.module.css). The embedded Geist font retains the license in `GEIST-OFL.txt`.

## Validation limits

JavaScript was executed with DOM stubs to check navigation, depth filtering, selection context, friendly-rule search, relationship endpoints, model toggles, zoom, code, and theme state. Relationship endpoints were checked against actual table columns. Browser rendering, native pointer behavior, and visual layout still require review in a browser.
