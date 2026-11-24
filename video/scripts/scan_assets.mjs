// Lists what the user has dropped into video/public/ so the film can pick it up: writes public/assets.json.
// Runs automatically before `npm run studio|draft|render` and at the end of prep_audio.sh. Missing files are fine.
import fs from "node:fs";
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
const music = fs.readdirSync(PUBLIC).filter((f) => /^music.*\.(mp3|m4a|wav|aac|ogg)$/i.test(f)).sort()[0] ?? null;
const sfx = list("sfx", /\.(mp3|wav|m4a|ogg|aac)$/i);
const clips = list("clips", /\.(mp4|mov|webm)$/i);

fs.mkdirSync(PUBLIC, { recursive: true });
fs.writeFileSync(path.join(PUBLIC, "assets.json"), JSON.stringify({ vo, parts, music, sfx, clips }, null, 1) + "\n");
console.log(`assets: ${vo.length}/9 voice files, music ${music ?? "none"}, ${sfx.length} sound effects, ${clips.length} clips`);
