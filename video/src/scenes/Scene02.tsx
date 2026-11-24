import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, outCubic, prog, springSoft } from "../theme";
import { Caption, Chip, FadeIn, Scene, Sfx, Words } from "../components/ui";
import { SCENE_CAPTIONS, chunkSpans } from "../captions";
import { LEAD_FRAMES } from "../timing";
import { useAssets } from "../assets";
import type { Level } from "../theme";

const FAMILY: Level[] = ["seats", "standing", "crowded", "no_data"];

export const Scene02: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, durationInFrames: D } = useVideoConfig();
  const { vo } = useAssets();
  const wipe = prog(f, 0, 15, outCubic);
  const speechEnd = vo[1] != null ? Math.round(vo[1]! * 30) : D - 40;
  const spans = chunkSpans(SCENE_CAPTIONS[1], LEAD_FRAMES + 6, Math.max(speechEnd, 150));
  return (
    <Scene fadeOut={12} bg={C.paper}>
      <div style={{ position: "absolute", inset: 0, background: C.paper, clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)` }}>
        <div style={{ position: "absolute", top: 230, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center" }}>
          <Words text="Delhi Bus Crowding Planner" size={116} color={C.blue} start={0} gap={8} rise={24} dur={12} />
          <FadeIn at={60} dur={12} rise={10} style={{ marginTop: 34, textAlign: "center", fontSize: 50, color: C.ink, lineHeight: 1.25 }}>
            <div>How crowded each stretch of your trip usually is,</div>
          </FadeIn>
          <FadeIn at={72} dur={12} rise={10} style={{ textAlign: "center", fontSize: 50, color: C.ink, lineHeight: 1.25 }}>
            <div>before you board.</div>
          </FadeIn>
          <div style={{ display: "flex", gap: 26, marginTop: 70 }}>
            {FAMILY.map((lv, i) => {
              const t = springSoft(f, fps, 120 + i * 6, 20);
              return (
                <div key={lv} style={{ opacity: t, transform: `scale(${0.5 + 0.5 * t})` }}>
                  <Chip level={lv} size={38} />
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <Caption spans={spans} bottom={44} />
      <Sfx name="chime" at={4} volume={0.35} />
    </Scene>
  );
};
