"""Build offline stakeholder guides from the repository's rule catalog."""

from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each entry explains the actual local implementation, including its limitations.
NOTES = {
    "DAX_COLUMNS_FULLY_QUALIFIED": ("Make column references unambiguous", "A dependency on a column uses an unqualified reference such as [Amount]. Use Sales[Amount].", "Uses TE2 dependency metadata; it is not a free-text search. Columns and measures intentionally follow different conventions."),
    "DAX_MEASURES_UNQUALIFIED": ("Keep measure references portable", "A measure dependency includes a table prefix. Replace Measures[Revenue] with [Revenue].", "This repository deliberately treats this naming convention as severity 3. It does not establish a wrong calculation result."),
    "RELATIONSHIP_COLUMNS_SAME_DATA_TYPE": ("Avoid joining incompatible keys", "Two resolved endpoint types differ, for example Int64 versus DateTime. Correct the source/model type after checking the intended relationship.", "Custom correction: Unknown and Automatic are excluded from proven mismatches and handled by the coverage rule below. No type is guessed."),
    "RELATIONSHIP_COLUMN_TYPE_UNRESOLVED": ("Make incomplete validation visible", "At least one relationship endpoint is Unknown or Automatic in the offline model. Verify it in a processed model.", "Repository-specific coverage rule, severity 2. Calculated tables can omit inferred types in PBIP. This warning is not proof of a mismatch and is not runtime certification."),
    "AVOID_THE_USERELATIONSHIP_FUNCTION_AND_RLS_AGAINST_THE_SAME_TABLE": ("Review relationship activation with security filters", "A table has a non-null RLS entry and a measure matches a USERELATIONSHIP pattern naming that table.", "Regex-based candidate detection, not a complete RLS execution test. Confirm the actual relationship, role and query before changing security behavior."),
    "AVOID_M2M_RELATIONSHIPS_ON_DYNAMIC_RLS_TABLES": ("Review many-to-many joins on secured tables", "A table has a many-to-many relationship and a nonempty RLS expression.", "Despite the rule name, the expression does not prove that RLS is dynamic: it checks any nonempty role expression. Investigate the actual role semantics."),
    "AVOID_INVALID_NAME_CHARACTERS": ("Avoid hidden control characters in names", "An object name contains a control character that is not classified as whitespace.", "This is a narrow character check; it does not validate every platform naming restriction or forbid whitespace."),
    "DATA_COLUMNS_MUST_HAVE_A_SOURCE_COLUMN": ("Keep imported columns bound to source fields", "A DataColumn has a blank SourceColumn. Restore the intended source-field mapping.", "Applies to data columns, not inferred calculated-table columns. Source connectivity is not tested."),
    "EXPRESSION_RELIANT_OBJECTS_MUST_HAVE_AN_EXPRESSION": ("Do not leave calculations empty", "A measure, calculated column or calculation item has an empty expression.", "Checks presence, not DAX correctness or calculation-item business meaning."),
    "EVALUATEANDLOG_SHOULD_NOT_BE_USED_IN_PRODUCTION_MODELS": ("Remove debugging instrumentation from production calculations", "A measure expression contains an EVALUATEANDLOG call pattern.", "Regex detection may match comments or strings. Confirm the occurrence before removing it."),
    "MODEL_SHOULD_HAVE_A_DATE_TABLE": ("Check for a recognizable calendar", "No table has DataCategory Time plus a key DateTime column.", "This is a metadata proxy. Offline Unknown date types can trigger it; it does not run time-intelligence calculations."),
    "DATE_CALENDAR_TABLES_MARKED_AS_DATE_TABLE": ("Review calendar metadata", "A table name contains DATE or CALENDAR but lacks Time category or a key DateTime column.", "The naming heuristic can include unrelated names. Verify inferred types and the intended calendar before changing metadata."),
    "REMOVE_AUTO_DATE_TABLE": ("Review automatically generated date tables", "A table name starts with DateTableTemplate_ or LocalDateTable_. Consider an explicit shared calendar.", "Prefix matching only; auto-date tables may be intentional and can support existing visual hierarchies."),
    "SNOWFLAKE_SCHEMA_ARCHITECTURE": ("Review chained dimension relationships", "A table occurs on both the From and To sides of relationships.", "This is a structural hint, not proof of a slow or incorrect model. Star-schema changes require semantic review."),
    "AVOID_EXCESSIVE_BIDIRECTIONAL_OR_M2M_RELATIONSHIPS": ("Keep complex filter paths deliberate", "The number of bidirectional relationships plus many-to-many relationships exceeds 30% of all relationships.", "Local threshold: 0.3. A relationship that is both bidirectional and many-to-many is counted twice; this is not the percentage of unique complex relationships."),
    "M2M_RELATIONSHIPS_SINGLE_DIRECTION": ("Review bidirectional many-to-many filtering", "A many-to-many relationship also uses BothDirections.", "Review filter ambiguity and intended behavior; changing direction can change business results."),
    "ISAVAILABLEINMDX_FALSE_NONATTRIBUTE_COLUMNS": ("Review unnecessary MDX attribute support", "A hidden column/table retains IsAvailableInMDX and is not used by the checked sort, hierarchy or variation metadata.", "Validate Excel/MDX consumers before disabling it; report-only usage does not represent all external consumers."),
    "REDUCE_USAGE_OF_CALCULATED_COLUMNS_THAT_USE_THE_RELATED_FUNCTION": ("Review row-by-row lookups", "A calculated column contains a RELATED call pattern. Consider a suitable source transformation or model design.", "Regex heuristic, not a measured performance result. Do not replace a calculation without equivalence checks."),
    "REDUCE_NUMBER_OF_CALCULATED_COLUMNS": ("Review stored calculation complexity", "The model has more than five columns whose type is Calculated.", "Local threshold: 5. Inferred calculated-table columns are not counted by this expression. The acceptable number depends on model size and use."),
    "AVOID_FLOATING_POINT_DATA_TYPES": ("Review numeric precision", "A column uses Double. Confirm whether floating point or fixed decimal matches the business requirement.", "Double can be appropriate for scientific values; conversion can alter precision or range."),
    "NUMERIC_COLUMN_SUMMARIZE_BY": ("Avoid accidental default totals", "A visible numeric column has a default summary other than None.", "Checks Int64, Decimal and Double. Summation can be appropriate for business quantities; IDs often should not sum."),
    "HIDE_FOREIGN_KEYS": ("Reduce confusing authoring fields", "A visible column participates as a From-column on the many side of a relationship.", "The local expression compares column names within relationship usage. Verify the intended endpoint before hiding a field authors need."),
    "USE_THE_DIVIDE_FUNCTION_FOR_DIVISION": ("Handle division edge cases deliberately", "A calculation contains a closing bracket or parenthesis followed by a division operator. Consider DIVIDE([Profit], [Sales]).", "The pattern intentionally avoids comment delimiters but is not a DAX parser. It does not find every division and does not establish the desired zero-denominator result."),
    "AVOID_USING_THE_IFERROR_FUNCTION": ("Handle expected error cases explicitly", "A measure or calculated column contains an IFERROR call pattern.", "Review the failing operation, blanks and error semantics; a blanket rewrite may change behavior."),
    "FILTER_COLUMN_VALUES": ("Review broad table filtering inside CALCULATE", "A calculation matches a FILTER(Table, Table[Column]...) pattern inside CALCULATE/CALCULATETABLE.", "Regex-based and limited by expression shape. Prefer a narrower equivalent filter only after checking row/context semantics."),
    "FILTER_MEASURE_VALUES_BY_COLUMNS": ("Review measure-driven row filtering", "A calculation matches FILTER(Table, [Measure]...) inside CALCULATE/CALCULATETABLE.", "This may be intentional. A column filter is not automatically equivalent to a context-dependent measure predicate."),
    "AVOID_DUPLICATE_MEASURES": ("Review duplicated calculation definitions", "Another measure has an identical expression after stripping spaces, tabs and line breaks.", "Not semantic equivalence; it can miss equivalent formulas and can remove meaningful whitespace inside strings. Review before consolidating."),
    "MEASURES_SHOULD_NOT_BE_DIRECT_REFERENCES_OF_OTHER_MEASURES": ("Review simple alias measures", "The complete expression exactly equals another measure's DaxObjectName.", "Exact text comparison, not a parser. Aliases can be intentional for presentation, formatting or compatibility."),
    "INACTIVE_RELATIONSHIPS_THAT_ARE_NEVER_ACTIVATED": ("Review relationships with no detected activation", "An inactive relationship has no matching USERELATIONSHIP text in measures or calculation items for the checked endpoint order.", "Regex checks may miss reversed argument order or other valid forms. Do not delete a relationship based on this result alone."),
    "PROVIDE_FORMAT_STRING_FOR_NUMERIC_MEASURES": ("Give visible measures an explicit display format", "A visible measure has no format string, is not ImageUrl, and does not start with a quoted string expression.", "The name says numeric, but the expression does not infer the full return type. Review text-returning DAX before applying a numeric format."),
    "PQ_AVOID_TABLE_NESTEDJOIN": ("Review nested merge transformations", "M text contains Table.NestedJoin. Inspect folding and the data volume at the merge.", "Case-sensitive substring detection, not a folding test. Merges are normal operations and are not automatically defects."),
    "PQ_AVOID_TABLE_JOIN": ("Review join transformations", "M text contains Table.Join. Check whether the join belongs upstream or folds efficiently.", "Substring heuristic; no query is executed and no performance measurement is made."),
    "PQ_AVOID_FUZZY_JOINS": ("Review the cost of fuzzy matching", "M text contains Table.FuzzyJoin or Table.FuzzyNestedJoin.", "Fuzzy matching may be required; verify match quality and cost with representative data."),
    "PQ_AVOID_TABLE_DISTINCT": ("Review de-duplication cost and intent", "M text contains Table.Distinct.", "Not proof that duplicates exist or that folding is lost. Preserve the intended data grain."),
    "PQ_AVOID_REMOVE_DUPLICATES": ("Review explicit duplicate-removal calls", "M text contains Table.RemoveDuplicates.", "Narrow literal check, not a general duplicate detector or M function-validity check; standard Table.Distinct is covered separately."),
    "PQ_HARDCODED_LOCAL_PATHS": ("Make data sources portable", "M text matches a Windows drive path or Users directory pattern. Prefer a managed location or parameter.", "Does not cover every operating-system path, indirect source, credential or portability problem."),
    "MEASURE_NO_DESCRIPTION": ("Explain visible business calculations", "A measure and its table are visible, but the measure description is blank.", "Checks presence, not whether a description is accurate or useful."),
    "VISIBLE_COLUMN_NO_DESCRIPTION": ("Explain fields authors can see", "A column and its table are visible, but the column description is blank.", "Checks presence; generated descriptions still need business-owner review."),
    "MEASURE_NO_DISPLAY_FOLDER": ("Organize the measure catalog", "A non-hidden measure has no display folder.", "The expression does not exclude a measure simply because its table is hidden. Folder standards are repository/team policy."),
    "DESCRIPTION_EXCEEDS_COPILOT_200_CHARS": ("Keep descriptions concise", "A supported object's description exceeds 200 characters.", "Local documentation-length policy; this check alone does not validate Copilot readiness, licensing or every current product limit."),
    "VERTIPAQ_BIDI_HIGH_CARDINALITY": ("Review expensive filter propagation", "A column used in a bidirectional relationship has Vertipaq_Cardinality greater than 100,000.", "Optional only. Requires measured annotations; metadata-only CI does not populate them."),
    "VERTIPAQ_LONG_LENGTH_HIGH_CARDINALITY": ("Review long-value storage cost", "LongLengthRowCount annotation exceeds 500,000.", "Optional annotation-driven heuristic; verify what the measurement represents in the supplying tool."),
    "VERTIPAQ_SPLIT_DATE_AND_TIME": ("Review timestamp storage granularity", "DateTimeWithHourMinSec annotation is greater than zero.", "Optional. Splitting dates and times changes the field model; preserve required timestamp precision."),
    "VERTIPAQ_LARGE_TABLES_PARTITIONED": ("Review refresh management for large tables", "Vertipaq_RowCount is greater than 25 million and the table has exactly one partition.", "Optional threshold-based guidance; partitions do not automatically improve every query or refresh workload."),
    "VERTIPAQ_FIX_REFERENTIAL_INTEGRITY": ("Investigate orphaned relationship keys", "Vertipaq_RIViolationInvalidRows annotation is greater than zero.", "Optional measured-data rule; fix the source/key semantics rather than simply hiding blank members."),
    "PBIR_BROKEN_FIELD_REF": ("Keep report bindings connected to the model", "A parsed visual/filter references a missing measure name or table/column pair.", "Python cross-layer check, severity 3. Uses parsed bindings, not visual rendering or every possible PBIR feature. Legacy Column-syntax measure references have a compatibility fallback."),
    "PBIR_UNUSED_MEASURE": ("Review apparently unused visible measures", "No parsed report binding or transitive dependency from a used measure reaches the visible measure.", "Python check, severity 2. External Excel, thin reports, ad-hoc DAX and unparsed bindings can still use it. Do not auto-delete."),
    "PBIR_UNUSED_TABLE": ("Review apparently disconnected business objects", "A visible table is not reached from parsed bindings, DAX references or the traversed relationship graph.", "Python check, severity 2. The implementation traverses all listed relationships, including inactive ones; it does not prove that the table has no external consumers."),
    "PBIP_RUNTIME_CACHE_COMMITTED": ("Keep machine-local runtime files out of Git", "Tracked ticket files include .pbi/localSettings.json or .pbi/*.abf cache state.", "Python check, severity 3. This is a specific tracked-file check, not a secret scanner or a full .gitignore audit. Ignore rules prevent new files; tracked files also need untracking."),
}

