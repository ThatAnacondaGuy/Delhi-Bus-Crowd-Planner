"""Stage 4: app riders on every route stretch at on-board time, with the terminal
alighting correction.

Each resolved ticket is placed on the stretches between its boarding and alighting stops. Stretch k
(stop k to k+1) is occupied at purchase time + corrected run time from the boarding stop (Clock), so
a rider counts where the bus really is. App tickets end at route terminals about twice as often as
they start there (people buy near the end of a ride), so terminal alightings are capped at the reverse
route's terminal boardings times the intermediate-stop ratio (ruling R11) and the excess is spread over
earlier stops of the same fare slab in proportion to the reverse direction's boardings.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .clean import excluded
from .config import (ALIGHTING_LAST_STRETCHES, ALIGHTING_MIN_REVERSE_BOARD, BOUND_MIN_TICKETS, BOUND_PERCENTILE,
                     CORRIDOR_SIMPLIFY_M, EXCLUDED_DATES, EXCLUDED_WINDOWS, LOW_APP_USE_FRACTION,
                     NO_DATA_PERCENTILE, PLANNER_TABLES, PUBLISHED_RIDERSHIP, S0_MAX_SHARE, SCALE_RANGE,
                     SEATS_FRACTION, SUPPLY_WIDEN_MIN, WINDOWS)
from .errors import GateError
from .network import Clock

RATIO_CLAMP = (0.5, 2.0)    # R11: intermediate-stop ratio bounds
GATE_TOLERANCE = 0.005      # rider-minutes balance within 0.5%


@dataclass
class RiderStats:
    tickets: int
    rows: int
    ticket_rm: float
    excluded_rm: float
    moved_rm: float
    moved_pax: float
    terminal_rows: int
    corrected_routes: int
    alighting_sensitive: int
    gate_dev: float

    def __str__(self) -> str:
        return (f"{self.tickets:,} tickets on {self.rows:,} stretch rows, rider-minutes {self.ticket_rm:,.0f} "
                f"(excluded {self.excluded_rm:,.0f}, moved {self.moved_rm:,.0f}), gate deviation "
                f"{self.gate_dev:.4%}; {self.terminal_rows} terminal rows, {self.corrected_routes} routes corrected "
                f"({self.moved_pax:,.0f} pax moved), {self.alighting_sensitive} alighting-sensitive")


def _naive(dt) -> str:
    return dt.replace(tzinfo=None).isoformat(sep=" ")


def _excluded_sql(ts: str, day: str) -> str:
    """SQL boolean: the instant `ts` (naive IST TIMESTAMP) is on an excluded date or in a half-open window."""
    dates = ", ".join(f"DATE '{d}'" for d in EXCLUDED_DATES)
    wins = " OR ".join(f"({ts} >= TIMESTAMP '{_naive(a)}' AND {ts} < TIMESTAMP '{_naive(b)}')"
                       for a, b in EXCLUDED_WINDOWS)
    return f"({day} IN ({dates}) OR {wins})"


def _has(con, table: str) -> bool:
    return con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                       [table]).fetchall()[0][0] > 0


def _day_type(col: str) -> str:
    return f"CASE WHEN isodow({col}) >= 6 THEN 'weekend' ELSE 'weekday' END"


# ---------------------------------------------------------------- clock tables

def _clock_tables(con, clock: Clock) -> None:
    """_q(route_id, k, q): cumulative corrected-clock template seconds from stop 1 to stop k (ring-aware),
    _fh(route_id, hour, factor)."""
    mx = dict(con.execute("SELECT route_id, greatest(max(dest_seq), max(orig_seq)) FROM _rt GROUP BY 1").fetchall())
    n = dict(con.execute("SELECT route_id, n_stops FROM route_meta").fetchall())
    rids, ks, qs, frid, fh, ff = [], [], [], [], [], []
    for rid, m in mx.items():
        top = max(m, n.get(rid, 0)) + 1
        seg = np.array([0.0] + [clock.template(rid, s) for s in range(2, top + 1)])
        q = np.concatenate([[0.0], np.cumsum(seg)])[1:]       # q[k-1] = seconds to stop k
        rids.append(np.full(top, rid))
        ks.append(np.arange(1, top + 1))
        qs.append(q)
        frid.append(np.full(24, rid))
        fh.append(np.arange(24))
        ff.append(np.array(clock.hour_factors(rid)))
    _q = pd.DataFrame({"route_id": np.concatenate(rids), "k": np.concatenate(ks), "q": np.concatenate(qs)})
    _fh = pd.DataFrame({"route_id": np.concatenate(frid), "hour": np.concatenate(fh).astype(int),
                        "factor": np.concatenate(ff)})
    for name, df in (("_q", _q), ("_fh", _fh)):
        con.register("_df", df)
        con.execute(f"CREATE OR REPLACE TEMP TABLE {name} AS SELECT * FROM _df")
        con.unregister("_df")


def _exact_ticket_rm(clock: Clock, cols: dict) -> float:
    """Rider-minutes of every ticket by stepping the Clock stretch by stretch (numpy over tickets per route);
    independent of the SQL expansion."""
    total = 0.0
    df = pd.DataFrame(cols)
    for rid, g in df.groupby("route_id"):
        o, d, t, p = (g[c].to_numpy() for c in ("orig_seq", "dest_seq", "m0", "pax"))
        top = int(d.max()) + 1
        tmpl = np.array([0.0] + [clock.template(int(rid), s) for s in range(1, top + 1)])
        fac = np.array(clock.hour_factors(int(rid)))
        pos, secs = o.astype(int).copy(), np.zeros(len(g))
        tt = t.astype(float).copy()
        for _ in range(int((d - o).max())):
            act = pos < d
            if not act.any():
                break
            s = tmpl[np.minimum(pos + 1, top)] * fac[(tt // 60).astype(int) % 24]
            s = np.where(act, s, 0.0)
            secs += s
            tt += s / 60.0
            pos = pos + act
        total += float((secs * p).sum() / 60.0)
    return total


# ---------------------------------------------------------------- correction inputs

def _prepare(con) -> None:
    ex = _excluded_sql("lts", "date")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _rt AS
        SELECT *, {ex} AS ex0 FROM (
            SELECT t.ticket_id, t.route_id, t.orig_seq, t.dest_seq, t.pax, t.date, t.is_ac,
                   round(t.amount / nullif(t.pax, 0), 2) AS fare,
                   CAST(timezone('Asia/Kolkata', t.ts) AS TIMESTAMP) AS lts,
                   extract(epoch FROM (CAST(timezone('Asia/Kolkata', t.ts) AS TIMESTAMP)
                                       - CAST(t.date AS TIMESTAMP))) / 60.0 AS m0
            FROM tickets_resolved t WHERE t.dest_seq > t.orig_seq)""")
    if _has(con, "places"):
        pk = "SELECT stop_id, min(place_id)::VARCHAR AS pkey FROM places GROUP BY stop_id"
    else:
        pk = "SELECT DISTINCT stop_id, 'S:' || stop_id AS pkey FROM canonical_stops"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _cs AS
        SELECT c.route_id, c.seq, coalesce(p.pkey, 'S:' || c.stop_id) AS pkey
        FROM canonical_stops c LEFT JOIN ({pk}) p USING (stop_id)""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _bd AS
        SELECT t.route_id, c.pkey, sum(t.pax) AS pax
        FROM _rt t JOIN _cs c ON c.route_id = t.route_id AND c.seq = t.orig_seq
        WHERE NOT t.ex0 GROUP BY 1, 2""")


def _asymmetry(con, correct: bool) -> None:
    """_ta: per route with terminal alightings, the R11 figures and the move target."""
    lo, hi = RATIO_CLAMP
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _ta AS
        WITH rm AS (SELECT route_id, n_stops, opposite_route_id AS opp FROM route_meta),
        tt AS (SELECT t.route_id, sum(t.pax) AS t_alight FROM _rt t JOIN rm USING (route_id)
               WHERE NOT t.ex0 AND t.dest_seq = rm.n_stops GROUP BY 1),
        b1 AS (SELECT route_id, sum(pax) AS b FROM _rt WHERE NOT ex0 AND orig_seq = 1 GROUP BY 1),
        btot AS (SELECT route_id, sum(pax) AS tot FROM _rt WHERE NOT ex0 GROUP BY 1),
        al AS (SELECT t.route_id, sum(t.pax) AS num FROM _rt t JOIN rm USING (route_id)
               WHERE NOT t.ex0 AND t.dest_seq BETWEEN 2 AND rm.n_stops - 1 GROUP BY 1),
        dn AS (SELECT c.route_id, sum(coalesce(bd.pax, 0)) AS den
               FROM _cs c JOIN rm USING (route_id) LEFT JOIN _bd bd ON bd.route_id = rm.opp AND bd.pkey = c.pkey
               WHERE c.seq BETWEEN 2 AND rm.n_stops - 1 GROUP BY 1)
        SELECT tt.route_id, rm.n_stops, rm.opp, tt.t_alight::DOUBLE AS t_alight,
               coalesce((SELECT b FROM b1 WHERE b1.route_id = rm.opp) >= {ALIGHTING_MIN_REVERSE_BOARD}, false) AS known,
               (SELECT b FROM b1 WHERE b1.route_id = rm.opp) AS rev_board,
               CASE WHEN coalesce(dn.den, 0) > 0 AND coalesce(al.num, 0) > 0
                    THEN least(greatest(al.num / dn.den, {lo}), {hi}) ELSE 1.0 END AS ratio
        FROM tt JOIN rm USING (route_id) LEFT JOIN btot USING (route_id) LEFT JOIN al USING (route_id)
        LEFT JOIN dn USING (route_id)""")
    con.execute(f"""
        ALTER TABLE _ta ADD COLUMN move DOUBLE;
        UPDATE _ta SET move = CASE WHEN {str(correct).upper()} AND known
                                   THEN greatest(t_alight - coalesce(rev_board, 0) * ratio, 0) ELSE 0 END""")


