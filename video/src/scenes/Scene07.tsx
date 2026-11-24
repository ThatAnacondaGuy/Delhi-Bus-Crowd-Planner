// Scene 7: the evidence. The checklist written first (phrase 0); every row arrives (1); peaks and weekends tick (2);
// bus-km and the rest tick (3); the load factor flips to a Miss (4); the number line (5); the corridor row (6) is struck
// through as chance alone gives ten of ten (7); "No field count was possible." (8) alone on the screen.
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, RADIUS, SHADOW, TYPE, W, clamp01, fmt, inOutCubic, lerp, outCubic, prog, springPop, springSoft } from "../design";
import { Backdrop, Captions, Chapter, FitText, Kinetic, SceneShell, Sfx, textWidth, useBeats } from "../components/kit";

const CARD = { x: 210, y: 96, w: 1500, h: 784 };
const PADX = 48;
const INNER = CARD.w - 2 * PADX;

const Tick: React.FC<{ t: number; kind: "hit" | "miss"; size: number }> = ({ t, kind, size }) => {
  const col = kind === "hit" ? C.teal : C.red;
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" style={{ flex: "none" }}>
      <circle cx="20" cy="20" r="17" fill={t > 0.05 ? col : "none"} stroke={t > 0.05 ? col : "#b7bcc1"} strokeWidth="3" />
      {kind === "hit" ? (
        <path d="M11 21 L18 28 L30 13" fill="none" stroke="#fff" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={40} strokeDashoffset={40 * (1 - t)} />
      ) : (
        <>
          <path d="M13 13 L27 27" stroke="#fff" strokeWidth="4.5" strokeLinecap="round" strokeDasharray={20} strokeDashoffset={20 * (1 - Math.min(1, t * 2))} />
          <path d="M27 13 L13 27" stroke="#fff" strokeWidth="4.5" strokeLinecap="round" strokeDasharray={20} strokeDashoffset={20 * (1 - Math.max(0, t * 2 - 1))} />
        </>
      )}
    </svg>
  );
};

/** One checklist row: appears on `appear`, fills and ticks on `fill`. */
const Row: React.FC<{ text: string; appear: number; fill: number; y: number; h: number; size: number; dim?: number; kind?: "hit" | "miss"; tag?: string }> = ({ text, appear, fill, y, h, size, dim = 1, kind = "hit", tag }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = springSoft(f, fps, appear, 16);
  const t = prog(f, fill, 12, outCubic);
  const col = kind === "hit" ? C.teal : C.red;
  const bg = kind === "hit" ? C.tealBg : C.redBg;
  const tagW = tag ? 120 : 0;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: y,
        width: INNER,
        height: h,
        display: "flex",
        alignItems: "center",
        gap: 18,
        padding: "0 24px",
        boxSizing: "border-box",
        borderRadius: h / 2,
        border: `3px solid ${t > 0.05 ? col : "#c9ccd1"}`,
        background: `color-mix(in srgb, ${bg} ${Math.round(t * 100)}%, #ffffff)`,
        opacity: a * dim,
        transform: `translateY(${(1 - a) * 16}px)`,
      }}
    >
      <Tick t={t} kind={kind} size={h * 0.62} />
      <FitText text={text} size={size} width={INNER - 48 - h * 0.62 - 18 - tagW - 18} weight={600} color={C.ink} />
      {tag ? <div style={{ width: tagW, textAlign: "right", fontSize: TYPE.label, fontWeight: 800, color: col, opacity: t }}>{tag}</div> : null}
    </div>
  );
};

