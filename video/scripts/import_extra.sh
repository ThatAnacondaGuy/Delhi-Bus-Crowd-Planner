#!/usr/bin/env bash
# Copy the recordings and sounds you keep in video/extra resources/ into the folders the film reads from.
# COPIES only: the originals are never moved, renamed or changed.
#   extra resources/voice over /scene-NN.(wav|m4a|mp3|...)  ->  public/vo/
#   extra resources/sound effects/*.(mp3|wav|m4a)           ->  public/sfx/   (matched by words in the file name)
#   a music file (name contains "music" or "background")     ->  public/music.mp3 (first one found)
# Then run:  bash video/scripts/prep_audio.sh   and   cd video && npm run render
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="extra resources"
[ -d "$SRC" ] || { echo "No '$SRC' folder in video/. Put files straight into public/vo, public/sfx and public/music.mp3 instead."; exit 0; }
mkdir -p public/vo public/sfx

n=0
while IFS= read -r -d '' f; do
  cp -p "$f" public/vo/ && n=$((n + 1))
done < <(find "$SRC" -type f -iname 'scene-0[1-9].*' -print0)
echo "voice files copied: $n"

m=0
while IFS= read -r -d '' f; do
  cp -p "$f" public/sfx/ && m=$((m + 1))
done < <(find "$SRC" -type f -ipath '*sound effects*' \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' \) -print0)
echo "sound effects copied: $m"

music=$(find "$SRC" -type f \( -iname '*music*' -o -iname '*background*' \) \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' \) | head -n 1 || true)
if [ -n "$music" ]; then
  ext="${music##*.}"
  cp -p "$music" "public/music.$ext"
  echo "music copied: $music -> public/music.$ext"
else
  echo "no music file found"
fi
