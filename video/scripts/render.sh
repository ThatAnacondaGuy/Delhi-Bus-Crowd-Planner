#!/usr/bin/env bash
# One render command: scan the dropped files, write the captions and the sync table, render the film, master the audio.
#   bash scripts/render.sh out/kshama-delhi-bus-crowding.mp4        (npm run render)
#   bash scripts/render.sh out/near-final.mp4                         (npm run near-final)
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-out/kshama-delhi-bus-crowding.mp4}"
mkdir -p "$(dirname "$out")"
raw="$(dirname "$out")/.raw-$(basename "$out")"
node scripts/scan_assets.mjs
node --no-warnings scripts/captions_srt.mjs "$(dirname "$out")/captions.srt"
node --no-warnings scripts/sync_table.mjs "$(dirname "$out")/sync-table.md"
npx remotion render src/index.ts Main "$raw" --codec=h264 --audio-codec=aac --audio-bitrate=320k --crf=18 --pixel-format=yuv420p
bash scripts/master.sh "$raw" "$out"
rm -f "$raw"
echo "done: $out"