CSS = r"""
:root{--bg:#f7f8fb;--surface:#fff;--text:#242938;--muted:#687287;--line:#e0e4ed;--accent:#7154c4;--soft:#eee9fb;--good:#197754;--warn:#996419;--bad:#bc435d;color-scheme:light}
[data-theme=dark]{--bg:#10151f;--surface:#191f2b;--text:#e4e9f2;--muted:#a2adc0;--line:#30394b;--accent:#b9a2ff;--soft:#2d2545;--good:#71d2b1;--warn:#e8bd76;--bad:#ff91a4;color-scheme:dark}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.65 Geist,'Segoe UI',sans-serif}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}button,input,select{font:inherit}button,select{cursor:pointer}button,a,input,select,summary{outline-offset:4px}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--accent)}.side{position:fixed;width:230px;inset:0 auto 0 0;padding:28px 20px;border-right:1px solid var(--line);background:var(--surface);overflow:auto}.brand{font-weight:650;font-size:18px;letter-spacing:-.5px;display:flex;gap:10px;align-items:center}.mark{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--soft);color:var(--accent)}.side small,.eyebrow{color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;font-size:10px}.side nav{display:grid;gap:6px;margin-top:25px}.side nav a{padding:9px 12px;border-radius:7px;color:var(--muted)}.side nav a:hover,.side nav a.current{background:var(--soft);color:var(--accent);text-decoration:none}.side footer{font-size:11px;color:var(--muted);margin-top:35px}.app{margin-left:230px}.top{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--line);padding:14px 30px;display:flex;align-items:center;gap:12px;font-size:12px}.grow{flex:1}.btn{border:1px solid var(--line);border-radius:7px;background:var(--surface);padding:7px 12px;color:var(--text);transition:background .15s,transform .1s}.btn:hover{background:var(--soft)}.btn:active{transform:translateY(1px)}main{max-width:1220px;padding:44px 38px 80px;margin:auto}h1{font-size:42px;line-height:1.15;letter-spacing:-1.5px;font-weight:600;margin:14px 0 18px;max-width:850px}h2{font-size:23px;letter-spacing:-.5px;margin:0 0 12px}h3{font-size:16px;margin:0 0 8px}p{margin:8px 0 15px}.lead{font-size:17px;color:var(--muted);max-width:810px}.pill{display:inline-flex;align-items:center;border-radius:5px;padding:3px 8px;font-size:11px;background:var(--soft);color:var(--accent);gap:5px}.pill.good{color:var(--good)}.pill.warn{color:var(--warn)}.pill.bad{color:var(--bad)}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px;margin:25px 0}.card,.panel,.rule{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:23px}.card p{font-size:13px;color:var(--muted);margin-bottom:0}.card b.big{display:block;font-size:28px;margin:12px 0}section{margin-top:48px}.callout{border-left:3px solid var(--accent);background:var(--soft);padding:16px 20px;border-radius:0 8px 8px 0;margin:22px 0}.callout p{margin:0}.tree{list-style:none;padding:0;margin:20px 0}.tree ul{list-style:none;border-left:1px solid var(--line);padding:0 0 0 28px;margin:15px 0 15px 20px}.tree li{position:relative;margin:14px 0}.tree ul>li:before{content:'';position:absolute;width:28px;left:-28px;top:24px;border-top:1px solid var(--line)}.node{display:block;padding:15px 18px;background:var(--surface);border:1px solid var(--line);border-radius:9px;max-width:900px}.node summary{cursor:pointer;font-weight:550}.node p,.node ol{color:var(--muted);font-size:13px;margin-bottom:4px}.step{display:inline-grid;place-items:center;width:25px;height:25px;border-radius:7px;background:var(--soft);color:var(--accent);margin-right:10px;font-size:12px}.muted{color:var(--muted)}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--surface)}table{width:100%;border-collapse:collapse;font-size:13px;text-align:left}th,td{padding:13px 16px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:11px;color:var(--muted);background:var(--bg)}tr:last-child td{border-bottom:0}code,pre{font-family:Consolas,monospace;font-size:12px}code{overflow-wrap:anywhere}pre{background:var(--bg);border:1px solid var(--line);padding:16px;border-radius:8px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}.filters{display:flex;gap:10px;flex-wrap:wrap;position:sticky;top:65px;background:var(--bg);padding:16px 0;z-index:3}.filters input,.filters select{border:1px solid var(--line);border-radius:8px;padding:10px 14px;background:var(--surface);color:var(--text);min-width:155px}.filters input{flex:1;min-width:230px}.rule{margin:14px 0;scroll-margin-top:160px}.rule h3{font-size:19px}.rule-id{font-size:10px;letter-spacing:.25px;color:var(--muted);margin:12px 0;overflow-wrap:anywhere}.rule details{margin-top:16px}.rule summary{cursor:pointer;color:var(--accent);font-size:12px}.two{display:grid;grid-template-columns:1fr 1fr;gap:22px}.label{display:block;text-transform:uppercase;font-size:10px;letter-spacing:1px;color:var(--muted);margin:16px 0 6px}.rule[hidden]{display:none}.result{font-size:12px;color:var(--muted);margin:4px 0 18px}.empty{padding:30px;text-align:center;color:var(--muted)}.end{border-top:1px solid var(--line);margin-top:45px;padding-top:20px;color:var(--muted);font-size:11px}
@media(max-width:1000px){.side{width:185px}.app{margin-left:185px}main{padding:30px 24px}.grid{grid-template-columns:1fr}h1{font-size:34px}.two{grid-template-columns:1fr}}
@media(max-width:650px){.side{position:static;width:auto;border-right:0;border-bottom:1px solid var(--line);padding:16px}.side nav{display:flex;flex-wrap:wrap;margin:10px 0 0;gap:2px}.side footer,.side small{display:none}.app{margin-left:0}.top{padding:10px 16px}main{padding:25px 16px}h1{font-size:30px}.tree ul{margin-left:8px;padding-left:16px}.tree ul>li:before{left:-16px;width:16px}.filters{position:static}.top .muted{display:none}}
@media print{.side,.top,.filters,.no-print{display:none}.app{margin:0}main{max-width:none;padding:0}body{background:white;color:#222;font-size:11px}.card,.panel,.rule,.node{break-inside:avoid;box-shadow:none}h1{font-size:30px}section{margin-top:24px}.rule[hidden]{display:block}a{color:#333}details> :not(summary){display:block!important}}
.guide-pages{list-style:none;padding:0;margin:0}.guide-pages>li+li{margin-top:10px}.side nav .page-link{display:block;font-weight:600;color:var(--text)}.side nav .page-link.current{background:var(--soft);color:var(--accent)}
@media(max-width:650px){.side nav{display:block}.guide-pages{display:grid;grid-template-columns:1fr 1fr;gap:12px}.guide-pages>li+li{margin-top:0}}
.inpage-nav{position:fixed;right:12px;top:50%;transform:translateY(-50%);display:grid;gap:2px;z-index:8;padding:8px 3px;background:var(--surface);border:1px solid var(--line);border-radius:20px;box-shadow:0 3px 14px #00000008}.inpage-nav .section-link{position:relative;display:flex;align-items:center;justify-content:center;width:30px;height:26px}.nav-tick{width:9px;height:2px;background:var(--muted);opacity:.5;transition:width .15s,opacity .15s,background .15s}.section-link[aria-current=location] .nav-tick{width:23px;background:var(--accent);opacity:1}.section-link:hover .nav-tick,.section-link:focus-visible .nav-tick{width:18px;opacity:1}.nav-tooltip{position:absolute;right:40px;white-space:nowrap;pointer-events:none;opacity:0;transform:translateX(5px);transition:opacity .15s,transform .15s;background:var(--surface);border:1px solid var(--line);box-shadow:0 4px 16px #00000012;border-radius:6px;padding:6px 10px;font-size:12px;color:var(--text)}.section-link:hover .nav-tooltip,.section-link:focus-visible .nav-tooltip{opacity:1;transform:translateX(0)}main{padding-right:64px}.workflow-diagram{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:auto;margin:24px 0}.workflow-diagram svg{display:block;width:100%;min-width:700px;height:auto}.flow-edges{stroke:var(--muted);stroke-width:1.5;stroke-linejoin:round}.flow-edges .edge-fail{stroke:var(--bad)}.flow-edges .edge-pass{stroke:var(--good)}.flow-edges .edge-error{stroke:var(--warn);stroke-dasharray:5 4}.flow-node rect,.flow-node>path{fill:var(--surface);stroke:var(--line);stroke-width:1.5}.flow-node text{text-anchor:middle;fill:var(--text);font-size:14px;font-weight:550}.flow-node .flow-sub{fill:var(--muted);font-size:11px;font-weight:400}.flow-gate>path,.flow-evidence rect{fill:var(--soft);stroke:var(--accent)}.flow-fail rect{stroke:var(--bad)}.flow-pass rect{stroke:var(--good)}.flow-error rect{stroke:var(--warn)}.flow-labels text{fill:var(--muted);font-size:10px}.rule-catalog table{min-width:900px;font-size:12px}.rule-catalog th{white-space:nowrap}.rule-catalog .rule{padding:0;border:0;border-radius:0;scroll-margin-top:150px}.rule-catalog .rule:hover{background:var(--bg)}.rule-catalog td{vertical-align:middle;padding:14px}.rule-catalog td:first-child{min-width:280px;max-width:400px}.rule-catalog strong{font-size:12px;font-weight:550}.rule-catalog .rule-id{display:block;font-size:9px;line-height:1.5;margin:5px 0 0}.scope-cell{max-width:180px;color:var(--muted);font-size:11px;overflow-wrap:anywhere}.rule-toggle{font-size:11px;padding:6px 10px;min-width:62px}.rule-toggle[aria-expanded=true]{background:var(--soft);border-color:var(--accent);color:var(--accent)}.rule-detail[hidden]{display:none}.rule-detail>td{padding:0!important}.rule-body{padding:24px 28px;background:var(--bg);border-left:3px solid var(--accent)}.rule-body h3{font-size:20px;margin-top:8px}.rule-body details{margin-top:18px}.rule-body summary{cursor:pointer;color:var(--accent)}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:650px){main{padding-right:45px}.inpage-nav{right:4px}.inpage-nav .section-link{width:24px;height:24px}.nav-tooltip{right:32px}.workflow-diagram svg{min-width:620px}.rule-body{padding:18px}}
@media print{.inpage-nav{display:none}.workflow-diagram{overflow:visible}.workflow-diagram svg{min-width:0;width:100%}.rule-catalog{overflow:visible}.rule-catalog table{min-width:0;font-size:9px}.rule-catalog tr.rule[hidden],.rule-detail[hidden]{display:table-row}.rule-toggle{display:none}.rule-catalog td:first-child{min-width:0}.rule-catalog td{padding:6px}.rule-detail{break-inside:avoid}}


.section-arrival{animation:section-arrival 1.2s ease-out;border-radius:5px}@keyframes section-arrival{from{background:var(--soft);box-shadow:0 0 0 8px var(--soft)}to{background:transparent;box-shadow:0 0 0 0 transparent}}html:has(dialog:modal){overflow:hidden}.rule-dialog{padding:0;width:min(960px,calc(100vw - 48px));max-height:85svh;overflow:auto;border:1px solid var(--line);border-radius:14px;background:var(--surface);color:var(--text);box-shadow:0 24px 90px #00000040}.rule-dialog::backdrop{background:#080c1770;backdrop-filter:blur(4px)}.dialog-header{position:sticky;top:0;z-index:2;display:flex;align-items:flex-start;justify-content:space-between;gap:24px;padding:24px 28px;background:var(--surface);border-bottom:1px solid var(--line)}.dialog-header h2{font-size:20px;line-height:1.4;margin:8px 0 0}.dialog-close{flex-shrink:0}.rule-dialog .rule-body{background:var(--surface);border-left:0}.rule-dialog details{margin-top:8px}.rule-dialog pre{white-space:pre-wrap}.rule-dialog:not([open]){display:none}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.section-arrival{animation:none}}
@media(max-width:650px){.rule-dialog{width:calc(100vw - 20px);max-height:92svh}.dialog-header{padding:18px;gap:12px}}
@media print{main>section:last-of-type{min-height:0}.rule-dialog:not([open]),.rule-dialog[open]{display:block;position:static;width:auto;max-height:none;overflow:visible;border:0;border-top:1px solid #aaa;box-shadow:none;margin:20px 0;break-inside:avoid}.dialog-header{position:static;padding:12px 0}.dialog-close{display:none}.rule-dialog .rule-body{padding:0}.section-arrival{animation:none}}

"""

