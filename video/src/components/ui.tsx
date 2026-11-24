import React, { createContext, useContext } from "react";
import { AbsoluteFill, Audio, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, LEVELS, Level, clamp01, inOutCubic, lerp, outCubic, prog, springSoft } from "../theme";
import { useAssets } from "../assets";
import { matchSfx } from "../timing";
import { Span, captionAt } from "../captions";

/* ------------------------------------------------------------------ scene wrapper and clock */

/** Scripted frame: if the scene was trimmed shorter than its script length, time is compressed so nothing is cut off. */
export function useClock(base: number): number {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return durationInFrames < base ? (f * base) / durationInFrames : f;
}

export const Scene: React.FC<{ fadeIn?: number; fadeOut?: number; bg?: string; children: React.ReactNode }> = ({
  fadeIn = 0,
  fadeOut = 0,
  bg = C.paper,
  children,
}) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const a = fadeIn > 0 ? clamp01(f / fadeIn) : 1;
  const b = fadeOut > 0 ? clamp01((durationInFrames - f) / fadeOut) : 1;
  return (
    <AbsoluteFill style={{ opacity: Math.min(a, b), backgroundColor: bg, fontFamily: FONT, color: C.ink }}>
      {children}
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------ sound effects (only when the file exists) */

export const Sfx: React.FC<{ name: string; at: number; volume?: number; len?: number }> = ({ name, at, volume = 0.4, len }) => {
  const { sfx } = useAssets();
  const file = matchSfx(sfx, name);
  if (!file) return null;
  return (
    <Sequence from={Math.round(at)} durationInFrames={len} layout="none">
      <Audio src={staticFile(`sfx/${file}`)} volume={volume} />
    </Sequence>
  );
};

/* ------------------------------------------------------------------ chips */

export const Chip: React.FC<{
  level: Level;
  size?: number;
  hi?: boolean;
  glow?: number;
  style?: React.CSSProperties;
}> = ({ level, size = 40, hi = false, glow = 0, style }) => {
  const L = LEVELS[level];
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.32,
        padding: `${size * 0.22}px ${size * 0.5}px`,
        borderRadius: size * 0.7,
        background: L.bg,
        color: L.color,
        border: `${Math.max(3, size * 0.07)}px ${level === "no_data" ? "dashed" : "solid"} ${L.color}`,
        fontWeight: 700,
        fontSize: size,
        lineHeight: 1.15,
        whiteSpace: "nowrap",
        boxShadow: glow ? `0 0 ${size * 0.9 * glow}px ${L.color}66` : undefined,
        ...style,
      }}
    >
      <span style={{ letterSpacing: size * 0.06, fontSize: size * 0.82 }} aria-hidden>
        {L.dots}
      </span>
      <span>{hi ? L.hi : L.en}</span>
    </div>
  );
};

/* ------------------------------------------------------------------ type */

export const Words: React.FC<{
  text: string;
  start?: number;
  gap?: number;
  rise?: number;
  dur?: number;
  size: number;
  color?: string;
  weight?: number;
  align?: React.CSSProperties["textAlign"];
  style?: React.CSSProperties;
}> = ({ text, start = 0, gap = 8, rise = 24, dur = 12, size, color = C.ink, weight = 700, align = "center", style }) => {
  const f = useCurrentFrame();
  const words = text.split(" ");
  return (
    <div style={{ fontSize: size, fontWeight: weight, color, textAlign: align, lineHeight: 1.12, ...style }}>
      {words.map((w, i) => {
        const t = prog(f, start + i * gap, dur, outCubic);
        return (
          <span key={i} style={{ display: "inline-block", opacity: t, transform: `translateY(${(1 - t) * rise}px)`, marginRight: size * 0.26 }}>
            {w}
          </span>
        );
      })}
    </div>
  );
};

