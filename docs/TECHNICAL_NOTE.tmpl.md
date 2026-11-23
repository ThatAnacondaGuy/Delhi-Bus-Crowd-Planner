<!-- Rendered to TECHNICAL_NOTE.md by `python -m src.pipeline.run --until render`. Edit this template, never the .md: every number is a placeholder filled from the pipeline's own output or from config.py. -->
<div align="center">

# Technical note

### How we estimate how crowded a Delhi bus stretch usually is, and how far to trust it

Transport Stack Hackathon 2026 · Phase 1 · Problem 2 · Aniket Ingale and Ashish Maurya (Ash)

<sub>Run `{{run_id}}` · code `{{code_version}}` · finished {{pipeline_finished_ist}} IST · every number below is read from that run</sub>

</div>

> **In one paragraph.** From {{tickets_clean:,}} ONDC app tickets (October 2026) we estimate, for every Delhi bus route, direction, stretch between two stops and half hour, how many people are usually on board, and we show it to riders as a level: *Usually seats*, *Usually standing*, *Usually crowded* or *No data*. App tickets are about 1 in {{app_riders_one_in}} riders, so we scale them up, never to more than a bus can hold. **No field count was possible**, so we test the model against everything we can compare it with and report the misses beside the hits. Most levels ({{evidence_rough_share:.0%}} of bus-km) are a Rough guess, and the card says so.

