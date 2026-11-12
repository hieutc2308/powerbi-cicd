/* Exercise the generated browser script without changing model or report inputs. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const documentText = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...documentText.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
const payload = JSON.parse(scripts.find(s => s[1].includes('id="portal-data"'))[2]);
const script = scripts.find(s => !s[1].includes('application/json'))[2];
new vm.Script(script);

const elements = new Map();
const storage = new Map();
function element() {
    const classes = new Set();
    return {
        value: '', textContent: '', innerHTML: '', style: {}, dataset: {}, attributes: {},
        options: [], events: {}, clientWidth: 1080, clientHeight: 780, tagName: 'DIV',
        classList: {
            add: k => classes.add(k), remove: k => classes.delete(k), contains: k => classes.has(k),
            toggle(k, force) { const on = force === undefined ? !classes.has(k) : force; on ? classes.add(k) : classes.delete(k); return on; },
        },
        addEventListener(k, f) { this.events[k] = f; },
        setAttribute(k, v) { this.attributes[k] = v; },
        getAttribute(k) { return this.attributes[k]; },
        removeAttribute(k) { delete this.attributes[k]; },
        getBoundingClientRect() { return {left: 0, top: 0, width: 138, height: 91}; },
        querySelectorAll() { return []; }, querySelector() { return element(); },
        focus() {}, setPointerCapture() {},
    };
}
function get(id) {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
}
get('portal-data').textContent = JSON.stringify(payload);
const document = {
    getElementById: get, querySelectorAll: () => [], querySelector: () => null,
    body: element(), documentElement: element(), activeElement: element(), addEventListener() {},
};
const context = vm.createContext({
    document, window: {addEventListener() {}, innerWidth: 1440, innerHeight: 900},
    localStorage: {getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v)},
    requestAnimationFrame: f => f(), setTimeout: () => 0, clearTimeout() {}, Blob, URL, console,
});
vm.runInContext(script, context);
const run = code => vm.runInContext(code, context);

assert.equal(get('project-name').textContent, payload.pbipName);
assert.equal(run('allFindings.length'), payload.bpa.violations.length, 'Use canonical BPA findings, including unmatched project findings.');
if (payload.bpa.violations.some(f => f.ruleId === 'PROJECT_POLICY')) assert(run("allFindings.some(f => f.ruleId === 'PROJECT_POLICY')"));
for (const page of ['home', 'catalog', 'checks', 'model', 'lineage']) run(`navigate('${page}')`);
assert(get('page-checks').innerHTML.includes('Advisory Gate'));
run("navigate('catalog');state.catalogFolder='Missing folder';state.visualMode='decorative';");
get('catalog-kind').onchange({target: {value: 'table'}});
assert.equal(run('state.catalogFolder'), 'all');
assert.equal(run('state.visualMode'), 'all');
assert.equal(run('sortedCatalog().length'), payload.model.tables.length);
if (payload.bpa.ruleErrors.some(e => e.message === 'Evaluation failed')) assert(get('page-checks').innerHTML.includes('Evaluation failed'));
if (payload.bpa.violations.some(f => f.ruleId === 'PROJECT_POLICY')) {
    run("state.checksQuery='cache.abf';updateCheckRows()");
    assert.equal(run('filteredFindings().length'), 1);
}

run("state.all=true;renderGraph();fit()");
assert(run("visible.every(n=>['source','pq','table','measure'].includes(n.kind))"));
assert(run('visible.every(n=>Number.isFinite(layoutNodes.get(n.id).x)&&Number.isFinite(layoutNodes.get(n.id).y))'));
assert(run('Number.isFinite(scale) && Number.isFinite(tx) && Number.isFinite(ty)'));
for (const sort of ['kind', 'name', 'findings', 'downstream']) {
    run(`state.catalogSort='${sort}'`);
    const sorted = run('sortedCatalog()');
    const start = sorted.findIndex(n => n.kind === 'visual');
    if (start !== -1) assert(sorted.slice(start).every(n => n.kind === 'visual'));
}

const measure = payload.lineage.nodes.find(n => n.kind === 'measure');
if (measure) {
    context.measureId = measure.id;
    run('openCode(measureId)');
    assert.equal(run('currentCode'), measure.expression);
    assert(get('code-content').innerHTML.includes('code-source'));
    run("state.kind='measure';state.catalogFolder='Finance';state.catalogQuery='VAR x';");
    if (measure.label === 'Net amount') assert.equal(run('sortedCatalog().length'), 1, 'Search measure expressions and filter display folders.');
    run("state.catalogFolder='all';state.catalogQuery='';");
}
for (const node of payload.lineage.nodes) {
    context.testId = node.id;
    run('openDetail(testId)');
    for (const tab of ['overview', 'dependencies', 'usage', 'findings']) run(`state.detailTab='${tab}';renderDetail()`);
}
run("state.kind='all';state.catalogFolder='all';state.catalogQuery='';");
for (const direction of ['up', 'down']) {
    context.direction = direction;
    assert(run('traverse(initialObject?.id,direction).size <= DATA.nodes.length'));
}
run("navigate('model');fitModel()");
assert.equal(run('modelTables.length'), payload.model.tables.length);
assert(run('Number.isFinite(modelState.scale)'));
assert(!script.includes('setTool('));
assert(documentText.includes('white-space:pre'));
run("setTheme('dark')");
assert.equal(document.documentElement.dataset.theme, 'dark');
console.log('PASS: generated runtime, all pages, canonical BPA/gate/errors, code, catalog, graph, model, and themes.');
