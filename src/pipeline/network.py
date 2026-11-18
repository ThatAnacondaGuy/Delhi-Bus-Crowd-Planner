"""Stage 3: the corrected travel-time clock, scheduled passings and service hours.

The GTFS template run times are free-flow. Linked tickets (same vehicle, route and day) give observed
run times between two boarding stops, so each operator x hour gets a factor = observed / template.
Everything later asks `Clock` for timing, so one corrected clock is used throughout.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .config import (BUS_SPECS, DEVI_ROUTE_SHARE, DEVI_VEHICLE_MIN_TICKETS, EXCLUDED_DATES, EXCLUDED_WINDOWS,
                     HUB_STOP_CATEGORIES, IS_AC_MIN_TICKETS, PLACE_RADIUS_M, SERVICE_CLASS_PATTERNS)
from .errors import GateError
from .resolve import haversine_m

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


# ---------------------------------------------------------------- bus types, service class

def _devi_vehicles(con) -> None:
    con.execute(f"""
        CREATE OR REPLACE TABLE devi_vehicles AS
        SELECT t.vehicle FROM tickets_resolved t JOIN route_meta m USING (route_id)
        WHERE m.is_devi AND t.vehicle IS NOT NULL
        GROUP BY t.vehicle HAVING count(*) >= {DEVI_VEHICLE_MIN_TICKETS} ORDER BY t.vehicle""")


def build_bus_mix(con) -> None:
    """bus_mix per route_id: D- routes are 9 m; other routes follow the vehicle rule, else the is_ac mix."""
    _devi_vehicles(con)
    con.execute(f"""
        CREATE OR REPLACE TABLE bus_mix AS
        WITH v AS (
            SELECT t.route_id,
                   count(*) FILTER (WHERE t.vehicle IS NOT NULL) AS n_veh,
                   count(*) FILTER (WHERE d.vehicle IS NOT NULL) AS n_devi
            FROM tickets_resolved t LEFT JOIN devi_vehicles d ON d.vehicle = t.vehicle GROUP BY t.route_id),
        r AS (SELECT m.route_id, m.is_devi,
                     CASE WHEN v.n_veh > 0 THEN v.n_devi::DOUBLE / v.n_veh ELSE 0 END AS dshare
              FROM route_meta m LEFT JOIN v USING (route_id)),
        a AS (  -- is_ac mix over tickets not on 9 m vehicles
            SELECT t.route_id, count(t.is_ac) AS n_ac,
                   avg(CASE WHEN t.is_ac THEN 0.0 ELSE 1.0 END) AS nonac
            FROM tickets_resolved t LEFT JOIN devi_vehicles d ON d.vehicle = t.vehicle
            WHERE d.vehicle IS NULL GROUP BY t.route_id),
        j AS (SELECT r.route_id, r.is_devi, r.dshare >= {DEVI_ROUTE_SHARE} AND NOT r.is_devi AS by_vehicle,
                     r.dshare, a.n_ac, coalesce(a.nonac, 0) AS nonac
              FROM r LEFT JOIN a USING (route_id)),
        s AS (SELECT route_id, is_devi, by_vehicle, n_ac, nonac,
                     CASE WHEN is_devi THEN 1.0 WHEN by_vehicle THEN dshare ELSE 0.0 END AS s9
              FROM j)
        SELECT route_id::BIGINT AS route_id, s9::DOUBLE AS share_9m,
               CASE WHEN is_devi THEN 0.0 WHEN coalesce(n_ac, 0) >= {IS_AC_MIN_TICKETS}
                    THEN (1 - s9) * nonac ELSE 0.0 END::DOUBLE AS share_12m_nonac,
               CASE WHEN is_devi THEN 0.0 WHEN coalesce(n_ac, 0) >= {IS_AC_MIN_TICKETS}
                    THEN (1 - s9) * (1 - nonac) ELSE 1 - s9 END::DOUBLE AS share_12m_ac,
               CASE WHEN is_devi THEN 'devi_name' WHEN by_vehicle THEN 'vehicle_rule'
                    WHEN coalesce(n_ac, 0) >= {IS_AC_MIN_TICKETS} THEN 'is_ac' ELSE 'default' END AS basis
        FROM s ORDER BY route_id""")
    s9, s12, sn = (BUS_SPECS["9m_devi"], BUS_SPECS["12m_ac"], BUS_SPECS["12m_nonac"])
    con.execute(f"""
        CREATE OR REPLACE TABLE route_specs AS
        SELECT route_id,
               share_9m * {s9.seats} + share_12m_ac * {s12.seats} + share_12m_nonac * {sn.seats} AS seats,
               share_9m * {s9.rated_total} + share_12m_ac * {s12.rated_total}
                   + share_12m_nonac * {sn.rated_total} AS rated_total,
               share_9m * {s9.crush} + share_12m_ac * {s12.crush} + share_12m_nonac * {sn.crush} AS crush
        FROM bus_mix ORDER BY route_id""")


def build_service_class(con, paths) -> None:
    """service_class per GTFS route_id from SERVICE_CLASS_PATTERNS (first match; else regular)."""
    rows = con.execute("SELECT route_id::BIGINT, route_short_name, route_long_name "
                       "FROM read_csv(?, header=true, all_varchar=true)",
                       [str(Path(paths.gtfs_dir) / "routes.txt")]).fetchall()
    pats = {c: re.compile(p, re.I) for c, p in SERVICE_CLASS_PATTERNS.items()}
    out = []
    for rid, short, long_ in rows:
        names = [(short or "").strip(), (long_ or "").strip()]
        cls = next((c for c, p in pats.items() if any(p.search(n) for n in names)), "regular")
        out.append((rid, cls))
    _write(con, "service_class", pd.DataFrame(out, columns=["route_id", "class"]).astype({"route_id": "int64"}))


# ---------------------------------------------------------------- places and hub aliases

_STEM_DROP = re.compile(r"\(.*?\)|\bopp\b|\bterminal\b|\bmetro station\b|\bbus stop\b")


def name_stem(name: str) -> str:
    low = (name or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", _STEM_DROP.sub(" ", low))
    s = re.sub(r"\s+", " ", s).strip()
    return s or re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", low)).strip()


def _group_places(stops: list[tuple[str, str, float, float]]) -> dict[str, int]:
    """stop_id -> place number: same stem and within PLACE_RADIUS_M of each other (single linkage)."""
    parent = {s[0]: s[0] for s in stops}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_stem: dict[str, list] = {}
    for s in stops:
        by_stem.setdefault(name_stem(s[1]), []).append(s)
    for grp in by_stem.values():
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                if haversine_m(grp[i][2], grp[i][3], grp[j][2], grp[j][3]) <= PLACE_RADIUS_M:
                    parent[find(grp[i][0])] = find(grp[j][0])
    roots: dict[str, int] = {}
    out = {}
    for sid, *_ in sorted(stops, key=lambda s: (_stop_key(s[0]))):
        out[sid] = roots.setdefault(find(sid), len(roots) + 1)
    return out


def _stop_key(stop_id: str):
    return (0, int(stop_id), "") if stop_id.isdigit() else (1, 0, stop_id)


def _hub_place(hub_stems: list[str], stops, place_of: dict[str, int]) -> int | None:
    pats = [re.compile(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])") for s in hub_stems]
    cats = {c: re.compile(p, re.I) for c, p in HUB_STOP_CATEGORIES.items()}
    size: dict[int, int] = {}
    for s in stops:
        size[place_of[s[0]]] = size.get(place_of[s[0]], 0) + 1
    best = None
    for sid, name, _la, _lo in stops:
        stem = name_stem(name)
        full = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", name.lower())).strip()  # keeps "( Connaught Place )"
        in_stem = any(p.search(stem) for p in pats)
        if not in_stem and not any(p.search(full) for p in pats):
            continue
        pid = place_of[sid]
        rank = (any(c.search(name) for c in cats.values()), not in_stem,
                (hub_stems.index(stem) if stem in hub_stems else len(hub_stems)), -size[pid], pid)
        if best is None or rank < best[0]:
            best = (rank, pid)
    return best[1] if best else None


def build_places(con, paths) -> None:
    rows = con.execute("SELECT trim(stop_id), trim(stop_name), stop_lat::DOUBLE, stop_lon::DOUBLE "
                       "FROM read_csv(?, header=true, all_varchar=true) "
                       "WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL",
                       [str(Path(paths.gtfs_dir) / "stops.txt")]).fetchall()
    place_of = _group_places(rows)
    names: dict[int, str] = {}
    for sid, name, *_ in sorted(rows, key=lambda s: (len(s[1]), s[1])):
        names.setdefault(place_of[sid], name)
    df = pd.DataFrame([(place_of[sid], names[place_of[sid]], sid, la, lo) for sid, _n, la, lo in rows],
                      columns=["place_id", "name", "stop_id", "lat", "lon"]).astype({"place_id": "int64"})
    _write(con, "places", df.sort_values(["place_id", "stop_id"]).reset_index(drop=True))
    hubs = yaml.safe_load((Path(__file__).parent / "hubs.yaml").read_text(encoding="utf-8"))
    alias_rows, missing = {}, []
    for hub, spec in hubs.items():
        pid = _hub_place([s.lower() for s in spec["gtfs_stems"]], rows, place_of)
        if pid is None:
            missing.append(hub)
            continue
        for a in [hub.lower(), *spec.get("aliases", []), *spec["gtfs_stems"]]:
            alias_rows.setdefault(a.lower(), pid)
    _write(con, "hub_alias", pd.DataFrame(sorted(alias_rows.items()), columns=["alias", "place_id"])
           .astype({"place_id": "int64"}))
    if missing:
        print(f"network: hubs without a matching stop: {', '.join(missing)}")


# ---------------------------------------------------------------- segment shapes

def _project(pts: np.ndarray, lat0: float, k: float) -> np.ndarray:
    return np.column_stack([pts[:, 1] * k, pts[:, 0]]) * 111_195.0


def slice_segments(shape: np.ndarray, stops: np.ndarray, k_cands: int = 6) -> list[list[list[float]]]:
    """One coordinate list per consecutive stop pair. Each stop is projected onto the shape; positions along
    the shape never move backwards (dynamic programme over the nearest candidate segments)."""
    lat0 = float(np.mean(shape[:, 0]))
    k = np.cos(np.radians(lat0))
    P, Q = _project(shape, lat0, k), _project(stops, lat0, k)
    A, B = P[:-1], P[1:]
    ab = B - A
    seg_len = np.hypot(ab[:, 0], ab[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    denom = np.where(seg_len > 0, seg_len ** 2, 1.0)
    n, m = len(Q), len(A)
    cand_pos, cand_pt, cand_cost = [], [], []
    for q in Q:
        t = np.clip(((q - A) * ab).sum(1) / denom, 0.0, 1.0)
        proj = A + ab * t[:, None]
        d = np.hypot(*(proj - q).T)
        idx = np.argsort(d, kind="stable")[:k_cands]
        cand_pos.append(cum[idx] + t[idx] * seg_len[idx])
        cand_pt.append(np.column_stack([idx, t[idx]]))
        cand_cost.append(d[idx])
    cost = [cand_cost[0].copy()]
    back = []
    for i in range(1, n):
        c = np.full(len(cand_pos[i]), np.inf)
        bk = np.zeros(len(c), dtype=int)
        for b, pos in enumerate(cand_pos[i]):
            ok = cand_pos[i - 1] <= pos + 1e-6
            if ok.any():
                prev = np.where(ok, cost[-1], np.inf)
                bk[b] = int(np.argmin(prev))
                c[b] = prev[bk[b]] + cand_cost[i][b]
        if not np.isfinite(c).any():  # no monotone choice: stay on the previous position
            c = cand_cost[i] + cost[-1].min()
            bk[:] = int(np.argmin(cost[-1]))
            for b in range(len(c)):
                cand_pos[i][b] = max(cand_pos[i][b], cand_pos[i - 1][bk[b]])
        cost.append(c)
        back.append(bk)
    choice = [int(np.argmin(cost[-1]))]
    for bk in reversed(back):
        choice.append(int(bk[choice[-1]]))
    choice.reverse()
    pos = [float(cand_pos[i][c]) for i, c in enumerate(choice)]
    for i in range(1, n):
        pos[i] = max(pos[i], pos[i - 1])
    pts = []
    for i, c in enumerate(choice):
        j, t = int(cand_pt[i][c][0]), float(cand_pt[i][c][1])
        a, b = shape[j], shape[j + 1]
        pts.append(a + (b - a) * t)
    out = []
    for i in range(n - 1):
        lo = int(np.searchsorted(cum, pos[i], side="right"))
        hi = int(np.searchsorted(cum, pos[i + 1], side="left"))
        mid = [shape[v] for v in range(lo, hi) if pos[i] < cum[v] < pos[i + 1]]
        out.append([pts[i], *mid, pts[i + 1]])
    return [[[round(float(la), 6), round(float(lo_), 6)] for la, lo_ in seg] for seg in out]


def _coords_len(coords: list[list[float]]) -> float:
    return float(sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(coords, coords[1:])))


def build_segment_shapes(con, paths) -> tuple[int, int]:
    """segment_shapes for every canonical route; returns (routes with a GTFS shape, total routes)."""
    g = Path(paths.gtfs_dir)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _canon_shape AS
        WITH n AS (SELECT route_id::BIGINT AS route_id, trim(trip_id) AS trip_id, trim(shape_id) AS shape_id
                   FROM read_csv(?, header=true, all_varchar=true)),
        c AS (SELECT trim(trip_id) AS trip_id, count(*) AS n FROM read_csv(?, header=true, all_varchar=true)
              GROUP BY ALL)
        SELECT n.route_id, n.shape_id FROM n JOIN c USING (trip_id)
        QUALIFY row_number() OVER (PARTITION BY n.route_id ORDER BY c.n DESC, n.trip_id) = 1""",
                [str(g / "trips.txt"), str(g / "stop_times.txt")])
    shp = con.execute("""
        SELECT trim(shape_id) AS shape_id, shape_pt_lat::DOUBLE AS shape_pt_lat,
               shape_pt_lon::DOUBLE AS shape_pt_lon
        FROM read_csv(?, header=true, all_varchar=true)
        ORDER BY shape_id, shape_pt_sequence::INT""", [str(g / "shapes.txt")]).df()
    shapes = {sid: grp[["shape_pt_lat", "shape_pt_lon"]].to_numpy() for sid, grp in shp.groupby("shape_id")}
    sid_of = dict(con.execute("SELECT route_id, shape_id FROM _canon_shape").fetchall())
    stops = con.execute("SELECT route_id, lat, lon FROM canonical_stops ORDER BY route_id, seq").df()
    rows, with_shape, total = [], 0, 0
    for rid, grp in stops.groupby("route_id"):
        pts = grp[["lat", "lon"]].to_numpy()
        if len(pts) < 2:
            continue
        total += 1
        shape = shapes.get(sid_of.get(int(rid)))
        if shape is not None and len(shape) >= 2:
            with_shape += 1
            segs = slice_segments(shape, pts)
        else:
            segs = [[[round(float(a[0]), 6), round(float(a[1]), 6)], [round(float(b[0]), 6), round(float(b[1]), 6)]]
                    for a, b in zip(pts, pts[1:])]
        for seq, coords in enumerate(segs, 2):
            rows.append((int(rid), seq, json.dumps(coords), _coords_len(coords)))
    df = pd.DataFrame(rows, columns=["route_id", "seq", "coords", "length_m"]).astype(
        {"route_id": "int64", "seq": "int32", "length_m": "float64"})
    _write(con, "segment_shapes", df)
    return with_shape, total


