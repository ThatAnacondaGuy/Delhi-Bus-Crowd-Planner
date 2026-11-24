#!/usr/bin/env bash
# Render single frames of the film to video/out/stills/ for a visual check.  Usage: bash video/scripts/stills.sh 120 900 2400 ...
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out/stills
for f in "$@"; do
  npx remotion still src/index.ts Main "out/stills/f$(printf '%05d' "$f").png" --frame="$f" --log=error
done
