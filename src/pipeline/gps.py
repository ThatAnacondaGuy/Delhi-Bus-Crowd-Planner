"""GPS layer (reduced scope): the share of scheduled trips that ran (rho) and a run-time cross-check.

Reads one day file of the feed (SQLite, read-only and immutable), drops duplicate polls, matches each ping to
the nearest canonical stop of its own route within 75 m, and counts a (vehicle, trip) as run when at least
80% of the route's stops are passed in order (longest strictly increasing chain of stop sequence numbers).
The feed's `speed` column is never read. Aggregates are by route x hour x day type; no vehicle-level data
leaves this module.
"""
import bisect
import math
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

MATCH_M = 75.0
MIN_STOP_SHARE = 0.8
COVERAGE_MIN = 0.8
MAX_SEG_S = 180            # consecutive pings further apart than this do not define a path
MAX_SEG_M = 2000.0
PASS_GAP_S = 900           # hits of one stop further apart than this are separate passes
RUN_GAP_S = 3600           # no stop reached for this long ends a run
RUN_DROP = 0.5             # a fall in stop number by more than this share of the route starts a new run
IST_OFFSET_S = 19800
CSV_NAME = "gps_route_hour.csv"
RHO_SHRINK_TRIPS = 3.0
SAMPLE_DAYS = ("2026-10-13", "2026-10-14", "2026-10-15", "2026-10-21", "2026-10-22", "2026-10-27",
               "2026-10-03", "2026-10-04", "2026-10-10", "2026-10-11")
COLUMNS = ["route_id", "hour", "day_type", "observed_trips", "scheduled_trips", "coverage", "rho", "rho_first",
           "rho_mid", "rho_last", "runtime_ratio", "source"]
M_PER_DEG = 111195.0


# ------------------------------------------------------------------ pings


def load_pings(con, db_path, day: str) -> int:
    """Stream one day file into `pings(vehicle, route_id, trip_id, ts, lat, lon)` of `con`, dropping duplicate
    (vehicle, timestamp) polls. Opened read-only and immutable; `speed` is never selected."""
    src = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    con.execute("DROP TABLE IF EXISTS _raw")
    con.execute("CREATE TEMP TABLE _raw (vehicle VARCHAR, route_id INTEGER, trip_id VARCHAR, ts BIGINT, "
                "lat DOUBLE, lon DOUBLE)")
    try:
        cur = src.execute("SELECT vehicle_id, CAST(route_id AS INTEGER), trip_id, CAST(timestamp AS INTEGER), "
                          "CAST(lat AS REAL), CAST(lng AS REAL) FROM vehicle_feed "
                          "WHERE date = ? AND route_id IS NOT NULL AND vehicle_id IS NOT NULL", (day,))
        while True:
            rows = cur.fetchmany(1_000_000)
            if not rows:
                break
            df = pd.DataFrame(rows, columns=["vehicle", "route_id", "trip_id", "ts", "lat", "lon"])
            con.register("_chunk", df)
            con.execute("INSERT INTO _raw SELECT * FROM _chunk")
            con.unregister("_chunk")
    finally:
        src.close()
    con.execute("""CREATE OR REPLACE TEMP TABLE pings AS
        SELECT vehicle, any_value(route_id) AS route_id, any_value(trip_id) AS trip_id, ts,
               any_value(lat) AS lat, any_value(lon) AS lon
        FROM _raw GROUP BY vehicle, ts""")
    con.execute("DROP TABLE _raw")
    return con.execute("SELECT count(*) FROM pings").fetchall()[0][0]


# ------------------------------------------------------------------ trips


def _chain(seqs: np.ndarray) -> list[int]:
    """Indices of a longest strictly increasing subsequence of `seqs` (patience sorting with back-pointers)."""
    tails: list[int] = []        # tails[k] = smallest tail value of an increasing run of length k + 1
    tail_idx: list[int] = []
    prev = [-1] * len(seqs)
    for i, v in enumerate(seqs.tolist()):
        k = bisect.bisect_left(tails, v)
        if k == len(tails):
            tails.append(v)
            tail_idx.append(i)
        else:
            tails[k] = v
            tail_idx[k] = i
        prev[i] = tail_idx[k - 1] if k else -1
    out, i = [], tail_idx[-1] if tail_idx else -1
    while i != -1:
        out.append(i)
        i = prev[i]
    return out[::-1]


