/* ============================================================
   TerraTrend · Earth Change Observatory
   3D interactive globe (three.js) + multi-variable analysis
   ============================================================ */

const $ = (id) => document.getElementById(id);

const C = {
  /* Kaspersky-cybermap palette: data glows magenta / cyan on an olive world */
  rise: "#59baff",
  fall: "#ff786a",
  compare: "#e9c77a",
  flat: "#4a5f54",
  nodata: "#22302a",
  cyan: "#cce8d9",
  land: "#3f5f4d",
  landDim: "#1d2c25",
  globeLine: "#1b2a22",
  ring: "#93e2bc",
  arcHot: "#ff3ea5",
  arcCool: "#38d9ff",
  ocean: "#050b08",
};

const MAX_VARS = 3;

const state = {
  catalog: null,
  selected: ["T2M"],
  result: null,
  // incremented per analysis so a slow, superseded response cannot repaint
  // the globe over a newer click
  analyzeSeq: 0,
  mode: "yearly",
  activeVarIdx: 0,
  activeSphere: "all",
  compareMode: false,
  preferredVar: null,
  pendingBbox: null,
  satellite: null,
  selectedCellBbox: null,
  activeSatBbox: null,
  activeSatTitle: null,
  satModalMode: "slider",
  satModalLayer: "true_color",
  satYearBase: 2005,
  satYearRecent: 2024,
  satCustomDate: "08-15",
  expandedVarIdx: 0,
  expandedMode: "yearly",
  zoomAxis: "x",
  compareRegionId: null,
  telecon: null,
};

let chart = null;
let expandedChart = null;
let clockTimer = null;

/* ============================================================
   BOOT
   ============================================================ */
async function boot() {
  try {
    const r = await fetch("/api/catalog");
    state.catalog = await r.json();
  } catch (e) {
    setStatus("err", "Cannot reach the API. Is the server running?");
    return;
  }

  // start with nothing selected - the user picks for themselves
  state.selected = [];
  renderVarList();
  renderRegionSelect();

  // Data currency readout from live availability probe
  const avail = state.catalog.availability || {};
  if (avail.ok && avail.latest_month_label) {
    const el = $("data-through");
    if (el) {
      el.textContent = avail.latest_month_label;
      el.title =
        `NASA POWER monthly data valid through ${avail.latest_month_label}` +
        (avail.latest_day_label ? ` (daily through ${avail.latest_day_label})` : "");
    }
  }

  const maxYear = state.catalog.years.max;
  $("start").min = state.catalog.years.min;
  $("start").max = maxYear - 8;
  $("end").min = state.catalog.years.min + 8;
  $("end").max = maxYear;
  if (+$("end").value < maxYear) $("end").value = maxYear;
  if (+$("start").value > maxYear - 8) $("start").value = maxYear - 8;

  wireStartModal();
  $("run").addEventListener("click", analyze);
  $("scan").addEventListener("click", scanAll);
  $("scan-close").addEventListener("click", closeScan);
  $("defs-open").addEventListener("click", openDefs);
  $("defs-close").addEventListener("click", closeDefs);

  const defsM = $("defs-modal");
  if (defsM) defsM.addEventListener("click", (e) => { if (e.target === defsM) closeDefs(); });
  const scanM = $("scan-modal");
  if (scanM) scanM.addEventListener("click", (e) => { if (e.target === scanM) closeScan(); });

  const traceBtn = $("btn-trace-impacts");
  if (traceBtn) traceBtn.addEventListener("click", traceGlobalImpacts);
  const ledgerBtn = $("btn-open-ledger");
  if (ledgerBtn) ledgerBtn.addEventListener("click", () => openInterconnectScreen({ force: true }));
  const ledgerClose = $("ledger-close");
  if (ledgerClose) ledgerClose.addEventListener("click", closeImpactLedger);
  const ledgerDone = $("ledger-done");
  if (ledgerDone) ledgerDone.addEventListener("click", closeImpactLedger);
  const ledgerM = $("impact-ledger-modal");
  if (ledgerM) ledgerM.addEventListener("click", (e) => { if (e.target === ledgerM) closeImpactLedger(); });

  $("region").addEventListener("change", onRegionChange);
  const compToggle = $("toggle-compare-mode");
  if (compToggle) compToggle.addEventListener("click", toggleCompareMode);
  const compRegSel = $("compare-region");
  if (compRegSel) compRegSel.addEventListener("change", onCompareRegionChange);

  document.querySelectorAll(".sphere-tab").forEach((tab) => {
    tab.addEventListener("click", () => setSphereFilter(tab.dataset.sphere));
  });

  $("start").addEventListener("change", clampRange);
  $("end").addEventListener("change", clampRange);
  document.querySelectorAll(".chart-panel .seg-btn").forEach((b) =>
    b.addEventListener("click", () => setMode(b.dataset.mode))
  );

  initSatModal();
  initDataModal();

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeSatelliteModal();
      closeDataModal();
      closeScan();
      closeDefs();
      closeImpactLedger();
    }
  });

  startClock();
  await initGlobe();
}

function startClock() {
  const tick = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    $("foot-clock").textContent =
      `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ` +
      `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
  };
  tick();
  clockTimer = setInterval(tick, 1000);
}

/* ============================================================
   VARIABLE LIST & EARTH SYSTEM SPHERES
   ============================================================ */
function setSphereFilter(sphere) {
  state.activeSphere = sphere || "all";
  document.querySelectorAll(".sphere-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.sphere === state.activeSphere);
  });
  renderVarList();
}

function renderVarList() {
  const box = $("var-list");
  box.innerHTML = "";

  const GROUPS = [
    ["temperature", "TEMPERATURE"],
    ["water", "WATER & MOISTURE"],
    ["energy", "ENERGY & ATMOSPHERE"],
  ];

  const showUnavailable=state.showUnavailable===true;
  let hiddenCount=0;
  box.dataset.hiddenUnavailable='0';
  const addItem = (v) => {
    const on=state.selected.includes(v.id),unavailable=typeof variableSourceAvailable==='function'&&!variableSourceAvailable(v.id);
    if(unavailable&&!on&&!showUnavailable){hiddenCount++;box.dataset.hiddenUnavailable=String(hiddenCount);return;}
    const el=document.createElement('label');el.className='var-item'+(on?' on':'')+(unavailable?' source-unavailable':'');el.dataset.variable=v.id;
    el.style.setProperty('--vc',v.color);el.title=(v.desc||v.plain||'')+(unavailable?' · Not available for the current processing method.':'');
    el.innerHTML=`<input class="variable-check" type="checkbox" aria-label="${esc(v.name)}" ${on?'checked':''} ${unavailable&&!on?'disabled':''}><i class="var-dot"></i><span class="var-text"><span class="var-name">${esc(v.name)}</span><span class="var-meta">${esc(v.sphere_code||'ATM')} · ${esc(v.unit)}</span>${unavailable?'<span class="var-source-note">NOT AVAILABLE YET</span>':''}</span>`;
    const check=el.querySelector('input');check.addEventListener('change',()=>{toggleVar(v.id);check.checked=state.selected.includes(v.id);});box.appendChild(el);
  };

  if (state.activeSphere === "all") {
    GROUPS.forEach(([gid, label]) => {
      const vars = state.catalog.variables.filter((v) => v.group === gid);
      if (!vars.length) return;
      const head = document.createElement("div");
      head.className = "var-group";
      head.textContent = label;
      box.appendChild(head);
      vars.forEach(addItem);
    });
  } else {
    const filtered = state.catalog.variables.filter((v) => v.sphere === state.activeSphere);
    filtered.forEach(addItem);
  }

  if(hiddenCount){
    const note=document.createElement('p');note.className='var-hidden-note';
    note.id='var-hidden-note';
    note.textContent=`${hiddenCount} more measurement${hiddenCount===1?'':'s'} need a different data source and ${hiddenCount===1?'is':'are'} hidden.`;
    const reveal=document.createElement('button');reveal.type='button';reveal.className='link-btn';reveal.id='show-unavailable';
    reveal.textContent='Show them anyway';
    reveal.onclick=()=>{state.showUnavailable=true;renderVarList();};
    note.append(document.createTextNode(' '),reveal);
    box.append(note);
  }
  $("var-count").textContent = `${state.selected.length} / ${MAX_VARS}`;
  window.TerraWorkspace?.refresh?.();
}

function toggleVar(id) {
  const i = state.selected.indexOf(id);
  if (i >= 0) {
    // allow an empty selection: the user should be able to start from nothing
    state.selected.splice(i, 1);
  } else {
    if (state.selected.length >= MAX_VARS) {
      setStatus("busy",
        `LIMIT ${MAX_VARS} VARIABLES — DESELECT ONE FIRST`);
      setTimeout(() => setStatus("ok", ""), 2200);
      return;
    }
    state.selected.push(id);
  }
  state.activeVarIdx = 0;
  renderVarList();
  updateGlobeOverlay();

  // a selection clears the "pick a variable" warning
  const st = $("status");
  if (st && !st.hidden && /SELECT AT LEAST ONE/.test(st.textContent)) {
    clearTimeout(state.warnTimer);
    setStatus("ok", "");
  }

  if (!state.selected.length) {
    // nothing to analyse any more: clear stale results rather than keep them
    clearResults();
    return;
  }
  if (state.result) analyze();
}

/* Wipe the analysis state when the selection becomes empty. */
function clearResults() {
  state.result = null;
  state.satellite = null;
  if (chart) {
    chart.destroy();
    chart = null;
  }
  const list = $("signal-list");
  if (list) {
    list.innerHTML =
      '<p class="micro">Run an analysis to populate.</p>';
  }
  ["cell-summary", "lit-list", "sat-summary"].forEach((id) => {
    const el = $(id);
    if (el) el.innerHTML = "";
  });
  ["cell-tag", "lit-tag", "verdict-chip"].forEach((id) => {
    const el = $(id);
    if (el) el.textContent = "—";
  });
  const threat = $("threat-val");
  if (threat) threat.textContent = "—";
  if (typeof renderGlobeRegions === "function") renderGlobeRegions(null);
}

/* ============================================================
   REGION SELECTION & CONTRAST MODE
   ============================================================ */
function toggleCompareMode() {
  state.compareMode = !state.compareMode;
  const pill = $("toggle-compare-mode");
  const grp = $("compare-region-group");
  if (state.compareMode) {
    if (pill) {
      pill.classList.add("active");
      pill.textContent = "MODE: CONTRAST (A vs B)";
    }
    if (grp) grp.style.display = "block";
    const selA = $("region");
    const selB = $("compare-region");
    if (selA && selB && selA.value === selB.value) {
      const alt = state.catalog.regions.find((r) => r.id !== selA.value);
      if (alt) selB.value = alt.id;
    }
    onCompareRegionChange();
  } else {
    if (pill) {
      pill.classList.remove("active");
      pill.textContent = "MODE: SINGLE";
    }
    if (grp) grp.style.display = "none";
    const contrastPanel = $("contrast-panel");
    if (contrastPanel) contrastPanel.style.display = "none";
    if (state.result && state.result.compare) {
      delete state.result.compare;
      render();
    }
  }
  if (state.result) analyze();
}

function renderRegionSelect() {
  const sel = $("region");
  const selB = $("compare-region");
  sel.innerHTML = "";
  if (selB) selB.innerHTML = "";

  state.catalog.regions.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.id;
    o.textContent = r.name;
    sel.appendChild(o);

    if (selB) {
      const oB = document.createElement("option");
      oB.value = r.id;
      oB.textContent = r.name;
      selB.appendChild(oB);
    }
  });

  sel.value = "sahel";
  if (selB) selB.value = "amazon";
  onRegionChange();
  if (selB) onCompareRegionChange();
}

function onRegionChange() {
  // choosing a preset from the dropdown overrides any area picked on the globe
  state.pendingBbox = null;
  applyRegionSelection(currentRegion());
  if (state.result) analyze();
}

function onCompareRegionChange() {
  const r = currentCompareRegion();
  const descEl = $("compare-region-desc");
  if (descEl) descEl.textContent = r ? r.desc : "";
  if (state.result && state.compareMode) analyze();
}

function currentRegion() {
  if (!state.catalog || !state.catalog.regions) return null;
  const id = $("region") ? $("region").value : null;
  return state.catalog.regions.find((r) => r.id === id) || null;
}

function currentCompareRegion() {
  const id = $("compare-region") ? $("compare-region").value : null;
  return state.catalog.regions.find((r) => r.id === id) || null;
}

function clampRange() {
  let s = +$("start").value;
  let e = +$("end").value;
  const maxYear = (state.catalog && state.catalog.years) ? state.catalog.years.max : 2026;
  const minYear = (state.catalog && state.catalog.years) ? state.catalog.years.min : 1985;
  if (e - s < 8) {
    if (document.activeElement === $("start")) {
      e = Math.min(maxYear, s + 8);
    } else {
      s = Math.max(minYear, e - 8);
    }
    $("start").value = s;
    $("end").value = e;
  }
}

function setMode(m) {
  state.mode = m;
  document.querySelectorAll(".chart-panel .seg-btn").forEach((b) =>
    b.classList.toggle("on", b.dataset.mode === m)
  );
  if (state.result) drawChart();
}

/* ============================================================
   VARIABLE DEFINITIONS & GLOSSARY MODAL
   ============================================================ */
const DEF_GROUPS = [
  ["temperature", "TEMPERATURE — Heat & Thermal Gradients"],
  ["water", "WATER & MOISTURE — Precipitation, Humidity & Land Moisture"],
  ["energy", "ENERGY & ATMOSPHERE — Radiant Flux, Pressure & Wind"],
];

function openDefs() {
  const box = $("defs-body");
  const vars = state.catalog.variables;

  box.innerHTML = DEF_GROUPS.map(([gid, label]) => {
    const items = vars.filter((v) => v.group === gid)
      .map((v) => `
        <div class="def-item">
          <div class="def-left">
            <i class="def-dot" style="background:${v.color}"></i>
            <div>
              <div class="def-name">${esc(v.name)}</div>
              <div class="def-meta">${esc(v.unit)} · ${esc(v.sphere_name || v.mission)}</div>
            </div>
          </div>
          <div>
            <div class="def-plain">${esc(v.plain || v.desc)}</div>
            ${v.trend_means ? `<div class="def-means"><b>A trend means:</b> ${esc(v.trend_means)}</div>` : ""}
          </div>
        </div>`).join("");
    return `<div class="defs-group">${label}</div>${items}`;
  }).join("");

  showModal($("defs-modal"));
}

function closeDefs() {
  hideModal($("defs-modal"));
}

/* ============================================================
   TREND SCAN — Automated Multi-Variable Detective
   ============================================================ */
async function scanAll() {
  const btn = $("scan");
  const ids = state.catalog.variables.map((v) => v.id);
  const CHUNK = 4;
  const total = ids.length;
  const collected = [];
  const reg = currentRegion();
  const windowLbl = `${$("start").value}–${$("end").value}`;

  btn.disabled = true;
  $("scan-title").textContent =
    `${reg ? reg.name.toUpperCase() : "—"} · ${windowLbl}`;
  $("scan-sub").textContent = "SCANNING…";
  $("scan-table").innerHTML =
    `<div class="scan-note">Acquiring NASA POWER grid across ${total} Earth system variables…</div>`;
  showModal($("scan-modal"));

  try {
    for (let i = 0; i < total; i += CHUNK) {
      const batch = ids.slice(i, i + CHUNK);
      setStatus("busy",
        `<span class="spin"></span>SCANNING ${Math.min(i + CHUNK, total)}/${total}` +
        ` · ${batch.join(", ")}`);
      const params = new URLSearchParams({
        region: $("region").value,
        start: $("start").value,
        end: $("end").value,
        variables: batch.join(","),
      });
      const r = await fetch(`/api/scan?${params}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
      collected.push(...d.scanned);
      renderScan(collected, total);
    }
    setStatus("ok", "");
  } catch (e) {
    setStatus("err", `SCAN FAILED: ${esc(e.message)}`);
  } finally {
    btn.disabled = false;
  }
}

function rankRows(rows) {
  return [...rows].sort((a, b) => {
    const sa = a.ok && a.significant ? 0 : 1;
    const sb = b.ok && b.significant ? 0 : 1;
    if (sa !== sb) return sa - sb;
    return Math.abs(b.tau || 0) - Math.abs(a.tau || 0);
  });
}

function renderScan(rows, total) {
  const ranked = rankRows(rows);
  const okRows = ranked.filter((r) => r.ok);
  const sig = okRows.filter((r) => r.significant);
  const rising = sig.filter((r) => r.direction === "rising").length;
  const falling = sig.filter((r) => r.direction === "falling").length;
  const done = rows.length;

  $("scan-sub").textContent =
    `${sig.length}/${okRows.length} variables significant · ` +
    `${rising} rising · ${falling} falling` +
    (done < total ? ` · scanning ${done}/${total}` : "");

  const head = `<div class="scan-head">
    <span>#</span><span></span><span>VARIABLE</span><span>SLOPE</span>
    <span>p-VALUE</span><span>CELLS</span><span>VERDICT</span>
  </div>`;

  const body = ranked.map((r, i) => {
    const rank = String(i + 1).padStart(2, "0");
    if (!r.ok || r.p === undefined || r.p === null) {
      return `<div class="scan-row nodata">
        <span class="sr-rank">${rank}</span>
        <i class="sr-dot" style="background:${r.color}"></i>
        <span class="sr-name">${esc(r.name)}</span>
        <span class="sr-slope">—</span>
        <span class="sr-p">—</span>
        <span class="sr-cells">—</span>
        <span class="sr-dir nodata" title="${esc(r.error || r.reason || 'Not enough supported observations for a trend test.')}">${r.error ? 'SOURCE ERROR' : 'INSUFFICIENT DATA'}</span>
      </div>`;
    }
    const dir = r.significant ? r.direction : "flat";
    const label = dir === "rising" ? "RISING"
      : dir === "falling" ? "FALLING" : "NOT SIGNIFICANT";
    const sign = r.slope_decade > 0 ? "+" : "";
    return `<div class="scan-row" data-var="${esc(r.id)}">
      <span class="sr-rank">${rank}</span>
      <i class="sr-dot" style="background:${r.color}"></i>
      <span class="sr-name">${esc(r.name)}</span>
      <span class="sr-slope">${sign}${num(r.slope_decade, 3)} ${esc(r.unit)}/dec</span>
      <span class="sr-p">p=${r.p < 0.001 ? "<0.001" : num(r.p, 3)}</span>
      <span class="sr-cells">${r.provenance?.spatial_detail_available===false?'REGIONAL':`${r.cells_sig}/${r.cells_total}`}</span>
      <span class="sr-dir ${dir}">${label}</span>
    </div>`;
  }).join("");

  const box = $("scan-table");
  box.innerHTML = head + body;
  box.querySelectorAll(".scan-row[data-var]").forEach((el) => {
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    el.setAttribute('aria-label', `Open analysis for ${rows.find(r => r.id === el.dataset.var)?.name || el.dataset.var}`);
    el.addEventListener("click", () => openFromScan(el.dataset.var));
    el.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openFromScan(el.dataset.var); } });
  });
}

function closeScan() {
  hideModal($("scan-modal"));
}

function openFromScan(vid) {
  if (!state.selected.includes(vid)) {
    while (state.selected.length >= MAX_VARS) state.selected.pop();
    state.selected.push(vid);
  }
  state.preferredVar = vid;
  renderVarList();
  updateGlobeOverlay();
  closeScan();
  analyze();
}

/* ============================================================
   GLOBAL IMPACT & TELECONNECTION DETECTIVE
   ============================================================ */

