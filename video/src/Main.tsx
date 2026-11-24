import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { Assets, AssetsContext } from "./assets";
import { C, FONT } from "./theme";
import { FPS, XFADE_FRAMES, XFADE_TARGET, pickCrossfade, planScenes, speechWindows, trackGains } from "./timing";
import { Sfx } from "./components/ui";
import { SCENE_CAPTIONS } from "./captions";
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
void SCENE_CAPTIONS;

export const Main: React.FC<MainProps> = ({ assets }) => {
  const plan = planScenes(assets.vo);
  const windows = speechWindows(plan.starts, assets.vo, plan.durations);
  // music: track 1 from the start, track 2 crossfades in (4 s, equal power) at the scene boundary closest to 1:55
  const tracks = assets.music.length >= 2 ? 2 : assets.music.length;
  const xs = tracks >= 2 ? pickCrossfade(plan.starts, XFADE_TARGET, Math.floor(assets.musicSeconds[0] * FPS)) : null;
  const trim = (i: number) => assets.musicTrim[i] ?? 1;
  return (
    <AssetsContext.Provider value={assets}>
      <AbsoluteFill style={{ backgroundColor: C.paper, fontFamily: FONT }}>
        {SCENES.map((S, i) => (
          <Sequence key={i} from={plan.starts[i]} durationInFrames={plan.durations[i]} name={`Scene ${String(i + 1).padStart(2, "0")}`}>
            <S />
          </Sequence>
        ))}

        {/* voice-over: the cleaned files from prep_audio.sh, when present */}
        {assets.vo.map((v, i) =>
          v == null ? null : (
            <Sequence key={`vo${i}`} from={plan.starts[i]} durationInFrames={plan.durations[i]} name={`VO ${i + 1}`}>
              <Audio src={staticFile(`vo/clean/scene-${String(i + 1).padStart(2, "0")}.wav`)} />
            </Sequence>
          ),
        )}

        {/* transitions: a soft whoosh into every scene after the first two, alternating the user's swoosh and swoop */}
        {plan.starts.slice(2, 8).map((st, k) => (
          <Sfx key={`tr${k}`} name={k % 2 === 0 ? "whoosh" : "swoop"} at={st - 3} len={45} volume={0.5} />
        ))}

        {/* music: ducked under speech, faded in and out, crossfaded between the two tracks */}
        {tracks >= 1 ? (
          <Sequence from={0} durationInFrames={xs != null ? xs + XFADE_FRAMES : plan.total} name="Music 1">
            <Audio src={staticFile(assets.music[0])} volume={(f) => trim(0) * trackGains(f, windows, plan.total, xs, tracks)[0]} />
          </Sequence>
        ) : null}
        {tracks >= 2 && xs != null ? (
          <Sequence from={xs} durationInFrames={plan.total - xs} name="Music 2">
            <Audio src={staticFile(assets.music[1])} volume={(f) => trim(1) * trackGains(f + xs, windows, plan.total, xs, tracks)[1]} />
          </Sequence>
        ) : null}
      </AbsoluteFill>
    </AssetsContext.Provider>
  );
};
