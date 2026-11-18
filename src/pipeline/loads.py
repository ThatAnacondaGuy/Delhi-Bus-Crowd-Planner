"""Stage 4 (riders part): app riders on every route stretch at on-board time, with the terminal
alighting correction.

Each resolved ticket is placed on the stretches between its boarding and alighting stops. Stretch k
(stop k to k+1) is occupied at purchase time + corrected run time from the boarding stop (Clock), so
a rider counts where the bus really is. App tickets end at route terminals about twice as often as
they start there (people buy near the end of a ride), so terminal alightings are capped at the reverse
route's terminal boardings times the intermediate-stop ratio (ruling R11) and the excess is spread over
earlier stops of the same fare slab in proportion to the reverse direction's boardings.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import EXCLUDED_DATES, EXCLUDED_WINDOWS
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

def _tmpl(clock: Clock, rid: int, seq: int, n: int, ring: bool) -> float:
    """Template seconds of the segment ending at stop seq; past the end of a ring it is the segment the
    wrapped stretch maps onto (R4: stretch k > N-1 is stretch k-(N-1))."""
    if ring and seq > n:
        seq -= n - 1
    return clock.template(rid, seq)


def _clock_tables(con, clock: Clock) -> None:
    """_q(route_id, k, q): cumulative corrected-clock template seconds from stop 1 to stop k (ring-aware),
    _fh(route_id, hour, factor)."""
    mx = dict(con.execute("SELECT route_id, greatest(max(dest_seq), max(orig_seq)) FROM _rt GROUP BY 1").fetchall())
    n = {r: (c, bool(g)) for r, c, g in con.execute("SELECT route_id, n_stops, is_ring FROM route_meta").fetchall()}
    rids, ks, qs, frid, fh, ff = [], [], [], [], [], []
    for rid, m in mx.items():
        ns, ring = n.get(rid, (0, False))
        top = max(m, ns) + 1
        seg = np.array([0.0] + [_tmpl(clock, rid, s, ns, ring) for s in range(2, top + 1)])
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


def _exact_ticket_rm(clock: Clock, cols: dict, meta: dict) -> float:
    """Rider-minutes of every ticket by stepping the Clock stretch by stretch (numpy over tickets per route);
    independent of the SQL expansion."""
    total = 0.0
    df = pd.DataFrame(cols)
    for rid, g in df.groupby("route_id"):
        o, d, t, p = (g[c].to_numpy() for c in ("orig_seq", "dest_seq", "m0", "pax"))
        top = int(d.max()) + 1
        ns, ring = meta.get(int(rid), (0, False))
        tmpl = np.array([0.0] + [_tmpl(clock, int(rid), s, ns, ring) for s in range(1, top + 1)])
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
               coalesce((SELECT tot FROM btot WHERE btot.route_id = rm.opp) > 0, false) AS known,
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
    meta = {r: (c, bool(g)) for r, c, g in con.execute("SELECT route_id, n_stops, is_ring FROM route_meta").fetchall()}
    ticket_rm = _exact_ticket_rm(clock, cols, meta)
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
