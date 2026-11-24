// Scene 1: a Delhi street at dusk, drawn (no footage). The phone knows the bus is coming; the bus arrives full; the question.
// Beats: phrase 0 "Your phone says the bus is coming." (phone), its end (the bus pulls in), phrase 1 "Not whether you'll sit"
// (push into the packed windows), phrase 2 "or stand for an hour." (the question).
import React from "react";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { C, CONTENT, H, TYPE, W, clamp01, inOutCubic, lerp, outCubic, prog, springSoft } from "../design";
import { Captions, Chapter, Grain, Kinetic, Sfx, useBeats } from "../components/kit";
import { Person } from "../components/Person";

const Skyline: React.FC<{ seed: string; base: number; minH: number; maxH: number; color: string; shift: number; lit: number; count: number }> = ({ seed, base, minH, maxH, color, shift, lit, count }) => {
  const f = useCurrentFrame();
  const bw = (W + 400) / count;
  return (
    <div style={{ position: "absolute", left: -200 - shift, top: 0, width: W + 400, height: H }}>
      {Array.from({ length: count }, (_, i) => {
        const h = lerp(minH, maxH, random(`${seed}h${i}`));
        const w = bw * lerp(0.7, 1.05, random(`${seed}w${i}`));
        const cols = Math.max(2, Math.floor((w - 8) / 26));
        const rows = Math.floor((h - 12) / 34);
        return (
          <div key={i} style={{ position: "absolute", left: i * bw, top: base - h, width: w, height: h, background: color }}>
            {Array.from({ length: cols * rows }, (_, k) => {
              const r = random(`${seed}${i}win${k}`);
              if (r > lit) return null;
              const tw = 0.55 + 0.45 * Math.sin(f / (18 + r * 30) + r * 40);
              return (
                <div
                  key={k}
                  style={{ position: "absolute", left: 8 + (k % cols) * 26, top: 12 + Math.floor(k / cols) * 34, width: 11, height: 15, background: r < lit * 0.3 ? "#ffd58a" : "#f3b562", opacity: 0.35 + 0.5 * tw }}
                />
              );
            })}
          </div>
        );
      })}
    </div>
  );
};

/** Light streaks of traffic on the far lane. */
const Traffic: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <>
      {Array.from({ length: 9 }, (_, i) => {
        const dir = i % 2 === 0 ? 1 : -1;
        const speed = 9 + random(`sp${i}`) * 7;
        const x = ((((random(`x${i}`) * 2600 + f * speed * dir) % 2600) + 2600) % 2600) - 340;
        const y = dir > 0 ? 760 + random(`y${i}`) * 14 : 790 + random(`y${i}`) * 14;
        const col = dir > 0 ? "255,90,80" : "255,244,214";
        return (
          <div
            key={i}
            style={{ position: "absolute", left: x, top: y, width: 260, height: 6, borderRadius: 3, background: `linear-gradient(90deg, rgba(${col},0), rgba(${col},0.85))`, transform: dir < 0 ? "scaleX(-1)" : undefined, filter: "blur(1.5px)" }}
          />
        );
      })}
    </>
  );
};

const Lamp: React.FC<{ x: number }> = ({ x }) => (
  <>
    <div style={{ position: "absolute", left: x - 260, top: 260, width: 520, height: 520, borderRadius: "50%", background: "radial-gradient(circle, rgba(255,205,130,0.30), rgba(255,205,130,0) 62%)" }} />
    <div style={{ position: "absolute", left: x - 4, top: 400, width: 8, height: 440, background: "#05070c" }} />
    <div style={{ position: "absolute", left: x - 4, top: 396, width: 70, height: 8, background: "#05070c", borderRadius: 4 }} />
    <div style={{ position: "absolute", left: x + 50, top: 402, width: 26, height: 10, borderRadius: 5, background: "#ffe2a8", boxShadow: "0 0 30px 12px rgba(255,214,150,0.6)" }} />
  </>
);

