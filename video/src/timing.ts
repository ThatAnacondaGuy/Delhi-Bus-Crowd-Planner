// Pure timing and mix logic. No imports, so `node --test` can run it directly (tests/timing.test.mjs).

export const FPS = 30;
/** Scene lengths in frames from docs/DEMO_VIDEO_SCRIPT.md (scene table): 5400 frames = 3:00 exactly. */
export const BASE_FRAMES = [300, 270, 450, 720, 1440, 660, 900, 390, 270];
export const MIN_TOTAL = 170 * FPS; // 2:50
export const MAX_TOTAL = 190 * FPS; // 3:10
/** A scene never ends on the last word: the clean voice file is followed by 0.6 s of room. */
export const TAIL_FRAMES = Math.round(0.6 * FPS);
/** prep_audio.sh trims the lead-in to about 0.3 s. */
export const LEAD_FRAMES = Math.round(0.3 * FPS);

export type ScenePlan = {
  durations: number[];
  starts: number[];
  total: number;
  warnings: string[];
};

/**
 * Scene lengths from the script timings, stretched only when a clean voice file (seconds, null when absent) plus the
 * tail is longer than the slot. If the total passes 3:10, holds are trimmed (never speech): each scene may shrink
 * towards max(voice + tail, 80% of its script length), in proportion to the room it has.
 */
export function planScenes(voSeconds: (number | null)[]): ScenePlan {
  const warnings: string[] = [];
  const need = BASE_FRAMES.map((_, i) => {
    const v = voSeconds[i];
    return v == null || !(v > 0) ? 0 : Math.ceil(v * FPS) + TAIL_FRAMES;
  });
  const durations = BASE_FRAMES.map((b, i) => Math.max(b, need[i]));
  let total = durations.reduce((a, b) => a + b, 0);

  if (total > MAX_TOTAL) {
    const floors = BASE_FRAMES.map((b, i) => Math.max(need[i], Math.round(b * 0.8)));
    let excess = total - MAX_TOTAL;
    for (let pass = 0; pass < 4 && excess > 0; pass++) {
      const slack = durations.map((d, i) => Math.max(0, d - floors[i]));
      const slackSum = slack.reduce((a, b) => a + b, 0);
      if (slackSum === 0) break;
      const cut = slack.map((s) => Math.min(s, Math.ceil((excess * s) / slackSum)));
      let cutSum = cut.reduce((a, b) => a + b, 0);
      // never remove more than the excess
      for (let i = cut.length - 1; i >= 0 && cutSum > excess; i--) {
        const give = Math.min(cut[i], cutSum - excess);
        cut[i] -= give;
        cutSum -= give;
      }
      cut.forEach((c, i) => (durations[i] -= c));
      excess -= cutSum;
    }
    total = durations.reduce((a, b) => a + b, 0);
    if (total > MAX_TOTAL) warnings.push(`Total ${(total / FPS).toFixed(1)} s is over 3:10: the voice itself is too long, record shorter takes or use the "Cut first" lines.`);
  }
  if (total < MIN_TOTAL) warnings.push(`Total ${(total / FPS).toFixed(1)} s is under 2:50.`);

  const starts: number[] = [];
  let at = 0;
  for (const d of durations) {
    starts.push(at);
    at += d;
  }
  return { durations, starts, total, warnings };
}

/** Scene 05 shot starts (frames inside the scene): the script split, or the silences found in the clean voice file. */
const SHOT_SPLIT = [0, 300, 540, 810, 1140];
export function shotStarts(duration: number, partStartsSeconds: number[] | null): number[] {
  if (!partStartsSeconds || partStartsSeconds.length !== 5) {
    return SHOT_SPLIT.map((f) => Math.round((f / 1440) * duration));
  }
  const MIN_SHOT = 90;
  const out: number[] = [];
  partStartsSeconds.forEach((s, i) => {
    // the picture arrives a moment before the words (a small J-cut), except for the first shot
    let f = i === 0 ? 0 : Math.round(s * FPS) - 9;
    const lo = i === 0 ? 0 : out[i - 1] + MIN_SHOT;
    const hi = duration - (5 - i) * MIN_SHOT;
    f = Math.max(lo, Math.min(f, hi));
    out.push(f);
  });
  return out;
}

/** [startFrame, endFrame] of speech per scene that has a voice file (global frames). */
export function speechWindows(starts: number[], voSeconds: (number | null)[]): [number, number][] {
  const w: [number, number][] = [];
  voSeconds.forEach((v, i) => {
    if (v != null && v > 0) w.push([starts[i], starts[i] + Math.round(v * FPS)]);
  });
  return w;
}

export const MUSIC_BASE = 0.55; // full level in the gaps
export const DUCK_DB = -18;
const DUCK = Math.pow(10, DUCK_DB / 20);
export const RAMP = 12;

/** Music volume at a frame: ducked about 18 dB while speech plays, back to full over 12 frames, fade in 1.5 s, out 2.5 s. */
export function musicGain(frame: number, windows: [number, number][], total: number): number {
  let duck = 0; // 0 = full, 1 = fully ducked
  for (const [a, b] of windows) {
    let d: number;
    if (frame >= a && frame <= b) d = 1;
    else if (frame < a) d = Math.max(0, 1 - (a - frame) / RAMP);
    else d = Math.max(0, 1 - (frame - b) / RAMP);
    if (d > duck) duck = d;
  }
  const level = MUSIC_BASE * (1 - duck * (1 - DUCK));
  const fadeIn = Math.min(1, Math.max(0, frame / (1.5 * FPS)));
  const fadeOut = Math.min(1, Math.max(0, (total - 1 - frame) / (2.5 * FPS)));
  return level * Math.min(fadeIn, fadeOut);
}

export type SfxKey = "ambience" | "whoosh" | "tap" | "pop" | "chime" | "riser" | "map-swoosh" | "city-ambience" | "air-brake" | "horn" | "engine";

const SYNONYMS: Record<string, string[]> = {
  ambience: ["ambien", "city", "street", "traffic"],
  "city-ambience": ["ambien", "city", "street", "traffic"],
  whoosh: ["whoosh", "swoosh", "swish"],
  tap: ["tap", "click", "tick"],
  pop: ["pop", "blip"],
  chime: ["chime", "bell", "ding"],
  riser: ["riser", "rise", "swell"],
  "map-swoosh": ["map", "whoosh", "swoosh"],
  "air-brake": ["hiss", "brake", "whoosh", "swoosh"],
  horn: ["horn"],
  engine: ["engine", "idl"],
};

/** Match a sound effect file by loose name (case-insensitive substring); null when nothing in the folder fits. */
export function matchSfx(files: string[], key: string): string | null {
  const words = SYNONYMS[key] ?? [key];
  for (const w of words) {
    const hit = files.find((f) => f.toLowerCase().includes(w));
    if (hit) return hit;
  }
  return null;
}
