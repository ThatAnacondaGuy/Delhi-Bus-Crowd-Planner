// Burned-in caption text, from the voice-over script (docs/DEMO_VIDEO_SCRIPT.md section 4), one chunk per phrase.
// Numbers follow the rule "digits where the voice says them as words" only where the number is in the numbers table
// (0.54, 09:00, 578 Down); other spoken numbers stay in words so nothing typed disagrees with the rendered docs.
// Pure data and a pure helper: no imports (tests/captions.test.mjs).

export const SCENE_CAPTIONS: string[][] = [
  ["Your phone says the bus is coming.", "Not whether you'll sit — or stand for an hour."],
  ["Delhi Bus Crowding Planner.", "How crowded each stretch of your trip usually is — before you board."],
  [
    "Nobody counts people on Delhi buses.",
    "We started with what is recorded: over two and a half million app tickets,",
    "from October 2026, matched to the timetable and to GPS.",
  ],
  [
    "Every ticket records where a rider got on, and off.",
    "We spread it over the stretches they rode, then scale app riders up to everyone on board —",
    "never more than a bus can hold.",
    "Set that against the seats, and you get one word, three dots, and a colour.",
  ],
  // scene 5 is split into five parts (5a to 5e); see PLANNER_PARTS
  [],
  [
    "A second screen is for bus operators.",
    "Where would one extra trip help most?",
    "On a weekday, route 578 Down at 08:30: nearly twenty thousand crowded rider-minutes removed,",
    "and over seven thousand riders moved down a level.",
    "Model estimates, not counts.",
  ],
  [
    "We wrote down what we expected first. Then reported every hit — and every miss.",
    "Peaks at nine and seven: hit. Published bus-kilometres: hit.",
    "Load factor: a miss — 0.54, below the published band.",
    "Ten of ten corridors? Chance alone gives ten of ten.",
    "No field count was possible.",
  ],
  [
    "Most levels are a rough guess, and buses can be fuller than shown.",
    "Next: more months of tickets, an on-bus count, live arrivals.",
  ],
  [
    "Try it live — or run it yourself from GitHub.",
    "Delhi Bus Crowding Planner. Made by Aniket and Ash.",
  ],
];

export const PLANNER_PARTS: string[][] = [
  [
    "The brief's own example, six in the evening: the fastest bus is usually standing.",
    "A slightly slower one usually has seats.",
  ],
  ["Reverse it, and the answer changes: usually crowded.", "Same road, different direction. The planner knows."],
  ["Tap Why: app tickets, about 1 in 44 riders, scaled up, against the seats and rated total."],
  [
    "Mandi House to Laxmi Nagar: crowded.",
    "Leave a little later: same ride, room to stand.",
    "Offered only when it's really better.",
  ],
  ["Each card says how sure we are — mostly, a rough guess.", "Too little data? It says No data, never a seat."],
];

export type Span = { text: string; from: number; to: number };

/** Spread caption chunks over [start, end] frames in proportion to their length (so longer phrases stay up longer). */
export function chunkSpans(chunks: string[], start: number, end: number): Span[] {
  const total = chunks.reduce((a, c) => a + c.length, 0) || 1;
  const spans: Span[] = [];
  let at = start;
  for (const text of chunks) {
    const len = ((end - start) * text.length) / total;
    spans.push({ text, from: Math.round(at), to: Math.round(at + len) });
    at += len;
  }
  return spans;
}

/** The caption shown at a frame, or null. */
export function captionAt(spans: Span[], frame: number): string | null {
  const s = spans.find((x) => frame >= x.from && frame < x.to);
  return s ? s.text : null;
}

/**
 * Picture-led scenes (3, 4, 6, 7, 8): while there is no voice file, caption chunks follow the script's own timecodes
 * (frame boundaries inside the scene at its script length). Once a voice file exists they follow the speech instead.
 * bounds has chunks.length + 1 entries.
 */
export const SCRIPT_BOUNDS: Record<number, number[]> = {
  3: [10, 100, 220, 400],
  4: [10, 144, 350, 432, 700],
  6: [10, 70, 140, 250, 350, 430],
  7: [10, 120, 420, 630, 810, 895],
  8: [10, 150, 360],
};

export function boundSpans(chunks: string[], bounds: number[], scale = 1): Span[] {
  return chunks.map((text, i) => ({ text, from: Math.round(bounds[i] * scale), to: Math.round(bounds[i + 1] * scale) }));
}

/** Caption spans for a scene: speech-led when a voice file (frames) is known, script-led otherwise. */
export function sceneSpans(scene: number, chunks: string[], voFrames: number | null, base: number, duration: number, lead: number): Span[] {
  const bounds = SCRIPT_BOUNDS[scene];
  if (voFrames == null && bounds) return boundSpans(chunks, bounds, Math.min(1, duration / base));
  const end = voFrames != null ? voFrames : duration - 40;
  return chunkSpans(chunks, lead + 6, Math.max(end, 120));
}