async function traceGlobalImpacts() {
  const reg = currentRegion();
  if (!reg) return;

  const vId = (state.result && state.result.series && state.result.series[state.activeVarIdx])
    ? state.result.series[state.activeVarIdx].variable.id
    : (state.selected[0] || "T2M");

  const btn = $("btn-trace-impacts");
  if (btn) btn.disabled = true;

  setStatus("busy", `<span class="spin"></span>TRACING GLOBAL TELECONNECTIONS FOR ${esc(reg.name.toUpperCase())}...`);

  const params = new URLSearchParams({
    region: reg.id,
    variable: vId,
    start: $("start").value,
    end: $("end").value,
    min_r: "0.15",
  });

  try {
    const r = await fetch(`/api/teleconnections?${params}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);

    state.telecon = d;
    renderTeleconHUD(d);
    render3DTeleconArcs(d);
    renderImpactLedger(d);
    openImpactLedger();
    setStatus("ok", "");
  } catch (err) {
    setStatus("err", `TELECONNECTION SCAN FAILED: ${esc(err.message)}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderTeleconHUD(d) {
  const tag = $("telecon-tag");
  const summaryText = $("telecon-summary-text");
  const miniList = $("telecon-mini-list");
  const openBtn = $("btn-open-ledger");

  const conns = (d && d.teleconnections) ? d.teleconnections : [];
  if (tag) tag.textContent = `${conns.length} FOUND`;

  if (summaryText) {
    if (conns.length > 0) {
      summaryText.textContent = `Found ${conns.length} statistically significant remote ripple effects (|r| >= 0.38, p < 0.05).`;
    } else {
      summaryText.textContent = "No significant planetary teleconnections detected (|r| < 0.38). This variable operates as a localized regional signal.";
    }
  }

  if (miniList) {
    miniList.innerHTML = "";
    conns.slice(0, 3).forEach((c) => {
      const pill = document.createElement("div");
      pill.className = "tc-pill";
      const isDirect = c.direction === "direct";
      const sign = c.r > 0 ? "+" : "";
      pill.innerHTML = `
        <span class="tc-pill-name">${esc(c.target_region.name)}: ${esc(c.target_variable.name)}</span>
        <span class="tc-pill-r ${isDirect ? "direct" : "inverse"}">${sign}${c.r.toFixed(2)}</span>
      `;
      pill.title = `${c.strength}: ${c.mechanism}`;
      pill.addEventListener("click", () => {
        investigateTeleconnection(c.target_region.id, c.target_variable.id);
      });
      miniList.appendChild(pill);
    });
  }

  if (openBtn) {
    openBtn.style.display = conns.length > 0 ? "block" : "none";
  }
}

function renderImpactLedger(d) {
  const src = (d && d.source) ? d.source : {};
  const sReg = src.region || {};
  const sVar = src.variable || {};
  const sum = (d && d.summary) ? d.summary : {};
  const conns = (d && d.teleconnections) ? d.teleconnections : [];

  $("ledger-title").textContent = `GLOBAL RIPPLE EFFECTS: ${sVar.name ? sVar.name.toUpperCase() : "VARIABLE"} · ${sReg.name ? sReg.name.toUpperCase() : "REGION"}`;
  $("ledger-sub").textContent = `CROSS-REGIONAL MULTI-SPHERE TELECONNECTIONS (${src.start || ""}–${src.end || ""} · p < 0.05)`;

  const regEl = $("ls-origin-reg");
  if (regEl) regEl.textContent = sReg.name || "—";
  const varEl = $("ls-origin-var");
  if (varEl) varEl.textContent = sVar.name ? `${sVar.name} (${sVar.unit})` : "—";
  const countEl = $("ls-count");
  if (countEl) countEl.textContent = `${conns.length} / ${sum.total_scanned || 0}`;

  const maxREl = $("ls-max-r");
  if (maxREl) {
    if (sum.strongest_direct) {
      maxREl.textContent = `+${sum.strongest_direct.r.toFixed(2)} (${sum.strongest_direct.region})`;
      maxREl.style.color = "var(--rise)";
    } else if (sum.strongest_inverse) {
      maxREl.textContent = `${sum.strongest_inverse.r.toFixed(2)} (${sum.strongest_inverse.region})`;
      maxREl.style.color = "#00e5ff";
    } else {
      maxREl.textContent = "NONE";
      maxREl.style.color = "var(--muted)";
    }
  }

  const body = $("ledger-body");
  if (!body) return;

  if (conns.length === 0) {
    body.innerHTML = `
      <div style="padding: 24px; text-align: center; color: #a6adb5; font-family: var(--font);">
        NO STATISTICALLY SIGNIFICANT GLOBAL TELECONNECTIONS FOUND (|r| < 0.38).<br>
        <span style="font-size: .54rem; color: var(--muted); margin-top: 6px; display: block;">
          This variable's variance is predominantly localized to ${esc(sReg.name || "the selected region")}.
        </span>
      </div>`;
    return;
  }

  const head = `
    <div class="ledger-head">
      <span>#</span>
      <span>IMPACTED REGION</span>
      <span>VARIABLE</span>
      <span>CORRELATION</span>
      <span>PHYSICAL MECHANISM</span>
      <span style="text-align: right;">ACTION</span>
    </div>
  `;

  const rows = conns.map((c, i) => {
    const rank = String(i + 1).padStart(2, "0");
    const isDirect = c.direction === "direct";
    const sign = c.r > 0 ? "+" : "";
    const strengthClass = c.strength.toLowerCase();

    return `
      <div class="ledger-row">
        <span class="lr-rank">${rank}</span>
        <div class="lr-reg">
          <span class="lr-reg-name">${esc(c.target_region.name)}</span>
          <span class="lr-reg-surf">${esc(c.target_region.surface || "land")}</span>
        </div>
        <div class="lr-var">
          <i class="lr-var-dot" style="background:${c.target_variable.color}"></i>
          <div class="lr-var-info">
            <span class="lr-var-name">${esc(c.target_variable.name)}</span>
            <span class="lr-var-sph">[${esc(c.target_variable.sphere_code)}] ${esc(c.target_variable.unit)}</span>
          </div>
        </div>
        <div class="lr-coupling">
          <span class="lr-r ${isDirect ? "direct" : "inverse"}">${sign}${c.r.toFixed(2)}</span>
          <span class="lr-p">p = ${c.p < 0.001 ? "<0.001" : c.p.toFixed(3)}</span>
          <span class="lr-strength ${strengthClass}">${esc(c.strength)}</span>
        </div>
        <div class="lr-mech">${esc(c.mechanism)}</div>
        <div class="lr-act">
          <button class="lr-btn" data-reg="${esc(c.target_region.id)}" data-var="${esc(c.target_variable.id)}">INVESTIGATE</button>
        </div>
      </div>
    `;
  }).join("");

  body.innerHTML = head + rows;

  body.querySelectorAll(".lr-btn").forEach((b) => {
    b.addEventListener("click", () => {
      investigateTeleconnection(b.dataset.reg, b.dataset.var);
    });
  });
}

function openImpactLedger() {
  showModal($("impact-ledger-modal"));
}

function closeImpactLedger() {
  hideModal($("impact-ledger-modal"));
}

function investigateTeleconnection(targetRegId, targetVarId) {
  closeImpactLedger();

  // Switch to Regional Contrast Mode comparing Origin vs Target
  state.compareMode = true;
  const toggleBtn = $("toggle-compare-mode");
  if (toggleBtn) {
    toggleBtn.classList.add("active");
    toggleBtn.textContent = "MODE: CONTRAST (A vs B)";
  }

  const compBox = $("compare-region-box");
  if (compBox) compBox.hidden = false;

  const compSel = $("compare-region");
  if (compSel) compSel.value = targetRegId;

  // Make sure target variable is in selected list
  if (targetVarId && !state.selected.includes(targetVarId)) {
    while (state.selected.length >= MAX_VARS) state.selected.pop();
    state.selected.push(targetVarId);
    renderVarList();
  }

  // Smoothly rotate globe towards midpoint
  const srcReg = currentRegion();
  const tgtReg = state.catalog.regions.find((r) => r.id === targetRegId);
  if (srcReg && tgtReg) {
    const midLon = (srcReg.bbox[0] + srcReg.bbox[2] + tgtReg.bbox[0] + tgtReg.bbox[2]) / 4;
    const midLat = (srcReg.bbox[1] + srcReg.bbox[3] + tgtReg.bbox[1] + tgtReg.bbox[3]) / 4;
    const targetY = -(midLon * Math.PI / 180) - Math.PI / 2;
    const targetX = midLat * Math.PI / 180;
    animateGlobeTo(targetX, targetY);
  }

  analyze();
}

function render3DTeleconArcs(d) {
  if (!teleconArcsGroup) return;

  // Clear existing arcs
  arcPackets = [];
  arcRings = [];
  while (teleconArcsGroup.children.length > 0) {
    const obj = teleconArcsGroup.children[0];
    teleconArcsGroup.remove(obj);
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) obj.material.dispose();
  }

  const conns = (d && d.teleconnections) ? d.teleconnections.slice(0, 10) : [];
  if (!conns.length) return;

  const src = d.source;
  const srcLat = (src.region.bbox[1] + src.region.bbox[3]) / 2;
  const srcLon = (src.region.bbox[0] + src.region.bbox[2]) / 2;
  const p1 = latLonToVec3(srcLat, srcLon, 1.0);

  conns.forEach((c) => {
    const tgt = c.target_region;
    const p2 = latLonToVec3(tgt.lat, tgt.lon, 1.0);

    const isDirect = c.direction === "direct";
    // Kaspersky reads a live attack stream as magenta; the reverse leg is cyan
    const colorHex = isDirect ? 0xff3ea5 : 0x38d9ff;

    // Elevation height scales with angular distance across globe
    const angle = p1.angleTo(p2);
    const altitude = 1.0 + Math.sin(angle / 2) * 0.42;

    const mid = p1.clone().add(p2).multiplyScalar(0.5).normalize().multiplyScalar(altitude);
    const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
    const points = curve.getPoints(48);

    // wide, faint halo under a bright core — cheap bloom without a post pass
    const haloGeom = new THREE.BufferGeometry().setFromPoints(points);
    const haloMat = new THREE.LineBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: Math.min(0.30, Math.abs(c.r) * 0.30),
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const halo = new THREE.Line(haloGeom, haloMat);
    halo.renderOrder = 4;
    halo.scale.setScalar(1.0);
    teleconArcsGroup.add(halo);

    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: Math.min(0.95, 0.45 + Math.abs(c.r) * 0.6),
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const line = new THREE.Line(geom, mat);
    line.renderOrder = 5;
    teleconArcsGroup.add(line);

    // a packet that crawls along the arc, so the link reads as live traffic
    const packetGeom = new THREE.SphereGeometry(0.010, 8, 8);
    const packetMat = new THREE.MeshBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const packet = new THREE.Mesh(packetGeom, packetMat);
    packet.renderOrder = 6;
    packet.userData = { curve, t: Math.random(), speed: 0.0038 + Math.random() * 0.0032 };
    arcPackets.push(packet);
    teleconArcsGroup.add(packet);

    // Glowing target ring on destination
    const ringGeom = new THREE.RingGeometry(0.016, 0.030, 28);
    const ringMat = new THREE.MeshBasicMaterial({
      color: colorHex,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const ring = new THREE.Mesh(ringGeom, ringMat);
    ring.position.copy(p2.clone().multiplyScalar(1.002));
    ring.lookAt(p2.clone().multiplyScalar(2.0));
    ring.userData.pulse = Math.random() * Math.PI * 2;
    arcRings.push(ring);
    teleconArcsGroup.add(ring);
  });
}

/* ============================================================
   STATUS
   ============================================================ */
function setStatus(kind, html) {
  const el = $("status");
  if (!html) {
    el.hidden = true;
    $("sys-status").textContent = "READY";
    return;
  }
  el.hidden = false;
  // "warn" is for user-input problems (nothing selected) - red text, but it
  // must not flip the whole system readout to ERROR
  el.className = "hud-status" + (kind === "err" || kind === "warn" ? " err" : "");
  el.innerHTML = html;
  $("sys-status").textContent =
    kind === "err" ? "ERROR"
      : kind === "warn" ? "CHECK INPUT"
        : kind === "busy" ? "ANALYZING" : "READY";
}

/* ============================================================
   ANALYSIS
   ============================================================ */
async function analyze() {
  const btn = $("run");

  // guard: an analysis needs at least one variable
  if (!state.selected.length) {
    setStatus("warn", "SELECT AT LEAST ONE VARIABLE FIRST");
    const list = $("var-list");
    if (list) {
      list.classList.add("needs-selection");
      setTimeout(() => list.classList.remove("needs-selection"), 1600);
    }
    clearTimeout(state.warnTimer);
    state.warnTimer = setTimeout(() => setStatus("ok", ""), 4000);
    return;
  }

  const seq = ++state.analyzeSeq;
  btn.disabled = true;
  setStatus("busy",
    `<span class="spin"></span>ACQUIRING NASA POWER GRID · TESTING TRENDS…`);

  const params = new URLSearchParams({
    variables: state.selected.join(","),
    region: $("region").value,
    start: $("start").value,
    end: $("end").value,
  });

  // A globe click outside the preset boxes carries its own area.
  if (state.pendingBbox) {
    params.set("bbox", state.pendingBbox.join(","));
  }

  if (state.compareMode && $("compare-region")) {
    const compVal = $("compare-region").value;
    if (compVal && compVal !== $("region").value) {
      params.set("compare_region", compVal);
    }
  }

  try {
    const r = await fetch(`/api/analyze?${params}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    // a region click that landed while this request was in flight has already
    // drawn its own selection; do not let this stale answer overwrite it
    if (seq !== state.analyzeSeq) return;
    state.result = data;
    // a variable chosen from the SCAN table wins; otherwise default to first significant
    const pref = state.preferredVar;
    state.preferredVar = null;
    const prefIdx = pref
      ? data.series.findIndex((s) => s.variable.id === pref)
      : -1;
    const firstSig = data.series.findIndex(
      (s) => s.overall && s.overall.ok && s.overall.significant);
    state.activeVarIdx = prefIdx >= 0 ? prefIdx
      : (firstSig >= 0 ? firstSig : 0);
    render();
    announceVerdict(data);
    setStatus("ok", "");
  } catch (e) {
    if (seq === state.analyzeSeq) {
      setStatus("err", `ANALYSIS FAILED: ${esc(e.message)}`);
    }
  } finally {
    if (seq === state.analyzeSeq) btn.disabled = false;
  }
}

/* ============================================================
   RENDER
   ============================================================ */
function render() {
  const d = state.result;
  renderRegionCard(d);
  renderHeader(d);
  renderSignals(d);
  renderCouplings(d);
  renderRegionalContrast(d);
  renderCells(d);
  renderLegend(d);
  renderSatellite(d);
  renderLiterature();
  drawChart();
  renderGlobeRegions(d);
  updateGlobeOverlay();
}


/* The "country panel" from the reference map, but for a region: name, one
   headline number, and a short bar per selected variable. It reads from the
   same analysis the rest of the HUD uses — nothing new is computed here. */
function renderRegionCard(d) {
  const nameEl = $("krc-name");
  if (!nameEl) return;

  const reg = currentRegion();
  nameEl.textContent = reg ? reg.name : "No region";
  const foot = $("k-foot-region");
  if (foot) foot.textContent = reg ? reg.name.toUpperCase() : "NO REGION SELECTED";

  const surfEl = $("krc-surface");
  if (surfEl) surfEl.textContent = reg && reg.surface ? reg.surface : "—";

  const valEl = $("krc-value");
  const unitEl = $("krc-unit");
  const perEl = $("krc-period");
  const verEl = $("krc-verdict");
  const barsEl = $("krc-bars");
  if (barsEl) barsEl.innerHTML = "";

  if (!d || !d.series || !d.series.length) {
    if (valEl) valEl.textContent = "—";
    if (unitEl) unitEl.textContent = "run an analysis";
    if (perEl) perEl.textContent = "—";
    if (verEl) verEl.textContent = "—";
    return;
  }

  const series = d.series;
  const sig = series.filter((x) => x.overall && x.overall.ok && x.overall.significant);
  if (valEl) valEl.textContent = `${sig.length}/${series.length}`;
  if (unitEl) unitEl.textContent = "significant";

  if (perEl) {
    perEl.textContent = d.start && d.end ? `${d.start}–${d.end}` : "—";
  }
  if (verEl) {
    const active = series[state.activeVarIdx] || series[0];
    const o = active && active.overall;
    let label = "NO TREND";
    if (o && o.ok) {
      if (!o.significant) label = "NOT SIGNIFICANT";
      else label = o.direction === "falling" ? "FALLING" : "RISING";
    }
    verEl.textContent = label;
    verEl.style.color = o && o.ok && o.significant
      ? (o.direction === "falling" ? C.fall : C.rise)
      : "var(--muted-2)";
  }

  if (!barsEl) return;
  // one thin bar per variable, width proportional to |slope| across the set
  const rows = series
    .map((x) => ({ x, o: x.overall, mag: x.overall && x.overall.ok ? Math.abs(x.overall.slope || 0) : 0 }))
    .filter((r) => r.o && r.o.ok);
  if (!rows.length) return;
  const max = Math.max(...rows.map((r) => r.mag), 1e-9);

  for (const r of rows) {
    const pct = Math.max(2, Math.round((r.mag / max) * 100));
    const col = !r.o.significant ? C.flat
      : (r.o.direction === "falling" ? C.fall : C.rise);
    const row = document.createElement("div");
    row.className = "krc-bar";
    row.innerHTML =
      `<span>${esc(r.x.variable.name)}</span>` +
      `<span class="krc-bar-val" style="color:${col}">` +
        `${r.o.slope > 0 ? "+" : ""}${num(r.o.slope * 10, 2)}</span>` +
      `<span class="krc-bar-track">` +
        `<span class="krc-bar-fill" style="width:${pct}%;background:${col};box-shadow:0 0 8px ${col}"></span>` +
      `</span>`;
    barsEl.appendChild(row);
  }
}

function renderCouplings(d) {
  const panel = $("coupling-panel");
  const list = $("coupling-list");
  if (!panel || !list) return;

  const couplings = d.couplings || [];
  if (!couplings.length) {
    panel.style.display = "none";
    return;
  }

  panel.style.display = "block";
  $("coupling-tag").textContent = `${couplings.length} DETECTED`;

  list.innerHTML = couplings.map((c) => {
    const rSign = c.r > 0 ? "+" : "";
    return `
      <div class="coupling-card ${c.phase}">
        <div class="coupling-top">
          <span class="coupling-title">${esc(c.title)}</span>
          <span class="coupling-r">r = ${rSign}${num(c.r, 2)}</span>
        </div>
        <div class="coupling-spheres">
          <span>[${esc(c.sphere_a_code)}] ${esc(c.var_a_name)}</span>
          <span>&harr;</span>
          <span>[${esc(c.sphere_b_code)}] ${esc(c.var_b_name)}</span>
        </div>
        <div class="coupling-phase-tag ${c.phase}">${esc(c.phase_label)}</div>
        <p class="coupling-desc">${esc(c.description)}</p>
      </div>
    `;
  }).join("");
}

function renderRegionalContrast(d) {
  const panel = $("contrast-panel");
  const list = $("contrast-list");
  if (!panel || !list) return;

  if (!d.compare || !d.compare.contrasts || !d.compare.contrasts.length) {
    panel.style.display = "none";
    return;
  }

  panel.style.display = "block";
  const comp = d.compare;
  $("contrast-tag").textContent = `${d.region.name.toUpperCase()} VS ${comp.region.name.toUpperCase()}`;

  list.innerHTML = comp.contrasts.map((c) => {
    const diffSign = c.diff_decade > 0 ? "+" : "";
    const sASign = c.slope_a_decade > 0 ? "+" : "";
    const sBSign = c.slope_b_decade > 0 ? "+" : "";
    let verdictCls = "localized";
    if (c.verdict.includes("DIVERGENT")) verdictCls = "divergent";
    else if (c.verdict.includes("PARALLEL")) verdictCls = "parallel";

    return `
      <div class="contrast-card">
        <div class="contrast-head">
          <span class="contrast-var-name">${esc(c.var_name)}</span>
          <span class="contrast-verdict-pill ${verdictCls}">${esc(c.verdict)}</span>
        </div>
        <div class="contrast-rows">
          <div class="contrast-row reg-a">
            <span>A: ${esc(c.region_a)}</span>
            <b>${sASign}${num(c.slope_a_decade, 2)} ${esc(c.unit)}/dec (p=${num(c.p_a, 3)})</b>
          </div>
          <div class="contrast-row reg-b">
            <span>B: ${esc(c.region_b)}</span>
            <b>${sBSign}${num(c.slope_b_decade, 2)} ${esc(c.unit)}/dec (p=${num(c.p_b, 3)})</b>
          </div>
        </div>
        <div class="contrast-delta">
          <span>Slope Delta: <b>${diffSign}${num(c.diff_decade, 2)} ${esc(c.unit)}/dec</b></span>
          <span>Co-trend: <b>r = ${c.r > 0 ? "+" : ""}${num(c.r, 2)}</b></span>
        </div>
        <p class="contrast-desc">${esc(c.explanation)}</p>
      </div>
    `;
  }).join("");
}

function renderLiterature() {
  // Replaced: the previous OpenAlex/Crossref lookup was a non-NASA data
  // source, which the challenge rules disallow. This panel now points only at
  // NASA/partner resources from the challenge Resources tab.
  const box = $("lit-list");
  if (!box) return;
  const tag = $("lit-tag");
  if (tag) tag.textContent = "NASA";
  const links = [
    ["Giovanni", "https://giovanni.gsfc.nasa.gov/",
     "Multi-variable time series and downloads"],
    ["AppEEARS", "https://appeears.earthdatacloud.nasa.gov/",
     "Subset MODIS/VIIRS/ASTER, build time series"],
    ["Hydrology Time Series", "https://disc.gsfc.nasa.gov/information/tools?title=Hydrology%20Time%20Series",
     "Hydrological series, incl. streamflow"],
    ["KNMI Climate Explorer", "https://climexp.knmi.nl/",
     "Cross-check a trend in an independent tool"],
  ];
  box.innerHTML = links.map(([name, href, note]) => `
    <a class="lit-item" href="${href}" target="_blank" rel="noopener noreferrer">
      <div class="lt">${name}</div>
      <div class="lm"><span>${note}</span></div>
    </a>`).join("");
}

function renderLegend(d) {
  const box = $("legend-active");
  box.innerHTML = "";
  d.series.forEach((s, i) => {
    const li = document.createElement("li");
    li.style.cursor = "pointer";
    const active = i === state.activeVarIdx;
    li.innerHTML = `
      <i class="sw" style="background:${s.variable.color};box-shadow:0 0 7px ${s.variable.color};opacity:${active ? 1 : .4}"></i>
      <span class="legend-var-name ${active ? "active" : ""}">${esc(s.variable.name)}</span>
      <span class="legend-chip ${active ? "active" : ""}">${active ? "ON GLOBE" : "SHOW"}</span>`;
    li.tabIndex=0;li.setAttribute('role','button');
    li.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();li.click();}});
    li.addEventListener("click", () => {
      cancelPendingWork();state.activeVarIdx=i;render();window.TerraWorkspace?.refresh?.();
    });
    box.appendChild(li);
  });

  if (d.compare && d.compare.region) {
    const liComp = document.createElement("li");
    liComp.innerHTML = `
      <i class="sw" style="background:#00e5ff;box-shadow:0 0 7px #00e5ff;"></i>
      <span class="legend-var-name active">[B] ${esc(d.compare.region.name)}</span>
      <span class="legend-chip active">CONTRAST</span>`;
    box.appendChild(liComp);
  }
}

/* Speak the headline result for screen-reader users. The visual verdict is a
   colour-coded dial, which conveys nothing without sight. */
function announceVerdict(d) {
  const el = $("sr-live");
  if (!el || !d || !d.series || !d.series.length) return;
  const idx = Math.min(state.activeVarIdx, d.series.length - 1);
  const s = d.series[idx];
  const o = s.overall || {};
  const reg = d.region ? d.region.name : "the selected region";
  const name = s.variable ? s.variable.name : "the variable";
  if (!o.ok) {
    el.textContent = `${name} over ${reg}: not enough data to test a trend.`;
    return;
  }
  const dir = o.direction === "rising" ? "rising"
    : o.direction === "falling" ? "falling" : "showing no significant trend";
  const sig = o.significant ? "This is statistically significant"
    : "This is not statistically significant";
  const slope = (o.per_decade > 0 ? "+" : "") + (Math.round(o.per_decade * 100) / 100);
  el.textContent = `${name} over ${reg} is ${dir}, ${slope} `
    + `${s.variable ? s.variable.unit : ""} per decade, p equal to `
    + `${Math.round((o.p || 0) * 1000) / 1000}. ${sig}.`;
}

function renderHeader(d) {
  const idx = Math.min(state.activeVarIdx, d.series.length - 1);
  const s = d.series[idx];
  const o = s.overall;
  const reg = d.region.name.toUpperCase();

  $("tm-region").textContent = reg;
  $("tm-period").textContent = `${d.start}–${d.end}`;
  $("tm-samples").textContent = o.ok ? `${o.n} YR` : "—";

  const sig = d.series.filter((x) => x.overall.ok && x.overall.significant).length;
  const total = d.series.filter((x) => x.overall.ok).length;

  let color = C.cyan;
  let pct = 0;

  if (o.ok) {
    const strength = Math.min(1, Math.abs(o.tau));
    pct = o.significant ? 0.55 + strength * 0.45 : strength * 0.45;
    if (o.significant) {
      color = o.direction === "rising" ? C.rise : C.fall;
    } else {
      color = C.flat;
    }
  }

  $("verdict-chip").textContent = `${sig}/${total} SIGNIFICANT`;
  $("verdict-chip").style.color = sig ? color : C.muted;

  const arc = $("dial-arc");
  const circ = 2 * Math.PI * 50;
  arc.style.strokeDasharray = circ;
  arc.style.strokeDashoffset = circ * (1 - pct);
  arc.style.stroke = color;

  $("threat-val").textContent = o.ok
    ? `${o.per_decade > 0 ? "+" : ""}${num(o.per_decade, 2)}`
    : "—";
  $("threat-val").style.color = color;
}

function renderSignals(d) {
  const box = $("signal-list");
  box.innerHTML = "";
  d.series.forEach((s, i) => {
    const v = s.variable;
    const o = s.overall;
    const dir = o.ok ? o.direction : "nodata";
    const dirTxt =
      !o.ok ? "INSUFFICIENT DATA" : !o.significant ? "NOT SIGNIFICANT" :
      dir === "rising" ? "RISING" :
      dir === "falling" ? "FALLING" :
      "NOT SIGNIFICANT";
    const el = document.createElement("div");
    el.className = "signal";
    el.style.setProperty("--vc", v.color);
    el.style.cursor = "pointer";
    if (i === state.activeVarIdx) el.style.background = "#17191b";
    el.innerHTML = `
      <div class="sig-top">
        <span class="sig-name" style="color:${v.color}">${esc(v.name)}</span>
        <span class="sig-dir ${dir}">${dirTxt}</span>
      </div>
      <div class="sig-vals">
        <span>TREND <b>${o.ok ? (o.per_decade > 0 ? "+" : "") +
          num(o.per_decade, 3)+" "+esc(v.unit||"")+" per decade" : "—"}</b></span>
        <span title="Evidence against the no-trend model; not a probability that the result is true">SIGNIFICANCE p <b>${o.ok ? (o.p < 0.001 ? "<0.001" : num(o.p, 3)) : "—"}</b></span>
      </div>`;
    el.tabIndex=0;el.setAttribute('role','button');
    el.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();el.click();}});
    el.addEventListener("click", () => {
      cancelPendingWork();state.activeVarIdx=i;render();window.TerraWorkspace?.refresh?.();
    });
    box.appendChild(el);
  });
}

function renderCells(d) {
  const box = $("cell-summary");
  box.innerHTML = "";
  const s = d.series[state.activeVarIdx] || d.series[0];
  const sm = s.summary;
  if(sm.spatial_detail_available===false){$('cell-tag').textContent='REGIONAL SUMMARY';const note=document.createElement('p');note.className='micro';note.textContent='This source supplied a regional or station-summary series. Native-cell trends, spatial consensus and monthly area coverage are not supplied. See the source and aggregation details for its meaning.';box.appendChild(note);return;}
  $("cell-tag").textContent =
    `${sm.significant_cells.toLocaleString()} of ${sm.total_cells.toLocaleString()} cells changed clearly`;

  // server returns rising_cells / falling_cells (older payloads used rising /
  // falling) — tolerate both, and exclude no-data cells from "no trend"
  const rising = sm.rising_cells ?? sm.rising ?? 0;
  const falling = sm.falling_cells ?? sm.falling ?? 0;
  const validCells = sm.valid_cells ?? sm.total_cells ?? 0;
  const rows = [
    ["RISING", rising, C.rise],
    ["FALLING", falling, C.fall],
    ["NO TREND", Math.max(0, validCells - (sm.significant_cells || 0)), C.flat],
  ];
  const max = Math.max(1, validCells, sm.total_cells || 0);
  rows.forEach(([label, n, color]) => {
    const row = document.createElement("div");
    row.className = "cell-row";
    row.innerHTML = `
      <span style="width:52px">${label}</span>
      <div class="cr-bar"><div class="cr-fill" style="width:${(n / max) * 100}%;background:${color}"></div></div>
      <span class="cr-n" style="color:${color}">${n}</span>`;
    box.appendChild(row);
  });
}

/* ============================================================
   SATELLITE EVIDENCE (NASA GIBS & WORLDVIEW)
   ============================================================ */
function renderSatellite(d) {
  const box = $("sat-summary");
  if (!box) return;
  const sat = d.satellite;
  if (!sat || sat.error) {
    box.innerHTML = `<p class="micro">Satellite imagery unavailable for this region selection.</p>`;
    $("sat-tag").textContent = "OFFLINE";
    return;
  }
  state.satellite = sat;
  state.activeSatBbox = sat.bbox;
  state.activeSatTitle = sat.region_name;
  $("sat-tag").textContent = `${sat.baseline.year} VS ${sat.recent.year}`;

  box.innerHTML = `
    <div class="sat-thumb-row">
      <div class="sat-thumb-card" id="sat-card-baseline">
        <span class="st-lbl">BASELINE (${sat.baseline.year})</span>
        <div class="st-img-wrap">
          <img id="sat-thumb-base" alt="Baseline orbital pass" src="${esc(sat.baseline.image_url)}" loading="lazy">
          <div class="st-spinner" id="sat-spin-base"></div>
        </div>
        <span class="st-date">${esc(sat.baseline.date)}</span>
      </div>
      <div class="sat-thumb-card" id="sat-card-recent">
        <span class="st-lbl">RECENT (${sat.recent.year})</span>
        <div class="st-img-wrap">
          <img id="sat-thumb-recent" alt="Recent orbital pass" src="${esc(sat.recent.image_url)}" loading="lazy">
          <div class="st-spinner" id="sat-spin-recent"></div>
        </div>
        <span class="st-date">${esc(sat.recent.date)}</span>
      </div>
    </div>
    <div class="sat-actions">
      <button id="open-sat-modal" class="hud-btn-mini">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/></svg>
        COMPARE ORBITAL PASS
      </button>
      <a id="sat-worldview-direct" class="hud-link-ext" target="_blank" rel="noopener noreferrer" href="${esc(sat.recent.worldview_url)}">
        WORLDVIEW
      </a>
    </div>
  `;

  const tb = $("sat-thumb-base");
  const tr = $("sat-thumb-recent");
  const sb = $("sat-spin-base");
  const sr = $("sat-spin-recent");
  if (tb && sb) tb.onload = () => { sb.style.display = "none"; };
  if (tr && sr) tr.onload = () => { sr.style.display = "none"; };

  $("open-sat-modal").addEventListener("click", () => openSatelliteModal());

  // Show coordinate bar orbital button
  const cbBtn = $("coord-sat-btn");
  const cbSep = $("coord-sat-sep");
  if (cbBtn) {
    cbBtn.hidden = false;
    cbBtn.textContent = "ORBITAL VIEW";
    cbBtn.onclick = () => openSatelliteModal();
  }
  if (cbSep) cbSep.hidden = false;
}

function initSatModal() {
  const modal = $("sat-modal");
  const closeBtn = $("modal-close");
  if (!modal) return;

  if (closeBtn) closeBtn.addEventListener("click", closeSatelliteModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeSatelliteModal();
  });

  document.querySelectorAll("[data-sat-mode]").forEach((btn) => {
    btn.addEventListener("click", () => setSatModalMode(btn.dataset.satMode));
  });

  const layerSel = $("modal-layer-select");
  if (layerSel) {
    layerSel.addEventListener("change", onModalLayerChange);
  }

  // Populate Year A and Year B dropdowns (2000 to 2024)
  const selBase = $("modal-year-base");
  const selRecent = $("modal-year-recent");
  if (selBase && selRecent) {
    selBase.innerHTML = "";
    selRecent.innerHTML = "";
    for (let yr = 2000; yr <= 2024; yr++) {
      const o1 = document.createElement("option");
      o1.value = yr;
      o1.textContent = yr;
      selBase.appendChild(o1);

      const o2 = document.createElement("option");
      o2.value = yr;
      o2.textContent = yr;
      selRecent.appendChild(o2);
    }
    selBase.addEventListener("change", () => {
      state.satYearBase = parseInt(selBase.value, 10);
      reloadModalSatellite();
    });
    selRecent.addEventListener("change", () => {
      state.satYearRecent = parseInt(selRecent.value, 10);
      reloadModalSatellite();
    });
  }

  // Populate day dropdown (01 to 31)
  const selMonth = $("modal-month-select");
  const selDay = $("modal-day-select");
  if (selDay) {
    selDay.innerHTML = "";
    for (let d = 1; d <= 31; d++) {
      const opt = document.createElement("option");
      const dStr = String(d).padStart(2, "0");
      opt.value = dStr;
      opt.textContent = dStr;
      if (d === 15) opt.selected = true;
      selDay.appendChild(opt);
    }
  }

  const triggerDateUpdate = () => {
    const m = (selMonth && selMonth.value) ? selMonth.value : "08";
    const d = (selDay && selDay.value) ? selDay.value : "15";
    state.satCustomDate = `${m}-${d}`;
    reloadModalSatellite();
  };

  if (selMonth) selMonth.addEventListener("change", triggerDateUpdate);
  if (selDay) selDay.addEventListener("change", triggerDateUpdate);

  const prevMonthBtn = $("modal-month-prev");
  if (prevMonthBtn && selMonth) {
    prevMonthBtn.addEventListener("click", () => {
      let cur = parseInt(selMonth.value, 10);
      cur = cur > 1 ? cur - 1 : 12;
      selMonth.value = String(cur).padStart(2, "0");
      triggerDateUpdate();
    });
  }

  const nextMonthBtn = $("modal-month-next");
  if (nextMonthBtn && selMonth) {
    nextMonthBtn.addEventListener("click", () => {
      let cur = parseInt(selMonth.value, 10);
      cur = cur < 12 ? cur + 1 : 1;
      selMonth.value = String(cur).padStart(2, "0");
      triggerDateUpdate();
    });
  }

  const prevBtn = $("modal-prev-year");
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      state.satYearRecent = Math.max(2000, state.satYearRecent - 1);
      if (selRecent) selRecent.value = state.satYearRecent;
      reloadModalSatellite();
    });
  }

  const nextBtn = $("modal-next-year");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      state.satYearRecent = Math.min(2024, state.satYearRecent + 1);
      if (selRecent) selRecent.value = state.satYearRecent;
      reloadModalSatellite();
    });
  }

  const swapBtn = $("modal-swap-years");
  if (swapBtn) {
    swapBtn.addEventListener("click", () => {
      const temp = state.satYearBase;
      state.satYearBase = state.satYearRecent;
      state.satYearRecent = temp;
      if (selBase) selBase.value = state.satYearBase;
      if (selRecent) selRecent.value = state.satYearRecent;
      reloadModalSatellite();
    });
  }

  initSplitSlider();
}

function showModal(modal) {
  if (!modal) return;
  modal.hidden = false;
  void modal.offsetWidth; // force browser layout reflow for animation
  modal.classList.add("open");
}

function hideModal(modal) {
  if (!modal) return;
  modal.classList.remove("open");
  setTimeout(() => {
    if (!modal.classList.contains("open")) modal.hidden = true;
  }, 270);
}

function openSatelliteModal(customBbox = null, customTitle = null) {
  const modal = $("sat-modal");
  if (!modal) return;

  const startYr = Math.max(2000, parseInt($("start").value, 10) || 2005);
  const endYr = Math.max(2000, parseInt($("end").value, 10) || 2024);
  state.satYearBase = startYr;
  state.satYearRecent = endYr;

  const selBase = $("modal-year-base");
  const selRecent = $("modal-year-recent");
  if (selBase) selBase.value = state.satYearBase;
  if (selRecent) selRecent.value = state.satYearRecent;

  if (state.satellite && state.satellite.seasonal_md) {
    state.satCustomDate = state.satellite.seasonal_md;
  }
  const [curM, curD] = (state.satCustomDate || "08-15").split("-");
  if ($("modal-month-select")) $("modal-month-select").value = curM;
  if ($("modal-day-select")) $("modal-day-select").value = curD;

  const targetBbox = customBbox || (state.result && state.result.region ? state.result.region.bbox : null);
  const targetTitle = customTitle || (state.result && state.result.region ? state.result.region.name : "Selected Region");

  state.activeSatBbox = targetBbox;
  state.activeSatTitle = targetTitle;

  showModal(modal);
  // keep the markup in sync with the remembered mode on every open, so the
  // split slider is what the user lands on
  setSatModalMode(state.satModalMode);
  reloadModalSatellite();
}

function closeSatelliteModal() {
  hideModal($("sat-modal"));
}

function setSatModalMode(mode) {
  state.satModalMode = mode;
  document.querySelectorAll("[data-sat-mode]").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.satMode === mode);
  });
  const sideView = $("view-sidebyside");
  const sliderView = $("view-slider");
  if (sideView) sideView.hidden = mode !== "side";
  if (sliderView) sliderView.hidden = mode !== "slider";
}

async function onModalLayerChange() {
  const layerSel = $("modal-layer-select");
  if (!layerSel) return;
  state.satModalLayer = layerSel.value;
  reloadModalSatellite();
}

function reloadModalSatellite() {
  const regId = $("region").value;
  fetchSatelliteImagery(
    regId,
    state.activeSatBbox,
    state.satYearBase,
    state.satYearRecent,
    state.satModalLayer,
    state.activeSatTitle,
    state.satCustomDate
  );
}

async function fetchSatelliteImagery(regId, bbox, start, end, layer, title, customDate = null) {
  const loadBase = $("loading-base");
  const loadRecent = $("loading-recent");
  if (loadBase) { loadBase.textContent = "LOADING NASA GIBS…"; loadBase.classList.remove("hidden"); }
  if (loadRecent) { loadRecent.textContent = "LOADING NASA GIBS…"; loadRecent.classList.remove("hidden"); }

  let url = `/api/satellite-imagery?start=${start}&end=${end}&layer=${encodeURIComponent(layer)}`;
  if (customDate) url += `&date=${encodeURIComponent(customDate)}`;
  if (bbox && bbox.length === 4) {
    url += `&bbox=${bbox.join(",")}`;
  } else if (regId) {
    url += `&region=${encodeURIComponent(regId)}`;
  }

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sat = await res.json();
    if (title) sat.region_name = title;
    loadSatelliteImages(sat);
  } catch (err) {
    if (loadBase) { loadBase.textContent = "ORBITAL PASS UNAVAILABLE"; }
    if (loadRecent) { loadRecent.textContent = "ORBITAL PASS UNAVAILABLE"; }
  }
}

function loadSatelliteImages(sat) {
  if (!sat || !sat.baseline || !sat.recent) return;

  $("modal-region-title").textContent = (sat.region_name || "SATELLITE EVIDENCE").toUpperCase();
  const b = sat.bbox || [];
  $("modal-bbox-sub").textContent = b.length === 4
    ? `BBOX: [${b[0].toFixed(2)}°, ${b[1].toFixed(2)}°] to [${b[2].toFixed(2)}°, ${b[3].toFixed(2)}°]`
    : "COORDINATES —";

  if ($("side-badge-base")) $("side-badge-base").textContent = `${sat.baseline.year} · BASELINE`;
  if ($("side-badge-recent")) $("side-badge-recent").textContent = `${sat.recent.year} · COMPARISON`;
  $("side-date-base").textContent = sat.baseline.date || "BASELINE";
  $("side-date-recent").textContent = sat.recent.date || "RECENT";

  // Split slider labels and status
  if ($("slider-badge-base")) $("slider-badge-base").textContent = `LEFT: ${sat.baseline.year}`;
  if ($("slider-badge-comp")) $("slider-badge-comp").textContent = `RIGHT: ${sat.recent.year}`;
  if ($("slider-handle-tag")) $("slider-handle-tag").textContent = `${sat.baseline.year} | ${sat.recent.year}`;
  if ($("slider-info-left")) $("slider-info-left").textContent = `LEFT: ${sat.baseline.date}`;
  if ($("slider-info-right")) $("slider-info-right").textContent = `RIGHT: ${sat.recent.date}`;

  $("modal-worldview-link").href = sat.recent.worldview_url || "#";

  const layerName = sat.layer ? sat.layer.name : "MODIS Terra";
  $("side-sensor-base").textContent = `Sensor: ${layerName} (NASA EOSDIS)`;
  $("side-sensor-recent").textContent = `Sensor: ${layerName} (NASA EOSDIS)`;

  const imgBase = $("modal-img-base");
  const imgRecent = $("modal-img-recent");
  const sliderBase = $("slider-img-base");
  const sliderComp = $("slider-img-comp");
  const loadBase = $("loading-base");
  const loadRecent = $("loading-recent");

  const bUrl = sat.baseline.image_url;
  const rUrl = sat.recent.image_url;

  if (imgBase) {
    imgBase.onload = () => { if (loadBase) loadBase.classList.add("hidden"); };
    imgBase.onerror = () => { if (loadBase) { loadBase.textContent = "ORBITAL PASS UNAVAILABLE"; } };
    imgBase.src = bUrl;
  }
  if (sliderBase) sliderBase.src = bUrl;

  if (imgRecent) {
    imgRecent.onload = () => { if (loadRecent) loadRecent.classList.add("hidden"); };
    imgRecent.onerror = () => { if (loadRecent) { loadRecent.textContent = "ORBITAL PASS UNAVAILABLE"; } };
    imgRecent.src = rUrl;
  }
  if (sliderComp) sliderComp.src = rUrl;
}

let isDraggingSlider = false;

function initSplitSlider() {
  const wrapper = $("slider-wrapper");
  if (!wrapper) return;

  const updateSplit = (clientX) => {
    const rect = wrapper.getBoundingClientRect();
    if (rect.width <= 0) return;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    const pct = Math.max(2, Math.min(98, (x / rect.width) * 100));
    wrapper.style.setProperty("--split-pos", `${pct}%`);
  };

  wrapper.addEventListener("pointerdown", (e) => {
    isDraggingSlider = true;
    wrapper.setPointerCapture(e.pointerId);
    updateSplit(e.clientX);
  });

  wrapper.addEventListener("pointermove", (e) => {
    if (!isDraggingSlider) return;
    updateSplit(e.clientX);
  });

  const stopDrag = (e) => {
    if (isDraggingSlider) {
      isDraggingSlider = false;
      try { wrapper.releasePointerCapture(e.pointerId); } catch (_) {}
    }
  };

  wrapper.addEventListener("pointerup", stopDrag);
  wrapper.addEventListener("pointercancel", stopDrag);
}

/* ============================================================
   DATA & GRAPH OBSERVATORY MODAL (EXPANDED VIEW)
   ============================================================ */
function initDataModal() {
  const modal = $("data-modal");
  const closeBtn = $("data-modal-close");
  if (!modal) return;

  // Register ChartZoom plugin if needed
  if (window.Chart && window.ChartZoom && window.Chart.registry && !window.Chart.registry.plugins.get("zoom")) {
    try {
      window.Chart.register(window.ChartZoom);
    } catch (e) {
      console.warn("ChartZoom registration notice:", e);
    }
  }

  if (closeBtn) closeBtn.addEventListener("click", closeDataModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeDataModal();
  });

  const expandChartBtn = $("btn-expand-chart");
  if (expandChartBtn) {
    expandChartBtn.addEventListener("click", () => openDataModal());
  }

  const expandSignalBtn = $("btn-expand-signal");
  if (expandSignalBtn) {
    expandSignalBtn.addEventListener("click", () => openDataModal());
  }

  const chartBox = $("chart-box-clickable");
  if (chartBox) {
    chartBox.addEventListener("click", () => openDataModal());
  }

  const yearlyBtn = $("data-mode-yearly");
  const monthlyBtn = $("data-mode-monthly");
  if (yearlyBtn && monthlyBtn) {
    yearlyBtn.addEventListener("click", () => setDataModalMode("yearly"));
    monthlyBtn.addEventListener("click", () => setDataModalMode("monthly"));
  }

  const exportBtn = $("data-export-csv");
  if (exportBtn) {
    exportBtn.addEventListener("click", exportDataCSV);
  }

  // Zoom toolbar axis buttons
  const axisBtns = document.querySelectorAll("#zoom-axis-seg .seg-btn");
  axisBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      axisBtns.forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      state.zoomAxis = btn.dataset.axis || "x";
      if (expandedChart && expandedChart.options && expandedChart.options.plugins && expandedChart.options.plugins.zoom) {
        expandedChart.options.plugins.zoom.zoom.mode = state.zoomAxis;
        expandedChart.options.plugins.zoom.pan.mode = state.zoomAxis;
        expandedChart.update("none");
      }
    });
  });

  // Zoom toolbar buttons - smooth animated steps
  const zoomInBtn = $("btn-zoom-in");
  if (zoomInBtn) {
    zoomInBtn.addEventListener("click", () => {
      if (!expandedChart) return;
      if (typeof expandedChart.zoom === "function") {
        const factor = 1.15;
        if (state.zoomAxis === "x") {
          expandedChart.zoom({ x: factor, y: 1 }, "default");
        } else if (state.zoomAxis === "y") {
          expandedChart.zoom({ x: 1, y: factor }, "default");
        } else {
          expandedChart.zoom(factor, "default");
        }
        setTimeout(updateZoomBadge, 260);
      }
    });
  }

  const zoomOutBtn = $("btn-zoom-out");
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener("click", () => {
      if (!expandedChart) return;
      if (typeof expandedChart.zoom === "function") {
        const factor = 0.87;
        if (state.zoomAxis === "x") {
          expandedChart.zoom({ x: factor, y: 1 }, "default");
        } else if (state.zoomAxis === "y") {
          expandedChart.zoom({ x: 1, y: factor }, "default");
        } else {
          expandedChart.zoom(factor, "default");
        }
        setTimeout(updateZoomBadge, 260);
      }
    });
  }

  const zoomResetBtn = $("btn-zoom-reset");
  if (zoomResetBtn) {
    zoomResetBtn.addEventListener("click", () => {
      if (!expandedChart) return;
      if (typeof expandedChart.resetZoom === "function") {
        expandedChart.resetZoom("default");
        setTimeout(updateZoomBadge, 260);
      }
    });
  }

  // Expanded chart canvas events: double-click to reset, smooth calibrated 60fps wheel & pan
  const expCanvas = $("chart-expanded");
  if (expCanvas) {
    expCanvas.addEventListener("dblclick", () => {
      if (expandedChart && typeof expandedChart.resetZoom === "function") {
        expandedChart.resetZoom("default");
        setTimeout(updateZoomBadge, 260);
      }
    });

    let wheelRafId = null;
    let wheelZoomAccum = 0;
    let wheelPanAccum = 0;
    let wheelFocalPoint = null;

    const flushWheel = () => {
      wheelRafId = null;
      if (!expandedChart) return;

      // Handle horizontal swipe panning along timeline
      if (Math.abs(wheelPanAccum) > 0.5) {
        if (typeof expandedChart.pan === "function") {
          expandedChart.pan({ x: -wheelPanAccum * 0.85 }, undefined, "none");
        }
        wheelPanAccum = 0;
      }

      // Handle vertical scroll / trackpad pinch zoom
      if (Math.abs(wheelZoomAccum) > 0.2) {
        // Calibrated exponential scaling: gentle trackpad tick (2px) -> ~0.3% zoom, solid mouse notch (20px) -> ~3% zoom
        const factor = Math.exp(-wheelZoomAccum * 0.0015);
        if (typeof expandedChart.zoom === "function") {
          const fp = wheelFocalPoint;
          if (state.zoomAxis === "x") {
            expandedChart.zoom({ x: factor, y: 1, focalPoint: fp }, "none");
          } else if (state.zoomAxis === "y") {
            expandedChart.zoom({ x: 1, y: factor, focalPoint: fp }, "none");
          } else {
            expandedChart.zoom({ x: factor, y: factor, focalPoint: fp }, "none");
          }
        }
        wheelZoomAccum = 0;
      }

      updateZoomBadge();
    };

    expCanvas.addEventListener("wheel", (e) => {
      if (!expandedChart) return;
      e.preventDefault();

      let dx = e.deltaX;
      let dy = e.deltaY;
      if (e.deltaMode === 1) { dx *= 16; dy *= 16; }
      else if (e.deltaMode === 2) { dx *= 300; dy *= 300; }

      // Clamp individual events to avoid wild spikes from sudden flick inertia
      dx = Math.max(-40, Math.min(40, dx));
      dy = Math.max(-30, Math.min(30, dy));

      const rect = expCanvas.getBoundingClientRect();
      wheelFocalPoint = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      };

      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 1.2) {
        wheelPanAccum += dx;
      } else if (Math.abs(dy) > 0.4) {
        wheelZoomAccum += dy;
      }

      if (!wheelRafId) {
        wheelRafId = requestAnimationFrame(flushWheel);
      }
    }, { passive: false });
  }
}

function updateZoomBadge() {
  const badge = $("zoom-level-badge");
  if (!badge) return;
  if (!expandedChart) {
    badge.textContent = "ZOOM: 1.0x";
    badge.classList.remove("active");
    return;
  }
  try {
    const level = typeof expandedChart.getZoomLevel === "function" ? expandedChart.getZoomLevel() : 1;
    const isZoomed = typeof expandedChart.isZoomedOrPanned === "function"
      ? expandedChart.isZoomedOrPanned()
      : (level > 1.04 || level < 0.96);
    badge.textContent = `ZOOM: ${level.toFixed(1)}x`;
    badge.classList.toggle("active", isZoomed);
  } catch (err) {
    badge.textContent = "ZOOM: 1.0x";
    badge.classList.remove("active");
  }
}

function openDataModal(varIdx = null) {
  const modal = $("data-modal");
  if (!modal) return;
  if (!state.result || !state.result.series || !state.result.series.length) {
    flashHint("RUN AN ANALYSIS FIRST TO EXPAND DATA");
    return;
  }

  if (varIdx !== null && varIdx >= 0) {
    state.expandedVarIdx = Math.min(varIdx, state.result.series.length - 1);
  } else {
    state.expandedVarIdx = Math.min(state.activeVarIdx, state.result.series.length - 1);
  }
  state.expandedMode = state.mode || "yearly";

  showModal(modal);
  renderDataModal();
}

function closeDataModal() {
  hideModal($("data-modal"));
  if (expandedChart) {
    expandedChart.destroy();
    expandedChart = null;
  }
}

function setDataModalMode(mode) {
  state.expandedMode = mode;
  const yearlyBtn = $("data-mode-yearly");
  const monthlyBtn = $("data-mode-monthly");
  if (yearlyBtn) yearlyBtn.classList.toggle("on", mode === "yearly");
  if (monthlyBtn) monthlyBtn.classList.toggle("on", mode === "monthly");
  drawExpandedChart();
}

function renderDataModal() {
  const d = state.result;
  if (!d) return;
  const s = d.series[state.expandedVarIdx] || d.series[0];
  const v = s.variable;
  const o = s.overall || {};

  $("data-modal-title").textContent = `${v.name.toUpperCase()} · ${d.region.name.toUpperCase()}`;
  $("data-modal-sub").textContent =
    `PERIOD: ${d.start} – ${d.end} · SENSOR/MODEL: ${v.mission} · SAMPLES: 25 CELLS · ALPHA: 0.05`;

  const tabBox = $("data-modal-var-tabs");
  if (tabBox) {
    tabBox.innerHTML = "";
    d.series.forEach((ser, idx) => {
      const btn = document.createElement("button");
      btn.className = `data-var-tab ${idx === state.expandedVarIdx ? "on" : ""}`;
      btn.textContent = ser.variable.name;
      btn.style.setProperty("--vc", ser.variable.color);
      btn.addEventListener("click", () => {
        state.expandedVarIdx = idx;
        renderDataModal();
      });
      tabBox.appendChild(btn);
    });
  }

  const yearlyBtn = $("data-mode-yearly");
  const monthlyBtn = $("data-mode-monthly");
  if (yearlyBtn) yearlyBtn.classList.toggle("on", state.expandedMode === "yearly");
  if (monthlyBtn) monthlyBtn.classList.toggle("on", state.expandedMode === "monthly");

  if (o.ok) {
    const slopeDecade = o.slope * 10;
    $("mc-slope").textContent = `${slopeDecade > 0 ? "+" : ""}${num(slopeDecade, 2)} ${v.unit}`;
    $("mc-slope").style.color = o.direction === "falling" ? C.fall : (o.direction === "rising" ? C.rise : C.flat);
    $("mc-slope-sub").textContent = `${o.slope > 0 ? "+" : ""}${num(o.slope, 3)} ${v.unit}/year`;

    $("mc-change").textContent = `${o.change_total > 0 ? "+" : ""}${num(o.change_total, 2)} ${v.unit}`;
    $("mc-change").style.color = o.direction === "falling" ? C.fall : (o.direction === "rising" ? C.rise : C.flat);
    $("mc-change-sub").textContent = o.change_pct == null
      ? "Cumulative shift (percent not meaningful for this scale)"
      : `Cumulative shift: ${o.change_pct > 0 ? "+" : ""}${num(o.change_pct, 1)}%`;

    $("mc-mk").textContent = `p = ${num(o.p, 3)} · Z = ${o.z > 0 ? "+" : ""}${num(o.z, 2)}`;
    $("mc-mk").style.color = o.significant ? (o.direction === "falling" ? C.fall : C.rise) : C.flat;
    $("mc-mk-sub").textContent = o.significant
      ? (o.direction === "rising" ? "STATISTICALLY SIGNIFICANT RISE" : "STATISTICALLY SIGNIFICANT FALL")
      : "NO STATISTICALLY SIGNIFICANT TREND";

    if (o.seasonal_p !== undefined && o.seasonal_p !== null) {
      $("mc-seasonal").textContent = `p = ${num(o.seasonal_p, 3)} · Z = ${o.seasonal_z > 0 ? "+" : ""}${num(o.seasonal_z, 2)}`;
      $("mc-seasonal-sub").textContent = o.seasonal_significant
        ? "Seasonal cycle controlled: CONFIRMED"
        : "Seasonality unverified";
    } else {
      $("mc-seasonal").textContent = "N/A";
      $("mc-seasonal-sub").textContent = "Insufficient monthly data";
    }
  } else {
    $("mc-slope").textContent = "NO DATA";
    $("mc-change").textContent = "—";
    $("mc-mk").textContent = "—";
    $("mc-seasonal").textContent = "—";
  }

  const matrixBox = $("eg-cell-matrix");
  if (matrixBox) {
    matrixBox.innerHTML = "";
    const cells = s.cells || [];
    $("eg-cell-count").textContent = `${cells.length} OBSERVED CELLS`;

    // Sort cells into geographic matrix order:
    // Row 0 = North (highest lat) down to Row 4 = South (lowest lat)
    // Col 0 = West (lowest lon) across to Col 4 = East (highest lon)
    // This perfectly matches the 3D globe alignment (North at top, South at bottom)
    const geoSortedCells = [...cells].sort((a, b) => {
      if (Math.abs(b.lat - a.lat) > 0.0001) {
        return b.lat - a.lat; // Latitude descending (North to South)
      }
      return a.lon - b.lon; // Longitude ascending (West to East)
    });

    geoSortedCells.forEach((c) => {
      const chip = document.createElement("div");
      chip.className = "eg-cell-chip";
      const cColor = c.direction === "nodata" ? C.nodata : c.significant
        ? (c.direction === "falling" ? C.fall : C.rise)
        : C.flat;
      const slopeStr = c.slope !== null && c.slope !== undefined
        ? `${c.slope > 0 ? "+" : ""}${num(c.slope * 10, 2)}`
        : "—";

      chip.innerHTML = `
        <span class="egc-coord">${c.lat.toFixed(1)}°, ${c.lon.toFixed(1)}°</span>
        <span class="egc-slope" style="color:${cColor}">${slopeStr} ${v.unit}</span>
      `;

      chip.addEventListener("mouseenter", () => {
        matrixBox.querySelectorAll(".eg-cell-chip").forEach((el) => el.classList.remove("active"));
        chip.classList.add("active");
        $("eg-cell-detail").innerHTML = `
          <strong>Cell [${c.lat.toFixed(2)}°, ${c.lon.toFixed(2)}°]:</strong>
          Slope: <span style="color:${cColor}">${slopeStr} ${v.unit}/decade</span> ·
          Mann-Kendall p-value: <strong>${c.p !== undefined ? num(c.p, 3) : "—"}</strong> ·
          Status: <strong>${c.direction === "nodata" ? "INSUFFICIENT DATA" : c.significant ? (c.direction === "falling" ? "SIGNIFICANT FALL" : "SIGNIFICANT RISE") : "NO SIGNIFICANT TREND"}</strong>
        `;
      });

      matrixBox.appendChild(chip);
    });
  }

  // Render Earth System Couplings inside Expanded Modal
  const coupSec = $("eg-coupling-section");
  const coupGrid = $("eg-coupling-grid");
  if (coupSec && coupGrid) {
    const couplings = d.couplings || [];
    if (couplings.length > 0) {
      coupSec.style.display = "block";
      $("eg-coupling-count").textContent = `${couplings.length} DETECTED`;
      coupGrid.innerHTML = couplings.map((c) => {
        const rSign = c.r > 0 ? "+" : "";
        return `
          <div class="coupling-card ${c.phase}">
            <div class="coupling-top">
              <span class="coupling-title">${esc(c.title)}</span>
              <span class="coupling-r">r = ${rSign}${num(c.r, 2)}</span>
            </div>
            <div class="coupling-spheres">
              <span>[${esc(c.sphere_a_code)}] ${esc(c.var_a_name)}</span>
              <span>&harr;</span>
              <span>[${esc(c.sphere_b_code)}] ${esc(c.var_b_name)}</span>
            </div>
            <div class="coupling-phase-tag ${c.phase}">${esc(c.phase_label)}</div>
            <p class="coupling-desc">${esc(c.description)}</p>
          </div>
        `;
      }).join("");
    } else {
      coupSec.style.display = "none";
    }
  }

  // Render Regional Contrast inside Expanded Modal
  const contSec = $("eg-contrast-section");
  const contGrid = $("eg-contrast-grid");
  if (contSec && contGrid) {
    if (d.compare && d.compare.contrasts && d.compare.contrasts.length > 0) {
      contSec.style.display = "block";
      $("eg-contrast-badge").textContent = `${d.region.name.toUpperCase()} VS ${d.compare.region.name.toUpperCase()}`;
      contGrid.innerHTML = d.compare.contrasts.map((c) => {
        const diffSign = c.diff_decade > 0 ? "+" : "";
        const sASign = c.slope_a_decade > 0 ? "+" : "";
        const sBSign = c.slope_b_decade > 0 ? "+" : "";
        let verdictCls = "localized";
        if (c.verdict.includes("DIVERGENT")) verdictCls = "divergent";
        else if (c.verdict.includes("PARALLEL")) verdictCls = "parallel";

        return `
          <div class="contrast-card">
            <div class="contrast-head">
              <span class="contrast-var-name">${esc(c.var_name)}</span>
              <span class="contrast-verdict-pill ${verdictCls}">${esc(c.verdict)}</span>
            </div>
            <div class="contrast-rows">
              <div class="contrast-row reg-a">
                <span>A: ${esc(c.region_a)}</span>
                <b>${sASign}${num(c.slope_a_decade, 2)} ${esc(c.unit)}/dec (p=${num(c.p_a, 3)})</b>
              </div>
              <div class="contrast-row reg-b">
                <span>B: ${esc(c.region_b)}</span>
                <b>${sBSign}${num(c.slope_b_decade, 2)} ${esc(c.unit)}/dec (p=${num(c.p_b, 3)})</b>
              </div>
            </div>
            <div class="contrast-delta">
              <span>Slope Delta: <b>${diffSign}${num(c.diff_decade, 2)} ${esc(c.unit)}/dec</b></span>
              <span>Co-trend: <b>r = ${c.r > 0 ? "+" : ""}${num(c.r, 2)}</b></span>
            </div>
            <p class="contrast-desc">${esc(c.explanation)}</p>
          </div>
        `;
      }).join("");
    } else {
      contSec.style.display = "none";
    }
  }

  requestAnimationFrame(() => {
    drawExpandedChart();
  });
}

function drawExpandedChart() {
  const d = state.result;
  if (!d) return;
  const s = d.series[state.expandedVarIdx] || d.series[0];
  const canvas = $("chart-expanded");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const isYear = state.expandedMode === "yearly";

  let chartPoints = [];
  let minX = 0;
  let maxX = 0;

  const partialFlags = isYear
    ? s.yearly_timeseries.map((p) => !p.complete)
    : [];
  const partialYears = isYear
    ? s.yearly_timeseries.filter((p) => !p.complete)
    : [];

  if (isYear) {
    chartPoints = s.yearly_timeseries.map((p) => ({
      x: Number(p.year),
      y: p.complete === false ? null : p.value,
    }));
    minX = Number(s.yearly_timeseries[0].year);
    maxX = Number(s.yearly_timeseries[s.yearly_timeseries.length - 1].year);
  } else {
    // the server sends monthly_timeseries as [{month, value}], not a flat array
    chartPoints = s.monthly_timeseries.map((p, i) => ({
      x: i,
      y: p.value,
    }));
    minX = 0;
    maxX = Math.max(0, s.monthly_timeseries.length - 1);
  }

  if (expandedChart) expandedChart.destroy();

  const o = s.overall || {};
  const accent = o.ok && o.direction === "falling" ? C.fall : (s.variable.color || C.rise);

  const grad = ctx.createLinearGradient(0, 0, 0, 320);
  grad.addColorStop(0, hexA(accent, 0.38));
  grad.addColorStop(1, hexA(accent, 0.01));

  const hasCompare = !!(d.compare && d.compare.series && d.compare.series[state.expandedVarIdx]);
  const sB = hasCompare ? d.compare.series[state.expandedVarIdx] : null;

  /* Constants live at module scope; a sliced or partial load still gets the
     same identity colours rather than throwing. */
  const AREA_C = typeof AREA_COLORS !== "undefined" ? AREA_COLORS : { a: "#68b8ff", b: "#e9c77a" };
  const AREA_D = typeof AREA_DASH !== "undefined" ? AREA_DASH : { a: [7, 4], b: [2, 3] };
  const observedColor = hasCompare ? AREA_C.a : accent;
  const datasets = [{
    label: hasCompare ? `A / ${d.region.name} · ${s.variable.name}` : s.variable.name,
    data: chartPoints,
    trendModel:s.overall,calendarStart:isYear?null:d.start,
    $side:"a",$kind:"observed",$areaName:hasCompare?`A / ${d.region.name}`:s.variable.name,$unit:s.variable.unit,
    borderColor: observedColor,
    backgroundColor: hasCompare ? "transparent" : grad,
    fill: !hasCompare,
    tension: 0.25,
    pointRadius: isYear ? 3.5 : 1.2,
    pointHoverRadius: 6,
    pointBackgroundColor: observedColor,
    borderWidth: 2.2,
    spanGaps: false,
  }];

  if (partialYears.length > 0) {
    datasets.push({
      label: "Partial Year (Excluded from Trend)",
      data: s.yearly_timeseries.map((p) => ({
        x: Number(p.year),
        y: p.complete === false ? p.value : null,
      })),
      showLine: false,
      borderColor: "transparent",
      backgroundColor: "#0c0e11",
      borderWidth: 1.5,
      pointBackgroundColor: "#0c0e11",
      pointBorderColor: "#ffffff",
      pointBorderWidth: 1.5,
      pointRadius: 5.5,
      pointHoverRadius: 7,
      pointStyle: "rectRot",
    });
  }

  const validPts = chartPoints.filter((p) => p.y !== null && Number.isFinite(p.y));
  if (validPts.length > 2 && o.ok) {
    let lineFn;
    if (o.ok) {
      lineFn = (x) => o.intercept + o.slope * (isYear ? x : d.start + x/12);
    } else {
      const ptPairs = validPts.map((p) => [p.x, p.y]);
      lineFn = fitLine(ptPairs);
    }
    datasets.push({
      label: hasCompare ? `A / ${d.region.name} · fitted trend` : `${s.variable.name} · fitted trend`,
      data: chartPoints.map((p) => ({ x: p.x, y: lineFn(p.x) })),
      $side:"a",$kind:"trend",$areaName:hasCompare?`A / ${d.region.name}`:s.variable.name,$unit:s.variable.unit,
      borderColor: observedColor,
      borderDash: AREA_D.a,
      borderWidth: 1.9,
      pointRadius: 0,
      fill: false,
      tension: 0,
    });
  }

  if (hasCompare && sB) {
    let chartPointsB = [];
    if (isYear) {
      chartPointsB = sB.yearly_timeseries.map((p) => ({
        x: Number(p.year),
        y: p.complete === false ? null : p.value,
      }));
    } else {
      chartPointsB = (sB.monthly_timeseries || []).map((p, i) => ({
        x: i,
        y: p.value,
      }));
    }

    datasets.push({
      label: `B / ${d.compare.region.name} · ${sB.variable.name}`,
      data: chartPointsB,
      trendModel:sB.overall,calendarStart:isYear?null:d.start,
      $side:"b",$kind:"observed",$areaName:`B / ${d.compare.region.name}`,$unit:sB.variable.unit,
      borderColor: AREA_C.b,
      backgroundColor: "transparent",
      fill: false,
      tension: 0.25,
      pointRadius: isYear ? 3.5 : 1.2,
      pointHoverRadius: 6,
      pointBackgroundColor: AREA_C.b,
      borderWidth: 2.2,
      spanGaps: false,
    });

    const validPtsB = chartPointsB.filter((p) => p.y !== null && Number.isFinite(p.y));
    if (validPtsB.length > 2) {
      const oB = sB.overall || {};
      let lineFnB;
      if (oB.ok) {
        lineFnB = (x) => oB.intercept + oB.slope * (isYear ? x : d.start + x / 12);
      } else {
        const ptPairsB = validPtsB.map((p) => [p.x, p.y]);
        lineFnB = fitLine(ptPairsB);
      }
      datasets.push({
        label: `B / ${d.compare.region.name} · fitted trend`,
        data: chartPointsB.map((p) => ({ x: p.x, y: lineFnB(p.x) })),
        $side:"b",$kind:"trend",$areaName:`B / ${d.compare.region.name}`,$unit:sB.variable.unit,
        borderColor: AREA_C.b,
        borderDash: AREA_D.b,
        borderWidth: 1.9,
        pointRadius: 0,
        fill: false,
        tension: 0,
      });
    }
  }

  expandedChart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 250,
        easing: "easeOutCubic",
      },
      interaction: {
        mode: "nearest",
        axis: "x",
        intersect: false,
      },
      plugins: {
        zoom: {
          pan: {
            enabled: true,
            mode: state.zoomAxis || "x",
            modifierKey: null,
            onPanComplete: updateZoomBadge,
          },
          zoom: {
            wheel: {
              enabled: false, // Handled by our normalized smooth wheel controller
            },
            pinch: {
              enabled: true,
            },
            mode: state.zoomAxis || "x",
            onZoomComplete: updateZoomBadge,
          },
          limits: {
            x: {
              min: minX,
              max: maxX,
              minRange: isYear ? 3 : 12,
            },
          },
        },
        legend: {
          display: true,
          position: "top",
          labels: {
            color: "#ffffff",
            font: { family: "monospace", size: 11, weight: "600" },
            boxWidth: 14,
          },
        },
        tooltip: {
          backgroundColor: "rgba(8,9,10,.95)",
          borderColor: "#505663",
          borderWidth: 1,
          padding: 10,
          titleFont: { family: "monospace", size: 12, weight: "bold" },
          bodyFont: { family: "monospace", size: 12 },
          titleColor: "#ffffff",
          bodyColor: "#dbe0e6",
          callbacks: {
            title: (items) => {
              if (!items || !items.length) return "";
              const xVal = items[0].parsed.x;
              if (isYear) return `YEAR: ${Math.round(xVal)}`;
              const idx = Math.round(xVal);
              return `MONTH: ${d.months[idx] || ""}`;
            },
            label: c => trendTooltip(c,s.variable.unit),
            labelTextColor:c=>{const o=c.dataset.trendModel;if(!o?.ok)return "#cfe4d5";const x=c.dataset.calendarStart==null?c.parsed.x:c.dataset.calendarStart+c.parsed.x/12;return c.parsed.y>=o.intercept+o.slope*x?C.rise:C.fall;},
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          min: minX,
          max: maxX,
          ticks: {
            color: "#b4bac2",
            maxTicksLimit: isYear ? 12 : 10,
            stepSize: isYear ? 1 : undefined,
            font: { family: "monospace", size: 11, weight: "500" },
            callback: (val) => {
              if (!Number.isFinite(val)) return "";
              if (isYear) {
                if (Math.abs(val - Math.round(val)) < 0.05) {
                  return String(Math.round(val));
                }
                return "";
              } else {
                const idx = Math.round(val);
                if (Math.abs(val - idx) < 0.05 && idx >= 0 && idx < d.months.length) {
                  return d.months[idx];
                }
                return "";
              }
            },
          },
          grid: { color: "#242830" },
          border: { color: "#3d434d" },
        },
        y: {
          ticks: {
            color: "#b4bac2",
            font: { family: "monospace", size: 11, weight: "500" },
            callback: (v) => `${num(v, 2)} ${s.variable.unit}`,
          },
          grid: { color: "#242830" },
          border: { color: "#3d434d" },
        },
      },
    },
  });

  updateZoomBadge();

  const expTrendEl = $("expanded-trendline");
  if (expTrendEl) {
    if (o.ok) {
      const slopePerDec = o.slope * 10;
      const stars = o.p < 0.001 ? "***" : (o.p < 0.01 ? "**" : (o.p < 0.05 ? "*" : ""));
      const dirColor = o.direction === "falling" ? C.fall
        : (o.direction === "rising" ? C.rise : C.flat);
      const dirLabel = o.direction === "rising" ? "RISING"
        : (o.direction === "falling" ? "FALLING" : "FLAT");

      const rows = [];

      rows.push(
        `<div class="tn-row"><span class="tn-key">THEIL–SEN</span><span class="tn-val">` +
        `<b style="color:${dirColor}">${o.slope > 0 ? "+" : ""}${num(slopePerDec, 3)} ${esc(s.variable.unit)}/decade</b> ` +
        `(${dirLabel}) · CUMULATIVE SHIFT ` +
        `<b>${o.change_total > 0 ? "+" : ""}${num(o.change_total, 2)} ${esc(s.variable.unit)}` +
        (o.change_pct == null ? "" : ` (${o.change_pct > 0 ? "+" : ""}${num(o.change_pct, 1)}%)`) +
        `</b></span></div>`
      );

      rows.push(
        `<div class="tn-row"><span class="tn-key">MANN–KENDALL</span><span class="tn-val">` +
        `Z = <b>${o.z > 0 ? "+" : ""}${num(o.z, 2)}</b> · p = <b>${o.p < 0.001 ? "<0.001" : num(o.p, 3)}${stars}</b> · ` +
        `<b style="color:${o.significant ? dirColor : "#a6adb5"}">${o.significant ? "STATISTICALLY SIGNIFICANT" : "NOT SIGNIFICANT"}</b>` +
        `</span></div>`
      );

      if (o.ci_low_per_decade !== null && o.ci_low_per_decade !== undefined) {
        rows.push(
          `<div class="tn-row"><span class="tn-key">95% CI</span><span class="tn-val">` +
          `[<b>${o.ci_low_per_decade > 0 ? "+" : ""}${num(o.ci_low_per_decade, 3)}, ` +
          `${o.ci_high_per_decade > 0 ? "+" : ""}${num(o.ci_high_per_decade, 3)}</b>] ` +
          `${esc(s.variable.unit)}/decade · Theil-Sen confidence interval</span></div>`
        );
      }

      if (o.t_p !== null && o.t_p !== undefined) {
        rows.push(
          `<div class="tn-row"><span class="tn-key">OLS CROSS-CHECK</span><span class="tn-val">` +
          `t-test (df=${o.t_df}) p = <b>${o.t_p < 0.001 ? "<0.001" : num(o.t_p, 3)}</b> · ` +
          `slope <b>${o.t_per_decade > 0 ? "+" : ""}${num(o.t_per_decade, 3)} ${esc(s.variable.unit)}/decade</b> · ` +
          `<b style="color:${o.methods_agree ? "#00e5ff" : "#e3c265"}">` +
          `${o.methods_agree ? "AGREES with Mann–Kendall" : "DISAGREES with Mann–Kendall"}</b></span></div>`
        );
      }

      if (partialYears.length) {
        rows.push(
          `<div class="tn-row"><span class="tn-key">PARTIAL YEAR</span><span class="tn-val">` +
          `${partialYears.map((p) => `${p.year} (${p.months}/12 mo)`).join(" · ")} ` +
          `— shown as points, excluded from the trend slope</span></div>`
        );
      }

      if (hasCompare && sB && sB.overall && sB.overall.ok) {
        const oB = sB.overall;
        rows.push(
          `<div class="tn-row"><span class="tn-key">CONTRAST A vs B</span><span class="tn-val">` +
          `<b>[A] ${esc(d.region.name)}:</b> ${o.per_decade > 0 ? "+" : ""}${num(o.per_decade, 2)} ${esc(s.variable.unit)}/dec (${o.direction.toUpperCase()}) · ` +
          `<b>[B] ${esc(d.compare.region.name)}:</b> ${oB.per_decade > 0 ? "+" : ""}${num(oB.per_decade, 2)} ${esc(sB.variable.unit)}/dec (${oB.direction.toUpperCase()})` +
          `</span></div>`
        );
      }

      expTrendEl.innerHTML = rows.join("");
    } else {
      expTrendEl.textContent = "INSUFFICIENT DATA POINTS FOR STATISTICAL SIGNIFICANCE TESTING";
    }
  }
  if (typeof chartSeriesKey === "function") {
    chartSeriesKey(datasets.map((row) => ({
      text: row.$kind === "trend" ? `${row.label} (dashed)`
        : row.$kind === "partial" ? `${row.label}`
        : `${row.label} (solid)`,
      color: row.borderColor,
      dashed: row.$kind === "trend",
    })), $("expanded-series-key"));
  }
}

function buildAnalysisCSV(d, variableIndex, isYear) {
  const selected = d.series[variableIndex] || d.series[0];
  const areas = [{ slot: "A", region: d.region, block: selected }];
  const comparison = d.compare?.series.find(s => s.variable.id === selected.variable.id);
  if (comparison) areas.push({ slot: "B", region: d.compare.region, block: comparison });
  const periods = isYear
    ? Array.from({ length: d.end - d.start + 1 }, (_, i) => Number(d.start) + i)
    : (d.months?.length ? d.months : [...new Set(areas.flatMap(a => (a.block.monthly_timeseries || []).map(p => p.month)))].sort());
  const rows = [[isYear ? "Year" : "Month_YYYY_MM",
    `${isYear ? "Annual" : "Regional"}_Mean_${selected.variable.id}_${selected.variable.unit}`,
    "Area_Slot", "Area_ID", "Area_Name", "Valid_Months_In_Year", "Complete_Year", "Value_Status",
    "Period_Area_Fraction_With_Any_Data", "Period_Native_Cells_With_Any_Data", "Expected_Native_Cells",
    "Provider", "Source", "Dataset", "Collection_Version", "Source_Field", "Source_Policy",
    "First_Observed_Month", "Last_Observed_Month", "Requested_Start_Year", "Requested_End_Year",
    "Longitude_Spacing_Deg", "Latitude_Spacing_Deg", "Geometry_Revision", "Retrieved_UTC", "Citation", "Quality_Notes"]];
  const observedMonth = value => value ? `${String(value).slice(0, 4)}-${String(value).slice(4, 6)}` : "";
  for (const { slot, region, block } of areas) {
    const p = block.provenance || {};
    const yearly = new Map((block.yearly_timeseries || []).map(point => [point.year, point]));
    const points = new Map((isYear ? block.yearly_timeseries : block.monthly_timeseries || []).map(point => [isYear ? point.year : point.month, point]));
    for (const period of periods) {
      const point = points.get(period), annual = yearly.get(isYear ? period : Number(period.slice(0, 4)));
      const valid = typeof point?.value === "number" && Number.isFinite(point.value);
      rows.push([period, valid ? point.value : "", slot, region.id, region.name,
        annual?.months ?? 0, !!annual?.complete, !valid ? "unavailable" : isYear && !annual?.complete ? "partial_year" : "valid",
        // This provenance is availability in any month of the requested period,
        // not a claim of identical spatial support in every exported month.
        p.available_area_fraction, p.available_cells, p.expected_cells, p.provider, p.source,
        p.dataset, p.collection_version, p.field, p.policy, observedMonth(p.first_observed_month), observedMonth(p.last_observed_month),
        d.start, d.end, p.dlon, p.dlat, p.geometry_version || region.geometry_version, p.retrieved_utc, p.citation, p.quality]);
    }
  }
  const cell = value => {
    if (value === undefined || value === null) return "";
    let text = String(value);
    if (typeof value === "string" && /^[\s\uFEFF]*[=+\-@]/.test(text)) text = "'" + text;
    return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  };
  return rows.map(row => row.map(cell).join(",")).join("\r\n") + "\r\n";
}

function exportDataCSV() {
  const d = state.result;
  if (!d) return;
  const s = d.series[state.expandedVarIdx] || d.series[0];
  const csvContent = buildAnalysisCSV(d, state.expandedVarIdx, state.expandedMode === "yearly");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `terratrend_${d.region.id}_${s.variable.id}_${d.start}_${d.end}${d.compare ? "_comparison" : ""}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ============================================================
   CHART
   ============================================================ */
/* ---------------------------------------------------------------------------
   Chart series identity. Area A and area B keep their own colours everywhere,
   independent of whether the trend rises or falls (direction is carried by the
   text labels, not by the line colour). Observed values are solid, the fitted
   trend is dashed with a per-area dash so the two remain distinguishable in
   greyscale and with colour-vision differences.
   --------------------------------------------------------------------------- */
const AREA_COLORS = { a: "#68b8ff", b: "#e9c77a" };
const AREA_DASH = { a: [7, 4], b: [2, 3] };
function chartSeriesKey(rows, container) {
  if (!container) return;
  container.replaceChildren();
  for (const row of rows) {
    const item = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.style.borderTop = `2px solid ${row.color}`;
    swatch.style.borderTopStyle = row.dashed ? "dashed" : "solid";
    const text = document.createElement("span");
    text.textContent = row.text;
    item.append(swatch, text);
    container.append(item);
  }
  container.hidden = rows.length === 0;
}
function chartTooltipLabel(c, fallbackUnit, fallbackName) {
  const ds = (c && c.dataset) || {};
  const unit = ds.$unit || fallbackUnit || "";
  const area = ds.$areaName || fallbackName || "";
  const value = num(c.parsed.y, 3);
  if (ds.$kind === "trend") return `${area} · fitted trend ${value} ${unit}`;
  if (ds.$kind === "partial") return `${area} · incomplete year, excluded from trend ${value} ${unit}`;
  const fitted = c.chart && c.chart.$fitted && c.chart.$fitted[ds.$side];
  const fitValue = fitted ? fitted[c.dataIndex] : null;
  let extra = "";
  if (Number.isFinite(fitValue)) {
    const delta = c.parsed.y - fitValue;
    extra = ` · ${delta >= 0 ? "+" : ""}${num(delta, 3)} ${unit} ${delta >= 0 ? "above" : "below"} fitted trend`;
  }
  return `${area} · observed ${value} ${unit}${extra}`;
}
function drawChart() {
  const d = state.result;
  if (!d) return;
  const s = d.series[state.activeVarIdx] || d.series[0];
  const ctx = $("chart").getContext("2d");
  const isYear = state.mode === "yearly";

  const labels = isYear
    ? s.yearly_timeseries.map((p) => p.year)
    : s.monthly_timeseries.map((p) => p.month);
  const values = isYear
    ? s.yearly_timeseries.map((p) => p.value)
    : s.monthly_timeseries.map((p) => p.value);

  const partialFlags = isYear
    ? s.yearly_timeseries.map((p) => !p.complete)
    : [];
  if (chart) chart.destroy();

  const o = s.overall;
  const accent = o.ok && o.direction === "falling" ? C.fall :
    (s.variable.color || C.rise);

  const grad = ctx.createLinearGradient(0, 0, 0, 130);
  grad.addColorStop(0, hexA(accent, 0.34));
  grad.addColorStop(1, hexA(accent, 0.01));

  const hasCompare = !!(d.compare && d.compare.series && d.compare.series[state.activeVarIdx]);
  const sB = hasCompare ? d.compare.series[state.activeVarIdx] : null;

  const observedColor = hasCompare ? AREA_COLORS.a : accent;
  const datasets = [{
    label: hasCompare ? `A / ${d.region.name} · ${s.variable.name}` : s.variable.name,
    data: values.map((v, i) => (partialFlags[i] ? null : v)),
    $side: "a", $kind: "observed", $areaName: hasCompare ? `A / ${d.region.name}` : s.variable.name, $unit: s.variable.unit,
    borderColor: observedColor,
    backgroundColor: hasCompare ? "transparent" : grad,
    fill: !hasCompare,
    tension: 0.3,
    pointRadius: isYear ? 2.6 : 0,
    pointHoverRadius: 4,
    borderWidth: 2.1,
    spanGaps: false,
  }];

  if (hasCompare && sB) {
    const valsB = isYear
      ? sB.yearly_timeseries.map((p) => p.value)
      : (sB.monthly_timeseries || []).map((p) => p.value);
    const partialFlagsB = isYear
      ? sB.yearly_timeseries.map((p) => !p.complete)
      : [];
    datasets.push({
      label: `B / ${d.compare.region.name} · ${sB.variable.name}`,
      data: valsB.map((v, i) => (partialFlagsB[i] ? null : v)),
      $side: "b", $kind: "observed", $areaName: `B / ${d.compare.region.name}`, $unit: sB.variable.unit,
      borderColor: AREA_C.b,
      backgroundColor: "transparent",
      fill: false,
      tension: 0.3,
      pointRadius: isYear ? 2.6 : 0,
      pointHoverRadius: 4,
      borderWidth: 2.1,
      spanGaps: false,
    });
  }

  // Draw incomplete / trailing partial years as isolated points
  if (partialFlags.some(Boolean)) {
    datasets.push({
      label: "Incomplete year (excluded from the trend)",
      data: values.map((v, i) => (partialFlags[i] ? v : null)),
      $side: "a", $kind: "partial", $areaName: `A / ${d.region.name}`, $unit: s.variable.unit,
      showLine: false,
      borderColor: "transparent",
      backgroundColor: "#0c0e11",
      borderWidth: 1.5,
      pointBackgroundColor: "#0c0e11",
      pointBorderColor: "#ffffff",
      pointBorderWidth: 1.5,
      pointRadius: 4.5,
      pointHoverRadius: 6,
      pointStyle: "rectRot",
    });
  }

  const pts = values
    .map((v, i) => [i, v])
    .filter((p, i) => p[1] !== null && !partialFlags[i]);

  if (pts.length > 2) {
    let line;
    if (o.ok) {
      const slopePerStep = o.slope * (isYear ? 1 : 1 / 12);
      const mid = pts.reduce((a, p) => a + p[1], 0) / pts.length;
      const midIdx = (values.length - 1) / 2;
      line = (x) => mid + slopePerStep * (x - midIdx);
    } else {
      line = fitLine(pts);
    }
    const fittedA = values.map((_, i) => (partialFlags[i] ? null : line(i)));
    datasets.push({
      label: hasCompare ? `A / ${d.region.name} · fitted trend` : `${s.variable.name} · fitted trend`,
      data: fittedA,
      $side: "a", $kind: "trend", $areaName: hasCompare ? `A / ${d.region.name}` : s.variable.name, $unit: s.variable.unit,
      borderColor: observedColor,
      borderDash: AREA_D.a,
      borderWidth: 1.7,
      pointRadius: 0,
      fill: false,
      tension: 0,
    });
    if (hasCompare && sB) {
      const oB = sB.overall || {};
      let lineB;
      if (oB.ok) {
        const slopeB = oB.slope * (isYear ? 1 : 1 / 12);
        const midB = valsB.filter((v) => v !== null && Number.isFinite(v)).reduce((a, v) => a + v, 0) /
          Math.max(1, valsB.filter((v) => v !== null && Number.isFinite(v)).length);
        const midIdxB = (valsB.length - 1) / 2;
        lineB = (x) => midB + slopeB * (x - midIdxB);
      } else {
        const ptsB = valsB.map((v, i) => [i, v]).filter((p) => p[1] !== null && Number.isFinite(p[1]));
        lineB = ptsB.length > 2 ? fitLine(ptsB) : null;
      }
      if (lineB) {
        datasets.push({
          label: `B / ${d.compare.region.name} · fitted trend`,
          data: valsB.map((_, i) => (partialFlagsB[i] ? null : lineB(i))),
          $side: "b", $kind: "trend", $areaName: `B / ${d.compare.region.name}`, $unit: sB.variable.unit,
          borderColor: AREA_C.b,
          borderDash: AREA_D.b,
          borderWidth: 1.7,
          pointRadius: 0,
          fill: false,
          tension: 0,
        });
      }
    }
  }

  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(8,9,10,.97)",
          borderColor: "#505663",
          borderWidth: 1,
          titleFont: { family: "monospace", size: 10, weight: "bold" },
          bodyFont: { family: "monospace", size: 10 },
          titleColor: "#ffffff",
          bodyColor: "#dbe0e6",
          displayColors: false,
          callbacks: {
            label: (c) => chartTooltipLabel(c, s.variable.unit, s.variable.name),
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#a6adb5",
            maxTicksLimit: isYear ? 8 : 6,
            maxRotation: 0,
            font: { family: "monospace", size: 10, weight: "500" },
            callback: function (val) {
              const raw = this.getLabelForValue(val);
              return isYear ? String(raw).slice(2) : String(raw).slice(0, 4);
            },
          },
          grid: { color: "#242830", tickLength: 3 },
          border: { color: "#3d434d" },
        },
        y: {
          ticks: {
            color: "#a6adb5",
            maxTicksLimit: 5,
            font: { family: "monospace", size: 10, weight: "500" },
          },
          grid: { color: "#242830", tickLength: 3 },
          border: { color: "#3d434d" },
        },
      },
    },
  });

}

function fitLine(pts) {
  const n = pts.length;
  const mx = pts.reduce((s, p) => s + p[0], 0) / n;
  const my = pts.reduce((s, p) => s + p[1], 0) / n;
  let a = 0, b = 0;
  for (const [x, y] of pts) {
    a += (x - mx) * (y - my);
    b += (x - mx) ** 2;
  }
  const m = b === 0 ? 0 : a / b;
  return (x) => my + m * (x - mx);
}

/* ============================================================
   HELPERS
   ============================================================ */
function num(x, d = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return Number(x).toFixed(d);
}
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* ============================================================
   3D GLOBE
   ============================================================ */
const R = 1;
let renderer, scene, camera, globeGroup;
let teleconArcsGroup;
let arcPackets = [];   // travelling packets along teleconnection arcs
let arcRings = [];     // pulsing destination rings
let landPoints, gridLines, regionMesh, haloMesh, atmosphere, pickSphere;
// ring drawn for a region click that has not finished analysing yet
let previewRing = null;
let dragState = null;
let autoRotate = true;
let regionMarkers = [];
let landData = [];
let raycaster, pointer;
let lastPointer = { x: 0, y: 0 };

function latLonToVec3(lat, lon, radius) {
  const phi = (90 - lat) * Math.PI / 180;
  const theta = (lon + 180) * Math.PI / 180;
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  );
}

function bboxCenter(bbox, radius) {
  const lon = (bbox[0] + bbox[2]) / 2;
  const lat = (bbox[1] + bbox[3]) / 2;
  return latLonToVec3(lat, lon, radius);
}

async function initGlobe() {
  const host = $("globe");
  const w = host.clientWidth || 700;
  const h = host.clientHeight || 520;

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, w / h, 0.1, 100);
  camera.position.set(0, 0, 3.35);

  renderer = new THREE.WebGLRenderer({
    // no MSAA: a full-bleed globe at DPR 2 with multisampling stalls
    // integrated / software GL, and the soft shader edges do not need it
    antialias: false, alpha: true, powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(w, h);
  host.appendChild(renderer.domElement);

  globeGroup = new THREE.Group();
  globeGroup.rotation.y = -0.6;
  scene.add(globeGroup);

  teleconArcsGroup = new THREE.Group();
  globeGroup.add(teleconArcsGroup);

  try {
    const r = await fetch("land_dots.json");
    landData = await r.json();
  } catch (e) {
    landData = [];
  }

  buildLandDots();
  buildGridLines();
  buildGlobeLabels();
  buildAtmosphere();
  buildRegionMesh();
  buildEarthSurface();
  buildClouds();
  buildStarfield();

  // the photographic globe is the default; fall back to dots if textures fail
  initGlobeModeMenu();
  // dots while the texture is still loading; skip if it already landed
  if (textureState !== "ready") applyGlobeStyle();

  // invisible sphere used to convert a click into a lat/lon.
  // Radius matches the visible surface (0.999): at 0.995 its silhouette fell
  // just inside the planet's, leaving a thin unclickable band at the limb.
  pickSphere = new THREE.Mesh(
    new THREE.SphereGeometry(1.0, 32, 32),
    new THREE.MeshBasicMaterial({ visible: false })
  );
  globeGroup.add(pickSphere);

  raycaster = new THREE.Raycaster();
  raycaster.params.Points.threshold = 0.03;
  pointer = new THREE.Vector2();

  bindGlobeEvents(host);
  animateGlobe();

  const ro = new ResizeObserver(() => {
    const nw = host.clientWidth, nh = host.clientHeight;
    if (!nw || !nh) return;
    camera.aspect = nw / nh;
    camera.updateProjectionMatrix();
    renderer.setSize(nw, nh);
  });
  ro.observe(host);

  updateGlobeOverlay();
}

/* ---------- country-style labels hovering on the globe ----------
   The cybermap names the places it is watching. We do the same with the
   23 focus regions: each label is a DOM node projected from the sphere
   every frame, so it stays put while the planet turns underneath it. */
let labelEls = [];       // { el, lat, lon, name }

function buildGlobeLabels() {
  const layer = $("globe-labels");
  if (!layer) return;
  layer.innerHTML = "";
  labelEls = [];

  const regions = (state.catalog && state.catalog.regions) || [];
  if (!regions.length) return;

  const frag = document.createDocumentFragment();
  for (const r of regions) {
    const lat = (r.bbox[1] + r.bbox[3]) / 2;
    const lon = (r.bbox[0] + r.bbox[2]) / 2;
    const el = document.createElement("span");
    el.className = "globe-label";
    el.dataset.region = r.id;
    el.textContent = r.name.toUpperCase();
    frag.appendChild(el);
    labelEls.push({ el, lat, lon, id: r.id });
  }
  layer.appendChild(frag);
}

function updateGlobeLabels() {
  if (!labelEls.length || !camera || !globeGroup) return;
  const host = $("globe");
  if (!host) return;
  const w = host.clientWidth, h = host.clientHeight;
  if (!w || !h) return;

  const camDir = camera.position.clone().normalize();
  const tmp = new THREE.Vector3();

  // which region is the user currently looking at?
  const regSel = $("region");
  const activeId = regSel ? regSel.value : null;

  for (const L of labelEls) {
    const on = L.id === activeId;
    if (L.el.classList.contains("is-active") !== on) {
      L.el.classList.toggle("is-active", on);
    }
    tmp.copy(latLonToVec3(L.lat, L.lon, 1.0)).applyMatrix4(globeGroup.matrixWorld);
    const facing = tmp.clone().normalize().dot(camDir);

    tmp.project(camera);
    const x = (tmp.x * 0.5 + 0.5) * w;
    const y = (-tmp.y * 0.5 + 0.5) * h;

    // fade out across the limb so labels never smear on the horizon
    const k = Math.max(0, Math.min(1, (facing - 0.06) / (0.34 - 0.06)));
    let a = k * k * (3 - 2 * k);
    if (Math.abs(tmp.x) > 1.4 || Math.abs(tmp.y) > 1.4) a = 0;

    const st = L.el.style;
    if (a <= 0.01) {
      if (st.display !== "none") st.display = "none";
      continue;
    }
    if (st.display === "none") st.display = "block";
    st.transform = `translate(-50%,-50%) translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
    st.opacity = a.toFixed(2);
  }
}

function buildLandDots() {
  const count = landData.length;
  const pos = new Float32Array(count * 3);
  const col = new Float32Array(count * 3);
  const base = new THREE.Color(C.land);
  const dim = new THREE.Color(C.landDim);

  for (let i = 0; i < count; i++) {
    const [lat, lon] = landData[i];
    const v = latLonToVec3(lat, lon, R);
    pos[i * 3] = v.x;
    pos[i * 3 + 1] = v.y;
    pos[i * 3 + 2] = v.z;
    const mix = Math.random();
    const c = base.clone().lerp(dim, mix * 0.45);
    col[i * 3] = c.r;
    col[i * 3 + 1] = c.g;
    col[i * 3 + 2] = c.b;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));

  const mat = new THREE.PointsMaterial({
    size: 0.0145,
    vertexColors: true,
    transparent: true,
    opacity: 1,
    sizeAttenuation: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
  });
  landPoints = new THREE.Points(geo, mat);
  landPoints.renderOrder = 3;
  globeGroup.add(landPoints);
}

function buildGridLines() {
  const mat = new THREE.LineBasicMaterial({
    color: C.globeLine, transparent: true, opacity: 0.5,
  });
  gridLines = [];

  for (let lat = -60; lat <= 60; lat += 30) {
    const pts = [];
    for (let lon = -180; lon <= 180; lon += 3) {
      pts.push(latLonToVec3(lat, lon, R * 0.999));
    }
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts), mat);
    gridLines.push(line);
    globeGroup.add(line);
  }
  for (let lon = -180; lon < 180; lon += 30) {
    const pts = [];
    for (let lat = -90; lat <= 90; lat += 3) {
      pts.push(latLonToVec3(lat, lon, R * 0.999));
    }
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts), mat);
    gridLines.push(line);
    globeGroup.add(line);
  }
}