SCRIPT = """
const root=document.documentElement;
const $=id=>document.getElementById(id);
const esc=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const uiIcon=name=>`<svg class="ui-icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
function setGuideTheme(theme){
    const current=theme==='dark'?'dark':'light';root.dataset.theme=current;
    $('theme').innerHTML=uiIcon(current==='dark'?'moon':'sun')+`<span>${current==='dark'?'Dark':'Light'}</span>`;
    $('theme').setAttribute('aria-label',`Switch to ${current==='dark'?'light':'dark'} theme`);
    $('theme').title=$('theme').getAttribute('aria-label');
    try{localStorage.setItem('lineage-guide-theme',current);}catch{}
}
let guideTheme='light';try{guideTheme=localStorage.getItem('lineage-guide-theme')||'light';}catch{}
setGuideTheme(guideTheme);
$('theme').onclick=()=>setGuideTheme(root.dataset.theme==='dark'?'light':'dark');
document.getElementById('print').onclick=()=>{document.querySelectorAll('details').forEach(d=>d.open=true);window.print();};
const sectionLinks=[...document.querySelectorAll('.section-link')];
const sectionTargets=sectionLinks.map(link=>document.getElementById(link.hash.slice(1)));
let sectionFrame=false, selectedSection=null;
function highlightSection(){
    let active=0;
    sectionTargets.forEach((target,index)=>{if(target&&target.getBoundingClientRect().top<=150)active=index;});
    if(selectedSection!==null)active=selectedSection;
    sectionLinks.forEach((link,index)=>{if(index===active)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');});
    sectionFrame=false;
}
window.addEventListener('scroll',()=>{if(!sectionFrame){sectionFrame=true;requestAnimationFrame(highlightSection);}},{passive:true});
window.addEventListener('hashchange',()=>{const index=sectionLinks.findIndex(link=>link.hash===location.hash);selectedSection=index>=0?index:null;highlightSection();});
window.addEventListener('wheel',()=>{selectedSection=null;},{passive:true});
window.addEventListener('touchstart',()=>{selectedSection=null;},{passive:true});
window.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp','PageDown','PageUp','Home','End',' '].includes(event.key))selectedSection=null;});
highlightSection();
sectionLinks.forEach((link,index)=>link.addEventListener('click',()=>{
    selectedSection=index;highlightSection();
    const heading=sectionTargets[index]?.querySelector('h2');
    if(!heading)return;
    heading.setAttribute('tabindex','-1');
    heading.focus({preventScroll:true});
    heading.classList.remove('section-arrival');
    void heading.offsetWidth;
    heading.classList.add('section-arrival');
}));

const search=document.getElementById('search');
if(search){
    const controls=['search','severity','engine'].map(id=>document.getElementById(id));
    const rows=[...document.querySelectorAll('tr.rule')];
    rows.forEach(row=>{
        const button=row.querySelector('.rule-toggle');
        const detail=document.getElementById(button.getAttribute('aria-controls'));
        button.onclick=()=>detail.showModal();
        detail.querySelector('.dialog-close').onclick=()=>detail.close();
        detail.addEventListener('click',event=>{
            const bounds=detail.getBoundingClientRect();
            if(event.target===detail&&(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom))detail.close();
        });
    });
    function filter(){
        const q=search.value.toLowerCase();let count=0;
        rows.forEach(row=>{
            const button=row.querySelector('.rule-toggle');
            const detail=document.getElementById(button.getAttribute('aria-controls'));
            const show=(row.textContent+' '+detail.textContent).toLowerCase().includes(q)&&(controls[1].value==='all'||row.dataset.severity===controls[1].value)&&(controls[2].value==='all'||row.dataset.engine===controls[2].value);
            row.hidden=!show;
            if(show)count++;
        });
        document.getElementById('count').textContent=count+' of '+rows.length+' rules';
        document.getElementById('empty').hidden=count!==0;
    }
    controls.forEach(el=>{el.addEventListener('input',filter);el.addEventListener('change',filter);});
    document.getElementById('reset').onclick=()=>{search.value='';controls.slice(1).forEach(el=>el.value='all');enhanceSelects();filter();};
    filter();
}

"""


