// Scene 2: the name and the promise. Title on phrase 0, tagline on phrase 1, the four level chips pop on phrase 2
// ("before you board"), each with its pop. A stylised city map draws itself behind, its corridor glowing.
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, CONTENT, Level, TYPE, prog, springSoft } from "../design";
import { Backdrop, Captions, Kinetic, PopChip, SceneShell, Sfx, StylisedMap, useBeats } from "../components/kit";

const FAMILY: Level[] = ["seats", "standing", "crowded", "no_data"];

export const Scene02: React.FC = () => {
  const f = useCurrentFrame();
  const { fps, durationInFrames: D } = useVideoConfig();
  const { beat } = useBeats();
  const titleAt = beat(0) - 4;
  const tagAt = beat(1);
  const chipsAt = beat(2);
  const lift = springSoft(f, fps, tagAt - 6, 26);
  return (
    <SceneShell>
      <Backdrop tint={[C.blue, C.teal, "#3b2a5c"]} />
      <StylisedMap draw={prog(f, 0, D * 0.9)} glow={prog(f, tagAt, 40)} opacity={0.55} />
      <div style={{ position: "absolute", left: CONTENT.left, top: 300 - lift * 70, width: CONTENT.width }}>
        <Kinetic text="Delhi Bus Crowding Planner" at={titleAt} size={TYPE.display} width={CONTENT.width} maxLines={1} stagger={5} align="center" accent={{ crowding: C.tealGlow }} />
      </div>
      <div style={{ position: "absolute", left: (1920 - 1300) / 2, top: 440 - lift * 50, width: 1300 }}>
        <Kinetic text="How crowded each stretch of your trip usually is, before you board." at={tagAt} size={TYPE.h2} width={1300} maxLines={2} stagger={2} weight={500} align="center" color={C.textDim} accent={{ usually: C.text }} />
      </div>
      <div style={{ position: "absolute", left: CONTENT.left, top: 650, width: CONTENT.width, height: 80, display: "flex", justifyContent: "center", alignItems: "center", gap: 24 }}>
        {FAMILY.map((lv, i) => (
          <PopChip key={lv} level={lv} at={chipsAt + i * 6} size={TYPE.body} style={{ transformOrigin: "center" }} />
        ))}
      </div>
      <Captions />
      <Sfx name="chime" at={titleAt + 2} volume={0.6} />
      {FAMILY.map((_, i) => (
        <Sfx key={i} name="pop" at={chipsAt + i * 6} volume={0.45} />
      ))}
    </SceneShell>
  );
};
