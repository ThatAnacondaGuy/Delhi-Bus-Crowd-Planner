#!/usr/bin/env bash
# Build the film's single music bed (R38): the second track looped to the film length with 3 s equal-power crossfades
# at the loop joins, each join centred on a scene cut.
#   bash scripts/loop_music.sh "<track>" public/music-1.mp3 [total_s] [join1_s] [join2_s]
# Defaults: 183.6 s film, joins on the scene 4/5 cut (61.667 s) and the scene 6/7 cut (131.9 s).
set -euo pipefail
src="$1"; out="$2"; total="${3:-183.6}"; j1="${4:-61.667}"; j2="${5:-131.9}"
X=3
l1=$(python3 -c "print($j1+$X/2)")                   # segment 1 runs to just past join 1
l2=$(python3 -c "print($j2-$j1+$X)")                 # segment 2 spans join 1 .. join 2 (+ crossfade overlaps)
l3=$(python3 -c "print($total-$j2+$X/2+1)")          # segment 3 covers the rest
ffmpeg -hide_banner -loglevel error -y -i "$src" -i "$src" -i "$src" -filter_complex \
"[0:a]atrim=0:$l1,asetpts=N/SR/TB[a];[1:a]atrim=0:$l2,asetpts=N/SR/TB[b];[2:a]atrim=0:$l3,asetpts=N/SR/TB[c];\
[a][b]acrossfade=d=$X:c1=qsin:c2=qsin[ab];[ab][c]acrossfade=d=$X:c1=qsin:c2=qsin[o]" \
-map "[o]" -ar 48000 -ac 2 -c:a libmp3lame -b:a 256k "$out"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$out"
