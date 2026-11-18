# Validation report

This is a check of the model against things we can compare it with. No field count was possible, so none of it measures how close a level is to the truth on a given bus. Every figure below is computed by `src/pipeline/validate.py` from the same tables the app reads; misses are reported as misses.

## Headline

- Tickets: 2,559,899 clean, 94.5% resolved to a route and stops (94.5% of passengers).
- Scale from app passengers to people: E = 34.81 for DTC and 77.18 for the cluster operator (published ridership / resolved app passengers per clean day).
- Route capacity bound: 1155 routes are scaled to bus capacity (746 DTC, 409 cluster).
- Scale ceiling: the operator scale may not exceed 3 times E. For DTC the ceiling does not bind; the unallocated share of published DTC ridership is 0.0%. For the cluster operator the ceiling binds and 50.0% of its published ridership is unallocated: the model places only the rest on routes, so cluster loads are, if anything, understated.
- Ticket-pair run-time window: observed / template ratios from 0.4-2.5 are used. With the wider 0.25-4 window the DTC 18:00 factor is 1.521 instead of 1.423 (08:00: 1.033 instead of 1.003).
- Week to week: 74.3% of commuter-facing cells (rider-weighted) keep their level between two different weeks of the month; load correlation 0.713. A week held out lands inside the sampling range in 62.2% of cells. Secondary, not independent (the runs share three weeks): dropping one week from the full month leaves 94.2% unchanged.
- Pre-registered corridors: 2 of 2 strong, 4 of 4 moderate, 4 of 4 weak; the primary rule's result, 10 of 10 in all), but that rule turned out to be weak: 10.0 of 10 hits would be expected if the same number of stretches per corridor were drawn at random (seeded simulation, 2000 draws per corridor, seed 25, stretches drawn without replacement from the 13,181 weekday stretches with service). The informative readings are the enrichment (on average 17.9% of mapped stretches are in the top decile, against 10% at random) and the stricter both-ends mapping (6 of 10).
- Published figures: modelled DTC bus-km 1,147,445 per day against 501,000 (miss; the schedule offers 2.29 times the published figure, an implied rho of 0.44); modelled load factor 0.493 against the 0.78-0.89 band (miss).
- Scheduled DTC bus-km is 2.29 times the published figure (implied share of trips run about 0.44 if the published figure is right); until GPS-based trip counts are in, loads may be understated. The model figure counts each scheduled trip's segments once, on the feed's single service day, the same per-day basis as the published figure.
- Routes whose last stretches depend on the alighting correction: 662.
- Coverage: 93.2% of scheduled bus-km has a commuter-facing level, 4.0% rests on many tickets.
- GPS layer: not available, so bus supply uses the schedule (rho = 1) and the GPS checks are marked not available; they are not counted as misses.
- Run time of the validation stage: 40 s.

## A. Gates (a failure stops the run)

| Gate | Result | Value | Rule |
|---|---|---|---|
| ticket_conservation | pass |  | raw = resolved + rejected per route string, each ticket exactly once |
| rider_minutes | pass | 0.0202% | stretch rider-minutes + excluded + moved = resolved-ticket rider-minutes |
| supply | pass | 0.7248% | rider volume with no scheduled bus after the fallback stays under 1% |
| run_times | pass | 6.1417% | modelled hourly run times within 15% of ticket-pair run times |
| time_zone | pass |  | fixture tests (tests/test_clean.py, tests/test_config.py, tests/test_loads_riders.py) pin every operation to Asia/Kolkata |
| schema | pass |  |  |
| finite | pass |  | no NaN or inf in people_mid/low/high or E_r |

The rebuilt base case equals the stored output: 3,384,288 of 3,384,288 rows, levels and evidence identical (yes).

## B. Expectations written down before the first full run

| Expectation | Result | Detail |
|---|---|---|
| AM peak in 08-10 | hit | busiest morning hour 09:00 |
| PM peak in 17-20 | hit | busiest evening hour 19:00 |
| Weekend lower | hit | 5,059,448 vs 23,792,348 crowded rider-minutes per day |
| Weekend flatter | hit | peak-to-mean 5.72 vs 6.25 |
| Weekend peak later | hit | weekend 10:00, weekday 09:00 |
| Radial: inbound busier in the AM | hit | 86.6% of 359 route pairs |
| Radial: outbound busier in the PM | hit | 83.8% of 359 route pairs |
| GPS stop-time activity | not available | GPS aggregates are not built yet; not counted as a miss |

### The ten researched corridors