**Contents:** [1 Data](#1-data-and-what-it-cannot-see) · [2 Method](#2-method) · [3 Assumptions](#3-assumptions) · [4 Brief checklist](#4-the-brief-checklist) · [5 App share and the hackathon figure](#5-reconciling-the-app-share) · [6 Validation](#6-validation-and-independent-checks) · [7 Coverage and weak spots](#7-coverage-and-the-least-reliable-areas) · [8 Phase 2](#8-phase-2) · [Appendix](#appendix)

---

## 1. Data and what it cannot see

**Tickets.** One CSV of ONDC app and QR tickets, 1–31 October 2026: {{tickets_clean:,}} tickets, {{passengers_clean:,}} passengers, {{route_strings:,}} route strings. Each row has the route string, boarding and alighting stop names, passengers, fare, time (time-zone aware; we pin every operation to Asia/Kolkata) and, on {{vehicle_missing_share:.1%}} of rows, no vehicle number. Both ticket channels are bought on board and behave as one population, so we never use the missing-vehicle share to scale anything.

Known holes are cut out of every rider count: 2 October (public holiday) and 20 October (Dussehra) as whole days, and three windows (6 October morning, 17–19 October when one channel fell to a quarter of normal, 29 October evening). That leaves {{clean_days}} clean days of {{days_in_file}}.

**Timetable (GTFS).** {{gtfs_routes:,}} routes for DTC and the cluster operator, one service day for every day of the week. The scheduled times are a template: every stop-to-stop time equals the straight-line distance at a fixed 18 km/h, so they carry no information about real traffic. Direction is not in the feed; it is read from the route name (UP, DOWN, ring markers, A-B pairs).

**GPS.** The October 2026 DTC feed (about 11–12 s between pings for most buses). We do not publish it. We reduce it to one aggregate (the share of scheduled trips that ran, by route, hour and day type, and a run-time ratio) from {{gps_sample_days}} sample days, and only that aggregate is in the repository.

**Outside figures** used only as checks: published daily ridership, bus-km and load factor (Economic Survey of Delhi 2025-26; CAG report 4 of 2024), and ten corridors researched without looking at our output.

**What the data cannot see.** Women riding free, pass holders and cash riders are not in app tickets. The month is one festival-season October. There is no count of people on a bus anywhere in it. Everything in this note follows from those three facts.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/architecture-dark.svg">
    <img src="assets/architecture.svg" alt="System diagram: inputs, pipeline stages, outputs, planner and API, screens" width="900">
  </picture>
</p>

---

## 2. Method

Eight resumable stages (`python -m src.pipeline.run`), each reading and writing tables in one DuckDB file. Each step below says what it does, why, and where it can be wrong.

### 2.1 Resolve tickets to the timetable

Stop names in tickets are free text ("Ito Agcr / Ito", "sec", "stn"). Names are first tidied (common abbreviations such as "stn" are expanded). For each route we then match each name only against that route's own stops: an exact match first, then a fuzzy match with a floor of {{fuzzy_floor:.0f}} out of 100. Ties between equally good stops are broken by a second and third comparison; if still tied the ticket is rejected as ambiguous rather than guessed. Route strings that match no route exactly are tried against close aliases (for example the same number without a variant suffix such as STL or EXT) and accepted only when at least {{alias_min_in_order:.0%}} of their tickets resolve in stop order on that route.

**Result:** {{tickets_resolved:,}} of {{tickets_clean:,}} tickets resolved ({{match_rate:.1%}} of tickets, {{match_rate_passengers:.1%}} of passengers). The {{tickets_rejected:,}} rejected are counted by reason in [Appendix A](#a-tickets-that-did-not-resolve). Ticket conservation is a gate: raw = resolved + rejected, per route string.

### 2.2 The travel-time clock

Because the timetable is a template, run times come from tickets. Two tickets bought on the same vehicle, route and day give the real time between two boarding stops. We compare that with the template time and average the ratio by operator and hour (and by route where it has at least 30 pairs).

| Hour of day | DTC: observed ÷ template | Cluster: observed ÷ template |
|---|---|---|
| 06:00 | {{dtc_clock_factor_6h:.2f}} | {{dimts_clock_factor_6h:.2f}} |
| 08:00 | {{dtc_clock_factor_8h:.2f}} | {{dimts_clock_factor_8h:.2f}} |
| 12:00 | {{dtc_clock_factor_12h:.2f}} | {{dimts_clock_factor_12h:.2f}} |
| 18:00 | {{dtc_clock_factor_18h:.2f}} | {{dimts_clock_factor_18h:.2f}} |
| 22:00 | {{dtc_clock_factor_22h:.2f}} | {{dimts_clock_factor_22h:.2f}} |

<sub>From {{ticket_pairs:,}} ticket pairs. Early morning is faster than the template, the evening peak is about {{dtc_clock_factor_18h:.1f}} times slower.</sub>

**A choice we made after seeing numbers, so we show both.** A pair of consecutive tickets can span two different trips (a rider boards a later bus) or be a batch print. We keep pairs whose ratio is between {{pair_ratio_window}} and drop the rest. The window was chosen after looking at the data, so here is the wider {{pair_ratio_window_alternative}} window: the DTC 18:00 factor would be {{dtc_factor_18h_alternative_window:.3f}} instead of {{dtc_factor_18h:.3f}}, and 08:00 would be {{dtc_factor_8h_alternative_window:.3f}} instead of {{dtc_factor_8h:.3f}}. The 08:00 value stays near 1.0 under both windows.

**GPS disagrees a little, and we say so.** On weekdays between 05:00 and 21:00 GPS run times are {{gps_runtime_ratio_min:.2f}} to {{gps_runtime_ratio_max:.2f}} times the ticket clock (median {{gps_runtime_ratio_median:.2f}}), so real trips are roughly 10–20% slower than our clock. We state this and do not apply it. The ticket clock is measured between boarding stops of paying riders; we have not worked out which clock is closer to the truth, so planner travel times may be a little short.

<p align="center"><img src="assets/fig-travel-time-factor.svg" alt="Observed run time against the timetable by hour, DTC and cluster" width="720"></p>

### 2.3 Which scheduled trips really ran

The timetable lists {{scheduled_trips_per_day:,}} trips a day. DTC's published bus-km is far below what that schedule implies, so dividing riders by *scheduled* buses would spread them too thinly. From GPS we count a trip as run when one vehicle passes at least {{gps_trip_stop_share:.0%}} of the route's stops in order (positions interpolated between pings, within 75 m of a stop). The share that ran is set only where at least {{gps_coverage_min:.0%}} of the route's ticket-linked vehicles appear in the feed ({{gps_routes_covered:,}} of {{gps_routes_total:,}} routes). Everywhere else it falls back, in order, to the route's own value, then to the operator's value for that hour and day type, then to the operator's value for the day type. It is never set to 1.

**Result:** about {{gps_trips_ran_share_weekday:.0%}} of scheduled trips show up as having run on weekdays. Applied to the timetable, DTC bus-km come to {{dtc_bus_km_model:,.0f}} a day against {{dtc_bus_km_published:,.0f}} published, which is a check we did not tune to (see 6.4).

<p align="center"><img src="assets/fig-trips-ran-by-hour.svg" alt="Share of scheduled trips that ran, by hour, from GPS" width="720"></p>

### 2.4 Riders on each stretch

Each resolved ticket is placed on the stretches between its boarding and alighting stops, at the time the bus is on each stretch: purchase time plus the corrected run time from the boarding stop. Purchase time is a good proxy for boarding. Every stretch exists in every window with explicit zeros, so a quiet stretch is a measured zero, not a missing value.

**Alighting correction.** App tickets end at route terminals more often than they start there (people buy near the end of a ride): the median route-direction has {{terminal_ratio_median:.2f}} times as many terminal alightings as the reverse direction has terminal boardings, and one in ten has {{terminal_ratio_p90:.1f}} times or more. We cap terminal alightings at the reverse route's terminal boardings times the route's intermediate-stop ratio, and spread the excess over earlier stops in the same fare slab in proportion to the reverse direction's boardings. If the reverse route has fewer than {{alighting_min_reverse_board}} terminal boardings in the month it is uninformative, so we apply no correction and flag the route instead. Of {{terminal_routes:,}} route directions, {{terminal_routes_known:,}} have a known ratio, {{terminal_routes_corrected}} were corrected ({{terminal_moved_passengers:,.0f}} passengers moved) and {{alighting_sensitive_routes}} are flagged *alighting-sensitive*: their last {{alighting_last_stretches}} stretches show a Rough guess at best. The result is published with and without the correction (6.5).

### 2.5 Buses and riders per bus

Riders and buses are counted in a centred {{base_weekday_min}}-minute window, reported every {{step_weekday_min}} minutes on weekdays ({{base_weekend_min}} and {{step_weekend_min}} on weekends, where tickets are thinner). Buses on a stretch are the scheduled buses passing in that window times the share that ran. If no bus is scheduled while riders exist, we widen the window by {{supply_widen_min}} minutes each side, then to the route-hour; if there is still none the cell says "no bus scheduled" and riders see No data. We never divide by a floor value. After the fallback, {{rider_volume_no_bus_share:.2%}} of rider volume has no bus (the gate allows {{s0_max_share:.0%}}). App riders per bus ℓ is riders divided by buses, per clean day.

### 2.6 Scaling app riders up to people on board

This is the step that matters most and the one we are least able to verify, so we describe it in full.

1. **Operator scale E.** Published daily ridership divided by app passengers resolved per clean day: **{{e_dtc:.1f}}** for DTC and **{{e_dimts:.1f}}** for the cluster operator. One citywide factor would be wrong: app use differs by operator and by route, so a single factor would put some routes far above what a bus can hold.
2. **Capacity bound per route.** B = a route's crush load divided by the {{bound_percentile_pct}}th percentile of its weekday-peak app riders per bus, over cells with at least {{bound_min_tickets}} tickets. A route's scale is E or B, whichever is smaller; the operator's E is raised (by bisection, "water-filling") so that the totals still match published ridership. Routes where the bound binds are flagged *scaled to bus capacity (high app use)*: **{{capped_routes:,}}** routes ({{capped_routes_dtc}} DTC, {{capped_routes_dimts}} cluster).
3. **A ceiling of {{e_scale_ceiling:.0f}} times E.** Without it, thin cluster routes absorbed riders the model could not justify. With the ceiling, the operator scale reaches {{e_star_dtc:.1f}} for DTC and {{e_star_dimts:.1f}} for the cluster, the ceiling binds for both, and **{{unallocated_share_dtc:.0%}} of published DTC ridership and {{unallocated_share_dimts:.0%}} of published cluster ridership is left unplaced.** We report that instead of forcing the totals to match. The ceiling was a modelling choice; 2× and 5× change {{sensitivity_ceiling_2x:.1%}} and {{sensitivity_ceiling_5x:.1%}} of levels.
4. **People on board** L = route scale × ℓ, shown as a range that combines the sampling error (day-to-day variation) and the scale uncertainty ({{scale_low:.1f}}–{{scale_high:.1f}} times the route scale, upper end capped at B). Displayed people on board are capped at the crush load, with a flag *full: real demand is likely higher*.

What the caps mean: on capped routes the crowding we show is a **conservative, lower estimate**. We may under-call a crowded bus; the design avoids the opposite error.

### 2.7 Levels and evidence

Levels use each route's bus mix (seats, rated total, crush; Appendix B). *Usually seats*: L below {{seats_fraction:.0%}} of seats, because reserved seats are rarely free. *Usually standing*: L up to the rated total. *Usually crowded*: L above the rated total. Mixed fleets use share-weighted thresholds.

Every cell also carries an evidence state:
- **Based on many tickets:** the level is the same across the whole range.
- **Rough guess:** the range spans two levels, or the route is flagged *low app use* (app riders per scheduled trip below {{low_app_use_fraction:.0%}} of the shared-stretch median). A quiet count on a route that does sell app tickets is evidence of a quiet bus, so *Usually seats* is allowed as a rough guess.
- **No data:** the route's app riders per scheduled trip are below the network {{no_data_percentile_pct}}th percentile, or no bus is scheduled. It is never shown as comfortable.

There is no shrinkage and no bunching factor: sparse cells are handled by the wider windows and these rules.

### 2.8 The planner

A frequency-based round search suits buses that run to headways, not timetables; waits are half the headway from buses that really ran. The planner returns three roles:

- **Fastest.**
- **Less crowded:** within the larger of {{less_crowded_slack_min}} minutes or {{less_crowded_slack_share:.0%}} of the fastest, with the fewest minutes crowded and then standing, using the upper end of the range. Not offered if more than half of it is No data, or if its advantage rests on legs flagged *low app use*.
- **Leave later** (+{{leave_later_first}} to +{{leave_later_last}} minutes): offered only if the later trip's whole range is in a better level and the route still runs.

The **headline** level is the worst level the rider spends at least {{headline_min_minutes}} minutes in, with the crowded stretch named. If more than {{no_data_cutoff:.0%}} of the ride is No data, the headline is *No data* (it is never *Usually seats* over a mostly unknown ride). Routes with fewer than {{min_daily_trips}} scheduled trips a day are timetable-only and are not used by the planner (they remain in all tables and in the operator view). Before {{night_end_h}}:00 and after {{night_start_h}}:00 options are marked "timetable uncertain".

### 2.9 The operator view

For each route-direction and departure window, we walk one extra bus down its route at the times it reaches each stretch (buses become S + 1), and count the riders whose level improves and the *crowded rider-minutes* removed. Weekdays and weekends are ranked separately. On weekdays the best single extra trip for DTC is route **{{operator_top_dtc_route}} at {{operator_top_dtc_departs}}**, removing about {{operator_top_dtc_crowded_minutes:,.0f}} crowded rider-minutes and moving about {{operator_top_dtc_riders_moved:,.0f}} riders down a level; for the cluster it is **{{operator_top_dimts_route}} at {{operator_top_dimts_departs}}** ({{operator_top_dimts_crowded_minutes:,.0f}} and {{operator_top_dimts_riders_moved:,.0f}}). These are model estimates scaled from app tickets, not counts.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/how-it-works-dark.svg">
    <img src="assets/how-it-works.svg" alt="One ticket becomes a crowding level in five steps" width="900">
  </picture>
</p>

---

## 3. Assumptions

Every constant below lives in code, mostly in [`src/pipeline/config.py`](../src/pipeline/config.py), with its source. The last column is from the sensitivity runs in 6.5 (share of commuter-facing cells whose level changes).

| Assumption | Value | Where | Why | If it is wrong |
|---|---|---|---|---|
| 12 m AC bus: seats / rated total / crush | {{seats_12m_ac}} / {{rated_12m_ac}} / {{crush_12m_ac}} | `BUS_SPECS` | DTC e-bus tender and CESL tender (seats); Tata and Switch data sheets (rated total); DTC tenders "peak loading of over 100" (crush) | Capacity ±10%: {{sensitivity_capacity_minus_10:.1%}} / {{sensitivity_capacity_plus_10:.1%}} of cells |
| 9 m DEVI bus | {{seats_9m_devi}} / {{rated_9m_devi}} / {{crush_9m_devi}} | `BUS_SPECS` | Press reports of the DEVI order (23 seated, 13 standing); highest stated 9 m capacity | As above |
| 12 m non-AC CNG bus | {{seats_12m_nonac}} / {{rated_12m_nonac}} / {{crush_12m_nonac}} | `BUS_SPECS` | The seat figure has the weakest source | As above |
| "Comfortable capacity" alternative | 12 m {{comfortable_12m_ac}}, 9 m {{comfortable_9m_devi}} | `BUS_SPECS` | Seats plus four standees per m², the CESL off-peak cap | {{sensitivity_comfortable:.1%}} of cells |
| *Usually seats* below this share of seats | {{seats_fraction:.0%}} | `SEATS_FRACTION` | Reserved seats are rarely free | Not varied |
| Scale range around a route's scale | {{scale_low:.1f}}–{{scale_high:.1f}} × | `SCALE_RANGE` | Honest width for the scale uncertainty | E −30% / +30%: {{sensitivity_e_minus_30:.1%}} / {{sensitivity_e_plus_30:.1%}} |
| Capacity bound | {{bound_percentile_pct}}th percentile, cells with {{bound_min_tickets}}+ tickets | `BOUND_PERCENTILE`, `BOUND_MIN_TICKETS` | Stops a thin route absorbing impossible loads | Bound off: **{{sensitivity_no_capacity_bound:.1%}}** |
| Operator scale ceiling | {{e_scale_ceiling:.0f}} × E | `E_SCALE_CEILING_MULT` | Stops unbounded scale on thin routes; leaves ridership unplaced | 2×: {{sensitivity_ceiling_2x:.1%}}; 5×: {{sensitivity_ceiling_5x:.1%}} |
| Load window, weekday / weekend | {{base_weekday_min}} min every {{step_weekday_min}}; {{base_weekend_min}} min every {{step_weekend_min}} | `WINDOWS` | Enough tickets per cell without blurring the peak | Not varied |
| Widen when no bus is scheduled | ±{{supply_widen_min}} min, then route-hour | `SUPPLY_WIDEN_MIN` | Never divide by a floor | Gate: under {{s0_max_share:.0%}} of volume |
| Ticket-pair ratio window | {{pair_ratio_window}} (alternative {{pair_ratio_window_alternative}}) | `PAIR_RATIO_BOUNDS` in `network.py` | Drop pairs that span two trips | DTC 18:00 factor {{dtc_factor_18h:.3f}} vs {{dtc_factor_18h_alternative_window:.3f}} |
| A trip counted as run | at least {{gps_trip_stop_share:.0%}} of stops, in order | `GPS_TRIP_STOP_SHARE` | Conservative; bus-km agrees with the published figure | Not varied |
| GPS used for a route | at least {{gps_coverage_min:.0%}} of its linked vehicles in the feed | `GPS_COVERAGE_MIN` | Avoids a share built on a few buses | Fallback chain (2.3) |
| 9 m bus rule | route starts with D-, or at least {{devi_route_share:.0%}} of vehicles that sell {{devi_vehicle_min_tickets}}+ tickets on D- routes | `DEVI_ROUTE_SHARE`, `DEVI_VEHICLE_MIN_TICKETS` | The D- routes are DEVI buses; the rest is an inference | 90%: {{sensitivity_vehicle_rule_90:.1%}} |
| Alighting correction | ratio clamped to 0.5–2.0; reverse uninformative under {{alighting_min_reverse_board}} boardings | `ALIGHTING_MIN_REVERSE_BOARD` | Corrects terminal asymmetry without erasing it | Correction off: {{sensitivity_no_alighting_correction:.1%}} |
| Low app use / No data | under {{low_app_use_fraction:.0%}} of the shared-stretch median; under the network {{no_data_percentile_pct}}th percentile | `LOW_APP_USE_FRACTION`, `NO_DATA_PERCENTILE` | Quiet is not the same as unknown | Not varied |
| Published ridership | DTC {{published_ridership_dtc:,}}, cluster {{published_ridership_dimts:,}} a day | `PUBLISHED_RIDERSHIP` | Economic Survey of Delhi 2025-26 | Scales every level; see 6.5 |
| Planner thresholds | slack {{less_crowded_slack_min}} min or {{less_crowded_slack_share:.0%}}; headline from {{headline_min_minutes}} min; No data above {{no_data_cutoff:.0%}}; routes under {{min_daily_trips}} trips a day skipped | `config.py`, `planner.py` | Planner rules, not data | Product choices |

---

## 4. The brief checklist

The Problem 2 brief names six things to handle. For each: what we did, the evidence and what risk remains.

| Item in the brief | What we did | Evidence | Remaining risk |
|---|---|---|---|
| **Running count per trip** | Not used. We estimate people on board per stretch and half hour, then divide by buses. | App tickets are about {{tickets_per_scheduled_trip:.1f}} per scheduled trip ({{tickets_per_weekday:,.0f}} a weekday for {{scheduled_trips_per_day:,}} trips), so a per-trip count would be nearly all zeros and ones. | One bus can differ from the average of its window; "usually" is the claim. |
| **Pass and free riders** | Not in app tickets. We scale app riders to published daily ridership, which we take to include them, then cap at bus capacity. | The app-share reconciliation (section 5); women's free journeys are about {{women_free_share_rough:.0%}} of published ridership, rough. | App users may ride different routes and hours from free-ride and pass users; the scale is by operator and route, not by rider type. If published ridership excludes them, buses are fuller still. |
| **Planned vs actual alighting** | A ticket gives the stop the rider paid to, not where they got off. We correct the one asymmetry we can see: terminal alightings. | Median terminal ratio {{terminal_ratio_median:.2f}}; {{terminal_routes_corrected}} routes corrected, {{terminal_moved_passengers:,.0f}} passengers moved; {{alighting_sensitive_routes}} routes flagged. | Mid-route differences are not measured. Correction off changes {{sensitivity_no_alighting_correction:.1%}} of cells. |
| **Bus size (12 m vs 9 m)** | Seats, rated total and crush by bus type, per route mix (Appendix B). | D- routes are DEVI 9 m buses ({{bus_mix_devi_name}} route rows, high confidence); {{bus_mix_vehicle_rule}} more by a vehicle rule (inference); capacity ±10% changes {{sensitivity_capacity_minus_10:.1%}} of cells. | The 12 m non-AC seat count has a weak source; the vehicle rule is an inference. |
| **Thin routes and hours** | Evidence state on every cell; wider windows; no shrinkage; No data where tickets are too few; planner skips timetable-only routes. | {{bus_km_share_many_tickets:.1%}} of bus-km rests on many tickets, {{evidence_rough_share:.0%}} is Rough guess, {{evidence_none_share:.1%}} No data; {{no_data_routes}} routes are No data. | Most of the network is a Rough guess. Two weeks apart, {{unchanged_level_share:.0%}} of cells keep their level. |
| **Simple display** | Three option cards; a word, dots and a colour for every level; Hindi for chips, roles and the headline sentence; plain evidence labels; a Why? sheet. | 16 px text, 48 px tap targets, no raw percentages shown. | Not tested with real riders. Stop names stay in English as in the timetable. |

---

## 5. Reconciling the app share

We say app tickets are about **1 in {{app_riders_one_in}}** riders, or **{{app_share_of_riders:.1%}}** of published ridership of {{published_ridership_total:,.0f}} riders a day. The hackathon pages put e-ticketing at **{{hackathon_share_low:.0%}}–{{hackathon_share_high:.0%}}** of bus tickets. Both can be true, because the two shares have different bases.

- Ours divides by *all riders* (published ridership).
- Theirs divides by *bus tickets*, and a free ride or a pass is a rider but not a ticket.
- If app tickets are {{hackathon_share_low:.0%}} of tickets while being {{app_share_of_riders:.1%}} of riders, then {{outside_ticket_base_needed_low:.0%}} of riders are outside the ticket base. At {{hackathon_share_high:.0%}} it is {{outside_ticket_base_needed_high:.0%}}.
- The Economic Survey reports {{women_free_journeys_crore:.2f}} crore free journeys by women in 2025-26 up to February. Spread over {{women_free_period_days}} days, that is about {{women_free_per_day_lakh:.1f}} lakh a day, roughly {{women_free_share_rough:.0%}} of published ridership. That sits inside the range above.

This is consistent, not proven: pass holders are counted nowhere we can see, the period end and the year of the cluster figure differ, and the free-ride number is a rough division. What matters for the product is the direction of the error. Free and pass riders are missing from the tickets, so buses can only be **fuller** than the tickets alone suggest, and every Why? sheet says so.

---

## 6. Validation and independent checks

**No field count was possible.** The team is in Pune and no on-bus count of Delhi buses is public. So none of the checks below measures how close a level is to the truth on a given bus. They test whether the model behaves the way an honest model of Delhi buses must, and where it does not, we say so. We never use the word "accuracy".

### 6.1 Checks that stop the run (gates)

| Gate | Result |
|---|---|
| Ticket conservation (raw = resolved + rejected, per route string) | pass |
| Rider-minutes in the output equal the resolved tickets' rider-minutes (limit {{conservation_tol:.1%}}) | pass; difference {{rider_minutes_gate_deviation:.3%}} |
| Rider volume with no bus after the fallback (limit {{s0_max_share:.0%}}) | pass; {{rider_volume_no_bus_share:.2%}} |
| Modelled hourly run times within {{runtime_gate_tol:.0%}} of ticket-pair run times | pass; worst {{run_time_gate_max_deviation:.1%}} |
| Time-zone invariance, schema, no NaN or infinity | pass |
| The stored result is rebuilt exactly from the inputs | {{stretch_crowding_rows:,}} of {{stretch_crowding_rows:,}} rows identical |

### 6.2 Expectations written down before the first full run

`validation/expectations.yaml` was committed before any model output existed, each item with a source. Misses are reported, not tuned away.

| Expectation | Result |
|---|---|
| Morning peak in 08–10, evening peak in 17–20 | **Hit.** Busiest hours {{am_peak_hour:02d}}:00 and {{pm_peak_hour:02d}}:00 |
| Weekend lower, flatter, with a later peak | **Hit** on all three |
| Radial routes busier inbound in the morning, outbound in the evening | **Hit.** {{radial_am_share:.1%}} and {{radial_pm_share:.1%}} of {{radial_pairs}} route pairs |
| DTC bus-km within ±20% of {{dtc_bus_km_published:,.0f}} a day | **Hit.** Model {{dtc_bus_km_model:,.0f}} (band {{dtc_bus_km_band_low:,.0f}}–{{dtc_bus_km_band_high:,.0f}}) |
| Fleet load factor inside the published {{load_factor_band_low:.2f}}–{{load_factor_band_high:.2f}} band | **Miss.** Model {{load_factor_model:.2f}} (6.4) |
| Ten researched corridors | 6.3 |
| GPS stop-time activity rises with boardings and alightings | Not built in Phase 1; not counted as a miss |

<p align="center"><img src="assets/fig-levels-by-hour.svg" alt="Share of weekday bus-km by crowding level, by hour of day" width="760"></p>

### 6.3 The corridor check, and why 10 of 10 is weak

We researched ten busy corridors without looking at our output and wrote them down: {{corridors_strong}} strong, {{corridors_moderate}} moderate, {{corridors_weak}} weak evidence. A corridor counts as a hit if at least one of its mapped stretches is in the top decile of weekday crowded rider-minutes per km in its stated peak.

By that rule: strong {{corridor_hits_strong}} of {{corridors_strong}}, moderate {{corridor_hits_moderate}} of {{corridors_moderate}}, weak {{corridor_hits_weak}} of {{corridors_weak}}, **{{corridor_hits_total}} of {{corridors_total}} in all**. **That rule turned out to be too easy.** Each corridor maps to many stretches, so picking the same number at random would already give {{corridor_hits_chance_expected:.1f}} of {{corridors_total}} hits ({{corridor_hits_chance_method}}). We keep the rule because we pre-registered it, and report two stricter readings:

- **Enrichment:** on average {{corridor_top_decile_share_mean:.1%}} of a corridor's mapped stretches are in the top decile, against {{corridor_top_decile_chance:.0%}} by chance.
- **Both ends on the corridor:** {{corridor_hits_both_ends}} of {{corridors_total}} hit.

<p align="center"><img src="assets/fig-corridor-check.svg" alt="Corridor check against its chance baseline" width="720"></p>

### 6.4 Published figures and the load-factor bracket

**Bus-km: hit.** Scheduled DTC bus-km are {{dtc_bus_km_scheduled:,.0f}} a day against {{dtc_bus_km_published:,.0f}} published, which implies that only about {{dtc_implied_rho:.0%}} of scheduled service ran. GPS measures the share that ran independently, at {{dtc_rho_effective:.0%}} (bus-km weighted), and the modelled {{dtc_bus_km_model:,.0f}} a day falls inside the band. Two separate routes to about the same share is the best evidence we have that the bus supply is roughly right.

**Load factor: miss.** Weekday passenger-km over seat-km is {{load_factor_model:.2f}} for the model as it stands (DTC {{load_factor_dtc:.2f}}, cluster {{load_factor_dimts:.2f}}), below the published {{load_factor_band_low:.2f}}–{{load_factor_band_high:.2f}}. The definitions differ (DTC computes load factor from revenue against seating capacity; the cluster figure uses another formula), so this is a rough check. Two cases bracket the published band:

| Case | Weekday load factor |
|---|---|
| Model as it stands: no bus above crush load; riders no bus can carry are left unplaced | {{load_factor_model:.2f}} |
| Capacity bound off, all published ridership placed, people on board capped at crush | {{load_factor_full_allocation_capped_at_crush:.2f}} |
| Capacity bound off, all published ridership placed, uncapped | {{load_factor_full_allocation:.2f}} |
| Published band | {{load_factor_band_low:.2f}}–{{load_factor_band_high:.2f}} |

Published ridership, the trips GPS shows ran, and a bus's crush capacity **do not fit together**: placing all published riders on the buses that ran needs more people per bus than a bus can hold. The model never exceeds crush load, so on capped routes the crowding it shows is a conservative lower estimate, and the true load factor lies between the two cases. We did not tune anything to close this gap.

<p align="center"><img src="assets/fig-load-factor-bracket.svg" alt="The model's load factor and the full-allocation load factor around the published band" width="760"></p>

### 6.5 Sensitivity: what moves the levels

Share of commuter-facing cells whose level changes when one assumption moves.

| Change | Cells whose level changes |
|---|---|
| Operator scale E down 30% | {{sensitivity_e_minus_30:.1%}} |
| Operator scale E up 30% | {{sensitivity_e_plus_30:.1%}} |
| **Capacity bound switched off** | **{{sensitivity_no_capacity_bound:.1%}}** |
| "Comfortable capacity" thresholds instead of rated totals | {{sensitivity_comfortable:.1%}} |
| Bus capacity −10% / +10% | {{sensitivity_capacity_minus_10:.1%}} / {{sensitivity_capacity_plus_10:.1%}} |
| 9 m vehicle rule at 90% instead of 50% | {{sensitivity_vehicle_rule_90:.1%}} |
| Scale ceiling 2× / 5× instead of 3× | {{sensitivity_ceiling_2x:.1%}} / {{sensitivity_ceiling_5x:.1%}} |
| Terminal alighting correction switched off | {{sensitivity_no_alighting_correction:.1%}} |

The capacity bound is the assumption that matters. Everything else moves under one cell in ten.

### 6.6 Repeatability: do two different weeks agree?

We split the weekdays into four blocks (5–9, 12–16, 21–23 and 26–30 October), rebuild the levels from each block alone, and compare two blocks at a time, weighted by riders. The word "accuracy" is not used.

| Comparison | Result |
|---|---|
| **Two different weeks, each alone** (headline) | **{{unchanged_level_share:.1%}}** of rider-weighted cells keep their level; load correlation **{{load_correlation_week_pairs:.2f}}** |
| A held-out week against the range built from the others | lands **inside our range in {{range_coverage_heldout:.1%}}** of cells |
| One week left out of the full month (secondary) | {{unchanged_level_share_leave_one_out:.1%}} unchanged; correlation {{load_correlation_leave_one_out:.2f}} |

The last row looks better but is not independent: the runs share three weeks of data. The honest figure is the first one. A range that contains the held-out week only {{range_coverage_heldout:.0%}} of the time is **not** a confidence interval, and we do not describe it as one.

**Other cross-checks.** Tickets with a vehicle number and tickets without one (two halves of the data) correlate at {{split_half_pearson:.2f}} on {{split_half_route_hours:,}} route-hours, so the missing vehicle number does not bias what the tickets say. GPS run times against the ticket clock are in 2.2.

### 6.7 What we did not validate

Choice stability for alternatives with the same origin, destination and hour is not measured. The GPS stop-time check is not built. The figures above never measure a level against a real count.

---

## 7. Coverage and the least reliable areas

Share of scheduled bus-km by level, from `coverage.csv` (both operators):

| | Usually seats | Usually standing | Usually crowded | No data |
|---|---|---|---|---|
| Weekday 08:00–11:00 | {{weekday_0811_seats_share:.1%}} | {{weekday_0811_standing_share:.1%}} | {{weekday_0811_crowded_share:.1%}} | {{weekday_0811_no_data_share:.1%}} |
| Weekday 11:00–17:00 | {{weekday_1117_seats_share:.1%}} | {{weekday_1117_standing_share:.1%}} | {{weekday_1117_crowded_share:.1%}} | {{weekday_1117_no_data_share:.1%}} |
| Weekday 17:00–21:00 | {{weekday_1721_seats_share:.1%}} | {{weekday_1721_standing_share:.1%}} | {{weekday_1721_crowded_share:.1%}} | {{weekday_1721_no_data_share:.1%}} |
| All weekday | {{weekday_seats_share:.1%}} | {{weekday_standing_share:.1%}} | {{weekday_crowded_share:.1%}} | {{weekday_no_data_share:.1%}} |
| All weekend | {{weekend_seats_share:.1%}} | {{weekend_standing_share:.1%}} | {{weekend_crowded_share:.1%}} | {{weekend_no_data_share:.1%}} |

{{bus_km_share_commuter_facing:.1%}} of scheduled bus-km has a level riders can see; **{{bus_km_share_many_tickets:.1%}} rests on many tickets, {{evidence_rough_share:.1%}} is a Rough guess and {{evidence_none_share:.1%}} is No data.**

**Where to trust it least**, with the number for each:

1. **Anywhere with few tickets.** Rough guess is the common case, not the exception. Weekends are thinner than weekdays.
2. **Routes the capacity bound caps:** {{capped_routes:,}} routes. Their crowding is a lower estimate; {{unallocated_share_dtc:.0%}} of DTC and {{unallocated_share_dimts:.0%}} of cluster published ridership is unplaced, so cluster loads are, if anything, understated.
3. **Terminal-end stretches** of the {{alighting_sensitive_routes}} alighting-sensitive routes (last {{alighting_last_stretches}} stretches).
4. **No-data routes:** {{no_data_routes}} routes fall below the network's {{no_data_percentile_pct}}th percentile of app riders per scheduled trip.
5. **Unresolved tickets:** {{tickets_rejected:,}} tickets ({{match_rate:.1%}} resolved overall); {{low_resolution_route_strings}} route strings with at least 50 tickets resolve under 80% and hold {{low_resolution_ticket_share:.1%}} of all tickets.
6. **Special services:** {{service_class_office_special}} office-special, {{service_class_school}} school and {{service_class_daf}} DAF routes run on their own pattern; the planner treats them with the rest of the network and the operator view flags them.
7. **Bus type:** {{bus_mix_vehicle_rule}} route rows get their 9 m status by inference from vehicles.
8. **Hours.** Before {{night_end_h}}:00 and after {{night_start_h}}:00 timetables are uncertain and we mark the options so.
9. **Where GPS has no say.** GPS covers {{gps_routes_covered:,}} of {{gps_routes_total:,}} routes; {{rho_fallback_bus_km_share:.0%}} of weekday bus-km uses a fallback share of trips that ran.
10. **One month.** October 2026 includes Navratri, Dussehra and the run-up to Diwali.

---

## 8. Phase 2

What we would do with more time, in order of how much it would change the answer:

1. **Replace the scale assumption with a measurement.** A small on-bus count on a few corridors, with the transport department's help, would turn the unverifiable step (2.6) into a calibrated one.
2. **More months of tickets**, so more cells move from Rough guess to many tickets and seasonal effects can be separated.
3. **Link a ticket to its exact trip with GPS stop times** (the stop-time check we designed and did not build), to replace the share-that-ran estimate with a per-trip one and to settle which clock, ticket or GPS, is right.
4. **Use free-ride and pass counts** if the operator can share them by route, to scale by rider type.
5. **Live arrivals and live load per bus**, so levels become "now" as well as "usually".
6. **Full Hindi stop search** and user testing with real riders.
7. **A hosted service** that can serve many riders at once, in place of the free static demo.

---

## Appendix

### A. Tickets that did not resolve

| Reason | Tickets |
|---|---|
| Stop name matched no stop on the route | {{rejected_unmatched_stop:,}} |
| Route string matched no route | {{rejected_unmatched_route:,}} |
| Alighting stop before boarding stop (reversed) | {{rejected_reversed:,}} |
| Two stops equally likely (ambiguous) | {{rejected_ambiguous_stop:,}} |
| Boarding and alighting stop the same | {{rejected_same_stop:,}} |
| **Total rejected** | **{{tickets_rejected:,}}** |

### B. Bus specifications

| Bus | Seats | Rated total | Crush | Comfortable |
|---|---|---|---|---|
| 12 m AC (electric or CNG) | {{seats_12m_ac}} | {{rated_12m_ac}} | {{crush_12m_ac}} | {{comfortable_12m_ac}} |
| 9 m DEVI | {{seats_9m_devi}} | {{rated_9m_devi}} | {{crush_9m_devi}} | {{comfortable_9m_devi}} |
| 12 m non-AC CNG | {{seats_12m_nonac}} | {{rated_12m_nonac}} | {{crush_12m_nonac}} | {{comfortable_12m_nonac}} |

Route bus mix is decided by: DEVI route name ({{bus_mix_devi_name}} route rows); the vehicle rule ({{bus_mix_vehicle_rule}}); the bus's AC flag in tickets ({{bus_mix_is_ac}}); otherwise the default ({{bus_mix_default}}).

### C. Glossary

- **Stretch.** The road between two consecutive stops of a route.
- **Window.** A centred {{base_weekday_min}}-minute span, reported every {{step_weekday_min}} minutes on weekdays.
- **People on board (L).** Estimated people on a bus on a stretch in a window, with a range.
- **Rated total.** Seats plus the standing places a bus is rated to carry. **Crush load** is the most it can physically hold.
- **Crowded rider-minutes.** Riders on Usually-crowded cells times the minutes they spend there.
- **Evidence state.** *Based on many tickets*, *Rough guess* or *No data*.

### D. Reproduce

```bash
git clone https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner && cd Delhi-Bus-Crowd-Planner
uv venv --python 3.12 && source .venv/bin/activate && uv pip install -r requirements.lock
# put October-Delhi.csv in data/raw/ and the GTFS folder in data/raw/gtfs/
python -m src.pipeline.run        # resumable; the last stage renders this note
python -m pytest
```

### E. Sources

- Economic Survey of Delhi 2025-26, chapter 12 (transport): <https://delhiplanning.delhi.gov.in/sites/default/files/Planning/12_chapter_12_transport.pdf>
- CAG, Performance audit of DTC, Report 4 of 2024.
- DTC e-bus tender (cl. 28.2), CESL tender, JBM Ecolife release, PTI report on DEVI buses (seats and capacities).
- Transport Stack hackathon pages and Problem 2 brief: <https://delhi.transportstack.in/hackathon/>

<sub>**Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.** Aggregates only: no ticket-level or vehicle-level data is published.</sub>
