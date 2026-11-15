/* ============================================================================
   TerraTrend interactive onboarding
   ----------------------------------------------------------------------------
   A short, honest tutorial that waits for the learner to perform real actions
   in the app. It never calls app functions to perform those actions, and it
   never starts an analysis on the learner's behalf.

   Public API: window.TerraTour
     start(opts)          opts {chapter:'core'|'advanced', lesson:id, resume:bool}
     stop(reason)         clean exit, restores focus
     restart()            replay the current chapter from its first lesson
     resume()             continue from the saved position
     skipLesson()         skip only the current step (marks nothing complete)
     isActive()
     lessons()            [{id, chapter, title, kind, action?}]
     completeStep(id)     the app may call this after it verified an action
     refresh()            re-measure and reposition the spotlight
     setBusy(bool,msg)    block advancing while the app is loading
     openWelcome()        Welcome to TerraTrend dialog
     openLessons()        the lesson list (replay one lesson)
     maybeWelcome()       Welcome only when no versioned completion record exists
     loadEvidence()       GET /api/results?kind=analysis&limit=50 -> [] on failure
     pickLessonEvidence({variable, area, start, end})

   App events listened to on document:
     new CustomEvent('terratrend:action', {detail:{action, ...}})
   with action values area-selected, measurement-checked, dates-changed,
   run-clicked, analysis-complete, result-restored, navigate, chart-point,
   compare-mode, measurement-panel, remote-run, result-saved,
     measurement-filtered, selection-mode, event-selected, event-pathway-open,
   event-explanation-opened.

   Progress persists under localStorage['terratrend-onboarding-v2'] as
   {version:2, completed:[lessonId], started:ISO, lastLesson:lessonId}.
   Every storage access is wrapped: private mode simply means no memory.

   The state machine and matching helpers below are pure and exported under
   module.exports.__pure so tests/onboarding.test.cjs can run without a DOM.
   ========================================================================== */