CONTROL_LAYOUT = """
:root,:root[data-theme="dark"]{--bg:var(--subtle);--soft:var(--accent-soft);--good:var(--success);--warn:var(--warning);--bad:var(--danger)}
body{background:var(--bg)}.btn{display:inline-flex;align-items:center;justify-content:center;font-weight:400;transform:none}.btn:active{transform:none}.top{height:58px;padding:0 24px;gap:10px}.filters{gap:10px}.filters input{font-size:11px;border-radius:8px;padding:8px 12px;min-height:34px}.filters .select-trigger{min-width:155px}.rule-catalog td:first-child>strong{display:block}.rule-catalog .rule-id{display:inline-block;margin:6px 0 0}.definition-cell{min-width:260px;max-width:430px;color:var(--muted);font-size:11px;line-height:1.7}.rule-catalog td+td{border-left:1px solid var(--line)}
main{padding-bottom:28px}main>section:nth-last-of-type(-n+2){margin-top:28px}.end{margin-top:28px}.select-popover{line-height:1.6}button:focus-visible,input:focus-visible{outline:2px solid var(--accent-border);outline-offset:2px}
@media(max-width:650px){.top{height:auto;min-height:58px;padding:10px 16px}.theme-switch{min-width:32px;padding:7px}.theme-switch span{display:none}}
@media print{.select-control{display:none}}
"""


