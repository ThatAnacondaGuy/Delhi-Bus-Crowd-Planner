"use strict";
/* Data access for both screens, in two modes.

   API mode (config.js sets nothing): CrowdData.fetch is the browser's own fetch and links are left alone, so the
   screens behave exactly as they always did.

   Static mode (the demo build's config.js sets window.CROWD_STATIC = {data, github}): the screens keep asking
   for the same API-style URLs, and this file answers them from the precomputed JSON and CSV files that sit
   beside the page. The answers have the same shape as the API's, because the build wrote them with the API's own code. */
(function () {
  const cfg = window.CROWD_STATIC || null;
  const nativeFetch = window.fetch.bind(window);

  if (!cfg) {
    window.CrowdData = { static: false, fetch: nativeFetch, link: (u) => u, meta: null, banner: () => Promise.resolve() };
    return;
  }

  const base = String(cfg.data || "static-data/").replace(/\/?$/, "/");
  const cache = new Map();

  function reply(body, status) {
    return new Response(JSON.stringify(body), { status: status || 200, headers: { "Content-Type": "application/json" } });
  }
  function missing(detail, suggestions) { return reply({ detail, suggestions: suggestions || [] }, 404); }

  async function file(path) {
    const res = await nativeFetch(base + path);
    if (!res.ok) { const e = new Error(`${path}: ${res.status}`); e.status = res.status; throw e; }
    return res.json();
  }
  // the small files every page needs are read once
  function once(path) {
    if (!cache.has(path)) cache.set(path, file(path).catch((e) => { cache.delete(path); throw e; }));
    return cache.get(path);
  }
  async function optional(path) {
    try { return await file(path); } catch (e) { if (e.status === 404) return null; throw e; }
  }

  const hhmm = (s) => String(s || "").trim().replace(/^(\d):/, "0$1");
  const compact = (s) => hhmm(s).replace(":", "");
  const STEP = { weekday: 30, weekend: 60 };

  function findPlace(meta, name) {
    const k = String(name || "").trim().toLowerCase();
    return (meta.places || []).find((p) => p.name.toLowerCase() === k || p.slug === k) || null;
  }

  async function plan(q) {
    const meta = await once("places.json");
    const from = findPlace(meta, q.get("from")), to = findPlace(meta, q.get("to"));
    const names = (meta.places || []).map((p) => p.name).slice(0, 5);
    if (!from) return missing(`No place matches '${q.get("from")}'`, names);
    if (!to) return missing(`No place matches '${q.get("to")}'`, names);
    if (from.slug === to.slug) return reply({ detail: "Pick two different places." }, 422);
    const day = q.get("day");
    const body = await optional(`plans/${from.slug}/${to.slug}.json`);
    const hit = body && body.slots ? body.slots[`${day}-${compact(q.get("depart"))}`] : null;
    if (!hit) return missing("The demo has no ready-made answer for that time.", []);
    return reply(hit);
  }

  async function operatorTrips(q) {
    const day = q.get("day");
    const body = await optional(`operator/trips-${day}.json`);
    if (!body) return missing(`No operator data for a ${day}`);
    const op = (q.get("operator") || "").toUpperCase();
    let rows = (body.trips || []).filter((t) => !op || String(t.operator).toUpperCase() === op);
    rows = rows.slice(0, Number(q.get("limit")) || rows.length);
    return reply({ data_version: body.data_version, day, operator: q.get("operator"), count: rows.length, trips: rows });
  }

  async function corridors(q) {
    const day = q.get("day");
    const step = STEP[day] || 30;
    const [h, m] = hhmm(q.get("window")).split(":").map(Number);
    const start = Math.floor((h * 60 + m) / step) * step;
    const name = `${String(Math.floor(start / 60)).padStart(2, "0")}${String(start % 60).padStart(2, "0")}`;
    const body = await optional(`corridors/${day}-${name}.json`);
    if (!body) return missing(`No corridor data for a ${day} at ${name}`);
    const limit = Number(q.get("limit"));
    if (limit > 0 && body.features.length > limit) return reply(Object.assign({}, body, { features: body.features.slice(0, limit) }));
    return reply(body);
  }

  async function crowding(q) {
    const day = q.get("day"), id = q.get("route_id");
    const body = await optional(`crowding/${day}/${id}.json`);
    if (!body) return missing(`No crowding data for route ${id} on a ${day}`);
    const w = q.get("window");
    if (w === null || w === "") return reply(body);
    const start = hhmm(w);
    const exact = (body.windows || []).find((x) => x.start === start);
    if (!exact) return missing(`No crowding data for route ${id} on a ${day} at ${start}`);
    const head = Object.assign({}, body);
    delete head.windows;
    return reply(Object.assign(head, { window: { start: exact.start }, stretches: exact.stretches }));
  }

  async function answer(url) {
    const u = new URL(url, location.href);
    const q = u.searchParams;
    switch (u.pathname) {
      case "/v1/plan": return plan(q);
      case "/v1/health": return reply(await once("health.json"));
      case "/v1/places/search": {
        const meta = await once("places.json");
        const k = String(q.get("q") || "").toLowerCase();
        const rows = (meta.places || []).filter((p) => p.name.toLowerCase().includes(k)).slice(0, Number(q.get("limit")) || 8);
        return reply({ data_version: meta.data_version, query: q.get("q"), places: rows });
      }
      case "/v1/operator/trips": return operatorTrips(q);
      case "/v1/corridors": return corridors(q);
      case "/v1/crowding": return crowding(q);
      default: return missing("Not part of the demo.");
    }
  }

  async function staticFetch(url, opts) {
    const path = new URL(url, location.href).pathname;
    if (!path.startsWith("/v1/")) return nativeFetch(url, opts);
    try {
      return await answer(url);
    } catch (e) {
      return reply({ detail: "The demo data could not be loaded." }, 503);
    }
  }

  // anchor targets: the CSV of the ranked trips is a static file
  function link(url) {
    const u = new URL(url, location.href);
    if (u.pathname === "/v1/operator/trips.csv") return `${base}operator/trips-${u.searchParams.get("day") || "weekday"}.csv`;
    return url;
  }

  // the slim banner at the top of each page; every number in it comes from the data files
  async function banner(box, kind) {
    if (!box) return;
    const meta = await once("places.json");
    const gh = h("a", "", "GitHub");
    gh.href = cfg.github || "#";
    gh.rel = "noopener";
    const lead = kind === "operator"
      ? "Live demo: ready-made tables, maps and route strips from the same model. The full planner (any place, any time) runs from the code on "
      : `Live demo: ready-made answers for ${(meta.places || []).length} places at ${(meta.slots || []).length} departure times, computed by the same model. The full planner (any place, any time) runs from the code on `;
    box.replaceChildren(lead, gh, ".");
    box.hidden = false;
  }
  function h(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text) el.textContent = text;
    return el;
  }

  window.CrowdData = { static: true, fetch: staticFetch, link, meta: () => once("places.json"), banner };
})();
