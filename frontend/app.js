/* ============================================================
   TerraTrend · Earth Change Observatory
   3D interactive globe (three.js) + multi-variable analysis
   ============================================================ */

const $ = (id) => document.getElementById(id);

const C = {
  rise: "#ff7a33",
  fall: "#4d7cf3",
  flat: "#4a5057",
  nodata: "#2b2f34",
  cyan: "#e9ebed",
  land: "#e6e9ec",
  landDim: "#6f757a",
  globeLine: "#2a2d31",
  ring: "#f0f2f4",
};

const MAX_VARS = 3;

const state = {
  catalog: null,
  selected: ["T2M"],
  result: null,
  mode: "yearly",
  activeVarIdx: 0,
  satellite: null,
  selectedCellBbox: null,
  activeSatBbox: null,
  activeSatTitle: null,
  satModalMode: "side",
  satModalLayer: "true_color",
  satYearBase: 2005,
  satYearRecent: 2024,
  satCustomDate: "08-15",
};

let chart = null;
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

  state.selected = ["T2M"];
  renderVarList();
  renderRegionSelect();

  // data currency comes from the server's live probe of NASA POWER
  const avail = state.catalog.availability || {};
  if (avail.ok && avail.latest_month_label) {
    $("data-through").textContent = avail.latest_month_label;
    $("data-through").title =
      `NASA POWER monthly data valid through ${avail.latest_month_label}` +
      (avail.latest_day_label ? ` (daily through ${avail.latest_day_label})` : "");
  } else {
    $("data-through").textContent = "—";
    $("data-through").title = avail.error || "availability probe failed";
  }

  const maxYear = state.catalog.years.max;
  $("start").min = state.catalog.years.min + 8;
  $("start").max = maxYear - 8;
  $("end").min = state.catalog.years.min + 8;
  $("end").max = maxYear;
  // default window ends at the newest data year
  if (+$("end").value < maxYear) $("end").value = maxYear;
  if (+$("start").value > maxYear - 8) $("start").value = maxYear - 8;

  $("run").addEventListener("click", analyze);
  $("region").addEventListener("change", onRegionChange);
  $("start").addEventListener("change", clampRange);
  $("end").addEventListener("change", clampRange);
  document.querySelectorAll(".chart-panel .seg-btn").forEach((b) =>
    b.addEventListener("click", () => setMode(b.dataset.mode))
  );

  initSatModal();
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
   VARIABLE LIST
   ============================================================ */
function renderVarList() {
  const box = $("var-list");
  box.innerHTML = "";
  state.catalog.variables.forEach((v) => {
    const on = state.selected.includes(v.id);
    const el = document.createElement("div");
    el.className = "var-item" + (on ? " on" : "");
    el.style.setProperty("--vc", v.color);
    el.innerHTML = `
      <i class="var-dot"></i>
      <span class="var-name">${esc(v.name)}</span>
      <span class="var-unit">${esc(v.unit)}</span>`;
    el.addEventListener("click", () => toggleVar(v.id));
    box.appendChild(el);
  });
  $("var-count").textContent = `${state.selected.length} / ${MAX_VARS}`;
}

function toggleVar(id) {
  const i = state.selected.indexOf(id);
  if (i >= 0) {
    if (state.selected.length === 1) return;
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
  if (state.result) analyze();
}

function renderRegionSelect() {
  const sel = $("region");
  sel.innerHTML = "";
  state.catalog.regions.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.id;
    o.textContent = r.name;
    sel.appendChild(o);
  });
  sel.value = "sahel";
  onRegionChange();
}

function onRegionChange() {
  const r = currentRegion();
  $("region-desc").textContent = r ? r.desc : "";
  $("region-readout").textContent = r
    ? r.name.toUpperCase()
    : "NO REGION SELECTED";
  updateGlobeOverlay();
  if (regionMesh) regionMesh.position.copy(bboxCenter(r.bbox, 1.005));
}

