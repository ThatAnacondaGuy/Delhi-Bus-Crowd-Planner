import { createContext, useContext } from "react";
import { staticFile } from "remotion";
import { getAudioDurationInSeconds } from "@remotion/media-utils";

/** What the user has dropped into video/public/ (scripts/scan_assets.mjs writes public/assets.json before a render). */
export type Assets = {
  /** clean voice-over length in seconds per scene (null when scene-NN.wav is not there) */
  vo: (number | null)[];
  /** start of each of the five planner parts in scene 5, seconds, when found by prep_audio.sh */
  parts: number[] | null;
  music: string | null;
  sfx: string[];
  clips: string[];
};

export const NO_ASSETS: Assets = { vo: Array(9).fill(null), parts: null, music: null, sfx: [], clips: [] };

export const AssetsContext = createContext<Assets>(NO_ASSETS);
export const useAssets = () => useContext(AssetsContext);

type Listing = { vo: string[]; parts?: number[] | null; music: string | null; sfx: string[]; clips: string[] };

/** Called from calculateMetadata: reads assets.json and the length of each clean voice file. Never throws. */
export async function loadAssets(): Promise<Assets> {
  let listing: Listing | null = null;
  try {
    const res = await fetch(staticFile("assets.json"));
    if (res.ok) listing = (await res.json()) as Listing;
  } catch {
    listing = null;
  }
  if (!listing) return NO_ASSETS;
  const vo: (number | null)[] = await Promise.all(
    Array.from({ length: 9 }, async (_, i) => {
      const name = `scene-${String(i + 1).padStart(2, "0")}.wav`;
      if (!listing!.vo.includes(name)) return null;
      try {
        return await getAudioDurationInSeconds(staticFile(`vo/clean/${name}`));
      } catch {
        return null;
      }
    }),
  );
  return {
    vo,
    parts: Array.isArray(listing.parts) && listing.parts.length === 5 ? listing.parts : null,
    music: listing.music ?? null,
    sfx: listing.sfx ?? [],
    clips: listing.clips ?? [],
  };
}
