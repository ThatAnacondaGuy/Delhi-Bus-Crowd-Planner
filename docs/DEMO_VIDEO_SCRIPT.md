<!-- Plan for the ~3:00 demo film. Hand-written planning document (not rendered from a template): every number on screen is quoted from README.md or docs/TECHNICAL_NOTE.md, and tests/test_docs.py checks that. If the pipeline is re-run, re-check section 11. -->
<div align="center">

# Demo film: plan and voice-over script

### Delhi Bus Crowding Planner · 3:00 · 1920×1080 · 30 fps

*"See how crowded each stretch of your Delhi bus trip usually is, before you board."*

Transport Stack Hackathon 2026 · Phase 1 · Problem 2 · Aniket Ingale and Ashish Maurya (Ash)

</div>

**Status:** this is the plan the demo film was built from (Remotion motion graphics, 3:00 at 30 fps).

| At a glance | |
|---|---|
| Length | 3:00 exactly, 5400 frames at 30 fps, 9 scenes |
| Picture | 1920×1080, motion graphics plus real screen recordings of the live planner |
| Voice | one narrator (you), English, about 340 words at 140–150 words a minute; a few optional Hindi lines |
| Sound | calm music bed, light sound effects, voice at -16 LUFS |
| First 10 seconds | a real commuter moment, no logo, no title: a question every Delhi bus rider has asked |
| Last 10 seconds | the live demo link and the GitHub link, large and still |
| Rule | every number on screen or in the voice comes from the rendered README and technical note (section 11) |

---

## 1. Concept and tone

**One question, answered calmly.** At six in the evening a rider at a Delhi bus stop knows when the bus comes, and has no way to know whether it will have a seat or an hour of standing. The film opens on that moment, in the dusk blue of the end of a working day, then gives the answer in the app's own language: one word, three dots and a colour. The tone is that of a good documentary explainer: warm, steady and exact, with no hype and no hurry. Motion is data made visible: tickets flowing along arrows into a pipeline, a ticket spread over the stretches it rode, a slider sweeping a city from morning to evening. The emotional centre is the evidence scene: we show the hits, then the load-factor miss, and we let the miss land. The music thins, the word *Miss* appears in dark red, and the film moves on without apologising or hiding. Honesty is the signature of the piece, so the states *Rough guess* and *No data* are shown as features of the product, in full size, not as footnotes.

