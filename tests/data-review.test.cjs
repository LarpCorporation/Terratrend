const test = require('node:test');
const assert = require('node:assert/strict');
const Review = require('../frontend/data-review.js');

const catalog = {
  variables: ['T2M', 'TS', 'GWETROOT', 'WS2M'].map(id => ({ id, name: id })),
  regions: [
    { id: 'a', name: 'Area A', bbox: [-3, 5, 1, 11] },
    { id: 'b', name: 'Area B', bbox: [20, 60, 30, 70] },
  ],
};
const fields = ['T2M', 'TS', 'GWETROOT'];
const spec = extra => ({ operation: 'analyze', provider: 'nasa-merra2', region: 'a', variables: ['T2M'], start: 2005, end: 2024, ...extra });

test('automatic remote review includes only the chosen companion fields and actual planned routes',()=>{
  const c={...catalog,variables:[...catalog.variables,{id:'T10M',name:'Air temperature at 10 m'}]};
  const routes={a:{T2M:'nasa-giovanni',T10M:'nasa-giovanni'},b:{T2M:'nasa-giovanni',T10M:'nasa-giovanni'}};
  const plan=Review.estimate(spec({operation:'interconnections',provider:'auto',relationship_scope:'remote',relationship_variables:['T2M','T10M'],target_regions:['b'],routing:{routes}}),c,[...fields,'T10M']);
  assert.equal(plan.requests,4);assert.deepEqual(plan.routes,['nasa-giovanni']);assert.ok(plan.bytes<1000000);
});

test('automatic discovery review omits measurements excluded by geometry preflight',()=>{
  const c={...catalog,variables:[...catalog.variables,{id:'T10M',name:'Ten metre temperature'}]};
  const plan=Review.estimate(spec({operation:'scan',provider:'auto',variables:['T2M'],routing:{variables:['T2M'],routes:{a:{T2M:'nasa-merra2'}}}}),c,[...fields,'T10M']);
  assert.deepEqual(plan.variables,['T2M']);assert.equal(plan.requests,240);
});

test('new live sources disclose nonzero traffic and local screening does not add remote areas',()=>{
  for(const provider of ['nasa-hydrology','nasa-appeears','noaa-cdo','multi-source']){
    const plan=Review.estimate(spec({provider}),catalog,fields);
    assert.ok(plan.bytes>0,provider+' must not be represented as an offline provider');
  }
  const local=Review.estimate(spec({operation:'interconnections',relationship_variables:['T2M','TS'],relationship_scope:'local'}),catalog,fields);
  assert.deepEqual(local.variables,['T2M','TS']);assert.equal(local.areas.length,1);
});

test('Giovanni review estimates regional series rather than zero transfer or raw native grids',()=>{
  const plan=Review.estimate(spec({provider:'nasa-giovanni'}),catalog,['T2M','TS']);
  assert.equal(plan.regional,true);assert.ok(plan.bytes>0);assert.ok(plan.bytes<200000);
  assert.equal(plan.requests,1);
  const discovery=Review.estimate(spec({provider:'nasa-giovanni',operation:'scan',variables:[]}),catalog,['T2M','TS']);
  assert.deepEqual(discovery.variables,['T2M','TS']);assert.equal(discovery.requests,2);
});

test('a download estimate grows with area, period and number of measurements', () => {
  const a = Review.estimate(spec(), catalog, fields);
  const b = Review.estimate(spec({ region: 'b' }), catalog, fields);
  const longer = Review.estimate(spec({ start: 1985 }), catalog, fields);
  const multiple = Review.estimate(spec({ variables: ['T2M', 'TS'] }), catalog, fields);
  assert.equal(a.months, 240);
  assert.equal(a.requests, 240);
  assert.ok(a.bytes > 0);
  assert.ok(b.bytes > a.bytes);
  assert.equal(longer.bytes, a.bytes * 2);
  assert.equal(multiple.bytes, a.bytes * 2);
});

test('discovery estimates every supported field even with no selected variables', () => {
  const plan = Review.estimate(spec({ operation: 'scan', variables: [] }), catalog, fields);
  assert.deepEqual(plan.variables, fields);
  assert.equal(plan.requests, 720);
  assert.equal(plan.discovery, true);
});

