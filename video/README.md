# Demo film (Remotion)

The 3-minute demo film for the Delhi Bus Crowding Planner, by **Team Kshama** (Aniket Ingale, Ashish Maurya). It is a
Remotion project: React components rendered frame by frame to H.264. The plan and the voice-over script are in
[`docs/DEMO_VIDEO_SCRIPT.md`](../docs/DEMO_VIDEO_SCRIPT.md); this folder builds that film.

1920×1080, 30 fps, 9 scenes. With the recorded voice it is about 3:04 (the voice sets the length); without any voice it is
the script's 3:00 draft.

> **Licence note.** Remotion is free for individuals and for companies of up to 3 people. Team Kshama is 2 people, so the
> free licence covers this film. Nothing here is a paid or hosted service.

## What is committed and what is not

Committed: the code, `package.json` with exact versions, `package-lock.json`, the numbers file `src/numbers.json`, the capture
metadata `src/captures.generated.json`, and the scripts. **Never committed** (see `.gitignore`): `node_modules/`, `out/`,
`video/extra resources/` and everything in `public/` (voice, music, sound effects, app captures, `assets.json`).

## One-time setup

```bash
cd video
npm install          # exact versions from package-lock.json; Remotion downloads its own headless Chrome on the first render
```

## Final render

```bash
# 1. copy the voice, sound and music files from "video/extra resources/" into video/public/ (originals untouched)
bash video/scripts/import_extra.sh
# 2. clean every voice file (-16 LUFS), find the five parts of scene 5 from its pauses, rescan (speech segments included)
bash video/scripts/prep_audio.sh
# 3. render: captions.srt + sync-table.md + the film, mastered (about 3 minutes), then the thumbnail
cd video && npm run render && npm run thumbnail
```

Results in `video/out/`: `kshama-delhi-bus-crowding.mp4` (1920x1080, 30 fps, H.264 yuv420p faststart + AAC 48 kHz, -16 LUFS,
true peak under -1.0 dBTP), `captions.srt` (English, for the upload), `sync-table.md` (every caption against the speech it
sits on) and `thumbnail.png` (1280x720).

`import_extra.sh` finds `voice over /scene-NN.*` (the folder name ends with a space; scene 5 may also be named like
`scene 5 the planner in Phone.wav`, `Scene05 ...`, `scene-05 take 2.m4a`, any case: it becomes `public/vo/scene-05.<ext>`,
and a plain `scene-05.*` wins), `sound effects/*` and the music files ("startup ..." first). The opening is drawn, not filmed:
no footage is used.

## How the picture follows the voice

1. `prep_audio.sh` cleans each voice file (high-pass 80 Hz, denoise, silence trimmed to a 0.3 s lead, two-pass loudnorm to
   -16 LUFS) into `public/vo/clean/scene-NN.wav`. Scene 5 (five parts, 5a to 5e, in one file) gets its part starts from its
   pauses of 0.9 s or more (`scene-05.parts.json`); when there are more than four such pauses it picks the four that best fit
   the script's word shares and prints them all.
2. `scripts/scan_assets.mjs` runs `ffmpeg silencedetect` (-35 dB, pauses of 0.2 s or more) on every clean file and writes the
   pauses to `public/assets.json`.
3. **The voice sets the timeline.** A voiced scene lasts `HEAD + voice + TAIL` frames (`src/timing.ts`: a short lead before
   the first word, scene 1 two seconds of city first; a short tail after the last word, longer for the chip that grows in
   scene 4, the held sentence in scene 7 and the end card). The script's own lengths are used only when a scene has no voice.
4. **Phrases are placed on the speech.** The voice-over script is split into phrases at its pause marks (`src/captions.ts`).
   `src/sync.ts` turns the pauses into speech segments and places the phrases on them in order: every phrase boundary goes
   to a real pause, the one whose share of the speaking time best matches the phrase's share of the characters; if there are
   fewer pauses than boundaries, a segment is split by relative character length (none needed with the current takes).
5. **Everything is keyed to those times.** Captions start on the first word of their phrase; every visual beat of a scene
   (text reveal, tap, chip pop, camera move, counter, shot change, sound effect) is written as "phrase N" in the scene file
   (`useBeats()`), never as a fixed frame. Scene 5 cuts its five phone shots at the four pauses between parts (8 frames
   before the first word). `npm run sync-table` writes `out/sync-table.md` with every caption against its speech segment
   (drift is frame rounding only: at most 16.7 ms).

