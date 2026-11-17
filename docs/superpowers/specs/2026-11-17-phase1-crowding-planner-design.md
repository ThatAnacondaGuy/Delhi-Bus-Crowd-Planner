# Phase 1 design: crowding model and journey planner (v2)

Transport Stack Hackathon 2026, Problem 2 (crowdedness-aware journey planner, Delhi buses).
v1 written 17 Nov 2026. v2 revised the same night after five independent reviews: a builder check, plus a statistician, a hackathon judge, a delivery lead and a Delhi bus-operations expert. Every fix below was either checked against the data or agreed by several reviewers.
Phase 1 submission closes **24 Nov 2026, 23:59 IST**; we submit by **18:00 IST**.

## 1. Intent

Delhi bus riders choose trips by time alone because no planner knows how full buses are. We are building a pipeline that turns one month of ticket data into honest crowding estimates by route, direction, stretch between stops and time of day, and a planner that shows those estimates next to each trip option, so a commuter can trade a faster trip for a more comfortable one. A second view shows bus operators and planners where buses are overloaded and where one extra trip helps most.

The judges score two things: how well the crowding estimate is grounded in the data, and how clearly it is shown. The brief says a simple planner with a sound crowding model beats a polished planner with a weak one. So the model and its evidence come first, then a clear screen.

The team wants something that would survive real Delhi use, so the design is honest by default:
- No invented values.
- Every estimate carries an evidence state.
- What we can and cannot measure is published: week-to-week repeatability from the tickets, and a small field count of real buses as ground truth.

## 2. Goals, non-goals, anti-goals

**Goals (Phase 1, by 24 Nov)**
1. A re-runnable pipeline: raw tickets + GTFS (+ a small committed GPS aggregate) to crowding tables with one command.
2. Crowding per route, direction, stretch and time window for weekdays and weekends: people on board as a range, a commuter level, and an evidence state.
3. A corridor view: the same estimates combined across all routes for each road stretch, so maps show "how crowded is this road at 6 pm".
4. Validation:
   - invariant checks that stop the run
   - pattern checks written down before the first run
   - week-to-week repeatability
   - a field count of real buses compared with the model
5. A planner with three option roles (Fastest, Less crowded, Leave later), each showing times, level, crowded stretch and the trade-off.
6. An operator view ranking the extra trips that would remove the most crowded rider-minutes, with CSV export.
7. A technical note, proposal and demo video whose every number comes from the pipeline's own output.

**Non-goals (designed now, built in Phase 2 or later)**
- Public hosting for lakhs of users, an offline phone app, live arrival times, live per-bus load.
- OpenTripPlanner.
- Estimating app share route by route from shared stretches, and GPS dwell-time evidence.
- A rider-experienced bunching factor, and full Hindi stop search.

**Anti-goals (failure even if it works)**
- Showing a level for a stretch we have no evidence for, or showing "no data" as comfortable.
- Tuning the scale factor, capacity or thresholds until a check passes.
- Raw scores or percentages shown to commuters, or wording that reads as a promise (railway-style "confirmed").
- Any number in the docs, UI or video that the pipeline did not produce, or any old-method term left in judge-facing files.
- Ticket-level or vehicle-level data in git or in published outputs.
- A broken demo at submission.

## 3. Facts and constraints

**Tickets** (`data/raw/October-Delhi.csv`, 1–31 Oct 2026)
- 2,559,899 tickets; 2,753,606 passengers; 2,259 route strings; 6,810 vehicles.
- ONDC app/QR tickets only, so women's free rides, passes and cash tickets are absent:
  - fares are 90% of standard slabs
  - only 8 tickets are zero-fare
  - `ticket_type_id` is always 1
