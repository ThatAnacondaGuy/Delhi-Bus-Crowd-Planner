// Scene 4: one ticket becomes a level. Every step lands on its phrase: the ticket (0), the stretches (1), the scale-up (2),
// the bus's limit (3), seats and rated total (4), then the chip is built word (5), dots (6), colour (7).
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, RADIUS, SHADOW, TYPE, W, clamp01, inOutCubic, lerp, outCubic, prog, springPop, springSoft } from "../design";
import { Backdrop, Captions, Chapter, Chip, FitText, SceneShell, Sfx, useBeats } from "../components/kit";
import { Person } from "../components/Person";

const STOPS = ["A", "B", "C", "D"];
const X0 = 360;
const DX = 400;
const LY = 430;
const sx = (i: number) => X0 + i * DX;

/** A small clock: the bus passes each stretch at its own time. */
const Clock: React.FC<{ x: number; y: number; angle: number; t: number }> = ({ x, y, angle, t }) => (
  <svg width={56} height={56} viewBox="0 0 64 64" style={{ position: "absolute", left: x - 28, top: y, opacity: t, transform: `scale(${0.6 + 0.4 * t})` }}>
    <circle cx="32" cy="32" r="27" fill="rgba(255,255,255,0.08)" stroke={C.blueGlow} strokeWidth="4" />
    <line x1="32" y1="32" x2="32" y2="13" stroke={C.text} strokeWidth="4" strokeLinecap="round" transform={`rotate(${angle} 32 32)`} />
    <line x1="32" y1="32" x2="44" y2="32" stroke={C.text} strokeWidth="4" strokeLinecap="round" transform={`rotate(${angle * 0.3 - 60} 32 32)`} />
  </svg>
);

