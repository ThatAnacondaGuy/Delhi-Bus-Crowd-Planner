"""Stage 2: resolve cleaned tickets to GTFS routes and canonical stop positions (design §5.3).

Tables written to the work database:
- route_meta: one row per GTFS route: short_name, operator, direction, n_stops, is_ring (canonical
  first stop_id = last stop_id), is_devi and opposite_route_id.
- canonical_stops: each route's longest trip renumbered 1..N. template_s is the scheduled run time
  of the segment ENDING at the stop (0 at seq 1); cum_template_s is its running total.
- route_map: one row per ticket route string: the GTFS route it maps to, match_type (exact, alias,
  remap, unmatched) and the evidence for the decision as JSON.
- tickets_resolved: tickets placed on a route as orig_seq -> dest_seq. how is forward, remapped (a
  reversed ticket that runs forward on the opposite route) or ring_wrap. A ring_wrap ticket's
  dest_seq is its stop's seq + (N - 1), i.e. on the second lap, so it can exceed N; later stages map
  stretch k > N - 1 back to k - (N - 1).
- tickets_rejected: every other ticket, with reason unmatched_route, unmatched_stop, same_stop or
  reversed. dq_resolve counts tickets and passengers per reason.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, NamedTuple

import pandas as pd
import pyarrow as pa
from rapidfuzz import fuzz, process

from .config import ALIAS_MIN_IN_ORDER, MERGE_MIN_ORDERED, REMAP_MIN_REVERSED, STOP_FUZZY_MIN_SCORE
from .errors import GateError
from .routes import alias_key, is_devi, opposite, pair_key, parse_route

GTFS_FILES = ("routes.txt", "trips.txt", "stop_times.txt", "stops.txt")
REJECT_REASONS = ("unmatched_route", "unmatched_stop", "same_stop", "reversed")
_IN_ORDER = ("forward", "ring_wrap")


@dataclass
class ResolveStats:
    tickets: int
    pax: int
    resolved_tickets: int
    resolved_pax: int
    match_rate: float                    # resolved passengers / all passengers
    forward: int
    remapped: int                        # reversed tickets kept on the opposite route
    ring_wrap: int
    aliases: int                         # route strings mapped by alias
    routes_remapped: int                 # route strings swapped to the opposite route (majority rule)
    routes: dict[str, int] = field(default_factory=dict)    # route strings per match_type
    rejected: dict[str, int] = field(default_factory=dict)  # tickets per rejection reason

    def __str__(self) -> str:
        return (f"{self.resolved_pax:,} of {self.pax:,} passengers resolved ({self.match_rate:.2%}); "
                f"remapped {self.remapped:,} tickets, {self.routes_remapped} route strings swapped; "
                f"rejected {sum(self.rejected.values()):,} tickets")


# ---------------------------------------------------------------- stop names (moved from sprint 1)

def normalize_transit_text(text: str) -> str:
    """
    Delhi transit domain text normalizer.
    Expands abbreviations, standardizes transit acronyms, and removes punctuation.
    """
    if not text or pd.isna(text):
        return ""
    t = str(text).lower()

    # Standardize phases
    t = re.sub(r'\bph(?:ase)?[- ]?iv\b', 'phase 4', t)
    t = re.sub(r'\bph(?:ase)?[- ]?iii\b', 'phase 3', t)
    t = re.sub(r'\bph(?:ase)?[- ]?ii\b', 'phase 2', t)
    t = re.sub(r'\bph(?:ase)?[- ]?i\b', 'phase 1', t)

    # Common ETM transit abbreviations
    t = re.sub(r'\bsec\b|\bsec\.|\bsect\b', 'sector', t)
    t = re.sub(r'\bstn\b|\bstn\.', 'station', t)
    t = re.sub(r'\bxing\b|\bx-ing\b', 'crossing', t)
    t = re.sub(r'\bmkr\b|\bmkt\b|\bmkt\.', 'market', t)
    t = re.sub(r'\bhosp\b|\bhosp\.', 'hospital', t)
    t = re.sub(r'\bvhr\b|\bvhr\.', 'vihar', t)
    t = re.sub(r'\bng\b|\bng\.', 'nagar', t)
    t = re.sub(r'\bextn\b|\bext\b|\bext\.|\bexten\b', 'extension', t)
    t = re.sub(r'\brd\b|\brd\.', 'road', t)
    t = re.sub(r'\bclny\b|\bcol\b', 'colony', t)
    t = re.sub(r'\bdep\b|\bdept\b', 'depot', t)
    t = re.sub(r'\bt-point\b|\bt\.point\b|\bt point\b', 't point', t)
    t = re.sub(r'\(t\)', 'terminal', t)
    t = re.sub(r'\bt\b|\bt\.', 'terminal', t)

    # Clean non-alphanumeric except spaces and slashes
    t = re.sub(r'[^a-z0-9\s/]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


class StopIndex(NamedTuple):
    keys: dict[str, tuple[int, ...]]   # normalized stop name or slash token -> every seq it appears at
    choices: list[str]                 # the keys in first-seen order (RapidFuzz candidates)


def build_stop_index(stops: Iterable[tuple[int, str]]) -> StopIndex:
    """Index one route's canonical stops, given as (seq, stop_name) in seq order, by normalized name
    and by each slash-separated part of the name."""
    keys: dict[str, list[int]] = {}
    for seq, name in stops:
        variants = [normalize_transit_text(name)]
        if "/" in str(name):
            variants += [normalize_transit_text(part) for part in str(name).split("/")]
        for v in variants:
            if v:
                seqs = keys.setdefault(v, [])
                if seq not in seqs:
                    seqs.append(seq)
    return StopIndex({k: tuple(v) for k, v in keys.items()}, list(keys))


def match_stop(raw: str | None, index: StopIndex) -> tuple[str, float, str] | None:
    """Route-scoped match of one ticket stop name: (key, score, 'exact' | 'fuzzy'), or None.

    The query is the normalized name plus its slash-separated parts. An exact key match wins;
    otherwise the best RapidFuzz max(WRatio, token_sort_ratio) of at least STOP_FUZZY_MIN_SCORE.
    """
    if raw is None:
        return None
    norm_full = normalize_transit_text(raw)
    q_vars = [norm_full] if norm_full else []
    if "/" in str(raw):
        for part in str(raw).split("/"):
            pn = normalize_transit_text(part)
            if pn and pn not in q_vars:
                q_vars.append(pn)
    for qv in q_vars:
        if qv in index.keys:
            return qv, 100.0, "exact"
    best_score, best_key = -1.0, None
    if index.choices:
        for qv in q_vars:
            res = process.extractOne(qv, index.choices, scorer=fuzz.WRatio)
            if res:
                m_str, score, _ = res
                final = max(score, fuzz.token_sort_ratio(qv, m_str))
                if final >= STOP_FUZZY_MIN_SCORE and final > best_score:
                    best_score, best_key = final, m_str
    if best_key is None:
        return None
    return best_key, round(best_score, 1), "fuzzy"


def resolve_stops_route_scoped(pairs: Iterable[tuple[int, str]], indexes: dict[int, StopIndex]
                               ) -> tuple[list[tuple], dict[str, int]]:
    """Match unique (route_id, raw stop name) pairs against that route's canonical stops.

    Returns one row (route_id, name, key, seq, score, method) per position the matched stop holds
    on the route, and pair counts by method (exact, fuzzy, unmatched).
    """
    rows, counts = [], {"exact": 0, "fuzzy": 0, "unmatched": 0}
    for route_id, name in pairs:
        index = indexes.get(route_id)
        m = match_stop(name, index) if index is not None else None
        if m is None:
            counts["unmatched"] += 1
            continue
        key, score, method = m
        counts[method] += 1
        rows.extend((route_id, name, key, seq, score, method) for seq in index.keys[key])
    return rows, counts


# ---------------------------------------------------------------- GTFS: canonical stops, route meta

def _secs(col: str) -> str:
    c = f"trim({col})"
    return (f"(split_part({c}, ':', 1)::INT * 3600 + split_part({c}, ':', 2)::INT * 60 "
            f"+ split_part({c}, ':', 3)::INT)")


def build_canonical(con, gtfs_dir) -> None:
    """canonical_stops: the longest trip per route_id (ties: smallest trip_id), renumbered 1..N, with
    template_s = arrival - previous departure attached to the arriving stop."""
    f = {n: str(Path(gtfs_dir) / n) for n in GTFS_FILES}
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _gtfs_routes AS
        SELECT route_id::BIGINT AS route_id, trim(route_short_name) AS short_name, trim(agency_id) AS operator
        FROM read_csv(?, header=true, all_varchar=true)""", [f["routes.txt"]])
    con.execute(f"""
        CREATE OR REPLACE TABLE canonical_stops AS
        WITH st AS (
            SELECT trim(trip_id) AS trip_id, trim(stop_id) AS stop_id, stop_sequence::INT AS stop_sequence,
                   {_secs('arrival_time')} AS arr_s, {_secs('departure_time')} AS dep_s
            FROM read_csv(?, header=true, all_varchar=true)),
        tr AS (SELECT route_id::BIGINT AS route_id, trim(trip_id) AS trip_id
               FROM read_csv(?, header=true, all_varchar=true)),
        n AS (SELECT tr.route_id, tr.trip_id, count(*) AS n FROM tr JOIN st USING (trip_id) GROUP BY ALL),
        longest AS (SELECT route_id, trip_id FROM n
                    QUALIFY row_number() OVER (PARTITION BY route_id ORDER BY n DESC, trip_id) = 1),
        seqd AS (SELECT l.route_id, st.stop_id, st.arr_s, st.dep_s,
                        row_number() OVER (PARTITION BY l.route_id ORDER BY st.stop_sequence)::INT AS seq
                 FROM longest l JOIN st USING (trip_id)),
        timed AS (SELECT *, coalesce(arr_s - lag(dep_s) OVER (PARTITION BY route_id ORDER BY seq), 0)::INT
                            AS template_s
                  FROM seqd),
        stops AS (SELECT trim(stop_id) AS stop_id, trim(stop_name) AS stop_name,
                         stop_lat::DOUBLE AS lat, stop_lon::DOUBLE AS lon
                  FROM read_csv(?, header=true, all_varchar=true))
        SELECT t.route_id, r.short_name, r.operator, t.seq, t.stop_id, s.stop_name, s.lat, s.lon,
               t.template_s,
               (sum(t.template_s) OVER (PARTITION BY t.route_id ORDER BY t.seq ROWS UNBOUNDED PRECEDING))::INT
                   AS cum_template_s
        FROM timed t JOIN _gtfs_routes r USING (route_id) LEFT JOIN stops s USING (stop_id)
        ORDER BY t.route_id, t.seq""", [f["stop_times.txt"], f["trips.txt"], f["stops.txt"]])


