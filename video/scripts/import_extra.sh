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
plain5=0
while IFS= read -r -d '' f; do
  cp -p "$f" public/vo/ && n=$((n + 1))
  case "$(basename "$f" | tr '[:upper:]' '[:lower:]')" in scene-05.*) plain5=1 ;; esac
done < <(find "$SRC" -type f -iname 'scene-0[1-9].*' -print0)
# Scene 5 may arrive under another name ("scene 5 the planner in Phone.wav", "Scene05 ...", "scene-05 ..."): a file whose name
# starts with "scene 5" / "scene-05" / "scene05" (any case) becomes public/vo/scene-05.<ext>, unless a plain scene-05.<ext> was found (that one wins).
while IFS= read -r -d '' f; do
  b=$(basename "$f"); lb=$(printf '%s' "$b" | tr '[:upper:]' '[:lower:]'); ext="${lb##*.}"
  case "$ext" in wav|m4a|mp3|aac|aiff|aif|caf) ;; *) continue ;; esac
  [[ "$lb" =~ ^scene[\ -]?0?5([^0-9].*)?\.[a-z0-9]+$ ]] || continue   # not "scene 50", not "scene 15"
  [[ "$lb" =~ ^scene-05\. ]] && continue                                # the plain name was copied above
  [ "$plain5" = 1 ] && continue
  cp -p "$f" "public/vo/scene-05.$ext" && n=$((n + 1)) && echo "scene 5: '$b' -> public/vo/scene-05.$ext"
done < <(find "$SRC" -type f -iname 'scene*' -print0)
echo "voice files copied: $n"

m=0
while IFS= read -r -d '' f; do
  cp -p "$f" public/sfx/ && m=$((m + 1))
done < <(find "$SRC" -type f -ipath '*sound effects*' \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' \) -print0)
echo "sound effects copied: $m"

# Music (R38): only the "ambient corporate startup promo background" track is used, looped to the film length with 3 s
# equal-power crossfades at scene cuts (scripts/loop_music.sh). The first track ("startup background") is not used.
rm -f public/music.* public/music-*.*
track=$(find "$SRC" -type f -iname '*ambient corporate*' \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' \) -print -quit)
if [ -z "$track" ]; then
  echo "no music file found"
else
  bash "$(dirname "$0")/loop_music.sh" "$track" public/music-1.mp3 >/dev/null
  echo "music: $track -> public/music-1.mp3 (looped)"
fi
