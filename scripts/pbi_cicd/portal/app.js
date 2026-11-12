'use strict';
const PORTAL = JSON.parse(document.getElementById('portal-data').textContent);
const MODEL = PORTAL.model || {};
const REPORT = PORTAL.report || {};
const BPA = PORTAL.bpa || {};
const rawGraph = PORTAL.lineage || {};
const DATA = {nodes:rawGraph.nodes || [],edges:rawGraph.edges || [],summary:rawGraph.summary || {}};
const $ = id => document.getElementById(id);
const uiIcon = name => `<svg class="ui-icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storageKey = name => 'lineage-studio:' + encodeURIComponent(PORTAL.pbipName || 'project') + ':' + name;
const metadataTables = new Map((MODEL.tables || []).map(t => [t.name,t]));
DATA.nodes = DATA.nodes.map(node => {
    const meta = node.kind === 'table' ? metadataTables.get(node.label)
        : node.kind === 'measure' ? metadataTables.get(node.table)?.measures?.find(m => m.name === node.label)
        : node.kind === 'pq' ? (MODEL.expressions || []).find(e => e.name === node.label) : null;
    return meta ? {...meta,...node,description:meta.description || node.description || '',columns:meta.columns || node.columns,partitions:meta.partitions || node.partitions,queryGroup:meta.queryGroup || node.queryGroup} : node;
});
const byId = new Map(DATA.nodes.map(n => [n.id,n]));
const kinds = ['source', 'pq', 'table', 'measure', 'page', 'visual'];
const kindNames = {source:'Data source', pq:'Power Query', table:'Model table', measure:'DAX measure', page:'Report page', visual:'Visual'};
const kindSymbols = {source:uiIcon('source'), pq:uiIcon('query'), table:uiIcon('table'), measure:uiIcon('measure'), page:uiIcon('page'), visual:uiIcon('chart')};
const kindClass = n => n.kind === 'page' ? 'page-kind' : n.kind;
const icon = n => `<span class="kind-icon ${kindClass(n)}">${kindSymbols[n.kind]}</span>`;
const visualPage = new Map(DATA.nodes.filter(n => n.kind === 'visual').map(n => [n.id, 'page:' + n.pageId]));
const collapsedEdges = new Map();
for (const e of DATA.edges) {
    if (['PAGE_CONTAINS', 'REL', 'BIND_MEASURE', 'BIND_COLUMN'].includes(e.type)) continue;
    const target = e.target;
    if (!['source', 'pq', 'table', 'measure'].includes(byId.get(target)?.kind) || !['source', 'pq', 'table', 'measure'].includes(byId.get(e.source)?.kind)) continue;
    if (target === e.source || !byId.has(target)) continue;
    const key = e.source + '|' + target;
    if (!collapsedEdges.has(key)) collapsedEdges.set(key, {...e, target, grouped:visualPage.has(e.target), bindings:1});
    else collapsedEdges.get(key).bindings++;
}
const graphEdges = [...collapsedEdges.values()];
const graphNodes = DATA.nodes.filter(n => ['source', 'pq', 'table', 'measure'].includes(n.kind));
const adjacency = {up:new Map(), down:new Map()};
for (const n of graphNodes) {adjacency.up.set(n.id, []); adjacency.down.set(n.id, []);}
for (const e of graphEdges) {adjacency.down.get(e.source)?.push(e.target); adjacency.up.get(e.target)?.push(e.source);}
function traverse(id, direction, depth = Infinity) {
    const result = new Map(), queue = [[id, 0]], visited = new Set([id]);
    for (let cursor = 0; cursor < queue.length; cursor++) {
        const [current, level] = queue[cursor];
        if (level >= depth) continue;
        for (const next of adjacency[direction].get(current) || []) {
            if (visited.has(next)) continue;
            visited.add(next); result.set(next, level + 1); queue.push([next, level + 1]);
        }
    }
    return result;
}
const initialObject = [...graphNodes].sort((a,b) => Number(b.kind === 'table') - Number(a.kind === 'table') || (b.columnCount || 0) - (a.columnCount || 0) || a.label.localeCompare(b.label))[0];
const defaults = {type:true, checks:true, schema:true, dependencies:false, description:false, tags:true};
let facets = {...defaults}, facetDraft = {...defaults};
try {facets = {...defaults, ...JSON.parse(localStorage.getItem(storageKey('facets')) || '{}')};} catch {}
const state = {page:'home', root:initialObject?.id || null, selected:initialObject?.id || null, up:1, down:1, all:false, explorerMode:'context', explorerKind:'all', kind:'all', catalogQuery:'', catalogSort:'kind', catalogTab:'all', catalogFolder:'all', visualMode:'all', detailTab:'overview', detailId:initialObject?.id || null, checksSeverity:'all', checksQuery:'', checksCategory:'all', checksKind:'all', checksRule:'all', checksSort:'severity', codeId:null, partition:0};
const friendlyRules = {
    PQ_HARDCODED_LOCAL_PATHS:['Replace local file paths with reusable parameters','The query points to a file on one computer. Review whether a parameter or shared source would make it portable.'],
    VISIBLE_COLUMN_NO_DESCRIPTION:['Add descriptions to visible columns','Describe what each column means so report authors can choose the right field.'],
    PBIR_UNUSED_TABLE:['Review tables with no detected usage','No report binding or model DAX reference was detected. Check the table before deciding whether to hide or remove it.'],
    DATE_CALENDAR_TABLES_MARKED_AS_DATE_TABLE:['Mark the calendar as a date table','Review the date table setting and select its date column when it is intended for calendar calculations.'],
    HIDE_FOREIGN_KEYS:['Hide relationship keys from report authors','Foreign keys are usually used to connect tables. Consider hiding them when they are not useful report fields.'],
    NUMERIC_COLUMN_SUMMARIZE_BY:['Review automatic totals for numeric columns','Set the default summary behavior explicitly, especially for numbers such as IDs that should not be added together.'],
    FILTER_COLUMN_VALUES:['Filter specific columns inside CALCULATE','Review FILTER(Table, ...) and, where the result is equivalent, filter only the columns required by the calculation.'],
    REDUCE_USAGE_OF_CALCULATED_COLUMNS_THAT_USE_THE_RELATED_FUNCTION:['Review calculated columns that use RELATED','Check whether a relationship, measure, or source transformation can meet the same need with less stored data.'],
    AVOID_FLOATING_POINT_DATA_TYPES:['Review floating-point number columns','Check whether the number type provides the precision the column needs before choosing an alternative.'],
    DAX_MEASURES_UNQUALIFIED:['Reference measures without a table name',"Use [Measure] rather than 'Table'[Measure] to distinguish measures from columns."],
    MEASURE_NO_DISPLAY_FOLDER:['Group measures into display folders','Organize related measures so report authors can find them more easily.'],
    PBIR_UNUSED_MEASURE:['Review measures with no detected usage','No report binding or downstream measure reference was detected. Confirm whether the measure is still needed.'],
    PROVIDE_FORMAT_STRING_FOR_NUMERIC_MEASURES:['Set a display format for numeric measures','Choose a suitable number, percentage, or currency format instead of relying on a default.'],
    USE_THE_DIVIDE_FUNCTION_FOR_DIVISION:['Handle division by zero with DIVIDE','Review division expressions and use DIVIDE where its handling of zero or blank denominators matches the intended result.'],
    MEASURE_NO_DESCRIPTION:['Add descriptions to visible measures','Explain what the measure calculates and how report authors should interpret it.'],
    PBIR_BROKEN_FIELD_REF:['Repair report fields that no longer exist','A visual or filter points to a model field that was not found. Review the binding and replace the missing field.']
};
const ruleTitle = rule => friendlyRules[rule.ruleId]?.[0] || (rule.ruleName||rule.ruleId||'Rule').replace(/^\[[^\]]+\]\s*/, '');
const ruleExplanation = rule => friendlyRules[rule.ruleId]?.[1] || 'Review the original rule and the affected object below.';
function ruleMarkup(rule) {
    return `<div class="rule-title">${esc(ruleTitle(rule))}</div><div class="rule-explanation">${esc(ruleExplanation(rule))}</div><details class="technical-rule"><summary>Original rule & ID</summary><div>${esc(rule.ruleName)}</div><code>${esc(rule.ruleId)}</code></details>`;
}
let visible = [], visibleEdges = [], layoutNodes = new Map(), ranks = [], routes = [], scale = 1, tx = 30, ty = 100;
let layoutQuality = {before:0, after:0};
let space = false, gesture = null, moved = false, currentCode = '', lastModalFocus = null;
const NODE_W = 266, COL_GAP = 132, ROW_GAP = 58;
const status = n => !n.bpa?.length ? ['neutral','No attached findings'] : n.maxSeverity >= 3 ? ['bad','High severity'] : n.maxSeverity >= 2 ? ['warn','Needs review'] : ['link','Metadata findings'];
const statusPill = n => {const [cls, text] = status(n); return `<span class="pill ${cls}"><span class="status-dot"></span>${text}</span>`;};
function definitions(n) {
    if (n.kind === 'measure') return [{name:'DAX expression', language:'DAX', code:n.expression || ''}];
    if (n.kind === 'pq') return [{name:'M expression', language:'M', code:n.expression || ''}];
    if (n.partitions?.length) return n.partitions.map(p => ({name:p.name || 'Partition', language:p.sourceType === 'M' ? 'M' : p.sourceType === 'Calculated' ? 'DAX' : p.sourceType || 'Definition', code:p.expression || ''}));
    const calculated = n.columns?.filter(c => c.expression);
    if (calculated?.length) return calculated.map(c => ({name:c.name, language:'DAX', code:c.expression}));
    return [];
}
function codeTag(n) {
    const defs = definitions(n);
    if (!defs.length) return `<span class="pill ${kindClass(n)}">${esc(n.kind === 'source' ? n.connector || 'Source' : kindNames[n.kind])}</span>`;
    return `<button class="code-action" data-code="${esc(n.id)}" title="View ${esc(defs[0].language)} code">${uiIcon('code')}<span>${esc(defs[0].language)}</span></button>`;
}
const directCount = (id, dir) => adjacency[dir].get(id)?.length || 0;
function schemaText(n) {
    if (n.kind === 'table') return `${n.columnCount || 0} cols · ${n.measureCount || 0} measures`;
    if (n.kind === 'page') return `${n.visualCount || 0} visuals`;
    if (n.kind === 'measure') return n.formatString || 'General';
    if (n.kind === 'pq') return `${n.transformations?.length || 0} transformation functions`;
    return n.connector || n.visualType || n.subtitle || '—';
}
function cardHTML(n, config = facets, preview = false) {
    const p = layoutNodes.get(n.id) || {x:0, y:0};
    const rows = [];
    if (config.type) rows.push(`<div class="node-row"><span class="label">Object type</span><span class="value">${kindNames[n.kind]}</span></div>`);
    if (config.checks) rows.push(`<div class="node-row"><span class="label">BPA findings</span><span class="value">${n.bpa?.length || 0} attached ${n.bpa?.length ? '· ' + (status(n)[1]) : ''}</span></div>`);
    if (config.schema) rows.push(`<div class="node-row"><span class="label">${n.kind === 'measure' ? 'Format' : n.kind === 'table' ? 'Schema' : 'Definition'}</span><span class="value" title="${esc(schemaText(n))}">${esc(schemaText(n))}</span></div>`);
    if (config.dependencies) rows.push(`<div class="node-row"><span class="label">Dependencies</span><span class="value">↑ ${directCount(n.id, 'up')} &nbsp; ↓ ${directCount(n.id, 'down')}</span></div>`);
    if (config.description) rows.push(`<div class="node-row description-row">${esc(n.description || 'No description in this snapshot.')}</div>`);
    if (config.tags) rows.push(`<div class="node-tags">${codeTag(n)}${n.kind === 'table' ? `<span class="pill">${esc(n.tableType?.includes('Calculated') ? 'Calculated' : n.partitions?.[0]?.mode || 'Import')}</span>` : ''}${config.checks ? statusPill(n) : ''}</div>`);
    const omittedUp = (adjacency.up.get(n.id) || []).filter(id => !visible.some(v => v.id === id)).length;
    const omittedDown = (adjacency.down.get(n.id) || []).filter(id => !visible.some(v => v.id === id)).length;
    const relation = relationInfo(n.id);
    return `<div class="asset-node ${preview ? '' : relation.kind}" data-context="${preview ? '' : esc(relation.label)}" data-node="${esc(n.id)}" style="left:${p.x}px;top:${p.y}px" tabindex="0" aria-label="${esc(n.label)}"><span class="port input"></span><div class="node-header">${icon(n)}<span class="node-title" title="${esc(n.label)}">${esc(n.label)}</span><button class="node-open" data-detail="${esc(n.id)}" title="Object details" aria-label="Open ${esc(n.label)} details">${uiIcon('info')}</button></div>${rows.join('')}<span class="port output"></span>${!preview && !state.all && omittedUp ? `<button class="more-links up" data-expand="up" data-expand-root="${esc(n.id)}">↑ ${omittedUp} outside view</button>` : ''}${!preview && !state.all && omittedDown ? `<button class="more-links down" data-expand="down" data-expand-root="${esc(n.id)}">${omittedDown} outside view ↓</button>` : ''}</div>`;
}
function relationInfo(id) {
    if (id === state.selected) return {kind:'selected',label:'Selected object'};
    const up = traverse(state.selected,'up'), down = traverse(state.selected,'down');
    if (up.has(id)) return {kind:'upstream',label:`Upstream · ${up.get(id)} ${up.get(id) === 1 ? 'step' : 'steps'}`};
    if (down.has(id)) return {kind:'downstream',label:`Downstream · ${down.get(id)} ${down.get(id) === 1 ? 'step' : 'steps'}`};
    return {kind:'unrelated',label:''};
}
function estimatedHeight(config = facets) {
    return 41 + (['type','checks','schema','dependencies'].filter(k => config[k]).length * 27) + (config.description ? 39 : 0) + (config.tags ? 40 : 0);
}
function computeScope() {
    if (state.all) visible = [...graphNodes];
    else {
        const ids = new Set([state.root, ...traverse(state.root, 'up', state.up).keys(), ...traverse(state.root, 'down', state.down).keys()]);
        visible = graphNodes.filter(n => ids.has(n.id));
    }
    const ids = new Set(visible.map(n => n.id));
    visibleEdges = graphEdges.filter(e => ids.has(e.source) && ids.has(e.target));
}

// Rank by dependencies, insert routing vertices, and reorder layers to reduce crossings.
function arrange() {
    layoutNodes.clear(); ranks = []; routes = [];
    const nodeHeight = estimatedHeight(), indegree = new Map(visible.map(n => [n.id, 0]));
    const rankOf = new Map(visible.map(n => [n.id, 0]));
    const outgoing = new Map(visible.map(n => [n.id, []]));
    for (const e of visibleEdges) {indegree.set(e.target, indegree.get(e.target) + 1); outgoing.get(e.source).push(e.target);}
    const queue = visible.filter(n => !indegree.get(n.id)).map(n => n.id), done = new Set();
    for (let cursor = 0; cursor < queue.length; cursor++) {
        const id = queue[cursor]; done.add(id);
        for (const target of outgoing.get(id)) {rankOf.set(target, Math.max(rankOf.get(target), rankOf.get(id) + 1)); indegree.set(target, indegree.get(target) - 1); if (!indegree.get(target)) queue.push(target);}
    }
    for (const n of visible) {
        const rank = rankOf.get(n.id), vertex = {id:n.id, rank, dummy:false, h:nodeHeight, up:[], down:[]};
        layoutNodes.set(n.id, vertex); (ranks[rank] ||= []).push(vertex);
    }
    visibleEdges.forEach((e, index) => {
        const a = layoutNodes.get(e.source), b = layoutNodes.get(e.target), path = [a];
        for (let rank = a.rank + 1; rank < b.rank; rank++) {
            const v = {id:`routing-${index}-${rank}`, rank, dummy:true, h:12, up:[], down:[]};
            layoutNodes.set(v.id, v); (ranks[rank] ||= []).push(v); path.push(v);
        }
        path.push(b);
        for (let j = 0; j < path.length - 1; j++) {path[j].down.push(path[j + 1]); path[j + 1].up.push(path[j]);}
        routes.push({edge:e, path});
    });
    const updateOrder = () => ranks.forEach(layer => layer.forEach((v, i) => v.order = i));
    const crossingCount = () => {
        let count = 0;
        for (let rank = 0; rank < ranks.length - 1; rank++) {
            const segments = ranks[rank].flatMap(v => v.down.map(n => [v.order, n.order]));
            for (let i = 0; i < segments.length; i++) for (let j = i + 1; j < segments.length; j++) {
                if ((segments[i][0] - segments[j][0]) * (segments[i][1] - segments[j][1]) < 0) count++;
            }
        }
        return count;
    };
    updateOrder();
    let bestCount = crossingCount(), bestOrder = ranks.map(layer => [...layer]);
    layoutQuality.before = bestCount;
    for (let pass = 0; pass < 12; pass++) {
        const forward = pass % 2 === 0, ordered = forward ? ranks.slice(1) : ranks.slice(0, -1).reverse();
        for (const layer of ordered) {
            for (const v of layer) {const adjacent = v[forward ? 'up' : 'down']; v.bary = adjacent.length ? adjacent.reduce((sum, n) => sum + n.order, 0) / adjacent.length : v.order;}
            layer.sort((a, b) => a.bary - b.bary || a.order - b.order); updateOrder();
        }
        const count = crossingCount();
        if (count < bestCount) {bestCount = count; bestOrder = ranks.map(layer => [...layer]);}
    }
    ranks = bestOrder; updateOrder(); layoutQuality.after = bestCount;
    const maxHeight = Math.max(0, ...ranks.map(layer => layer.reduce((sum, v) => sum + v.h + ROW_GAP, -ROW_GAP)));
    ranks.forEach((layer, rank) => {
        const height = layer.reduce((sum, v) => sum + v.h + ROW_GAP, -ROW_GAP);
        let y = (maxHeight - height) / 2 + 55;
        for (const v of layer) {v.x = rank * (NODE_W + COL_GAP); v.y = y; y += v.h + ROW_GAP;}
    });
    for (let pass = 0; pass < 8; pass++) {
        for (const layer of (pass % 2 ? [...ranks].reverse() : ranks)) {
            const dir = pass % 2 ? 'down' : 'up'; let previousBottom = 30;
            for (const v of layer) {
                const adjacent = v[dir], ideal = adjacent.length ? adjacent.reduce((s, n) => s + n.y + n.h / 2, 0) / adjacent.length - v.h / 2 : v.y;
                v.y = Math.max(previousBottom + ROW_GAP, (v.y + ideal) / 2); previousBottom = v.y + v.h;
            }
        }
    }
    const minY = Math.min(0, ...[...layoutNodes.values()].map(v => v.y));
    for (const v of layoutNodes.values()) v.y -= minY;
}
function graphBounds() {
    const vertices = [...layoutNodes.values()];
    return {minX:Math.min(0, ...vertices.map(v => v.x - 25)), minY:Math.min(0, ...vertices.map(v => v.y - 40)), maxX:Math.max(300, ...vertices.map(v => v.x + NODE_W + 25)), maxY:Math.max(220, ...vertices.map(v => v.y + v.h + 35))};
}
function renderGraph(reflow = true) {
    computeScope(); if (reflow) arrange();
    $('nodes').innerHTML = visible.map(n => cardHTML(n)).join('');
    const root = byId.get(state.root);
    $('canvas-context').innerHTML = `<b>${state.all ? 'Model lineage' : esc(root?.label || 'Model lineage')}</b> &nbsp; / &nbsp; ${visible.length} objects · ${visibleEdges.length} connections · Model dependencies`;
    $('whole-graph').classList.toggle('active', state.all);
    $('up-depth').disabled = state.all; $('down-depth').disabled = state.all;
    drawEdges(); renderAssetList(); renderDrawer(); bindActions($('nodes'));
    document.querySelectorAll('#nodes .asset-node').forEach(el => {
        el.addEventListener('pointerdown', e => startNodeDrag(e, el));
        el.addEventListener('click', e => {if (moved || e.target.closest('button')) return; selectNode(el.dataset.node);});
        el.addEventListener('dblclick', e => {if (!e.target.closest('button')) openDetail(el.dataset.node);});
        el.addEventListener('keydown', e => {if (e.key === 'Enter') selectNode(el.dataset.node);});
    });
    document.querySelectorAll('[data-expand]').forEach(el => el.onclick = () => {
        const dir = el.dataset.expand;
        state.root = el.dataset.expandRoot; state.selected = state.root; state.all = false;
        state[dir] = 1; state[dir === 'up' ? 'down' : 'up'] = 1;
        syncDepths(); renderGraph(); fit();
    });
}
function drawEdges() {
    const related = new Set([state.selected, ...traverse(state.selected, 'up').keys(), ...traverse(state.selected, 'down').keys()]);
    $('edges').innerHTML = '<defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L8 4L0 8" fill="#a1a9bc"/></marker></defs>' + routes.map(({edge, path}) => {
        let d = '';
        for (let i = 0; i < path.length - 1; i++) {
            const a = path[i], b = path[i + 1];
            const x = a.x + (a.dummy ? NODE_W / 2 : NODE_W), y = a.y + (a.dummy ? a.h / 2 : 19);
            const x2 = b.x + (b.dummy ? NODE_W / 2 : 0), y2 = b.y + (b.dummy ? b.h / 2 : 19);
            const bend = (x2 - x) / 2;
            d += `${i ? 'L' : 'M'}${x},${y} C${x + bend},${y} ${x2 - bend},${y2} ${x2},${y2} `;
        }
        return `<path class="edge ${related.has(edge.source) && related.has(edge.target) ? 'related' : ''}" d="${d}" marker-end="url(#arrow)"><title>${esc(byId.get(edge.source).label)} → ${esc(byId.get(edge.target).label)}${edge.grouped ? ` (${edge.bindings} grouped bindings)` : ''}</title></path>`;
    }).join('');
    renderMinimap();
}
function transform() {
    $('world').style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
    $('viewport').style.backgroundSize = `${20 * scale}px ${20 * scale}px`;
    $('viewport').style.backgroundPosition = `${tx}px ${ty}px`;
    $('zoom-label').textContent = Math.round(scale * 100) + '%'; renderMinimap();
}
function fit() {
    if (state.page !== 'lineage') return;
    const b = graphBounds(), v = $('viewport'), w = b.maxX - b.minX, h = b.maxY - b.minY;
    if (!v.clientWidth || !v.clientHeight) return;
    scale = Math.max(.035, Math.min(1, (v.clientWidth - 80) / w, (v.clientHeight - 160) / h));
    tx = (v.clientWidth - w * scale) / 2 - b.minX * scale;
    ty = 60 + (v.clientHeight - 130 - h * scale) / 2 - b.minY * scale; transform();
}
function zoomAt(factor, x, y) {const next = Math.max(.035, Math.min(2.5, scale * factor)); tx = x - (x - tx) * next / scale; ty = y - (y - ty) * next / scale; scale = next; transform();}
function mapGeometry() {const b = graphBounds(), s = Math.min(118 / (b.maxX - b.minX), 68 / (b.maxY - b.minY)); return {...b, s};}
function renderMinimap() {
    if (!layoutNodes.size) return;
    const b = mapGeometry();
    $('minimap-svg').setAttribute('viewBox', '0 0 138 91');
    $('minimap-svg').innerHTML = visible.map(n => {const p = layoutNodes.get(n.id); return `<rect x="${10 + (p.x - b.minX) * b.s}" y="${10 + (p.y - b.minY) * b.s}" width="${NODE_W * b.s}" height="${p.h * b.s}" rx="1" fill="${n.id === state.selected ? '#8c7abf' : '#d5dae5'}"/>`;}).join('') + `<rect x="${10 + (-tx / scale - b.minX) * b.s}" y="${10 + (-ty / scale - b.minY) * b.s}" width="${$('viewport').clientWidth / scale * b.s}" height="${$('viewport').clientHeight / scale * b.s}" fill="#8c7abf0a" stroke="#8c7abf" stroke-width=".7"/>`;
}
function renderAssetList() {
    const q = $('lineage-search').value.trim().toLowerCase();
    const mode = q ? 'browse' : state.explorerMode;
    const kindMatches = n => state.explorerKind === 'all' || (state.explorerKind === 'queries' ? ['source','pq'].includes(n.kind) : n.kind === state.explorerKind);
    const matches = n => kindMatches(n) && `${n.label} ${n.table || ''}`.toLowerCase().includes(q);
    const source = (mode === 'context' ? visible.filter(n => relationInfo(n.id).kind !== 'unrelated') : graphNodes).filter(matches);
    const selected = byId.get(state.selected) || {label:'No object selected'};
    const row = n => {const rel = relationInfo(n.id);return `<button class="asset-item ${rel.kind}" data-jump="${esc(n.id)}" title="${esc(n.label)}" aria-current="${n.id === state.selected ? 'true' : 'false'}">${icon(n)}<span class="object-lines"><span class="object-label">${esc(n.label)}</span><span class="object-relation">${rel.label || kindNames[n.kind]}</span></span></button>`;};
    let html = `<div class="navigator-header"><div><span class="eyebrow">Navigate</span><h3>Model objects</h3></div><span class="pill">${source.length}</span></div><div class="navigator-tabs"><button data-explorer-mode="context" class="${mode === 'context' ? 'active' : ''}">In context</button><button data-explorer-mode="browse" class="${mode === 'browse' ? 'active' : ''}">Browse all</button></div><div class="navigator-filter"><select id="explorer-kind" class="filter" aria-label="Navigator object type"><option value="all">All types</option><option value="table">Tables</option><option value="measure">Measures</option><option value="queries">Sources & queries</option></select></div>`;
    if (mode === 'context') {
        for (const [kind,label] of [['selected','Selected'],['upstream','Feeds into selection'],['downstream','Depends on selection']]) {
            const list = source.filter(n => relationInfo(n.id).kind === kind).sort((a,b) => a.label.localeCompare(b.label));
            if (list.length) html += `<div class="context-group ${kind}"><div class="asset-group">${label}<span>${list.length}</span></div>${list.map(row).join('')}</div>`;
        }
        html += `<div class="navigator-hint">Click an object to select and jump to it. Use <b>Focus selection</b> to rebuild the graph around it.</div>`;
    } else {
        for (const kind of ['source','pq','table','measure']) {
            const list = source.filter(n => n.kind === kind).sort((a,b) => a.label.localeCompare(b.label));
            if (list.length) html += `<details class="navigator-group" open><summary>${kindNames[kind]}<span>${list.length}</span></summary>${list.map(row).join('')}</details>`;
        }
    }
    if (!source.length) html += '<div class="empty">No matching objects. Try another type or search.</div>';
    html += `<div class="navigator-footer"><span class="tiny muted" title="${esc(selected.label)}">${esc(selected.label)}</span><button class="btn" id="focus-selection">${uiIcon('lineage')}Focus selection</button></div>`;
    $('asset-list').innerHTML = html;$('explorer-kind').value = state.explorerKind;
    $('explorer-kind').onchange = e => {state.explorerKind = e.target.value;renderAssetList();};
    document.querySelectorAll('[data-explorer-mode]').forEach(b => b.onclick = () => {state.explorerMode = b.dataset.explorerMode;$('lineage-search').value = '';renderAssetList();});
    $('asset-list').querySelectorAll('[data-jump]').forEach(b => b.onclick = () => jumpToNode(b.dataset.jump));
    $('focus-selection').disabled = !state.selected;
    $('focus-selection').onclick = () => focusRoot(state.selected);
    enhanceSelects();
}
function jumpToNode(id) {
    if (!layoutNodes.has(id)) {focusRoot(id);return;}
    selectNode(id);const p = layoutNodes.get(id);
    tx = $('viewport').clientWidth / 2 - (p.x + NODE_W / 2) * scale;
    ty = $('viewport').clientHeight / 2 - (p.y + p.h / 2) * scale;transform();
}
function focusRoot(id) {
    if (!byId.has(id)) return;
    if (!graphNodes.some(n => n.id === id)) {openDetail(id); state.detailTab = 'usage'; renderDetail(); return;}
    state.root = id; state.selected = state.root; state.all = false;
    if (state.page !== 'lineage') navigate('lineage', false);
    renderGraph(); fit();
}
function selectNode(id) {
    state.selected = id;
    document.querySelectorAll('#nodes .asset-node').forEach(el => {
        const rel = relationInfo(el.dataset.node);
        for (const cls of ['selected','upstream','downstream','unrelated']) el.classList.toggle(cls,cls === rel.kind);
        el.dataset.context = rel.label;
    });
    renderDrawer(); renderAssetList(); drawEdges();
}
function metadataRows(n) {
    const values = [['Object type', kindNames[n.kind]], ['Storage mode', n.partitions?.[0]?.mode || '—'], ['Parent table', n.table || '—'], ['Display folder', n.displayFolder || '—'], ['Format string', n.formatString || '—'], ['Visibility', n.isHidden === undefined ? '—' : n.isHidden ? 'Hidden' : 'Visible']];
    if (n.location) values.push(['Location', n.location]);
    if (n.connector) values.push(['Connector',n.connector]);
    if (n.queryGroup) values.push(['Query group',n.queryGroup]);
    if (n.transformations?.length) values.push(['Transformations',n.transformations.join(', ')]);
    if (n.kind==='visual') values.push(['Visual type',n.visualType||'Unknown'],['Report page',n.pageName||'—'],['Data bindings',n.isDataBound?'Data-bound':'Decorative']);
    return values.map(([key, value]) => `<tr><th>${key}</th><td style="overflow-wrap:anywhere">${esc(value)}</td></tr>`).join('');
}
function renderDrawer() {
    const n = byId.get(state.selected);
    if (!n) {$('drawer').innerHTML='<div class="empty">Select an object to inspect it.</div>';return;}
    $('drawer').innerHTML = `<div class="drawer-head">Selected object<span class="grow"></span><button class="btn icon" id="close-drawer"><svg class="ui-icon" aria-hidden="true"><use href="#i-close"></use></svg></button></div><div class="drawer-body">${icon(n)}<h2>${esc(n.label)}</h2><div class="hero-tags">${statusPill(n)}${codeTag(n)}</div><p class="description" style="margin-top:15px">${esc(n.description || 'No description in the project snapshot.')}</p><table class="meta-table">${metadataRows(n)}</table><div style="display:flex;gap:7px;margin:16px 0"><button class="pill link" data-root="${esc(n.id)}">↑ ${directCount(n.id, 'up')} direct upstream</button><button class="pill link" data-root="${esc(n.id)}">↓ ${directCount(n.id, 'down')} direct downstream</button></div><button class="btn primary" style="width:100%" data-detail="${esc(n.id)}">Object details </button></div><button class="review-pin" data-region="7" style="right:10px;top:55px">7</button>`;
    $('close-drawer').onclick = () => {$('drawer').classList.add('hidden'); fit();}; bindActions($('drawer')); bindPins();
}
function navigate(page, update = true) {
    state.page = page;
    document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === 'page-' + page));
    document.querySelectorAll('[data-nav]').forEach(el => el.classList.toggle('active', el.dataset.nav === (page === 'detail' ? 'catalog' : page)));
    $('breadcrumb').innerHTML = `<span class="muted">Workspace</span><span class="muted">/</span><strong>${esc(({home:'Home',catalog:'Catalog',lineage:'Model lineage',model:'Data model',checks:'BPA findings',detail:byId.get(state.detailId)?.label})[page])}</strong>`;
    if (!update) return;
    if (page === 'home') renderHome();
    if (page === 'catalog') renderCatalog();
    if (page === 'checks') renderChecks();
    if (page === 'detail') renderDetail();
    if (page === 'lineage') {renderGraph(); requestAnimationFrame(fit);}
    if (page === 'model') {renderModel(); requestAnimationFrame(fitModel);}
}
function renderHome() {
    const attached = graphNodes.filter(n => n.bpa?.length), high = attached.filter(n => n.maxSeverity >= 3);
    $('page-home').innerHTML = `<div class="page-content"><div class="page-heading"><div><div class="eyebrow">${esc(PORTAL.pbipName)}</div><h1>Your project, in perspective.</h1><p>Discover objects, inspect definitions, and understand the impact of a change.</p></div><span class="grow"></span><button class="btn primary" data-go="lineage">Explore lineage</button></div>${gateSummary()}<div class="grid"><button class="metric" data-go="catalog"><div class="metric-icon">${uiIcon('catalog')}</div><span>Project objects</span><b>${DATA.nodes.length}</b><span>${graphNodes.length} model objects</span></button><button class="metric" data-kind="measure"><div class="metric-icon">${uiIcon('measure')}</div><span>DAX measures</span><b>${DATA.nodes.filter(n => n.kind === 'measure').length}</b><span>Explore calculations and dependencies</span></button><button class="metric" data-go="checks"><div class="metric-icon">${uiIcon('checks')}</div><span>Objects with BPA findings</span><b>${attached.length}</b><span>${high.length} with high-severity findings</span></button><button class="metric" data-kind="page"><div class="metric-icon">${uiIcon('page')}</div><span>Report pages</span><b>${DATA.nodes.filter(n => n.kind === 'page').length}</b><span>${DATA.summary.dataBoundVisuals ?? DATA.nodes.filter(n=>n.kind==='visual'&&n.isDataBound).length} data-bound visuals</span></button></div><div class="home-cols"><div><div class="section-head"><h2>Start exploring</h2><span class="tiny muted">A few paths into your project</span></div><div class="panel">${graphNodes.filter(n => ['table','measure'].includes(n.kind)).sort((a,b) => directCount(b.id,'down')-directCount(a.id,'down')).slice(0,3).map(n => {const id=n.id;return `<button class="shortcut" data-detail="${esc(id)}">${icon(n)}<div><h3>${esc(n.label)}</h3><p>${kindNames[n.kind]} · ${directCount(id, 'down')} direct downstream objects</p></div><span class="grow"></span><span class="muted"></span></button>`;}).join('')}</div></div><div><div class="section-head"><h2>Project composition</h2></div><div class="panel"><table>${kinds.map(k => `<tr><td>${kindNames[k]}</td><td class="num mono">${DATA.nodes.filter(n => n.kind === k).length}</td><td style="width:80px"><button class="pill link" data-kind="${k}">Browse</button></td></tr>`).join('')}</table></div></div></div><div class="section-head"><h2>About this view</h2></div><div class="callout">This is a project metadata snapshot. BPA findings are static rule results; refresh history, runtime health, freshness, and ownership are not available. Counts refer to attached object findings and may overlap when a rule is attached to more than one object.</div><button class="review-pin" data-region="8" style="right:30px;top:185px">8</button></div>`; bindActions($('page-home')); bindPins();
}
function catalogMatches(n) {
    const query=state.catalogQuery.trim().toLowerCase();
    const folder=n.displayFolder||'(Unassigned)';
    const matchesFolder=state.catalogFolder==='all'||(n.kind==='measure'&&folder===state.catalogFolder);
    const matchesVisual=state.visualMode==='all'||n.kind!=='visual'||(state.visualMode==='bound'?!!n.isDataBound:!n.isDataBound);
    return matchesFolder&&matchesVisual&& (state.kind === 'all' || n.kind === state.kind) && `${n.label} ${n.description||''} ${n.expression||''}`.toLowerCase().includes(query) && (state.catalogTab !== 'findings' || n.bpa?.length) && (state.catalogTab !== 'code' || definitions(n).length);
}
function catalogRows(nodes) {
    const maxDown = Math.max(1, ...graphNodes.map(n => directCount(n.id, 'down')));
    return nodes.map(n => {
        const modelObject = graphNodes.some(m => m.id === n.id);
        const downstream = modelObject ? `<span class="bar-track"><span style="width:${directCount(n.id,'down') / maxDown * 100}%"></span></span><span class="mono">${directCount(n.id,'down')}</span>` : '<span class="muted">—</span>';
        return `<tr><td><div class="object-name">${icon(n)}<div><button data-detail="${esc(n.id)}">${esc(n.label)}</button><small>${esc(n.table || n.pageName || kindNames[n.kind])}</small></div></div></td><td><button class="pill" data-kind="${n.kind}" title="Filter catalog by ${kindNames[n.kind]}">${kindSymbols[n.kind]} ${kindNames[n.kind]}</button></td><td>${statusPill(n)}<div class="tiny muted" style="margin-top:5px">${n.bpa?.length || 0} attached findings</div></td><td>${codeTag(n)}</td><td><span class="small muted">${esc(schemaText(n))}</span></td><td class="num">${downstream}</td><td><div class="row-actions">${modelObject ? `<button class="btn" data-root="${esc(n.id)}" title="Focus this object in the model graph">${uiIcon('lineage')}Lineage</button>` : ''}<button class="btn" data-detail="${esc(n.id)}" title="Open metadata, schema, usage, and code">Details </button></div></td></tr>`;
    }).join('') || '<tr><td colspan="7" class="empty">No objects match these filters.</td></tr>';
}
function sortedCatalog() {
    return DATA.nodes.filter(catalogMatches).sort((a,b) => {
        const visualOrder = Number(a.kind === 'visual') - Number(b.kind === 'visual');
        if (visualOrder) return visualOrder;
        const order = state.catalogSort === 'kind' ? kinds.indexOf(a.kind) - kinds.indexOf(b.kind)
            : state.catalogSort === 'findings' ? (b.bpa?.length || 0) - (a.bpa?.length || 0)
            : state.catalogSort === 'downstream' ? directCount(b.id, 'down') - directCount(a.id, 'down') : 0;
        return order || a.label.localeCompare(b.label);
    });
}
function renderCatalog() {
    $('page-catalog').innerHTML = `<div class="catalog-panel"><h1>Object catalog</h1><p>Search your project. Inspect an object, its code, or its place in the graph.</p></div><div class="tabbar"><button data-catalog-tab="all">All objects</button><button data-catalog-tab="findings">With BPA findings</button><button data-catalog-tab="code">With code</button></div><div class="table-tools"><div class="search"><svg class="ui-icon" aria-hidden="true"><use href="#i-search"></use></svg><input id="catalog-search" placeholder="Search names, descriptions, M or DAX…" value="${esc(state.catalogQuery)}" aria-label="Search catalog"></div><select class="filter" id="catalog-kind" aria-label="Object type"><option value="all">All object types</option>${kinds.map(k => `<option value="${k}" ${state.kind === k ? 'selected' : ''}>${kindNames[k]}</option>`).join('')}</select><select class="filter" id="catalog-folder" aria-label="Measure display folder"><option value="all">All display folders</option>${[...new Set(DATA.nodes.filter(n=>n.kind==='measure').map(n=>n.displayFolder||'(Unassigned)'))].sort().map(folder=>`<option value="${esc(folder)}" ${state.catalogFolder===folder?'selected':''}>${esc(folder)}</option>`).join('')}</select><select class="filter" id="catalog-visual-mode" aria-label="Visual data bindings"><option value="all">All visuals</option><option value="bound">Data-bound visuals</option><option value="decorative">Decorative visuals</option></select><button class="btn" id="clear-catalog">Clear filters</button><span class="grow"></span><span class="tiny muted">Sort by</span><select class="filter" id="catalog-sort"><option value="kind">Kind, then name</option><option value="name">Name A–Z</option><option value="findings">Most BPA findings</option><option value="downstream">Most downstream</option></select></div><div class="table-wrap"><table><thead><tr><th>Object</th><th>Kind</th><th>BPA assessment</th><th>Definition</th><th>Schema / format</th><th class="num">Direct downstream</th><th>Explore</th></tr></thead><tbody id="catalog-rows"></tbody></table></div><div class="table-foot" id="catalog-count"></div><button class="review-pin" data-region="6" style="right:24px;top:268px">6</button>`;
    $('catalog-sort').value = state.catalogSort;
    $('catalog-visual-mode').value=state.visualMode;
    $('catalog-folder').onchange=e=>{state.catalogFolder=e.target.value;if(state.catalogFolder!=='all'){state.kind='measure';$('catalog-kind').value='measure';}updateCatalogRows();};
    $('catalog-visual-mode').onchange=e=>{state.visualMode=e.target.value;if(state.visualMode!=='all'){state.kind='visual';state.catalogFolder='all';$('catalog-kind').value='visual';$('catalog-folder').value='all';}updateCatalogRows();};
    document.querySelectorAll('[data-catalog-tab]').forEach(b => {b.classList.toggle('active', b.dataset.catalogTab === state.catalogTab);b.onclick = () => {state.catalogTab = b.dataset.catalogTab; renderCatalog();};});
    $('catalog-search').oninput = e => {state.catalogQuery = e.target.value; updateCatalogRows();};
    $('catalog-kind').onchange = e => {state.kind=e.target.value;if(state.kind!=='measure'){state.catalogFolder='all';$('catalog-folder').value='all';}if(state.kind!=='visual'){state.visualMode='all';$('catalog-visual-mode').value='all';}updateCatalogRows();};
    $('catalog-sort').onchange = e => {state.catalogSort = e.target.value; updateCatalogRows();};
    $('clear-catalog').onclick = () => {state.kind = 'all'; state.catalogQuery = ''; state.catalogTab = 'all';state.catalogFolder='all';state.visualMode='all'; renderCatalog();}; updateCatalogRows(); bindPins();
}
function updateCatalogRows() {const nodes = sortedCatalog(); $('catalog-rows').innerHTML = catalogRows(nodes); $('catalog-count').textContent = `${nodes.length} of ${DATA.nodes.length} objects · Downstream counts use model objects only; report and visual usage appears in object details.`;bindActions($('catalog-rows'));enhanceSelects();}
function openDetail(id) {if(!byId.has(id))return;state.detailId = id; state.detailTab = 'overview'; navigate('detail'); $('page-detail').scrollTop = 0;}
function dependencyTable(n, dir) {
    const ids = adjacency[dir].get(n.id) || [];
    if (!ids.length) return '<div class="empty">No direct dependencies in this view.</div>';
    return `<table><thead><tr><th>Object</th><th>Definition</th><th>Kind</th></tr></thead><tbody>${ids.map(id => {const target = byId.get(id); return `<tr><td><button class="pill link" data-detail="${esc(id)}">${esc(target.label)}</button></td><td>${codeTag(target)}</td><td class="muted">${kindNames[target.kind]}</td></tr>`;}).join('')}</tbody></table>`;
}
function findingTable(n) {
    return `<table><thead><tr><th>Severity</th><th>Rule</th><th>Category</th></tr></thead><tbody>${(n.bpa || []).map(b => `<tr><td>${severityPill(b.severity)}</td><td class="issue-title">${ruleMarkup(b)}</td><td><span class="pill">${esc(b.category || 'General')}</span></td></tr>`).join('') || '<tr><td colspan="3" class="empty">No findings attached to this object in the snapshot.</td></tr>'}</tbody></table>`;
}
function reportUsage(n) {
    const modelIds = new Set([n.id, ...traverse(n.id, 'down').keys()]);
    const usages = new Map();
    for (const e of DATA.edges) {
        if (!['BIND_MEASURE','BIND_COLUMN'].includes(e.type) || !modelIds.has(e.source)) continue;
        const target = byId.get(e.target);
        if (!target || !['page','visual'].includes(target.kind)) continue;
        const key = target.id;
        if (!usages.has(key)) usages.set(key, {target, direct:e.source === n.id, bindings:[], via:new Set()});
        const row = usages.get(key);row.direct ||= e.source === n.id;row.via.add(byId.get(e.source)?.label || e.source);
        if (e.label && !row.bindings.includes(e.label)) row.bindings.push(e.label);
    }
    if (n.kind === 'page') for (const v of DATA.nodes.filter(v => v.kind === 'visual' && v.pageId === n.pageId)) usages.set(v.id,{target:v,direct:true,bindings:['Contained on this report page'],via:new Set()});
    if (n.kind === 'visual') usages.set(n.id,{target:n,direct:true,bindings:(n.fieldRefs || []).map(f => typeof f === 'string' ? f : f.name || f.field || JSON.stringify(f)),via:new Set()});
    return [...usages.values()].sort((a,b) => (a.target.pageName || a.target.label).localeCompare(b.target.pageName || b.target.label));
}
function usagePanel(n) {
    const usages = reportUsage(n), pages = new Set(usages.map(u => u.target.pageId));
    return `<div class="panel"><div class="panel-head"><h3>Report usage</h3><span class="pill">${usages.length} bound items</span><span class="grow"></span><span class="tiny muted">${pages.size} report pages</span></div><div class="table-wrap"><table class="usage-table"><thead><tr><th>Report page</th><th>Visual / item</th><th>Usage</th><th>Binding / via</th></tr></thead><tbody>${usages.map(({target,direct,bindings,via}) => {const page = byId.get('page:' + target.pageId);return `<tr><td><button class="pill link" data-detail="${esc(page?.id || target.id)}">${uiIcon('page')}${esc(page?.label || target.pageName || target.label)}</button></td><td><div class="object-name">${icon(target)}<div><button data-detail="${esc(target.id)}">${esc(target.kind === 'page' ? 'Page-level filter' : target.visualType || target.label)}</button><div class="visual-id mono">${esc(target.kind === 'visual' ? target.id.split('/').pop() : target.label)}</div></div></div></td><td><span class="pill ${direct ? 'link' : ''}">${direct ? 'Direct' : 'Via dependency'}</span></td><td><div class="small muted" style="line-height:1.8;max-width:420px;overflow-wrap:anywhere">${bindings.map(esc).join('<br>') || 'Visual field binding'}${!direct ? '<div class="tiny" style="margin-top:5px">Via: '+[...via].map(esc).join(', ')+'</div>' : ''}</div></td></tr>`;}).join('') || '<tr><td colspan="4" class="empty">No report bindings found for this object or its downstream model dependencies.</td></tr>'}</tbody></table></div></div><div class="callout">Direct usage comes from this object’s report bindings. Indirect usage follows downstream model dependencies. Visual names and binding labels come from the project snapshot.</div>`;
}
function renderDetail() {
    const n = byId.get(state.detailId);if(!n){$('page-detail').innerHTML='<div class="empty">No object selected.</div>';return;}const defs=definitions(n);
    let body = '';
    if (state.detailTab === 'overview') {
        body = `<div class="detail-columns"><div><div class="panel"><div class="panel-head"><h3>Metadata</h3></div><table class="meta-table">${metadataRows(n)}</table></div><div class="panel"><div class="panel-head"><h3>Definitions</h3></div>${defs.length ? defs.map((d,i) => `<button class="shortcut" data-code="${esc(n.id)}" data-partition="${i}"><span class="pill link mono">${esc(d.language)}</span><span>${esc(d.name)}</span><span class="grow"></span><span class="muted">View code</span></button>`).join('') : '<div class="empty">No expression available for this object.</div>'}</div></div><div><div class="panel"><div class="panel-head"><h3>Direct upstream</h3><span class="pill">${directCount(n.id,'up')}</span></div>${dependencyTable(n, 'up')}</div><div class="panel"><div class="panel-head"><h3>Direct downstream</h3><span class="pill">${directCount(n.id,'down')}</span></div>${dependencyTable(n, 'down')}</div></div></div>`;
        if (n.columns?.length) body += `<div class="panel"><div class="panel-head"><h3>Columns</h3><span class="pill">${n.columns.length}</span></div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Data type</th><th>Kind</th><th>Format string</th><th>Visibility</th><th>Definition</th></tr></thead><tbody>${n.columns.map((c,i) => `<tr><td class="mono">${esc(c.name)}</td><td><span class="pill column-type">${esc(c.dataType)}</span></td><td class="muted">${esc(c.columnType)}</td><td class="mono muted">${esc(c.formatString || '—')}</td><td><span class="pill ${c.isHidden ? 'neutral' : ''}">${c.isHidden ? 'Hidden' : 'Visible'}</span></td><td>${c.expression ? `<button class="pill link" data-column-code="${i}" data-owner="${esc(n.id)}">${uiIcon('code')}DAX </button>` : '<span class="muted">Source column</span>'}</td></tr>`).join('')}</tbody></table></div></div>`;
        const owned = DATA.nodes.filter(m => m.kind === 'measure' && m.table === n.label && n.kind === 'table');
        if (owned.length) body += `<div class="panel"><div class="panel-head"><h3>Measures in this table</h3><span class="pill">${owned.length}</span></div><table><thead><tr><th>Name</th><th>Format string</th><th>Code</th><th>BPA assessment</th></tr></thead><tbody>${owned.map(m => `<tr><td><button class="pill link" data-detail="${esc(m.id)}">${uiIcon('measure')}${esc(m.label)} </button></td><td class="mono muted">${esc(m.formatString || 'General')}</td><td>${codeTag(m)}</td><td>${statusPill(m)}</td></tr>`).join('')}</tbody></table></div>`;
    } else if (state.detailTab === 'dependencies') {
        body = `<div class="detail-columns"><div class="panel"><div class="panel-head"><h3>Upstream objects</h3></div>${dependencyTable(n,'up')}</div><div class="panel"><div class="panel-head"><h3>Downstream objects</h3></div>${dependencyTable(n,'down')}</div></div>`;
        const rels = DATA.edges.filter(e => e.type === 'REL' && (e.source === n.id || e.target === n.id));
        body += `<div class="panel"><div class="panel-head"><h3>Model relationships</h3><span class="pill">${rels.length}</span></div><table><thead><tr><th>From</th><th>To</th><th>Relationship</th></tr></thead><tbody>${rels.map(e => `<tr><td><button class="pill link" data-detail="${esc(e.source)}">${esc(byId.get(e.source)?.label)}</button></td><td><button class="pill link" data-detail="${esc(e.target)}">${esc(byId.get(e.target)?.label)}</button></td><td class="mono muted">${esc(e.label)}</td></tr>`).join('') || '<tr><td colspan="3" class="empty">No model relationships for this object.</td></tr>'}</tbody></table></div><div class="callout">The lineage canvas follows source, query, expression, and report bindings. Model relationships are listed separately here; they do not change upstream/downstream depth.</div>`;
    } else if (state.detailTab === 'usage') body = usagePanel(n);
    else body = `<div class="panel">${findingTable(n)}</div>`;
    if(state.detailTab==='overview'&&n.fieldRefs?.length)body+=fieldBindingsPanel(n);
    $('page-detail').innerHTML = `<div class="hero"><div class="hero-tags"><button class="pill" data-kind="${n.kind}">${kindNames[n.kind]}</button>${statusPill(n)}${defs.length ? codeTag(n) : ''}<span class="grow"></span>${graphNodes.some(m => m.id === n.id) ? `<button class="btn primary" data-root="${esc(n.id)}">${uiIcon('lineage')} Model lineage</button>` : ''}</div><h1>${esc(n.label)}</h1><p>${esc(n.description || n.subtitle || 'No description available in this project snapshot.')}</p><div class="tabbar detail-tabs"><button data-detail-tab="overview">Overview & schema</button><button data-detail-tab="dependencies">Model dependencies</button><button data-detail-tab="usage">Report usage (${reportUsage(n).length})</button><button data-detail-tab="findings">BPA findings (${n.bpa?.length || 0})</button></div></div><div class="detail-content">${body}</div><button class="review-pin" data-region="7" style="right:24px;top:195px">7</button>`;
    document.querySelectorAll('[data-detail-tab]').forEach(b => {b.classList.toggle('active', b.dataset.detailTab === state.detailTab);b.onclick = () => {state.detailTab = b.dataset.detailTab; renderDetail();};}); bindActions($('page-detail')); bindPins();
}
function fieldBindingsPanel(node) {
    return `<section class="panel"><div class="panel-head"><h3>PBIR field bindings</h3><span class="pill">${node.fieldRefs.length}</span></div><table><thead><tr><th>Kind</th><th>Table</th><th>Field</th><th>Usage</th><th>Inspect</th></tr></thead><tbody>${node.fieldRefs.map(ref=>{
        const target=ref.kind==='Measure'?byId.get('meas:'+ref.name):byId.get('tbl:'+ref.table);
        return `<tr><td>${esc(ref.kind)}</td><td class="mono">${esc(ref.table)}</td><td class="mono">${esc(ref.name)}</td><td>${esc(ref.usage)}</td><td>${target?`<button class="pill link" data-detail="${esc(target.id)}">Object details</button>`:'<span class="muted">Not found</span>'}</td></tr>`;
    }).join('')}</tbody></table></section>`;
}
const severityPill = level => `<span class="pill ${level >= 3 ? 'bad' : level === 2 ? 'warn' : 'link'}"><span class="status-dot"></span>${level >= 3 ? 'High' : level === 2 ? 'Medium' : 'Low'}</span>`;
function violationObject(violation) {
    const prefix={Table:'tbl:',Measure:'meas:',NamedExpression:'pq:',Visual:'vis:',Page:'page:'}[violation.objectType];
    if(prefix&&byId.has(prefix+violation.objectName))return byId.get(prefix+violation.objectName);
    if(violation.objectType==='Column') {
        const match=/^'?(.+?)'?\[([^\]]+)\]$/.exec(violation.objectName||'');
        if(match&&byId.has('tbl:'+match[1]))return byId.get('tbl:'+match[1]);
    }
    return {id:null,kind:'project',label:violation.objectDisplay||violation.objectName||'Project',bpa:[]};
}
const findingKinds={Table:'table',Measure:'measure',NamedExpression:'pq',Column:'column',Visual:'visual',Page:'page'};
const findingKindNames={...kindNames,column:'Column',project:'Project / repository'};
const allFindings=(BPA.violations||[]).map(v=>({...v,kind:findingKinds[v.objectType]||'project',object:violationObject(v)}));
function gateSummary() {
    const gate=BPA.gate||{},counts=BPA.summary?.severityCounts||{};
    const status=gate.status||(gate.passed===true?'PASS':gate.passed===false?'FAIL':'NOT EVALUATED');
    return `<section class="gate-summary"><div><span class="eyebrow">Advisory Gate</span><strong class="pill ${gate.passed===true?'good':gate.passed===false?'bad':'neutral'}">${esc(status)}</strong></div><div><b>${(BPA.violations||[]).length}</b><span>Total findings</span></div><div><b>${Number(gate.blockingCount)||0}</b><span>Blocking · severity ≥ ${esc(gate.failSeverity??'—')}</span></div><div><b>${Number(counts['3'])||0} / ${Number(counts['2'])||0} / ${Number(counts['1'])||0}</b><span>High / medium / low</span></div><div><b>${(BPA.ruleErrors||[]).length}</b><span>Rule evaluation errors</span></div></section>`;
}
function ruleErrorsPanel() {
    const errors=BPA.ruleErrors||[];
    return errors.length?`<section class="rule-errors"><h3>Rule evaluation errors</h3><p>These errors affect the Advisory Gate even when no violation is attached to an object.</p>${errors.map(error=>`<details open><summary>${esc(error.ruleName||error.ruleId||'Rule evaluation error')}</summary><pre>${esc(error.message||error.error||error.line||JSON.stringify(error))}</pre></details>`).join('')}</section>`:'';
}
function renderChecks() {
    const categories = [...new Set(allFindings.map(f => f.category || 'General'))].sort();
    const rules = [...new Map(allFindings.map(f => [f.ruleId,ruleTitle(f)])).entries()].sort((a,b) => a[1].localeCompare(b[1]));
    $('page-checks').innerHTML = `<div class="checks-heading"><div class="eyebrow">Project quality</div><h1>BPA findings</h1><p>Filter static rule results by severity, category, object type, or a specific rule.</p></div>${gateSummary()}${ruleErrorsPanel()}<div class="table-tools"><div class="search"><span>${uiIcon('search')}</span><input id="checks-search" aria-label="Search findings" placeholder="Search a rule or object…" value="${esc(state.checksQuery)}"></div><span class="grow"></span><span class="tiny muted">Sort by</span><select class="filter" id="checks-sort" aria-label="Sort findings"><option value="severity">Severity: high to low</option><option value="object">Object name A–Z</option><option value="rule">Rule name A–Z</option></select></div><div class="checks-filters"><span class="muted">${uiIcon('sliders')}</span><select class="filter" id="checks-severity" aria-label="Filter severity"><option value="all">All severities</option><option value="3">High severity</option><option value="2">Medium severity</option><option value="1">Low severity</option></select><select class="filter" id="checks-category" aria-label="Filter category"><option value="all">All categories</option>${categories.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select><select class="filter" id="checks-kind" aria-label="Filter object type"><option value="all">All object types</option>${[...new Set(allFindings.map(f=>f.kind))].map(k => `<option value="${k}">${esc(findingKindNames[k]||k)}</option>`).join('')}</select><select class="filter" id="checks-rule" aria-label="Filter rule"><option value="all">All rules</option>${rules.map(([id,name]) => `<option value="${esc(id)}">${esc(name)}</option>`).join('')}</select><span class="grow"></span><span class="filter-summary" id="checks-active"></span><button class="btn" id="checks-clear">Reset filters</button></div><div class="table-wrap"><table><thead><tr><th>Severity</th><th>Rule</th><th>Object</th><th>Category</th><th>Definition</th></tr></thead><tbody id="checks-rows"></tbody></table></div><div class="table-foot" id="checks-count"></div>`;
    for (const [id,key] of [['checks-severity','checksSeverity'],['checks-category','checksCategory'],['checks-kind','checksKind'],['checks-rule','checksRule'],['checks-sort','checksSort']]) {
        $(id).value = state[key];$(id).onchange = e => {state[key] = e.target.value;updateCheckRows();};
    }
    $('checks-search').oninput = e => {state.checksQuery = e.target.value;updateCheckRows();};
    $('checks-clear').onclick = () => {Object.assign(state,{checksSeverity:'all',checksCategory:'all',checksKind:'all',checksRule:'all',checksQuery:'',checksSort:'severity'});renderChecks();};
    updateCheckRows();
}
function filteredFindings() {
    const q = state.checksQuery.trim().toLowerCase();
    return allFindings.filter(b => (state.checksSeverity === 'all' || b.severity === Number(state.checksSeverity)) && (state.checksCategory === 'all' || (b.category || 'General') === state.checksCategory) && (state.checksKind === 'all' || b.kind === state.checksKind) && (state.checksRule === 'all' || b.ruleId === state.checksRule) && (ruleTitle(b)+' '+ruleExplanation(b)+' '+b.ruleName+' '+b.ruleId+' '+b.object.label+' '+(b.objectDisplay||'')+' '+b.category).toLowerCase().includes(q)).sort((a,b) => state.checksSort === 'object' ? a.object.label.localeCompare(b.object.label) || b.severity-a.severity : state.checksSort === 'rule' ? ruleTitle(a).localeCompare(ruleTitle(b)) || b.severity-a.severity : b.severity-a.severity || a.object.label.localeCompare(b.object.label));
}
function updateCheckRows() {
    const findings = filteredFindings();
    $('checks-rows').innerHTML = findings.map(b => `<tr><td>${severityPill(b.severity)}<div class="tiny muted" style="margin-top:6px">${esc(b.layer||'')}</div></td><td class="issue-title">${ruleMarkup(b)}</td><td>${b.object.id?`<button class="pill link" data-detail="${esc(b.object.id)}">${esc(b.objectDisplay||b.object.label)}</button>`:`<span class="small">${esc(b.objectDisplay||b.object.label)}</span>`}</td><td><span class="pill">${esc(b.category||'General')}</span></td><td>${b.object.id?codeTag(b.object):'<span class="muted">—</span>'}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">No matching findings.</td></tr>';
    $('checks-count').textContent = `${findings.length} of ${allFindings.length} findings · Source: pipeline BPA report`;
    const count = ['checksSeverity','checksCategory','checksKind','checksRule'].filter(k => state[k] !== 'all').length + (state.checksQuery.trim() ? 1 : 0);
    $('checks-active').textContent = count ? `${count} active filter${count === 1 ? '' : 's'}` : 'No active filters';
    for (const [id,key] of [['checks-severity','checksSeverity'],['checks-category','checksCategory'],['checks-kind','checksKind'],['checks-rule','checksRule']]) $(id).classList.toggle('active-filter',state[key] !== 'all');
    bindActions($('checks-rows'));enhanceSelects();
}
function bindActions(container) {
    container.querySelectorAll('[data-detail]').forEach(b => b.onclick = e => {e.stopPropagation();openDetail(b.dataset.detail);});
    container.querySelectorAll('[data-code]').forEach(b => b.onclick = e => {e.stopPropagation();openCode(b.dataset.code, Number(b.dataset.partition || 0));});
    container.querySelectorAll('[data-root]').forEach(b => b.onclick = () => focusRoot(b.dataset.root));
    container.querySelectorAll('[data-go]').forEach(b => b.onclick = () => navigate(b.dataset.go));
    container.querySelectorAll('[data-kind]').forEach(b => b.onclick = () => {state.kind = b.dataset.kind;state.catalogQuery = '';state.catalogTab = 'all';state.catalogFolder='all';state.visualMode='all';navigate('catalog');});
    container.querySelectorAll('[data-column-code]').forEach(b => b.onclick = () => {const n = byId.get(b.dataset.owner), c = n.columns[Number(b.dataset.columnCode)]; openColumnCode(n, c);});
}
function highlight(line) {
    const pattern = /(\/\/.*$|"(?:[^"\\]|\\.)*"|\b(?:let|in|each|if|then|else|type|true|false|null|VAR|RETURN|CALCULATE|FILTER|DISTINCTCOUNT|COUNTROWS|COALESCE|MAXX|ALL|NOT|ISBLANK|UTCTODAY)\b|\b\d+(?:\.\d+)?\b)/g;
    let last = 0, out = '', match;
    while ((match = pattern.exec(line))) {out += esc(line.slice(last, match.index));const token = match[0], cls = token.startsWith('//') ? 'comment' : token.startsWith('"') ? 'string' : /^\d/.test(token) ? 'number' : 'keyword';out += `<span class="token-${cls}">${esc(token)}</span>`;last = pattern.lastIndex;}
    return out + esc(line.slice(last));
}
function showCodeText(definition) {
    currentCode = definition.code;
    $('code-language').textContent = definition.language;
    $('code-content').innerHTML = (currentCode || 'No expression is available in this snapshot.').split(/\r?\n/).map((line,i) => `<div class="code-line"><span class="line-number">${i + 1}</span><span class="code-source">${highlight(line)}</span></div>`).join('');
    $('code-lines').textContent = `${currentCode.split(/\r?\n/).length} lines`;
}
function openModal(id) {lastModalFocus = document.activeElement;$(id).classList.remove('hidden');enhanceSelects($(id));$(id).querySelector('button')?.focus();}
function closeModal(id) {$(id).classList.add('hidden');lastModalFocus?.focus?.();}
function openCode(id, partition = 0) {
    const n = byId.get(id);if(!n)return;const defs = definitions(n); if (!defs.length) return;
    state.codeId = id;state.partition = Math.min(partition, defs.length - 1);
    $('code-title').textContent = n.label;
    $('code-partition').innerHTML = defs.map((d,i) => `<option value="${i}">${esc(d.name)}</option>`).join('');
    $('code-partition').value = state.partition;$('code-partition').disabled = defs.length === 1;
    $('code-partition').onchange = e => {state.partition = Number(e.target.value);showCodeText(defs[state.partition]);};
    $('code-caption').textContent = defs.length > 1 ? `${defs.length} definitions available for this object` : kindNames[n.kind] + ' definition';
    showCodeText(defs[state.partition]);$('code-content').scrollTop = 0;openModal('code-overlay');
}
function openColumnCode(n,c) {
    state.codeId = n.id;$('code-title').textContent = `${n.label}[${c.name}]`;
    $('code-partition').innerHTML = `<option>${esc(c.name)}</option>`;$('code-partition').disabled = true;
    $('code-caption').textContent = 'Calculated column expression';showCodeText({code:c.expression,language:'DAX'});openModal('code-overlay');
}
const facetLabels = {type:'Object type',checks:'BPA findings',schema:'Schema / format',dependencies:'Direct dependency counts',description:'Description',tags:'Definition & assessment tags'};
function renderFacetPreview() {$('facet-preview').innerHTML = cardHTML(byId.get(state.selected),facetDraft,true);$('facet-preview').querySelectorAll('button').forEach(b => b.disabled = true);}
function openFacets() {
    if (!byId.has(state.selected)) {toast('Select an object first.');return;}
    facetDraft = {...facets};$('facet-options').innerHTML = Object.entries(facetLabels).map(([key,label]) => `<label class="facet-option"><input type="checkbox" data-facet="${key}" ${facetDraft[key] ? 'checked' : ''}>${label}</label>`).join('');
    document.querySelectorAll('[data-facet]').forEach(el => el.onchange = () => {facetDraft[el.dataset.facet] = el.checked;renderFacetPreview();});renderFacetPreview();openModal('facets-overlay');
}
function syncDepths() {$('up-depth').value = state.up === Infinity ? 'all' : state.up;$('down-depth').value = state.down === Infinity ? 'all' : state.down;enhanceSelects();}
function startNodeDrag(e,el) {
    if (e.target.closest('button') || e.button !== 0 || space) return;
    e.stopPropagation();moved = false;const p = layoutNodes.get(el.dataset.node);
    gesture = {type:'node',id:el.dataset.node,el,sx:e.clientX,sy:e.clientY,x:p.x,y:p.y};el.setPointerCapture(e.pointerId);
}
$('viewport').addEventListener('pointerdown', e => {
    if (e.target.closest('button') || (e.button !== 0 && e.button !== 1)) return;
    if (e.target.closest('.asset-node') && !space) return;
    e.preventDefault();moved = false;gesture = {type:'pan',sx:e.clientX,sy:e.clientY,x:tx,y:ty};$('viewport').setPointerCapture(e.pointerId);
});
window.addEventListener('pointermove', e => {
    if (!gesture) return;const dx = e.clientX - gesture.sx,dy = e.clientY - gesture.sy;
    if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
    if (gesture.type === 'pan') {tx = gesture.x + dx;ty = gesture.y + dy;transform();}
    else {const p = layoutNodes.get(gesture.id);p.x = gesture.x + dx / scale;p.y = gesture.y + dy / scale;gesture.el.style.left = p.x + 'px';gesture.el.style.top = p.y + 'px';drawEdges();}
});
window.addEventListener('pointerup', () => {gesture = null;setTimeout(() => moved = false,0);});
$('viewport').addEventListener('wheel', e => {e.preventDefault();const r = $('viewport').getBoundingClientRect();zoomAt(Math.exp(-e.deltaY * .0015),e.clientX - r.left,e.clientY - r.top);},{passive:false});
$('zoom-in').onclick = () => zoomAt(1.2,$('viewport').clientWidth / 2,$('viewport').clientHeight / 2);
$('zoom-out').onclick = () => zoomAt(1/1.2,$('viewport').clientWidth / 2,$('viewport').clientHeight / 2);
$('zoom-label').onclick = () => zoomAt(1/scale,$('viewport').clientWidth / 2,$('viewport').clientHeight / 2);
$('fit').onclick = fit;$('tidy').onclick = () => {arrange();renderGraph(false);fit();};
for (const [id,key] of [['up-depth','up'],['down-depth','down']]) $(id).onchange = e => {state[key] = e.target.value === 'all' ? Infinity : Number(e.target.value);state.all = false;renderGraph();fit();};
$('whole-graph').onclick = () => {state.all = !state.all;renderGraph();fit();};
$('lineage-search').oninput = renderAssetList;
$('lineage-search').onkeydown = e => {if (e.key !== 'Enter') return;const query=e.target.value.trim().toLowerCase();const matches=graphNodes.filter(n=>n.label.toLowerCase().includes(query));const n=matches.find(n=>n.label.toLowerCase()===query)||matches[0];if(n)jumpToNode(n.id);};
$('list-toggle').onclick = () => {$('asset-list').classList.toggle('hidden');fit();};
$('details-toggle').onclick = () => {$('drawer').classList.toggle('hidden');fit();};
$('minimap').onclick = e => {const b = mapGeometry(),r = $('minimap').getBoundingClientRect();tx = $('viewport').clientWidth / 2 - (b.minX + ((e.clientX-r.left)*138/r.width-10)/b.s)*scale;ty = $('viewport').clientHeight / 2 - (b.minY + ((e.clientY-r.top)*91/r.height-10)/b.s)*scale;transform();};
document.querySelectorAll('[data-nav]').forEach(el => el.onclick = () => navigate(el.dataset.nav));
$('collapse-nav').onclick = () => {$('nav').classList.toggle('collapsed-nav');fit();};
$('nav-toggle').onclick = () => {$('nav').classList.toggle('collapsed-nav');fit();};
$('facets-button').onclick = openFacets;
$('reset-facets').onclick = () => {facetDraft = {...defaults};document.querySelectorAll('[data-facet]').forEach(el => el.checked = facetDraft[el.dataset.facet]);renderFacetPreview();};
$('save-facets').onclick = () => {facets = {...facetDraft};try {localStorage.setItem(storageKey('facets'),JSON.stringify(facets));} catch {}closeModal('facets-overlay');renderGraph();fit();};
document.querySelectorAll('[data-close]').forEach(el => el.onclick = () => closeModal(el.dataset.close));
document.querySelectorAll('.overlay').forEach(el => el.addEventListener('click', e => {if (e.target === el) closeModal(el.id);}));
$('copy-code').onclick = async () => {try {await navigator.clipboard.writeText(currentCode);toast('Code copied.');} catch {const selection = window.getSelection(),range = document.createRange();range.selectNodeContents($('code-content'));selection.removeAllRanges();selection.addRange(range);toast('Select code and press Ctrl+C to copy.');}};
$('code-open-detail').onclick = () => {closeModal('code-overlay');openDetail(state.codeId);};
$('wrap-code').onclick = () => {const enabled = $('code-content').classList.toggle('wrap');$('wrap-code').setAttribute('aria-pressed',String(enabled));};
$('expand-code').onclick = () => {const enabled = document.querySelector('#code-overlay .modal').classList.toggle('expanded');$('expand-code').setAttribute('aria-pressed',String(enabled));};
function setTheme(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    $('theme-toggle').innerHTML = `${uiIcon(next === 'dark' ? 'moon' : 'sun')}<span>${next === 'dark' ? 'Dark' : 'Light'}</span>`;
    $('theme-toggle').setAttribute('aria-label',`Switch to ${next === 'dark' ? 'light' : 'dark'} theme`);
    $('theme-toggle').title = `Switch to ${next === 'dark' ? 'light' : 'dark'} theme`;
    try {localStorage.setItem(storageKey('theme'),next);} catch {}
}
$('theme-toggle').onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
$('theme-info').onclick = () => toast((PORTAL.pbipName||'Power BI project')+' · '+(MODEL.sourceMode||'Metadata snapshot')+' · Read-only analysis');
window.addEventListener('keydown', e => {
    const modal = document.querySelector('.overlay:not(.hidden)');
    if (e.key === 'Escape') {if (modal) closeModal(modal.id);$('review-panel').classList.add('hidden');return;}
    if (modal && e.key === 'Tab') {const items = [...modal.querySelectorAll('button:not(:disabled),select:not(:disabled),input:not(:disabled)')].filter(el=>el.getClientRects().length>0);const first = items[0],last = items[items.length-1];if (e.shiftKey && document.activeElement === first) {e.preventDefault();last.focus();} else if (!e.shiftKey && document.activeElement === last) {e.preventDefault();first.focus();}return;}
    if (modal || ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName) || state.page !== 'lineage') return;
    if (e.code === 'Space') {space = true;e.preventDefault();}if (e.key.toLowerCase() === 'f') fit();
});
window.addEventListener('keyup', e => {if (e.code === 'Space') space = false;});window.addEventListener('blur', () => {space = false;gesture = null;});window.addEventListener('resize',fit);
const regions = {1:['Navigation','Home, Catalog, Lineage, BPA findings; project context and navigation density.'],2:['Page header','Breadcrumb, project context, and review entry.'],3:['Lineage controls','Object search, upstream/downstream depth, all objects, and card facets.'],4:['Graph and cards','Dependency layout, edge crossings, card density, tags, and omitted neighbors.'],5:['Canvas navigation','Pan/zoom, minimap, keyboard gestures, and fit.'],6:['Catalog table','Column types, formatting, filters, pill tags, and row actions.'],7:['Object details','Metadata and schema tables, dependencies, definitions, and code popup.'],8:['Home','Project summary, entry points, and navigation to detail.']};
let notes = {},activeRegion = '4',toastTimer;try {notes = JSON.parse(localStorage.getItem(storageKey('notes')) || '{}');} catch {}
function bindPins() {document.querySelectorAll('[data-region]').forEach(b => b.onclick = () => {activeRegion = b.dataset.region;$('review-title').textContent = activeRegion + ' · ' + regions[activeRegion][0];$('review-description').textContent = regions[activeRegion][1];$('review-note').value = notes[activeRegion] || '';$('review-panel').classList.remove('hidden');$('review-note').focus();});}
$('review-toggle').onclick = () => {const on = document.body.classList.toggle('reviewing');$('review-toggle').classList.toggle('active',on);if (!on) $('review-panel').classList.add('hidden');};
$('close-review').onclick = () => $('review-panel').classList.add('hidden');
$('save-note').onclick = () => {notes[activeRegion] = $('review-note').value;try {localStorage.setItem(storageKey('notes'),JSON.stringify(notes));toast('Note saved in this browser.');} catch {toast('Note kept in memory. Export before closing.');}$('review-panel').classList.add('hidden');};
$('export-notes').onclick = () => {const text = '# Lineage Studio · v6 feedback\n\n' + Object.entries(notes).map(([id,note]) => `## ${id}. ${regions[id]?.[0]}\n${note}\n`).join('\n');const url = URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'})),a = document.createElement('a');a.href=url;a.download='lineage-v6-feedback.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
function toast(message) {$('toast').textContent = message;$('toast').classList.remove('hidden');clearTimeout(toastTimer);toastTimer = setTimeout(() => $('toast').classList.add('hidden'),3500);}
const modelTables = DATA.nodes.filter(n => n.kind === 'table');
const RELATIONSHIPS = (MODEL.relationships || []).filter(r=>modelTables.some(t=>t.label===r.fromTable)&&modelTables.some(t=>t.label===r.toTable));
const relatedTables = new Set(RELATIONSHIPS.flatMap(r => [r.fromTable,r.toTable]));
const modelState = {keysOnly:true,connectedOnly:false,expanded:new Set(),query:'',table:null,relationship:null,scale:1,tx:30,ty:80,positions:new Map(),scroll:new Map(),gesture:null,dragged:false};
function modelTableKind(table) {
    if(!table.columns?.length && table.measureCount>0)return 'Measure table';
    if(table.partitions?.some(p=>p.sourceType==='Calculated'))return 'Calculated table';
    return 'Imported table';
}
function modelFields(table) {
    const keys = new Set(RELATIONSHIPS.flatMap(r => [...(r.fromTable === table.label ? [r.fromColumn] : []),...(r.toTable === table.label ? [r.toColumn] : [])]));
    const here=modelState.positions.get(table.label);
    const fieldOrder=column=>{
        const relation=RELATIONSHIPS.find(r=>(r.fromTable===table.label&&r.fromColumn===column.name)||(r.toTable===table.label&&r.toColumn===column.name));
        if(!relation)return [2,0];
        const otherName=relation.fromTable===table.label?relation.toTable:relation.fromTable;
        const other=modelState.positions.get(otherName);
        return [here&&other&&other.x<here.x?0:1,other?.y||0];
    };
    const columns=[...(table.columns||[])].sort((a,b)=>{const ao=fieldOrder(a),bo=fieldOrder(b);return ao[0]-bo[0]||ao[1]-bo[1];});
    if(modelState.expanded.has(table.label))return columns;
    return keys.size?columns.filter(c=>keys.has(c.name)):[];
}
function modelMembers(table) {
    const columns=modelFields(table).map(c=>({...c,memberKind:c.columnType==='Calculated'?'calculated':c.columnType==='CalculatedTableColumn'?'table-column':'column'}));
    const measures=modelState.expanded.has(table.label)?DATA.nodes.filter(n=>n.kind==='measure'&&n.table===table.label).map(m=>({...m,name:m.label,memberKind:'measure'})):[];
    return [...columns,...measures];
}
function shownModelTables() {return modelTables.filter(t => !modelState.connectedOnly || relatedTables.has(t.label));}
function modelVisibleRows(table) {return Math.min(modelMembers(table).length,relatedTables.has(table.label)?9:6);}
function modelTableHeight(table) {return 65+modelVisibleRows(table)*27+43;}
function isolatedBay() {
    const tables=modelTables.filter(t=>!relatedTables.has(t.label));
    return {x:relatedTables.size?1270:25,y:35,width:310,height:Math.max(420,tables.reduce((sum,t)=>sum+modelTableHeight(t)+18,55))};
}
function renderModelBay() {const b=isolatedBay();return `<div class="model-isolated-bay" style="left:${b.x}px;top:${b.y}px;width:${b.width}px;height:${b.height}px"><span>Disconnected tables</span><small>Utility, calculated & measure tables</small></div>`;}
function packIsolatedTables() {
    let y=90;const bay=isolatedBay();
    for(const table of modelTables.filter(t=>!relatedTables.has(t.label))) {modelState.positions.set(table.label,{x:bay.x+15,y});y+=modelTableHeight(table)+18;}
}
function arrangeModel() {
    modelState.positions.clear();
    const remaining=new Set(modelTables.filter(t=>relatedTables.has(t.label)).map(t=>t.label));
    const links=name=>RELATIONSHIPS.filter(r=>r.fromTable===name||r.toTable===name);
    let componentY=45;
    while(remaining.size) {
        const root=[...remaining].sort((a,b)=>links(b).length-links(a).length||a.localeCompare(b))[0];
        const component=[],queue=[root];remaining.delete(root);
        for(let cursor=0;cursor<queue.length;cursor++) {
            const name=queue[cursor];component.push(name);
            const adjacent=links(name).map(r=>({name:r.fromTable===name?r.toTable:r.fromTable,one:(r.fromTable===name?r.toCardinality:r.fromCardinality)==='One'})).sort((a,b)=>Number(b.one)-Number(a.one)||a.name.localeCompare(b.name));
            for(const next of adjacent)if(remaining.delete(next.name))queue.push(next.name);
        }
        modelState.positions.set(root,{x:445,y:componentY+160});
        let leftY=componentY,rightY=componentY+160;
        component.slice(1).forEach((name,index)=>{
            const left=index%3!==2,x=left?25:865,y=left?leftY:rightY;
            modelState.positions.set(name,{x,y});
            const table=modelTables.find(t=>t.label===name);
            if(left)leftY+=modelTableHeight(table)+100;else rightY+=modelTableHeight(table)+100;
        });
        componentY=Math.max(leftY,rightY,componentY+modelTableHeight(modelTables.find(t=>t.label===root))+250)+100;
    }
    packIsolatedTables();
}
function avoidModelOverlap() {
    const columns=new Map();
    for(const table of modelTables.filter(t=>relatedTables.has(t.label))) {
        const p=modelState.positions.get(table.label);if(!p)continue;
        if(!columns.has(p.x))columns.set(p.x,[]);columns.get(p.x).push(table);
    }
    for(const tables of columns.values()) {
        tables.sort((a,b)=>modelState.positions.get(a.label).y-modelState.positions.get(b.label).y);
        let bottom=-Infinity;
        for(const table of tables){const p=modelState.positions.get(table.label);p.y=Math.max(p.y,bottom+80);bottom=p.y+modelTableHeight(table);}
    }
}
function modelBounds() {
    const tables = shownModelTables();
    return {minX:Math.min(0,...tables.map(t => modelState.positions.get(t.label).x-30)),minY:Math.min(0,...tables.map(t => modelState.positions.get(t.label).y-30)),maxX:Math.max(500,...tables.map(t => modelState.positions.get(t.label).x+310)),maxY:Math.max(400,...tables.map(t => modelState.positions.get(t.label).y+modelTableHeight(t)+30))};
}
function renderModelTable(table) {
    const p=modelState.positions.get(table.label),members=modelMembers(table),r=RELATIONSHIPS[modelState.relationship];
    const connected=RELATIONSHIPS.filter(r=>r.fromTable===table.label||r.toTable===table.label).length;
    const expanded=modelState.expanded.has(table.label),total=(table.columns?.length||0)+(table.measureCount||0);
    const type=modelTableKind(table),kindLabels={column:'Source',calculated:'Calculated','table-column':'Table col.',measure:'Measure'};
    return `<article class="model-table ${modelState.table===table.label?'selected':''} ${!connected?'isolated-table':''}" data-model-table="${esc(table.label)}" style="left:${p.x}px;top:${p.y}px"><div class="model-table-head">${icon(table)}<button data-model-select="${esc(table.label)}" title="Table properties">${esc(table.label)}</button><button class="model-info" data-detail="${esc(table.id)}" aria-label="Table details">${uiIcon('info')}</button></div><div class="model-table-meta"><span>${table.columnCount||0} columns</span><span>${table.measureCount||0} measures</span><span class="grow"></span><span>${connected?`${connected} links`:'Disconnected'}</span></div><div class="model-field-list" data-model-scroll="${esc(table.label)}" style="max-height:${modelVisibleRows(table)*27}px">${members.map(c=>{
        const key=c.memberKind!=='measure'&&RELATIONSHIPS.some(r=>(r.fromTable===table.label&&r.fromColumn===c.name)||(r.toTable===table.label&&r.toColumn===c.name));
        const active=r&&((r.fromTable===table.label&&r.fromColumn===c.name)||(r.toTable===table.label&&r.toColumn===c.name));
        const glyph=c.memberKind==='measure'?'measure':c.memberKind==='column'?'table':'query';
        const dataType=c.memberKind==='measure'?'DAX':c.dataType==='Unknown'?'—':c.dataType||'—';
        return `<button class="model-field member-${c.memberKind} ${key?'relationship-key':''} ${active?'active':''}" data-model-field="${esc(c.name)}" data-model-owner="${esc(table.label)}" data-member-kind="${c.memberKind}" data-member-id="${esc(c.id||'')}" title="${esc(c.name)} · ${c.memberKind==='table-column'?'Column generated by a calculated table':kindLabels[c.memberKind]} · ${esc(dataType)}"><span class="member-glyph">${uiIcon(glyph)}</span><span class="field-name">${esc(c.name)}</span><span class="member-kind-label">${kindLabels[c.memberKind]}</span><span class="field-type">${esc(dataType)}</span></button>`;
    }).join('')}</div><div class="model-table-footer"><span class="pill table-kind ${type==='Calculated table'?'calculated-kind':type==='Measure table'?'measure-kind':''}">${type==='Imported table'?'Import':type}</span><button class="model-members-toggle" data-model-members="${esc(table.label)}" aria-expanded="${expanded}">${uiIcon('catalog')}${expanded?'Collapse':`Fields · ${total}`}</button></div></article>`;
}
function toggleModelMembers(name) {
    if(modelState.expanded.has(name))modelState.expanded.delete(name);else modelState.expanded.add(name);
    modelState.scroll.delete(name);packIsolatedTables();
    avoidModelOverlap();
    renderModel();
}
function openModelMember(tableName,name,kind) {
    const table=modelTables.find(t=>t.label===tableName);
    if(kind==='measure'){const measure=DATA.nodes.find(n=>n.kind==='measure'&&n.table===tableName&&n.label===name);if(measure)openCode(measure.id);return;}
    const column=table.columns.find(c=>c.name===name);
    if(kind==='calculated'&&column?.expression){openColumnCode(table,column);return;}
    if(kind==='table-column'){openCode(table.id);return;}
    const index=RELATIONSHIPS.findIndex(r=>(r.fromTable===tableName&&r.fromColumn===name)||(r.toTable===tableName&&r.toColumn===name));
    if(index>=0)selectModelRelationship(index);else selectModelTable(tableName);
}
function renderModel() {
    if (!modelState.positions.size) arrangeModel();
    $('page-model').innerHTML = `<div class="model-toolbar"><div class="search"><span>${uiIcon('search')}</span><input id="model-search" aria-label="Find table or column" placeholder="Find a table or column · Enter to jump" value="${esc(modelState.query)}"></div><div class="segmented"><button id="model-keys" class="${modelState.keysOnly ? 'active' : ''}">Keys</button><button id="model-columns" class="${!modelState.keysOnly ? 'active' : ''}">All fields</button></div><button class="btn ${!modelState.connectedOnly ? 'active' : ''}" id="model-isolated">Disconnected tables <span class="pill">${modelTables.filter(t => !relatedTables.has(t.label)).length}</span></button><span class="grow"></span><button class="btn" id="model-tidy">${uiIcon('refresh')}Tidy up</button><button class="btn" id="model-fit">${uiIcon('fit')}Fit</button></div><div class="model-workspace"><div class="model-canvas"><div class="model-viewport" id="model-viewport"><div class="model-world" id="model-world">${!modelState.connectedOnly&&modelTables.some(t=>!relatedTables.has(t.label))?renderModelBay():''}<svg class="model-edges" id="model-edges"></svg><div id="model-tables">${shownModelTables().map(renderModelTable).join('')}</div></div></div><div class="model-context"><h3>Table relationships</h3><p>${shownModelTables().length} of ${modelTables.length} tables · ${RELATIONSHIPS.length} relationships</p></div><div class="model-legend"><span><b>1</b> One</span><span><b>∗</b> Many</span><span><i class="legend-line"></i>Active</span><span><i class="legend-line inactive"></i>Inactive</span><span>Arrows show filter flow</span></div><div class="canvas-bottom"><button class="tool" id="model-zoom-out" aria-label="Zoom out">${uiIcon('minus')}</button><span class="tool zoom" id="model-zoom-label"></span><button class="tool" id="model-zoom-in" aria-label="Zoom in">${uiIcon('plus')}</button><span class="tool-sep"></span><button class="tool" id="model-fit-bottom" title="Fit model">${uiIcon('fit')}</button></div><div class="canvas-hint">Drag headers to arrange tables · Drag background to pan · Scroll to zoom · Click a relationship for properties</div><button class="review-pin" data-region="9" style="top:100px;right:20px">9</button></div><section class="model-inspector hidden" id="model-inspector" aria-label="Model properties"></section></div>`;
    bindActions($('page-model'));
    $('model-keys').onclick = () => {modelState.keysOnly=true;modelState.expanded.clear();arrangeModel();renderModel();fitModel();};
    $('model-columns').onclick = () => {modelState.keysOnly=false;modelTables.forEach(t=>modelState.expanded.add(t.label));arrangeModel();renderModel();fitModel();};
    $('model-isolated').onclick = () => {modelState.connectedOnly=!modelState.connectedOnly;renderModel();fitModel();};
    $('model-tidy').onclick = () => {arrangeModel();renderModel();fitModel();};
    $('model-fit').onclick = fitModel;$('model-fit-bottom').onclick = fitModel;
    $('model-zoom-out').onclick = () => zoomModel(1/1.2);$('model-zoom-in').onclick = () => zoomModel(1.2);
    $('model-search').oninput = e => {modelState.query=e.target.value;highlightModelSearch();};
    $('model-search').onkeydown = e => {if (e.key !== 'Enter') return;const query=modelState.query.trim().toLowerCase();const table=modelTables.find(t => t.label.toLowerCase().includes(query)||t.columns?.some(c => c.name.toLowerCase().includes(query)));if(table) jumpModelTable(table.label);else toast('No matching table or column.');};
    $('page-model').querySelectorAll('[data-model-select]').forEach(b => b.onclick = () => {if(!modelState.dragged)selectModelTable(b.dataset.modelSelect);});
    $('page-model').querySelectorAll('[data-model-field]').forEach(b=>b.onclick=()=>openModelMember(b.dataset.modelOwner,b.dataset.modelField,b.dataset.memberKind));
    $('page-model').querySelectorAll('[data-model-members]').forEach(b=>b.onclick=()=>toggleModelMembers(b.dataset.modelMembers));
    $('page-model').querySelectorAll('.model-table-head').forEach(head => {
        head.onpointerdown = e => {if(e.button!==0 || e.target.closest('[data-detail]'))return;e.stopPropagation();modelState.dragged=false;const el=head.closest('.model-table'),p=modelState.positions.get(el.dataset.modelTable);modelState.gesture={type:'table',name:el.dataset.modelTable,el,x:p.x,y:p.y,sx:e.clientX,sy:e.clientY};head.setPointerCapture(e.pointerId);};
        head.onclick = e => {if(!modelState.dragged&&!e.target.closest('[data-detail]'))selectModelTable(head.closest('.model-table').dataset.modelTable);};
    });
    $('page-model').querySelectorAll('[data-model-scroll]').forEach(el => {el.scrollTop=modelState.scroll.get(el.dataset.modelScroll)||0;el.onscroll=()=>{modelState.scroll.set(el.dataset.modelScroll,el.scrollTop);drawModelEdges();};});
    $('model-viewport').onpointerdown = e => {if(e.button!==0 || e.target.closest('.model-table') || e.target.closest('[data-model-rel]'))return;e.preventDefault();modelState.gesture={type:'pan',x:modelState.tx,y:modelState.ty,sx:e.clientX,sy:e.clientY};$('model-viewport').setPointerCapture(e.pointerId);};
    $('model-viewport').addEventListener('wheel',e=>{if(e.target.closest('.model-field-list') && !e.ctrlKey)return;e.preventDefault();const r=$('model-viewport').getBoundingClientRect();zoomModel(Math.exp(-e.deltaY*.0015),e.clientX-r.left,e.clientY-r.top);},{passive:false});
    renderModelInspector();drawModelEdges();transformModel();highlightModelSearch();bindPins();
}
function modelAnchor(tableName,column,side) {
    const table=modelTables.find(t=>t.label===tableName),p=modelState.positions.get(tableName),row=Math.max(0,modelFields(table).findIndex(c=>c.name===column));
    const y=Math.max(68,Math.min(65+modelVisibleRows(table)*27-6,65+row*27+13.5-(modelState.scroll.get(tableName)||0)));
    return {x:p.x+(side==='right'?280:0),y:p.y+y};
}
const cardinality = value => value === 'One' ? '1' : value === 'Many' ? '∗' : '?';
function drawModelEdges() {
    if (!$('model-edges'))return;
    const names=new Set(shownModelTables().map(t=>t.label));
    $('model-edges').innerHTML='<defs><marker id="model-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L8 4L0 8" fill="var(--edge-selected)"/></marker></defs>'+RELATIONSHIPS.map((r,index)=>{
        if(!names.has(r.fromTable)||!names.has(r.toTable))return '';
        const fromPos=modelState.positions.get(r.fromTable),toPos=modelState.positions.get(r.toTable),right=toPos.x>fromPos.x;
        const a=modelAnchor(r.fromTable,r.fromColumn,right?'right':'left'),b=modelAnchor(r.toTable,r.toColumn,right?'left':'right'),bend=Math.max(55,Math.abs(b.x-a.x)/2),sign=right?1:-1;
        const d=`M${a.x},${a.y}C${a.x+sign*bend},${a.y} ${b.x-sign*bend},${b.y} ${b.x},${b.y}`;
        const midX=(a.x+b.x)/2,midY=(a.y+b.y)/2,selected=modelState.relationship===index;
        const bidirectional=r.crossFilteringBehavior==='BothDirections';
        return `<g class="model-rel ${selected?'selected':''} ${r.isActive?'':'inactive'}" data-model-rel="${index}" role="button" tabindex="0" aria-label="${esc(r.name)}"><path class="model-rel-hit" d="${d}"/><path class="model-rel-line" d="${d}" marker-start="url(#model-arrow)" ${bidirectional?'marker-end="url(#model-arrow)"':''}/><text x="${a.x+sign*15}" y="${a.y-9}" class="cardinality">${cardinality(r.fromCardinality)}</text><text x="${b.x-sign*15}" y="${b.y-9}" class="cardinality">${cardinality(r.toCardinality)}</text><g class="relationship-badge" transform="translate(${midX-25},${midY-11})"><rect width="50" height="22" rx="6"/><text x="25" y="15">${cardinality(r.fromCardinality)} : ${cardinality(r.toCardinality)}</text></g></g>`;
    }).join('');
    $('model-edges').querySelectorAll('[data-model-rel]').forEach(el=>{el.onclick=()=>selectModelRelationship(Number(el.dataset.modelRel));el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectModelRelationship(Number(el.dataset.modelRel));}};});
}
function transformModel() {
    if(!$('model-world'))return;
    $('model-world').style.transform=`translate(${modelState.tx}px,${modelState.ty}px) scale(${modelState.scale})`;
    $('model-viewport').style.backgroundSize=`${20*modelState.scale}px ${20*modelState.scale}px`;
    $('model-viewport').style.backgroundPosition=`${modelState.tx}px ${modelState.ty}px`;
    $('model-zoom-label').textContent=Math.round(modelState.scale*100)+'%';
}
function fitModel() {
    if(state.page!=='model')return;
    const v=$('model-viewport'),b=modelBounds(),w=b.maxX-b.minX,h=b.maxY-b.minY;
    modelState.scale=Math.max(.08,Math.min(1,(v.clientWidth-70)/w,(v.clientHeight-170)/h));
    modelState.tx=(v.clientWidth-w*modelState.scale)/2-b.minX*modelState.scale;modelState.ty=70+(v.clientHeight-150-h*modelState.scale)/2-b.minY*modelState.scale;transformModel();
}
function zoomModel(factor,x=$('model-viewport').clientWidth/2,y=$('model-viewport').clientHeight/2) {
    const next=Math.max(.08,Math.min(2,modelState.scale*factor));modelState.tx=x-(x-modelState.tx)*next/modelState.scale;modelState.ty=y-(y-modelState.ty)*next/modelState.scale;modelState.scale=next;transformModel();
}
function selectModelTable(name) {modelState.table=name;modelState.relationship=null;renderModelInspector();refreshModelSelection();drawModelEdges();}
function selectModelRelationship(index) {modelState.relationship=index;modelState.table=null;renderModelInspector();refreshModelSelection();drawModelEdges();}
function refreshModelSelection() {
    const r=RELATIONSHIPS[modelState.relationship];
    $('page-model').querySelectorAll('.model-table').forEach(el=>el.classList.toggle('selected',el.dataset.modelTable===modelState.table || !!r&&(el.dataset.modelTable===r.fromTable||el.dataset.modelTable===r.toTable)));
    $('page-model').querySelectorAll('[data-model-field]').forEach(el=>el.classList.toggle('active',!!r&&((r.fromTable===el.dataset.modelOwner&&r.fromColumn===el.dataset.modelField)||(r.toTable===el.dataset.modelOwner&&r.toColumn===el.dataset.modelField))));
}
function renderModelInspector() {
    const panel=$('model-inspector'),r=RELATIONSHIPS[modelState.relationship],table=modelTables.find(t=>t.label===modelState.table);
    if(!r&&!table){panel.classList.add('hidden');return;}
    panel.classList.remove('hidden');
    if(r){
        const cardinalText=`${r.fromCardinality} to ${r.toCardinality}`;
        panel.innerHTML=`<div class="drawer-head">Relationship properties<span class="grow"></span><button class="btn icon" id="close-model-inspector" aria-label="Close properties">${uiIcon('close')}</button></div><div class="drawer-body"><span class="pill ${r.isActive?'good':'neutral'}">${r.isActive?'Active':'Inactive'}</span><h2>${esc(cardinalText)}</h2><div class="relationship-endpoint"><span>From</span><strong>${esc(r.fromTable)}</strong><code>${esc(r.fromColumn)}</code></div><div class="relationship-endpoint"><span>To</span><strong>${esc(r.toTable)}</strong><code>${esc(r.toColumn)}</code></div><table class="meta-table"><tr><th>Cardinality</th><td>${cardinality(r.fromCardinality)} : ${cardinality(r.toCardinality)}</td></tr><tr><th>Cross-filter</th><td>${r.crossFilteringBehavior==='BothDirections'?'Both directions':'Single direction'}</td></tr><tr><th>Security filter</th><td>${esc(r.securityFilteringBehavior)}</td></tr></table><div class="callout" style="margin-top:17px">${r.crossFilteringBehavior==='BothDirections'?'Filters can travel between these tables in both directions.':`Filters travel from ${esc(r.toTable)} to ${esc(r.fromTable)}.`}</div></div>`;
    } else panel.innerHTML=`<div class="drawer-head">Table properties<span class="grow"></span><button class="btn icon" id="close-model-inspector" aria-label="Close properties">${uiIcon('close')}</button></div><div class="drawer-body">${icon(table)}<h2>${esc(table.label)}</h2><table class="meta-table"><tr><th>Columns</th><td>${table.columnCount||0}</td></tr><tr><th>Measures</th><td>${table.measureCount||0}</td></tr><tr><th>Relationships</th><td>${RELATIONSHIPS.filter(r=>r.fromTable===table.label||r.toTable===table.label).length}</td></tr></table><button class="btn" style="margin-top:20px" data-detail="${esc(table.id)}">Object details</button></div>`;
    $('close-model-inspector').onclick=()=>{modelState.relationship=null;modelState.table=null;panel.classList.add('hidden');refreshModelSelection();drawModelEdges();};bindActions(panel);
}
function jumpModelTable(name) {
    if(!relatedTables.has(name)&&modelState.connectedOnly){modelState.connectedOnly=false;renderModel();}
    selectModelTable(name);const p=modelState.positions.get(name);modelState.scale=Math.max(.65,modelState.scale);modelState.tx=$('model-viewport').clientWidth/2-(p.x+140)*modelState.scale;modelState.ty=$('model-viewport').clientHeight/2-(p.y+100)*modelState.scale;transformModel();
}
function highlightModelSearch() {const q=modelState.query.trim().toLowerCase();$('page-model').querySelectorAll('[data-model-table]').forEach(el=>{const t=modelTables.find(t=>t.label===el.dataset.modelTable);const match=!q||t.label.toLowerCase().includes(q)||t.columns?.some(c=>c.name.toLowerCase().includes(q));el.classList.toggle('search-dimmed',!match);});}
window.addEventListener('pointermove',e=>{
    const g=modelState.gesture;if(!g)return;const dx=e.clientX-g.sx,dy=e.clientY-g.sy;if(Math.abs(dx)+Math.abs(dy)>4)modelState.dragged=true;
    if(g.type==='pan'){modelState.tx=g.x+dx;modelState.ty=g.y+dy;transformModel();}
    else{const p=modelState.positions.get(g.name);p.x=g.x+dx/modelState.scale;p.y=g.y+dy/modelState.scale;g.el.style.left=p.x+'px';g.el.style.top=p.y+'px';drawModelEdges();}
});
window.addEventListener('pointerup',()=>{modelState.gesture=null;setTimeout(()=>modelState.dragged=false,0);});window.addEventListener('blur',()=>modelState.gesture=null);window.addEventListener('resize',fitModel);
window.addEventListener('keydown',e=>{if(state.page==='model'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&e.key.toLowerCase()==='f'&&!document.querySelector('.overlay:not(.hidden)'))fitModel();});
regions[9]=['Data model','Relationship canvas, cardinality, filter direction, key columns, disconnected tables, and relationship properties.'];
const selectControllers=new WeakMap();
let activeDropdown=null,dropdownIndex=0,dropdownQuery='',dropdownTypeahead='',dropdownTypedAt=0;
function selectOptions(select,query='') {
    return [...select.options].filter(o=>!o.hidden&&o.textContent.toLowerCase().includes(query.toLowerCase())).map(o=>({value:o.value,label:o.textContent,disabled:o.disabled}));
}
function syncSelect(select) {
    const controller=selectControllers.get(select);if(!controller)return;
    const selected=[...select.options].find(o=>o.value===select.value);
    controller.label.textContent=selected?.textContent||'Choose an option';
    controller.button.disabled=select.disabled;
    controller.button.title=selected?.textContent||'';
    controller.button.classList.toggle('active-filter',select.classList.contains('active-filter'));
    controller.button.setAttribute('aria-expanded',String(activeDropdown?.select===select));
}
function enhanceSelects(container=document) {
    container.querySelectorAll('select').forEach(select=>{
        if(!selectControllers.has(select)) {
            const wrapper=document.createElement('span');wrapper.className='select-control';
            select.parentNode.insertBefore(wrapper,select);wrapper.appendChild(select);
            select.classList.add('native-select');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
            const button=document.createElement('button');button.type='button';button.className='select-trigger '+(select.classList.contains('filter')?'filter':'');
            button.id=(select.id||'select')+'-trigger';button.setAttribute('role','combobox');button.setAttribute('aria-haspopup','listbox');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls','select-popover-options');
            button.setAttribute('aria-label',select.getAttribute('aria-label')||select.labels?.[0]?.textContent||'Choose an option');
            const label=document.createElement('span');label.className='select-value';button.appendChild(label);
            const chevron=document.createElement('span');chevron.className='select-chevron';chevron.innerHTML=uiIcon('chevron');button.appendChild(chevron);wrapper.appendChild(button);
            selectControllers.set(select,{wrapper,button,label});
            button.onclick=()=>activeDropdown?.select===select?closeDropdown():openDropdown(select);
            button.onkeydown=e=>{if(['ArrowDown','ArrowUp','Enter',' '].includes(e.key)){e.preventDefault();e.stopPropagation();openDropdown(select);}};
            select.addEventListener('change',()=>syncSelect(select));
        }
        syncSelect(select);
    });
}
function dropdownElement() {
    let popup=$('select-popover');
    if(!popup) {popup=document.createElement('div');popup.id='select-popover';popup.className='select-popover hidden';document.body.appendChild(popup);}
    return popup;
}
function openDropdown(select) {
    if(select.disabled)return;
    closeDropdown(false);const controller=selectControllers.get(select);if(!controller)return;
    activeDropdown={select,controller};dropdownQuery='';
    const popup=dropdownElement(),options=selectOptions(select),searchable=options.length>10;
    dropdownIndex=Math.max(0,options.findIndex(o=>o.value===select.value));
    popup.innerHTML=`${searchable?`<div class="select-search">${uiIcon('search')}<input id="select-popover-search" placeholder="Find an option…" aria-label="Search dropdown options" autocomplete="off"></div>`:''}<div id="select-popover-options" role="listbox" aria-label="${esc(controller.button.getAttribute('aria-label'))}"></div><div class="select-menu-hint">↑ ↓ Navigate<span>Enter Select · Esc Close</span></div>`;
    popup.classList.remove('hidden');controller.button.setAttribute('aria-expanded','true');
    renderDropdownOptions();positionDropdown();
    if(searchable) {$('select-popover-search').oninput=e=>{dropdownQuery=e.target.value;dropdownIndex=0;renderDropdownOptions();};$('select-popover-search').focus();}
}
function renderDropdownOptions() {
    if(!activeDropdown)return;
    const {select,controller}=activeDropdown,options=selectOptions(select,dropdownQuery);
    dropdownIndex=Math.max(0,Math.min(dropdownIndex,options.length-1));
    $('select-popover-options').innerHTML=options.map((o,index)=>`<button type="button" role="option" id="select-option-${index}" class="select-option ${o.value===select.value?'selected':''} ${index===dropdownIndex?'highlighted':''}" aria-selected="${o.value===select.value}" data-option-index="${index}" ${o.disabled?'disabled':''}><span>${esc(o.label)}</span><span class="option-check">${o.value===select.value?uiIcon('check'):''}</span></button>`).join('')||'<div class="select-no-results">No matching options.</div>';
    controller.button.setAttribute('aria-activedescendant','select-option-'+dropdownIndex);
    $('select-popover-options').querySelectorAll('[data-option-index]').forEach(button=>{
        button.onpointermove=()=>{dropdownIndex=Number(button.dataset.optionIndex);$('select-popover-options').querySelectorAll('.select-option').forEach(b=>b.classList.toggle('highlighted',b===button));};
        button.onclick=()=>chooseDropdownOption(Number(button.dataset.optionIndex));
    });
}
function positionDropdown() {
    if(!activeDropdown)return;
    const popup=dropdownElement(),rect=activeDropdown.controller.button.getBoundingClientRect();
    const width=Math.min(420,Math.max(rect.width,activeDropdown.select.options.length>10?270:190));
    popup.style.width=width+'px';popup.style.left=Math.max(10,Math.min(rect.left,window.innerWidth-width-10))+'px';
    const height=Math.min(360,popup.offsetHeight||300),below=window.innerHeight-rect.bottom-10;
    popup.style.top=(below>=height?rect.bottom+7:Math.max(10,rect.top-height-7))+'px';
}
function chooseDropdownOption(index) {
    if(!activeDropdown)return;
    const {select}=activeDropdown,option=selectOptions(select,dropdownQuery)[index];if(!option||option.disabled)return;
    closeDropdown(false);select.value=option.value;syncSelect(select);
    select.dispatchEvent(new Event('change',{bubbles:true}));
    const replacement=select.id?document.getElementById(select.id):select;
    selectControllers.get(replacement)?.button.focus();
}
function closeDropdown(restoreFocus=true) {
    if(!activeDropdown)return;
    const controller=activeDropdown.controller;controller.button.setAttribute('aria-expanded','false');controller.button.removeAttribute('aria-activedescendant');
    $('select-popover')?.classList.add('hidden');activeDropdown=null;if(restoreFocus&&controller.button.isConnected)controller.button.focus();
}
document.addEventListener('pointerdown',e=>{if(activeDropdown&&!$('select-popover')?.contains(e.target)&&!activeDropdown.controller.button.contains(e.target))closeDropdown(false);},true);
document.addEventListener('keydown',e=>{
    if(!activeDropdown)return;
    const options=selectOptions(activeDropdown.select,dropdownQuery);
    if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();closeDropdown();return;}
    if(e.key==='Tab'){closeDropdown();return;}
    if(['ArrowDown','ArrowUp','Home','End','Enter'].includes(e.key)) {
        e.preventDefault();e.stopImmediatePropagation();
        if(e.key==='Enter'){chooseDropdownOption(dropdownIndex);return;}
        if(e.key==='Home')dropdownIndex=0;else if(e.key==='End')dropdownIndex=options.length-1;else dropdownIndex=(dropdownIndex+(e.key==='ArrowDown'?1:-1)+options.length)%Math.max(1,options.length);
        for(let attempts=0;attempts<options.length&&options[dropdownIndex]?.disabled;attempts++)dropdownIndex=(dropdownIndex+1)%options.length;
        renderDropdownOptions();$('select-option-'+dropdownIndex)?.scrollIntoView({block:'nearest'});return;
    }
    if(e.key.length===1&&document.activeElement.id!=='select-popover-search'&&!e.ctrlKey&&!e.metaKey) {
        e.preventDefault();e.stopImmediatePropagation();const now=Date.now();dropdownTypeahead=now-dropdownTypedAt>700?e.key:dropdownTypeahead+e.key;dropdownTypedAt=now;
        const index=options.findIndex(o=>o.label.toLowerCase().startsWith(dropdownTypeahead.toLowerCase()));if(index>=0){dropdownIndex=index;renderDropdownOptions();$('select-option-'+index)?.scrollIntoView({block:'nearest'});}
    }
},true);
window.addEventListener('resize',()=>closeDropdown(false));
document.addEventListener('scroll',e=>{if(activeDropdown&&!$('select-popover')?.contains(e.target))closeDropdown(false);},true);
let savedTheme = 'light';try {savedTheme = localStorage.getItem(storageKey('theme')) || 'light';} catch {}
$('project-name').textContent=PORTAL.pbipName || 'Power BI project';
$('gate-status').textContent='Gate: '+(BPA.gate?.status||'Not evaluated');
$('gate-status').classList.add(BPA.gate?.passed===true?'good':BPA.gate?.passed===false?'bad':'neutral');
$('gate-status').onclick=()=>navigate('checks');
$('catalog-total').textContent=DATA.nodes.length;
setTheme(savedTheme);navigate('home');bindPins();
