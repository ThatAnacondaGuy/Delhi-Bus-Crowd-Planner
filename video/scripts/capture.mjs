// Capture the real app (API on the full data) into video/public/captures/ at device scale 2.
// Start the API first:  venv/bin/python -m uvicorn src.api.main:app --port 8790   (from the repo root)
// Then:                  cd video && npm run capture            (BASE=http://127.0.0.1:8790 CHROME_PATH=... to override)
// Writes PNGs plus video/src/captures.generated.json (sizes and element rectangles the film animates).
// Nothing is faked: every image is a screenshot of the running app.
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, "../public/captures");
const META = path.resolve(HERE, "../src/captures.generated.json");
const BASE = process.env.BASE || "http://127.0.0.1:8790";
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const meta = {};
const q = (o) => "/?" + new URLSearchParams(o).toString();

const JOURNEYS = {
  j1: { from: "ISBT Anand Vihar", to: "Connaught Place", depart: "18:00", day: "weekday" },
  j2: { from: "Connaught Place", to: "ISBT Anand Vihar", depart: "18:00", day: "weekday" },
  j3: { from: "Ambedkar Nagar", to: "ITO", depart: "09:00", day: "weekday" },
  j4: { from: "Mandi House", to: "Laxmi Nagar", depart: "18:00", day: "weekday" },
  j5: { from: "Ambedkar Nagar", to: "AIIMS", depart: "09:00", day: "weekday" },
  nodata: { from: "AIIMS", to: "Ambedkar Nagar", depart: "07:00", day: "weekend" },
};

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--no-proxy-server", "--hide-scrollbars"],
});

async function newPage(vp) {
  const p = await browser.newPage();
  await p.setViewport(vp);
  return p;
}

async function shot(page, name, opts = {}) {
  const file = path.join(OUT, name + ".png");
  await page.screenshot({ path: file, ...opts });
  return file;
}

/* ------------------------------------------------------------------ commuter (phone, 390x844 @2x) */
const phone = await newPage({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });

const rectsScript = () => {
  const r = (el) => {
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { x: b.x + scrollX, y: b.y + scrollY, w: b.width, h: b.height };
  };
  const cards = [...document.querySelectorAll(".card")].map((c) => ({
    roles: c.dataset.roles,
    card: r(c),
    chip: r(c.querySelector(".chip")),
    why: r([...c.querySelectorAll(".btn")][0]),
    map: r([...c.querySelectorAll(".btn")][1]),
    callout: r(c.querySelector(".callout")),
    evidence: r(c.querySelector(".evidence")),
    tradeoff: r(c.querySelector(".tradeoff")),
    bar: r(c.querySelector(".bar")),
    level: (c.querySelector(".chip") || {}).className || null,
  }));
  return {
    page: { w: document.documentElement.clientWidth, h: document.documentElement.scrollHeight },
    cards,
    presets: [...document.querySelectorAll(".preset")].map(r),
    seat: r(document.getElementById("seat")),
    langHi: r(document.querySelector('.lang-btn[data-lang="hi"]')),
    langEn: r(document.querySelector('.lang-btn[data-lang="en"]')),
    key: r(document.getElementById("key")),
    summary: r(document.getElementById("summary")),
    notes: r(document.getElementById("notes")),
  };
};

async function load(page, route, waitCards = true) {
  await page.goto(BASE + route, { waitUntil: "domcontentloaded", timeout: 60000 });
  if (waitCards) await page.waitForSelector(".card", { timeout: 90000 });
  await page.evaluate(() => document.fonts.ready);
  await sleep(2600); // the cards animate in; wait until they are still
}

// first screen, no trip yet
await load(phone, "/", false);
await sleep(800);
await shot(phone, "m-first");
meta["m-first"] = { w: 390, h: 844, rects: await phone.evaluate(rectsScript) };

for (const [id, j] of Object.entries(JOURNEYS)) {
  await load(phone, q(j));
  await phone.evaluate(() => window.scrollTo(0, 0));
  const rects = await phone.evaluate(rectsScript);
  await shot(phone, `m-${id}-full`, { fullPage: true });
  meta[`m-${id}-full`] = { w: rects.page.w, h: rects.page.h, rects, query: j };
  console.log("captured", id, rects.cards.map((c) => c.level).join(" | "));
}

// Why? sheet (journey 1, fastest card, then journey 2)
for (const id of ["j1", "j2"]) {
  await load(phone, q(JOURNEYS[id]));
  const btn = (await phone.$$(".card"))[0];
  const why = (await btn.$$(".btn"))[0];
  await why.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await sleep(300);
  const sheetRects = {};
  await why.click();
  await sleep(1400);
  sheetRects.panel = await phone.evaluate(() => {
    const b = document.querySelector(".sheet-panel").getBoundingClientRect();
    return { x: b.x, y: b.y, w: b.width, h: b.height };
  });
  sheetRects.body = await phone.evaluate(() => {
    const el = document.getElementById("sheet-body");
    return { scrollH: el.scrollHeight, clientH: el.clientHeight };
  });
  await shot(phone, `m-${id}-why`);
  meta[`m-${id}-why`] = { w: 390, h: 844, rects: sheetRects };
}

// map sheet (journey 1, second card if there is one, else first)
await load(phone, q(JOURNEYS.j1));
{
  const cards = await phone.$$(".card");
  const card = cards[Math.min(1, cards.length - 1)];
  const mapBtn = (await card.$$(".btn"))[1];
  await mapBtn.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await sleep(300);
  await mapBtn.click();
  await sleep(6000); // leaflet and the tiles come from the internet
  await shot(phone, "m-j1-map");
  meta["m-j1-map"] = { w: 390, h: 844, rects: {} };
}

