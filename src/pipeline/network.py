"""Stage 3: the corrected travel-time clock, scheduled passings and service hours.

The GTFS template run times are free-flow. Linked tickets (same vehicle, route and day) give observed
run times between two boarding stops, so each operator x hour gets a factor = observed / template.
Everything later asks `Clock` for timing, so one corrected clock is used throughout.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import EXCLUDED_DATES, EXCLUDED_WINDOWS
from .errors import GateError

MIN_ROUTE_PAIRS = 30        # route-scope factor is used only with at least this many pairs
MIN_TEMPLATE_S = 600        # pairs shorter than this (template seconds) are ignored
PAIR_RATIO_BOUNDS = (0.4, 2.5)  # observed / template outside this (symmetric in log) is another trip or a batch print
MIN_TICKET_DATES = 3        # an hour joins a route's service hours with tickets on this many clean dates
GATE_TOLERANCE = 0.15
GATE_MIN_PAIRS = 30         # operator x hour cells with fewer pairs are too noisy to gate


@dataclass
class ClockStats:
    pairs: int
    operator_factors: int
    route_factors: int
    passings: int
    fallback_cells: int
    gate_cells: int
    gate_max_dev: float

    def __str__(self) -> str:
        return (f"{self.pairs:,} ticket pairs, {self.operator_factors} operator and {self.route_factors} "
                f"route factors, {self.passings:,} passings, {self.fallback_cells} operator-hour fallbacks, "
                f"gate {self.gate_cells} cells max deviation {self.gate_max_dev:.1%}")


class Clock:
    """Template run times scaled by operator/route x hour factors."""

    def __init__(self, tmpl: dict[int, np.ndarray], operator: dict[int, str],
                 op_factor: dict[str, list[float]], route_factor: dict[int, dict[int, float]], fallbacks: int):
        self._tmpl, self._operator = tmpl, operator
        self._op, self._route = op_factor, route_factor
        self.fallbacks = fallbacks  # operator x hour cells filled by R10 (nearest hour, else 1.0)
        self._table: dict[int, list[float]] = {}

    @classmethod
    def from_frames(cls, canonical: pd.DataFrame, factors: pd.DataFrame) -> "Clock":
        tmpl, operator = {}, {}
        for rid, g in canonical.sort_values(["route_id", "seq"]).groupby("route_id"):
            tmpl[int(rid)] = g["template_s"].to_numpy(dtype=float)
            operator[int(rid)] = g["operator"].iloc[0]
        op_raw: dict[str, dict[int, float]] = {}
        route: dict[int, dict[int, float]] = {}
        for scope, key, hour, factor, n in factors[["scope", "key", "hour", "factor", "n_pairs"]].itertuples(index=False):
            if scope == "operator":
                op_raw.setdefault(key, {})[int(hour)] = float(factor)
            elif n >= MIN_ROUTE_PAIRS:
                route.setdefault(int(key), {})[int(hour)] = float(factor)
        op_factor, fallbacks = {}, 0
        for op in sorted(set(operator.values()) | set(op_raw)):
            have = op_raw.get(op, {})
            row = []
            for h in range(24):
                if h in have:
                    row.append(have[h])
                    continue
                fallbacks += 1
                near = min(have, key=lambda k: (abs(k - h), k)) if have else None
                row.append(have[near] if near is not None else 1.0)
            op_factor[op] = row
        return cls(tmpl, operator, op_factor, route, fallbacks)

    @classmethod
    def load(cls, con) -> "Clock":
        canon = con.execute("SELECT route_id, seq, template_s, operator FROM canonical_stops").df()
        fac = con.execute("SELECT scope, key, hour, factor, n_pairs FROM runtime_factors").df()
        return cls.from_frames(canon, fac)

    def hour_factors(self, route_id: int) -> list[float]:
        """The 24 factors for a route (route factor where it has >= 30 pairs, else its operator's)."""
        t = self._table.get(route_id)
        if t is None:
            op = self._op.get(self._operator.get(route_id), [1.0] * 24)
            rf = self._route.get(route_id, {})
            t = self._table[route_id] = [rf.get(h, op[h]) for h in range(24)]
        return t

    def factor(self, route_id: int, hour: int) -> float:
        return self.hour_factors(int(route_id))[int(hour) % 24]

    def template(self, route_id: int, seq: int) -> float:
        """Template seconds of the segment ending at seq; on a ring, seq past N wraps round the route."""
        t = self._tmpl[route_id]
        n = len(t)
        v = t[(seq - 1) % n]
        if v == 0 and seq > 1:
            nz = t[t > 0]
            v = nz.mean() if len(nz) else 0.0  # the unrecorded closing segment of a ring
        return float(v)

    def travel_seconds(self, route_id: int, from_seq: int, to_seq: int, start_minute: float) -> float:
        route_id = int(route_id)
        fac = self.hour_factors(route_id)
        t, total = float(start_minute), 0.0
        for seq in range(from_seq + 1, to_seq + 1):
            s = self.template(route_id, seq) * fac[int(t // 60) % 24]
            total += s
            t += s / 60.0
        return total


# ---------------------------------------------------------------- pairs and factors

def _exclusions(con) -> None:
    con.execute("CREATE OR REPLACE TEMP TABLE _excl AS SELECT * FROM (VALUES "
                + ",".join(["(?::TIMESTAMPTZ, ?::TIMESTAMPTZ)"] * len(EXCLUDED_WINDOWS)) + ") t(a, b)",
                [x.isoformat() for w in EXCLUDED_WINDOWS for x in w])
    con.execute("CREATE OR REPLACE TEMP TABLE _clean_tix AS "
                "SELECT t.* FROM tickets_resolved t JOIN clean_days d ON d.date = t.date "
                "WHERE NOT d.is_excluded_date AND NOT EXISTS (SELECT 1 FROM _excl e WHERE t.ts >= e.a AND t.ts < e.b)")


def _build_pairs(con) -> pd.DataFrame:
    lo, hi = PAIR_RATIO_BOUNDS
    return con.execute(f"""
        WITH p AS (
            SELECT route_id, vehicle, orig_seq, ts,
                   lag(orig_seq) OVER w AS prev_seq, lag(ts) OVER w AS prev_ts
            FROM _clean_tix WHERE vehicle IS NOT NULL
            WINDOW w AS (PARTITION BY vehicle, route_id, date ORDER BY ts, ticket_id)),
        q AS (
            SELECT p.route_id, c1.operator, p.prev_seq, p.orig_seq,
                   epoch(p.ts) - epoch(p.prev_ts) AS observed_s,
                   (c2.cum_template_s - c1.cum_template_s)::DOUBLE AS expected_s,
                   hour(timezone('Asia/Kolkata', p.prev_ts)) AS hour,
                   hour(timezone('Asia/Kolkata', p.prev_ts)) * 60
                     + minute(timezone('Asia/Kolkata', p.prev_ts))
                     + second(timezone('Asia/Kolkata', p.prev_ts)) / 60.0 AS start_minute
            FROM p JOIN canonical_stops c1 ON c1.route_id = p.route_id AND c1.seq = p.prev_seq
                   JOIN canonical_stops c2 ON c2.route_id = p.route_id AND c2.seq = p.orig_seq
            WHERE p.orig_seq > p.prev_seq)
        SELECT * FROM q WHERE expected_s >= {MIN_TEMPLATE_S}
          AND observed_s / expected_s BETWEEN {lo} AND {hi}""").df()


def _factor_rows(pairs: pd.DataFrame) -> pd.DataFrame:
    out = []
    for scope, col in (("operator", "operator"), ("route", "route_id")):
        g = pairs.groupby([col, "hour"]).agg(obs=("observed_s", "sum"), exp=("expected_s", "sum"),
                                              n=("observed_s", "size")).reset_index()
        out.append(pd.DataFrame({"scope": scope, "key": g[col].astype(str), "hour": g["hour"].astype(int),
                                 "factor": g["obs"] / g["exp"], "n_pairs": g["n"].astype(int)}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _gate(clock: Clock, pairs: pd.DataFrame) -> tuple[int, float]:
    """Modelled vs observed pair time per operator x hour (cells with >= GATE_MIN_PAIRS pairs)."""
    if pairs.empty:
        return 0, 0.0
    cache: dict[tuple, float] = {}
    model = []
    for r in pairs[["route_id", "prev_seq", "orig_seq", "start_minute"]].itertuples(index=False):
        k = (r.route_id, r.prev_seq, r.orig_seq, round(r.start_minute, 1))
        v = cache.get(k)
        if v is None:
            v = cache[k] = clock.travel_seconds(r.route_id, r.prev_seq, r.orig_seq, r.start_minute)
        model.append(v)
    df = pairs.assign(model_s=model)
    g = df.groupby(["operator", "hour"]).agg(obs=("observed_s", "sum"), mod=("model_s", "sum"),
                                              n=("observed_s", "size")).reset_index()
    g = g[g["n"] >= GATE_MIN_PAIRS]
    if g.empty:
        return 0, 0.0
    dev = (g["mod"] / g["obs"] - 1).abs()
    bad = g[dev > GATE_TOLERANCE]
    if len(bad):
        cells = ", ".join(f"{r.operator} {r.hour:02d}h model/observed {r.mod / r.obs:.2f}" for r in bad.itertuples())
        raise GateError(f"clock gate: modelled pair time off by more than {GATE_TOLERANCE:.0%} in {cells}")
    return len(g), float(dev.max())


# ---------------------------------------------------------------- passings, service hours

def _passings(con, paths, clock: Clock) -> pd.DataFrame:
    g = Path(paths.gtfs_dir)
    starts = con.execute("""
        WITH tr AS (SELECT route_id::BIGINT AS route_id, trim(trip_id) AS trip_id
                    FROM read_csv(?, header=true, all_varchar=true)),
        st AS (SELECT trim(trip_id) AS trip_id, split_part(trim(departure_time), ':', 1)::INT * 60
                        + split_part(trim(departure_time), ':', 2)::INT
                        + split_part(trim(departure_time), ':', 3)::INT / 60.0 AS dep_min,
                      stop_sequence::INT AS sq, count(*) OVER (PARTITION BY trim(trip_id)) AS n
               FROM read_csv(?, header=true, all_varchar=true))
        SELECT route_id, dep_min, n FROM tr JOIN st USING (trip_id)
        QUALIFY row_number() OVER (PARTITION BY trip_id ORDER BY sq) = 1""",
        [str(g / "trips.txt"), str(g / "stop_times.txt")]).df()
    frames = []
    for rid, grp in starts.groupby("route_id"):
        rid = int(rid)
        if rid not in clock._tmpl:
            continue
        fac = np.array(clock.hour_factors(rid))
        n_stops = grp["n"].to_numpy()
        t = grp["dep_min"].to_numpy(dtype=float)
        for seq in range(1, len(clock._tmpl[rid]) + 1):
            if seq > 1:
                t = t + clock.template(rid, seq) * fac[(t // 60).astype(int) % 24] / 60.0
            keep = n_stops >= seq
            if keep.any():
                frames.append(pd.DataFrame({"route_id": rid, "seq": seq,
                                            "minute": np.floor(t[keep] + 0.5).astype(int)}))
    out = pd.concat(frames, ignore_index=True)
    out["route_id"] = out["route_id"].astype("int64")
    out["seq"] = out["seq"].astype("int32")
    out["minute"] = out["minute"].astype("int32")
    return out


def _service_hours(con) -> None:
    con.execute(f"""
        CREATE OR REPLACE TABLE service_hours AS
        WITH th AS (
            SELECT route_id, hour(timezone('Asia/Kolkata', ts)) AS h FROM _clean_tix
            GROUP BY route_id, h HAVING count(DISTINCT date) >= {MIN_TICKET_DATES}),
        thl AS (SELECT route_id, string_agg(h::VARCHAR, ',' ORDER BY h) AS ticket_hours FROM th GROUP BY route_id),
        sched AS (SELECT route_id, min(minute) AS first_min, max(minute) AS last_min FROM passings GROUP BY route_id)
        SELECT s.route_id::BIGINT AS route_id, s.first_min::INT AS first_min, s.last_min::INT AS last_min,
               coalesce(t.ticket_hours, '') AS ticket_hours
        FROM sched s LEFT JOIN thl t USING (route_id) ORDER BY route_id""")


def _write(con, name: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
    con.unregister("_df")


def run_clock(con, paths, **_) -> ClockStats:
    _exclusions(con)
    pairs = _build_pairs(con)
    n_pairs = len(pairs)
    fac = _factor_rows(pairs)
    if fac.empty:
        fac = pd.DataFrame({"scope": pd.Series(dtype=str), "key": pd.Series(dtype=str),
                            "hour": pd.Series(dtype="int32"), "factor": pd.Series(dtype=float),
                            "n_pairs": pd.Series(dtype="int32")})
    _write(con, "runtime_factors", fac.astype({"hour": "int32", "n_pairs": "int32"}))
    clock = Clock.load(con)
    gate_cells, gate_dev = _gate(clock, pairs)
    _write(con, "passings", _passings(con, paths, clock))
    _service_hours(con)
    stats = ClockStats(
        pairs=n_pairs, operator_factors=int((fac["scope"] == "operator").sum()),
        route_factors=int(((fac["scope"] == "route") & (fac["n_pairs"] >= MIN_ROUTE_PAIRS)).sum()),
        passings=con.execute("SELECT count(*) FROM passings").fetchall()[0][0],
        fallback_cells=clock.fallbacks, gate_cells=gate_cells, gate_max_dev=gate_dev)
    dq = [("pairs", n_pairs), ("fallback_cells", clock.fallbacks), ("gate_cells", gate_cells),
          ("gate_max_dev", gate_dev), ("passings", stats.passings)]
    _write(con, "dq_clock", pd.DataFrame(dq, columns=["name", "value"]).astype({"value": float}))
    for op, h, f, n in con.execute("SELECT key, hour, factor, n_pairs FROM runtime_factors "
                                   "WHERE scope='operator' AND hour IN (8, 18) ORDER BY key, hour").fetchall():
        print(f"network: {op} {h:02d}h factor {f:.3f} ({n:,} pairs)")
    print(f"network: {stats}")
    return stats
