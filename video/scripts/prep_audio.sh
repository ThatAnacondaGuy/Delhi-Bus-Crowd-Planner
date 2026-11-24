#!/usr/bin/env bash
# Clean the voice-over recordings for the film.
#   video/public/vo/scene-01.m4a ... scene-09.m4a   (also .wav .mp3 .aac .aiff .caf)
# For each file present: high-pass 80 Hz, denoise (afftdn), trim leading and trailing silence, put back a 0.3 s lead,
# loudness-normalise to -16 LUFS (two-pass loudnorm) and write video/public/vo/clean/scene-NN.wav (48 kHz, stereo).
# Scene 05 is one file with five parts separated by pauses: the part starts are written to
# public/vo/clean/scene-05.parts.json so the five phone shots follow the voice.
# Missing files are skipped. Re-run after dropping in new takes.
set -euo pipefail
cd "$(dirname "$0")/.."
VO=public/vo
OUT=$VO/clean
mkdir -p "$OUT"
command -v ffmpeg >/dev/null || { echo "ffmpeg is not installed (brew install ffmpeg)"; exit 1; }

TARGET_I=-16
TARGET_TP=-1
TARGET_LRA=11
# voice chain before loudness: high-pass, denoise, drop leading/trailing silence, then a 0.3 s lead-in
PRE="highpass=f=80,afftdn=nr=12:nf=-40,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,adelay=300:all=1"

found=0
for n in 01 02 03 04 05 06 07 08 09; do
  src=""
  for ext in m4a wav mp3 aac aiff aif caf; do
    [ -f "$VO/scene-$n.$ext" ] && { src="$VO/scene-$n.$ext"; break; }
  done
  [ -z "$src" ] && continue
  found=$((found + 1))
  dst="$OUT/scene-$n.wav"

  # pass 1: measure
  stats=$(ffmpeg -hide_banner -nostats -i "$src" -af "$PRE,loudnorm=I=$TARGET_I:TP=$TARGET_TP:LRA=$TARGET_LRA:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
  get() { printf '%s' "$stats" | python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }
  mi=$(get input_i); mtp=$(get input_tp); mlra=$(get input_lra); mth=$(get input_thresh); moff=$(get target_offset)

  # pass 2: apply with the measured values, 48 kHz stereo
  ffmpeg -hide_banner -loglevel error -y -i "$src" \
    -af "$PRE,loudnorm=I=$TARGET_I:TP=$TARGET_TP:LRA=$TARGET_LRA:measured_I=$mi:measured_TP=$mtp:measured_LRA=$mlra:measured_thresh=$mth:offset=$moff:linear=true" \
    -ar 48000 -ac 2 -c:a pcm_s16le "$dst"

  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$dst")
  lufs=$(ffmpeg -hide_banner -nostats -i "$dst" -af ebur128=framelog=quiet -f null - 2>&1 | awk '/I:/ {v=$2} END {print v}')
  printf 'scene-%s  %6.2f s  %s LUFS  (%s)\n' "$n" "$dur" "$lufs" "$src"

  if [ "$n" = "05" ]; then
    # five parts separated by pauses: find where each part starts. With exactly four pauses of 0.9 s or more they are the part
    # breaks. With more (the voice also pauses inside a part: the script has "//" long pauses), pick the four that make each
    # part's speaking time closest to its share of the script's words (5a to 5e: 20, 15, 19, 21, 21 words).
    PARTS_PY=$(cat <<'PY'
import re, sys, json, os, itertools
text = sys.stdin.read()
sil = [(float(a), float(b)) for a, b in re.findall(r"silence_start: ([0-9.]+)\s*\n.*?silence_end: ([0-9.]+)", text)]
WORDS = [20, 15, 19, 21, 21]
total_end = float(sys.argv[2])
def fail(msg):
    print("  scene 5: " + msg + "; using the script split")
    try:
        os.remove(sys.argv[1])
    except OSError:
        pass
if len(sil) < 4:
    fail(f"found {len(sil)} pauses of 0.9 s or more, expected 4 (about 1.5 s between 5a..5e)")
    sys.exit(0)
def starts_for(choice):
    return [0.3] + [sil[i][1] for i in choice]
def speech_between(a, b):
    # speaking time in [a, b] = length minus the pauses inside it
    t = b - a
    for s0, s1 in sil:
        t -= max(0.0, min(b, s1) - max(a, s0))
    return t
best = None
for choice in itertools.combinations(range(len(sil)), 4):
    st = starts_for(choice)
    ends = [sil[i][0] for i in choice] + [total_end]
    times = [speech_between(a, b) for a, b in zip(st, ends)]
    rate = sum(times) / sum(WORDS)
    err = sum(abs(t - w * rate) for t, w in zip(times, WORDS))
    if best is None or err < best[0]:
        best = (err, choice, st)
how = "the four pauses" if len(sil) == 4 else f"the best fit of the script's word counts among {len(sil)} pauses"
json.dump([round(x, 2) for x in best[2]], open(sys.argv[1], "w"))
print("  scene 5 parts start at", [round(x, 2) for x in best[2]], "seconds (" + how + ")")
print("  scene 5 pauses of 0.9 s or more (start-end):", [(round(a, 2), round(b, 2)) for a, b in sil])
PY
)
    ffmpeg -hide_banner -nostats -i "$dst" -af "silencedetect=noise=-38dB:d=0.9" -f null - 2>&1 | python3 -c "$PARTS_PY" "$OUT/scene-05.parts.json" "$dur"
  fi
done

[ "$found" -eq 0 ] && echo "No voice files in $VO yet (scene-01.m4a ... scene-09.m4a). Nothing to do."
node scripts/scan_assets.mjs