def _prepare_moves(con) -> None:
    """Fare-slab candidate stops, reverse-boarding weights and the per-route moved fraction."""
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _mv0 AS
        SELECT route_id, n_stops, move FROM _ta WHERE move > 0""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _w AS
        SELECT c.route_id, c.seq,
               sum(CASE WHEN c.seq BETWEEN 2 AND m.n_stops - 1 THEN coalesce(bd.pax, 0) ELSE 0 END)
                   OVER (PARTITION BY c.route_id ORDER BY c.seq) AS s,
               sum(CASE WHEN c.seq BETWEEN 2 AND m.n_stops - 1 THEN 1 ELSE 0 END)
                   OVER (PARTITION BY c.route_id ORDER BY c.seq) AS u
        FROM _cs c JOIN _mv0 m USING (route_id) JOIN _ta a ON a.route_id = c.route_id
        LEFT JOIN _bd bd ON bd.route_id = a.opp AND bd.pkey = c.pkey""")
    # Fare of each (route, from, to, AC) pair: median per-passenger fare. A ticket to the terminal can
    # alight at any earlier stop after the last stop that is known to cost less: same slab.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _pf AS
        SELECT t.route_id, t.orig_seq, t.dest_seq, t.is_ac, median(t.fare) AS fare
        FROM _rt t JOIN _mv0 m USING (route_id)
        WHERE NOT t.ex0 AND t.fare > 0 AND t.dest_seq < m.n_stops GROUP BY ALL""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _tj AS
        WITH k AS (SELECT DISTINCT t.route_id, t.orig_seq, coalesce(t.fare, 0) AS fare, t.is_ac, m.n_stops
                   FROM _rt t JOIN _mv0 m USING (route_id) WHERE t.dest_seq = m.n_stops),
        j AS (SELECT k.route_id, k.orig_seq, k.fare, k.is_ac, k.n_stops,
                     greatest(coalesce(max(CASE WHEN p.fare < k.fare - 0.005 THEN p.dest_seq END), 0),
                              k.orig_seq) AS jj
              FROM k LEFT JOIN _pf p ON p.route_id = k.route_id AND p.orig_seq = k.orig_seq AND p.is_ac = k.is_ac
              GROUP BY k.route_id, k.orig_seq, k.fare, k.is_ac, k.n_stops)
        SELECT j.route_id, j.orig_seq, j.fare, j.is_ac, j.jj AS jj, j.n_stops,
               (a.s - sj.s) <= 0 AS use_u,
               CASE WHEN (a.s - sj.s) <= 0 THEN sj.u ELSE sj.s END AS sj,
               CASE WHEN (a.s - sj.s) <= 0 THEN a.u - sj.u ELSE a.s - sj.s END AS den
        FROM j JOIN _w a ON a.route_id = j.route_id AND a.seq = j.n_stops - 1
        JOIN _w sj ON sj.route_id = j.route_id AND sj.seq = j.jj
        WHERE j.jj < j.n_stops - 1""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _mv AS
        WITH tm AS (SELECT t.route_id, sum(t.pax) AS t_mov
                    FROM _rt t JOIN _tj j ON j.route_id = t.route_id AND j.orig_seq = t.orig_seq
                         AND j.fare = coalesce(t.fare, 0) AND j.is_ac = t.is_ac
                    WHERE NOT t.ex0 AND t.dest_seq = j.n_stops GROUP BY 1)
        SELECT m.route_id, tm.t_mov, least(1.0, m.move / tm.t_mov) AS m
        FROM _mv0 m JOIN tm USING (route_id) WHERE tm.t_mov > 0""")


