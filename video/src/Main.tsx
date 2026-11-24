import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { Assets, AssetsContext } from "./assets";
import { C, FONT } from "./theme";
import { MUSIC_BASE, musicGain, planScenes, speechWindows } from "./timing";
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
  const windows = speechWindows(plan.starts, assets.vo);
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

        {/* music: ducked under speech, faded in and out; only when public/music.* exists */}
        {assets.music ? (
          <Audio src={staticFile(assets.music)} volume={(f) => musicGain(f, windows, plan.total)} name={`Music (${MUSIC_BASE})`} />
        ) : null}
      </AbsoluteFill>
    </AssetsContext.Provider>
  );
};
