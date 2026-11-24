import React from "react";
import { useVideoConfig } from "remotion";
import { evolvePath, getLength, getPointAtLength } from "@remotion/paths";
import N from "../numbers.json";
import { C, fmt, inOutCubic, lerp, linear, outCubic, prog, springSoft } from "../theme";
import { Caption, Scene, Sfx, useClock } from "../components/ui";
import { sceneCaptionSpans } from "../captions";
import { LEAD_FRAMES } from "../timing";
import { useAssets } from "../assets";

const STAGES = ["clean", "resolve", "network", "GPS trips", "stretch riders", "alighting", "supply", "scale up", "levels", "operator rank", "validate", "render"];
const BOX = { x: 580, y: 250, w: 640, h: 560 };
const SRC = [
  { y: 290, h: 190, label: "ONDC app tickets", color: C.teal },
  { y: 520, h: 120, label: "GTFS timetable", color: C.blue },
  { y: 680, h: 120, label: "GPS feed", color: C.amber },
];
const SRC_X = 60;
const SRC_W = 430;
const OUT = { x: 1300, y: 420, w: 250, h: 160 };
const SCREENS = ["commuter", "operator", "live demo"];

const pathFor = (i: number) => {
  const y1 = SRC[i].y + SRC[i].h / 2;
  const y2 = BOX.y + 130 + i * 150;
  return `M ${SRC_X + SRC_W} ${y1} C ${SRC_X + SRC_W + 40} ${y1}, ${BOX.x - 40} ${y2}, ${BOX.x} ${y2}`;
};
const outPath = (i: number) => {
  const y2 = 390 + i * 150;
  return `M ${OUT.x + OUT.w} ${OUT.y + OUT.h / 2} C ${OUT.x + OUT.w + 40} ${OUT.y + OUT.h / 2}, ${1590} ${y2}, ${1640} ${y2}`;
};

