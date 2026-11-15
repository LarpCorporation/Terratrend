/* Onboarding state machine and saved-evidence matching.
   Node's test runner only: no browser, DOM library, network or timers. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Tour = require('../frontend/onboarding.js');
const P = Tour.__pure;

function fakeStorage(initial) {
  const map = new Map(Object.entries(initial || {}));
  return {
    getItem(key) { return map.has(key) ? map.get(key) : null; },
    setItem(key, value) { map.set(key, String(value)); },
    removeItem(key) { map.delete(key); },
    has(key) { return map.has(key); }
  };
}

function record(overrides) {
  return Object.assign({
    id: 'result-1',
    kind: 'analysis',
    status: 'current',
    title: 'Ghana North (Savannah) · 10 m air temperature · 2016–2024',
    areas: [{ role: 'a', id: 'focus:ghana_north', name: 'Ghana North (Savannah)', level: 'preset' }],
    variables: [{ id: 'T10M', unit: '°C' }],
    window: { start: 2016, end: 2024 },
    created_at: '2026-11-15T09:30:00Z'
  }, overrides || {});
}

test('an action step cannot advance until its matching completion event arrives', () => {
  const start = P.createSession({ chapter: 'core', plan: ['pick-area', 'pick-measurement'] });
  assert.equal(P.currentLesson(start).id, 'pick-area');
  assert.equal(P.currentLesson(start).kind, 'action');
  assert.equal(P.progressOf(start).text, '1 / 2');

  assert.equal(P.canAdvance(start), false);
  assert.equal(P.reduce(start, { type: 'next' }), start, 'Next must not change an unverified action step');
  assert.equal(
    P.reduce(start, { type: 'action', detail: { action: 'area-selected', slot: 'b', id: 'country:nga' } }),
    start,
    'a different slot must not satisfy area A'
  );
  assert.equal(
    P.reduce(start, { type: 'action', detail: { action: 'measurement-checked', checked: true, count: 1 } }),
    start,
    'an unrelated action must not satisfy the step'
  );

  const advanced = P.reduce(start, {
    type: 'action',
    detail: { action: 'area-selected', slot: 'a', id: 'country:gha', name: 'Ghana', level: 'country' }
  });
  assert.notEqual(advanced, start);
  assert.equal(P.currentLesson(advanced).id, 'pick-measurement');
  assert.equal(P.progressOf(advanced).text, '2 / 2');
  assert.deepEqual(advanced.completed, ['pick-area']);
  assert.deepEqual(advanced.verified, ['pick-area']);
});

test('the App event envelope and completion matchers follow the agreed contract', () => {
  const eventLike = { type: 'terratrend:action', detail: { action: 'measurement-checked', id: 'T2M', checked: true, count: 1 } };
  assert.deepEqual(P.normalizeAction(eventLike), eventLike.detail);
  assert.deepEqual(P.normalizeAction({ action: 'navigate', screen: 'map' }), { action: 'navigate', screen: 'map' });
  for (const bad of [null, undefined, {}, { detail: 'x' }, { action: '' }, { action: 7 }]) {
    assert.equal(P.normalizeAction(bad), null);
  }

  const dates = P.lessonById('pick-dates');
  assert.equal(P.matchAction(dates, { action: 'dates-changed', start: '2016', end: '2024' }), true);
  assert.equal(P.matchAction(dates, { action: 'dates-changed', start: '2024', end: '2016' }), false);
  assert.equal(P.matchAction(dates, { action: 'dates-changed', start: '2018', end: '2024' }), false);
  assert.equal(P.matchAction(dates, { action: 'dates-changed', start: '2016-01', end: '2024-12' }), false);

  const run = P.lessonById('run-analysis');
  assert.equal(P.matchAction(run, { action: 'run-clicked', kind: 'analyze' }), true);
  assert.equal(P.matchAction(run, { action: 'run-clicked', kind: 'compare' }), true);
  assert.equal(P.matchAction(run, { action: 'run-clicked', kind: 'blocked' }), false);

  const nav = P.lessonById('open-analysis');
  assert.equal(P.matchAction(nav, { action: 'navigate', screen: 'analysis' }), true);
  assert.equal(P.matchAction(nav, { action: 'navigate', screen: 'observatory' }), true);
  assert.equal(P.matchAction(nav, { action: 'navigate', screen: 'compare' }), false);
  assert.equal(P.matchAction(nav, { action: 'navigate' }), false);

  const measurement = P.lessonById('pick-measurement');
  assert.equal(P.matchAction(measurement, { action: 'measurement-checked', checked: true, count: 1 }), true);
  assert.equal(P.matchAction(measurement, { action: 'measurement-checked', checked: false, count: 0 }), false);
});

test('skipping, exiting and restarting behave without recording a required action', () => {
  const start = P.createSession({ plan: ['pick-area', 'pick-dates'] });
  assert.equal(P.reduce(start, { type: 'skip-step' }).completed.indexOf('pick-area'), -1);

  const skipped = P.reduce(start, { type: 'skip-step' });
  assert.equal(P.currentLesson(skipped).id, 'pick-dates');
  assert.deepEqual(skipped.skipped, ['pick-area']);
  assert.deepEqual(skipped.completed, [], 'a skipped step is not complete');
  assert.deepEqual(skipped.verified, []);
  assert.equal(P.canAdvance(P.createSession({ plan: ['pick-area'] })), false);

  const dismissed = P.reduce(skipped, { type: 'skip-tour' });
  assert.equal(dismissed.active, false);
  assert.equal(dismissed.finished, true);
  assert.equal(dismissed.reason, 'skip-tour');
  assert.deepEqual(dismissed.completed, []);

  const exited = P.reduce(start, { type: 'exit' });
  assert.equal(exited.active, false);
  assert.equal(exited.reason, 'exit');
  assert.equal(exited.index, start.index, 'exiting keeps the position for a later resume');

  const completedBefore = P.createSession({ plan: ['pick-dates'], completed: ['wrap-up'] });
  const restarted = P.reduce(completedBefore, { type: 'restart' });
  assert.equal(restarted.active, true);
  assert.equal(restarted.index, 0);
  assert.deepEqual(restarted.verified, [], 'a restart requires the actions again');
  assert.deepEqual(restarted.completed, ['wrap-up'], 'restart keeps the persisted history');
});

test('Back exists only on explanatory steps and keeps earlier completions', () => {
  let session = P.createSession({ plan: ['focus-rectangles', 'wrap-up'] });
  assert.equal(P.canGoBack(session), false, 'there is no earlier step yet');
  session = P.reduce(session, { type: 'next' });
  assert.equal(P.currentLesson(session).id, 'wrap-up');
  assert.equal(P.canGoBack(session), true);
  const back = P.reduce(session, { type: 'back' });
  assert.equal(P.currentLesson(back).id, 'focus-rectangles');
  assert.ok(back.completed.indexOf('focus-rectangles') !== -1, 'going back does not erase a completion');

  let action = P.createSession({ plan: ['pick-area', 'pick-dates'] });
  action = P.reduce(action, { type: 'skip-step' });
  assert.equal(P.currentLesson(action).id, 'pick-dates');
  assert.equal(P.canGoBack(action), false, 'action steps do not offer Back');
});

test('app-verified completion only satisfies the current step', () => {
  const session = P.createSession({ plan: ['pick-area', 'pick-measurement'] });
  assert.equal(P.reduce(session, { type: 'complete-step', id: 'pick-measurement' }), session);
  const verified = P.reduce(session, { type: 'complete-step', id: 'pick-area' });
  assert.equal(P.currentLesson(verified).id, 'pick-measurement');
  assert.deepEqual(verified.completed, ['pick-area']);
  assert.equal(P.reduce(verified, { type: 'complete-step', id: '' }), verified);
});

test('progress persists, resumes and resets cleanly on a version mismatch', () => {
  const store = fakeStorage();
  const fresh = P.readProgress(store);
  assert.equal(fresh.version, 2);
  assert.deepEqual(fresh.completed, []);
  assert.equal(fresh.lastLesson, null);
  assert.equal(typeof fresh.started, 'string');

  assert.equal(P.writeProgress(store, {
    version: 2,
    completed: ['pick-area', 'pick-area', 'not-a-lesson'],
    started: '2026-01-02T03:04:05.000Z',
    lastLesson: 'pick-measurement'
  }), true);
  const loaded = P.readProgress(store);
  assert.deepEqual(loaded.completed, ['pick-area']);
  assert.equal(loaded.started, '2026-01-02T03:04:05.000Z');
  assert.equal(loaded.lastLesson, 'pick-measurement');

  const resumed = P.createSession({ chapter: 'core', resumeFrom: loaded.lastLesson, completed: loaded.completed });
  assert.equal(P.currentLesson(resumed).id, 'pick-measurement', 'resume continues at the saved lesson');
  assert.deepEqual(resumed.completed, ['pick-area']);
  const unknownResume = P.createSession({ chapter: 'core', resumeFrom: 'gone' });
  assert.equal(P.currentLesson(unknownResume).id, 'trend-vs-relationship');

  store.setItem(P.STORAGE_KEY, JSON.stringify({ version: 1, completed: ['pick-area'], started: 'old', lastLesson: 'pick-area' }));
  const reset = P.readProgress(store);
  assert.equal(reset.version, 2);
  assert.deepEqual(reset.completed, [], 'a version mismatch does not import old completions');
  assert.equal(reset.lastLesson, null);
  assert.equal(JSON.parse(store.getItem(P.STORAGE_KEY)).version, 2, 'the unusable record is rewritten as v2');

  store.setItem(P.STORAGE_KEY, 'not json');
  assert.deepEqual(P.readProgress(store).completed, []);

  // Storage may be unavailable, full or throwing: never throw.
  assert.equal(P.readProgress(null).version, 2);
  assert.equal(P.writeProgress(null, { version: 2 }), false);
  const throwing = {
    getItem() { throw new Error('private mode'); },
    setItem() { throw new Error('quota exceeded'); }
  };
  assert.equal(P.readProgress(throwing).version, 2);
  assert.equal(P.writeProgress(throwing, { version: 2 }), false);
});

test('the Welcome appears only while no versioned progress record exists', () => {
  assert.equal(P.shouldShowWelcome(null), true);
  assert.equal(P.shouldShowWelcome(''), true);
  assert.equal(P.shouldShowWelcome(undefined), true, 'no localStorage at all means a first visit');
  assert.equal(P.shouldShowWelcome(JSON.stringify({ version: 1, completed: [] })), true);
  assert.equal(P.shouldShowWelcome('{broken'), true);
  assert.equal(P.shouldShowWelcome(JSON.stringify({ version: 2, completed: [], started: 'x', lastLesson: null })), false);
  assert.equal(P.shouldShowWelcome(JSON.stringify({ version: 2, completed: ['pick-area'] })), false);
});

test('saved evidence matches exactly on measurement, area and window', () => {
  const oldWindow = record({ id: 'old-window', window: { start: 2005, end: 2024 } });
  const exact = record({ id: 'exact' });
  const otherVariable = record({ id: 'other-variable', variables: [{ id: 'T2M', unit: '°C' }] });
  const otherArea = record({ id: 'other-area', areas: [{ role: 'a', id: 'country:gha', name: 'Ghana', level: 'country' }] });
  const cancelled = record({ id: 'cancelled', status: 'cancelled' });
  const damaged = record({ id: 'damaged', status: 'damaged' });
  const comparison = record({ id: 'comparison', kind: 'compare' });
  const records = [oldWindow, exact, otherVariable, otherArea, cancelled, damaged, comparison];

  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, records).id, 'exact');
  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2005, end: 2024 }, records).id, 'old-window');
  assert.equal(
    P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2010, end: 2020 }, records),
    null,
    'a wider saved window must never be substituted for the requested one'
  );
  assert.equal(
    P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, [oldWindow]),
    null,
    '2016–2024 must not silently reuse a 2005–2024 result'
  );
  assert.equal(
    P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2005, end: 2024 }, [exact]),
    null,
    '2005–2024 must not silently reuse a 2016–2024 result'
  );
  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, [otherVariable]), null);
  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, [otherArea]), null);
  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, [cancelled]), null);
  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, [damaged]), null);
  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, [comparison]), null);

  // No measurement or no window cannot select an arbitrary record.
  for (const query of [
    { area: 'focus:ghana_north', start: 2016, end: 2024 },
    { variable: 'T10M', area: 'focus:ghana_north', end: 2024 },
    { variable: 'T10M', area: 'focus:ghana_north', start: 2024, end: 2016 },
    { variable: 'T10M', area: 'focus:ghana_north', start: 'soon', end: 2024 },
    null
  ]) {
    assert.equal(P.pickLessonEvidence(query, records), null);
  }

  // A legacy but readable record is still the same evidence; damaged/cancelled are not.
  const legacy = record({ id: 'legacy', status: 'legacy', stale_reason: 'Saved under an older method version.' });
  assert.equal(P.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }, [legacy]).id, 'legacy');
});

test('the evidence listing is a local request that fails closed', async () => {
  const notOk = await Tour.loadEvidence({ force: true, fetch: async () => ({ ok: false, json: async () => ({ results: [record()] }) }) });
  assert.deepEqual(notOk, []);
  const offline = await Tour.loadEvidence({ force: true, fetch: async () => { throw new Error('offline'); } });
  assert.deepEqual(offline, []);
  const badJson = await Tour.loadEvidence({ force: true, fetch: async () => ({ ok: true, json: async () => { throw new Error('bad json'); } }) });
  assert.deepEqual(badJson, []);
  const empty = await Tour.loadEvidence({ force: true, fetch: async () => ({ ok: true, json: async () => ({}) }) });
  assert.deepEqual(empty, []);

  let calls = 0;
  const good = await Tour.loadEvidence({
    force: true,
    fetch: async (url) => {
      calls += 1;
      assert.equal(url, '/api/results?kind=analysis&limit=50');
      return { ok: true, json: async () => ({ results: [record()], total: 1 }) };
    }
  });
  assert.equal(calls, 1);
  assert.equal(good.length, 1);
  assert.equal(Tour.pickLessonEvidence({ variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 }).id, 'result-1');

  // The loaded listing is reused; asking for evidence does not fetch again.
  const cached = await Tour.loadEvidence({ fetch: async () => { throw new Error('must not refetch'); } });
  assert.equal(cached.length, 1);

  const alternatives = P.cachedLessonsFor([record()], 'two-variables');
  assert.ok(alternatives.some(lesson => lesson.id === 'read-statistics'), 'the cached-evidence alternative is a real lesson');
  assert.ok(alternatives.every(lesson => lesson.evidence && lesson.id !== 'two-variables'));
});

test('busy loads block every advance until the app says it is finished', () => {
  let session = P.createSession({ plan: ['pick-area', 'pick-dates'] });
  session = P.reduce(session, { type: 'busy', busy: true, message: 'Loading country boundaries…' });
  assert.equal(P.canAdvance(session), false);
  assert.equal(P.canSkip(session), false);
  assert.equal(P.reduce(session, { type: 'next' }), session);
  assert.equal(P.reduce(session, { type: 'skip-step' }), session, 'skipping must not slip past the gate');
  assert.equal(
    P.reduce(session, { type: 'action', detail: { action: 'area-selected', slot: 'a', id: 'country:gha' } }),
    session,
    'an action that arrives while loading must not advance early'
  );
  assert.equal(session.busyMessage, 'Loading country boundaries…');

  const idle = P.reduce(session, { type: 'busy', busy: false });
  assert.equal(idle.busy, false);
  assert.equal(idle.busyMessage, '');
  assert.equal(P.canAdvance(idle), false, 'the action still has not happened');
  const advanced = P.reduce(idle, { type: 'action', detail: { action: 'area-selected', slot: 'a', id: 'country:gha' } });
  assert.equal(P.currentLesson(advanced).id, 'pick-dates');

  let explanation = P.createSession({ plan: ['focus-rectangles', 'wrap-up'] });
  assert.equal(P.canAdvance(explanation), true);
  explanation = P.reduce(explanation, { type: 'busy', busy: true });
  assert.equal(P.canAdvance(explanation), false, 'explanatory Next also waits for a load');
});

test('reduced motion disables the morph duration', () => {
  assert.equal(P.prefersReducedMotion((query) => ({ matches: query === '(prefers-reduced-motion: reduce)' })), true);
  assert.equal(P.prefersReducedMotion(() => ({ matches: false })), false);
  assert.equal(P.prefersReducedMotion(() => { throw new Error('no media query support'); }), false);
  assert.equal(P.motionDuration(true), 0);
  const normal = P.motionDuration(false);
  assert.ok(normal >= 220 && normal <= 320, 'the spotlight morph stays within 220–320 ms');
});

test('the lesson set covers the required topics and only agreed action events', () => {
  const lessons = Tour.lessons();
  assert.ok(lessons.length >= 20, 'core plus an optional advanced chapter');
  const allowed = new Set([
    'area-selected', 'measurement-checked', 'dates-changed', 'run-clicked',
    'analysis-complete', 'result-restored', 'navigate', 'chart-point',
    'compare-mode', 'measurement-panel', 'remote-run', 'result-saved',
    'measurement-filtered','event-selected','event-pathway-open','event-explanation-opened'
  ]);
  const ids = new Set();
  for (const lesson of lessons) {
    assert.equal(typeof lesson.id, 'string');
    assert.ok(lesson.id.length > 0);
    assert.equal(ids.has(lesson.id), false, 'duplicate lesson id ' + lesson.id);
    ids.add(lesson.id);
    assert.ok(['core', 'advanced'].includes(lesson.chapter), lesson.id + ' chapter');
    assert.ok(['explain', 'action'].includes(lesson.kind), lesson.id + ' kind');
    assert.equal(typeof lesson.title, 'string');
    if (lesson.kind === 'action') {
      assert.ok(lesson.action, lesson.id + ' needs an action contract');
      assert.ok(allowed.has(lesson.action.event), lesson.id + ' uses an unagreed event ' + lesson.action.event);
      assert.equal(typeof lesson.action.require, 'string');
      assert.ok(lesson.action.require.length > 0);
    }
  }

  for (const required of [
    'trend-vs-relationship', 'pick-area', 'geographic-levels', 'focus-rectangles',
    'draw-area', 'pick-measurement', 'pick-dates', 'saved-evidence-first',
    'run-analysis', 'open-analysis', 'read-statistics', 'compare-places',
    'relationships', 'read-saved'
  ]) {
    assert.ok(ids.has(required), 'missing core lesson ' + required);
  }
  for (const advanced of ['two-variables', 'discovery', 'local-remote', 'anomaly', 'sources-review', 'restore-saved']) {
    assert.ok(ids.has(advanced), 'missing advanced lesson ' + advanced);
    assert.equal(P.lessonById(advanced).chapter, 'advanced');
  }

  const ghana = P.lessonById('focus-rectangles');
  assert.match(ghana.body, /Ghana North \(Savannah\) is a curated focus rectangle, not the exact Ghana national boundary/i);
  assert.match(ghana.body, /not an official/i);

  // The learner is told that a matching result already exists; the copy must
  // not lecture them about caches, network transfers or data-use internals.
  const evidence = P.lessonById('saved-evidence-first');
  assert.match(evidence.body, /already exists/i);
  assert.doesNotMatch(evidence.body, /cache|computer|network|download|storage|local/i);

  const welcome = P.lessonById('trend-vs-relationship');
  assert.match(welcome.body, /trend/i);
  assert.match(welcome.body, /relationship/i);
  assert.match(welcome.body, /association/i);
  assert.match(welcome.body, /not proof/i);
});

test('every lesson anchor points at a real control or a documented container', () => {
  const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
  const htmlIds = new Set();
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) htmlIds.add(match[1]);
  // workspace.js creates this container at runtime.
  htmlIds.add('saved-results-control');
  const eventSource=fs.readFileSync(path.join(__dirname,'../frontend/events.js'),'utf8');
  for(const id of ['event-select','event-explain']){
    assert.ok(eventSource.includes(".id='"+id+"'")||eventSource.includes(".id = '"+id+"'"),'Events creates #'+id);
    htmlIds.add(id);
  }
  for (const lesson of P.LESSONS) {
    assert.ok(Array.isArray(lesson.anchor) && lesson.anchor.length > 0, lesson.id + ' needs anchors');
    for (const selector of lesson.anchor) {
      assert.equal(typeof selector, 'string');
      assert.ok(selector.length > 0);
      const idOnly = /^#([A-Za-z][\w-]*)$/.exec(selector);
      if (idOnly) {
        assert.ok(htmlIds.has(idOnly[1]), lesson.id + ' anchors to missing #' + idOnly[1]);
      } else {
        assert.match(selector, /^[.#\[]/, lesson.id + ' anchor must be a selector');
      }
    }
  }
});

test('the browser API stays available and does nothing without a document', () => {
  for (const name of [
    'start', 'stop', 'restart', 'resume', 'skipLesson', 'isActive', 'lessons',
    'completeStep', 'refresh', 'setBusy', 'openWelcome', 'openLessons',
    'maybeWelcome', 'loadEvidence', 'pickLessonEvidence'
  ]) {
    assert.equal(typeof Tour[name], 'function', name + ' must be callable');
  }
  assert.equal(Tour.STORAGE_KEY, 'terratrend-onboarding-v2');
  assert.equal(Tour.VERSION, 2);
  assert.equal(globalThis.TerraTour, Tour, 'the browser global name stays window.TerraTour');
  assert.equal(Tour.start({ chapter: 'core' }), null, 'no DOM: start is a safe no-op');
  assert.equal(Tour.isActive(), false);
  assert.equal(Tour.stop('test'), false);
  assert.equal(Tour.setBusy(true, 'loading'), false);
  assert.equal(Tour.refresh(), false);
  assert.equal(Tour.skipLesson(), false);
  assert.equal(Tour.completeStep('pick-area'), false);
  assert.equal(Tour.openWelcome(), false);
  assert.equal(Tour.openLessons(), false);
  assert.equal(Tour.maybeWelcome(), false);
});