test('A/B and geographic-layer estimates include every requested area', () => {
  const single = Review.estimate(spec(), catalog, fields);
  const b = Review.estimate(spec({ region: 'b' }), catalog, fields);
  const compare = Review.estimate(spec({ compare_region: 'b' }), catalog, fields);
  const layer = Review.estimate(spec({ operation: 'overview', features: ['a', 'b'] }), catalog, fields);
  assert.equal(compare.bytes, single.bytes + b.bytes);
  assert.equal(layer.bytes, compare.bytes);
  assert.equal(compare.areas.length, 2);
});

test('relationship review includes companion measurements and screened remote areas', () => {
  const plan = Review.estimate(spec({ operation: 'interconnections', target_regions: ['b'], target_vars: ['TS'] }), catalog, fields);
  assert.equal(plan.requests, 240 * 4);
  assert.deepEqual(plan.variables, fields);
  assert.equal(plan.areas.length, 2);
});

test('cache and imported providers require no NASA observation downloads', () => {
  for (const provider of ['project-cache', 'import:existing']) {
    const plan = Review.estimate(spec({ provider }), catalog, fields);
    assert.equal(plan.bytes, 0);
    assert.equal(plan.requests, 0);
  }
});

test('custom bounds and dateline windows can be estimated without a network request', () => {
  const custom = { type: 'Feature', id: 'custom:test', properties: { name: 'Across the date line', bbox: [179, -1, -179, 1] } };
  const plan = Review.estimate(spec({ region: custom.id, custom_areas: [custom] }), catalog, fields);
  assert.equal(plan.requests, 480);
  assert.ok(plan.bytes < 30_000_000);
});

test('missing geometry or an invalid period cannot silently approve a request', async () => {
  assert.throws(() => Review.estimate(spec({ region: 'unknown' }), catalog, fields), /area|bound/i);
  assert.throws(() => Review.estimate(spec({ start: 2024, end: 2005 }), catalog, fields), /period|year/i);
  await assert.rejects(Review.review(spec(), catalog, fields), /Reload TerraTrend/);
});

test('the review waits for Start and resolves cancellation without approving data use', async () => {
  const previousDocument = global.document, controls = new Map();
  const document = { activeElement: null, createElement: () => ({ textContent: '' }), getElementById: id => {
    if (!controls.has(id)) controls.set(id, { hidden: true, children: [], classList: { add() {}, remove() {} },
      focus() { document.activeElement = this; }, replaceChildren() { this.children = []; }, append(value) { this.children.push(value); },
      contains(value) { return [...controls.values()].includes(value); },
      querySelectorAll() { return ['data-review-close', 'data-review-cancel', 'data-review-start'].map(key => document.getElementById(key)); },
    });
    return controls.get(id);
  } };
  const trigger = { focus() { document.activeElement = this; } }; document.activeElement = trigger;
  global.document = document;
  try {
    let settled = false;
    const pending = Review.review(spec(), catalog, fields).then(value => { settled = true; return value; });
    await Promise.resolve();
    assert.equal(settled, false);
    assert.equal(document.getElementById('data-review-modal').hidden, false);
    assert.equal(document.activeElement, document.getElementById('data-review-cancel'));
    document.getElementById('data-review-start').onclick();
    assert.equal(await pending, true);
    assert.equal(document.activeElement, trigger);
    const cancelled = Review.review(spec(), catalog, fields);
    Review.cancel();
    assert.equal(await cancelled, false);
    assert.equal(document.getElementById('data-review-modal').hidden, true);
    const keyboard = Review.review(spec(), catalog, fields);
    const modal = document.getElementById('data-review-modal');
    document.getElementById('data-review-close').focus();
    modal.onkeydown({ key: 'Tab', shiftKey: true, preventDefault() {} });
    assert.equal(document.activeElement, document.getElementById('data-review-start'));
    modal.onkeydown({ key: 'Tab', shiftKey: false, preventDefault() {} });
    assert.equal(document.activeElement, document.getElementById('data-review-close'));
    modal.onkeydown({ key: 'Escape', preventDefault() {}, stopPropagation() {} });
    assert.equal(await keyboard, false);
    const backdrop = Review.review(spec(), catalog, fields);
    modal.onclick({ target: modal });
    assert.equal(await backdrop, false);
  } finally { Review.cancel(); global.document = previousDocument; }
});
