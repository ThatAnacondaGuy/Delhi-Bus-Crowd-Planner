// The film's building blocks: timeline hooks, backgrounds, fitted type, captions, chips, counters, devices, pointer effects.
import React, { createContext, useContext, useMemo } from "react";
import { AbsoluteFill, Audio, Img, Sequence, interpolate, random, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { fitText, measureText } from "@remotion/layout-utils";
import { C, CAPTION_TOP, H, LEVELS, Level, RADIUS, SAFE, SHADOW, TYPE, W, clamp01, fmt, inOutCubic, lerp, outCubic, outExpo, prog, springPop, springSoft } from "../design";
import { FONT } from "../fonts";
import { useAssets } from "../assets";
import { FrameCue, SceneTimeline, captionLines, captionSpans, matchSfx } from "../timing";
import { fitSize } from "../sync";

/* ------------------------------------------------------------------ timeline of the current scene */

export const TimelineCtx = createContext<SceneTimeline | null>(null);

/** The cues of the current scene: beat(i) = first frame of phrase i; beat(i, k) = k of the way through it. */
export function useBeats() {
  const tl = useContext(TimelineCtx);
  if (!tl) throw new Error("useBeats outside a scene");
  const cue = (i: number): FrameCue => tl.cues[Math.max(0, Math.min(tl.cues.length - 1, i))];
  const beat = (i: number, k = 0) => {
    const c = cue(i);
    return Math.round(c.from + (c.to - c.from) * k);
  };
  const end = (i: number) => cue(i).to;
  return { tl, cue, beat, end };
}

/* ------------------------------------------------------------------ measuring */

type Fit = { size: number; lines: string[] };

/** Width of a string in the film's font (after the fonts are loaded: see FontGate). */
export const textWidth = (text: string, size: number, weight: number | string = 700) =>
  measureText({ text, fontFamily: FONT, fontSize: size, fontWeight: String(weight), validateFontIsLoaded: /[a-z]/i.test(text) }).width;

/** One line that fits `width`: the scale size, or smaller when the measured text is wider. */
export const fitLine = (text: string, size: number, width: number, weight: number | string = 700) => {
  const w = textWidth(text, size, weight);
  if (w <= width) return size;
  const f = fitText({ text, withinWidth: width, fontFamily: FONT, fontWeight: String(weight) }).fontSize;
  const out = Math.max(TYPE.label, Math.min(size, Math.floor(f * 0.98), fitSize(w, size, width, TYPE.label)));
  if (textWidth(text, out, weight) > width + 0.5 && typeof console !== "undefined") console.warn(`[fit] "${text}" is wider than ${width}px even at ${out}px`);
  return out;
};

/** Greedy word wrap at a size, measured. */
export function wrapMeasured(text: string, size: number, width: number, weight: number | string = 700): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const t = cur ? `${cur} ${w}` : w;
    if (cur && textWidth(t, size, weight) > width) {
      lines.push(cur);
      cur = w;
    } else cur = t;
  }
  if (cur) lines.push(cur);
  return lines;
}

/** Fit text into a box of `width` on at most `maxLines` lines, starting from the scale size and stepping down. */
export function fitBlock(text: string, size: number, width: number, maxLines = 2, weight: number | string = 700): Fit {
  for (let s = size; s >= TYPE.label; s -= 2) {
    const lines = wrapMeasured(text, s, width, weight);
    if (lines.length <= maxLines && lines.every((l) => textWidth(l, s, weight) <= width)) return { size: s, lines };
  }
  const lines = wrapMeasured(text, TYPE.label, width, weight);
  if (typeof console !== "undefined") console.warn(`[fit] "${text}" needs ${lines.length} lines at ${TYPE.label}px in ${width}px`);
  return { size: TYPE.label, lines };
}