/* ---------- stylized "blue relief" Earth ----------
   Real, sharp coastlines from NASA topology data, recoloured the way the
   reference dashboard does it: ice-blue land that brightens with elevation,
   deep blue sea. Lit gently for roundness - no day/night terminator. */
const EARTH_TEXTURES = {
  topo: "vendor/earth-topology.png",
};
let earthMesh = null;
let cloudMesh = null;
let starField = null;
let textureState = "idle";   // idle | loading | ready | failed
let globeStyle = "relief";   // what the user wants
let appliedStyle = "dots";   // what is actually on screen

// remember the last chosen mode across reloads
try {
  const saved = window.localStorage.getItem("tt-globe-style");
  if (saved === "dots" || saved === "relief") globeStyle = saved;
} catch (e) { /* private mode / storage disabled: keep the default */ }

function buildEarthSurface() {
  textureState = "loading";
  const loader = new THREE.TextureLoader();
  loader.setCrossOrigin("anonymous");

  const onFail = () => {
    // no textures (offline / CDN blocked): quietly stay on the dot globe
    textureState = "failed";
    applyGlobeStyle("dots");
  };

  const topo = loader.load(EARTH_TEXTURES.topo, () => {
    textureState = "ready";
    // defer one frame: on a cached texture this callback can beat initGlobe's
    // initial applyGlobeStyle(), which would then reset the globe to dots
    requestAnimationFrame(() => applyGlobeStyle());
  }, undefined, onFail);
  // data mask: sample raw values, no colour-space conversion
  topo.colorSpace = THREE.NoColorSpace;
  topo.anisotropy = 4;

  earthMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.999, 72, 48),
    new THREE.ShaderMaterial({
      uniforms: {
        uTopo: { value: topo },
        uSunDir: { value: new THREE.Vector3(0.55, 0.30, 0.78).normalize() },
      },
      vertexShader: `
        varying vec2 vUv;
        varying vec3 vNormalW;
        varying vec3 vViewDirW;
        void main() {
          vUv = uv;
          vec4 wp = modelMatrix * vec4(position, 1.0);
          vNormalW = normalize(mat3(modelMatrix) * normal);
          vViewDirW = normalize(cameraPosition - wp.xyz);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        uniform sampler2D uTopo;
        uniform vec3 uSunDir;
        varying vec2 vUv;
        varying vec3 vNormalW;
        varying vec3 vViewDirW;

        // Terrain tones measured off the cybermap feed: a lifted grey-olive
        // world rather than a black one. Lands sit near #4a544d, seas near
        // #1b2620, and the lit limb picks up mint.
        const vec3 cShadow = vec3(0.110, 0.157, 0.129);  // #1c2821
        const vec3 cOcean  = vec3(0.169, 0.235, 0.200);  // #2b3c33
        const vec3 cLand   = vec3(0.365, 0.459, 0.384);  // #5d7562
        const vec3 cLit    = vec3(0.643, 0.780, 0.675);  // #a4c7ac
        const vec3 cRim    = vec3(0.800, 0.914, 0.839);  // #cce9d6

        void main() {
          // topology: 0 = ocean, higher = land elevation (0..~0.55 typical)
          float elev = texture2D(uTopo, vUv).r;

          // crisp coastlines
          float landMask = smoothstep(0.028, 0.075, elev);

          // base land -> illuminated terrain with elevation
          vec3 landCol = mix(cLand, cLit, smoothstep(0.08, 0.72, elev));
          // thin bright coastline band
          float coast = smoothstep(0.045, 0.09, elev)
                      * (1.0 - smoothstep(0.09, 0.20, elev));
          landCol = mix(landCol, cLit, coast * 0.85);

          // deep ocean, faint coastal shelf lifting toward the land tone
          vec3 seaCol = mix(cOcean, mix(cOcean, cLand, 0.45),
                            smoothstep(0.004, 0.05, elev));

          vec3 col = mix(seaCol, landCol, landMask);

          vec3 n = normalize(vNormalW);
          vec3 L = normalize(uSunDir);
          float lam = dot(n, L);

          // matte directional falloff: the far limb sinks into deep space
          col = mix(cShadow, col, smoothstep(-0.12, 0.42, lam));

          // high-contrast fresnel rim on the sunlit edge
          float ndv = max(dot(n, normalize(vViewDirW)), 0.0);
          float fres = pow(1.0 - ndv, 2.4);
          float litMask = smoothstep(0.05, 0.55, lam);
          col = mix(col, cRim, fres * litMask * 0.45);

          gl_FragColor = vec4(col, 1.0);
        }`,
    }),
  );
  earthMesh.visible = false;
  globeGroup.add(earthMesh);
}