class Routes(NamedTuple):
    meta: dict[int, dict]                 # route_id -> route_meta row
    by_short: dict[str, int]              # GTFS short name -> route_id
    by_alias: dict[str, list[int]]        # alias_key(short name) -> route_ids
    indexes: dict[int, StopIndex]         # route_id -> stop index for route-scoped matching
    names: dict[int, list[str]]           # route_id -> normalized canonical stop names in seq order


def _load_arrow(con, name: str, columns: dict[str, pa.DataType], rows: list[tuple], temp: bool = False) -> None:
    table = pa.table({c: pa.array([r[i] for r in rows], type=t) for i, (c, t) in enumerate(columns.items())})
    con.register("_arrow_rows", table)
    try:
        con.execute(f"CREATE OR REPLACE {'TEMP ' if temp else ''}TABLE {name} AS SELECT * FROM _arrow_rows")
    finally:
        con.unregister("_arrow_rows")


def _opposites(parsed: dict[int, tuple], names: dict[int, list[str]]) -> dict[int, int | None]:
    """The opposite of a route is the GTFS route whose short name parses to opposite(parse_route(name))
    with the same pair_key. Ties go to the most shared stop names, then the smallest route_id."""
    by_pair = defaultdict(list)
    for rid, p in parsed.items():
        if p.direction:
            by_pair[pair_key(p)].append(rid)
    out = {}
    for rid, p in parsed.items():
        cands = []
        if p.direction:
            want = opposite(p)
            cands = [o for o in by_pair[pair_key(p)] if o != rid and parsed[o].direction == want.direction
                     and (parsed[o].variant or "") == (want.variant or "")]
        mine = set(names.get(rid, []))
        cands.sort(key=lambda o: (-len(mine & set(names.get(o, []))), o))
        out[rid] = cands[0] if cands else None
    return out


