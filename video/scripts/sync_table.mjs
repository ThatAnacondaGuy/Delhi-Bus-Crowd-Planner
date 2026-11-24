// Writes out/sync-table.md: per scene, its voice file, clean length, place on the timeline, and every caption cue against
// the speech segment it was placed on (the visual beats of each scene are keyed to the same cue frames).
// Usage: node scripts/sync_table.mjs [out/sync-table.md]
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { FPS, HEAD, planScenes, sceneTimeline, captionSpans } from "../src/timing.ts";
import { speechFromSilences } from "../src/sync.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.resolve(root, process.argv[2] ?? "out/sync-table.md");
const A = JSON.parse(fs.readFileSync(path.join(root, "public/assets.json"), "utf8"));
const vo = Array.from({ length: 9 }, (_, i) => {
  const name = `scene-0${i + 1}.wav`;
  if (!A.vo.includes(name)) return null;
  const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path.join(root, "public/vo/clean", name)], { encoding: "utf8" });
  return parseFloat(r.stdout);
});
const plan = planScenes(vo);
const t = (sec) => {
  const m = Math.floor(sec / 60);
  return `${m}:${(sec - m * 60).toFixed(3).padStart(6, "0")}`;
};
let maxDrift = 0;
let splits = 0;
const lines = [];
lines.push("# Sync table", "");
lines.push(`Film: ${plan.total} frames = ${(plan.total / FPS).toFixed(2)} s at ${FPS} fps. Times are film time (m:ss.sss).`);
lines.push("Speech segments: ffmpeg silencedetect at -35 dB, pauses of 0.2 s or more, on each clean voice file. Each phrase of the script is placed on");
lines.push("the segments in order (src/sync.ts mapCues); its caption and the scene's visual beats start on the first frame of its first segment.");
lines.push("Drift = |caption start - speech start| (frame rounding; at 30 fps at most 16.7 ms). Caption end = speech end plus a short hold, or the next phrase's start.", "");
for (let i = 0; i < 9; i++) {
  const sil = A.silence?.[String(i + 1).padStart(2, "0")] ?? null;
  const tl = sceneTimeline(i + 1, plan.durations[i], vo[i], sil, i === 4 ? A.parts : null);
  const st = plan.starts[i] / FPS;
  const segs = vo[i] ? speechFromSilences(sil ?? [], vo[i]) : [];
  lines.push(`## Scene ${i + 1}`, "");
  lines.push(`- Voice file: public/vo/clean/scene-0${i + 1}.wav${vo[i] ? `, clean length ${vo[i].toFixed(3)} s, ${segs.length} speech segments` : " (none)"}`);
  lines.push(`- Scene: ${t(st)} to ${t((plan.starts[i] + plan.durations[i]) / FPS)} (${plan.durations[i]} frames); voice starts ${HEAD[i]} frames in, at ${t(st + HEAD[i] / FPS)}`);
  if (i === 4) lines.push(`- Shots 5a-5e start at ${tl.shots.map((s) => t(st + s / FPS)).join(", ")} (part starts in the file: ${(A.parts ?? []).join(", ")} s, minus 8 frames)`);
  lines.push("", "| # | Phrase | Caption start | Caption end | Speech start | Speech end | Drift (ms) |", "|---|---|---|---|---|---|---|");
  const spans = captionSpans(tl.cues, tl.duration);
  let sceneMax = 0;
  tl.cues.forEach((c, k) => {
    // the speech times of the phrase in the file, from the mapping in seconds (unrounded)
    const exactFrom = c.from; // frames (head + round(sec*FPS)); recompute exact seconds from the segments for the drift
    const seg = segs.find(([a]) => Math.abs(tl.head + Math.round(a * FPS) - exactFrom) === 0);
    const speechStart = seg ? st + tl.head / FPS + seg[0] : st + c.from / FPS;
    const segEnd = segs.find(([, b]) => tl.head + Math.round(b * FPS) === c.to);
    const speechEnd = segEnd ? st + tl.head / FPS + segEnd[1] : st + c.to / FPS;
    const capStart = st + spans[k].from / FPS;
    const capEnd = st + spans[k].to / FPS;
    const drift = Math.abs(capStart - speechStart) * 1000;
    if (c.split) splits++;
    sceneMax = Math.max(sceneMax, drift);
    lines.push(`| ${k + 1}${i === 4 ? ` (5${"abcde"[c.part]})` : ""} | ${c.text.replace(/\|/g, "/")}${c.split ? " (split)" : ""} | ${t(capStart)} | ${t(capEnd)} | ${t(speechStart)} | ${t(speechEnd)} | ${drift.toFixed(1)} |`);
  });
  maxDrift = Math.max(maxDrift, sceneMax);
  lines.push("", `Max drift in scene ${i + 1}: ${sceneMax.toFixed(1)} ms.`, "");
}
lines.splice(6, 0, `**Max drift over the film: ${maxDrift.toFixed(1)} ms. Phrases split inside a segment (no pause under the boundary): ${splits}.**`, "");
fs.writeFileSync(out, lines.join("\n") + "\n");
console.log(`sync table -> ${path.relative(root, out)}; max drift ${maxDrift.toFixed(1)} ms; splits ${splits}`);