def match_stops(con, stops: pd.DataFrame, match_m: float = MATCH_M) -> int:
    """crossed(vehicle, route_id, seq, t_first, t_last): the stops of its own route that a vehicle's path
    (straight lines between consecutive pings, at most MAX_SEG_S and MAX_SEG_M long) comes within match_m of, one
    row per pass, with the interpolated time of closest approach. Interpolating means a stop is found even when the 11 s (or 60 s)
    ping spacing steps over it."""
    con.register("_stops", stops[["route_id", "seq", "lat", "lon"]].astype({"route_id": "int32"}))
    d = match_m / M_PER_DEG * 1.05
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE crossed AS
        WITH seg AS (
            SELECT vehicle, route_id, ts AS t0, lat AS la0, lon AS lo0,
                   coalesce(lead(ts) OVER w, ts) AS t1, coalesce(lead(lat) OVER w, lat) AS la1,
                   coalesce(lead(lon) OVER w, lon) AS lo1
            FROM pings WINDOW w AS (PARTITION BY vehicle ORDER BY ts)),
        j AS (
            SELECT g.vehicle, g.route_id, s.seq, g.t0, g.t1,
                   (g.lo0 - s.lon) * {M_PER_DEG} * cos(radians(s.lat)) AS ax, (g.la0 - s.lat) * {M_PER_DEG} AS ay,
                   (g.lo1 - g.lo0) * {M_PER_DEG} * cos(radians(s.lat)) AS dx, (g.la1 - g.la0) * {M_PER_DEG} AS dy
            FROM seg g JOIN _stops s ON s.route_id = g.route_id
                 AND s.lat BETWEEN least(g.la0, g.la1) - {d} AND greatest(g.la0, g.la1) + {d}
                 AND s.lon BETWEEN least(g.lo0, g.lo1) - {d * 1.2} AND greatest(g.lo0, g.lo1) + {d * 1.2}
            WHERE g.t1 - g.t0 <= {MAX_SEG_S}),
        u AS (
            SELECT *, CASE WHEN dx * dx + dy * dy = 0 THEN 0.0
                           ELSE least(1.0, greatest(0.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) END AS f
            FROM j WHERE dx * dx + dy * dy <= {MAX_SEG_M ** 2})
        , hit AS (
            SELECT vehicle, route_id, seq, t0 + f * (t1 - t0) AS t FROM u
            WHERE power(ax + f * dx, 2) + power(ay + f * dy, 2) <= {match_m ** 2}),
        gap AS (
            SELECT *, coalesce(t - lag(t) OVER w2 > {PASS_GAP_S}, true) AS fresh
            FROM hit WINDOW w2 AS (PARTITION BY vehicle, route_id, seq ORDER BY t)),
        grp AS (SELECT *, sum(fresh::INT) OVER (PARTITION BY vehicle, route_id, seq ORDER BY t) AS pass FROM gap)
        SELECT vehicle, route_id, seq, min(t) AS t_first, max(t) AS t_last
        FROM grp GROUP BY vehicle, route_id, seq, pass""")
    con.unregister("_stops")
    return con.execute("SELECT count(*) FROM crossed").fetchall()[0][0]


def find_trips(con, stops: pd.DataFrame) -> pd.DataFrame:
    """Runs of one vehicle on one route, one row each: route_id, vehicle, hour (IST, of the first stop reached),
    chain_len (stops passed in order), ran (chain >= 80% of the route's stops), in_first/in_mid/in_last (>= 80%
    of that third's stops passed in order), run_s (leaving the first chain stop to reaching the last) and the
    first/last chain seq (a, b).

    The feed's trip_id is not used to cut runs: it changes mid-run (a vehicle is relabelled with its next
    scheduled trip before it finishes), which would split one run into several partial trips. A run ends when
    the vehicle's stop number falls back by more than half the route, or no stop is reached for an hour."""
    match_stops(con, stops)
    m = con.execute("SELECT vehicle, route_id, seq, t_first, t_last FROM crossed "
                    "ORDER BY vehicle, route_id, t_first, seq").fetchnumpy()
    n_stops = stops.groupby("route_id")["seq"].max().to_dict()
    veh, rid, seq, tf, tl = (m[k] for k in ("vehicle", "route_id", "seq", "t_first", "t_last"))
    cols = ["route_id", "vehicle", "hour", "chain_len", "ran", "in_first", "in_mid", "in_last", "run_s", "a", "b"]
    if len(seq) == 0:
        return pd.DataFrame(columns=cols)
    key_break = np.flatnonzero((veh[1:] != veh[:-1]) | (rid[1:] != rid[:-1])) + 1
    bounds = np.concatenate([[0], key_break, [len(seq)]])
    rows = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        r = int(rid[lo])
        n = int(n_stops[r])
        drop = max(2, RUN_DROP * n)
        sq_l, tf_l = seq[lo:hi].tolist(), tf[lo:hi].tolist()
        starts, run_max = [0], sq_l[0]
        for i in range(1, len(sq_l)):
            if sq_l[i] < run_max - drop or tf_l[i] - tf_l[i - 1] > RUN_GAP_S:
                starts.append(i)
                run_max = sq_l[i]
            else:
                run_max = max(run_max, sq_l[i])
        starts.append(hi - lo)
        for s0, s1 in zip(starts[:-1], starts[1:]):
            sq, first_t, last_t = seq[lo + s0:lo + s1], tf[lo + s0:lo + s1], tl[lo + s0:lo + s1]
            idx = _chain(sq)
            cs, ft = sq[idx], first_t[idx]
            need = math.ceil(MIN_STOP_SHARE * n - 1e-9)
            c3 = math.ceil(n / 3)
            flags = []
            for a_, b_ in ((1, c3), (c3 + 1, math.ceil(2 * n / 3)), (math.ceil(2 * n / 3) + 1, n)):
                size = max(b_ - a_ + 1, 0)
                flags.append(size > 0 and int(((cs >= a_) & (cs <= b_)).sum()) >= math.ceil(MIN_STOP_SHARE * size - 1e-9))
            t_depart = float(last_t[idx[0]])
            if len(idx) > 1:
                t_depart = min(t_depart, float(ft[1]))
            rows.append((r, str(veh[lo]), int(((int(ft[0]) + IST_OFFSET_S) // 3600) % 24), len(cs), len(cs) >= need,
                         *flags, float(ft[-1]) - t_depart, int(cs[0]), int(cs[-1])))
    return pd.DataFrame(rows, columns=cols)


def run_ratio(trips: pd.DataFrame, stops: pd.DataFrame, factor) -> pd.Series:
    """Observed run time / ticket-clock run time between the same two stops, per trip. `factor(route, hour)` is
    the clock's pace factor. NaN where the clock has no time or the observed time is not plausible."""
    cum = {r: g.sort_values("seq")["cum_template_s"].to_numpy(dtype=float) for r, g in stops.groupby("route_id")}
    out = np.full(len(trips), np.nan)
    for i, (r, h, a, b, s) in enumerate(zip(trips["route_id"], trips["hour"], trips["a"], trips["b"], trips["run_s"])):
        c = cum.get(r)
        if c is None or b <= a or b > len(c):
            continue
        model = (c[b - 1] - c[a - 1]) * factor(r, h)
        if model >= 300 and 120 <= s <= 6 * 3600:
            out[i] = s / model
    return pd.Series(out, index=trips.index)


# ------------------------------------------------------------------ aggregation


def day_aggregate(trips: pd.DataFrame) -> pd.DataFrame:
    """Per route x hour for one day: trips that ran, per third, and the median run-time ratio."""
    g = trips.rename(columns={"in_first": "first", "in_mid": "mid", "in_last": "last"})
    ran = g[g["ran"]]
    obs = ran.groupby(["route_id", "hour"]).size().rename("ran")
    third = g.groupby(["route_id", "hour"])[["first", "mid", "last"]].sum()
    rr = ran.dropna(subset=["run_ratio"]).groupby(["route_id", "hour"])["run_ratio"].agg(["median", "size"])
    out = pd.concat([obs, third], axis=1).fillna(0).join(rr.rename(columns={"median": "rt_median", "size": "rt_n"}))
    return out.reset_index()


def combine(day_trips: dict, day_cov: dict, scheduled: pd.DataFrame, day_types: dict) -> pd.DataFrame:
    """The committed table. `day_trips[day]` has route_id, hour, ran, in_first/in_mid/in_last, run_ratio per trip;
    `day_cov[day]` has route_id, linked, seen (counts only); `scheduled` has route_id, hour, scheduled_trips;
    `day_types[day]` is 'weekday' or 'weekend'. Per day type: observed = mean trips per day, coverage = seen /
    linked pooled over the days, rho = observed / (scheduled x coverage) where coverage >= 0.8."""
    out = []
    for dt in ("weekday", "weekend"):
        days = [d for d, t in day_types.items() if t == dt and d in day_trips]
        if not days:
            continue
        agg = pd.concat([day_aggregate(day_trips[d]).assign(day=d) for d in days], ignore_index=True)
        n = len(days)
        sums = agg.groupby(["route_id", "hour"])[["ran", "first", "mid", "last"]].sum() / n
        rt = agg.dropna(subset=["rt_median"]).groupby(["route_id", "hour"]).apply(
            lambda x: np.average(x["rt_median"], weights=x["rt_n"]), include_groups=False).rename("runtime_ratio")
        cov = pd.concat([day_cov[d] for d in days]).groupby("route_id")[["linked", "seen"]].sum()
        cov["coverage"] = np.where(cov["linked"] > 0, cov["seen"] / cov["linked"].where(cov["linked"] > 0), np.nan)
        t = pd.concat([sums, rt], axis=1).reset_index().merge(scheduled, on=["route_id", "hour"], how="outer")
        t = t.merge(cov[["coverage"]].reset_index(), on="route_id", how="left")
        for c in ("ran", "first", "mid", "last"):
            t[c] = t[c].fillna(0.0)
        t["day_type"] = dt
        t["scheduled_trips"] = t["scheduled_trips"].fillna(0).astype(int)
        ok = (t["coverage"] >= COVERAGE_MIN - 1e-9) & (t["scheduled_trips"] > 0)
        den = t["scheduled_trips"] * t["coverage"]
        for src, name in (("ran", "rho"), ("first", "rho_first"), ("mid", "rho_mid"), ("last", "rho_last")):
            t[name] = np.where(ok, t[src] / den.where(den > 0), np.nan)
        t["source"] = np.where(t["coverage"] >= COVERAGE_MIN - 1e-9, "gps", "schedule_only")
        t = t.rename(columns={"ran": "observed_trips"})
        out.append(t[COLUMNS])
    res = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=COLUMNS)
    res["route_id"] = res["route_id"].astype("int64")
    res["hour"] = res["hour"].astype("int64")
    return res.sort_values(["route_id", "day_type", "hour"]).reset_index(drop=True)


# ------------------------------------------------------------------ pipeline glue


def load_aggregates(con, paths) -> bool:
    """Create gps_route_hour from the committed CSV; False (table not created) when the CSV is absent.

    Besides the CSV columns the table has `rho_model`, the share the model applies to scheduled buses: for cells
    with source 'gps' and scheduled trips, (observed / coverage + K x route rho) / (scheduled + K) capped at 1,
    where route rho pools the route's hours for that day type. One sample-day cell with 1-3 scheduled trips is a
    handful of Bernoulli draws; the shrinkage keeps a cell that happened to see none from deleting the supply.
    NULL elsewhere (the model then uses rho = 1 and says 'schedule')."""
    csv = Path(paths.gps_aggregates) / CSV_NAME
    if not csv.exists():
        return False
    con.execute(f"""CREATE OR REPLACE TABLE gps_route_hour AS
        WITH raw AS (
            SELECT route_id::BIGINT AS route_id, hour::INTEGER AS hour, day_type::VARCHAR AS day_type,
                   observed_trips::DOUBLE AS observed_trips, scheduled_trips::INTEGER AS scheduled_trips,
                   coverage::DOUBLE AS coverage, rho::DOUBLE AS rho, rho_first::DOUBLE AS rho_first,
                   rho_mid::DOUBLE AS rho_mid, rho_last::DOUBLE AS rho_last, runtime_ratio::DOUBLE AS runtime_ratio,
                   source::VARCHAR AS source
            FROM read_csv(?, header = true, nullstr = '')),
        rr AS (SELECT route_id, day_type, sum(observed_trips / coverage) / sum(scheduled_trips) AS rho_route
               FROM raw WHERE source = 'gps' AND scheduled_trips > 0 GROUP BY 1, 2)
        SELECT raw.*, CASE WHEN raw.source = 'gps' AND raw.scheduled_trips > 0 THEN
                   least(1.0, (raw.observed_trips / raw.coverage + {RHO_SHRINK_TRIPS} * rr.rho_route)
                              / (raw.scheduled_trips + {RHO_SHRINK_TRIPS})) END AS rho_model
        FROM raw LEFT JOIN rr USING (route_id, day_type)""", [str(csv)])
    _fill(con)
    return True


def _fill(con) -> None:
    """gps_rho_fill(route_id, hour, day_type, rho, rho_src): rho for every route x hour x day type, so no cell
    defaults to 1 (that would give uncovered routes about 2.3x the buses of measured ones). Order: 'cell'
    (rho_model) -> 'route' (route rho pooled over hours) -> 'op_hour' (operator x hour x day type, trip-weighted
    over covered routes) -> 'op_day' (operator x day type). The last two are flagged rho_fallback in the output.
    Only built when route_meta exists."""
    if not con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'route_meta'").fetchall()[0][0]:
        con.execute("DROP TABLE IF EXISTS gps_rho_fill")
        return
    con.execute("""CREATE OR REPLACE TABLE gps_rho_fill AS
        WITH grid AS (SELECT m.route_id, m.operator, h.hour, d.day_type FROM route_meta m,
                      range(24) h(hour), (VALUES ('weekday'), ('weekend')) d(day_type)),
        cov AS (SELECT g.*, m.operator FROM gps_route_hour g JOIN route_meta m USING (route_id)
                WHERE g.source = 'gps' AND g.scheduled_trips > 0),
        rt AS (SELECT route_id, day_type, least(1.0, sum(observed_trips / coverage) / sum(scheduled_trips)) AS rho
               FROM cov GROUP BY 1, 2),
        oh AS (SELECT operator, hour, day_type, least(1.0, sum(observed_trips / coverage) / sum(scheduled_trips)) AS rho
               FROM cov GROUP BY 1, 2, 3),
        od AS (SELECT operator, day_type, least(1.0, sum(observed_trips / coverage) / sum(scheduled_trips)) AS rho
               FROM cov GROUP BY 1, 2)
        SELECT grid.route_id, grid.hour, grid.day_type,
               coalesce(g.rho_model, rt.rho, oh.rho, od.rho, 1.0) AS rho,
               CASE WHEN g.rho_model IS NOT NULL THEN 'cell' WHEN rt.rho IS NOT NULL THEN 'route'
                    WHEN oh.rho IS NOT NULL THEN 'op_hour' WHEN od.rho IS NOT NULL THEN 'op_day' ELSE 'none' END AS rho_src
        FROM grid LEFT JOIN gps_route_hour g USING (route_id, hour, day_type)
        LEFT JOIN rt USING (route_id, day_type) LEFT JOIN oh USING (operator, hour, day_type)
        LEFT JOIN od USING (operator, day_type)""")


def run(con, paths, gps_raw: bool = False, gps_days=None, **_) -> str:
    """Stage `gps`: with --gps-raw, (re)build the aggregates for --gps-days (default: the ten sample days; days
    already done are skipped); always load the committed aggregates when present, else the model uses rho = 1."""
    if gps_raw:
        build_aggregates(list(gps_days or SAMPLE_DAYS), paths, wcon=con)
    if load_aggregates(con, paths):
        n, g = con.execute("SELECT count(*), count(rho_model) FROM gps_route_hour").fetchall()[0]
        return f"gps_route_hour {n:,} cells, {g:,} with rho"
    con.execute("DROP TABLE IF EXISTS gps_route_hour")
    con.execute("DROP TABLE IF EXISTS gps_rho_fill")
    return "no GPS aggregates: rho = 1"


def _day_file(day: str, paths) -> Path:
    return Path(paths.gps_archive).parent / "days" / f"bus_movements_{day.replace('-', '_')}.db"


def _work_dir(paths) -> Path:
    d = Path(paths.processed) / "gps_work"
    d.mkdir(parents=True, exist_ok=True)
    return d


def process_day(day: str, paths, wcon, force: bool = False) -> None:
    """Aggregate one day into <work>/<day>_trips.parquet and <day>_cov.parquet (no vehicle ids). An existing
    extracted .db is used in place and never deleted; otherwise the day is extracted from the 7z archive into a
    temp folder and that copy is deleted afterwards."""
    from .db import connect
    from .network import Clock

    work = _work_dir(paths)
    tp, cp = work / f"{day}_trips.parquet", work / f"{day}_cov.parquet"
    if tp.exists() and cp.exists() and not force:
        return
    db, tmp = _day_file(day, paths), None
    if not db.exists():
        tmp = Path(tempfile.mkdtemp(prefix="gps_extract_", dir=work))
        name = f"bus_movements_{day.replace('-', '_')}.db"
        subprocess.run(["7z", "e", f"-o{tmp}", "-y", str(paths.gps_archive), f"*{name}"], check=True,
                       stdout=subprocess.DEVNULL)
        found = list(tmp.rglob(name))
        if not found:
            raise FileNotFoundError(f"{name} not in {paths.gps_archive}")
        db = found[0]
    try:
        stops = wcon.execute("SELECT route_id, seq, lat, lon, cum_template_s FROM canonical_stops "
                             "ORDER BY route_id, seq").df()
        clock = Clock.load(wcon)
        con = connect()
        load_pings(con, db, day)
        trips = find_trips(con, stops)
        trips["run_ratio"] = run_ratio(trips, stops, clock.factor)
        linked = wcon.execute("SELECT route_id, vehicle FROM tickets_resolved WHERE date = ? AND vehicle IS NOT NULL "
                              "GROUP BY ALL", [day]).df()
        con.register("_linked", linked)
        cov = con.execute("""SELECT l.route_id::BIGINT AS route_id, count(*)::INT AS linked,
                                    count(*) FILTER (WHERE p.vehicle IS NOT NULL)::INT AS seen
                             FROM _linked l LEFT JOIN (SELECT DISTINCT vehicle FROM pings) p ON p.vehicle = l.vehicle
                             GROUP BY 1""").df()
        con.close()
        trips.drop(columns=["vehicle"]).to_parquet(tp)
        cov.to_parquet(cp)
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def scheduled_trips(wcon) -> pd.DataFrame:
    """Scheduled trips per route x hour of day (first-stop departures; the feed has one service day)."""
    return wcon.execute("""SELECT route_id::BIGINT AS route_id, ((minute % 1440) // 60)::BIGINT AS hour,
                                  count(*)::INT AS scheduled_trips
                           FROM passings WHERE seq = 1 GROUP BY 1, 2""").df()


def build_aggregates(days: list[str], paths, wcon=None, force: bool = False, log=print) -> Path:
    """Process the days (resumable) and write the committed CSV and SHA256SUMS for every day done so far."""
    import hashlib

    import duckdb
    own = wcon is None
    if own:
        wcon = duckdb.connect(str(paths.work_db), read_only=True)
        wcon.execute("SET TimeZone='Asia/Kolkata'")
    try:
        for d in days:
            log(f"gps day {d}")
            process_day(d, paths, wcon, force)
        work = _work_dir(paths)
        done = sorted(p.name.removesuffix("_trips.parquet") for p in work.glob("*_trips.parquet")
                      if (work / p.name.replace("_trips", "_cov")).exists())
        types = {str(d): t for d, t in wcon.execute("SELECT date, day_type FROM clean_days").fetchall()}
        dt = {d: types[d] for d in done if d in types}
        table = combine({d: pd.read_parquet(work / f"{d}_trips.parquet") for d in dt},
                        {d: pd.read_parquet(work / f"{d}_cov.parquet") for d in dt},
                        scheduled_trips(wcon), dt)
        outd = Path(paths.gps_aggregates)
        outd.mkdir(parents=True, exist_ok=True)
        csv = outd / CSV_NAME
        table.round(4).to_csv(csv, index=False)
        (outd / "SHA256SUMS").write_text(f"{hashlib.sha256(csv.read_bytes()).hexdigest()}  {CSV_NAME}\n")
        return csv
    finally:
        if own:
            wcon.close()