def shared_controls(assets: Path) -> tuple[str, str, str]:
    """Embed the portal's existing controls without loading its report application."""
    styles = (assets / "styles.css").read_text(encoding="utf-8")
    app = (assets / "app.js").read_text(encoding="utf-8")
    template = (assets / "index.html").read_text(encoding="utf-8")
    tokens = ':root {' + styles.split(':root {', 1)[1].split('html,body{', 1)[0]
    primitives = re.findall(r'(?:^|})(\.btn\{[^}]+\})', styles)
    for prefix in ('.ui-icon{', '.theme-switch{', '.native-select{', '.select-popover{', '.technical-id{', '.btn,button.pill,', '.btn:hover:', '.btn:active:', '.btn:focus-visible'):
        primitives.extend(line for line in styles.splitlines() if line.startswith(prefix))
    dropdown = app[app.index('const selectControllers='):app.index('let savedTheme =')]
    symbols = ''.join(re.search(r'<symbol id="i-' + name + r'".*?</symbol>', template).group() for name in ('sun', 'moon', 'chevron', 'check', 'search'))
    return tokens + '\n'.join(primitives), dropdown + '\nenhanceSelects();', '<svg width="0" height="0" aria-hidden="true" style="position:absolute;overflow:hidden"><defs>' + symbols + '</defs></svg>'


def page(title: str, body: str, links: list[tuple[str, str]], current: str) -> str:
    assets = ROOT / "scripts/pbi_cicd/portal"
    font = (assets / "geist.css").read_text(encoding="utf-8")
    control_styles, control_script, symbols = shared_controls(assets)
    license_text = html.escape("\n".join(line.rstrip() for line in (assets / "GEIST-OFL.txt").read_text(encoding="utf-8").splitlines()))
    sections = ''.join(f'<a class="section-link" href="{url}" aria-label="{html.escape(label)}"><span class="nav-tick"></span><span class="nav-tooltip">{html.escape(label)}</span></a>' for url, label in links)
    nav = '<ul class="guide-pages">'
    for key, filename, label in [("workflow", "workflow.html", "Workflow guide"), ("rules", "bpa-rulebook.html", "BPA rulebook")]:
        active = key == current
        attributes = ' class="page-link current" aria-current="page"' if active else ' class="page-link"'
        nav += f'<li><a{attributes} href="{filename}">{label}</a>'
        nav += '</li>'
    nav += '</ul>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — Lineage Studio</title><style>{font}{CSS}{control_styles}{CONTROL_LAYOUT}</style></head><body>{symbols}