def build_route_meta(con) -> Routes:
    """route_meta from _gtfs_routes and canonical_stops; returns the lookups resolution needs."""
    stops = defaultdict(list)
    for rid, seq, stop_name in con.execute(
            "SELECT route_id, seq, stop_name FROM canonical_stops ORDER BY route_id, seq").fetchall():
        stops[rid].append((seq, stop_name))
    names = {rid: [normalize_transit_text(n) for _, n in s] for rid, s in stops.items()}
    rows = con.execute("""
        SELECT r.route_id, r.short_name, r.operator, count(c.seq)::INT AS n_stops,
               arg_min(c.stop_id, c.seq) AS first_stop, arg_max(c.stop_id, c.seq) AS last_stop
        FROM _gtfs_routes r LEFT JOIN canonical_stops c USING (route_id)
        GROUP BY ALL ORDER BY r.route_id""").fetchall()
    parsed = {rid: parse_route(short) for rid, short, *_ in rows}
    opp = _opposites(parsed, names)
    meta, out_rows = {}, []
    for rid, short, operator, n_stops, first, last in rows:
        m = {"route_id": rid, "short_name": short, "operator": operator, "direction": parsed[rid].direction,
             "n_stops": n_stops, "is_ring": n_stops >= 3 and first == last, "is_devi": is_devi(short),
             "opposite_route_id": opp[rid]}
        meta[rid] = m
        out_rows.append(tuple(m.values()))
    _load_arrow(con, "route_meta", {"route_id": pa.int64(), "short_name": pa.string(), "operator": pa.string(),
                                    "direction": pa.string(), "n_stops": pa.int32(), "is_ring": pa.bool_(),
                                    "is_devi": pa.bool_(), "opposite_route_id": pa.int64()}, out_rows)
    by_alias = defaultdict(list)
    for rid, m in meta.items():
        by_alias[alias_key(m["short_name"])].append(rid)
    return Routes(meta, {m["short_name"]: rid for rid, m in meta.items()}, dict(by_alias),
                  {rid: build_stop_index(s) for rid, s in stops.items()}, names)


