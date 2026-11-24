#!/usr/bin/env bash
# Master the film's audio: integrated about -16 LUFS, true peak at most -1.0 dBTP.
#   bash scripts/master.sh in.mp4 out.mp4
# Two-pass loudnorm (linear, TP target -1.5) followed by a brick-wall limiter at -1.5 dBFS, then AAC 256k 48 kHz.
# The picture is copied, not re-encoded. Prints the result as measured by ebur128.
set -euo pipefail
in="$1"; out="$2"
LOUD="I=-16:TP=-1.5:LRA=11"
stats=$(ffmpeg -hide_banner -nostats -i "$in" -vn -af "loudnorm=$LOUD:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
get() { printf '%s' "$stats" | python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }
mi=$(get input_i); mtp=$(get input_tp); mlra=$(get input_lra); mth=$(get input_thresh); moff=$(get target_offset)
echo "master: before  I=$mi LUFS  TP=$mtp dBTP  LRA=$mlra"
ffmpeg -hide_banner -loglevel error -y -i "$in" \
  -af "loudnorm=$LOUD:measured_I=$mi:measured_TP=$mtp:measured_LRA=$mlra:measured_thresh=$mth:offset=$moff:linear=true,alimiter=limit=0.84:attack=3:release=60:level=false" \
  -map 0:v -map 0:a -c:v copy -c:a aac -b:a 256k -ar 48000 -ac 2 -movflags +faststart "$out"
ffmpeg -hide_banner -nostats -i "$out" -vn -af ebur128=peak=true -f null - 2>&1 | awk '/Integrated loudness/ {f=1} f && /I:/ {i=$2} f && /Peak:/ {p=$2} END {print "master: after   I=" i " LUFS  TP=" p " dBTP"}'