<aside class="side"><div class="brand"><span class="mark">◈</span>Lineage Studio</div><p><small>Project guides</small></p><nav aria-label="Guide pages and sections">{nav}</nav><footer>Power BI CI/CD<br>Source-backed explanation<br>English · 13 November 2026<br><a href="https://hieutc2308.github.io/powerbi-cicd/">Open the live report catalog</a></footer></aside>
<div class="app"><header class="top"><span>Guides / <b>{html.escape(title)}</b></span><span class="grow"></span><button class="btn theme-switch" id="theme" aria-label="Switch color theme">Light</button><button class="btn" id="print">Print / PDF</button></header><nav class="inpage-nav" aria-label="On this page">{sections}</nav><main>{body}<footer class="end">Maintained from repository configuration and workflow source. Static analysis supports review; it does not replace business validation, data refresh testing or security approval.</footer></main></div><script>{SCRIPT}{control_script}</script><pre hidden>{license_text}</pre></body></html>'''


WORKFLOW = '''
<span class="eyebrow">A proposal for governed report changes</span><h1>From a report change<br>to a reviewable decision.</h1><p class="lead">Every ticket gets an independent check, an understandable findings report and its own documentation. Reviewers can inspect a failed change before deciding what to fix or approve.</p>
<div class="row"><span class="pill good">Phase 1 · Implemented on GitHub</span><span class="pill">Read-only model analysis</span><span class="pill warn">Service deployment · Planned</span></div>
<div class="grid"><article class="card"><span class="eyebrow">Visibility</span><b class="big">One ticket. One trail.</b><p>Connect the proposed change, its checks, findings and documentation in one pull request.</p></article><article class="card"><span class="eyebrow">Quality</span><b class="big">Review before merge.</b><p>Blocking findings fail the CI check. Warnings stay visible for informed judgment.</p></article><article class="card"><span class="eyebrow">Continuity</span><b class="big">Failed changes stay inspectable.</b><p>Documentation is generated and uploaded before the quality Gate is enforced.</p></article></div>
<section id="overview"><h2>The workflow at a glance</h2><p class="muted">Follow the arrows from ticket to publication. A failed quality Gate keeps its documentation available for review.</p>
<div class="workflow-diagram"><svg viewBox="0 0 1120 1110" role="img" aria-labelledby="flow-title flow-desc" xmlns="http://www.w3.org/2000/svg">
<title id="flow-title">Report change, CI quality Gate and documentation publication</title><desc id="flow-desc">Ticket branch to pull request, checks, analysis and artifact upload before a quality Gate. Failures return to the author; pass proceeds to review and merge. Main triggers independent CI and Pages workflows. Extraction failures may prevent artifacts. Pages does not depend on the report Gate.</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>
<g class="flow-edges" fill="none" marker-end="url(#arrow)">
<path d="M500 112V146"/><path d="M500 220V254"/><path d="M500 328V362"/><path d="M500 436V470"/><path d="M500 544V580"/>
<path class="edge-fail" d="M415 635H225V720"/><path class="edge-pass" d="M585 635H745V720"/>
<path class="edge-fail" d="M100 757H45V183H365"/>
<path class="edge-error" d="M635 399H900V470"/>
<path d="M745 794V834"/><path d="M745 908V928H540V958"/><path d="M745 928H920V958"/><path d="M920 1032V1055"/>
</g>
<g class="flow-labels"><text x="242" y="623">FAIL / RULE ERROR</text><text x="630" y="623">PASS</text><text x="58" y="168">Fix &amp; push again</text><text x="775" y="387">Extraction failure</text><text x="758" y="948">Independent workflows</text></g>
<g class="flow-node"><rect x="365" y="38" width="270" height="74" rx="10"/><text x="500" y="68">Ticket + report branch</text><text class="flow-sub" x="500" y="92">Author · reports/TEST-002/</text></g>
<g class="flow-node"><rect x="365" y="146" width="270" height="74" rx="10"/><text x="500" y="176">Pull request to main</text><text class="flow-sub" x="500" y="200">Open / update / reopen</text></g>
<g class="flow-node"><rect x="365" y="254" width="270" height="74" rx="10"/><text x="500" y="284">Select tickets + run tests</text><text class="flow-sub" x="500" y="308">Changed tickets; shared changes = all</text></g>
<g class="flow-node"><rect x="365" y="362" width="270" height="74" rx="10"/><text x="500" y="392">Analyze each ticket</text><text class="flow-sub" x="500" y="416">TE2 + Python · read-only</text></g>
<g class="flow-node flow-evidence"><rect x="365" y="470" width="270" height="74" rx="10"/><text x="500" y="500">Generate docs + upload artifact</text><text class="flow-sub" x="500" y="524">Saved before Gate enforcement</text></g>
<g class="flow-node flow-error"><rect x="765" y="470" width="270" height="74" rx="10"/><text x="900" y="500">Diagnose logs + retry</text><text class="flow-sub" x="900" y="524">Complete docs not guaranteed</text></g>
<g class="flow-node flow-gate"><path d="M500 580L585 635L500 690L415 635Z"/><text x="500" y="632">Quality Gate</text><text class="flow-sub" x="500" y="653">Any blockers?</text></g>
<g class="flow-node flow-fail"><rect x="100" y="720" width="250" height="74" rx="10"/><text x="225" y="750">Review findings + fix</text><text class="flow-sub" x="225" y="774">Artifact remains downloadable</text></g>
<g class="flow-node flow-pass"><rect x="610" y="720" width="270" height="74" rx="10"/><text x="745" y="750">Human review + approval</text><text class="flow-sub" x="745" y="774">Business meaning + technical impact</text></g>
<g class="flow-node"><rect x="610" y="834" width="270" height="74" rx="10"/><text x="745" y="864">Merge to main</text><text class="flow-sub" x="745" y="888">Requires configured branch protection</text></g>
<g class="flow-node"><rect x="405" y="958" width="270" height="74" rx="10"/><text x="540" y="988">CI validates merged diff</text><text class="flow-sub" x="540" y="1012">Selected ticket jobs + tests</text></g>
<g class="flow-node flow-evidence"><rect x="785" y="958" width="270" height="74" rx="10"/><text x="920" y="988">Pages rebuilds all tickets</text><text class="flow-sub" x="920" y="1012">Separate build · report Gates advisory</text></g>
<g class="flow-node flow-pass"><rect x="785" y="1055" width="270" height="44" rx="10"/><text x="920" y="1083">Latest successful portal</text></g>
</svg></div>
<div class="grid"><article class="card"><h3>Before the Gate</h3><p>Each ticket's artifact contains the standalone HTML, Markdown docs, BPA results and extraction evidence. No data refresh or model rewrite is performed.</p></article><article class="card"><h3>When a check fails</h3><p>Inspect the artifact and fix the source. Extraction or infrastructure failure may leave incomplete output. The aggregate PBIP CI status must be configured as a required branch check to block merges.</p></article><article class="card"><h3>After merge</h3><p>Main CI validates the merged diff. Separately, Pages tests and rebuilds every current ticket; deployment requires ENABLE_GITHUB_PAGES=true. A failed publication leaves the previous site available.</p></article></div>
<div class="callout"><p><b>Current publication policy:</b> Pages does not depend on the CI Gate job and does not enforce report Gates. It can publish docs with a FAIL badge if analysis succeeds. Build/extraction/deployment failure prevents a new publication. A stricter Gate-before-publication policy is proposed for Phase 2, not implemented today.</p></div></section>
<section id="selection"><h2>Which reports are checked?</h2><div class="table-wrap"><table><thead><tr><th>What changes?</th><th>Selected ticket jobs</th><th>What reviewers see</th></tr></thead><tbody>
<tr><td>Only files under reports/TEST-002/</td><td>TEST-002</td><td>Its Gate, artifact and summary. An unrelated failing TEST-001 is not automatically included.</td></tr>
<tr><td>Multiple ticket folders</td><td>Those current tickets</td><td>A separate result per ticket; any selected failure fails the combined CI status.</td></tr>
<tr><td>Shared code, rules, tests or workflows</td><td>All current tickets</td><td>The shared change can affect every report, so all are checked.</td></tr>
<tr><td>README or plan only</td><td>No report analysis</td><td>Regression tests still run; CI can pass with the analysis job legitimately skipped.</td></tr>
<tr><td>Manual CI run / initial push</td><td>All current tickets</td><td>A complete analysis selection.</td></tr>
<tr><td>Ticket renamed or deleted</td><td>Surviving affected tickets; deleted keys recorded</td><td>No attempt to analyze a removed project. A successful Pages rebuild removes obsolete catalog entries.</td></tr></tbody></table></div>
<details class="panel" style="margin-top:15px"><summary>Exact shared-change paths for the technical owner</summary><p><code>scripts/</code>, <code>config/</code>, <code>tests/</code>, <code>.github/</code>; root <code>pyproject.toml</code>, <code>.gitattributes</code>, <code>.gitignore</code>, <code>AGENTS.md</code>. PR events target main; the current workflow uses GitHub's default opened, synchronize and reopened PR events. Fork PRs do not receive the write-token summary job.</p></details></section>
<section id="decisions"><h2>What does the Gate mean?</h2><div class="grid"><article class="card"><span class="pill bad">Severity 3 · Blocking</span><h3 style="margin-top:14px">Fix or review policy explicitly</h3><p>Examples: a report binds to a missing field, or known relationship endpoint types disagree. The configured threshold is severity ≥ 3.</p></article><article class="card"><span class="pill warn">Severity 2 · Warning</span><h3 style="margin-top:14px">Investigate in context</h3><p>Performance heuristics, portability concerns and unresolved offline types. Warnings do not fail the current Gate.</p></article><article class="card"><span class="pill">Severity 1 · Information</span><h3 style="margin-top:14px">Improve authoring quality</h3><p>Descriptions, display folders and other maintainability recommendations. They remain visible in the portal.</p></article></div><p>Rule evaluation errors are a separate failure condition. A rule that could not execute must not be mistaken for a clean result. Infrastructure problems can also fail CI before any Gate result is available.</p><p><a href="bpa-rulebook.html">Explore all rules and their limitations in the BPA Rulebook.</a></p></section>
<section id="evidence"><h2>Where is the evidence?</h2><div class="two"><article class="panel"><span class="pill">Before merge · Exact PR snapshot</span><h3 style="margin-top:15px">The PR summary and artifacts</h3><p>The bot comment includes selected ticket results and exact-run artifact links. Download the ZIP, extract it and open <code>index.html</code> in Chrome or Edge. Bundles are kept for 30 days under the current configuration.</p><p class="muted">The summary's published main portal link is not a preview of the unmerged PR. Fork PRs still receive checks/artifacts but no bot comment from this job.</p></article><article class="panel"><span class="pill good">After deploy · Shared reference</span><h3 style="margin-top:15px">The live Lineage Studio catalog</h3><p>The published site represents the latest <b>successful Pages deployment</b>, not necessarily the newest commit. Failed publication leaves the previous version available; browser/CDN caching can briefly show old content.</p><p class="muted">Source provenance binds outputs to ticket definitions and prevents accidental reuse of stale TE2 files.</p></article></div><div class="callout"><p><b>Confidentiality:</b> the standalone HTML contains model definitions and report metadata. “Only HTML is published” does not mean sensitive content has been redacted. The current GitHub repository and Pages site are public by owner approval. Internal rollout needs an approved audience and access controls.</p></div></section>
<section id="people"><h2>Who owns each decision?</h2><div class="table-wrap"><table><thead><tr><th>Role</th><th>Responsibility</th><th>Evidence to review</th></tr></thead><tbody><tr><td>Report author</td><td>Prepare ticket source, resolve findings and explain intended behavior.</td><td>PR diff, ticket artifact, model/lineage details.</td></tr><tr><td>Business / report owner</td><td>Confirm measures, report meaning and acceptance criteria.</td><td>Business validation and representative report output; CI alone cannot supply this.</td></tr><tr><td>Technical reviewer</td><td>Review dependencies, bindings, warnings and regression risk.</td><td>Gate results, source diff, test results, impact in the portal.</td></tr><tr><td>Repository / platform owner</td><td>Configure protected branches, credentials, publication audience and future deployment approvals.</td><td>Settings, required checks, environment access and deployment logs.</td></tr></tbody></table></div></section>
<section id="roadmap"><h2>Adopt in three phases</h2><div class="grid"><article class="card"><span class="pill good">01 · Done</span><h3 style="margin-top:14px">Validate on GitHub</h3><p>Multi-ticket CI, rule checks, artifacts, PR summaries and public documentation. PR #1 exercised failure, correction, successful checks and merge for Hardware sales report.</p></article><article class="card"><span class="pill">02 · Planned</span><h3 style="margin-top:14px">Move to GitLab</h3><p>Port CI to the target instance and runner; verify HTML artifact preview, MR summaries, Pages access control and retention. Optional MR preview URLs depend on the actual version/tier.</p></article><article class="card"><span class="pill">03 · Planned</span><h3 style="margin-top:14px">Deploy and connect Jira</h3><p>Integrate Power BI or Fabric deployment pipelines with approved Dev/Test/Prod promotion and Jira ticket context. Service deployment and Jira updates are not implemented today.</p></article></div><p class="muted">The proposed flow is incremental: establish review evidence first, then confirm the internal hosting controls, then automate promotion. The root PLAN.md is the authoritative progress record.</p></section>
<section id="proposal"><h2>What stakeholders are being asked to approve</h2><ol><li>Adopt one ticket folder and one review trail for each report change.</li><li>Nominate business and technical reviewers; agree which findings should block a merge.</li><li>Approve internal hosting, retention and access to model/report documentation.</li><li>Provide a GitLab pilot project and runner for Phase 2.</li><li>Agree deployment ownership and acceptance checks before Phase 3 promotion automation.</li></ol><p class="muted">Passing CI provides repeatable technical evidence. It supports, rather than replaces, ownership and approval.</p></section>
'''


def catalog() -> list[dict]:
    rows = []
    for file, engine in [("bpa-rules.json", "te2"), ("bpa-rules-vertipaq.json", "optional")]:
        for rule in json.loads((ROOT / "config" / file).read_text(encoding="utf-8-sig")):
            rows.append({**rule, "engine": engine, "source": f"config/{file}"})
    source_path = ROOT / "scripts/pbi_cicd/bpa_analyzer.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            data = {key.value: value.value for key, value in zip(node.keys, node.values) if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)}
            if "ruleId" in data:
                found[data["ruleId"]] = data
    for rule in found.values():
        rows.append({"ID": rule["ruleId"], "Name": rule["ruleName"], "Description": rule["description"], "Category": rule["category"], "Severity": rule["severity"], "Scope": rule.get("objectType", "Report binding"), "Expression": NOTES[rule["ruleId"]][1], "engine": "python", "source": "scripts/pbi_cicd/bpa_analyzer.py"})
    assert len(rows) == 49 and {r["ID"] for r in rows} == set(NOTES), "Update explanations when the catalog changes"
    return rows


def rulebook(rows: list[dict]) -> str:
    esc = html.escape
    engine_labels = {"te2": "Default TE2", "python": "Python cross-layer", "optional": "Optional VertiPaq"}
    body = '''<span class="eyebrow">The quality policy, made inspectable</span><h1>What each check means.<br>And what it cannot prove.</h1><p class="lead">A practical reference for reviewers and model owners. Browse the catalog, filter the checks and open Details for the exact logic and customization guidance.</p><div class="row"><span class="pill">40 default TE2 rules</span><span class="pill">4 Python checks</span><span class="pill warn">5 optional VertiPaq rules</span></div>