// "I need a seat" (journey 5 has a Less crowded option) and Hindi (journey 1)
await load(phone, q(JOURNEYS.j5));
await phone.click("#seat");
await sleep(1800);
await phone.evaluate(() => window.scrollTo(0, 0));
{
  const rects = await phone.evaluate(rectsScript);
  await shot(phone, "m-j5-seat-full", { fullPage: true });
  meta["m-j5-seat-full"] = { w: rects.page.w, h: rects.page.h, rects, query: JOURNEYS.j5 };
}
await load(phone, q(JOURNEYS.j1));
await phone.click('.lang-btn[data-lang="hi"]');
await sleep(2000);
await phone.evaluate(() => window.scrollTo(0, 0));
{
  const rects = await phone.evaluate(rectsScript);
  await shot(phone, "m-j1-hi-full", { fullPage: true });
  meta["m-j1-hi-full"] = { w: rects.page.w, h: rects.page.h, rects, query: JOURNEYS.j1 };
}
await phone.evaluate(() => { try { localStorage.removeItem("lang"); } catch (e) {} });
await phone.close();

/* ------------------------------------------------------------------ operator (laptop, 1440x900 @2x) */
const lap = await newPage({ width: 1440, height: 900, deviceScaleFactor: 2 });
await lap.goto(BASE + "/operator", { waitUntil: "domcontentloaded", timeout: 60000 });
await lap.waitForSelector("#trips-body tr", { timeout: 90000 });
await lap.evaluate(() => document.fonts.ready);
await sleep(5000); // map tiles

const elRect = (sel) => lap.evaluate((s) => {
  const e = document.querySelector(s);
  if (!e) return null;
  const b = e.getBoundingClientRect();
  return { x: b.x + scrollX, y: b.y + scrollY, w: b.width, h: b.height };
}, sel);
const clip = async (name, sel, pad = 0) => {
  const r = await elRect(sel);
  const file = path.join(OUT, name + ".png");
  await lap.screenshot({
    path: file,
    clip: { x: Math.max(0, r.x - pad), y: Math.max(0, r.y - pad), width: r.w + 2 * pad, height: r.h + 2 * pad },
    captureBeyondViewport: true,
  });
  meta[name] = { w: Math.round(r.w + 2 * pad), h: Math.round(r.h + 2 * pad), rects: {} };
  return r;
};

await shot(lap, "o-view");
meta["o-view"] = { w: 1440, h: 900, rects: {} };
await shot(lap, "o-full", { fullPage: true });
const pageH = await lap.evaluate(() => document.documentElement.scrollHeight);
meta["o-full"] = {
  w: 1440, h: pageH,
  rects: {
    tiles: await elRect("#tiles"),
    trips: await elRect(".op-trips"),
    row1: await elRect("#trips-body tr:first-child"),
    map: await elRect(".op-mapcard"),
    slider: await elRect("#slider"),
    sliderLabel: await elRect("#slider-label"),
    strip: await elRect(".op-strip"),
    csv: await elRect("#csv"),
    op2: await elRect('[data-operator="DIMTS"]'),
    weekend: await elRect('[data-day="weekend"]'),
  },
};
await clip("o-tiles", "#tiles", 8);

// select row 1 (578DOWN at 08:30) and wait for the heat strip
await lap.click("#trips-body tr:first-child .op-route");
await sleep(5000);
await shot(lap, "o-full-selected", { fullPage: true });
meta["o-full-selected"] = { w: 1440, h: await lap.evaluate(() => document.documentElement.scrollHeight), rects: {
  strip: await elRect(".op-strip"), row1: await elRect("#trips-body tr:first-child"), trips: await elRect(".op-trips"),
  legend: await elRect("#strip-legend"), heat: await elRect("#heat") } };
await clip("o-strip", ".op-strip", 0);
await clip("o-trips-selected", ".op-trips", 0);

// slider sweep: every half hour from 09:00 (value 18) to 19:00 (value 38)
await lap.evaluate(() => window.scrollTo(0, 0));
for (let v = 18; v <= 38; v++) {
  await lap.evaluate((val) => {
    const s = document.getElementById("slider");
    s.value = String(val);
    s.dispatchEvent(new Event("input", { bubbles: true }));
    s.dispatchEvent(new Event("change", { bubbles: true }));
  }, v);
  await sleep(v === 18 ? 5000 : 3200);
  const label = await lap.evaluate(() => document.getElementById("slider-label").textContent);
  await clip(`o-map-${String(v).padStart(2, "0")}`, ".op-mapcard", 0);
  meta[`o-map-${String(v).padStart(2, "0")}`].label = label;
  process.stdout.write(`map ${label}  `);
}
console.log();
await lap.evaluate((val) => {
  const s = document.getElementById("slider"); s.value = String(val);
  s.dispatchEvent(new Event("input", { bubbles: true })); s.dispatchEvent(new Event("change", { bubbles: true }));
}, 18);

// weekend and cluster views (B-roll, and a No data cell on a real screen)
await lap.click('[data-day="weekend"]');
await sleep(3500);
await shot(lap, "o-weekend-view");
meta["o-weekend-view"] = { w: 1440, h: 900, rects: {} };
await lap.click('[data-operator="DIMTS"]');
await sleep(2500);
await shot(lap, "o-cluster-view");
meta["o-cluster-view"] = { w: 1440, h: 900, rects: {} };

await browser.close();
fs.writeFileSync(META, JSON.stringify(meta, null, 1) + "\n");
console.log("wrote", path.relative(process.cwd(), META), Object.keys(meta).length, "captures");