export const Scene07: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, durationInFrames: D } = useVideoConfig();
  const { beat, cue } = useBeats();
  const b = [0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => beat(i));

  const card = springSoft(f, fps, b[0] - 8, 26);
  const lock = prog(f, b[0] + 30, 8, outCubic);
  // the hit rows: full size, then compact and dim when the miss arrives
  const compact = prog(f, b[4] - 6, 16, inOutCubic);
  const rowH = lerp(72, 46, compact);
  const rowGap = lerp(14, 8, compact);
  const rowSize = Math.round(lerp(TYPE.caption, TYPE.label, compact));
  const hitDim = lerp(1, 0.55, compact);
  const span1 = Math.max(20, cue(1).to - b[1]);
  const hits = [
    { text: `Peaks ${N.peaks[0]} and ${N.peaks[1]}`, fill: b[2] + 4 },
    { text: "Weekends lower and flatter", fill: b[2] + 16 },
    { text: `Direction: ${N.radial_am_pct}% of ${N.radial_pairs} route pairs in the morning, ${N.radial_pm_pct}% in the evening`, fill: b[3] + 14 },
    { text: `Bus-km ${fmt(N.bus_km_model)} against ${fmt(N.bus_km_published)} published`, fill: b[3] + 2 },
    { text: `Two different weeks: ${N.week_keep_pct}% keep their level · load correlation ${N.week_load_corr}`, fill: b[3] + 24 },
  ];
  const ROWS_TOP = 110;
  const missTop = ROWS_TOP + 5 * (46 + 8) + 14;
  const missWord = springPop(f, fps, beat(4, 0.45));

  // number line (phrase 5)
  const nlOn = prog(f, b[5] - 4, 12) * (1 - prog(f, b[6] - 8, 10));
  const NL = { x: 60, w: INNER - 120, y: 84 };
  const nx = (v: number) => NL.x + ((v - 0.4) / 1.5) * NL.w;
  const model = Number(N.load_factor_model);
  const bandLo = Number(N.load_band_low);
  const bandHi = Number(N.load_band_high);
  const fullAlloc = Number(N.load_full_allocation);
  const lineT = prog(f, b[5], 18, inOutCubic);

  // corridor row (phrases 6 and 7)
  const corOn = prog(f, b[6] - 4, 12);
  const corText = `${N.corridor_hits_total} of ${N.corridors_total} corridors`;
  const corTextW = textWidth(corText, TYPE.caption, 600);
  const strike = prog(f, b[7], 14, outCubic);

  // the closing sentence (phrase 8)
  const closing = prog(f, b[8] - 6, 14, inOutCubic);

  return (
    <SceneShell>
      <Backdrop tint={["#3b2a5c", C.blue, "#5a1d1d"]} />
      <Chapter n="05" text="The evidence" />
      <div
        style={{
          position: "absolute",
          left: CARD.x,
          top: CARD.y,
          width: CARD.w,
          height: CARD.h,
          padding: `32px ${PADX}px`,
          boxSizing: "border-box",
          borderRadius: RADIUS.xl,
          background: C.paper,
          boxShadow: SHADOW.float,
          opacity: card * lerp(1, 0.05, closing),
          filter: closing > 0 ? `blur(${6 * closing}px)` : undefined,
          transform: `translateY(${(1 - card) * 60 + closing * 30}px) scale(${lerp(1, 0.94, closing)})`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24, height: 64 }}>
          <FitText text="Written down before the first full run" size={TYPE.h2} width={INNER - 380} weight={800} color={C.blue} />
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12, padding: "8px 18px", borderRadius: RADIUS.md, border: `2px solid ${C.grey}`, background: C.white, fontSize: TYPE.label, fontWeight: 700, color: C.ink, whiteSpace: "nowrap" }}>
            expectations.yaml
            <svg width="30" height="36" viewBox="0 0 34 40">
              <path d="M9 18 V12 a8 8 0 0 1 16 0 V18" fill="none" stroke={C.ink} strokeWidth="4" strokeLinecap="round" transform={`translate(0 ${(1 - lock) * -7})`} />
              <rect x="4" y="18" width="26" height="20" rx="4" fill={C.ink} />
            </svg>
          </div>
        </div>

        <div style={{ position: "relative", marginTop: 0 }}>
          {hits.map((h, i) => (
            <Row key={i} text={h.text} appear={Math.min(b[0] + 30 + i * 8, b[1] + (i * span1) / 6)} fill={h.fill} y={ROWS_TOP - 64 + i * (rowH + rowGap)} h={rowH} size={rowSize} dim={hitDim} tag="Hit" />
          ))}

          {/* the miss */}
          <div style={{ position: "absolute", left: 0, top: missTop - 64, width: INNER, height: 96, opacity: prog(f, b[4] - 2, 10) }}>
            <Row text={`Load factor ${N.load_factor_model} · published ${N.load_band}`} appear={b[4] - 2} fill={beat(4, 0.45)} y={0} h={96} size={TYPE.body} kind="miss" />
            <div style={{ position: "absolute", right: 36, top: 0, height: 96, display: "flex", alignItems: "center", fontSize: TYPE.h1, fontWeight: 900, color: C.red, transform: `scale(${0.3 + 0.7 * missWord})`, transformOrigin: "right center", opacity: clamp01(missWord * 2), letterSpacing: -1 }}>
              Miss
            </div>
          </div>

          {/* number line */}
          <div style={{ position: "absolute", left: 0, top: missTop - 64 + 108, width: INNER, height: 224, opacity: nlOn }}>
            <svg width={INNER} height={224} style={{ overflow: "visible" }}>
              <line x1={NL.x} y1={NL.y} x2={NL.x + NL.w * lineT} y2={NL.y} stroke={C.grey} strokeWidth={5} strokeLinecap="round" />
              <rect x={nx(bandLo)} y={NL.y - 22} width={(nx(bandHi) - nx(bandLo)) * lineT} height={44} rx={10} fill={C.teal} />
              <text x={(nx(bandLo) + nx(bandHi)) / 2 + 30} y={NL.y - 38} textAnchor="middle" fontSize={TYPE.label} fontWeight={700} fill={C.teal} opacity={prog(f, b[5] + 10, 8)}>
                {N.load_band} published
              </text>
              <g opacity={prog(f, b[5] + 4, 8)}>
                <circle cx={nx(model)} cy={NL.y} r={18} fill={C.red} />
                <text x={nx(model)} y={NL.y - 34} textAnchor="middle" fontSize={TYPE.body} fontWeight={800} fill={C.red}>
                  {N.load_factor_model}
                </text>
                <text x={nx(model)} y={NL.y + 58} textAnchor="middle" fontSize={TYPE.label} fontWeight={700} fill={C.red}>
                  model
                </text>
              </g>
              <g opacity={prog(f, b[5] + 16, 8)}>
                <circle cx={nx(fullAlloc)} cy={NL.y} r={18} fill={C.amber} />
                <text x={nx(fullAlloc)} y={NL.y - 34} textAnchor="middle" fontSize={TYPE.body} fontWeight={800} fill={C.amber}>
                  {N.load_full_allocation}
                </text>
                <text x={NL.x + NL.w} y={NL.y + 58} textAnchor="end" fontSize={TYPE.label} fontWeight={700} fill={C.amber}>
                  all published ridership placed
                </text>
              </g>
              {(() => {
                const t = prog(f, b[5] + 24, 18, inOutCubic);
                const a = nx(model);
                const e = a + (nx(fullAlloc) - a) * t;
                return t > 0 ? (
                  <g>
                    <path d={`M${a} 160 V172 H${e} V160`} fill="none" stroke={C.ink} strokeWidth={3} />
                    <text x={(a + nx(fullAlloc)) / 2} y={210} textAnchor="middle" fontSize={TYPE.label} fill={C.ink} fontWeight={600} opacity={t > 0.9 ? 1 : 0}>
                      the truth is somewhere between
                    </text>
                  </g>
                ) : null;
              })()}
            </svg>
          </div>

          {/* the corridor row, struck through */}
          <div style={{ position: "absolute", left: 0, top: missTop - 64 + 116, width: INNER, opacity: corOn }}>
            <div style={{ position: "relative", height: 66 }}>
              <Row text={corText} appear={b[6] - 4} fill={b[6] + 4} y={0} h={66} size={TYPE.caption} />
              <div style={{ position: "absolute", left: 24 + 66 * 0.62 + 18 - 6, top: 31, height: 5, borderRadius: 3, background: C.ink, width: (corTextW + 12) * strike }} />
              <div style={{ position: "absolute", right: 28, top: 0, height: 66, display: "flex", alignItems: "center", fontSize: TYPE.label, fontWeight: 800, color: C.red, opacity: prog(f, b[7] + 6, 10, outCubic) }}>
                chance alone gives {N.corridor_chance} of {N.corridors_total}
              </div>
            </div>
            {[
              { text: `${N.corridor_top_decile_pct}% of corridor stretches in the top decile, chance ${N.corridor_top_decile_chance_pct}%`, at: b[7] + 16 },
              { text: `${N.corridor_both_ends} of ${N.corridors_total} with both ends on the corridor`, at: b[7] + 26 },
            ].map((l, i) => {
              const t = springSoft(f, fps, l.at, 16);
              return (
                <div key={i} style={{ marginTop: 14, padding: "8px 22px", borderLeft: `8px solid ${C.teal}`, borderRadius: RADIUS.sm, background: C.tealBg, opacity: t, transform: `translateX(${(1 - t) * 30}px)` }}>
                  <FitText text={l.text} size={TYPE.label} width={INNER - 60} weight={600} color={C.ink} />
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div style={{ position: "absolute", left: 96, top: 440, width: W - 192, opacity: closing }}>
        <Kinetic text="No field count was possible." at={b[8] - 2} size={TYPE.h1} width={W - 192} maxLines={1} stagger={4} align="center" />
      </div>

      <Captions />
      <Sfx name="tap" at={b[0] + 30} volume={0.35} />
      {hits.map((h, i) => (
        <Sfx key={i} name="tap" at={h.fill} volume={0.32} />
      ))}
      <Sfx name="pop" at={beat(4, 0.45)} volume={0.4} />
      <Sfx name="tap" at={b[6] + 4} volume={0.3} />
      <Sfx name="swoop" at={b[7]} volume={0.2} len={30} />
    </SceneShell>
  );
};
