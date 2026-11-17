# Phase 1 design: crowding model and journey planner

Transport Stack Hackathon 2026, Problem 2 (crowdedness-aware journey planner, Delhi buses).
Written 17 Nov 2026. Phase 1 submission closes **24 Nov 2026, 23:59 IST**.

## 1. Intent

Delhi bus riders choose trips by time alone because no planner knows how full buses are. We are building a pipeline that turns one month of ticket data into honest crowding estimates by route, direction, stretch between stops and time of day, and a planner that shows those estimates next to each trip option, so a commuter can trade a faster trip for a more comfortable one. A second view lets bus operators and planners see where buses are overloaded and where one extra bus helps most.

The judges score two things: how well the crowding estimate is grounded in the data, and how clearly it is shown to commuters. The brief says a simple planner with a sound crowding model beats a polished planner with a weak one. So every hour this week goes first to the model and its evidence, then to a clear screen.

The team also wants something that would survive real Delhi use, so the design is honest by default: no invented values, every estimate carries a confidence level, and the measured accuracy is published.

## 2. Goals, non-goals, anti-goals

**Goals (Phase 1, by 24 Nov)**
1. A re-runnable pipeline: raw tickets + GTFS (+ GPS sample) to crowding tables with one command.
2. Crowding per route, direction, stretch and 30-minute window, for weekday / Saturday / Sunday, with people on board (as a range), a commuter level (Seats / Standing / Crowded / No data) and a confidence state.
3. Accuracy measured on a held-out week and reported per confidence class, plus automated checks against known patterns.
4. A planner that returns three options with fixed roles (Fastest, Less crowded, Leave later), each showing times, the crowding level, the crowded stretch and the trade-off.
5. An operator view that ranks overloaded route-stretch-hours and the effect of one extra bus, with CSV export.
6. A technical note whose every number comes from the pipeline's own output.

**Non-goals (designed now, built in Phase 2 or later)**
Public hosting for lakhs of users, offline phone app, live GPS arrival times, live per-bus load, OpenTripPlanner integration, survey-calibrated cost weights, full Hindi stop-name search, user accounts.

**Anti-goals (failure even if it works)**
- Showing a crowding level for a stretch we have no evidence for, or showing "no data" as comfortable.
- Raw scores or percentages shown to commuters.
- Any number in the docs or UI that the pipeline did not produce.
- A broken demo at submission time (code freeze at 12:00 IST on 24 Nov).

## 3. Facts and constraints

**Tickets** (`data/raw/October-Delhi.csv`, 1–31 Oct 2026)
- 2,559,899 tickets, 2,753,606 passengers, 2,259 route strings, 6,810 vehicles.
- ONDC app/QR tickets only (data README). Fares are 90% of standard slabs (₹4.5, 9, 13.5, 18, 22.5...). Only 8 zero-fare tickets and `ticket_type_id` is always 1, so women's free rides and passes are absent.
- About 2.2% of published ridership (40.8 lakh/day, FY2024-25; to be re-checked).
- `vehicle_number` is the literal string `NULL` on 48.5% of rows. Expert analysis shows NULL and linked tickets are both bought on board and behave as one population, so the NULL share must never be used to scale bus counts.
- `is_ac` describes the bus, not the route (some routes run mixed fleets).
- `created_at` is a time-zone-aware timestamp; reading hours without pinning `Asia/Kolkata` shifts everything by 5.5 h on a UTC machine.
- Known holes: 2 Oct (41k tickets, holiday), 20 Oct (49k, Dussehra), 6 Oct 09:15–11:00 (281 tickets against about 18.6k on 7–8 Oct), 17–19 Oct (NULL-channel share drops to 0.35 / 0.15 / 0.38 against about 0.51).
- Weekday route-direction × hour totals agree between weeks (r = 0.96). 41% of those cells have under 10 tickets, but the 21% with 75+ carry 80% of riders.

