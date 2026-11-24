// Speech segments, phrase-to-segment mapping, caption lines and the fit rule (src/sync.ts).
import test from "node:test";
import assert from "node:assert/strict";
import { speechFromSilences, mapCues, segsWithin, spreadCues, wrapCaption, fitSize, speechWeight } from "../src/sync.ts";
import { SCENE_CUES, PLANNER_PARTS } from "../src/captions.ts";

test("speech segments are the complement of the silences, blips dropped", () => {
  const segs = speechFromSilences([[0, 0.34], [1.5, 2.2], [3.4, 3.45], [5.0, 5.3]], 6);
  assert.deepEqual(segs, [[0.34, 1.5], [2.2, 3.4], [3.45, 5], [5.3, 6]]);
  assert.deepEqual(speechFromSilences([[0, 0.3], [1, 1.05]], 1.1), [[0.3, 1]]); // 1.05..1.1 is a 50 ms blip
  assert.deepEqual(speechFromSilences([], 2), [[0, 2]]);
});

test("each phrase boundary lands on a pause, chosen by character share", () => {
  // scene 1 as recorded: five segments, three phrases; the long pause (3.47..5.36) is the first boundary
  const segs = [[0.34, 1.56], [2.22, 3.47], [5.36, 5.97], [6.37, 6.87], [7.78, 9.09]];
  const cues = mapCues(SCENE_CUES[0], segs);
  assert.equal(cues.length, 3);
  assert.deepEqual(cues.map((c) => c.from), [0.34, 5.36, 7.78]);
  assert.deepEqual(cues.map((c) => c.to), [3.47, 6.87, 9.09]);
  assert.ok(cues.every((c) => !c.split));
});

test("more phrases than pauses: the rest split a segment by relative character length", () => {
  const cues = mapCues(["aaaa aaaa", "bbbb", "cccc"], [[0, 2], [3, 5]]);
  assert.equal(cues.length, 3);
  assert.equal(cues[0].from, 0);
  assert.equal(cues.at(-1).to, 5);
  // in order, no overlaps, inside the speech
  for (let i = 1; i < cues.length; i++) assert.ok(cues[i].from >= cues[i - 1].to - 1e-9);
  assert.equal(cues.filter((c) => c.split).length, 1, "one boundary has no pause under it");
  cues.forEach((c) => assert.ok(c.to > c.from));
});

test("a phrase never starts inside a pause; one phrase covers all the speech", () => {
  const segs = [[0.3, 1], [1.4, 2.2], [2.9, 4], [4.6, 6.1], [6.5, 7]];
  const cues = mapCues(["one two three", "four five", "six seven eight nine"], segs);
  for (const c of cues) assert.ok(segs.some(([a, b]) => c.from >= a - 1e-9 && c.from < b), `starts in speech: ${c.from}`);
  const one = mapCues(["just one"], segs);
  assert.deepEqual([one[0].from, one[0].to], [0.3, 7]);
});

test("segments inside a part window are clipped to it", () => {
  assert.deepEqual(segsWithin([[0, 2], [3, 5], [6, 8]], 1, 6.5), [[1, 2], [3, 5], [6, 6.5]]);
});

test("without a voice, phrases are spread by character share", () => {
  const c = spreadCues(["aa", "aaaa"], 0, 6);
  assert.equal(c[0].from, 0);
  assert.ok(c[1].from > c[0].from && c[1].from < 6);
  assert.ok(speechWeight("2026") > speechWeight("abcd"), "a digit takes longer to say than a letter");
});

test("captions: every phrase fits two lines of at most 42 characters", () => {
  for (const t of [...SCENE_CUES.flat(), ...PLANNER_PARTS.flat()]) {
    const lines = wrapCaption(t, 42);
    assert.ok(lines.length >= 1 && lines.length <= 2, t);
    lines.forEach((l) => assert.ok(l.length <= 42, `${l.length}: ${l}`));
    assert.equal(lines.join(" "), t.replace(/\s+/g, " ").trim());
  }
  assert.deepEqual(wrapCaption("short"), ["short"]);
  assert.throws(() => wrapCaption("x".repeat(30) + " " + "y".repeat(30) + " " + "z".repeat(30)));
});

test("fit rule: the scale size when it fits, smaller when the measured width is wider, never below the floor", () => {
  assert.equal(fitSize(800, 52, 1000), 52);
  assert.equal(fitSize(1300, 52, 1000), 40);
  assert.ok(fitSize(1300, 52, 1000) * (1300 / 52) <= 1000 + 1e-9);
  assert.equal(fitSize(5000, 52, 1000), 32);
});
