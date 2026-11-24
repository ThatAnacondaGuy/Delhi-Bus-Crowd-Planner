// Scene 9: the end card. The live demo link lands on "Try it live" (phrase 0), GitHub on (1), the title glows on (2),
// the team and the credit line on (3); then it holds, still, and fades.
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C, RADIUS, SHADOW, TYPE, W, prog, springSoft } from "../design";
import { Backdrop, Captions, FitText, Kinetic, SceneShell, Sfx, StylisedMap, useBeats } from "../components/kit";
import { Qr } from "../components/Qr";

export const DEMO_URL = "https://huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner";
export const GITHUB_URL = "https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner";
export const CREDIT = "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.";

const CARD_W = 1400;
const QR = 150;

const LinkCard: React.FC<{ label: string; url: string; show: string; at: number; color: string; top: number }> = ({ label, url, show, at, color, top }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = springSoft(f, fps, at, 22);
  const textW = CARD_W - 2 * 40 - QR - 40;
  return (
    <div
      style={{
        position: "absolute",
        left: (W - CARD_W) / 2,
        top,
        width: CARD_W,
        height: 200,
        padding: "0 40px",
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
        gap: 40,
        borderRadius: RADIUS.xl,
        background: "linear-gradient(160deg, rgba(255,255,255,0.12), rgba(255,255,255,0.05))",
        border: `2px solid ${color}88`,
        boxShadow: SHADOW.card,
        opacity: t,
        transform: `translateY(${(1 - t) * 40}px)`,
      }}
    >
      <div style={{ width: textW }}>
        <FitText text={label} size={TYPE.label} width={textW} weight={800} color={color} />
        <FitText text={show} size={TYPE.body} width={textW} weight={700} color={C.text} style={{ marginTop: 10 }} />
      </div>
      <Qr text={url} size={QR} />
    </div>
  );
};

export const Scene09: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames: D, fps } = useVideoConfig();
  const { beat } = useBeats();
  const [b0, b1, b2, b3] = [0, 1, 2, 3].map((i) => beat(i));
  const glow = prog(f, b2, 12) * (1 - prog(f, b2 + 40, 30));
  const team = springSoft(f, fps, b3 - 2, 22);
  const fade = prog(f, D - 9, 9);
  return (
    <SceneShell>
      <Backdrop tint={[C.teal, C.blue, "#3b2a5c"]} drift={0.6} />
      <StylisedMap draw={1} glow={0.8} opacity={0.14} />
      <div style={{ position: "absolute", left: 96, top: 92, width: W - 192, textShadow: `0 0 ${50 * glow}px ${C.tealGlow}` }}>
        <Kinetic text="Delhi Bus Crowding Planner" at={0} size={TYPE.h1} width={W - 192} maxLines={1} stagger={3} align="center" accent={{ crowding: C.tealGlow }} />
      </div>
      <LinkCard label="Live demo" url={DEMO_URL} show="huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner" at={b0 - 4} color={C.tealGlow} top={230} />
      <LinkCard label="GitHub" url={GITHUB_URL} show="github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner" at={b1 - 4} color={C.blueGlow} top={460} />
      <div style={{ position: "absolute", left: 96, top: 700, width: W - 192, opacity: team, transform: `translateY(${(1 - team) * 20}px)`, display: "flex", flexDirection: "column", alignItems: "center" }}>
        <FitText text="Team Kshama · Aniket Ingale · Ashish Maurya" size={TYPE.h2} width={W - 192} weight={800} color={C.text} align="center" />
        <FitText text={CREDIT} size={TYPE.label} width={W - 192} weight={500} color={C.textDim} align="center" style={{ marginTop: 12 }} />
      </div>
      <Captions />
      <div style={{ position: "absolute", inset: 0, background: C.dusk, opacity: fade }} />
      <Sfx name="chime" at={b0} volume={0.5} />
      <Sfx name="pop" at={b1} volume={0.3} />
      <Sfx name="chime" at={b3} volume={0.4} />
    </SceneShell>
  );
};
