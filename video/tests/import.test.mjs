// scripts/import_extra.sh copies scene 5's voice-over even when it arrives under another name.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const SCRIPT = process.env.IMPORT_SCRIPT ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../scripts/import_extra.sh");

function run(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "import-"));
  fs.mkdirSync(path.join(root, "scripts"));
  fs.copyFileSync(SCRIPT, path.join(root, "scripts/import_extra.sh"));
  const vo = path.join(root, "extra resources", "voice over ");
  fs.mkdirSync(vo, { recursive: true });
  for (const f of files) fs.writeFileSync(path.join(vo, f), "x");
  const r = spawnSync("bash", [path.join(root, "scripts/import_extra.sh")], { encoding: "utf8" });
  const got = fs.existsSync(path.join(root, "public/vo")) ? fs.readdirSync(path.join(root, "public/vo")).sort() : [];
  const kept = fs.readdirSync(vo).sort();
  fs.rmSync(root, { recursive: true, force: true });
  return { r, got, kept };
}

for (const name of ["scene 5 the planner in Phone.wav", "Scene 5 The Planner.WAV", "scene05 take 2.m4a", "SCENE-05 final.mp3"]) {
  test(`scene 5 under the name "${name}" becomes scene-05`, () => {
    const { got, kept } = run([name, "scene-01.wav"]);
    const ext = name.split(".").pop().toLowerCase();
    assert.ok(got.includes(`scene-05.${ext}`), `public/vo has ${got.join(", ")}`);
    assert.ok(got.includes("scene-01.wav"));
    assert.ok(kept.includes(name), "the original is untouched");
  });
}

test("a plain scene-05.wav wins over a differently named file", () => {
  const { got } = run(["scene 5 old.mp3", "scene-05.wav"]);
  assert.deepEqual(got, ["scene-05.wav"]);
});

test("other files are not taken for scene 5", () => {
  const { got } = run(["scene 50 notes.wav", "scene 5 notes.txt"]);
  assert.deepEqual(got, []);
});
