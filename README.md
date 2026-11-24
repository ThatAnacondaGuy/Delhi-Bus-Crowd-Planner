<!-- Rendered to README.md by `python -m src.pipeline.run --until render`. Edit this template, never README.md: every number below is a placeholder filled from the pipeline's own output. -->
<div align="center">

# Delhi Bus Crowding Planner

### See how crowded each stretch of your Delhi bus trip usually is — before you board.

[![Transport Stack Hackathon 2026](https://img.shields.io/badge/Transport%20Stack%20Hackathon%202026-Problem%202-1f4e79)](https://delhi.transportstack.in/hackathon/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-0f766e)](requirements.lock)
[![Live demo](https://img.shields.io/badge/live%20demo-Hugging%20Face-b45309)](https://huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner)
[![Tests](https://img.shields.io/badge/tests-pytest-0f766e)](tests)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-5f6670)](LICENSE)

**[Live demo](https://huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner)** ·
**[Technical note](docs/TECHNICAL_NOTE.md)** ·
**[Proposal (PDF)](docs/PROPOSAL.pdf)** ·
**[Validation report](data/processed/validation_report.md)**

<br>

<table>
  <tr>
    <td align="center" width="38%"><img src="docs/assets/app-commuter-leave-later-mandi-house.png" alt="Commuter screen: Mandi House to Laxmi Nagar at 18:00, fastest option usually crowded, leaving later usually standing" width="300"></td>
    <td align="center" width="62%"><img src="docs/assets/app-operator-view.png" alt="Operator view: ranked extra trips, corridor map with a time slider and route heat strip" width="520"></td>
  </tr>
  <tr>
    <td align="center"><sub><b>Commuter screen, Leave later.</b> The fastest bus is usually crowded; a bus 20 minutes later is usually standing. Shown only when a later bus is really better.</sub></td>
    <td align="center"><sub><b>Operator view.</b> Where one extra trip takes the most people out of crowded buses.</sub></td>
  </tr>
</table>

</div>

---

## Try it

**Live demo:** <https://huggingface.co/spaces/ThatAnacondaGuy/delhi-bus-crowd-planner>
It is a free static page with precomputed answers for a menu of well-known places and departure times, so it opens instantly and never sleeps. The full planner, where you type any pair of places, runs on your own computer from this repository ([Quick start](#quick-start)).

Five journeys to try first (weekday):

| # | Journey | Leaves | What it shows |
|---|---|---|---|
| 1 | ISBT Anand Vihar → Connaught Place | 18:00 | The brief's own example |
| 2 | Connaught Place → ISBT Anand Vihar | 18:00 | The reverse trip: the same road, a different answer by direction |
| 3 | Ambedkar Nagar → ITO | 09:00 | A morning trip on the Ambedkar Nagar – ITO corridor |
| 4 | Mandi House → Laxmi Nagar | 18:00 | A **Leave later** card: a later bus that is really better |
| 5 | Ambedkar Nagar → AIIMS | 09:00 | A **Less crowded** option that costs a few minutes |

<p align="center"><img src="docs/assets/app-commuter-cp-to-anand-vihar.png" alt="Commuter screen: Connaught Place to ISBT Anand Vihar on a weekday at 18:00, with a Usually crowded chip, the crowded stretch named, and a Leave later card" width="240"><br><sub>Journey 2. The app tells you when it uses a nearby stop for the place you typed, as in the note at the top of the card.</sub></p>

## The problem

Delhi has thousands of buses, and every journey planner picks a trip by time alone. None of them can tell a rider that the fastest bus is the one that is usually packed at 18:00, or that a later bus can be the better one: on Mandi House to Laxmi Nagar at 18:00 the fastest bus is usually crowded, and leaving at 18:20 is usually standing instead, on a trip of the same length. Nobody counts people on Delhi buses by stretch, so we estimate it from what *is* recorded: **2,559,899 ONDC app tickets from October 2026**, matched to the official timetable and to GPS traces, then scaled up to everyone on board and checked against everything we can compare it with.

The result is a crowding level for every route, direction, stretch between two stops and half hour, a planner that shows it beside each trip option, and a second screen that tells a bus operator where one extra trip helps most.

## How it works

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/architecture-dark.svg">
    <img src="docs/assets/architecture.svg" alt="System diagram. Inputs: ONDC app tickets, GTFS timetable, GPS feed. Pipeline: clean, resolve, network clock and assets, GPS trips that ran, riders on stretches, alighting correction, supply, scale, levels and evidence, operator ranking, validate, render. Outputs: crowding tables, planner tables, reports. Then the planner and API, and the commuter screen, operator view and live demo." width="900">
  </picture>
</p>

<sub>Data packets move along the arrows and each stage lights up in pipeline order. Switch on "reduce motion" in your system settings and the picture stands still.</sub>

**One ticket's story.** Every ticket says where a rider boarded and where they got off. We spread it over the stretches that rider travelled, at the time the bus was on each stretch. We add up everyone on that stretch in a half-hour window, scale the app tickets up to all riders, divide by the buses that really ran, and compare the people on board with the seats and the bus's rated total.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/how-it-works-dark.svg">
    <img src="docs/assets/how-it-works.svg" alt="Five steps: a ticket from boarding to alighting, spread over the stretches it rides, scaled to people on board, compared with seats and rated total, shown as a level chip" width="900">
  </picture>
</p>

### What a rider sees

Every level is a word, dots and a colour, never colour alone, and each one comes in Hindi.

| Level | Meaning | Hindi |
|---|---|---|
| ●○○ **Usually seats** | people on board stay under 70% of the seats, because some seats are reserved | आमतौर पर सीट मिल जाती है |
| ●●○ **Usually standing** | more than that, up to what the bus is rated to carry | आमतौर पर खड़े होकर जाना पड़ता है |
| ●●● **Usually crowded** | more people than the bus is rated to carry | आमतौर पर भारी भीड़ |
| ○○○ **No data** | not enough tickets or no bus scheduled; never shown as comfortable | जानकारी नहीं |

Each card also says **Based on many tickets** (कई टिकटों पर आधारित) or **Rough guess** (अंदाज़ा (कम टिकट)), names the crowded stretch, and offers three roles: **Fastest**, **Less crowded** and **Leave later**. A **Why?** sheet shows the people-on-board range against the bus's seats and rated total, and says plainly that the data is app tickets, scaled up.

## What makes it trustworthy

We wrote down what we expected to see **before** the first full run (`validation/expectations.yaml`), then reported every hit and every miss. **No field count was possible**: the team is in Pune and no one has counted people on Delhi buses, so none of this measures how close a level is to the truth on a given bus. What we can do is test the model against everything that can be compared with it.

<p align="center">
  <img src="docs/assets/fig-levels-by-hour.svg" alt="Share of weekday bus-km by crowding level, by hour of day, peaking in the morning and the evening" width="760">
</p>

| Check | Result |
|---|---|
| **Run stops if broken.** Ticket conservation, rider-minutes within 0.5%, buses for the riders, run times, schema, no NaN | All pass. Rider-minutes differ by 0.020%; run times by at most 6.1% |
| **Peaks** written down in advance: morning 08–10, evening 17–20 | **Hit.** Busiest hours are 09:00 and 19:00 |
| **Weekends** lower, flatter, later peak | **Hit** on all three |
| **Direction.** Inbound busier in the morning, outbound in the evening | **Hit.** 80% of 359 radial route pairs in the morning, 78% in the evening |
| **Week to week.** Two different weeks of the month, each alone | 76% of rider-weighted cells keep their level; load correlation 0.78. A held-out week lands inside our range in 63% of cells |
| **Published DTC bus-km per day** against 501,000 | **Hit.** Model 496,158, once GPS measured the trips that ran; the timetable alone was 2.29 times the published figure |
| **Published load factor** band 0.78–0.89 | **Miss.** Model 0.54, below the band. See the bracket below |
| **Ten researched busy corridors** | 10 of 10 by the rule we wrote down, **but chance alone gives 10.0 of 10**, so that proves little. The honest readings: 19% of corridor stretches sit in the top decile (chance 10%), and 7 of 10 hit with both ends on the corridor |

<details>
<summary><b>The load-factor miss, explained (it matters)</b></summary>

<br>

Published ridership, the trips GPS shows actually ran, and a bus's crush capacity do not fit together. With the model as it stands (no bus ever carries more than its crush load; riders no bus can carry are left unplaced) the weekday load factor is **0.54**. With the capacity bound off and all published ridership placed it is **1.70**. The published band of 0.78–0.89 lies between the two. We did not tune anything to close the gap; on routes where the capacity bound binds, **the crowding shown is a conservative, lower estimate.**

<p align="center">
  <img src="docs/assets/fig-load-factor-bracket.svg" alt="The model's load factor and the full-allocation load factor on either side of the published band" width="760">
</p>

</details>

<details>
<summary><b>More figures: the corridor check, trips that ran, travel-time factor</b></summary>

<br>

<p align="center">
  <img src="docs/assets/fig-corridor-check.svg" alt="Corridor check against its chance baseline" width="720"><br><br>
  <img src="docs/assets/fig-trips-ran-by-hour.svg" alt="Share of scheduled trips that ran, by hour, from GPS" width="720"><br><br>
  <img src="docs/assets/fig-travel-time-factor.svg" alt="Observed run time against the timetable by hour, DTC and cluster" width="720">
</p>

</details>

The full account, with method, assumptions, sensitivity tests and the checks that did not come out our way, is in the **[technical note](docs/TECHNICAL_NOTE.md)** and the generated **[validation report](data/processed/validation_report.md)**.

## Limits, stated plainly

- **Most levels are a Rough guess.** Only 4.7% of scheduled bus-km rests on many tickets; 89% is a rough guess and 6.4% is No data. The card says which one it is.
- **App tickets are about 1 in 44 riders.** We scale them up, never to more than a bus can hold. Women riding free, pass holders and cash riders are not in this data, so buses can be fuller than shown.
- **Capped routes read low.** On 1,257 routes the scale is held to bus capacity; 59% of published DTC ridership and 73% of cluster ridership could not be placed.
- **One month.** October 2026, which includes a festival season; weekends are thin.
- **Timetables are templates.** The official run times are a straight-line template, so we take run times from ticket pairs. GPS runs about 1.08 to 1.24 times that clock on weekdays; we state it and do not apply it.
- **GPS is a check, not ground truth.** About 38% of scheduled trips show up as having run; we use that to count buses.
- **No live arrivals, no live load per bus.** Levels are what is *usually* so at that stretch and hour.

## Quick start

Python 3.12 and [`uv`](https://docs.astral.sh/uv/). The raw ticket and GTFS files are not in the repository (size and terms of use); the small GPS aggregate that the pipeline needs is.

1. **Clone the repository.**
   ```bash
   git clone https://github.com/ThatAnacondaGuy/Delhi-Bus-Crowd-Planner && cd Delhi-Bus-Crowd-Planner
   ```
2. **Install the pinned packages.**
   ```bash
   uv venv --python 3.12 && source .venv/bin/activate
   uv pip install -r requirements.lock
   ```
3. **Place the data** from Transport Stack: `October-Delhi.csv` in `data/raw/` and the GTFS folder `delhi_buses_static_gtfs_v1/` in `data/raw/gtfs/`.
4. **Run the pipeline** (resumable: finished stages are skipped).
   ```bash
   python -m src.pipeline.run
   ```
5. **Start the planner**, then open <http://127.0.0.1:8000> for riders and <http://127.0.0.1:8000/operator> for operators.
   ```bash
   uvicorn src.api.main:app
   ```

Tests: `python -m pytest`. Health check: `/v1/health` reports the data version and what is loaded. Interactive API docs: `/docs`.

## Repository map

```text
src/pipeline/    the eight stages: clean, resolve, network, gps, loads, operator, validate, render
src/routing/     the planner: frequency-based round search, option roles, headline rules
src/api/         FastAPI service, /v1/plan, /v1/crowding, /v1/corridors, /v1/operator/trips
frontend/        commuter screen (English and Hindi) and operator view; no build step
validation/      expectations.yaml, written down before the first full run
docs/            technical note, proposal, figure and diagram scripts, docs/assets pictures
deploy/          bundle builder for the demo (aggregates only)
data/processed/  the small reports that are committed: validation report, coverage, data quality
data/gps_aggregates/  the committed GPS aggregate (trips that ran, by route and hour)
tests/           unit, golden-journey and documentation tests
```

<sub>README, technical note and proposal are rendered from `*.tmpl.md` templates by the last pipeline stage, so every number in them comes from the run that produced the tables (run `20261124-1340-fc8a433f`, code `b52923d`, finished 2026-11-24 13:40 IST).</sub>

## Data and credit

**Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing.**

| Source | What we use | In this repository |
|---|---|---|
| ONDC e-ticketing, October 2026 | 2,559,899 tickets, 2,753,606 passengers, 31 days, 2,259 route strings | No. Only aggregates |
| Static GTFS, DTC and cluster | 2,574 routes, stops, timetables, shapes | No |
| DTC bus GPS, October 2026 | Share of scheduled trips that ran, and run-time cross-check, from 10 sample days | Aggregate only |
| Economic Survey of Delhi 2025-26 and CAG audit | Published ridership, bus-km and load factor, used as outside checks | Cited in the technical note |

No ticket-level or vehicle-level data is committed or served; every response is an aggregate by route, stretch, corridor or scheduled trip.

## Phase 2

The aim is the same product with the evidence getting stronger: more months of tickets, so more cells rest on many tickets; a way to find out how many people really ride (a small on-bus count on a few corridors, if the transport department agrees); GPS stop times at scale to link a ticket to its exact trip; live arrival times; full Hindi stop search; and a hosted version that can serve many riders. The technical note lists them with the reason for each.

## Team

**Team Kshama**: **Aniket Ingale** and **Ashish Maurya (Ash)**, Pune. Transport Stack Hackathon 2026, Problem 2: a crowdedness-aware journey planner for Delhi buses.

<sub>MIT licence. Built with Python, DuckDB, pandas, FastAPI and plain JavaScript.</sub>
