# Validation report

This is a check of the model against things we can compare it with. No field count was possible, so none of it measures how close a level is to the truth on a given bus. Every figure below is computed by `src/pipeline/validate.py` from the same tables the app reads; misses are reported as misses.

## Headline

- Tickets: 2,559,899 clean, 94.5% resolved to a route and stops (94.5% of passengers).
- Scale from app passengers to people: E = 34.81 for DTC and 77.18 for the cluster operator (published ridership / resolved app passengers per clean day).
- Route capacity bound: 1257 routes are scaled to bus capacity (847 DTC, 410 cluster).
- Scale ceiling: the operator scale may not exceed 3 times E. For DTC the ceiling binds; the unallocated share of published DTC ridership is 59.2%. For the cluster operator the ceiling binds and 73.2% of its published ridership is unallocated: the model places only the rest on routes, so cluster loads are, if anything, understated.
- Ticket-pair run-time window: observed / template ratios from 0.4-2.5 are used. With the wider 0.25-4 window the DTC 18:00 factor is 1.521 instead of 1.423 (08:00: 1.033 instead of 1.003).
- Week to week: 76.2% of commuter-facing cells (rider-weighted) keep their level between two different weeks of the month; load correlation 0.780. A week held out lands inside the sampling range in 62.6% of cells. Secondary, not independent (the runs share three weeks): dropping one week from the full month leaves 94.7% unchanged.
- Pre-registered corridors: 2 of 2 strong, 4 of 4 moderate, 4 of 4 weak; 10 of 10 in all. That primary rule turned out to be weak: 10.0 of 10 hits would be expected if the same number of stretches per corridor were drawn at random (seeded simulation, 2000 draws per corridor, seed 25, stretches drawn without replacement from the 12,603 weekday stretches with service). The informative readings are the enrichment (on average 19.0% of mapped stretches are in the top decile, against 10% at random) and the stricter both-ends mapping (7 of 10).
- Published figures: modelled DTC bus-km 496,158 per day against 501,000 (hit); modelled load factor 0.540 against the 0.78-0.89 band (miss).
- Scheduled DTC bus-km is 2.29 times the published figure (implied share of trips run about 0.44 if the published figure is right). The model applies the share of trips that ran, measured from GPS, which is 0.43 bus-km weighted for DTC. The model figure counts each scheduled trip's segments once, on the feed's single service day, the same per-day basis as the published figure.
- Routes whose last stretches depend on the alighting correction: 662.
- Coverage: 93.6% of scheduled bus-km has a commuter-facing level, 4.7% rests on many tickets.
- GPS layer: in: bus supply is scheduled buses times the share that ran (GPS, ten sample days); the stop-time corroboration is not built and is not counted as a miss.
- Run time of the validation stage: 44 s.

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
| Weekend lower | hit | 3,589,174 vs 10,054,832 crowded rider-minutes per day |
| Weekend flatter | hit | peak-to-mean 3.55 vs 5.19 |
| Weekend peak later | hit | weekend 10:00, weekday 09:00 |
| Radial: inbound busier in the AM | hit | 79.7% of 359 route pairs |
| Radial: outbound busier in the PM | hit | 78.3% of 359 route pairs |
| GPS stop-time activity | not available | the stop-time corroboration is not built; not counted as a miss |

### The ten researched corridors

A corridor is a hit when one of its mapped stretches is in the top decile of weekday crowded rider-minutes per km in its stated peak window. A stretch is mapped when either end's stop name is in the corridor's list (and, where a direction is stated, it heads that way); both-ends is shown as a stricter reading. With this many mapped stretches a hit is likely even by chance, so the share of mapped stretches in the top decile (10% would be chance) and the chance of a hit are shown too.

The primary rule turned out to be weak: 10.0 of 10 hits are expected at random (seeded simulation, 2000 draws per corridor, seed 25, stretches drawn without replacement from the 12,603 weekday stretches with service). The informative readings are the enrichment (19.0% of mapped stretches in the top decile vs 10% at random) and the both-ends mapping (7 of 10).