(function (root) {
  'use strict';

  var STORAGE_KEY = 'terratrend-onboarding-v2';
  var VERSION = 2;
  var MOTION_MS = 280;
  var MOTION_QUERY = '(prefers-reduced-motion: reduce)';
  var EVIDENCE_URL = '/api/results?kind=analysis&limit=50';
  var MAX_VARS_HINT = 3;

  /* ------------------------------------------------------------------------
     Lesson data. Each lesson is one step.
     kind:'action'  -> Next is disabled until the matching app event arrives
                       (or the learner explicitly presses "Skip this step").
     kind:'explain' -> ordinary Next/Back.
     action.match(detail) receives the event's detail object.
     ---------------------------------------------------------------------- */
  var LESSONS = [
    {
      id: 'trend-vs-relationship',
      chapter: 'core',
      task: 'START HERE',
      title: 'Two different questions',
      kind: 'explain',
      screen: 'map',
      anchor: ['.brand', '.k-nav', '#help-tour'],
      body: 'A trend asks how one measurement changes over time in one place. A relationship asks whether two measurements move together — an association, not proof that one causes the other.'
    },
    {
      id: 'geographic-levels',
      chapter: 'core',
      task: 'STEP 1 · MAP LEVEL',
      title: 'Start with the map level',
      kind: 'explain',
      screen: 'map',
      anchor: ['.geography-levels', '#selection-breadcrumb', '#k-region-card'],
      body: 'Choose what kind of boundary you want first: country, region, continent. The app opens on Country, which is where most investigations begin.'
    },
    {
      id: 'pick-area',
      chapter: 'core',
      task: 'STEP 2 · YOUR REGION',
      title: 'Choose Ghana',
      kind: 'action',
      screen: 'map',
      anchor: ['#region', '#area-list-picker', '#pick-area-a'],
      nextOnAction: true,
      body: 'Pick Ghana from the list — or click it on the globe. That is the place you are investigating.',
      action: {
        event: 'area-selected',
        match: function (detail) { return detail.slot === 'a' && !!detail.id; },
        require: 'Waiting for you to select an area in the area list or on the globe.'
      }
    },
    {
      id: 'pick-measurement',
      chapter: 'core',
      task: 'STEP 3 · MEASUREMENT',
      title: 'Choose Air Temperature',
      kind: 'action',
      screen: 'map',
      anchor: ['#var-list', '#measurement-picker', '#variables-drawer'],
      nextOnAction: true,
      body: 'Check Air Temperature. You can add up to three measurements; each keeps its own unit and source.',
      action: {
        event: 'measurement-checked',
        match: function (detail) { return detail.checked !== false && Number(detail.count) >= 1; },
        require: 'Waiting for you to check a measurement in the Measurements list.'
      }
    },
    {
      id: 'pick-dates',
      chapter: 'core',
      task: 'STEP 4 · PERIOD',
      title: 'Choose the years',
      kind: 'action',
      screen: 'map',
      anchor: ['#start', '#end', '.year-row'],
      nextOnAction: true,
      body: 'Set the period you want. At least nine complete years are needed, and incomplete years are left out of the trend.',
      action: {
        event: 'dates-changed',
        match: function (detail) {
          var start = Number(detail.start);
          var end = Number(detail.end);
          return isFinite(start) && isFinite(end) && end - start >= 8;
        },
        require: 'Waiting for you to choose a From/To window of at least nine years.'
      }
    },
    {
      id: 'saved-evidence-first',
      chapter: 'core',
      task: 'BEFORE YOU RUN',
      title: 'This one is already available',
      kind: 'explain',
      screen: 'map',
      anchor: ['#run', '#run-requirement', '#variables-drawer'],
      body: 'A matching Ghana result already exists, so this run returns quickly instead of asking for new data.'
    },
    {
      id: 'run-analysis',
      chapter: 'core',
      task: 'STEP 5 · RUN',
      title: 'Press Analyze Region',
      kind: 'action',
      screen: 'map',
      anchor: ['#run', '#run-requirement', '#variables-drawer'],
      nextOnAction: true,
      body: 'Press Analyze Region. It shows what will be looked up before anything starts.',
      action: {
        event: 'run-clicked',
        match: function (detail) { return detail.kind === 'analyze' || detail.kind === 'compare'; },
        require: 'Waiting for you to press Analyze Region.'
      }
    },
    {
      id: 'open-analysis',
      chapter: 'core',
      task: 'STEP 6 · RESULT',
      title: 'Open Analysis',
      kind: 'action',
      screen: 'map',
      anchor: ['[data-kview="observatory"]', '.k-nav', '#card-analysis'],
      nextOnAction: true,
      body: 'Open Analysis. The map, the graph and the statistics all describe the same completed result.',
      action: {
        event: 'navigate',
        match: function (detail) { return detail.screen === 'analysis' || detail.screen === 'observatory'; },
        require: 'Waiting for you to open Analysis from the top navigation.'
      }
    },
    {
      id: 'read-statistics',
      chapter: 'core',
      task: 'READ IT',
      title: 'Direction, then size',
      kind: 'explain',
      screen: 'analysis',
      anchor: ['#analysis-screen', '#verdict-chip', '#signal-list', '[data-kview="observatory"]'],
      evidence: { variable: 'T10M', area: 'focus:ghana_north', start: 2016, end: 2024 },
      body: 'Check the sign and the size first, then whether the trend passed its test. “No significant trend” is not the same as missing data.'
    },
    {
      id: 'compare-places',
      chapter: 'core',
      task: 'COMPARE',
      title: 'Two places at once',
      kind: 'explain',
      screen: 'map',
      anchor: ['#add-comparison-area', '#compare-region', '#k-region-card'],
      body: 'Add a comparison area B to put a second place beside the first. The run control then reads Compare A + B.'
    },
    {
      id: 'relationships',
      chapter: 'core',
      task: 'RELATIONSHIPS',
      title: 'Look for linked measurements',
      kind: 'action',
      screen: 'map',
      anchor: ['#btn-open-interconnect', '[data-kview="interconnect"]', '#variables-drawer'],
      nextOnAction: true,
      body: 'Open Interconnections to test whether two measurements moved together. What you see is an association, not a cause.',
      action: {
        event: 'navigate',
        match: function (detail) { return detail.screen === 'interconnect'; },
        require: 'Waiting for you to open Interconnections.'
      }
    },
    {
      id: 'read-saved',
      chapter: 'core',
      task: 'SAVED RESULTS',
      title: 'Reopen an investigation',
      kind: 'explain',
      screen: 'map',
      anchor: ['#saved-open', '#completed-result-summary', '#k-region-card'],
      body: 'Open a saved investigation to put the map, the measurement and its result back exactly as it was.'
    },
    {
      id: 'wrap-up',
      chapter: 'core',
      task: 'DONE',
      title: 'That is the loop',
      kind: 'explain',
      screen: 'map',
      anchor: ['#help-tour', '.brand'],
      body: 'Choose a level, an area, a measurement and a period; then read the result. Help replays this tour or a single lesson whenever you want.'
    },
    {
      id: 'focus-rectangles',
      chapter: 'core',
      task: 'ADVANCED · AREAS',
      title: 'Curated rectangle presets',
      kind: 'explain',
      screen: 'map',
      anchor: ['#geography-presets', '.geography-levels'],
      body: 'Ghana North (Savannah) is a curated focus rectangle, not the exact Ghana national boundary. Presets are starting extents, not an official ecosystem or administrative boundary.'
    },
    {
      id: 'draw-area',
      chapter: 'core',
      task: 'ADVANCED · AREAS',
      title: 'Lasso, bounds and shapes',
      kind: 'explain',
      screen: 'map',
      anchor: ['#selection-dock', '#selection-dock-tools', '#selection-breadcrumb'],
      body: 'Draw a lasso, enter latitude/longitude bounds, or place a circle or square. Each shape stays exact for that area, A and B can use different methods.'
    },
    {
      id: 'faster-rectangles',
      chapter: 'advanced',
      task: 'TIP · FASTER DATA',
      title: 'Get data faster with a rectangle',
      kind: 'action',
      screen: 'map',
      anchor: ['#selection-dock'],
      nextOnAction: true,
      body: 'Open Selection tools here, then choose Latitude / longitude. With Automatic processing, temperature and humidity can use compact monthly summaries, reducing data transfer and local processing. Rectangular Presets work too. A rectangle includes everything inside the box; other measurements and exact country borders may need more data. For a comparison, both areas must be rectangles to use this shortcut.',
      action: {
        event: 'selection-mode',
        match: function (detail) { return detail.mode === 'bounds'; },
        require: 'Waiting for you to click Latitude / longitude in the selection toolbar.'
      }
    },
    {
      id: 'two-variables',
      chapter: 'advanced',
      task: 'ADVANCED · MEASUREMENTS',
      title: 'Two measurements, one area',
      kind: 'explain',
      screen: 'map',
      anchor: ['#var-list', '#measurement-picker'],
      body: 'Select two or three measurements to see them side by side in one area, each with its own units.'
    },
    {
      id: 'discovery',
      chapter: 'advanced',
      task: 'ADVANCED · DISCOVERY',
      title: 'Analyze with nothing selected',
      kind: 'explain',
      screen: 'map',
      anchor: ['#scan', '#variables-drawer', '#run'],
      body: 'With no measurement checked, Analyze discovers which measurements have enough data to test in area A.'
    },
    {
      id: 'local-remote',
      chapter: 'advanced',
      task: 'ADVANCED · RELATIONSHIPS',
      title: 'Local and remote links',
      kind: 'explain',
      screen: 'interconnect',
      anchor: ['#ix-remote-context', '#ix-run-remote', '.ix-search-scope'],
      body: 'Local tests stay inside area A. Remote tests compare A with the one area B you choose, and only after you ask for them.'
    },
    {
      id: 'remote-screening',
      chapter: 'advanced',
      task: 'ADVANCED · RELATIONSHIPS',
      title: 'Run a remote test',
      kind: 'explain',
      screen: 'interconnect',
      anchor: ['#ix-run-remote', '#ix-remote-context'],
      body: 'The remote action reuses the finished investigation and names the area B it will test. Nothing else is added to the request.'
    },
    {
      id: 'anomaly',
      chapter: 'advanced',
      task: 'ADVANCED · ANOMALIES',
      title: 'Months above or below the trend',
      kind: 'explain',
      screen: 'interconnect',
      anchor: ['[data-ix-tab="anomaly"]', '.ix-tabs', '#ix-screen'],
      body: 'An anomaly is a month that sat away from that measurement’s own trend. Open an episode to see the months, values and threshold behind it.'
    },
    {
      id: 'sources-review',
      chapter: 'advanced',
      task: 'ADVANCED · SOURCES',
      title: 'Where the numbers come from',
      kind: 'explain',
      screen: 'map',
      anchor: ['[data-kview="sources"]', '.k-nav', '#data-review-modal'],
      body: 'Data & Methods names the datasets, units, coverage and limits behind a result. Read the source and coverage before quoting a number.'
    },
    {
      id: 'restore-saved',
      chapter: 'advanced',
      task: 'ADVANCED · SAVED',
      title: 'Saved investigations',
      kind: 'explain',
      screen: 'map',
      anchor: ['#saved-open', '#saved-library', '#saved-results-control'],
      body: 'Saved results restore the whole investigation, including the map colours and the analysis that was already computed.'
    },
    {id:'event-story',chapter:'advanced',task:'EVENTS · CHOOSE',title:'Choose a documented event',kind:'action',screen:'events',anchor:['#event-select','#events-list'],nextOnAction:true,
      body:'Choose a story from the event menu. This opens the documented pathways without requesting observations.',
      action:{event:'event-selected',match:function(d){return !!d.eventId;},require:'Waiting for you to choose an event.'}},
    {id:'event-pathway',chapter:'advanced',task:'EVENTS · FOLLOW A PATHWAY',title:'Read what connects the measurements',kind:'action',screen:'events',anchor:['.ev-edge','#events-detail'],nextOnAction:true,
      body:'Open Documented mechanism and references on a pathway card. Gold globe lines describe the catalogue story; they are not a newly computed result.',
      action:{event:'event-pathway-open',match:function(d){return !!d.edgeId;},require:'Waiting for you to open a pathway’s mechanism and references.'}},
    {id:'event-evidence',chapter:'advanced',task:'EVENTS · EVIDENCE',title:'The story and the data check are separate',kind:'explain',screen:'events',anchor:['.event-run-controls','#events-detail'],
      body:'Check with data lets you choose dates and review every source request. Blue lines appear only for statistical links that pass the stated checks. A time lead or correlation does not prove a physical cause. This walkthrough starts no observation request.'},
    {id:'event-explanation',chapter:'advanced',task:'EVENTS · EXPLAIN',title:'Ask for the verified explanation',kind:'action',screen:'events',anchor:['#event-explain','.event-run-controls'],nextOnAction:true,
      body:'Choose Explain this event. Plain, Student and Researcher use the same evidence. If observations have not been checked, the explanation says so.',
      action:{event:'event-explanation-opened',match:function(d){return !!d.eventId;},require:'Waiting for you to open the event explanation.'}}
  ];

  var LESSON_INDEX = {};
  for (var lessonIndex = 0; lessonIndex < LESSONS.length; lessonIndex++) {
    LESSON_INDEX[LESSONS[lessonIndex].id] = LESSONS[lessonIndex];
  }

  /* ------------------------------------------------------------------------
     Pure state machine
     ---------------------------------------------------------------------- */
  function unique(values) {
    var out = [];
    for (var i = 0; i < values.length; i++) {
      if (values[i] !== undefined && values[i] !== null && out.indexOf(values[i]) === -1) out.push(values[i]);
    }
    return out;
  }

  function lessonById(id) {
    if (typeof id !== 'string' || !id) return null;
    return LESSON_INDEX[id] || null;
  }

  function lessonsForChapter(chapter) {
    var wanted = chapter === 'advanced' ? 'advanced' : 'core';
    var out = [];
    for (var i = 0; i < LESSONS.length; i++) if (LESSONS[i].chapter === wanted) out.push(LESSONS[i].id);
    return out;
  }

  function createSession(options) {
    var opts = options || {};
    var chapter = opts.chapter === 'advanced' ? 'advanced' : 'core';
    var plan;
    if (Array.isArray(opts.plan) && opts.plan.length) {
      plan = unique(opts.plan.filter(function (id) { return !!lessonById(id); }));
    }
    if (!plan || !plan.length) plan = lessonsForChapter(chapter);
    if (!plan.length) plan = lessonsForChapter('core');
    var index = 0;
    if (opts.resumeFrom) {
      var found = plan.indexOf(opts.resumeFrom);
      if (found >= 0) index = found;
    }
    var completed = [];
    if (Array.isArray(opts.completed)) {
      for (var i = 0; i < opts.completed.length; i++) {
        if (lessonById(opts.completed[i])) completed.push(opts.completed[i]);
      }
    }
    return {
      active: true,
      chapter: chapter,
      plan: plan,
      index: index,
      completed: unique(completed),
      verified: [],
      skipped: [],
      busy: false,
      busyMessage: '',
      finished: false,
      reason: null,
      lastLesson: plan[index] || null
    };
  }

  function currentLesson(session) {
    if (!session || !Array.isArray(session.plan)) return null;
    return lessonById(session.plan[session.index]) || null;
  }

  function progressOf(session) {
    if (!session || !Array.isArray(session.plan) || !session.plan.length) return { index: 0, total: 0, text: '0 / 0' };
    var total = session.plan.length;
    var index = Math.min(session.index + 1, total);
    return { index: index, total: total, text: index + ' / ' + total };
  }

  function canAdvance(session) {
    if (!session || !session.active || session.finished || session.busy) return false;
    var step = currentLesson(session);
    if (!step) return false;
    if (step.kind === 'action') return session.verified.indexOf(step.id) !== -1;
    return true;
  }

  function canSkip(session) {
    if (!session || !session.active || session.finished || session.busy) return false;
    return !!currentLesson(session);
  }

  function canGoBack(session) {
    if (!session || !session.active || session.finished || session.busy) return false;
    if (session.index <= 0) return false;
    var step = currentLesson(session);
    return !!step && step.kind === 'explain';
  }

  function jumpToIndex(session, index) {
    if (!Number.isInteger(index) || index < 0 || index >= session.plan.length) return session;
    if (index === session.index) return session;
    return Object.assign({}, session, { index: index, lastLesson: session.plan[index] });
  }

  function advance(session, kind) {
    var step = currentLesson(session);
    if (!step) return session;
    var completed = session.completed;
    var verified = session.verified;
    var skipped = session.skipped;
    if (kind === 'complete') {
      completed = unique(completed.concat([step.id]));
      verified = unique(verified.concat([step.id]));
    } else {
      skipped = unique(skipped.concat([step.id]));
    }
    var nextIndex = session.index + 1;
    if (nextIndex >= session.plan.length) {
      return Object.assign({}, session, {
        completed: completed,
        verified: verified,
        skipped: skipped,
        index: nextIndex,
        active: false,
        finished: true,
        reason: kind === 'skip' ? 'skipped' : 'complete',
        lastLesson: null
      });
    }
    return Object.assign({}, session, {
      completed: completed,
      verified: verified,
      skipped: skipped,
      index: nextIndex,
      lastLesson: session.plan[nextIndex]
    });
  }

  function endSession(session, reason) {
    if (!session) return session;
    return Object.assign({}, session, {
      active: false,
      finished: true,
      reason: reason || 'exit',
      busy: false,
      busyMessage: ''
    });
  }

  function normalizeAction(input) {
    if (!input || typeof input !== 'object') return null;
    var source = input.detail && typeof input.detail === 'object' ? input.detail : input;
    if (!source || typeof source.action !== 'string' || !source.action) return null;
    return source;
  }

  function matchAction(step, detail) {
    if (!step || !step.action || !detail) return false;
    if (detail.action !== step.action.event) return false;
    if (typeof step.action.match === 'function') {
      try { return !!step.action.match(detail); } catch (_) { return false; }
    }
    return true;
  }

  function applyAction(session, rawDetail) {
    if (!session.active || session.finished || session.busy) return session;
    var step = currentLesson(session);
    if (!step || step.kind !== 'action') return session;
    var detail = normalizeAction(rawDetail);
    if (!detail || !matchAction(step, detail)) return session;
    return advance(session, 'complete');
  }

  function reduce(session, event) {
    if (!session || !event || typeof event !== 'object') return session;
    switch (event.type) {
      case 'busy': {
        var busy = !!event.busy;
        var message = busy ? String(event.message || '') : '';
        if (session.busy === busy && session.busyMessage === message) return session;
        return Object.assign({}, session, { busy: busy, busyMessage: message });
      }
      case 'next':
        return canAdvance(session) ? advance(session, 'complete') : session;
      case 'back':
        return canGoBack(session) ? jumpToIndex(session, session.index - 1) : session;
      case 'skip-step':
      case 'skip-lesson':
        return canSkip(session) ? advance(session, 'skip') : session;
      case 'skip-tour':
        return session.active ? endSession(session, 'skip-tour') : session;
      case 'exit':
        return session.active ? endSession(session, 'exit') : session;
      case 'restart':
        return createSession({ chapter: session.chapter, plan: session.plan.slice(), completed: session.completed });
      case 'action':
        return applyAction(session, event.detail);
      case 'complete-step': {
        var id = String(event.id || '');
        if (!session.active || session.finished || session.busy) return session;
        var step = currentLesson(session);
        if (!step || step.id !== id) return session;
        return advance(session, 'complete');
      }
      case 'jump': {
        var lesson = lessonById(String(event.id || ''));
        if (!lesson) return session;
        if (session.plan.indexOf(lesson.id) === -1) {
          return createSession({ chapter: lesson.chapter, plan: [lesson.id], completed: session.completed });
        }
        return jumpToIndex(session, session.plan.indexOf(lesson.id));
      }
      default:
        return session;
    }
  }

  /* ------------------------------------------------------------------------
     Persistence. Every access is guarded: no storage simply means no memory.
     ---------------------------------------------------------------------- */
  function nowIso() {
    try { return new Date().toISOString(); } catch (_) { return ''; }
  }

  function freshProgress() {
    return { version: VERSION, completed: [], started: nowIso(), lastLesson: null };
  }

  function sanitizeProgress(raw) {
    if (!raw || typeof raw !== 'object' || raw.version !== VERSION) return freshProgress();
    var completed = [];
    if (Array.isArray(raw.completed)) {
      for (var i = 0; i < raw.completed.length; i++) {
        if (typeof raw.completed[i] === 'string' && lessonById(raw.completed[i])) completed.push(raw.completed[i]);
      }
    }
    var started = typeof raw.started === 'string' && raw.started ? raw.started : nowIso();
    var lastLesson = lessonById(raw.lastLesson) ? raw.lastLesson : null;
    return {
      version: VERSION,
      completed: unique(completed),
      started: started,
      lastLesson: lastLesson
    };
  }

  function storageOrNull() {
    // Persistence is a browser concern; outside a document there is nothing
    // to remember and no storage API to probe.
    if (typeof document === 'undefined') return null;
    try {
      var storage = root.localStorage;
      if (!storage || typeof storage.getItem !== 'function') return null;
      return storage;
    } catch (_) {
      return null;
    }
  }

  function readProgress(storage) {
    var store = storage === undefined ? storageOrNull() : storage;
    if (!store) return freshProgress();
    var raw = null;
    if (typeof store.getItem !== 'function') return freshProgress();
    try { raw = store.getItem(STORAGE_KEY); } catch (_) { return freshProgress(); }
    if (!raw) return freshProgress();
    var parsed = null;
    try { parsed = JSON.parse(raw); } catch (_) { parsed = null; }
    var clean = sanitizeProgress(parsed);
    // Rewrite unusable or older records so a version mismatch resets cleanly
    // instead of leaving a key the Welcome would keep re-reading.
    try {
      if (raw !== JSON.stringify(clean)) store.setItem(STORAGE_KEY, JSON.stringify(clean));
    } catch (_) { /* Private mode: memory is simply not durable. */ }
    return clean;
  }

  function writeProgress(storage, progress) {
    var store = storage === undefined ? storageOrNull() : storage;
    if (!store || typeof store.setItem !== 'function') return false;
    var clean = sanitizeProgress(progress);
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(clean));
      return true;
    } catch (_) {
      return false;
    }
  }

  function shouldShowWelcome(raw) {
    if (raw === undefined) {
      var store = storageOrNull();
      if (!store) return true;
      try { raw = store.getItem(STORAGE_KEY); } catch (_) { return true; }
    }
    if (raw === null || raw === undefined || raw === '') return true;
    var parsed = raw;
    if (typeof raw === 'string') {
      try { parsed = JSON.parse(raw); } catch (_) { return true; }
    }
    if (!parsed || typeof parsed !== 'object') return true;
    return parsed.version !== VERSION;
  }

  /* ------------------------------------------------------------------------
     Cached evidence: tiny local listing, never a scientific download.
     ---------------------------------------------------------------------- */
  var evidenceCache = { status: 'idle', records: [], promise: null, error: null };

  function loadEvidence(options) {
    var opts = options || {};
    if (opts.force !== true) {
      if (evidenceCache.status === 'ready') return Promise.resolve(evidenceCache.records);
      if (evidenceCache.status === 'failed' || evidenceCache.status === 'unavailable') return Promise.resolve([]);
      if (evidenceCache.promise) return evidenceCache.promise;
    }
    var impl = typeof opts.fetch === 'function' ? opts.fetch : (typeof root.fetch === 'function' ? root.fetch : null);
    if (!impl) {
      evidenceCache.status = 'unavailable';
      evidenceCache.records = [];
      return Promise.resolve([]);
    }
    var url = typeof opts.url === 'string' && opts.url ? opts.url : EVIDENCE_URL;
    evidenceCache.status = 'loading';
    evidenceCache.error = null;
    evidenceCache.promise = Promise.resolve()
      .then(function () { return impl(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' }); })
      .then(function (response) {
        if (!response || response.ok === false) throw new Error('results listing unavailable');
        if (typeof response.json !== 'function') throw new Error('results listing not JSON');
        return response.json();
      })
      .then(function (payload) {
        var list = payload && Array.isArray(payload.results) ? payload.results : [];
        evidenceCache.records = list.filter(function (record) { return record && typeof record === 'object'; });
        evidenceCache.status = 'ready';
        return evidenceCache.records;
      })
      .catch(function (error) {
        evidenceCache.error = error && error.message ? error.message : 'unavailable';
        evidenceCache.records = [];
        evidenceCache.status = 'failed';
        return [];
      })
      .then(function (records) {
        evidenceCache.promise = null;
        return records;
      });
    return evidenceCache.promise;
  }

  function toYear(value) {
    if (value === null || value === undefined || value === '') return null;
    var number = Number(value);
    if (!isFinite(number) || Math.round(number) !== number) return null;
    return number;
  }

  function idList(value) {
    if (!Array.isArray(value)) return [];
    var out = [];
    for (var i = 0; i < value.length; i++) {
      var entry = value[i];
      if (typeof entry === 'string') out.push(entry);
      else if (entry && typeof entry === 'object' && typeof entry.id === 'string') out.push(entry.id);
    }
    return out;
  }

  var EVIDENCE_OK_STATUS = ['complete', 'current', 'ok', 'saved', 'legacy', ''];

  function recordIsComplete(record) {
    var status = String(record.status === undefined || record.status === null ? '' : record.status).toLowerCase();
    return EVIDENCE_OK_STATUS.indexOf(status) !== -1;
  }

  function recordMatches(record, query) {
    if (!record || typeof record !== 'object') return false;
    if (!recordIsComplete(record)) return false;
    var kind = String(record.kind || '').toLowerCase();
    if (query.kind && kind !== String(query.kind).toLowerCase()) return false;
    if (idList(record.variables).indexOf(query.variable) === -1) return false;
    if (query.area && idList(record.areas).indexOf(query.area) === -1) return false;
    var window = record.window;
    if (!window || typeof window !== 'object') return false;
    return toYear(window.start) === query.start && toYear(window.end) === query.end;
  }

  function pickLessonEvidence(query, records) {
    if (!query || typeof query !== 'object') return null;
    var variable = typeof query.variable === 'string' ? query.variable.trim() : '';
    var start = toYear(query.start);
    var end = toYear(query.end);
    if (!variable || start === null || end === null || end < start) return null;
    var list = Array.isArray(records) ? records : evidenceCache.records;
    if (!Array.isArray(list)) return null;
    var normalized = {
      variable: variable,
      start: start,
      end: end,
      area: typeof query.area === 'string' && query.area ? query.area : null,
      kind: typeof query.kind === 'string' && query.kind ? query.kind : 'analysis'
    };
    for (var i = 0; i < list.length; i++) {
      if (recordMatches(list[i], normalized)) return list[i];
    }
    return null;
  }

  function cachedLessonsFor(records, excludeId) {
    var out = [];
    for (var i = 0; i < LESSONS.length; i++) {
      var lesson = LESSONS[i];
      if (!lesson.evidence || lesson.id === excludeId) continue;
      if (pickLessonEvidence(lesson.evidence, records)) out.push(lesson);
    }
    return out;
  }

  /* ------------------------------------------------------------------------
     Motion preference helpers (pure for tests)
     ---------------------------------------------------------------------- */
  function prefersReducedMotion(mediaQuery) {
    var media = mediaQuery;
    if (!media && typeof root.matchMedia === 'function') {
      media = function (query) { return root.matchMedia(query); };
    }
    if (typeof media !== 'function') return false;
    try { return !!media(MOTION_QUERY).matches; } catch (_) { return false; }
  }

  function motionDuration(reduced) {
    return reduced ? 0 : MOTION_MS;
  }

  /* ------------------------------------------------------------------------
     Browser layer
     ---------------------------------------------------------------------- */
  var ui = {
    layer: null, scrims: {}, ring: null, pointer: null, panel: null,
    task: null, progress: null, title: null, body: null, requirement: null,
    evidence: null, live: null, actions: null, back: null, next: null,
    skipStep: null, skipTour: null, exit: null, restart: null,
    focusTarget: null, welcome: null, lessonsModal: null, toast: null
  };
  var session = null;
  var savedFocus = null;
  var currentTarget = null;
  var currentHole = null;
  var stepToken = 0;
  var evidenceToken = 0;
  var bound = false;
  var refreshQueued = false;
  var reducedCache = null;
  var activeModal = null;
  var modalReturnFocus = null;
  var welcomeRequested = false;
  var toastTimer = 0;
  var placing = false;
  var targetObserver = null;
  var targetResize = null;
  var panelResize = null;
  var bodyObserver = null;
  var motionWatcher = null;

  function make(tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = text;
    return element;
  }

  function requestFrame(callback) {
    if (typeof root.requestAnimationFrame === 'function') root.requestAnimationFrame(callback);
    else setTimeout(callback, 16);
  }

  function reducedMotion() {
    if (reducedCache === null) reducedCache = prefersReducedMotion();
    return reducedCache;
  }

  function applyMotionPreference() {
    if (typeof document === 'undefined' || !document.documentElement) return;
    try {
      document.documentElement.classList.toggle('tt-reduced-motion', reducedMotion());
    } catch (_) { /* ignore */ }
  }

  function watchMotionPreference() {
    if (motionWatcher || typeof root.matchMedia !== 'function') return;
    try {
      var media = root.matchMedia(MOTION_QUERY);
      if (!media || typeof media.addEventListener !== 'function') return;
      motionWatcher = function (event) {
        reducedCache = !!event.matches;
        applyMotionPreference();
        if (!reducedMotion() && session && session.active) positionFor('refresh');
      };
      media.addEventListener('change', motionWatcher);
    } catch (_) { /* ignore */ }
  }

  function hasOpenAppModal() {
    if (typeof document === 'undefined') return false;
    try {
      if (document.querySelector('.modal-backdrop.open')) return true;
      var dialogs = document.querySelectorAll('dialog[open]');
      for (var i = 0; i < dialogs.length; i++) return true;
      return false;
    } catch (_) {
      return false;
    }
  }

  /* ---- panel construction ------------------------------------------------ */
  function ensureUi() {
    if (ui.panel || typeof document === 'undefined') return ui;
    if (!document.body) return ui;

    var layer = make('div', 'tt-layer');
    layer.hidden = true;
    layer.setAttribute('aria-hidden', 'true');
    var sides = ['top', 'bottom', 'left', 'right'];
    for (var i = 0; i < sides.length; i++) {
      var scrim = make('div', 'tt-scrim');
      scrim.dataset.side = sides[i];
      scrim.setAttribute('aria-hidden', 'true');
      layer.append(scrim);
      ui.scrims[sides[i]] = scrim;
    }
    ui.ring = make('div', 'tt-ring');
    ui.ring.hidden = true;
    ui.ring.setAttribute('aria-hidden', 'true');
    layer.append(ui.ring);
    ui.pointer = make('div', 'tt-pointer');
    ui.pointer.hidden = true;
    ui.pointer.setAttribute('aria-hidden', 'true');
    layer.append(ui.pointer);
    document.body.append(layer);
    ui.layer = layer;

    var panel = make('section', 'tt-panel');
    panel.hidden = true;
    panel.setAttribute('role', 'region');
    panel.setAttribute('aria-label', 'TerraTrend interactive tutorial');
    panel.setAttribute('aria-labelledby', 'tt-title');
    panel.setAttribute('aria-describedby', 'tt-body tt-requirement');

    var head = make('div', 'tt-head');
    ui.task = make('span', 'tt-task');
    ui.progress = make('span', 'tt-progress');
    ui.progress.setAttribute('aria-hidden', 'true');
    ui.restart = make('button', 'tt-icon-btn', '↻');
    ui.restart.type = 'button';
    ui.restart.dataset.tt = 'restart';
    ui.restart.title = 'Restart this chapter';
    ui.restart.setAttribute('aria-label', 'Restart this tutorial chapter');
    ui.exit = make('button', 'tt-icon-btn', '×');
    ui.exit.type = 'button';
    ui.exit.dataset.tt = 'exit';
    ui.exit.title = 'Exit the tutorial (Escape)';
    ui.exit.setAttribute('aria-label', 'Exit the tutorial');
    head.append(ui.task, ui.progress, ui.restart, ui.exit);

    ui.title = make('h2', 'tt-title');
    ui.title.id = 'tt-title';
    ui.title.tabIndex = -1;
    ui.body = make('p', 'tt-body');
    ui.body.id = 'tt-body';
    ui.requirement = make('p', 'tt-requirement');
    ui.requirement.id = 'tt-requirement';
    ui.requirement.setAttribute('role', 'status');
    ui.requirement.setAttribute('aria-live', 'polite');
    ui.requirement.hidden = true;
    ui.evidence = make('div', 'tt-evidence');
    ui.evidence.id = 'tt-evidence';
    ui.evidence.hidden = true;
    ui.live = make('p', 'tt-live');
    ui.live.setAttribute('role', 'status');
    ui.live.setAttribute('aria-live', 'polite');
    ui.live.setAttribute('aria-atomic', 'true');

    var actions = make('div', 'tt-actions');
    ui.back = make('button', 'tt-btn ghost', 'Back');
    ui.back.type = 'button';
    ui.back.dataset.tt = 'back';
    ui.next = make('button', 'tt-btn primary', 'Next');
    ui.next.type = 'button';
    ui.next.dataset.tt = 'next';
    actions.append(ui.back, ui.next);

    var secondary = make('div', 'tt-secondary');
    ui.focusTarget = make('button', 'tt-link', 'Focus the highlighted control');
    ui.focusTarget.type = 'button';
    ui.focusTarget.dataset.tt = 'focus-target';
    ui.focusTarget.hidden = true;
    ui.skipStep = make('button', 'tt-link', 'Skip this step');
    ui.skipStep.type = 'button';
    ui.skipStep.dataset.tt = 'skip-step';
    ui.skipTour = make('button', 'tt-link', 'Skip tour');
    ui.skipTour.type = 'button';
    ui.skipTour.dataset.tt = 'skip-tour';
    secondary.append(ui.focusTarget, ui.skipStep, ui.skipTour);

    panel.append(head, ui.title, ui.body, ui.requirement, ui.evidence, ui.live, actions, secondary);
    panel.addEventListener('click', onPanelClick);
    document.body.append(panel);
    ui.panel = panel;

    buildWelcome();
    buildLessonsModal();
    ui.toast = make('div', 'tt-toast');
    ui.toast.hidden = true;
    ui.toast.setAttribute('role', 'status');
    ui.toast.setAttribute('aria-live', 'polite');
    document.body.append(ui.toast);
    applyMotionPreference();
    return ui;
  }

  function onPanelClick(event) {
    var button = event.target && event.target.closest ? event.target.closest('button') : null;
    if (!button || !ui.panel.contains(button)) return;
    var action = button.dataset.tt;
    if (action === 'next') { sendNext(); return; }
    if (action === 'back') { applyEvent({ type: 'back' }); return; }
    if (action === 'skip-step') { skipLesson(); return; }
    if (action === 'skip-tour') { applyEvent({ type: 'skip-tour' }); return; }
    if (action === 'exit') { stop('exit'); return; }
    if (action === 'restart') { restart(); return; }
    if (action === 'focus-target') { focusTargetControl(); return; }
    var lessonId = button.dataset.ttLesson;
    if (lessonId) { start({ lesson: lessonId }); return; }
    var choice = button.dataset.ttChoice;
    if (choice) { handleEvidenceChoice(choice); return; }
  }

  /* ---- dialogs ----------------------------------------------------------- */
  function buildWelcome() {
    var wrapper = make('div', 'tt-modal');
    wrapper.hidden = true;
    var windowEl = make('div', 'tt-window tt-welcome');
    windowEl.setAttribute('role', 'dialog');
    windowEl.setAttribute('aria-modal', 'true');
    windowEl.setAttribute('aria-labelledby', 'tt-welcome-title');
    windowEl.setAttribute('aria-describedby', 'tt-welcome-lead');

    var kicker = make('p', 'tt-kicker', 'WELCOME · TERRATREND');
    var title = make('h2', '', 'Welcome to TerraTrend');
    title.id = 'tt-welcome-title';
    var lead = make('p', 'tt-welcome-lead',
      'Choose a place, a measurement and a period to see what has changed. Explore trends or test whether measurements move together. The interactive tour walks through a real example.');
    lead.id = 'tt-welcome-lead';
    var note = make('p', 'tt-welcome-note',
      'It waits for you to do each step yourself. Press Escape to leave at any time, or replay a lesson from HELP.');

    var speedTip = make('section', 'tt-speed-tip');
    var speedTitle = make('h3', '', 'Try a rectangle for faster data');
    speedTitle.id = 'tt-speed-title';
    speedTip.setAttribute('aria-labelledby', speedTitle.id);
    var speedBody = make('p', '', 'With Automatic processing, Latitude / longitude boxes and rectangular Presets can retrieve compact monthly temperature and humidity summaries. That can use less data and reduce local processing.');
    var speedLimit = make('p', 'tt-note', 'Other measurements may still need larger downloads. A box covers its whole extent, including places beyond country borders.');
    var speedButton = make('button', 'tt-btn ghost', 'Show the rectangle selector');
    speedButton.type = 'button';
    speedButton.dataset.ttWelcome = 'faster-rectangles';
    speedTip.append(speedTitle, speedBody, speedLimit, speedButton);

    var actionsRow = make('div', 'tt-welcome-actions');
    var startButton = make('button', 'tt-btn primary', 'Start interactive tour');
    startButton.type = 'button';
    startButton.dataset.ttWelcome = 'core';
    var exploreButton = make('button', 'tt-btn ghost', 'Explore on my own');
    exploreButton.type = 'button';
    exploreButton.dataset.ttWelcome = 'explore';
    actionsRow.append(startButton, exploreButton);

    var foot = make('p', 'tt-welcome-foot');
    var lessonsLink = make('button', 'tt-link', 'Replay a single lesson');
    lessonsLink.type = 'button';
    lessonsLink.dataset.ttWelcome = 'lessons';
    var advancedLink = make('button', 'tt-link', 'Optional advanced chapter');
    advancedLink.type = 'button';
    advancedLink.dataset.ttWelcome = 'advanced';
    foot.append(lessonsLink, advancedLink);

    windowEl.append(kicker, title, lead, speedTip, note, actionsRow, foot);
    wrapper.append(windowEl);
    wrapper.addEventListener('click', function (event) {
      if (event.target === wrapper) closeModal();
    });
    windowEl.addEventListener('click', function (event) {
      var button = event.target && event.target.closest ? event.target.closest('button[data-tt-welcome]') : null;
      if (!button) return;
      var choice = button.dataset.ttWelcome;
      if (choice === 'explore') {
        markSeen();
        closeModal();
        return;
      }
      if (choice === 'lessons') {
        closeModal();
        openLessons();
        return;
      }
      if (choice === 'advanced') {
        closeModal();
        start({ chapter: 'advanced' });
        return;
      }
      if (choice === 'faster-rectangles') {
        start({ lesson: 'faster-rectangles' });
        return;
      }
      closeModal();
      start({ chapter: 'core' });
    });
    windowEl.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeModal();
        return;
      }
      trapTab(event, windowEl);
    });
    document.body.append(wrapper);
    ui.welcome = wrapper;
  }

  function buildLessonsModal() {
    var wrapper = make('div', 'tt-modal');
    wrapper.hidden = true;
    var windowEl = make('div', 'tt-window tt-lessons-window');
    windowEl.setAttribute('role', 'dialog');
    windowEl.setAttribute('aria-modal', 'true');
    windowEl.setAttribute('aria-labelledby', 'tt-lessons-title');

    var kicker = make('p', 'tt-kicker', 'HELP · REPLAY');
    var title = make('h2', '', 'Replay a single lesson');
    title.id = 'tt-lessons-title';
    var note = make('p', 'tt-note',
      'Each lesson is short. Action lessons wait for the real app event and never mark a skipped action as completed.');
    var rectangleButton = make('button', 'tt-btn ghost', 'Show the rectangle selector for faster data');
    rectangleButton.type = 'button';
    rectangleButton.dataset.ttLesson = 'faster-rectangles';
    var body = make('div', 'tt-lessons-body');
    var foot = make('div', 'tt-window-foot');
    var resumeButton = make('button', 'tt-btn ghost', 'Resume last lesson');
    resumeButton.type = 'button';
    resumeButton.dataset.ttLessons = 'resume';
    var restartButton = make('button', 'tt-btn ghost', 'Restart the tour');
    restartButton.type = 'button';
    restartButton.dataset.ttLessons = 'restart';
    var closeButton = make('button', 'tt-btn primary', 'Close');
    closeButton.type = 'button';
    closeButton.dataset.ttLessons = 'close';
    foot.append(resumeButton, restartButton, closeButton);

    windowEl.append(kicker, title, note, rectangleButton, body, foot);
    wrapper.append(windowEl);
    wrapper.addEventListener('click', function (event) {
      if (event.target === wrapper) closeModal();
    });
    windowEl.addEventListener('click', function (event) {
      var button = event.target && event.target.closest ? event.target.closest('button') : null;
      if (!button) return;
      if (button.dataset.ttLesson) {
        closeModal();
        start({ lesson: button.dataset.ttLesson });
        return;
      }
      var choice = button.dataset.ttLessons;
      if (choice === 'resume') {
        closeModal();
        resume();
      } else if (choice === 'restart') {
        closeModal();
        restart();
      } else if (choice === 'close') {
        closeModal();
      }
    });
    windowEl.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeModal();
        return;
      }
      trapTab(event, windowEl);
    });
    document.body.append(wrapper);
    ui.lessonsModal = wrapper;
  }

  function trapTab(event, container) {
    if (event.key !== 'Tab') return;
    var focusables = [];
    var candidates = container.querySelectorAll('button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])');
    for (var i = 0; i < candidates.length; i++) {
      var candidate = candidates[i];
      if (candidate.disabled) continue;
      if (candidate.hidden) continue;
      focusables.push(candidate);
    }
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function openModalElement(element) {
    if (!element) return;
    element.hidden = false;
    var focusable = element.querySelector('button:not([disabled])');
    if (focusable) {
      try { focusable.focus({ preventScroll: true }); } catch (_) { focusable.focus(); }
    }
  }

  function closeModal() {
    if (!activeModal) return;
    activeModal = null;
    if (ui.welcome) ui.welcome.hidden = true;
    if (ui.lessonsModal) ui.lessonsModal.hidden = true;
    var returnTo = modalReturnFocus;
    modalReturnFocus = null;
    if (returnTo && typeof returnTo.focus === 'function' && document.contains(returnTo)) {
      try { returnTo.focus({ preventScroll: true }); } catch (_) { /* ignore */ }
    }
  }

  function openWelcome() {
    if (typeof document === 'undefined' || !document.body) return false;
    if (hasOpenAppModal()) {
      welcomeRequested = false;
      return false;
    }
    stop('welcome');
    closeModal();
    ensureUi();
    modalReturnFocus = document.activeElement;
    activeModal = 'welcome';
    openModalElement(ui.welcome);
    return true;
  }

  function markSeen() {
    var saved = readProgress();
    writeProgress(undefined, {
      version: VERSION,
      completed: saved.completed,
      started: saved.started,
      lastLesson: saved.lastLesson
    });
  }

  function waitForClearModals(callback) {
    var tries = 0;
    var check = function () {
      if (isActive() || activeModal) return;
      if (!hasOpenAppModal()) { callback(); return; }
      tries += 1;
      if (tries > 60) return; // ~18 s; HELP can still open the tour afterwards
      setTimeout(check, 300);
    };
    setTimeout(check, 350);
  }

  function maybeWelcome() {
    if (typeof document === 'undefined') return false;
    if (welcomeRequested || isActive() || activeModal) return false;
    if (!shouldShowWelcome(undefined)) return false;
    welcomeRequested = true;
    waitForClearModals(function () {
      if (isActive() || activeModal) return;
      if (!shouldShowWelcome(undefined)) return;
      openWelcome();
    });
    return true;
  }

  function openLessons() {
    if (typeof document === 'undefined' || !document.body) return false;
    stop('lessons');
    closeModal();
    ensureUi();
    var saved = readProgress();
    var body = ui.lessonsModal.querySelector('.tt-lessons-body');
    if (!body) return false;
    body.replaceChildren();
    body.append(makeLessonGroup('core', saved.completed));
    body.append(makeLessonGroup('advanced', saved.completed));
    var resumeButton = ui.lessonsModal.querySelector('[data-tt-lessons="resume"]');
    if (resumeButton) {
      resumeButton.disabled = !saved.lastLesson;
      resumeButton.title = saved.lastLesson ? 'Continue from ' + saved.lastLesson : 'No saved tutorial position yet';
    }
    modalReturnFocus = document.activeElement;
    activeModal = 'lessons';
    openModalElement(ui.lessonsModal);
    return true;
  }

  function makeLessonGroup(chapter, completed) {
    var group = make('section', 'tt-lesson-group');
    group.append(make('h3', 'tt-lesson-group-title', chapter === 'advanced' ? 'Optional advanced chapter' : 'Core lessons'));
    var list = make('ul', 'tt-lessons');
    for (var i = 0; i < LESSONS.length; i++) {
      var lesson = LESSONS[i];
      if (lesson.chapter !== chapter) continue;
      var item = make('li', 'tt-lesson');
      var info = make('div', 'tt-lesson-info');
      info.append(make('p', 'tt-lesson-title', lesson.title));
      var meta = lesson.kind === 'action' ? 'Action · ' + (lesson.action && lesson.action.require ? lesson.action.require : 'Waits for the real action') : 'Explanation';
      if (lesson.evidence) meta += ' · saved local evidence';
      info.append(make('p', 'tt-lesson-meta', meta));
      var done = completed.indexOf(lesson.id) !== -1;
      var status = make('span', 'tt-lesson-status', done ? 'DONE' : 'NOT YET');
      if (done) status.classList.add('done');
      var button = make('button', 'tt-btn ghost', 'Replay');
      button.type = 'button';
      button.dataset.ttLesson = lesson.id;
      button.setAttribute('aria-label', 'Replay lesson: ' + lesson.title);
      item.append(info, status, button);
      list.append(item);
    }
    group.append(list);
    return group;
  }

  function showToast(message) {
    if (!ui.toast) return;
    ui.toast.textContent = message;
    ui.toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      if (ui.toast) ui.toast.hidden = true;
    }, 6500);
  }

  /* ---- session lifecycle -------------------------------------------------- */
  function persistSession() {
    var saved = readProgress();
    var completed = saved.completed;
    var last = saved.lastLesson;
    var started = saved.started || nowIso();
    if (session) {
      for (var i = 0; i < session.completed.length; i++) {
        if (completed.indexOf(session.completed[i]) === -1) completed.push(session.completed[i]);
      }
      var step = currentLesson(session);
      if (session.finished && session.reason === 'complete') last = null;
      else if (session.active) last = step ? step.id : last;
      else last = session.lastLesson || (step ? step.id : last);
    }
    writeProgress(undefined, {
      version: VERSION,
      completed: completed,
      started: started,
      lastLesson: last
    });
  }

  function restoreSavedFocus() {
    var target = savedFocus;
    savedFocus = null;
    if (!target || typeof target.focus !== 'function') return;
    try {
      if (document.contains(target)) target.focus({ preventScroll: true });
    } catch (_) {
      try { target.focus(); } catch (__) { /* ignore */ }
    }
  }

  function dispatchEnd(reason) {
    try {
      if (typeof CustomEvent !== 'function') return;
      document.dispatchEvent(new CustomEvent('terratrend:tour-end', { detail: { reason: reason || 'exit' } }));
    } catch (_) { /* ignore */ }
  }

  function hideUi() {
    if (ui.panel) {
      ui.panel.hidden = true;
      ui.panel.style.opacity = '';
    }
    if (ui.layer) {
      ui.layer.hidden = true;
      ui.layer.style.opacity = '';
      delete ui.layer.dataset.shown;
    }
    if (ui.ring) ui.ring.hidden = true;
    if (ui.pointer) ui.pointer.hidden = true;
    currentTarget = null;
    currentHole = null;
    stepToken += 1;
    evidenceToken += 1;
    disconnectObservers();
  }

  function finishRun() {
    var reason = session ? session.reason : 'exit';
    hideUi();
    persistSession();
    restoreSavedFocus();
    if (reason === 'complete') showToast('Tutorial complete. Replay any lesson from HELP.');
    else if (reason === 'skipped') showToast('Lesson skipped. Replay any lesson from HELP.');
    dispatchEnd(reason);
  }

  function start(options) {
    if (typeof document === 'undefined' || !document.body) return null;
    var opts = options || {};
    var lesson = opts.lesson ? lessonById(String(opts.lesson)) : null;
    if (opts.lesson && !lesson) return start({ chapter: opts.chapter === 'advanced' ? 'advanced' : 'core' });
    var saved = readProgress();
    var chapter = lesson ? lesson.chapter : (opts.chapter === 'advanced' ? 'advanced' : 'core');
    var nextSession;
    if (lesson) {
      nextSession = createSession({ chapter: lesson.chapter, plan: [lesson.id], completed: saved.completed });
    } else if (opts.resume) {
      nextSession = createSession({ chapter: chapter, resumeFrom: saved.lastLesson, completed: saved.completed });
    } else {
      nextSession = createSession({ chapter: chapter, plan:opts.plan, completed: saved.completed });
    }
    var previousFocus = (activeModal && modalReturnFocus) || document.activeElement;
    closeModal();
    if (!session || !session.active) {
      savedFocus = previousFocus && previousFocus !== document.body ? previousFocus : null;
    }
    session = nextSession;
    currentTarget = null;
    currentHole = null;
    connectGlobalHandlers();
    watchMotionPreference();
    applyMotionPreference();
    ensureUi();
    ui.layer.hidden = false;
    ui.layer.style.opacity = '';
    ui.panel.hidden = false;
    ui.panel.style.opacity = '';
    delete ui.layer.dataset.shown;
    showStep(true);
    return session;
  }

  function stop(reason) {
    if (!session) {
      hideUi();
      closeModal();
      return false;
    }
    var wasActive = session.active;
    session = endSession(session, reason || 'exit');
    persistSession();
    hideUi();
    restoreSavedFocus();
    if (wasActive) dispatchEnd(reason || 'exit');
    return true;
  }

  function restart() {
    var chapter = session ? session.chapter : 'core';
    return start({ chapter: chapter });
  }

  function resume() {
    var saved = readProgress();
    var lesson = saved.lastLesson ? lessonById(saved.lastLesson) : null;
    return start({ chapter: lesson ? lesson.chapter : 'core', resume: true });
  }

  function skipLesson() {
    if (!session || !session.active) return false;
    return applyEvent({ type: 'skip-step' });
  }

  function completeStep(id) {
    if (!session || !session.active) return false;
    return applyEvent({ type: 'complete-step', id: String(id || '') });
  }

  function isActive() {
    return !!(session && session.active);
  }

  function listLessons() {
    var out = [];
    for (var i = 0; i < LESSONS.length; i++) {
      var lesson = LESSONS[i];
      var copy = { id: lesson.id, chapter: lesson.chapter, title: lesson.title, kind: lesson.kind };
      if (lesson.action) copy.action = { event: lesson.action.event, require: lesson.action.require || '' };
      if (lesson.evidence) copy.evidence = {
        variable: lesson.evidence.variable,
        area: lesson.evidence.area,
        start: lesson.evidence.start,
        end: lesson.evidence.end
      };
      out.push(copy);
    }
    return out;
  }

  function setBusy(busy, message) {
    if (!session || !session.active) return false;
    return applyEvent({ type: 'busy', busy: !!busy, message: message || '' });
  }

  function refresh() {
    if (!session || !session.active) return false;
    var step = currentLesson(session);
    currentTarget = step ? resolveTarget(step) : null;
    positionFor('step');
    watchTarget();
    return true;
  }

  /* ---- event plumbing ----------------------------------------------------- */
  function applyEvent(event) {
    if (!session) return false;
    var before = session;
    var next = reduce(session, event);
    if (next === before) return false;
    var moved = next.index !== before.index || next.active !== before.active;
    session = next;
    persistSession();
    if (!session.active) {
      finishRun();
      return true;
    }
    if (moved) showStep(false);
    else {
      renderPanel();
      positionFor('refresh');
    }
    return true;
  }

  function sendNext() {
    if (!session) return;
    if (!canAdvance(session)) {
      announceRequirement();
      return;
    }
    applyEvent({ type: 'next' });
  }

  function announceRequirement() {
    if (!ui.live || !session) return;
    var step = currentLesson(session);
    if (session.busy) ui.live.textContent = 'Waiting for TerraTrend to finish loading.';
    else if (step && step.action) ui.live.textContent = step.action.require || 'Complete the highlighted action to continue.';
  }

  function onActionEvent(event) {
    if (!session || !session.active) return;
    var detail = normalizeAction(event);
    if (!detail) return;
    if (detail.action === 'navigate') refreshSoon();
    var step = currentLesson(session);
    if (!step || step.kind !== 'action') return;
    var before = session;
    var next = reduce(session, { type: 'action', detail: detail });
    if (next === before) return;
    session = next;
    persistSession();
    if (session.active) showStep(false);
    else finishRun();
  }

  function onDocumentKeydown(event) {
    if (event.key !== 'Escape') return;
    if (activeModal) {
      event.stopPropagation();
      closeModal();
      return;
    }
    if (!session || !session.active) return;
    if (hasOpenAppModal()) return; // the app modal owns its own Escape
    event.stopPropagation();
    stop('escape');
  }

  function onViewportChange() {
    refreshSoon();
  }

  function refreshSoon() {
    if (refreshQueued) return;
    refreshQueued = true;
    requestFrame(function () {
      refreshQueued = false;
      if (!session || !session.active) return;
      if (!ui.panel || ui.panel.hidden) return;
      positionFor('refresh');
    });
  }

  function connectGlobalHandlers() {
    if (bound || typeof document === 'undefined') return;
    bound = true;
    try {
      document.addEventListener('scroll', onViewportChange, true);
      root.addEventListener('resize', onViewportChange);
      root.addEventListener('orientationchange', onViewportChange);
      if (root.visualViewport) {
        root.visualViewport.addEventListener('resize', onViewportChange);
        root.visualViewport.addEventListener('scroll', onViewportChange);
      }
      document.addEventListener('keydown', onDocumentKeydown);
      document.addEventListener('terratrend:action', onActionEvent);
      if (typeof root.MutationObserver === 'function' && document.body) {
        bodyObserver = new root.MutationObserver(refreshSoon);
        bodyObserver.observe(document.body, { attributes: true, attributeFilter: ['data-screen'] });
      }
    } catch (_) { /* ignore */ }
  }

  /* ---- step rendering ----------------------------------------------------- */
  function showStep(first) {
    if (!session || !session.active) { hideUi(); return; }
    var step = currentLesson(session);
    if (!step) { finishRun(); return; }
    stepToken += 1;
    // Replaying this tip from another page only opens Map; the learner still
    // chooses the selector and enters every boundary themselves.
    if (step.id === 'faster-rectangles' && typeof root.showInvestigationScreen === 'function') root.showInvestigationScreen('map');
    if (step.screen && (step.kind !== 'action' || step.id.indexOf('event-')===0)) announceScreen(step);
    currentTarget = resolveTarget(step);
    currentHole = null;
    ensureUi();
    ui.layer.hidden = false;
    ui.panel.hidden = false;
    renderPanel();
    loadStepEvidence(step, stepToken);
    positionFor(first ? 'first' : 'step');
    watchTarget();
    if (first) focusPanelTitle();
    announceStep(step);
    persistSession();
  }

  function announceScreen(step) {
    try {
      var current = document.body ? document.body.dataset.screen : '';
      if (current === step.screen) return;
      if (typeof CustomEvent !== 'function') return;
      document.dispatchEvent(new CustomEvent('terratrend:tour-navigate', {
        detail: { screen: step.screen, lessonId: step.id }
      }));
    } catch (_) { /* ignore */ }
  }

  function focusPanelTitle() {
    if (!ui.title) return;
    try { ui.title.focus({ preventScroll: true }); } catch (_) { /* ignore */ }
  }

  function announceStep(step) {
    if (!ui.live) return;
    var progress = progressOf(session);
    var text = 'Step ' + progress.index + ' of ' + progress.total + '. ' + step.title + '.';
    if (step.kind === 'action') text += ' ' + (step.action && step.action.require ? step.action.require : 'This step needs a real action.');
    else text += ' ' + step.body;
    ui.live.textContent = text;
  }

  function renderPanel() {
    ensureUi();
    if (!session) { hideUi(); return; }
    var step = currentLesson(session);
    var progress = progressOf(session);
    if (step) {
      ui.task.textContent = (step.chapter === 'advanced' ? 'ADVANCED · ' : '') + (step.task || 'TUTORIAL');
      ui.title.textContent = step.title || '';
      ui.body.textContent = step.body || '';
    }
    ui.progress.textContent = progress.text;
    ui.progress.setAttribute('aria-label', 'Step ' + progress.index + ' of ' + progress.total);
    var busy = !!session.busy;
    var actionStep = !!step && step.kind === 'action';
    var last = progress.index === progress.total;
    ui.next.textContent = last ? 'Done' : 'Next';
    ui.next.disabled = !canAdvance(session);
    ui.back.hidden = !step || actionStep;
    ui.back.disabled = !canGoBack(session);
    ui.skipStep.disabled = !canSkip(session);
    ui.skipTour.disabled = false;
    if (ui.focusTarget) ui.focusTarget.hidden = !currentTarget;
    if (busy) {
      ui.requirement.hidden = false;
      ui.requirement.classList.add('tt-waiting');
      ui.requirement.textContent = 'Waiting for TerraTrend to finish' +
        (session.busyMessage ? ': ' + session.busyMessage : '.') +
        ' The next step stays locked until loading completes.';
    } else if (actionStep && session.verified.indexOf(step.id) === -1) {
      ui.requirement.hidden = false;
      ui.requirement.classList.remove('tt-waiting');
      ui.requirement.textContent = step.action && step.action.require
        ? step.action.require
        : 'Complete the highlighted action to continue.';
    } else {
      ui.requirement.hidden = true;
      ui.requirement.classList.remove('tt-waiting');
      ui.requirement.textContent = '';
    }
  }

  function focusTargetControl() {
    var target = currentTarget;
    if (!target) {
      if (ui.live) ui.live.textContent = 'No highlighted control is available for this step.';
      return;
    }
    var focusable = null;
    if (target.matches && target.matches('a, button, input, select, textarea, summary, details, [tabindex]')) focusable = target;
    if (!focusable && typeof target.querySelector === 'function') {
      focusable = target.querySelector('a, button, input, select, textarea, summary, [tabindex]');
    }
    var node = focusable || target;
    if (!focusable && !node.hasAttribute('tabindex')) node.setAttribute('tabindex', '-1');
    try { node.focus({ preventScroll: false }); } catch (_) { try { node.focus(); } catch (__) { /* ignore */ } }
  }

  /* ---- saved evidence ----------------------------------------------------- */
  function loadStepEvidence(step, token) {
    if (!ui.evidence) return;
    ui.evidence.replaceChildren();
    ui.evidence.hidden = true;
    evidenceToken = token;
    if (!step.evidence) return;
    ui.evidence.hidden = false;
    ui.evidence.append(make('p', 'tt-evidence-note', 'Checking for saved evidence on this computer…'));
    loadEvidence().then(function (records) {
      if (token !== stepToken || !session || !session.active) return;
      var current = currentLesson(session);
      if (!current || current.id !== step.id) return;
      var record = pickLessonEvidence(step.evidence, records);
      if (record) renderEvidenceFound(step.evidence, record);
      else renderEvidenceMissing(step);
      if (currentHole) placePanel(currentHole);
    });
  }

  function requestDescription(request) {
    var label = request.label || request.variable;
    var area = request.areaLabel ? request.areaLabel : request.area;
    return label + ' · ' + area + ' · ' + request.start + '–' + request.end;
  }

  function renderEvidenceFound(request, record) {
    if (!ui.evidence) return;
    var box = ui.evidence;
    box.replaceChildren();
    box.append(make('span', 'tt-chip', 'LOCAL SAVED EVIDENCE'));
    box.append(make('p', 'tt-evidence-title', record.title || requestDescription(request)));
    var meta = [];
    if (request.label) meta.push(request.label);
    if (record.window) meta.push(record.window.start + '–' + record.window.end);
    if (record.kind) meta.push(String(record.kind));
    if (record.status) meta.push(String(record.status));
    if (record.created_at) meta.push(String(record.created_at).slice(0, 10));
    if (meta.length) box.append(make('p', 'tt-evidence-meta', meta.join(' · ')));
    box.append(make('p', 'tt-evidence-note', 'This lesson reads evidence already saved on this computer. It does not fetch new observations and it is not a new finding.'));
    if (record.status === 'legacy' && record.stale_reason) {
      box.append(make('p', 'tt-evidence-note', 'Saved under an older method version: ' + record.stale_reason));
    }
  }

  function renderEvidenceMissing(step) {
    if (!ui.evidence) return;
    var request = step.evidence;
    var box = ui.evidence;
    box.replaceChildren();
    box.append(make('span', 'tt-chip', 'NO MATCHING SAVED EVIDENCE'));
    box.append(make('p', 'tt-evidence-title', requestDescription(request)));
    box.append(make('p', 'tt-evidence-note',
      'No saved local result matches this measurement and window exactly, so this lesson will not show numbers it does not have. Nothing has been downloaded, and this limited saved-evidence lesson has not scanned all live variables.'));
    var options = make('div', 'tt-evidence-options');
    options.append(evidenceChoice('cached', 'Use another cached lesson'));
    options.append(evidenceChoice('preview', 'Continue without data'));
    options.append(evidenceChoice('live', 'Request live data (needs your confirmation)'));
    box.append(options);
  }

  function evidenceChoice(value, label) {
    var button = make('button', 'tt-btn ghost', label);
    button.type = 'button';
    button.dataset.ttChoice = value;
    return button;
  }

  function handleEvidenceChoice(choice) {
    if (!session || !session.active || !ui.evidence) return;
    var step = currentLesson(session);
    if (choice === 'preview') {
      ui.evidence.replaceChildren();
      ui.evidence.append(make('span', 'tt-chip', 'EXPLANATORY PREVIEW'));
      ui.evidence.append(make('p', 'tt-evidence-note', 'This lesson explains what to look for, without data. No request was made.'));
      if (currentHole) placePanel(currentHole);
      return;
    }
    if (choice === 'cached') {
      loadEvidence().then(function (records) {
        if (!session || !session.active) return;
        var alternatives = cachedLessonsFor(records, step.id);
        ui.evidence.replaceChildren();
        ui.evidence.append(make('span', 'tt-chip', 'CACHED LESSONS'));
        if (!alternatives.length) {
          ui.evidence.append(make('p', 'tt-evidence-note',
            'No other lesson has a matching saved result on this computer. You can continue without data, or run your own live request from the investigation panel.'));
          var again = make('div', 'tt-evidence-options');
          again.append(evidenceChoice('preview', 'Continue without data'));
          ui.evidence.append(again);
        } else {
          ui.evidence.append(make('p', 'tt-evidence-note', 'These lessons have genuinely matching saved evidence:'));
          var list = make('div', 'tt-evidence-options');
          for (var i = 0; i < alternatives.length; i++) {
            var button = make('button', 'tt-btn ghost', 'Replay: ' + alternatives[i].title);
            button.type = 'button';
            button.dataset.ttLesson = alternatives[i].id;
            list.append(button);
          }
          ui.evidence.append(list);
        }
        if (currentHole) placePanel(currentHole);
      });
      return;
    }
    if (choice === 'live') {
      var request = step.evidence;
      ui.evidence.replaceChildren();
      ui.evidence.append(make('span', 'tt-chip', 'LIVE REQUEST · YOUR CONFIRMATION'));
      ui.evidence.append(make('p', 'tt-evidence-title', requestDescription(request)));
      ui.evidence.append(make('p', 'tt-evidence-note',
        'A live request would ask NASA services for this measurement, area and window. TerraTrend always shows its own data-use review first, and nothing is sent until you confirm it there. The tutorial never starts this request for you and will not fill in your selections.'));
      var actions = make('div', 'tt-evidence-options');
      var locate = evidenceChoice('locate-live', 'Show me where to run it');
      var cancel = evidenceChoice('cancel-live', 'Cancel');
      actions.append(locate, cancel);
      ui.evidence.append(actions);
      if (currentHole) placePanel(currentHole);
      return;
    }
    if (choice === 'cancel-live') {
      renderEvidenceMissing(step);
      if (currentHole) placePanel(currentHole);
      return;
    }
    if (choice === 'locate-live') {
      var evidence = step.evidence;
      try {
        if (typeof CustomEvent === 'function') {
          document.dispatchEvent(new CustomEvent('terratrend:tour-live-request', {
            detail: {
              variable: evidence.variable,
              area: evidence.area,
              start: evidence.start,
              end: evidence.end
            }
          }));
        }
      } catch (_) { /* ignore */ }
      ui.evidence.replaceChildren();
      ui.evidence.append(make('span', 'tt-chip', 'YOU RUN THIS REQUEST'));
      ui.evidence.append(make('p', 'tt-evidence-note',
        'Nothing is filled in for you. Open Map, choose ' + (evidence.label || evidence.variable) +
        ' in Measurements, area ' + (evidence.areaLabel || evidence.area) +
        ' and ' + evidence.start + '–' + evidence.end +
        ', then press Analyze and confirm the data-use review. You can also skip this step and keep using saved evidence.'));
      if (currentHole) placePanel(currentHole);
    }
  }

  /* ---- target resolution -------------------------------------------------- */
  function resolveTarget(step) {
    if (!step || typeof document === 'undefined') return null;
    var selectors = Array.isArray(step.anchor) ? step.anchor : [step.anchor];
    for (var i = 0; i < selectors.length; i++) {
      var selector = selectors[i];
      if (!selector) continue;
      var element = null;
      try { element = document.querySelector(selector); } catch (_) { element = null; }
      if (!element || !element.isConnected) continue;
      openDetailsFor(element);
      if (isVisible(element)) return element;
    }
    return null;
  }

  function openDetailsFor(element) {
    try {
      var details = element.closest ? element.closest('details') : null;
      if (details && !details.open) details.open = true;
    } catch (_) { /* ignore */ }
  }

  function isVisible(element) {
    if (!element || !element.isConnected) return false;
    var rect = null;
    try { rect = element.getBoundingClientRect(); } catch (_) { return false; }
    if (!rect) return false;
    if (rect.width < 1 && rect.height < 1) return false;
    try {
      var style = root.getComputedStyle ? root.getComputedStyle(element) : null;
      if (style && (style.display === 'none' || style.visibility === 'hidden')) return false;
    } catch (_) { /* ignore */ }
    return true;
  }

  /* ---- geometry and spotlight -------------------------------------------- */
  function viewportBox() {
    var vv = root.visualViewport;
    if (vv && vv.width && vv.height) {
      return { left: vv.offsetLeft || 0, top: vv.offsetTop || 0, width: vv.width, height: vv.height };
    }
    var doc = document.documentElement || document.body;
    return {
      left: 0,
      top: 0,
      width: (doc && doc.clientWidth) || root.innerWidth || 320,
      height: (doc && doc.clientHeight) || root.innerHeight || 480
    };
  }

  function rectFor(element) {
    if (!element) return null;
    var rect = null;
    try { rect = element.getBoundingClientRect(); } catch (_) { return null; }
    if (!rect || (!rect.width && !rect.height)) return null;
    var view = viewportBox();
    var left = Math.max(view.left + 2, Math.min(rect.left, view.left + view.width - 2));
    var top = Math.max(view.top + 2, Math.min(rect.top, view.top + view.height - 2));
    var right = Math.min(view.left + view.width - 2, Math.max(left, rect.right));
    var bottom = Math.min(view.top + view.height - 2, Math.max(top, rect.bottom));
    return { left: left, top: top, right: right, bottom: bottom, width: Math.max(1, right - left), height: Math.max(1, bottom - top) };
  }

  function expandRect(rect, padding) {
    var view = viewportBox();
    var left = Math.max(view.left, rect.left - padding);
    var top = Math.max(view.top, rect.top - padding);
    var right = Math.min(view.left + view.width, rect.right + padding);
    var bottom = Math.min(view.top + view.height, rect.bottom + padding);
    return { left: left, top: top, right: right, bottom: bottom, width: Math.max(1, right - left), height: Math.max(1, bottom - top) };
  }

  function wideHole() {
    var view = viewportBox();
    var width = Math.min(view.width * 0.62, 760);
    var height = Math.min(view.height * 0.58, 540);
    var left = view.left + (view.width - width) / 2;
    var top = view.top + (view.height - height) / 2;
    return { left: left, top: top, right: left + width, bottom: top + height, width: width, height: height };
  }

  function scrollTargetIntoView(element) {
    var rect = null;
    try { rect = element.getBoundingClientRect(); } catch (_) { return; }
    if (!rect) return;
    var view = viewportBox();
    var margin = 28;
    var inside = rect.top >= view.top + margin &&
      rect.bottom <= view.top + view.height - margin &&
      rect.left >= view.left + margin &&
      rect.right <= view.left + view.width - margin;
    if (inside) return;
    try {
      element.scrollIntoView({ block: 'center', inline: 'center', behavior: 'auto' });
    } catch (_) {
      try { element.scrollIntoView(); } catch (__) { /* ignore */ }
    }
  }

  function setHole(hole) {
    var view = viewportBox();
    var top = ui.scrims.top;
    var bottom = ui.scrims.bottom;
    var left = ui.scrims.left;
    var right = ui.scrims.right;
    if (!top || !bottom || !left || !right) return;
    var topHeight = Math.max(0, hole.top - view.top);
    var bottomTop = Math.min(view.top + view.height, hole.bottom);
    var leftWidth = Math.max(0, hole.left - view.left);
    var rightLeft = Math.min(view.left + view.width, hole.right);
    top.style.left = Math.round(view.left) + 'px';
    top.style.top = Math.round(view.top) + 'px';
    top.style.width = Math.round(view.width) + 'px';
    top.style.height = Math.round(topHeight) + 'px';
    bottom.style.left = Math.round(view.left) + 'px';
    bottom.style.top = Math.round(bottomTop) + 'px';
    bottom.style.width = Math.round(view.width) + 'px';
    bottom.style.height = Math.round(Math.max(0, view.top + view.height - bottomTop)) + 'px';
    left.style.left = Math.round(view.left) + 'px';
    left.style.top = Math.round(hole.top) + 'px';
    left.style.width = Math.round(leftWidth) + 'px';
    left.style.height = Math.round(hole.height) + 'px';
    right.style.left = Math.round(rightLeft) + 'px';
    right.style.top = Math.round(hole.top) + 'px';
    right.style.width = Math.round(Math.max(0, view.left + view.width - rightLeft)) + 'px';
    right.style.height = Math.round(hole.height) + 'px';
    if (ui.ring) {
      ui.ring.hidden = false;
      ui.ring.style.left = Math.round(hole.left) + 'px';
      ui.ring.style.top = Math.round(hole.top) + 'px';
      ui.ring.style.width = Math.round(hole.width) + 'px';
      ui.ring.style.height = Math.round(hole.height) + 'px';
    }
  }

  function positionFor(mode) {
    if (!session || !session.active) return;
    ensureUi();
    var step = currentLesson(session);
    var target = currentTarget && currentTarget.isConnected ? currentTarget : null;
    var rect = target ? rectFor(target) : null;
    if (!rect && step) {
      target = resolveTarget(step);
      currentTarget = target;
      rect = target ? rectFor(target) : null;
    }
    if (ui.focusTarget) ui.focusTarget.hidden = !target;
    if (!target || !rect) {
      dockWithoutSpotlight();
      return;
    }
    if (mode === 'first' || mode === 'step') scrollTargetIntoView(target);
    var refreshed = target ? rectFor(target) : rect;
    if (refreshed) rect = refreshed;
    var hole = expandRect(rect, 7);
    currentHole = hole;
    ui.layer.hidden = false;
    ui.layer.style.opacity = '1';
    ui.ring.hidden = false;
    ui.pointer.hidden = false;
    if (mode === 'first' && !reducedMotion()) {
      setHole(wideHole());
      placePanel(hole);
      ui.panel.style.opacity = '0';
      requestFrame(function () {
        if (!session || !session.active) return;
        setHole(hole);
        ui.panel.style.opacity = '1';
        placePanel(hole);
      });
    } else {
      ui.layer.classList.toggle('tt-following', mode === 'refresh');
      setHole(hole);
      placePanel(hole);
      if (mode === 'refresh') {
        setTimeout(function () {
          if (ui.layer) ui.layer.classList.remove('tt-following');
        }, 140);
      }
    }
  }

  function dockWithoutSpotlight() {
    if (ui.layer) ui.layer.hidden = true;
    if (ui.ring) ui.ring.hidden = true;
    if (ui.pointer) ui.pointer.hidden = true;
    currentHole = null;
    placePanel(null);
  }

  function setPanelBox(x, y) {
    if (!ui.panel) return;
    ui.panel.style.left = Math.round(x) + 'px';
    ui.panel.style.top = Math.round(y) + 'px';
  }

  function placePanel(hole) {
    if (!ui.panel || placing) return;
    placing = true;
    try {
      var view = viewportBox();
      var pad = 10;
      var gap = 15;
      var viewportHeight = Math.max(160, view.height - pad * 2);
      var width = ui.panel.offsetWidth || Math.min(400, view.width - 20);
      var height = ui.panel.offsetHeight || 240;
      if (!hole) {
        ui.panel.style.maxHeight = viewportHeight + 'px';
        width = ui.panel.offsetWidth || width;
        height = ui.panel.offsetHeight || height;
        setPanelBox(view.left + view.width - width - pad, view.top + view.height - height - pad);
        if (ui.pointer) ui.pointer.hidden = true;
        return;
      }
      var space = {
        below: view.top + view.height - hole.bottom,
        above: hole.top - view.top,
        right: view.left + view.width - hole.right,
        left: hole.left - view.left
      };
      var narrow = view.width < 640;
      var order = narrow ? ['below', 'above', 'right', 'left'] : ['right', 'left', 'below', 'above'];
      var fits = {
        below: space.below >= height + gap,
        above: space.above >= height + gap,
        right: space.right >= width + gap,
        left: space.left >= width + gap
      };
      var side = null;
      for (var i = 0; i < order.length; i++) {
        if (fits[order[i]]) { side = order[i]; break; }
      }
      if (!side) {
        var ranked = order.slice().sort(function (a, b) { return space[b] - space[a]; });
        side = ranked[0];
      }
      if (side === 'below' || side === 'above') {
        var available = Math.max(150, space[side] - gap);
        ui.panel.style.maxHeight = Math.min(viewportHeight, available) + 'px';
        ui.panel.style.maxWidth = '';
      } else {
        ui.panel.style.maxHeight = viewportHeight + 'px';
        ui.panel.style.maxWidth = Math.max(250, Math.min(420, space[side] - gap)) + 'px';
      }
      var boxWidth = ui.panel.offsetWidth || width;
      var boxHeight = ui.panel.offsetHeight || height;
      var x;
      var y;
      if (side === 'below') {
        x = hole.left + hole.width / 2 - boxWidth / 2;
        y = hole.bottom + gap;
      } else if (side === 'above') {
        x = hole.left + hole.width / 2 - boxWidth / 2;
        y = hole.top - gap - boxHeight;
      } else if (side === 'right') {
        x = hole.right + gap;
        y = hole.top + hole.height / 2 - boxHeight / 2;
      } else {
        x = hole.left - gap - boxWidth;
        y = hole.top + hole.height / 2 - boxHeight / 2;
      }
      var bounds = {
        left: view.left + pad,
        top: view.top + pad,
        right: view.left + view.width - pad,
        bottom: view.top + view.height - pad
      };
      x = Math.max(bounds.left, Math.min(x, bounds.right - boxWidth));
      y = Math.max(bounds.top, Math.min(y, bounds.bottom - boxHeight));
      setPanelBox(x, y);
      placePointer(side, hole, { x: x, y: y, width: boxWidth, height: boxHeight });
    } finally {
      placing = false;
    }
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(value, max));
  }

  function placePointer(side, hole, box) {
    var pointer = ui.pointer;
    if (!pointer) return;
    var size = 14;
    var left;
    var top;
    var rotation;
    if (side === 'below') {
      left = clamp(hole.left + hole.width / 2 - size / 2, box.x + 16, box.x + box.width - size - 16);
      top = box.y - size + 1;
      rotation = 0;
    } else if (side === 'above') {
      left = clamp(hole.left + hole.width / 2 - size / 2, box.x + 16, box.x + box.width - size - 16);
      top = box.y + box.height - 1;
      rotation = 180;
    } else if (side === 'right') {
      top = clamp(hole.top + hole.height / 2 - size / 2, box.y + 14, box.y + box.height - size - 14);
      left = box.x - size + 1;
      rotation = -90;
    } else {
      top = clamp(hole.top + hole.height / 2 - size / 2, box.y + 14, box.y + box.height - size - 14);
      left = box.x + box.width - 1;
      rotation = 90;
    }
    pointer.hidden = false;
    pointer.style.left = Math.round(left) + 'px';
    pointer.style.top = Math.round(top) + 'px';
    pointer.style.transform = 'rotate(' + rotation + 'deg)';
  }

  /* ---- observers ---------------------------------------------------------- */
  function watchTarget() {
    disconnectObservers();
    if (!currentTarget) return;
    try {
      if (typeof root.MutationObserver === 'function') {
        targetObserver = new root.MutationObserver(refreshSoon);
        targetObserver.observe(currentTarget, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
        var ancestor = currentTarget.closest ? currentTarget.closest('.k-region-card, .selection-workbench, .col-left, .col-right, .ix-screen, .hud-top, .methods-screen, .saved-library') : null;
        if (ancestor && ancestor !== currentTarget) {
          targetObserver.observe(ancestor, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
        }
      }
      if (typeof root.ResizeObserver === 'function') {
        targetResize = new root.ResizeObserver(refreshSoon);
        targetResize.observe(currentTarget);
      }
    } catch (_) { /* ignore */ }
    if (ui.panel && !panelResize && typeof root.ResizeObserver === 'function') {
      try {
        panelResize = new root.ResizeObserver(function () {
          if (session && session.active && currentHole) placePanel(currentHole);
        });
        panelResize.observe(ui.panel);
      } catch (_) { panelResize = null; }
    }
  }

  function disconnectObservers() {
    if (targetObserver) { try { targetObserver.disconnect(); } catch (_) { /* ignore */ } targetObserver = null; }
    if (targetResize) { try { targetResize.disconnect(); } catch (_) { /* ignore */ } targetResize = null; }
  }

  /* ------------------------------------------------------------------------
     Public API
     ---------------------------------------------------------------------- */
  var api = {
    start: start,
    stop: stop,
    restart: restart,
    resume: resume,
    skipLesson: skipLesson,
    isActive: isActive,
    lessons: listLessons,
    completeStep: completeStep,
    refresh: refresh,
    setBusy: setBusy,
    openWelcome: openWelcome,
    openLessons: openLessons,
    maybeWelcome: maybeWelcome,
    loadEvidence: loadEvidence,
    pickLessonEvidence: pickLessonEvidence,
    STORAGE_KEY: STORAGE_KEY,
    VERSION: VERSION,
    __pure: {
      LESSONS: LESSONS,
      lessonById: lessonById,
      createSession: createSession,
      reduce: reduce,
      currentLesson: currentLesson,
      progressOf: progressOf,
      canAdvance: canAdvance,
      canSkip: canSkip,
      canGoBack: canGoBack,
      normalizeAction: normalizeAction,
      matchAction: matchAction,
      sanitizeProgress: sanitizeProgress,
      readProgress: readProgress,
      writeProgress: writeProgress,
      shouldShowWelcome: shouldShowWelcome,
      pickLessonEvidence: pickLessonEvidence,
      recordMatches: recordMatches,
      cachedLessonsFor: cachedLessonsFor,
      prefersReducedMotion: prefersReducedMotion,
      motionDuration: motionDuration,
      STORAGE_KEY: STORAGE_KEY,
      VERSION: VERSION
    }
  };

  root.TerraTour = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

  /* A defensive first-visit Welcome if the app never calls maybeWelcome().
     maybeWelcome() itself is idempotent, so a second call is harmless. */
  if (typeof document !== 'undefined') {
    var boot = function () {
      setTimeout(function () {
        if (!welcomeRequested && !isActive() && !activeModal) maybeWelcome();
      }, 1200);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
    else boot();
  }
})(typeof window === 'undefined' ? globalThis : window);