def _write_asymmetry(con, correct: bool) -> int:
    con.execute("""
        CREATE OR REPLACE TABLE terminal_asymmetry AS
        SELECT a.route_id, a.t_alight AS terminal_alight,
               CASE WHEN a.known THEN coalesce(a.rev_board, 0) END::DOUBLE AS reverse_terminal_board,
               CASE WHEN a.known THEN a.ratio END::DOUBLE AS ratio,
               coalesce(v.t_mov * v.m, 0)::DOUBLE AS moved_pax,
               NOT a.known AS alighting_sensitive
        FROM _ta a LEFT JOIN _mv v USING (route_id) ORDER BY a.route_id""")
    return con.execute("SELECT count(*) FROM terminal_asymmetry").fetchall()[0][0]


# ---------------------------------------------------------------- expansion

def _expand_day(con, day, ex_sql: str) -> tuple[float, float, float]:
    """Expand one date's tickets onto stretches; append kept rows to _sr_stage and return
    (excluded_rm, moved_rm, total_rm)."""
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _y AS
        WITH t AS (
            SELECT r.route_id, r.date, r.pax, r.m0, r.orig_seq, r.dest_seq, r.n_stops, r.is_ring, r.mv, r.jj,
                   r.use_u, r.sj, r.den, unnest(range(r.orig_seq, r.dest_seq)) AS k
            FROM _rtj r WHERE r.date = ?),
        x AS (
            SELECT t.*, t.m0 + f0.factor * (q1.q - q0.q) / 60.0 AS mk, (q2.q - q1.q) AS seg,
                   CASE WHEN t.mv > 0 AND t.k > t.jj
                        THEN 1.0 - t.mv * ((CASE WHEN t.use_u THEN w.u ELSE w.s END) - t.sj) / t.den
                        ELSE 1.0 END AS wt
            FROM t
            JOIN _fh f0 ON f0.route_id = t.route_id AND f0.hour = least(floor(t.m0 / 60)::INT, 23)
            JOIN _q q0 ON q0.route_id = t.route_id AND q0.k = t.orig_seq
            JOIN _q q1 ON q1.route_id = t.route_id AND q1.k = t.k
            JOIN _q q2 ON q2.route_id = t.route_id AND q2.k = t.k + 1
            LEFT JOIN _w w ON w.route_id = t.route_id AND w.seq = t.k)
        SELECT x.route_id,
               CASE WHEN x.is_ring AND x.k > x.n_stops - 1 THEN x.k - (x.n_stops - 1) ELSE x.k END::INT AS seq,
               x.date AS d0, x.mk, x.pax, x.wt, x.seg * f1.factor / 60.0 AS dur,
               CAST(x.date AS TIMESTAMP) + to_seconds(floor(x.mk * 60)::BIGINT) AS inst
        FROM x JOIN _fh f1 ON f1.route_id = x.route_id AND f1.hour = floor(x.mk / 60)::INT % 24""", [day])
    con.execute(f"""
        INSERT INTO _sr_stage
        SELECT route_id, seq, dd AS date, {_day_type('dd')} AS day_type,
               (floor(mk) - 1440 * (dd - d0))::INT AS minute,
               sum(pax * wt) AS pax, count(*)::INT AS tickets, bool_or(wt < 1.0) AS corrected
        FROM (SELECT *, CAST(inst AS DATE) AS dd FROM _y) WHERE NOT {_excluded_sql('inst', 'dd')}
        GROUP BY route_id, seq, dd, d0, floor(mk)""")
    return con.execute(f"""
        SELECT coalesce(sum(CASE WHEN {_excluded_sql('inst', 'CAST(inst AS DATE)')} THEN pax * wt * dur END), 0),
               coalesce(sum(pax * (1.0 - wt) * dur), 0), coalesce(sum(pax * dur), 0)
        FROM _y""").fetchall()[0]


def _stretch_rm(con, clock: Clock) -> float:
    """Rider-minutes in stretch_riders: pax x the stretch's corrected run time at its on-board hour."""
    rows = []
    for rid, n in con.execute("SELECT route_id, max(seq) FROM stretch_riders GROUP BY 1").fetchall():
        fac = clock.hour_factors(rid)
        for seq in range(1, n + 1):
            t = clock.template(rid, seq + 1)
            rows += [(rid, seq, h, t * fac[h] / 60.0) for h in range(24)]
    con.register("_df", pd.DataFrame(rows, columns=["route_id", "seq", "hour", "dur"]))
    try:
        return con.execute("""
            SELECT coalesce(sum(s.pax * g.dur), 0) FROM stretch_riders s
            JOIN _df g ON g.route_id = s.route_id AND g.seq = s.seq AND g.hour = (s.minute // 60) % 24""").fetchall()[0][0]
    finally:
        con.unregister("_df")


def check_rider_gate(con, clock: Clock | None = None, tolerance: float | None = None) -> float:
    """Rider-minutes in stretch_riders + excluded + moved must equal the resolved tickets' rider-minutes
    (same clock, stepped independently) within the tolerance; returns the relative deviation."""
    tol = GATE_TOLERANCE if tolerance is None else tolerance
    clock = clock or Clock.load(con)
    dq = dict(con.execute("SELECT name, value FROM dq_riders").fetchall())
    got = _stretch_rm(con, clock) + dq["excluded_rm"] + dq["moved_rm"]
    want = dq["ticket_rm"]
    dev = abs(got / want - 1) if want else 0.0
    if dev > tol:
        raise GateError(f"riders gate: stretch rider-minutes {got:,.0f} (incl. excluded and moved) vs resolved "
                        f"tickets {want:,.0f}, off by {dev:.2%} (limit {tol:.1%})")
    return dev


