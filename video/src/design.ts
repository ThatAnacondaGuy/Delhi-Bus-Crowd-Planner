// The design system of the film: one place for the canvas, safe area, type scale, colours, radii, shadows, spacing and motion.
// Every scene takes its sizes from here; nothing on screen picks its own font size.
import { Easing, spring } from "remotion";

export const W = 1920;
export const H = 1080;
/** Safe area: 96 px left and right, 72 px top; the bottom band (CAPTION_TOP to H) is kept for captions. */
export const SAFE = { x: 96, top: 72, bottom: 72 } as const;
export const CONTENT = { left: SAFE.x, right: W - SAFE.x, top: SAFE.top, bottom: 880, width: W - 2 * SAFE.x } as const;
export const CAPTION_TOP = 900;

/** Fixed type scale (px at 1080p). Nothing is smaller than `label`. */
export const TYPE = {
  display: 96,
  h1: 72,
  h2: 52,
  body: 40,
  caption: 36,
  label: 32,
  stat: 120,
} as const;
/** Longest comfortable line for body text (px). */
export const MEASURE = 1100;

export const C = {
  // the app's own palette
  paper: "#f6f5f1",
  paperDeep: "#ece9e1",
  ink: "#1d2327",
  blue: "#1f4e79",
  teal: "#0f766e",
  amber: "#b45309",
  red: "#8f1d1d",
  grey: "#5f6670",
  white: "#ffffff",
  tealBg: "#d9efeb",
  amberBg: "#fbebd6",
  redBg: "#f3d9d9",
  greyBg: "#e7e9eb",
  // the film's dusk ground and light-on-dark tones
  dusk: "#0b1120",
  duskMid: "#111b30",
  duskHi: "#1a2a47",
  text: "#f3f1ea",
  textDim: "#aab4c3",
  tealGlow: "#2dd4bf",
  amberGlow: "#f59e0b",
  redGlow: "#f87171",
  blueGlow: "#60a5fa",
} as const;

export const RADIUS = { sm: 12, md: 20, lg: 28, xl: 40, pill: 999 } as const;
export const SHADOW = {
  card: "0 18px 50px rgba(3,7,18,0.38), 0 4px 14px rgba(3,7,18,0.22)",
  float: "0 40px 90px rgba(3,7,18,0.55), 0 10px 24px rgba(3,7,18,0.3)",
  soft: "0 10px 30px rgba(3,7,18,0.22)",
} as const;
export const SPACE = { xs: 8, sm: 16, md: 24, lg: 40, xl: 64 } as const;

export type Level = "seats" | "standing" | "crowded" | "no_data";
export const LEVELS: Record<Level, { en: string; hi: string; dots: string; color: string; bg: string; glow: string }> = {
  seats: { en: "Usually seats", hi: "आमतौर पर सीट मिल जाती है", dots: "●○○", color: C.teal, bg: C.tealBg, glow: C.tealGlow },
  standing: { en: "Usually standing", hi: "आमतौर पर खड़े होकर जाना पड़ता है", dots: "●●○", color: C.amber, bg: C.amberBg, glow: C.amberGlow },
  crowded: { en: "Usually crowded", hi: "आमतौर पर भारी भीड़", dots: "●●●", color: C.red, bg: C.redBg, glow: C.redGlow },
  no_data: { en: "No data", hi: "जानकारी नहीं", dots: "○○○", color: C.grey, bg: C.greyBg, glow: "#cbd5e1" },
};

/* ------------------------------------------------------------------ motion */

export const outCubic = Easing.out(Easing.cubic);
/** exponential ease-out that lands exactly on 1 (counters stop on the true value) */
export const outExpo = (t: number) => (t >= 1 ? 1 : (1 - Math.pow(2, -10 * t)) / (1 - Math.pow(2, -10)));
export const inOutCubic = Easing.inOut(Easing.cubic);
export const inCubic = Easing.in(Easing.cubic);
export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
/** progress 0..1 of frame inside [from, from+dur] with an easing */
export const prog = (frame: number, from: number, dur: number, ease: (t: number) => number = (t) => t) => ease(clamp01((frame - from) / Math.max(1, dur)));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const fmt = (n: number) => Math.round(n).toLocaleString("en-US");

/** The film's two springs: `soft` for cards and moves (no overshoot), `pop` for chips and ticks (a little overshoot). */
export const springSoft = (frame: number, fps: number, at: number, durationInFrames = 22) =>
  spring({ frame: frame - at, fps, config: { damping: 200 }, durationInFrames });
export const springPop = (frame: number, fps: number, at: number) => spring({ frame: frame - at, fps, config: { damping: 13, stiffness: 170, mass: 0.7 } });