- About 2.2% of published ridership. App use differs by operator: DTC routes carry 78% of app passengers but 61–63% of published riders.
- `vehicle_number` is `NULL` on 48.5% of rows. Both channels are bought on board and behave as one population. Never use the NULL share to scale bus counts.
- `is_ac` describes the bus. `created_at` is time-zone aware: pin `Asia/Kolkata`.
- Known holes and events:
  - 2 Oct (holiday, −56%) and 20 Oct (Dussehra, −48%)
  - 6 Oct 09:15–11:00 (281 tickets vs about 18.6k on 7–8 Oct)
  - 17 Oct 11:45 – 19 Oct 10:00 (NULL channel at 21–26% of normal)
  - 29 Oct evening (Karva Chauth)
  - Navratri 11–19 Oct
  - late-October weekends 10–20% higher (pre-Diwali)
- Week-to-week, weekday route-direction × hour totals correlate at r = 0.96. Sparse cells: about 55% of Saturday and 80% of Sunday rider-stretches have under 10 tickets at stretch × 30 min.
- **One citywide scale factor is impossible.** With one factor (about 43), 47.5% of stretch-hours with 150+ tickets exceed crush load. App use is uneven by route as well as operator. Found independently by three reviewers.
- **Real run times can be measured from tickets.** Two tickets bought on the same bus show how long it took to travel between their boarding stops. Over 238k such pairs, the real-to-scheduled ratio for DTC is about 0.73 at 06 h, 0.95 at 08 h, 1.15 at 12 h, 1.43 at 18 h and 0.81 at 22 h; cluster routes are similar.

**GTFS** (`data/raw/gtfs/delhi_buses_static_gtfs_v1/`, v32)
- 2,574 routes (DTC 1,814; cluster 760), 80,357 trips, one service id every day. Feed dates are meaningless.
- **Scheduled times are a template:** every stop-to-stop time equals straight-line distance at 18 km/h (verified on 200k segments). No route segment's time varies across trips or hours (0 of 80,859). So the schedule's times carry no time-of-day signal.
- `direction_id` is empty. Directions appear as UP/DOWN with optional digits, (+)/(−) or PLUS/MINUS on rings, and A-B/B-A pairs.
- `fare_stage` is a sparse boundary flag; `stop_dist` is empty.

**Published ridership** (Economic Survey of Delhi 2025-26, via news reports)
- DTC 25.6 lakh/day and cluster 15.3 lakh/day in FY2024-25. DTC was 24.3 lakh/day in FY2025-26.
- These include all riders. Sources and years go in `config.py`.

**GPS** (`delhi-dtc-bus-gtfs-rt-2026-10.7z`)
- 16.1 GB, downloading to `data/raw/gps/` (10.9 GB at 23:42 on 17 Nov, resuming after drops). A 7z lists its files at the end, so nothing is usable until it completes.
- 31 daily SQLite files with one table `vehicle_feed`, DTC buses only. `vehicle_id` uses the same format as ticket `vehicle_number`.

**Environment and team**
- The venv is incomplete, old artifacts sit in `data/processed_/`, and `.gitignore` misses parquet, pkl, geojson and 7z.
- Two people plus an AI coding assistant writing most of the code. Python 3.12. macOS, 375 GB free.
- The repo is Ash's (ashhhcodes/delhi-crowd-planner). Work goes as frequent local commits on `phase1` under the user's identity, with no AI co-author line. It is pushed only when the user says, and merged later with a merge commit, not squash.

## 4. Approaches

1. **Tickets + schedule only.** Low risk. Weakness: buses that ran and run times are guesses.
2. **Same, plus a GPS reality check (chosen by the team).** Hard cut-off at the end of 20 Nov. v2 makes the GPS optional on the critical path: run times now come from ticket pairs for every route, and GPS becomes the DTC cross-check and the source of "trips that ran".
3. Dropped:
   - OpenTripPlanner: days of setup on the part that is not judged.
   - Relative-only levels: the brief asks for seats / standing / crowded.

## 5. Design

### 5.1 Pipeline shape (my call)

