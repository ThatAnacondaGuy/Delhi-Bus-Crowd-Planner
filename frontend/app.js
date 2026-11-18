"use strict";
/* Commuter screen. No framework. Every API string goes in with textContent (the h() helper), never as markup. */
(function () {
  // ---------------------------------------------------------------- copy

  const LEVEL = {
    seats: { en: "Usually seats", hi: "आमतौर पर सीट मिल जाती है", dots: "●○○", color: "#0f766e" },
    standing: { en: "Usually standing", hi: "आमतौर पर खड़े होकर जाना पड़ता है", dots: "●●○", color: "#b45309" },
    crowded: { en: "Usually crowded", hi: "आमतौर पर भारी भीड़", dots: "●●●", color: "#8f1d1d" },
    no_data: { en: "No data", hi: "जानकारी नहीं", dots: "○○○", color: "#5f6670" },
  };
  const EVIDENCE = {
    many_tickets: { en: "Based on many tickets", hi: "कई टिकटों पर आधारित" },
    rough: { en: "Rough guess", hi: "अंदाज़ा (कम टिकट)" },
  };
  const FULL = { en: "Full buses may not stop", hi: "भरी बस शायद न रुके" };
  const ROLE = {
    fastest: { en: "Fastest", hi: "सबसे तेज़" },
    less_crowded: { en: "Less crowded", hi: "कम भीड़" },
    leave_later: { en: "Leave later", hi: "थोड़ा बाद निकलें" },
  };
  const ROLE_ORDER = ["fastest", "less_crowded", "leave_later"];
  const T = {
    title: { en: "Delhi bus crowding", hi: "दिल्ली बस भीड़" },
    change: { en: "Change", hi: "बदलें" },
    from: { en: "From", hi: "कहाँ से" },
    to: { en: "To", hi: "कहाँ तक" },
    leave: { en: "Leave at", hi: "निकलने का समय" },
    weekday: { en: "Weekday", hi: "सोम–शुक्र" },
    weekend: { en: "Weekend", hi: "शनि–रवि" },
    plan: { en: "Plan", hi: "रास्ता देखें" },
    seat: { en: "I need a seat", hi: "मुझे सीट चाहिए" },
    why: { en: "Why?", hi: "क्यों?" },
    map: { en: "Show map", hi: "नक्शा देखें" },
    close: { en: "Close", hi: "बंद करें" },
    mapTitle: { en: "Map", hi: "नक्शा" },
    walk: { en: "Walk", hi: "पैदल" },
    leaveAt: { en: "Leave", hi: "निकलें" },
    arriveAt: { en: "arrive", hi: "पहुँचें" },
    buses: { en: "Buses", hi: "बसें" },
    changes: { en: "Changes", hi: "बदलाव" },
    fare: { en: "Fare", hi: "किराया" },
    noChanges: { en: "No changes", hi: "बिना बदले" },
    seatBest: { en: "Your best chance of a seat", hi: "सीट मिलने की सबसे अच्छी संभावना" },
    seatNone: { en: "No less-crowded option for this trip.", hi: "इस यात्रा के लिए कम भीड़ वाला विकल्प नहीं है।" },
    noBusNeeded: { en: "No bus needed.", hi: "बस की ज़रूरत नहीं।" },
    uncertain: {
      en: "Timetable times may be off at this hour.",
      hi: "इस समय बसों का समय-सारणी से अलग होना संभव है।",
    },
    finding: { en: "Finding journeys…", hi: "रास्ते खोज रहे हैं…" },
    pickTrip: { en: "Pick a trip", hi: "यात्रा चुनें" },
    badInput: {
      en: "Please check the place names and the time (like 18:00), then try again.",
      hi: "कृपया जगहों के नाम और समय (जैसे 18:00) जाँचें, फिर दोबारा कोशिश करें।",
    },
    offline: {
      en: "Could not reach the planner. Check your connection and try again.",
      hi: "प्लानर से संपर्क नहीं हो सका। कनेक्शन जाँचकर दोबारा कोशिश करें।",
    },
    didYouMean: { en: "Did you mean:", hi: "क्या आपका मतलब था:" },
    noOptions: { en: "No journey was found.", hi: "कोई रास्ता नहीं मिला।" },
    whyLead: { en: "Based on app tickets", hi: "ऐप टिकटों पर आधारित" },
    onBoard: { en: "People on board", hi: "बस में लोग" },
    routeNotes: { en: "About this route", hi: "इस रूट के बारे में" },
    mapFail: { en: "The map could not be loaded. The list above still works.", hi: "नक्शा लोड नहीं हो सका। ऊपर की सूची काम करती है।" },
    dataVersion: { en: "Data version", hi: "डेटा संस्करण" },
  };
  const FLAG_WORDS = {
    full: "On the busiest stretches the count stops at what a bus can hold, so a bus may be fuller than shown.",
    scaled_to_capacity: "Counts on this route were scaled down so they fit what its buses can carry.",
    low_app_use: "Few riders on this route use the app, so this is a rough guess.",
    schedule_mismatch: "Buses on this route ran differently from the timetable.",
    alighting_sensitive: "Near the end of the route, where people get off, the counts are less certain.",
    office_special: "This includes an office special service.",
    rho_fallback: "How often buses run here is estimated from similar routes.",
  };
  const BUS_TYPE = { "12m_ac": "12 m AC bus", "9m_devi": "9 m Devi (small) bus", "12m_nonac": "12 m non-AC bus" };
  const WOMEN_SENTENCE = "Women riding free and pass holders are not in this data, so buses can be fuller than shown.";

  const PRESETS = [
    { from: "ISBT Anand Vihar", to: "Connaught Place", depart: "18:00", day: "weekday" },
    { from: "Connaught Place", to: "ISBT Anand Vihar", depart: "18:00", day: "weekday" },
    { from: "Ambedkar Nagar", to: "ITO", depart: "09:00", day: "weekday" },
    { from: "Mandi House", to: "Laxmi Nagar", depart: "18:00", day: "weekday" },
    { from: "Ambedkar Nagar", to: "AIIMS", depart: "09:00", day: "weekday" },
  ];

  // ---------------------------------------------------------------- state and helpers

  const state = { lang: "en", q: null, data: null, seat: false, req: 0, oneIn: null, opener: null, map: null };
  const $ = (id) => document.getElementById(id);

  function h(tag, cls, ...kids) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    for (const k of kids) {
      if (k === null || k === undefined || k === false) continue;
      el.append(k instanceof Node ? k : document.createTextNode(String(k)));
    }
    return el;
  }

  function tx(key) { return T[key][state.lang]; }
  function pick(o) { return o[state.lang]; }
  function level(lv) { return LEVEL[lv] || LEVEL.no_data; }

  function mins(m) {
    const hi = state.lang === "hi";
    if (m >= 60) {
      const hr = Math.floor(m / 60), r = m - hr * 60;
      return hi ? `${hr} घंटा ${r} मिनट` : `${hr} h ${r} min`;
    }
    return hi ? `${m} मिनट` : `${m} min`;
  }

  function dayLabel(day) { return tx(day === "weekend" ? "weekend" : "weekday"); }

  function storeLang(v) {
    try { localStorage.setItem("lang", v); } catch (e) { /* private mode: fine */ }
  }
  function savedLang() {
    try { return localStorage.getItem("lang"); } catch (e) { return null; }
  }

  // ---------------------------------------------------------------- trade-off line in Hindi

  function tradeoff(s) {
    if (state.lang !== "hi" || !s) return s;
    let m;
    if (s === "Fastest") return "सबसे तेज़";
    if (s === "Fastest and least crowded") return "सबसे तेज़ और सबसे कम भीड़";
    if (s === "Walk") return "पैदल";
    m = /^Leave (\d\d:\d\d) · usually (seats|standing|crowded) · arrive (\d\d:\d\d)$/.exec(s);
    if (m) return `${m[1]} पर निकलें · ${LEVEL[m[2]].hi} · ${m[3]} पर पहुँचें`;
    m = /^(?:\+(\d+) min|Same time), (.*)$/.exec(s);
    if (m) {
      const lead = m[1] ? `+${m[1]} मिनट` : "उतना ही समय";
      let tail = m[2], k;
      if (tail === "no crowded stretch") tail = "कोई भारी भीड़ वाला हिस्सा नहीं";
      else if ((k = /^(\d+) fewer crowded min$/.exec(tail))) tail = `${k[1]} मिनट कम भारी भीड़`;
      else if ((k = /^(\d+) fewer standing min$/.exec(tail))) tail = `${k[1]} मिनट कम खड़े रहना`;
      else if (tail === "similar crowding") tail = "भीड़ लगभग वैसी ही";
      return `${lead}, ${tail}`;
    }
    return s;
  }

  // ---------------------------------------------------------------- card pieces

  function chip(lv) {
    const L = level(lv);
    return h("p", "chip lvl-" + (LEVEL[lv] ? lv : "no_data"),
      h("span", "dots", L.dots), h("span", "", pick(L)));
  }
  // aria: the dots are decoration; the word carries the meaning
  function chipEl(lv) {
    const el = chip(lv);
    el.firstChild.setAttribute("aria-hidden", "true");
    return el;
  }

  function stretchLine(head) {
    const st = head && head.stretch;
    if (!st) return null;
    const lv = level(head.level);
    return state.lang === "hi"
      ? `${lv.hi}: ${st.from} से ${st.to}, ${mins(st.minutes)}`
      : `${lv.en} from ${st.from} to ${st.to}, ${mins(st.minutes)}`;
  }

  function timeBar(opt) {
    const bar = h("div", "bar");
    bar.setAttribute("role", "img");
    const parts = [];
    for (const leg of opt.legs || []) {
      if (leg.mode === "walk") {
        bar.append(piece("walk", leg.minutes));
        parts.push(`${tx("walk")} ${mins(leg.minutes)}`);
      } else {
        for (const s of leg.segments || []) {
          bar.append(piece("lvl-" + (LEVEL[s.level] ? s.level : "no_data"), s.minutes));
        }
        parts.push(`${leg.route}`);
      }
    }
    bar.setAttribute("aria-label", parts.join(" · "));
    return bar;
  }
  function piece(cls, minutes) {
    const i = document.createElement("i");
    i.className = cls;
    i.style.flexGrow = String(Math.max(Number(minutes) || 0, 0.5));
    return i;
  }

  function segments(opt) {
    const out = [];
    for (const leg of opt.legs || []) if (leg.mode === "bus") out.push(...(leg.segments || []));
    return out;
  }
  function busLegs(opt) { return (opt.legs || []).filter((l) => l.mode === "bus"); }
  function hasFull(opt) { return segments(opt).some((s) => (s.flags || []).includes("full")); }

  function roleText(roles) {
    return (roles || []).map((r) => (ROLE[r] ? pick(ROLE[r]) : r)).join(" · ");
  }

  function changesText(n) {
    if (!n) return tx("noChanges");
    return state.lang === "hi" ? `${n} बार बदलना` : `${n} ${n === 1 ? "change" : "changes"}`;
  }

  function fact(label, value) { return h("div", "", h("dt", "", label), h("dd", "", value)); }

  function buildCard(opt) {
    const walkOnly = !opt.headline;
    const isSeat = state.seat && (opt.roles || []).includes("less_crowded");
    const card = h("article", "card" + (isSeat ? " card--seat" : ""));
    card.dataset.roles = (opt.roles || []).join(" ");

    card.append(h("header", "card-head", h("h2", "role", roleText(opt.roles)), h("div", "dur", mins(opt.minutes))));
    card.append(h("p", "times", `${tx("leaveAt")} `, h("b", "", opt.depart), ` → ${tx("arriveAt")} `, h("b", "", opt.arrive)));
    if (isSeat) card.append(h("p", "stretch", tx("seatBest")));

    if (walkOnly) {
      const w = (opt.legs || []).find((l) => l.mode === "walk");
      const meters = w && w.meters ? ` (${w.meters} m)` : "";
      card.append(h("p", "stretch", `${tx("walk")} ${mins(opt.minutes)}${meters}. ${tx("noBusNeeded")}`));
      card.append(timeBar(opt));
      return card;
    }

    const head = opt.headline;
    card.append(chipEl(head.level));
    const line = stretchLine(head);
    if (line) card.append(h("p", "stretch", line));
    if (opt.tradeoff) card.append(h("p", "tradeoff", tradeoff(opt.tradeoff)));
    card.append(timeBar(opt));
    if (EVIDENCE[head.evidence]) card.append(h("p", "evidence", pick(EVIDENCE[head.evidence])));
    if (hasFull(opt)) card.append(h("p", "full-flag", pick(FULL)));
    if (opt.timetable_uncertain) card.append(h("p", "warn", tx("uncertain")));

    const dl = h("dl", "facts");
    dl.append(fact(tx("buses"), busLegs(opt).map((l) => l.route).join(", ")));
    dl.append(fact(tx("changes"), changesText(opt.changes)));
    dl.append(fact(tx("fare"), `₹${opt.fare_inr}`));
    card.append(dl);

    const why = h("button", "btn", tx("why"));
    why.type = "button";
    why.addEventListener("click", () => openWhy(opt, why));
    const map = h("button", "btn", tx("map"));
    map.type = "button";
    map.addEventListener("click", () => openMap(opt, map));
    card.append(h("div", "actions", why, map));
    return card;
  }

  // ---------------------------------------------------------------- results

  function orderOptions(opts) {
    const rank = (o) => Math.min(...(o.roles || []).map((r) => ROLE_ORDER.indexOf(r)).filter((i) => i >= 0), 9);
    return opts.slice().sort((a, b) => rank(a) - rank(b));
  }

  function renderResults() {
    const box = $("results");
    box.replaceChildren();
    const d = state.data;
    $("tools").hidden = !d;
    if (!d) return;
    const opts = orderOptions(d.options || []);
    box.className = "results" + (opts.length === 1 ? " results--one" : "");
    for (const o of opts) box.append(buildCard(o));
    if (!opts.length) box.append(h("p", "problem", tx("noOptions")));

    const notes = $("notes");
    notes.replaceChildren(...(d.notes || []).map((n) => h("p", "", n)));
    notes.hidden = !(d.notes || []).length;

    const hasLess = opts.some((o) => (o.roles || []).includes("less_crowded"));
    $("seat-note").textContent = state.seat && !hasLess ? tx("seatNone") : "";
    $("version").textContent = d.data_version ? `${tx("dataVersion")}: ${d.data_version}` : "";
  }

  function setStatus(msg) { $("status").textContent = msg || ""; }

  function showProblem(msg, suggestions) {
    const box = $("problem");
    box.replaceChildren(h("p", "", msg));
    if (suggestions && suggestions.length) {
      const row = h("div", "sugg");
      for (const s of suggestions) {
        const b = h("button", "", s);
        b.type = "button";
        b.addEventListener("click", () => useSuggestion(s));
        row.append(b);
      }
      box.append(h("p", "", tx("didYouMean")), row);
    }
    box.hidden = false;
    state.data = null;
    renderResults();
  }

  function useSuggestion(name) {
    const q = Object.assign({}, state.q);
    const detail = ($("problem").firstChild.textContent || "").toLowerCase();
    const inTo = q.to && detail.includes(q.to.trim().toLowerCase());
    const inFrom = q.from && detail.includes(q.from.trim().toLowerCase());
    if (inTo && !inFrom) q.to = name; else q.from = name;
    run(q);
  }

  // ---------------------------------------------------------------- query

  function updateSummary() {
    const q = state.q;
    $("summary-text").textContent = q ? `${q.from} → ${q.to} · ${dayLabel(q.day)} ${q.depart}` : tx("pickTrip");
  }

  function fillForm(q) {
    $("from").value = q.from;
    $("to").value = q.to;
    $("depart").value = q.depart;
    setDay(q.day);
  }

  function setDay(day) {
    for (const b of document.querySelectorAll(".seg-btn")) b.setAttribute("aria-pressed", String(b.dataset.day === day));
  }
  function currentDay() {
    const b = document.querySelector('.seg-btn[aria-pressed="true"]');
    return b ? b.dataset.day : "weekday";
  }

  function syncUrl(q) {
    try {
      const p = new URLSearchParams({ from: q.from, to: q.to, depart: q.depart, day: q.day });
      history.replaceState(null, "", "?" + p.toString());
    } catch (e) { /* not essential */ }
  }

  function markPreset(q) {
    document.querySelectorAll(".preset").forEach((b, i) => {
      const p = PRESETS[i];
      const on = q && p.from === q.from && p.to === q.to && p.depart === q.depart && p.day === q.day;
      if (on) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });
  }

  async function run(q) {
    const id = ++state.req;
    state.q = q;
    fillForm(q);
    updateSummary();
    markPreset(q);
    syncUrl(q);
    $("problem").hidden = true;
    closeForm();
    setStatus(tx("finding"));
    try {
      const params = new URLSearchParams({ from: q.from, to: q.to, depart: q.depart, day: q.day });
      const res = await fetch("/v1/plan?" + params.toString());
      if (id !== state.req) return;
      if (res.status === 404) {
        const body = await res.json().catch(() => ({}));
        setStatus("");
        showProblem(typeof body.detail === "string" ? body.detail : tx("badInput"), body.suggestions || []);
        return;
      }
      if (!res.ok) {
        setStatus("");
        showProblem(res.status === 422 ? tx("badInput") : tx("offline"));
        return;
      }
      state.data = await res.json();
      if (id !== state.req) return;
      setStatus("");
      renderResults();
    } catch (e) {
      if (id !== state.req) return;
      setStatus("");
      showProblem(tx("offline"));
    }
  }

  function closeForm() {
    $("form").hidden = true;
    $("summary").setAttribute("aria-expanded", "false");
  }
  function toggleForm() {
    const open = $("form").hidden;
    $("form").hidden = !open;
    $("summary").setAttribute("aria-expanded", String(open));
    if (open) $("from").focus();
  }

  function buildPresets() {
    const row = $("presets");
    row.replaceChildren();
    PRESETS.forEach((p) => {
      const b = h("button", "preset", `${p.from} → ${p.to}`, h("small", "", `${dayLabel(p.day)} ${p.depart}`));
      b.type = "button";
      b.addEventListener("click", () => run(Object.assign({}, p)));
      row.append(b);
    });
    markPreset(state.q);
  }

  let suggestTimer = null;
  function suggestPlaces(input) {
    clearTimeout(suggestTimer);
    const q = input.value.trim();
    if (q.length < 2) return;
    suggestTimer = setTimeout(async () => {
      try {
        const res = await fetch("/v1/places/search?" + new URLSearchParams({ q, limit: "8" }).toString());
        if (!res.ok) return;
        const body = await res.json();
        $("places").replaceChildren(...(body.places || []).map((p) => {
          const o = document.createElement("option");
          o.value = p.name;
          return o;
        }));
      } catch (e) { /* suggestions are optional */ }
    }, 200);
  }

  function submitForm(ev) {
    ev.preventDefault();
    const q = { from: $("from").value.trim(), to: $("to").value.trim(), depart: $("depart").value, day: currentDay() };
    if (!q.from || !q.to || !/^([01]?\d|2[0-3]):[0-5]\d$/.test(q.depart)) {
      showProblem(tx("badInput"));
      return;
    }
    run(q);
  }

  // ---------------------------------------------------------------- sheet

  function focusables(root) {
    return Array.from(root.querySelectorAll("button, [href], input, [tabindex]:not([tabindex='-1'])")).filter((e) => !e.disabled);
  }

  function openSheet(title, bodyNodes, opener) {
    state.opener = opener || null;
    $("sheet-title").textContent = title;
    $("sheet-close").setAttribute("aria-label", tx("close"));
    $("sheet-body").replaceChildren(...bodyNodes);
    $("sheet").hidden = false;
    document.body.style.overflow = "hidden";
    $("sheet-close").focus();
  }

  function closeSheet() {
    if ($("sheet").hidden) return;
    $("sheet").hidden = true;
    document.body.style.overflow = "";
    if (state.map) { state.map.remove(); state.map = null; }
    $("sheet-body").replaceChildren();
    if (state.opener && state.opener.focus) state.opener.focus();
  }

  function onSheetKey(ev) {
    if ($("sheet").hidden) return;
    if (ev.key === "Escape") { closeSheet(); return; }
    if (ev.key !== "Tab") return;
    const f = focusables($("sheet"));
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  }

  // ---------------------------------------------------------------- why sheet

  function whyLead() {
    const n = state.oneIn;
    const paren = Number.isFinite(n) && n > 0 ? ` (about 1 in ${n} riders)` : "";
    return `Based on app tickets${paren}, scaled up to estimate everyone on board — never more than a bus can hold. ${WOMEN_SENTENCE}`;
  }

  function peopleText(leg) {
    const withData = (leg.segments || []).filter((s) => Array.isArray(s.people) && s.people[1] !== null && s.people[1] !== undefined);
    if (!withData.length) return state.lang === "hi" ? `${leg.route}: इस रूट का डेटा नहीं है।` : `No ticket data for route ${leg.route}.`;
    const s = withData.reduce((a, b) => (b.people[1] > a.people[1] ? b : a));
    const [lo, mid, hi] = s.people.map((v) => Math.round(v));
    const range = lo === hi ? `${mid}` : state.lang === "hi" ? `${lo} से ${hi}` : `${lo} to ${hi}`;
    return state.lang === "hi"
      ? `${leg.route} पर सबसे भीड़ वाला हिस्सा: बस में लगभग ${range} लोग (अनुमान ${mid})। बस में ${s.seats} सीटें हैं और ${s.rated_total} लोगों की क्षमता है।`
      : `Busiest stretch on route ${leg.route}: about ${range} people on board (best guess ${mid}). The bus has ${s.seats} seats and is rated for ${s.rated_total} people.`;
  }

  function openWhy(opt, opener) {
    const body = [h("p", "why-lead", whyLead())];
    const day = (state.data && state.data.query && state.data.query.day) || (state.q && state.q.day) || "weekday";
    body.push(h("p", "why-period", `October 2026 ${day === "weekend" ? "weekends" : "weekdays"}, festival season`));
    for (const leg of busLegs(opt)) {
      body.push(h("h3", "", `${tx("onBoard")}: ${leg.route} · ${BUS_TYPE[leg.bus_type] || leg.bus_type || ""}`));
      body.push(h("p", "", peopleText(leg)));
    }
    const flags = new Set();
    for (const s of segments(opt)) for (const f of s.flags || []) flags.add(f);
    const words = Array.from(flags).filter((f) => FLAG_WORDS[f]).map((f) => FLAG_WORDS[f]);
    if (words.length) {
      body.push(h("h3", "", tx("routeNotes")));
      body.push(h("ul", "", ...words.map((w) => h("li", "", w))));
    }
    openSheet(tx("why"), body, opener);
  }

  // ---------------------------------------------------------------- map (Leaflet loads only on demand)

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

  async function openMap(opt, opener) {
    const holder = h("div", "map");
    holder.id = "map";
    const legend = h("div", "legend");
    for (const lv of ["seats", "standing", "crowded", "no_data"]) legend.append(h("span", "l-" + lv, pick(LEVEL[lv])));
    openSheet(tx("mapTitle"), [legend, holder], opener);
    let L;
    try {
      L = await loadLeaflet();
    } catch (e) {
      if (!$("sheet").hidden) $("sheet-body").replaceChildren(h("p", "problem", tx("mapFail")));
      return;
    }
    if ($("sheet").hidden || !holder.isConnected) return;
    const map = L.map(holder);
    state.map = map;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    const all = [];
    for (const s of segments(opt)) {
      if (!Array.isArray(s.coords) || s.coords.length < 2) continue;
      const lv = LEVEL[s.level] ? s.level : "no_data";
      const line = L.polyline(s.coords, { color: LEVEL[lv].color, weight: 6, opacity: 0.9, dashArray: lv === "no_data" ? "4 8" : null });
      line.bindTooltip(h("span", "", pick(LEVEL[lv])));
      line.addTo(map);
      all.push(...s.coords);
    }
    if (all.length) map.fitBounds(L.latLngBounds(all), { padding: [24, 24] }); else map.setView([28.6139, 77.209], 11);
    setTimeout(() => map.invalidateSize(), 50);
  }

  // ---------------------------------------------------------------- language

  function applyLang(lang) {
    state.lang = lang;
    storeLang(lang);
    document.documentElement.lang = lang === "hi" ? "hi" : "en";
    document.body.dataset.lang = lang;
    document.querySelectorAll("[data-t]").forEach((el) => { el.textContent = tx(el.dataset.t); });
    document.querySelectorAll(".lang-btn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    $("sheet-close").setAttribute("aria-label", tx("close"));
    updateSummary();
    buildPresets();
    renderResults();
  }

  // ---------------------------------------------------------------- start

  async function loadHealth() {
    try {
      const res = await fetch("/v1/health");
      if (!res.ok) return;
      const body = await res.json();
      const n = body.app_riders_one_in;
      state.oneIn = Number.isFinite(n) && n > 0 ? n : null;
    } catch (e) { /* the parenthetical is simply left out */ }
  }

  function queryFromUrl() {
    try {
      const p = new URLSearchParams(location.search);
      const q = { from: p.get("from"), to: p.get("to"), depart: p.get("depart"), day: p.get("day") };
      if (q.from && q.to && /^\d\d?:\d\d$/.test(q.depart || "") && ["weekday", "weekend"].includes(q.day)) return q;
    } catch (e) { /* ignore */ }
    return null;
  }

  function init() {
    document.querySelectorAll(".lang-btn").forEach((b) => b.addEventListener("click", () => applyLang(b.dataset.lang)));
    document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => setDay(b.dataset.day)));
    $("summary").addEventListener("click", toggleForm);
    $("form").addEventListener("submit", submitForm);
    $("from").addEventListener("input", (e) => suggestPlaces(e.target));
    $("to").addEventListener("input", (e) => suggestPlaces(e.target));
    $("seat").addEventListener("click", () => {
      state.seat = !state.seat;
      $("seat").setAttribute("aria-pressed", String(state.seat));
      renderResults();
      const hit = document.querySelector(".card--seat");
      if (hit) hit.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
    document.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", closeSheet));
    document.addEventListener("keydown", onSheetKey);

    const first = queryFromUrl() || Object.assign({}, PRESETS[0]);
    applyLang(savedLang() === "hi" ? "hi" : "en");
    loadHealth();
    run(first);
  }

  init();
})();
