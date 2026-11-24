import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import N from "../numbers.json";
import { C, inOutCubic, lerp, outCubic, prog, springSoft } from "../theme";
import { Caption, Scene, Sfx, useClock } from "../components/ui";
import { sceneCaptionSpans } from "../captions";
import { LEAD_FRAMES } from "../timing";
import { useAssets } from "../assets";

const BAR_X = 260;
const BAR_W = 1400;
const NEXT = ["More months of tickets", "An on-bus count", "GPS stop times", "Live arrivals"];

export const Scene08: React.FC = () => {
  const u = useClock(390);
  const f = useCurrentFrame();
  const { fps, durationInFrames: D } = useVideoConfig();
  const { vo } = useAssets();
  const many = Number(N.share_many_tickets);
  const rough = Number(N.share_rough);
  const none = Number(N.share_no_data);
  const total = many + rough + none;
  const w1 = (many / total) * BAR_W;
  const w2 = (rough / total) * BAR_W;
  const w3 = (none / total) * BAR_W;
  const g1 = prog(u, 0, 30, inOutCubic);
  const g2 = prog(u, 30, 30, inOutCubic);
  const g3 = prog(u, 60, 30, inOutCubic);
  const slide = prog(u, 150, 30, inOutCubic);
  const barY = lerp(400, 170, slide);
  const barOpacity = lerp(1, 0.28, slide);
  const out = 1 - prog(u, 378, 12);
  const spans = sceneCaptionSpans(8, { voFrames: vo[7] != null ? Math.round(vo[7]! * 30) : null, duration: D, base: 390, lead: LEAD_FRAMES });
  void f;
  return (
    <Scene fadeIn={0} fadeOut={0}>
      <div style={{ position: "absolute", inset: 0, opacity: out }}>
        <div style={{ position: "absolute", left: BAR_X, top: barY - 200, fontSize: 56, fontWeight: 700, color: C.ink, opacity: 1 - slide, whiteSpace: "nowrap" }}>All scheduled bus-km</div>
        <div style={{ position: "absolute", left: BAR_X, top: barY, width: BAR_W, height: 100, opacity: barOpacity }}>
          <div style={{ position: "absolute", left: 0, top: 0, width: w1 * g1, height: 100, background: C.teal, borderRadius: "14px 0 0 14px" }} />
          <div style={{ position: "absolute", left: w1, top: 0, width: w2 * g2, height: 100, background: "#c9893f" }} />
          <div style={{ position: "absolute", left: w1 + w2, top: 0, width: w3 * g3, height: 100, display: g3 > 0.02 ? "block" : "none", border: `5px dashed ${C.grey}`, borderLeft: "none", background: C.greyBg, borderRadius: "0 14px 14px 0", boxSizing: "border-box" }} />
          {/* labels */}
          <div style={{ position: "absolute", left: 0, top: -92, opacity: prog(u, 26, 12, outCubic), fontSize: 44, fontWeight: 700, color: C.teal, whiteSpace: "nowrap" }}>
            {N.share_many_tickets}% many tickets
            <div style={{ width: 4, height: 38, background: C.teal, marginLeft: 20, marginTop: 4 }} />
          </div>
          <div style={{ position: "absolute", left: w1 + w2 / 2 - 400, width: 800, top: 120, opacity: prog(u, 56, 12, outCubic) * (1 - slide), fontSize: 60, fontWeight: 700, color: "#8a5a1d", textAlign: "center", whiteSpace: "nowrap" }}>{N.share_rough}% Rough guess</div>
          <div style={{ position: "absolute", right: 0, top: -92, opacity: prog(u, 86, 12, outCubic), fontSize: 44, fontWeight: 700, color: C.grey, whiteSpace: "nowrap", textAlign: "right" }}>
            {N.share_no_data}% No data
            <div style={{ width: 4, height: 38, background: C.grey, marginRight: 30, marginTop: 4, marginLeft: "auto" }} />
          </div>
        </div>
        <div style={{ position: "absolute", left: BAR_X, top: barY + 240, width: BAR_W, fontSize: 38, color: C.grey, lineHeight: 1.3, opacity: prog(u, 100, 14, outCubic) * (1 - slide) }}>
          about 1 in {N.one_in} riders, women riding free and pass holders not in this data
        </div>

        <div style={{ position: "absolute", left: 0, right: 0, top: 400, textAlign: "center", fontSize: 60, fontWeight: 700, color: C.blue, opacity: prog(u, 160, 12, outCubic) }}>Next, in Phase 2</div>
        <div style={{ position: "absolute", left: 260, top: 510, width: 1400, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 34 }}>
          {NEXT.map((s, i) => {
            const t = springSoft(u, fps, 176 + i * 8, 20);
            return (
              <div key={s} style={{ opacity: t, transform: `scale(${0.8 + 0.2 * t})`, padding: "28px 36px", borderRadius: 30, background: C.white, border: `5px solid ${C.blue}`, fontSize: 52, fontWeight: 700, color: C.blue, textAlign: "center", boxShadow: "0 12px 30px rgba(13,17,23,0.10)" }}>
                {s}
              </div>
            );
          })}
        </div>
      </div>
      <Caption spans={spans} bottom={30} />
      <Sfx name="riser" at={0} volume={0.4} />
      <Sfx name="pop" at={176} volume={0.5} />
    </Scene>
  );
};
