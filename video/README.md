# Demo film (Remotion)

The 3-minute demo film for the Delhi Bus Crowding Planner, by **Team Kshama** (Aniket Ingale, Ashish Maurya). It is a
Remotion project: React components rendered frame by frame to H.264. The plan, the scene table, the voice-over script and
the animation spec are in [`docs/DEMO_VIDEO_SCRIPT.md`](../docs/DEMO_VIDEO_SCRIPT.md); this folder builds exactly that film.

1920×1080, 30 fps, 9 scenes, 5400 frames (3:00) before the voice is in.

> **Licence note.** Remotion is free for individuals and for companies of up to 3 people. Team Kshama is 2 people, so the
> free licence covers this film. Nothing here is a paid or hosted service.

## What is committed and what is not

Committed: the code, `package.json` with exact versions, `package-lock.json`, the numbers file `src/numbers.json`, the capture
metadata `src/captures.generated.json`, and the scripts. **Never committed** (see `.gitignore`): `node_modules/`, `out/`,
and everything you drop into `public/` (voice, music, sound effects, clips, app captures).

## One-time setup

```bash
cd video
npm install          # exact versions from package-lock.json; Remotion downloads its own headless Chrome on the first render
```

## The film works without your files

With nothing in `public/vo`, `public/music*`, `public/sfx` or `public/clips`, the film renders silent, with the motion-graphics
opening and the script's own timings. Render that draft any time:

```bash
cd video && npm run draft          # writes out/draft.mp4 (about a minute)
npm run studio                     # live preview in the browser
npm run thumbnail                  # writes out/thumbnail.png (1280x720)
```

## Dropping in your files

Put them here, then run the two commands under "To finish" below. Every file is optional.

| What | Where and name | What the film does with it |
|---|---|---|
| Voice-over | `video/public/vo/scene-01.m4a` ... `scene-09.m4a` (`.wav`, `.mp3`, `.aac`, `.aiff` also work). Scene 5 is one file with five parts and about 1.5 s of silence between them. | `prep_audio.sh` cleans each file (high-pass 80 Hz, denoise, silence trimmed to a 0.3 s lead, -16 LUFS) into `public/vo/clean/scene-NN.wav`. Each scene is as long as the script says, stretched only if its voice plus a 0.6 s tail is longer; the whole film stays within 2:50 to 3:10 by shortening holds, never speech. Scene 5's five phone shots follow the silences. Captions follow the speech. |
| Music | `video/public/music.mp3` (any `music*.mp3/.m4a/.wav`) | Ducked about 18 dB while speech plays, full level in the gaps, 1.5 s fade in, 2.5 s fade out. |
| Sound effects | `video/public/sfx/` with names like `whoosh`, `tap`, `pop`, `chime`, `riser`, `city-ambience`, `map-swoosh` (matched loosely by file name) | Placed at the cues the script names: street ambience and a whoosh in scene 1, taps on every tap ring, a chime on *Usually seats*, a riser as the crowd forms, a whoosh under the slider sweep. A missing effect is simply skipped. |
| Stock footage for the opening | `video/public/clips/*.mp4` | Replaces the motion-graphics bus stop in scene 1 (graded dark, with the phone, the clock and the question on top). |

The cleaned voice lengths are read by Remotion's `calculateMetadata`, so the timeline resizes itself. If the total would pass
3:10 the render prints a warning (the voice itself is too long: re-record or use the "Cut first" lines of the script).

## To finish (after your recordings are in `video/public/vo/`)

```bash
bash video/scripts/prep_audio.sh
cd video && npm run render
```

`npm run render` scans `public/` for your files and then runs

```bash
remotion render src/index.ts Main out/kshama-delhi-bus-crowding.mp4 --codec=h264 --audio-codec=aac --crf=18 --pixel-format=yuv420p
```

The result is `video/out/kshama-delhi-bus-crowding.mp4` (H.264 + AAC, 48 kHz). `prep_audio.sh` prints each scene's length and
loudness; the voice should read about -16 LUFS.

## Where the numbers come from

Nothing on screen is typed. `scripts/numbers.py` writes `src/numbers.json` from `data/processed/validation_report.json`
(headline numbers and evidence shares), `data/processed/manifest.json` (run id) and `data/processed/operator_trips.parquet`
(the top weekday DTC extra trip). The scenes read that file, and a test checks it against the report.

```bash
cd video && npm run numbers        # same as: venv/bin/python video/scripts/numbers.py from the repo root
```

The phone and laptop pictures are real screenshots of the app running on the full data (the journeys and the operator view),
taken by `scripts/capture.mjs` into `public/captures/`; their sizes and element positions are in `src/captures.generated.json`.
To retake them (for example after the screens change):

```bash
# from the repo root
venv/bin/python -m uvicorn src.api.main:app --port 8790 &
cd video && npm run capture           # needs Google Chrome; set CHROME_PATH to use another build; the map tiles need internet
kill %1
```

If a corporate proxy blocks Chrome from reaching `127.0.0.1`, the script already starts Chrome with `--no-proxy-server`.

## Scenes

| # | Frames (script) | What |
|---|---|---|
| 01 | 0-300 | Dusk at a bus stop, a phone, two buses, the question |
| 02 | 300-570 | Name, promise, the four level chips |
| 03 | 570-1020 | "Nobody counts people on Delhi buses", three sources, the pipeline |
| 04 | 1020-1740 | One ticket, five steps, a level |
| 05 | 1740-3180 | The planner on a phone: journeys 1, 2, 4, the Why? sheet, Hindi, a real No data card, the chip family |
| 06 | 3180-3840 | The operator view on a laptop: ranked trips, the time slider, the heat strip |
| 07 | 3840-4740 | The evidence: hits, the miss, the corridor check, "No field count was possible." |
| 08 | 4740-5130 | Limits (89% Rough guess) and what is next |
| 09 | 5130-5400 | End card: demo link, GitHub link, team, credit line |

## Checks

```bash
cd video && npm test                                   # timing, mix, captions, forbidden words (node:test)
venv/bin/python -m pytest video/tests -q               # the numbers file against the validation report (from the repo root)
npx tsc --noEmit                                       # types
bash scripts/stills.sh 120 900 2400                    # single frames to out/stills/ for a visual check
```

## Rules the film follows

- The words are the app's words: *Usually seats*, *Usually standing*, *Usually crowded*, *No data*, *Rough guess*, *Based on
  many tickets*, *Fastest*, *Less crowded*, *Leave later*. A level is never shown by colour alone.
- Captions are burned in at the bottom, at most two lines, from the voice-over script text; the sentence "No field count was
  possible." is exact.
- Fonts: the system font, with Noto Sans Devanagari for Hindi (fetched through `@remotion/google-fonts` at render time).
- Nothing below 32 px; titles stay inside the safe area.
