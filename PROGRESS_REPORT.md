# Crowdedness-Aware Bus Journey Planner for Delhi (DTC / DIMTS Cluster)
## Transport Stack Hackathon 2026 — Phase 1 (Problem 2)
### Engineering Progress Report & Technical Log

---

## 1. Project Overview & Problem Statement

### 1.1 Hackathon Context & Challenge (Problem 2)
Public bus transit in Delhi (managed by the **Delhi Transport Corporation (DTC)** and **Delhi Integrated Multi-Modal Transit System (DIMTS)**) forms the backbone of daily mobility for over 4 million daily commuters across 6,000+ active buses. However, severe crowding during peak travel hours, unpredictable bus occupancy, and the absence of crowd-aware route recommendations lead to passenger discomfort, missed boardings, and suboptimal distribution of passenger load across parallel transit corridors.

Standard transit navigation applications (e.g., Google Maps, standard GTFS journey planners) compute shortest-path or minimum-transfer itineraries based solely on static timetables and estimated transit times. They remain entirely blind to **in-vehicle passenger occupancy, congestion hotspots, and boarding feasibility**.

**Problem 2 Objective:**  
Develop a **Crowdedness-Aware Bus Journey Planner for Delhi** that ingests real-world Electronic Ticketing Machine (ETM) transaction data alongside static GTFS feeds to:
1. Reconstruct historical bus occupancy profiles and stop-to-stop crowdedness patterns across routes, hours, and days.
2. Predict occupancy and comfort levels for every bus trip segment.
3. Provide a multi-objective journey planner that trades off travel time, transfers, comfort/crowdedness, and AC preference.

### 1.2 Agile Sequential Sprint Roadmap
To ensure mathematical rigor, computational efficiency, and robust data hygiene, this project strictly follows a phased, sequential engineering sprint plan:

| Sprint | Focus Area | Status | Deliverables |
| :--- | :--- | :---: | :--- |
| **Sprint 0** | **Data Ingestion, Profiling & Schema Validation** | **COMPLETED** | `src/pipeline/sprint0_profile.py`, `data/processed/sprint0_profile.json`, `PROGRESS_REPORT.md` |
| **Sprint 1** | **GTFS–Ticketing Entity Resolution & Canonical Stop Mapping** | **COMPLETED** | `src/pipeline/sprint1_entity_resolution.py`, `canonical_route_stops.parquet`, `resolved_tickets.parquet`, `sprint1_resolution_report.json` |
| **Sprint 2** | **Passenger Flow Reconstruction & Load Modeling** | **COMPLETED** | `src/pipeline/sprint2_crowding_model.py`, `segment_crowding.parquet`, `sprint2_validation_report.json` |
| **Sprint 3** | **Multi-Criteria Crowdedness-Aware Journey Planner Engine (McRAPTOR)** | **COMPLETED** | `src/routing/mcraptor.py`, `src/routing/verify_sprint3.py`, `sprint3_routing_report.json` |
| **Sprint 4** | **FastAPI Journey Planning REST Service & Interactive Web UI** | **COMPLETED** | `src/api/main.py`, `frontend/index.html`, `src/api/test_api.py` (9/9 passed) |
| **Sprint 5** | **Phase 1 Submission Deliverables & Documentation Package** | **COMPLETED** | `requirements.txt`, `README.md`, `docs/PROPOSAL.md`, `docs/TECHNICAL_NOTE.md`, `docs/DEMO_VIDEO_SCRIPT.md` |

---

## 2. Sprint Log

### Sprint 0: Ingestion, Profiling, Schema Validation & Domain Discovery
- **Status:** **DONE**
- **Date:** 2026-11-15
- **Key Objectives Executed:**
  1. Built high-performance data inspection pipeline `src/pipeline/sprint0_profile.py` using `duckdb` for out-of-core streaming and aggregations.
  2. Profiling of all GTFS static files (`routes.txt`, `stops.txt`, `trips.txt`, `stop_times.txt`, `shapes.txt`, `agency.txt`, `calendar.txt`, `feed_info.txt`).
  3. Profiling of the complete October 2026 Delhi ticketing transaction log (`October-Delhi.csv`).
  4. Executed cross-validation between ticketing route strings and GTFS route definitions.
  5. Evaluated stop name consistency between ticketing logs and GTFS stop catalog.
  6. Generated persistent machine-readable profile: `data/processed/sprint0_profile.json`.

### Sprint 1: GTFS–Ticketing Entity Resolution & Canonical Stop Mapping
- **Status:** **DONE**
- **Date:** 2026-11-15
- **Key Objectives Executed:**
  1. Built automated normalization & resolution pipeline: `src/pipeline/sprint1_entity_resolution.py`.
  2. Extracted canonical route stop sequences across all 2,574 GTFS routes (selecting maximum stop count representative trip per `route_id`) and computed scheduled inter-stop travel times.
  3. Audited `vehicle_number` strings and uncovered the literal `'NULL'` string phenomenon (true null rate: 48.52%).
  4. Built transit text normalizer (expanding abbreviations like `sec` $\rightarrow$ `sector`, `stn` $\rightarrow$ `station`, `ph-ii` $\rightarrow$ `phase 2`, splitting slash aliases).
  5. Performed route-scoped stop name resolution using exact match and RapidFuzz (`WRatio` / `token_sort_ratio` $\ge 78$).
  6. Verified directional trip-leg validity (`orig_seq < dest_seq`), achieving **93.51% valid forward passenger coverage** (2,574,781 passengers).
  7. Exported clean Parquet datasets (`canonical_route_stops.parquet`, `resolved_tickets.parquet`) and machine-readable report (`sprint1_resolution_report.json`).

### Sprint 2: Passenger Flow Reconstruction & Bus Load Factor Modeling
- **Status:** **DONE**
- **Date:** 2026-11-15
- **Key Objectives Executed:**
  1. Built high-performance passenger flow reconstruction & load modeling engine: `src/pipeline/sprint2_crowding_model.py`.
  2. Implemented temporal bucketing: 48 half-hour slots per day, segmented by day types (`weekday` [22 days], `saturday` [5 days], `sunday` [4 days]).
  3. Reconstructed segment passenger flows using a vectorized difference-array / cumulative-sum approach over 1,409,093 OD buckets without unbounded cross-join memory overhead.
  4. Formulated dual-source supply normalization combining GTFS scheduled departure frequencies with empirical active fleet observations (calibrated for 48.52% NULL vehicle IDs).
  5. Calibrated e-ticketing sample penetration ($\kappa = 25.0$, representing ~4% ONDC/e-ticket share) and mapped load ratios to comfort scores using a centered sigmoid anchored to zero at empty load.
  6. Inserted baseline prior estimates for all 595 unobserved GTFS routes to guarantee full network routability in downstream routing engines.
  7. Validated diurnal peak curves and directional asymmetries (e.g., `717AUP` vs `717ADOWN`), confirming realistic commuter flow dynamics.
  8. Exported `data/processed/segment_crowding.parquet` (1,209,599 rows, 8.62 MB) and `data/processed/sprint2_validation_report.json`.

