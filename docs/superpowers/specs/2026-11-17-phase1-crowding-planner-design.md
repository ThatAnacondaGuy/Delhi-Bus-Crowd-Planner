# Phase 1 design: crowding model and journey planner (v3)

Transport Stack Hackathon 2026, Problem 2 (crowdedness-aware journey planner, Delhi buses).

- **v1** (17 Nov 2026): first design.
- **v2** (17 Nov): revised after five independent reviews: a builder check, a statistician, a hackathon judge, a delivery lead and a Delhi bus-operations expert.
- **v3** (18 Nov): adds the team's answers and verified research on bus capacities, busy corridors, submission rules and a GPS stop-time test. Every number below was either checked against the data or verified against its source by a second researcher.

Phase 1 submission closes **24 Nov 2026, 23:59 IST**; we submit by **18:00 IST**.

## 1. Intent

Delhi bus riders choose trips by time alone because no planner knows how full buses are. We are building:
- a pipeline that turns one month of ticket data into honest crowding estimates by route, direction, stretch between stops and time of day
- a planner that shows those estimates next to each trip option, so a commuter can trade a faster trip for a more comfortable one
- a second view that shows bus operators and planners where buses are overloaded and where one extra trip helps most

The judges score two things: how well the crowding estimate is grounded in the data, and how clearly it is shown. The brief says a simple planner with a sound crowding model beats a polished planner with a weak one. So the model and its evidence come first, then a clear screen.

The design is honest by default:
- **No invented values.**
- **Every estimate carries an evidence state.**
- **What we can and cannot measure is published:**
  - week-to-week repeatability from the tickets
  - independent checks against published operating figures, outside evidence of busy corridors, and GPS stop times
  - a plain statement that no field count was possible, because the team is based in Pune

## 2. Goals, non-goals, anti-goals

**Goals (Phase 1, by 24 Nov)**
1. A re-runnable pipeline: raw tickets + GTFS (+ a small committed GPS aggregate) to crowding tables with one command.
2. Crowding per route, direction, stretch and time window for weekdays and weekends: people on board as a range, a commuter level, and an evidence state.
3. A corridor view: the same estimates combined across all routes for each road stretch, so maps show "how crowded is this road at 6 pm".
4. Validation:
   - invariant checks that stop the run
   - pattern checks written down before the first run, including ten researched busy corridors
   - week-to-week repeatability
   - independent checks against published bus-km and load factors, plus GPS stop times
5. A planner with three option roles (Fastest, Less crowded, Leave later), each showing times, level, crowded stretch and the trade-off.
6. An operator view ranking the extra trips that would remove the most crowded rider-minutes, with CSV export.
7. All four submission items, with every number coming from the pipeline's own output: proposal PDF, video, live link, and GitHub repo with README and technical note.

**Non-goals (designed now, built in Phase 2 or later)**
- Hosting for lakhs of users, an offline phone app, live arrival times, live per-bus load.
- OpenTripPlanner.
- Estimating app share route by route from shared stretches.
- A rider-experienced bunching factor.
- Linking tickets to their exact GPS trip.
- Full Hindi stop search.

**Anti-goals (failure even if it works)**
- Showing a level for a stretch we have no evidence for, or showing "no data" as comfortable.
- Tuning the scale factor, capacity or thresholds until a check passes.
- Raw scores or percentages shown to commuters, or wording that reads as a promise (railway-style "confirmed").
- Any number in the docs, UI or video that the pipeline did not produce, or any old-method term left in judge-facing files.
- Ticket-level or vehicle-level data in git, on the live link or in published outputs.
- A broken demo or a dead live link at submission.

## 3. Facts and constraints

**Tickets** (`data/raw/October-Delhi.csv`, 1–31 Oct 2026)
- 2,559,899 tickets; 2,753,606 passengers; 2,259 route strings; 6,810 vehicles.
- ONDC app/QR tickets only, so women's free rides, passes and cash tickets are absent:
  - fares are 90% of standard slabs
  - only 8 tickets are zero-fare
  - `ticket_type_id` is always 1
- About 2.2% of published riders.
  - The hackathon pages put app tickets at 3–4% of bus tickets. The two agree once free rides (about 30% of boardings) and passes are taken out of the ticket base: 2.2% ÷ 0.7 ≈ 3.1%. The note explains this.
  - App use differs by operator: DTC routes carry 78% of app passengers but about 62% of published riders.