**GTFS** (`data/raw/gtfs/delhi_buses_static_gtfs_v1/`, feed v32)
- 2,574 routes (DTC 1,814, DIMTS cluster 760), 80,357 trips, one service id running every day. Feed dates (2025–2040) are meaningless.
- `direction_id` is empty; direction is the UP/DOWN suffix of `route_short_name`.
- `stop_times` has `fare_stage` and `stop_dist` (`stop_dist` empty on the routes sampled).
- Scheduled run times change with time of day on some routes (route 1924: about 53 min in the morning peak, 31 min at midday) and not on others.

**GPS** (`delhi-dtc-bus-gtfs-rt-2026-10.7z`, downloading to `data/raw/gps/`)
- 31 daily SQLite files, 16.1 GB compressed, 124 GB unpacked, one table `vehicle_feed` (vehicle_id, lat, lng, speed, route_id, trip_id, timestamp UTC, date and time IST). Raw: duplicates, gaps, noise.
- DTC buses only. DTC routes carry 77.4% of ticket passengers (cluster 20.8%, unmatched 1.8%).
- `vehicle_id` is the bus registration, the same format as ticket `vehicle_number`.

**Other constraints**
- 7 days, 2 people plus an AI coding assistant writing most code. Python 3.12. macOS, 375 GB free disk.
- The repo belongs to Ash (ashhhcodes/delhi-crowd-planner). Work lands through short-lived branches and pull requests. Commits carry no AI co-author line.
- Only aggregates are published; no vehicle-level data leaves the pipeline.

## 4. Approaches

1. **Fix and finish on tickets + schedule.** Low risk. Weakness: how many buses ran and how long trips take come from a timetable Delhi buses often ignore, so loads can be wrong in a way we cannot check.
2. **Same, plus a GPS reality check (chosen by the team).** Replaces three guesses with observations for DTC routes: trips that actually ran, real run times by hour, and how unevenly buses are spaced. Costs about 1.5 days and a 16 GB download. Hard cut-off: end of 20 Nov. Approach 1 is built first, so falling back loses nothing.
3. Dropped: rebuilding on OpenTripPlanner (days of setup on the part that is not judged); relative-only "busier / quieter than usual" levels (the brief asks for seats / standing / crowded).

## 5. Design

### 5.1 Pipeline shape (my call)

One command rebuilds everything from raw data: `python -m src.pipeline.run`. Stages write versioned files to `data/processed/` and a `manifest.json` (input checksums, row counts, run time, code version). All assumptions live in one file, `src/pipeline/config.py`, each with its source or "assumption".

