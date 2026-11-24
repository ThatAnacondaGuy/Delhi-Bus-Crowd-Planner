import React from "react";
import { Composition, Still } from "remotion";
import { Main, MainProps } from "./Main";
import { NO_ASSETS, loadAssets } from "./assets";
import { FPS, planScenes } from "./timing";
import { Thumbnail } from "./Thumbnail";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Main"
      component={Main}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={5400}
      defaultProps={{ assets: NO_ASSETS } as MainProps}
      calculateMetadata={async () => {
        const assets = await loadAssets();
        const plan = planScenes(assets.vo);
        for (const w of plan.warnings) console.warn(`[film] ${w}`);
        return { durationInFrames: plan.total, props: { assets } };
      }}
    />
    <Still id="Thumbnail" component={Thumbnail} width={1280} height={720} />
  </>
);
