import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, outCubic, prog, springSoft } from "../theme";
import { Caption, Chip, Scene, Sfx } from "../components/ui";
import { Qr } from "../components/Qr";
import { SCENE_CAPTIONS, chunkSpans } from "../captions";
import { LEAD_FRAMES, TAIL_FRAMES } from "../timing";
import { useAssets } from "../assets";

export const DEMO_URL = "https://huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner";
export const GITHUB_URL = "https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner";
export const CREDIT = "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.";

const LinkBar: React.FC<{ label: string; url: string; show: string; at: number; color: string }> = ({ label, url, show, at, color }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = springSoft(f, fps, at);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 36,
        width: 1560,
        padding: "18px 30px 18px 44px",
        borderRadius: 28,
        background: C.white,
        border: `4px solid ${color}`,
        boxShadow: "0 14px 40px rgba(13,17,23,0.10)",
        opacity: t,
        transform: `translateY(${(1 - t) * 30}px)`,
      }}
    >
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 40, fontWeight: 700, color, letterSpacing: 0.5 }}>{label}</div>
        <div style={{ fontSize: 36, fontWeight: 700, color: C.ink, marginTop: 4, whiteSpace: "nowrap" }}>{show}</div>
      </div>
      <Qr text={url} size={150} />
    </div>
  );
};

export const Scene09: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const { vo } = useAssets();
  const drift = Math.sin((f / durationInFrames) * Math.PI) * 6;
  const fadeOut = prog(f, durationInFrames - 9, 9);
  const speechEnd = vo[8] != null ? Math.round(vo[8]! * 30) : 150;
  const spans = chunkSpans(SCENE_CAPTIONS[8], LEAD_FRAMES + 6, Math.max(speechEnd, 120) - 0);
  void TAIL_FRAMES;
  return (
    <Scene bg={C.paper}>
      <div style={{ position: "absolute", inset: 0, transform: `translateY(${drift}px)`, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 36 }}>
        <div style={{ fontSize: 96, fontWeight: 700, color: C.blue, letterSpacing: -1 }}>Delhi Bus Crowding Planner</div>
        <div style={{ display: "flex", gap: 22, marginTop: 16, opacity: prog(f, 0, 12) }}>
          <Chip level="seats" size={32} />
          <Chip level="standing" size={32} />
          <Chip level="crowded" size={32} />
          <Chip level="no_data" size={32} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20, marginTop: 30 }}>
          <LinkBar label="Live demo" url={DEMO_URL} show="huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner" at={6} color={C.teal} />
          <LinkBar label="GitHub" url={GITHUB_URL} show="github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner" at={18} color={C.blue} />
        </div>
        <div style={{ opacity: prog(f, 36, 14, outCubic), marginTop: 26, textAlign: "center" }}>
          <div style={{ fontSize: 44, fontWeight: 700 }}>Team Kshama · Aniket Ingale · Ashish Maurya</div>
          <div style={{ fontSize: 34, color: C.grey, marginTop: 6 }}>{CREDIT}</div>
        </div>
      </div>
      <Caption spans={spans} bottom={34} dark />
      <div style={{ position: "absolute", inset: 0, background: C.paper, opacity: fadeOut }} />
      <Sfx name="chime" at={6} volume={0.5} />
    </Scene>
  );
};
