import React from "react";
import { AbsoluteFill } from "remotion";
import { C, FONT } from "./theme";
import { Chip, Phone, Shot, World } from "./components/ui";
import { cards, capMeta, capUrl, cy } from "./captures";

export const Thumbnail: React.FC = () => {
  const m = capMeta("m-j4-full");
  const cs = cards("m-j4-full");
  return (
    <AbsoluteFill style={{ background: C.paper, fontFamily: FONT }}>
      <div style={{ position: "absolute", left: 70, top: 62, width: 700 }}>
        <div style={{ fontSize: 80, fontWeight: 700, color: C.blue, lineHeight: 1.04, letterSpacing: -1 }}>Delhi Bus Crowding Planner</div>
        <div style={{ fontSize: 40, color: C.ink, marginTop: 26, lineHeight: 1.25 }}>How crowded each stretch of your trip usually is, before you board.</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 38, alignItems: "flex-start" }}>
          <Chip level="seats" size={34} />
          <Chip level="standing" size={34} />
          <Chip level="crowded" size={34} />
        </div>
        <div style={{ marginTop: 30, fontSize: 36, fontWeight: 700, color: C.grey }}>Team Kshama</div>
      </div>
      <div style={{ position: "absolute", left: 830, top: 28 }}>
        <Phone scale={0.8}>
          <World cam={{ wx: 195, wy: cy(cs[0].chip) + 90, z: 1 }} ax={195} ay={422}>
            <Shot src={capUrl("m-j4-full")} w={m.w} h={m.h} />
          </World>
        </Phone>
      </div>
    </AbsoluteFill>
  );
};
