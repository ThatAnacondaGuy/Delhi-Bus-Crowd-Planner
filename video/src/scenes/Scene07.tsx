import React from "react";
import { useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, fmt, inOutCubic, lerp, outCubic, prog, springSoft } from "../theme";
import { Caption, Scene, Sfx, useClock } from "../components/ui";
import { sceneCaptionSpans } from "../captions";
import { LEAD_FRAMES } from "../timing";
import { useAssets } from "../assets";

const CARD_X = 300;
const CARD_W = 1320;

type RowProps = { u: number; y: number; h?: number; appear: number; fillAt?: number; text: React.ReactNode; tag?: string; kind?: "hit" | "miss"; dim?: number; size?: number };

const Row: React.FC<RowProps> = ({ u, y, h = 58, appear, fillAt, text, tag, kind = "hit", dim = 1, size = 32 }) => {
  const a = prog(u, appear, 12, outCubic);
  const filled = fillAt === undefined ? 0 : prog(u, fillAt, 12, outCubic);
  const col = kind === "hit" ? C.teal : C.red;
  const bg = kind === "hit" ? C.tealBg : C.redBg;
  const draw = fillAt === undefined ? 0 : prog(u, fillAt, 14, outCubic);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: y,
        width: "100%",
        height: h,
        display: "flex",
        alignItems: "center",
        gap: 22,
        padding: "0 22px",
        borderRadius: h / 2,
        border: `3px solid ${filled > 0.05 ? col : "#b7bcc1"}`,
        background: filled > 0 ? `color-mix(in srgb, ${bg} ${Math.round(filled * 100)}%, white)` : "white",
        opacity: a * dim,
        transform: `translateY(${(1 - a) * 14}px)`,
        boxSizing: "border-box",
      }}
    >
      <svg width={size + 8} height={size + 8} viewBox="0 0 40 40" style={{ flex: "none" }}>
        <circle cx="20" cy="20" r="17" fill="none" stroke={filled > 0.05 ? col : "#b7bcc1"} strokeWidth="3.5" />
        {kind === "hit" ? (
          <path d="M11 21 L18 28 L30 12" fill="none" stroke={col} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={40} strokeDashoffset={40 * (1 - draw)} />
        ) : (
          <>
            <path d="M12 12 L28 28" stroke={col} strokeWidth="5" strokeLinecap="round" strokeDasharray={24} strokeDashoffset={24 * (1 - Math.min(1, draw * 2))} />
            <path d="M28 12 L12 28" stroke={col} strokeWidth="5" strokeLinecap="round" strokeDasharray={24} strokeDashoffset={24 * (1 - Math.max(0, draw * 2 - 1))} />
          </>
        )}
      </svg>
      <div style={{ fontSize: size, fontWeight: 700, color: C.ink, flex: 1, lineHeight: 1.1 }}>{text}</div>
      {tag ? <div style={{ fontSize: size, fontWeight: 700, color: col, opacity: filled }}>{tag}</div> : null}
    </div>
  );
};

const pct = (v: number) => `${v}%`;