/* drifting procedural cloud layer (fbm noise - no texture asset) */
function buildClouds() {
  cloudMesh = new THREE.Mesh(
    new THREE.SphereGeometry(1.012, 48, 32),
    new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: { uTime: { value: 0 } },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `
        varying vec2 vUv;
        uniform float uTime;
        float hash(vec2 p) {
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
        }
        float noise(vec2 p) {
          vec2 i = floor(p), f = fract(p);
          vec2 u = f * f * (3.0 - 2.0 * f);
          return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
                     mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
                     u.y);
        }
        float fbm(vec2 p) {
          float v = 0.0, a = 0.5;
          for (int i = 0; i < 5; i++) {
            v += a * noise(p);
            p = p * 2.1 + vec2(1.7, 0.3);
            a *= 0.5;
          }
          return v;
        }
        void main() {
          vec2 p = vec2(vUv.x * 7.0, vUv.y * 3.6);
          p.x += uTime * 0.012;
          float c = fbm(p);
          // wispy shapes: two noise octaves, thresholded softly
          float shape = smoothstep(0.52, 0.85, c);
          // band the clouds toward the tropics and mid-latitudes
          float latBand = smoothstep(0.02, 0.16, abs(vUv.y - 0.5))
                        * (1.0 - smoothstep(0.38, 0.5, abs(vUv.y - 0.5)));
          float a = shape * latBand * 0.62;
          vec3 col = vec3(0.576, 0.792, 0.678);  // #93CAB0 mint haze
          gl_FragColor = vec4(col, a);
        }`,
    }),
  );
  cloudMesh.visible = false;
  globeGroup.add(cloudMesh);
}

