import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT, inOutCubic, lerp, outCubic, prog } from "../theme";
import { Caption, Sfx, Words } from "../components/ui";
import { Person } from "../components/Person";
import { sceneCaptionSpans } from "../captions";
import { LEAD_FRAMES } from "../timing";
import { useAssets } from "../assets";

const INK = "#05080c";

/** A bus-interior panel: rows of seats along the bottom, poles, and N standing silhouettes. */
const Interior: React.FC<{ count: number; at: number; stagger: number; seed: number; u: number; warm: number }> = ({ count, at, stagger, seed, u, warm }) => {
  const W = 1140;
  const H = 580;
  const figs = Array.from({ length: count }, (_, i) => {
    const r = Math.sin((i + 1) * 12.9898 + seed) * 43758.5453;
    const rnd = r - Math.floor(r);
    const x = count > 8 ? 40 + ((i * 78 + rnd * 30) % (W - 140)) : 160 + i * 240 + rnd * 60;
    const y = 190 + (i % 3) * 38 + rnd * 20;
    return { x, y, size: 300 - (i % 3) * 10, t: prog(u, at + i * stagger, 10, outCubic) };
  });
  return (
    <div style={{ position: "absolute", left: 120, top: 250, width: W, height: H, borderRadius: 34, overflow: "hidden", background: `linear-gradient(#2a2418, #17130d)`, boxShadow: "0 30px 80px rgba(0,0,0,0.6)", opacity: warm }}>
      {/* ceiling lights */}
      {[140, 420, 700, 980].map((x) => (
        <div key={x} style={{ position: "absolute", left: x - 90, top: 0, width: 180, height: 16, borderRadius: 8, background: "#ffe9b0", boxShadow: "0 0 80px 30px rgba(255,226,160,0.28)" }} />
      ))}
      {/* windows */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 60, height: 130, background: "linear-gradient(#1d2b44,#0d1522)", opacity: 0.8 }} />
      {/* poles */}
      {[200, 560, 920].map((x) => (
        <div key={x} style={{ position: "absolute", left: x, top: 20, width: 12, height: H - 20, background: "#9aa3ab", opacity: 0.8 }} />
      ))}
      {/* floor and seat rows */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 120, background: "#0e0b07" }} />
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} style={{ position: "absolute", left: 40 + i * 180, bottom: 60, width: 130, height: 120, borderRadius: "28px 28px 10px 10px", background: "#7a5b2b" }} />
      ))}
      {figs.map((f, i) => (
        <Person key={i} x={f.x} y={f.y + (1 - f.t) * 40} size={f.size} color="#07090c" opacity={f.t} />
      ))}
    </div>
  );
};

const Phone: React.FC<{ u: number }> = ({ u }) => {
  const enter = prog(u, 45, 18, outCubic);
  const digit = prog(u, 75, 8);
  return (
    <div style={{ position: "absolute", left: 1420, top: 260 + (1 - enter) * 700, width: 380, height: 760, borderRadius: 56, background: "#06090d", border: "10px solid #1c242c", boxShadow: "0 40px 90px rgba(0,0,0,0.6)", transform: "rotate(-4deg)", padding: "40px 24px", boxSizing: "border-box", opacity: enter }}>
      <div style={{ textAlign: "center", color: "#e9edf0", fontSize: 92, fontWeight: 700, height: 100, overflow: "hidden", position: "relative" }}>
        <div style={{ position: "absolute", left: 0, right: 0, top: -digit * 100 }}>17:59</div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 100 - digit * 100 }}>18:00</div>
      </div>
      <div style={{ marginTop: 40, background: "#141c24", borderRadius: 22, padding: "22px 24px", color: "#e9edf0", border: "2px solid #26323d" }}>
        <div style={{ fontSize: 40, fontWeight: 700 }}>359UP</div>
        <div style={{ fontSize: 32, color: "#9fb0bd", marginTop: 4 }}>arriving</div>
      </div>
      <div style={{ marginTop: 18, background: "#141c24", borderRadius: 22, padding: "22px 24px", color: "#e9edf0", border: "2px solid #26323d", opacity: 0.8 }}>
        <div style={{ fontSize: 40, fontWeight: 700 }}>764DOWN</div>
        <div style={{ fontSize: 32, color: "#9fb0bd", marginTop: 4 }}>arriving</div>
      </div>
    </div>
  );
};

