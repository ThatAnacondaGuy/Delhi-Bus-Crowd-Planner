import test from "node:test";
import assert from "node:assert/strict";
import {
  BASE_FRAMES, FPS, HEAD, TAIL, MIN_TOTAL, MAX_TOTAL, LAST_TAIL_FRAMES,
  planScenes, sceneTimeline, captionSpans, musicGain, speechWindows, matchSfx,
  XFADE_FRAMES, XFADE_TARGET, pickCrossfade, trackGains,
} from "../src/timing.ts";
import { PLANNER_PARTS, SCENE_CUES } from "../src/captions.ts";

const none = Array(9).fill(null);
// the recorded clean voice lengths (s) and the silences found in scene 1 (silencedetect -35 dB, 0.2 s)
const VO = [9.091, 8.536, 14.521, 23.048, 44.983, 22.888, 25.501, 10.548, 8.583];
const S1 = [[0, 0.344], [1.557, 2.221], [3.475, 5.357], [5.972, 6.369], [6.866, 7.779]];

test("without voice-over the scenes keep the script timings: 3:00 exactly", () => {
  const p = planScenes(none);
  assert.deepEqual(p.durations, BASE_FRAMES);
  assert.equal(p.total, 5400);
  assert.equal(FPS, 30);
});

test("with a clean voice file the scene is driven by the voice, never by the script slot", () => {
  const p = planScenes(VO);
  VO.forEach((v, i) => assert.equal(p.durations[i], HEAD[i] + Math.ceil(v * FPS) + TAIL[i], `scene ${i + 1}`));
  assert.notEqual(p.durations[0], BASE_FRAMES[0]);
  assert.ok(p.total >= MIN_TOTAL && p.total <= MAX_TOTAL, `total ${p.total / FPS} s`);
  assert.deepEqual(p.warnings, []);
  assert.equal(p.starts[8] + p.durations[8], p.total);
});

test("a total outside 2:55..3:20 is reported", () => {
  assert.ok(planScenes(Array(9).fill(25)).warnings.length > 0);
  assert.ok(planScenes(Array(9).fill(5)).warnings.length > 0);
});

test("scene cues sit on the speech: first word of each phrase = head + segment start", () => {
  const p = planScenes(VO);
  const tl = sceneTimeline(1, p.durations[0], VO[0], S1, null);
  assert.equal(tl.head, HEAD[0]);
  assert.deepEqual(tl.cues.map((c) => c.text), SCENE_CUES[0]);
  assert.deepEqual(tl.cues.map((c) => c.from), [0.344, 5.357, 7.779].map((s) => HEAD[0] + Math.round(s * FPS)));
});

test("scene 5: five shots cut at the four pauses between parts, a few frames before the first word", () => {
  const p = planScenes(VO);
  const parts = [0.3, 9.91, 18.35, 26.41, 37.0];
  // two pauses inside each part, plus the four long part breaks
  const sil = [[0, 0.3], [3, 3.6], [8.67, 9.91], [13.7, 14.6], [17.43, 18.35], [22.0, 22.5], [25.37, 26.41], [29.9, 30.7], [35.49, 37.0], [40.7, 41.7]];
  const tl = sceneTimeline(5, p.durations[4], VO[4], sil, parts);
  assert.equal(tl.shots.length, 5);
  assert.equal(tl.shots[0], 0);
  parts.slice(1).forEach((s, k) => assert.equal(tl.shots[k + 1], HEAD[4] + Math.round(s * FPS) - 8));
  assert.equal(tl.cues.length, PLANNER_PARTS.flat().length);
  // every part's first phrase starts on its part's first word
  let k = 0;
  PLANNER_PARTS.forEach((texts, part) => {
    const c = tl.cues[k];
    assert.equal(c.part, part);
    assert.equal(c.text, texts[0]);
    assert.equal(c.from, HEAD[4] + Math.round(parts[part] * FPS));
    k += texts.length;
  });
});

test("caption spans: start on the first word, never overlap, bridge short pauses, end inside the scene", () => {
  const p = planScenes(VO);
  const tl = sceneTimeline(1, p.durations[0], VO[0], S1, null);
  const spans = captionSpans(tl.cues, tl.duration);
  spans.forEach((s, i) => {
    assert.equal(s.from, tl.cues[i].from);
    assert.ok(s.to > s.from);
    if (i) assert.ok(s.from >= spans[i - 1].to);
    assert.ok(s.to <= tl.duration);
  });
  const bridged = captionSpans([{ text: "a", from: 10, to: 40, part: 0, split: false }, { text: "b", from: 46, to: 80, part: 0, split: false }], 200);
  assert.equal(bridged[0].to, 46);
});

test("music is ducked about 18 dB under speech, full in gaps, faded in 1.5 s and out 2.5 s", () => {
  const total = 5400;
  const win = [[120, 300]];
  const full = musicGain(2000, win, total);
  const ducked = musicGain(200, win, total);
  assert.ok(Math.abs(20 * Math.log10(ducked / full) + 18) < 0.5);
  assert.equal(musicGain(0, win, total), 0);
  assert.ok(musicGain(total - 1, [], total) < 0.02);
  const before = musicGain(115, win, total);
  assert.ok(before < full && before > ducked);
});

test("speech windows run from each scene's first to last voice frame", () => {
  const p = planScenes(VO);
  const w = speechWindows(p.starts, VO);
  assert.equal(w.length, 9);
  assert.equal(w[0][0], HEAD[0]);
  assert.equal(w[0][1], HEAD[0] + Math.round(VO[0] * FPS));
  assert.equal(speechWindows(planScenes(none).starts, none).length, 0);
});

test("the end card keeps its tail after the last voice line so the music fades out fully", () => {
  const p = planScenes(VO);
  const w = speechWindows(p.starts, VO);
  assert.ok(LAST_TAIL_FRAMES >= 75);
  assert.ok(p.total - w[8][1] >= LAST_TAIL_FRAMES);
});

test("music crossfade: the scene boundary closest to 1:55, centred, 4 s long, equal power", () => {
  assert.equal(XFADE_FRAMES, 120);
  const starts = [0, 300, 574, 1028, 1748, 3188, 3893, 4793, 5183];
  assert.equal(pickCrossfade(starts, XFADE_TARGET, 122 * FPS), 3188 - XFADE_FRAMES / 2);
  const xs2 = pickCrossfade([0, 300, 3600, 3900], XFADE_TARGET, 3700);
  assert.ok(xs2 + XFADE_FRAMES <= 3700);
  const xs = 3128;
  const mid = trackGains(xs + XFADE_FRAMES / 2, [], 5460, xs, 2);
  const base = musicGain(xs + XFADE_FRAMES / 2, [], 5460);
  assert.ok(Math.abs(mid[0] ** 2 + mid[1] ** 2 - base ** 2) < 1e-9);
});

test("sound effects are matched loosely by file name; none when absent", () => {
  const files = ["Big_Whoosh-01.wav", "ui tap soft.mp3", "city-ambience.mp3", "Chime_2.wav", "bus door hissing.mp3", "bus horn.mp3", "busengine idling.mp3"];
  assert.equal(matchSfx(files, "whoosh"), "Big_Whoosh-01.wav");
  assert.equal(matchSfx(files, "tap"), "ui tap soft.mp3");
  assert.equal(matchSfx(files, "chime"), "Chime_2.wav");
  assert.equal(matchSfx(files, "air-brake"), "bus door hissing.mp3");
  assert.equal(matchSfx(files, "engine"), "busengine idling.mp3");
  assert.equal(matchSfx(files, "riser"), null);
});