function currentRegion() {
  const id = $("region") ? $("region").value : null;
  return state.catalog.regions.find((r) => r.id === id) || null;
}

function clampRange() {
  let s = +$("start").value;
  let e = +$("end").value;
  if (e - s < 8) {
    if (document.activeElement === $("start")) {
      e = Math.min(2024, s + 8);
    } else {
      s = Math.max(1985, e - 8);
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
  el.className = "hud-status" + (kind === "err" ? " err" : "");
  el.innerHTML = html;
  $("sys-status").textContent =
    kind === "err" ? "ERROR" : kind === "busy" ? "ANALYZING" : "READY";
}

/* ============================================================
   ANALYSIS
   ============================================================ */
async function analyze() {
  const btn = $("run");
  btn.disabled = true;
  setStatus("busy",
    `<span class="spin"></span>ACQUIRING NASA POWER GRID · TESTING TRENDS…`);

  const params = new URLSearchParams({
    variables: state.selected.join(","),
    region: $("region").value,
    start: $("start").value,
    end: $("end").value,
  });

  try {
    const r = await fetch(`/api/analyze?${params}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    state.result = data;
    // default the globe to the most newsworthy variable: first significant
    const firstSig = data.series.findIndex(
      (s) => s.overall && s.overall.ok && s.overall.significant);
    state.activeVarIdx = firstSig >= 0 ? firstSig : 0;
    render();
    setStatus("ok", "");
  } catch (e) {
    setStatus("err", `ANALYSIS FAILED: ${esc(e.message)}`);
  } finally {
    btn.disabled = false;
  }
}

/* ============================================================
   RENDER
   ============================================================ */
function render() {
  const d = state.result;
  renderHeader(d);
  renderSignals(d);
  renderCells(d);
  renderLegend(d);
  renderSatellite(d);
  renderLiterature(d);
  drawChart();
  renderGlobeRegions(d);
  updateGlobeOverlay();
}

function renderLiterature(d) {
  const box = $("lit-list");
  const s = d.series[Math.min(state.activeVarIdx, d.series.length - 1)];
  const lit = (s && s.literature) || { ok: false, papers: [] };
  if (!lit.ok) {
    $("lit-tag").textContent = "OFFLINE";
    box.innerHTML =
      `<div class="lit-empty">Literature lookup unavailable — analysis unaffected.</div>`;
    return;
  }
  const papers = lit.papers || [];
  if (!papers.length) {
    $("lit-tag").textContent = "NONE";
    box.innerHTML = `<div class="lit-empty">No close matches for this variable + region.</div>`;
    return;
  }
  $("lit-tag").textContent =
    `${papers.length} · ${s.variable.name.split(" ")[0].toUpperCase()}`;
  box.innerHTML = papers.slice(0, 2).map((p) => {
    const href = p.doi
      ? `https://doi.org/${encodeURIComponent(p.doi)}` : "#";
    return `<a class="lit-item" href="${esc(href)}" target="_blank"
      rel="noopener noreferrer">
      <div class="lt">${esc(p.title)}</div>
      <div class="lm">
        ${p.year ? `<span class="yr">${p.year}</span>` : ""}
        ${p.citations ? `<span class="cit">${p.citations} cites</span>` : ""}
        ${p.venue ? `<span>${esc(String(p.venue).slice(0, 26))}</span>` : ""}
      </div>
    </a>`;
  }).join("");
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
    li.addEventListener("click", () => {
      state.activeVarIdx = i;
      renderHeader(d);
      renderSignals(d);
      renderLegend(d);
      renderCells(d);
      renderLiterature(d);
      drawChart();
      renderGlobeRegions(d);
    });
    box.appendChild(li);
  });
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
      dir === "rising" ? "▲ RISING" :
      dir === "falling" ? "▼ FALLING" :
      dir === "flat" ? "◆ STABLE" : "— NODATA";
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
        <span>SLOPE <b>${o.ok ? (o.per_decade > 0 ? "+" : "") +
          num(o.per_decade, 3) : "—"}</b></span>
        <span>p <b>${o.ok ? (o.p < 0.001 ? "<0.001" : num(o.p, 3)) : "—"}</b></span>
      </div>`;
    el.addEventListener("click", () => {
      state.activeVarIdx = i;
      renderHeader(d);
      renderSignals(d);
      renderLegend(d);
      renderCells(d);
      renderLiterature(d);
      drawChart();
      renderGlobeRegions(d);
    });
    box.appendChild(el);
  });
}

function renderCells(d) {
  const box = $("cell-summary");
  box.innerHTML = "";
  const s = d.series[state.activeVarIdx] || d.series[0];
  const sm = s.summary;
  $("cell-tag").textContent =
    `${sm.significant_cells}/${sm.total_cells} SIG · ${s.variable.name.split(" ")[0]}`;

  const rows = [
    ["RISING", sm.rising, C.rise],
    ["FALLING", sm.falling, C.fall],
    ["NO TREND", sm.total_cells - sm.significant_cells, C.flat],
  ];
  const max = Math.max(1, sm.total_cells);
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
        WORLDVIEW ↗
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
    cbBtn.textContent = "🛰️ ORBITAL VIEW";
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

  const applyBtn = $("modal-date-apply");
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      const val = ($("modal-date-picker").value || "").trim();
      if (/^\d{2}-\d{2}$/.test(val)) {
        state.satCustomDate = val;
        reloadModalSatellite();
      } else {
        alert("Please enter a valid MM-DD date format (e.g. 08-15).");
      }
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

function openSatelliteModal(customBbox = null, customTitle = null) {
  const modal = $("sat-modal");
  if (!modal) return;

  modal.hidden = false;
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
    if ($("modal-date-picker")) $("modal-date-picker").value = state.satCustomDate;
  }

  const targetBbox = customBbox || (state.result && state.result.region ? state.result.region.bbox : null);
  const targetTitle = customTitle || (state.result && state.result.region ? state.result.region.name : "Selected Region");

  state.activeSatBbox = targetBbox;
  state.activeSatTitle = targetTitle;

  reloadModalSatellite();
}

function closeSatelliteModal() {
  const modal = $("sat-modal");
  if (modal) modal.hidden = true;
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
  if ($("slider-info-left")) $("slider-info-left").textContent = `◀ LEFT: ${sat.baseline.date}`;
  if ($("slider-info-right")) $("slider-info-right").textContent = `RIGHT: ${sat.recent.date} ▶`;

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
   CHART
   ============================================================ */
function drawChart() {
  const d = state.result;
  if (!d) return;
  const s = d.series[state.activeVarIdx] || d.series[0];
  const ctx = $("chart").getContext("2d");
  const isYear = state.mode === "yearly";

  const labels = isYear
    ? s.yearly_timeseries.map((p) => p.year)
    : d.months;
  const values = isYear
    ? s.yearly_timeseries.map((p) => p.value)
    : s.region_timeseries;
  // partial years (e.g. the current year, still accumulating months) are drawn
  // but excluded from every trend calculation — see _annualize() on the server
  const partialFlags = isYear
    ? s.yearly_timeseries.map((p) => !p.complete)
    : [];
  const partialYears = isYear
    ? s.yearly_timeseries.filter((p) => !p.complete)
    : [];

  if (chart) chart.destroy();

  const o = s.overall;
  const accent = o.ok && o.direction === "falling" ? C.fall :
    (s.variable.color || C.rise);

  const grad = ctx.createLinearGradient(0, 0, 0, 130);
  grad.addColorStop(0, hexA(accent, 0.34));
  grad.addColorStop(1, hexA(accent, 0.01));

  const datasets = [{
    // partial years are withheld from the connected line: a 9-month mean is not
    // comparable to an annual mean, so it must not appear joined to the series
    data: values.map((v, i) => (partialFlags[i] ? null : v)),
    borderColor: accent,
    backgroundColor: grad,
    fill: true,
    tension: 0.3,
    pointRadius: isYear ? 0 : 0,
    pointHoverRadius: 4,
    borderWidth: 1.6,
    spanGaps: true,
  }];

  const pts = values.map((v, i) => [i, v]).filter((p) => p[1] !== null);
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
    datasets.push({
      data: values.map((_, i) => (partialFlags[i] ? null : line(i))),
      borderColor: "#e9ebed",
      borderDash: [5, 4],
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
      tension: 0,
    });
  }

  // mark incomplete years: hollow diamonds, never part of the trend line
  if (partialFlags.some(Boolean)) {
    datasets.push({
      data: values.map((v, i) => (partialFlags[i] ? v : null)),
      showLine: false,
      borderColor: "transparent",
      backgroundColor: "#0b0c0d",
      borderWidth: 1.5,
      pointBackgroundColor: "#0b0c0d",
      pointBorderColor: "#e9ebed",
      pointBorderWidth: 1.5,
      pointRadius: 4.5,
      pointHoverRadius: 6,
      pointStyle: "rectRot",
    });
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
          borderColor: "#3b3e44",
          borderWidth: 1,
          titleFont: { family: "monospace", size: 10 },
          bodyFont: { family: "monospace", size: 10 },
          titleColor: "#e9ebed",
          bodyColor: "#b9bdc2",
          displayColors: false,
          callbacks: {
            label: (c) =>
              `${num(c.parsed.y, 3)} ${s.variable.unit}`,
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#6d7276",
            maxTicksLimit: isYear ? 8 : 6,
            maxRotation: 0,
            font: { family: "monospace", size: 9 },
            callback: function (val) {
              const raw = this.getLabelForValue(val);
              return isYear ? String(raw).slice(2) : String(raw).slice(0, 4);
            },
          },
          grid: { color: "#1c1e21", tickLength: 3 },
          border: { color: "#2a2d31" },
        },
        y: {
          ticks: {
            color: "#6d7276",
            maxTicksLimit: 5,
            font: { family: "monospace", size: 9 },
          },
          grid: { color: "#1c1e21", tickLength: 3 },
          border: { color: "#2a2d31" },
        },
      },
    },
  });

  const partialNote = partialYears.length
    ? `<br><span style="color:#8c9297">◇ ${
        partialYears.map((p) => `${p.year} partial (${p.months}/12 mo)`)
          .join(" · ")} — shown, excluded from trend</span>`
    : "";

  $("trendline").innerHTML = (o.ok
    ? `<b>${s.variable.name}</b> ${o.direction === "rising" ? "rising" :
       o.direction === "falling" ? "falling" : "flat"} at
       <b>${o.per_decade > 0 ? "+" : ""}${num(o.per_decade, 3)}
       ${esc(s.variable.unit)}/decade</b> · MK z=<b>${num(o.z, 2)}</b>
       p=<b>${o.p < 0.001 ? "<0.001" : num(o.p, 3)}</b>
       ${o.significant ? "· SIGNIFICANT" : "· NOT SIGNIFICANT"}
       · n=<b>${o.n}</b> complete years`
    : "Insufficient data for trend estimation.") + partialNote;
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
let landPoints, gridLines, regionMesh, haloMesh, atmosphere, pickSphere;
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
    antialias: true, alpha: true, powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h);
  host.appendChild(renderer.domElement);

  globeGroup = new THREE.Group();
  globeGroup.rotation.y = -0.6;
  scene.add(globeGroup);

  try {
    const r = await fetch("land_dots.json");
    landData = await r.json();
  } catch (e) {
    landData = [];
  }

  buildLandDots();
  buildGridLines();
  buildAtmosphere();
  buildRegionMesh();

  // invisible sphere used to convert a click into a lat/lon
  pickSphere = new THREE.Mesh(
    new THREE.SphereGeometry(0.995, 32, 32),
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

  for (let lat = -60; lat <= 60; lat += 30) {
    const pts = [];
    for (let lon = -180; lon <= 180; lon += 3) {
      pts.push(latLonToVec3(lat, lon, R * 0.999));
    }
    globeGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts), mat));
  }
  for (let lon = -180; lon < 180; lon += 30) {
    const pts = [];
    for (let lat = -90; lat <= 90; lat += 3) {
      pts.push(latLonToVec3(lat, lon, R * 0.999));
    }
    globeGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts), mat));
  }
}

function buildAtmosphere() {
  const geo = new THREE.SphereGeometry(1.10, 48, 48);
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: { uColor: { value: new THREE.Color("#c9ced3") } },
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
        float a = pow(rim, 3.4) * 0.34;
        gl_FragColor = vec4(uColor, a);
      }`,
  });
  atmosphere = new THREE.Mesh(geo, mat);
  scene.add(atmosphere);

  haloMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.985, 48, 48),
    new THREE.MeshBasicMaterial({ color: 0x101214 })
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

