// Writes out/captions.srt (English, from the voice-over script text) for the YouTube upload.
// The cues are the same spans the film burns in (src/captions.ts sceneCaptionSpans), placed on the same timeline
// (src/timing.ts planScenes, which reads the length of each clean voice file). Scenes without a voice file keep the script's timing.
// Usage: node scripts/captions_srt.mjs [out/captions.srt]      (runs as part of `npm run render`)
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { BASE_FRAMES, FPS, LEAD_FRAMES, TAIL_FRAMES, planScenes, shotStarts } from "../src/timing.ts";
import { sceneCaptionSpans, toSrt } from "../src/captions.ts";

/** voSeconds: clean voice length per scene (null when absent); parts: scene 5 part starts in seconds or null. Returns the .srt text. */
export function buildSrt(voSeconds, parts = null) {
  const plan = planScenes(voSeconds);
  const entries = [];
  for (let i = 0; i < 9; i++) {
    const voFrames = voSeconds[i] != null && voSeconds[i] > 0 ? Math.round(voSeconds[i] * FPS) : null;
    const spans = sceneCaptionSpans(i + 1, {
      voFrames,
      duration: plan.durations[i],
      base: BASE_FRAMES[i],
      lead: LEAD_FRAMES,
      tail: TAIL_FRAMES,
      partStarts: i === 4 ? shotStarts(plan.durations[4], parts) : undefined,
    });
    for (const s of spans) entries.push({ text: s.text, from: plan.starts[i] + s.from, to: plan.starts[i] + s.to });
  }
  return toSrt(entries, FPS);
}

function readAssets(root) {
  const pub = path.join(root, "public");
  let listing = { vo: [], parts: null };
  try {
    listing = JSON.parse(fs.readFileSync(path.join(pub, "assets.json"), "utf8"));
  } catch {
    /* no assets.json: script timings */
  }
  const voSeconds = Array.from({ length: 9 }, (_, i) => {
    const name = `scene-${String(i + 1).padStart(2, "0")}.wav`;
    if (!listing.vo?.includes(name)) return null;
    const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path.join(pub, "vo/clean", name)], { encoding: "utf8" });
    const v = parseFloat(r.stdout);
    return Number.isFinite(v) ? v : null;
  });
  const parts = Array.isArray(listing.parts) && listing.parts.length === 5 ? listing.parts : null;
  return { voSeconds, parts };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const out = path.resolve(root, process.argv[2] ?? "out/captions.srt");
  const { voSeconds, parts } = readAssets(root);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const srt = buildSrt(voSeconds, parts);
  fs.writeFileSync(out, srt);
  console.log(`captions: ${srt.trim().split(/\n\n/).length} cues -> ${path.relative(root, out)}`);
}
