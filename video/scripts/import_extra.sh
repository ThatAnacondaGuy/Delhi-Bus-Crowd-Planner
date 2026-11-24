#!/usr/bin/env bash
# Copy the recordings and sounds you keep in video/extra resources/ into the folders the film reads from.
# COPIES only: the originals are never moved, renamed or changed.
#   extra resources/voice over /scene-NN.(wav|m4a|mp3|...)  ->  public/vo/
#   extra resources/sound effects/*.(mp3|wav|m4a)           ->  public/sfx/   (matched by words in the file name)
#   music files (name contains "music" or "background")      ->  public/music-1.mp3, music-2.mp3 (played in that order)
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

# Music: every file with "music" or "background" in its name, played in this order: names starting with "startup" first,
# then the rest alphabetically. They become public/music-1.ext, music-2.ext ... and the film crossfades from one to the next
# (4 s, equal power) at the scene boundary closest to 1:55. Old public/music* copies are replaced.
rm -f public/music.* public/music-*.*
tracks=()
while IFS= read -r -d '' f; do tracks+=("$f"); done < <(find "$SRC" -type f \( -iname '*music*' -o -iname '*background*' \) \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' \) -print0)
if [ "${#tracks[@]}" -eq 0 ]; then
  echo "no music file found"
else
  lines=""
  for f in "${tracks[@]}"; do
    b=$(basename "$f" | tr '[:upper:]' '[:lower:]')
    k=1
    if [[ "$b" == startup* ]]; then k=0; fi
    lines+="$k"$'\t'"$b"$'\t'"$f"$'\n'
  done
  ordered=$(printf '%s' "$lines" | sort -t $'\t' -k1,1 -k2,2 | cut -f3)
  n=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    n=$((n + 1)); ext="${f##*.}"
    cp -p "$f" "public/music-$n.$ext"
    echo "music $n: $f -> public/music-$n.$ext"
  done <<< "$ordered"
fi