export const Scene03: React.FC = () => {
  const u = useClock(450);
  const { fps, durationInFrames: D } = useVideoConfig();
  const { vo } = useAssets();

  const titleT = prog(u, 36, 24, inOutCubic);
  const titleY = lerp(400, 90, titleT);
  const titleSize = lerp(112, 56, titleT);
  const dim = lerp(1, 0.25, prog(u, 330, 24, inOutCubic));
  const push = lerp(1, 1.4, prog(u, 330, 60, inOutCubic));
  const counter = Math.round(N.tickets * prog(u, 80, 60, outCubic));

  const spans = sceneCaptionSpans(3, { voFrames: vo[2] != null ? Math.round(vo[2]! * 30) : null, duration: D, base: 450, lead: LEAD_FRAMES });

  return (
    <Scene fadeIn={0} fadeOut={6}>
      <div style={{ position: "absolute", inset: 0, transform: `scale(${push})`, transformOrigin: `${BOX.x + BOX.w / 2}px ${BOX.y + BOX.h / 2}px` }}>
        <div style={{ position: "absolute", left: 0, right: 0, top: titleY, textAlign: "center", fontWeight: 700, fontSize: titleSize, lineHeight: 1.1, color: C.ink, padding: "0 200px" }}>
          {u < 36 ? (
            <>
              {"Nobody counts people".split(" ").map((w, i) => (
                <span key={i} style={{ display: "inline-block", marginRight: titleSize * 0.26, opacity: prog(u, i * 6, 12, outCubic), transform: `translateY(${(1 - prog(u, i * 6, 12, outCubic)) * 24}px)` }}>{w}</span>
              ))}
              <br />
              {"on Delhi buses".split(" ").map((w, i) => (
                <span key={i} style={{ display: "inline-block", marginRight: titleSize * 0.26, opacity: prog(u, 18 + i * 6, 12, outCubic), transform: `translateY(${(1 - prog(u, 18 + i * 6, 12, outCubic)) * 24}px)` }}>{w}</span>
              ))}
            </>
          ) : (
            "Nobody counts people on Delhi buses"
          )}
        </div>

        {/* source cards */}
        {SRC.map((s, i) => {
          const t = springSoft(u, fps, 60 + i * 12, 20);
          return (
            <div key={s.label} style={{ position: "absolute", left: SRC_X, top: s.y, width: SRC_W, height: s.h, borderRadius: 26, background: C.white, border: `5px solid ${s.color}`, boxShadow: "0 12px 30px rgba(13,17,23,0.10)", transform: `translateX(${(1 - t) * -520}px)`, opacity: t * (i === 0 ? 1 : dim), padding: "16px 26px", boxSizing: "border-box" }}>
              <div style={{ fontSize: 38, fontWeight: 700, color: s.color }}>{s.label}</div>
              {i === 0 ? (
                <>
                  <div style={{ fontSize: 64, fontWeight: 700, color: C.ink, fontVariantNumeric: "tabular-nums", lineHeight: 1.15 }}>{fmt(counter)}</div>
                  <div style={{ fontSize: 36, color: C.grey }}>October 2026</div>
                </>
              ) : (
                <div style={{ fontSize: 34, color: C.grey, marginTop: 8 }}>{i === 1 ? "scheduled trips" : "where buses ran"}</div>
              )}
            </div>
          );
        })}

        {/* arrows and packets */}
        <svg width={1920} height={1080} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
          {SRC.map((s, i) => {
            const d = pathFor(i);
            const ev = evolvePath(prog(u, 150 + i * 8, 24, inOutCubic), d);
            const len = getLength(d);
            const packets = [] as React.ReactNode[];
            for (let k = 0; k < 8; k++) {
              const start = 190 + i * 6 + k * 18;
              const t = (u - start) / 60;
              if (t < 0 || t > 1) continue;
              const p = getPointAtLength(d, linear(t) * len);
              if (!p) continue;
              packets.push(<circle key={k} cx={p.x} cy={p.y} r={7} fill={C.teal} opacity={Math.min(1, t * 6, (1 - t) * 6)} />);
            }
            return (
              <g key={i} opacity={i === 0 ? 1 : dim}>
                <path d={d} fill="none" stroke={s.color} strokeWidth={5} strokeLinecap="round" strokeDasharray={ev.strokeDasharray} strokeDashoffset={ev.strokeDashoffset} />
                {packets}
              </g>
            );
          })}
          {SCREENS.map((_, i) => {
            const d = outPath(i);
            const ev = evolvePath(prog(u, 262 + i * 8, 24, inOutCubic), d);
            const len = getLength(d);
            const packets = [] as React.ReactNode[];
            for (let k = 0; k < 4; k++) {
              const start = 296 + i * 6 + k * 18;
              const t = (u - start) / 36;
              if (t < 0 || t > 1) continue;
              const p = getPointAtLength(d, t * len);
              if (!p) continue;
              packets.push(<circle key={k} cx={p.x} cy={p.y} r={7} fill={C.teal} opacity={Math.min(1, t * 6, (1 - t) * 6)} />);
            }
            return (
              <g key={i} opacity={dim}>
                <path d={d} fill="none" stroke={C.grey} strokeWidth={4} strokeLinecap="round" strokeDasharray={ev.strokeDasharray} strokeDashoffset={ev.strokeDashoffset} />
                {packets}
              </g>
            );
          })}
        </svg>

        {/* pipeline lane */}
        <div style={{ position: "absolute", left: BOX.x, top: BOX.y, width: BOX.w, height: BOX.h, borderRadius: 34, background: C.white, border: `5px solid ${C.blue}`, boxShadow: "0 18px 50px rgba(13,17,23,0.12)", opacity: prog(u, 120, 20, outCubic), padding: 22, boxSizing: "border-box" }}>
          <div style={{ fontSize: 38, fontWeight: 700, color: C.blue, marginBottom: 12 }}>The pipeline</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {STAGES.map((s, i) => {
              const on = prog(u, 196 + i * 8, 12, outCubic);
              return (
                <div key={s} style={{ height: 62, borderRadius: 16, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, fontWeight: 700, color: on > 0.5 ? C.white : C.grey, background: on > 0 ? `color-mix(in srgb, ${C.teal} ${Math.round(on * 100)}%, ${C.paperDeep})` : C.paperDeep, boxShadow: on > 0 ? `0 0 ${24 * on}px ${C.teal}66` : "none", opacity: i < 1 ? 1 : lerp(1, dim, prog(u, 330, 24)) }}>
                  {s}
                </div>
              );
            })}
          </div>
        </div>

        {/* planner and the three screens */}
        <div style={{ position: "absolute", left: OUT.x, top: OUT.y, width: OUT.w, height: OUT.h, borderRadius: 26, background: C.blue, color: C.paper, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", fontSize: 40, fontWeight: 700, lineHeight: 1.15, padding: 18, opacity: prog(u, 250, 18, outCubic) * dim, boxSizing: "border-box" }}>Planner and API</div>
        {SCREENS.map((s, i) => {
          const t = springSoft(u, fps, 288 + i * 10, 20);
          return (
            <div key={s} style={{ position: "absolute", left: 1640, top: 345 + i * 150, width: 250, height: 90, borderRadius: 18, background: C.white, border: `4px solid ${C.blue}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 34, fontWeight: 700, color: C.blue, opacity: t * dim, transform: `scale(${0.7 + 0.3 * t})` }}>
              {s}
            </div>
          );
        })}
      </div>
      <Caption spans={spans} bottom={30} />
      {SRC.map((_, i) => (
        <Sfx key={i} name="pop" at={64 + i * 12} volume={0.35} />
      ))}
    </Scene>
  );
};
