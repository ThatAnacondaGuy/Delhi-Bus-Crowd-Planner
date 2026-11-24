// Timeline and mix logic. Pure: imports only other pure modules (with their .ts extension) so `node --test` runs it directly.
import { mapCues, segsWithin, speechFromSilences, spreadCues, wrapCaption } from "./sync.ts";
import type { Cue, Seg } from "./sync.ts";
import { PLANNER_PARTS, SCENE_CUES } from "./captions.ts";
import type { Span } from "./captions.ts";

export const FPS = 30;
/** Scene lengths from the script (docs/DEMO_VIDEO_SCRIPT.md scene table), used only for a scene with no voice file. */
export const BASE_FRAMES = [300, 270, 450, 720, 1440, 660, 900, 390, 270];
export const MIN_TOTAL = 175 * FPS; // 2:55
export const MAX_TOTAL = 200 * FPS; // 3:20
/**
 * With a voice file a scene is HEAD + the clean voice + TAIL frames, nothing else: the voice drives the timeline.
 * HEAD: picture before the first word (scene 1: the city and its sound first). TAIL: room after the last word
 * (scene 4: the chip grows into the phone; scene 7: "No field count was possible." is held; scene 9: the end card).
 */
export const HEAD = [66, 10, 10, 10, 12, 12, 12, 10, 10];
export const TAIL = [20, 22, 20, 34, 24, 22, 50, 20, 105];
/** Kept for the end-card music fade: the last scene keeps this long after its voice. */
export const LAST_TAIL_FRAMES = TAIL[8];
/** Boundary transitions: a wipe of this many frames centred on every scene cut. */
export const WIPE = 12;

export type ScenePlan = { durations: number[]; starts: number[]; total: number; warnings: string[] };

export function planScenes(voSeconds: (number | null)[]): ScenePlan {
  const warnings: string[] = [];
  const durations = BASE_FRAMES.map((b, i) => {
    const v = voSeconds[i];
    return v != null && v > 0 ? HEAD[i] + Math.ceil(v * FPS) + TAIL[i] : b;
  });
  const total = durations.reduce((a, b) => a + b, 0);
  if (voSeconds.some((v) => v != null && v > 0)) {
    if (total > MAX_TOTAL) warnings.push(`Total ${(total / FPS).toFixed(1)} s is over 3:20: record shorter takes or use the "Cut first" lines.`);
    if (total < MIN_TOTAL) warnings.push(`Total ${(total / FPS).toFixed(1)} s is under 2:55.`);
  }
  const starts: number[] = [];
  let at = 0;
  for (const d of durations) {
    starts.push(at);
    at += d;
  }
  return { durations, starts, total, warnings };
}

/* ------------------------------------------------------------------ cues on the timeline */

/** A cue in scene-local frames. part: scene 5's part (0..4), else 0. segFrom/segTo: the speech it was placed on (frames). */
export type FrameCue = { text: string; from: number; to: number; part: number; split: boolean };
export type SceneTimeline = {
  scene: number;
  duration: number;
  head: number;
  voiced: boolean;
  cues: FrameCue[];
  /** scene 5: first frame of each of the five phone shots (scene-local); others: [0] */
  shots: number[];
};

const f = (sec: number) => Math.round(sec * FPS);

/**
 * The timeline of scene n (1..9). silences: [start, end] seconds detected in the clean voice file; voSec its length;
 * partStarts: scene 5's part starts in seconds (from prep_audio.sh), or null.
 */
export function sceneTimeline(
  scene: number,
  duration: number,
  voSec: number | null,
  silences: Seg[] | null,
  partStarts: number[] | null,
): SceneTimeline {
  const i = scene - 1;
  const voiced = voSec != null && voSec > 0;
  const head = voiced ? HEAD[i] : 12;
  const toFrames = (c: Cue, part: number): FrameCue => ({ text: c.text, from: head + f(c.from), to: head + f(c.to), part, split: c.split });

  if (scene !== 5) {
    const texts = SCENE_CUES[i];
    if (!voiced) return { scene, duration, head, voiced, cues: spreadCues(texts, 0, (duration - 30) / FPS).map((c) => toFrames(c, 0)), shots: [0] };
    const segs = speechFromSilences(silences ?? [], voSec!);
    return { scene, duration, head, voiced, cues: mapCues(texts, segs).map((c) => toFrames(c, 0)), shots: [0] };
  }

  // scene 5: five parts; each shot starts a few frames before its first word (a small J-cut), the first at frame 0
  if (!voiced) {
    const split = [0, 300, 540, 810, 1140].map((x) => Math.round((x / 1440) * duration));
    const ends = [...split.slice(1), duration];
    const cues = PLANNER_PARTS.flatMap((texts, k) => spreadCues(texts, (split[k] + 14) / FPS, (ends[k] - 20) / FPS).map((c) => ({ ...toFrames(c, k), from: f(c.from), to: f(c.to) })));
    return { scene, duration, head: 0, voiced, cues, shots: split };
  }
  const segs = speechFromSilences(silences ?? [], voSec!);
  const ps = partStarts && partStarts.length === 5 ? partStarts : null;
  // without detected part starts, the parts follow the word shares of the script over the speech
  const bounds = ps ?? mapCues(PLANNER_PARTS.map((p) => p.join(" ")), segs).map((c) => c.from);
  const cues: FrameCue[] = [];
  PLANNER_PARTS.forEach((texts, k) => {
    const a = k === 0 ? 0 : bounds[k] - 0.05;
    const b = k === 4 ? voSec! + 1 : bounds[k + 1] - 0.05;
    const within = segsWithin(segs, a, b);
    mapCues(texts, within).forEach((c) => cues.push(toFrames(c, k)));
  });
  const shots = [0, 1, 2, 3, 4].map((k) => (k === 0 ? 0 : head + f(bounds[k]) - 8));
  return { scene, duration, head, voiced, cues, shots };
}

