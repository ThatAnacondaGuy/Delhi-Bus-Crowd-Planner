import { Easing, spring } from "remotion";
import { loadFont } from "@remotion/google-fonts/NotoSansDevanagari";

loadFont("normal", { weights: ["400", "700"], subsets: ["devanagari", "latin"] });

export const C = {
  paper: "#f6f5f1",
  paperDeep: "#ece9e1",
  ink: "#1d2327",
  blue: "#1f4e79",
  teal: "#0f766e",
  amber: "#b45309",
  red: "#8f1d1d",
  grey: "#5f6670",
  dusk: "#0d1117",
  duskBlue: "#14263d",
  white: "#ffffff",
  tealBg: "#d9efeb",
  amberBg: "#fbebd6",
  redBg: "#f3d9d9",
  greyBg: "#e7e9eb",
} as const;

export const FONT =
  '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Noto Sans", "Noto Sans Devanagari", "Devanagari Sangam MN", sans-serif';

export type Level = "seats" | "standing" | "crowded" | "no_data";

export const LEVELS: Record<Level, { en: string; hi: string; dots: string; color: string; bg: string }> = {
  seats: { en: "Usually seats", hi: "आमतौर पर सीट मिल जाती है", dots: "●○○", color: C.teal, bg: C.tealBg },
  standing: { en: "Usually standing", hi: "आमतौर पर खड़े होकर जाना पड़ता है", dots: "●●○", color: C.amber, bg: C.amberBg },
  crowded: { en: "Usually crowded", hi: "आमतौर पर भारी भीड़", dots: "●●●", color: C.red, bg: C.redBg },
  no_data: { en: "No data", hi: "जानकारी नहीं", dots: "○○○", color: C.grey, bg: C.greyBg },
};

/* easings: only these four */
export const outCubic = Easing.out(Easing.cubic);
export const inOutCubic = Easing.inOut(Easing.cubic);
export const linear = (t: number) => t;
export const springSoft = (frame: number, fps: number, delay = 0, durationInFrames?: number) =>
  spring({ frame: frame - delay, fps, config: { damping: 200 }, durationInFrames });

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
/** progress 0..1 of frame inside [from, from+dur] with an easing */
export const prog = (frame: number, from: number, dur: number, ease: (t: number) => number = linear) =>
  ease(clamp01((frame - from) / dur));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const fmt = (n: number) => Math.round(n).toLocaleString("en-US");