# ---------------------------------------------------------------- placing tickets on routes

class _StopMatches:
    """Route-scoped stop matches, computed once per unique (route_id, name) and kept in _stop_match."""

    def __init__(self, con, indexes: dict[int, StopIndex]):
        self.con, self.indexes, self.done = con, indexes, set()
        self.counts = {"exact": 0, "fuzzy": 0, "unmatched": 0}
        con.execute("CREATE OR REPLACE TEMP TABLE _stop_match (route_id BIGINT, name VARCHAR, key VARCHAR, "
                    "seq INTEGER, score DOUBLE, method VARCHAR)")

    def ensure(self, assign: str) -> None:
        pairs = self.con.execute(f"""
            SELECT a.route_id, t.start_raw FROM {assign} a JOIN _tix t USING (ticket_id)
            UNION SELECT a.route_id, t.end_raw FROM {assign} a JOIN _tix t USING (ticket_id)""").fetchall()
        todo = sorted(p for p in pairs if p[1] is not None and p not in self.done)
        self.done.update(todo)
        rows, counts = resolve_stops_route_scoped(todo, self.indexes)
        for k, v in counts.items():
            self.counts[k] += v
        if rows:
            _load_arrow(self.con, "_stop_match_new",
                        {"route_id": pa.int64(), "name": pa.string(), "key": pa.string(), "seq": pa.int32(),
                         "score": pa.float64(), "method": pa.string()}, rows, temp=True)
            self.con.execute("INSERT INTO _stop_match SELECT * FROM _stop_match_new")
            self.con.execute("DROP TABLE _stop_match_new")