function buildStarfield() {
  const COUNT = 1600;
  const pos = new Float32Array(COUNT * 3);
  for (let i = 0; i < COUNT; i++) {
    const r = 16 + Math.random() * 24;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = r * Math.cos(phi);
    pos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  starField = new THREE.Points(geo, new THREE.PointsMaterial({
    color: 0x628b74, size: 0.055, sizeAttenuation: true,
    transparent: true, opacity: 0.30, depthWrite: false,
  }));
  starField.visible = false;
  scene.add(starField);
}

/* switch between the blue-relief Earth and the original dot matrix.
   Call with no argument to (re)apply whatever the user last chose. */
function applyGlobeStyle(style) {
  if (style) globeStyle = style;
  const wantRelief = globeStyle === "relief" && textureState === "ready";
  appliedStyle = wantRelief ? "relief" : "dots";

  if (landPoints) landPoints.visible = !wantRelief;
  if (earthMesh) earthMesh.visible = wantRelief;
  if (cloudMesh) cloudMesh.visible = wantRelief;
  if (haloMesh) haloMesh.visible = !wantRelief;
  if (starField) starField.visible = wantRelief;
  if (Array.isArray(gridLines)) {
    gridLines.forEach((line) => { line.visible = !wantRelief; });
  }

  // keep the map rail button in step with the active render mode
  const mcStyle = $("mc-style");
  if (mcStyle) mcStyle.classList.toggle("on", appliedStyle === "relief");

  // sync the dropdown
  const value = $("globe-style-value");
  if (value) {
    value.textContent = appliedStyle === "relief" ? "EARTH RELIEF" : "DOT MATRIX";
  }
  document.querySelectorAll(".gm-option").forEach((opt) => {
    const on = opt.dataset.style === appliedStyle;
    opt.classList.toggle("on", on);
    opt.setAttribute("aria-selected", on ? "true" : "false");
    if (opt.dataset.style === "relief") {
      // no textures (offline / CDN blocked): offer the mode but explain
      opt.disabled = textureState !== "ready";
      const desc = opt.querySelector(".gm-desc");
      if (desc) {
        desc.textContent = textureState === "ready"
          ? "lit sphere · olive terrain"
          : "needs the CDN textures — unavailable offline";
      }
    }
  });
}

function initGlobeModeMenu() {
  const trigger = $("globe-style-btn");
  const menu = $("globe-style-menu");
  const wrap = $("globe-mode");
  if (!trigger || !menu || !wrap) return;

  const setOpen = (open) => {
    menu.hidden = !open;
    wrap.classList.toggle("open", open);
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
  };

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    setOpen(menu.hidden);
  });

  menu.querySelectorAll(".gm-option").forEach((opt) => {
    opt.addEventListener("click", (e) => {
      e.stopPropagation();
      if (opt.disabled) return;
      applyGlobeStyle(opt.dataset.style);
      try {
        window.localStorage.setItem("tt-globe-style", opt.dataset.style);
      } catch (err) { /* storage unavailable: not fatal */ }
      setOpen(false);
    });
  });

  document.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setOpen(false);
  });
  menu.addEventListener("click", (e) => e.stopPropagation());
}