<section id="catalog"><h2>Explore the 49 checks</h2><div class="filters"><input id="search" type="search" placeholder="Search intent, rule ID, threshold or expression" aria-label="Search BPA rules"><select id="severity" aria-label="Severity"><option value="all">All severities</option><option value="3">3 · Blocking</option><option value="2">2 · Warning</option><option value="1">1 · Information</option></select><select id="engine" aria-label="Rule engine"><option value="all">All engines</option><option value="te2">Default TE2</option><option value="python">Python checks</option><option value="optional">Optional VertiPaq</option></select><button class="btn" id="reset">Reset</button></div><p class="result" id="count" role="status" aria-live="polite"></p><p class="empty" id="empty" hidden>No matching rules. Try another search or reset the filters.</p><div class="table-wrap rule-catalog"><table><caption class="sr-only">BPA rule catalog. Open Details for detection logic and customization.</caption><thead><tr><th>Rule / Intent</th><th aria-sort="descending">Severity · High to low</th><th>Category</th><th>Engine</th><th>Definition</th><th>Explore</th></tr></thead><tbody>'''
    dialogs = []
    for rule in sorted(rows, key=lambda rule: (-rule["Severity"], rule["Category"].casefold(), engine_labels[rule["engine"]].casefold(), NOTES[rule["ID"]][0].casefold())):
        title, detection, caveat = NOTES[rule["ID"]]
        severity = rule["Severity"]
        tone = {3: "bad", 2: "warn", 1: ""}[severity]
        engine = engine_labels[rule["engine"]]
        note = "Requires measured annotations; not enabled by default." if rule["engine"] == "optional" else "Effective severity/ignore policy can be changed through cicd-config.json."
        detail_id = "detail-" + rule["ID"]
        body += f'''<tr class="rule" id="{rule['ID']}" data-severity="{severity}" data-engine="{rule['engine']}"><td><strong>{esc(title)}</strong><code class="rule-id technical-id">{rule['ID']}</code></td><td><span class="pill {tone}">{severity} · { {3:'Blocking',2:'Warning',1:'Info'}[severity]}</span></td><td>{esc(rule['Category'])}</td><td><span class="pill">{engine}</span></td><td class="definition-cell">{esc(rule['Description'])}</td><td><button class="btn rule-toggle" aria-haspopup="dialog" aria-controls="{detail_id}" aria-label="Details for {esc(title)}">Details</button></td></tr>'''
        dialogs.append(f'''<dialog class="rule-dialog" id="{detail_id}" aria-labelledby="title-{rule['ID']}"><header class="dialog-header"><div><span class="eyebrow">{engine} · Severity {severity}</span><h2 id="title-{rule['ID']}">{esc(title)}</h2></div><button class="btn dialog-close" aria-label="Close rule details" autofocus>Close</button></header><article class="rule-body"><p class="muted">{esc(rule['Description'])}</p><div class="two"><div><span class="label">What triggers it / what to do</span><p>{esc(detection)}</p></div><div><span class="label">Local behavior and limitations</span><p>{esc(caveat)}</p></div></div><details open><summary>Detection logic, scope and customization</summary><span class="label">Catalog name</span><p>{esc(rule['Name'])}</p><span class="label">Scope</span><code>{esc(rule['Scope'])}</code><span class="label">{'Python detection summary' if rule['engine']=='python' else 'Exact TE2 expression'}</span><pre>{esc(rule['Expression'])}</pre><span class="label">Source of truth</span><code>{esc(rule['source'])}</code><p>{note} {('Edit the owning Python check and tests to change detection.' if rule['engine']=='python' else 'Edit this catalog entry to change detection; validate the expression against TE2.')}</p></details></article></dialog>''')
    body += '</tbody></table></div></section>' + ''.join(dialogs) + '''<section id="policy"><h2>How to interpret a finding</h2><p>The default Gate fails on severity ≥ 3 or any rule evaluation error. Severity 2 and 1 remain visible without blocking. These are this repository's configured defaults, not universal Microsoft requirements. Local severity overrides and ignored IDs can change the effective Gate.</p><p>All catalog rules are repository-curated. No reliable per-rule upstream attribution or unchanged-standard certification is recorded. An expression that returns true reports a finding; a missing prerequisite or parser limitation must be reviewed explicitly.</p><div class="callout"><p><b>Read-only execution:</b> the runner analyzes and exports metadata. It does not invoke rule fixes, refresh source data, save changes to the PBIP, or deploy a semantic model.</p></div></section>
