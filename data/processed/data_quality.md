# Data quality

Every table here is read from the pipeline's own tables (`dq_*` and the tables they describe).

## Clean

2,559,899 tickets and 2,753,606 passengers on 31 dates; 48.5% of tickets carry no vehicle number. Excluded dates: 2 and 20 October; excluded windows are cut from every rider count.

| Date | Tickets | Passengers | No vehicle | AC passengers | Non-AC passengers |
|---|---|---|---|---|---|
| 2026-10-01 00:00:00 | 95,155 | 101,171 | 52.0% | 78,249 | 22,922 |
| 2026-10-02 00:00:00 | 41,016 | 45,706 | 47.4% | 35,456 | 10,250 |
| 2026-10-03 00:00:00 | 75,708 | 80,911 | 49.5% | 62,279 | 18,632 |
| 2026-10-04 00:00:00 | 46,622 | 51,831 | 47.4% | 40,077 | 11,754 |
| 2026-10-05 00:00:00 | 99,517 | 106,379 | 51.0% | 83,364 | 23,015 |
| 2026-10-06 00:00:00 | 81,592 | 87,481 | 50.8% | 67,852 | 19,629 |
| 2026-10-07 00:00:00 | 100,385 | 107,503 | 50.8% | 84,119 | 23,384 |
| 2026-10-08 00:00:00 | 102,219 | 109,330 | 50.7% | 85,095 | 24,235 |
| 2026-10-09 00:00:00 | 100,032 | 107,190 | 50.9% | 88,206 | 18,984 |
| 2026-10-10 00:00:00 | 67,249 | 72,796 | 47.6% | 63,067 | 9,729 |
| 2026-10-11 00:00:00 | 45,057 | 50,789 | 46.8% | 44,787 | 6,002 |
| 2026-10-12 00:00:00 | 94,588 | 101,195 | 51.1% | 87,391 | 13,804 |
| 2026-10-13 00:00:00 | 101,697 | 108,557 | 51.2% | 89,406 | 19,151 |
| 2026-10-14 00:00:00 | 101,540 | 108,424 | 50.8% | 89,096 | 19,328 |
| 2026-10-15 00:00:00 | 99,848 | 106,390 | 50.3% | 86,166 | 20,224 |
| 2026-10-16 00:00:00 | 98,503 | 105,481 | 50.7% | 89,499 | 15,982 |
| 2026-10-17 00:00:00 | 68,836 | 74,273 | 35.0% | 60,150 | 14,123 |
| 2026-10-18 00:00:00 | 35,009 | 40,103 | 14.8% | 31,809 | 8,294 |
| 2026-10-19 00:00:00 | 74,801 | 80,945 | 38.2% | 64,269 | 16,676 |
| 2026-10-20 00:00:00 | 49,375 | 56,102 | 43.7% | 44,605 | 11,497 |
| 2026-10-21 00:00:00 | 93,657 | 99,884 | 49.2% | 79,938 | 19,946 |
| 2026-10-22 00:00:00 | 95,860 | 102,021 | 49.2% | 81,502 | 20,519 |
| 2026-10-23 00:00:00 | 95,559 | 101,861 | 49.5% | 81,613 | 20,248 |
| 2026-10-24 00:00:00 | 81,046 | 87,457 | 47.5% | 69,495 | 17,962 |
| 2026-10-25 00:00:00 | 50,161 | 56,767 | 45.2% | 44,947 | 11,820 |
| 2026-10-26 00:00:00 | 92,632 | 99,114 | 49.5% | 80,290 | 18,824 |
| 2026-10-27 00:00:00 | 102,746 | 109,569 | 50.2% | 87,691 | 21,878 |
| 2026-10-28 00:00:00 | 100,879 | 107,517 | 50.0% | 86,176 | 21,341 |
| 2026-10-29 00:00:00 | 92,529 | 98,342 | 50.5% | 77,642 | 20,700 |
| 2026-10-30 00:00:00 | 91,896 | 97,699 | 49.9% | 76,984 | 20,715 |
| 2026-10-31 00:00:00 | 84,185 | 90,818 | 48.3% | 71,700 | 19,118 |

## Resolve

2,559,899 clean tickets = 2,420,185 resolved + 139,714 rejected (match rate 94.5%).

| Rejected because | Tickets | Passengers |
|---|---|---|
| unmatched_stop | 62,309 | 67,406 |
| unmatched_route | 36,819 | 39,639 |
| reversed | 20,604 | 22,253 |
| ambiguous_stop | 16,245 | 17,109 |
| same_stop | 3,737 | 4,063 |

## Network

Bus mix basis (routes):

| Basis | Routes |
|---|---|
| default | 719 |
| devi_name | 302 |
| is_ac | 1,331 |
| vehicle_rule | 222 |

Service class (routes):

| Class | Routes |
|---|---|
| daf | 44 |
| office_special | 127 |
| regular | 2,338 |
| school | 65 |

Other:

| Name | Value |
|---|---|
| places | 4,404 |
| place_stops | 6,862 |
| shapes_with_gtfs_shape | 2,574 |
| shapes_routes | 2,574 |

Travel-time clock:

| Name | Value |
|---|---|
| pairs | 206,984 |
| fallback_cells | 4.0000 |
| gate_cells | 40 |
| gate_max_dev | 0.0614 |
| passings | 2,737,136 |

Ticket-pair ratio window 0.4-2.5 (206,984 pairs); with 0.25-4 there would be 215,733 pairs and the largest operator-hour factor changes by 110.3%.

## Riders

| Name | Value |
|---|---|
| ticket_rm | 68,180,890 |
| excluded_rm | 5,281,701 |
| moved_rm | 1,850,773 |
| expanded_rm | 68,167,099 |

Rider-minute gate deviation: 0.0202% (limit 0.5%).

## Levels

| Name | Value |
|---|---|
| rows | 3,384,288 |
| capped_routes | 1,155 |
| s0_widened_share | 0.0169 |
| s0_mismatch_share | 0.0072 |
| dropped_rider_share | 0.0001 |
| corridor_pairs | 13,582 |
| no_data_routes | 603 |
| e_op_DTC | 34.8097 |
| e_op_DIMTS | 77.1806 |
| e_star_DTC | 69.8739 |
| e_star_DIMTS | 232 |
| DTC_e_op | 34.8097 |
| DTC_e_star | 69.8739 |
| DTC_ceiling | 104 |
| DTC_ceiling_bound | 0.0000 |
| DTC_capped_routes | 746 |
| DTC_unallocated_share | 0.0000 |
| DIMTS_e_op | 77.1806 |
| DIMTS_e_star | 232 |
| DIMTS_ceiling | 232 |
| DIMTS_ceiling_bound | 1.0000 |
| DIMTS_capped_routes | 409 |
| DIMTS_unallocated_share | 0.5003 |

The E* ceiling is 3 x E_op. DTC: ceiling does not bind, unallocated 0.0%. Cluster: ceiling binds, unallocated 50.0% of published ridership.
