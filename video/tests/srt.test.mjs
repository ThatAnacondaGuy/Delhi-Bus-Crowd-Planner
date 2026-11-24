import test from "node:test";
import assert from "node:assert/strict";
import { buildSrt } from "../scripts/captions_srt.mjs";
import { SCENE_CAPTIONS, PLANNER_PARTS } from "../src/captions.ts";

const parse = (srt) =>
  srt.trim().split(/\n\n/).map((b) => {
    const [n, t, ...text] = b.split("\n");
    const m = t.match(/(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)/);
    const ms = (h, mi, s, x) => ((+h * 60 + +mi) * 60 + +s) * 1000 + +x;
    return { n: +n, from: ms(...m.slice(1, 5)), to: ms(...m.slice(5, 9)), text: text.join("\n") };
  });

test("the SRT carries every script caption in order, numbered, without overlaps", () => {
  const cues = parse(buildSrt(Array(9).fill(null)));
  const all = [...SCENE_CAPTIONS.slice(0, 4).flat(), ...PLANNER_PARTS.flat(), ...SCENE_CAPTIONS.slice(5).flat()];
  assert.deepEqual(cues.map((c) => c.text), all);
  cues.forEach((c, i) => {
    assert.equal(c.n, i + 1);
    assert.ok(c.to > c.from, `cue ${c.n} has no length`);
    if (i) assert.ok(c.from >= cues[i - 1].to, `cue ${c.n} overlaps`);
  });
});

test("without voice the cues sit inside the 3:00 film; with voice they follow the longer timeline", () => {
  const bare = parse(buildSrt(Array(9).fill(null)));
  assert.ok(bare.at(-1).to <= 180000);
  assert.equal(bare.at(-1).text, SCENE_CAPTIONS[8].at(-1));
  const vo = [9.09, 8.54, 14.52, 23.05, null, 22.89, 25.5, 10.55, 8.58];
  const cues = parse(buildSrt(vo));
  const sceneSeven = cues.find((c) => c.text === "No field count was possible.");
  assert.ok(sceneSeven, "the exact sentence is in the file");
  assert.ok(cues.at(-1).to > 180000, "scene 5 placeholder plus voice-length scenes run past 3:00");
});

test("scene 5 cues follow the voice once scene-05.wav exists (part starts from the silences)", () => {
  const vo = [9.09, 8.54, 14.52, 23.05, 52, 22.89, 25.5, 10.55, 8.58];
  const cues = parse(buildSrt(vo, [0.3, 10, 21, 33, 45]));
  const first = cues.find((c) => c.text === PLANNER_PARTS[0][0]);
  const fourth = cues.find((c) => c.text === PLANNER_PARTS[3][0]);
  assert.ok(fourth.from - first.from > 30000 - 5000, "parts are spread by the silences, not the script split");
});
