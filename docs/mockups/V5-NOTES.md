# Workspace concept 05

Open `lineage-canvas-v5.html` in a local browser. The mockup is self-contained and does not change the portal generator, BPA rules, or Power BI definitions.

- Dropdowns use a shared rounded popover rather than operating-system option menus. They support selection, keyboard navigation, type-ahead, search for long option lists, and light/dark themes. Existing filter handlers still receive native change events.
- Code indentation is preserved with `white-space: pre` and four-character tab stops; wrapping switches the source text to `pre-wrap`. The earlier theme transformation had accidentally changed the property name to `var(--surface)-space`. Source expressions and Copy input remain unchanged.
- Relationship columns are ordered by the positions of the connected tables. In the default layout, Date precedes user_id on the fact table, matching the upper/lower order of their dimension tables and separating the two left-side curves.
- Every table has a Fields toggle. Expanded rows include source columns, calculated columns, calculated-table columns, and attached measures with explicit labels. Clicking a calculated field or measure opens the available source definition.
- All eight tables are initially visible. The four disconnected tables occupy a compact shelf at the right. Expanding one repacks that shelf without changing relationships. Keys collapses the field lists; All fields expands them.

Validation covered JavaScript initialization, the dropdown controller and existing change handlers, source indentation, original expressions, member classifications, 61 measures on the measure table, relationship endpoints, and default curve separation. Browser visual verification is still outstanding.

The Geist font license remains in `GEIST-OFL.txt`.