/** The bus. `packed` 0..1 fills the lit windows with standing riders. */
const Bus: React.FC<{ x: number; packed: number; lights: number }> = ({ x, packed, lights }) => (
  <div style={{ position: "absolute", left: x, top: 470, width: 1180, height: 380 }}>
    <div style={{ position: "absolute", left: -560, top: 170, width: 640, height: 240, background: "radial-gradient(ellipse at 100% 50%, rgba(255,244,210,0.5), rgba(255,244,210,0) 70%)", opacity: lights }} />
    <div style={{ position: "absolute", inset: 0, borderRadius: "46px 46px 18px 18px", background: "linear-gradient(180deg,#1d6b4f 0%,#145238 60%,#0d3a28 100%)", boxShadow: "0 30px 60px rgba(0,0,0,0.6), inset 0 3px 0 rgba(255,255,255,0.12)" }} />
    {Array.from({ length: 6 }, (_, i) => (
      <div key={i} style={{ position: "absolute", left: 120 + i * 168, top: 46, width: 150, height: 150, borderRadius: 12, overflow: "hidden", background: "linear-gradient(#ffe6a6,#f3c46b)", boxShadow: "0 0 40px rgba(255,214,140,0.45)" }}>
        {Array.from({ length: 4 }, (_, k) => {
          const t = clamp01(packed * 6 - (i * 4 + k) * 0.22);
          return <Person key={k} x={-12 + k * 38 + random(`p${i}${k}`) * 10} y={30 + (k % 2) * 10 + (1 - t) * 50} size={150} color="#1a140b" opacity={t} />;
        })}
      </div>
    ))}
    <div style={{ position: "absolute", left: 18, top: 46, width: 82, height: 290, borderRadius: 10, background: "linear-gradient(#ffe6a6,#e9b55b)" }} />
    <div style={{ position: "absolute", left: 0, right: 0, top: 236, height: 14, background: "rgba(255,255,255,0.12)" }} />
    <div style={{ position: "absolute", left: -14, top: 270, width: 22, height: 44, borderRadius: 10, background: "#fff4cf", boxShadow: "0 0 50px 20px rgba(255,240,200,0.55)", opacity: lights }} />
    {[150, 900].map((wx) => (
      <div key={wx} style={{ position: "absolute", left: wx, bottom: -52, width: 112, height: 112, borderRadius: 56, background: "#06080c", border: "10px solid #1b232e" }} />
    ))}
  </div>
);

/** The phone in the rider's hand: a plain planner row with no crowd information at all. */
const HandPhone: React.FC<{ at: number; out: number }> = ({ at, out }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = springSoft(f, fps, at, 26);
  const o = prog(f, out, 18, inOutCubic);
  const roll = prog(f, at + 18, 10, outCubic);
  const pulse = 0.5 + 0.5 * Math.sin((f - at) / 5);
  if (f < at - 2) return null;
  return (
    <div style={{ position: "absolute", left: 1330, top: 150 + (1 - t) * 900 + o * 1100, display: o >= 1 ? "none" : undefined, width: 400, height: 800, transform: `rotate(${lerp(10, -5, t)}deg)` }}>
      <div style={{ position: "absolute", inset: 0, borderRadius: 58, background: "linear-gradient(150deg,#2a333d,#07090d 50%)", boxShadow: "0 50px 100px rgba(0,0,0,0.7), inset 0 0 0 2px rgba(255,255,255,0.08)" }} />
      <div style={{ position: "absolute", inset: 14, borderRadius: 46, overflow: "hidden", background: "linear-gradient(180deg,#0f1726,#0a0f18)" }}>
        <div style={{ position: "relative", height: 110, marginTop: 70, overflow: "hidden", textAlign: "center", fontSize: TYPE.display, fontWeight: 700, color: C.text, fontVariantNumeric: "tabular-nums", letterSpacing: -3, lineHeight: "110px" }}>
          <div style={{ position: "absolute", left: 0, right: 0, top: -roll * 110 }}>17:59</div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 110 - roll * 110 }}>18:00</div>
        </div>
        <div style={{ margin: "40px 22px 0", padding: "22px 24px", borderRadius: 24, background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: TYPE.body, fontWeight: 800, color: C.text }}>359UP</div>
            <div style={{ width: 16, height: 16, borderRadius: 8, background: C.tealGlow, opacity: 0.4 + 0.6 * pulse, boxShadow: `0 0 16px ${C.tealGlow}` }} />
          </div>
          <div style={{ fontSize: TYPE.label, color: C.textDim, marginTop: 6 }}>arriving now</div>
        </div>
        <div style={{ margin: "18px 22px 0", padding: "22px 24px", borderRadius: 24, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", opacity: 0.75 }}>
          <div style={{ fontSize: TYPE.body, fontWeight: 800, color: C.text }}>764DOWN</div>
          <div style={{ fontSize: TYPE.label, color: C.textDim, marginTop: 6 }}>arriving soon</div>
        </div>
      </div>
    </div>
  );
};