/** A block of text fitted into its box (never overflows; never larger than its scale size). */
export const FitText: React.FC<{
  text: string;
  size: number;
  width: number;
  maxLines?: number;
  weight?: number;
  color?: string;
  align?: "left" | "center" | "right";
  lineHeight?: number;
  style?: React.CSSProperties;
}> = ({ text, size, width, maxLines = 1, weight = 700, color = C.text, align = "left", lineHeight = 1.15, style }) => {
  const fit = useMemo(() => (maxLines === 1 ? { size: fitLine(text, size, width, weight), lines: [text] } : fitBlock(text, size, width, maxLines, weight)), [text, size, width, maxLines, weight]);
  return (
    <div style={{ width, fontSize: fit.size, fontWeight: weight, color, textAlign: align, lineHeight, whiteSpace: "nowrap", ...style }}>
      {fit.lines.map((l, i) => (
        <div key={i}>{l}</div>
      ))}
    </div>
  );
};

/** Kinetic type: the fitted lines, word by word, each rising with the soft spring and un-blurring. */
export const Kinetic: React.FC<{
  text: string;
  at: number;
  size: number;
  width: number;
  maxLines?: number;
  stagger?: number;
  weight?: number;
  color?: string;
  align?: "left" | "center";
  accent?: Record<string, string>;
  out?: number;
  style?: React.CSSProperties;
}> = ({ text, at, size, width, maxLines = 2, stagger = 3, weight = 800, color = C.text, align = "left", accent = {}, out, style }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fit = useMemo(() => fitBlock(text, size, width, maxLines, weight), [text, size, width, maxLines, weight]);
  const fade = out == null ? 1 : 1 - prog(f, out, 10, inOutCubic);
  let k = 0;
  return (
    <div style={{ width, fontSize: fit.size, fontWeight: weight, color, textAlign: align, lineHeight: 1.08, letterSpacing: fit.size >= 72 ? -1.5 : -0.5, opacity: fade, ...style }}>
      {fit.lines.map((line, li) => (
        <div key={li} style={{ whiteSpace: "nowrap" }}>
          {line.split(" ").map((w, wi) => {
            const t = springSoft(f, fps, at + k++ * stagger, 20);
            const key = w.replace(/[^\p{L}\p{N}]/gu, "").toLowerCase();
            return (
              <span
                key={wi}
                style={{
                  display: "inline-block",
                  opacity: t,
                  transform: `translateY(${(1 - t) * size * 0.45}px)`,
                  filter: t < 0.98 ? `blur(${(1 - t) * 8}px)` : undefined,
                  color: accent[key] ?? undefined,
                  marginRight: wi < line.split(" ").length - 1 ? "0.26em" : 0,
                }}
              >
                {w}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ grounds */

/** Soft animated gradient on dusk ink, with drifting colour blooms, a vignette and fine film grain. */
export const Backdrop: React.FC<{ tint?: [string, string, string]; light?: boolean; drift?: number }> = ({
  tint = [C.blue, C.teal, "#3b2a5c"],
  light = false,
  drift = 1,
}) => {
  const f = useCurrentFrame();
  const t = (f / 30) * drift;
  const blob = (i: number, color: string, size: number, x0: number, y0: number, ax: number, ay: number, op: number) => (
    <div
      key={i}
      style={{
        position: "absolute",
        left: x0 + Math.sin(t * 0.21 + i * 1.7) * ax - size / 2,
        top: y0 + Math.cos(t * 0.17 + i * 2.3) * ay - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        background: `radial-gradient(circle, ${color} 0%, transparent 65%)`,
        opacity: op,
      }}
    />
  );
  return (
    <AbsoluteFill style={{ background: light ? `linear-gradient(160deg, ${C.paper}, ${C.paperDeep})` : `linear-gradient(165deg, ${C.duskMid} 0%, ${C.dusk} 55%, #070b15 100%)`, overflow: "hidden" }}>
      {blob(0, tint[0], 1400, 420, 260, 140, 90, light ? 0.18 : 0.55)}
      {blob(1, tint[1], 1100, 1560, 820, 160, 80, light ? 0.14 : 0.32)}
      {blob(2, tint[2], 1200, 1500, 120, 120, 110, light ? 0.12 : 0.38)}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 45%, transparent 55%, rgba(2,4,10,0.55) 100%)", opacity: light ? 0.15 : 1 }} />
      <Grain />
    </AbsoluteFill>
  );
};

/** Fine animated grain (SVG turbulence, a new seed every 2 frames). */
export const Grain: React.FC<{ opacity?: number }> = ({ opacity = 0.07 }) => {
  const f = useCurrentFrame();
  const seed = Math.floor(f / 2) % 97;
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0, opacity, mixBlendMode: "overlay", pointerEvents: "none" }}>
      <filter id={`g${seed}`}>
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed={seed} stitchTiles="stitch" />
        <feColorMatrix type="saturate" values="0" />
      </filter>
      <rect width="100%" height="100%" filter={`url(#g${seed})`} />
    </svg>
  );
};

/** A short chapter label, top left in the safe area, for the first seconds of a scene. */
export const Chapter: React.FC<{ n: string; text: string; hold?: number; x?: number }> = ({ n, text, hold = 110, x = SAFE.x }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = springSoft(f, fps, 4, 18);
  const o = t * (1 - prog(f, hold, 14, inOutCubic));
  if (o <= 0) return null;
  return (
    <div style={{ position: "absolute", left: x, top: SAFE.top - 16, display: "flex", alignItems: "center", gap: 14, opacity: o, transform: `translateX(${(1 - t) * -24}px)` }}>
      <div style={{ fontSize: TYPE.label, fontWeight: 800, color: C.tealGlow, fontVariantNumeric: "tabular-nums" }}>{n}</div>
      <div style={{ width: 36 * t, height: 3, background: C.tealGlow, borderRadius: 2 }} />
      <div style={{ fontSize: TYPE.label, fontWeight: 600, color: C.textDim, letterSpacing: 0.5 }}>{text}</div>
    </div>
  );
};

/* ------------------------------------------------------------------ captions */

/**
 * The burned-in caption: phrase by phrase on the speech, at most two lines of at most 42 characters, in the bottom band,
 * its box sized to the measured text. `region` keeps it under a column (so it never covers the focal element).
 */
export const Captions: React.FC<{ region?: [number, number]; dark?: boolean }> = ({ region = [SAFE.x, W - SAFE.x], dark = true }) => {
  const f = useCurrentFrame();
  const { tl } = useBeats();
  const spans = useMemo(() => captionSpans(tl.cues, tl.duration), [tl]);
  const s = spans.find((x) => f >= x.from && f < x.to);
  if (!s) return null;
  const lines = captionLines(s.text);
  const maxW = region[1] - region[0] - 2 * 36;
  const size = Math.min(...lines.map((l) => fitLine(l, TYPE.caption, maxW, 600)));
  const boxW = Math.ceil(Math.max(...lines.map((l) => textWidth(l, size, 600)))) + 2 * 32;
  const t = Math.min(prog(f, s.from, 5, outCubic), clamp01((s.to - f) / 5));
  const lineH = Math.round(size * 1.3);
  const boxH = lines.length * lineH + 2 * 14;
  const cx = (region[0] + region[1]) / 2;
  return (
    <div
      style={{
        position: "absolute",
        left: cx - boxW / 2,
        top: H - SAFE.bottom + 18 - boxH,
        width: boxW,
        height: boxH,
        padding: "14px 32px",
        boxSizing: "border-box",
        borderRadius: RADIUS.md,
        background: dark ? "rgba(6,10,20,0.78)" : "rgba(255,255,255,0.9)",
        border: dark ? "1px solid rgba(255,255,255,0.10)" : "1px solid rgba(13,17,23,0.08)",
        backdropFilter: "blur(10px)",
        color: dark ? C.text : C.ink,
        fontSize: size,
        fontWeight: 600,
        lineHeight: `${lineH}px`,
        textAlign: "center",
        whiteSpace: "nowrap",
        opacity: t,
        transform: `translateY(${(1 - t) * 8}px)`,
        boxShadow: SHADOW.soft,
      }}
    >
      {lines.map((l, i) => (
        <div key={i}>{l}</div>
      ))}
    </div>
  );
};
void CAPTION_TOP;

/* ------------------------------------------------------------------ sound effects (only when the file exists) */

export const Sfx: React.FC<{ name: string; at: number; volume?: number; len?: number; fade?: number }> = ({ name, at, volume = 0.4, len, fade = 0 }) => {
  const { sfx, sfxTrim } = useAssets();
  const file = matchSfx(sfx, name);
  if (!file || !Number.isFinite(at)) return null;
  const trim = sfxTrim[file] ?? 1;
  const vol = (fr: number) => {
    if (!fade) return volume * trim;
    const fin = Math.min(1, fr / fade);
    const fout = len ? Math.min(1, Math.max(0, (len - fr) / fade)) : 1;
    return volume * trim * Math.min(fin, fout);
  };
  return (
    <Sequence from={Math.max(0, Math.round(at))} durationInFrames={len} layout="none">
      <Audio src={staticFile(`sfx/${file}`)} volume={vol} />
    </Sequence>
  );
};

/* ------------------------------------------------------------------ chips */

/** The app's level chip: dots + word + colour, never colour alone. `build` (0..1 each) assembles it word, dots, colour. */
export const Chip: React.FC<{
  level: Level;
  size?: number;
  hi?: boolean;
  glow?: number;
  build?: { word: number; dots: number; colour: number };
  style?: React.CSSProperties;
}> = ({ level, size = TYPE.body, hi = false, glow = 0, build, style }) => {
  const L = LEVELS[level];
  const b = build ?? { word: 1, dots: 1, colour: 1 };
  const bg = `color-mix(in srgb, ${L.bg} ${Math.round(b.colour * 100)}%, #ffffff)`;
  const fg = `color-mix(in srgb, ${L.color} ${Math.round(b.colour * 100)}%, ${C.ink})`;
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.34,
        padding: `${size * 0.24}px ${size * 0.55}px`,
        borderRadius: RADIUS.pill,
        background: bg,
        color: fg,
        border: `${Math.max(3, size * 0.07)}px ${level === "no_data" ? "dashed" : "solid"} ${fg}`,
        fontWeight: 700,
        fontSize: size,
        lineHeight: 1.12,
        whiteSpace: "nowrap",
        boxShadow: glow ? `0 0 ${size * 1.2 * glow}px ${L.glow}88, 0 8px 22px rgba(3,7,18,0.25)` : "0 8px 22px rgba(3,7,18,0.22)",
        ...style,
      }}
    >
      <span style={{ display: "inline-flex", gap: size * 0.1 }} aria-hidden>
        {L.dots.split("").map((d, i) => {
          const t = clamp01(b.dots * 3 - i);
          return (
            <span key={i} style={{ fontSize: size * 0.8, display: "inline-block", transform: `scale(${0.2 + 0.8 * t})`, opacity: t }}>
              {d}
            </span>
          );
        })}
      </span>
      <span style={{ opacity: b.word }}>{hi ? L.hi : L.en}</span>
    </div>
  );
};

/** A chip that pops in (spring with a little overshoot) at a frame. */
export const PopChip: React.FC<{ level: Level; at: number; size?: number; hi?: boolean; glow?: boolean; style?: React.CSSProperties }> = ({ level, at, size, hi, glow = true, style }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = f < at ? 0 : springPop(f, fps, at);
  const g = glow && f >= at ? Math.max(0, 1 - (f - at) / 40) : 0;
  return (
    <div style={{ display: "inline-block", transform: `scale(${0.4 + 0.6 * t})`, transformOrigin: "left center", opacity: clamp01(t * 2), ...style }}>
      <Chip level={level} size={size} hi={hi} glow={g} />
    </div>
  );
};

/* ------------------------------------------------------------------ numbers */

export const Counter: React.FC<{ value: number; at: number; dur?: number; size?: number; color?: string; suffix?: string; decimals?: number; style?: React.CSSProperties }> = ({
  value,
  at,
  dur = 40,
  size = TYPE.stat,
  color = C.text,
  suffix = "",
  decimals = 0,
  style,
}) => {
  const f = useCurrentFrame();
  const v = value * prog(f, at, dur, outExpo);
  const shown = decimals ? v.toFixed(decimals) : fmt(v);
  return <div style={{ fontSize: size, fontWeight: 800, color, lineHeight: 1, letterSpacing: -2, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", ...style }}>{shown + suffix}</div>;
};

/* ------------------------------------------------------------------ camera over a page (capture coordinates) */

export type Cam = { wx: number; wy: number; z: number };

export function camAt(u: number, keys: [number, Cam][]): Cam {
  if (u <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    if (u <= keys[i][0]) {
      const [t0, c0] = keys[i - 1];
      const [t1, c1] = keys[i];
      const t = inOutCubic(clamp01((u - t0) / Math.max(1, t1 - t0)));
      return { wx: lerp(c0.wx, c1.wx, t), wy: lerp(c0.wy, c1.wy, t), z: lerp(c0.z, c1.z, t) };
    }
  }
  return keys[keys.length - 1][1];
}

/** Keys must rise in time; a camera move keyed to a beat can be pushed later by an earlier long move: keep them ordered. */
export const ordered = (keys: [number, Cam][]): [number, Cam][] => {
  const out: [number, Cam][] = [];
  for (const [t, c] of keys) out.push([out.length ? Math.max(t, out[out.length - 1][0] + 1) : t, c]);
  return out;
};

export const World: React.FC<{ cam: Cam; ax: number; ay: number; children: React.ReactNode; opacity?: number }> = ({ cam, ax, ay, children, opacity = 1 }) => (
  <div style={{ position: "absolute", left: 0, top: 0, transformOrigin: "0 0", transform: `translate(${ax - cam.wx * cam.z}px, ${ay - cam.wy * cam.z}px) scale(${cam.z})`, opacity }}>{children}</div>
);

export const Shot: React.FC<{ src: string; w: number; h: number; x?: number; y?: number; opacity?: number }> = ({ src, w, h, x = 0, y = 0, opacity = 1 }) => (
  <Img src={src} style={{ position: "absolute", left: x, top: y, width: w, height: h, opacity, display: "block" }} />
);

/* ------------------------------------------------------------------ devices */

/** A plain phone with depth: dark bezel, glass sheen, soft floor shadow. Children live in 390x844 css-pixel coordinates. */
export const Phone: React.FC<{ scale: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ scale, children, style }) => {
  const b = 13;
  return (
    <div style={{ position: "relative", width: (390 + 2 * b) * scale, height: (844 + 2 * b) * scale, ...style }}>
      <div style={{ position: "absolute", left: "8%", right: "8%", bottom: -36 * scale, height: 60 * scale, borderRadius: "50%", background: "rgba(0,0,0,0.55)", filter: `blur(${26 * scale}px)` }} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: 60 * scale,
          background: "linear-gradient(145deg,#2a333d,#0b0f14 45%,#1a2129)",
          padding: b * scale,
          boxSizing: "border-box",
          boxShadow: `${SHADOW.float}, inset 0 0 0 ${2 * scale}px rgba(255,255,255,0.08)`,
        }}
      >
        <div style={{ width: 390 * scale, height: 844 * scale, borderRadius: 47 * scale, overflow: "hidden", position: "relative", background: C.paper }}>
          <div style={{ position: "absolute", left: 0, top: 0, width: 390, height: 844, transform: `scale(${scale})`, transformOrigin: "0 0", overflow: "hidden" }}>{children}</div>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(115deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0) 32%)", pointerEvents: "none" }} />
        </div>
      </div>
    </div>
  );
};