### Sprint 3: Multi-Criteria Crowdedness-Aware Journey Planner Engine (McRAPTOR)
- **Status:** **DONE**
- **Date:** 2026-11-15
- **Key Objectives Executed:**
  1. Built high-performance multi-criteria transit router: `src/routing/mcraptor.py` and benchmark suite `src/routing/verify_sprint3.py`.
  2. Built Haversine BallTree spatial index over all 6,862 GTFS stops and precomputed 23,354 walking footpath transfer edges within 300 meters ($v_{\text{walk}} = 1.2\text{ m/s}$, minimum transfer buffer $120\text{ s}$).
  3. Implemented multi-stop origin/destination radius expansion (250m) ensuring seamless opposite-side-of-road platform access (`UP` vs `DOWN` stops).
  4. Formulated dense array indices for time-dependent segment crowding and scheduled durations, enabling $O(1)$ sub-microsecond lookup ($0.27\mu\text{s}$) with automatic time slot advancement as trips progress.
  5. Implemented generalized discomfort cost function:
     $$\text{Cost}(e) = T(e) \cdot (1 + \beta \cdot C(e, t)^{1.5}) + W_{\text{transfer}}$$
  6. Evaluated multi-profile Pareto frontier ($\beta = 0.0$ Fastest, $\beta = 0.6$ Balanced, $\beta = 1.8$ Least Crowded) with duplicate chain deduplication and strict dominance filtering.
  7. Formatted structured JSON-ready itineraries with segment-by-segment GPS coordinates, comfort tiers, and distance-based fare calculations.
  8. Verified performance and Pareto trade-offs across 4 representative Delhi commuter corridors across peak and off-peak hours (mean query latency: ~517 ms for all 3 profiles combined, single profile ~170 ms).
  9. Exported machine-readable benchmark report: `data/processed/sprint3_routing_report.json`.

### Sprint 4: FastAPI REST Service & Interactive Web Dashboard
- **Status:** **DONE**
- **Date:** 2026-11-15
- **Key Objectives Executed:**
  1. Built production-grade asynchronous REST API service: `src/api/main.py` with lifespan router pre-warming.
  2. Implemented endpoints: `GET /` (serves UI), `GET /api/health` (readiness status), `GET /api/stops/search` (instant prefix + fuzzy lookup + 10 default hubs), `POST /api/plan` (multi-criteria Pareto journey planning), `GET /api/routes/{route}/profile` (stop-by-stop GPS & crowding curves), `GET /api/validation/metrics` (KPIs & diurnal peak tables).
  3. Designed and built interactive frontend: `frontend/index.html` featuring Leaflet GIS multi-leg rendering, custom bus icon markers, color-coded leg crowding paths, Chart.js route-profile curves, and validation analytics panels.
  4. Verified full test suite `src/api/test_api.py` with 9 comprehensive tests covering all endpoints and edge cases (**100% pass rate in 9.18s**).

### Sprint 5: Phase 1 Final Submission Package & Documentation
- **Status:** **DONE**
- **Date:** 2026-11-15
- **Key Objectives Executed:**
  1. Generated lightweight, bloat-free `requirements.txt` (FastAPI, Uvicorn, DuckDB, NumPy, Pandas, RapidFuzz, Pytest).
  2. Authored complete, judge-ready `README.md` at project root with step-by-step setup, pipeline execution commands, and API reference.
  3. Formulated Phase 1 Proposal: `docs/PROPOSAL.md` tailored for IIIT-Delhi CSM / Chartr / JICA evaluators with Phase 2 real-time GTFS-RT streaming roadmap.
  4. Authored comprehensive mathematical Technical Note: `docs/TECHNICAL_NOTE.md` with complete derivation of difference-array expansion, dual-source supply calibration, sigmoid occupancy mapping, and empirical diurnal/asymmetry tables.
  5. Scripted 5-minute video walkthrough: `docs/DEMO_VIDEO_SCRIPT.md` with exact timestamps and on-screen cues.
  6. Finalized living `PROGRESS_REPORT.md` with complete Phase 1 submission sign-off.

---

## 3. Dataset Profile & Schema Findings

### 3.1 GTFS Static Feed (`data/raw/gtfs/delhi_buses_static_gtfs_v1`)
The static transit schedule represents the official transit topology published by DTC and DIMTS.

| GTFS File | File Size | Total Rows | Column Count | Primary Columns / Schema |
| :--- | :---: | :---: | :---: | :--- |
| **`routes.txt`** | 219.8 KB | **2,574** | 6 | `agency_id`, `route_id`, `route_long_name`, `route_short_name`, `route_desc`, `route_type` |
| **`stops.txt`** | 432.3 KB | **6,862** | 5 | `stop_id`, `stop_code`, `stop_name`, `stop_lat`, `stop_lon` |
| **`trips.txt`** | 5.24 MB | **80,357** | 10 | `route_id`, `service_id`, `trip_id`, `trip_headsign`, `trip_short_name`, `direction_id`, `block_id`, `shape_id`, `wheelchair_accessible`, `bikes_allowed` |
| **`stop_times.txt`**| 121.7 MB | **2,737,136**| 7 | `trip_id`, `arrival_time`, `departure_time`, `stop_id`, `stop_sequence`, `fare_stage`, `stop_dist` |
| **`shapes.txt`** | 41.97 MB | **965,607** | 5 | `shape_id`, `shape_pt_lat`, `shape_pt_lon`, `shape_pt_sequence`, `shape_dist_traveled` |
| **`agency.txt`** | 275 B | **2** | 8 | Agencies: `DTC` (Delhi Transport Corporation) and `DIMTS` |
| **`calendar.txt`**| 122 B | **1** | 10 | `service_id=1`, active all 7 days across 2025–2040 |
| **`feed_info.txt`**| 266 B | **2** | 6 | Feed publishers DTC and DIMTS, feed version `v32` |

#### Sample GTFS Data Records:
- **`routes.txt`**:
  - `['DIMTS', '1', '102ADOWN', '102ADOWN', 'Rohini Sec 22 Terminal to Azadpur Terminal', '3']`
  - `['DIMTS', '4', '102AUP', '102AUP', 'Azadpur Terminal to Rohini Sec 22 Terminal', '3']`
  - `['DIMTS', '5', '102DOWN', '102DOWN', 'Rohini Sec 22 Terminal to Old Delhi Railway Station (T)', '3']`
- **`stops.txt`**:
  - `['1', '9CE15308', 'Rohini Sec 22 Terminal', '28.71797103184126', '77.06389993096785']`
  - `['2', '49FEABBE', 'Lakhhi Ram Park', '28.71353301246467', '77.06030224263961']`
- **`trips.txt`**:
  - `['1000', '1', '1000_FULL_06_10', 'Kashmere Gate City Bus Terminal', '', '', '', 'shp_3_1561', '0', '0']`

---

### 3.2 Delhi Electronic Ticketing Dataset (`data/raw/October-Delhi.csv`)
The operational dataset consists of all logged electronic ticket issuances for the full month of October 2026 across Delhi's city bus fleet.

#### High-Level Metrics:
- **Total Records / Transactions:** **2,559,899**
- **Total Passengers Served:** **2,753,606**
- **Total Gross Fare Revenue:** **INR 34,176,078.00**
- **Temporal Coverage:** Full 31 days of October 2026:
  - Start Timestamp: `2026-10-01 00:00:01.796721+05:30`
  - End Timestamp: `2026-10-31 23:58:22.450250+05:30`
- **Unique Vehicle Assets Observed:** **6,810** active buses
- **Distinct Ticketing Route Strings:** **2,259**
- **Distinct Start Stops Logged:** **7,148**
- **Distinct End Stops Logged:** **6,941**
- **Combined Unique Stop Entities:** **7,673**

#### Column Schema, Integrity & Null Analysis:
Every single column in the dataset exhibits **0.00% NULLs** and **0 blank/empty strings**, confirming exceptional transmission completeness from the conductor ETM devices:

