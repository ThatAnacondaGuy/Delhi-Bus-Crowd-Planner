import { staticFile } from "remotion";
import meta from "./captures.generated.json";

export type R = { x: number; y: number; w: number; h: number };
export type CardRects = {
  roles: string;
  card: R;
  chip: R;
  why: R;
  map: R;
  callout: R | null;
  evidence: R | null;
  tradeoff: R | null;
  bar: R | null;
  level: string;
};
type Meta = { w: number; h: number; rects: any; query?: any; label?: string };
const M = meta as unknown as Record<string, Meta>;

export const capMeta = (name: string): Meta => {
  const m = M[name];
  if (!m) throw new Error(`capture ${name} is missing: run "npm run capture" (see README)`);
  return m;
};
export const capUrl = (name: string) => staticFile(`captures/${name}.png`);
export const cards = (name: string): CardRects[] => capMeta(name).rects.cards as CardRects[];
export const cx = (r: R) => r.x + r.w / 2;
export const cy = (r: R) => r.y + r.h / 2;