function buildAtmosphere() {
  const geo = new THREE.SphereGeometry(1.10, 48, 48);
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: { uColor: { value: new THREE.Color("#629c7f") } },
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vPos;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vPos = (modelViewMatrix * vec4(position,1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
      }`,
    fragmentShader: `
      uniform vec3 uColor;
      varying vec3 vNormal;
      varying vec3 vPos;
      void main() {
        float rim = 1.0 - abs(dot(vNormal, normalize(-vPos)));
        float a = pow(rim, 3.0) * 0.30;
        gl_FragColor = vec4(uColor, a);
      }`,
  });
  atmosphere = new THREE.Mesh(geo, mat);
  scene.add(atmosphere);

  haloMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.985, 48, 48),
    new THREE.MeshBasicMaterial({ color: 0x050907 })
  );
  haloMesh.renderOrder = -2;
  globeGroup.add(haloMesh);
}

function buildRegionMesh() {
  regionMesh = new THREE.Mesh(
    new THREE.BoxGeometry(0.055, 0.055, 0.055),
    new THREE.MeshBasicMaterial({
      color: 0xffa726, transparent: true, opacity: 0.9,
    })
  );
  regionMesh.scale.set(1, 1, 1);
  globeGroup.add(regionMesh);
}

/* A ring drawn ON the sphere surface (constant angular radius around a centre
   direction). A flat disc only works when you look straight at the region:
   near the limb the sphere curves away and corner cells spill outside it. */
function makeSphericalRing(center, angRad, thickness, radius, segments = 96) {
  const c = center.clone().normalize();
  const up = Math.abs(c.y) > 0.9
    ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  const u = new THREE.Vector3().crossVectors(up, c).normalize();
  const v = new THREE.Vector3().crossVectors(c, u).normalize();

  const inner = Math.max(0.001, angRad - thickness);
  const positions = [];
  const indices = [];

  for (let i = 0; i <= segments; i++) {
    const t = (i / segments) * Math.PI * 2;
    for (const ar of [inner, angRad]) {
      const dir = c.clone().multiplyScalar(Math.cos(ar))
        .add(u.clone().multiplyScalar(Math.cos(t) * Math.sin(ar)))
        .add(v.clone().multiplyScalar(Math.sin(t) * Math.sin(ar)))
        .normalize();
      positions.push(dir.x * radius, dir.y * radius, dir.z * radius);
    }
  }
  for (let i = 0; i < segments; i++) {
    const a = i * 2, b = i * 2 + 1, c2 = (i + 1) * 2, d = (i + 1) * 2 + 1;
    indices.push(a, c2, b, b, c2, d);
  }

  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  g.setIndex(indices);
  return g;
}

const REGION_MAG = 1.0; // visually amplify the small region so cells are readable

/* The selection ring around a lat/lon bbox. The analysed result and the
   optimistic preview both draw through here, so the ring does not jump when
   the response lands. */
function makeSelectionRingMesh(bbox, color = 0xf0f2f4, opacity = 0.7) {
  const bw = Math.abs(bbox[2] - bbox[0]) * REGION_MAG;
  const bh = Math.abs(bbox[3] - bbox[1]) * REGION_MAG;
  // The amplified grid reaches to the CORNERS of the box, so the radius must
  // come from the half-diagonal, and the ring follows the sphere so it keeps
  // enclosing the cells even when the region sits near the limb.
  const angRad = Math.hypot(bw / 2, bh / 2) * Math.PI / 180 * 1.12;
  const c0 = bboxCenter(bbox, 1);
  const geo = makeSphericalRing(
    c0, angRad, Math.max(0.006, angRad * 0.08), 1.06);
  const mat = new THREE.MeshBasicMaterial({
    color, side: THREE.DoubleSide, transparent: true,
    opacity, depthWrite: false,
    // depth-tested: the ring is a curve on the sphere, so it must be hidden
    // by the planet when the region rotates round the back. Disabling this
    // made it float across the face as the globe turned.
    depthTest: true,
  });
  const ring = new THREE.Mesh(geo, mat);
  ring.renderOrder = 9;
  ring.userData = { pulsing: true };
  return ring;
}

/* ---------- interactive region markers ---------- */
function renderGlobeRegions(d) {
  regionMarkers.forEach((m) => globeGroup.remove(m));
  regionMarkers = [];
  previewRing = null;

  if (!d) return;

  // Rotate the globe so the selected region faces the camera.
  if (d.region && d.region.bbox) {
    const bbox = d.region.bbox;
    const lon = (bbox[0] + bbox[2]) / 2;
    const lat = (bbox[1] + bbox[3]) / 2;
    // latLonToVec3 puts lon L at world (cos L, sin lat, -sin L), so a Y
    // rotation of -(L + 90 deg) brings it to +Z (facing the camera).
    const targetY = -(lon * Math.PI / 180) - Math.PI / 2;
    const targetX = lat * Math.PI / 180;
    animateGlobeTo(targetX, targetY);
  }

  const bbox = d.grid.bbox;
  const lon0 = Math.min(bbox[0], bbox[2]);
  const lon1 = Math.max(bbox[0], bbox[2]);
  const lat0 = Math.min(bbox[1], bbox[3]);
  const lat1 = Math.max(bbox[1], bbox[3]);

  const MAG = REGION_MAG; // visually amplify the small region so cells are readable
  const cLat0 = (Math.min(bbox[1], bbox[3]) + Math.max(bbox[1], bbox[3])) / 2;
  const cLon0 = (Math.min(bbox[0], bbox[2]) + Math.max(bbox[0], bbox[2])) / 2;

  d.series.forEach((s, si) => {
    const v = s.variable;
    const isActive = si === state.activeVarIdx;
    const alt = isActive ? 1.055 : 1.015;
    s.cells.forEach((c) => {
      if (c.slope === null) return;
      const colour = !c.significant
        ? "#3a3f45"
        : (c.direction === "falling" ? C.fall : C.rise);

      // marked down for the textured globe: the old sizes were tuned for the
      // dot matrix and read as blobs on top of real terrain
      const base = isActive ? 0.0105 : 0.005;
      const size = base + Math.min(isActive ? 0.0085 : 0.0025,
        Math.abs(c.slope) * 0.02);
      const geo = new THREE.SphereGeometry(size, 10, 10);
      const mat = new THREE.MeshBasicMaterial({
        color: colour,
        transparent: true,
        opacity: isActive ? (c.significant ? 1 : 0.45) : 0.28,
      });
      const dot = new THREE.Mesh(geo, mat);
      const pLat = cLat0 + (c.lat - cLat0) * MAG;
      const pLon = cLon0 + (c.lon - cLon0) * MAG;
      dot.position.copy(latLonToVec3(pLat, pLon, R * alt));
      dot.userData = { cell: c, variable: v, active: isActive };
      dot.renderOrder = isActive ? 8 : 4;
      globeGroup.add(dot);
      regionMarkers.push(dot);
    });
  });

  // pulsing ring bounding the analyzed region
  const ring = makeSelectionRingMesh(d.grid.bbox);
  globeGroup.add(ring);
  regionMarkers.push(ring);

  // If Regional Contrast Mode is active, render Region B markers and pulsing cyan ring
  if (d.compare && d.compare.series && d.compare.region && d.compare.region.bbox) {
    const sB = d.compare.series[state.activeVarIdx] || d.compare.series[0];
    const bboxB = d.compare.region.bbox;
    const cLatB = (Math.min(bboxB[1], bboxB[3]) + Math.max(bboxB[1], bboxB[3])) / 2;
    const cLonB = (Math.min(bboxB[0], bboxB[2]) + Math.max(bboxB[0], bboxB[2])) / 2;

    sB.cells.forEach((c) => {
      if (c.slope === null) return;
      const colour = !c.significant ? "#2a3d45" : (c.direction === "falling" ? "#29b6f6" : "#00e5ff");
      const geo = new THREE.SphereGeometry(0.016, 8, 8);
      const mat = new THREE.MeshBasicMaterial({
        color: colour,
        transparent: true,
        opacity: c.significant ? 0.95 : 0.4,
      });
      const dot = new THREE.Mesh(geo, mat);
      const pLat = cLatB + (c.lat - cLatB) * MAG;
      const pLon = cLonB + (c.lon - cLonB) * MAG;
      dot.position.copy(latLonToVec3(pLat, pLon, R * 1.055));
      dot.userData = { cell: c, variable: sB.variable, compare: true };
      dot.renderOrder = 8;
      globeGroup.add(dot);
      regionMarkers.push(dot);
    });

    // same geometry path as region A, so contrast mode agrees
    const ringB = makeSelectionRingMesh(bboxB, 0x00e5ff, 0.85);
    globeGroup.add(ringB);
    regionMarkers.push(ringB);
  }
}

function updateGlobeOverlay() {
  const n = state.selected.length;
  const g = $("globe-title");
  if (n === 0) {
    g.querySelector(".gt-main").textContent = "EARTH";
    g.querySelector(".gt-sub").textContent =
      "NO VARIABLE SELECTED · PICK ONE TO BEGIN";
  } else if (n === 1) {
    const v = state.catalog.variables.find((x) => x.id === state.selected[0]);
    g.querySelector(".gt-main").textContent = v ? v.name.toUpperCase() : "EARTH";
    g.querySelector(".gt-sub").textContent =
      `${v ? v.mission : ""} · SINGLE VARIABLE`;
  } else {
    g.querySelector(".gt-main").textContent = `${n} VARIABLES`;
    g.querySelector(".gt-sub").textContent = "MULTI-LAYER COMPOSITE";
  }
}

/* ---------- events ---------- */
function bindGlobeEvents(host) {
  const tip = document.createElement("div");
  tip.className = "globe-tip";
  tip.style.display = "none";
  document.body.appendChild(tip);

  host.addEventListener("pointerdown", (e) => {
    dragState = {
      x: e.clientX, y: e.clientY,
      rotX: globeGroup.rotation.x,
      rotY: globeGroup.rotation.y,
      moved: false,
    };
    autoRotate = false;
    host.setPointerCapture(e.pointerId);
  });

  host.addEventListener("pointermove", (e) => {
    lastPointer = { x: e.clientX, y: e.clientY };

    if (dragState) {
      const dx = e.clientX - dragState.x;
      const dy = e.clientY - dragState.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) dragState.moved = true;
      globeGroup.rotation.y = dragState.rotY + dx * 0.006;
      globeGroup.rotation.x = Math.max(-1.1, Math.min(1.1,
        dragState.rotX + dy * 0.006));
      tip.style.display = "none";
      return;
    }

    const hit = pickGlobe(e);
    if (hit && hit.object.userData.cell) {
      const c = hit.object.userData.cell;
      const v = hit.object.userData.variable;
      const dir = c.significant
        ? (c.direction === "rising" ? "RISING" : "FALLING")
        : "NO TREND";
      tip.innerHTML = `
        <div class="tt-h">${esc(v.name)}</div>
        <div class="tt-row"><span>LAT</span><b>${c.lat.toFixed(2)}°</b></div>
        <div class="tt-row"><span>LON</span><b>${c.lon.toFixed(2)}°</b></div>
        <div class="tt-row"><span>SLOPE</span><b>${c.slope > 0 ? "+" : ""}${num(c.slope * 10, 3)} ${esc(v.unit)}/dec</b></div>
        <div class="tt-row"><span>p</span><b>${c.p === undefined ? "—" : num(c.p, 3)}</b></div>
        <div class="tt-row"><span>TREND</span><b style="color:${c.significant ? (c.direction === "falling" ? C.fall : C.rise) : "#b4bac2"}">${dir}</b></div>`;
      tip.style.display = "block";
      tip.style.left = Math.min(window.innerWidth - 220, e.clientX + 14) + "px";
      tip.style.top = Math.min(window.innerHeight - 130, e.clientY + 14) + "px";
      host.style.cursor = "pointer";
    } else {
      tip.style.display = "none";
      host.style.cursor = dragState ? "grabbing" : "grab";
    }
  });

  const endDrag = (e) => {
    if (dragState && !dragState.moved) {
      const hit = pickGlobe(e);
      if (hit && hit.object.userData.cell) {
        showCellDetail(hit.object.userData);
      } else {
        const ll = pickLatLon(e);
        if (ll) {
          $("coord-readout").textContent =
            `LAT ${ll.lat.toFixed(2)} · LON ${ll.lon.toFixed(2)}`;
          selectNearestRegion(ll.lat, ll.lon);
        }
      }
    }
    dragState = null;
    tip.style.display = "none";
    host.style.cursor = "grab";
  };
  host.addEventListener("pointerup", endDrag);
  host.addEventListener("pointerleave", () => {
    tip.style.display = "none";
    dragState = null;
  });
  host.addEventListener("wheel", (e) => {
    e.preventDefault();
    camera.position.z = Math.max(2.1, Math.min(5.2,
      camera.position.z + e.deltaY * 0.0015));
  }, { passive: false });

  window.addEventListener("resize", () => {
    const nw = host.clientWidth, nh = host.clientHeight;
    if (nw && nh) {
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    }
  });

  host.addEventListener("dblclick", () => {
    autoRotate = true;
    camera.position.z = 3.35;
  });
}

function pickGlobe(e) {
  if (!raycaster) return null;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(regionMarkers, false);
  return hits.length ? hits[0] : null;
}

/* Convert a screen click into a lat/lon on the globe surface. */
function pickLatLon(e) {
  if (!raycaster || !pickSphere) return null;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObject(pickSphere, false);
  if (!hits.length) return null;
  const p = globeGroup.worldToLocal(hits[0].point.clone());
  const r = p.length() || 1;
  const phi = Math.acos(Math.max(-1, Math.min(1, p.y / r)));
  const theta = Math.atan2(p.z, -p.x);
  let lon = theta * 180 / Math.PI - 180;
  lon = ((lon + 540) % 360) - 180;
  return { lat: 90 - phi * 180 / Math.PI, lon };
}

/* The ring drawn for a pick that has not finished analysing yet. */
function clearPreviewRing() {
  if (!previewRing) return;
  if (previewRing.parent) previewRing.parent.remove(previewRing);
  const i = regionMarkers.indexOf(previewRing);
  if (i >= 0) regionMarkers.splice(i, 1);
  previewRing = null;
}

/* Answer a region pick immediately: ring on the sphere and a camera turn,
   both before /api/analyze resolves, so the globe never feels unresponsive. */
function previewRegionSelection(region) {
  if (!globeGroup || !region || !region.bbox) return;
  clearPreviewRing();

  // If this region is already analysed its real ring is on the sphere; drawing
  // a preview on top would just double the outline.
  const alreadyDrawn = state.result && state.result.region
    && state.result.region.id === region.id
    && regionMarkers.some((m) => m.userData && m.userData.pulsing && !m.userData.optimistic);

  if (!alreadyDrawn) {
    const ring = makeSelectionRingMesh(region.bbox, 0xf0f2f4, 0.55);
    ring.userData.optimistic = true;
    globeGroup.add(ring);
    regionMarkers.push(ring);
    previewRing = ring;
  }

  const bbox = region.bbox;
  const lon = (bbox[0] + bbox[2]) / 2;
  const lat = (bbox[1] + bbox[3]) / 2;
  // same maths renderGlobeRegions uses, so the camera does not jump later
  animateGlobeTo(lat * Math.PI / 180, -(lon * Math.PI / 180) - Math.PI / 2);
}

/* Update every piece of region UI that does not depend on the analysis. */
function applyRegionSelection(region) {
  const desc = $("region-desc");
  const readout = $("region-readout");
  if (!region) {
    if (desc) desc.textContent = "";
    if (readout) readout.textContent = "NO REGION SELECTED";
    updateGlobeOverlay();
    return;
  }
  if (desc) desc.textContent = region.desc || "";
  if (readout) readout.textContent = region.name.toUpperCase();
  updateGlobeOverlay();
  if (regionMesh) regionMesh.position.copy(bboxCenter(region.bbox, 1.005));
  previewRegionSelection(region);
}

/* Tap the globe -> analyse the area actually clicked.
   If the click lands inside a preset focus region, use that preset (it has a
   curated description). Otherwise build a real 4-degree box around the click
   and send it as a bbox, so the answer is about the place the user pointed at
   rather than the nearest of 23 unrelated boxes. */
function selectNearestRegion(lat, lon) {
  let inside = null;
  state.catalog.regions.forEach((r) => {
    const b = r.bbox;
    if (lon >= b[0] && lon <= b[2] && lat >= b[1] && lat <= b[3]) inside = r;
  });

  const HALF = 2.0;  // 4 x 4 degree box around the click
  const lon0 = Math.max(-180, lon - HALF);
  const lon1 = Math.min(180, lon + HALF);
  const lat0 = Math.max(-89, lat - HALF);
  const lat1 = Math.min(89, lat + HALF);

  const target = inside || {
    id: "custom",
    name: "Selected Area",
    desc: `${lat.toFixed(1)}\u00b0, ${lon.toFixed(1)}\u00b0 \u00b7 ${(lon1 - lon0).toFixed(1)}\u00d7${(lat1 - lat0).toFixed(1)}\u00b0 box`,
    bbox: [lon0, lat0, lon1, lat1],
    custom: true,
  };

  const sel = $("region");
  const changed = !sel || sel.value !== target.id;
  if (sel && !target.custom) sel.value = target.id;

  state.pendingBbox = target.custom ? target.bbox : null;

  // optimistic: the globe answers the click before the network does
  applyRegionSelection(target);

  if (!state.selected.length) {
    flashHint(`${target.name.toUpperCase()} SELECTED — PICK A VARIABLE`);
    return;
  }
  if (changed || !state.result || target.custom) {
    flashHint(`${target.name.toUpperCase()} SELECTED — ANALYZING`);
    analyze();
  } else {
    // clicking inside the region already on screen must still acknowledge
    flashHint(`${target.name.toUpperCase()} SELECTED`);
  }
}

