# Phase 1 Crowding Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Delhi crowd planner so one command turns October 2026 app tickets, GTFS and a GPS aggregate into honest stretch-level crowding estimates, served by a planner, an API, a commuter screen, an operator screen and a public live link, with every judge-facing number rendered from pipeline output.

**Architecture:**
- **Pipeline:** stages (clean → resolve → network → loads → operator → validate → render) write tables into one DuckDB work file and small final outputs into `data/processed/`. `src/pipeline/run.py` runs them in order, and each stage can be resumed.
- **Planner:** a frequency-based round search (kept from the old router) reads the final tables.
- **API:** FastAPI serves `/v1/*` and two static pages.
- **Live link:** a Docker Hugging Face Space packages the API with aggregate outputs only.

**Tech Stack:** Python 3.12, DuckDB, pandas + pyarrow, RapidFuzz, FastAPI + uvicorn, PyYAML, pytest + httpx, Leaflet 1.9.4 (pinned), plain CSS (no Tailwind CDN), 7-Zip for the GPS archive.

**Specs:**
- `docs/superpowers/specs/2026-11-17-phase1-crowding-planner-design.md` (v3)
- `docs/superpowers/specs/2026-11-18-phase1-research-notes.md`

Read both before any task; section numbers below (§) refer to the design.

## Global Constraints

- **Deadline:** submit by 18:00 IST on 24 Nov 2026. The freeze tag is made on the evening of 23 Nov.
- **Time zone:** every time operation runs in `Asia/Kolkata`; every DuckDB connection comes from `src/pipeline/db.connect()`.
- **Git:**
  - commits under the user's git identity, with no `Co-Authored-By` or "Generated with" line
  - stage explicit paths only, never `git add -A`
  - push `phase1` at each evening check
- **Repo contents:** never commit raw tickets, GTFS, GPS, `*.parquet`, `*.pkl`, `*.geojson`, `*.7z` or `*.db`, or any file over 5 MB. No ticket-level or vehicle-level data in git, on the live link or in outputs.
- **Bus specs** (seats / rated total / crush / comfortable):

  | Bus | Seats | Rated total | Crush | Comfortable |
  |---|---|---|---|---|
  | `12m_ac` | 35 | 63 | 100 | 77 |
  | `9m_devi` | 23 | 36 | 42 | 32 |
  | `12m_nonac` | 37 | 63 | 100 | 79 |

- **Levels:**
  - `seats` if L < 0.7 × seats
  - `standing` if L ≤ rated total
  - `crowded` if L > rated total
  - `no_data` per §5.6 step 8
  - The displayed L is capped at crush, with flag `full`.
- **Evidence states:** `many_tickets`, `rough`, `none`.
- **Commuter copy** (exact):
  - Usually seats / आमतौर पर सीट मिल जाती है
  - Usually standing / आमतौर पर खड़े होकर जाना पड़ता है
  - Usually crowded / आमतौर पर भारी भीड़
  - No data / जानकारी नहीं
  - Based on many tickets / कई टिकटों पर आधारित
  - Rough guess / अंदाज़ा (कम टिकट)
  - Full buses may not stop / भरी बस शायद न रुके