/** A plain laptop with depth. Children live in 1440x900 css-pixel coordinates. */
export const Laptop: React.FC<{ scale: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ scale, children, style }) => {
  const b = 16;
  const w = (1440 + 2 * b) * scale;
  return (
    <div style={{ width: w, position: "relative", ...style }}>
      <div style={{ width: w, height: (900 + 2 * b) * scale, borderRadius: 24 * scale, background: "linear-gradient(160deg,#2a333d,#0c1015)", padding: b * scale, boxSizing: "border-box", boxShadow: `${SHADOW.float}, inset 0 0 0 ${2 * scale}px rgba(255,255,255,0.07)` }}>
        <div style={{ width: 1440 * scale, height: 900 * scale, borderRadius: 6 * scale, overflow: "hidden", position: "relative", background: C.paper }}>
          <div style={{ position: "absolute", left: 0, top: 0, width: 1440, height: 900, transform: `scale(${scale})`, transformOrigin: "0 0", overflow: "hidden" }}>{children}</div>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(120deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0) 30%)", pointerEvents: "none" }} />
        </div>
      </div>
      <div style={{ width: w * 1.08, marginLeft: -w * 0.04, height: 22 * scale, borderRadius: `0 0 ${26 * scale}px ${26 * scale}px`, background: "linear-gradient(#d5d9de,#8d959e)", boxShadow: "0 18px 40px rgba(0,0,0,0.5)" }} />
    </div>
  );
};