- One command, `python -m src.pipeline.run`, with `--until <stage>` and a `--sample` mode (a few routes) for fast iteration.
- All assumptions live in `src/pipeline/config.py` with source or "assumption".
- Outputs go to `data/processed/` with a `manifest.json` (input checksums, row counts, package versions, code version).
- A render step fills the numbers in the technical note, README and proposal from `validation_report.json` and `manifest.json`. A test fails on unfilled placeholders.
- Modules: `clean`, `resolve`, `network`, `gps` (reads the committed aggregate; raw processing behind `--gps-raw`), `loads`, `validate`, `render`, `run`. The builder may rename them. The old sprint scripts are replaced; git history keeps them.

### 5.2 Cleaning

- Pin `Asia/Kolkata` everywhere.
- A calendar file lists holidays, festivals, data holes and the outage window. Exclusions apply in **on-board time**, because a gap in purchases empties on-board windows for up to an hour after it. Excluded: 2 and 20 Oct, 6 Oct 09:15–11:00, 17 Oct 11:45 – 19 Oct 10:00, and 29 Oct after 19:00.
- Two day types: **weekday** and **weekend** (Saturday and Sunday pooled; 7 clean days). The Saturday/Sunday split is kept in validation tables only.
- Denominators are clean-day counts per day type and window.
- `data_quality.md` records:
  - daily totals
  - exclusions
  - NULL share by day
  - AC and non-AC totals
  - terminal asymmetry
  - aliases, remaps, rejections
  - excluded services

### 5.3 Resolving tickets to GTFS

- Keep today's route-scoped fuzzy stop matching (93%).
- **Aliases:** only for ticket strings with no exact GTFS short name (1.8%, e.g. `ML96UP`, `567BSTLUP`, `522BDOWN2`, `BPEXPUP`). Match by normalising punctuation, leading zeros, PLUS/MINUS ↔ (+)/(−) and trailing digits, then require ≥ 80% ordered stop overlap in the same direction. Merge two GTFS route_ids only with ≥ 90% ordered stop match and the same termini. Never merge different termini or opposite directions. List every alias with its evidence.
- **Direction parser:** handles UP/DOWN with an optional trailing digit, (+)/PLUS clockwise, (−)/MINUS anticlockwise, and A-B ↔ B-A. Wrap-around only where the first stop is also the last. Fixture tests cover OMS, YMS and 522BDOWN2.
- **Direction remap per route:** where most tickets come out reversed, swap the mapping instead of dropping them.
- **Fare check (report-only):** fare per passenger = amount ÷ passengers ÷ 0.9, mapped to a slab via the AC or non-AC table. Flag tickets 2+ slabs off from the shape distance.
- **Service classes:** a table in `config.py`. School and DAF routes are excluded from planner and supply. DS, U-Special and office circulars run on weekdays only, tagged "office special".

### 5.4 Network

- Canonical stop sequence per route_id: the longest trip.
- **Clock.** GTFS template time × run-time factor, with run times attached to the to-stop (fixes the one-stop shift). Factors come from same-bus ticket pairs that move forward and are at least 10 scheduled minutes apart:
  - per operator × hour
  - per route group × hour where there are 30 or more pairs
  - GPS cross-checks DTC routes

  The same clock is used for riders and for bus passing times.
- **Bus passing times:** scheduled buses passing each stop, on the corrected clock.
- **Service hours:** GTFS first and last bus, plus any hour with tickets on 3 or more clean days.
- **Places:**
  - stops sharing a name stem within about 400 m are grouped
  - a hand-made alias table for about 30 hubs (CP / Rajiv Chowk, ISBT Anand Vihar, Kashmere Gate, Sarai Kale Khan, AIIMS, ITO, Nehru Place, Dhaula Kuan…) in English and Hinglish forms
- **Shapes:** a road-following slice per segment, with its generator script, plus distances along the shape.

### 5.5 GPS layer (time-boxed, DTC only, off the critical path)