let hintTimer = null;
function flashHint(text) {
  const el = $("globe-hint");
  if (!el) return;
  const original = "DRAG TO ROTATE · CLICK A REGION TO ANALYZE";
  el.style.color = "#f0f2f4";
  el.innerHTML = `<span class="gh-dot"></span>${text}`;
  clearTimeout(hintTimer);
  hintTimer = setTimeout(() => {
    el.style.color = "";
    el.innerHTML = `<span class="gh-dot"></span>${original}`;
  }, 2600);
}

function showCellDetail(hit) {
  const c = hit.cell;
  const v = hit.variable;
  $("globe-title").querySelector(".gt-main").textContent =
    `${v.name.toUpperCase()}`;
  $("globe-title").querySelector(".gt-sub").textContent =
    `CELL ${c.lat.toFixed(1)}°, ${c.lon.toFixed(1)}° · ${c.significant
      ? (c.direction === "rising" ? "SIGNIFICANT RISE" : "SIGNIFICANT FALL")
      : "NO SIGNIFICANT TREND"}`;
  $("coord-readout").textContent =
    `LAT ${c.lat.toFixed(2)} · LON ${c.lon.toFixed(2)}`;

  const cellBbox = [c.lon - 0.4, c.lat - 0.4, c.lon + 0.4, c.lat + 0.4];
  state.selectedCellBbox = cellBbox;
  const cbBtn = $("coord-sat-btn");
  const cbSep = $("coord-sat-sep");
  if (cbBtn) {
    cbBtn.hidden = false;
    cbBtn.textContent = `CELL (${c.lat.toFixed(1)}°, ${c.lon.toFixed(1)}°)`;
    cbBtn.onclick = () => openSatelliteModal(cellBbox, `CELL [${c.lat.toFixed(1)}°, ${c.lon.toFixed(1)}°]`);
  }
  if (cbSep) cbSep.hidden = false;
}

/* ---------- animation ---------- */
let globeTween = null;

function animateGlobeTo(targetX, targetY) {
  autoRotate = false;
  globeTween = {
    fromX: globeGroup.rotation.x,
    fromY: globeGroup.rotation.y,
    toX: targetX,
    toY: targetY,
    t: 0,
    dur: 900,
    start: performance.now(),
  };
}

function animateGlobe() {
  requestAnimationFrame(animateGlobe);

  if (globeTween) {
    const p = Math.min(1, (performance.now() - globeTween.start) / globeTween.dur);
    const e = 1 - Math.pow(1 - p, 3);
    let dy = globeTween.toY - globeTween.fromY;
    // shortest rotational path
    while (dy > Math.PI) dy -= Math.PI * 2;
    while (dy < -Math.PI) dy += Math.PI * 2;
    globeGroup.rotation.x =
      globeTween.fromX + (globeTween.toX - globeTween.fromX) * e;
    globeGroup.rotation.y = globeTween.fromY + dy * e;
    if (p >= 1) globeTween = null;
  } else if (autoRotate && !dragState) {
    globeGroup.rotation.y += 0.0011;
  }

  if (regionMesh) {
    const t = performance.now() * 0.002;
    const s = 1 + Math.sin(t) * 0.22;
    regionMesh.scale.set(s, s, s);
    regionMesh.visible = false;
  }

  // drift the cloud layer slightly faster than the surface for parallax
  if (cloudMesh && cloudMesh.visible) {
    cloudMesh.rotation.y += 0.0004;
    if (cloudMesh.material.uniforms) {
      cloudMesh.material.uniforms.uTime.value = performance.now() * 0.001;
    }
  }

  // live traffic along the teleconnection arcs: a bright packet crawls the
  // curve and the destination ring breathes, the way the cybermap's attack
  // links behave
  if (arcPackets.length) {
    for (const pkt of arcPackets) {
      pkt.userData.t = (pkt.userData.t + pkt.userData.speed) % 1;
      const pos = pkt.userData.curve.getPoint(pkt.userData.t);
      pkt.position.copy(pos);
      // fade in at the origin, out at the target
      const t = pkt.userData.t;
      pkt.material.opacity = 0.95 * Math.sin(Math.PI * t);
      const sc = 0.7 + 0.5 * Math.sin(t * Math.PI);
      pkt.scale.setScalar(sc);
    }
  }
  if (arcRings.length) {
    const now = performance.now() * 0.0018;
    for (const ring of arcRings) {
      const k = 1 + 0.30 * Math.sin(now + ring.userData.pulse);
      ring.scale.setScalar(k);
      ring.material.opacity = 0.55 + 0.35 * Math.sin(now + ring.userData.pulse);
    }
  }

  updateGlobeLabels();
  renderer.render(scene, camera);
}

/* ============================================================
   GUIDED START — the "data detective" front door
   The challenge brief asks for a short question flow and a couple
   of demonstration examples. These four stories are pre-verified
   against the live API, so a first-time user sees a real answer
   within seconds instead of facing 16 variables x 23 regions.
   ============================================================ */
const DEMOS = {
  warming: {
    vars: ["T2M"], region: "europe", start: 2005, end: 2024,
    hint: "Central Europe \u00b7 Air Temperature",
  },
  rain: {
    vars: ["PRECTOTCORR"], region: "sahel", start: 2005, end: 2024,
    hint: "Sahel Central \u00b7 Precipitation",
  },
  contrast: {
    vars: ["PRECTOTCORR"], region: "sahel", start: 2005, end: 2024,
    compare: "amazon", hint: "Precipitation \u00b7 Sahel vs Amazon",
  },
  negative: {
    vars: ["T2M"], region: "arctic", start: 2005, end: 2024,
    hint: "Arctic Siberia \u00b7 Air Temperature",
  },
};

function wireStartModal() {
  const modal = $("start-modal");
  if (!modal) return;
  const close = $("start-close");
  if (close) close.addEventListener("click", () => hideModal(modal));
  modal.addEventListener("click", (e) => { if (e.target === modal) hideModal(modal); });

  modal.querySelectorAll(".start-card").forEach((card) => {
    card.addEventListener("click", () => runDemo(card.dataset.demo));
  });

  // Only show on a genuinely fresh visit, and never block a returning user.
  let seen = null;
  try { seen = window.localStorage.getItem("tt-seen-start"); } catch (_) {}
  if (!seen) {
    showModal(modal);
    if (close) close.focus();
  }
}

function runDemo(key) {
  const demo = DEMOS[key];
  if (!demo) return;
  hideModal($("start-modal"));
  try { window.localStorage.setItem("tt-seen-start", "1"); } catch (_) {}

  state.selected = demo.vars.slice();
  state.pendingBbox = null;
  state.preferredVar = demo.vars[0];

  if ($("region")) $("region").value = demo.region;
  if ($("start")) $("start").value = demo.start;
  if ($("end")) $("end").value = demo.end;

  // contrast demo turns compare mode on and picks the second region
  if (demo.compare) {
    state.compareMode = true;
    const pill = $("toggle-compare-mode");
    if (pill) pill.textContent = "MODE: CONTRAST";
    const grp = $("compare-region-group");
    if (grp) grp.style.display = "";
    if ($("compare-region")) $("compare-region").value = demo.compare;
  }

  renderVarList();
  applyRegionSelection(currentRegion());
  flashHint(demo.hint.toUpperCase());
  analyze();
}

/* ============================================================
   KASPERSKY-STYLE SHELL
   The chrome is a cybermap: a 60px header with the primary nav, a
   40px tool strip, a full-bleed globe and a 51px legend footer.
   Everything here is presentation — no analysis logic lives in it.
   ============================================================ */
function initCyberShell() {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  const zoomBy = (factor) => {
    if (!camera) return;
    camera.position.z = clamp(camera.position.z * factor, 2.1, 5.4);
  };
  const mczi = $("mc-zoom-in");
  const mczo = $("mc-zoom-out");
  if (mczi) mczi.addEventListener("click", () => zoomBy(0.86));
  if (mczo) mczo.addEventListener("click", () => zoomBy(1.16));

  // render-mode toggle on the map rail mirrors the header dropdown
  const mcStyle = $("mc-style");
  if (mcStyle) {
    mcStyle.addEventListener("click", () => {
      const next = appliedStyle === "relief" ? "dots" : "relief";
      if (next === "relief" && textureState !== "ready") return;
      applyGlobeStyle(next);
      try { window.localStorage.setItem("tt-globe-style", next); } catch (e) { /* ignore */ }
    });
  }

  const mcRotate = $("mc-rotate");
  if (mcRotate) {
    mcRotate.classList.toggle("on", autoRotate);
    mcRotate.addEventListener("click", () => {
      autoRotate = !autoRotate;
      mcRotate.classList.toggle("on", autoRotate);
    });
  }

  const mcReset = $("mc-reset");
  if (mcReset) {
    mcReset.addEventListener("click", () => {
      if (camera) camera.position.z = 3.35;
      autoRotate = true;
      if (mcRotate) mcRotate.classList.add("on");
      if (globeGroup) globeGroup.rotation.x = 0.18;
      if (globeGroup) globeGroup.rotation.y = -0.6;
      updateGlobeOverlay();
    });
  }

  // primary nav — each entry reveals the surface that already exists
  document.querySelectorAll("[data-kview]").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelectorAll("[data-kview]").forEach((l) => l.classList.remove("active"));
      link.classList.add("active");
      const view = link.dataset.kview;
      if (view === "observatory") openDataModal();
      else if (view === "statistics") {
        // the all-variable ranking table is the statistics surface
        if (state.selected.length) $("scan").click();
        else flashHint("SELECT A VARIABLE FIRST");
      } else if (view === "interconnect") openInterconnectScreen({ force: true });
      else if (view === "sources") openDefs();
      else flashHint("GLOBAL CHANGE MAP");
    });
  });

  // header CTA = the scan action, kept in one place
  const cta = $("k-scan-cta");
  if (cta) {
    cta.addEventListener("click", () => {
      if (state.selected.length === 0) {
        // the scan needs at least one variable in the current engine
        flashHint("SELECT A VARIABLE FIRST");
        return;
      }
      const scanBtn = $("scan");
      if (scanBtn) scanBtn.click();
    });
  }

  // footer mirrors the selected region so the strip always reads true
  const footRegion = $("k-foot-region");
  if (footRegion) {
    const reg = currentRegion();
    if (reg) footRegion.textContent = reg.name.toUpperCase();
  }
}

window.addEventListener("DOMContentLoaded", () => boot());

/* ============================================================
   EARTH SYSTEM INTERCONNECTIONS SCREEN
   The main deliverable: local coupling, global impacts and the
   driver's own anomaly history, each in its own focused view
   instead of crammed into the rail.
   ============================================================ */
let ixState = {
  local: null,
  global: null,
  anomaly: null,
  tab: "local",
  loading: false,
};

function initInterconnectScreen() {
  document.querySelectorAll('[data-ix-tab]').forEach(btn=>btn.addEventListener('click',()=>setIxTab(btn.dataset.ixTab)));
  $('ix-close').onclick=()=>showInvestigationScreen('map');
  $('ix-rerun').onclick=()=>{showInvestigationScreen('map');openDrawer(true);};
}