def run_network(con, paths, **kwargs) -> ClockStats:
    stats = run_clock(con, paths, **kwargs)
    build_bus_mix(con)
    build_service_class(con, paths)
    build_places(con, paths)
    with_shape, total = build_segment_shapes(con, paths)
    mix = con.execute("SELECT basis, count(*), sum((share_9m = 1)::INT) FROM bus_mix GROUP BY basis "
                      "ORDER BY basis").fetchall()
    classes = con.execute('SELECT "class", count(*) FROM service_class GROUP BY 1 ORDER BY 1').fetchall()
    n_places = con.execute("SELECT count(DISTINCT place_id), count(*) FROM places").fetchall()[0]
    dq = [(f"bus_mix_{b}", n) for b, n, _ in mix] + [(f"service_class_{c}", n) for c, n in classes] + [
        ("places", n_places[0]), ("place_stops", n_places[1]), ("shapes_with_gtfs_shape", with_shape),
        ("shapes_routes", total)]
    _write(con, "dq_network", pd.DataFrame(dq, columns=["name", "value"]).astype({"value": float}))
    print(f"network: bus mix {dict((b, n) for b, n, _ in mix)}; service classes {dict(classes)}; "
          f"{n_places[0]:,} places from {n_places[1]:,} stops; shapes {with_shape:,}/{total:,} routes")
    return stats
