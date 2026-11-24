import test from "node:test";
import assert from "node:assert/strict";
import {
  BASE_FRAMES, FPS, MIN_TOTAL, MAX_TOTAL, TAIL_FRAMES,
  planScenes, shotStarts, musicGain, speechWindows, matchSfx,
} from "../src/timing.ts";

const none = Array(9).fill(null);

test("without voice-over the scenes keep the script timings and total exactly 3:00", () => {
  const p = planScenes(none);
  assert.deepEqual(p.durations, BASE_FRAMES);
  assert.equal(p.total, 5400);
  assert.equal(FPS, 30);
  assert.deepEqual(p.warnings, []);
});

test("a scene stretches only when its clean voice file is longer than the slot (voice + 0.6 s tail)", () => {
  const vo = [...none];
  vo[0] = 8; // fits in 300 frames (needs 8*30+18 = 258)
  vo[1] = 9.5; // 285+18 = 303 > 270 -> stretches
  const p = planScenes(vo);
  assert.equal(p.durations[0], 300);
  assert.equal(p.durations[1], Math.ceil(9.5 * FPS) + TAIL_FRAMES);
});

test("a long total is brought back to 3:10 by trimming holds, never speech", () => {
  const vo = [...none];
  vo[4] = 60; // scene 5 needs 1818 frames instead of 1440
  vo[6] = 36; // scene 7 needs 1098 instead of 900
  vo[2] = 17; // scene 3 needs 528 instead of 450
  const p = planScenes(vo);
  assert.ok(p.total <= MAX_TOTAL, `total ${p.total}`);
  assert.ok(p.total >= MIN_TOTAL);
  [[4, 60], [6, 36], [2, 17]].forEach(([i, s]) => assert.ok(p.durations[i] >= Math.ceil(s * FPS) + TAIL_FRAMES, `scene ${i + 1} cut into speech`));
  assert.equal(p.durations.reduce((a, b) => a + b, 0), p.total);
});

test("warns when speech alone cannot fit in 3:10", () => {
  const vo = Array(9).fill(25);
  const p = planScenes(vo);
  assert.ok(p.warnings.length > 0);
});

test("scene starts accumulate", () => {
  const p = planScenes(none);
  assert.equal(p.starts[0], 0);
  assert.equal(p.starts[1], 300);
  assert.equal(p.starts[8] + p.durations[8], 5400);
});

test("scene 5 shots follow the script split by default and the silences when known", () => {
  const d = shotStarts(1440, null);
  assert.deepEqual(d, [0, 300, 540, 810, 1140]);
  const s = shotStarts(1440, [0.3, 9, 16.5, 24, 34]);
  assert.equal(s.length, 5);
  assert.ok(s.every((v, i) => i === 0 || v > s[i - 1]));
  assert.ok(s[4] < 1440);
});

test("music is ducked about 18 dB under speech, full in gaps, faded in 1.5 s and out 2.5 s", () => {
  const total = 5400;
  const win = [[120, 300]];
  const full = musicGain(2000, win, total);
  const ducked = musicGain(200, win, total);
  assert.ok(full > 0.4);
  assert.ok(Math.abs(20 * Math.log10(ducked / full) + 18) < 0.5, `duck ${20 * Math.log10(ducked / full)}`);
  assert.equal(musicGain(0, win, total), 0);
  assert.ok(musicGain(45, [], total) > 0.95 * full);
  assert.ok(musicGain(total - 1, [], total) < 0.02);
  // a 12-frame ramp, not a jump
  const before = musicGain(115, win, total);
  assert.ok(before < full && before > ducked);
});

test("speech windows come from each scene's voice start and length", () => {
  const p = planScenes([4, null, ...Array(7).fill(null)]);
  const w = speechWindows(p.starts, [4, null, ...Array(7).fill(null)]);
  assert.equal(w.length, 1);
  assert.equal(w[0][0], 0);
  assert.equal(w[0][1], Math.round(4 * FPS));
});

test("sound effects are matched loosely by file name; none when absent", () => {
  const files = ["Big_Whoosh-01.wav", "ui tap soft.mp3", "city-ambience.mp3", "Chime_2.wav"];
  assert.equal(matchSfx(files, "whoosh"), "Big_Whoosh-01.wav");
  assert.equal(matchSfx(files, "tap"), "ui tap soft.mp3");
  assert.equal(matchSfx(files, "city-ambience"), "city-ambience.mp3");
  assert.equal(matchSfx(files, "chime"), "Chime_2.wav");
  assert.equal(matchSfx(files, "riser"), null);
  assert.equal(matchSfx([], "tap"), null);
  assert.equal(matchSfx(files, "map-swoosh"), "Big_Whoosh-01.wav");
});

test("scene 1 cues find the user's bus sounds, with a whoosh as the fallback for the air brake", () => {
  const files = ["bus door hissing.mp3", "bus horn.mp3", "busengine idling.mp3", "swoosh.mp3"];
  assert.equal(matchSfx(files, "air-brake"), "bus door hissing.mp3");
  assert.equal(matchSfx(files, "horn"), "bus horn.mp3");
  assert.equal(matchSfx(files, "engine"), "busengine idling.mp3");
  assert.equal(matchSfx(["swoosh.mp3"], "air-brake"), "swoosh.mp3");
  assert.equal(matchSfx(["a.mp3"], "horn"), null);
});