<section id="custom"><h2>How to customize responsibly</h2><div class="two"><article class="panel"><h3>Change policy in configuration</h3><p><code>config/bpa-rules.json</code>: ID, Name, Category, Description, Severity, Scope and the TE2 Expression. IDs must remain stable for overrides and historical comparison.</p><p><code>config/cicd-config.json</code>: <code>bpa.fail_severity</code>, <code>ignored_rule_ids</code>, <code>severity_overrides</code> and <code>rules_file</code>. Overrides affect combined TE2/Python findings; they do not repair source definitions.</p><pre>{"bpa": {"fail_severity": 3,
  "ignored_rule_ids": [],
  "severity_overrides": {"MEASURE_NO_DESCRIPTION": 2}}}</pre><p class="muted">Example only; this is not a complete replacement config. Keep config JSON in CRLF.</p></article><article class="panel"><h3>Validate the behavior, not just the JSON</h3><ol><li>Explain the intended risk and the accepted exception.</li><li>Test a triggering example, a legitimate non-triggering example and an unresolved/edge case.</li><li>Run real TE2 for expression syntax and scope compatibility, plus Python/portal tests.</li><li>Open a PR. Shared rule/config changes analyze all tickets.</li><li>Review the resulting findings and document the policy decision.</li></ol><p class="muted">Python checks are implemented in <code>bpa_analyzer.py</code>, not the TE2 JSON catalog. Changing a UI label or rule description does not change detection.</p></article></div></section>
<section id="coverage"><h2>Coverage and prerequisites</h2><p>The 40 TE2 rules run from the configured shared catalog. Four Python checks add report/model binding, detected usage and tracked-cache checks. The five VertiPaq rules live in a separate optional file and require measured annotations; the default pipeline does not populate or run those measurements.</p><p>Offline Unknown/Automatic types remain unresolved warnings. Regex/string rules are heuristics; dependency-based rules rely on TE2 metadata. None of these checks validates all data values, data freshness, business calculations, external consumers, query performance or access controls.</p></section>
'''
    return body + '<section id="maintenance"><h2>Keep this reference synchronized</h2><p>Run <code>python scripts/build_guides.py</code> after catalog changes. Rule IDs, severity, scope and TE2 expressions are loaded from configuration; human explanations are maintained alongside the guide builder. Missing or extra rule explanations stop the build so a changed catalog cannot silently omit a rule.</p><p>The Python runtime-cache check is narrower than ignoring every .pbi file. Optional VertiPaq annotations must be provided by a separate measurement workflow; missing values are not evidence of healthy measured data.</p></section>'


def build(output: Path | None = None) -> None:
    destination = output or ROOT / "docs"
    destination.mkdir(parents=True, exist_ok=True)
    rows = catalog()
    (destination / "workflow.html").write_text(page("Workflow guide", WORKFLOW, [("#overview", "Workflow diagram"), ("#selection", "Ticket selection"), ("#decisions", "Quality decisions"), ("#evidence", "Docs & evidence"), ("#people", "People & ownership"), ("#roadmap", "Roadmap"), ("#proposal", "Proposal decisions")], "workflow"), encoding="utf-8")
    (destination / "bpa-rulebook.html").write_text(page("BPA rulebook", rulebook(rows), [("#catalog", "All 49 checks"), ("#policy", "Gate policy"), ("#custom", "Customization"), ("#coverage", "Coverage"), ("#maintenance", "Maintenance")], "rules"), encoding="utf-8")
    print(f"Built two standalone guides covering {len(rows)} rules: {destination}")


if __name__ == "__main__":
    build()