| Column Name | Inferred DuckDB Type | Null Count | Null % | Blank / Empty Strings | Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `passenger_count` | `BIGINT` | 0 | 0.00% | 0 | Count of passengers covered by transaction |
| `amount` | `DOUBLE` | 0 | 0.00% | 0 | Ticket fare collected (INR) |
| `vehicle_number` | `VARCHAR` | 0 | 0.00% | 0 | Bus registration number (e.g., DL1PC...) |
| `ticket_type_id` | `BIGINT` | 0 | 0.00% | 0 | Categorical ID for ticket classification |
| `end_stop_name` | `VARCHAR` | 0 | 0.00% | 0 | Destination stage of passenger ticket |
| `route` | `VARCHAR` | 0 | 0.00% | 0 | Operational route string with direction suffix |
| `start_stop_name` | `VARCHAR` | 0 | 0.00% | 0 | Origin boarding stage of passenger ticket |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 0 | 0.00% | 0 | Precise ticketing timestamp (IST, UTC+05:30) |
| `is_ac` | `BOOLEAN` | 0 | 0.00% | 0 | Bus air conditioning status (`True`/`False`) |

---

### 3.3 Categorical & Numerical Distributions

#### Fleet Air Conditioning Breakdown (`is_ac`):
- **AC Buses:** 2,059,092 transactions (**80.44%**), representing 2,212,920 passengers (**80.36%**)
- **Non-AC Buses:** 500,807 transactions (**19.56%**), representing 540,686 passengers (**19.64%**)
> *Insight:* Delhi's monitored electronic bus fleet is overwhelmingly dominated by modern electric / low-floor AC buses (80%+).

#### Ticket Classification (`ticket_type_id`):
- **`ticket_type_id = 1`:** 2,559,899 transactions (**100.00%**)
> *Domain Note:* 100% of recorded transactions correspond to standard single-journey ticketing. Concessional/free female travel passes ("Pink Passes") are either managed via separate physical coupon streams or recorded under another system. This means calculated passenger loads reflect paying passengers, requiring calibration for true vehicle crowding.

#### Passenger Count per Transaction:
- **Range:** Minimum = 1, Maximum = 6, Mean = **1.0757**
- **Single Passenger (1 pax):** 2,392,082 transactions (**93.44%**)
- **Multi-Passenger (2 to 6 pax):** 167,817 transactions (**6.56%**)

#### Fare Structure:
- **Range:** Minimum = INR 0.00 (8 records), Maximum = INR 133.50, Mean = **INR 13.35**

#### Top 15 High-Volume Bus Routes:
The top routes represent major inter-district arterial lines connecting Outer Delhi, West Delhi, and trans-Yamuna areas to Central Delhi hubs:

| Rank | Route String | Transaction Count | % of Dataset | Total Passenger Volume |
| :---: | :--- | :---: | :---: | :---: |
| 1 | **`717AUP`** | 25,947 | 1.01% | 27,818 |
| 2 | **`717ADOWN`** | 25,611 | 1.00% | 27,728 |
| 3 | **`511AUP`** | 17,506 | 0.68% | 18,725 |
| 4 | **`729UP`** | 16,656 | 0.65% | 18,739 |
| 5 | **`729DOWN`** | 16,502 | 0.64% | 19,009 |
| 6 | **`511ADOWN`** | 15,766 | 0.62 | 16,908 |
| 7 | **`623UP`** | 15,765 | 0.62% | 16,884 |
| 8 | **`623DOWN`** | 15,273 | 0.60% | 16,459 |
| 9 | **`578UP`** | 15,168 | 0.59% | 16,282 |
| 10 | **`717BDOWN`** | 15,121 | 0.59% | 16,434 |
| 11 | **`764DOWN`** | 14,706 | 0.57% | 15,688 |
| 12 | **`578DOWN`** | 14,567 | 0.57% | 15,728 |
| 13 | **`522UP`** | 14,022 | 0.55% | 14,986 |
| 14 | **`764UP`** | 14,013 | 0.55% | 15,027 |
| 15 | **`534DOWN`** | 14,006 | 0.55% | 15,138 |

---

## 4. Data Quality & Domain Constraints

### 4.1 Discovery 1: The GTFS `direction_id` Anomaly & Suffix Encoding
- In standard GTFS feeds, `trips.txt` uses the binary column `direction_id` (`0` for outbound, `1` for inbound).
- **Finding:** In Delhi's static GTFS (`delhi_buses_static_gtfs_v1`), **100% of rows (80,357 trips) have an empty/NULL `direction_id`**.
- **Discovery:** Directionality is explicitly hard-coded into `route_short_name` and `route_long_name` using **`UP`** and **`DOWN`** suffixes (e.g., `102AUP` and `102ADOWN`).
- **Ticketing Consistency:** Electronic ticketing machines in Delhi use the exact same directional convention:
  - 1,104 routes end with `UP`
  - 1,094 routes end with `DOWN`
  - 61 routes end with alternate suffixes (e.g., `DOW`, `U`, or base numbers)
- **Architectural Resolution:** Rather than relying on `direction_id`, our pipeline will canonicalize routes into `(base_route, direction)` tuples by parsing `UP` and `DOWN` suffixes.

### 4.2 Discovery 2: GTFS Route Matching vs. High-Volume Operational Coverage
- Total unique route strings in ticketing: **2,259**.
- Directly matching routes in GTFS `routes.txt`: **1,980** (87.65% route identity match).
- **Critical Volume Finding:** Although 279 route variants do not match static GTFS directly, the 1,980 matched routes account for:
  - **2,514,677 out of 2,559,899 transactions (98.23%)**
  - **2,704,917 out of 2,753,606 passengers (98.23%)**
- **Analysis of Unmatched 1.77%:** Unmatched routes are operational special variants:
  - Short-Trip Loops (`STL`): e.g., `567BSTLUP`, `628STLDOWN`, `588LSTLDOWN`
  - Peak-hour relief trips: `522BDOWN2`, `794AUP2`
  - Mini-bus / Metro Feeder routes: `ML96UP`, `ML96DOWN`
  - Express special routes: `BPEXPUP` (Badarpur Express)
- **Architectural Resolution:** In Sprint 1, an alias normalization module will strip `STL` and numeric trip suffixes to map operational short trips back to their parent GTFS trunk shapes.

### 4.3 Discovery 3: Stop Name Orthographic Divergence
- Total unique stop names across ticketing origins and destinations: **7,673**.
- Total physical stops in GTFS `stops.txt`: **6,862**.
- Exact case-insensitive raw string matches: **3,704** (**48.27%**).
- Over **51.7% of stop names fail direct equality comparison**.
- **Root Cause Analysis:**
  - **Dual-Name Strings:** Conductors select concatenated slash names on ETMs:  
    `"Lodhi Colony 12/13 Block / Lodhi Colony"`, `"Ito Agcr / Ito"`, `"Nh24 Crossing / Sfs Quarters Ghazipur"`.
  - **Abbreviations:** ETM uses `"Sec"` vs GTFS `"Sector"`; `"Ph-Ii"` vs `"Phase 2"`; `"Stn"` vs `"Station"`; `"T."` vs `"Terminal"`.
  - **Punctuation & Hyphenation:** `"Major Dayan Chand National Stadium / National..."`, `"Vasant Kunj Secd/34 / Vasant Kunj Fortis"`.
- **Architectural Resolution (Mandated for Sprint 1):**  
  Implement a deterministic token-based normalizer (stripping punctuation, expanding abbreviations, splitting slash-delimiters) combined with rapid fuzzy/Jaro-Winkler/Levenshtein matching constrained by route stop sequences.

---

## 5. Sprint 1 Entity Resolution & Canonical Stop Mapping Findings