export const FadeIn: React.FC<{ at: number; dur?: number; rise?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({
  at,
  dur = 12,
  rise = 0,
  children,
  style,
}) => {
  const f = useCurrentFrame();
  const t = prog(f, at, dur, outCubic);
  return <div style={{ opacity: t, transform: rise ? `translateY(${(1 - t) * rise}px)` : undefined, ...style }}>{children}</div>;
};

/* ------------------------------------------------------------------ counters */

export const useCount = (frame: number, from: number, dur: number, target: number) =>
  Math.round(target * prog(frame, from, dur, outCubic));

/* ------------------------------------------------------------------ captions */

export const Caption: React.FC<{ spans: Span[]; offset?: number; bottom?: number; dark?: boolean; maxWidth?: number }> = ({
  spans,
  offset = 0,
  bottom = 54,
  dark = true,
  maxWidth = 1560,
}) => {
  const f = useCurrentFrame();
  const text = captionAt(spans, f + offset);
  if (!text) return null;
  const s = spans.find((x) => f + offset >= x.from && f + offset < x.to)!;
  const t = Math.min(prog(f + offset, s.from, 6, outCubic), clamp01((s.to - (f + offset)) / 6));
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom, display: "flex", justifyContent: "center", opacity: t }}>
      <div
        style={{
          maxWidth,
          padding: "14px 34px 16px",
          borderRadius: 18,
          background: dark ? "rgba(13,17,23,0.86)" : "rgba(246,245,241,0.92)",
          color: dark ? C.paper : C.ink,
          fontSize: 44,
          fontWeight: 700,
          lineHeight: 1.22,
          textAlign: "center",
          textWrap: "balance" as any,
          boxShadow: "0 6px 24px rgba(0,0,0,0.25)",
        }}
      >
        {text}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ camera over a "world" (page coordinates) */

export type Cam = { wx: number; wy: number; z: number };
export const lerpCam = (a: Cam, b: Cam, t: number): Cam => ({ wx: lerp(a.wx, b.wx, t), wy: lerp(a.wy, b.wy, t), z: lerp(a.z, b.z, t) });

/** A layer whose children are in page coordinates; the camera puts point (wx, wy) at the screen anchor (ax, ay). */
export const World: React.FC<{ cam: Cam; ax: number; ay: number; children: React.ReactNode; opacity?: number }> = ({ cam, ax, ay, children, opacity = 1 }) => (
  <div
    style={{
      position: "absolute",
      left: 0,
      top: 0,
      transformOrigin: "0 0",
      transform: `translate(${ax - cam.wx * cam.z}px, ${ay - cam.wy * cam.z}px) scale(${cam.z})`,
      opacity,
    }}
  >
    {children}
  </div>
);

export const Shot: React.FC<{ src: string; w: number; h: number; x?: number; y?: number; opacity?: number }> = ({ src, w, h, x = 0, y = 0, opacity = 1 }) => (
  <Img src={src} style={{ position: "absolute", left: x, top: y, width: w, height: h, opacity, display: "block" }} />
);

/* ------------------------------------------------------------------ devices */

/** A plain phone: rounded dark bezel, no brand. Children live in 390x844 css-pixel screen coordinates. */
export const Phone: React.FC<{ scale: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ scale, children, style }) => {
  const b = 12;
  return (
    <div
      style={{
        width: (390 + 2 * b) * scale,
        height: (844 + 2 * b) * scale,
        borderRadius: 58 * scale,
        background: "linear-gradient(145deg,#1b2229,#0b0f13)",
        padding: b * scale,
        boxSizing: "border-box",
        boxShadow: "0 30px 70px rgba(13,17,23,0.28), 0 6px 18px rgba(13,17,23,0.2)",
        ...style,
      }}
    >
      <div style={{ width: 390 * scale, height: 844 * scale, borderRadius: 46 * scale, overflow: "hidden", position: "relative", background: C.paper }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: 390, height: 844, transform: `scale(${scale})`, transformOrigin: "0 0", overflow: "hidden" }}>
          {children}
        </div>
      </div>
    </div>
  );
};