- `vehicle_number` is `NULL` on 48.5% of rows. Both channels are bought on board and behave as one population. Never use the NULL share to scale bus counts.
- `is_ac` describes the bus. `created_at` is time-zone aware: pin `Asia/Kolkata`.
- Known holes and events:
  - 2 Oct (holiday, −56%) and 20 Oct (Dussehra, −48%)
  - 6 Oct 09:15–11:00 (281 tickets vs about 18.6k on 7–8 Oct)
  - 17 Oct 11:45 – 19 Oct 10:00 (NULL channel at 21–26% of normal)
  - 29 Oct evening (Karva Chauth)
  - Navratri 11–19 Oct
  - late-October weekends 10–20% higher (pre-Diwali)
- Weekday route-direction × hour totals correlate at r = 0.96 between weeks. Weekends are sparse: about 55% of Saturday and 80% of Sunday rider-stretches have under 10 tickets at stretch × 30 min.
- **One citywide scale factor is impossible.** With one factor (about 43), 47.5% of stretch-hours with 150+ tickets exceed crush load, because app use is uneven by route and by operator. Three reviewers found this independently.
- **Real run times come from tickets.** Two tickets bought on the same bus show the real travel time between their boarding stops. Over 238k such pairs, the real-to-scheduled ratio for DTC is about 0.73 at 06 h, 0.95 at 08 h, 1.15 at 12 h, 1.43 at 18 h and 0.81 at 22 h; cluster routes are similar.

**GTFS** (`data/raw/gtfs/delhi_buses_static_gtfs_v1/`, v32)
- 2,574 routes (DTC 1,814; cluster 760), 80,357 trips, one service id every day. Feed dates are meaningless.
- **Scheduled times are a template:** every stop-to-stop time equals straight-line distance at 18 km/h (verified on 200k segments), and no route segment's time varies across trips or hours (0 of 80,859).
- `direction_id` is empty. Directions are UP/DOWN with optional digits, (+)/(−) or PLUS/MINUS on rings, and A-B/B-A pairs.
- `fare_stage` is a sparse boundary flag; `stop_dist` is empty.

**Fleet and bus sizes** (verified against sources by a second researcher)
- **March 2026 fleet** (Economic Survey of Delhi 2025-26, ch. 12): 6,100 buses.
  - 2,750 AC electric 12 m
  - 1,588 AC electric 9 m
  - 760 AC CNG 12 m
  - 1,002 non-AC CNG 12 m
  - About 500 more electric buses arrived by Aug 2026.
- **Seats** (sourced: DTC e-bus tender cl. 28.2, CESL tender, JBM release, PTI): 12 m AC electric and CNG 35; 9 m (DEVI) 23; non-AC CNG 37 (weak source).
- **Rated totals:**
  - 12 m: about 60–63 (Tata 60; Switch EiV12 39 + 24 = 63)
  - 9 m DEVI: 36 (23 seated + 13 standing; one report says 17 standing)
- **Crush loads:**
  - 12 m: 100, from DTC tenders that design for "peak loading of over 100 passengers". The tender's extra 20% is a power margin, not passengers.
  - 9 m: 42, the highest stated 9 m capacity (JBM Ecolife e9).
- **9 m routes:**
  - Routes numbered `D-…` are DEVI routes: 302 GTFS route rows, 142 numbers, 15.7% of scheduled trips, 6.3% of app tickets. High confidence.
  - Other routes are run mostly by 9 m buses when at least 50% of their vehicle-linked tickets come from vehicles that sell 5 or more tickets on D- routes. This is an inference: 170 GTFS rows at 50%, 86 at 90%.

**Published operating figures** (Economic Survey 2025-26, CAG Report 4 of 2024)
- **Ridership:** DTC 25.6 lakh/day in 2024-25 and 24.29 lakh/day in 2025-26; cluster 15.3 lakh/day in 2024-25.
- **Bus-km:** DTC 5.01 lakh/day in 2025-26.
- **Passengers per bus per day:** DTC 731 (2024-25); cluster 511 (2024-25).
- **Load factor:** DTC 88.77% (2024-25) and 88.33% (2025-26 to 20 Mar); cluster 78% (2024-25).
  - DTC computes its load factor from revenue against seating capacity, and the cluster figure uses the CIRT formula, so these are rough checks only.

**Busy corridors from outside evidence** (researched without looking at our data; to be pre-registered)
- **Strong:**
  1. Ambedkar Nagar / Khanpur – Chirag Delhi – Moolchand – Mathura Road – ITO – Delhi Gate – Old Delhi (former BRT corridor; routes 423, 419, 534; morning peak 8–10, both directions busy in counts).
  2. ITO / Mandi House – Vikas Marg – Laxmi Nagar – Preet Vihar – Karkardooma – Anand Vihar ISBT (routes 611, 740, 85, 73; evening peak, eastbound).
