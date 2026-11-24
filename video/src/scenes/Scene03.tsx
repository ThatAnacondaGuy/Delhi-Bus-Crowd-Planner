// Scene 3: what we have. "Nobody counts..." (phrase 0); three sources arrive on "what is recorded" (1); the ticket counter
// runs on "two and a half million app tickets" (2); "October 2026" lands on (3); timetable and GPS flow into the match on (4).
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { evolvePath, getLength, getPointAtLength } from "@remotion/paths";
import N from "../numbers.json";
import { C, CONTENT, RADIUS, SHADOW, TYPE, clamp01, inOutCubic, lerp, outCubic, prog, springPop, springSoft } from "../design";
import { Backdrop, Captions, Chapter, Counter, FitText, Kinetic, SceneShell, Sfx, fitLine, useBeats } from "../components/kit";

const CARD_X = CONTENT.left;
const CARD_W = 560;
const PAD = 32;
const CARDS = [
  { y: 230, h: 250, title: "ONDC app tickets", sub: "", color: C.tealGlow },
  { y: 510, h: 150, title: "GTFS timetable", sub: "every scheduled trip", color: C.blueGlow },
  { y: 690, h: 150, title: "GPS feed", sub: "where buses ran", color: C.amberGlow },
];
const HUB = { x: 1010, y: 535, r: 120 };
const OUT = { x: 1300, y: 300, w: 524, h: 470 };

const inPath = (i: number) => {
  const c = CARDS[i];
  const y1 = c.y + c.h / 2;
  const y2 = HUB.y + (i - 1) * 60;
  return `M ${CARD_X + CARD_W + 10} ${y1} C ${CARD_X + CARD_W + 160} ${y1}, ${HUB.x - HUB.r - 140} ${y2}, ${HUB.x - HUB.r + 6} ${y2}`;
};
const OUT_PATH = `M ${HUB.x + HUB.r - 6} ${HUB.y} C ${HUB.x + HUB.r + 60} ${HUB.y}, ${OUT.x - 60} ${OUT.y + OUT.h / 2}, ${OUT.x - 8} ${OUT.y + OUT.h / 2}`;

const Flow: React.FC<{ d: string; at: number; color: string; every?: number; width?: number }> = ({ d, at, color, every = 9, width = 4 }) => {
  const f = useCurrentFrame();
  const ev = evolvePath(prog(f, at, 20, inOutCubic), d);
  const len = getLength(d);
  const packets: React.ReactNode[] = [];
  for (let k = 0; k < 40; k++) {
    const st = at + 14 + k * every;
    const t = (f - st) / 34;
    if (t < 0 || t > 1) continue;
    const p = getPointAtLength(d, t * len);
    if (!p) continue;
    packets.push(<circle key={k} cx={p.x} cy={p.y} r={7} fill={color} opacity={Math.min(1, t * 5, (1 - t) * 5)} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />);
  }
  return (
    <g>
      <path d={d} fill="none" stroke={color} strokeOpacity={0.55} strokeWidth={width} strokeLinecap="round" strokeDasharray={ev.strokeDasharray} strokeDashoffset={ev.strokeDashoffset} />
      {packets}
    </g>
  );
};