/**
 * When a caption is on screen: from the first word of its phrase to its last word plus a short hold; a pause shorter
 * than 0.4 s to the next phrase is bridged so captions never flicker.
 */
export function captionSpans(cues: FrameCue[], duration: number): Span[] {
  return cues.map((c, k) => {
    const next = cues[k + 1];
    let to = c.to + 9;
    if (next) to = next.from - c.to < 12 ? next.from : Math.min(to, next.from - 2);
    else to = Math.min(to + 6, duration - 2);
    return { text: c.text, from: c.from, to: Math.max(to, c.from + 15) };
  });
}

/** Caption lines (at most 2 of at most 42 characters). */
export const captionLines = (text: string) => wrapCaption(text, 42);

/* ------------------------------------------------------------------ music */

/** A speech window: [startFrame, endFrame, depth]. */
export type Window = [number, number, number?];

/** Music is ducked from the first word to the last word of every voiced scene (global frames). */
export function speechWindows(starts: number[], voSeconds: (number | null)[]): Window[] {
  const w: Window[] = [];
  voSeconds.forEach((v, i) => {
    if (v != null && v > 0) w.push([starts[i] + HEAD[i], starts[i] + HEAD[i] + Math.round(v * FPS)]);
  });
  return w;
}

export const MUSIC_BASE = 0.9; // full level in the gaps (tracks are first trimmed to a common loudness)
export const MUSIC_TARGET_LUFS = -18;
export const DUCK_DB = -18;
const DUCK = Math.pow(10, DUCK_DB / 20);
export const RAMP = 12;

/** Music volume at a frame: ducked about 18 dB while speech plays, back to full over 12 frames, fade in 1.5 s, out 2.5 s. */
export function musicGain(frame: number, windows: Window[], total: number): number {
  let duck = 0;
  for (const [a, b, depth = 1] of windows) {
    let d: number;
    if (frame >= a && frame <= b) d = 1;
    else if (frame < a) d = Math.max(0, 1 - (a - frame) / RAMP);
    else d = Math.max(0, 1 - (frame - b) / RAMP);
    d *= depth;
    if (d > duck) duck = d;
  }
  const level = MUSIC_BASE * (1 - duck * (1 - DUCK));
  const fadeIn = Math.min(1, Math.max(0, frame / (1.5 * FPS)));
  const fadeOut = Math.min(1, Math.max(0, (total - 1 - frame) / (2.5 * FPS)));
  return level * Math.min(fadeIn, fadeOut);
}

/** The two music tracks cross over during 4 s, centred on the scene boundary closest to 1:55 (R37). */
export const XFADE_FRAMES = 4 * FPS;
export const XFADE_TARGET = 115 * FPS;

export function pickCrossfade(starts: number[], target: number, aFrames: number): number {
  const ok = starts.slice(1).filter((b) => b + XFADE_FRAMES / 2 <= aFrames);
  if (ok.length === 0) return Math.max(0, aFrames - XFADE_FRAMES);
  const best = ok.reduce((m, b) => (Math.abs(b - target) < Math.abs(m - target) ? b : m), ok[0]);
  return best - XFADE_FRAMES / 2;
}

export function trackGains(frame: number, windows: Window[], total: number, xs: number | null, tracks: number): number[] {
  const base = musicGain(frame, windows, total);
  if (tracks < 2 || xs == null) return [base];
  const t = Math.min(1, Math.max(0, (frame - xs) / XFADE_FRAMES));
  const a = t >= 1 ? 0 : Math.cos((t * Math.PI) / 2);
  const b = t <= 0 ? 0 : Math.sin((t * Math.PI) / 2);
  return [base * a, base * b];
}

/* ------------------------------------------------------------------ sound effects by loose file name */

const SYNONYMS: Record<string, string[]> = {
  ambience: ["road", "ambien", "city", "street", "traffic"],
  "city-ambience": ["city amb", "ambien", "city", "street", "traffic"],
  whoosh: ["whoosh", "swoosh", "swish"],
  swoop: ["swoop", "swoosh", "whoosh"],
  ding: ["ding", "chime", "bell"],
  tap: ["tap", "click", "tick"],
  pop: ["pop", "blip"],
  chime: ["chime", "bell", "ding"],
  riser: ["riser", "rise", "swell"],
  "map-swoosh": ["map", "whoosh", "swoosh"],
  "air-brake": ["hiss", "brake", "whoosh", "swoosh"],
  horn: ["horn"],
  engine: ["engine", "idl"],
};

export function matchSfx(files: string[], key: string): string | null {
  const words = SYNONYMS[key] ?? [key];
  for (const w of words) {
    const hit = files.find((x) => x.toLowerCase().includes(w));
    if (hit) return hit;
  }
  return null;
}
