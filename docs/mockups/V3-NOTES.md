# Workspace concept 03

Open `lineage-canvas-v3.html` in a local browser. This is a standalone prototype with embedded project metadata and font data. It does not modify the portal generator or Power BI project definitions.

- The model graph contains sources, Power Query expressions, tables, and measures. Report bindings and relationships do not affect depth in this graph.
- Object details include report usage derived from actual bindings. Indirect usage follows downstream model dependencies.
- Catalog actions are labeled Lineage and Details. Report objects have Details only.
- The theme switch, facet preferences, and review notes use browser-local storage.
- BPA filters can be combined: search, severity, category, object kind, and rule. Results can be sorted by severity, object, or rule.
- The read-only code popup supports syntax coloring, line wrapping, expansion, and copying.

UI research references:

- [Dagster Button](https://github.com/dagster-io/dagster/blob/master/js_modules/ui-components/src/components/Button.tsx)
- [Dagster Tag](https://github.com/dagster-io/dagster/blob/master/js_modules/ui-components/src/components/Tag.tsx)
- [Dagster Dialog](https://github.com/dagster-io/dagster/blob/master/js_modules/ui-components/src/components/Dialog.tsx)
- [Dagster theme](https://github.com/dagster-io/dagster/blob/master/js_modules/ui-components/src/theme/GlobalThemeStyle.css)

The SVG icon paths were authored for this prototype. The embedded Geist font was obtained from Dagster's `GlobalGeist.css`; Geist is distributed under the SIL Open Font License. See `GEIST-OFL.txt` and the [Geist font project](https://github.com/vercel/geist-font).

Validation covers JavaScript execution with DOM stubs, graph depth and routing, model-only scope, report usage, filters, themes, and navigation markup. This does not replace browser visual verification. Automatic layout reduces edge crossings and does not guarantee a crossing-free graph.