export const Scene03: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { beat } = useBeats();
  const b0 = beat(0);
  const b1 = beat(1);
  const b2 = beat(2);
  const b3 = beat(3);
  const b4 = beat(4);

  // the headline: centred, then up and smaller as the sources arrive
  const up = springSoft(f, fps, b1 - 8, 26);
  const headScale = lerp(1, TYPE.h2 / TYPE.h1, up);
  const headTop = lerp(430, 112, up);
  const numSize = fitLine(Number(N.tickets).toLocaleString("en-US"), TYPE.stat, CARD_W - 2 * PAD, 800);
  const oct = springPop(f, fps, b3);
  const hub = springSoft(f, fps, b4 + 6, 24);
  const out = springSoft(f, fps, b4 + 30, 24);

  return (
    <SceneShell>
      <Backdrop tint={[C.teal, C.blue, "#2b2350"]} />
      <Chapter n="01" text="The data" />
      <div style={{ position: "absolute", left: CONTENT.left, top: headTop, width: CONTENT.width, transform: `scale(${headScale})`, transformOrigin: "50% 0" }}>
        <Kinetic text="Nobody counts people on Delhi buses." at={b0 - 4} size={TYPE.h1} width={CONTENT.width} maxLines={1} stagger={4} align="center" accent={{ nobody: C.amberGlow }} />
      </div>

      {/* sources */}
      {CARDS.map((c, i) => {
        const t = springSoft(f, fps, b1 + i * 7, 22);
        const lit = i === 0 ? 1 : lerp(0.55, 1, prog(f, b4, 14));
        return (
          <div
            key={c.title}
            style={{
              position: "absolute",
              left: CARD_X,
              top: c.y,
              width: CARD_W,
              height: c.h,
              padding: `24px ${PAD}px`,
              boxSizing: "border-box",
              borderRadius: RADIUS.lg,
              background: "linear-gradient(160deg, rgba(255,255,255,0.10), rgba(255,255,255,0.04))",
              border: `2px solid ${c.color}55`,
              boxShadow: SHADOW.card,
              transform: `translateX(${(1 - t) * -120}px)`,
              opacity: t * lit,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{ width: 14, height: 14, borderRadius: 7, background: c.color, boxShadow: `0 0 14px ${c.color}` }} />
              <FitText text={c.title} size={TYPE.body} width={CARD_W - 2 * PAD - 28} color={C.text} />
            </div>
            {i === 0 ? (
              <>
                <Counter value={N.tickets} at={b2} dur={46} size={numSize} color={C.text} style={{ marginTop: 14 }} />
                <div style={{ display: "inline-block", marginTop: 14, padding: "6px 18px", borderRadius: RADIUS.pill, background: `${C.tealGlow}22`, border: `2px solid ${C.tealGlow}88`, color: C.tealGlow, fontSize: TYPE.label, fontWeight: 700, transform: `scale(${0.5 + 0.5 * oct})`, transformOrigin: "left center", opacity: clamp01(oct * 2) }}>
                  October 2026
                </div>
              </>
            ) : (
              <FitText text={c.sub} size={TYPE.label} width={CARD_W - 2 * PAD} weight={500} color={C.textDim} style={{ marginTop: 14 }} />
            )}
          </div>
        );
      })}

      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <Flow d={inPath(0)} at={b2 + 4} color={C.tealGlow} />
        <Flow d={inPath(1)} at={b4} color={C.blueGlow} every={12} />
        <Flow d={inPath(2)} at={b4 + 6} color={C.amberGlow} every={12} />
        <Flow d={OUT_PATH} at={b4 + 26} color={C.tealGlow} every={7} width={5} />
      </svg>

      {/* the match */}
      <div
        style={{
          position: "absolute",
          left: HUB.x - HUB.r,
          top: HUB.y - HUB.r,
          width: 2 * HUB.r,
          height: 2 * HUB.r,
          borderRadius: "50%",
          background: `radial-gradient(circle at 35% 30%, ${C.blue}, #0c1a33)`,
          border: `3px solid ${C.blueGlow}`,
          boxShadow: `0 0 ${60 * hub}px ${C.blueGlow}88, ${SHADOW.card}`,
          transform: `scale(${0.6 + 0.4 * hub})`,
          opacity: clamp01(hub * 1.4),
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <FitText text="Matched" size={TYPE.body} width={2 * HUB.r - 40} align="center" color={C.text} />
      </div>

      {/* out: every stretch of every trip, every half hour */}
      <div style={{ position: "absolute", left: OUT.x, top: OUT.y, width: OUT.w, height: OUT.h, padding: 28, boxSizing: "border-box", borderRadius: RADIUS.lg, background: "rgba(255,255,255,0.06)", border: "2px solid rgba(255,255,255,0.12)", boxShadow: SHADOW.card, opacity: out, transform: `translateY(${(1 - out) * 30}px)` }}>
        <FitText text="Every stretch, every half hour" size={TYPE.body} width={OUT.w - 56} maxLines={2} color={C.text} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 6, marginTop: 22 }}>
          {Array.from({ length: 84 }, (_, k) => {
            const col = k % 12;
            const row = Math.floor(k / 12);
            const v = Math.sin(col * 0.55 + row * 0.9) + Math.sin(col * 0.21 - row * 0.4) + (col > 3 && col < 8 ? 0.8 : 0);
            const lv = v > 1.2 ? C.red : v > 0.2 ? C.amber : C.teal;
            const on = prog(f, b4 + 34 + col * 2 + row * 3, 8);
            return <div key={k} style={{ height: 30, borderRadius: 6, background: on > 0 ? lv : "rgba(255,255,255,0.08)", opacity: lerp(0.35, 1, on) }} />;
          })}
        </div>
      </div>

      <Captions />
      <Sfx name="pop" at={b1} volume={0.35} />
      <Sfx name="pop" at={b1 + 7} volume={0.3} />
      <Sfx name="pop" at={b1 + 14} volume={0.3} />
      <Sfx name="tap" at={b3} volume={0.35} />
      <Sfx name="chime" at={b4 + 8} volume={0.45} />
      <div style={{ display: "none" }}>{outCubic(0)}</div>
    </SceneShell>
  );
};
