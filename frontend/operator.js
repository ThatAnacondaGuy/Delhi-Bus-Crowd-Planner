/* Operator view: ranked extra trips, corridor map with a time slider, route heat strip.
   Every number shown comes from the API. API strings are inserted with textContent / createElement only. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  // data.js: the browser's own fetch in API mode, the precomputed files in the static demo
  const CD = window.CrowdData || { static: false, fetch: window.fetch.bind(window), link: (u) => u };
  const NUM = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  const DEC = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const STEP = { weekday: 30, weekend: 60 };        // minutes between windows (design 5.3)
  const TOP_N = 20;                                 // ranked rows per operator
  const CSV_LIMIT = 1000;                           // rows in the CSV download
  const MAP_LIMIT = 5000;                           // corridor stretches drawn per window (busiest first)
  const OPERATORS = { DTC: "DTC", DIMTS: "Cluster (DIMTS)" };
  const DAY_WORD = { weekday: "weekday", weekend: "weekend" };

  const LEVEL = {
    seats: { word: "Seats", glyph: "○", color: "#0f766e" },
    standing: { word: "Standing", glyph: "◐", color: "#b45309" },
    crowded: { word: "Crowded", glyph: "●", color: "#8f1d1d" },
    no_data: { word: "No data", glyph: "·", color: "#5f6670" },
  };
  const EVIDENCE = { many_tickets: "based on many tickets", rough: "rough guess (few tickets)", none: "no data" };
  const FLAG_WORDS = {
    scaled_to_capacity: "scaled to bus capacity (high app use)",
    low_app_use: "low app use",
    full: "full (real demand likely higher)",
    schedule_mismatch: "schedule mismatch",
    alighting_sensitive: "less certain near the end of the route",
    office_special: "office special",
    rho_fallback: "bus frequency estimated from similar routes",
  };
  const BUS_SOURCE = {
    gps: "buses that ran (from GPS)",
    schedule: "estimate: buses on the timetable",
    widened: "estimate: buses on the timetable, searched over a wider time",
    none: "estimate: no bus count available",
  };
  // map colour bins: words always travel with the colour
  const BASIS = {
    load_ratio: {
      key: "load_ratio",
      title: "People per rated capacity",
      bins: [
        { lv: "seats", max: 0.4, label: "Seats free: under 0.4 of rated capacity", weight: 2 },
        { lv: "standing", max: 1.0, label: "Standing: 0.4 to 1.0", weight: 4 },
        { lv: "crowded", max: Infinity, label: "Crowded: over 1.0", weight: 7 },
      ],
      text: (v) => `${DEC.format(v)} people per place the bus is rated for`,
    },
    share_crowded: {
      key: "share_crowded",
      title: "Buses crowded",
      bins: [
        { lv: "seats", max: 0.0001, label: "No bus crowded", weight: 2 },
        { lv: "standing", max: 0.5, label: "Some buses crowded: under half", weight: 4 },
        { lv: "crowded", max: Infinity, label: "Most buses crowded: half or more", weight: 7 },
      ],
      text: (v) => `${NUM.format(v * 100)} in 100 buses crowded`,
    },
  };

  const state = {
    day: "weekday",
    operator: "DTC",
    trips: { DTC: [], DIMTS: [] },
    basis: "load_ratio",
    win: 18,                         // slider index
    selected: null,                  // {route_id, short_name, direction, depart_min, operator}
    map: null, layer: null, fitted: false,
    seq: { trips: 0, map: 0, strip: 0 },
  };

  // ---------------------------------------------------------------- helpers

  function h(tag, cls, ...kids) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    for (const k of kids) if (k != null && k !== false) el.append(k);
    return el;
  }

  const hhmm = (min) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
  const nWin = () => Math.floor(1440 / STEP[state.day]);
  const winLabel = (i) => hhmm(i * STEP[state.day]);
  const nice = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : "");

  async function getJSON(url) {
    const res = await CD.fetch(url);
    if (!res.ok) {
      let msg = `${res.status}`;
      try { const b = await res.json(); if (b && typeof b.detail === "string") msg = b.detail; } catch (e) { /* keep status */ }
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  function say(text) { $("status").textContent = text || ""; }
  function problem(text) {
    const box = $("problem");
    box.textContent = text || "";
    box.hidden = !text;
  }

  function legendInto(box, items) {
    box.replaceChildren(...items.map((it) => h("span", "l-" + it.lv, it.label)));
  }

  // ---------------------------------------------------------------- ranked table

  function flagWords(flags) {
    return String(flags || "").split(",").filter(Boolean)
      .map((f) => FLAG_WORDS[f] || f.replace(/_/g, " "));
  }

  function csvHref() {
    const q = new URLSearchParams({ day: state.day, operator: state.operator, limit: String(CSV_LIMIT) });
    return CD.link(`/v1/operator/trips.csv?${q.toString()}`);
  }

  function renderCsv() {
    const a = $("csv");
    a.href = csvHref();
    a.setAttribute("download", `operator_trips_${state.day}.csv`);
    a.textContent = "Download CSV";
    a.title = CD.static
      ? `The ranked extra trips for both operators on a ${DAY_WORD[state.day]}`
      : `Top ${NUM.format(CSV_LIMIT)} extra trips for ${OPERATORS[state.operator]} on a ${DAY_WORD[state.day]}`;
  }

  // Headline tiles: sums over the rows the table is showing, so they always match it (nothing typed in)
  function renderTiles() {
    const box = $("tiles");
    const rows = state.trips[state.operator] || [];
    box.hidden = !rows.length;
    if (!rows.length) { box.replaceChildren(); return; }
    const sum = (k) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);
    const routes = new Set(rows.map((r) => r.route_id));
    const scaled = new Set(rows.filter((r) => String(r.flags || "").split(",").includes("scaled_to_capacity")).map((r) => r.route_id));
    const who = `${OPERATORS[state.operator]}, ${DAY_WORD[state.day]}`;
    const tile = (value, label, note) => h("div", "op-tile", h("p", "op-tile-num", value), h("p", "op-tile-label", label), h("p", "op-tile-note", note));
    box.replaceChildren(
      tile(NUM.format(sum("crowded_rider_min_removed")), "Crowded rider-minutes removed",
        `If one extra bus ran on each of the ${NUM.format(rows.length)} departures listed (${who}).`),
      tile(NUM.format(sum("riders_moved_down")), "Riders moved down a level",
        "Riders who would go from crowded to standing, or from standing to seats."),
      tile(`${NUM.format(scaled.size)} of ${NUM.format(routes.size)}`, "Listed routes scaled to bus capacity",
        "Counts on these routes were scaled down to fit what their buses can carry."));
  }

  function renderTrips() {
    renderTiles();
    const rows = state.trips[state.operator] || [];
    $("trips-caption").textContent = `Extra trips that help most: ${OPERATORS[state.operator]}, ${DAY_WORD[state.day]}`;
    $("trips-sub").textContent = `One extra bus on each of these departures would take the most people out of crowded buses. Top ${TOP_N} for ${OPERATORS[state.operator]} on a ${DAY_WORD[state.day]}.`;
    const body = $("trips-body");
    if (!rows.length) {
      const td = h("td", "op-empty", `No extra trips are ranked for ${OPERATORS[state.operator]} on a ${DAY_WORD[state.day]}.`);
      td.colSpan = 10;
      body.replaceChildren(h("tr", "", td));
      return;
    }
    const sel = state.selected;
    body.replaceChildren(...rows.map((r, i) => {
      const on = sel && sel.route_id === r.route_id && sel.depart_min === r.depart_min && sel.direction === r.direction;
      const btn = h("button", "op-route", r.short_name);
      btn.type = "button";
      btn.setAttribute("aria-label", `Show the heat strip for route ${r.short_name}, departing ${r.depart}`);
      btn.addEventListener("click", () => selectRoute(r));
      const flags = h("td", "op-flags");
      for (const w of flagWords(r.flags)) flags.append(h("span", "op-flag", w));
      const tr = h("tr", on ? "is-selected" : "",
        h("td", "op-rank", String(i + 1)),
        h("td", "", btn),
        h("td", "", nice(r.direction)),
        h("td", "op-time", r.depart),
        h("td", "num", NUM.format(r.crowded_rider_min_removed)),
        h("td", "num", NUM.format(r.riders_moved_down)),
        h("td", "op-section", r.max_load_section || ""),
        h("td", "num", r.peak_load_factor == null ? "" : DEC.format(r.peak_load_factor)),
        h("td", "num", r.evidence_share == null ? "" : `${NUM.format(r.evidence_share * 100)}%`),
        flags);
      tr.dataset.routeId = String(r.route_id);
      return tr;
    }));
  }

  async function loadTrips() {
    const id = ++state.seq.trips;
    say("Loading the ranked extra trips");
    problem("");
    try {
      const [a, b] = await Promise.all(["DTC", "DIMTS"].map((op) =>
        getJSON(`/v1/operator/trips?${new URLSearchParams({ day: state.day, operator: op, limit: String(TOP_N) })}`)));
      if (id !== state.seq.trips) return;
      state.trips.DTC = a.trips || [];
      state.trips.DIMTS = b.trips || [];
      renderTrips();
      renderCsv();
      say("");
      const first = (state.trips[state.operator] || [])[0];
      if (first) selectRoute(first, true);
      else clearStrip(`No ranked trips for ${OPERATORS[state.operator]} on a ${DAY_WORD[state.day]}.`);
    } catch (e) {
      if (id !== state.seq.trips) return;
      say("");
      problem(`The ranked table could not load: ${e.message}. Try again in a moment.`);
    }
  }

  // ---------------------------------------------------------------- Leaflet (pinned 1.9.4, same files and SRI as the commuter map)

  let leafletPromise = null;
  function loadLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    if (leafletPromise) return leafletPromise;
    leafletPromise = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      css.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
      css.crossOrigin = "";
      document.head.append(css);
      const js = document.createElement("script");
      js.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      js.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
      js.crossOrigin = "";
      js.onload = () => (window.L ? resolve(window.L) : reject(new Error("no leaflet")));
      js.onerror = () => { leafletPromise = null; reject(new Error("leaflet failed")); };
      document.head.append(js);
    });
    return leafletPromise;
  }

  // ---------------------------------------------------------------- corridor map and slider

  function binFor(basis, v) {
    if (v == null || Number.isNaN(v)) return null;
    for (const b of BASIS[basis].bins) if (v < b.max) return b;
    return BASIS[basis].bins[BASIS[basis].bins.length - 1];
  }

  function renderMapLegend() {
    const b = BASIS[state.basis];
    legendInto($("map-legend"), b.bins.concat([{ lv: "no_data", label: "No data" }]));
  }

  // readable time labels under the slider: every six hours, placed where the thumb would sit
  function renderTicks() {
    const n = nWin();
    const idx = [0, 6, 12, 18].map((hr) => Math.round((hr * 60) / STEP[state.day])).concat([n - 1]);
    $("ticks").replaceChildren(...idx.map((i) => {
      const t = h("span", "op-tick", winLabel(i));
      t.style.left = `${(i / (n - 1)) * 100}%`;
      return t;
    }));
  }

  function renderSliderLabels() {
    renderTicks();
    const s = $("slider");
    const i = Number(s.value);
    $("slider-label").textContent = winLabel(i);
    $("slider-note").textContent = `Window ${i + 1} of ${nWin()}, one every ${STEP[state.day]} minutes`;
    s.setAttribute("aria-valuetext", `${winLabel(i)}`);
  }

  function configureSlider(keepTime) {
    const s = $("slider");
    s.min = "0";
    s.max = String(nWin() - 1);
    s.step = "1";
    const minute = keepTime == null ? 540 : keepTime;       // 09:00 on first load
    state.win = Math.min(nWin() - 1, Math.round(minute / STEP[state.day]));
    s.value = String(state.win);
    renderSliderLabels();
  }

  async function ensureMap() {
    if (state.map) return state.map;
    const L = await loadLeaflet();
    if (state.map) return state.map;
    const map = L.map($("map"), { preferCanvas: true }).setView([28.6139, 77.209], 11);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    state.map = map;
    state.layer = L.layerGroup().addTo(map);
    setTimeout(() => map.invalidateSize(), 50);
    return map;
  }

  function tipText(p) {
    const bits = [];
    if (p.load_ratio != null) bits.push(BASIS.load_ratio.text(p.load_ratio));
    if (p.share_crowded != null) bits.push(BASIS.share_crowded.text(p.share_crowded));
    if (p.buses != null) bits.push(`${DEC.format(p.buses)} buses in the window`);
    if (p.routes != null) bits.push(`${NUM.format(p.routes)} routes`);
    if (p.crowded_rider_min != null) bits.push(`${NUM.format(p.crowded_rider_min)} crowded rider-minutes`);
    return bits.join("; ");
  }

  function drawCorridors(L, fc) {
    state.layer.clearLayers();
    const feats = (fc.features || []).filter((f) => f.geometry);
    const canvas = L.canvas({ padding: 0.4 });
    const key = state.basis;
    const group = [];
    // draw the quiet stretches first so the crowded ones sit on top
    const order = feats.slice().sort((a, b) => (a.properties[key] || 0) - (b.properties[key] || 0));
    for (const f of order) {
      const v = f.properties[key];
      const bin = binFor(key, v);
      const lv = bin ? bin.lv : "no_data";
      const layer = L.geoJSON(f, {
        renderer: canvas,
        style: () => ({ color: LEVEL[lv].color, weight: bin ? bin.weight : 2, opacity: 0.85, dashArray: bin ? null : "4 6" }),
      });
      layer.bindTooltip(`${bin ? bin.label.split(":")[0] : "No data"}. ${tipText(f.properties)}`, { sticky: true });
      layer.addTo(state.layer);
      group.push(layer);
    }
    if (!state.fitted && group.length) {
      const bounds = L.featureGroup(group).getBounds();
      if (bounds.isValid()) { state.map.fitBounds(bounds, { padding: [20, 20] }); state.fitted = true; }
    }
    return { drawn: feats.length, total: (fc.features || []).length };
  }

  async function loadMap() {
    const id = ++state.seq.map;
    const start = winLabel(state.win);
    try {
      const [L, fc] = await Promise.all([
        loadLeaflet().catch(() => null),
        getJSON(`/v1/corridors?${new URLSearchParams({ day: state.day, window: start, limit: String(MAP_LIMIT) })}`),
      ]);
      if (id !== state.seq.map) return;
      if (!L) { $("map-sub").textContent = "The map library could not load (no connection to the map servers), so the map is not drawn."; return; }
      await ensureMap();
      if (id !== state.seq.map) return;
      const r = drawCorridors(L, fc);
      $("map-sub").textContent = `${NUM.format(r.drawn)} corridor stretches at ${start} on a ${DAY_WORD[state.day]}, the ones with the most crowded rider-minutes first. Thicker lines are more crowded.${CD.static ? " The demo includes only the busiest stretches." : ""}`;
    } catch (e) {
      if (id !== state.seq.map) return;
      $("map-sub").textContent = `The corridor map could not load: ${e.message}.`;
    }
  }

  let sliderTimer = null;
  function onSlider(commit) {
    state.win = Number($("slider").value);
    renderSliderLabels();
    clearTimeout(sliderTimer);
    if (commit) loadMap(); else sliderTimer = setTimeout(loadMap, 150);
  }

  // ---------------------------------------------------------------- route heat strip

  const heat = { active: null, cells: new Map() };

  function clearStrip(msg) {
    $("strip-sub").textContent = msg;
    $("heat").replaceChildren();
    $("cell-detail").textContent = "Select a cell to see its detail.";
  }

  function selectRoute(r, quiet) {
    state.selected = { route_id: r.route_id, short_name: r.short_name, direction: r.direction, depart_min: r.depart_min, depart: r.depart, operator: r.operator };
    document.querySelectorAll("#trips-body tr").forEach((tr) => tr.classList.toggle("is-selected",
      tr.dataset.routeId === String(r.route_id) && tr.children[3] && tr.children[3].textContent === r.depart));
    loadStrip();
    if (!quiet) $("strip-title").scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function cellLabel(win, row, s) {
    if (!s) return `${win}, ${row}: no data`;
    const lv = LEVEL[s.level] || LEVEL.no_data;
    const ppl = s.people && s.people[1] != null ? `, about ${NUM.format(s.people[1])} people on board` : "";
    return `${win}, ${row}: ${lv.word}${ppl}, ${EVIDENCE[s.evidence] || EVIDENCE.none}`;
  }

  function showCell(td) {
    const info = heat.cells.get(td);
    if (!info) return;
    const { win, s, from, to } = info;
    const box = $("cell-detail");
    const lv = s ? (LEVEL[s.level] || LEVEL.no_data) : LEVEL.no_data;
    const parts = [h("strong", "", `${win}, ${from} to ${to}`), h("span", "chip lvl-" + (s ? s.level : "no_data"), `${lv.glyph} ${lv.word}`)];
    const lines = [];
    if (s) {
      const [lo, mid, hi] = s.people || [];
      if (mid != null) lines.push(`About ${NUM.format(mid)} people on board per bus (range ${NUM.format(lo)} to ${NUM.format(hi)}).`);
      if (s.seats != null && s.rated_total != null) lines.push(`The bus has ${NUM.format(s.seats)} seats and is rated for ${NUM.format(s.rated_total)} people${s.crush != null ? `, crush ${NUM.format(s.crush)}` : ""}.`);
      if (mid != null && s.rated_total) lines.push(`Load factor ${DEC.format(mid / s.rated_total)}.`);
      if (s.buses != null) lines.push(`${NUM.format(Math.round(s.buses * 10) / 10)} buses, ${BUS_SOURCE[s.bus_source] || "estimate"}.`);
      lines.push(`Evidence: ${EVIDENCE[s.evidence] || EVIDENCE.none}.`);
      const fl = flagWords((s.flags || []).join(","));
      if (fl.length) lines.push(`Notes: ${fl.join("; ")}.`);
    } else {
      lines.push("There is no row for this stretch in this window.");
    }
    box.replaceChildren(h("div", "op-detail-head", ...parts), ...lines.map((t) => h("p", "", t)));
  }

  function setActiveCell(td, focus) {
    if (heat.active && heat.active !== td) heat.active.tabIndex = -1;
    heat.active = td;
    td.tabIndex = 0;
    td.classList.add("is-active");
    document.querySelectorAll("#heat td.is-active").forEach((o) => { if (o !== td) o.classList.remove("is-active"); });
    if (focus) td.focus({ preventScroll: false });
    showCell(td);
  }

  function renderStrip(data, sel) {
    const step = STEP[state.day];
    const nw = nWin();
    const starts = Array.from({ length: nw }, (_, i) => hhmm(i * step));
    const byWin = new Map();
    for (const w of data.windows || []) byWin.set(w.start, w);
    // rows: every stretch the route has, in route order
    const rows = new Map();
    for (const w of data.windows || []) for (const s of w.stretches) if (!rows.has(s.seq)) rows.set(s.seq, { seq: s.seq, from: s.from_name, to: s.to_name });
    const seqs = Array.from(rows.keys()).sort((a, b) => a - b);
    const depCol = Math.round(sel.depart_min / step) % nw;

    const table = $("heat");
    heat.cells = new Map();
    heat.active = null;

    const cap = h("caption", "sr-only", `Crowding of route ${data.route} by stretch and time of day on a ${DAY_WORD[state.day]}. Rows are stretches in route order, columns are time windows.`);
    const hr = h("tr", "");
    const corner = h("th", "op-corner", "Stretch");
    corner.scope = "col";
    hr.append(corner);
    starts.forEach((s, i) => {
      const th = h("th", "op-hour" + (i === depCol ? " is-dep" : ""), s.endsWith(":00") && (i % (step === 30 ? 2 : 1) === 0) ? s.slice(0, 2) : "");
      th.scope = "col";
      th.setAttribute("aria-label", i === depCol ? `${s}, the extra trip departs in this window` : s);
      hr.append(th);
    });
    const thead = h("thead", "", hr);

    const body = h("tbody", "");
    for (const seq of seqs) {
      const info = rows.get(seq);
      const th = h("th", "op-rowhead", `${seq}. ${info.from}`);
      th.scope = "row";
      th.title = `${info.from} to ${info.to}`;
      const tr = h("tr", "", th);
      starts.forEach((win, i) => {
        const w = byWin.get(win);
        const s = w ? w.stretches.find((x) => x.seq === seq) : null;
        const lv = s ? (LEVEL[s.level] ? s.level : "no_data") : "no_data";
        const td = h("td", `op-cell lvl-${lv}` + (i === depCol ? " is-dep" : ""), LEVEL[lv].glyph);
        td.tabIndex = -1;
        td.setAttribute("aria-label", cellLabel(win, `${info.from} to ${info.to}`, s));
        heat.cells.set(td, { win, s, from: info.from, to: info.to, seq, col: i });
        tr.append(td);
      });
      body.append(tr);
    }
    table.replaceChildren(cap, thead, body);
    const firstCell = body.querySelector("td");
    if (firstCell) { firstCell.tabIndex = 0; heat.active = firstCell; }
    // bring the departure column into view
    const scroller = $("strip-scroll");
    const dep = body.querySelector("td.is-dep");
    if (dep) scroller.scrollLeft = Math.max(0, dep.offsetLeft - scroller.clientWidth / 2);
    scroller.scrollTop = 0;
    $("cell-detail").textContent = "Select a cell to see its detail.";
  }

  async function loadStrip() {
    const sel = state.selected;
    if (!sel) return;
    const id = ++state.seq.strip;
    $("strip-title").textContent = `Route heat strip: ${sel.short_name}`;
    $("strip-sub").textContent = `Loading route ${sel.short_name}`;
    try {
      const data = await getJSON(`/v1/crowding?${new URLSearchParams({ route_id: String(sel.route_id), day: state.day })}`);
      if (id !== state.seq.strip) return;
      renderStrip(data, sel);
      $("strip-sub").textContent = `Route ${data.route} (${OPERATORS[sel.operator] || sel.operator}), ${DAY_WORD[state.day]}. Each row is a stretch between two stops, in route order. Each column is a ${STEP[state.day]}-minute window. The outlined column is when the extra trip would depart (${sel.depart}).`;
    } catch (e) {
      if (id !== state.seq.strip) return;
      clearStrip(`The heat strip for route ${sel.short_name} could not load: ${e.message}.`);
    }
  }

  function onHeatKey(ev) {
    const td = ev.target.closest && ev.target.closest("td.op-cell");
    if (!td) return;
    const info = heat.cells.get(td);
    const moves = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
    const m = moves[ev.key];
    if (!m || !info) return;
    ev.preventDefault();
    const tr = td.parentElement;
    const target = m[0] === 0 ? (m[1] < 0 ? td.previousElementSibling : td.nextElementSibling)
      : (() => { const t2 = m[0] < 0 ? tr.previousElementSibling : tr.nextElementSibling; return t2 ? t2.children[info.col + 1] : null; })();
    if (target && target.classList.contains("op-cell")) setActiveCell(target, true);
  }

  // ---------------------------------------------------------------- wiring

  function setDay(day) {
    if (day === state.day) return;
    const minute = state.win * STEP[state.day];
    state.day = day;
    document.querySelectorAll("[data-day]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.day === day)));
    state.selected = null;
    configureSlider(minute);
    renderCsv();
    loadTrips();
    loadMap();
  }

  function setOperator(op) {
    state.operator = op;
    document.querySelectorAll("[data-operator]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.operator === op)));
    renderTrips();
    renderCsv();
    const first = (state.trips[op] || [])[0];
    if (first) selectRoute(first, true);
    else clearStrip(`No ranked trips for ${OPERATORS[op]} on a ${DAY_WORD[state.day]}.`);
  }

  function setBasis(key) {
    state.basis = key;
    document.querySelectorAll("[data-basis]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.basis === key)));
    renderMapLegend();
    loadMap();
  }

  async function loadHealth() {
    try {
      const body = await getJSON("/v1/health");
      if (body.data_version) $("version").textContent = `Data version ${body.data_version}`;
    } catch (e) { /* the version line is simply left out */ }
  }

  function init() {
    if (CD.static) CD.banner($("demo-banner"), "operator").catch(() => { /* the banner is optional */ });
    document.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => setDay(b.dataset.day)));
    document.querySelectorAll("[data-operator]").forEach((b) => b.addEventListener("click", () => setOperator(b.dataset.operator)));
    document.querySelectorAll("[data-basis]").forEach((b) => b.addEventListener("click", () => setBasis(b.dataset.basis)));
    $("slider").addEventListener("input", () => onSlider(false));
    $("slider").addEventListener("change", () => onSlider(true));
    const heatEl = $("heat");
    heatEl.addEventListener("click", (ev) => { const td = ev.target.closest("td.op-cell"); if (td) setActiveCell(td, false); });
    heatEl.addEventListener("keydown", onHeatKey);
    heatEl.addEventListener("focusin", (ev) => { const td = ev.target.closest && ev.target.closest("td.op-cell"); if (td && td !== heat.active) setActiveCell(td, false); });
    legendInto($("strip-legend"), [
      { lv: "seats", label: `${LEVEL.seats.glyph} Seats: seats are usually free` },
      { lv: "standing", label: `${LEVEL.standing.glyph} Standing: some standing` },
      { lv: "crowded", label: `${LEVEL.crowded.glyph} Crowded: more people than the bus is rated for` },
      { lv: "no_data", label: `${LEVEL.no_data.glyph} No data` },
    ]);
    configureSlider(null);
    renderMapLegend();
    renderCsv();
    loadHealth();
    loadTrips();
    loadMap();
  }

  init();
})();