def _place(con, assign: str, out: str) -> None:
    """Place each (ticket_id, route_id) of `assign` on its route.

    outcome: unmatched_stop (a name not found on the route), same_stop (both names are the same
    stop), forward (a pair orig < dest; the shortest wins), ring_wrap (rings only: dest before orig,
    so dest_seq = seq + N - 1 on the second lap) or reversed. A stop holding several positions on
    the route can be any of them.
    """
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {out} AS
        WITH a AS (
            SELECT a.ticket_id, a.route_id, t.start_raw, t.end_raw, m.n_stops, m.is_ring
            FROM {assign} a JOIN _tix t USING (ticket_id) JOIN route_meta m USING (route_id)),
        p AS (
            SELECT a.ticket_id, o.key AS okey, d.key AS dkey, o.seq AS o, d.seq AS d
            FROM a JOIN _stop_match o ON o.route_id = a.route_id AND o.name = a.start_raw
                   JOIN _stop_match d ON d.route_id = a.route_id AND d.name = a.end_raw),
        g AS (
            SELECT ticket_id, bool_or(okey = dkey) AS same_key,
                   arg_min(o, (d - o) * 100000 + o) FILTER (WHERE o < d) AS fo,
                   arg_min(d, (d - o) * 100000 + o) FILTER (WHERE o < d) AS fd,
                   arg_min(o, (d - o) * 100000 + o) FILTER (WHERE o > d) AS bo,
                   arg_min(d, (d - o) * 100000 + o) FILTER (WHERE o > d) AS bd
            FROM p GROUP BY ticket_id)
        SELECT a.ticket_id, a.route_id,
               CASE WHEN g.ticket_id IS NULL THEN 'unmatched_stop'
                    WHEN g.same_key THEN 'same_stop'
                    WHEN g.fo IS NOT NULL THEN 'forward'
                    WHEN g.bo IS NOT NULL AND a.is_ring THEN 'ring_wrap'
                    WHEN g.bo IS NOT NULL THEN 'reversed'
                    ELSE 'same_stop' END AS outcome,
               CASE WHEN g.fo IS NOT NULL THEN g.fo ELSE g.bo END AS orig_seq,
               CASE WHEN g.fo IS NOT NULL THEN g.fd
                    WHEN a.is_ring THEN g.bd + a.n_stops - 1 ELSE g.bd END AS dest_seq
        FROM a LEFT JOIN g USING (ticket_id)""")


def _assign_from_map(con, route_map: dict) -> None:
    rows = [(raw, m["route_id"]) for raw, m in route_map.items() if raw is not None and m["route_id"] is not None]
    _load_arrow(con, "_rm", {"route_raw": pa.string(), "route_id": pa.int64()}, rows, temp=True)
    con.execute("CREATE OR REPLACE TEMP TABLE _assign AS "
                "SELECT t.ticket_id, m.route_id FROM _tix t JOIN _rm m USING (route_raw)")


# ---------------------------------------------------------------- route strings

def _lcs(a: list[str], b: list[str]) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def mergeable(a: list[str], b: list[str]) -> tuple[bool, dict]:
    """Two GTFS routes (normalized canonical stop names in order) may merge only with the same termini
    and an ordered stop match (longest common subsequence over the longer list) >= MERGE_MIN_ORDERED.
    Different termini and opposite directions never merge."""
    same_termini = bool(a) and bool(b) and a[0] == b[0] and a[-1] == b[-1]
    ordered = _lcs(a, b) / max(len(a), len(b)) if a and b else 0.0
    return same_termini and ordered >= MERGE_MIN_ORDERED, {"same_termini": same_termini,
                                                            "ordered_match": round(ordered, 3)}


def _ev(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def _alias_decisions(con, routes: Routes, matches: _StopMatches, strings: list) -> dict:
    """Aliases for strings with no exact short name: candidates share alias_key; one stands when at
    least ALIAS_MIN_IN_ORDER of the string's tickets resolve in stop order on it (§5.3)."""
    cands = []
    keys = {}
    for raw in strings:
        k = alias_key(raw) if raw is not None else ""
        keys[raw] = k
        cands += [(raw, rid) for rid in routes.by_alias.get(k, [])] if k else []
    decisions = {}
    in_order = {}
    if cands:
        _load_arrow(con, "_alias_cand", {"route_raw": pa.string(), "route_id": pa.int64()}, cands, temp=True)
        con.execute("CREATE OR REPLACE TEMP TABLE _assign_alias AS "
                    "SELECT t.ticket_id, c.route_id FROM _tix t JOIN _alias_cand c USING (route_raw)")
        matches.ensure("_assign_alias")
        _place(con, "_assign_alias", "_placed_alias")
        for raw, rid, n, ok in con.execute(f"""
                SELECT t.route_raw, p.route_id, count(*), count(*) FILTER (WHERE p.outcome IN {_IN_ORDER})
                FROM _placed_alias p JOIN _tix t USING (ticket_id) GROUP BY ALL""").fetchall():
            in_order[(raw, rid)] = (n, ok)
    for raw in strings:
        tried = []
        for rid in routes.by_alias.get(keys[raw], []) if keys[raw] else []:
            n, ok = in_order.get((raw, rid), (0, 0))
            tried.append({"route_id": rid, "short_name": routes.meta[rid]["short_name"], "tickets": n,
                          "in_order": ok, "share": round(ok / n, 4) if n else 0.0})
        tried.sort(key=lambda c: (-c["share"], -c["in_order"], c["route_id"]))
        ev = {"rule": "alias_key", "alias_key": keys[raw], "threshold": ALIAS_MIN_IN_ORDER, "candidates": tried}
        passing = [c for c in tried if c["share"] >= ALIAS_MIN_IN_ORDER]
        chosen = None
        if passing:
            best = passing[0]
            merged, separate = [], []
            for other in passing[1:]:
                ok, why = mergeable(routes.names.get(best["route_id"], []), routes.names.get(other["route_id"], []))
                (merged if ok else separate).append({"route_id": other["route_id"], **why})
            ev.update(merged=merged, not_merged=separate)
            if any(o["share"] == best["share"] for o in passing[1:]
                   if o["route_id"] in {s["route_id"] for s in separate}):
                ev["ambiguous"] = True     # tie between routes that may not merge: no alias
            else:
                chosen = best["route_id"]
        decisions[raw] = (chosen, ev)
    return decisions