function setIxTab(tab) {
  ixState.tab = tab;
  document.querySelectorAll("[data-ix-tab]").forEach((b) => {
    const on = b.dataset.ixTab === tab;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll("[data-ix-panel]").forEach((p) => {
    p.classList.toggle("on", p.dataset.ixPanel === tab);
  });
}

function closeInterconnectScreen() {showInvestigationScreen('map');}

function ixDrivers() {
  const reg = currentRegion();
  const s = state.result && state.result.series
    ? state.result.series[state.activeVarIdx] : null;
  const vId = state.selected[state.activeVarIdx] || state.selected[0] || (s ? s.variable.id : "T2M");
  const vMeta = state.catalog?.variables.find(v=>v.id===vId) || (s?.variable.id===vId?s.variable:null);
  return { reg, vId, vMeta };
}

async function openInterconnectScreen(opts = {}) {
  const screen = $("ix-screen");
  if (!screen) return;
  const { reg, vId, vMeta } = ixDrivers();
  if (!reg) {
    flashHint("PICK A REGION FIRST");
    return;
  }

  screen.hidden = false;
  requestAnimationFrame(() => screen.classList.add("open"));
  setIxTab(ixState.tab);

  if (ixState.loading) return;
  if (!opts.force && ixState.local && ixState.global
      && ixState.regionId === reg.id && ixState.varId === vId) {
    return;
  }

  ixState.loading = true;
  ixState.regionId = reg.id;
  ixState.varId = vId;
  ixState.regName = reg.name;
  ixState.varName = vMeta ? vMeta.name : vId;
  ixState.varUnit = vMeta ? vMeta.unit : "";

  $("ix-sub").textContent =
    "Candidate relationships for " + ixState.varName + " over " + reg.name + ", computed from the selected datasets. Statistical links do not establish a physical cause.";
  $("ix-period").textContent = $("start").value + "-" + $("end").value;
  $("ix-hero").innerHTML = ixHeroHTML(reg, vMeta || { name: vId }, null, null);
  showIxPanels(true);

  const rerun = $("ix-rerun");
  if (rerun) rerun.disabled = true;

  try {
    await loadInterconnectData(reg, vId);
  } finally {
    ixState.loading = false;
    if (rerun) rerun.disabled = false;
  }
}

function showIxPanels(loading) {
  if (loading) {
    $("ix-pair-list").innerHTML =
      '<div class="ix-loading"><span class="spin"></span>TESTING EVERY VARIABLE PAIR IN THIS REGION...</div>';
    $("ix-global-list").innerHTML =
      '<div class="ix-loading"><span class="spin"></span>SCANNING GLOBAL REGIONS WITH +/-24 MONTH LAGS...</div>';
    $("ix-anomaly-summary").innerHTML = "";
    $("ix-anomaly-strip").innerHTML = "";
    $("ix-episode-list").innerHTML = "";
    $("ix-empty").classList.remove("on");
    $("ix-net").innerHTML = "";
  }
}

async function loadInterconnectData(reg, vId) {
  const couplingUrl = "/api/coupling?" + new URLSearchParams({
    region: reg.id,
    start: $("start").value,
    end: $("end").value,
  });
  const teleUrl = "/api/teleconnections?" + new URLSearchParams({
    region: reg.id,
    variable: vId,
    start: $("start").value,
    end: $("end").value,
  });

  const [couplingRes, teleconRes] = await Promise.allSettled([
    fetch(couplingUrl),
    fetch(teleUrl),
  ]);

  let local = null;
  if (couplingRes.status === "fulfilled" && couplingRes.value.ok) {
    try { local = await couplingRes.value.json(); } catch (e) { local = null; }
  }
  let global = null;
  if (teleconRes.status === "fulfilled" && teleconRes.value.ok) {
    try { global = await teleconRes.value.json(); } catch (e) { global = null; }
  }

  ixState.local = local;
  ixState.global = global;
  ixState.anomaly = global && global.source ? global.source : null;

  const methodEl = $("ix-method");
  if (methodEl) {
    const cm = local && local.method ? local.method : "";
    const tm = global && global.method ? global.method : "";
    methodEl.textContent = [cm, tm].filter(Boolean).join("  ·  ") ||
      "Computed from the selected dataset’s monthly grid cells.";
  }

  renderIxHero(local, global);
  renderIxLocal(local, vId);
  renderIxGlobal(global, vId);
  renderIxAnomaly(global);
}

function ixHeroHTML(reg, varMeta, local, global) {
  const pairs = local && local.pairs ? local.pairs : [];
  const strong = pairs.filter((p) => p.confidence === "HIGH").length;
  const conns = global && global.teleconnections ? global.teleconnections : [];
  const rep = global && global.source ? global.source.anomaly_report : local?.source_anomaly?.anomaly_report;
  const peak = rep ? (rep.peak_sigma > 0 ? "+" : "") + rep.peak_sigma + "σ" : "...";

  return '' +
    '<div class="ix-hero-cell lead">' +
      '<span class="ixh-lbl">SELECTED MEASUREMENT</span>' +
      '<span class="ixh-val">' + esc(varMeta.name || "—") + '</span>' +
      '<span class="ixh-sub">' + esc(reg.name) + ' · ' + esc(varMeta.unit || "") + '</span>' +
    '</div>' +
    '<div class="ix-hero-cell">' +
      '<span class="ixh-lbl">LOCAL COUPLINGS</span>' +
      '<span class="ixh-val">' + (ixState.loading && !local ? "..." : pairs.length) + '</span>' +
      '<span class="ixh-sub">' + strong + ' high-confidence</span>' +
    '</div>' +
    '<div class="ix-hero-cell">' +
      '<span class="ixh-lbl">REMOTE RELATIONSHIPS</span>' +
      '<span class="ixh-val">' + (global?conns.length:local?'NOT REQUESTED':"...") + '</span>' +
      '<span class="ixh-sub">after effect + FDR gates</span>' +
    '</div>' +
    '<div class="ix-hero-cell">' +
      '<span class="ixh-lbl">PEAK ANOMALY</span>' +
      '<span class="ixh-val">' + peak + '</span>' +
      '<span class="ixh-sub">' + (rep ? "in " + esc(rep.peak_month) : "computing") + '</span>' +
    '</div>' +
    '<div class="ix-hero-cell">' +
      '<span class="ixh-lbl">PAIRS TESTED</span>' +
      '<span class="ixh-val">' + (global && global.summary ? global.summary.total_scanned : "—") + '</span>' +
      '<span class="ixh-sub">remote region × variable</span>' +
    '</div>';
}

function renderIxHero(local, global) {
  const { reg, vMeta } = ixDrivers();
  const el = $("ix-hero");
  if (el) el.innerHTML = ixHeroHTML(reg, vMeta || { name: ixState.varName, unit: ixState.varUnit }, local, global);
}

function renderIxLocal(local, driverId) {
  const pairs = local && local.pairs ? local.pairs : [];
  const vars = local && local.variables ? local.variables : [];
  drawIxNetwork(vars, pairs, driverId);

  const list = $("ix-pair-list");
  if (!list) return;
  const sub = $("ix-local-sub");

  // The driver's own couplings are the reason the user opened this screen;
  // everything else measured in the region is secondary and stays behind a
  // disclosure instead of being dumped into the same list.
  const mine = pairs.filter((p) => p.driver === driverId || p.response === driverId
    || p.a.id === driverId || p.b.id === driverId);
  const others = pairs.filter((p) => mine.indexOf(p) === -1);
  const driverVar = vars.find((v) => v.id === driverId) || { name: driverId, id: driverId };

  if (sub && local) {
    sub.textContent =
      "Every pair of variables measured in " + local.region.name +
      " is tested. " + mine.length + " involve the selected measurement " + driverVar.name +
      "; " + others.length + " are couplings between the other variables.";
  }

  if (!pairs.length) {
    list.innerHTML =
      '<div class="ix-empty on"><h4>NO LOCAL COUPLING SURVIVED THE TESTS</h4>' +
      '<p>Within ' + esc(local && local.region ? local.region.name : "this region") +
      ', no relationship passed the checks for the available overlapping observations. Missing coverage or an unavailable source can prevent testing. This does not establish that the variables are independent.</p></div>';
    return;
  }

  let html = '<div class="ix-group"><h4 class="ix-group-title">RELATIONSHIPS · ' +
    esc(driverVar.name.toUpperCase()) + '</h4>';
  if (!mine.length) {
    html += '<p class="ix-group-empty">No tested relationship involving ' + esc(driverVar.name) + ' passed the evidence checks for this area and period.</p>';
  } else {
    for(const [label,selected] of [
      ['CANDIDATE INCOMING DRIVERS',mine.filter(p=>p.response===driverId)],
      ['ASSOCIATED DOWNSTREAM RESPONSES',mine.filter(p=>p.driver===driverId)],
      ['NO CLEAR TEMPORAL LEAD',mine.filter(p=>!p.driver||!p.response)]
    ])if(selected.length)html+='<h4 class="ix-group-title">'+label+'</h4>'+selected.map(p=>ixPairHTML(p,pairs,driverId)).join('');
  }
  html += '</div>';

  if (others.length) {
    html += '<details class="ix-group ix-more">' +
      '<summary><span class="ix-more-label">OTHER COUPLINGS IN THIS REGION</span>' +
      '<span class="ix-more-count">' + others.length + ' pairs</span>' +
      '<span class="ix-chev">▸</span></summary>' +
      '<div class="ix-more-body">' +
      others.map((p) => ixPairHTML(p, pairs, driverId)).join("") +
      '</div></details>';
  }

  list.innerHTML = html;
}

function ixPairHTML(p, allPairs, driverId) {
  const isDriver = p.a.id === driverId || p.b.id === driverId;
  const sign = p.r > 0 ? "+" : "";
  const color = p.phase === "in_phase" ? "var(--rise)" : "var(--fall)";
  const drv = p.driver && p.response
    ? '<span class="ix-pair-name">' + esc(nameOf(allPairs, p.driver)) + '</span>' +
      '<span class="ix-pair-arrow">→</span>' +
      '<span class="ix-pair-name">' + esc(nameOf(allPairs, p.response)) + '</span>'
    : '<span class="ix-pair-name">' + esc(p.a.name) + '</span>' +
      '<span class="ix-pair-arrow">⇄</span>' +
      '<span class="ix-pair-name">' + esc(p.b.name) + '</span>';
  const pTxt = p.p < 0.001 ? "<0.001" : p.p.toFixed(3);
  const prTxt = p.r_partial === null || p.r_partial === undefined ? "—" : p.r_partial.toFixed(2);
  return '' +
    '<div class="ix-pair ' + p.phase + '">' +
      '<div class="ix-pair-top">' +
        drv +
        (isDriver ? '<span class="ix-conf HIGH">SELECTED MEASUREMENT</span>' : "") +
        '<span class="ix-pair-r" style="color:' + color + '">' + sign + p.r.toFixed(2) + '</span>' +
      '</div>' +
      '<div class="ix-pair-scale">RELATIONSHIP STRENGTH · unitless, −1 to +1' +
        (p.partial_control ? ' · partial, ' + esc(p.partial_control) + ' held constant' : '') + '</div>' +
      '<div class="ix-pair-meta">' +
        '<span>LAG <b>' + (p.lag_months > 0 ? "+" : "") + p.lag_months + ' mo</b></span>' +
        '<span>p <b>' + pTxt + '</b></span>' +
        '<span>PARTIAL r <b>' + prTxt + '</b></span>' +
        '<span class="ix-conf ' + p.confidence + '">' + p.confidence + ' CONFIDENCE</span>' +
      '</div>' +
      '<div class="ix-pair-note">' + esc(p.lag_note) + '. ' + esc(p.mechanism) + '</div>' +
      '<div class="ix-pair-note">'+esc([p.source_a,p.source_b].filter(Boolean).join(' ↔ '))+(p.overlapping_months?' · '+p.overlapping_months+' overlapping months':'')+'</div>'+
    '</div>';
}

/* NASA POWER parameter ids are long (ALLSKY_SFC_LW_DWN). The ring is a map,
   not a legend, so trim to something that fits while staying recognisable. */
const IX_SHORT = {
  ALLSKY_SFC_LW_DWN: "LW DWN",
  ALLSKY_SFC_SW_DNI: "SW DNI",
  ALLSKY_SFC_SW_DWN: "SW DWN",
  PRECTOTCORR: "PRECIP",
  EVPTRNS: "EVPTRANS",
  EVLAND: "EVLAND",
  GWETROOT: "GW ROOT",
  GWETTOP: "GW TOP",
  RH2M: "RH2M",
  QV2M: "QV2M",
  WS2M: "WS2M",
  T2M: "T2M",
  T2M_MAX: "T2M MAX",
  T2M_MIN: "T2M MIN",
  T2M_RANGE: "T2M RNG",
  TS: "TS",
  PS: "PS",
};
function shortVarLabel(id) {
  return IX_SHORT[id] || String(id).replace(/^ALLSKY_SFC_/, "").replace(/_/g, " ");
}

function nameOf(pairs, id) {
  for (const p of pairs) {
    if (p.a.id === id) return p.a.name;
    if (p.b.id === id) return p.b.name;
  }
  return id;
}

function drawIxNetwork(vars, pairs, driverId) {
  const svg = $("ix-net");
  if (!svg) return;
  if (!vars.length) { svg.innerHTML = ""; return; }

  // Draw only the pairs that involve the driver, plus the strongest few
  // couplings among the others. Every chord in the full 16-variable graph
  // made the picture unreadable; this keeps it legible while the list beside
  // it still accounts for every tested pair.
  const mine = pairs.filter((p) => p.a.id === driverId || p.b.id === driverId
    || p.driver === driverId || p.response === driverId);
  const rest = pairs.filter((p) => mine.indexOf(p) === -1)
    .sort((x, y) => Math.abs(y.r) - Math.abs(x.r))
    .slice(0, 6);
  const shown = mine.concat(rest);
  const shownIds = new Set([driverId]);
  shown.forEach((p) => { shownIds.add(p.a.id); shownIds.add(p.b.id); });
  // keep the node ring stable: only label nodes that actually appear
  const nodes = vars.filter((v) => shownIds.has(v.id));

  const W = 460, H = 420;
  const cx = W / 2, cy = H / 2 - 4;
  const R = 120;
  const pos = {};
  nodes.forEach((v, i) => {
    const a = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
    pos[v.id] = { x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R, color: v.color || "#889" };
  });

  const parts = [];

  shown.forEach((p) => {
    const A = pos[p.a.id], B = pos[p.b.id];
    if (!A || !B) return;
    const isPos = p.phase === "in_phase";
    const stroke = isPos ? C.rise : C.fall;
    const w = Math.max(0.8, Math.min(4, Math.abs(p.r) * 7));
    const op = Math.max(0.28, Math.min(0.85, Math.abs(p.r) + 0.2));
    const mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
    const dx = mx - cx, dy = my - cy;
    const bow = 0.28;
    const cxp = mx + dx * bow, cyp = my + dy * bow;
    parts.push(
      '<path d="M ' + A.x.toFixed(1) + ' ' + A.y.toFixed(1) + ' Q ' + cxp.toFixed(1) + ' ' + cyp.toFixed(1) + ' ' + B.x.toFixed(1) + ' ' + B.y.toFixed(1) + '" fill="none" stroke="' + stroke + '" stroke-width="' + w.toFixed(2) + '" stroke-opacity="' + op.toFixed(2) + '"/>'
    );
    const resp = p.response;
    let tip = null, ctrl = { x: cxp, y: cyp };
    if (resp === p.b.id) tip = B;
    else if (resp === p.a.id) tip = A;
    if (tip) {
      const vx = tip.x - ctrl.x, vy = tip.y - ctrl.y;
      const len = Math.hypot(vx, vy) || 1;
      const ux = vx / len, uy = vy / len;
      const px = -uy, py = ux;
      const bx = tip.x - ux * 14, by = tip.y - uy * 14;
      parts.push(
        '<path d="M ' + tip.x.toFixed(1) + ' ' + tip.y.toFixed(1) + ' L ' + (bx + px * 4.5).toFixed(1) + ' ' + (by + py * 4.5).toFixed(1) + ' L ' + (bx - px * 4.5).toFixed(1) + ' ' + (by - py * 4.5).toFixed(1) + ' Z" fill="' + stroke + '" fill-opacity="' + Math.min(0.95, op + 0.15).toFixed(2) + '"/>'
      );
    }
  });

  nodes.forEach((v) => {
    const p = pos[v.id];
    if (!p) return;
    const isDriver = v.id === driverId;
    const r = isDriver ? 11 : 7.5;
    parts.push(
      '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + (r + 4) + '" fill="#05070a" />',
      '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + r + '" fill="' + p.color + '" fill-opacity="' + (isDriver ? 1 : 0.8) + '" stroke="' + (isDriver ? "#ffffff" : "none") + '" stroke-width="' + (isDriver ? 1.8 : 0) + '"/>'
    );
    const words=(v.name||v.id).split(/\s+/),lines=[''];
    for(const word of words){if((lines[lines.length-1]+' '+word).trim().length>26)lines.push(word);else lines[lines.length-1]=(lines[lines.length-1]+' '+word).trim();}
    const top=p.y<cy?p.y-22-(lines.length-1)*16:p.y+26;
    parts.push('<text x="'+p.x.toFixed(1)+'" y="'+top.toFixed(1)+'" text-anchor="middle" font-family="ui-monospace, monospace" font-size="14" fill="#e1eee5">'+lines.map((line,i)=>'<tspan x="'+p.x.toFixed(1)+'" dy="'+(i?16:0)+'">'+esc(line)+'</tspan>').join('')+'</text>');

  });

  svg.innerHTML = parts.join("");
}

function renderIxGlobal(global, driverId) {
  const list = $("ix-global-list");
  if (!list) return;
  const conns = global && global.teleconnections ? global.teleconnections : [];
  const sum = global && global.summary ? global.summary : {};
  const sub = $("ix-global-sub");

  if (sub && global) {
    sub.textContent =
      "Tested " + (sum.total_scanned || 0) + " remote region x variable pairs with lags up to +/-24 months. " +
      conns.length + " survived the correlation, effect-size and FDR gates. " +
      "Effect size is how far the remote variable sat off its own baseline during this driver's surges.";
  }

  $("ix-empty").classList.toggle("on", conns.length === 0);

  if (!conns.length) {
    list.innerHTML = "";
    return;
  }

  const maxEff = Math.max.apply(null, conns.map((c) => Math.abs((c.composite || {}).effect_sigma || 0)).concat([0.5]));

  list.innerHTML = conns.map((c) => {
    const comp = c.composite || {};
    const eff = comp.effect_sigma || 0;
    const width = Math.min(50, (Math.abs(eff) / maxEff) * 50);
    const effColor = eff >= 0 ? "var(--rise)" : "#42a5f5";
    const rColor = c.direction === "direct" ? "var(--rise)" : "#42a5f5";
    const left = eff >= 0 ? "50%" : (50 - width) + "%";
    const pTxt = c.p < 0.001 ? "<.001" : c.p.toFixed(3);
    return '' +
      '<div class="ix-globe-row ' + c.direction + '">' +
        '<div class="ixg-where">' +
          '<span class="ixg-region">' + esc(c.target_region.name) + '</span>' +
          '<span class="ixg-var">' + esc(c.target_variable.name) + ' · ' + esc(c.target_variable.sphere_code || "") + '</span>' +
        '</div>' +
        '<div class="ixg-effect">' +
          '<span class="ixg-eff-lbl">REMOTE RESPONSE</span>' +
          '<div class="ixg-eff-bar">' +
            '<div class="ixg-eff-fill" style="left:' + left + ';width:' + width + '%;background:' + effColor + '"></div>' +
          '</div>' +
          '<span class="ixg-eff-val">' + (eff >= 0 ? "+" : "") + eff.toFixed(2) + 'σ vs its baseline</span>' +
        '</div>' +
        '<div class="ixg-stat">' +
          '<span class="n" style="color:' + rColor + '">' + (c.r >= 0 ? "+" : "") + c.r.toFixed(2) + '</span>' +
          '<span class="l">r · p=' + pTxt + '</span>' +
        '</div>' +
        '<div class="ixg-stat">' +
          '<span class="n" style="color:#e9ebed">' + (c.lag_months > 0 ? "+" : "") + c.lag_months + ' mo</span>' +
          '<span class="l">' + esc(c.lead_note || "") + '</span>' +
        '</div>' +
        '<div class="ixg-mech">' + esc(c.mechanism) + '</div>' +
      '</div>';
  }).join("");
}

function renderIxAnomaly(global) {
  const src = global && global.source ? global.source : null;
  const rep = src ? src.anomaly_report : null;
  const yearly = src && src.anomaly_yearly ? src.anomaly_yearly : [];
  const summary = $("ix-anomaly-summary");
  const strip = $("ix-anomaly-strip");
  const eps = $("ix-episode-list");
  const sub = $("ix-anomaly-sub");
  if (!summary) return;

  if (!rep) {
    summary.innerHTML = "";
    strip.innerHTML = "";
    eps.innerHTML = '<div class="ix-empty on"><h4>NOT ENOUGH MONTHS TO DECOMPOSE</h4><p>A seasonal decomposition needs at least three years of complete monthly data.</p></div>';
    return;
  }

  if (sub && src) {
    sub.textContent =
      src.variable.name + " over " + src.region.name +
      ", after its monthly seasonal cycle and its long-term trend are removed. " +
      "What is left is how far each month departed from where that region's own history says it should have been.";
  }

  const pctAbove = rep.total_months ? (100 * rep.months_above / rep.total_months).toFixed(0) : "0";
  summary.innerHTML = '' +
    '<div class="ix-astat"><span class="v">' + rep.total_months + '</span><span class="l">MONTHS ANALYSED</span></div>' +
    '<div class="ix-astat"><span class="v" style="color:var(--rise)">' + rep.months_above + '</span><span class="l">ABOVE TREND (' + pctAbove + '%)</span></div>' +
    '<div class="ix-astat"><span class="v" style="color:#42a5f5">' + rep.months_below + '</span><span class="l">BELOW TREND</span></div>' +
    '<div class="ix-astat"><span class="v">' + (rep.peak_sigma > 0 ? "+" : "") + rep.peak_sigma + 'σ</span><span class="l">PEAK · ' + esc(rep.peak_month) + '</span></div>' +
    '<div class="ix-astat"><span class="v">' + rep.episodes.length + '</span><span class="l">EPISODES</span></div>';

  const maxAbs = Math.max.apply(null, yearly.map((y) => Math.abs(y.value)).concat([0.001]));
  strip.innerHTML = yearly.map((y) => {
    const frac = Math.abs(y.value) / maxAbs;
    const h = Math.max(2, frac * 40);
    const pos = y.value >= 0;
    return '<div class="ix-anom-bar" title="' + y.year + ': ' + (y.value > 0 ? "+" : "") + y.value.toFixed(3) + '">' +
      '<div class="ix-anom-fill" style="height:' + h + 'px;' + (pos ? "bottom:50%" : "top:50%") + ';background:' + (pos ? "var(--rise)" : "#42a5f5") + '"></div>' +
    '</div>';
  }).join("");

  const episodes = (rep.episodes || []).slice().sort(
    (a, b) => Math.abs(b.peak_sigma) - Math.abs(a.peak_sigma)).slice(0, 14);

  if (!episodes.length) {
    eps.innerHTML = '<div class="ix-empty on"><h4>NO SUSTAINED SURGES</h4><p>This variable never ran more than one standard deviation from its own trend for a whole month.</p></div>';
    return;
  }

  ixState.anomalySource = src;
  ixState.anomalyEpisodes = episodes;
  eps.innerHTML = episodes.map((e, i) => '' +
    '<button type="button" class="ix-episode" data-anomaly-episode="' + i + '" ' +
      'aria-label="Open details for the ' + (e.side === "below" ? "below" : "above") + '-baseline episode beginning ' + esc(e.start) + '">' +
      '<span class="ix-ep-n">' + String(i + 1).padStart(2, "0") + '</span>' +
      '<span class="ix-ep-range">' + esc(e.start) + (e.end !== e.start ? " → " + esc(e.end) : "") + '</span>' +
      '<span class="ix-ep-peak">' + (e.peak_sigma > 0 ? "+" : "") + e.peak_sigma + 'σ</span>' +
      '<span class="ix-ep-len">' + e.months + ' MO</span>' +
      '<span class="ix-ep-side">' + (e.side === "below" ? "BELOW" : "ABOVE") + '</span>' +
    '</button>').join("");
  eps.querySelectorAll('[data-anomaly-episode]').forEach((button) => {
    button.addEventListener("click", () => openAnomalyEpisode(Number(button.dataset.anomalyEpisode)));
  });
}

/* Anomaly drill-down: the per-month evidence behind one highlighted episode.
   The numbers come from the fitted baseline the run already used; nothing is
   recomputed here and no attribution is inferred from the departure. */
function openAnomalyEpisode(index) {
  const src = ixState.anomalySource;
  const episodes = ixState.anomalyEpisodes || [];
  const episode = episodes[index];
  if (!src || !episode) return;
  const detail = src.anomaly_detail;
  const report = src.anomaly_report || {};
  const unit = src.variable?.unit || "";
  const store = (src.provenance?.source || src.provenance?.dataset || "the stored source");
  const dialog = document.createElement("dialog");
  dialog.className = "anomaly-detail-dialog";
  const title = document.createElement("h2");
  title.textContent = (episode.side === "below" ? "Below-baseline episode" : "Above-baseline episode") +
    " · " + src.variable?.name + " over " + src.region?.name;
  const lead = document.createElement("p");
  lead.textContent = "Months where the observed value sat " + (episode.side === "below" ? "below" : "above") +
    " the fitted baseline (seasonal climatology plus the long-term trend fitted to the whole analysis period). " +
    "The threshold is " + (detail?.threshold_sigma ?? 1) + "σ, where σ is the residual standard deviation" +
    (report.sigma ? " (" + report.sigma + " " + unit + ")" : "") + ".";
  dialog.append(title, lead);

  if (!detail || !Array.isArray(detail.months)) {
    const missing = document.createElement("p");
    missing.textContent = "This run did not retain a per-month drill-down. Re-run the relationship analysis to build one. No numbers are invented here.";
    dialog.append(missing);
  } else {
    const months = detail.months.filter((row) => {
      if (!episode.start || !episode.end) return false;
      return row.month >= episode.start && row.month <= episode.end;
    });
    const baseline = document.createElement("p");
    baseline.className = "anomaly-baseline";
    baseline.textContent = [
      "Baseline period: " + (detail.baseline_period?.first_month || "?") + "–" + (detail.baseline_period?.last_month || "?"),
      "Valid months: " + (detail.baseline_period?.valid_months ?? "?"),
      "Missing months: " + (detail.baseline_period?.missing_months ?? "?"),
      "Threshold: " + (detail.threshold_sigma ?? 1) + "σ",
      "Source: " + store,
    ].join(" · ");
    dialog.append(baseline);

    const table = document.createElement("table");
    table.className = "anomaly-table";
    const head = document.createElement("tr");
    for (const label of ["Month", "Observed (" + unit + ")", "Expected baseline (" + unit + ")", "Departure (" + unit + ")", "Standardised (σ)"]) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = label;
      head.append(cell);
    }
    const thead = document.createElement("thead");
    thead.append(head);
    const tbody = document.createElement("tbody");
    for (const row of months) {
      const tr = document.createElement("tr");
      const cells = [row.month, num(row.observed, 3), num(row.expected, 3),
        Number.isFinite(row.departure) ? (row.departure >= 0 ? "+" : "") + num(row.departure, 3) : "no observation",
        Number.isFinite(row.sigma_units) ? (row.sigma_units >= 0 ? "+" : "") + row.sigma_units.toFixed(2) : "—"];
      for (const value of cells) {
        const td = document.createElement("td");
        td.textContent = String(value);
        tr.append(td);
      }
      if (episode.peak_month === row.month) tr.className = "peak";
      tbody.append(tr);
    }
    table.append(thead, tbody);
    const tableWrap = document.createElement("div");
    tableWrap.className = "anomaly-table-wrap";
    tableWrap.append(table);
    dialog.append(tableWrap);

    const reading = document.createElement("p");
    reading.className = "anomaly-reading";
    reading.textContent = "An unusual departure is a difference from this measurement's own fitted baseline, not an extreme-event " +
      "or hazard assessment. This threshold alone cannot say whether a departure mattered, what caused it, or what happened " +
      "as a result; that would need physical damage or exposure evidence, which this analysis does not contain.";
    dialog.append(reading);
  }

  const links = (ixState.local?.pairs || []).filter((pair) =>
    pair.a === src.variable?.id || pair.b === src.variable?.id || pair.var_a === src.variable?.id || pair.var_b === src.variable?.id);
  const linked = document.createElement("div");
  linked.className = "anomaly-links";
  const linkedTitle = document.createElement("h3");
  linkedTitle.textContent = "Explore possible linked variables";
  const linkedNote = document.createElement("p");
  linkedNote.textContent = links.length
    ? "These are the statistical associations this run tested between the episode's variable and another measurement in the same area and months. An association is not an attribution: nothing here establishes that one variable caused the departure."
    : "No surviving association with another measurement was found in this run. Attribution has not been established, and this anomaly alone does not identify a cause.";
  linked.append(linkedTitle, linkedNote);
  for (const pair of links.slice(0, 4)) {
    const row = document.createElement("p");
    const rValue = Number(pair.r);
    row.textContent = (pair.a_name || pair.var_a || "series 1") + " ↔ " + (pair.b_name || pair.var_b || "series 2") +
      " · relationship strength " + (Number.isFinite(rValue) ? (rValue >= 0 ? "+" : "") + rValue.toFixed(2) : "—") +
      " on a −1 to +1 scale (unitless)" + (pair.lead_note ? " · " + pair.lead_note : "") +
      (Number.isFinite(Number(pair.p_adjusted ?? pair.p)) ? " · adjusted p " + Number(pair.p_adjusted ?? pair.p).toPrecision(3) : "");
    linked.append(row);
  }
  dialog.append(linked);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "toolbar-button";
  close.textContent = "Close";
  close.onclick = () => dialog.close();
  dialog.append(close);
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  close.focus();
}

initInterconnectScreen();

/* ============================================================
   EXPLAIN-YOURSELF LAYER
   The statistics on this screen are the point, but a reader should
   not need a stats course to see what they mean. Every technical
   term carries a plain-English definition in a tooltip, and the
   screen opens with a short guide to reading it.
   ============================================================ */
const IX_TIPS = {
  driver:
    "The variable you selected. Everything on this screen is measured against this one.",
  localCouplings:
    "How many pairs of variables in this region still move together after the seasons, the long-term trend and air temperature are factored out.",
  globalRipples:
    "Places far from this region whose variables shifted measurably when this one ran hotter or colder than its own normal.",
  peakAnomaly:
    "The single month this variable strayed furthest from where its own history says it should have been, in standard deviations (\u03c3).",
  pairsTested:
    "How many remote region-and-variable combinations the scan checked before deciding which ones count.",

  r:
    "Correlation, from -1 to +1. Positive means both rise and fall together; negative means one rises as the other falls. Near 0 means no relationship.",
  p:
    "The chance of seeing a link this strong purely by luck. 0.05 means 1 in 20; lower is more trustworthy.",
  lag:
    "How many months one variable leads the other. 0 months means they change in the same month. A positive number means the driver moves first.",
  partialR:
    "The correlation left over after air temperature is held constant. If this drops near zero, the link was really just a shared response to temperature.",
  confidence:
    "Three separate tests must agree: the correlation itself, surviving the temperature control, and one actually helping predict the other. HIGH means all three passed.",
  sigma:
    "Standard deviations from normal. +1\u03c3 means higher than about 84% of months on record; +2\u03c3 is rarer still.",
  effectSize:
    "How far the remote variable sat from its own normal during this driver's surges, in \u03c3. Bigger means a stronger real-world response.",
  fdr:
    "When you test dozens of pairs, some will look linked by pure chance. False-discovery control throws those lucky results out before anything is reported.",

  aboveTrend:
    "Months this variable ran higher than its own seasonal cycle and long-term trend predict.",
  belowTrend:
    "Months it ran lower than its own trend predicts.",
  episodes:
    "Separate stretches of time it stayed more than one standard deviation from its trend.",
  decomposition:
    "Each month is compared with what that same calendar month normally looks like in this region, and with the region's long-term drift, so the leftover is genuine departure rather than season or slow warming.",
  network:
    "Each dot is a variable measured here. A line means the two move together. Arrowheads point at the one that reacts, so the drawing shows the computed direction of influence.",
};

function initIxTooltips() {
  const tip = document.createElement("div");
  tip.className = "ix-tooltip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.appendChild(tip);

  const show = (el) => {
    const text = el.getAttribute("data-tip");
    if (!text) return;
    tip.textContent = text;
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = box.left + box.width / 2 - tw / 2;
    left = Math.max(10, Math.min(window.innerWidth - tw - 10, left));
    let top = box.top - th - 10;
    if (top < 10) top = box.bottom + 10;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  };
  const hide = () => { tip.hidden = true; };

  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) show(el);
  });
  document.addEventListener("mouseout", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) hide();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) show(el);
  });
  document.addEventListener("focusout", hide);
  window.addEventListener("scroll", hide, true);
}

/* A term with a dotted underline and a tooltip. Keyboard focusable so the
   definitions are reachable without a mouse. */
function tipTerm(label, tipKey, extraClass) {
  const text = IX_TIPS[tipKey] || "";
  return '<span class="ix-term ' + (extraClass || "") + '" tabindex="0" data-tip="' +
    esc(text) + '">' + label + '<i class="ix-q" aria-hidden="true">?</i></span>';
}

/* The guide that explains the three views before any numbers appear. */
function ixGuideHTML() {
  return '<details class="ix-guide">' +
    '<summary><span class="ixg-title">HOW TO READ THIS SCREEN</span>' +
    '<span class="ixg-sub">Three views of the same question, in plain English</span>' +
    '<span class="ix-chev">\u25b8</span></summary>' +
    '<div class="ix-guide-body">' +
      '<div class="ixg-col">' +
        '<h5>01 \u00b7 LOCAL COUPLING</h5>' +
        '<p><b>Which variables here move together, and which one moves first.</b> ' +
        'The engine tests the available pairs using your selected period of monthly data. ' +
        'It removes the seasonal cycle, the long-term trend and the effect of air temperature, ' +
        'then asks whether what is left still lines up. Supported lead relationships identify candidates: when one consistently ' +
        'changes before the other, the display reports the measured lag. This does not establish a physical cause.</p>' +
      '</div>' +
      '<div class="ixg-col">' +
        '<h5>02 \u00b7 GLOBAL IMPACTS</h5>' +
        '<p><b>Where this variable shows up far away.</b> ' +
        'We find the months when the driver ran unusually high, then look at what other ' +
        'variables were doing elsewhere at the same time or up to two years later. ' +
        'A row is reported only if the remote variable really shifted \u2014 and after we throw out ' +
        'results that are merely the luckiest of dozens of tests.</p>' +
      '</div>' +
      '<div class="ixg-col">' +
        '<h5>03 \u00b7 DRIVER ANOMALY</h5>' +
        '<p><b>When this variable departed from its own normal.</b> ' +
        'Every month is compared with what that same calendar month usually looks like, ' +
        'and with the region\u2019s slow long-term drift. What remains is the genuine surprise: ' +
        'the months it ran hotter, drier, or windier than its own history predicts.</p>' +
      '</div>' +
      '<p class="ixg-foot">Every number on this screen is computed from the selected dataset’s monthly grid cells. ' +
      'Nothing is looked up from a list of expected relationships. ' +
      'Hover any underlined term for a definition.</p>' +
    '</div></details>';
}

window.TerraLegacy = { render, clearResults, renderSatellite, renderDataModal };
