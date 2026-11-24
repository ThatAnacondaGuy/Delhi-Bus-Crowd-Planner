// Writes out/captions.srt (English, from the voice-over script text) for the YouTube upload.
// The cues are the same spans the film burns in (src/timing.ts sceneTimeline + captionSpans): each phrase sits on the speech
// segments found in the clean voice file, on the voice-driven timeline (planScenes). Scenes without a voice keep the script's pace.
// Usage: node scripts/captions_srt.mjs [out/captions.srt]      (runs as part of `npm run render`)
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { FPS, planScenes, sceneTimeline, captionSpans } from "../src/timing.ts";
import { toSrt } from "../src/captions.ts";

/**
 * voSeconds: clean voice length per scene (null when absent); parts: scene 5 part starts (s) or null;
 * silences: per scene, the [start, end] pauses detected in the clean file (null when absent). Returns the .srt text.
 */
export function buildSrt(voSeconds, parts = null, silences = Array(9).fill(null)) {
  const plan = planScenes(voSeconds);
  const entries = [];
  for (let i = 0; i < 9; i++) {
    const tl = sceneTimeline(i + 1, plan.durations[i], voSeconds[i], silences[i], i === 4 ? parts : null);
    for (const s of captionSpans(tl.cues, tl.duration)) entries.push({ text: s.text, from: plan.starts[i] + s.from, to: plan.starts[i] + s.to });
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
  const silences = Array.from({ length: 9 }, (_, i) => listing.silence?.[String(i + 1).padStart(2, "0")] ?? null);
  return { voSeconds, parts, silences };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const out = path.resolve(root, process.argv[2] ?? "out/captions.srt");
  const { voSeconds, parts, silences } = readAssets(root);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const srt = buildSrt(voSeconds, parts, silences);
  fs.writeFileSync(out, srt);
  console.log(`captions: ${srt.trim().split(/\n\n/).length} cues -> ${path.relative(root, out)}`);
}