/** A plain laptop: dark lid, thin base. Children live in 1440x900 css-pixel screen coordinates. */
export const Laptop: React.FC<{ scale: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ scale, children, style }) => {
  const b = 18;
  return (
    <div style={{ width: (1440 + 2 * b) * scale, ...style }}>
      <div
        style={{
          width: (1440 + 2 * b) * scale,
          height: (900 + 2 * b) * scale,
          borderRadius: 26 * scale,
          background: "linear-gradient(160deg,#222a31,#0d1115)",
          padding: b * scale,
          boxSizing: "border-box",
          boxShadow: "0 30px 70px rgba(13,17,23,0.3)",
        }}
      >
        <div style={{ width: 1440 * scale, height: 900 * scale, borderRadius: 8 * scale, overflow: "hidden", position: "relative", background: C.paper }}>
          <div style={{ position: "absolute", left: 0, top: 0, width: 1440, height: 900, transform: `scale(${scale})`, transformOrigin: "0 0", overflow: "hidden" }}>{children}</div>
        </div>
      </div>
      <div
        style={{
          width: (1440 + 2 * b) * scale * 1.06,
          marginLeft: -(1440 + 2 * b) * scale * 0.03,
          height: 20 * scale,
          borderRadius: `0 0 ${24 * scale}px ${24 * scale}px`,
          background: "linear-gradient(#cfd3d7,#9aa1a8)",
        }}
      />
    </div>
  );
};

/* ------------------------------------------------------------------ pointer effects (inside a World, page coordinates) */

export const TapRing: React.FC<{ x: number; y: number; at: number; size?: number; color?: string }> = ({ x, y, at, size = 56, color = C.blue }) => {
  const f = useCurrentFrame();
  const t = (f - at) / 12;
  if (t < 0 || t > 1) return null;
  const s = lerp(0.6, 1.4, outCubic(t));
  return (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        borderRadius: "50%",
        border: `3px solid ${color}`,
        background: `${color}22`,
        transform: `scale(${s})`,
        opacity: 1 - t,
        pointerEvents: "none",
      }}
    />
  );
};

/** A soft cursor that glides between points. pts: [frame, x, y]. */
export const Cursor: React.FC<{ pts: [number, number, number][]; size?: number; color?: string }> = ({ pts, size = 30, color = C.ink }) => {
  const f = useCurrentFrame();
  if (f < pts[0][0]) return null;
  const xs = pts.map((p) => p[0]);
  const x = interpolate(f, xs, pts.map((p) => p[1]), { easing: inOutCubic, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(f, xs, pts.map((p) => p[2]), { easing: inOutCubic, extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const out = clamp01((xs[xs.length - 1] + 24 - f) / 12);
  return (
    <svg width={size} height={size * 1.4} viewBox="0 0 20 28" style={{ position: "absolute", left: x, top: y, opacity: out, filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.35))" }}>
      <path d="M2 2 L2 22 L7 17.5 L10.5 25.5 L13.8 24 L10.4 16.3 L17 16 Z" fill={color} stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
};

/** Spotlight on a rectangle (page coordinates): everything else is dimmed. */
export const Spot: React.FC<{ r: { x: number; y: number; w: number; h: number }; amount: number; pad?: number; color?: string; radius?: number }> = ({
  r,
  amount,
  pad = 6,
  color = C.teal,
  radius = 16,
}) => (
  <div
    style={{
      position: "absolute",
      left: r.x - pad,
      top: r.y - pad,
      width: r.w + 2 * pad,
      height: r.h + 2 * pad,
      borderRadius: radius,
      boxShadow: `0 0 0 4000px rgba(13,17,23,${0.34 * amount})`,
      outline: `${3}px solid ${color}`,
      outlineOffset: 0,
      opacity: amount > 0 ? 1 : 0,
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

export { C, springSoft };
