import React, { useMemo } from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { Assets, AssetsContext } from "./assets";
import { C, H, W, clamp01, inOutCubic } from "./design";
import { FONT, FontGate } from "./fonts";
import { FPS, HEAD, WIPE, XFADE_FRAMES, XFADE_TARGET, pickCrossfade, planScenes, sceneTimeline, speechWindows, trackGains } from "./timing";
import { Sfx, TimelineCtx } from "./components/kit";
import { Scene01 } from "./scenes/Scene01";
import { Scene02 } from "./scenes/Scene02";
import { Scene03 } from "./scenes/Scene03";
import { Scene04 } from "./scenes/Scene04";
import { Scene05 } from "./scenes/Scene05";
import { Scene06 } from "./scenes/Scene06";
import { Scene07 } from "./scenes/Scene07";
import { Scene08 } from "./scenes/Scene08";
import { Scene09 } from "./scenes/Scene09";

export type MainProps = { assets: Assets };

const SCENES = [Scene01, Scene02, Scene03, Scene04, Scene05, Scene06, Scene07, Scene08, Scene09];
/** Wipe colours at each cut (into scene 2..9). */
const WIPE_COLOURS = [C.tealGlow, C.blueGlow, C.amberGlow, C.tealGlow, C.blueGlow, "#e2e8f0", C.amberGlow, C.tealGlow];

/** A diagonal wipe centred on a cut: a coloured band sweeps across, the cut happens under it. */
const Wipe: React.FC<{ at: number; color: string }> = ({ at, color }) => {
  const f = useCurrentFrame();
  const t = clamp01((f - (at - WIPE / 2)) / WIPE);
  if (t <= 0 || t >= 1) return null;
  const x = (-1.3 + 2.6 * inOutCubic(t)) * W;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: W / 2 - W * 0.75 + x,
          top: -H * 0.25,
          width: W * 1.5,
          height: H * 1.5,
          transform: "skewX(-14deg)",
          background: `linear-gradient(90deg, transparent 0%, ${color} 16%, ${C.dusk} 30%, ${C.dusk} 70%, ${color} 84%, transparent 100%)`,
        }}
      />
    </AbsoluteFill>
  );
};

export const Main: React.FC<MainProps> = ({ assets }) => {
  const plan = useMemo(() => planScenes(assets.vo), [assets]);
  const timelines = useMemo(
    () => SCENES.map((_, i) => sceneTimeline(i + 1, plan.durations[i], assets.vo[i], assets.silence[i], i === 4 ? assets.parts : null)),
    [assets, plan],
  );
  const windows = speechWindows(plan.starts, assets.vo);
  const tracks = assets.music.length >= 2 ? 2 : assets.music.length;
  const xs = tracks >= 2 ? pickCrossfade(plan.starts, XFADE_TARGET, Math.floor(assets.musicSeconds[0] * FPS)) : null;
  const trim = (i: number) => assets.musicTrim[i] ?? 1;
  return (
    <AssetsContext.Provider value={assets}>
      <AbsoluteFill style={{ backgroundColor: C.dusk, fontFamily: FONT }}>
        <FontGate>
          {SCENES.map((S, i) => (
            <Sequence key={i} from={plan.starts[i]} durationInFrames={plan.durations[i]} name={`Scene ${String(i + 1).padStart(2, "0")}`}>
              <TimelineCtx.Provider value={timelines[i]}>
                <S />
              </TimelineCtx.Provider>
            </Sequence>
          ))}
          {plan.starts.slice(1).map((st, k) => (
            <Wipe key={`w${k}`} at={st} color={WIPE_COLOURS[k]} />
          ))}
        </FontGate>

        {/* voice-over: each clean file starts HEAD frames into its scene */}
        {assets.vo.map((v, i) =>
          v == null ? null : (
            <Sequence key={`vo${i}`} from={plan.starts[i] + HEAD[i]} durationInFrames={Math.ceil(v * FPS) + 2} name={`VO ${i + 1}`}>
              <Audio src={staticFile(`vo/clean/scene-${String(i + 1).padStart(2, "0")}.wav`)} />
            </Sequence>
          ),
        )}

        {/* a soft whoosh under every wipe from scene 3 on */}
        {plan.starts.slice(2).map((st, k) => (
          <Sfx key={`tr${k}`} name={k % 2 === 0 ? "whoosh" : "swoop"} at={st - 8} len={40} volume={0.32} />
        ))}

        {/* music: ducked under speech, faded in and out, crossfaded between the two tracks (R37) */}
        {tracks >= 1 ? (
          <Sequence from={0} durationInFrames={xs != null ? xs + XFADE_FRAMES : plan.total} name="Music 1">
            <Audio src={staticFile(assets.music[0])} volume={(fr) => trim(0) * trackGains(fr, windows, plan.total, xs, tracks)[0]} />
          </Sequence>
        ) : null}
        {tracks >= 2 && xs != null ? (
          <Sequence from={xs} durationInFrames={plan.total - xs} name="Music 2">
            <Audio src={staticFile(assets.music[1])} volume={(fr) => trim(1) * trackGains(fr + xs, windows, plan.total, xs, tracks)[1]} />
          </Sequence>
        ) : null}
      </AbsoluteFill>
    </AssetsContext.Provider>
  );
};
