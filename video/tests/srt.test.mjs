import test from "node:test";
import assert from "node:assert/strict";
import { buildSrt } from "../scripts/captions_srt.mjs";
import { SCENE_CUES, PLANNER_PARTS } from "../src/captions.ts";

const parse = (srt) =>
  srt.trim().split(/\n\n/).map((b) => {
    const [n, t, ...text] = b.split("\n");
    const m = t.match(/(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)/);
    const ms = (h, mi, s, x) => ((+h * 60 + +mi) * 60 + +s) * 1000 + +x;
    return { n: +n, from: ms(...m.slice(1, 5)), to: ms(...m.slice(5, 9)), text: text.join(" "), lines: text };
  });
const ALL = [...SCENE_CUES.slice(0, 4).flat(), ...PLANNER_PARTS.flat(), ...SCENE_CUES.slice(5).flat()];

test("the SRT carries every phrase in order, numbered, without overlaps", () => {
  const cues = parse(buildSrt(Array(9).fill(null)));
  assert.deepEqual(cues.map((c) => c.text), ALL);
  cues.forEach((c, i) => {
    assert.equal(c.n, i + 1);
    assert.ok(c.to > c.from);
    if (i) assert.ok(c.from >= cues[i - 1].to);
  });
  assert.ok(cues.at(-1).to <= 180000);
});

test("with voice the cues start on the detected speech", () => {
  const vo = [9.091, 8.536, 14.521, 23.048, 44.983, 22.888, 25.501, 10.548, 8.583];
  const sil = Array(9).fill(null);
  sil[0] = [[0, 0.344], [1.557, 2.221], [3.475, 5.357], [5.972, 6.369], [6.866, 7.779]];
  const cues = parse(buildSrt(vo, null, sil));
  assert.deepEqual(cues.map((c) => c.text), ALL);
  // scene 1 starts at 0, its voice HEAD (66 frames = 2.2 s) in: "Not whether" begins at 2.2 + 5.357 s
  const c2 = cues.find((c) => c.text === SCENE_CUES[0][1]);
  assert.ok(Math.abs(c2.from - (2200 + 5357)) <= 34, `cue at ${c2.from} ms`);
  assert.ok(cues.find((c) => c.text === "No field count was possible."));
});

test("no SRT line is longer than 42 characters (cues over 42 are broken into two lines)", () => {
  const cues = parse(buildSrt(Array(9).fill(null)));
  for (const c of cues) {
    assert.ok(c.lines.length <= 2, c.text);
    for (const l of c.lines) assert.ok(l.length <= 42, `"${l}" is ${l.length} characters`);
  }
  assert.ok(cues.some((c) => c.lines.length === 2));
});