def _route_row(raw, rid, routes: Routes, match_type: str, ev: dict) -> dict:
    if rid is None:
        p = parse_route(raw or "")
        return {"route_id": None, "short_name": None, "operator": None, "direction": p.direction,
                "is_ring": None, "is_devi": is_devi(raw or ""), "match_type": match_type, "evidence": ev}
    m = routes.meta[rid]
    return {"route_id": rid, "short_name": m["short_name"], "operator": m["operator"], "direction": m["direction"],
            "is_ring": m["is_ring"], "is_devi": m["is_devi"], "match_type": match_type, "evidence": ev}


def _majority_swaps(con, routes: Routes, route_map: dict) -> int:
    """Swap a route string to the opposite route when more than REMAP_MIN_REVERSED of its resolvable
    tickets come out reversed. Returns the number of strings swapped."""
    swapped = 0
    for raw, resolvable, reversed_ in con.execute("""
            SELECT t.route_raw, count(*) FILTER (WHERE p.outcome IN ('forward', 'ring_wrap', 'reversed')),
                   count(*) FILTER (WHERE p.outcome = 'reversed')
            FROM _placed p JOIN _tix t USING (ticket_id) GROUP BY ALL ORDER BY 1""").fetchall():
        if not resolvable or reversed_ / resolvable <= REMAP_MIN_REVERSED:
            continue
        cur = route_map[raw]
        counts = {"reversed": reversed_, "resolvable": resolvable, "share": round(reversed_ / resolvable, 4)}
        opp = routes.meta[cur["route_id"]]["opposite_route_id"]
        if opp is None:
            cur["evidence"]["majority_reversed_no_opposite"] = counts
            continue
        ev = {"rule": "majority_reversed", "from_route_id": cur["route_id"], "from_short_name": cur["short_name"],
              "to_route_id": opp, "before": cur["evidence"], **counts}
        route_map[raw] = _route_row(raw, opp, routes, "remap", ev)
        swapped += 1
    return swapped


# ---------------------------------------------------------------- stage

def _select_tickets(con, sample_routes) -> None:
    where, params = "", []
    if sample_routes is not None:
        where, params = "WHERE route_raw IN (SELECT unnest(?))", [list(sample_routes)]
    con.execute(f"CREATE OR REPLACE TEMP TABLE _tix AS SELECT ticket_id, route_raw, start_raw, end_raw, pax "
                f"FROM tickets_clean {where}", params)


