// Scene 8: limits and what is next. The bar of all weekday bus-km draws on "Most levels are a rough guess" (phrase 0);
// the note on who is missing lands on (1); the Phase 2 cards pop on (2), (3) and (4).
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, CONTENT, RADIUS, SHADOW, TYPE, clamp01, inOutCubic, lerp, prog, springPop, springSoft } from "../design";
import { Backdrop, Captions, Chapter, Counter, FitText, SceneShell, Sfx, fitLine, useBeats } from "../components/kit";

const BAR = { x: CONTENT.left + 40, y: 280, w: CONTENT.width - 80, h: 84 };
const NEXT: [string, string][] = [["More months", "of tickets"], ["An on-bus", "count"], ["GPS stop", "times"], ["Live", "arrivals"]];

export const Scene08: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { beat } = useBeats();
  const [b0, b1, b2, b3, b4] = [0, 1, 2, 3, 4].map((i) => beat(i));
  const many = Number(N.share_many_tickets);
  const rough = Number(N.share_rough);
  const none = Number(N.share_no_data);
  const total = many + rough + none;
  const w1 = (many / total) * BAR.w;
  const w2 = (rough / total) * BAR.w;
  const w3 = (none / total) * BAR.w;
  const g1 = prog(f, b0, 12, inOutCubic);
  const g2 = prog(f, b0 + 8, 22, inOutCubic);
  const g3 = prog(f, b0 + 26, 12, inOutCubic);
  const dimTop = lerp(1, 0.4, prog(f, b2 - 6, 14, inOutCubic));
  const head = springSoft(f, fps, 2, 20);
  const note = springSoft(f, fps, b1, 20);
  const nextHead = springSoft(f, fps, b2 - 4, 20);
  const cardW = (CONTENT.width - 3 * 24) / 4;
  const cardAt = [b2 + 6, b3 + 2, b3 + 14, b4 + 2];
  const bigSize = fitLine(`${N.share_rough}% Rough guess`, TYPE.h1, BAR.w * 0.7, 800);
  return (
    <SceneShell>
      <Backdrop tint={["#5a3a12", C.blue, "#3b2a5c"]} />
      <Chapter n="06" text="Limits, and what is next" />
      <div style={{ opacity: dimTop }}>
        <div style={{ position: "absolute", left: BAR.x, top: 130, width: BAR.w, opacity: head, transform: `translateY(${(1 - head) * 20}px)` }}>
          <FitText text="All weekday bus-km, by how sure each level is" size={TYPE.h2} width={BAR.w} weight={800} color={C.text} />
        </div>
        <div style={{ position: "absolute", left: BAR.x, top: BAR.y, width: BAR.w, height: BAR.h, borderRadius: RADIUS.md, background: "rgba(255,255,255,0.06)", overflow: "hidden", boxShadow: SHADOW.card }}>
          <div style={{ position: "absolute", left: 0, top: 0, width: w1 * g1, height: BAR.h, background: C.teal }} />
          <div style={{ position: "absolute", left: w1, top: 0, width: w2 * g2, height: BAR.h, background: "linear-gradient(90deg,#b45309,#d08a3a)" }} />
          <div style={{ position: "absolute", left: w1 + w2, top: 0, width: w3 * g3, height: BAR.h, background: "repeating-linear-gradient(135deg, rgba(203,213,225,0.35) 0 10px, rgba(203,213,225,0.12) 10px 20px)" }} />
        </div>
        <div style={{ position: "absolute", left: BAR.x, top: BAR.y + BAR.h + 14, opacity: prog(f, b0 + 6, 10) }}>
          <FitText text={`${N.share_many_tickets}% many tickets`} size={TYPE.label} width={420} weight={700} color={C.tealGlow} />
        </div>
        <div style={{ position: "absolute", left: BAR.x + BAR.w - 420, top: BAR.y + BAR.h + 14, opacity: prog(f, b0 + 30, 10) }}>
          <FitText text={`${N.share_no_data}% No data`} size={TYPE.label} width={420} weight={700} color="#cbd5e1" align="right" />
        </div>
        <div style={{ position: "absolute", left: BAR.x, top: 430, width: BAR.w, display: "flex", justifyContent: "center", alignItems: "baseline", gap: 18, opacity: prog(f, b0 + 10, 10) }}>
          <Counter value={rough} at={b0 + 8} dur={30} size={bigSize} color={C.amberGlow} suffix="%" />
          <div style={{ fontSize: bigSize, fontWeight: 800, color: C.text, whiteSpace: "nowrap", letterSpacing: -1 }}>Rough guess</div>
        </div>
        <div style={{ position: "absolute", left: (1920 - 1300) / 2, top: 540, width: 1300, opacity: note, transform: `translateY(${(1 - note) * 16}px)` }}>
          <FitText text={`Buses can be fuller than shown: app tickets are about 1 in ${N.one_in} riders, and women riding free and pass holders are not in this data.`} size={TYPE.body} width={1300} maxLines={2} weight={500} color={C.textDim} align="center" lineHeight={1.3} />
        </div>
      </div>

      <div style={{ position: "absolute", left: CONTENT.left, top: 668, width: CONTENT.width, opacity: nextHead, transform: `translateY(${(1 - nextHead) * 20}px)` }}>
        <FitText text="Next, in Phase 2" size={TYPE.h2} width={CONTENT.width} weight={800} color={C.text} />
      </div>
      {NEXT.map((s, i) => {
        const t = springPop(f, fps, cardAt[i]);
        return (
          <div
            key={s[0]}
            style={{
              position: "absolute",
              left: CONTENT.left + i * (cardW + 24),
              top: 750,
              width: cardW,
              height: 120,
              padding: "0 24px",
              boxSizing: "border-box",
              display: "flex",
              alignItems: "center",
              borderRadius: RADIUS.lg,
              background: "linear-gradient(160deg, rgba(96,165,250,0.22), rgba(96,165,250,0.08))",
              border: `2px solid ${C.blueGlow}88`,
              boxShadow: SHADOW.card,
              opacity: clamp01(t * 2),
              transform: `scale(${0.6 + 0.4 * t})`,
            }}
          >
            <div style={{ fontSize: TYPE.body, fontWeight: 700, color: C.text, lineHeight: 1.15, whiteSpace: "nowrap" }}>
              <div>{s[0]}</div>
              <div>{s[1]}</div>
            </div>
          </div>
        );
      })}
      <Captions />
      <Sfx name="riser" at={b0 - 30} volume={0.3} />
      {cardAt.map((a, i) => (
        <Sfx key={i} name="pop" at={a} volume={0.4} />
      ))}
    </SceneShell>
  );
};
