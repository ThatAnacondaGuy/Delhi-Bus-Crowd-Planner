// Render single frames of the film for a visual check, bundling once.
//   node scripts/stills.mjs out/stills-v4 120 900 2400 ...     (frames)
//   node scripts/stills.mjs out/stills-v4 auto                  (a frame in every phrase of every scene, both ends of each scene)
// Any text that cannot fit its box even at the 32 px floor is reported as "frame N: [fit] ...".
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";
import { planScenes, sceneTimeline } from "../src/timing.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const [outDir = "out/stills", ...args] = process.argv.slice(2);

function autoFrames() {
  const A = JSON.parse(fs.readFileSync(path.join(root, "public/assets.json"), "utf8"));
  const vo = Array.from({ length: 9 }, (_, i) => {
    const name = `scene-0${i + 1}.wav`;
    if (!A.vo.includes(name)) return null;
    const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path.join(root, "public/vo/clean", name)], { encoding: "utf8" });
    return parseFloat(r.stdout);
  });
  const plan = planScenes(vo);
  const frames = [];
  for (let s = 0; s < 9; s++) {
    const tl = sceneTimeline(s + 1, plan.durations[s], vo[s], A.silence?.[String(s + 1).padStart(2, "0")] ?? null, s === 4 ? A.parts : null);
    const st = plan.starts[s];
    frames.push({ f: st + 14, tag: `s${s + 1}-start` });
    tl.cues.forEach((c, k) => frames.push({ f: st + Math.min(c.to - 2, c.from + Math.round((c.to - c.from) * 0.7)), tag: `s${s + 1}-p${k}` }));
    frames.push({ f: st + plan.durations[s] - 14, tag: `s${s + 1}-end` });
  }
  return frames;
}

const frames = args[0] === "auto" ? autoFrames() : args.map((a) => ({ f: Number(a), tag: "f" }));
fs.mkdirSync(path.resolve(root, outDir), { recursive: true });
const serveUrl = await bundle({ entryPoint: path.join(root, "src/index.ts") });
const browser = await openBrowser("chrome");
const composition = await selectComposition({ serveUrl, id: "Main", puppeteerInstance: browser });
for (const { f, tag } of frames) {
  const file = path.resolve(root, outDir, `${String(f).padStart(5, "0")}-${tag}.png`);
  await renderStill({ serveUrl, composition, frame: f, output: file, puppeteerInstance: browser, overwrite: true, onBrowserLog: (l) => /\[fit\]/.test(l.text) && console.warn(`frame ${f}: ${l.text}`) });
  console.log(path.relative(root, file));
}
await browser.close({ silent: true });