def _write_outputs(con, route_map: dict) -> None:
    _load_arrow(con, "route_map", {
        "route_raw": pa.string(), "route_id": pa.int64(), "short_name": pa.string(), "operator": pa.string(),
        "direction": pa.string(), "is_ring": pa.bool_(), "is_devi": pa.bool_(), "match_type": pa.string(),
        "evidence": pa.string()},
        [(raw, m["route_id"], m["short_name"], m["operator"], m["direction"], m["is_ring"], m["is_devi"],
          m["match_type"], _ev(m["evidence"])) for raw, m in sorted(route_map.items(), key=lambda kv: kv[0] or "")])
    con.execute("""
        CREATE OR REPLACE TABLE tickets_resolved AS
        WITH f AS (
            SELECT ticket_id, route_id, orig_seq, dest_seq, outcome AS how FROM _placed WHERE outcome IN ('forward', 'ring_wrap')
            UNION ALL
            SELECT ticket_id, route_id, orig_seq, dest_seq, 'remapped' FROM _placed_opp WHERE outcome = 'forward')
        SELECT f.ticket_id, f.route_id, f.orig_seq::INT AS orig_seq, f.dest_seq::INT AS dest_seq, c.pax, c.vehicle,
               c.is_ac, c.ts, c.date, c.day_type, c.channel, c.amount, f.how
        FROM f JOIN tickets_clean c USING (ticket_id) ORDER BY f.ticket_id""")
    con.execute("""
        CREATE OR REPLACE TABLE tickets_rejected AS
        SELECT t.ticket_id, t.route_raw,
               CASE WHEN p.ticket_id IS NULL THEN 'unmatched_route' ELSE p.outcome END AS reason
        FROM _tix t LEFT JOIN _placed p USING (ticket_id) LEFT JOIN _placed_opp q USING (ticket_id)
        WHERE p.ticket_id IS NULL OR p.outcome IN ('unmatched_stop', 'same_stop')
           OR (p.outcome = 'reversed' AND (q.outcome IS NULL OR q.outcome <> 'forward'))
        ORDER BY t.ticket_id""")
    con.execute("""
        CREATE OR REPLACE TABLE dq_resolve AS
        SELECT r.reason, count(j.ticket_id)::BIGINT AS tickets, coalesce(sum(t.pax), 0)::BIGINT AS pax
        FROM (SELECT unnest(?) AS reason, unnest(range(4)) AS i) r
        LEFT JOIN tickets_rejected j ON j.reason = r.reason LEFT JOIN _tix t ON t.ticket_id = j.ticket_id
        GROUP BY r.reason, r.i ORDER BY r.i""", [list(REJECT_REASONS)])


def check_conservation(con, sample_routes: list[str] | None = None) -> None:
    """Gate: per route string, count(tickets_clean) == count(tickets_resolved) + count(tickets_rejected),
    and every clean ticket appears exactly once across the two. Raises GateError on the first failure."""
    where, params = "", []
    if sample_routes is not None:
        where, params = "WHERE route_raw IN (SELECT unnest(?))", [list(sample_routes)]
    bad = con.execute(f"""
        WITH c AS (SELECT coalesce(route_raw, '<NULL>') AS k, count(*) AS n FROM tickets_clean {where} GROUP BY 1),
        r AS (SELECT coalesce(t.route_raw, '<NULL>') AS k, count(*) AS n
              FROM tickets_resolved x LEFT JOIN tickets_clean t USING (ticket_id) GROUP BY 1),
        j AS (SELECT coalesce(route_raw, '<NULL>') AS k, count(*) AS n FROM tickets_rejected GROUP BY 1)
        SELECT k, coalesce(c.n, 0), coalesce(r.n, 0), coalesce(j.n, 0)
        FROM c FULL JOIN r USING (k) FULL JOIN j USING (k)
        WHERE coalesce(c.n, 0) <> coalesce(r.n, 0) + coalesce(j.n, 0) ORDER BY k LIMIT 1""", params).fetchone()
    if bad:
        raise GateError(f"resolve conservation gate failed for route {bad[0]!r}: {bad[1]} clean tickets != "
                        f"{bad[2]} resolved + {bad[3]} rejected")
    bad = con.execute(f"""
        WITH c AS (SELECT ticket_id, coalesce(route_raw, '<NULL>') AS k FROM tickets_clean {where}),
        o AS (SELECT ticket_id, count(*) AS n FROM (SELECT ticket_id FROM tickets_resolved
                                                    UNION ALL SELECT ticket_id FROM tickets_rejected) GROUP BY 1)
        SELECT coalesce(c.k, '<not in tickets_clean>'), ticket_id, coalesce(o.n, 0)
        FROM c FULL JOIN o USING (ticket_id)
        WHERE c.k IS NULL OR coalesce(o.n, 0) <> 1 ORDER BY 1, 2 LIMIT 1""", params).fetchone()
    if bad:
        raise GateError(f"resolve conservation gate failed for route {bad[0]!r}: ticket {bad[1]} appears "
                        f"{bad[2]} times in tickets_resolved + tickets_rejected")