export const Scene07: React.FC = () => {
  const u = useClock(900);
  const { fps, durationInFrames: D } = useVideoConfig();
  const { vo } = useAssets();

  // phases
  const dimHits = lerp(1, 0.35, prog(u, 420, 16));
  const phaseB = prog(u, 438, 12) * (1 - prog(u, 622, 10));
  const phaseC = prog(u, 636, 12) * (1 - prog(u, 806, 10));
  const dimAll = prog(u, 812, 16);
  const closing = prog(u, 820, 20, outCubic);

  // number line: 0.40 .. 1.90
  const NL_X = 60;
  const NL_W = CARD_W - 2 * 60 - 40;
  const nx = (v: number) => NL_X + ((v - 0.4) / 1.5) * NL_W;
  const model = Number(N.load_factor_model);
  const bandLo = Number(N.load_band_low);
  const bandHi = Number(N.load_band_high);
  const full = Number(N.load_full_allocation);
  const lineT = prog(u, 470, 30, inOutCubic);

  const missRow = prog(u, 420, 12);
  const missWord = springSoft(u, fps, 446, 18);

  const spans = sceneCaptionSpans(7, { voFrames: vo[6] != null ? Math.round(vo[6]! * 30) : null, duration: D, base: 900, lead: LEAD_FRAMES });

  const hits: { at: number; text: React.ReactNode }[] = [
    { at: 120, text: `Peaks ${N.peaks[0]} and ${N.peaks[1]}` },
    { at: 165, text: "Weekends lower and flatter" },
    { at: 210, text: `Direction: ${pct(N.radial_am_pct)} of ${N.radial_pairs} route pairs in the morning, ${pct(N.radial_pm_pct)} in the evening` },
    { at: 255, text: `Bus-km ${fmt(N.bus_km_model)} against ${fmt(N.bus_km_published)} published` },
    { at: 300, text: `Two different weeks: ${pct(N.week_keep_pct)} keep their level · load correlation ${N.week_load_corr}` },
  ];

  return (
    <Scene bg={C.dusk} fadeIn={12} fadeOut={12}>
      <div style={{ position: "absolute", inset: 0, background: `radial-gradient(1200px 700px at 50% 20%, ${C.duskBlue}, ${C.dusk})` }} />
      <div style={{ position: "absolute", left: CARD_X, top: 48, width: CARD_W, height: 850, background: C.paper, borderRadius: 36, boxShadow: "0 30px 90px rgba(0,0,0,0.5)", opacity: 1 - dimAll * 0.9, padding: "34px 40px 0", boxSizing: "border-box" }}>
        {/* title and the file with its lock */}
        <div style={{ display: "flex", alignItems: "center", gap: 26, opacity: prog(u, 0, 12, outCubic), height: 70 }}>
          <div style={{ fontSize: 48, fontWeight: 700, color: C.blue, flex: 1, lineHeight: 1.05, whiteSpace: "nowrap" }}>Written down before the first full run</div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 32, fontWeight: 700, color: C.ink, background: C.white, border: `3px solid ${C.grey}`, borderRadius: 16, padding: "6px 16px", transform: `translateX(${(1 - prog(u, 16, 20, outCubic)) * 300}px)` }}>
            <span>expectations.yaml</span>
            <svg width="34" height="40" viewBox="0 0 34 40">
              <path d="M9 18 V12 a8 8 0 0 1 16 0 V18" fill="none" stroke={C.ink} strokeWidth="4" strokeLinecap="round" transform={`translate(0 ${(1 - prog(u, 44, 9)) * -6})`} />
              <rect x="4" y="18" width="26" height="20" rx="4" fill={C.ink} />
            </svg>
          </div>
        </div>

        <div style={{ position: "relative", marginTop: 18, height: 740 }}>
          {hits.map((h, i) => (
            <Row key={i} u={u} y={i * 66} h={58} appear={60 + i * 12} fillAt={h.at} text={h.text} dim={dimHits} />
          ))}
          <Sfx name="tap" at={120} volume={0.4} />
          <Sfx name="tap" at={165} volume={0.4} />
          <Sfx name="tap" at={210} volume={0.4} />
          <Sfx name="tap" at={255} volume={0.4} />
          <Sfx name="tap" at={300} volume={0.4} />

          {/* the miss */}
          <div style={{ position: "absolute", left: 0, top: 346, width: "100%", opacity: missRow }}>
            <Row u={u} y={0} h={100} appear={420} fillAt={448} kind="miss" size={40} text={`Load factor ${N.load_factor_model} · published ${N.load_band}`} dim={1 - dimAll * 0} />
            <div style={{ position: "absolute", right: 34, top: -6, fontSize: 112, fontWeight: 700, color: C.red, transform: `scale(${0.4 + 0.6 * missWord})`, transformOrigin: "right center", opacity: missWord, lineHeight: 1 }}>Miss</div>
          </div>

          {/* number line */}
          <div style={{ position: "absolute", left: 0, top: 452, width: "100%", height: 260, opacity: phaseB }}>
            <svg width={CARD_W - 80} height={260} style={{ overflow: "visible" }}>
              <line x1={NL_X} y1={120} x2={NL_X + NL_W * lineT} y2={120} stroke={C.grey} strokeWidth={5} strokeLinecap="round" />
              {/* published band */}
              <rect x={nx(bandLo)} y={96} width={(nx(bandHi) - nx(bandLo)) * lineT} height={48} rx={8} fill={C.teal} />
              <text x={nx((bandLo + bandHi) / 2) + 40} y={66} textAnchor="middle" fontSize={34} fontWeight={700} fill={C.teal} opacity={lineT > 0.8 ? 1 : 0}>
                {N.load_band} published
              </text>
              {/* the model */}
              <g opacity={prog(u, 500, 12)}>
                <circle cx={nx(model)} cy={120} r={20} fill={C.red} />
                <text x={nx(model)} y={66} textAnchor="middle" fontSize={44} fontWeight={700} fill={C.red}>
                  {N.load_factor_model}
                </text>
                <text x={nx(model)} y={186} textAnchor="middle" fontSize={34} fontWeight={700} fill={C.red}>
                  model
                </text>
              </g>
              {/* all published ridership placed */}
              <g opacity={prog(u, 526, 12)}>
                <circle cx={nx(full)} cy={120} r={20} fill={C.amber} />
                <text x={nx(full)} y={66} textAnchor="middle" fontSize={44} fontWeight={700} fill={C.amber}>
                  {N.load_full_allocation}
                </text>
                <text x={NL_X + NL_W + 20} y={186} textAnchor="end" fontSize={32} fontWeight={700} fill={C.amber}>
                  all published ridership placed
                </text>
              </g>
              {/* bracket */}
              {(() => {
                const t = prog(u, 548, 30, inOutCubic);
                const a = nx(model);
                const b = a + (nx(full) - a) * t;
                return (
                  <g opacity={t > 0 ? 1 : 0}>
                    <path d={`M${a} 212 V224 H${b} V212`} fill="none" stroke={C.ink} strokeWidth={4} />
                    <text x={(a + nx(full)) / 2} y={254} textAnchor="middle" fontSize={32} fill={C.ink} opacity={t > 0.9 ? 1 : 0} fontWeight={700}>
                      the truth is somewhere between
                    </text>
                  </g>
                );
              })()}
            </svg>
          </div>

          {/* the corridor row */}
          <div style={{ position: "absolute", left: 0, top: 470, width: "100%", opacity: phaseC }}>
            <div style={{ position: "relative", height: 72 }}>
              <Row u={u} y={0} h={72} appear={640} fillAt={652} text={`${N.corridor_hits_total} of ${N.corridors_total} corridors`} />
              {/* strike line */}
              <div style={{ position: "absolute", left: 70, top: 35, height: 6, borderRadius: 3, background: C.ink, width: 292 * prog(u, 690, 12, outCubic) }} />
              <div style={{ position: "absolute", right: 30, top: 0, height: 72, display: "flex", alignItems: "center", fontSize: 34, fontWeight: 700, color: C.red, opacity: prog(u, 700, 12, outCubic) }}>chance alone gives {N.corridor_chance} of {N.corridors_total}</div>
            </div>
            <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 18 }}>
              <div style={{ opacity: prog(u, 724, 12, outCubic), transform: `translateX(${(1 - prog(u, 724, 12, outCubic)) * 40}px)`, fontSize: 38, fontWeight: 700, color: C.ink, padding: "14px 24px", background: C.tealBg, borderRadius: 18, borderLeft: `10px solid ${C.teal}` }}>
                {N.corridor_top_decile_pct}% of corridor stretches in the top decile, chance {N.corridor_top_decile_chance_pct}%
              </div>
              <div style={{ opacity: prog(u, 756, 12, outCubic), transform: `translateX(${(1 - prog(u, 756, 12, outCubic)) * 40}px)`, fontSize: 38, fontWeight: 700, color: C.ink, padding: "14px 24px", background: C.tealBg, borderRadius: 18, borderLeft: `10px solid ${C.teal}` }}>
                {N.corridor_both_ends} of {N.corridors_total} with both ends on the corridor
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ position: "absolute", left: 0, right: 0, top: 400, textAlign: "center", fontSize: 84, fontWeight: 700, color: C.paper, opacity: closing, transform: `translateY(${(1 - closing) * 20}px)`, textShadow: "0 4px 30px rgba(0,0,0,0.6)" }}>No field count was possible.</div>
      <Caption spans={spans} bottom={30} />
      <Sfx name="pop" at={448} volume={0.5} />
    </Scene>
  );
};
