// Burned-in caption phrases, from the voice-over script (docs/DEMO_VIDEO_SCRIPT.md section 4), split at the script's own
// pause marks ("/" and "//") so one phrase is one breath of the recording. src/sync.ts places each phrase on the speech
// segments of the clean voice file; captions and the visual beats of each scene follow those times.
// Digits only where the numbers table has them (0.54, 08:30, 578 Down, 1 in 44, October 2026); other spoken numbers stay in words.
// Pure data and a pure helper: no imports (tests/captions.test.mjs).

/** Phrases per scene (index 0 = scene 1). Scene 5 is carried by PLANNER_PARTS. */
export const SCENE_CUES: string[][] = [
  ["Your phone says the bus is coming.", "Not whether you'll sit —", "or stand for an hour."],
  ["Delhi Bus Crowding Planner.", "How crowded each stretch of your trip usually is —", "before you board."],
  [
    "Nobody counts people on Delhi buses.",
    "We started with what is recorded:",
    "over two and a half million app tickets,",
    "from October 2026,",
    "matched to the timetable and to GPS.",
  ],
  [
    "Every ticket records where a rider got on, and off.",
    "We spread it over the stretches they rode,",
    "then scale app riders up to everyone on board —",
    "never more than a bus can hold.",
    "Set that against the seats,",
    "and you get one word,",
    "three dots,",
    "and a colour.",
  ],
  [],
  [
    "A second screen is for bus operators.",
    "Where would one extra trip help most?",
    "On a weekday, route 578 Down at 08:30:",
    "nearly twenty thousand crowded rider-minutes removed,",
    "and over seven thousand riders moved down a level.",
    "Model estimates, not counts.",
  ],
  [
    "We wrote down what we expected first.",
    "Then reported every hit — and every miss.",
    "Peaks at nine and seven: hit.",
    "Published bus-kilometres: hit.",
    "Load factor: a miss —",
    "0.54, below the published band.",
    "Ten of ten corridors?",
    "Chance alone gives ten of ten.",
    "No field count was possible.",
  ],
  [
    "Most levels are a rough guess,",
    "and buses can be fuller than shown.",
    "Next: more months of tickets,",
    "an on-bus count,",
    "live arrivals.",
  ],
  ["Try it live —", "or run it yourself from GitHub.", "Delhi Bus Crowding Planner.", "Made by Aniket and Ash."],
];

/** Scene 5, recorded as one file in five parts (5a to 5e) with a pause between parts. */
export const PLANNER_PARTS: string[][] = [
  ["The brief's own example, six in the evening:", "the fastest bus is usually standing.", "A slightly slower one usually has seats."],
  ["Reverse it, and the answer changes:", "usually crowded.", "Same road, different direction.", "The planner knows."],
  ["Tap Why: app tickets,", "about 1 in 44 riders, scaled up,", "against the seats and rated total."],
  ["Mandi House to Laxmi Nagar: crowded.", "Leave a little later:", "same ride, room to stand.", "Offered only when it's really better."],
  ["Each card says how sure we are —", "mostly, a rough guess.", "Too little data? It says No data,", "never a seat."],
];

/** Phrases of scene n (1..9), scene 5 flattened. */
export const cueTexts = (scene: number): string[] => (scene === 5 ? PLANNER_PARTS.flat() : SCENE_CUES[scene - 1]);

export type Span = { text: string; from: number; to: number };

/** SubRip text for a list of spans placed at global frame offsets (fps frames per second). Overlaps are trimmed. */
export function toSrt(entries: Span[], fps: number): string {
  const sorted = [...entries].sort((a, b) => a.from - b.from);
  const stamp = (frames: number) => {
    const ms = Math.round((frames / fps) * 1000);
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    const p = (n: number, w = 2) => String(n).padStart(w, "0");
    return `${p(h)}:${p(m)}:${p(s)},${p(ms % 1000, 3)}`;
  };
  return sorted
    .map((e, i) => {
      const next = sorted[i + 1];
      const to = next ? Math.min(e.to, next.from) : e.to;
      return `${i + 1}\n${stamp(e.from)} --> ${stamp(Math.max(to, e.from + 1))}\n${e.text}\n`;
    })
    .join("\n");
}