def run_riders(con, paths=None, correct_alighting: bool = True, **_) -> RiderStats:
    clock = Clock.load(con)
    _prepare(con)
    _clock_tables(con, clock)
    _asymmetry(con, correct_alighting)
    _prepare_moves(con)
    terminal_rows = _write_asymmetry(con, correct_alighting)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _rtj AS
        SELECT t.route_id, t.date, t.pax, t.m0, t.orig_seq, t.dest_seq, m.n_stops, m.is_ring,
               CASE WHEN j.route_id IS NOT NULL THEN v.m ELSE 0.0 END AS mv,
               coalesce(j.jj, 0) AS jj, coalesce(j.use_u, false) AS use_u, coalesce(j.sj, 0) AS sj,
               coalesce(j.den, 1) AS den
        FROM _rt t JOIN route_meta m USING (route_id)
        LEFT JOIN _mv v ON v.route_id = t.route_id AND t.dest_seq = m.n_stops
        LEFT JOIN _tj j ON j.route_id = t.route_id AND j.orig_seq = t.orig_seq AND j.fare = coalesce(t.fare, 0)
             AND j.is_ac = t.is_ac AND t.dest_seq = j.n_stops""")
    con.execute("""CREATE OR REPLACE TEMP TABLE _sr_stage (route_id BIGINT, seq INT, date DATE, day_type VARCHAR,
                   minute INT, pax DOUBLE, tickets INT, corrected BOOLEAN)""")
    excl = moved = total = 0.0
    days = [r[0] for r in con.execute("SELECT DISTINCT date FROM _rtj ORDER BY 1").fetchall()]
    for d in days:
        e, m, t = _expand_day(con, d, "")
        excl, moved, total = excl + e, moved + m, total + t
    con.execute("""
        CREATE OR REPLACE TABLE stretch_riders AS
        SELECT route_id, seq, date, day_type, minute, sum(pax) AS pax, sum(tickets)::INT AS tickets,
               bool_or(corrected) AS corrected
        FROM _sr_stage GROUP BY route_id, seq, date, day_type, minute ORDER BY route_id, date, seq, minute""")
    cols = con.execute("SELECT route_id, orig_seq, dest_seq, m0, pax FROM _rt").fetchnumpy()
    ticket_rm = _exact_ticket_rm(clock, cols)
    dq = [("ticket_rm", ticket_rm), ("excluded_rm", excl), ("moved_rm", moved), ("expanded_rm", total)]
    con.register("_df", pd.DataFrame(dq, columns=["name", "value"]))
    con.execute("CREATE OR REPLACE TABLE dq_riders AS SELECT * FROM _df")
    con.unregister("_df")
    dev = check_rider_gate(con, clock)
    n_rows = con.execute("SELECT count(*) FROM stretch_riders").fetchall()[0][0]
    moved_pax, corrected, sens = con.execute(
        "SELECT coalesce(sum(moved_pax), 0), count(*) FILTER (WHERE moved_pax > 0), "
        "count(*) FILTER (WHERE alighting_sensitive) FROM terminal_asymmetry").fetchall()[0]
    stats = RiderStats(tickets=con.execute("SELECT count(*) FROM _rt").fetchall()[0][0], rows=n_rows,
                       ticket_rm=ticket_rm, excluded_rm=excl, moved_rm=moved, moved_pax=float(moved_pax),
                       terminal_rows=terminal_rows, corrected_routes=int(corrected), alighting_sensitive=int(sens),
                       gate_dev=dev)
    print(f"loads: {stats}")
    return stats


# =================================================================== levels (Task 10, design 5.6 steps 3-8)

@dataclass
class LevelStats:
    rows: int
    e_op: dict
    e_star: dict
    capped_routes: int
    infeasible: list
    s0_widened_share: float
    s0_mismatch_share: float
    dropped_rider_share: float
    no_data_routes: int
    bands: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    sizes: dict = field(default_factory=dict)

    def __str__(self) -> str:
        e = ", ".join(f"E_{k} {v:.2f}" for k, v in self.e_op.items())
        st = ", ".join(f"E*_{k} {v:.2f}" for k, v in self.e_star.items())
        return (f"{self.rows:,} stretch_crowding rows; {e} (before water-filling); {st}; {self.capped_routes} routes "
                f"scaled to capacity; S=0 widened {self.s0_widened_share:.3%} / schedule mismatch "
                f"{self.s0_mismatch_share:.3%} of rider volume; {self.no_data_routes} no-data routes")


# ---------------------------------------------------------------- pure functions

def _level_v(mid, seats, rated):
    mid = np.asarray(mid, dtype=float)
    return np.where(mid < SEATS_FRACTION * seats, "seats", np.where(mid <= rated, "standing", "crowded"))


def level(people_mid: float, spec) -> str:
    """seats if L < 0.7 x seats; standing up to the rated total; crowded above it."""
    return str(_level_v(people_mid, spec.seats, spec.rated_total))


def evidence(low: float, high: float, spec, flags, route_no_data: bool) -> str:
    """none for no-data routes; rough when low app use flags it, when the range spans two levels, or when even
    the upper end stays under the seats threshold (a quiet count is only a rough guess); else many_tickets."""
    if route_no_data:
        return "none"
    if "low_app_use" in flags:
        return "rough"
    lo, hi = level(low, spec), level(high, spec)
    return "rough" if lo != hi or hi == "seats" else "many_tickets"


def cap_to_crush(people: float, spec) -> tuple[float, bool]:
    """Displayed people on board never exceed the crush load; the second value says it was capped (flag full)."""
    return (float(spec.crush), True) if people > spec.crush else (float(people), False)


def sampling_se(daily) -> float:
    """Standard error of a cell's mean: sample SD of its daily values (zero days included) / sqrt(days)."""
    v = np.asarray(daily, dtype=float)
    return float(v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 1 else 0.0


def waterfill(app_by_route: dict, bound_by_route: dict, total: float) -> tuple[float, dict]:
    """Operator scale E* with per-route capacity bounds: E_r = min(E*, B_r) and sum(app_r x E_r) = total.
    Routes without a bound are absent from bound_by_route (or inf). If even all-capped cannot reach the total
    E* is the largest bound (every bounded route capped). Returns (E*, E_r)."""
    inf = float("inf")
    items = sorted(((bound_by_route.get(r, inf), r, a) for r, a in app_by_route.items() if a > 0),
                   key=lambda t: (t[0], str(t[1])))
    remaining, weight, e = float(total), sum(a for _, _, a in items), 0.0
    for b, _, a in items:
        e = remaining / weight if weight > 0 else 0.0
        if e <= b:
            break
        remaining -= a * b
        weight -= a
    else:
        if items:
            e = max(b for b, _, _ in items if b < inf) if any(b < inf for b, _, _ in items) else e
    return e, {r: min(e, bound_by_route.get(r, inf)) for r in app_by_route}


# ---------------------------------------------------------------- helpers

def _windows(fn) -> str:
    """UNION ALL of fn(dt, step, half, wide_half, last_j) over the two day types."""
    parts = []
    for dt, w in WINDOWS.items():
        half = w.base_min // 2
        parts.append(fn(dt, w.step_min, half, half + SUPPLY_WIDEN_MIN, (1440 - 1) // w.step_min))
    return " UNION ALL ".join(parts)


def _unnest_windows(col: str, step: int, half: int, last_j: int) -> str:
    """SQL list of window indexes j (window label j*step) whose base [j*step-half, j*step+half) holds `col`."""
    return (f"unnest(range(greatest(0, CAST(floor(({col} - {half}) / {step}.0) AS BIGINT) + 1), "
            f"least(CAST(floor(({col} + {half}) / {step}.0) AS BIGINT), {last_j}) + 1))")


def effective_days(con) -> pd.DataFrame:
    """(day_type, w, n_days): clean days per window, a day counting by the share of the base window that is
    not excluded (R8 half-open windows; equals the plain clean-day count when no window is cut)."""
    days = con.execute("SELECT date, day_type FROM clean_days WHERE NOT is_excluded_date").fetchall()
    rows = []
    for dt, spec in WINDOWS.items():
        half = spec.base_min // 2
        ds = [d for d, t in days if t == dt]
        for w in range(0, 1440, spec.step_min):
            lo, hi = max(0, w - half), min(1440, w + half)
            tot = 0.0
            for d in ds:
                base = datetime(d.year, d.month, d.day)
                tot += 1 - sum(excluded(base + timedelta(minutes=m)) for m in range(lo, hi)) / (hi - lo)
            rows.append((dt, w, tot))
    return pd.DataFrame(rows, columns=["day_type", "w", "n_days"])


def clean_day_totals(con) -> dict[str, float]:
    """Effective clean days per day type over the whole day: each non-excluded date counts by the share of its
    minutes outside the excluded windows (a day inside an excluded window counts 0)."""
    out: dict[str, float] = {}
    for d, dt in con.execute("SELECT date, day_type FROM clean_days WHERE NOT is_excluded_date").fetchall():
        base = datetime(d.year, d.month, d.day)
        out[dt] = out.get(dt, 0.0) + 1 - sum(excluded(base + timedelta(minutes=m)) for m in range(1440)) / 1440
    return out


def _register(con, name: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {name} AS SELECT * FROM _df")
    con.unregister("_df")


def _eligible(con) -> None:
    """Routes that carry supply per day type (R6): regular always, office_special on weekdays only; school and
    daf routes never. passings itself is not filtered."""
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _elig AS
        SELECT m.route_id, d.day_type, s."class" = 'office_special' AS office
        FROM route_meta m JOIN service_class s USING (route_id)
        CROSS JOIN (VALUES ('weekday'), ('weekend')) d(day_type)
        WHERE s."class" = 'regular' OR (s."class" = 'office_special' AND d.day_type = 'weekday')""")
    # stretch k = stop k to k+1; the bus is on it at its passing of stop k
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _pm AS
        SELECT p.route_id, p.seq, p.minute % 1440 AS m
        FROM passings p JOIN route_meta r USING (route_id)
        WHERE p.seq <= r.n_stops - 1 AND p.route_id IN (SELECT route_id FROM _elig)""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _pair AS
        SELECT a.route_id, a.seq, a.stop_id AS from_stop_id, b.stop_id AS to_stop_id,
               a.stop_name AS from_name, b.stop_name AS to_name
        FROM canonical_stops a JOIN canonical_stops b ON a.route_id = b.route_id AND b.seq = a.seq + 1""")


def _supply(con) -> None:
    """_sup(route_id, seq, day_type, w, s_base, s_wide): scheduled buses at stop k in the base window and in
    the base widened by SUPPLY_WIDEN_MIN each side; _rh: the route-hour fallback."""
    con.execute("CREATE OR REPLACE TEMP TABLE _sup AS " + _windows(lambda dt, step, half, wh, last_j: f"""
        SELECT route_id, seq, '{dt}' AS day_type, j * {step} AS w, count(*)::INT AS s_wide,
               (count(*) FILTER (WHERE m >= j * {step} - {half} AND m < j * {step} + {half}))::INT AS s_base
        FROM (SELECT p.route_id, p.seq, p.m, {_unnest_windows('p.m', step, wh, last_j)} AS j
              FROM _pm p JOIN _elig e ON e.route_id = p.route_id AND e.day_type = '{dt}')
        GROUP BY route_id, seq, j"""))
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _rh AS
        SELECT route_id, h, max(c)::INT AS rh
        FROM (SELECT route_id, seq, m // 60 AS h, count(*) AS c FROM _pm GROUP BY ALL) GROUP BY route_id, h""")


def _rider_cells(con) -> None:
    """_ry: per (route, stretch, day type, window) the sum over clean days of daily rider counts and of their
    squares (days without riders contribute zero), plus tickets."""
    con.execute("CREATE OR REPLACE TEMP TABLE _ry AS " + _windows(lambda dt, step, half, wh, last_j: f"""
        SELECT route_id, seq, '{dt}' AS day_type, j * {step} AS w, sum(y) AS sum_y, sum(y * y) AS sum_y2,
               sum(t)::BIGINT AS tickets
        FROM (SELECT route_id, seq, date, j, sum(pax) AS y, sum(tickets) AS t
              FROM (SELECT s.route_id, s.seq, s.date, s.pax, s.tickets,
                           {_unnest_windows('s.minute', step, half, last_j)} AS j
                    FROM stretch_riders s JOIN _elig e ON e.route_id = s.route_id AND e.day_type = s.day_type
                    WHERE s.day_type = '{dt}')
              GROUP BY route_id, seq, date, j)
        GROUP BY route_id, seq, j"""))


def _gps_rho(con) -> bool:
    """Task 13's gps_route_hour(route_id, hour, rho), if it exists; otherwise rho = 1."""
    if not _has(con, "gps_route_hour"):
        return False
    cols = {r[0] for r in con.execute("DESCRIBE gps_route_hour").fetchall()}
    return {"route_id", "hour", "rho"} <= cols


def _cells(con, nd: pd.DataFrame) -> None:
    """_cell: one row per (route, stretch, day type, window) with riders or scheduled buses, the supply tier
    that applied (4: schedule, widened +-30, route-hour, none), and l = riders per bus."""
    _register(con, "_nd", nd)
    rho = _gps_rho(con)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _cell AS
        WITH j AS (
            SELECT route_id, seq, day_type, w, coalesce(y.sum_y, 0) AS sum_y, coalesce(y.sum_y2, 0) AS sum_y2,
                   coalesce(y.tickets, 0) AS tickets, coalesce(s.s_base, 0) AS s_base, coalesce(s.s_wide, 0) AS s_wide
            FROM _ry y FULL OUTER JOIN _sup s USING (route_id, seq, day_type, w)),
        k AS (
            SELECT j.*, n.n_days, coalesce(h.rh, 0) AS rh, {'coalesce(g.rho, 1.0)' if rho else '1.0'} AS rho,
                   {'g.rho IS NOT NULL' if rho else 'false'} AS has_gps
            FROM j JOIN _pair USING (route_id, seq)
            JOIN _nd n ON n.day_type = j.day_type AND n.w = j.w
            LEFT JOIN _rh h ON h.route_id = j.route_id AND h.h = j.w // 60
            {"LEFT JOIN gps_route_hour g ON g.route_id = j.route_id AND g.hour = j.w // 60" if rho else ""}
            WHERE n.n_days > 0),
        t AS (
            SELECT k.*, CASE WHEN s_base > 0 THEN s_base WHEN sum_y > 0 AND s_wide > 0 THEN s_wide
                             WHEN sum_y > 0 AND rh > 0 THEN rh END AS s_raw,
                   CASE WHEN s_base > 0 THEN CASE WHEN has_gps THEN 'gps' ELSE 'schedule' END
                        WHEN sum_y > 0 AND (s_wide > 0 OR rh > 0) THEN 'widened'
                        WHEN sum_y > 0 THEN 'none' END AS src
            FROM k)
        SELECT route_id, seq, day_type, w, sum_y, sum_y2, tickets, n_days, src, s_raw * rho AS s,
               sum_y / n_days AS y_day,
               CASE WHEN s_raw > 0 THEN sum_y / n_days / (s_raw * rho) END AS l,
               CASE WHEN s_raw > 0 AND n_days > 1
                    THEN sqrt(greatest((sum_y2 - sum_y * sum_y / n_days) / (n_days - 1), 0)) / sqrt(n_days)
                         / (s_raw * rho) ELSE 0.0 END AS se_l
        FROM t WHERE src IS NOT NULL""")


def _route_level(con, n_clean: int) -> None:
    """_app(route_id, operator, app): resolved passengers per clean day; _rnd: the no-data rule."""
    ex = _excluded_sql("CAST(timezone('Asia/Kolkata', t.ts) AS TIMESTAMP)", "t.date")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _app AS
        SELECT m.route_id, m.operator, coalesce(a.pax, 0) / {n_clean} AS app
        FROM route_meta m LEFT JOIN (SELECT t.route_id, sum(t.pax) AS pax FROM tickets_resolved t
                                     WHERE NOT {ex} GROUP BY 1) a USING (route_id)""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _rnd AS
        WITH tr AS (SELECT route_id, count(*) AS trips FROM _pm WHERE seq = 1 GROUP BY 1),
        r AS (SELECT a.route_id, a.app / tr.trips AS per_trip FROM _app a JOIN tr USING (route_id))
        SELECT route_id, per_trip, per_trip <= 0 OR per_trip < (SELECT quantile_cont(per_trip, ?) FROM r) AS no_data
        FROM r""", [NO_DATA_PERCENTILE])


def _low_app_use(con, nday: dict) -> None:
    """_low(route_id, seq, day_type): app riders per scheduled bus on a stop pair served by >= 2 routes
    below a third of the pair's median across routes that sell tickets."""
    _register(con, "_nday", pd.DataFrame(list(nday.items()), columns=["day_type", "n"]))
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _low AS
        WITH y AS (SELECT s.route_id, s.seq, s.day_type, sum(s.pax) / any_value(n.n) AS y
                   FROM stretch_riders s JOIN _nday n USING (day_type) GROUP BY ALL),
        sd AS (SELECT p.route_id, p.seq, e.day_type, count(*) AS s_day
               FROM _pm p JOIN _elig e USING (route_id) GROUP BY ALL),
        rt AS (SELECT sd.route_id, sd.seq, sd.day_type, pr.from_stop_id, pr.to_stop_id,
                      coalesce(y.y, 0) / sd.s_day AS rate
               FROM sd JOIN _pair pr USING (route_id, seq) LEFT JOIN y USING (route_id, seq, day_type)
               JOIN _rnd r USING (route_id) WHERE NOT r.no_data),
        md AS (SELECT from_stop_id, to_stop_id, day_type, median(rate) AS med, count(*) AS n FROM rt GROUP BY ALL)
        SELECT rt.route_id, rt.seq, rt.day_type FROM rt JOIN md USING (from_stop_id, to_stop_id, day_type)
        WHERE md.n >= 2 AND rt.rate < md.med * {LOW_APP_USE_FRACTION}""")


def _scale(con, cells: str = "_cell") -> tuple[dict, dict, dict, set, list]:
    """Per operator: E_op, the capacity bounds, the water-filled E*; fills _er(route_id, e_r, bound, capped)."""
    bounds = dict(con.execute(f"""
        SELECT c.route_id, s.crush / quantile_cont(c.l, {BOUND_PERCENTILE}) AS b
        FROM {cells} c JOIN route_specs s USING (route_id)
        WHERE c.day_type = 'weekday' AND c.tickets >= {BOUND_MIN_TICKETS} AND c.l > 0
        GROUP BY c.route_id, s.crush HAVING quantile_cont(c.l, {BOUND_PERCENTILE}) > 0""").fetchall())
    app = con.execute("SELECT route_id, operator, app FROM _app").fetchall()
    e_op, e_star, er, capped, infeasible = {}, {}, {}, set(), []
    for op, src in PUBLISHED_RIDERSHIP.items():
        by = {r: a for r, o, a in app if o == op}
        tot = sum(by.values())
        if tot <= 0:
            continue
        e_op[op] = src.value / tot
        e, e_r = waterfill(by, bounds, src.value)
        e_star[op] = e
        er.update(e_r)
        got = sum(by[r] * e_r[r] for r in by)
        if abs(got / src.value - 1) > 1e-6:
            infeasible.append(op)
            capped |= {r for r in by if r in bounds and by[r] > 0}
        else:
            capped |= {r for r in by if r in bounds and by[r] > 0 and bounds[r] < e}
    rows = [(r, er.get(r), bounds.get(r), r in capped) for r, _, _ in app]
    _register(con, "_er", pd.DataFrame(rows, columns=["route_id", "e_r", "bound", "capped"]).astype(
        {"route_id": "int64", "e_r": "float64", "bound": "float64", "capped": "bool"}))
    return e_op, e_star, bounds, capped, infeasible


def _durations(con, clock: Clock) -> None:
    """_dur(route_id, seq, hour, dur_min): corrected run time of stretch k at that hour."""
    rows = []
    for rid, n in con.execute("SELECT route_id, n_stops FROM route_meta").fetchall():
        fac = np.array(clock.hour_factors(rid))
        for seq in range(1, n):
            t = clock.template(rid, seq + 1) / 60.0
            rows.append(pd.DataFrame({"route_id": rid, "seq": seq, "hour": np.arange(24), "dur_min": t * fac}))
    df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        {"route_id": [], "seq": [], "hour": [], "dur_min": []})
    _register(con, "_dur", df.astype({"route_id": "int64", "seq": "int32", "hour": "int32"}))


# ---------------------------------------------------------------- final table

def _build_crowding(con) -> None:
    lo, hi = SCALE_RANGE
    con.execute(f"""
        CREATE OR REPLACE TABLE stretch_crowding AS
        WITH base AS (
            SELECT m.route_id, m.short_name, m.operator, m.direction, c.seq, p.from_stop_id, p.to_stop_id,
                   p.from_name, p.to_name, c.day_type, c.w::INT AS window_start_min,
                   c.y_day AS app_riders, c.tickets, c.s AS buses, c.src AS bus_source,
                   b.share_9m, sp.seats, sp.rated_total, sp.crush, er.e_r, er.bound, er.capped,
                   c.l, c.se_l, m.n_stops,
                   coalesce(r.no_data, true) AS route_no_data,
                   (c.src = 'none') AS mismatch,
                   (lw.route_id IS NOT NULL) AS low_use,
                   coalesce(ta.alighting_sensitive, false) AS alight,
                   (e.office AND c.day_type = 'weekday') AS office
            FROM _cell c JOIN route_meta m USING (route_id) JOIN _pair p USING (route_id, seq)
            JOIN bus_mix b USING (route_id) JOIN route_specs sp USING (route_id)
            JOIN _er er USING (route_id) LEFT JOIN _rnd r USING (route_id)
            JOIN _elig e ON e.route_id = c.route_id AND e.day_type = c.day_type
            LEFT JOIN _low lw ON lw.route_id = c.route_id AND lw.seq = c.seq AND lw.day_type = c.day_type
            LEFT JOIN terminal_asymmetry ta ON ta.route_id = c.route_id),
        est AS (
            SELECT *, (route_no_data OR mismatch OR e_r IS NULL) AS nd,
                   e_r * l AS mid_raw,
                   {lo} * e_r * greatest(l - se_l, 0) AS low_raw,
                   greatest(e_r, least({hi} * e_r, coalesce(bound, 1e18))) * (l + se_l) AS high_raw
            FROM base),
        lvl AS (
            SELECT *, CASE WHEN nd THEN 'no_data' WHEN mid_raw < {SEATS_FRACTION} * seats THEN 'seats'
                           WHEN mid_raw <= rated_total THEN 'standing' ELSE 'crowded' END AS level,
                   CASE WHEN nd THEN 'none' WHEN low_use THEN 'rough'
                        WHEN (CASE WHEN low_raw < {SEATS_FRACTION} * seats THEN 'a' WHEN low_raw <= rated_total
                                   THEN 'b' ELSE 'c' END)
                             <> (CASE WHEN high_raw < {SEATS_FRACTION} * seats THEN 'a' WHEN high_raw <= rated_total
                                      THEN 'b' ELSE 'c' END)
                             OR high_raw < {SEATS_FRACTION} * seats THEN 'rough' ELSE 'many_tickets' END AS ev0
            FROM est)
        SELECT route_id, short_name, operator, direction, seq, from_stop_id, to_stop_id, from_name, to_name,
               day_type, window_start_min, round(app_riders, 4) AS app_riders, tickets::INT AS tickets,
               round(buses, 3) AS buses, bus_source, share_9m, seats, rated_total, crush, e_r AS "E_r",
               CASE WHEN nd THEN NULL ELSE round(least(mid_raw, crush), 3) END AS people_mid,
               CASE WHEN nd THEN NULL ELSE round(least(low_raw, crush), 3) END AS people_low,
               CASE WHEN nd THEN NULL ELSE round(least(high_raw, crush), 3) END AS people_high,
               level,
               CASE WHEN ev0 = 'many_tickets' AND alight AND seq >= n_stops - 1 - {ALIGHTING_LAST_STRETCHES} + 1
                    THEN 'rough' ELSE ev0 END AS evidence,
               concat_ws(',', CASE WHEN NOT nd AND mid_raw > crush THEN 'full' END,
                              CASE WHEN capped THEN 'scaled_to_capacity' END,
                              CASE WHEN low_use THEN 'low_app_use' END,
                              CASE WHEN mismatch THEN 'schedule_mismatch' END,
                              CASE WHEN alight THEN 'alighting_sensitive' END,
                              CASE WHEN office THEN 'office_special' END) AS flags
        FROM lvl ORDER BY route_id, day_type, seq, window_start_min""")


# ---------------------------------------------------------------- outputs

def _simplify(coords: list, tol_m: float) -> list:
    """Douglas-Peucker on [lat, lon] points (local metres); returns GeoJSON [lon, lat] rounded to 5 decimals."""
    pts = np.array(coords, dtype=float)
    if len(pts) <= 2:
        keep = np.arange(len(pts))
    else:
        xy = (pts - pts[0]) * np.array([111_320.0, 111_320.0 * np.cos(np.radians(pts[:, 0].mean()))])
        keep_m = np.zeros(len(pts), bool)
        keep_m[[0, -1]] = True
        stack = [(0, len(pts) - 1)]
        while stack:
            i, j = stack.pop()
            if j <= i + 1:
                continue
            d = xy[j] - xy[i]
            n = np.hypot(*d)
            seg = xy[i + 1:j] - xy[i]
            dist = np.hypot(*seg.T) if n == 0 else np.abs(d[0] * seg[:, 1] - d[1] * seg[:, 0]) / n
            k = int(np.argmax(dist))
            if dist[k] > tol_m:
                keep_m[i + 1 + k] = True
                stack += [(i, i + 1 + k), (i + 1 + k, j)]
        keep = np.flatnonzero(keep_m)
    return [[round(float(pts[i, 1]), 5), round(float(pts[i, 0]), 5)] for i in keep]


def _corridor(con, paths, clock: Clock) -> int:
    _durations(con, clock)
    con.execute("""
        CREATE OR REPLACE TABLE corridor_values AS
        SELECT from_stop_id || '-' || to_stop_id AS pair_id, any_value(from_stop_id) AS from_stop_id,
               any_value(to_stop_id) AS to_stop_id, c.day_type, c.window_start_min,
               round(sum(c.buses * c.people_mid) / sum(c.buses * c.rated_total), 4) AS load_ratio,
               round(sum(c.buses) FILTER (WHERE c.level = 'crowded') / sum(c.buses), 4) AS share_crowded,
               round(sum(c.buses * c.people_mid * d.dur_min) FILTER (WHERE c.level = 'crowded')
                     * CASE WHEN c.day_type = 'weekday' THEN 30.0 / 90 ELSE 60.0 / 120 END, 1) AS crowded_rider_min,
               round(sum(c.buses), 2) AS buses, count(*)::INT AS routes
        FROM stretch_crowding c
        JOIN _dur d ON d.route_id = c.route_id AND d.seq = c.seq AND d.hour = c.window_start_min // 60
        WHERE c.level <> 'no_data' AND c.buses > 0
        GROUP BY from_stop_id, to_stop_id, c.day_type, c.window_start_min
        ORDER BY pair_id, c.day_type, c.window_start_min""")
    con.execute(f"COPY corridor_values TO '{paths.processed / 'corridor_values.parquet'}' (FORMAT PARQUET)")
    # one geometry per stop pair: the lowest route id that serves it and has a shape
    rows = con.execute("""
        SELECT pair_id, coords FROM (
            SELECT v.pair_id, sh.coords, row_number() OVER (PARTITION BY v.pair_id ORDER BY p.route_id) AS rn
            FROM (SELECT DISTINCT pair_id, from_stop_id, to_stop_id FROM corridor_values) v
            JOIN _pair p ON p.from_stop_id = v.from_stop_id AND p.to_stop_id = v.to_stop_id
            JOIN segment_shapes sh ON sh.route_id = p.route_id AND sh.seq = p.seq + 1
            WHERE p.route_id IN (SELECT route_id FROM _elig)) WHERE rn = 1 ORDER BY pair_id""").fetchall()
    feats = [{"type": "Feature", "id": pid,
              "properties": {"id": pid},
              "geometry": {"type": "LineString", "coordinates": _simplify(json.loads(c), CORRIDOR_SIMPLIFY_M)}}
             for pid, c in rows]
    (paths.processed / "corridor_geometry.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    return len(feats)


def _summaries(con, paths) -> pd.DataFrame:
    con.execute("""
        COPY (SELECT route_id, any_value(short_name) AS short_name, any_value(operator) AS operator, day_type,
                     window_start_min // 60 AS hour,
                     round(max(buses), 2) AS buses,
                     round(avg(people_mid), 2) AS mean_people, round(max(people_mid), 2) AS max_people,
                     round(avg((level = 'crowded')::INT) FILTER (WHERE level <> 'no_data'), 4) AS share_crowded,
                     round(avg((level = 'no_data')::INT), 4) AS share_no_data,
                     round(avg((evidence = 'many_tickets')::INT), 4) AS share_many_tickets
              FROM stretch_crowding WHERE window_start_min % 60 = 0
              GROUP BY route_id, day_type, window_start_min // 60 ORDER BY route_id, day_type, hour)
        TO '""" + str(paths.processed / "route_hour_summary.csv") + "' (HEADER, DELIMITER ',')")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _cov AS
        SELECT m.operator, c.day_type, c.window_start_min // 60 AS hour, c.level, c.evidence,
               sum(c.buses * CASE WHEN c.day_type = 'weekday' THEN 30.0 / 90 ELSE 60.0 / 120 END
                   * coalesce(sh.length_m, 0) / 1000.0) AS bus_km
        FROM stretch_crowding c JOIN route_meta m USING (route_id)
        LEFT JOIN segment_shapes sh ON sh.route_id = c.route_id AND sh.seq = c.seq + 1
        GROUP BY ALL""")
    con.execute("""
        COPY (SELECT operator, day_type, hour, level, evidence, round(bus_km, 1) AS bus_km,
                     round(bus_km / sum(bus_km) OVER (PARTITION BY operator, day_type, hour), 4) AS share
              FROM _cov ORDER BY operator, day_type, hour, level, evidence)
        TO '""" + str(paths.processed / "coverage.csv") + "' (HEADER, DELIMITER ',')")
    return con.execute("""
        SELECT day_type,
               CASE WHEN hour < 5 THEN '00-05' WHEN hour < 8 THEN '05-08' WHEN hour < 11 THEN '08-11'
                    WHEN hour < 17 THEN '11-17' WHEN hour < 21 THEN '17-21' ELSE '21-24' END AS band,
               level, evidence, sum(bus_km) AS bus_km
        FROM _cov GROUP BY ALL""").df()


def export_planner(con, paths) -> dict[str, int]:
    """processed/planner/*.parquet from work.duckdb: only the whitelisted tables (never tickets, never
    devi_vehicles)."""
    paths.planner_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for t in PLANNER_TABLES:
        if _has(con, t):
            f = paths.planner_dir / f"{t}.parquet"
            con.execute(f"COPY (SELECT * FROM {t}) TO '{f}' (FORMAT PARQUET)")
            out[t] = f.stat().st_size
    return out


def run_levels(con, paths, gate: bool = True, **_) -> LevelStats:
    paths.processed.mkdir(parents=True, exist_ok=True)
    clock = Clock.load(con)
    nd = effective_days(con)
    nday = clean_day_totals(con)
    n_clean = sum(nday.values())
    _eligible(con)
    _supply(con)
    _rider_cells(con)
    _cells(con, nd)
    _route_level(con, n_clean)
    _low_app_use(con, nday)
    e_op, e_star, bounds, capped, infeasible = _scale(con)
    _build_crowding(con)

    tot_y, widened, mism = con.execute("""
        SELECT coalesce(sum(sum_y), 0), coalesce(sum(sum_y) FILTER (WHERE src = 'widened'), 0),
               coalesce(sum(sum_y) FILTER (WHERE src = 'none'), 0) FROM _cell""").fetchall()[0]
    all_y = con.execute("SELECT coalesce(sum(pax), 0) FROM stretch_riders").fetchall()[0][0]
    kept_y = con.execute("SELECT coalesce(sum(s.pax), 0) FROM stretch_riders s JOIN _elig e ON "
                         "e.route_id = s.route_id AND e.day_type = s.day_type").fetchall()[0][0]
    s0 = mism / tot_y if tot_y else 0.0
    if gate and s0 >= S0_MAX_SHARE:
        raise GateError(f"supply gate: {s0:.2%} of rider volume has no scheduled bus even after widening "
                        f"(limit {S0_MAX_SHARE:.0%})")

    n_pairs = _corridor(con, paths, clock)
    bands = _summaries(con, paths)
    con.execute(f"COPY stretch_crowding TO '{paths.processed / 'stretch_crowding.parquet'}' (FORMAT PARQUET)")
    planner = export_planner(con, paths)
    sizes = {f.name: f.stat().st_size for f in sorted(paths.processed.glob("*"))
             if f.suffix in (".parquet", ".csv", ".geojson")}
    sizes.update({f"planner/{k}.parquet": v for k, v in planner.items()})
    rows = con.execute("SELECT count(*) FROM stretch_crowding").fetchall()[0][0]
    n_nd = con.execute("SELECT count(*) FROM _rnd WHERE no_data").fetchall()[0][0]
    stats = LevelStats(rows=rows, e_op=e_op, e_star=e_star, capped_routes=len(capped), infeasible=infeasible,
                       s0_widened_share=widened / tot_y if tot_y else 0.0, s0_mismatch_share=s0,
                       dropped_rider_share=1 - kept_y / all_y if all_y else 0.0, no_data_routes=n_nd,
                       bands=bands, sizes=sizes)
    dq = [("rows", rows), ("capped_routes", len(capped)), ("s0_widened_share", stats.s0_widened_share),
          ("s0_mismatch_share", s0), ("dropped_rider_share", stats.dropped_rider_share),
          ("corridor_pairs", n_pairs), ("no_data_routes", n_nd)] + [(f"e_op_{k}", v) for k, v in e_op.items()] + [
        (f"e_star_{k}", v) for k, v in e_star.items()]
    _register(con, "_dq", pd.DataFrame(dq, columns=["name", "value"]).astype({"value": float}))
    con.execute("CREATE OR REPLACE TABLE dq_levels AS SELECT * FROM _dq")
    _print_report(stats)
    return stats


def _print_report(st: LevelStats) -> None:
    print(f"levels: {st}")
    if st.infeasible:
        print(f"levels: capacity bounds make the published total unreachable for {st.infeasible}")
    b = st.bands
    if not b.empty:
        for dt in ("weekday", "weekend"):
            for what in ("level", "evidence"):
                t = b[b.day_type == dt].pivot_table(index="band", columns=what, values="bus_km", aggfunc="sum",
                                                    fill_value=0.0)
                t = t.div(t.sum(axis=1), axis=0).round(3)
                print(f"levels: {dt} {what} share of bus-km by hour band\n{t.to_string()}")
    print("levels: files " + ", ".join(f"{k} {v / 1e6:.2f} MB" for k, v in st.sizes.items()))


def run_loads(con, paths, **kwargs):
    """The `loads` stage: riders on stretches, then levels."""
    run_riders(con, paths, **kwargs)
    return run_levels(con, paths, **kwargs)