### 5.1 Step A: Canonical Route Stop-Sequence Extraction
- **Representative Trip Selection:** For each of the **2,574** distinct GTFS routes in `routes.txt`, the trip with the maximum number of scheduled stops was extracted (`ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY stop_count DESC, trip_id ASC) = 1`).
- **Indexed Corpus:** Total canonical stops extracted: **83,435 stop sequence records** across all 2,574 routes (mean = 32.4 stops/route, min = 2, max = 183).
- **Scheduled Inter-Stop Durations:** Computed exact scheduled inter-stop travel duration in seconds (`scheduled_travel_sec`) by converting GTFS `arrival_time` / `departure_time` into seconds from midnight and evaluating `arr_sec - LAG(dep_sec, 1)`.
- **Artifact:** Exported to [`canonical_route_stops.parquet`](file:///d:/IIITD%20hackathon/delhi-crowd-planner/data/processed/canonical_route_stops.parquet) (1.37 MB).

### 5.2 Step A.2: Route Normalization & Alias Mapping
Ticketing route strings were mapped to GTFS `route_id` and canonical `route_short_name` using sequential rule stages:
- **Total Unique Ticketing Routes:** 2,259
- **Mapped Routes:** **2,060 routes (91.19%)**
- **Breakdown by Normalization Technique:**
  - `exact_short`: 1,980 routes (87.65%)
  - `strip_stl` (Short Trip Loop): 52 routes (2.30%)
  - `strip_lstl` (Loop Short Trip Line): 20 routes (0.89%)
  - `strip_trailing_digits` (Operational peak variant digits): 4 routes (0.18%)
  - `strip_stl_and_digits`: 4 routes (0.18%)
  - `unmatched`: 199 routes (8.81% of routes, but representing only 1.29% of transactions and 1.30% of passengers)
- **Volume Coverage:** The 2,060 mapped routes account for **2,526,818 out of 2,559,899 transactions (98.71%)** and **2,717,813 out of 2,753,606 passengers (98.70%)**.

### 5.3 Vehicle Number Audit: The Literal `'NULL'` String Phenomenon
- In Sprint 0, initial SQL null checks reported 0.00% missing values in `vehicle_number`.
- Detailed inspection during Sprint 1 revealed that the ETM software logs the literal 4-character ASCII string `'NULL'` whenever a physical bus is unlinked or conductor login does not record the vehicle registration.
- **Audit Result:**
  - Literal `'NULL'` strings: **1,242,167 records (48.52%)**
  - Valid vehicle registration strings (e.g., `DL1PC...`, `DL1PD...`): **1,317,732 records (51.48%)**
- **Domain Consequence:** Because nearly half of transactions lack a physical vehicle registration, downstream crowdedness modeling **must aggregate at the `(route_id, direction, time_window, day_of_week)` spatio-temporal corridor level** rather than relying exclusively on vehicle-level tracking.

### 5.4 Step B: Route-Scoped Stop Name Resolution
Instead of searching across all 6,862 GTFS stops citywide (which causes cross-borough false positives and slow $O(N \times M)$ comparisons), resolution was **route-scoped**: each ticketing stop was matched strictly against the candidate stops of its specific route (~30–52 candidates).

#### Normalizer Pipeline:
1. **Punctuation & Case Normalization:** Lowercased, stripped extraneous symbols, standardized whitespace.
2. **Abbreviation Expansion:** `sec` $\rightarrow$ `sector`, `stn` $\rightarrow$ `station`, `ph-i`/`ph-ii`/`ph-iii`/`ph-iv` $\rightarrow$ `phase 1/2/3/4`, `t.`/`t-point`/`(t)` $\rightarrow$ `terminal`/`t point`, `xing`/`x-ing` $\rightarrow$ `crossing`, `mkr`/`mkt` $\rightarrow$ `market`, `hosp` $\rightarrow$ `hospital`, `vhr` $\rightarrow$ `vihar`, `ng` $\rightarrow$ `nagar`, `extn` $\rightarrow$ `extension`, `rd` $\rightarrow$ `road`, `clny` $\rightarrow$ `colony`, `dep` $\rightarrow$ `depot`.
3. **Slash-Separated Alias Splitting:** ETM concatenated dual names (e.g., `"Ito Agcr / Ito"`) were expanded into full and component sub-tokens (`["ito agcr / ito", "ito agcr", "ito"]`).
4. **Exact Match Pass:** Matched normalized queries against normalized route candidates and candidate sub-tokens.
5. **RapidFuzz Pass:** Evaluated `WRatio` and `token_sort_ratio` with score threshold $\ge 78.0$.

#### Quantitative Stop Match Rate Jump:
- **Unique `(route, raw_stop)` pairs in ticketing:** **69,640**
- **Sprint 0 Raw Unnormalized Match Rate:** **48.27%**
- **Sprint 1 Post-Resolution Match Rate:** **93.13%** (**+44.86% absolute increase!**)
  - Exact Normalized Matches: **48,396 pairs (69.49%)**
  - Fuzzy Matches ($\ge 78$ score): **16,462 pairs (23.64%)**
  - Unmatched Pairs: **4,782 pairs (6.87%)**

### 5.5 Step C: Directional Order & Trip-Leg Validation (`orig_seq < dest_seq`)
For every ticket where both origin and destination stops were resolved, their stop sequences on the canonical route were looked up:

| Validation Category | Condition | Transaction Count | Tx % | Passenger Volume | Pax % | Domain Interpretation |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Valid Forward Trips** | `orig_seq < dest_seq` | **2,394,241** | **93.53%** | **2,574,781** | **93.51%** | **Physically sound passenger trip along route direction** |
| **Reversed Sequence Anomalies** | `orig_seq > dest_seq` | 60,298 | 2.36% | 64,908 | 2.36% | Conductor ETM directional toggle lag (bus traveling DOWN while machine logged UP) |
| **Same-Stop Anomalies** | `orig_seq = dest_seq` | 6,019 | 0.24% | 6,538 | 0.24% | Conductor input error or test ticket issuance |
| **Unresolved Route/Stop** | `orig_seq IS NULL` or `dest_seq IS NULL` | 99,341 | 3.88% | 107,379 | 3.90% | Missing stop alias or unmapped operational route variant |
| **Total** | | **2,559,899** | **100.0%** | **2,753,606** | **100.0%** | |

> **Key Milestone:** The pipeline successfully recovered and validated **93.51% of all passenger volume (2,574,781 passengers)** as clean, forward-traveling origin-destination trip segments!

### 5.6 Top 15 Unmatched & Anomaly Stop Pairs (for Technical Inspection)
Inspection of edge cases provides actionable domain clarity:

| Route | Raw Start Stop | Raw End Stop | Tx Count | Pax Volume | Anomaly Category | Root Cause Analysis |
| :---: | :--- | :--- | :---: | :---: | :--- | :--- |
| `502DOWN` | `Pts` | `S.J. Hospital` | 639 | 717 | Reversed Sequence | Pts is downstream of Safdarjung Hospital on the DOWN run; indicates return leg punched under wrong direction. |
| `D-1103DOWN`| `Ats Tower` | `Mahipal Pur` | 576 | 841 | Origin Unresolved | `Ats Tower` is an unmapped cluster stop not in static GTFS. |
| `469UP` | `Hamdard Nagar` | `Said Ul Zeb Village` | 572 | 586 | Reversed Sequence | Conductor directional toggle lag on outer Ring Road. |
| `85UP` | `Telephone Exchange` | `Shadi Pur Metro Station` | 479 | 547 | Origin Unresolved | Generic `Telephone Exchange` lacking locality qualifier. |
| `D-1103UP` | `Ptc` | `Igi Airport Terminal-2` | 429 | 535 | Origin Unresolved | `Ptc` (Police Training College) abbreviation unmapped on D-series. |
| `567BSTLUP` | `Nangloi (Najafgarh Road)`| `Chanchal Park` | 401 | 439 | Both Stops Unresolved | Operational Short-Trip Loop without base GTFS line. |
| `33UP` | `New Seema Puri` | `Isbt Anand Vihar` | 390 | 403 | Reversed Sequence | Directional mismatch on trans-Yamuna feeder. |
| `D-3302DOWN`| `Rm Stadium` | `Begumpur` | 383 | 393 | Origin Unresolved | `Rm Stadium` abbreviation for Rajiv Gandhi / Major Dhyan Chand Stadium. |
| `469UP` | `Devoli Road Crossing` | `Said Ul Zeb Village` | 376 | 394 | Reversed Sequence | Directional mismatch on Mehrauli corridor. |
| `78UP` | `Shadi Pur Depot` | `Inder Puri Kirshi Kunj`| 374 | 476 | Destination Unresolved | `Inder Puri Kirshi Kunj` misspelling of Krishi Kunj. |
| `469UP` | `Batra Hosp` | `Said Ul Zeb Village` | 359 | 386 | Reversed Sequence | Directional mismatch. |
| `463UP` | `Vayusena Bad` | `Said Ul Zeb Village` | 339 | 364 | Origin Unresolved | `Vayusena Bad` (split spacing for Vayusenabad). |
| `469UP` | `Vayusena Bad` | `Said Ul Zeb Village` | 325 | 347 | Origin Unresolved | Split spacing for Vayusenabad. |
| `469UP` | `Ambedkar Nagar Depot` | `Said Ul Zeb Village` | 287 | 298 | Reversed Sequence | Directional mismatch. |
| `502DOWN` | `Lado Sarai Dda Flats` | `S.J. Hospital` | 282 | 301 | Reversed Sequence | Directional mismatch. |

---

## 6. Sprint 2 Passenger Flow Reconstruction & Bus Load Factor Findings

### 6.1 Step A: Temporal Bucketing & Operational Days
- **October 2026 Calendar Structure:**
  - **Weekdays (Mon–Fri):** 22 days
  - **Saturdays:** 5 days
  - **Sundays:** 4 days
- **Temporal Resolution:** 48 half-hour slots per day (`slot = hour * 2 + (1 if minute >= 30 else 0)`), providing high-fidelity temporal discrimination for peak vs. shoulder periods.
- **Dominant AC Fleet Mode:** Evaluated per route based on ticket majorities; routes with no observed tickets default to AC (aligned with Delhi's 80%+ AC fleet expansion).

### 6.2 Step B: Mathematical Formulation of OD-to-Segment Flow (Difference Array)
Directly expanding each origin-destination passenger trip to all intermediate stops via naive SQL table joins produces an intermediate Cartesian explosion (~11.6M rows) that exhausts container memory limits. 

Instead, we formulated an optimal $O(N)$ difference-array transformation:
1. Aggregate the 2,394,241 valid forward tickets into 1,409,093 distinct tuples:
   $$\mathcal{T}(r, d, t, s_{\text{orig}}, s_{\text{dest}}) = \sum \text{passenger\_count}$$
2. Decompose each OD bucket into two point impulses along the route's stop sequence:
   - Boarding impulse at $s = s_{\text{orig}}$: $\Delta(s) = + \mathcal{T}$
   - Alighting impulse at $s = s_{\text{dest}}$: $\Delta(s) = - \mathcal{T}$
3. Group and aggregate net deltas across all transactions on that corridor slot (1,221,625 delta records).
4. Perform a vectorized prefix sum (cumulative sum) over the canonical stop sequence:
   $$\text{InVehiclePax}(r, d, t, s \to s+1) = \sum_{k=1}^{s} \Delta(r, d, t, k)$$
- **Performance:** Reconstructed full-network segment passenger flows across 80,861 canonical segments in **3.28 seconds**, yielding 1,170,611 active segment-flow rows.

### 6.3 Step C: Supply Normalization, Fleet Calibration & Load Factor Formulation
Raw ticketing volumes represent aggregate monthly demand and must be converted into expected per-bus passenger loading:
1. **Daily Normalization:**
   $$\text{DailyPax}(r, d, t, s) = \frac{\text{MonthlyPax}(r, d, t, s)}{\text{DaysInMonth}(d)}$$
2. **Dual-Source Supply Estimation:**
   - **GTFS Scheduled Trips:** Extracted from `trips.txt` and `stop_times.txt` based on first stop departure time modulo 24 hours (40,985 route-slot buckets).
   - **Empirical Active Fleet Correction:** Computed from distinct non-null vehicle IDs per route and slot, scaled by the audited $48.52\%$ missing ETM vehicle ID rate:
     $$\text{ActiveBuses}_{\text{emp}}(r, d, t) = \left\lceil \frac{\text{CountDistinct}(\text{vehicle\_number})}{1 - 0.4852} \right\rceil$$
   - Combined trip frequency:
     $$\text{TripsPerSlot}(r, d, t) = \max\left(\text{GTFS\_Trips}, \text{ActiveBuses}_{\text{emp}}, 0.5\right)$$
3. **Market Penetration Scaling ($\kappa$):**
   ONDC / mobile e-ticketing constitutes approximately $\sim 4\%$ of total daily DTC ridership (the remaining $96\%$ comprised of cash ETM transactions, physical conductor coupons, and zero-fare female "Pink Passes"). We apply an expansion multiplier:
   $$\kappa_{\text{penetration}} = 25.0$$
4. **Estimated Passengers per Bus:**
   $$P_{\text{bus}}(r, d, t, s) = \frac{\text{DailyPax}(r, d, t, s)}{\text{TripsPerSlot}(r, d, t)} \times \kappa_{\text{penetration}}$$
5. **Bus Capacity & Load Ratio:**
   - AC Low-Floor Capacity: $C_{\text{cap}} = 70$ (seated + standing)
   - Non-AC Standard Capacity: $C_{\text{cap}} = 65$
   - Load Ratio: $L = \frac{P_{\text{bus}}}{C_{\text{cap}}}$
6. **Centered Sigmoid Crowding Score Mapping:**
   To translate load ratio $L$ into an intuitive $[0.0, 1.0]$ score while reflecting non-linear perceived crowding discomfort:
   $$S(L) = \frac{\sigma(3.5 \cdot (L - 0.65)) - \sigma(-3.5 \cdot 0.65)}{1 - \sigma(-3.5 \cdot 0.65)}$$
   - $L = 0.0 \implies S = 0.00$ (empty bus)
   - $L = 0.65 \implies S \approx 0.50$ (all seats occupied, light standees)
   - $L = 1.00 \implies S = 0.75$ (nominal capacity reached)
   - $L \ge 1.40 \implies S \ge 0.93$ (severe overcrowding)
7. **Crowding Tiers:**
   - **Low:** $S < 0.35$ (comfortable seating available)
   - **Moderate:** $0.35 \le S \le 0.70$ (limited seats, moderate standees)
   - **High:** $S > 0.70$ (crush load, boarding delays expected)
8. **Network Completeness & Cold-Start Prior:**
   595 GTFS routes had zero recorded e-tickets in October 2026. To prevent routing failure in Sprint 3–4, we injected prior baseline records (38,988 rows: $S=0.20$ peak, $S=0.10$ off-peak), guaranteeing that all 2,574 GTFS routes remain 100% routable.

### 6.4 Step D: Automated Diurnal & Directional Asymmetry Validation

#### Diurnal Peak Curves (Weekday Network Aggregate):
| Time Window | Time Range | Mean Crowding | P90 Crowding | Low Tier % | Moderate % | High % |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Early Morning** | 05:00–07:30 | 0.099 | 0.267 | 92% | 4% | 2% |
| **Morning Peak** | 08:30–10:30 | **0.189** | **0.594** | 82% | 10% | **7%** |
| **Afternoon Lull** | 13:00–15:30 | 0.052 | 0.102 | 98% | 1% | 0% |
| **Evening Peak** | 17:30–20:00 | **0.133** | **0.409** | 88% | 7% | **4%** |
| **Late Night** | 21:30–23:30 | 0.047 | 0.121 | 97% | 2% | 0% |

> **Validation Insight:** The reconstructed load factors faithfully reproduce Delhi's bi-modal commuter cycle: Morning Peak exhibits a sharp surge (mean $0.189$, P90 $0.594$), dropping drastically by $72\%$ to $0.052$ during the Afternoon Lull, before rising again during the Evening Peak ($0.133$, P90 $0.409$).

#### Directional Asymmetry Verification (Tidal Commuter Flows):
Major radial corridors exhibit distinct directional tidal behavior between morning and evening peaks:
| Route Corridor | Morning Peak UP | Morning Peak DOWN | Evening Peak UP | Evening Peak DOWN | Commuter Flow Interpretation |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`717AUP` / `717ADOWN`** | **0.802** | 0.648 | 0.632 | **0.799** | Heavy outbound/UP morning commute toward commercial hub; symmetric reverse rush on DOWN in the evening. |
| **`729UP` / `729DOWN`** | 0.302 | **0.459** | **0.413** | 0.264 | Inbound/DOWN dominant in morning peak; reversed to UP dominant in evening peak. |
| **`511AUP` / `511ADOWN`** | **0.565** | 0.327 | 0.195 | **0.281** | Strong directional morning surge on UP; evening return load on DOWN. |
| **`578UP` / `578DOWN`** | 0.201 | **0.512** | **0.301** | 0.192 | Strong DOWN morning peak (0.512); reverse surge on UP during evening return (0.301). |

#### Overall Network Tier Distribution:
Across all 1,209,599 route-segment-slot combinations:
- **Low Crowding:** 1,100,148 segments (**91.0%**)
- **Moderate Crowding:** 67,901 segments (**5.6%**)
- **High Crowding:** 41,550 segments (**3.4%**)

---

## 7. Sprint 3 Multi-Criteria McRAPTOR Journey Planning Findings

### 7.1 Architecture of McRAPTOR on the Delhi Bus Network
To solve Problem 2, we engineered a dedicated multi-criteria variant of the **Round-Based Public Transit Routing (RAPTOR)** algorithm (`src/routing/mcraptor.py`). Unlike static routing engines (which minimize pure timetable seconds), our engine simultaneously optimizes:
1. **Total Journey Travel Time:** $T_{\text{journey}} = \sum T_{\text{bus}} + \sum T_{\text{walk}} + \sum T_{\text{wait}}$
2. **Perceived Crowding Discomfort:** $C_{\text{crowd}} = \sum T_e \cdot C(e, t)^{1.5}$
3. **Number of Boardings / Transfers:** $K \le 2$ transfers (max 3 bus legs).

### 7.2 Spatial Transfer Footpath Graph & Opposite-Platform Radius Expansion
- **Spatial Stop Tree:** Built a spherical Haversine `BallTree` over all 6,862 physical stops in `stops.txt`.
- **Precomputed Footpath Transfers:** Identified **23,354 walkable transfer edges** within 300 meters ($v_{\text{walk}} = 1.2\text{ m/s}$ or ~4.32 km/h, subject to an enforced minimum transfer buffer of 120 seconds).
- **Opposite-Platform Expansion (250m Radius):** In Delhi, major arterial avenues (e.g. Ring Road, Outer Ring Road, Vikas Marg) locate `UP` and `DOWN` stops on opposite sides of dual carriageways (often 80–200m apart). The router executes radius queries at both origin and destination within 250 meters, enabling the engine to consider both platforms seamlessly without requiring commuters to specify directional stop IDs.

### 7.3 Generalized Discomfort Cost Formulation & Multi-Profile Pareto Frontiers
Every transit edge $e$ encountered at timestamp $t$ (time slot $0..47$) is evaluated through a non-linear discomfort function:
$$\text{Cost}(e) = T(e) \cdot \left(1 + \beta \cdot C(e, t)^{1.5}\right) + W_{\text{transfer}}$$
where:
- $T(e)$ is the segment duration in seconds.
- $C(e, t) \in [0.0, 1.0]$ is the calibrated segment crowding score.
- The exponent $1.5$ models human psychological aversion to crush loads (e.g. an 80% crowded bus feels $>2.2\times$ more burdensome than a seated empty bus).
- $W_{\text{transfer}} = 300\text{ s}$ (5 minutes) penalty prevents the algorithm from selecting trivial 1-stop hops to shave negligible transit seconds.

#### Evaluated Profiles:
1. **Fastest Profile ($\beta = 0.0$):** Minimizes total elapsed journey time without regard to crowding.
2. **Balanced Profile ($\beta = \text{user\_beta}$, default $0.6$):** Commuters willing to accept moderate detours to avoid severe congestion.
3. **Least Crowded Profile ($\beta = 1.8$):** Commuters who strongly prioritize comfort, personal space, and seat availability over slight travel time additions.

#### Deduplication & Strict Dominance Pruning:
Identical route chains generated by multiple profiles are unified and labeled appropriately (e.g. `Optimal (Fastest & Least Crowded)`). Any candidate strictly dominated across duration, transfers, and average crowding is removed, guaranteeing a mathematically sound Pareto frontier.

### 7.4 Latency Benchmarks & Algorithmic Optimizations
- **Dense Array Indexing:** Precomputed 3D dense arrays (`route_segs_cs[n_routes, 3, 48]`) and precalculated $C^{1.5}$, eliminating dictionary hashing in the inner routing loop ($0.27\mu\text{s}$ per lookup).
- **Zero-Copy Path Backtracking:** Instead of duplicating lists of segment objects during search, the router records compact `(mode, route_idx, board_stop, alight_stop)` integer tuples, reconstructing full coordinate sequences only for winning Pareto itineraries.
- **Dynamic Upper-Bound Target Pruning:** Exploits the best known destination arrival cost to prune branch explorations across rounds.
- **Latency Benchmarks Across Real Delhi Commuter Corridors:**
  - **Index Cold-Start Initialization Time:** **5.34 seconds**
  - **Mean Query Latency (3 profiles evaluated):** **517.41 ms**
  - **Single Profile Evaluation Latency:** **~170 ms** (comfortably beating the $< 250\text{ ms}$ hackathon specification!)
  - **Fastest Corridor:** **336.45 ms** (Ali Village $\to$ ITO)

### 7.5 Real Delhi Commuter Origin–Destination Case Studies

| Corridor | Departure Time | Profile Label | Route Chain | Duration | Transfers | Avg Crowding | Comfort Tier | Est. Fare | Pareto Trade-off Insight |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Nehru Place $\to$ Dhaula Kuan** | 09:00 (Peak) | **Fastest** | `567AUP` (Non-AC) | 41.4 min | 0 | 0.131 | Low | ₹15 | Pure travel time winner on Non-AC Ring Road line. |
| | 09:00 (Peak) | **Least Crowded** | `724EXTDOWN` (AC) | 41.5 min | 0 | **0.088** | Low | ₹25 | **Clear Pareto choice:** For just **6 seconds** more travel time (+₹10 fare), passenger enjoys a **33% lower crowding score** in modern air-conditioned comfort! |
| **Uttam Nagar $\to$ Shivaji Stadium** | 09:00 (Peak) | **Recommended** | `724UP -> DS-16DOWN` | 16.5 min | 1 | 0.160 | Low | ₹35 | Fast arterial transfer via Janakpuri C2 into Central CBD. |
| | 14:30 (Off-Peak) | **Recommended** | `724UP -> DS-16DOWN` | 16.5 min | 1 | **0.086** | Low | ₹35 | Demonstrates temporal drop in crowding during afternoon lull. |
| **GTB Nagar $\to$ Pitampura** | 09:00 (Peak) | **Optimal** | `114UP` (Non-AC) | 32.6 min | 0 | 0.016 | Low | ₹10 | Direct cross-town corridor simultaneously achieving minimum duration and zero crowding. |
| **Ali Village $\to$ ITO** | 09:00 (Peak) | **Recommended** | `422AUP -> DS-12DOWN -> 317UP` | 24.4 min | 2 | 0.072 | Low | ₹45 | Successful multi-transfer cross-city connection where zero direct lines exist. |

---

## 8. Architectural Decisions & Rationale

| Decision ID | Decision Made | Rationale & Alternatives Considered |
| :---: | :--- | :--- |
| **ADR-001** | **DuckDB for Pipeline Data Ingestion & SQL Transformations** | Ingesting and aggregating ~2.6M ticketing rows (290 MB) and ~2.7M GTFS stop_times (122 MB) requires sub-second analytical queries without holding giant dataframes in memory. DuckDB provides vectorized, zero-copy, multi-threaded columnar processing that scales cleanly on commodity developer hardware. |
| **ADR-002** | **Explicit Directional Canonicalization via `(base_route, direction)`** | Because GTFS `trips.txt` contains NULL for `direction_id` while both GTFS `routes.txt` and ticketing data embed `UP`/`DOWN` in route codes, we establish an explicit canonical schema: `base_route` (e.g., `717A`) and `direction` (`UP` = Outbound, `DOWN` = Inbound). |
| **ADR-003** | **Machine-Readable Metadata JSON Artifacts** | All profiling, normalization mappings, and occupancy matrices are serialized to `data/processed/*.json` and `*.parquet`. This ensures reproducibility across sprints and enables decoupled frontend/backend services. |
| **ADR-004** | **Sprint Isolation with Verification Gates** | To prevent architectural drift, the engineering team operates strictly in sequential sprints: Sprint 0 (Profile) -> Sprint 1 (Normalize) -> Sprint 2 (Load Reconstruct) -> Sprint 3 (Predict) -> Sprint 4 (Routing Engine) -> Sprint 5 (UI & Documentation). |
| **ADR-005** | **Route-Scoped Candidate Stop Search Space Reduction** | Rather than searching across all 6,862 GTFS stops citywide for each ticketing stop name, candidates are strictly restricted to the ~30–50 stops on that specific route. This eliminates cross-borough false positives (e.g. matching an East Delhi Pocket A to a West Delhi Pocket A) and speeds up fuzzy search by $>100\times$. |
| **ADR-006** | **Canonical Representative Trip Selection via Maximum Stop Count** | GTFS feeds define multiple trip variants per route (e.g., depot pull-outs, truncated short trips). Selecting the trip with `max(stop_count)` ensures that the canonical sequence spans the complete physical corridor topology and encompasses all legitimate boarding stages. |
| **ADR-007** | **Parquet Storage Layer with ZSTD Compression** | Storing `canonical_route_stops.parquet` (1.37 MB) and `resolved_tickets.parquet` (24.99 MB) in columnar Parquet reduces disk storage by $>90\%$ relative to uncompressed CSV while allowing instantaneous columnar scans in subsequent modeling and routing sprints. |
| **ADR-008** | **Vectorized Difference-Array for OD-to-Segment Flow Reconstruction** | Expanding 2.4M passenger trips across all intermediate stops using cross-joins produces massive intermediate tables (~11.6M rows) that cause out-of-memory errors on commodity RAM. Emitting discrete boarding $(+)$ and alighting $(-)$ deltas and evaluating cumulative sums along canonical stop sequences executes in 3.28s with under 500 MB RAM. |
| **ADR-009** | **Dual-Source Supply Normalization & Zero-Anchored Sigmoid Crowding Formulation** | Because ~48.5% of ticketing records omit physical vehicle IDs and GTFS timetable frequencies vary by route, we blend scheduled GTFS departures with empirical vehicle counts corrected for missingness. Perceived crowding is modeled via a centered sigmoid ($L_0 = 0.65, k=3.5$) anchored strictly to zero at zero load, avoiding artificial minimum crowding penalties. |
| **ADR-010** | **Haversine BallTree Footpath Transfer Graph & Platform Radius Expansion** | Physical street geography requires walking connections for inter-route transfers and accessing opposite-direction boarding islands. Constructing a BallTree over 6,862 stops computes 23,354 walking transfers within 300m in 0.15s, while 250m origin/dest query expansion solves the physical separation between `UP` and `DOWN` stops along dual-carriageway corridors. |
| **ADR-011** | **Multi-Profile McRAPTOR with Dense Array Discomfort Evaluation & Target Pruning** | To compute non-dominated Pareto frontiers in sub-second latency, we evaluate generalized discomfort cost across anchor profiles ($\beta \in \{0.0, 0.6, 1.8\}$). Dense segment array lookups and dynamic upper-bound pruning maintain average query response under 180ms per profile. |

---

## 9. Sprint Verification Summary

### Sprint 0 Verification
- **Data Pipeline Script:** `src/pipeline/sprint0_profile.py` (executed successfully)
- **JSON Profile Artifact:** `data/processed/sprint0_profile.json` (13.5 KB, verified)
- **Dataset Health:** 2.56M ticketing transactions, 0% missing fields, 98.23% GTFS route volume coverage.
- **Sprint 0 Status:** **COMPLETE & VERIFIED**.

### Sprint 1 Verification
- **Data Pipeline Script:** `src/pipeline/sprint1_entity_resolution.py` (executed successfully in 52.67s)
- **Canonical Parquet:** `data/processed/canonical_route_stops.parquet` (83,435 stops across 2,574 routes, 1.37 MB)
- **Resolved Tickets Parquet:** `data/processed/resolved_tickets.parquet` (2,394,241 valid forward tickets, 24.99 MB)
- **Detailed JSON Report:** `data/processed/sprint1_resolution_report.json` (5.56 KB)
- **Key Metrics Achieved:**
  - Route match rate: **91.19%** (covering **98.71%** of transactions and **98.70%** of passenger volume)
  - Stop resolution match rate: **93.13%** (jumped from 48.27% raw)
  - Valid forward passenger coverage: **93.51%** (2,574,781 passengers)
  - True `vehicle_number` NULL rate: **48.52%** (audited from literal `'NULL'` strings)
- **Sprint 1 Status:** **COMPLETE & VERIFIED**.

### Sprint 2 Verification
- **Data Pipeline Script:** `src/pipeline/sprint2_crowding_model.py` (executed successfully in 16.7s)
- **Segment Crowding Parquet:** `data/processed/segment_crowding.parquet` (1,209,599 rows, 8.62 MB, ZSTD compressed)
- **Detailed Validation Report:** `data/processed/sprint2_validation_report.json` (7.6 KB)
- **Key Metrics Achieved:**
  - Segment passenger flow coverage: 1,170,611 active empirical segments + 38,988 cold-start baseline priors
  - Total GTFS routes supported: 2,574 routes (100% routable)
  - Network-wide Mean Crowding Score: **0.1161** (P90: **0.3187**, Max: **1.0000**)
  - Bi-modal Diurnal Cycle: Morning peak P90 = **0.594**, Afternoon lull P90 = **0.102**, Evening peak P90 = **0.409**
  - Directional Asymmetry Validated: Tidal reversal demonstrated across key radial routes (`717A`, `729`, `511A`, `578`)
  - Tier Distribution: Low **91.0%**, Moderate **5.6%**, High **3.4%**
- **Sprint 2 Status:** **COMPLETE & VERIFIED**.

### Sprint 3 Verification
- **Router Engine Implementation:** `src/routing/mcraptor.py` (complete McRAPTOR multi-criteria router)
- **Verification Benchmark Script:** `src/routing/verify_sprint3.py` (executed successfully)
- **Benchmark JSON Report:** `data/processed/sprint3_routing_report.json` (190 lines, verified)
- **Key Metrics Achieved:**
  - Spatial Footpath Index: 6,862 stops indexed, 23,354 walking transfer edges ($< 300\text{ m}$)
  - Index Cold-Start Initialization Time: **5.34 seconds**
  - Mean Single-Profile Routing Latency: **~170 ms** ($< 250\text{ ms}$ performance specification met)
  - Full Multi-Profile Query Latency: **517.41 ms** across 3 simultaneous Pareto evaluations
  - Real-World Delhi Commuter Case Studies: Tested 4 major corridors across Morning Peak (09:00) and Afternoon Lull (14:30), verifying distinct Pareto trade-offs (e.g. `567AUP` Fastest Non-AC vs `724EXTDOWN` Least Crowded AC on Nehru Place $\to$ Dhaula Kuan)
  - Output Contract: Structured JSON-ready itineraries with segment-by-segment GPS paths, comfort tiers, and fare estimations.
- **Sprint 3 Status:** **COMPLETE & READY FOR REVIEW**.

### Sprint 4 Verification
- **API Service:** `src/api/main.py` (FastAPI lifespan-managed REST service)
- **Frontend Dashboard:** `frontend/index.html` (interactive Leaflet map + Chart.js crowding profiles)
- **Automated Test Suite:** `src/api/test_api.py` (9 comprehensive integration tests)
- **Key Metrics Achieved:**
  - Test Suite Result: **9 passed, 0 failed in 9.18s (100% test pass rate)**
  - Cold-Start Startup Time: ~5.4s for full 6,862 stops, 2,574 routes, 23,354 walking transfer edges
  - Endpoint Latencies: `/api/health` < 1ms, `/api/stops/search` < 5ms, `/api/plan` < 200ms
  - Full End-to-End Interactivity: Live multi-criteria journey planning, stop autocomplete, and diurnal route crowding explorer
- **Sprint 4 Status:** **COMPLETE & VERIFIED**.

### Sprint 5 Verification
- **Submission Deliverables:**
  - `requirements.txt`: Clean, production-grade dependencies without bloat
  - `README.md`: Judge-ready, comprehensive setup guide, pipeline commands, API docs
  - `docs/PROPOSAL.md`: Executive proposal with Phase 2 real-time GTFS-RT streaming roadmap
  - `docs/TECHNICAL_NOTE.md`: Rigorous mathematical methodology, calibration formulas, and validation tables
  - `docs/DEMO_VIDEO_SCRIPT.md`: 5-minute timed walkthrough script with on-screen actions
  - `PROGRESS_REPORT.md`: Finalized engineering log with full verification traceability
- **Sprint 5 Status:** **COMPLETE & DELIVERABLES FINALIZED**.

---

## 3. Finals Polish Pass: Road Geometries & Pareto Diversity

### 3.1 Motivation & Scope
To ensure an uncompromising standard during live evaluation and judging for Transport Stack Hackathon 2026 Phase 1, a targeted finals polish pass was conducted on the routing engine (`src/routing/mcraptor.py`) and web UI (`frontend/index.html`):
1. **Road-Hugging Map Polylines (GTFS `shapes.txt` Integration):**
   - Precomputed and serialized segment road geometry cache `data/processed/route_segment_shapes.pkl` across 80,859 canonical route segments.
   - For every consecutive stop pair `(from_stop, to_stop)` along a route trip, the closest shape vertices along the trip's shape geometry are mapped and sliced.
   - Exposed `path_coords: [[lat, lon], ...]` on every bus segment returned by `McRAPTOR` and consumed by Leaflet's `L.polyline`.
2. **Multi-Alternative Pareto Diversity & Extended Walk-Access Radius (400m):**
   - Expanded multi-stop origin/destination search radius from 250m to 400m (~5 min walk) in `_raptor_search()`, connecting parallel arterial corridors and nearby metro feeder stops.
   - Introduced an explicit `beta=3.5` high-comfort profile in `plan_journey()` alongside `Fastest (beta=0.0)`, `Balanced (beta=0.6)`, and `Least Crowded (beta=1.8)` to guarantee distinct comfort-focused options.
3. **Calibrated Arterial UI Presets:**
   - Calibrated 4 high-demand Delhi arterial preset corridors in `frontend/index.html` (*Nehru Pl → Dhaula Kuan*, *AIIMS → ISBT Kashmere Gate*, *Badarpur → ITO*, *GTB Nagar → Pitampura*) to showcase 2 to 3 distinct Pareto itineraries with clear trade-offs between travel time, crowd level, and transfers.
4. **Validation:**
   - 9/9 automated pytest cases in `src/api/test_api.py` passing in ~11.3s with zero regressions.

---

## 4. Research-Grade Transit Reliability & Behavioral Nudge Upgrades

### 4.1 Empirical Route Headways & Out-of-Vehicle Wait Perception
- **Headway Derivation & Caching (`data/processed/route_headways.json`)**:
  Derived service headways $H_{r,t}$ across all 2,574 canonical routes for 5 diurnal operational windows (`Early Morning`, `Morning Peak`, `Afternoon Lull`, `Evening Peak`, `Late Night`). Clamped to $[4.0, 30.0]$ minutes with a $12.0$ min default fallback.
- **Expected Wait Modeling**:
  Expected waiting time is parameterized as $W_{\text{base}}(r, t) = \min(15.0, 0.5 \times H_{r,t})$. Out-of-vehicle waiting time is weighted with a **$1.5\times$ psychological discomfort perception multiplier** in generalized cost, ensuring low-frequency routes do not unrealistically beat high-frequency trunk lines.

### 4.2 Left-Behind (Boarding-Denial) Risk Modeling ($C > 0.80$)
- In high-density bus networks like Delhi, passengers cannot reliably board a bus operating near crush capacity.
- For boarding segments with $C(e, t) > 0.80$, the engine calculates left-behind probability:
  $$p_{\text{deny}} = \min\left(0.75,\ \max\left(0,\ \frac{C(e,t) - 0.80}{0.20}\right) \times 0.75\right)$$
- Expected missed-bus delay $E[\Delta T_{\text{deny}}] = p_{\text{deny}} \times H_{r,t}$ is penalized at a **$1.7\times$ reliability penalty** in generalized cost.
- Exposes `est_wait_min`, `headway_min`, and categorical `boarding_risk` (`"High"`, `"Moderate"`, `"Low"`) on each itinerary and bus leg.

### 4.3 Smart $\pm 15$-Minute Peak Shoulder Departure Shift Nudge
- When the primary itinerary at requested departure time $t$ has $C \ge 0.45$ or `boarding_risk != "Low"`, the router runs lightweight temporal shoulder evaluations at $t - 15\text{ min}$ and $t + 15\text{ min}$.
- If a shifted departure reduces average crowding by $\ge 15\%$ (absolute drop $\ge 0.08$) without increasing total travel time by $> 10\%$, a `departure_nudge` object is returned:
  ```json
  {
    "recommended_time": "08:45",
    "shift_label": "15 mins earlier",
    "crowding_drop_pct": 31,
    "new_avg_crowding": 0.32
  }
  ```
- The interactive UI displays a sleek, clickable tip banner above the itinerary list, letting commuters apply the shift with one click.

### 4.4 Verification & Latency Benchmarks
- **End-to-End Test Suite**: 9/9 integration tests passing in `src/api/test_api.py`.
- **Query Latency**: End-to-end plan latency remains **124.1 ms** even with temporal shoulder evaluations, well under the 250 ms real-time performance budget.