/* ---------- interactive region markers ---------- */
function renderGlobeRegions(d) {
  regionMarkers.forEach((m) => globeGroup.remove(m));
  regionMarkers = [];

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

  const MAG = 2.8; // visually amplify the small region so cells are readable
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

      const base = isActive ? 0.019 : 0.008;
      const size = base + Math.min(isActive ? 0.016 : 0.004,
        Math.abs(c.slope) * 0.04);
      const geo = new THREE.SphereGeometry(size, 8, 8);
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

  // pulsing ring bounding the analyzed region (matches amplified grid spread)
  const bw = Math.abs(d.grid.bbox[2] - d.grid.bbox[0]) * MAG;
  const bh = Math.abs(d.grid.bbox[3] - d.grid.bbox[1]) * MAG;
  const angRad = (Math.max(bw, bh) / 2) * Math.PI / 180 * 1.15;
  const ringGeo = new THREE.RingGeometry(
    Math.max(0.02, angRad * 0.9), Math.max(0.024, angRad), 64, 1);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0xf0f2f4, side: THREE.DoubleSide, transparent: true,
    opacity: 0.7, depthWrite: false, depthTest: false,
  });
  const c0 = bboxCenter(d.grid.bbox, 1);
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.position.copy(c0.clone().multiplyScalar(1.014));
  ring.lookAt(c0.clone().multiplyScalar(2));
  ring.renderOrder = 9;
  ring.userData = { pulsing: true };
  globeGroup.add(ring);
  regionMarkers.push(ring);
}