**Look.** Warm paper background (#f6f5f1) for the app scenes and a deep dusk ink (#0d1117) for the opening and the miss. The four level colours are the app's own, and they are never used alone: every level appears with its word and its dots.

| Token | Hex | Use |
|---|---|---|
| Paper | #f6f5f1 | background of app and diagram scenes |
| Ink | #1d2327 | text on paper |
| Accent blue | #1f4e79 | links, selected states, titles |
| Seats teal | #0f766e | *Usually seats*, hits, data in motion |
| Standing amber | #b45309 | *Usually standing*, caution |
| Crowded dark red | #8f1d1d | *Usually crowded*, the miss |
| No data grey | #5f6670 | *No data*, secondary text |
| Dusk ink | #0d1117 | cold open, miss beat |

**Type.** The system font stack (`-apple-system, "Segoe UI", Roboto, "Noto Sans"`) for English, Noto Sans Devanagari for Hindi, weights 400 and 700 only. Sizes at 1080p: titles 96 px, big numbers 160 px, captions and call-outs 40 px or more, nothing below 32 px. Keep titles inside a safe area of 96 px left and right and 54 px top and bottom.

**Editing grammar.** Cuts land on the music's bar lines. Voice leads picture by a few frames (a J-cut) wherever a screen recording starts. Every screen recording gets a slow push-in (a small scale change over its length) so a still app never feels dead. Fades are 12 frames; everything else is a hard cut or a match cut (the level chip on a phone card grows into the big chip in the next scene). Numbers count up, then stop and hold for a full second. One idea per scene, one new element at a time.

**What the film must not do.** No stock-photo montage of crowds, no sped-up traffic, no stereotypes of Delhi, no claim of accuracy, no bright "AI" visuals, no on-screen word the README does not use for the same thing. Never colour alone.

---

## 2. The story in five beats

The five beats of the design (the design's section on docs and submission) are the spine. The spec's first plan was 4–5 minutes; this cut fits them into 3:00 by giving each beat one clear job.

| Beat | Job | Scenes | Time |
|---|---|---|---|
| 0. Hook | A rider's real moment; the film's promise | 01, 02 | 0:00–0:19 |
| 1. Problem and data, stated honestly | Nobody counts people on buses; what we have instead; one ticket's story | 03, 04 | 0:19–0:58 |
| 2. The commuter planner | The brief's example, the reverse trip, *Why?*, *Leave later*, honest evidence labels, Hindi | 05 | 0:58–1:46 |
| 3. The operator view | Where one extra trip helps most | 06 | 1:46–2:08 |
| 4. Evidence | Written down first; hits, the miss, the weak corridor check; no field count | 07 | 2:08–2:38 |
| 5. Limits, Phase 2, and the call | Rough guess is the common case; what is next; live demo and GitHub | 08, 09 | 2:38–3:00 |

If you want a longer cut later (for example 4:30), the extra material is already planned: journeys 3 and 5 in full, the operator heat strip and cluster tab, and the sensitivity table. It is listed as B-roll in section 6.

---

## 3. Scene table

Timecodes are minutes:seconds; frames are at 30 fps. *Type* is how the scene is built: **MG** motion graphic, **SC** screen capture, **KT** kinetic type.

| # | Time | Frames | Type | Visual | On screen | Voice-over (gist) | Music and sound | Out |
|---|---|---|---|---|---|---|---|---|
| 01 | 0:00–0:10 | 0–300 | MG (stock optional) | Dusk at a bus stop; a phone shows a bus arriving; the doors open on a packed bus, then a second bus with free seats; the question hangs | `18:00 · Connaught Place`, then `A seat, or an hour on your feet?` | Your phone says the bus is coming; not whether you will sit | Street ambience from frame 0, air brake, low pad rising; one sparse note at the question | Cut to black, 6 frames |
| 02 | 0:10–0:19 | 300–570 | KT | Title builds word by word over paper; the level chip family appears small beneath | `Delhi Bus Crowding Planner` and the tagline | Name and promise | Music enters on the downbeat, warm and calm | 12-frame dissolve |
| 03 | 0:19–0:34 | 570–1020 | MG | The sentence *Nobody counts people on Delhi buses*; then three source cards (tickets, timetable, GPS) with packets flowing along arrows into the pipeline and out to the planner | `Nobody counts people on Delhi buses`, `2,559,899 app tickets · October 2026`, `Timetable · GPS` | The data we do have | Soft pulse; packet blips light and rhythmic | Push through the pipeline box |
| 04 | 0:34–0:58 | 1020–1740 | MG | One ticket's story in five steps: ticket, stretches, scaled up, against seats and rated total, level chip | Step captions; `about 1 in 44 riders`; the chip `●●○ Usually standing` | How a ticket becomes a level | Pulse builds a little; a tick on each step | The final chip grows; match cut to the phone |
| 05 | 0:58–1:46 | 1740–3180 | SC + MG | The commuter planner on a phone: the brief's example; the reverse; *Why?*; *Leave later*; evidence labels; Hindi; the chip family insert | Big captions beside the phone (section 6) | Five short lines, one per shot | Music at its fullest; taps on every press; a soft chime on *Usually seats* | Slide phone off to the left |
| 06 | 1:46–2:08 | 3180–3840 | SC + MG | The operator view: ranked extra trips, the time slider sweeping the corridor map from morning to evening | `578DOWN · 08:30`, `19,589 crowded rider-minutes removed`, `7,363 riders moved down a level` | Where one extra trip helps most | Music steady; a low whoosh on the slider sweep | 12-frame dissolve to dusk ink |
| 07 | 2:08–2:38 | 3840–4740 | MG + KT | The checklist written before the first run: hits tick teal; the load factor flips to a dark red *Miss*; the number line shows 0.54 against the published band; the corridor line is struck through and replaced by the stricter reading | `Hit`, `Miss`, `0.54`, `0.78–0.89`, `10.0 of 10`, `19% vs 10%`, `7 of 10`, `No field count was possible.` | Written down first; hits; the miss; no field count | Music drops to one held note under the miss, then resolves | Dissolve to paper |
| 08 | 2:38–2:51 | 4740–5130 | MG | A bar of all weekday bus-km: a sliver of many tickets, most of it Rough guess, a little No data; then four Phase 2 chips | `89% Rough guess`, `4.7% many tickets`, `6.4% No data`, `More months · On-bus count · Live arrivals` | Honest limits; what is next | Music lifts toward the resolution | Hard cut on a beat |
| 09 | 2:51–3:00 | 5130–5400 | KT | End card: still, large, calm | Live demo link, GitHub link, team, the credit line | The call | Final chord rings out; 1 second of tail | Fade to paper over the last 9 frames |

### Scene 05, shot by shot

| Shot | Time | Frames | Source | What happens |
|---|---|---|---|---|
| 5a | 0:58–1:08 | 1740–2040 | capture C01 | Journey 1, ISBT Anand Vihar → Connaught Place, weekday 18:00. Cards appear; push in to the *Fastest* chip, then the *Less crowded* chip |
| 5b | 1:08–1:16 | 2040–2280 | capture C02 | Tap the reverse preset, Connaught Place → ISBT Anand Vihar. The chip turns dark red; the *Leave later* card slides into view |
| 5c | 1:16–1:25 | 2280–2550 | capture C03 | Tap *Why?*; the sheet rises; push in to the people-on-board range against seats and rated total |
| 5d | 1:25–1:36 | 2550–2880 | capture C04 | Journey 4, Mandi House → Laxmi Nagar: the fastest card, then the *Leave later* card |
| 5e | 1:36–1:46 | 2880–3180 | C05, C06, MG | Hindi toggle, a one-second flash of journey 5 (*Less crowded* for a few minutes), then the chip family full screen |

---

## 4. Voice-over script

**How to read this.** Read only the lines that start with `>`. Marks: `/` is a short pause (a breath, about a third of a second); `//` is a long pause (nearly a second, let the picture speak); `**bold**` is a word to lean on, gently; `[...]` is a direction to you, not to be read. Lines that start with `> HI:` are optional Hindi lines, never counted in the time; the level names in them are the app's own words, the other Hindi lines are our draft and a Hindi speaker should check them before you record. Numbers are written as you say them. Pace: 140–150 words a minute; the whole film has about 340 words in 180 seconds, so there is room to breathe. Start each scene half a second after it begins, so the picture arrives first.

**Cut first.** If a take runs long once the voice is recorded, trim in the order given under "Cut first" in each scene.

### Scene 01 · Cold open (0:00–0:10)

> Your phone says the bus is coming. //
> Not whether you'll **sit** — / or stand for an hour.

[Tone: quiet, close, a little tired, like a real evening. Do not announce. Start after one second of street sound.]
**Cut first:** nothing; it is already short.

### Scene 02 · Name and promise (0:10–0:19)

> Delhi Bus Crowding Planner. //
> How crowded each stretch of your trip **usually** is — / before you board.

> HI: बस में चढ़ने से पहले जानिए, सफ़र के हर हिस्से में आमतौर पर कितनी भीड़ होती है।

[Tone: lift slightly, a smile in the voice. The Hindi line, if used, replaces the second English line on a second cut of the film; have a Hindi speaker check it before recording.]
**Cut first:** nothing.

### Scene 03 · The problem and the data (0:19–0:34)

> Nobody counts people on Delhi buses. //
> We started with what **is** recorded: / over two and a half million app tickets, from October twenty twenty-six, / matched to the timetable and to GPS.

[Tone: matter-of-fact. "Nobody counts" is the honest start; do not dramatise it.]
**Cut first:** "from October twenty twenty-six" (the date stays on screen).

### Scene 04 · One ticket's story (0:34–0:58)

> Every ticket records where a rider got on, and off. //
> We spread it over the stretches they rode, / then scale app riders up to everyone on board — / never more than a bus can **hold**. //
> Set that against the seats, / and you get one word, / three dots, / and a colour.

> HI: आमतौर पर सीट मिल जाती है। आमतौर पर खड़े होकर जाना पड़ता है। आमतौर पर भारी भीड़।

[Tone: explain it like you would to a friend across a table. The three Hindi levels, if used, play over the chip family on screen in scene 05e rather than here; they are listed so they are recorded once.]
**Cut first:** "and a colour" is the tagline: keep it; trim "never more than a bus can hold" last.

### Scene 05 · The planner on a phone (0:58–1:46)

Record the five parts one after another in one file, with a second and a half of silence between them (the editor cuts at the silences).

> **5a.** The brief's own example, six in the evening: / the fastest bus is usually **standing**. // A slightly slower one usually has **seats**.
>
> **5b.** Reverse it, and the answer changes: / usually **crowded**. // Same road, different direction. The planner knows.
>
> **5c.** Tap Why: app tickets, about one in forty-four riders, **scaled up**, against the seats and rated total.
>
> **5d.** Mandi House to Laxmi Nagar: crowded. // Leave a little **later**: same ride, room to stand. / Offered only when it's really better.
>
> **5e.** Each card says how sure we are — mostly, a **rough guess**. // Too little data? It says **No data**, never a seat.

> HI: 5e. जानकारी कम हो तो लिखा आता है — जानकारी नहीं।

[Tone: the confident centre of the film. Slightly brisker than the other scenes, but keep every pause: the picture does its work in them. In 5b, "usually crowded" goes down, not up.]
**Cut first:** "The planner knows." in 5b, then "Offered only when it's really better." in 5d, then "scaled up" stays, never cut it.

### Scene 06 · The operator view (1:46–2:08)

> A second screen is for bus operators. //
> Where would one extra trip help **most**? //
> On a weekday, route five-seven-eight Down at eight-thirty: / nearly twenty thousand crowded rider-minutes removed, / and over seven thousand riders moved down a level. //
> Model estimates, not counts.

[Tone: curious, then precise on the numbers. Say "five-seven-eight Down" as three digits and a word. "Model estimates, not counts" is a plain, quiet aside, not a disclaimer rush.]
**Cut first:** "Where would one extra trip help most?"

### Scene 07 · The evidence (2:08–2:38)

> We wrote down what we expected first. / Then reported every hit — and every **miss**. //
> Peaks at nine and seven: hit. / Published bus-kilometres: hit. //
> Load factor: a **miss** — / point five four, below the published band. //
> Ten of ten corridors? / Chance alone gives ten of ten. //
> No field count was possible.

[Tone: the most careful reading in the film. Give "a miss" a full stop of its own; do not rush past it and do not soften it. "Chance alone gives ten of ten" is said flat, as a fact. The last sentence is exact, word for word.]
**Cut first:** "Published bus-kilometres: hit.", then "Ten of ten corridors?" line (the on-screen text still shows it).

### Scene 08 · Limits and what's next (2:38–2:51)

> Most levels are a rough guess, / and buses can be **fuller** than shown. //
> Next: more months of tickets, / an on-bus count, / live arrivals.

> HI: ज़्यादातर अनुमान ही हैं — अंदाज़ा (कम टिकट)।

[Tone: plain and forward-looking, like closing a notebook. Do not apologise.]
**Cut first:** "live arrivals."

### Scene 09 · The call (2:51–3:00)

> Try it live — or run it yourself from GitHub. //
> Delhi Bus Crowding Planner. / Made by Aniket and Ash.

[Tone: warm, unhurried; land on "Ash" with a small smile, then stay quiet for the tail of the music. The links are read by the eye, not the voice.]
**Cut first:** "Made by Aniket and Ash."

**Totals.** About 340 spoken words, around 140 seconds of speech in 180 seconds, so roughly 40 seconds of music, sound and silence. If the finished voice is more than half a second longer than its scene, trim in the "Cut first" order before touching the picture.

---

## 5. Animation spec

Everything is built in Remotion as React components at 1920×1080, 30 fps, 5400 frames. **All motion is driven by the frame number** (`useCurrentFrame`, `interpolate`, `spring`), never by CSS animation: the animated SVGs in `docs/assets/` run on a wall clock and would not render the same on every frame, so they are **ported, not embedded**. Geometry (box positions, arrow paths, colours) is lifted from `docs/make_diagrams.py`; the packets move with `@remotion/paths` (`getLength`, `getPointAtLength`, `evolvePath`). Each scene is a `<Sequence from durationInFrames>` that fades itself in and out, so the total length is exactly 5400 frames. Durations below are in frames at 30 fps (30 frames is one second); *scene frame* means frames from the start of that scene.

**Easings (use only these).** `out-cubic` (arrivals: `Easing.out(Easing.cubic)`), `in-out-cubic` (moves and pushes), `spring-soft` (`spring` with damping 200, no overshoot: chips and cards), `linear` (packets on arrows, the clock).

### Scene 01 · Dusk and the question (300 frames)

- **Ground.** Dusk ink (#0d1117) with a slow vertical gradient to deep blue at the horizon; a faint street-light bloom on the left. Camera: a slow push-in, scale from 100 to 108 over all 300 frames, `in-out-cubic`.
- **Bus stop (frames 0–120).** Flat silhouettes of a shelter and a queue of 7 people fade in from 0 to full over 24 frames, staggered by 4 frames each. Two silhouettes shift weight (a 6 px sway, 90 frames per cycle, `in-out-cubic`).
- **Phone (frames 45–150).** A phone enters from bottom right, 18 frames, `out-cubic`, and settles in the foreground, out of focus background. The clock on the lock line changes from `17:59` to `18:00` at frame 75 (digit roll, 8 frames). The screen shows a plain planner row: `359UP · arriving`, with no crowd information at all.
- **The two buses (frames 120–255).** Headlights sweep in from the right (frames 120–150, `out-cubic`). Doors open (a vertical slice wipe, 15 frames). Interior one: silhouettes pack in, 14 figures staggered by 3 frames. Hard cut at frame 195 to interior two: 4 figures, rows of empty seats. Hold 30 frames.
- **The question (frames 225–285).** `A seat, or an hour on your feet?` fades in word by word, 6 frames apart, 56 px, paper colour on dusk. Everything else dims to 30 percent over 18 frames.
- **Out (frames 294–300).** Cut to black.
- **Optional upgrade.** Replace the silhouettes with 5–8 seconds of licensed footage (section 10); keep the phone, the text and the colour grade. Plan B above needs nothing from outside.

### Scene 02 · Name and promise (270 frames)

- Paper background wipes in from the left over 15 frames.
- `Delhi Bus Crowding Planner`, 96 px, accent blue, reveals word by word: each word rises 24 px and fades in over 12 frames, 8 frames apart, `out-cubic`.
- Frame 60: the tagline, 44 px ink, fades in line by line (12 frames each).
- Frame 120: the chip family (`●○○ Usually seats`, `●●○ Usually standing`, `●●● Usually crowded`, `○○○ No data` with a dashed grey outline) pops in at 50 percent size, `spring-soft`, 6 frames apart; they sit small under the title like a legend.
- Frame 240–270: 12-frame dissolve.

### Scene 03 · What we have (450 frames)

- **Frames 0–60.** Large type `Nobody counts people on Delhi buses` appears in two lines (words 6 frames apart), then moves up 80 px and shrinks to 56 px over 24 frames.
- **Frames 60–180.** Three source cards enter from the left, 12 frames apart, `spring-soft`: `ONDC app tickets`, `GTFS timetable`, `GPS feed`. In the first card a counter runs from 0 to `2,559,899` over 60 frames (`out-cubic`), then holds; beneath it `October 2026`.
- **Frames 150–330 (the live arrows).** From each card an arrow draws itself to the pipeline lane (`evolvePath`, 24 frames, `in-out-cubic`). Then small packets (14 px circles in teal) travel along each arrow on `linear`, one packet every 18 frames, 60 frames to cross. The twelve stage chips of the pipeline (clean, resolve, network clock and assets, GPS trips that ran, riders on stretches, alighting correction, supply, scale, levels and evidence, operator ranking, validate, render) light up in order, 8 frames apart, teal fill and a soft glow that holds. Packets then leave to `Planner and API` and fan to three small screens (commuter, operator, live demo).
- **Frames 330–420.** Everything except the first stage lane dims to 25 percent; the camera pushes forward through the pipeline box (scale 100 to 140, 60 frames, `in-out-cubic`) so that the next scene starts inside it.
- Reduced detail rule: the stage chips carry 22 px labels; they are texture, not meant to be read in 8 frames. The voice names only three sources.

### Scene 04 · One ticket, five steps (720 frames; 144 frames a step)

Geometry from `how-it-works.svg` (viewBox 960×440, scale 2 for 1920×880 centred). Each step: the step number badge pops in (`spring-soft`, 9 frames); a caption (44 px) fades in beside it; a tick sound on the badge.

1. **A ticket (0–144).** A ticket slides in from the left (18 frames, `out-cubic`): `Stop A → Stop D`, `boarding → alighting`. Stops A to D draw as dots on a line, 8 frames apart.
2. **Stretches (144–288).** The ticket's ride highlights stretch by stretch (A–B, B–C, C–D), 24 frames each, the highlight a teal bar thickening from 4 to 14 px. A small clock under each stretch shows the bus passing at its own time.
3. **Scaled up (288–432).** The single rider icon multiplies into a crowd on the bus: 1 figure becomes 44 figures in 60 frames (staggered, `spring-soft`), with the caption `about 1 in 44 riders`. A stop line appears at the bus's capacity; figures beyond it do not appear (`never more than a bus can hold`).
4. **Against seats (432–576).** A bar of seats (teal) then rated total (amber) draws left to right (30 frames each); a marker slides to the crowd size (30 frames, `in-out-cubic`).
5. **A level (576–720).** The marker's zone becomes the chip `●●○ Usually standing`; it grows from 60 percent to 100 percent over 18 frames and, in the last 24 frames, scales up to fill the middle of the screen as the match cut into scene 05.

### Scene 05 · The planner (1440 frames)

- **Layout.** A drawn phone frame (a plain rounded rectangle, no brand device) on the left, 450×960; the capture plays inside it. On the right a column of captions, 40–56 px, ink on paper. Frame content comes from `OffthreadVideo` clips (section 6). Paper background; a very light drop shadow under the phone.
- **Each shot.** Phone slides in from the left on 5a (24 frames, `out-cubic`) and stays for the whole scene. Captions change per shot: fade out 6 frames, fade in 12 frames.
- **Tap ring.** A ring (56 px, accent blue, 3 px) scales from 60 percent to 140 percent and fades over 12 frames at every tap position; add a small `tap` sound.
- **5a.** Caption `Fastest: Usually standing` then `Less crowded: Usually seats`. Push-in on each chip (scale 100 to 118 over 30 frames, `in-out-cubic`), the other half of the screen dims to 70 percent.
- **5b.** Caption `The same road, the other direction`. After the tap, the chip colour crossfades over 8 frames to dark red; the *Leave later* card slides up 40 px (18 frames, `spring-soft`) and a highlight ring pulses once.
- **5c.** The *Why?* sheet rises (24 frames, `out-cubic`). Callout lines draw to `about 1 in 44 riders`, the people-on-board range, `seats`, `rated total`. Zoom into the sheet text (scale 100 to 130).
- **5d.** Split caption: `Fastest · Usually crowded` then `Leave later · Usually standing`; between them a thin arrow draws from the first chip to the second.
- **5e.** The phone slides left and shrinks to 70 percent (24 frames). **Chip family:** four large chips stack in a column, 12 frames apart, each with its Hindi (`आमतौर पर सीट मिल जाती है`, `आमतौर पर खड़े होकर जाना पड़ता है`, `आमतौर पर भारी भीड़`, `जानकारी नहीं`). A small label crossfades beside the chips: `Rough guess · अंदाज़ा (कम टिकट)` and `Based on many tickets · कई टिकटों पर आधारित`. The `No data` chip pulses once (its dashed outline draws around it over 24 frames) as the voice says "No data". A final 24-frame slide-off to the left clears the stage.

### Scene 06 · The operator view (660 frames)

- The 1440×900 capture is scaled to fit the height (1080), centred, in a thin paper-white frame on dusk ink for contrast (fade ink from paper over 18 frames).
- **Frames 30–210.** Push-in to the ranked table; row 1 (`578DOWN`, `08:30`) is highlighted (a teal outline draws around it over 18 frames). Two numbers count up beside the row at 120 px: `19,589` with the label `crowded rider-minutes removed`, and `7,363` with `riders moved down a level`. Count 0 to value over 45 frames, `out-cubic`, then hold. Small line below: `model estimates, scaled from app tickets`.
- **Frames 240–510.** Camera pans to the corridor map. The slider thumb moves from `09:00` to `19:00` over 150 frames (`in-out-cubic`); the clock label updates every frame; the map recolours with the capture. A low whoosh runs under the slider.
- **Frames 510–660.** Pull back to the whole page; the *Route heat strip* for 578DOWN is highlighted, then 12-frame dissolve out.

### Scene 07 · The evidence (900 frames)

- **Ground.** Dusk ink background; paper-white checklist card, 1200 px wide, centred.
- **Frames 0–120 (written first).** Title `Written down before the first full run`; a file icon labelled `expectations.yaml` slides in and a lock closes on it (9 frames). Rows appear one by one below, 12 frames apart, each a pill with a grey outline.
- **Hits (frames 120–420).** For each hit, the pill outline fills teal and a tick draws (12 frames), with the row text: `Peaks 09:00 and 19:00 · Hit`; `Weekends lower and flatter · Hit`; `Direction: 80% of 359 route pairs in the morning, 78% in the evening · Hit`; `Bus-km 496,158 against 501,000 published · Hit`; `Two different weeks: 76% keep their level · load correlation 0.78`. Spaced 45 frames apart to match the voice (voice names the first two and the bus-km one).
- **The miss (frames 420–630).** The music thins. The next row slides in: `Load factor 0.54 · published 0.78–0.89`. Its outline fills dark red and a cross draws (18 frames); the word `Miss` scales in at 120 px, dark red, `spring-soft`. A horizontal number line draws underneath (30 frames): the published band as a teal bar from `0.78` to `0.89`, the model's `0.54` as a dark red marker to its left, and `1.70` as an amber marker far to its right labelled `all published ridership placed`. A thin bracket draws from 0.54 to 1.70: `the truth is somewhere between`. Hold 60 frames.
- **The corridor row (frames 630–810).** A row `10 of 10 corridors` fills teal for 12 frames, then a strike line draws through it (12 frames) and `chance alone gives 10.0 of 10` appears beside it. Beneath it two stricter lines draw in: `19% of corridor stretches in the top decile, chance 10%` and `7 of 10 with both ends on the corridor`.
- **Frames 810–900.** All rows dim to 30 percent; large type `No field count was possible.` fades in centred, 72 px, paper on dusk, held for the last 60 frames, then a 12-frame dissolve to paper.

### Scene 08 · Limits and next (390 frames)

- **Bar (frames 0–150).** A single horizontal bar of all scheduled bus-km (1400 px wide) draws in three parts (30 frames each, `in-out-cubic`): a thin teal segment `4.7% many tickets`, a long amber-grey segment `89% Rough guess`, a short grey dashed segment `6.4% No data`. Labels arrive under each segment, 44 px. A small line: `about 1 in 44 riders, women riding free and pass holders not in this data`.
- **Frames 150–330.** The bar slides up and dims; four Phase 2 chips pop in 8 frames apart: `More months of tickets`, `An on-bus count`, `GPS stop times`, `Live arrivals`.
- **Frames 330–390.** Chips fade; the next scene starts with a hard cut on the beat.

### Scene 09 · End card (270 frames)

- Paper background. Title `Delhi Bus Crowding Planner` (96 px, blue) is already in place at frame 0.
- Frame 6: two large link bars appear one under the other, 12 frames apart: `Live demo  huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner` and `GitHub  github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner`; each with a QR code on the right (160 px, drawn with the `qrcode` npm package at build time, high error correction, quiet zone kept).
- Frame 36: `Aniket Ingale · Ashish Maurya (Ash)` and the credit line `Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.` (36 px, ink and grey).
- Frames 36–261: everything holds still; the only motion is a slow 6 px drift of the background. Last 9 frames: fade to paper.
- **Check before render.** The live demo link may 404 until the Space is published; render this scene last, after you have opened the link yourself.

---

## 6. Screen-capture shot list

**Set-up (once).** Start the full planner locally: `uvicorn src.api.main:app --port 8771` (the live demo's precomputed answers come from the same tables). Use Chrome with a clean profile, bookmarks bar hidden, no extensions. Commuter shots: DevTools device mode at 390×844, device pixel ratio 2, record the viewport only. Operator shots: window 1440×900. Record with QuickTime Player (File → New Screen Recording, select the area) or ask Claude to script and record the captures with the browser tools so they are repeatable. Hide the real mouse pointer and let the film draw its own tap rings. Do each take slowly: 1 second hold before the first action, 2 seconds hold after the last. Operator map tiles load from the internet and show the OpenStreetMap credit; keep it visible in the frame.

**Format.** ProRes or high-quality H.264, at least 30 fps, no audio. Name `C01-journey1.mov` and so on, saved in `video/captures/` (not committed).

| ID | Scene | Page and state | Actions and timing | Needed for |
|---|---|---|---|---|
| C01 | 5a | `/?from=ISBT Anand Vihar&to=Connaught Place&depart=18:00&day=weekday` | Load; hold 2 s; slow scroll down to the second card over 3 s; hold 2 s on its chip | Journey 1, the brief's example |
| C02 | 5b | Same page; tap the preset `Connaught Place → ISBT Anand Vihar`, weekday 18:00 | Tap; hold 2 s; scroll to the *Leave later* card over 3 s; hold 2 s | Journey 2, the reverse |
| C03 | 5c | After C02 or C01 | Tap *Why?*; hold 1 s as the sheet opens; scroll slowly through it over 5 s; hold 2 s; tap *Close* | The *Why?* sheet |
| C04 | 5d | `/?from=Mandi House&to=Laxmi Nagar&depart=18:00&day=weekday` | Load; hold 2 s; scroll to *Leave later*; hold 3 s | Journey 4 |
| C05 | 5e | Any journey; tap the Hindi toggle (हिं) | Hold 2 s on English, tap, hold 3 s on Hindi chips, tap back | Hindi |
| C06 | 5e | `/?from=Ambedkar Nagar&to=AIIMS&depart=09:00&day=weekday` | Load; hold 2 s on the *Less crowded* card (a few minutes slower) | Journey 5, flash |
| C07 | B-roll | `/?from=Ambedkar Nagar&to=ITO&depart=09:00&day=weekday` | Load; hold 3 s | Journey 3, extended cut |
| C08 | B-roll | Any journey; tap *I need a seat* | Tap; hold 3 s | Extended cut |
| C09 | 06 | `/operator` weekday, DTC tab | Load; hold 2 s; hover then click row 1 (`578DOWN`); wait for the route heat strip; hold 3 s | Ranked table |
| C10 | 06 | `/operator`, corridor map | Drag the slider from `09:00` to `19:00` over about 8 s, then hold 2 s; the map must be visible throughout | Time slider sweep |
| C11 | B-roll | `/operator`, Cluster tab, Weekend tab | Switch tabs slowly, 2 s each; hover *Download CSV* | Extended cut |
| C12 | 5e or 08 | Operator heat strip legend | Hold 3 s on the legend that shows *No data* as grey | A *No data* cell on a real screen |

**A real *No data* card.** The commuter card shows *No data* when more than half of the ride is unknown. On capture day, Claude searches the planner for one real journey whose headline is *No data* and records it as C13. If none turns up, the chip family in 5e and the heat-strip legend (C12) carry that beat. Nothing is faked: a card is shown only if the app produced it.

**Check the screen against the voice on capture day.** The five journeys are quoted in the README table (journey 1 and 2: standing and crowded by direction; journey 4: a *Leave later* card; journey 5: a *Less crowded* option for a few minutes). If a take disagrees with a line in section 4 (a chip word or a role), change the voice line, not the capture.

---

## 7. Sound

**Music.** One instrumental bed, 90 to 100 BPM, calm and confident: warm piano or soft synth pads, gentle pulse, no vocals, no big drops. It breathes: low under scenes 01–04, a little fuller in 05–06, almost silent for one held note under the miss in 07, a lifted resolve in 08 and a final chord in 09. Choose from royalty-free libraries that allow use in a competition submission (YouTube Audio Library, Pixabay Music, or a similar free service); save the licence text with the file; look for tracks with a steady pulse so cuts can land on bars. Read the hackathon rules on third-party music first.

**Sound effects.** Light and sparse; each one has a job.

| Scene | Cue |
|---|---|
| 01 | Street ambience from frame 0 (distant traffic, a horn); an air brake as the bus arrives; doors opening |
| 03 | Soft blips as packets enter the pipeline (a short high sine, a different pitch per source) |
| 04 | One tick per step, five in all; a soft rising tone as the crowd forms |
| 05 | A tap sound on each tap ring; a gentle chime on *Usually seats*; a low note on *Usually crowded* |
| 06 | A count-up tick under each number; a low whoosh under the slider sweep |
| 07 | A soft tick on each hit; silence, then one low note on *Miss* |
| 09 | The final chord rings; nothing else |

Free sources: Freesound (filter by CC0), Pixabay sound effects. Tick, blip and whoosh can also be generated with ffmpeg (`lavfi` sine and noise sources) if no download is wanted.

**Mix.** Voice first. After clean-up the voice sits at -16 LUFS integrated. The music is ducked about 10 dB under every voice line (side-chain compression in ffmpeg, or by volume automation in Remotion's `<Audio volume>`) and returns in the gaps over 12 frames. Sound effects sit well under the voice. Peak limit about -1 dB. Final audio: AAC, 48 kHz, stereo.

**Clean-up of the recordings (ffmpeg).**

```bash
ffmpeg -i scene-01.m4a -af "highpass=f=80,afftdn=nr=12:nf=-40,loudnorm=I=-16:TP=-1:LRA=11" -ar 48000 vo/scene-01.wav
```

Run it once per scene; check each file by ear, then measure its length with `ffprobe` to fix the final timings (section 9).

---

## 8. Voice-recording guide

1. **Room.** The quietest room you have. Soft things absorb sound: a bedroom with a wardrobe, a duvet over your head and the phone. Switch off fans, air conditioners and fridges for the takes; close windows; put the phone on Do Not Disturb or aeroplane mode.
2. **Phone.** Use the phone's own recorder (Voice Memos on iPhone, set to the best quality; the recorder app on Android). Hold or prop the phone 15–20 cm from your mouth, a little to one side so breath does not hit the microphone. Keep it still. Wired earphones are fine for monitoring.
3. **Each file starts with 2 seconds of silence.** Press record, say nothing for 2 seconds (the editor uses it to measure the room noise), then read.
4. **One file per scene**, named `scene-01.m4a`, `scene-02.m4a`, up to `scene-09.m4a`. Scene 05 is one file with a second and a half of silence between its five parts (5a to 5e). Optional Hindi lines go in separate files named `scene-02-hi.m4a`, `scene-04-hi.m4a`, `scene-05e-hi.m4a`, `scene-08-hi.m4a`.
5. **Read the text only, not the marks.** `/` short breath, `//` longer pause, **bold** a gentle lean, and the `[...]` lines are directions.
6. **Pace.** About 145 words a minute: slower than you would talk to a friend, faster than a newsreader. Read the scene aloud once with a stopwatch; scene 03 must not run past 15 seconds, scene 07 past 30.
7. **Tone.** Calm, warm, steady, close. Smile slightly on scene 02 and the last line. Do not perform. The numbers and the word *miss* are said as plainly as any other word.
8. **Takes.** Record each scene three times and keep them all; the editor picks. If you stumble, stop, wait a second, and start the sentence again; do not stop recording. Pick up from the last full sentence.
9. **Pronunciations.** ONDC (O-N-D-C), GTFS (G-T-F-S), GPS (G-P-S), ITO (I-T-O). Connaught (KON-awt). Anand Vihar, Laxmi Nagar, Mandi House. Aniket Ingale, Ashish Maurya (Ash). "578" is said five-seven-eight.
10. **Send** the files as they are (no editing, no noise filters in the phone app). Share the folder through any link that keeps the original quality.

---

## 9. Build plan

**Order of work (tomorrow, after your recordings).**

1. **Set up (about 30 minutes).** `npx create-video` for Remotion 4.x with TypeScript, pin exact versions; add `@remotion/paths` and `qrcode`; load the fonts (system stack, Noto Sans Devanagari from a local file through `staticFile`). Define the colour and easing tokens once in `theme.ts`. Folder `video/` at the repo root; outputs and captures are listed in `.gitignore` (the repository forbids committing media over 5 MB and data files).
2. **Capture the screens** (section 6), then crop and trim them.
3. **Build the heavy scenes first:** 04 (ticket story), 05 (planner), 07 (evidence), then 03, 06, 08, 09, and 01 last.
4. **Import the voice.** Clean up with the ffmpeg line in section 7, then read each file's length with `ffprobe`. Compare with the scene's slot. If a voice file is longer than its scene by up to half a second, shorten the scene's still tail first; beyond that, trim in the "Cut first" order, or take another take. Animations are keyed to absolute frames inside each scene, so a late hold can be shortened without touching earlier timing.
5. **Mix** music, effects and voice (section 7); check the loudness with `ffmpeg -i mix.wav -af loudnorm=I=-16:print_format=summary -f null -`.
6. **Render.**

```bash
npx remotion render src/index.ts Main out/silent.mp4 --codec=h264 --crf=18 --pixel-format=yuv420p
ffmpeg -i out/silent.mp4 -i audio/mix.wav -c:v copy -c:a aac -b:a 192k -shortest out/delhi-bus-crowding-planner.mp4
```

7. **Captions.** Burn English captions in at the bottom (40 px, paper on a dusk-ink strip) and also produce a `.srt` of the same lines. The captions follow the voice, with digits where the voice says them as words (`0.54` for "point five four").
8. **Quality check** (below), then upload where you tell us (section 10) and test the link in a private window.

**Checks before export.**

- Every number on screen is in section 11 and matches the README and the technical note. Nothing else is typed.
- The words are the app's words: *Usually seats*, *Usually standing*, *Usually crowded*, *No data*, *Rough guess*, *Based on many tickets*, *Fastest*, *Less crowded*, *Leave later*.
- No level is shown by colour alone. Nothing on screen is smaller than 32 px; titles sit in the safe area.
- The word *accuracy* never appears on screen, in captions or in the voice, and neither do the technical names the README leaves out.
- The honest scenes (07 and 08) are as large and as slow as the proud ones.
- No clipping in the audio; the voice is clearly above the music in every scene.
- The first frame is not black for more than 6 frames; the first 10 seconds work with the sound off (watch it once muted).
- The end card links open.

---

## 10. What we need from you

**To decide (reply with a word each).**

| # | Decision | Default if you say nothing |
|---|---|---|
| 1 | Runtime: 3:00 as planned, or the spec's longer 4–5 minute cut | 3:00 |
| 2 | Hindi: skip, or record the optional Hindi lines | Skip, and show Hindi only on screen |
| 3 | Captions burned into the picture | Yes, plus an `.srt` file |
| 4 | Where the video will be hosted (the submission needs a link: for example an unlisted YouTube video) | You tell us |

**To send (must-haves).**

| Item | Detail |
|---|---|
| Voice recordings | `scene-01.m4a` to `scene-09.m4a` as in section 8, with scene 05 as one file; at least three takes of each |
| A confirmed live demo | The Hugging Face Space published, so that the end card shows a working link (open the link before we render scene 09) |
| A music track | Your pick of 2–3 candidates that we list for you; send the track and its licence text |
| Spellings | Confirm `Aniket Ingale`, `Ashish Maurya (Ash)` and the title `Delhi Bus Crowding Planner` as shown on the end card |

**To send (nice to have, each one lifts the film).**

| Item | Why |
|---|---|
| A better microphone | A USB or lavalier microphone makes the voice more present; the phone is good enough |
| 5–8 seconds of your own footage of a bus stop or bus interior at dusk (only if safe and permitted to film; no faces) | A real texture for scene 01 instead of the drawn silhouettes |
| A native Hindi speaker | To check the optional Hindi line in scene 02 and to record the Hindi lines |
| Permission to show logos | We use text credit only unless you want the Transport Stack, ONDC or IIIT Delhi logos and the hackathon rules allow them |
| A short thumbnail text | If the video host asks for a poster frame; we will otherwise use the title card |

**Already on this computer.** Chrome, Node and ffmpeg are installed. Remotion and its packages will download on first use, so tomorrow needs an internet connection and a few minutes (it also fetches a headless browser for rendering).

---

## 11. Numbers on screen and in the voice-over

Every figure the film shows or says is listed here, with how it is said and where it comes from in the rendered documents. A test (`tests/test_docs.py`) checks that each value below appears in the README, the technical note or the proposal. If the pipeline is re-run and a number changes, change it here, on screen and in the voice together.

| ID | On screen | Said as | Source |
|---|---|---|---|
| N1 | 2,559,899 | over two and a half million | README (The problem); note section 1 |
| N2 | October 2026 | October twenty twenty-six | README (The problem) |
| N3 | 1 in 44 | about one in forty-four riders | README (Limits); note section 5 |
| N4 | 09:00 and 19:00 | nine and seven | README (trust table, Peaks) |
| N5 | 496,158 | not said (only "hit") | README (trust table, bus-km) |
| N6 | 501,000 | not said | README (trust table, bus-km) |
| N7 | 0.54 | point five four | README (trust table, load factor) |
| N8 | 0.78–0.89 | "the published band" | README (trust table, load factor) |
| N9 | 1.70 | not said | README (load-factor box) |
| N10 | 10.0 of 10 | ten of ten, from chance alone | README (trust table, corridors) |
| N11 | 19% | not said | README (trust table, corridors) |
| N12 | 7 of 10 | not said | README (trust table, corridors) |
| N13 | 80% of 359 | not said | README (trust table, direction) |
| N14 | 76% | not said | README (trust table, week to week) |
| N15 | 0.78 | not said | README (trust table, week to week) |
| N16 | 89% | "most levels are a rough guess" | README (Limits) |
| N17 | 4.7% | not said | README (Limits) |
| N18 | 6.4% | not said | README (Limits) |
| N19 | 19,589 | nearly twenty thousand | note section 2.9 |
| N20 | 7,363 | over seven thousand | note section 2.9 |
| N21 | 578DOWN | five-seven-eight Down | note section 2.9 |
| N22 | 08:30 | eight-thirty | note section 2.9 |

**Not in this table on purpose.** Journey durations, times and fares shown in the phone captures come from the live app on capture day and are never typed into captions or the voice (the voice says "a slightly slower one", "a little later", "a few minutes"). The levels said in the voice for the five journeys are the ones in the README table.

**The credit line and the sentence that must be heard.** The end card carries, exactly: *Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.* The voice says, exactly: *No field count was possible.* Links on the end card: https://huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner and https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner.
