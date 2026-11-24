import React from "react";
import { AbsoluteFill } from "remotion";
import { C } from "./design";
import { FONT, FontGate } from "./fonts";
import { Chip, FitText, Grain, Phone, Shot, World } from "./components/kit";
import { cards, capMeta, capUrl, cy } from "./captures";

const Inner: React.FC = () => {
  const m = capMeta("m-j4-full");
  const cs = cards("m-j4-full");
  return (
    <AbsoluteFill style={{ background: `radial-gradient(900px 600px at 25% 30%, ${C.blue}aa, transparent 70%), radial-gradient(700px 500px at 90% 90%, ${C.teal}88, transparent 70%), linear-gradient(165deg, ${C.duskMid}, ${C.dusk})`, fontFamily: FONT }}>
      <div style={{ position: "absolute", left: 64, top: 70, width: 700 }}>
        <FitText text="Delhi Bus" size={84} width={700} weight={800} color={C.text} lineHeight={1.02} />
        <FitText text="Crowding Planner" size={84} width={700} weight={800} color={C.tealGlow} lineHeight={1.02} />
        <FitText text="How crowded each stretch of your trip usually is, before you board." size={36} width={640} maxLines={2} weight={500} color={C.textDim} style={{ marginTop: 22 }} lineHeight={1.25} />
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 34, alignItems: "flex-start" }}>
          <Chip level="seats" size={32} />
          <Chip level="standing" size={32} />
          <Chip level="crowded" size={32} />
        </div>
        <div style={{ marginTop: 28, fontSize: 32, fontWeight: 700, color: C.textDim }}>Team Kshama</div>
      </div>
      <div style={{ position: "absolute", left: 850, top: 34, transform: "rotate(4deg)" }}>
        <Phone scale={0.74}>
          <World cam={{ wx: 195, wy: cy(cs[0].chip) + 90, z: 1 }} ax={195} ay={422}>
            <Shot src={capUrl("m-j4-full")} w={m.w} h={m.h} />
          </World>
        </Phone>
      </div>
      <Grain opacity={0.06} />
    </AbsoluteFill>
  );
};

export const Thumbnail: React.FC = () => (
  <FontGate>
    <Inner />
  </FontGate>
);