| Grade | Corridor | Peak | Mapped stretches | Result | Both ends only | Mapped stretches in top decile | Chance of a hit at random | Strongest mapped stretch | Its percentile |
|---|---|---|---|---|---|---|---|---|---|
| strong | Ambedkar Nagar/Khanpur – Chirag Delhi – Moolchand – Mathura Road – ITO | am | 147 | hit | miss | 8.1% | 100.0% | Pushp Vihar to Pushpa Bhawan | 98.7% |
| strong | ITO/Mandi House – Vikas Marg – Laxmi Nagar – Preet Vihar – Karkardooma | pm | 49 | hit | hit | 41.7% | 97.7% | Rainy Well to Laxmi Nagar X-ing /Shakarpur Crossing | 100.0% |
| moderate | Ring Road (Mudrika / Teevra Mudrika loop), including TRIPP's Moolchand | am/pm | 215 | hit | hit | 13.0% | 100.0% | Indira Gandhi Stadium to ITO Ring Road | 99.8% |
| moderate | Mehrauli–Badarpur (MB) Road: Saket – Khanpur – Sangam Vihar/Hamdard Na | am | 91 | hit | hit | 17.1% | 100.0% | Asian Market to Saket Crossing | 100.0% |
| moderate | Outer Ring Road (Outer/Bahri Mudrika), especially Nehru Place – IIT –  | pm | 147 | hit | hit | 22.5% | 100.0% | Saraswati Vihar C Block to Madhuban Chowk Outer Ring Road | 99.4% |
| moderate | Mathura Road: Ashram – Sarita Vihar – Badarpur Border | am/pm | 53 | hit | hit | 27.9% | 99.6% | Sarita Vihar to Madanpur Khadar Crossing | 99.6% |
| weak | North-East Delhi: Wazirabad Road / Pusta Road (Khajuri Khas – Bhajanpu | am/pm | 87 | hit | hit | 17.3% | 100.0% | Shastri Park GT Road to Shyam Giri Mandir | 99.7% |
| weak | GT Karnal Road / GT Road north: Narela – Alipur – Mukarba Chowk – Jaha | am/pm | 152 | hit | hit | 13.3% | 100.0% | Libas Pur GT Road to Sanjay Gandhi Transport Nagar | 99.7% |
| weak | Najafgarh Road: Najafgarh – Dwarka Mor – Uttam Nagar – Janakpuri – Til | am/pm | 124 | hit | miss | 11.0% | 100.0% | Moti Nagar to Moti Nagar Industrial Area | 99.5% |
| weak | Rohtak Road: Tikri Border – Mundka – Nangloi – Peeragarhi – Madipur –  | am/pm | 116 | hit | miss | 17.8% | 100.0% | Madipur JJ Colony /  Madipuri Metro Station to Madipur Village / CARI / P B Enclave | 99.9% |

Hits by grade: strong 2/2, moderate 4/4, weak 4/4.

## C. Week-to-week repeatability

Leave-one-out: levels are recomputed from the other weekday blocks (T). Week pairs: each block alone (H) is compared with another block alone, which is the independent week-to-week test. Weekend days stay in every run so the operator scale has the same basis. Cells are weekday commuter-facing cells present in both runs; rider-weighted by full-month app riders.

| Comparison | Cells unchanged (rider-weighted) | Cells unchanged (plain) | Load correlation |
|---|---|---|---|
| Two weeks, each alone (mean of week pairs) | 76.2% | 77.9% | 0.780 |
| One week left out vs the full month (mean) | 94.7% | 94.5% | 0.962 |
| Two leave-one-out runs against each other (mean) | 92.6% |  |  |

By week pair (each week alone):

| Pair | Cells | Unchanged (rider-weighted) | Load correlation |
|---|---|---|---|
| 5-9 Oct vs 12-16 Oct | 1,907,114 | 78.4% | 0.810 |
| 5-9 Oct vs 21-23 Oct | 1,897,586 | 73.8% | 0.742 |
| 5-9 Oct vs 26-30 Oct | 1,906,637 | 77.3% | 0.799 |
| 12-16 Oct vs 21-23 Oct | 1,899,479 | 74.0% | 0.748 |
| 12-16 Oct vs 26-30 Oct | 1,909,687 | 78.2% | 0.818 |
| 21-23 Oct vs 26-30 Oct | 1,907,486 | 75.3% | 0.766 |

By ticket band (cell tickets over the full month, mean of week pairs):

| Tickets in cell | Cells | Unchanged (rider-weighted) |
|---|---|---|
| 0 | 2,068,725 | 100.0% |
| 1-29 | 6,206,834 | 73.5% |
| 30-99 | 2,122,344 | 74.0% |
| 100+ | 1,030,086 | 77.9% |

Coverage of the sampling ranges: a week held out lands inside the range estimated from the other weeks in 62.6% of cells (rider-weighted). The range is not a confidence interval; the figure is reported as is.

## D. Independent checks

No field count was possible. The checks are published totals, the researched corridors above and, once the GPS layer is in, GPS stop-time activity.

| Check | Model | Published | Band | Result |
|---|---|---|---|---|
| DTC bus-km per day (scheduled x rho) | 496,158 | 501,000 | 400,800-601,200 | hit |
| Fleet load factor (weekday passenger-km / seat-km) | 0.540 | DTC 0.88-0.89, cluster 0.78 | 0.78-0.89 | miss |

Both are rough: definitions differ from ours. The schedule offers 2.29 times the published DTC bus-km, so only about 44% of scheduled DTC service would have run (an implied rho of 0.44). With rho = 1 every scheduled bus counts as running, which spreads the riders over more buses than ran and so understates people per bus; passenger-km per seat-km scales with 1/rho to first order (0.53 at the implied rho). Bus-km uses an average rho of 0.43 (GPS: share of scheduled trips that ran, per route, hour and weekday, from ten sample days (routes without enough ticket-linked vehicles keep rho = 1)); 0 of 1,976,283 DTC passings have no segment length. Load factor: DTC 0.550, cluster 0.515, over 93.7% of weekday bus-km that has a commuter-facing level.


**Load factor bracket.** With the model as it stands (people on a bus never exceed the crush load, riders that no bus can carry are left unplaced) the weekday load factor is 0.540; with the capacity bound off and the published ridership placed in full it is 1.697 (1.070 if people on board are still capped at crush), against the published 0.78-0.89. Unallocated share of published ridership: DTC 59.2%, cluster 73.2%. Published ridership, the GPS-measured trips that ran (DTC bus-km 496,158 against the published 501,000) and the crush capacity do not fit together. The model never puts more than the crush load on a bus, so on capped routes the crowding shown is a conservative (lower) estimate; the true load factor lies between the two cases. The 80%-of-stops rule for a trip that ran is conservative; the bus-km agreement (0.43 against the implied 0.44) supports it.

## E. Sensitivity

Share of commuter-facing cells (shared with the base case) whose level changes.

| Case | Cells | Changed | Changed (rider-weighted) | More crowded | Less crowded |
|---|---|---|---|---|---|
| E x 0.7 | 3,058,187 | 9.2% | 25.2% | 0 | 282,138 |
| E x 1.3 | 3,058,187 | 8.2% | 19.0% | 251,297 | 0 |
| comfortable-capacity thresholds (12 m 77/79, 9 m 32) replace the rated totals | 3,058,187 | 1.7% | 6.8% | 3,652 | 48,936 |
| bus capacity -10% | 3,058,187 | 0.4% | 0.0% | 11,197 | 0 |
| bus capacity +10% | 3,058,187 | 0.3% | 0.0% | 0 | 10,274 |
| 9 m vehicle rule at 90% instead of 50% | 3,058,187 | 0.4% | 0.7% | 10,524 | 1,276 |
| capacity bound switched off (E = operator scale on every route) | 3,058,187 | 38.5% | 61.5% | 1,063,130 | 115,118 |
| E* ceiling 2 x E_op instead of 3 x | 3,058,187 | 1.4% | 0.2% | 0 | 43,858 |
| E* ceiling 5 x E_op instead of 3 x | 3,058,187 | 1.7% | 0.2% | 52,292 | 0 |
| terminal alighting correction switched off | 3,058,187 | 1.0% | 1.9% | 23,561 | 6,893 |

Ceiling cases also change how much published ridership is placed:

| Case | Operator | E* | Capped routes | Unallocated ridership |
|---|---|---|---|---|
| capacity bound switched off (E = operator scale on every route) | DTC | 34.8 | 0 | 0.0% |
| capacity bound switched off (E = operator scale on every route) | DIMTS | 77.2 | 0 | 0.0% |
| E* ceiling 2 x E_op instead of 3 x | DTC | 69.6 | 844 | 60.7% |
| E* ceiling 2 x E_op instead of 3 x | DIMTS | 154.4 | 409 | 75.8% |
| E* ceiling 5 x E_op instead of 3 x | DTC | 174.0 | 851 | 56.3% |
| E* ceiling 5 x E_op instead of 3 x | DIMTS | 385.9 | 412 | 67.9% |

## F. Diagnostics (reported, not gates)

### Over-capacity

Share of weekday bus-km that is Usually crowded, and the share where people on board exceed the crush load, by operator and hour (peak hours shown).

| Operator | Hour | Usually crowded | Over crush load |
|---|---|---|---|
| DIMTS | 08:00 | 11.2% | 3.0% |
| DIMTS | 09:00 | 21.7% | 5.7% |
| DIMTS | 13:00 | 2.1% | 0.9% |
| DIMTS | 18:00 | 9.2% | 2.8% |
| DIMTS | 19:00 | 15.9% | 4.9% |
| DTC | 08:00 | 7.5% | 1.4% |
| DTC | 09:00 | 18.6% | 5.5% |
| DTC | 13:00 | 2.3% | 0.9% |
| DTC | 18:00 | 7.8% | 1.9% |
| DTC | 19:00 | 17.6% | 5.2% |

Routes with the largest over-crush share, and the suspected cause:

| Route | Operator | Cells | Over crush | Mean E | Mean buses | Suspected cause |
|---|---|---|---|---|---|---|
| 17UP | DTC | 1254 | 90.6% | 104.4 | 0.1 | few scheduled buses in the window, so each carries many app riders |
| U-SPL-03DOWN | DTC | 187 | 79.8% | 104.4 | 0.5 | office special: weekday-only service built for peak commuters |
| 910AUP | DTC | 1237 | 78.1% | 104.4 | 0.0 | few scheduled buses in the window, so each carries many app riders |
| 942UP | DIMTS | 1360 | 73.4% | 231.5 | 0.1 | few scheduled buses in the window, so each carries many app riders |
| U-SPL-01UP | DTC | 120 | 73.2% | 104.4 | 0.2 | office special: weekday-only service built for peak commuters |
| 0740(NS)UP | DTC | 1488 | 70.4% | 104.4 | 0.4 | few scheduled buses in the window, so each carries many app riders |
| 172AUP | DIMTS | 471 | 68.3% | 231.5 | 0.1 | few scheduled buses in the window, so each carries many app riders |
| 921EXTUP | DIMTS | 493 | 68.2% | 231.5 | 0.4 | few scheduled buses in the window, so each carries many app riders |
| U-SPL-01DOWN | DTC | 165 | 67.8% | 104.4 | 0.5 | office special: weekday-only service built for peak commuters |
| 763UP | DIMTS | 1093 | 63.3% | 231.5 | 0.5 | few scheduled buses in the window, so each carries many app riders |
| 763AUP | DIMTS | 524 | 63.0% | 231.5 | 0.2 | few scheduled buses in the window, so each carries many app riders |
| D-040UP | DIMTS | 883 | 62.5% | 231.5 | 0.4 | few scheduled buses in the window, so each carries many app riders |
| 763DOWN | DIMTS | 1018 | 62.1% | 231.5 | 0.5 | few scheduled buses in the window, so each carries many app riders |
| 921AEXTUP | DIMTS | 323 | 61.2% | 231.5 | 0.3 | few scheduled buses in the window, so each carries many app riders |
| 512DOWN | DTC | 729 | 61.2% | 104.4 | 0.1 | few scheduled buses in the window, so each carries many app riders |

### Level shares by hour band (share of scheduled bus-km)

| Day | Band | Usually seats | Usually standing | Usually crowded | No data |
|---|---|---|---|---|---|
| weekday | 00-05 | 81.5% | 5.4% | 4.1% | 9.0% |
| weekday | 05-08 | 79.0% | 9.5% | 1.6% | 9.9% |
| weekday | 08-11 | 53.4% | 29.4% | 12.7% | 4.5% |
| weekday | 11-17 | 80.1% | 10.3% | 2.0% | 7.5% |
| weekday | 17-21 | 63.5% | 23.3% | 9.2% | 3.9% |
| weekday | 21-24 | 73.5% | 15.6% | 4.4% | 6.5% |
| weekend | 00-05 | 83.5% | 3.3% | 4.2% | 9.0% |
| weekend | 05-08 | 83.0% | 5.6% | 0.9% | 10.5% |
| weekend | 08-11 | 69.7% | 22.2% | 3.4% | 4.8% |
| weekend | 11-17 | 80.8% | 9.5% | 1.8% | 7.9% |
| weekend | 17-21 | 78.0% | 15.5% | 2.3% | 4.2% |
| weekend | 21-24 | 78.2% | 12.6% | 3.3% | 5.9% |

### Ticket resolution

164 of 1628 route strings with at least 50 tickets resolve under 80%; they hold 150,251 tickets (5.9% of all).

### Terminal asymmetry

1012 of 1674 route directions have a known terminal alighting ratio (median 1.36, 90th percentile 2.00); 816 were corrected (145,061 passengers moved); 662 are alighting-sensitive and show Rough guess at best on their last stretches.

### Vehicle-linked vs unlinked tickets

On 14,299 weekday route-hours with at least 5 tickets in each half, the two halves correlate at 0.861 (Pearson) and 0.840 (Spearman); the hourly profile correlates at 0.997.

### GPS: share of scheduled trips that ran, and run times

A trip counts as run when one vehicle passes at least 80% of the route's stops in order (positions interpolated between pings, 75 m), on ten sample days (six weekdays, four weekend days). The share is observed trips divided by scheduled trips times coverage, and is set only where at least 80% of the route's ticket-linked vehicles appear in the feed; other routes keep the schedule.

| Day type | Routes with coverage 0.8+ | Route share 10th pct | Median | 90th pct | Trip-weighted share | First / middle / last third |
|---|---|---|---|---|---|---|
| weekday | 1,733 of 2,574 (67.3%) | 0.01 | 0.42 | 0.82 | 0.38 | 0.37 / 0.48 / 0.43 |
| weekend | 1,614 of 2,574 (62.7%) | 0.03 | 0.40 | 0.80 | 0.39 | 0.38 / 0.49 / 0.46 |

Run time, GPS against the ticket-pair clock (1.00 means they agree; trip-weighted mean over route-hours, weekdays):

| Hour | 00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ratio | 1.08 | 1.08 | 1.17 | 1.02 | 1.06 | 1.16 | 1.17 | 1.19 | 1.20 | 1.16 | 1.16 | 1.13 | 1.12 | 1.16 | 1.18 | 1.15 | 1.20 | 1.24 | 1.18 | 1.12 | 1.09 | 1.08 | 1.10 | 1.09 |

### Not available yet

Choice stability for alternatives with the same origin, destination and hour (planner not built).
