import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SCENE_CUES, PLANNER_PARTS, cueTexts } from "../src/captions.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "../src");

test("nine scenes; scene 5 is carried by five planner parts", () => {
  assert.equal(SCENE_CUES.length, 9);
  assert.equal(SCENE_CUES[4].length, 0);
  assert.equal(PLANNER_PARTS.length, 5);
  assert.deepEqual(cueTexts(5), PLANNER_PARTS.flat());
});

test("the sentence that must be heard is exact, and the phrases follow the script's words in order", () => {
  assert.ok(SCENE_CUES[6].includes("No field count was possible."));
  assert.equal(SCENE_CUES[6].at(-1), "No field count was possible.");
  assert.equal(SCENE_CUES[8].at(-1), "Made by Aniket and Ash.");
});

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? walk(p) : [p];
  });
}

test("no forbidden words anywhere on screen (source files, README)", () => {
  const files = [...walk(SRC), path.resolve(HERE, "../README.md")].filter((f) => /\.(ts|tsx|md|json)$/.test(f) && fs.existsSync(f));
  const forbidden = [/κ/, /kappa/i, /mcraptor/i, /pareto/i, /sigmoid/i, /\bscores?\b/i, /accuracy/i];
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    for (const re of forbidden) assert.ok(!re.test(text), `${path.relative(SRC, f)} contains ${re}`);
  }
});

test("design system: one type scale, nothing below 32 px, safe margins of at least 96 px", async () => {
  const d = fs.readFileSync(path.join(SRC, "design.ts"), "utf8");
  for (const [k, v] of Object.entries({ display: 96, h1: 72, h2: 52, body: 40, caption: 36, label: 32 })) assert.match(d, new RegExp(`${k}: ${v},`));
  assert.match(d, /SAFE = \{ x: 96,/);
  // scenes take sizes from the scale: no hand-picked fontSize numbers in scene files
  for (const f of walk(path.join(SRC, "scenes"))) {
    const t = fs.readFileSync(f, "utf8");
    const raw = [...t.matchAll(/fontSize:\s*(\d+)/g)].map((m) => +m[1]);
    assert.deepEqual(raw, [], `${path.basename(f)} has literal font sizes ${raw}`);
  }
});
