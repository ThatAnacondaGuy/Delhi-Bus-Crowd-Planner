import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, inOutCubic, lerp, outCubic, prog, springSoft } from "../theme";
import { Caption, Chip, Scene, Sfx, useClock } from "../components/ui";
import { Person } from "../components/Person";
import { SCENE_CAPTIONS, sceneSpans } from "../captions";
import { LEAD_FRAMES } from "../timing";
import { useAssets } from "../assets";

const STOPS = ["A", "B", "C", "D"];
const X0 = 380;
const DX = 400;
const LY = 560; // the line
const stopX = (i: number) => X0 + i * DX;

const Badge: React.FC<{ n: number; at: number; u: number; text: string; sub?: string }> = ({ n, at, u, text, sub }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = springSoft(u, fps, at, 14);
  const o = prog(u, at + 4, 14, outCubic);
  void f;
  return (
    <div style={{ position: "absolute", left: 110, top: 86, display: "flex", alignItems: "center", gap: 28, opacity: Math.min(1, s * 1.5) }}>
      <div style={{ width: 86, height: 86, borderRadius: 43, background: C.blue, color: C.paper, fontSize: 52, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${0.4 + 0.6 * s})` }}>{n}</div>
      <div style={{ opacity: o }}>
        <div style={{ fontSize: 58, fontWeight: 700, color: C.ink, lineHeight: 1.05 }}>{text}</div>
        {sub ? <div style={{ fontSize: 40, color: C.grey, marginTop: 4 }}>{sub}</div> : null}
      </div>
    </div>
  );
};

const Clock: React.FC<{ x: number; y: number; angle: number; t: number }> = ({ x, y, angle, t }) => (
  <svg width={64} height={64} viewBox="0 0 64 64" style={{ position: "absolute", left: x - 32, top: y, opacity: t }}>
    <circle cx="32" cy="32" r="28" fill={C.white} stroke={C.blue} strokeWidth="4" />
    <line x1="32" y1="32" x2="32" y2="12" stroke={C.ink} strokeWidth="4" strokeLinecap="round" transform={`rotate(${angle} 32 32)`} />
    <line x1="32" y1="32" x2="44" y2="32" stroke={C.ink} strokeWidth="4" strokeLinecap="round" transform={`rotate(${angle * 0.3 - 60} 32 32)`} />
  </svg>
);

export const Scene04: React.FC = () => {
  const u = useClock(720);
  const { fps, durationInFrames: D } = useVideoConfig();
  const { vo } = useAssets();
  const step = Math.min(4, Math.floor(u / 144));
  const local = u - step * 144;

  // ---- line and stops (step 1)
  const lineT = prog(u, 18, 36, inOutCubic);
  const ticketT = prog(u, 0, 18, outCubic);

  // ---- bar geometry (step 4)
  const BAR_X = 380;
  const BAR_W = 1160;
  const seatsW = 0.4 * BAR_W;
  const ratedW = 0.6 * BAR_W;
  const barY = 560;
  const markerFrom = BAR_X + 20;
  const markerTo = BAR_X + seatsW + ratedW * 0.4; // a bit past the seats: standing
  const marker = lerp(markerFrom, markerTo, prog(u, 432 + 60, 30, inOutCubic));

  const stepFade = (a: number, b: number) => prog(u, a, 8) * (1 - prog(u, b - 8, 8));

  // ---- crowd (step 3)
  const crowd = Array.from({ length: N.one_in }, (_, i) => i);
  const COLS = 11;

  // ---- final chip (step 5)
  const chipT = prog(u, 576, 18, outCubic);
  const grow = prog(u, 696, 24, inOutCubic); // last 24 frames: scale up to fill the middle
  const chipScale = lerp(0.6, 1, chipT) * lerp(1, 2.1, grow);

  const spans = sceneSpans(4, SCENE_CAPTIONS[3], vo[3] != null ? Math.round(vo[3]! * 30) : null, 720, D, LEAD_FRAMES);

  return (
    <Scene fadeIn={12} fadeOut={0}>
      {/* captions per step */}
      {step === 0 && <Badge n={1} at={0} u={local} text="A ticket" sub="where a rider got on, and where they got off" />}
      {step === 1 && <Badge n={2} at={0} u={local} text="Spread over the stretches" sub="each stretch at the time the bus passed" />}
      {step === 2 && <Badge n={3} at={0} u={local} text="Scaled up to everyone on board" sub={`about 1 in ${N.one_in} riders`} />}
      {step === 3 && <Badge n={4} at={0} u={local} text="Against seats and rated total" />}
      {step === 4 && <Badge n={5} at={0} u={local} text="One word, three dots, a colour" />}

      {/* the line, the stops and the ticket (steps 1 and 2) */}
      <div style={{ position: "absolute", inset: 0, opacity: stepFade(0, 300) + (u < 300 ? 0 : 0) }}>
        <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
          <line x1={stopX(0)} y1={LY} x2={lerp(stopX(0), stopX(3), lineT)} y2={LY} stroke={C.grey} strokeWidth={8} strokeLinecap="round" />
          {STOPS.map((s, i) => {
            const t = prog(u, 18 + i * 8, 10, outCubic);
            return (
              <g key={s} opacity={t}>
                <circle cx={stopX(i)} cy={LY} r={26} fill={C.white} stroke={C.ink} strokeWidth={6} />
                <text x={stopX(i)} y={LY + 80} textAnchor="middle" fontSize={44} fontWeight={700} fill={C.ink}>
                  Stop {s}
                </text>
              </g>
            );
          })}
          {/* teal bars, stretch by stretch (step 2) */}
          {[0, 1, 2].map((i) => {
            const t = prog(u, 144 + i * 24, 24, inOutCubic);
            const th = lerp(4, 14, t);
            return <line key={i} x1={stopX(i)} y1={LY} x2={lerp(stopX(i), stopX(i + 1), t)} y2={LY} stroke={C.teal} strokeWidth={t > 0 ? th : 0} strokeLinecap="round" />;
          })}
        </svg>
        {[0, 1, 2].map((i) => (
          <Clock key={i} x={(stopX(i) + stopX(i + 1)) / 2} y={LY + 40} angle={[40, 150, 260][i]} t={prog(u, 144 + i * 24 + 14, 12)} />
        ))}
        <div
          style={{
            position: "absolute",
            left: lerp(-700, stopX(0) - 150, ticketT),
            top: 250,
            width: 640,
            padding: "22px 34px",
            borderRadius: 24,
            background: C.white,
            border: `5px solid ${C.blue}`,
            boxShadow: "0 14px 40px rgba(13,17,23,0.12)",
            opacity: 1 - prog(u, 136, 8) * 0.55,
          }}
        >
          <div style={{ fontSize: 52, fontWeight: 700, color: C.blue }}>Stop A → Stop D</div>
          <div style={{ fontSize: 36, color: C.grey, marginTop: 4 }}>boarding → alighting</div>
        </div>
      </div>

      {/* step 3: one rider becomes the people on board */}
      <div style={{ position: "absolute", inset: 0, opacity: stepFade(288, 440) }}>
        <div style={{ position: "absolute", left: 420, top: 300, width: 1080, height: 480, border: `8px solid ${C.ink}`, borderRadius: 40, background: C.white }} />
        <div style={{ position: "absolute", left: 420, top: 300, width: 1080, height: 480 }}>
          {crowd.map((i) => {
            const col = i % COLS;
            const row = Math.floor(i / COLS);
            const t = i === 0 ? prog(u, 292, 10, outCubic) : springSoft(u, fps, 312 + (i - 1) * 1.1, 14);
            const x = 58 + col * 90;
            const y = 40 + row * 105;
            return <Person key={i} x={x} y={y} size={86} color={i === 0 ? C.teal : "#9aa3ab"} opacity={t} />;
          })}
        </div>
        <div style={{ position: "absolute", left: 420, top: 810, width: 1080, textAlign: "center", fontSize: 44, color: C.grey, opacity: prog(u, 372, 14, outCubic) }}>never more than a bus can hold</div>
      </div>
      <Sfx name="riser" at={288} volume={0.3} />

      {/* step 4: seats, rated total and the marker */}
      <div style={{ position: "absolute", inset: 0, opacity: stepFade(432, 590) }}>
        <div style={{ position: "absolute", left: BAR_X, top: barY, width: BAR_W, height: 80, borderRadius: 40, background: "#e3e1d9" }} />
        <div style={{ position: "absolute", left: BAR_X, top: barY, width: seatsW * prog(u, 440, 30, inOutCubic), height: 80, borderRadius: 40, background: C.teal }} />
        <div style={{ position: "absolute", left: BAR_X + seatsW, top: barY, width: ratedW * prog(u, 470, 30, inOutCubic), height: 80, background: C.amber, borderRadius: "0 40px 40px 0" }} />
        <div style={{ position: "absolute", left: BAR_X, top: barY + 104, fontSize: 44, fontWeight: 700, color: C.teal, opacity: prog(u, 456, 12) }}>seats</div>
        <div style={{ position: "absolute", left: BAR_X + seatsW + 30, top: barY + 104, fontSize: 44, fontWeight: 700, color: C.amber, opacity: prog(u, 486, 12) }}>standing places, up to the rated total</div>
        <div style={{ position: "absolute", left: marker - 5, top: barY - 90, width: 10, height: 140, background: C.ink, borderRadius: 5, opacity: prog(u, 492, 10) }} />
        <div style={{ position: "absolute", left: marker - 130, top: barY - 150, width: 260, textAlign: "center", fontSize: 40, fontWeight: 700, color: C.ink, opacity: prog(u, 492, 10) }}>people on board</div>
      </div>
      <Sfx name="pop" at={432} volume={0.3} />

      {/* step 5: the level */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 440, display: "flex", justifyContent: "center", opacity: chipT }}>
        <div style={{ transform: `scale(${chipScale})` }}>
          <Chip level="standing" size={110} glow={chipT} />
        </div>
      </div>

      {[0, 144, 288, 432, 576].map((t, i) => (
        <Sfx key={i} name="tap" at={t + 4} volume={0.3} />
      ))}
      <Caption spans={spans} bottom={30} />
    </Scene>
  );
};