export const Scene01: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames: D, fps } = useVideoConfig();
  const { beat, end } = useBeats();
  const phoneAt = beat(0) - 6;
  const busAt = end(0) - 10; // the bus pulls in as "...is coming" ends
  const packAt = beat(1);
  const qAt = beat(2);

  const busT = prog(f, busAt, 50, outCubic);
  const busX = lerp(W + 80, 640, busT);
  const push = lerp(1, 1.05, inOutCubic(f / D)) * lerp(1, 1.18, prog(f, packAt - 4, 44, inOutCubic));
  const dim = lerp(1, 0.4, prog(f, qAt, 16, inOutCubic));
  const fadeIn = prog(f, 0, 20);
  const blackout = prog(f, D - 5, 5);
  const sway = (i: number) => (i === 1 || i === 4 ? Math.sin((f / 80) * Math.PI * 2 + i) * 5 : 0);
  const queue = springSoft(f, fps, 8, 30);
  const glow = 0.85 + 0.15 * Math.sin(f / 40);

  return (
    <AbsoluteFill style={{ background: C.dusk, overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${push})`, transformOrigin: "1180px 600px", opacity: fadeIn }}>
        <AbsoluteFill style={{ background: "linear-gradient(180deg,#070b18 0%,#121c3d 38%,#3a2a52 62%,#a5523a 82%,#e08a4a 100%)" }} />
        <div style={{ position: "absolute", left: 0, right: 0, top: 380, height: 420, background: "radial-gradient(ellipse at 60% 100%, rgba(255,170,90,0.55), rgba(255,170,90,0) 65%)", opacity: glow }} />
        {Array.from({ length: 40 }, (_, i) => (
          <div key={i} style={{ position: "absolute", left: random(`sx${i}`) * W, top: random(`sy${i}`) * 300, width: 3, height: 3, borderRadius: 2, background: "#fff", opacity: 0.2 + 0.5 * Math.abs(Math.sin(f / 25 + i)) * random(`so${i}`) }} />
        ))}
        <Skyline seed="far" base={700} minH={140} maxH={330} color="#18203a" shift={f * 0.06} lit={0.28} count={26} />
        <Skyline seed="mid" base={720} minH={180} maxH={420} color="#0d1426" shift={f * 0.15} lit={0.36} count={16} />
        <div style={{ position: "absolute", left: 0, right: 0, top: 720, bottom: 0, background: "linear-gradient(#0a0e18,#05070c)" }} />
        <Traffic />
        <div style={{ position: "absolute", left: 0, right: 0, top: 860, height: 6, background: "repeating-linear-gradient(90deg, rgba(255,255,255,0.3) 0 80px, transparent 80px 160px)" }} />
        <div style={{ filter: `brightness(${dim})` }}>
          <Lamp x={110} />
          <Lamp x={1820} />
          <div style={{ position: "absolute", left: 160, top: 520, width: 560, height: 20, borderRadius: 6, background: "#03050a", opacity: queue }} />
          <div style={{ position: "absolute", left: 176, top: 540, width: 12, height: 320, background: "#03050a", opacity: queue }} />
          <div style={{ position: "absolute", left: 692, top: 540, width: 12, height: 320, background: "#03050a", opacity: queue }} />
          <div style={{ position: "absolute", left: 600, top: 400, width: 90, height: 56, borderRadius: 10, background: C.blue, opacity: queue, boxShadow: "0 0 24px rgba(96,165,250,0.5)" }} />
          {Array.from({ length: 6 }, (_, i) => {
            const t = springSoft(f, fps, 6 + i * 4, 24);
            return <Person key={i} x={210 + i * 78 + sway(i)} y={600 + (i % 2) * 14 + (1 - t) * 20} size={270} color="#02040a" opacity={t} />;
          })}
          <Bus x={busX} packed={prog(f, packAt - 6, 46)} lights={busT} />
        </div>
      </AbsoluteFill>

      <HandPhone at={phoneAt} out={busAt} />
      <Chapter n="18:00" text="Delhi, a weekday evening" hold={busAt} />

      <div style={{ position: "absolute", left: CONTENT.left, top: 150, width: CONTENT.width, textShadow: "0 6px 40px rgba(0,0,0,0.6)" }}>
        <Kinetic text="A seat, or an hour on your feet?" at={qAt} size={TYPE.display} width={CONTENT.width} maxLines={1} stagger={4} align="center" accent={{ seat: C.tealGlow, feet: C.amberGlow }} />
      </div>
      <Grain opacity={0.08} />
      <Captions />
      <AbsoluteFill style={{ background: "#000", opacity: blackout }} />

      <Sfx name="ambience" at={0} volume={0.34} len={D} fade={30} />
      <Sfx name="city-ambience" at={0} volume={0.2} len={D} fade={45} />
      <Sfx name="tap" at={phoneAt + 18} volume={0.25} />
      <Sfx name="engine" at={busAt - 6} volume={0.4} len={120} fade={12} />
      <Sfx name="horn" at={busAt + 6} volume={0.45} len={45} />
      <Sfx name="air-brake" at={busAt + 40} volume={0.8} len={60} fade={12} />
      <Sfx name="riser" at={qAt - 40} volume={0.25} />
    </AbsoluteFill>
  );
};