export const Scene04: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, durationInFrames: D } = useVideoConfig();
  const { beat, cue } = useBeats();
  const [b0, b1, b2, b3, b4, b5, b6, b7] = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => beat(i));

  // stage 1 (ticket and stretches) gives way to stage 2 (the bus) on phrase 2
  const s1 = 1 - prog(f, b2 - 6, 14, inOutCubic);
  const s2 = prog(f, b2 - 4, 14, inOutCubic) * lerp(1, 0.14, prog(f, b5 - 4, 14, inOutCubic));
  const ticket = springSoft(f, fps, b0 - 2, 24);
  const lineT = prog(f, b0 + 8, 30, inOutCubic);
  const stretchSpan = Math.max(30, cue(1).to - b1);

  // the bus: 1 rider becomes N.one_in riders across phrase 2
  const crowdSpan = Math.max(30, cue(2).to - b2 - 10);
  const COLS = 11;
  const BUS = { x: 410, y: 150, w: 1100, h: 330 };
  const extra = prog(f, b3, 30); // riders who would not fit try to get on and are turned away

  // seats and rated total
  const BAR = { x: 410, y: 600, w: 1100, h: 64 };
  const seatsW = BAR.w * 0.42;
  const ratedW = BAR.w * 0.58;
  const marker = lerp(BAR.x + 30, BAR.x + seatsW + ratedW * 0.42, prog(f, b4 + 20, 26, inOutCubic));

  // the chip: word, then dots one by one, then colour
  const word = prog(f, b5, 10, outCubic);
  const dotsSpan = Math.max(9, cue(6).to - b6);
  const dots = clamp01((f - b6) / dotsSpan);
  const colour = prog(f, b7, 12, outCubic);
  const chipIn = springSoft(f, fps, b5 - 4, 20);
  const grow = prog(f, D - 26, 26, inOutCubic);

  const label = (text: string, at: number, extraStyle: React.CSSProperties) => {
    const t = springSoft(f, fps, at, 18);
    return (
      <div style={{ position: "absolute", opacity: t, transform: `translateY(${(1 - t) * 14}px)`, ...extraStyle }}>
        <FitText text={text} size={TYPE.body} width={Number(extraStyle.width ?? 600)} color={C.text} align={(extraStyle.textAlign as any) ?? "left"} />
      </div>
    );
  };

  return (
    <SceneShell>
      <Backdrop tint={[C.blue, "#3b2a5c", C.teal]} />
      <Chapter n="02" text="How a ticket becomes a level" />

      {/* stage 1: a ticket, the stops, the stretches */}
      <div style={{ position: "absolute", inset: 0, opacity: s1 }}>
        <div
          style={{
            position: "absolute",
            left: W / 2 - 300,
            top: 170,
            width: 600,
            padding: "22px 34px",
            boxSizing: "border-box",
            borderRadius: RADIUS.lg,
            background: C.paper,
            color: C.ink,
            boxShadow: SHADOW.float,
            transform: `translateY(${(1 - ticket) * -60}px) rotate(${(1 - ticket) * -4}deg)`,
            opacity: ticket,
            borderLeft: `14px solid ${C.teal}`,
          }}
        >
          <FitText text="Stop A → Stop D" size={TYPE.h2} width={600 - 68 - 14} color={C.ink} />
          <FitText text="got on → got off" size={TYPE.label} width={600 - 68 - 14} weight={500} color={C.grey} style={{ marginTop: 6 }} />
        </div>
        <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
          <line x1={sx(0)} y1={LY} x2={lerp(sx(0), sx(3), lineT)} y2={LY} stroke="rgba(255,255,255,0.25)" strokeWidth={8} strokeLinecap="round" />
          {[0, 1, 2].map((i) => {
            const t = prog(f, b1 + (i * stretchSpan) / 3, stretchSpan / 3, inOutCubic);
            return t > 0 ? <line key={i} x1={sx(i)} y1={LY} x2={lerp(sx(i), sx(i + 1), t)} y2={LY} stroke={C.tealGlow} strokeWidth={lerp(6, 16, t)} strokeLinecap="round" style={{ filter: `drop-shadow(0 0 10px ${C.tealGlow})` }} /> : null;
          })}
          {STOPS.map((s, i) => {
            const t = springPop(f, fps, b0 + 10 + i * 5);
            const end = i === 0 || i === 3;
            return (
              <g key={s} opacity={clamp01(t * 2)} transform={`translate(${sx(i)} ${LY}) scale(${0.5 + 0.5 * t})`}>
                <circle r={24} fill={end ? C.tealGlow : C.duskHi} stroke={C.text} strokeWidth={5} />
              </g>
            );
          })}
        </svg>
        {STOPS.map((s, i) => label(`Stop ${s}`, b0 + 12 + i * 5, { left: sx(i) - 120, top: LY + 44, width: 240, textAlign: "center" }))}
        {[0, 1, 2].map((i) => (
          <Clock key={i} x={(sx(i) + sx(i + 1)) / 2} y={LY - 96} angle={[40, 150, 260][i]} t={prog(f, b1 + (i * stretchSpan) / 3 + 6, 10, outCubic)} />
        ))}
        {label("each stretch at the time the bus passed", b1 + 10, { left: W / 2 - 450, top: 590, width: 900, textAlign: "center" })}
      </div>

      {/* stage 2: everyone on board, the bus's limit, seats and rated total */}
      <div style={{ position: "absolute", inset: 0, opacity: s2 }}>
        <div style={{ position: "absolute", left: BUS.x, top: BUS.y, width: BUS.w, height: BUS.h, borderRadius: 44, border: "6px solid rgba(255,255,255,0.75)", background: "rgba(255,255,255,0.05)", boxShadow: SHADOW.card }} />
        <div style={{ position: "absolute", left: BUS.x, top: BUS.y, width: BUS.w, height: BUS.h, overflow: "hidden", borderRadius: 44 }}>
          {Array.from({ length: N.one_in }, (_, i) => {
            const t = i === 0 ? springPop(f, fps, b2 - 2) : springPop(f, fps, b2 + 8 + ((i - 1) * crowdSpan) / N.one_in);
            const col = i % COLS;
            const row = Math.floor(i / COLS);
            return <Person key={i} x={48 + col * 92} y={30 + row * 72} size={74} color={i === 0 ? C.tealGlow : "#cbd5e1"} opacity={clamp01(t * 1.5)} />;
          })}
        </div>
        {/* turned away */}
        {[0, 1, 2].map((i) => {
          const t = prog(f, b3 + i * 6, 22, outCubic);
          return <Person key={i} x={BUS.x + BUS.w + 40 + i * 64 - (1 - t) * 40} y={BUS.y + 120 + i * 18} size={74} color={C.redGlow} opacity={t * (1 - prog(f, b3 + 40 + i * 4, 18))} />;
        })}
        <div style={{ position: "absolute", left: BUS.x + BUS.w + 14, top: BUS.y - 6, width: 10, height: BUS.h + 12, borderRadius: 5, background: C.redGlow, opacity: extra, boxShadow: `0 0 20px ${C.redGlow}` }} />
        {label(`app tickets: about 1 in ${N.one_in} riders`, b2 + 6, { left: BUS.x, top: BUS.y + BUS.h + 22, width: BUS.w, textAlign: "center" })}

        {/* seats and rated total */}
        <div style={{ opacity: prog(f, b4 - 4, 12) }}>
          <div style={{ position: "absolute", left: BAR.x, top: BAR.y, width: BAR.w, height: BAR.h, borderRadius: RADIUS.pill, background: "rgba(255,255,255,0.08)" }} />
          <div style={{ position: "absolute", left: BAR.x, top: BAR.y, width: seatsW * prog(f, b4, 18, inOutCubic), height: BAR.h, borderRadius: `${BAR.h / 2}px 0 0 ${BAR.h / 2}px`, background: C.teal }} />
          <div style={{ position: "absolute", left: BAR.x + seatsW, top: BAR.y, width: ratedW * prog(f, b4 + 10, 18, inOutCubic), height: BAR.h, borderRadius: `0 ${BAR.h / 2}px ${BAR.h / 2}px 0`, background: C.amber }} />
          {label("seats", b4 + 6, { left: BAR.x, top: BAR.y + BAR.h + 16, width: seatsW - 20 })}
          {label("standing, up to the rated total", b4 + 14, { left: BAR.x + seatsW + 20, top: BAR.y + BAR.h + 16, width: ratedW - 20 })}
          <div style={{ position: "absolute", left: marker - 4, top: BAR.y - 22, width: 8, height: BAR.h + 44, borderRadius: 4, background: C.text, opacity: prog(f, b4 + 20, 8), boxShadow: "0 0 16px rgba(255,255,255,0.6)" }} />
        </div>
      </div>

      {/* the level: one word, three dots, a colour */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 380, display: "flex", justifyContent: "center", opacity: chipIn, transform: `scale(${lerp(0.85, 1, chipIn) * lerp(1, 1.35, grow)})` }}>
        <Chip level="standing" size={TYPE.h1} glow={colour * (0.6 + 0.4 * Math.sin((f - b7) / 6))} build={{ word, dots, colour }} />
      </div>

      <Captions />
      <Sfx name="pop" at={b0 + 2} volume={0.3} />
      {[0, 1, 2].map((i) => (
        <Sfx key={i} name="tap" at={b1 + (i * stretchSpan) / 3} volume={0.3} />
      ))}
      <Sfx name="riser" at={b2 - 10} volume={0.32} />
      <Sfx name="tap" at={b4} volume={0.3} />
      {[0, 1, 2].map((i) => (
        <Sfx key={`d${i}`} name="pop" at={b6 + (i * dotsSpan) / 3} volume={0.5} />
      ))}
      <Sfx name="chime" at={b7} volume={0.6} />
    </SceneShell>
  );
};