def _stats(con, route_map: dict, swapped: int) -> ResolveStats:
    tickets, pax = con.execute("SELECT count(*), coalesce(sum(pax), 0) FROM _tix").fetchone()
    how = {h: (n, p) for h, n, p in con.execute(
        "SELECT how, count(*), coalesce(sum(pax), 0) FROM tickets_resolved GROUP BY 1").fetchall()}
    rejected = {r: n for r, n, _ in con.execute("SELECT reason, tickets, pax FROM dq_resolve").fetchall()}
    res_t = sum(n for n, _ in how.values())
    res_p = sum(p for _, p in how.values())
    types = defaultdict(int)
    for m in route_map.values():
        types[m["match_type"]] += 1
    return ResolveStats(
        tickets=tickets, pax=int(pax), resolved_tickets=res_t, resolved_pax=int(res_p),
        match_rate=res_p / pax if pax else 0.0, forward=how.get("forward", (0, 0))[0],
        remapped=how.get("remapped", (0, 0))[0], ring_wrap=how.get("ring_wrap", (0, 0))[0],
        aliases=types["alias"], routes_remapped=swapped,
        routes={k: types[k] for k in ("exact", "alias", "remap", "unmatched")}, rejected=rejected)


def _report(con, stats: ResolveStats, matches: _StopMatches) -> None:
    r = stats.routes
    print(f"resolve: {sum(r.values()):,} route strings: exact {r['exact']:,}, alias {r['alias']:,}, "
          f"remap {r['remap']:,}, unmatched {r['unmatched']:,}")
    c = matches.counts
    print(f"resolve: {sum(c.values()):,} (route, stop name) pairs matched: exact {c['exact']:,}, "
          f"fuzzy {c['fuzzy']:,}, unmatched {c['unmatched']:,}")
    print(f"resolve: resolved {stats.resolved_tickets:,} of {stats.tickets:,} tickets; "
          f"{stats.resolved_pax:,} of {stats.pax:,} passengers = {stats.match_rate:.2%} passenger match rate")
    print(f"resolve: how forward {stats.forward:,}, remapped {stats.remapped:,}, ring_wrap {stats.ring_wrap:,}")
    parts = [f"{reason} {n:,} tickets / {p:,} pax" for reason, n, p in
             con.execute("SELECT reason, tickets, pax FROM dq_resolve").fetchall()]
    print("resolve: rejected " + "; ".join(parts))


def run(con, paths, sample_routes: list[str] | None = None) -> ResolveStats:
    build_canonical(con, paths.gtfs_dir)
    routes = build_route_meta(con)
    _select_tickets(con, sample_routes)
    matches = _StopMatches(con, routes.indexes)

    strings = [r[0] for r in con.execute("SELECT DISTINCT route_raw FROM _tix ORDER BY 1").fetchall()]
    route_map, no_exact = {}, []
    for raw in strings:
        rid = routes.by_short.get(raw.strip()) if raw is not None else None
        if rid is not None:
            route_map[raw] = _route_row(raw, rid, routes, "exact", {"rule": "exact"})
        else:
            no_exact.append(raw)
    for raw, (rid, ev) in _alias_decisions(con, routes, matches, no_exact).items():
        route_map[raw] = _route_row(raw, rid, routes, "alias" if rid is not None else "unmatched", ev)

    _assign_from_map(con, route_map)
    matches.ensure("_assign")
    _place(con, "_assign", "_placed")
    swapped = _majority_swaps(con, routes, route_map)
    if swapped:
        _assign_from_map(con, route_map)
        matches.ensure("_assign")
        _place(con, "_assign", "_placed")

    # Minority rule: a reversed ticket stays if it runs forward on the opposite route.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _assign_opp AS
        SELECT p.ticket_id, m.opposite_route_id AS route_id
        FROM _placed p JOIN route_meta m USING (route_id)
        WHERE p.outcome = 'reversed' AND m.opposite_route_id IS NOT NULL""")
    matches.ensure("_assign_opp")
    _place(con, "_assign_opp", "_placed_opp")

    _write_outputs(con, route_map)
    check_conservation(con, sample_routes)
    stats = _stats(con, route_map, swapped)
    _report(con, stats, matches)
    for t in ("_tix", "_stop_match", "_rm", "_assign", "_placed", "_assign_opp", "_placed_opp", "_alias_cand",
              "_assign_alias", "_placed_alias", "_gtfs_routes"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    return stats