Proposed modules (names are the builder's to adjust):
`clean.py`, `resolve.py` (from today's sprint1), `network.py` (GTFS), `gps.py` (optional layer), `loads.py` (the model), `validate.py`, `run.py`. The old sprint scripts are replaced; git history keeps them.

### 5.2 Cleaning

- Pin `Asia/Kolkata` for every time operation.
- Exclude: 2 Oct and 20 Oct (holidays), 6 Oct 09:15–11:00, and 17–19 Oct (channel outage). My call: exclude rather than model holidays separately; the note says so.
- Day types: weekday, Saturday, Sunday. Denominators are counts of clean days per day type (and per window where a window was excluded).
- Output a data-quality report (daily totals, excluded windows, NULL share by day).

### 5.3 Resolving tickets to GTFS

Keep today's route-scoped fuzzy stop matching (93% match) and add:
- Route aliases (strings sharing vehicles and stops on the same day, e.g. `YMS(+)UP` / `YMSPLUS`).
- Direction remap per route: when most of a route's tickets come out reversed, swap the direction mapping instead of dropping them (more than 99.9% of raw tickets agree with their stop pair's direction, so "conductor toggle" is not the cause).
- Ring (Mudrika) routes: allow wrap-around.
- Fare check: reject matches whose fare stage distance contradicts the fare slab paid.
- Report match rate, remapped and rejected tickets per route.

### 5.4 Network from GTFS

- Canonical stop sequence per route_id: the longest trip (as today).
- **Run times attached to the to-stop** (fixes today's one-stop shift) and **by time of day**: for each segment, the median scheduled run time of trips passing it in each hour.
- Scheduled buses passing each stop per 30-minute window (from arrival times at that stop, not first-stop departures).
- Service hours per route (first and last bus).
- Road-following shape slice per segment, with a generator script (today's .pkl has none).

### 5.5 GPS reality layer (time-boxed, DTC only)

Process a sample of clean days one at a time (extract one SQLite, aggregate, delete): at least 6 weekdays, 2 Saturdays, 2 Sundays.
1. Check on day one that GPS `route_id` matches GTFS `route_id`; if not, map through trip ids or route names before anything else.
2. **Trips that ran**: distinct trips per route per hour, giving reliability ρ = observed ÷ scheduled.
3. **Real run times**: trip duration by start hour, giving a factor against the scheduled run time per route-hour.
4. **Spacing between buses**: headway mean and coefficient of variation (CV) at a reference stop per route-hour.
5. **Ticket check**: for tickets with a vehicle number, the bus's GPS position at purchase time, to confirm boarding stop and direction resolution (reported as a percentage, not used to change tickets in Phase 1).

Cluster routes and DTC route-hours with too few GPS trips use the median DTC factor for that hour, marked as such. If these outputs are not solid by the end of 20 Nov, the pipeline uses schedule values (with ρ = 1 and CV from tickets where possible) and the note says so.

### 5.6 Crowding model

For each route r, stretch k (stop k to k+1), day type d and 30-minute window w:

1. **Time on each stretch.** Each ticket's time on stretch k = purchase time + run time from its boarding stop to stop k (GPS-adjusted where available). Riders are counted in the window when the bus is on the stretch, not when the ticket was bought (about half of on-board minutes fall in a later window).
2. **Digital riders.** y = average app passengers on the stretch in that window per clean day. Every stretch exists for every window (explicit zeros), so through-riders are never lost.
3. **Supply.** S = scheduled buses passing stop k in w × ρ (GPS) — buses that actually ran.
4. **Digital load per bus.** ℓ = y ÷ S.
5. **Shrinkage for sparse cells.** ℓ̂ = w·ℓ + (1 − w)·prior, w = n ÷ (n + κ), where n is the month's ticket count in the cell and κ (10–20) is tuned on the holdout. Default prior: the route-direction's window total smoothed over neighbouring windows, times the stretch's average share of the route's load; weekends borrow the weekday shape scaled by the route's weekend factor.
6. **Scale to real riders.** People on board L = E × ℓ̂, with E = published daily ridership ÷ mean clean-day app passengers (about 43). This implicitly adds free and pass riders, assuming app use is spread evenly. E's uncertainty (±30%) is reported once, globally, with a sensitivity check; it is not folded into each cell.
7. **What a rider experiences.** Riders arrive spread out, so more of them board the bus after a long gap. Rider-experienced load = L × (1 + CV²), using the GPS spacing CV (default CV from tickets or 0 if neither is available, stated). The same CV gives expected wait = mean headway ÷ 2 × (1 + CV²).
8. **Levels by bus type.** Seats and capacity per bus type are config values to be confirmed by the team (defaults: 12 m 37 seats / 70 total; 9 m 25 / 40). Bus type mix per route-window from `is_ac` and the 9 m route list.
   - Seats: experienced load < 0.85 × seats
   - Standing: < seats + 0.5 × (capacity − seats)
   - Crowded: above that
9. **Confidence.** Each cell gets a range for people on board from the holdout-measured error for its ticket count (about 14–22% at 75+ tickets, 33% at 30–74, 47% at 10–29).
   - Confident: the level is the same across the range.
   - Rough guess: the range spans two levels.
   - No data: n < 10. The level is withheld; the estimate is kept internally only for the operator view, marked.

### 5.7 Outputs

- `stretch_crowding.parquet`: route_id, route_short_name, direction, stretch (from/to stop ids and names), day type, window, digital riders, tickets n, buses S (and source: GPS or schedule), people on board (central, low, high), experienced load, seats, capacity, level, confidence, flags.
- `stretch_crowding.geojson` (per day type and window) for maps.
- `route_hour_summary.csv` for operators.
- `validation_report.json` and `validation_report.md`; `data_quality.md`; `manifest.json`.

### 5.8 Validation suite (automated, part of the one command)

1. Holdout: fit on clean weekdays 1–23 Oct, predict 26–30 Oct; error per confidence class and per ticket-count band.
2. Ranking: when one cell is at least 1.5× another at the same hour, how often the holdout agrees.
3. Split-half: loads from NULL-channel tickets alone vs linked tickets alone.
4. Peaks and day types: rider share 8–10 am and 5–8 pm; Saturday and Sunday as a share of weekday.
5. Direction switching: share of routes whose busier direction flips between AM and PM (tickets show about 72%).
6. Hubs: the busiest 1% of stretch-hours lead into the top AM alighting stops.
7. Sanity gates (fail the run): every stretch has every window; no constant fill values; a UTC run equals an IST run; under 1% of stretch-hours above capacity.
8. Sensitivity: share of cells changing level when E moves ±30% and capacity ±10%.
9. GPS (if used): ρ distribution, scheduled vs observed run times, CV by hour.

Gates 7 stop the pipeline; the others are reported honestly, not tuned to targets.

### 5.9 Planner

Keep the frequency-based round search (it suits buses that ignore timetables) and stop calling it McRAPTOR. Changes:
- Run times by hour from 5.4/5.5; service hours enforced; waits from real headways and CV.
- Crowding input is the stretch table. Missing means unknown, never a number.
- Three option roles:
  - **Fastest**.
  - **Less crowded**: within max(15 min, 30%) of the fastest time, fewest minutes at Crowded, then at Standing, ranked on the upper end of the range; options with over half their ride in No data are not eligible.
  - **Leave later**: the same trip at +10/+20/+30/+40 min; show the earliest that drops the headline level.
- If two roles give the same trip, return it once with both roles.
- Headline level of a trip = the worst level the rider spends at least 5 minutes in, plus the crowded stretch by name and minutes.
- Labels are computed from the returned options, never from search settings.

### 5.10 API (v1)

- `GET /v1/plan?from=<stop_id>&to=<stop_id>&depart=HH:MM&day=weekday|saturday|sunday`
- `GET /v1/stops/search?q=` (fuzzy, merges roadside stop pairs, shows locality and bus numbers)
- `GET /v1/crowding?route_id=&day=&window=`
- `GET /v1/operator/overload?day=&hour=` and `.csv`
- `GET /v1/health`: data version, data dates and computed counts.

Requirements: bad input gives a clear 4xx, never a 500; the data version is in every response.

### 5.11 Commuter screen

- Phone first, list first, map on request. The brief's example (Anand Vihar ISBT → Connaught Place, weekday 6 pm) is a one-tap preset.
- Three cards, each showing:
  - role, duration, leave → arrive times
  - level chip
  - one trade-off line against the fastest
  - buses, changes and fare
  - a time bar shaded by level
  - the crowded stretch in one sentence
- Level chips always combine a word, dots and colour, never colour alone:
  - Seats / सीट मिलेगी ●○○ teal
  - Standing / खड़े होने की जगह ●●○ amber
  - Crowded / भारी भीड़ ●●● dark red
  - No data / जानकारी नहीं grey dashed
- Confidence uses a railway-style status:
  - solid chip = confident
  - outlined chip with "?" = rough guess
  - grey = no data
  - "Why?" opens: tickets behind the estimate, days covered, people on board range against seats.
- Always say "usually" and give the data period (October 2026 weekdays). No percentages or scores.
- English and Hindi for all interface text and levels in Phase 1. Stop names stay as in GTFS.
- Light page: compiled CSS (no Tailwind development CDN), pinned libraries, system font plus Noto Sans Devanagari, 16 px text, 48 px tap targets.

### 5.12 Operator view

- **Heatmap**: route-direction × hour, by level, hatched where the data is thin.
- **Ranked table**: route, stretch, hours, people on board (range) against capacity, buses per hour (scheduled vs ran), crowded rider-minutes, and crowded rider-minutes removed by one extra bus in that window (the default sort), plus confidence.
- **Drill-down**: stop-by-stop profile chart for a route and time.
- **Export**: CSV.

### 5.13 Re-runnability, tests and docs

- Pinned dependencies (lock file), Python 3.12, a README quick start that works as written, and checksums verified against `SHA256SUMS`.
- `*.7z` added to `.gitignore`. A LICENSE file to match the README (MIT unless the team says otherwise).
- Unit tests on a small synthetic GTFS feed and ticket fixture (the routing review's toy feed is a starting point) and GitHub Actions CI on fixtures only. Today's tests that need the full data and check constants are replaced.
- Technical note rewritten for this method:
  - assumptions table, linked to `config.py`
  - where estimates are least reliable:
    - quiet routes, weekends, early and late hours
    - ring routes and variants
    - last stretches of long routes
    - cluster routes (no GPS)
    - free riders' timing
  - validation results pulled from `validation_report.json`
  - measured planner latency
- README KPIs computed, not hard-coded.

## 6. Schedule and roles

| Day | Build (assistant) | Team (Aniket, Ash) |
|---|---|---|
| 17 Nov | Design approval; GPS download runs | Review design |
| 18 Nov | Cleaning, IST pin, run-time fix, fill-forward, aliases, direction remap; first GPS day extracted and route_id check | Confirm seats/capacity and 9 m routes |
| 19 Nov | Time-on-stretch model, supply, scaling, levels; GPS trips, run times, spacing on sample days | Review outputs for known corridors |
| 20 Nov | Shrinkage, confidence, validation suite; GPS layer in or out (cut-off) | Spot-check routes they ride |
| 21 Nov | Planner fixes, option roles, API v1 | Review |
| 22 Nov | Commuter screen, operator view | Hindi wording check |
| 23 Nov | One-command rebuild, tests, CI, technical note, README | Test with 5 commuters on a cheap phone outdoors |
| 24 Nov | Buffer; freeze 12:00 IST | Demo video, proposal, submit |

Cut list if behind, cut first to last:
1. Docker
2. Map in the operator view
3. Rider-experienced load factor (keep trips-ran and run times)
4. Hindi stop search
5. Leave later beyond +20 min

## 7. Risks and fallbacks

- GPS route ids do not match GTFS: checked on day one; cut-off 20 Nov.
- Download fails or is slow: resumable download; schedule fallback.
- Validation shows weak areas: report them; confidence states carry the weakness to users.
- Parallel edits with Ash: branches and pull requests.
- Judges re-run on another machine or time zone: time zone pinned, fixtures, README tested from a clean clone.

## 8. Decisions

**Made by the team:** judges first this week; GPS check with a 20 Nov cut-off; city-scale pieces designed now, built in Phase 2; the assistant writes code while the team tests, confirms bus data and records the demo.

**My calls (open to change):**
- Excluding holidays and data holes.
- Anchoring scale to published ridership, with uncertainty stated once rather than per cell.
- Levels defined in people against seats.
- Confidence from ticket counts calibrated on the holdout.
- Keeping the frequency-based planner.
- Three fixed option roles.
- Hindi interface text in Phase 1, Hindi stop search later.
- Module layout.
- Branches and PRs.

## 9. Left to the builder

Exact prior hierarchy and κ tuning; GPS cleaning and how passing times are derived from pings; caching; visual details within 5.11–5.12; file and function names.