function updateGlobeOverlay() {
  const n = state.selected.length;
  const g = $("globe-title");
  if (n === 1) {
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
        <div class="tt-row"><span>TREND</span><b style="color:${c.significant ? (c.direction === "falling" ? C.fall : C.rise) : "#8c9297"}">${dir}</b></div>`;
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

/* Tap the globe -> analyze the nearest preset region. */
function selectNearestRegion(lat, lon) {
  let best = null;
  let bestD = Infinity;
  state.catalog.regions.forEach((r) => {
    const b = r.bbox;
    const cLat = (b[1] + b[3]) / 2;
    const cLon = (b[0] + b[2]) / 2;
    let dLon = Math.abs(lon - cLon);
    if (dLon > 180) dLon = 360 - dLon;
    const d = Math.hypot(lat - cLat, dLon);
    if (d < bestD) { bestD = d; best = r; }
  });
  if (!best) return;
  if ($("region").value === best.id) return;
  $("region").value = best.id;
  onRegionChange();
  analyze();
  flashHint(`${best.name.toUpperCase()} SELECTED — ANALYZING`);
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
    cbBtn.textContent = `🛰️ CELL (${c.lat.toFixed(1)}°, ${c.lon.toFixed(1)}°)`;
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
  renderer.render(scene, camera);
}

boot();