/* ------------------------------------------------------------------ pointer effects (inside a World, page coordinates) */

/** A tap: a filled press, then two rings rippling out. */
export const TapRipple: React.FC<{ x: number; y: number; at: number; color?: string; size?: number }> = ({ x, y, at, color = C.blue, size = 46 }) => {
  const f = useCurrentFrame();
  const t = (f - at) / 20;
  if (t < -0.2 || t > 1) return null;
  const press = clamp01(1 - Math.abs(t * 5 - 0.5));
  const ring = (d: number) => {
    const u = clamp01((t - d) / (1 - d));
    return (
      <div
        style={{
          position: "absolute",
          left: x - size,
          top: y - size,
          width: size * 2,
          height: size * 2,
          borderRadius: "50%",
          border: `3px solid ${color}`,
          transform: `scale(${0.3 + 0.9 * outCubic(u)})`,
          opacity: u > 0 && u < 1 ? 1 - u : 0,
        }}
      />
    );
  };
  return (
    <>
      <div style={{ position: "absolute", left: x - size / 2, top: y - size / 2, width: size, height: size, borderRadius: "50%", background: color, opacity: 0.3 * press }} />
      {ring(0)}
      {ring(0.25)}
    </>
  );
};

/** A soft round cursor gliding between points. pts: [frame, x, y]. Fades out after the last point. */
export const SoftCursor: React.FC<{ pts: [number, number, number][]; size?: number; hideAfter?: number }> = ({ pts, size = 34, hideAfter = 30 }) => {
  const f = useCurrentFrame();
  const first = pts[0][0];
  if (f < first - 8) return null;
  const xs = pts.map((p) => p[0]);
  const x = interpolate(f, xs, pts.map((p) => p[1]), { easing: inOutCubic, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(f, xs, pts.map((p) => p[2]), { easing: inOutCubic, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const o = prog(f, first - 8, 8) * (1 - prog(f, xs[xs.length - 1] + hideAfter, 10));
  const pressed = pts.some((p) => f >= p[0] && f < p[0] + 6) && f > first;
  return (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        background: "rgba(255,255,255,0.55)",
        border: "3px solid rgba(17,24,39,0.85)",
        boxShadow: "0 4px 14px rgba(0,0,0,0.35)",
        transform: `scale(${pressed ? 0.8 : 1})`,
        opacity: o,
      }}
    />
  );
};

/** Spotlight on a rectangle (page coordinates): the rest is dimmed and a coloured ring glows. */
export const Spot: React.FC<{ r: { x: number; y: number; w: number; h: number }; amount: number; pad?: number; color?: string; radius?: number }> = ({
  r,
  amount,
  pad = 6,
  color = C.teal,
  radius = 16,
}) =>
  amount <= 0 ? null : (
    <div
      style={{
        position: "absolute",
        left: r.x - pad,
        top: r.y - pad,
        width: r.w + 2 * pad,
        height: r.h + 2 * pad,
        borderRadius: radius,
        boxShadow: `0 0 0 4000px rgba(8,12,22,${0.42 * amount}), 0 0 ${18 * amount}px ${color}`,
        outline: `3px solid ${color}`,
        opacity: Math.min(1, amount * 1.5),
        pointerEvents: "none",
      }}
    />
  );

/** An outline that draws itself around a rectangle. */
export const DrawBox: React.FC<{ r: { x: number; y: number; w: number; h: number }; t: number; color?: string; pad?: number; width?: number; radius?: number }> = ({
  r,
  t,
  color = C.teal,
  pad = 6,
  width = 4,
  radius = 14,
}) => {
  if (t <= 0) return null;
  const w = r.w + 2 * pad;
  const h = r.h + 2 * pad;
  const len = 2 * (w + h);
  return (
    <svg width={w + 2 * width} height={h + 2 * width} style={{ position: "absolute", left: r.x - pad - width, top: r.y - pad - width, overflow: "visible" }}>
      <rect x={width} y={width} width={w} height={h} rx={radius} fill="none" stroke={color} strokeWidth={width} strokeDasharray={len} strokeDashoffset={len * (1 - t)} />
    </svg>
  );
};

/* ------------------------------------------------------------------ a stylised city map: roads, a glowing corridor, route lines */

const ROADS: string[] = (() => {
  const out: string[] = [];
  for (let i = 0; i < 14; i++) {
    const y = 60 + i * 72 + random(`ry${i}`) * 30;
    out.push(`M -40 ${y} C 500 ${y + (random(`a${i}`) - 0.5) * 160}, 1300 ${y + (random(`b${i}`) - 0.5) * 160}, 1960 ${y + (random(`c${i}`) - 0.5) * 80}`);
  }
  for (let i = 0; i < 16; i++) {
    const x = 40 + i * 122 + random(`rx${i}`) * 40;
    out.push(`M ${x} -40 C ${x + (random(`d${i}`) - 0.5) * 200} 380, ${x + (random(`e${i}`) - 0.5) * 200} 700, ${x + (random(`f${i}`) - 0.5) * 120} 1120`);
  }
  out.push("M 960 540 m -430 0 a 430 330 0 1 0 860 0 a 430 330 0 1 0 -860 0"); // ring road
  return out;
})();
export const CORRIDOR = "M 180 900 C 520 760, 700 640, 960 560 S 1460 380, 1760 200";
export const ROUTE_B = "M 240 220 C 560 330, 820 420, 960 560 S 1300 860, 1700 940";

export const StylisedMap: React.FC<{ draw: number; glow: number; opacity?: number; pulseAt?: number }> = ({ draw, glow, opacity = 1, pulseAt = 0 }) => {
  const f = useCurrentFrame();
  const dash = (f - pulseAt) * 4;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ position: "absolute", inset: 0, opacity }}>
      <defs>
        <filter id="cglow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="12" />
        </filter>
      </defs>
      {ROADS.map((d, i) => (
        <path key={i} d={d} fill="none" stroke="rgba(148,163,184,0.16)" strokeWidth={i === ROADS.length - 1 ? 5 : 2.5} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - clamp01(draw * 1.4 - i * 0.012)} />
      ))}
      <path d={ROUTE_B} fill="none" stroke={C.blueGlow} strokeOpacity={0.5} strokeWidth={5} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - clamp01(draw * 1.2 - 0.2)} strokeLinecap="round" />
      <path d={CORRIDOR} fill="none" stroke={C.amberGlow} strokeWidth={26} opacity={0.55 * glow} filter="url(#cglow)" />
      <path d={CORRIDOR} fill="none" stroke={C.amberGlow} strokeWidth={8} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - clamp01(draw * 1.2 - 0.1)} strokeLinecap="round" />
      <path d={CORRIDOR} fill="none" stroke="#fff7e6" strokeWidth={3} strokeDasharray="14 26" strokeDashoffset={-dash} opacity={0.75 * glow} strokeLinecap="round" />
    </svg>
  );
};

/* ------------------------------------------------------------------ scene shell */

export const SceneShell: React.FC<{ children: React.ReactNode; fadeIn?: number; fadeOut?: number }> = ({ children, fadeIn = 0, fadeOut = 0 }) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const a = fadeIn > 0 ? clamp01(f / fadeIn) : 1;
  const b = fadeOut > 0 ? clamp01((durationInFrames - f) / fadeOut) : 1;
  return <AbsoluteFill style={{ opacity: Math.min(a, b), fontFamily: FONT, color: C.text, overflow: "hidden" }}>{children}</AbsoluteFill>;
};

export { C, TYPE, springSoft, springPop };