export const Scene01: React.FC = () => {
  const u = useCurrentFrame();
  const { durationInFrames: D } = useVideoConfig();
  const { vo, clips } = useAssets();
  const clip = clips.find((c) => /\.(mp4|mov|webm)$/i.test(c));
  const push = lerp(1, 1.08, inOutCubic(u / 300));

  const bg = `linear-gradient(180deg, #0d1117 0%, #101c30 55%, #1c2f4c 100%)`;
  const busX = lerp(2300, 640, prog(u, 120, 30, outCubic));
  const doors = prog(u, 150, 15);
  const showInt1 = u >= 165 && u < 195;
  const showInt2 = u >= 195;
  const qT = prog(u, 225, 18);
  const dimOthers = lerp(1, 0.3, prog(u, 225, 18));
  const blackout = prog(u, 294, 6);

  const spans = sceneCaptionSpans(1, { voFrames: vo[0] != null ? Math.round(vo[0]! * 30) : null, duration: D, base: 300, lead: LEAD_FRAMES });

  return (
    <AbsoluteFill style={{ background: "#0d1117", fontFamily: FONT }}>
      <AbsoluteFill style={{ transform: `scale(${push})`, transformOrigin: "50% 55%" }}>
        {clip ? (
          <>
            <OffthreadVideo src={staticFile(`clips/${clip}`)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(13,17,23,0.55), rgba(13,17,23,0.35))" }} />
          </>
        ) : (
          <>
            <AbsoluteFill style={{ background: bg }} />
            {/* street-light bloom */}
            <div style={{ position: "absolute", left: -200, top: -100, width: 900, height: 900, borderRadius: "50%", background: "radial-gradient(circle, rgba(255,214,140,0.32), rgba(255,214,140,0) 62%)" }} />
            {/* road */}
            <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 250, background: "linear-gradient(#0a0e13,#05070a)" }} />
            <div style={{ position: "absolute", left: 0, right: 0, bottom: 250, height: 6, background: "#27384f" }} />
          </>
        )}

        {/* bus stop: shelter and the queue */}
        {!clip && (
          <div style={{ opacity: dimOthers }}>
            <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
              <g opacity={prog(u, 0, 24)}>
                <rect x={150} y={420} width={640} height={22} rx={6} fill="#04070a" />
                <rect x={170} y={440} width={14} height={390} fill="#04070a" />
                <rect x={760} y={440} width={14} height={390} fill="#04070a" />
                <rect x={176} y={560} width={590} height={8} fill="#0a1018" opacity={0.0} />
                <rect x={1000} y={300} width={12} height={530} fill="#04070a" />
                <rect x={960} y={270} width={96} height={56} rx={10} fill="#1f4e79" />
              </g>
            </svg>
            {Array.from({ length: 7 }, (_, i) => {
              const t = prog(u, i * 4, 24);
              const sway = i === 2 || i === 5 ? Math.sin((u / 90) * Math.PI * 2) * 6 : 0;
              return <Person key={i} x={230 + i * 78 + sway} y={540 + (i % 2) * 14 - (1 - t) * 12} size={290} color="#04070a" opacity={t} />;
            })}
          </div>
        )}

        {/* the bus arrives (headlights, then body) */}
        {!clip && u >= 118 && (
          <div style={{ opacity: u < 225 ? 1 : dimOthers }}>
            <div style={{ position: "absolute", left: busX + 880, top: 560, width: 700, height: 300, background: "radial-gradient(ellipse at 20% 50%, rgba(255,240,200,0.55), rgba(255,240,200,0) 65%)", opacity: prog(u, 120, 30, outCubic) * (1 - doors * 0.6) }} />
            <div style={{ position: "absolute", left: busX, top: 470, width: 980, height: 340, borderRadius: 40, background: "linear-gradient(#18222f,#0b1119)", border: "4px solid #26384e" }}>
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} style={{ position: "absolute", left: 40 + i * 140, top: 40, width: 110, height: 100, borderRadius: 14, background: "#f6d98c", opacity: 0.85 }} />
              ))}
              <div style={{ position: "absolute", left: 770, top: 30, width: 150, height: 290, borderRadius: 12, background: "#0a0f15", overflow: "hidden" }}>
                <div style={{ position: "absolute", inset: 0, background: "#f6d98c", opacity: 0.9, clipPath: `inset(0 ${(1 - doors) * 100}% 0 0)` }} />
              </div>
              <div style={{ position: "absolute", right: 14, top: 160, width: 18, height: 34, borderRadius: 9, background: "#fff3c4", boxShadow: "0 0 40px 18px rgba(255,240,200,0.7)" }} />
              <div style={{ position: "absolute", left: 80, bottom: -46, width: 100, height: 100, borderRadius: 50, background: "#05080c", border: "8px solid #1a2330" }} />
              <div style={{ position: "absolute", left: 640, bottom: -46, width: 100, height: 100, borderRadius: 50, background: "#05080c", border: "8px solid #1a2330" }} />
            </div>
          </div>
        )}

        {/* interiors */}
        {!clip && showInt1 && <Interior count={14} at={165} stagger={2} seed={1} u={u} warm={prog(u, 165, 6)} />}
        {!clip && showInt2 && <Interior count={4} at={195} stagger={0} seed={7} u={u} warm={dimOthers} />}

        <Phone u={u} />
        <div style={{ position: "absolute", left: 120, top: 80, color: "#e9edf0", fontSize: 50, fontWeight: 700, opacity: prog(u, 10, 14, outCubic) * dimOthers }}>18:00 · Connaught Place</div>
      </AbsoluteFill>

      {/* the question */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 120, textAlign: "center", opacity: qT }}>
        <Words text="A seat, or an hour on your feet?" start={225} gap={6} size={84} color={C.paper} rise={22} />
      </div>
      <Caption spans={spans} bottom={44} />
      <AbsoluteFill style={{ background: "#000", opacity: blackout }} />
      <Sfx name="ambience" at={0} volume={0.5} len={D} fade={30} />
      <Sfx name="city-ambience" at={0} volume={0.3} len={D} fade={45} />
      <Sfx name="horn" at={96} volume={0.5} len={45} />
      <Sfx name="engine" at={112} volume={0.4} len={110} fade={12} />
      <Sfx name="air-brake" at={140} volume={1} len={60} fade={12} />
      <Sfx name="pop" at={226} volume={0.5} />
      <div style={{ display: "none" }}>{INK}</div>
    </AbsoluteFill>
  );
};