- **Checkpoint 19 Nov 12:00:** archive complete, `7z t` passed, solid-block layout checked (if solid, extract all sample days in one pass), one day extracted, and GPS route_id matches GTFS ≥ 90% (or a working trip map). Otherwise stop GPS work. Builder time before the checkpoint is capped at about 4 h; extraction runs as background scripts.
- **Scope:**
  1. **Trips that ran.**
     - A trip counts only if one vehicle passes at least 80% of the canonical stops in order.
     - ρ = observed ÷ (scheduled × coverage), and only where coverage is 0.8 or more. Coverage is the share of the route's ticket-linked registrations seen in the feed that day.
     - ρ is reported separately for the first, middle and last third of the route, to catch short-turns.
     - Elsewhere the source is tagged "schedule only".
  2. **Run-time cross-check** between geofences at the first and last stops. Depot pings and stationary spells over 5 minutes at terminals are dropped.
- **Output:** a small checksummed `gps_route_hour` aggregate, committed so the one command runs without the 16 GB archive.
- **Hard cut-off end of 20 Nov.** If out, the model uses ρ = 1 and ticket run times, and the note says so.

### 5.6 Crowding model

For route r, stretch k (stop k to k+1), day type d, window w:

1. **Riders on each stretch at on-board time.**
   - Each ticket is placed on stretch k at purchase time + corrected run time from its boarding stop.
   - Purchase time is a good proxy for boarding in both channels (reviewer-checked). The GPS purchase-position check is a Phase 2 item.
   - Every stretch exists for every window, with explicit zeros.
2. **Alighting correction.**
   - App tickets end at route terminals about twice as often as they start there.
   - Terminal alightings are capped at the reverse route's terminal boardings × the route's intermediate-stop ratio.
   - The excess is spread over the stops in the same fare slab before the terminal, in proportion to the reverse direction's boardings (the symmetry method).
   - Published with and without the correction. Last stretches whose level depends on it are shown as Rough guess at best.
3. **Load base.**
   - Riders y and buses S are counted in a centred 90-minute window, reported every 30 minutes on weekdays.
   - Weekends use 60-minute steps on a 120-minute base.
   - This removes the swings when S jumps between 0, 1 and 2.
4. **Supply** S = scheduled passing buses in the same window × ρ.
   - If S = 0 while y > 0: widen to ±30 min, then to the route-hour.
   - If still 0: "no bus scheduled". Commuters see No data; operators see "schedule mismatch".
   - Never divide by a floor value.