A corridor is a hit when one of its mapped stretches is in the top decile of weekday crowded rider-minutes per km in its stated peak window. A stretch is mapped when either end's stop name is in the corridor's list (and, where a direction is stated, it heads that way); both-ends is shown as a stricter reading. With this many mapped stretches a hit is likely even by chance, so the share of mapped stretches in the top decile (10% would be chance) and the chance of a hit are shown too.

The primary rule turned out to be weak: 10.0 of 10 hits are expected at random (seeded simulation, 2000 draws per corridor, seed 25, stretches drawn without replacement from the 13,181 weekday stretches with service). The informative readings are the enrichment (17.9% of mapped stretches in the top decile vs 10% at random) and the both-ends mapping (6 of 10).

| Grade | Corridor | Peak | Mapped stretches | Result | Both ends only | Mapped stretches in top decile | Chance of a hit at random | Strongest mapped stretch | Its percentile |
|---|---|---|---|---|---|---|---|---|---|
| strong | Ambedkar Nagar/Khanpur – Chirag Delhi – Moolchand – Mathura Road – ITO | am | 147 | hit | miss | 13.7% | 100.0% | Sheikh Sarai Phase II / Shaheed Bhagat Singh College to Chirag Delhi | 99.5% |
| strong | ITO/Mandi House – Vikas Marg – Laxmi Nagar – Preet Vihar – Karkardooma | pm | 49 | hit | hit | 37.8% | 98.0% | ITO AGCR /  ITO to Delhi Secretariat | 100.0% |
| moderate | Ring Road (Mudrika / Teevra Mudrika loop), including TRIPP's Moolchand | am/pm | 215 | hit | hit | 15.3% | 100.0% | Dhaula Kuan (Ring Road) to R R Lines | 99.8% |
| moderate | Mehrauli–Badarpur (MB) Road: Saket – Khanpur – Sangam Vihar/Hamdard Na | am | 91 | hit | hit | 18.2% | 100.0% | Asian Market to Saket Crossing | 100.0% |
| moderate | Outer Ring Road (Outer/Bahri Mudrika), especially Nehru Place – IIT –  | pm | 147 | hit | miss | 16.8% | 100.0% | Madhuban Chowk Outer Ring Road to Saraswati  Vihar C Block | 99.1% |
| moderate | Mathura Road: Ashram – Sarita Vihar – Badarpur Border | am/pm | 53 | hit | hit | 26.0% | 99.6% | Sarita Vihar to Madanpur Khadar Crossing | 99.7% |
| weak | North-East Delhi: Wazirabad Road / Pusta Road (Khajuri Khas – Bhajanpu | am/pm | 87 | hit | hit | 11.3% | 100.0% | Shastri Park GT Road to Shyam Giri Mandir | 98.6% |
| weak | GT Karnal Road / GT Road north: Narela – Alipur – Mukarba Chowk – Jaha | am/pm | 152 | hit | hit | 10.9% | 100.0% | Libas Pur GT Road to Swaroop Nagar GT Road | 99.8% |
| weak | Najafgarh Road: Najafgarh – Dwarka Mor – Uttam Nagar – Janakpuri – Til | am/pm | 124 | hit | miss | 10.9% | 100.0% | Karol Bagh Terminal to Jhandewalan | 99.6% |
| weak | Rohtak Road: Tikri Border – Mundka – Nangloi – Peeragarhi – Madipur –  | am/pm | 116 | hit | miss | 18.3% | 100.0% | Madipur Village / CARI / P B Enclave to Madipur JJ Colony / MadiPur Metro Station | 100.0% |

Hits by grade: strong 2/2, moderate 4/4, weak 4/4.

## C. Week-to-week repeatability

Leave-one-out: levels are recomputed from the other weekday blocks (T). Week pairs: each block alone (H) is compared with another block alone, which is the independent week-to-week test. Weekend days stay in every run so the operator scale has the same basis. Cells are weekday commuter-facing cells present in both runs; rider-weighted by full-month app riders.

| Comparison | Cells unchanged (rider-weighted) | Cells unchanged (plain) | Load correlation |
|---|---|---|---|
| Two weeks, each alone (mean of week pairs) | 74.3% | 78.2% | 0.713 |
| One week left out vs the full month (mean) | 94.2% | 95.4% | 0.972 |
| Two leave-one-out runs against each other (mean) | 92.0% |  |  |

By week pair (each week alone):

| Pair | Cells | Unchanged (rider-weighted) | Load correlation |
|---|---|---|---|
| 5-9 Oct vs 12-16 Oct | 1,907,114 | 76.4% | 0.740 |
| 5-9 Oct vs 21-23 Oct | 1,897,586 | 71.6% | 0.678 |
| 5-9 Oct vs 26-30 Oct | 1,906,637 | 75.0% | 0.718 |
| 12-16 Oct vs 21-23 Oct | 1,899,479 | 72.6% | 0.684 |
| 12-16 Oct vs 26-30 Oct | 1,909,687 | 76.8% | 0.753 |
| 21-23 Oct vs 26-30 Oct | 1,907,486 | 73.4% | 0.705 |

By ticket band (cell tickets over the full month, mean of week pairs):

| Tickets in cell | Cells | Unchanged (rider-weighted) |
|---|---|---|
| 0 | 2,068,725 | 100.0% |
| 1-29 | 6,206,834 | 71.0% |
| 30-99 | 2,122,344 | 72.0% |
| 100+ | 1,030,086 | 76.3% |

Coverage of the sampling ranges: a week held out lands inside the range estimated from the other weeks in 62.2% of cells (rider-weighted). The range is not a confidence interval; the figure is reported as is.

## D. Independent checks

No field count was possible. The checks are published totals, the researched corridors above and, once the GPS layer is in, GPS stop-time activity.

| Check | Model | Published | Band | Result |
|---|---|---|---|---|
| DTC bus-km per day (scheduled x rho) | 1,147,445 | 501,000 | 400,800-601,200 | miss |
| Fleet load factor (weekday passenger-km / seat-km) | 0.493 | DTC 0.88-0.89, cluster 0.78 | 0.78-0.89 | miss |

Both are rough: definitions differ from ours. The schedule offers 2.29 times the published DTC bus-km, so only about 44% of scheduled DTC service would have run (an implied rho of 0.44). With rho = 1 every scheduled bus counts as running, which spreads the riders over more buses than ran and so understates people per bus; passenger-km per seat-km scales with 1/rho to first order (1.13 at the implied rho). The GPS layer is what sets rho from data. Bus-km uses rho = 1 (none: GPS aggregates not available, so every scheduled trip counts as run); 0 of 1,976,283 DTC passings have no segment length. Load factor: DTC 0.500, cluster 0.469, over 93.2% of weekday bus-km that has a commuter-facing level.

## E. Sensitivity

Share of commuter-facing cells (shared with the base case) whose level changes.

| Case | Cells | Changed | Changed (rider-weighted) | More crowded | Less crowded |
|---|---|---|---|---|---|
| E x 0.7 | 3,058,187 | 9.2% | 27.7% | 0 | 281,636 |
| E x 1.3 | 3,058,187 | 8.6% | 20.9% | 264,226 | 0 |
| comfortable-capacity thresholds (12 m 77/79, 9 m 32) replace the rated totals | 3,058,187 | 1.6% | 7.6% | 3,894 | 43,556 |
| bus capacity -10% | 3,058,187 | 1.9% | 1.5% | 58,402 | 0 |
| bus capacity +10% | 3,058,187 | 1.9% | 3.3% | 0 | 58,218 |
| 9 m vehicle rule at 90% instead of 50% | 3,058,187 | 0.8% | 1.5% | 9,106 | 16,766 |
| capacity bound switched off (E = operator scale on every route) | 3,058,187 | 17.2% | 38.1% | 361,241 | 166,189 |
| E* ceiling 2 x E_op instead of 3 x | 3,058,187 | 0.6% | 0.1% | 0 | 17,806 |
| E* ceiling 5 x E_op instead of 3 x | 3,058,187 | 0.8% | 0.1% | 23,670 | 0 |
| terminal alighting correction switched off | 3,058,187 | 1.1% | 2.1% | 28,981 | 5,623 |

Ceiling cases also change how much published ridership is placed:

| Case | Operator | E* | Capped routes | Unallocated ridership |
|---|---|---|---|---|
| capacity bound switched off (E = operator scale on every route) | DTC | 34.8 | 0 | 0.0% |
| capacity bound switched off (E = operator scale on every route) | DIMTS | 77.2 | 0 | 0.0% |
| E* ceiling 2 x E_op instead of 3 x | DTC | 69.6 | 745 | 0.1% |
| E* ceiling 2 x E_op instead of 3 x | DIMTS | 154.4 | 399 | 53.1% |
| E* ceiling 5 x E_op instead of 3 x | DTC | 69.9 | 746 | 0.0% |
| E* ceiling 5 x E_op instead of 3 x | DIMTS | 385.9 | 411 | 44.8% |

## F. Diagnostics (reported, not gates)

### Over-capacity

Share of weekday bus-km that is Usually crowded, and the share where people on board exceed the crush load, by operator and hour (peak hours shown).

| Operator | Hour | Usually crowded | Over crush load |
|---|---|---|---|
| DIMTS | 08:00 | 12.2% | 2.7% |
| DIMTS | 09:00 | 22.9% | 6.7% |
| DIMTS | 13:00 | 0.7% | 0.4% |
| DIMTS | 18:00 | 9.8% | 2.4% |
| DIMTS | 19:00 | 14.2% | 3.8% |
| DTC | 08:00 | 12.7% | 2.4% |
| DTC | 09:00 | 25.3% | 7.7% |
| DTC | 13:00 | 0.4% | 0.1% |
| DTC | 18:00 | 7.4% | 1.5% |
| DTC | 19:00 | 11.8% | 2.7% |

Routes with the largest over-crush share, and the suspected cause:

| Route | Operator | Cells | Over crush | Mean E | Mean buses | Suspected cause |
|---|---|---|---|---|---|---|
| 921EXTUP | DIMTS | 493 | 46.9% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |
| 763DOWN | DIMTS | 1018 | 46.6% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |
| U-SPL-01DOWN | DTC | 165 | 44.9% | 69.9 | 1.0 | office special: weekday-only service built for peak commuters |
| 763UP | DIMTS | 1093 | 40.9% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |
| 801AUP | DIMTS | 215 | 34.7% | 231.5 | 4.4 | scale factor is high on a route with many app riders per bus |
| U-SPL-20UP | DTC | 100 | 31.8% | 69.9 | 1.0 | office special: weekday-only service built for peak commuters |
| 763ADOWN | DIMTS | 493 | 31.0% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |
| 378STLUP | DIMTS | 225 | 30.6% | 231.5 | 1.7 | few scheduled buses in the window, so each carries many app riders |
| U-SPL-17UP | DTC | 225 | 30.4% | 69.9 | 1.0 | office special: weekday-only service built for peak commuters |
| 405EUP | DIMTS | 210 | 28.1% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |
| 801ADOWN | DIMTS | 242 | 27.9% | 231.5 | 4.5 | scale factor is high on a route with many app riders per bus |
| 405DUP | DIMTS | 253 | 25.7% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |
| U-SPL-21DOWN | DTC | 78 | 25.0% | 69.9 | 1.0 | office special: weekday-only service built for peak commuters |
| 763AUP | DIMTS | 524 | 21.1% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |
| 390UP | DIMTS | 683 | 21.0% | 231.5 | 1.0 | few scheduled buses in the window, so each carries many app riders |

### Level shares by hour band (share of scheduled bus-km)

| Day | Band | Usually seats | Usually standing | Usually crowded | No data |
|---|---|---|---|---|---|
| weekday | 00-05 | 83.8% | 2.8% | 1.0% | 12.4% |
| weekday | 05-08 | 77.7% | 11.8% | 1.6% | 8.9% |
| weekday | 08-11 | 49.0% | 30.7% | 16.3% | 4.0% |
| weekday | 11-17 | 82.5% | 8.5% | 0.8% | 8.2% |
| weekday | 17-21 | 66.0% | 22.4% | 7.5% | 4.2% |
| weekday | 21-24 | 76.4% | 12.0% | 2.0% | 9.6% |
| weekend | 00-05 | 83.2% | 2.9% | 1.0% | 12.9% |
| weekend | 05-08 | 83.2% | 7.0% | 0.4% | 9.4% |
| weekend | 08-11 | 64.5% | 27.9% | 3.5% | 4.1% |
| weekend | 11-17 | 83.3% | 8.0% | 0.6% | 8.2% |
| weekend | 17-21 | 78.6% | 16.1% | 1.2% | 4.1% |
| weekend | 21-24 | 79.5% | 10.5% | 0.9% | 9.1% |

### Ticket resolution

164 of 1628 route strings with at least 50 tickets resolve under 80%; they hold 150,251 tickets (5.9% of all).

### Terminal asymmetry

1012 of 1674 route directions have a known terminal alighting ratio (median 1.36, 90th percentile 2.00); 816 were corrected (145,061 passengers moved); 662 are alighting-sensitive and show Rough guess at best on their last stretches.

### Vehicle-linked vs unlinked tickets

On 14,299 weekday route-hours with at least 5 tickets in each half, the two halves correlate at 0.861 (Pearson) and 0.840 (Spearman); the hourly profile correlates at 0.997.

### Not available yet

GPS rho distribution and run-time cross-check (GPS aggregates not built); choice stability for alternatives with the same origin, destination and hour (planner not built).