## Design system

`src/design.ts` holds the canvas (1920×1080), the safe area (96 px left and right, 72 px top; the bottom band is the
captions'), the type scale (display 96, h1 72, h2 52, body 40, caption 36, label 32, stat 120), colours (the app's level
colours on a dusk ground), radii, shadows, spacing and the two springs. Scenes take every size from it (a test fails on a
literal font size in a scene file).

Fonts are loaded explicitly (`src/fonts.tsx`): Inter for English and Noto Sans Devanagari for Hindi, through
`@remotion/google-fonts`. Nothing is drawn or measured until both are loaded and `document.fonts.ready` resolves
(`delayRender`), so a text is measured in the font it is painted in. Every dynamic string is fitted to its box with
`@remotion/layout-utils` (`FitText`, `fitLine`, `fitBlock` in `src/components/kit.tsx`): the scale size when it fits, a
measured smaller size otherwise, never below 32 px. Captions are phrase by phrase, at most two lines of at most 42
characters, in a box sized to the measured text, kept under the right column in scenes where the focus is on the left.

## The film works without your files

With nothing in `public/`, the film renders silent at the script's timing (`npm run draft`, about a minute).
`npm run studio` opens the live preview.

## Where the numbers come from

Nothing on screen is typed. `scripts/numbers.py` writes `src/numbers.json` from `data/processed/validation_report.json`
(headline numbers and evidence shares), `data/processed/manifest.json` (run id) and `data/processed/operator_trips.parquet`
(the top weekday DTC extra trip). The scenes read that file (counters count up to its values), and a test checks it against
the report.

```bash
cd video && npm run numbers        # same as: venv/bin/python video/scripts/numbers.py from the repo root
```

The phone and laptop pictures are real screenshots of the app running on the full data, taken by `scripts/capture.mjs` into
`public/captures/`; their sizes and element positions are in `src/captures.generated.json`. To retake them:

```bash
# from the repo root
venv/bin/python -m uvicorn src.api.main:app --port 8790 &
cd video && npm run capture           # needs Google Chrome; set CHROME_PATH to use another build; the map tiles need internet
kill %1
```

## Scenes

| # | What | Beats keyed to |
|---|---|---|
| 01 | A Delhi street at dusk, drawn: skyline, traffic, the stop; the phone (17:59 to 18:00), the bus pulls in full; the question | phone on phrase 1, bus as it ends, packed windows on 2, question on 3 |
| 02 | Name and promise over a stylised city map with a glowing corridor; the four level chips pop | title, tagline, chips with their pops |
| 03 | "Nobody counts people on Delhi buses"; three sources; the ticket counter; matched to timetable and GPS | each phrase |
| 04 | One ticket: stops, stretches, scaled up to everyone on board, the bus's limit, seats and rated total; the chip built word, dots, colour | each phrase; the three dots pop with three pops |
| 05 | The planner on a phone: journeys 1, 2 (tap the reverse), Why?, journey 4 (Leave later), Hindi and how sure, a real No data card, the chip family | five shots at the part pauses; each phrase inside |
| 06 | The operator view on a laptop: row 578DOWN picked, counters, the corridor map's time slider | each phrase |
| 07 | The evidence: hits tick, the Miss, the number line, ten of ten struck through, "No field count was possible." | each phrase |
| 08 | 89% Rough guess, who is missing from the data, the Phase 2 cards | each phrase |
| 09 | End card: live demo and GitHub links with QR codes, team, credit line | each phrase, then a still hold |

## Checks

```bash
cd video && npm test                                   # sync mapping, caption fit, timing, mix, forbidden words, import (node:test)
venv/bin/python -m pytest video/tests -q               # the numbers file against the validation report (from the repo root)
npx tsc --noEmit                                       # types
npm run captions && npm run sync-table                 # out/captions.srt and out/sync-table.md on their own
npm run stills -- out/stills auto                      # a frame in every phrase of every scene, for a visual check
```

## Rules the film follows

- The words are the app's words: *Usually seats*, *Usually standing*, *Usually crowded*, *No data*, *Rough guess*, *Based on
  many tickets*, *Fastest*, *Less crowded*, *Leave later*. A level is never shown by colour alone.
- Captions are burned in from the voice-over script text; the sentence "No field count was possible." is exact.
- Nothing below 32 px; everything inside the safe area; nothing overflows its box.