- **Moderate:**
  3. Ring Road (Mudrika / Teevra Mudrika).
  4. Mehrauli–Badarpur Road (morning).
  5. Outer Ring Road (Bahri Mudrika, 764; evening outbound from Nehru Place).
  6. Mathura Road, Ashram – Badarpur Border (405).
- **Weak:**
  7. Wazirabad / Pusta Road and GT Road Shahdara.
  8. GT Karnal Road north.
  9. Najafgarh Road.
  10. Rohtak Road.

Each corridor's sources and GTFS stop names are in the research notes; they move into `validation/expectations.yaml`.

**GPS** (`delhi-dtc-bus-gtfs-rt-2026-10.7z`, in `data/raw/gps/`)
- Downloaded on 17 Nov; the SHA-256 matches the published checksum.
- The archive is not solid: the 31 daily SQLite files (3.4–4.8 GB each, 124 GB unpacked) extract one at a time. One table, `vehicle_feed`, in WAL mode with indexes on vehicle_id and timestamp. Open it read-only with `mode=ro&immutable=1`.
- **Checked on 15 Oct:**
  - 29.3M pings, about 11–12 s apart for most buses (56 of 717 sampled buses report every 60 s)
  - 6,093 buses
  - 99.9% of pings carry a GTFS route_id; 2,113 of 2,574 routes appear; a quarter of pings are on cluster-labelled routes
  - 97.8% of the buses on that day's linked tickets appear in the feed, carrying 99% of linked passengers on both DTC and cluster routes

  So despite the README's "DTC buses only", the feed covers practically the whole fleet.
- **Pitfalls:**
  - about 38% of rows are duplicate polls
  - the speed field is unreliable (lagged or inverted)
  - stops shorter than a ping interval are missed by "stationary spell" methods, so use interpolated time inside a zone around each stop
- **Stop times as a check** (tested on 24 route-directions): time spent at stops rises with app boardings + alightings.
  - Spearman 0.44 across stops, positive on all 24 route-directions, and it survives a mid-block null test and congestion controls.
  - But it is weak, it cannot place time-of-day peaks at a single stop, and it gives no absolute scale.
  - So it is corroboration of relative activity only, never ground truth.

**Submission rules** (public pages: Where U Elevate, the hackathon site, the Problem 2 brief)
- **Required:** a proposal, a working prototype and a code repository with a README; also a short technical note and a short demo video. The logged-in form also asks for a live link. "Mock-only or slide-only submissions will not qualify."
- **Not published:** page limits, video length, or a licence.
- **Judging (indicative):** problem relevance; technical depth and correct use of the data; feasibility; innovation; usability and impact. For Problem 2: how well the estimate rests on the data, and how clearly it is shown.
- **Competition:** about 10–12 teams go to Phase 2 (129 teams were registered on 18 Nov).
- **Phase 1 window:** closes 23:59 IST on 24 Nov. One part of the site shows 6:29 pm, a UTC label error.
- **Finale:** 11 Dec at IIIT Delhi; whether teams can present remotely is unclear.
- **Data terms:** Transport Stack's terms allow reuse with clear credit; per-dataset licences were not readable. We publish aggregates only and credit Transport Stack / IIIT Delhi and ONDC e-ticketing.

**Environment and team**
- The venv is incomplete, old artifacts sit in `data/processed_/`, and `.gitignore` misses parquet, pkl, geojson and 7z.
- This Mac's internet has dropped several times. Long jobs must be resumable, and the app keeps the Mac awake while they run.
- Team: two people in Pune, so no field visits. An AI coding assistant writes most of the code. Ash has finished his part and will not push.
- Python 3.12. macOS, 375 GB free.
- Work goes as frequent commits on `phase1` under the user's identity with no AI co-author line, pushed to GitHub at each evening check. It is merged to `main` later with a merge commit, not squash.

## 4. Approaches

1. **Tickets + schedule only.** Low risk. Weakness: buses that ran and run times are guesses.
2. **Same, plus a GPS reality check (chosen by the team).**
   - Hard cut-off at the end of 20 Nov.
   - Run times come from ticket pairs for every route, so GPS is off the critical path.
   - GPS supplies "trips that ran" and cross-checks run times for every route it covers (practically all), plus the stop-time corroboration.
3. **Dropped:**
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
- A calendar file lists holidays, festivals, data holes and the outage window. Exclusions apply in **on-board time**: 2 and 20 Oct, 6 Oct 09:15–11:00, 17 Oct 11:45 – 19 Oct 10:00, and 29 Oct after 19:00.
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
  - 9 m route assignments

### 5.3 Resolving tickets to GTFS