- **Credit line in UI and README:** "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing."
- **Forbidden in judge-facing files** (README, docs/*.md outside `docs/archive/` and `docs/superpowers/`, frontend, API strings): `κ`, `kappa`, `McRAPTOR`, `Pareto`, `sigmoid`, the word `score`.
- **Never invent a number.** Every number in docs, UI or video comes from `validation_report.json` or `manifest.json` through `render.py`.

## Review Focus

1. **Typed places in many forms.** Riders type "cp", "Rajiv Chowk", "anand vihar isbt", "kashmiri gate" or "ISBT AV". These should resolve to the right place or return a 404 with suggestions, never a 500 and never a silent wrong match. Pinned in Task 15 (`test_places_search_aliases`) and Task 16 (`test_plan_unknown_place_404`).
2. **Departures outside service hours** (03:00, 23:40). These must return options marked `timetable_uncertain` or a clear "no service" note, never an empty 200. Pinned in Task 15 (`test_night_departure_flagged`).
3. **Origin and destination at the same place, or within walking distance.** This must return one walk-only option, never an error. Pinned in Task 15 (`test_walk_only_trip`).
4. **Weekend queries where most stretches are `no_data`.** Cards must still render with the No data chip, and "Less crowded" must be absent rather than wrong. Pinned in Task 15 (`test_less_crowded_ineligible_when_mostly_no_data`) and Task 17 (`test_card_renders_no_data`).
5. **A scheduled route with zero app tickets.** The planner still routes on time alone, and its stretches show `no_data`, never `seats`. Pinned in Task 10 (`test_zero_ticket_route_is_no_data`).

---

## File structure

```
src/pipeline/
  config.py        constants and sourced assumptions (§3, §5.6)
  db.py            connect(): DuckDB with TimeZone pinned
  run.py           CLI and stage registry: --until, --sample, --gps-raw, --force
  manifest.py      stage completion, input checksums, versions
  clean.py         tickets_clean, calendar, data-quality numbers
  routes.py        route-string parsing, direction, D- rule, alias keys
  resolve.py       canonical_stops, alias confirmation, tickets_resolved/rejected
  network.py       run-time factors, passings, service hours, bus mix, places, shapes
  loads.py         stretch riders (on-board time), alighting correction, supply, scale, levels, evidence, outputs
  operator.py      extra-trip ranking
  validate.py      gates summary, expectations, repeatability, independent checks, sensitivity, diagnostics
  gps.py           GPS aggregates (reader always; raw processing behind --gps-raw)
  render.py        fill {{placeholders}} in docs templates
  hubs.yaml        hub alias table (~30 hubs)
src/routing/planner.py          frequency-based round search, roles, headline level
src/api/main.py                 /v1 endpoints, static pages
frontend/index.html, app.css, app.js    commuter screen
frontend/operator.html, operator.js     operator view
validation/expectations.yaml   written before any model run
tests/fixtures/                toy GTFS, ticket builder, GPS SQLite builder
tests/test_*.py
docs/TECHNICAL_NOTE.tmpl.md, docs/PROPOSAL.tmpl.md, docs/DEMO_VIDEO_SCRIPT.md, docs/archive/
deploy/Dockerfile, deploy/space_README.md, deploy/package_bundle.py
scripts/precommit_check.py
```

The old files are deleted in the task that replaces them; git history keeps them:
- `src/pipeline/sprint0_profile.py`, `sprint1_entity_resolution.py` and `sprint2_crowding_model.py` (by Task 6)
- `src/routing/mcraptor.py` and `verify_sprint3.py` (by Task 15)
- `src/api/test_api.py` (by Task 16)

Intermediate tables live in `data/processed/work.duckdb`, which is gitignored. Final outputs go to `data/processed/`:
- `stretch_crowding.parquet`
- `corridor_values.parquet`
- `corridor_geometry.geojson`
- `operator_trips.parquet`
- `route_hour_summary.csv`
- `coverage.csv`
- `validation_report.json` / `.md`
- `data_quality.md`
- `manifest.json`

Committed small outputs: the reports (`.json`, `.md`, `.csv` under 5 MB) and `data/gps_aggregates/`.

## Milestones (evening checks; tag `rc-<date>`, then push and `git bundle create ../delhi-crowd-planner-<date>.bundle --all`)

- **M1, 19 Nov:**
  - Tasks 1–10 run on the full data.
  - `/v1/plan` (Tasks 15–16) returns three options for the brief's preset from the new tables.
  - The GPS go/no-go is recorded at 12:00.
- **M2, 20 Nov:** Task 12 report renders and all gates pass. The GPS (Task 13) is in or out. Render step (Task 14) and proposal draft v1 (Task 19).
- **M3, 21 Nov:** commuter screen (Task 17) shows three cards for 5 demo journeys at 360 px width.
- **M4, 22 Nov:** operator view (Task 18) is live. Rehearsal deploy (Task 20) happens only after the user approves publishing.
- **M5, 23 Nov:**
  - Clean-clone rebuild (Task 21) and all docs rendered (Task 19).
  - Freeze tag; final deploy after the user approves.
  - The team records the video.
- **24 Nov:** the team submits the proposal PDF, video link, live link and GitHub link by 18:00 IST.

**Parallel tracks:**
- Task 13 (GPS) can run beside Tasks 6–10: different files, and it only needs `canonical_stops` from Task 6.
- Task 17 (commuter screen) can start once Task 16 has committed `tests/fixtures/plan_example.json`, or earlier from the response shape fixed in Task 15.

---

### Task 1: Environment, repo hygiene, baseline

**Files:**
- Modify: `requirements.txt`, `.gitignore`
- Create: `requirements.lock`, `scripts/precommit_check.py`, `.githooks/pre-commit`, `LICENSE`, `tests/test_repo_hygiene.py`
- Move: `PROGRESS_REPORT.md`, `docs/PROPOSAL.md`, `docs/DEMO_VIDEO_SCRIPT.md` and `docs/TECHNICAL_NOTE.md` to `docs/archive/`

**Interfaces:**
- Produces:
  - `scripts.precommit_check.check_paths(paths: list[str], max_bytes: int = 5_000_000) -> list[str]`, which returns error strings
  - git hook path `.githooks`

- [ ] **Step 1: Write the failing tests** in `tests/test_repo_hygiene.py`:

```python
IGNORED = ["data/processed_/x.parquet", "data/raw/gps/a.7z", "x.parquet", "x.pkl", "x.geojson", "x.db",
           "data/processed/stretch_crowding.parquet", "data/processed/work.duckdb"]
KEPT = ["tests/fixtures/toy_tickets.csv", "data/processed/validation_report.json",
        "data/processed/coverage.csv", "data/gps_aggregates/gps_route_hour.csv"]
def test_gitignore():  # uses `git check-ignore -q <path>` (exit 0 = ignored)
    assert all(ignored(p) for p in IGNORED) and not any(ignored(p) for p in KEPT)
def test_precommit_rejects(tmp_path):
    big = tmp_path / "big.bin"; big.write_bytes(b"0" * 5_000_001)
    errs = check_paths([str(big), "data/raw/x.csv", "docs/ok.md"])
    assert len(errs) == 2 and not any("docs/ok.md" in e for e in errs)
def test_imports():
    import pyarrow, rapidfuzz, fastapi, duckdb, yaml, httpx  # noqa
```

- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_repo_hygiene.py -v`. Expected: FAIL (missing pyarrow, unignored paths, no checker).
- [ ] **Step 3: Install and pin.**
  - Set `requirements.txt` to these lines: `duckdb>=1.1,<3`, `numpy>=1.26`, `pandas>=2.2`, `pyarrow>=14`, `rapidfuzz>=3.9`, `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `pydantic>=2.8`, `pyyaml>=6`, `pytest>=8`, `httpx>=0.27`.
  - Run `VIRTUAL_ENV=venv uv pip install -r requirements.txt`, then `uv pip freeze --python venv/bin/python > requirements.lock`.
- [ ] **Step 4: `.gitignore`.**
  - Add `data/processed_/`, `*.parquet`, `*.pkl`, `*.geojson`, `*.7z`, `*.db`, `*.duckdb` and `data/processed/*`.
  - Re-include `!data/processed/*.json`, `!data/processed/*.md`, `!data/processed/*.csv`, `!data/gps_aggregates/**` and `!tests/fixtures/**`.
  - Keep `*.csv` ignored elsewhere.
- [ ] **Step 5: Hook.**
  - Implement `check_paths`: reject a size over `max_bytes`, and any path under `data/` other than `data/processed/*.{json,md,csv}` and `data/gps_aggregates/*`.
  - `.githooks/pre-commit` runs it on `git diff --cached --name-only`.
  - Run `git config core.hooksPath .githooks`.
- [ ] **Step 6: Baseline tag.**
  - Copy only `data/processed_/*.parquet` and `*.pkl` to `data/processed/` (ignored). Do not copy the `.json` files: tracked files of the same name exist there.
  - Run `venv/bin/python -m uvicorn src.api.main:app --port 8765` and confirm `GET /api/health` returns 200.
  - Stop it and run `git tag baseline 9dbcbf4`. This is the old app's code.
- [ ] **Step 7: Archive and licence.**
  - `git mv` the four docs and the old tracked reports (`data/processed/sprint*_report.json`, `data/processed/sprint0_profile.json`, `data/processed/route_headways.json`) into `docs/archive/` (reports into `docs/archive/old_reports/`).
  - Prepend to each doc: `> Superseded on 18 Nov 2026 by the Phase 1 rebuild. Numbers here describe the old model and are not current.`
  - Add an MIT `LICENSE` ("Copyright (c) 2026 Delhi Crowd Planner contributors").
- [ ] **Step 8: Run the tests.** Expected: PASS.
- [ ] **Step 9: Commit.** `git add requirements.txt requirements.lock .gitignore scripts/precommit_check.py .githooks/pre-commit LICENSE tests/test_repo_hygiene.py docs/archive` (plus the removed paths), then `git commit -m "chore: pin environment, guard data from git, archive old docs"`.

### Task 2: Config, DuckDB helper, toy fixtures

**Files:**
- Create: `src/pipeline/config.py`, `src/pipeline/db.py`, `src/pipeline/hubs.yaml`
- Create fixtures: `tests/fixtures/build_toy_gtfs.py`, `tests/fixtures/toy_gtfs/*.txt` (generated, committed), `tests/conftest.py`, `tests/helpers.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces in `config.py`:
  - **Specs and sources:**
    - `BusSpec(NamedTuple): seats:int; rated_total:int; crush:int; comfortable:int`
    - `BUS_SPECS: dict[str, BusSpec]`
    - `Source(NamedTuple): value:float; year:str; url:str; note:str`
    - `PUBLISHED_RIDERSHIP: dict[str, Source]`: keys `"DTC"` = 2_429_000 (FY2025-26) and `"DIMTS"` = 1_530_000 (FY2024-25)
    - `PUBLISHED_DTC_BUS_KM = Source(501_000, "2025-26", …)`
    - `PUBLISHED_LOAD_FACTOR_BAND = (0.78, 0.89)`
  - **Calendar:**
    - `TZ = "Asia/Kolkata"`
    - `EXCLUDED_DATES` (2 Oct, 20 Oct 2026)
    - `EXCLUDED_WINDOWS: list[tuple[datetime, datetime]]` (tz-aware IST): 6 Oct 09:15–11:00; 17 Oct 11:45 – 19 Oct 10:00; 29 Oct 19:00 – 30 Oct 00:00
    - `WEEK_BLOCKS = [("2026-10-05","2026-10-09"), ("2026-10-12","2026-10-16"), ("2026-10-21","2026-10-23"), ("2026-10-26","2026-10-30")]`
  - **Windows:** `WindowSpec(NamedTuple): step_min:int; base_min:int`, with `WINDOWS = {"weekday": WindowSpec(30, 90), "weekend": WindowSpec(60, 120)}`
  - **Model constants:**
    - `SEATS_FRACTION = 0.7`, `SCALE_RANGE = (0.7, 1.3)`
    - `BOUND_PERCENTILE = 0.95`, `BOUND_MIN_TICKETS = 30`
    - `RUNTIME_MIN_PAIRS = 30`, `RUNTIME_MIN_GAP_S = 600`, `RUNTIME_GATE_TOL = 0.15`
    - `CONSERVATION_TOL = 0.005`, `S0_MAX_SHARE = 0.01`
    - `LOW_APP_USE_FRACTION = 1/3`, `NO_DATA_PERCENTILE = 0.25`
    - `DEVI_ROUTE_RE = r"^D-\d"`, `DEVI_VEHICLE_MIN_TICKETS = 5`, `DEVI_ROUTE_SHARE = 0.5`
    - `PLACE_RADIUS_M = 400`
  - **GPS and planner constants:**
    - `GPS_COVERAGE_MIN = 0.8`, `GPS_TRIP_STOP_SHARE = 0.8`, `GPS_STOPTIME_RHO_MIN = 0.3`
    - `LESS_CROWDED_SLACK = (15, 0.30)`, `LEAVE_LATER_SHIFTS = (10, 20, 30, 40)`
    - `HEADLINE_MIN_MINUTES = 5`, `NIGHT_START_H = 23`, `NIGHT_END_H = 5`
  - **Copy:** `LEVEL_COPY` and `EVIDENCE_COPY`, dicts holding the exact EN/HI strings from Global Constraints
- Produces `db.connect(path: str | None = None) -> duckdb.DuckDBPyConnection`. It runs `SET TimeZone='Asia/Kolkata'`; `path=None` means in-memory.
- Produces `src/pipeline/errors.py`: `class GateError(RuntimeError)` (raised by every invariant gate) and `class RenderError(RuntimeError)`.
- Produces `tests.helpers.make_tickets(con, rows: list[dict]) -> None`, which creates table `tickets_raw` with the CSV's columns; and `tests/conftest.py` fixtures `toy_gtfs_dir` and `con`.

**Toy GTFS** (built by `build_toy_gtfs.py`; stops 1.5 km apart, so the 18 km/h template gives 300 s per segment):
- **Stops:**
  - 1 Alpha Terminal (28.6000, 77.2000)
  - 2 Bravo Market (28.61349, 77.2000)
  - 3 Charlie Chowk (28.62698, 77.2000)
  - 4 Delta Metro (28.64047, 77.2000)
  - 5 Echo Depot (28.65396, 77.2000)
  - 6 Foxtrot Nagar (28.62698, 77.21531)
  - 7 Charlie Chowk Opp (28.62700, 77.20030), 30 m from stop 3
- **Routes** (agency_id, route_id, short name):
  - DTC 101 `101UP`: 1→2→3→4→5
  - DTC 102 `101DOWN`: 5→4→3→2→1
  - DIMTS 201 `202UP`: 2→3→6
  - DIMTS 202 `202DOWN`: 6→3→2
  - DTC 301 `D-005UP`: 1→2→3
  - DTC 401 `OMS(+)UP`: 2→3→6→2 (ring)
  - DTC 501 `909UP`: 4→5, scheduled but given no tickets anywhere
- **Trips:**
  - 101UP/DOWN every 15 min, first departures 06:00–21:45
  - 202UP/DOWN every 30 min, 06:00–21:30
  - D-005UP every 20 min, 07:00–20:00
  - OMS every 30 min, 06:00–21:30
  - 909UP hourly, 06:00–21:00
- `calendar.txt` has service 1 on all days for 2025-01-01..2040-01-01. Shapes are straight lines through the stops.

- [ ] **Step 1: Write the failing tests:**

```python
def test_bus_specs():
    assert BUS_SPECS["12m_ac"] == BusSpec(35, 63, 100, 77)
    assert BUS_SPECS["9m_devi"] == BusSpec(23, 36, 42, 32)
    assert BUS_SPECS["12m_nonac"] == BusSpec(37, 63, 100, 79)
def test_timezone_pinned(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    assert connect().execute("select hour(timestamptz '2026-10-15 08:10:00+05:30')").fetchone()[0] == 8
def test_copy_exact():
    assert LEVEL_COPY["seats"] == ("Usually seats", "आमतौर पर सीट मिल जाती है")
def test_toy_template_is_300s(toy_gtfs_dir):  # every consecutive stop pair on 101UP is 300 s apart
    ...
```

- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_config.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `config.py`, `db.py` and `hubs.yaml`.
  - `hubs.yaml` maps each hub name to a list of aliases and GTFS name stems. Include at least: Connaught Place (cp, rajiv chowk, super bazar, regal), ISBT Anand Vihar (anand vihar isbt, isbt av, bus adda anand vihar), Kashmere Gate (kashmiri gate, isbt kashmere gate), Sarai Kale Khan, AIIMS, ITO, Mandi House, Nehru Place, Dhaula Kuan, Laxmi Nagar, Chirag Delhi, Ambedkar Nagar, Mori Gate, Badarpur Border, Saket, Karkardooma.
- [ ] **Step 4: Build the fixtures.** Run `venv/bin/python tests/fixtures/build_toy_gtfs.py`.
- [ ] **Step 5: Run the tests.** Expected: PASS.
- [ ] **Step 6: Commit** the config, db, hubs.yaml, fixtures, conftest, helpers and tests. Message: `feat(pipeline): config with sourced constants, IST-pinned db, toy fixtures`.

### Task 3: Pre-register expectations (commit before any model run)

**Files:**
- Create: `validation/expectations.yaml`, `src/pipeline/expectations.py`
- Test: `tests/test_expectations.py`

**Interfaces:**
- Produces:
  - `Corridor(name, grade, peak: list[str], direction: str|None, gtfs_stop_names: list[str], sources: list[str])`
  - `Expectations(peaks, weekend, radial, corridors: list[Corridor], gps_stoptime_rho_min: float, dtc_bus_km: tuple[float,float], load_factor_band: tuple[float,float])`
  - `load_expectations(path) -> Expectations`

- [ ] **Step 1: Write the failing tests.**
  - `test_schema`:
    - 10 corridors with grades: 2 strong, 4 moderate, 4 weak
    - corridor 1 `peak == ["am"]`
    - corridor 2 `peak == ["pm"]` and `direction == "eastbound"`
    - `dtc_bus_km == (400_800, 601_200)`
    - `load_factor_band == (0.78, 0.89)`
    - `gps_stoptime_rho_min == 0.3`
  - `test_stop_names_exist`: every corridor has at least 3 `gtfs_stop_names` found in the real `stops.txt` (skip if the real GTFS is absent).
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_expectations.py -v`. Expected: FAIL.
- [ ] **Step 3: Write `expectations.yaml`.**
  - Fill it from research notes §1, copying each corridor's name, grade, stated peak or direction, GTFS stop names (fix any name the test cannot find by searching `stops.txt`) and source URLs.
  - Also include:
    - `peaks: {am: [8, 10], pm: [17, 20]}`
    - `weekend: {lower: true, flatter: true, later_peak: true}`
    - `radial: {inbound_am: true, outbound_pm: true, inbound_definition: "towards the terminal nearer CP/ITO"}`
    - the corridor hit rule text from §5.8 B
    - the GPS stop-time rule: rho ≥ 0.3 overall and > 0 on every tested route
    - published checks, with their sources
- [ ] **Step 4: Implement** `load_expectations`.
- [ ] **Step 5: Run the tests.** Expected: PASS.
- [ ] **Step 6: Commit and push now.** `git commit -m "test: pre-register validation expectations before any model run"`, then `git push origin phase1`. The commit timestamp is the evidence that the expectations came first.

### Task 4: Clean stage, run CLI, manifest

**Files:**
- Create: `src/pipeline/clean.py`, `src/pipeline/run.py`, `src/pipeline/manifest.py`, `src/pipeline/paths.py`
- Test: `tests/test_clean.py`, `tests/test_run.py`

**Interfaces:**
- Consumes: `db.connect`, `config` (Task 2).
- Produces:
  - `clean.run(con, paths: Paths, sample_routes: list[str] | None) -> CleanStats`, which writes:
    - `tickets_clean(ticket_id BIGINT, route_raw, start_raw, end_raw, pax INT, amount DOUBLE, vehicle VARCHAR NULL, is_ac BOOL, ts TIMESTAMPTZ, date DATE, day_type VARCHAR, channel VARCHAR)`. The literal `'NULL'` or blank becomes SQL NULL; `channel` is `'linked'` or `'null'`.
    - `clean_days(date, day_type, is_excluded_date)`
  - `clean.excluded(ts) -> bool`, using EXCLUDED_DATES or any EXCLUDED_WINDOWS, applied by later stages in on-board time
  - `clean.clean_day_count(con, day_type, minute_of_day) -> int`: clean dates of that type minus those whose window at `minute_of_day` is excluded
  - `paths.Paths` dataclass, with fields `repo`, `gtfs_dir`, `tickets_csv`, `gps_archive`, `gps_aggregates`, `processed`, `planner_dir` (= `processed/planner`) and `work_db`; `Paths.default()`; and `Paths.from_env()`, which honours `DATA_DIR` for `processed`
  - `run.main(argv)` with `--until {clean,resolve,network,loads,operator,validate,render}`, `--sample N` (the N busiest route strings), `--gps-raw`, `--gps-days D1,D2,…` and `--force`
  - `manifest.mark_done(stage, inputs: dict[str,str], outputs: list[str])` and `manifest.is_done(stage, inputs) -> bool`, which compares SHA-256 of the inputs and versions

- [ ] **Step 1: Write the failing tests.**
  - **Day types:** 2026-10-03 is `weekend`; 2026-10-05 is `weekday`.
  - **Exclusions:**
    - `excluded(2026-10-02 12:00 IST)` is True
    - `excluded(2026-10-06 10:00)` is True and `excluded(2026-10-06 11:30)` is False
    - `excluded(2026-10-18 09:00)` is True
    - `excluded(2026-10-29 19:30)` is True and `excluded(2026-10-29 18:30)` is False
  - **Clean day counts:**
    - weekday at 600 minutes (10:00) is 20: 22 weekdays minus 2 Oct and 20 Oct, minus 6 Oct and 19 Oct at 10:00
    - weekend at 600 is 7: 4 Saturdays (3, 10, 24, 31) and 3 Sundays (4, 11, 25); 17 Oct at 10:00 is before the 11:45 window opens. Write the expected value explicitly in the test and derive it in a comment.
  - **`'NULL'` handling:** a `make_tickets` row with `vehicle_number='NULL'` comes out as `vehicle IS NULL` and `channel='null'`.
  - **CLI:** `run.main(["--until","clean"])` on fixtures writes `manifest.json` with `stages.clean.done == True`. A second call skips the stage, which the test asserts via a counter.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_clean.py tests/test_run.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Read the CSV with `read_csv_auto`, keeping `created_at` as TIMESTAMPTZ.
  - `ticket_id` = row number.
  - Write the data-quality numbers to table `dq_daily(date, tickets, pax, null_share, ac_pax, nonac_pax)`.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Run on the real data.** `venv/bin/python -m src.pipeline.run --until clean`. Expected:
  - 2,559,899 rows in `tickets_clean`
  - the 2 Oct count (41,016 tickets) appears in `dq_daily`
- [ ] **Step 6: Commit.** `feat(pipeline): clean stage with IST calendar, exclusions, resumable run CLI`.

### Task 5: Route strings and the D- rule

**Files:**
- Create: `src/pipeline/routes.py`
- Test: `tests/test_routes.py`

**Interfaces:**
- Produces:
  - `ParsedRoute(NamedTuple): base:str; direction:str|None; variant:str|None`. Direction is one of `UP`, `DOWN`, `CW`, `ACW`.
  - `parse_route(raw: str) -> ParsedRoute`
  - `alias_key(raw: str) -> str`
  - `is_devi(short_name: str) -> bool`
  - `opposite(p: ParsedRoute) -> ParsedRoute`
  - `pair_key(p) -> str`: the same value for both directions of a route

- [ ] **Step 1: Write the failing tests:**

```python
assert parse_route("522BDOWN2") == ParsedRoute("522B", "DOWN", "2")
assert parse_route("8UP") == ParsedRoute("8", "UP", None)
assert parse_route("OMS(+)UP").direction == "CW" and parse_route("OMS(-)DOWN").direction == "ACW"
assert parse_route("YMSPLUS") == ParsedRoute("YMS", "CW", None)
assert alias_key("ML96UP") == alias_key("ML-96UP") and alias_key("D-005UP") == alias_key("D-0005UP")
assert is_devi("D-0002STLUP") and is_devi("D-9101UP") and not is_devi("817NUP") and not is_devi("DS-12DOWN")
assert opposite(parse_route("8UP")).direction == "DOWN" and opposite(parse_route("OMS(+)UP")).direction == "ACW"
```

- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_routes.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Ring markers `(+)`/`PLUS` and `(-)`/`(−)`/`MINUS` take precedence over UP/DOWN.
  - `alias_key` uppercases, removes punctuation, strips leading zeros inside numeric runs, maps PLUS→(+) and MINUS→(-), and drops a trailing direction digit.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit.** `feat(pipeline): route-string parser, ring directions, DEVI rule`.

### Task 6: Canonical stops and ticket resolution

**Files:**
- Create: `src/pipeline/resolve.py`. Move `normalize_transit_text` and the route-scoped matcher from `sprint1_entity_resolution.py` lines 49–83 and 232–378, keeping their behaviour.
- Delete: `src/pipeline/sprint0_profile.py`, `sprint1_entity_resolution.py`, `sprint2_crowding_model.py`
- Test: `tests/test_resolve.py`

**Interfaces:**
- Consumes: `tickets_clean` (Task 4) and `routes.*` (Task 5).
- Produces:
  - `resolve.run(con, paths) -> ResolveStats`, which writes:
    - `route_map(route_raw, route_id BIGINT, short_name, operator, direction, is_ring BOOL, is_devi BOOL, match_type, evidence)`. `match_type` is one of `exact`, `alias`, `remap`, `unmatched`.
    - `canonical_stops(route_id, short_name, operator, seq INT 1..N, stop_id VARCHAR, stop_name, lat, lon, template_s INT, cum_template_s INT)`. `template_s` is the run time of the segment **ending** at this stop; it is 0 at seq 1.
    - `tickets_resolved(ticket_id, route_id, orig_seq, dest_seq, pax, vehicle, is_ac, ts, date, day_type, channel, amount, how)`. `how` is one of `forward`, `remapped`, `ring_wrap`.
    - `tickets_rejected(ticket_id, route_raw, reason)`
  - Raises `errors.GateError` when, per route_raw, `count(tickets_clean) != count(resolved) + count(rejected)`

- [ ] **Step 1: Write the failing tests** (toy GTFS plus `make_tickets`):
  - `test_template_on_to_stop`: for 101UP, `template_s` is `[0, 300, 300, 300, 300]` and `cum_template_s[-1] == 1200`.
  - `test_forward`: an Alpha Terminal → Delta Metro ticket on `101UP` resolves to `orig_seq=1, dest_seq=4, how='forward'`.
  - `test_reversed_remapped`: a Delta Metro → Alpha Terminal ticket labelled `101UP` resolves to route 102 (`101DOWN`) with `how='remapped'`.
  - `test_ring_wrap`: a Foxtrot Nagar → Charlie Chowk ticket on `OMS(+)UP` (stops 2→3→6→2) wraps: `orig_seq=3, dest_seq=5` (seq 4 is stop 2 again, 5 is stop 3 on the second lap), `how='ring_wrap'`.
  - `test_alias_needs_overlap`: `ML-96UP` vs `ML96UP` is accepted only if ≥ 80% of ordered stops overlap. Build two toy routes to show one accept and one reject.
  - `test_conservation_gate`: deleting one resolved row before the gate raises `GateError`.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_resolve.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Canonical sequence:** the longest trip per route_id, renumbered 1..N, with `template_s = arr_s - prev_dep_s` attached to the arriving stop.
  - **Remap:** a route whose majority of tickets come out reversed swaps to the `opposite()` route_id. Minority reversed tickets try the opposite route and are kept if they resolve forward; otherwise they are rejected with reason `reversed`.
  - **Ring wrap:** applies only where the first stop equals the last.
  - **Aliases:** only for strings with no exact short name (§5.3).
  - **Fare check:** report-only; add column `fare_flag` (≥ 2 slabs off) if time allows, otherwise leave it out.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Run on the real data.** `venv/bin/python -m src.pipeline.run --until resolve`. Expected:
  - the gate passes
  - match rate ≥ 93% of passengers
  - remapped and rejected counts printed, and per-reason counts written to `dq_resolve`
- [ ] **Step 6: Commit.** `feat(pipeline): canonical stops with to-stop run times; resolution with remap, ring wrap, conservation gate`.

### Task 7: Clock, passings, service hours

**Files:**
- Create: `src/pipeline/network.py` (clock part)
- Test: `tests/test_network_clock.py`

**Interfaces:**
- Consumes: `canonical_stops` and `tickets_resolved` (Task 6), plus GTFS `stop_times`/`trips`.
- Produces:
  - **Tables** (written by `network.run_clock(con, paths) -> ClockStats`):
    - `runtime_factors(scope VARCHAR, key VARCHAR, hour INT, factor DOUBLE, n_pairs INT)`. `scope` is `operator` or `route`.
    - `passings(route_id, seq, minute INT)`: one row per scheduled bus passing (every day; the feed has one service id).
    - `service_hours(route_id, first_min INT, last_min INT, ticket_hours VARCHAR)`
  - **`network.Clock`:**
    - `Clock.load(con) -> Clock` caches `canonical_stops` templates and `runtime_factors`
    - `Clock.factor(route_id, hour) -> float`: the route factor if `n_pairs ≥ 30`, else the route's operator factor
    - `Clock.travel_seconds(route_id, from_seq, to_seq, start_minute: float) -> float`: sums `template_s × factor(hour at each segment start)` across segments, advancing time as it goes
    - Every later task uses this object for timing.
- **Gate:** the modelled travel time between ticket-pair stops, per operator × hour, must be within ±15% of the observed pair times. Raise `GateError` otherwise.

- [ ] **Step 1: Write the failing tests.**
  - `test_factor_from_pairs`:
    - Two linked tickets on the same vehicle, same route and day: boarding at seq 1 at 18:00 and at seq 4 at 18:21.
    - Template seq 1 → 4 is 900 s, the observed gap 1,260 s, so the hour-18 operator factor is 1.4 (one pair). Pairs under 600 template seconds are ignored.
    - Repeat the pair over 30 dates, so the route-scope factor also exists.
  - `test_travel_seconds_advances_hour`: with factors {07: 1.0, 08: 2.0}, starting at 07:55 over 101UP seq 1 → 3 (2 × 300 s): segment 1 starts at 07:55 (factor 1.0, 300 s, ends 08:00), segment 2 at 08:00 (factor 2.0, 600 s), total 900.
  - `test_passings`: 101UP seq 3 has its first passing at 06:10 (360 + 10 minutes) and 64 passings per day.
  - `test_service_hours_adds_ticket_hours`: a route with tickets at 23:10 on 3 clean dates gets hour 23 added.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_network_clock.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Pairs:** a self-join on `tickets_resolved`, same vehicle, route_id and date, with `orig_seq` increasing and consecutive purchases ordered by `ts`. Observed = Δts; expected = template between the boarding stops. Weight by pairs.
  - **Passings:** from the first-stop departures in `stop_times` plus `travel_seconds`.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Run on the real data.** `venv/bin/python -m src.pipeline.run --until network`. Expected:
  - the gate passes
  - the DTC factor near 1.4 at 18 h and near 0.95 at 08 h (review measured values; if far off, investigate rather than loosen)
- [ ] **Step 6: Commit.** `feat(pipeline): ticket-pair clock, passings on corrected clock, service hours, run-time gate`.

### Task 8: Bus types, places, shapes

**Files:**
- Modify: `src/pipeline/network.py` (add functions)
- Test: `tests/test_network_assets.py`

**Interfaces:**
- Produces:
  - `bus_mix(route_id, share_9m DOUBLE, share_12m_ac DOUBLE, share_12m_nonac DOUBLE, basis VARCHAR)`. `basis` is `devi_name`, `vehicle_rule`, `is_ac` or `default`.
  - `devi_vehicles(vehicle)`: vehicles with ≥ 5 tickets on D- routes; internal, never exported.
  - `places(place_id, name, stop_id, lat, lon)`
  - `hub_alias(alias, place_id)`
  - `segment_shapes(route_id, seq, coords JSON, length_m DOUBLE)`, the segment ending at seq
  - `route_specs(route_id, seats DOUBLE, rated_total DOUBLE, crush DOUBLE)`: the share-weighted blend of `BUS_SPECS` per route
  - `service_class(route_id, class VARCHAR)`. `class` is one of `regular`, `school`, `daf`, `office_special`. School and DAF routes are removed from `passings` and from the planner; office specials keep weekday passings only and carry the flag `office_special`.

- [ ] **Step 1: Write the failing tests.**
  - `D-005UP` gets `share_9m == 1.0`, `basis='devi_name'`.
  - A non-D route whose linked tickets come 60% from devi vehicles gets `share_9m == 0.6`, `basis='vehicle_rule'`. At 40%, the 9 m share stays below the 50% rule, so the route is treated as 12 m (`share_9m == 0`).
  - `is_ac = False` tickets push `share_12m_nonac` up.
  - `route_specs` on a 50/50 mix of 9 m and 12 m AC gives seats 29.
  - **Service class:** a toy route named `DS-12DOWN` is `office_special` and has no weekend passings. A route whose long name contains "School" is `school` and has no passings at all. Before writing patterns, inspect the real `routes.txt` (`route_short_name`, `route_long_name`, `route_desc`) for school, DAF and office-special markers. Record the patterns in `config.SERVICE_CLASS_PATTERNS` and the counts in `data_quality.md`.
  - **Places:** stops 3 and 7 (same stem "Charlie Chowk", 30 m apart) share a place_id; stop 6 does not.
  - `hub_alias("cp")` resolves to the place whose name stem matches "Connaught Place". Add a toy stop named "Connaught Place" in the fixture builder to make this testable.
  - **Shapes:** the 101UP seq 2 segment starts at stop 1's coordinates and ends at stop 2's; `length_m` is within 1% of 1,500.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_network_assets.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Name stem:** lowercase, drop `opp`, `(.*)`, `terminal`, `metro station`, `bus stop` and punctuation.
  - **Shape slicing:** project stops onto the route's shape and keep the vertices between consecutive projections, never moving backwards.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Run on the real data.** `--until network`. Expected:
  - `share_9m == 1` on about 302 GTFS route rows by name
  - about 170 more rows by the vehicle rule (report the actual count)
- [ ] **Step 6: Commit.** `feat(pipeline): bus mix (D- rule + vehicle rule), places with hub aliases, segment shapes`.

### Task 9: Riders on stretches at on-board time, alighting correction

**Files:**
- Create: `src/pipeline/loads.py` (riders part)
- Test: `tests/test_loads_riders.py`

**Interfaces:**
- Consumes: `tickets_resolved`, `canonical_stops`, `network.Clock`, `clean.excluded`.
- Produces:
  - **Tables:**
    - `stretch_riders(route_id, seq INT, date, day_type, minute INT, pax DOUBLE, tickets INT, corrected BOOL)`. `seq` is the stretch from stop seq to seq+1; `minute` is the on-board minute when the bus reaches stop `seq`. Rows are kept per date; tickets counts distinct tickets.
    - `terminal_asymmetry(route_id, terminal_alight, reverse_terminal_board, ratio, moved_pax)`
  - `loads.run_riders(con, paths, correct_alighting: bool = True) -> RiderStats`
- **Gate:** the sum over stretch_riders of pax × stretch minutes equals the resolved tickets' rider-minutes within ±0.5%, computed with the same clock.

- [ ] **Step 1: Write the failing tests.**
  - **Placement on stretches:** one ticket on 101UP from seq 1 to 4, bought at 08:00 on 2026-10-14, with factor 1.0, yields rows for stretches 1, 2 and 3 at minutes 480, 485 and 490, each with pax 1.
  - **Exclusion in on-board time:** a ticket on 6 Oct bought at 09:05 on a long route has its stretches after 09:15 dropped; the excluded rider-minutes are counted separately so the gate still balances.
  - **Alighting correction:**
    - A toy route has 10 tickets ending at its terminal, while its reverse route has 2 boardings at that terminal and an intermediate-stop ratio of 1.0.
    - With the correction on, terminal alightings drop to 2, and the 8 moved alightings land on earlier stops of the same fare slab in proportion to the reverse route's boardings.
    - With it off, nothing moves.
  - **Gate:** corrupting one pax value raises `GateError`.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_loads_riders.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Expand tickets into stretches with DuckDB `range()` joins, not Python loops. Minute = `minute_of_day(ts) + Clock.travel_seconds(route, orig_seq, seq, minute_of_day(ts)) / 60`. Precompute cumulative corrected offsets per route × start hour so the join stays in SQL.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Run on the real data.** `--until loads` (riders only). Expected: the gate passes, and `terminal_asymmetry` is filled.
- [ ] **Step 6: Commit.** `feat(pipeline): riders on stretches at on-board time with terminal alighting correction`.

### Task 10: Supply, scale, levels, evidence, outputs

**Files:**
- Modify: `src/pipeline/loads.py` (load part)
- Test: `tests/test_loads_levels.py`

**Interfaces:**
- Consumes: `stretch_riders`, `passings`, `bus_mix`, `route_specs`, `service_class`, `gps_route_hour` if present (Task 13; else ρ = 1), `config`.
- Produces:
  - **Outputs:**
    - **`stretch_crowding.parquet`.** Columns:
      - identity: route_id, short_name, operator, direction, seq, from_stop_id, to_stop_id, from_name, to_name, day_type, window_start_min INT
      - counts: app_riders, tickets, buses, bus_source (`schedule`, `gps`, `widened`, `none`)
      - bus: share_9m, seats, rated_total, crush
      - estimates: E_r, people_low, people_mid, people_high
      - state: level, evidence, flags (`full`, `scaled_to_capacity`, `low_app_use`, `schedule_mismatch`, `alighting_sensitive`, `office_special`)
    - `corridor_values.parquet` (stop-pair id, day_type, window, people ÷ rated capacity, share of buses crowded, crowded rider-minutes)
    - `corridor_geometry.geojson`
    - `route_hour_summary.csv`
    - `coverage.csv`
    - **Planner tables:** `processed/planner/*.parquet`, exported from `work.duckdb` (`canonical_stops`, `segment_shapes`, `places`, `hub_alias`, `passings`, `service_hours`, `service_class`, `runtime_factors`, `bus_mix`, `route_specs`). The planner, API and live link read only these files. `devi_vehicles` and every ticket table are never exported.
  - **Functions:**
    - `loads.level(people_mid, spec) -> str`
    - `loads.evidence(low, high, spec, flags, route_no_data) -> str`
    - `loads.waterfill(app_by_route: dict, bound_by_route: dict, total: float) -> tuple[float, dict]`, returning (E*, E_r)
    - `loads.run_levels(con, paths) -> LevelStats`

- [ ] **Step 1: Write the failing tests:**

```python
assert level(24.4, BUS_SPECS["12m_ac"]) == "seats" and level(24.6, BUS_SPECS["12m_ac"]) == "standing"
assert level(63, BUS_SPECS["12m_ac"]) == "standing" and level(63.1, BUS_SPECS["12m_ac"]) == "crowded"
assert level(16.0, BUS_SPECS["9m_devi"]) == "seats" and level(36.5, BUS_SPECS["9m_devi"]) == "crowded"
E, Er = waterfill({"a": 100, "b": 100}, {"a": 10.0, "b": 1e9}, total=4000)
assert Er["a"] == 10.0 and abs(E - 30.0) < 1e-6 and abs(100*10 + 100*Er["b"] - 4000) < 1e-6
assert evidence(20, 30, BUS_SPECS["12m_ac"], set(), False) == "rough"          # spans seats/standing
assert evidence(30, 50, BUS_SPECS["12m_ac"], set(), False) == "many_tickets"   # standing throughout
assert evidence(30, 50, BUS_SPECS["12m_ac"], {"low_app_use"}, False) == "rough"
assert evidence(30, 50, BUS_SPECS["12m_ac"], set(), True) == "none"
```

  Also add these tests:
  - `test_load_base_centred_90`: weekday window 08:00 counts riders and buses with minute in [07:15, 08:45).
  - **S = 0 fallback:**
    - riders with no bus in the 90-minute base widen to ±30 min (`bus_source='widened'`)
    - if still none, `schedule_mismatch` with level `no_data`
    - the gate fails if such rider volume is ≥ 1%
  - **Cap at crush:** people_mid 130 on 12 m is displayed as 100 with flag `full`.
  - **`test_zero_ticket_route_is_no_data`:** toy route `909UP` (no tickets) has every stretch `level == "no_data"`, `evidence == "none"`, and is never `seats`.
  - **Sampling range:** a cell's daily values [0, 2, 0, 2] give SE = sd/√4 and feed people_low/high together with `SCALE_RANGE`.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_loads_levels.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement**, following §5.6 steps 3–8.
  - E_op = `PUBLISHED_RIDERSHIP[op].value` ÷ resolved app passengers per clean day for that operator.
  - B_r = crush(route mix) ÷ the 95th percentile of the route's weekday peak ℓ over cells with tickets ≥ 30. Routes without such cells have no bound.
  - **Corridor layer:** aggregate by `(from_stop_id, to_stop_id)` across routes.
  - **No data rule:** the route's app riders per scheduled trip are below the network 25th percentile, or `schedule_mismatch`.
  - **Low app use:** on stop pairs served by ≥ 2 routes, app riders per scheduled trip below one third of the pair's median across routes.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Run on the real data.** `venv/bin/python -m src.pipeline.run --until loads`. Expected:
  - the S = 0 gate passes
  - print the level and evidence shares by hour band
  - print E_DTC (expected about 35–37) and E_DIMTS (about 79) before water-filling, the number of capped routes and E*
- [ ] **Step 6: Commit.** `feat(pipeline): supply on corrected clock, operator scale with capacity water-filling, levels and evidence, corridor layer`.

### Task 11: Operator extra-trip ranking

**Files:**
- Create: `src/pipeline/operator.py`
- Test: `tests/test_operator.py`

**Interfaces:**
- Produces:
  - `operator_trips.parquet` with columns route_id, short_name, operator, direction, day_type, depart_min, crowded_rider_min_removed, riders_moved_down, max_load_section (from/to names), peak_load_factor, evidence_share, flags
  - `operator.run(con, paths) -> int`, returning the number of rows

- [ ] **Step 1: Write the failing test.**
  - A toy route with one crowded stretch (people 80 on 12 m, 2 buses in the window) gets an extra trip departing so it reaches that stretch in the window. The result: people per bus 80×2/3 ≈ 53.3, so the stretch goes from crowded to standing.
  - `crowded_rider_min_removed` = 160 riders × stretch minutes; `riders_moved_down` = 160.
  - Departures that reach no crowded stretch rank last with 0.
- [ ] **Step 2: Run it.** `venv/bin/python -m pytest tests/test_operator.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** For each route-direction and departure step (30 min), walk the stretches using `Clock.travel_seconds`, recompute people per bus with S + 1 in each reached window, and sum. Only use cells with `evidence != 'none'`.
- [ ] **Step 4: Run it.** Expected: PASS.
- [ ] **Step 5: Run on the real data.** `--until operator`.
- [ ] **Step 6: Commit.** `feat(pipeline): rank extra trips by crowded rider-minutes removed`.

### Task 12: Validation suite and report

**Files:**
- Create: `src/pipeline/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: all tables, `load_expectations`, and GPS aggregates if present.
- Produces:
  - `validation_report.json` with keys `gates`, `expectations`, `repeatability`, `independent`, `sensitivity`, `diagnostics`, `coverage_summary`, `headline_numbers`. `headline_numbers` is a flat dict of everything docs may quote.
  - `validation_report.md` (human-readable)
  - `data_quality.md`
  - `validate.run(con, paths) -> dict`

- [ ] **Step 1: Write the failing tests:**
  - **`test_repeatability`:** two synthetic weeks of identical cells give unchanged-level share 1.0. Flipping one cell of four (equal weights) gives 0.75, rider-weighted if the weights differ.
  - **`test_corridor_hit_rule`:** the corridor is a hit when one of its mapped stretches is in the top decile of weekday crowded rider-minutes per km within its peak window. The same stretch in the 13:00 window does not count.
  - **`test_published_checks`:**
    - bus-km 450,000 against band (400,800, 601,200) is a hit
    - load factor 0.70 against (0.78, 0.89) is a miss and is reported as a miss, never raised
  - **`test_sensitivity_counts`:** with E × 1.3 a cell at people_mid 55 on 12 m (standing) becomes 71.5 (crowded), counted once.
  - **`test_report_has_headline_numbers`:** keys include `match_rate`, `e_dtc`, `e_dimts`, `capped_routes`, `unchanged_level_share`, `corridor_hits_strong`, `dtc_bus_km_model` and `load_factor_model`.
  - **`test_nan_gate`:** a NaN or inf in `people_mid` raises `GateError`.
  - **`test_radial_rule`:** a synthetic route pair with the inbound direction (towards the terminal nearer CP/ITO) busier at 08–10 and the outbound direction busier at 17–20 counts as a hit; the reverse pattern counts as a miss.
  - **`test_weekend_rule`:** weekend crowded rider-minutes lower than weekday, with a flatter profile (smaller peak-to-mean ratio) and a later peak hour, is a hit on all three parts.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_validate.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Repeatability leaves one week block out in turn and recomputes levels from the other blocks.
  - Fleet load factor = Σ passenger-km ÷ Σ seat-km over weekday scheduled service.
  - DTC bus-km = Σ passings × segment length on DTC routes × ρ.
  - Sensitivity covers all six cases in §5.8 E: E ±30%, comfortable thresholds instead of rated totals, capacity ±10%, the 9 m vehicle rule at 90%, the alighting correction off, and the capacity bound off.
  - Diagnostics cover everything in §5.8 F.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Run the whole pipeline on the real data.** `venv/bin/python -m src.pipeline.run` (all stages). Expected:
  - all gates pass
  - the report renders
  - commit `validation_report.json`, `.md`, `data_quality.md` and `coverage.csv`
- [ ] **Step 6: Commit and push.** `feat(pipeline): validation suite (gates, pre-registered expectations, repeatability, published checks, sensitivity)`.

### Task 13: GPS layer (time-boxed; checkpoint 19 Nov 12:00, cut-off end of 20 Nov)

**Files:**
- Create: `src/pipeline/gps.py`, `tests/fixtures/build_toy_gps.py`
- Test: `tests/test_gps.py`
- Output (committed): `data/gps_aggregates/gps_route_hour.csv`, `data/gps_aggregates/gps_stop_hour.csv` (optional), `data/gps_aggregates/SHA256SUMS`

**Interfaces:**
- Consumes: `canonical_stops` (Task 6), the archive `data/raw/gps/delhi-dtc-bus-gtfs-rt-2026-10.7z`, and the linked vehicles in `tickets_resolved` (for coverage).
- Produces:
  - `gps.load_aggregates(con, paths) -> bool`, which creates `gps_route_hour(route_id, hour, day_type, observed_trips, scheduled_trips, coverage, rho, rho_first, rho_mid, rho_last, runtime_ratio, source)` from the committed CSV. It returns False if the CSV is absent.
  - `gps.build_aggregates(days: list[str], paths) -> None`, behind `--gps-raw`. It extracts one day with `7z e -o<tmp>`, opens it with `file:…?mode=ro&immutable=1`, aggregates, writes `<day>.parquet` to a work folder and deletes the .db. Days that are already done are skipped.

- [ ] **Step 1: Write the failing tests** (toy SQLite from `build_toy_gps.py`):
  - Exact duplicate polls are dropped.
  - A vehicle passing 4 of 5 canonical stops of 101UP in order (within 75 m) counts as one trip run. Passing 3 of 5 does not.
  - The speed column is never read: set it to garbage and the result is unchanged.
  - **Coverage and ρ:**
    - linked registrations {A, B, C, D, E} with A–D in the feed give coverage 0.8, so ρ is computed
    - with A–C seen (0.6), `source='schedule_only'` and ρ is NULL
  - `load_aggregates` returns False when the CSV is missing, and the pipeline then uses ρ = 1.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_gps.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Match each ping to the nearest canonical stop of its route_id within 75 m. Order each vehicle's pings by time within its trip_id, and keep stops whose sequence increases.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Checkpoint on 15 Oct.** Run `venv/bin/python -m src.pipeline.run --gps-raw --gps-days 2026-10-15 --until network` in the background. Record in the report:
  - the ρ distribution
  - the share of routes with coverage ≥ 0.8
  - runtime_ratio vs the ticket clock by hour

  Go/no-go at 12:00 on 19 Nov.
- [ ] **Step 6: If go, process the sample days.** 6 weekdays (13, 14, 15, 21, 22, 27 Oct) and 2 + 2 weekend days (3, 10, 4, 11 Oct), resumable, in the background. Commit the CSVs and `SHA256SUMS`.
- [ ] **Step 7: Stop-time corroboration** (optional, cut first): `gps_stop_hour.csv` with time inside a 30–50 m zone per intermediate stop × hour, by interpolation. `validate.py` reports the across-stop Spearman against the model's boardings + alightings per bus, and the mid-block null test.
- [ ] **Step 8: Commit.** `feat(gps): trips-ran and run-time aggregates from the GPS feed`.

### Task 14: Render step

**Files:**
- Create: `src/pipeline/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Produces `render.render_file(template: Path, out: Path, numbers: dict) -> None`. It replaces `{{name}}` and `{{name:fmt}}`, and raises `RenderError` on an unknown or unfilled placeholder. It is called by the `render` stage for each `docs/*.tmpl.md` → `docs/*.md`, with `numbers = report["headline_numbers"] | manifest summary`.

- [ ] **Step 1: Write the failing tests:**
  - `{{match_rate:.1%}}` with 0.9313 renders "93.1%"
  - an unknown key raises `RenderError`
  - an output still containing `{{` raises
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_render.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Commit.** `feat(pipeline): render docs from pipeline numbers`.

### Task 15: Planner

**Files:**
- Create: `src/routing/planner.py`. Reuse from `mcraptor.py`: `haversine_dist_m`, `compute_bus_fare`, footpath construction (lines 131–160) and the round loop in `_raptor_search` (lines 398–584), rewired to the new inputs.
- Delete: `src/routing/mcraptor.py`, `src/routing/verify_sprint3.py`
- Test: `tests/test_planner.py`

**Interfaces:**
- Consumes: `processed/planner/*.parquet` (Task 10 export) and `stretch_crowding.parquet`, through `Planner.load(paths)`. It never opens `work.duckdb`.
- Produces:
  - **Methods:**
    - `Planner.load(paths) -> Planner`
    - `Planner.plan(from_ref: str, to_ref: str, depart: str, day: str) -> dict`, returning the `/v1/plan` body below
    - `Planner.search_places(q: str, limit=8) -> list[dict]`
  - **Error:** `class PlaceNotFound(KeyError)`, carrying a `.suggestions: list[str]`
  - **Response shape** (frozen; the UI is built against it):

```json
{"data_version": "<manifest run id>", "query": {"from": {"id": "place:12", "name": "ISBT Anand Vihar"}, "to": {...}, "depart": "18:00", "day": "weekday"},
 "options": [{"roles": ["fastest"], "depart": "18:00", "arrive": "18:45", "minutes": 45, "changes": 0, "fare_inr": 15,
   "headline": {"level": "crowded", "evidence": "many_tickets", "stretch": {"from": "Laxmi Nagar", "to": "ITO", "minutes": 15}},
   "tradeoff": "Fastest", "timetable_uncertain": false,
   "legs": [{"mode": "walk", "meters": 120, "minutes": 2},
            {"mode": "bus", "route": "534UP", "bus_type": "12m_ac", "from": {"stop_id": "…", "name": "…"}, "to": {...},
             "depart": "18:02", "arrive": "18:45",
             "segments": [{"from_stop_id": "…", "to_stop_id": "…", "minutes": 3.1, "level": "standing", "evidence": "rough",
                           "people": [40, 52, 66], "seats": 35, "rated_total": 63, "flags": [], "coords": [[28.6, 77.2], …]}]}]}],
 "notes": []}
```

- [ ] **Step 1: Write the failing tests** (toy network with a hand-built `stretch_crowding`):
  - **Fastest:** Alpha → Echo at 08:00 weekday is 101UP, 20 min of riding, plus the wait.
  - **Less crowded:**
    - Make Bravo → Charlie on 101UP crowded at 08:00 and on D-005UP standing.
    - Bravo → Charlie at 08:00 returns `less_crowded` = D-005UP when its total time ≤ max(fastest + 15, fastest × 1.3).
    - Otherwise there is no less_crowded option.
  - **`test_less_crowded_ineligible_when_mostly_no_data`:** if the alternative's stretches are > 50% `no_data`, there is no less_crowded option.
  - **Leave later:** if the 08:20 window on 101UP is `seats` across its whole range (low and high both below 24.5), `leave_later` appears with depart 08:20. A window whose range spans two levels is not offered.
  - **Merged roles:** when fastest and less crowded are the same trip, there is one option with `roles == ["fastest", "less_crowded"]`.
  - **Headline:** a trip with 4 crowded minutes and 10 standing minutes has headline `standing`; with 6 crowded minutes, `crowded`.
  - **`test_night_departure_flagged`:** at 23:40, options carry `timetable_uncertain: true`, or the notes say "No scheduled service"; the response is never an empty 200 without a note.
  - **`test_walk_only_trip`:** from Charlie Chowk to Charlie Chowk Opp, one option, all walk.
  - Labels and tradeoff text come from the returned options (for example "+10 min, no crowded stretch").
  - **`test_places_search_aliases`:** "cp", "Rajiv Chowk", "anand vihar isbt" and "ISBT AV" resolve through `hub_alias` (toy hubs). "zzzz" raises `PlaceNotFound` with suggestions.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_planner.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The round search runs with cost T × (1 + β·w(level_high)) for β ∈ {0, 1, 3}, with w = {seats: 0, standing: 0.5, crowded: 1.5, no_data: 0.5}. Roles are picked from the union of candidates by the §5.9 rules.
  - Waits are half the headway, where headway comes from `passings` × ρ at the boarding stop and hour.
  - Max 3 buses; transfers ≤ 300 m; access ≤ 400 m.
  - Crowding for a time between window starts is interpolated linearly between the two neighbouring window centres, so +10 and +20 minutes do not jump at :00 and :30. Levels and evidence are recomputed from the interpolated range.
  - School and DAF routes are excluded; office specials run on weekdays only.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Real-data smoke test.** `Planner.load(Paths.default()).plan("ISBT Anand Vihar", "Connaught Place", "18:00", "weekday")` returns ≥ 1 option in under 2 s. Print the options.
- [ ] **Step 6: Commit.** `feat(routing): frequency-based planner with fastest/less-crowded/leave-later roles and place search`.

### Task 16: API v1

**Files:**
- Rewrite: `src/api/main.py`
- Delete: `src/api/test_api.py`
- Create: `tests/test_api.py`, `tests/fixtures/plan_example.json` (frozen from the toy run; commit it on 19 Nov)

**Interfaces:**
- Consumes: `Planner` (Task 15) and the outputs (Tasks 10–12).
- Produces:
  - `GET /v1/plan?from=&to=&depart=HH:MM&day=weekday|weekend` (body as in Task 15)
  - `GET /v1/places/search?q=`
  - `GET /v1/crowding?route_id=&day=&window=`
  - `GET /v1/crowding/stretch?from=&to=&day=`
  - `GET /v1/corridors?day=&window=`
  - `GET /v1/operator/trips?day=&operator=` and `/v1/operator/trips.csv`
  - `GET /v1/health`: `data_version`, data dates and computed counts from the manifest
  - `/` and `/operator`, serving the static pages
  - environment variable `DATA_DIR` overrides `data/processed` (the tests point it at a toy run)

- [ ] **Step 1: Write the failing tests** (TestClient on a toy pipeline run built in a session fixture):
  - Every 200 response includes `data_version`.
  - `/v1/plan` with `depart=9am` → 422; `from=zzzz` → 404 with `suggestions`; `day=sunday` → 422.
  - `/v1/plan` for the toy preset matches `plan_example.json` keys.
  - `/v1/operator/trips.csv` returns `text/csv` with a header row.
  - `/v1/health` counts equal the manifest counts, not constants.
  - CORS allows GET from any origin without credentials.
  - **`test_plan_unknown_place_404`.**
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_api.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Load the planner once in the lifespan, use pydantic query models, map `PlaceNotFound` to 404, and send the file as a response for CSV.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Commit `plan_example.json` and the API.** `feat(api): v1 endpoints with data version, input validation, CSV export`.

### Task 17: Commuter screen

**Files:**
- Rewrite: `frontend/index.html`
- Create: `frontend/app.css`, `frontend/app.js`
- Test: `tests/test_frontend_static.py`, plus a browser check

**Interfaces:**
- Consumes: `/v1/plan`, `/v1/places/search` (`plan_example.json` for offline work).

- [ ] **Step 1: Write the failing static tests:**
  - No `cdn.tailwindcss.com`; Leaflet pinned at `@1.9.4`; no Chart.js on this page.
  - All 7 copy strings from Global Constraints are present.
  - The credit line is present.
  - None of the forbidden words appear.
  - No `%` is shown next to a level.
- [ ] **Step 2: Run them.** `venv/bin/python -m pytest tests/test_frontend_static.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** to §5.11.
  - **Presets:**
    - ISBT Anand Vihar → Connaught Place, weekday 18:00
    - Connaught Place → ISBT Anand Vihar, weekday 18:00
    - Ambedkar Nagar → ITO, weekday 09:00
  - **Cards:** three cards with role, times, level chip (word + dots + colour), trade-off line, buses, changes, fare, a time bar shaded by segment level, and the crowded-stretch sentence.
  - **"Why?" sheet:** text from §5.11.
  - **Controls:**
    - EN | हिं toggle
    - "I need a seat" chip, which highlights the less-crowded card
  - **Map:** behind a button, lazy-loads Leaflet, colours segments by level.
  - **Layout:** 16 px text, 48 px taps, phone first.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Browser check.**
  - Start the API on the full data. At 360×640 and at 1366×768, the first card is visible without scrolling and the presets work.
  - `test_card_renders_no_data`: with a weekend query, cards show the grey No data chip. Screenshot all three cases.
- [ ] **Step 6: Commit.** `feat(ui): commuter screen with three roles, bilingual levels, evidence and why sheet`.

### Task 18: Operator view

**Files:**
- Create: `frontend/operator.html`, `frontend/operator.js`
- Test: `tests/test_frontend_static.py` (extend), plus a browser check

- [ ] **Step 1: Write the failing static tests.**
  - `operator.html` contains "Extra trips that help most", "maximum load section" and "load factor".
  - It links `/v1/operator/trips.csv` and has no forbidden words.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Include:
  - a ranked table: top 20 per operator, with flags
  - a corridor map with a time slider (`/v1/corridors`)
  - a route heat strip: stretches × windows from `/v1/crowding?route_id`
  - a heatmap of the top 50 route-directions (cut first if late)
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Browser check.** At 1366×768 the table loads, the slider changes the map, and CSV downloads.
- [ ] **Step 6: Commit.** `feat(ui): operator view with extra-trip ranking, corridor map and heat strip`.

### Task 19: Docs, proposal, video script

**Files:**
- Create:
  - `docs/TECHNICAL_NOTE.tmpl.md` → rendered to `docs/TECHNICAL_NOTE.md`
  - `docs/PROPOSAL.tmpl.md` → rendered to `docs/PROPOSAL.md`, plus `docs/PROPOSAL.pdf`
  - `docs/DEMO_VIDEO_SCRIPT.md`
- Rewrite: `README.md`
- Test: `tests/test_docs.py`

- [ ] **Step 1: Write the failing tests:**
  - The rendered docs contain no `{{`.
  - README, the docs (outside `docs/archive` and `docs/superpowers`) and the frontend contain none of the forbidden words.
  - The README quick start lists exactly: clone, `uv pip install -r requirements.lock`, place data, `python -m src.pipeline.run`, `uvicorn src.api.main:app`.
  - The README and note contain the credit line and the sentence "No field count was possible".
  - The note contains the brief-checklist table with 6 rows.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Write the templates** to §5.14.
  - **Technical note:**
    - method
    - assumptions table linked to `config.py`
    - brief-checklist table
    - the 2.2% vs 3–4% reconciliation
    - coverage
    - validation and independent checks
    - least-reliable areas
    - Phase 2
  - **Proposal:** a 2–4 page summary, rendered to PDF with headless Chrome `--print-to-pdf` from a simple HTML wrapper, or pandoc if installed.
  - **Video script:** the five beats with timings.
- [ ] **Step 4: Render.** `venv/bin/python -m src.pipeline.run --until render`.
- [ ] **Step 5: Run the tests.** Expected: PASS.
- [ ] **Step 6: Commit.** `docs: technical note, proposal and README rendered from pipeline output`.

### Task 20: Live link (Hugging Face Space)

**Files:**
- Create: `deploy/Dockerfile`, `deploy/space_README.md` (Space front matter: `sdk: docker`, `app_port: 7860`), `deploy/package_bundle.py`
- Test: `tests/test_bundle.py`

**Interfaces:**
- Produces `package_bundle.build(out_dir) -> list[Path]`. It copies only `stretch_crowding.parquet`, `corridor_*`, `operator_trips.parquet`, `segment_shapes` (as parquet), the planner tables exported from `work.duckdb`, the reports and `manifest.json`.

- [ ] **Step 1: Write the failing tests.**
  - The bundle contains no file with columns `vehicle`, `vehicle_number`, `ticket_id` or `ts`.
  - The total size is under 500 MB.
  - The API starts from the bundle alone (`DATA_DIR=bundle`) and `/v1/health` returns 200.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** `package_bundle` and the Dockerfile (python:3.12-slim, install `requirements.lock`, copy `src`, `frontend` and the bundle, run `uvicorn --port 7860`).
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Ask the user for approval before publishing.** Show the Space name and confirm the account. On a yes, create or update the Space under their Hugging Face account and upload. Check `/v1/health` and the presets on the live URL.
  - Rehearsal: 22 Nov.
  - Final: 23 Nov, from the freeze tag.
- [ ] **Step 6: Commit.** `feat(deploy): Hugging Face Space bundle with aggregates only`.

### Task 21: Final integration and freeze (23 Nov)

- [ ] **Step 1: Clean-clone rebuild.**
  - `git clone` to a temp folder, symlink the raw data in, install from `requirements.lock`, then run `python -m src.pipeline.run` and `pytest -q`.
  - Expected: all pass, and the `validation_report.json` `headline_numbers` equal the committed ones.
- [ ] **Step 2: Golden demo journeys.**
  - Write `tests/test_golden.py` for the 3 presets plus 2 journeys chosen from the evidence table.
  - Assert the roles present and the headline levels as produced; this guards against regressions after the freeze.
- [ ] **Step 3: Forbidden-terms sweep.** Grep the judge-facing files once more; expect no matches.
- [ ] **Step 4: Tag and push.**
  - `git tag rc-2026-11-23`, then `git push origin phase1 --tags`.
  - Final Space deploy, after the user's yes.
- [ ] **Step 5: Merge to main.**
  - Ask the user. On a yes, merge `phase1` into `main` with a merge commit, not squash, and push.
