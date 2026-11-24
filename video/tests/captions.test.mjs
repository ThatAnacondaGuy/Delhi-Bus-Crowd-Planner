import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SCENE_CAPTIONS, PLANNER_PARTS, chunkSpans, captionAt } from "../src/captions.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "../src");

test("nine scenes; scene 5 is carried by five planner parts", () => {
  assert.equal(SCENE_CAPTIONS.length, 9);
  assert.equal(SCENE_CAPTIONS[4].length, 0);
  assert.equal(PLANNER_PARTS.length, 5);
});

test("every caption chunk fits two lines (at most 110 characters)", () => {
  const all = [...SCENE_CAPTIONS.flat(), ...PLANNER_PARTS.flat()];
  for (const c of all) assert.ok(c.length <= 110, `too long (${c.length}): ${c}`);
});

test("the sentence that must be heard is exact", () => {
  assert.ok(SCENE_CAPTIONS[6].includes("No field count was possible."));
});

test("chunk spans tile the range without gaps and follow length", () => {
  const spans = chunkSpans(["aaaa", "bb"], 0, 60);
  assert.equal(spans[0].from, 0);
  assert.equal(spans[0].to, spans[1].from);
  assert.equal(spans[1].to, 60);
  assert.ok(spans[0].to - spans[0].from > spans[1].to - spans[1].from);
  assert.equal(captionAt(spans, 5), "aaaa");
  assert.equal(captionAt(spans, 59), "bb");
  assert.equal(captionAt(spans, 60), null);
});

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? walk(p) : [p];
  });
}

test("no forbidden words anywhere on screen (source files, README)", () => {
  const files = [...walk(SRC), path.resolve(HERE, "../README.md")].filter(
    (f) => /\.(ts|tsx|md|json)$/.test(f) && fs.existsSync(f),
  );
  const forbidden = [/κ/, /kappa/i, /mcraptor/i, /pareto/i, /sigmoid/i, /\bscores?\b/i, /accuracy/i];
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    for (const re of forbidden) {
      assert.ok(!re.test(text), `${path.relative(SRC, f)} contains ${re}`);
    }
  }
});

import { boundSpans, sceneSpans, SCRIPT_BOUNDS } from "../src/captions.ts";

test("picture-led scenes follow script timecodes without voice, speech with voice", () => {
  const chunks = SCENE_CAPTIONS[6];
  assert.equal(SCRIPT_BOUNDS[7].length, chunks.length + 1);
  const noVo = sceneSpans(7, chunks, null, 900, 900, 9);
  assert.equal(noVo[2].from, 420);
  assert.equal(noVo[3].from, 630);
  const compressed = sceneSpans(7, chunks, null, 900, 720, 9);
  assert.equal(compressed[2].from, 336);
  const withVo = sceneSpans(7, chunks, 840, 900, 900, 9);
  assert.equal(withVo[0].from, 15);
  assert.equal(withVo[withVo.length - 1].to, 840);
  assert.equal(boundSpans(["a", "b"], [0, 10, 30])[1].to, 30);
  for (const k of [3, 4, 6, 7, 8]) assert.equal(SCRIPT_BOUNDS[k].length, SCENE_CAPTIONS[k - 1].length + 1);
});