- Keep today's route-scoped fuzzy stop matching (93%).
- **Aliases:** only for ticket strings with no exact GTFS short name (1.8%, e.g. `ML96UP`, `567BSTLUP`, `522BDOWN2`, `BPEXPUP`).
  - Normalise punctuation, leading zeros, PLUS/MINUS ↔ (+)/(−) and trailing digits, then require ≥ 80% ordered stop overlap in the same direction.
  - Merge two GTFS route_ids only with ≥ 90% ordered stop match and the same termini. Never merge different termini or opposite directions.
  - List every alias with its evidence.
- **Direction parser:** handles UP/DOWN with an optional trailing digit, (+)/PLUS clockwise, (−)/MINUS anticlockwise, and A-B ↔ B-A. Wrap-around only where the first stop is also the last. Fixture tests cover OMS, YMS, 522BDOWN2 and D-… names.
- **Direction remap per route:** where most tickets come out reversed, swap the mapping instead of dropping them.
- **Fare check (report-only):** fare per passenger = amount ÷ passengers ÷ 0.9, mapped to a slab via the AC or non-AC table. Flag tickets 2+ slabs off from the shape distance.
- **Service classes:** a table in `config.py`. School and DAF routes are excluded from planner and supply. DS, U-Special and office circulars run on weekdays only, tagged "office special".

### 5.4 Network

- Canonical stop sequence per route_id: the longest trip.
- **Clock.** GTFS template time × run-time factor, with run times attached to the to-stop (fixes the old one-stop shift).
  - Factors come from same-bus ticket pairs that move forward and are at least 10 scheduled minutes apart: per operator × hour, and per route group × hour where there are 30 or more pairs.
  - GPS cross-checks every route it covers.
  - The same clock is used for riders and for bus passing times.
- **Bus passing times:** scheduled buses passing each stop, on the corrected clock.
- **Service hours:** GTFS first and last bus, plus any hour with tickets on 3 or more clean days.
- **Bus type per route:**
  - `D-` routes → 9 m.
  - Other routes → 9 m share by the vehicle rule in section 3.
  - Non-AC buses → non-AC CNG 12 m.
  - Everything else → 12 m AC.
  - The per-window mix comes from vehicle-linked tickets where there are enough; otherwise the route's monthly mix is used.
- **Places:**
  - stops sharing a name stem within about 400 m are grouped
  - a hand-made alias table for about 30 hubs (CP / Rajiv Chowk, ISBT Anand Vihar, Kashmere Gate, Sarai Kale Khan, AIIMS, ITO, Mandi House, Nehru Place, Dhaula Kuan, Laxmi Nagar…) in English and Hinglish forms
- **Shapes:** a road-following slice per segment, with its generator script, plus distances along the shape.

### 5.5 GPS layer (time-boxed, off the critical path)

- **Checkpoint 19 Nov 12:00.**
  - Already passed on 17 Nov: archive verified, not solid, one day extracted, route ids match (99.9%).
  - Still due by the checkpoint: the trip definition below working on one day, and ρ for that day. Otherwise stop GPS work.
  - Builder time before the checkpoint is capped at about 4 h. Extraction runs as resumable background scripts, one day at a time, and each day is deleted after aggregation.
- **Cleaning:** drop duplicate polls; never use the speed field; use positions along the route shape, with a filter that stops the position going backwards (rings, self-overlapping shapes).
- **Scope, in order:**
  1. **Trips that ran.**
     - A trip counts only if one vehicle passes at least 80% of the canonical stops in order.
     - ρ = observed ÷ (scheduled × coverage), and only where coverage is 0.8 or more. Coverage is the share of the route's ticket-linked registrations seen in the feed that day.
     - ρ is reported separately for the first, middle and last third of the route, to catch short-turns.
     - Elsewhere the source is tagged "schedule only".
  2. **Run-time cross-check**, from interpolated passing times at the first and last stops, with depot pings and long terminal stops dropped.
  3. **Stop-time corroboration** (optional, about 1 day, cut first): interpolated time in a 30–50 m zone at intermediate stops per stop × hour, compared with the model's boardings + alightings per bus.
     - Expectation written beforehand: across-stop Spearman ≥ 0.3 overall and > 0 on every tested route.
     - Reported with the mid-block null test.
     - Never used to tune anything.
- **Output:** small checksummed aggregates (`gps_route_hour`, `gps_stop_hour`), committed so the one command runs without the 16 GB archive.
- **Hard cut-off end of 20 Nov.** If out, the model uses ρ = 1 and ticket run times, and the note says so.

### 5.6 Crowding model

For route r, stretch k (stop k to k+1), day type d, window w:

