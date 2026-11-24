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
| Music | `video/public/music-1.mp3`, `music-2.mp3` (any `music*.mp3/.m4a/.wav`; played in file-name order). One file also works. | Track 1 from the start; track 2 crossfades in (4 s, equal power, centred on the scene boundary closest to 1:55). Each track is first trimmed to the same loudness (-18 LUFS, measured by `scan_assets.mjs`; the two files differ by about 8 LU). Ducked about 18 dB under speech, full level in the gaps, 1.5 s fade in, 2.5 s fade-out that starts where the last voice line ends (the end card keeps 2.5 s after it). A scene without a voice file yet (scene 5) is ducked only about 8 dB so the film is not dead. |
| Sound effects | `video/public/sfx/` with names like `whoosh`, `swoosh`, `swoop`, `tap`, `pop`, `chime`, `ding`, `riser`, `road city ambience`, `city ambience`, `engine`, `hiss`, `horn` (matched loosely by file name) | Subtle, well below the voice, loud files trimmed first. Scene 1: road and city ambience, horn, engine idling, door hiss. A swoosh or swoop into scenes 3 to 8. Taps on tap rings, a bubble pop on each level chip, a soft bell chime when a level lands, a ding on the *Leave later* tip, a riser that ends on the reveal (scene 4 and scene 8), a swoosh under the slider sweep. A missing effect is simply skipped. |
| Stock footage for the opening | `video/public/clips/*.mp4` | Replaces the motion-graphics bus stop in scene 1 (graded dark, with the phone, the clock and the question on top). |

If you keep your files in `video/extra resources/` (`voice over /scene-NN.wav` (the folder name ends with a space, which the script handles), `sound effects/*.mp3`, `bgm/` with files with "background" or "music" in the name), run `bash video/scripts/import_extra.sh` first: it copies them into the folders above (music as `music-1`, `music-2`, "startup ..." first) and never touches the originals. `video/extra resources/` is git-ignored like the rest of the media.

The cleaned voice lengths are read by Remotion's `calculateMetadata`, so the timeline resizes itself. If the total would pass
3:10 the render prints a warning (the voice itself is too long: re-record or use the "Cut first" lines of the script).

## To finish (when `scene-05.wav` arrives)

Scene 5 (the planner on a phone) is the one voice file still to come. Until it exists the film shows scene 5 at the script's timing, with captions, a soft music bed and no voice (that is the near-final). When the file is there:

```bash
# 1. drop scene-05.wav (or .m4a/.mp3) into  video/extra resources/voice over /   (next to the other scenes)
bash video/scripts/import_extra.sh      # copies the voice, sound and music files into video/public/ (originals untouched)
# 2. one prep command: clean every voice file (-16 LUFS), find the five parts of scene 5 from its pauses, rescan the files
bash video/scripts/prep_audio.sh
# 3. one render command
cd video && npm run render
```

The result is `video/out/kshama-delhi-bus-crowding.mp4` (1920x1080, 30 fps, H.264 + AAC 48 kHz) and `video/out/captions.srt` (English, for the YouTube upload). If you put the file straight into `video/public/vo/scene-05.wav`, skip step 1.

`npm run render` (`scripts/render.sh`) does four things: scans `public/`, writes `out/captions.srt`, renders with Remotion, then masters the audio (`scripts/master.sh`: two-pass loudnorm to -16 LUFS, a limiter at -1.5 dBFS so the true peak stays under -1.0 dBTP, AAC 256 kbps; the picture is copied) and prints the measured loudness and true peak. `npm run near-final` does the same into `out/near-final.mp4`.

`prep_audio.sh` prints each scene's length and loudness; the voice reads about -16 LUFS. The timeline resizes itself to the voice (scene = script length, stretched only if its voice plus a 0.6 s tail is longer; the end card keeps 2.5 s after its voice). Scene 5's five phone shots follow the four pauses of about 1.5 s in its recording; if `prep_audio.sh` does not find four it says so and the script split is used.

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
npm run captions                                       # writes out/captions.srt on its own
bash scripts/stills.sh 120 900 2400                    # single frames to out/stills/ for a visual check
```

## Rules the film follows

- The words are the app's words: *Usually seats*, *Usually standing*, *Usually crowded*, *No data*, *Rough guess*, *Based on
  many tickets*, *Fastest*, *Less crowded*, *Leave later*. A level is never shown by colour alone.
- Captions are burned in at the bottom, at most two lines, from the voice-over script text; the sentence "No field count was
  possible." is exact.
- Fonts: the system font, with Noto Sans Devanagari for Hindi (fetched through `@remotion/google-fonts` at render time).
- Nothing below 32 px; titles stay inside the safe area.
