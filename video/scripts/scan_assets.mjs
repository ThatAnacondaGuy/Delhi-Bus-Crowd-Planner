// Lists what the user has dropped into video/public/ so the film can pick it up: writes public/assets.json.
// Runs automatically before `npm run studio|draft|render` and at the end of prep_audio.sh. Missing files are fine.
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PUBLIC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../public");
const list = (dir, re) => {
  try {
    return fs.readdirSync(path.join(PUBLIC, dir)).filter((f) => re.test(f) && !f.startsWith(".")).sort();
  } catch {
    return [];
  }
};

const vo = list("vo/clean", /^scene-0[1-9]\.wav$/);
let parts = null;
try {
  const p = JSON.parse(fs.readFileSync(path.join(PUBLIC, "vo/clean/scene-05.parts.json"), "utf8"));
  if (Array.isArray(p) && p.length === 5) parts = p;
} catch {
  parts = null;
}
// music tracks play in file-name order (music-1.mp3, then music-2.mp3 ...)
const music = fs.readdirSync(PUBLIC).filter((f) => /^music.*\.(mp3|m4a|wav|aac|ogg)$/i.test(f) && !f.startsWith(".")).sort();
const sfx = list("sfx", /\.(mp3|wav|m4a|ogg|aac)$/i);

// Integrated loudness of a file (LUFS) with ffmpeg's ebur128; null when ffmpeg is missing.
function lufs(file) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-nostats", "-i", file, "-af", "ebur128=framelog=quiet", "-f", "null", "-"], { encoding: "utf8" });
  const m = [...(r.stderr ?? "").matchAll(/I:\s+(-?[0-9.]+) LUFS/g)].pop();
  return m ? parseFloat(m[1]) : null;
}
const db = (x) => Math.pow(10, x / 20);
// every music track is trimmed to the same loudness (the user's two tracks differ by about 8 LU)
const MUSIC_TARGET_LUFS = -18;
const musicTrim = music.map((f) => {
  const l = lufs(path.join(PUBLIC, f));
  return l == null ? 1 : Math.min(1.5, +db(MUSIC_TARGET_LUFS - l).toFixed(4));
});
// loud sound effects are brought down towards -22 LUFS so the volumes in the scenes mean the same thing for every file
const SFX_REF_LUFS = -22;
const sfxTrim = {};
for (const f of sfx) {
  const l = lufs(path.join(PUBLIC, "sfx", f));
  sfxTrim[f] = l == null ? 1 : Math.min(1, +db(SFX_REF_LUFS - l).toFixed(4));
}
const clips = list("clips", /\.(mp4|mov|webm)$/i);

fs.mkdirSync(PUBLIC, { recursive: true });
fs.writeFileSync(path.join(PUBLIC, "assets.json"), JSON.stringify({ vo, parts, music, musicTrim, sfx, sfxTrim, clips }, null, 1) + "\n");
console.log(`assets: ${vo.length}/9 voice files, music ${music.length ? music.join(" + ") : "none"}, ${sfx.length} sound effects, ${clips.length} clips`);