1. **Riders on each stretch at on-board time.**
   - Each ticket is placed on stretch k at purchase time + corrected run time from its boarding stop. Purchase time is a good proxy for boarding in both channels.
   - Every stretch exists for every window, with explicit zeros.
2. **Alighting correction.**
   - App tickets end at route terminals about twice as often as they start there.
   - Terminal alightings are capped at the reverse route's terminal boardings × the route's intermediate-stop ratio.
   - The excess is spread over the stops in the same fare slab before the terminal, in proportion to the reverse direction's boardings.
   - Published with and without the correction. Last stretches whose level depends on it are shown as Rough guess at best.
3. **Load base.**
   - Riders y and buses S are counted in a centred 90-minute window, reported every 30 minutes on weekdays.
   - Weekends use 60-minute steps on a 120-minute base.
4. **Supply** S = scheduled passing buses in the same window × ρ.
   - If S = 0 while y > 0: widen to ±30 min, then to the route-hour.
   - If still 0: "no bus scheduled". Commuters see No data; operators see "schedule mismatch".
   - Never divide by a floor value.
5. **App riders per bus** ℓ = y ÷ S (per clean day).
6. **Scale to people on board.**
   - E_op = published operator ridership ÷ resolved app passengers per clean day for that operator: about 35–37 for DTC, about 79 for cluster.
   - **Capacity bound per route:** B_r = crush load of the route's bus mix ÷ the 95th percentile of the route's weekday peak ℓ over cells with ≥ 30 tickets.
   - **Route scale** E_r = min(E*_op, B_r). E*_op is solved by bisection so that each operator's total still matches published ridership (water-filling).
   - Routes where the bound binds are flagged "scaled to bus capacity (high app use)" and counted.
   - People on board L = E_r × ℓ, with a range combining:
     - **sampling:** the standard error from day-to-day variation (SD of the cell's daily values over clean days, zero days included, ÷ √days)
     - **scale:** 0.7–1.3 × E_r (upper end capped at B_r)
   - Displayed people on board are capped at crush load, with the flag "full: real demand is likely higher".
7. **Levels by bus type** (config values with sources):

   | Bus | Seats | Rated total | Crush |
   |---|---|---|---|
   | 12 m AC (electric or CNG) | 35 | 63 | 100 |
   | 9 m DEVI | 23 | 36 | 42 |
   | 12 m non-AC CNG | 37 (weak source) | 63 | 100 |

   - **Usually seats:** L < 0.7 × seats (reserved seats for women, seniors and others are rarely free).
   - **Usually standing:** L up to the rated total.
   - **Usually crowded:** L above the rated total, i.e. more people than the bus is rated to carry.
   - Mixed fleets use the share-weighted thresholds.
   - Sensitivity: a "comfortable capacity" alternative (12 m 77, 9 m 32: seats plus 4 standees per m², the CESL off-peak cap).
8. **Evidence state per cell:**
   - **Based on many tickets:** the level is the same across the whole range.
   - **Rough guess:** the range spans two levels, or the route is flagged "low app use".
     - Low app use means app riders per scheduled trip on a shared stretch below one third of that stretch's median across routes.
     - If the upper end is below the Seats threshold, show "Usually seats" as a rough guess, because a quiet count on a route that does sell app tickets is evidence of a quiet bus.
   - **No data:** the route's app riders per scheduled trip are below the network 25th percentile, or no bus is scheduled.
9. **No shrinkage.** Sparse cells are handled by the wider load base and the rules above.
10. **No bunching factor in commuter levels.**
11. **Per-trip running counts are not used.** There is about one app ticket per scheduled trip; the note explains this.

### 5.7 Outputs

- `stretch_crowding.parquet`. Columns:
  - identity: route_id, short name, operator, direction, stretch (stop ids and names), day type, window
  - counts: app riders, tickets n, buses S with source (GPS / schedule / widened)
  - bus: type mix
  - estimates: E_r, people on board (central, low, high), seats, rated total, crush, level
  - state: evidence state, flags (scaled to capacity, low app use, full, schedule mismatch, alighting-sensitive, office special)
- **Corridor layer**, per stop pair × window, combined across routes: people on board ÷ total rated capacity, share of buses Usually crowded, crowded rider-minutes. Shipped as one simplified geometry file keyed by stop-pair id plus a compact values file per day type, joined in the browser.
- Other files:
  - `route_hour_summary.csv`
  - `validation_report.json` and `.md`
  - `data_quality.md`
  - `coverage.csv` (share of bus-km per level and evidence state by hour, day type and operator)
  - `manifest.json`
- Only small reports and the GPS aggregates are committed. Large outputs are regenerated by the one command.

### 5.8 Validation

**A. Invariants that stop the run**
- Ticket conservation per route: raw = resolved + rejected, by reason.
- Output rider-minutes equal resolved-ticket rider-minutes within ±0.5%.
- Rider volume with no bus after the fallback stays under 1%.
- Modelled hourly run times are within ±15% of ticket-pair run times.
- Time-zone invariance (a fixture test).
- Schema; no NaN or inf.

**B. Expectations written down before the first full run**
- `validation/expectations.yaml` is committed on 18 Nov, before any model output exists. Each item has a source:
  - AM peak 08–10 and PM peak 17–20 in crowded rider-minutes from the model output
  - weekends lower, with a flatter and later peak
  - radial routes busier inbound in the AM and outbound in the PM (inbound = towards the terminal nearer CP/ITO, by geometry)
  - **the ten researched corridors** (section 3), each with its evidence grade, stated peak and GTFS stops. A corridor counts as a hit if at least one of its mapped stretches is in the network's top decile of weekday crowded rider-minutes per km in its stated peak window (or either peak if none is stated). Hits are reported by evidence grade.
  - the GPS stop-time expectation (5.5)
  - published figures: DTC bus-km within ±20% of 5.01 lakh/day; fleet load factor within the published 78–89% band
- Each gets a hit or miss in the report; misses are reported, not tuned away.

**C. Week-to-week repeatability (the brief's stability check)**
- Leave one weekday block out in turn (5–9, 12–16, 21–23, 26–30 Oct).
- Report, by week pair and ticket band, rider-weighted:
  - the share of commuter-facing cells whose level is unchanged
  - the correlation of route-direction-hour loads
  - coverage of the sampling ranges
- The word "accuracy" is not used.

**D. Independent checks (no field count is possible; the note says so)**
- **Published figures:**
  - modelled DTC bus-km per day (scheduled × ρ) against the published 5.01 lakh
  - modelled passenger-km ÷ seat-km against the published load factors (DTC 88–89%, cluster 78%)
  - Both are rough checks: the definitions differ.
- **External corridors:** the hit/miss list in B.
- **GPS stop times:** relative activity only, if the GPS layer is in.

**E. Sensitivity**
- Share of cells changing level when:
  - E moves ±30%
  - the comfortable-capacity thresholds replace the rated totals
  - capacity moves ±10%
  - the 9 m vehicle rule moves from 50% to 90%
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
- **Presets** (one tap each):
  - the brief's example, ISBT Anand Vihar → Connaught Place, weekday 18:00
  - its reverse, Connaught Place → ISBT Anand Vihar, weekday 18:00. Outside evidence says the Vikas Marg corridor is busiest eastbound in the evening, so this pair shows direction-awareness.
  - one morning trip on the Ambedkar Nagar – ITO corridor
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
- **Evidence** in plain words: Based on many tickets / कई टिकटों पर आधारित, and Rough guess / अंदाज़ा (कम टिकट). Capped cells add "Full buses may not stop / भरी बस शायद न रुके".
- **"Why?"** shows: "Based on app tickets (about 1 in 40 riders), scaled up to all riders. Women riding free and pass holders are not in this data, so buses can be fuller than shown." It also gives the people-on-board range against the bus's seats and rated total, the bus type, the period ("October 2026 weekdays, festival season") and the route flags.
- The rough-guess card is designed as the common case.
- Hindi covers level chips, roles, buttons and the headline sentence; more if time allows. Stop names stay as in GTFS.
- Light page:
  - compiled CSS
  - pinned libraries
  - system font + Noto Sans Devanagari
  - 16 px text, 48 px tap targets
- A footer credits Transport Stack / IIIT Delhi and ONDC e-ticketing.

### 5.12 Operator view

- **Ranked extra trips.**
  - For each route-direction and departure window, walk the trip's stretches at the windows it reaches them, with S + 1.
  - Sum the crowded rider-minutes removed and the riders moved down a level; rank per operator.
  - Use standard terms: maximum load section, load factor.
- **Corridor map with a time slider** (from the corridor layer).
- **Route heat strip:** stretches × windows, as the drill-down.
- **Heatmap** of the top 50 route-directions, with operator and corridor filters.
- **Flags:** scaled to capacity, low app use, full (censored), schedule mismatch, bus type. "Buses that ran" come from GPS where coverage is 0.8 or more; elsewhere they are the app-linked vehicles seen (a lower bound), marked as such.
- **Export:** CSV.

### 5.13 Engineering

- **Before any feature work:**
  - install the missing packages, write a lock file with exact versions, and test from it
  - fix `.gitignore`: ignore `data/processed_/`, `*.parquet`, `*.pkl`, `*.geojson`, `*.7z`, `*.db`, and everything in `data/processed/` except reports and the GPS aggregates; un-ignore `tests/fixtures/**`
  - commit by explicit paths, never `git add -A`
  - a pre-commit check rejects files over 5 MB and data paths other than reports
  - tag a working `baseline` of the old app pointed at `data/processed_/`, as a fallback demo
- **Tests:**
  - toy GTFS feed and ticket fixtures in `tests/fixtures/`
  - unit tests: to-stop run times, hourly factors, S = 0 rule, direction parser, D- route rule, time zone
  - golden tests for 3–5 demo journeys
- **CI:** local `pytest`; GitHub Actions once the branch is pushed (cut-able).
- **Before submission:** a clean-clone test of the README quick start.
- **Backups:** `phase1` pushed at each evening check, plus a nightly `git bundle` to a folder outside the repo.
- **Long jobs** (GPS extraction, full runs) are resumable: they write per-stage outputs and skip finished stages.

### 5.14 Live link, docs and submission

- **Live link** (my call: a public Hugging Face Space, Docker, under the user's Hugging Face account):
  - It serves the API and both screens from the precomputed aggregate tables only. No raw tickets and no vehicle-level data.
  - Rehearsal deploy on 22 Nov; final deploy on 23 Nov from the frozen tag. The user approves before anything is published.
  - The README gives a health-check URL and a note about cold start.
  - Fallback if the Space is down: the video and the one-command local run.
- **18 Nov:**
  - move `PROGRESS_REPORT.md`, the old proposal and the old demo script to `docs/archive/` with a "superseded" banner
  - remove hard-coded KPIs from the API and UI
  - grep judge-facing files for κ, kappa, McRAPTOR, Pareto, sigmoid, "score"
- **Technical note** (about 4 pages plus an appendix; in the repo, and summarised in the proposal):
  - method, plus an assumptions table linked to `config.py`
  - a **brief checklist table**: running count per trip, pass and free riders, planned vs actual alighting, bus size (12 m vs 9 m, with sources), thin routes and hours, simple display; for each, what was done, the evidence, and the remaining risk
  - the 2.2% vs 3–4% reconciliation
  - least-reliable areas, quantified with the coverage table
  - validation and independent-check results, and a plain statement that no field count was possible
  - Phase 2 plan
  - no latency section
- **Proposal:** a PDF rendered from markdown; draft v1 on 20 Nov with placeholders; numbers rendered on 23 Nov.
- **Video:** short (target 4–5 minutes).
  - Storyboard on 18 Nov:
    - 30 s: problem and data, stated honestly
    - 90 s: the presets (three cards, "Why?", leave later, both directions)
    - 60 s: operator corridor map and top extra trips
    - 60 s: evidence (peaks, weekday/weekend, repeatability, corridors, published figures, coverage)
    - 30 s: limits and Phase 2
  - Script v2 on 22 Nov; recorded on 23 Nov on the frozen tag.
- **Submission:** proposal PDF, video link, live link and GitHub link, submitted by 18:00 IST on 24 Nov.

## 6. Schedule (thin version end to end first; each evening's check must be visibly true)

| Day | Build (assistant) | Team (Aniket, Ash) | Evening check |
|---|---|---|---|
| 18 Nov | Environment, lock, `.gitignore`, baseline tag; `run --until network` (cleaning, calendar, resolving, clock factors, bus types, places); S = 0 rule; `expectations.yaml` (corridors, published figures); evidence table + demo-journey shortlist; archive old docs; storyboard | Approve design v3; optionally ask the organisers whether the finale can be attended remotely | Match ≥ 93% with counts; toy tests pass; run-time gate passes; expectations committed before any model output; pushed |
| 19 Nov | GPS go/no-go 12:00; model v0 (riders, supply, scale, levels, evidence); `/v1/plan` v0 for the presets; frozen JSON | Review the first outputs on the ten corridors | The presets return three options from the new model; pushed |
| 20 Nov | Validation suite; alighting correction; weekend; GPS in or out (cut-off); proposal draft v1 | Review the proposal draft | Report renders; all invariants pass; GPS decision recorded; pushed |
| 21 Nov | Planner (places, roles, leave later, night flags); API v1 incl. corridors; commuter screen v1 | Review the cards | Three cards for 5 demo journeys at phone width; pushed |
| 22 Nov | Operator view (extra trips, corridor map, heat strip, CSV); Hindi; live-link rehearsal deploy (after the user approves); demo script v2 | Phone test with 5 people (evening) | Operator page answers "where does one extra trip help most"; rehearsal link works; pushed |
| 23 Nov | Fixes from the phone test; clean-clone rebuild; tests; note, README and proposal rendered; freeze tag; final deploy | Record video | Clean clone reproduces the report; no placeholders; no old terms; live link serves the frozen tag; pushed |
| 24 Nov | Buffer only | Re-record or upload; submit by 18:00 IST | Submitted |

**Cut list (cut first to last):**
1. GPS stop-time corroboration
2. Heatmap of the top 50 route-directions
3. Service-class tagging (keep the school/DAF exclusion)
4. Fare check and ring wrap (report counts; exclude Mudrika routes and say so)
5. Leave later beyond +20 min
6. Hindi beyond chips, roles, buttons and headline
7. Route heat strip drill-down
8. Rest of the GPS layer (ticket clock and ρ = 1 remain)
9. GitHub Actions

**Never cut:**
- IST pin and exclusions
- the ticket clock
- S = 0 rule
- operator scale with capacity bound
- bus types and sourced capacities
- evidence states and No data
- invariants
- written expectations with the ten corridors
- repeatability
- the published-figure checks
- the brief's preset
- three roles
- corridor map
- extra-trip ranking
- technical note, proposal, video and live link
- clean-clone README

## 7. Risks and fallbacks

- **Scale still off for some routes:** ranges and evidence states carry it to users. The published-figure and corridor checks test it, and the note stresses that comparisons are firmer than absolute counts.
- **No ground truth:** stated plainly. The independent checks are labelled for what they are.
- **GPS trip definition fails:** the archive and route ids already passed; the 19 Nov checkpoint and 20 Nov cut-off apply. The ticket clock already covers every route.
- **Network drops on this Mac:** the keep-awake hold, resumable jobs, and a push at each evening check.
- **Live link down during judging:** health check and cold-start note; fallback to the video and the local run.
- **Thin data on demo journeys:** demo journeys are chosen on 18 Nov from the evidence table. The brief's preset is kept even if it shows no trade-off.
- **Overrun:** the thin version must be running on 19 Nov; then the cut list.
- **Finale in Delhi while the team is in Pune:** ask the organisers early whether remote presentation is allowed. This doesn't block Phase 1.
- **Judges re-run elsewhere:** time zone pinned and tested, lock file, committed GPS aggregates, clean-clone README.

## 8. Decisions

**Made by the team:**
- judges first this week
- GPS check with a 20 Nov cut-off
- city-scale pieces designed now, built in Phase 2
- the assistant writes code while the team reviews, tests and records the demo
- frequent commits under the user's name with no AI co-author line, pushed when asked (the user asked for pushes on 17 and 18 Nov)
- no field count (the team is in Pune)
- all four submission items, including a live link
- Ash has finished and will not push
- busy corridors and bus capacities come from online research

**My calls (open to change):**
- the ticket-pair clock, with GPS as a cross-check
- operator scale with a capacity bound and water-filling, plus ranges combining sampling and scale
- the capacity table, with "crowded" meaning above the rated total and sensitivity at comfortable capacity
- 9 m routes by the D- prefix plus the vehicle rule
- plain-word evidence states instead of railway-style chips
- Usually-seats at 0.7 × seats
- no shrinkage and no bunching factor
- weekends pooled
- a 90-minute centred load base
- the alighting correction, with sensitivity
- the S = 0 rule
- invariants, plus expectations written before results (including the ten corridors and the published figures)
- GPS stop times as corroboration only
- the corridor layer
- extra-trip ranking
- places and hub aliases, and the reverse preset
- a Hugging Face Space for the live link
- old docs archived and docs rendered from pipeline output
- pushing `phase1` at each evening check
- submit by 18:00

## 9. Left to the builder

- water-filling and percentile details
- the corridor hit rule's exact geometry
- place grouping thresholds
- GPS cleaning details
- corridor geometry simplification
- visual details within 5.11–5.12
- file and function names
- caching
- the Space's Dockerfile and data packaging

## 10. Team answers (18 Nov)

1. **Field count:** not possible; the team lives in Pune. Replaced by the independent checks in 5.8 D.
2. **Submission:** needs all four: proposal PDF, video, live link, GitHub link. Public rules add a README and a short technical note (5.14).
3. **Bus seats and capacities:** the team cannot check in person. Researched online and verified against sources (section 3).
4. **Ash's work:** Ash has finished and will not push. The user has asked for pushes, so `phase1` is pushed at each evening check.
5. **Busiest corridors:** researched online from outside evidence only, then graded (section 3). They are pre-registered before any model output exists.