5. **App riders per bus** ℓ = y ÷ S (per clean day).
6. **Scale to people on board.**
   - E_op = published operator ridership ÷ resolved app passengers per clean day for that operator: about 35–37 for DTC, about 79 for cluster.
   - **Capacity bound per route:** B_r = crush capacity ÷ the 95th percentile of the route's weekday peak ℓ over cells with ≥ 30 tickets.
   - **Route scale** E_r = min(E*_op, B_r). E*_op is solved by bisection so that each operator's total still matches published ridership (water-filling).
   - Routes where the bound binds are flagged "scaled to bus capacity (high app use)" and counted in the report.
   - People on board L = E_r × ℓ, shown with a range combining:
     - **sampling:** the standard error from day-to-day variation (SD of the cell's daily values over clean days, zero days included, ÷ √days)
     - **scale:** 0.7–1.3 × E_r (upper end capped at B_r), checked against the field count
   - Displayed people on board are capped at crush capacity. Capped cells are flagged "full: real demand is likely higher".
7. **Levels by bus type.**
   - 12 m by default; 9 m for routes on a team-confirmed list.
   - Seats, capacity and crush are config values with sources (defaults to confirm: 12 m 37 / 70 / 100; 9 m 25 / 40 / 55).
   - Thresholds:
     - Usually seats: L < 0.7 × seats (reserved seats for women, seniors and others are rarely free).
     - Usually standing: L < seats + 0.5 × (capacity − seats).
     - Usually crowded: above that.
8. **Evidence state per cell** (replaces "confidence"):
   - **Based on many tickets:** the level is the same across the whole range.
   - **Rough guess:** the range spans two levels, or the route is flagged "low app use".
     - Low app use means app riders per scheduled trip on a shared stretch below one third of that stretch's median across routes.
     - If the upper end is below the Seats threshold, show "Usually seats" as a rough guess, because a quiet count on a route that does sell app tickets is evidence of a quiet bus.
   - **No data:** the route's app riders per scheduled trip are below the network 25th percentile, or no bus is scheduled.
9. **No shrinkage.** Sparse cells are handled by the wider load base and the rules above.
10. **No bunching factor in commuter levels.** If GPS is in, headway spread is an operator-view diagnostic only.
11. **Per-trip running counts are not used.** There is about one app ticket per scheduled trip; the note explains this.

### 5.7 Outputs

- `stretch_crowding.parquet`. Columns:
  - identity: route_id, short name, operator, direction, stretch (stop ids and names), day type, window
  - counts: app riders, tickets n, buses S with source (GPS / schedule / widened)
  - estimates: E_r, people on board (central, low, high), seats, capacity, level
  - state: evidence state, flags (scaled to capacity, low app use, full, schedule mismatch, alighting-sensitive, office special)
- **Corridor layer**, per stop pair × window, combined across routes: people on board ÷ total capacity, share of buses Usually crowded, crowded rider-minutes. Shipped as one simplified geometry file keyed by stop-pair id plus a compact values file per day type, joined in the browser.
- Other files:
  - `route_hour_summary.csv`
  - `validation_report.json` and `.md`
  - `data_quality.md`
  - `coverage.csv` (share of bus-km per level and evidence state by hour, day type and operator)
  - `manifest.json`
- Only small reports and the GPS aggregate are committed. Large outputs are regenerated by the one command.

### 5.8 Validation

**A. Invariants that stop the run**
- Ticket conservation per route: raw = resolved + rejected, by reason.
- Output rider-minutes equal resolved-ticket rider-minutes within ±0.5%.
- Rider volume with no bus after the fallback stays under 1%.
- Modelled hourly run times are within ±15% of ticket-pair run times.
- Time-zone invariance (a fixture test).
- Schema; no NaN or inf.

**B. Patterns written down before the first full run**
- `validation/expectations.yaml` is committed on 18 Nov, each item with a source:
  - AM peak 08–10 and PM peak 17–20 in crowded rider-minutes from the model output
  - weekends lower, with a flatter and later peak
  - radial routes busier inbound in the AM and outbound in the PM (inbound = towards the terminal nearer CP/ITO, by geometry)
  - a top-10 list of known busy corridors from the team and published sources
- Each gets a hit or miss in the report.
- The old hub check is dropped; it was circular.

**C. Week-to-week repeatability (the brief's stability check)**
- Leave one weekday block out in turn (5–9, 12–16, 21–23, 26–30 Oct).
- Report, by week pair and ticket band, rider-weighted:
  - the share of commuter-facing cells whose level is unchanged
  - the correlation of route-direction-hour loads
  - coverage of the sampling ranges
- The word "accuracy" is not used for this.

**D. Field count (ground truth, team)**
- 19–20 Nov (and 23 Nov morning if needed), at 2–3 busy stops on well-covered corridors, during peak and off-peak. The team logs route, time, direction, bus size and a three-level visual load for every passing bus, aiming for 150–250 buses.
- The report shows a confusion matrix against the model and checks the scale by operator, with the November-vs-October caveat stated.

**E. Sensitivity**
- Share of cells changing level when:
  - E moves ±30%
  - capacity moves ±10%
  - the alighting correction or the capacity bound is switched off

**F. Diagnostics (reported, not gates)**
- over-capacity share by operator and hour, with top routes and suspected cause
- level shares by hour band
- routes with resolution under 80%
- coverage table
- terminal asymmetry
- NULL-vs-linked split-half agreement
- GPS ρ distribution and run-time cross-check
- choice stability for alternatives with the same origin, destination and hour

### 5.9 Planner

- Keep the frequency-based round search, which suits buses that ignore timetables. Stop calling it McRAPTOR.
- Run times come from the corrected clock and service hours are enforced. Waits are half the headway, from scheduled buses × ρ.
- Origins and destinations are places (5.4) or stops.
- Crowding comes from the stretch table. Missing means unknown, never a number.
- **Option roles:**
  - **Fastest.**
  - **Less crowded:**
    - within max(15 min, 30%) of the fastest
    - fewest minutes Usually crowded, then Usually standing, using the upper end of the range
    - not eligible if over half the ride is No data, or if its advantage rests on legs flagged "low app use"
  - **Leave later** (+10 / +20 min; +30 / +40 if time allows):
    - offered only if the later trip's whole range is in a better level and the route still runs
    - values are interpolated between window centres
    - labelled with times, e.g. "Leave 18:20 · usually seats · arrive 19:15"
- Roles that give the same trip are returned once with both roles. Labels are computed from the returned options.
- **Headline level** = the worst level the rider spends at least 5 minutes in, plus the crowded stretch by name and minutes.
- Before 05:00 and after 23:00, options are marked "timetable uncertain".

### 5.10 API (v1)

- `GET /v1/plan?from=<place|stop>&to=<place|stop>&depart=HH:MM&day=weekday|weekend`
- `GET /v1/places/search?q=` (fuzzy match plus hub aliases; shows bus numbers and "towards X")
- `GET /v1/crowding?route_id=&day=&window=` and `GET /v1/crowding/stretch?from=&to=&day=` (all routes × all windows)
- `GET /v1/corridors?day=&window=` (corridor values for the map)
- `GET /v1/operator/trips?day=&operator=` and `.csv`
- `GET /v1/health` (data version, data dates, computed counts)

A frozen `/v1/plan` example JSON is committed on 19 Nov so the screens can be built in parallel. Bad input gets a clear 4xx, never a 500. The data version is in every response. No hard-coded KPIs.

### 5.11 Commuter screen

- Phone first, list first, map on request.
- The brief's example is a one-tap preset, going place to place: ISBT Anand Vihar → Connaught Place, weekday 18:00.
- **Three cards**, each showing:
  - role, duration, leave → arrive times
  - level chip
  - one trade-off line against the fastest
  - buses, changes and fare
  - a time bar shaded by level
  - the crowded stretch in one sentence
- **Levels** always pair a word with dots and colour, never colour alone:
  - Usually seats / आमतौर पर सीट मिल जाती है ●○○ teal
  - Usually standing / आमतौर पर खड़े होकर जाना पड़ता है ●●○ amber
  - Usually crowded / आमतौर पर भारी भीड़ ●●● dark red
  - No data / जानकारी नहीं grey dashed
- **Evidence** in plain words, not a railway-status metaphor (riders read solid chips as a confirmed booking):
  - Based on many tickets / कई टिकटों पर आधारित
  - Rough guess / अंदाज़ा (कम टिकट)
  - Capped cells add "Full buses may not stop / भरी बस शायद न रुके".
- **"Why?"** shows: "Based on app tickets (about 1 in 40 riders), scaled up to all riders. Women riding free and pass holders are not in this data, so buses can be fuller than shown." It also gives the people-on-board range against the bus's seats, the period ("October 2026 weekdays, festival season"), and the route flags.
- The rough-guess card is designed as the common case.
- Hindi covers level chips, roles, buttons and the headline sentence; more if time allows. Stop names stay as in GTFS.
- Light page:
  - compiled CSS
  - pinned libraries
  - system font + Noto Sans Devanagari
  - 16 px text, 48 px tap targets

### 5.12 Operator view

- **Ranked extra trips.**
  - For each route-direction and departure window, walk the trip's stretches at the windows it reaches them, with S + 1.
  - Sum the crowded rider-minutes removed and the riders moved down a level; rank per operator.
  - Use standard terms: maximum load section, load factor.
- **Corridor map with a time slider** (from the corridor layer).
- **Route heat strip:** stretches × windows, as the drill-down.
- **Heatmap** of the top 50 route-directions, with operator and corridor filters.
- **Flags:** scaled to capacity, low app use, full (censored), schedule mismatch. For cluster routes, "buses that ran" = app-linked vehicles seen (a lower bound).
- **Export:** CSV.

### 5.13 Engineering

- **Before any feature work:**
  - install the missing packages, write a lock file with exact versions, and test from it
  - fix `.gitignore`: ignore `data/processed_/`, `*.parquet`, `*.pkl`, `*.geojson`, `*.7z`, and everything in `data/processed/` except reports; un-ignore `tests/fixtures/**`
  - commit by explicit paths, never `git add -A`
  - a pre-commit check rejects files over 5 MB and data paths other than reports
  - tag a working `baseline` of the old app pointed at `data/processed_/`, as a fallback demo
- **Tests:**
  - toy GTFS feed and ticket fixtures in `tests/fixtures/`
  - unit tests: to-stop run times, hourly factors, S = 0 rule, direction parser, time zone
  - golden tests for 3–5 demo journeys
- **CI:** local `pytest` until the user approves a push; GitHub Actions after that.
- **Before submission:** a clean-clone test of the README quick start.
- **Backups and freezes:** a nightly `git bundle` to a folder outside the repo, and `rc-<date>` tags at each evening check.

### 5.14 Docs and submission

- **18 Nov:**
  - move `PROGRESS_REPORT.md`, the old proposal and the old demo script to `docs/archive/` with a "superseded" banner
  - remove hard-coded KPIs from the API and UI
  - grep judge-facing files for κ, kappa, McRAPTOR, Pareto, sigmoid, "score"
- **Technical note** (about 4 pages plus an appendix):
  - method, plus an assumptions table linked to `config.py`
  - a **brief checklist table**: running count per trip, pass and free riders, planned vs actual alighting, bus size, thin routes and hours, simple display; for each, what was done, the evidence, and the remaining risk
  - least-reliable areas, quantified with the coverage table
  - validation and field-count results
  - Phase 2 plan
  - no latency section
- **Proposal:** draft v1 on 20 Nov with placeholders; numbers rendered on 23 Nov.
- **Demo:**
  - storyboard on 18 Nov:
    - 30 s: problem and data, stated honestly
    - 90 s: the preset (three cards, "Why?", leave later)
    - 60 s: operator corridor map and top extra trips
    - 60 s: evidence (peaks, weekday/weekend, repeatability, field count, coverage)
    - 30 s: limits and Phase 2
  - script v2 on 22 Nov
  - video recorded on 23 Nov on the frozen tag
- **Submission:**
  - the submission form's rules are read and copied into the plan by 18 Nov
  - if a live link is required, rehearse the deploy by 22 Nov; otherwise a phone hotspot covers the phone test, plus an optional static page of precomputed demo plans if the data terms allow
  - submit by 18:00 IST on 24 Nov

## 6. Schedule (thin version end to end first; each evening's check must be visibly true)

| Day | Build (assistant) | Team (Aniket, Ash) | Evening check |
|---|---|---|---|
| 17 Nov | After approval: environment, lock, `.gitignore`, baseline tag | Approve design v2; answer section 10 | `pytest` collects; old app serves from baseline |
| 18 Nov | `run --until network`: cleaning, calendar, resolving, clock factors, places; S = 0 rule; `expectations.yaml`; evidence table + demo-journey shortlist; archive old docs; storyboard | Submission rules; busy-corridor list; bus seats and 9 m routes; pick field-count stops | Match ≥ 93% with counts; toy tests pass; run-time gate passes |
| 19 Nov | GPS go/no-go 12:00; model v0 (riders, supply, scale, levels, evidence); `/v1/plan` v0 for the preset; frozen JSON | Field count 1 (evening peak) | The preset returns three options from the new model |
| 20 Nov | Validation suite; alighting correction; weekend; GPS in or out (cut-off); proposal draft v1 | Field count 2 (morning peak + off-peak); enter counts | Report renders; all invariants pass; GPS decision recorded |
| 21 Nov | Planner (places, roles, leave later, night flags); API v1 incl. corridors; commuter screen v1 | Review the cards | Three cards for 5 demo journeys at phone width |
| 22 Nov | Operator view (extra trips, corridor map, heat strip, CSV); Hindi; field-count comparison; demo script v2 | Phone test with 5 commuters (evening) | Operator page answers "where does one extra trip help most"; confusion matrix in report |
| 23 Nov | Fixes from the phone test; clean-clone rebuild; tests; note, README and proposal rendered; freeze tag | Record video | Clean clone reproduces the report; no placeholders; no old terms |
| 24 Nov | Buffer only | Re-record or upload; submit by 18:00 IST | Submitted |

**Cut list (cut first to last):**
1. Heatmap of the top 50 route-directions
2. Service-class tagging (keep the school/DAF exclusion)
3. Fare check and ring wrap (report counts; exclude Mudrika routes and say so)
4. Leave later beyond +20 min
5. Hindi beyond chips, roles, buttons and headline
6. Route heat strip drill-down
7. GPS layer (ticket clock and ρ = 1 remain)
8. GitHub Actions

**Never cut:**
- IST pin and exclusions
- the ticket clock
- S = 0 rule
- operator scale with capacity bound
- evidence states and No data
- invariants
- written expectations
- repeatability
- field count
- the brief's preset
- three roles
- corridor map
- extra-trip ranking
- technical note, proposal and video
- clean-clone README

## 7. Risks and fallbacks

- **Scale still off for some routes:** the field count measures it. Ranges and evidence states carry it to users, and the note stresses that comparisons are firmer than absolute counts.
- **GPS late or ids unmatched:** 19 Nov checkpoint and 20 Nov cut-off. The ticket clock already covers every route.
- **Field count not possible:** report repeatability only and say so.
- **Thin data on demo journeys:** demo journeys are chosen on 18 Nov from the evidence table. The preset is kept even if it shows no trade-off.
- **Overrun:** the thin version must be running on 19 Nov; then the cut list.
- **Parallel edits with Ash:** Ash edits only new files (e.g. `docs/proposal/`) until the branch is pushed.
- **One laptop holds unpushed work:** nightly bundle; daily push of `phase1` if the user agrees.
- **Judges re-run elsewhere:** time zone pinned and tested, lock file, committed GPS aggregate, clean-clone README.

## 8. Decisions

**Made by the team:**
- judges first this week
- GPS check with a 20 Nov cut-off
- city-scale pieces designed now, built in Phase 2
- the assistant writes code while the team tests, counts buses, confirms bus data and records the demo
- frequent local commits under the user's name, pushed only when the user says

**My calls (open to change):**
- the ticket-pair clock, with GPS as a cross-check
- operator scale with a capacity bound and water-filling, plus ranges combining sampling and scale
- plain-word evidence states instead of railway-style chips
- Usually-seats at 0.7 × seats
- no shrinkage and no bunching factor in Phase 1
- weekends pooled
- a 90-minute centred load base
- the alighting correction, with sensitivity
- the S = 0 rule
- invariants, plus expectations written before results
- the corridor layer
- extra-trip ranking
- places and hub aliases
- old docs archived
- docs rendered from pipeline output
- submit by 18:00

## 9. Left to the builder

- water-filling and percentile details
- place grouping thresholds
- GPS cleaning details
- corridor geometry simplification
- visual details within 5.11–5.12
- file and function names
- caching

## 10. Questions for the team (answers go here before approval)

1. Can you two do the field count (section 5.8 D) on 19–20 Nov?
2. What does the submission form require (proposal format, video length, live link, repo link)?
3. Can you confirm seats and capacity for 12 m and 9 m buses, and which routes use 9 m buses?
4. Is Ash changing code this week, and may `phase1` be pushed each evening as a backup?
5. Which ten corridors do you know to be the busiest?
