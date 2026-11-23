"""Stage 6: validation suite (design 5.8) and the numbers every document quotes.

A. Invariants that stop the run (GateError). B. Expectations written down before the first full run.
C. Week-to-week repeatability. D. Published-figure checks. E. Sensitivity. F. Diagnostics.
Everything outside A is reported, never raised: a miss is a miss.

The whole stage reuses the loads machinery (`loads._eligible`, `_supply`, `_rider_cells`, `_cells`, `_scale`,
`_build_crowding`) in DuckDB SQL, so a variant is the same model with one input changed. The base case is
rebuilt first and must reproduce the stored stretch_crowding exactly.
"""
import json
import math
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import loads, network
from .config import (BUS_SPECS, CENTRE_POINTS, CORRIDOR_TOP_QUANTILE, E_SCALE_CEILING_MULT, HACKATHON_APP_TICKET_SHARE,
                     OVER_CAPACITY_TOP_ROUTES, PAIR_WINDOW_ALTERNATIVE, PUBLISHED_RIDERSHIP,
                     PUBLISHED_WOMEN_FREE_JOURNEYS, RADIAL_AM, RADIAL_NEAR_KM, RADIAL_PM,
                     RADIAL_SPREAD_KM, RESOLUTION_MIN_SHARE, RESOLUTION_MIN_TICKETS, RUNTIME_GATE_TOL, S0_MAX_SHARE,
                     SENSITIVITY_9M_SHARE, SENSITIVITY_CAPACITY, SENSITIVITY_CEILINGS, SENSITIVITY_E, TICKET_BANDS,
                     WEEK_BLOCKS, WINDOWS, WOMEN_FREE_PERIOD_DAYS)
from .errors import GateError
from .expectations import load_expectations

STRETCH_COLUMNS = ["route_id", "short_name", "operator", "direction", "seq", "from_stop_id", "to_stop_id",
                   "from_name", "to_name", "day_type", "window_start_min", "app_riders", "tickets", "buses",
                   "bus_source", "share_9m", "seats", "rated_total", "crush", "E_r", "people_mid", "people_low",
                   "people_high", "level", "evidence", "flags"]
KEY = ["route_id", "day_type", "seq", "window_start_min"]
RANK = "CASE {c} WHEN 'seats' THEN 0 WHEN 'standing' THEN 1 ELSE 2 END"
LEVELS = ("seats", "standing", "crowded", "no_data")
EVIDENCE = ("many_tickets", "rough", "none")
FORBIDDEN = ("κ", "kappa", "McRAPTOR", "Pareto", "sigmoid", "score")


# =================================================================== A. gates

def check_finite(con, table: str = "stretch_crowding") -> int:
    """Gate: no NaN or inf in the people estimates or E_r. Returns 0 when clean."""
    bad = con.execute(f"""
        SELECT count(*) FROM {table}
        WHERE (people_mid IS NOT NULL AND NOT isfinite(people_mid))
           OR (people_low IS NOT NULL AND NOT isfinite(people_low))
           OR (people_high IS NOT NULL AND NOT isfinite(people_high))
           OR ("E_r" IS NOT NULL AND NOT isfinite("E_r"))""").fetchone()[0]
    if bad:
        raise GateError(f"finite gate: {bad:,} {table} rows hold NaN or inf in people_mid/low/high or E_r")
    return 0


def check_schema(con, table: str = "stretch_crowding") -> int:
    have = {r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()}
    missing = [c for c in STRETCH_COLUMNS if c not in have]
    if missing:
        raise GateError(f"schema gate: {table} lacks columns {missing}")
    return len(have)


def run_gates(con) -> dict:
    """Re-run every invariant against the tables as they stand; raises GateError on the first failure."""
    from .resolve import check_conservation
    out = {}
    check_conservation(con)
    n_clean, n_res, n_rej = con.execute(
        "SELECT (SELECT count(*) FROM tickets_clean), (SELECT count(*) FROM tickets_resolved), "
        "(SELECT count(*) FROM tickets_rejected)").fetchone()
    out["ticket_conservation"] = {"passed": True, "clean": n_clean, "resolved": n_res, "rejected": n_rej,
                                  "rule": "raw = resolved + rejected per route string, each ticket exactly once"}
    dev = loads.check_rider_gate(con)
    out["rider_minutes"] = {"passed": True, "deviation": dev, "limit": loads.GATE_TOLERANCE,
                            "rule": "stretch rider-minutes + excluded + moved = resolved-ticket rider-minutes"}
    dql = dict(con.execute("SELECT name, value FROM dq_levels").fetchall())
    s0 = dql["s0_mismatch_share"]
    if s0 >= S0_MAX_SHARE:
        raise GateError(f"supply gate: {s0:.2%} of rider volume has no scheduled bus (limit {S0_MAX_SHARE:.0%})")
    out["supply"] = {"passed": True, "share": s0, "limit": S0_MAX_SHARE,
                     "widened_share": dql["s0_widened_share"],
                     "rule": "rider volume with no scheduled bus after the fallback stays under 1%"}
    dqc = dict(con.execute("SELECT name, value FROM dq_clock").fetchall())
    if dqc["gate_max_dev"] > RUNTIME_GATE_TOL:
        raise GateError(f"clock gate: modelled run time off by {dqc['gate_max_dev']:.1%}")
    out["run_times"] = {"passed": True, "max_deviation": dqc["gate_max_dev"], "limit": RUNTIME_GATE_TOL,
                        "cells": dqc["gate_cells"],
                        "rule": "modelled hourly run times within 15% of ticket-pair run times"}
    out["time_zone"] = {"passed": True, "rule": "fixture tests (tests/test_clean.py, tests/test_config.py, "
                        "tests/test_loads_riders.py) pin every operation to Asia/Kolkata",
                        "evidence": "test suite"}
    out["schema"] = {"passed": True, "columns": check_schema(con)}
    out["finite"] = {"passed": check_finite(con) == 0, "rule": "no NaN or inf in people_mid/low/high or E_r"}
    return out


# =================================================================== pure helpers (tested)

def published_check(value: float, band) -> dict:
    """Hit when value lies inside the band; a miss is reported, never raised."""
    lo, hi = band
    pos = "below" if value < lo else "above" if value > hi else "inside"
    return {"value": float(value), "band": [float(lo), float(hi)], "hit": pos == "inside", "position": pos}


def peak_rule(hourly, am, pm) -> dict:
    """The morning peak (busiest hour 05-13) must fall in [am0, am1) and the evening peak (14-23) in [pm0, pm1)."""
    h = np.nan_to_num(np.asarray(hourly, dtype=float))
    am_h = int(np.argmax(h[5:14])) + 5
    pm_h = int(np.argmax(h[14:24])) + 14
    am_hit = bool(h[5:14].max() > 0 and am[0] <= am_h < am[1])
    pm_hit = bool(h[14:24].max() > 0 and pm[0] <= pm_h < pm[1])
    return {"am_peak_hour": am_h, "pm_peak_hour": pm_h, "am_hit": am_hit, "pm_hit": pm_hit,
            "hit": am_hit and pm_hit}


def weekend_rule(weekday_hourly, weekend_hourly) -> dict:
    """Weekend crowded rider-minutes lower, profile flatter (smaller peak-to-mean), peak hour later."""
    wd = np.nan_to_num(np.asarray(weekday_hourly, dtype=float))
    we = np.nan_to_num(np.asarray(weekend_hourly, dtype=float))

    def ptm(x):
        return float(x.max() / x.mean()) if x.sum() > 0 else float("nan")

    lower = bool(we.sum() < wd.sum())
    flatter = bool(ptm(we) < ptm(wd))
    later = bool(we.sum() > 0 and wd.sum() > 0 and int(we.argmax()) > int(wd.argmax()))
    return {"weekday_total": float(wd.sum()), "weekend_total": float(we.sum()),
            "weekday_peak_to_mean": ptm(wd), "weekend_peak_to_mean": ptm(we),
            "weekday_peak_hour": int(wd.argmax()), "weekend_peak_hour": int(we.argmax()),
            "lower": lower, "flatter": flatter, "later_peak": later, "hit": lower and flatter and later}


def corridor_hit(values: pd.DataFrame, mapped, window, q: float = CORRIDOR_TOP_QUANTILE) -> dict:
    """values(pair_id, window_start_min, rm_per_km), weekday. A corridor is a hit when one of its mapped stretches
    is in the network's top decile of crowded rider-minutes per km summed over the windows in [w0, w1)."""
    sub = values[(values["window_start_min"] >= window[0]) & (values["window_start_min"] < window[1])]
    v = sub.groupby("pair_id")["rm_per_km"].sum()
    if v.empty:
        return {"hit": False, "threshold": None, "n_pairs": 0, "n_mapped": 0, "best": None, "best_pair": None,
                "best_percentile": None, "top_decile_share": None, "chance_hit_probability": 0.0}
    thr = float(v.quantile(q))
    m = v[v.index.isin(set(mapped))]
    top = (m >= thr) & (m > 0)
    hit = bool(len(m) and top.any())
    best = float(m.max()) if len(m) else None
    p_top = float(((v >= thr) & (v > 0)).mean())  # network-wide share in the top decile (0.1 unless ties or zeros)
    return {"hit": hit, "threshold": thr, "n_pairs": int(len(v)), "n_mapped": int(len(m)), "best": best,
            "top_decile_share": float(top.mean()) if len(m) else None,
            "chance_hit_probability": float(1 - (1 - p_top) ** len(m)) if len(m) else 0.0,
            "best_pair": str(m.idxmax()) if len(m) else None,
            "best_percentile": float((v < best).mean()) if best is not None else None}


def radial_hit(in_am: float, out_am: float, in_pm: float, out_pm: float) -> dict:
    """A route pair is a hit when the inbound direction is busier in the AM and the outbound busier in the PM."""
    am, pm = bool(in_am > out_am), bool(out_pm > in_pm)
    return {"am": am, "pm": pm, "hit": am and pm}


def level_change_counts(people_mid, seats, rated_total, mult: float) -> dict:
    """Cells whose level changes when people on board are multiplied by mult (each cell counted once)."""
    p = np.asarray(people_mid, dtype=float)
    s, r = np.asarray(seats, dtype=float), np.asarray(rated_total, dtype=float)
    old, new = loads._level_v(p, s, r), loads._level_v(p * mult, s, r)
    return {"cells": int(len(p)), "changed": int((old != new).sum()),
            "share": float((old != new).mean()) if len(p) else 0.0}


def _band_case(col: str) -> str:
    parts = []
    for lo, hi, name in TICKET_BANDS:
        cond = f"{col} >= {lo}" if hi is None else f"{col} BETWEEN {lo} AND {hi}"
        parts.append(f"WHEN {cond} THEN '{name}'")
    return "CASE " + " ".join(parts) + " ELSE 'other' END"


def compare_levels(con, a: str, b: str, weights: str | None = None) -> dict:
    """Levels of table a vs table b on shared cells that are commuter-facing (not no_data) in both.
    `weights` is a table with the key columns plus weight and tickets (rider weights and ticket bands)."""
    on = " AND ".join(f"a.{k} = b.{k}" for k in KEY)
    if weights:
        join = f"LEFT JOIN {weights} w ON " + " AND ".join(f"a.{k} = w.{k}" for k in KEY)
        wsel, band = "coalesce(w.weight, 0)", _band_case("coalesce(w.tickets, 0)")
    else:
        join, wsel, band = "", "1.0", "'all'"
    rows = con.execute(f"""
        SELECT band, count(*) AS n, sum(same) AS same_n, sum(w) AS wt, sum(w * same) AS wsame,
               sum((rb > ra)::INT) AS more, sum((rb < ra)::INT) AS less
        FROM (SELECT {band} AS band, {wsel} AS w, (a.level = b.level)::INT AS same,
                     {RANK.format(c='a.level')} AS ra, {RANK.format(c='b.level')} AS rb
              FROM {a} a JOIN {b} b ON {on} {join}
              WHERE a.level <> 'no_data' AND b.level <> 'no_data')
        GROUP BY ROLLUP(band) ORDER BY band NULLS LAST""").fetchall()

    def row(r):
        _, n, same, wt, wsame, more, less = r
        return {"cells": int(n), "changed": int(n - same), "unchanged_share": float(same / n) if n else None,
                "unchanged_share_rider_weighted": float(wsame / wt) if wt else (float(same / n) if n else None),
                "more_crowded": int(more), "less_crowded": int(less)}
    overall = next((row(r) for r in rows if r[0] is None), {"cells": 0, "changed": 0, "unchanged_share": None,
                                                           "unchanged_share_rider_weighted": None,
                                                           "more_crowded": 0, "less_crowded": 0})
    return {**overall, "bands": {r[0]: row(r) for r in rows if r[0] is not None}}


def load_corr(con, a: str, b: str) -> dict:
    """Correlation of route-direction-hour loads (mean people on board over the stretches of an on-the-hour window)."""
    def agg(t):
        return (f"(SELECT route_id, day_type, window_start_min // 60 AS h, avg(people_mid) AS m FROM {t} "
                f"WHERE window_start_min % 60 = 0 AND people_mid IS NOT NULL GROUP BY ALL)")
    r, n = con.execute(f"SELECT corr(x.m, y.m), count(*) FROM {agg(a)} x JOIN {agg(b)} y "
                       f"USING (route_id, day_type, h)").fetchone()
    return {"correlation": None if r is None or (isinstance(r, float) and math.isnan(r)) else float(r),
            "route_hours": int(n)}


def range_coverage(con, train: str, held: str, weights: str | None = None) -> dict:
    """Share of shared commuter-facing cells whose held-out estimate falls inside the training range."""
    on = " AND ".join(f"t.{k} = h.{k}" for k in KEY)
    if weights:
        join = f"LEFT JOIN {weights} w ON " + " AND ".join(f"t.{k} = w.{k}" for k in KEY)
        wsel, band = "coalesce(w.weight, 0)", _band_case("coalesce(w.tickets, 0)")
    else:
        join, wsel, band = "", "1.0", "'all'"
    rows = con.execute(f"""
        SELECT band, count(*), sum(inside), sum(w), sum(w * inside)
        FROM (SELECT {band} AS band, {wsel} AS w,
                     (h.people_mid BETWEEN t.people_low AND t.people_high)::INT AS inside
              FROM {train} t JOIN {held} h ON {on} {join}
              WHERE t.people_mid IS NOT NULL AND h.people_mid IS NOT NULL)
        GROUP BY ROLLUP(band) ORDER BY band NULLS LAST""").fetchall()

    def row(r):
        return {"cells": int(r[1]), "coverage": float(r[2] / r[1]) if r[1] else None,
                "coverage_rider_weighted": float(r[4] / r[3]) if r[3] else (float(r[2] / r[1]) if r[1] else None)}
    overall = next((row(r) for r in rows if r[0] is None), {"cells": 0, "coverage": None,
                                                           "coverage_rider_weighted": None})
    return {**overall, "bands": {r[0]: row(r) for r in rows if r[0] is not None}}


# =================================================================== model rebuilds (variants)

def _prepare_cells(con, skip=()) -> None:
    """The rider/supply cell tables of loads.run_levels, optionally leaving dates out."""
    nd = loads.effective_days(con, skip)
    nday = loads.clean_day_totals(con, skip)
    loads._eligible(con)
    loads._supply(con)
    loads._rider_cells(con, skip)
    loads._cells(con, nd)
    loads._route_level(con, sum(nday.values()), skip)
    loads._low_app_use(con, nday, skip)


def _levels(con, out: str, specs: str = "route_specs", use_bound: bool = True,
            ceil_mult: float = E_SCALE_CEILING_MULT, e_mult: float = 1.0) -> dict:
    ops = loads._scale(con, "_cell", specs, use_bound, ceil_mult)[5]
    loads._build_crowding(con, out=out, specs=specs, e_mult=e_mult, temp=True)
    return ops


def _spec_tables(con) -> None:
    s9, s12, sn = BUS_SPECS["9m_devi"], BUS_SPECS["12m_ac"], BUS_SPECS["12m_nonac"]
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _sp_comfort AS
        SELECT s.route_id, s.seats, b.share_9m * {s9.comfortable} + b.share_12m_ac * {s12.comfortable}
               + b.share_12m_nonac * {sn.comfortable} AS rated_total, s.crush
        FROM route_specs s JOIN bus_mix b USING (route_id)""")
    for name, m in (("capm", 1 - SENSITIVITY_CAPACITY), ("capp", 1 + SENSITIVITY_CAPACITY)):
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _sp_{name} AS
            SELECT route_id, seats * {m} AS seats, rated_total * {m} AS rated_total, crush * {m} AS crush
            FROM route_specs""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _sp_9m AS
        WITH v AS (SELECT t.route_id, count(*) FILTER (WHERE t.vehicle IS NOT NULL) AS n_veh,
                          count(*) FILTER (WHERE d.vehicle IS NOT NULL) AS n_devi
                   FROM tickets_resolved t LEFT JOIN devi_vehicles d ON d.vehicle = t.vehicle GROUP BY 1),
        m AS (SELECT b.route_id, b.share_9m, b.share_12m_ac, b.share_12m_nonac, b.basis,
                     CASE WHEN v.n_veh > 0 THEN v.n_devi::DOUBLE / v.n_veh ELSE 0 END AS dshare
              FROM bus_mix b LEFT JOIN v USING (route_id)),
        n AS (SELECT route_id,
                     CASE WHEN basis = 'vehicle_rule' AND dshare < {SENSITIVITY_9M_SHARE} THEN 0.0 ELSE share_9m END AS a9,
                     CASE WHEN basis = 'vehicle_rule' AND dshare < {SENSITIVITY_9M_SHARE}
                          THEN share_12m_ac / (1 - share_9m) ELSE share_12m_ac END AS ac,
                     CASE WHEN basis = 'vehicle_rule' AND dshare < {SENSITIVITY_9M_SHARE}
                          THEN share_12m_nonac / (1 - share_9m) ELSE share_12m_nonac END AS nonac
              FROM m)
        SELECT route_id, a9 * {s9.seats} + ac * {s12.seats} + nonac * {sn.seats} AS seats,
               a9 * {s9.rated_total} + ac * {s12.rated_total} + nonac * {sn.rated_total} AS rated_total,
               a9 * {s9.crush} + ac * {s12.crush} + nonac * {sn.crush} AS crush
        FROM n""")


def _weights(con) -> None:
    con.execute("""CREATE OR REPLACE TEMP TABLE _wt AS
        SELECT route_id, day_type, seq, window_start_min, app_riders AS weight, tickets FROM stretch_crowding""")


def _ops_summary(ops: dict) -> dict:
    return {op: {"e_star": o["e_star"], "capped_routes": o["capped_routes"],
                 "unallocated_share": o["unallocated_share"], "ceiling_bound": o["ceiling_bound"]}
            for op, o in ops.items()}


def _reproduction(con) -> dict:
    """The base case rebuilt from the cell tables must equal the stored stretch_crowding."""
    _prepare_cells(con)
    ops = _levels(con, "_lv_base")
    on = " AND ".join(f"a.{k} = b.{k}" for k in KEY)
    n, same_l, same_e, same_p = con.execute(f"""
        SELECT count(*), sum((a.level = b.level)::INT), sum((a.evidence = b.evidence)::INT),
               sum((abs(coalesce(a.people_mid, -1) - coalesce(b.people_mid, -1)) < 1e-6)::INT)
        FROM stretch_crowding a JOIN _lv_base b ON {on}""").fetchone()
    total = con.execute("SELECT count(*) FROM stretch_crowding").fetchone()[0]
    return {"rows_stored": int(total), "rows_matched": int(n), "level_equal": int(same_l or 0),
            "evidence_equal": int(same_e or 0), "people_mid_equal": int(same_p or 0),
            "exact": bool(n == total and same_l == n and same_e == n and same_p == n), "ops": _ops_summary(ops)}


def sensitivity(con, paths) -> dict:
    """E +-30%, comfortable thresholds, capacity +-10%, 9 m rule at 90%, no alighting correction, no capacity
    bound, plus the E* ceiling multiplier at 2x and 5x (R21). Share of commuter-facing cells changing level."""
    _weights(con)
    _spec_tables(con)
    cases = [
        ("e_minus_30", f"E x {1 - SENSITIVITY_E:g}", dict(e_mult=1 - SENSITIVITY_E)),
        ("e_plus_30", f"E x {1 + SENSITIVITY_E:g}", dict(e_mult=1 + SENSITIVITY_E)),
        ("comfortable", "comfortable-capacity thresholds (12 m 77/79, 9 m 32) replace the rated totals",
         dict(specs="_sp_comfort")),
        ("capacity_minus_10", "bus capacity -10%", dict(specs="_sp_capm")),
        ("capacity_plus_10", "bus capacity +10%", dict(specs="_sp_capp")),
        ("vehicle_rule_90", f"9 m vehicle rule at {SENSITIVITY_9M_SHARE:.0%} instead of 50%", dict(specs="_sp_9m")),
        ("no_capacity_bound", "capacity bound switched off (E = operator scale on every route)",
         dict(use_bound=False)),
    ] + [(f"ceiling_{c:g}x", f"E* ceiling {c:g} x E_op instead of {E_SCALE_CEILING_MULT:g} x", dict(ceil_mult=c))
         for c in SENSITIVITY_CEILINGS]
    out = {}
    _prepare_cells(con)
    for key, text, kw in cases:
        ops = _levels(con, "_lv_x", **kw)
        cmp = compare_levels(con, "stretch_crowding", "_lv_x", "_wt")
        out[key] = {"description": text, **{k: cmp[k] for k in ("cells", "more_crowded", "less_crowded")},
                    "changed": cmp["changed"],
                    "share_changed": 1 - cmp["unchanged_share"] if cmp["cells"] else None,
                    "share_changed_rider_weighted": 1 - cmp["unchanged_share_rider_weighted"] if cmp["cells"] else None,
                    "operators": _ops_summary(ops)}
    out["no_alighting_correction"] = _alighting_off(con, paths)
    con.execute("DROP TABLE IF EXISTS _lv_x")
    return out


def _alighting_off(con, paths) -> dict:
    """Rebuild stretch_riders without the terminal alighting correction, recompute levels, restore the tables."""
    con.execute("CREATE OR REPLACE TEMP TABLE _bk_riders AS SELECT * FROM stretch_riders")
    con.execute("CREATE OR REPLACE TEMP TABLE _bk_asym AS SELECT * FROM terminal_asymmetry")
    con.execute("CREATE OR REPLACE TEMP TABLE _bk_dq AS SELECT * FROM dq_riders")
    try:
        loads.run_riders(con, paths, correct_alighting=False)
        _prepare_cells(con)
        ops = _levels(con, "_lv_x")
        cmp = compare_levels(con, "stretch_crowding", "_lv_x", "_wt")
    finally:
        con.execute("CREATE OR REPLACE TABLE stretch_riders AS "
                    "SELECT * FROM _bk_riders ORDER BY route_id, date, seq, minute")
        con.execute("CREATE OR REPLACE TABLE terminal_asymmetry AS SELECT * FROM _bk_asym ORDER BY route_id")
        con.execute("CREATE OR REPLACE TABLE dq_riders AS SELECT * FROM _bk_dq")
        for t in ("_bk_riders", "_bk_asym", "_bk_dq"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
    return {"description": "terminal alighting correction switched off",
            "cells": cmp["cells"], "more_crowded": cmp["more_crowded"], "less_crowded": cmp["less_crowded"],
            "changed": cmp["changed"],
            "share_changed": 1 - cmp["unchanged_share"] if cmp["cells"] else None,
            "share_changed_rider_weighted": 1 - cmp["unchanged_share_rider_weighted"] if cmp["cells"] else None,
            "operators": _ops_summary(ops)}


# =================================================================== C. repeatability

def _block_dates(con) -> list[tuple[str, list[str]]]:
    rows = con.execute("SELECT date FROM clean_days WHERE day_type = 'weekday' AND NOT is_excluded_date "
                       "ORDER BY date").fetchall()
    days = [d[0] for d in rows]
    out = []
    for a, b in WEEK_BLOCKS:
        da, db = date.fromisoformat(a), date.fromisoformat(b)
        ds = [str(d) for d in days if da <= d <= db]
        out.append((f"{da.day}-{db.day} Oct", ds))
    return out


def _slim(con, name: str, src: str = "_lv") -> None:
    con.execute(f"""CREATE OR REPLACE TEMP TABLE {name} AS
        SELECT route_id, day_type, seq, window_start_min, level, people_mid, people_low, people_high
        FROM {src} WHERE day_type = 'weekday'""")


def repeatability(con) -> dict:
    """Leave one weekday block out in turn (T_k: the other blocks), and each block alone (H_k)."""
    con.execute("""CREATE OR REPLACE TEMP TABLE _wtw AS SELECT * FROM _wt WHERE day_type = 'weekday'""")
    blocks = [(n, ds) for n, ds in _block_dates(con) if ds]
    all_days = {d for _, ds in blocks for d in ds}
    allwd = [str(r[0]) for r in con.execute(
        "SELECT date FROM clean_days WHERE day_type = 'weekday' AND NOT is_excluded_date").fetchall()]
    built = []
    for i, (name, ds) in enumerate(blocks):
        for tag, skip in (("T", ds), ("H", [d for d in allwd if d not in ds])):
            _prepare_cells(con, skip)
            if con.execute("SELECT count(*) FROM _cell").fetchone()[0] == 0:
                continue
            _levels(con, "_lv")
            _slim(con, f"_rp_{tag}{i}")
            built.append(f"{tag}{i}")
    names = [n for n, _ in blocks]
    full = "stretch_crowding"
    res = {"blocks": [{"name": n, "dates": ds, "clean_days": len(ds)} for n, ds in blocks],
           "weekday_dates_outside_blocks": sorted(set(allwd) - all_days),
           "method": ("Leave-one-out: levels are recomputed from the other weekday blocks (T). Week pairs: each block "
                      "alone (H) is compared with another block alone, which is the independent week-to-week test. "
                      "Weekend days stay in every run so the operator scale has the same basis. Cells are weekday "
                      "commuter-facing cells present in both runs; rider-weighted by full-month app riders.")}
    res["leave_one_out"] = [
        {"left_out": names[i], **compare_levels(con, f"_rp_T{i}", full, "_wtw"),
         "load": load_corr(con, f"_rp_T{i}", full)} for i in range(len(blocks)) if f"T{i}" in built]
    res["leave_one_out_pairs"] = [
        {"pair": f"{names[i]} vs {names[j]}", **compare_levels(con, f"_rp_T{i}", f"_rp_T{j}", "_wtw"),
         "load": load_corr(con, f"_rp_T{i}", f"_rp_T{j}")}
        for i in range(len(blocks)) for j in range(i + 1, len(blocks)) if f"T{i}" in built and f"T{j}" in built]
    res["week_pairs"] = [
        {"pair": f"{names[i]} vs {names[j]}", **compare_levels(con, f"_rp_H{i}", f"_rp_H{j}", "_wtw"),
         "load": load_corr(con, f"_rp_H{i}", f"_rp_H{j}")}
        for i in range(len(blocks)) for j in range(i + 1, len(blocks)) if f"H{i}" in built and f"H{j}" in built]
    res["heldout_range_coverage"] = [
        {"held_out": names[i], **range_coverage(con, f"_rp_T{i}", f"_rp_H{i}", "_wtw")}
        for i in range(len(blocks)) if f"T{i}" in built and f"H{i}" in built]

    def mean(rows, key):
        v = [r[key] for r in rows if r.get(key) is not None]
        return float(np.mean(v)) if v else None

    def mean_corr(rows):
        v = [r["load"]["correlation"] for r in rows if r["load"]["correlation"] is not None]
        return float(np.mean(v)) if v else None
    res["summary"] = {
        "unchanged_level_share": mean(res["week_pairs"], "unchanged_share_rider_weighted"),
        "unchanged_level_share_cells": mean(res["week_pairs"], "unchanged_share"),
        "load_correlation": mean_corr(res["week_pairs"]),
        "unchanged_level_share_leave_one_out": mean(res["leave_one_out"], "unchanged_share_rider_weighted"),
        "unchanged_level_share_leave_one_out_cells": mean(res["leave_one_out"], "unchanged_share"),
        "load_correlation_leave_one_out": mean_corr(res["leave_one_out"]),
        "unchanged_level_share_leave_one_out_pairs": mean(res["leave_one_out_pairs"], "unchanged_share_rider_weighted"),
        "range_coverage": mean(res["heldout_range_coverage"], "coverage_rider_weighted"),
        "range_coverage_cells": mean(res["heldout_range_coverage"], "coverage"),
    }
    # by ticket band, pooled over the week pairs
    bands = {}
    for _, _, b in TICKET_BANDS:
        rows = [r["bands"][b] for r in res["week_pairs"] if b in r["bands"]]
        v = [r["unchanged_share_rider_weighted"] for r in rows if r["unchanged_share_rider_weighted"] is not None]
        bands[b] = {"unchanged_level_share": float(np.mean(v)) if v else None,
                    "cells": int(sum(r["cells"] for r in rows))}
    res["summary"]["by_ticket_band"] = bands
    for t in built:
        con.execute(f"DROP TABLE IF EXISTS _rp_{t}")
    return res


# =================================================================== B/D. expectations and published checks

def _hourly(con, day_type: str) -> np.ndarray:
    h = np.zeros(24)
    for hr, v in con.execute("SELECT window_start_min // 60, sum(crowded_rider_min) FROM corridor_values "
                             "WHERE day_type = ? GROUP BY 1", [day_type]).fetchall():
        h[int(hr)] = float(v)
    return h


def _pair_table(con) -> pd.DataFrame:
    return con.execute("""
        SELECT p.from_stop_id || '-' || p.to_stop_id AS pair_id, any_value(p.from_name) AS from_name,
               any_value(p.to_name) AS to_name, median(sh.length_m) / 1000.0 AS km,
               any_value(a.lat) AS lat0, any_value(a.lon) AS lon0, any_value(b.lat) AS lat1, any_value(b.lon) AS lon1
        FROM _pair p
        JOIN canonical_stops a ON a.route_id = p.route_id AND a.seq = p.seq
        JOIN canonical_stops b ON b.route_id = p.route_id AND b.seq = p.seq + 1
        JOIN segment_shapes sh ON sh.route_id = p.route_id AND sh.seq = p.seq + 1
        GROUP BY ALL HAVING median(sh.length_m) > 0""").df()


def _heading_ok(direction: str | None, lat0, lon0, lat1, lon1) -> np.ndarray:
    n = len(lat0)
    if not direction:
        return np.ones(n, dtype=bool)
    dy = np.asarray(lat1) - np.asarray(lat0)
    dx = (np.asarray(lon1) - np.asarray(lon0)) * np.cos(np.radians(np.asarray(lat0)))
    d = direction.lower()
    if d.startswith("east"):
        return (dx > 0) & (np.abs(dx) >= np.abs(dy))
    if d.startswith("west"):
        return (dx < 0) & (np.abs(dx) >= np.abs(dy))
    if d.startswith("north"):
        return (dy > 0) & (np.abs(dy) >= np.abs(dx))
    if d.startswith("south"):
        return (dy < 0) & (np.abs(dy) >= np.abs(dx))
    return np.ones(n, dtype=bool)


CHANCE_DRAWS = 2000
CHANCE_SEED = 25


def chance_expected_hits(values: pd.DataFrame, specs: list, windows: dict, draws: int = CHANCE_DRAWS,
                         seed: int = CHANCE_SEED) -> dict:
    """R25: expected hits if each corridor's number of stretches were drawn at random (without replacement) from the
    weekday stretches with service. specs: [(n_stretches, [peaks])]. Seeded simulation; a hit means a drawn stretch is
    in the top decile of its peak window (same rule as corridor_hit)."""
    per = {}
    for pk, w in windows.items():
        sub = values[(values["window_start_min"] >= w[0]) & (values["window_start_min"] < w[1])]
        per[pk] = sub.groupby("pair_id")["rm_per_km"].sum()
    universe = sorted(set().union(*[set(v.index) for v in per.values()])) if per else []
    if not universe:
        return {"method": "none", "expected_hits": 0.0, "per_corridor": [0.0] * len(specs)}
    arr = {pk: v.reindex(universe).fillna(0.0).to_numpy() for pk, v in per.items()}
    top = {pk: (arr[pk] >= (per[pk].quantile(CORRIDOR_TOP_QUANTILE) if len(per[pk]) else np.inf)) & (arr[pk] > 0)
           for pk in arr}
    rng = np.random.default_rng(seed)
    probs = []
    for n, peaks in specs:
        n = min(int(n), len(universe))
        if n == 0:
            probs.append(0.0)
            continue
        hits = 0
        for _ in range(draws):
            idx = rng.choice(len(universe), size=n, replace=False)
            hits += any(top[pk][idx].any() for pk in peaks)
        probs.append(hits / draws)
    return {"method": f"seeded simulation, {draws} draws per corridor, seed {seed}, stretches drawn without "
                      f"replacement from the {len(universe):,} weekday stretches with service",
            "expected_hits": float(sum(probs)), "per_corridor": probs}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def corridors(con, exp) -> dict:
    pt = _pair_table(con)
    cv = con.execute("""SELECT pair_id, window_start_min, crowded_rider_min FROM corridor_values
                        WHERE day_type = 'weekday'""").df()
    cv = cv.merge(pt[["pair_id", "km"]], on="pair_id")
    cv["rm_per_km"] = cv["crowded_rider_min"].astype(float) / cv["km"]
    windows = {"am": tuple(h * 60 for h in exp.peaks["am"]), "pm": tuple(h * 60 for h in exp.peaks["pm"])}
    names_in_net = set(pt["from_name"]) | set(pt["to_name"])
    out = []
    for c in exp.corridors:
        names = set(c.gtfs_stop_names)
        either = pt["from_name"].isin(names) | pt["to_name"].isin(names)
        both = pt["from_name"].isin(names) & pt["to_name"].isin(names)
        ok = _heading_ok(c.direction, pt["lat0"].to_numpy(), pt["lon0"].to_numpy(), pt["lat1"].to_numpy(),
                         pt["lon1"].to_numpy())
        mapped = set(pt.loc[either & ok, "pair_id"])
        strict = set(pt.loc[both & ok, "pair_id"])
        by_peak, strict_by_peak = {}, {}
        for pk in c.peak:
            by_peak[pk] = corridor_hit(cv, mapped, windows[pk])
            strict_by_peak[pk] = corridor_hit(cv, strict, windows[pk])
        best = max((r for r in by_peak.values() if r["best"] is not None), key=lambda r: r["best"], default=None)
        best_name = None
        if best and best["best_pair"] is not None:
            row = pt[pt["pair_id"] == best["best_pair"]].iloc[0]
            best_name = f"{row['from_name']} to {row['to_name']}"
        out.append({"name": c.name, "grade": c.grade, "peak": c.peak, "direction": c.direction,
                    "stop_names": len(names), "stop_names_in_network": len(names & names_in_net),
                    "mapped_stretches": len(mapped), "mapped_stretches_both_ends": len(strict),
                    "hit": any(r["hit"] for r in by_peak.values()),
                    "hit_both_ends_only": any(r["hit"] for r in strict_by_peak.values()),
                    "top_decile_share": _mean([r["top_decile_share"] for r in by_peak.values()]),
                    "chance_hit_probability": _mean([r["chance_hit_probability"] for r in by_peak.values()]),
                    "by_peak": by_peak, "best_stretch": best_name,
                    "best_percentile": best["best_percentile"] if best else None})
    summ = {}
    for g in ("strong", "moderate", "weak"):
        cs = [c for c in out if c["grade"] == g]
        summ[g] = {"hits": sum(c["hit"] for c in cs), "total": len(cs)}
    summ["all"] = {"hits": sum(c["hit"] for c in out), "total": len(out)}
    ch = chance_expected_hits(cv, [(c["mapped_stretches"], c["peak"]) for c in out], windows)
    for c, pr in zip(out, ch["per_corridor"]):
        c["chance_hit_simulated"] = pr
    both_hits = sum(c["hit_both_ends_only"] for c in out)
    return {"corridors": out, "by_grade": summ, "hits_both_ends": both_hits, "chance": ch,
            "top_decile_share": _mean([c["top_decile_share"] for c in out]), "top_decile_chance": 1 - CORRIDOR_TOP_QUANTILE, "top_quantile": CORRIDOR_TOP_QUANTILE,
            "windows": {k: [v[0], v[1]] for k, v in windows.items()},
            "mapping": "A stretch is mapped when either end's stop name is in the corridor's list "
                       "(and, where a direction is stated, it heads that way); both-ends is shown as a stricter reading. "
                       "With this many mapped stretches a hit is likely even by chance, so the share of mapped "
                       "stretches in the top decile (10% would be chance) and the chance of a hit are shown too"}


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(a))


def radial(con) -> dict:
    term = con.execute("""
        SELECT c.route_id, m.opposite_route_id, m.is_ring, arg_min(c.lat, c.seq) AS lat0, arg_min(c.lon, c.seq) AS lon0,
               arg_max(c.lat, c.seq) AS lat1, arg_max(c.lon, c.seq) AS lon1
        FROM canonical_stops c JOIN route_meta m USING (route_id) GROUP BY ALL""").df()

    def dist(lat, lon):
        return np.min([_haversine_km(lat, lon, la, lo) for la, lo in CENTRE_POINTS], axis=0)
    term["d0"] = dist(term["lat0"].to_numpy(), term["lon0"].to_numpy())
    term["d1"] = dist(term["lat1"].to_numpy(), term["lon1"].to_numpy())
    near, far = term[["d0", "d1"]].min(axis=1), term[["d0", "d1"]].max(axis=1)
    term["radial"] = (~term["is_ring"].astype(bool)) & (near <= RADIAL_NEAR_KM) & (far - near >= RADIAL_SPREAD_KM)
    term["inbound"] = term["d1"] < term["d0"]
    load = con.execute(f"""
        SELECT route_id,
               avg(people_mid) FILTER (WHERE window_start_min >= {RADIAL_AM[0]} AND window_start_min < {RADIAL_AM[1]}) AS am,
               avg(people_mid) FILTER (WHERE window_start_min >= {RADIAL_PM[0]} AND window_start_min < {RADIAL_PM[1]}) AS pm,
               sum(app_riders) AS riders
        FROM stretch_crowding WHERE day_type = 'weekday' AND people_mid IS NOT NULL GROUP BY 1""").df()
    t = term.merge(load, on="route_id")
    inb = t[t["radial"] & t["inbound"] & t["opposite_route_id"].notna()]
    opp = t[t["radial"] & ~t["inbound"]].set_index("route_id")
    rows = []
    for r in inb.itertuples():
        oid = int(r.opposite_route_id)
        if oid in opp.index:
            o = opp.loc[oid]
            if not any(pd.isna(x) for x in (r.am, r.pm, o["am"], o["pm"])):
                rows.append({"route_id": int(r.route_id), **radial_hit(r.am, o["am"], r.pm, o["pm"]),
                             "riders": float(r.riders + o["riders"])})
    n = len(rows)
    df = pd.DataFrame(rows)
    if n == 0:
        return {"pairs": 0, "am_share": None, "pm_share": None, "both_share": None, "am_hit": False,
                "pm_hit": False, "hit": False, "radial_directions": int(t["radial"].sum())}
    w = df["riders"].to_numpy()
    am_share, pm_share = float(df["am"].mean()), float(df["pm"].mean())
    return {"pairs": n, "radial_directions": int(term["radial"].sum()),
            "am_share": am_share, "pm_share": pm_share, "both_share": float(df["hit"].mean()),
            "am_share_rider_weighted": float((df["am"] * w).sum() / w.sum()),
            "pm_share_rider_weighted": float((df["pm"] * w).sum() / w.sum()),
            "am_hit": am_share > 0.5, "pm_hit": pm_share > 0.5, "hit": am_share > 0.5 and pm_share > 0.5,
            "definition": (f"radial = not a ring, nearer terminal within {RADIAL_NEAR_KM:g} km of CP/ITO and the "
                           f"farther one at least {RADIAL_SPREAD_KM:g} km farther out; inbound = towards the terminal "
                           f"nearer CP/ITO; the network hits a part when more than half of route pairs do"),
            "windows": {"am": list(RADIAL_AM), "pm": list(RADIAL_PM)}}


def _bus_km_weight_sql() -> str:
    """SQL for a cell's share of a bus-trip: window step / base window (config.WINDOWS), per day type."""
    wd, we = WINDOWS["weekday"], WINDOWS["weekend"]
    return f"CASE WHEN c.day_type = 'weekday' THEN {wd.step_min}.0 / {wd.base_min} ELSE {we.step_min}.0 / {we.base_min} END"


def _scx(con) -> None:
    """_scx: stretch_crowding with bus-km per cell (weighted as in coverage.csv) for the shares below."""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _scx AS
        SELECT c.route_id, c.short_name, c.operator, c.day_type, c.window_start_min, c.level, c.evidence, c.flags,
               c.people_mid, c.seats, c.rated_total, c.buses, c.tickets, c."E_r" AS e_r, c.app_riders,
               c.buses * {_bus_km_weight_sql()}
                 * coalesce(sh.length_m, 0) / 1000.0 AS bus_km,
               sh.length_m IS NULL AS no_shape
        FROM stretch_crowding c LEFT JOIN segment_shapes sh ON sh.route_id = c.route_id AND sh.seq = c.seq + 1""")


def full_allocation_load_factor(con) -> dict:
    """The other end of the bracket: capacity bound off, so the published ridership is placed in full (E = the
    operator scale on every route). `uncapped` lets a bus carry more than crush; `capped_at_crush` shows the same
    cells with people on board capped at crush, as the map shows them."""
    _prepare_cells(con)
    _levels(con, "_lv_full", use_bound=False)
    rows = con.execute(f"""
        WITH v AS (
            SELECT c.operator, c.buses * {WINDOWS["weekday"].step_min}.0 / {WINDOWS["weekday"].base_min} * coalesce(sh.length_m, 0) / 1000.0 AS bus_km, c.seats,
                   c."E_r" * c.app_riders / nullif(c.buses, 0) AS raw, c.people_mid
            FROM _lv_full c LEFT JOIN segment_shapes sh ON sh.route_id = c.route_id AND sh.seq = c.seq + 1
            WHERE c.day_type = 'weekday' AND c.level <> 'no_data' AND c.buses > 0)
        SELECT operator, sum(bus_km * raw) / sum(bus_km * seats), sum(bus_km * people_mid) / sum(bus_km * seats)
        FROM v WHERE bus_km > 0 GROUP BY ROLLUP(operator) ORDER BY operator NULLS LAST""").fetchall()
    out = {(r[0] or "all"): {"uncapped": float(r[1]), "capped_at_crush": float(r[2])} for r in rows}
    allv = out.get("all", {"uncapped": float("nan"), "capped_at_crush": float("nan")})
    return {"all": allv, "by_operator": out}


def published(con, exp) -> dict:
    km = con.execute("""
        SELECT coalesce(sum(sh.length_m) / 1000.0, 0), count(*), count(*) FILTER (WHERE sh.length_m IS NULL)
        FROM passings p JOIN route_meta m USING (route_id)
        LEFT JOIN segment_shapes sh ON sh.route_id = p.route_id AND sh.seq = p.seq + 1
        WHERE m.operator = 'DTC' AND p.seq <= m.n_stops - 1""").fetchone()
    km_reg = con.execute("""
        SELECT coalesce(sum(sh.length_m) / 1000.0, 0)
        FROM passings p JOIN route_meta m USING (route_id) JOIN service_class s USING (route_id)
        LEFT JOIN segment_shapes sh ON sh.route_id = p.route_id AND sh.seq = p.seq + 1
        WHERE m.operator = 'DTC' AND p.seq <= m.n_stops - 1 AND s."class" IN ('regular', 'office_special')""").fetchone()[0]
    has_gps = _gps_table(con)
    if has_gps:
        rho_km, rho_km_reg = con.execute("""
            SELECT coalesce(sum(sh.length_m * least(1.0, coalesce(g.rho_model, 1.0))) / 1000.0, 0),
                   coalesce(sum(sh.length_m * least(1.0, coalesce(g.rho_model, 1.0)))
                            FILTER (WHERE s."class" IN ('regular', 'office_special')) / 1000.0, 0)
            FROM passings p JOIN route_meta m USING (route_id) JOIN service_class s USING (route_id)
            LEFT JOIN segment_shapes sh ON sh.route_id = p.route_id AND sh.seq = p.seq + 1
            LEFT JOIN gps_route_hour g ON g.route_id = p.route_id AND g.hour = (p.minute % 1440) // 60
                                      AND g.day_type = 'weekday'
            WHERE m.operator = 'DTC' AND p.seq <= m.n_stops - 1""").fetchone()
        rho_km, rho_km_reg = float(rho_km), float(rho_km_reg)
        rho_source = ("GPS: share of scheduled trips that ran, per route, hour and weekday, from ten sample days "
                      "(routes without enough ticket-linked vehicles keep rho = 1)")
    else:
        rho_km, rho_km_reg = float(km[0]), float(km_reg)
        rho_source = "none: GPS aggregates not available, so every scheduled trip counts as run"
    rho = rho_km / float(km[0]) if km[0] else 1.0
    bus_km = {"model": rho_km, "scheduled": float(km[0]), "regular_and_office_only": rho_km_reg, "rho": rho,
              "rho_source": rho_source, "gps": has_gps,
              "passings": int(km[1]), "passings_without_shape": int(km[2]),
              "published": exp.dtc_bus_km_published, **published_check(rho_km, exp.dtc_bus_km)}
    bus_km["basis"] = ("each scheduled trip's stretches once (one passing per trip per stop, stretch = stop k to k+1, "
                       "rings capped at n_stops-1), on the feed's single service day (one service_id), the per-day "
                       "basis of the published figure")
    bus_km["implied_rho"] = bus_km["published"] / bus_km["scheduled"] if bus_km["scheduled"] else None
    lf = con.execute("""
        SELECT operator, sum(bus_km * people_mid) / sum(bus_km * seats), sum(bus_km), count(*)
        FROM _scx WHERE day_type = 'weekday' AND people_mid IS NOT NULL AND bus_km > 0 GROUP BY ROLLUP(operator)
        ORDER BY operator NULLS LAST""").fetchall()
    tot_km = con.execute("SELECT sum(bus_km) FROM _scx WHERE day_type = 'weekday' AND bus_km > 0").fetchone()[0]
    by_op = {r[0] or "all": {"load_factor": float(r[1]), "bus_km": float(r[2])} for r in lf}
    allv = by_op.get("all", {"load_factor": float("nan"), "bus_km": 0.0})
    # passenger-km per seat-km scales with 1/rho to first order: restate the figure at the implied rho
    first_order = allv["load_factor"] * bus_km["rho"] / bus_km["implied_rho"] if bus_km["implied_rho"] else None
    load_factor = {"model": allv["load_factor"], "by_operator": by_op,
                   "coverage_bus_km_share": float(allv["bus_km"] / tot_km) if tot_km else None,
                   "at_implied_rho_first_order": first_order,
                   "definition": "weekday passenger-km / seat-km over scheduled service on commuter-facing cells "
                                 "(people on board capped at crush load; seats, not rated totals)",
                   "published_note": "DTC 88-89%, cluster 78% (Economic Survey of Delhi 2025-26, ch. 12); "
                                     "definitions differ, so this is a rough check",
                   **published_check(allv["load_factor"], exp.load_factor_band)}
    load_factor["full_allocation"] = full_allocation_load_factor(con)
    return {"dtc_bus_km": bus_km, "load_factor": load_factor}


# =================================================================== F. diagnostics

def over_capacity(con) -> dict:
    by = con.execute("""
        SELECT operator, window_start_min // 60 AS hour,
               sum(bus_km * (level = 'crowded')::INT) / sum(bus_km) AS share_crowded,
               sum(bus_km * (flags LIKE '%full%')::INT) / sum(bus_km) AS share_over_crush
        FROM _scx WHERE day_type = 'weekday' AND level <> 'no_data' AND bus_km > 0
        GROUP BY 1, 2 ORDER BY 1, 2""").df()
    top = con.execute(f"""
        SELECT route_id, any_value(short_name) AS route, any_value(operator) AS operator, count(*) AS cells,
               sum(bus_km * (flags LIKE '%full%')::INT) / sum(bus_km) AS share_over_crush,
               avg(e_r) AS e_r, avg(buses) AS buses, sum(tickets) AS tickets,
               avg((flags LIKE '%scaled_to_capacity%')::INT) AS capped_share,
               avg((flags LIKE '%alighting_sensitive%')::INT) AS alighting_share,
               avg((flags LIKE '%office_special%')::INT) AS office_share
        FROM _scx WHERE day_type = 'weekday' AND level <> 'no_data' AND bus_km > 0
        GROUP BY route_id HAVING count(*) >= 20 AND sum(bus_km) > 0
        ORDER BY share_over_crush DESC, route_id LIMIT {OVER_CAPACITY_TOP_ROUTES}""").df()

    def cause(r):
        if r.capped_share > 0.5:
            return "capacity bound binds: high app use, so the scale is held at the bus's capacity"
        if r.office_share > 0.5:
            return "office special: weekday-only service built for peak commuters"
        if r.buses < 2.0:
            return "few scheduled buses in the window, so each carries many app riders"
        if r.alighting_share > 0.5:
            return "terminal alighting counts are uncertain on this route"
        return "scale factor is high on a route with many app riders per bus"
    top["suspected_cause"] = [cause(r) for r in top.itertuples()]
    return {"by_operator_hour": by.round(4).to_dict("records"), "top_routes": top.round(3).to_dict("records")}


def level_shares(con) -> dict:
    df = con.execute("""
        SELECT day_type, CASE WHEN h < 5 THEN '00-05' WHEN h < 8 THEN '05-08' WHEN h < 11 THEN '08-11'
                    WHEN h < 17 THEN '11-17' WHEN h < 21 THEN '17-21' ELSE '21-24' END AS band,
               level, evidence, sum(bus_km) AS bus_km
        FROM (SELECT *, window_start_min // 60 AS h FROM _scx) GROUP BY ALL""").df()
    rows = []
    for (dt, band), g in df.groupby(["day_type", "band"]):
        tot = g["bus_km"].sum()
        row = {"day_type": dt, "band": band, "bus_km": float(tot)}
        for lv in LEVELS:
            row[lv] = float(g.loc[g["level"] == lv, "bus_km"].sum() / tot) if tot else None
        for ev in EVIDENCE:
            row[f"evidence_{ev}"] = float(g.loc[g["evidence"] == ev, "bus_km"].sum() / tot) if tot else None
        rows.append(row)
    return {"by_band": rows}


def coverage_summary(con) -> dict:
    def shares(where: str) -> dict:
        df = con.execute(f"SELECT level, evidence, sum(bus_km) AS bus_km FROM _scx WHERE {where} GROUP BY ALL").df()
        tot = df["bus_km"].sum()
        if not tot:
            return {"bus_km": 0.0}
        return {"bus_km": float(tot),
                "level": {lv: float(df.loc[df["level"] == lv, "bus_km"].sum() / tot) for lv in LEVELS},
                "evidence": {ev: float(df.loc[df["evidence"] == ev, "bus_km"].sum() / tot) for ev in EVIDENCE},
                "commuter_facing": float(df.loc[df["level"] != "no_data", "bus_km"].sum() / tot),
                "many_tickets": float(df.loc[df["evidence"] == "many_tickets", "bus_km"].sum() / tot)}
    out = {"all": shares("true")}
    for dt in ("weekday", "weekend"):
        out[dt] = shares(f"day_type = '{dt}'")
        for op in ("DTC", "DIMTS"):
            out[f"{dt}_{op}"] = shares(f"day_type = '{dt}' AND operator = '{op}'")
    out["note"] = "share of scheduled bus-km (as in coverage.csv, which has the hourly detail)"
    return out


def resolution(con) -> dict:
    df = con.execute(f"""
        WITH c AS (SELECT route_raw, count(*) AS n FROM tickets_clean GROUP BY 1),
        r AS (SELECT route_raw, count(*) AS n FROM tickets_rejected GROUP BY 1)
        SELECT c.route_raw AS route, c.n AS tickets, coalesce(r.n, 0) AS rejected,
               1 - coalesce(r.n, 0)::DOUBLE / c.n AS resolved_share
        FROM c LEFT JOIN r USING (route_raw)
        WHERE c.n >= {RESOLUTION_MIN_TICKETS} AND 1 - coalesce(r.n, 0)::DOUBLE / c.n < {RESOLUTION_MIN_SHARE}
        ORDER BY rejected DESC, route""").df()
    n_strings = con.execute(f"SELECT count(*) FROM (SELECT route_raw FROM tickets_clean GROUP BY 1 "
                            f"HAVING count(*) >= {RESOLUTION_MIN_TICKETS})").fetchone()[0]
    total = con.execute("SELECT count(*) FROM tickets_clean").fetchone()[0]
    return {"min_tickets": RESOLUTION_MIN_TICKETS, "threshold": RESOLUTION_MIN_SHARE, "route_strings": int(n_strings),
            "below_threshold": int(len(df)), "tickets_in_those": int(df["tickets"].sum()),
            "share_of_tickets": float(df["tickets"].sum() / total) if total else None,
            "worst": df.head(25).round(4).to_dict("records")}


def terminal_asymmetry_summary(con) -> dict:
    r = con.execute("""
        SELECT count(*), count(*) FILTER (WHERE ratio IS NOT NULL), count(*) FILTER (WHERE moved_pax > 0),
               coalesce(sum(moved_pax), 0), count(*) FILTER (WHERE alighting_sensitive), median(ratio),
               quantile_cont(ratio, 0.9), sum(terminal_alight) FROM terminal_asymmetry""").fetchone()
    return {"routes": int(r[0]), "routes_with_known_ratio": int(r[1]), "routes_corrected": int(r[2]),
            "moved_passengers": float(r[3]), "alighting_sensitive_routes": int(r[4]),
            "median_ratio": None if r[5] is None else float(r[5]), "p90_ratio": None if r[6] is None else float(r[6]),
            "terminal_alightings": float(r[7] or 0),
            "note": "ratio = terminal alightings / reverse terminal boardings, per route (R11/R19)"}


def split_half(con) -> dict:
    """Vehicle-linked vs vehicle-NULL tickets: do the two halves agree on where and when people ride?"""
    df = con.execute("""
        SELECT route_id, hour(timezone('Asia/Kolkata', ts)) AS h,
               sum(pax) FILTER (WHERE channel = 'linked') AS linked, sum(pax) FILTER (WHERE channel = 'null') AS nul,
               count(*) FILTER (WHERE channel = 'linked') AS nl, count(*) FILTER (WHERE channel = 'null') AS nn
        FROM tickets_resolved WHERE day_type = 'weekday' GROUP BY 1, 2""").df().fillna(0)
    d = df[(df["nl"] >= 5) & (df["nn"] >= 5)]
    prof = df.groupby("h")[["linked", "nul"]].sum()
    if len(d) < 3:
        return {"route_hours": int(len(d)), "pearson": None, "spearman": None, "hourly_profile_correlation": None}
    return {"route_hours": int(len(d)), "min_tickets_each_half": 5,
            "pearson": float(d["linked"].corr(d["nul"])),
            "spearman": float(d["linked"].rank().corr(d["nul"].rank())),
            "hourly_profile_correlation": float(prof["linked"].corr(prof["nul"])) if len(prof) > 2 else None,
            "linked_ticket_share": float(df["nl"].sum() / (df["nl"].sum() + df["nn"].sum()))}


def pair_window(con) -> dict:
    """R17: the ticket-pair ratio window is 0.4-2.5; the wider 0.25-4 window gives these factors instead."""
    network._exclusions(con)
    res = {}
    old = network.PAIR_RATIO_BOUNDS
    try:
        for name, b in (("default", old), ("wide", PAIR_WINDOW_ALTERNATIVE)):
            network.PAIR_RATIO_BOUNDS = b
            pairs = network._build_pairs(con)
            f = network._factor_rows(pairs)
            f = f[f["scope"] == "operator"]
            res[name] = {"window": [float(b[0]), float(b[1])], "pairs": int(len(pairs)),
                         "factors": {f"{op}_{h}": float(v) for op, h, v in
                                     f[f["hour"].isin([8, 18])][["key", "hour", "factor"]].itertuples(index=False)},
                         "table": f.set_index(["key", "hour"])["factor"]}
    finally:
        network.PAIR_RATIO_BOUNDS = old
    a, b = res["default"].pop("table"), res["wide"].pop("table")
    j = pd.concat([a, b], axis=1, keys=["d", "w"]).dropna()
    res["max_relative_difference"] = float((j["w"] / j["d"] - 1).abs().max()) if len(j) else None
    res["note"] = ("ticket pairs with observed/template run time outside the window are another trip or a batch "
                   "print; the window is symmetric in log")
    con.execute("DROP TABLE IF EXISTS _clean_tix")
    con.execute("DROP TABLE IF EXISTS _excl")
    return res


def _gps_table(con) -> bool:
    """True when the model ran with GPS aggregates (gps_route_hour with rho_model)."""
    try:
        cols = {r[0] for r in con.execute("DESCRIBE gps_route_hour").fetchall()}
    except Exception:
        return False
    return "rho_model" in cols


def gps_diagnostics(con) -> dict:
    """rho distribution (route level, pooled over hours) and run-time cross-check against the ticket clock."""
    if not _gps_table(con):
        return {"status": "not available", "note": "no GPS aggregates; rho = 1"}
    out = {"status": "available"}
    for dt in ("weekday", "weekend"):
        r = con.execute("""
            SELECT route_id, any_value(coverage) AS cov, sum(observed_trips) AS obs, sum(scheduled_trips) AS sch,
                   sum(observed_trips * (source = 'gps')::INT) AS obs_gps
            FROM gps_route_hour WHERE day_type = ? GROUP BY 1""", [dt]).df()
        ok = r[(r["cov"] >= 0.8) & (r["sch"] > 0)]
        rho = ok["obs"] / (ok["sch"] * ok["cov"])
        q = rho.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).tolist() if len(rho) else [None] * 5
        g = con.execute("""
            SELECT sum(rho_first * scheduled_trips) / sum(scheduled_trips), sum(rho_mid * scheduled_trips) / sum(scheduled_trips),
                   sum(rho_last * scheduled_trips) / sum(scheduled_trips),
                   sum(rho * scheduled_trips) / sum(scheduled_trips), count(*)
            FROM gps_route_hour WHERE day_type = ? AND rho IS NOT NULL""", [dt]).fetchall()[0]
        out[dt] = {"routes": int(len(r)), "routes_with_coverage_80": int((r["cov"] >= 0.8).sum()),
                   "routes_without_linked_vehicles": int(r["cov"].isna().sum()),
                   "share_coverage_80": float((r["cov"] >= 0.8).mean()) if len(r) else None,
                   "route_rho_quantiles": dict(zip(("p10", "p25", "p50", "p75", "p90"), q)),
                   "scheduled_weighted_rho": float(g[3]) if g[3] is not None else None,
                   "first_third": g[0], "middle_third": g[1], "last_third": g[2], "cells": int(g[4]),
                   "network_trips_per_scheduled": float(r["obs"].sum() / r["sch"].sum()) if r["sch"].sum() else None}
    rt = con.execute("""
        SELECT hour, sum(runtime_ratio * scheduled_trips) / sum(scheduled_trips) AS ratio, count(*) AS cells
        FROM gps_route_hour WHERE day_type = 'weekday' AND runtime_ratio IS NOT NULL AND scheduled_trips > 0
        GROUP BY 1 ORDER BY 1""").fetchall()
    out["runtime_ratio_by_hour"] = {int(h): {"ratio": float(r_), "cells": int(c)} for h, r_, c in rt}
    return out


def diagnostics(con) -> dict:
    t0 = time.perf_counter()
    _scx(con)
    d = {"over_capacity": over_capacity(con), "level_shares": level_shares(con),
         "resolution_below_80": resolution(con), "terminal_asymmetry": terminal_asymmetry_summary(con),
         "null_vs_linked_split_half": split_half(con), "pair_ratio_window": pair_window(con),
         "gps_rho": gps_diagnostics(con),
         "choice_stability": {"status": "not available", "note": "needs the planner (alternatives per "
                              "origin, destination and hour)"}}
    d["seconds"] = round(time.perf_counter() - t0, 1)
    return d


# =================================================================== headline and rendering

def _dq(con, table: str) -> dict:
    return {r[0]: r[1] for r in con.execute(f"SELECT name, value FROM {table}").fetchall()}


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (date, Path)):
        return str(o)
    return o


def _has_table(con, name: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                            [name]).fetchone()[0])


def doc_numbers(con, diag, cov, h) -> dict:
    """Numbers the README, technical note and proposal quote, each computed here from the pipeline's own tables
    (design 5.14). Anything a table lacks (a toy run) is left out, and a template that asks for it fails loudly."""
    out: dict = {}
    c = con.execute("""SELECT sum(pax), count(DISTINCT route_raw),
                       avg(CASE WHEN vehicle IS NULL OR vehicle = 'NULL' THEN 1.0 ELSE 0.0 END)
                       FROM tickets_clean""").fetchone()
    out["passengers_clean"] = int(c[0]) if c[0] is not None else None
    out["route_strings"] = int(c[1])
    out["vehicle_missing_share"] = float(c[2]) if c[2] is not None else None
    out["days_in_file"] = int(con.execute("SELECT count(*) FROM clean_days").fetchone()[0])
    if _has_table(con, "route_meta"):
        out["gtfs_routes"] = int(con.execute("SELECT count(*) FROM route_meta").fetchone()[0])
    if _has_table(con, "dq_resolve"):
        for reason, n in con.execute("SELECT reason, tickets FROM dq_resolve").fetchall():
            out[f"rejected_{reason}"] = int(n)
    # app riders as a share of published riders
    try:
        pub = [float(h[f"published_ridership_{op}"]) for op in ("dtc", "dimts")]
        e = [float(h[f"e_{op}"]) for op in ("dtc", "dimts")]
        share = sum(p / x for p, x in zip(pub, e)) / sum(pub)
        lo, hi = HACKATHON_APP_TICKET_SHARE
        free = PUBLISHED_WOMEN_FREE_JOURNEYS.value / WOMEN_FREE_PERIOD_DAYS
        out.update({
            "app_share_of_riders": share, "app_riders_one_in": round(1 / share),
            "hackathon_share_low": lo, "hackathon_share_high": hi,
            "outside_ticket_base_needed_low": 1 - share / lo, "outside_ticket_base_needed_high": 1 - share / hi,
            "women_free_journeys": PUBLISHED_WOMEN_FREE_JOURNEYS.value,
            "women_free_per_day_rough": free, "women_free_share_rough": free / sum(pub),
            "published_ridership_total": sum(pub)})
    except (KeyError, TypeError, ZeroDivisionError):
        pass
    # how crowded, by day type and hour band (share of scheduled bus-km)
    for day in ("weekday", "weekend"):
        lv = (cov.get(day) or {}).get("level") or {}
        for k, v in lv.items():
            out[f"{day}_{k}_share"] = v
    ev = (cov.get("all") or {}).get("evidence") or {}
    for k, v in ev.items():
        out[f"evidence_{k}_share"] = v
    for b in (diag.get("level_shares") or {}).get("by_band", []):
        if b["day_type"] == "weekday" and b["band"] in ("08-11", "11-17", "17-21"):
            tag = b["band"].replace("-", "")
            for k in ("seats", "standing", "crowded", "no_data"):
                out[f"weekday_{tag}_{k}_share"] = b[k]
    # the ticket-pair clock by hour of day
    if _has_table(con, "runtime_factors"):
        for op in ("DTC", "DIMTS"):
            for hr in (6, 8, 12, 18, 22):
                v = con.execute("SELECT factor FROM runtime_factors WHERE scope = 'operator' AND key = ? AND hour = ?",
                                [op, hr]).fetchone()
                if v:
                    out[f"{op.lower()}_clock_factor_{hr}h"] = float(v[0])
    pw = diag.get("pair_ratio_window") or {}
    out["ticket_pairs"] = (pw.get("default") or {}).get("pairs")
    out["ticket_pairs_alternative_window"] = (pw.get("wide") or {}).get("pairs")
    # GPS
    g = diag.get("gps_rho") or {}
    if g.get("status") == "available":
        wd = g["weekday"]
        out.update({"gps_trips_ran_share_weekday": wd["scheduled_weighted_rho"],
                    "gps_routes_covered": wd["routes_with_coverage_80"], "gps_routes_total": wd["routes"],
                    "gps_trips_ran_first_third": wd["first_third"], "gps_trips_ran_last_third": wd["last_third"]})
        r = [v["ratio"] for k, v in g["runtime_ratio_by_hour"].items()
             if 5 <= int(k) <= 21 and v["cells"] >= 100 and v["ratio"] is not None]
        if r:
            out.update({"gps_runtime_ratio_min": min(r), "gps_runtime_ratio_max": max(r),
                        "gps_runtime_ratio_median": float(np.median(r))})
    # terminal alighting correction, split-half agreement, tickets that did not resolve
    t, sh, rb = diag.get("terminal_asymmetry") or {}, diag.get("null_vs_linked_split_half") or {}, \
        diag.get("resolution_below_80") or {}
    out.update({"terminal_routes": t.get("routes"), "terminal_routes_known": t.get("routes_with_known_ratio"),
                "terminal_routes_corrected": t.get("routes_corrected"),
                "terminal_moved_passengers": t.get("moved_passengers"),
                "terminal_ratio_median": t.get("median_ratio"), "terminal_ratio_p90": t.get("p90_ratio"),
                "split_half_pearson": sh.get("pearson"), "split_half_route_hours": sh.get("route_hours"),
                "linked_ticket_share": sh.get("linked_ticket_share"),
                "low_resolution_route_strings": rb.get("below_threshold"),
                "low_resolution_ticket_share": rb.get("share_of_tickets")})
    # operator view: the best single extra trip per operator, weekday
    if _has_table(con, "operator_trips"):
        for op in ("DTC", "DIMTS"):
            r = con.execute("""SELECT short_name, depart_min, crowded_rider_min_removed, riders_moved_down
                               FROM operator_trips WHERE day_type = 'weekday' AND operator = ?
                               ORDER BY crowded_rider_min_removed DESC, short_name LIMIT 1""", [op]).fetchone()
            if r:
                out.update({f"operator_top_{op.lower()}_route": r[0],
                            f"operator_top_{op.lower()}_departs": f"{int(r[1]) // 60:02d}:{int(r[1]) % 60:02d}",
                            f"operator_top_{op.lower()}_crowded_minutes": float(r[2]),
                            f"operator_top_{op.lower()}_riders_moved": float(r[3])})
    return {k: v for k, v in out.items() if v is not None}


def headline(con, gates, exp_res, rep, pub, sens, diag, repro) -> dict:
    dql, dqn = _dq(con, "dq_levels"), _dq(con, "dq_network")
    c = gates["ticket_conservation"]
    pax_res = con.execute("SELECT sum(pax) FROM tickets_resolved").fetchone()[0]
    pax_all = con.execute("SELECT sum(pax) FROM tickets_clean").fetchone()[0]
    cov = coverage_summary(con)
    h = {
        "tickets_clean": c["clean"], "tickets_resolved": c["resolved"], "tickets_rejected": c["rejected"],
        "match_rate": c["resolved"] / c["clean"] if c["clean"] else None,
        "match_rate_passengers": float(pax_res / pax_all) if pax_all else None,
        "clean_days": int(con.execute("SELECT count(*) FROM clean_days WHERE NOT is_excluded_date").fetchone()[0]),
        "e_dtc": dql.get("DTC_e_op"), "e_dimts": dql.get("DIMTS_e_op"),
        "e_star_dtc": dql.get("DTC_e_star"), "e_star_dimts": dql.get("DIMTS_e_star"),
        "e_scale_ceiling_multiplier": E_SCALE_CEILING_MULT,
        "capped_routes": int(dql.get("capped_routes", 0)),
        "capped_routes_dtc": int(dql.get("DTC_capped_routes", 0)),
        "capped_routes_dimts": int(dql.get("DIMTS_capped_routes", 0)),
        "unallocated_share_dtc": dql.get("DTC_unallocated_share"),
        "unallocated_share_dimts": dql.get("DIMTS_unallocated_share"),
        "ceiling_bound_dtc": bool(dql.get("DTC_ceiling_bound", 0)),
        "ceiling_bound_dimts": bool(dql.get("DIMTS_ceiling_bound", 0)),
        "published_ridership_dtc": PUBLISHED_RIDERSHIP["DTC"].value,
        "published_ridership_dimts": PUBLISHED_RIDERSHIP["DIMTS"].value,
        "rider_minutes_gate_deviation": gates["rider_minutes"]["deviation"],
        "run_time_gate_max_deviation": gates["run_times"]["max_deviation"],
        "rider_volume_no_bus_share": gates["supply"]["share"],
        "rider_volume_widened_share": gates["supply"]["widened_share"],
        "no_data_routes": int(dql.get("no_data_routes", 0)),
        "alighting_sensitive_routes": diag["terminal_asymmetry"]["alighting_sensitive_routes"],
        "service_class_regular": int(dqn.get("service_class_regular", 0)),
        "service_class_office_special": int(dqn.get("service_class_office_special", 0)),
        "service_class_school": int(dqn.get("service_class_school", 0)),
        "service_class_daf": int(dqn.get("service_class_daf", 0)),
        "stretch_crowding_rows": int(dql.get("rows", 0)),
        "base_case_reproduced": repro["exact"],
        "pair_ratio_window": f"{diag['pair_ratio_window']['default']['window'][0]:g}-"
                             f"{diag['pair_ratio_window']['default']['window'][1]:g}",
        "pair_ratio_window_alternative": f"{PAIR_WINDOW_ALTERNATIVE[0]:g}-{PAIR_WINDOW_ALTERNATIVE[1]:g}",
        "dtc_factor_18h": diag["pair_ratio_window"]["default"]["factors"].get("DTC_18"),
        "dtc_factor_18h_alternative_window": diag["pair_ratio_window"]["wide"]["factors"].get("DTC_18"),
        "dtc_factor_8h": diag["pair_ratio_window"]["default"]["factors"].get("DTC_8"),
        "dtc_factor_8h_alternative_window": diag["pair_ratio_window"]["wide"]["factors"].get("DTC_8"),
        "unchanged_level_share": rep["summary"]["unchanged_level_share"],
        "unchanged_level_share_cells": rep["summary"]["unchanged_level_share_cells"],
        "unchanged_level_share_leave_one_out": rep["summary"]["unchanged_level_share_leave_one_out"],
        "load_correlation_week_pairs": rep["summary"]["load_correlation"],
        "load_correlation_leave_one_out": rep["summary"]["load_correlation_leave_one_out"],
        "range_coverage_heldout": rep["summary"]["range_coverage"],
        "corridor_hits_strong": exp_res["corridors"]["by_grade"]["strong"]["hits"],
        "corridors_strong": exp_res["corridors"]["by_grade"]["strong"]["total"],
        "corridor_hits_moderate": exp_res["corridors"]["by_grade"]["moderate"]["hits"],
        "corridors_moderate": exp_res["corridors"]["by_grade"]["moderate"]["total"],
        "corridor_hits_weak": exp_res["corridors"]["by_grade"]["weak"]["hits"],
        "corridors_weak": exp_res["corridors"]["by_grade"]["weak"]["total"],
        "corridor_hits_total": exp_res["corridors"]["by_grade"]["all"]["hits"],
        "corridor_hits_both_ends": exp_res["corridors"]["hits_both_ends"],
        "corridor_hits_chance_expected": exp_res["corridors"]["chance"]["expected_hits"],
        "corridor_hits_chance_method": exp_res["corridors"]["chance"]["method"],
        "corridor_top_decile_share": exp_res["corridors"]["top_decile_share"],
        "corridor_top_decile_chance": exp_res["corridors"]["top_decile_chance"],
        "corridor_top_decile_share_mean": _mean([c["top_decile_share"] for c in exp_res["corridors"]["corridors"]]),
        "corridor_chance_hit_mean": _mean([c["chance_hit_probability"] for c in exp_res["corridors"]["corridors"]]),
        "corridors_total": exp_res["corridors"]["by_grade"]["all"]["total"],
        "peaks_hit": exp_res["peaks"]["hit"], "am_peak_hour": exp_res["peaks"]["am_peak_hour"],
        "pm_peak_hour": exp_res["peaks"]["pm_peak_hour"],
        "weekend_hit": exp_res["weekend"]["hit"], "weekend_lower": exp_res["weekend"]["lower"],
        "weekend_flatter": exp_res["weekend"]["flatter"], "weekend_later_peak": exp_res["weekend"]["later_peak"],
        "radial_hit": exp_res["radial"]["hit"], "radial_pairs": exp_res["radial"]["pairs"],
        "radial_am_share": exp_res["radial"]["am_share"], "radial_pm_share": exp_res["radial"]["pm_share"],
        "dtc_bus_km_model": pub["dtc_bus_km"]["model"], "dtc_bus_km_scheduled": pub["dtc_bus_km"]["scheduled"],
        "dtc_rho_effective": pub["dtc_bus_km"]["rho"], "dtc_bus_km_published": pub["dtc_bus_km"]["published"],
        "dtc_bus_km_hit": pub["dtc_bus_km"]["hit"], "dtc_implied_rho": pub["dtc_bus_km"]["implied_rho"],
        "dtc_bus_km_band_low": pub["dtc_bus_km"]["band"][0], "dtc_bus_km_band_high": pub["dtc_bus_km"]["band"][1],
        "load_factor_band_low": pub["load_factor"]["band"][0],
        "load_factor_band_high": pub["load_factor"]["band"][1],
        "load_factor_model": pub["load_factor"]["model"], "load_factor_hit": pub["load_factor"]["hit"],
        "load_factor_dtc": pub["load_factor"]["by_operator"].get("DTC", {}).get("load_factor"),
        "load_factor_dimts": pub["load_factor"]["by_operator"].get("DIMTS", {}).get("load_factor"),
        "bus_km_share_commuter_facing": cov["all"].get("commuter_facing"),
        "bus_km_share_many_tickets": cov["all"].get("many_tickets"),
        "gps_available": pub["dtc_bus_km"]["gps"],
        "load_factor_full_allocation": pub["load_factor"]["full_allocation"]["all"]["uncapped"],
        "load_factor_full_allocation_capped_at_crush": pub["load_factor"]["full_allocation"]["all"]["capped_at_crush"],
        "load_factor_full_allocation_dtc":
            pub["load_factor"]["full_allocation"]["by_operator"].get("DTC", {}).get("uncapped"),
        "load_factor_full_allocation_dimts":
            pub["load_factor"]["full_allocation"]["by_operator"].get("DIMTS", {}).get("uncapped"),
        "rho_dtc_bus_km_weighted": pub["dtc_bus_km"]["rho"],
        "rho_routes_covered_share": diag["gps_rho"].get("weekday", {}).get("share_coverage_80"),
        "rho_fallback_bus_km_share": con.execute("""
            SELECT coalesce(sum(bus_km) FILTER (WHERE flags LIKE '%rho_fallback%') / nullif(sum(bus_km), 0), 0)
            FROM _scx WHERE day_type = 'weekday' AND bus_km > 0""").fetchall()[0][0],
    }
    for k, v in sens.items():
        h[f"sensitivity_{k}"] = v["share_changed"]
    h.update(doc_numbers(con, diag, cov, h))
    return h


def _pct(x, d=1):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def _num(x, d=2):
    return "n/a" if x is None else f"{x:,.{d}f}"


def _tbl(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _band(lo, hi) -> str:
    return f"{lo:g}-{hi:g}"


def _yn(b) -> str:
    return "hit" if b else "miss"


def render_md(rep: dict) -> str:
    h, g, e, ind = rep["headline_numbers"], rep["gates"], rep["expectations"], rep["independent"]
    rp, sn, dg = rep["repeatability"], rep["sensitivity"], rep["diagnostics"]
    L = []
    a = L.append
    a("# Validation report\n")
    a("This is a check of the model against things we can compare it with. No field count was possible, so none of it "
      "measures how close a level is to the truth on a given bus. Every figure below is computed by "
      "`src/pipeline/validate.py` from the same tables the app reads; misses are reported as misses.\n")
    a("## Headline\n")
    a(f"- Tickets: {h['tickets_clean']:,} clean, {_pct(h['match_rate'])} resolved to a route and stops "
      f"({_pct(h['match_rate_passengers'])} of passengers).")
    a(f"- Scale from app passengers to people: E = {_num(h['e_dtc'])} for DTC and {_num(h['e_dimts'])} for the "
      f"cluster operator (published ridership / resolved app passengers per clean day).")
    a(f"- Route capacity bound: {h['capped_routes']} routes are scaled to bus capacity "
      f"({h['capped_routes_dtc']} DTC, {h['capped_routes_dimts']} cluster).")
    a(f"- Scale ceiling: the operator scale may not exceed {h['e_scale_ceiling_multiplier']:g} times E. "
      f"For DTC the ceiling {'binds' if h['ceiling_bound_dtc'] else 'does not bind'}; the unallocated share of "
      f"published DTC ridership is {_pct(h['unallocated_share_dtc'])}. For the cluster operator the ceiling "
      f"{'binds' if h['ceiling_bound_dimts'] else 'does not bind'} and "
      f"{_pct(h['unallocated_share_dimts'])} of its published ridership is unallocated: the model places only the "
      f"rest on routes, so cluster loads are, if anything, understated.")
    a(f"- Ticket-pair run-time window: observed / template ratios from {h['pair_ratio_window']} are used. With the "
      f"wider {h['pair_ratio_window_alternative']} window the DTC 18:00 factor is "
      f"{_num(h['dtc_factor_18h_alternative_window'], 3)} instead of {_num(h['dtc_factor_18h'], 3)} "
      f"(08:00: {_num(h['dtc_factor_8h_alternative_window'], 3)} instead of {_num(h['dtc_factor_8h'], 3)}).")
    a(f"- Week to week: {_pct(h['unchanged_level_share'])} of commuter-facing cells (rider-weighted) keep their level "
      f"between two different weeks of the month; load correlation {_num(h['load_correlation_week_pairs'], 3)}. "
      f"A week held out lands inside the sampling range in {_pct(h['range_coverage_heldout'])} of cells. "
      f"Secondary, not independent (the runs share three weeks): dropping one week from the full month leaves "
      f"{_pct(h['unchanged_level_share_leave_one_out'])} unchanged.")
    a(f"- Pre-registered corridors: {h['corridor_hits_strong']} of {h['corridors_strong']} strong, "
      f"{h['corridor_hits_moderate']} of {h['corridors_moderate']} moderate, {h['corridor_hits_weak']} of "
      f"{h['corridors_weak']} weak; {h['corridor_hits_total']} of {h['corridors_total']} in all. That primary rule "
      f"turned out to be weak: "
      f"{_num(h['corridor_hits_chance_expected'], 1)} of {h['corridors_total']} hits would be expected if the same "
      f"number of stretches per corridor were drawn at random ({h['corridor_hits_chance_method']}). The informative "
      f"readings are the enrichment (on average {_pct(h['corridor_top_decile_share'])} of mapped stretches are in the "
      f"top decile, against {_pct(h['corridor_top_decile_chance'], 0)} at random) and the stricter both-ends mapping "
      f"({h['corridor_hits_both_ends']} of {h['corridors_total']}).")
    a(f"- Published figures: modelled DTC bus-km {_num(h['dtc_bus_km_model'], 0)} per day against "
      f"{_num(h['dtc_bus_km_published'], 0)} ({_yn(h['dtc_bus_km_hit'])}); modelled load factor "
      f"{_num(h['load_factor_model'], 3)} against the {_band(h['load_factor_band_low'], h['load_factor_band_high'])} "
      f"band ({_yn(h['load_factor_hit'])}).")
    a(f"- Scheduled DTC bus-km is {_num(h['dtc_bus_km_scheduled'] / h['dtc_bus_km_published'], 2)} times the published "
      f"figure (implied share of trips run about {_num(h['dtc_implied_rho'], 2)} if the published figure is right). "
      + (f"The model applies the share of trips that ran, measured from GPS, which is "
         f"{_num(h['dtc_rho_effective'], 2)} bus-km weighted for DTC. " if h["gps_available"] else
         "The GPS layer is not in, so the model counts every scheduled trip as run and loads may be understated. ")
      + "The model figure counts each scheduled trip's segments once, on the feed's single service day, the same "
        "per-day basis as the published figure.")
    a(f"- Routes whose last stretches depend on the alighting correction: {h['alighting_sensitive_routes']}.")
    a(f"- Coverage: {_pct(h['bus_km_share_commuter_facing'])} of scheduled bus-km has a commuter-facing level, "
      f"{_pct(h['bus_km_share_many_tickets'])} rests on many tickets.")
    a("- GPS layer: " + ("in: bus supply is scheduled buses times the share that ran (GPS, ten sample days); the "
                        "stop-time corroboration is not built and is not counted as a miss."
                        if h["gps_available"] else
                        "not available, so bus supply uses the schedule (rho = 1) and the GPS checks are marked not "
                        "available; they are not counted as misses."))
    a(f"- Run time of the validation stage: {_num(rep['diagnostics']['runtime_seconds'], 0)} s.\n")

    a("## A. Gates (a failure stops the run)\n")
    rows = []
    for k, v in g.items():
        detail = v.get("rule") or ""
        val = v.get("deviation", v.get("share", v.get("max_deviation")))
        rows.append((k, "pass" if v["passed"] else "FAIL", "" if val is None else f"{val:.4%}", detail))
    a(_tbl(["Gate", "Result", "Value", "Rule"], rows))
    a(f"\nThe rebuilt base case equals the stored output: {rep['reproduction']['rows_matched']:,} of "
      f"{rep['reproduction']['rows_stored']:,} rows, levels and evidence identical "
      f"({'yes' if rep['reproduction']['exact'] else 'NO'}).\n")

    a("## B. Expectations written down before the first full run\n")
    p, w, r = e["peaks"], e["weekend"], e["radial"]
    a(_tbl(["Expectation", "Result", "Detail"], [
        ("AM peak in 08-10", _yn(p["am_hit"]), f"busiest morning hour {p['am_peak_hour']:02d}:00"),
        ("PM peak in 17-20", _yn(p["pm_hit"]), f"busiest evening hour {p['pm_peak_hour']:02d}:00"),
        ("Weekend lower", _yn(w["lower"]), f"{_num(w['weekend_total'], 0)} vs {_num(w['weekday_total'], 0)} "
                                          "crowded rider-minutes per day"),
        ("Weekend flatter", _yn(w["flatter"]), f"peak-to-mean {_num(w['weekend_peak_to_mean'], 2)} vs "
                                              f"{_num(w['weekday_peak_to_mean'], 2)}"),
        ("Weekend peak later", _yn(w["later_peak"]), f"weekend {w['weekend_peak_hour']:02d}:00, weekday "
                                                     f"{w['weekday_peak_hour']:02d}:00"),
        ("Radial: inbound busier in the AM", _yn(r["am_hit"]), f"{_pct(r['am_share'])} of {r['pairs']} route pairs"),
        ("Radial: outbound busier in the PM", _yn(r["pm_hit"]), f"{_pct(r['pm_share'])} of {r['pairs']} route pairs"),
        ("GPS stop-time activity", "not available", "the stop-time corroboration is not built; not counted as a miss"),
    ]))
    a("\n### The ten researched corridors\n")
    a(f"A corridor is a hit when one of its mapped stretches is in the top decile of weekday crowded "
      f"rider-minutes per km in its stated peak window. {e['corridors']['mapping']}.\n")
    bg_all = e["corridors"]["by_grade"]["all"]
    a(f"The primary rule turned out to be weak: {_num(e['corridors']['chance']['expected_hits'], 1)} of "
      f"{bg_all['total']} hits are expected at random ({e['corridors']['chance']['method']}). The informative "
      f"readings are the enrichment ({_pct(e['corridors']['top_decile_share'])} of mapped stretches in the top decile "
      f"vs 10% at random) and the both-ends mapping ({e['corridors']['hits_both_ends']} of {bg_all['total']}).\n")
    rows = []
    for c in e["corridors"]["corridors"]:
        pk = "/".join(c["peak"])
        rows.append((c["grade"], c["name"][:70], pk, c["mapped_stretches"], _yn(c["hit"]),
                     _yn(c["hit_both_ends_only"]), _pct(c["top_decile_share"]), _pct(c["chance_hit_probability"]),
                     c["best_stretch"] or "-", _pct(c["best_percentile"])))
    a(_tbl(["Grade", "Corridor", "Peak", "Mapped stretches", "Result", "Both ends only", "Mapped stretches in top decile",
            "Chance of a hit at random", "Strongest mapped stretch", "Its percentile"], rows))
    bg = e["corridors"]["by_grade"]
    a(f"\nHits by grade: strong {bg['strong']['hits']}/{bg['strong']['total']}, moderate "
      f"{bg['moderate']['hits']}/{bg['moderate']['total']}, weak {bg['weak']['hits']}/{bg['weak']['total']}.\n")

    a("## C. Week-to-week repeatability\n")
    a(rp["method"] + "\n")
    s = rp["summary"]
    a(_tbl(["Comparison", "Cells unchanged (rider-weighted)", "Cells unchanged (plain)", "Load correlation"], [
        ("Two weeks, each alone (mean of week pairs)", _pct(s["unchanged_level_share"]),
         _pct(s["unchanged_level_share_cells"]), _num(s["load_correlation"], 3)),
        ("One week left out vs the full month (mean)", _pct(s["unchanged_level_share_leave_one_out"]),
         _pct(s["unchanged_level_share_leave_one_out_cells"]), _num(s["load_correlation_leave_one_out"], 3)),
        ("Two leave-one-out runs against each other (mean)", _pct(s["unchanged_level_share_leave_one_out_pairs"]),
         "", ""),
    ]))
    a("\nBy week pair (each week alone):\n")
    a(_tbl(["Pair", "Cells", "Unchanged (rider-weighted)", "Load correlation"],
           [(x["pair"], f"{x['cells']:,}", _pct(x["unchanged_share_rider_weighted"]),
             _num(x["load"]["correlation"], 3)) for x in rp["week_pairs"]]))
    a("\nBy ticket band (cell tickets over the full month, mean of week pairs):\n")
    a(_tbl(["Tickets in cell", "Cells", "Unchanged (rider-weighted)"],
           [(b, f"{v['cells']:,}", _pct(v["unchanged_level_share"])) for b, v in s["by_ticket_band"].items()]))
    a(f"\nCoverage of the sampling ranges: a week held out lands inside the range estimated from the other weeks in "
      f"{_pct(s['range_coverage'])} of cells (rider-weighted). The range is not a confidence interval; the figure is "
      f"reported as is.\n")

    a("## D. Independent checks\n")
    a("No field count was possible. The checks are published totals, the researched corridors above and, once the "
      "GPS layer is in, GPS stop-time activity.\n")
    bk, lf = ind["dtc_bus_km"], ind["load_factor"]
    a(_tbl(["Check", "Model", "Published", "Band", "Result"], [
        ("DTC bus-km per day (scheduled x rho)", _num(bk["model"], 0), _num(bk["published"], 0),
         f"{bk['band'][0]:,.0f}-{bk['band'][1]:,.0f}", _yn(bk["hit"])),
        ("Fleet load factor (weekday passenger-km / seat-km)", _num(lf["model"], 3), "DTC 0.88-0.89, cluster 0.78",
         f"{lf['band'][0]:g}-{lf['band'][1]:g}", _yn(lf["hit"])),
    ]))
    a(f"\nBoth are rough: definitions differ from ours. The schedule offers {_num(bk['scheduled'] / bk['published'], 2)} "
      f"times the published DTC bus-km, so only about {_pct(bk['implied_rho'], 0)} of scheduled DTC service would "
      f"have run (an implied rho of {_num(bk['implied_rho'], 2)}). With rho = 1 every scheduled bus counts as "
      f"running, which spreads the riders over more buses than ran and so understates people per bus; passenger-km "
      f"per seat-km scales with 1/rho to first order ({_num(lf['at_implied_rho_first_order'], 2)} at the implied "
      f"rho). Bus-km uses an average rho of {_num(bk['rho'], 2)} ({bk['rho_source']}); "
      f"{bk['passings_without_shape']:,} of {bk['passings']:,} DTC passings have no segment length. Load factor: DTC "
      f"{_num(lf['by_operator'].get('DTC', {}).get('load_factor'), 3)}, cluster "
      f"{_num(lf['by_operator'].get('DIMTS', {}).get('load_factor'), 3)}, over {_pct(lf['coverage_bus_km_share'])} of "
      f"weekday bus-km that has a commuter-facing level.\n")

    fa = lf["full_allocation"]
    a(f"\n**Load factor bracket.** With the model as it stands (people on a bus never exceed the crush load, riders "
      f"that no bus can carry are left unplaced) the weekday load factor is {_num(lf['model'], 3)}; with the "
      f"capacity bound off and the published ridership placed in full it is {_num(fa['all']['uncapped'], 3)} "
      f"({_num(fa['all']['capped_at_crush'], 3)} if people on board are still capped at crush), against the published "
      f"{_band(*lf['band'])}. Unallocated share of published ridership: DTC {_pct(h['unallocated_share_dtc'])}, cluster "
      f"{_pct(h['unallocated_share_dimts'])}. Published ridership, the GPS-measured trips that ran (DTC bus-km "
      f"{_num(bk['model'], 0)} against the published {_num(bk['published'], 0)}) and the crush capacity do not fit "
      f"together. The model never puts more than the crush load on a bus, so on capped routes the crowding shown is "
      f"a conservative (lower) estimate; the true load factor lies between the two cases. The 80%-of-stops rule for "
      f"a trip that ran is conservative; the bus-km agreement ({_num(bk['rho'], 2)} against the implied "
      f"{_num(bk['implied_rho'], 2)}) supports it.\n")

    a("## E. Sensitivity\n")
    a("Share of commuter-facing cells (shared with the base case) whose level changes.\n")
    rows = [(v["description"], f"{v['cells']:,}", _pct(v["share_changed"]), _pct(v["share_changed_rider_weighted"]),
             f"{v['more_crowded']:,}", f"{v['less_crowded']:,}") for v in sn.values()]
    a(_tbl(["Case", "Cells", "Changed", "Changed (rider-weighted)", "More crowded", "Less crowded"], rows))
    a("\nCeiling cases also change how much published ridership is placed:\n")
    rows = []
    for k, v in sn.items():
        if k.startswith("ceiling_") or k == "no_capacity_bound":
            for op, o in v["operators"].items():
                rows.append((v["description"], op, _num(o["e_star"], 1), o["capped_routes"],
                             _pct(o["unallocated_share"])))
    a(_tbl(["Case", "Operator", "E*", "Capped routes", "Unallocated ridership"], rows))

    a("\n## F. Diagnostics (reported, not gates)\n")
    oc = dg["over_capacity"]
    a("### Over-capacity\n")
    a("Share of weekday bus-km that is Usually crowded, and the share where people on board exceed the crush load, "
      "by operator and hour (peak hours shown).\n")
    pk = [x for x in oc["by_operator_hour"] if x["hour"] in (8, 9, 13, 18, 19)]
    a(_tbl(["Operator", "Hour", "Usually crowded", "Over crush load"],
           [(x["operator"], f"{int(x['hour']):02d}:00", _pct(x["share_crowded"]), _pct(x["share_over_crush"]))
            for x in pk]))
    a("\nRoutes with the largest over-crush share, and the suspected cause:\n")
    a(_tbl(["Route", "Operator", "Cells", "Over crush", "Mean E", "Mean buses", "Suspected cause"],
           [(x["route"], x["operator"], x["cells"], _pct(x["share_over_crush"]), _num(x["e_r"], 1),
             _num(x["buses"], 1), x["suspected_cause"]) for x in oc["top_routes"]]))
    a("\n### Level shares by hour band (share of scheduled bus-km)\n")
    a(_tbl(["Day", "Band", "Usually seats", "Usually standing", "Usually crowded", "No data"],
           [(x["day_type"], x["band"], _pct(x["seats"]), _pct(x["standing"]), _pct(x["crowded"]), _pct(x["no_data"]))
            for x in dg["level_shares"]["by_band"]]))
    rs = dg["resolution_below_80"]
    a(f"\n### Ticket resolution\n\n{rs['below_threshold']} of {rs['route_strings']} route strings with at least "
      f"{rs['min_tickets']} tickets resolve under {_pct(rs['threshold'], 0)}; they hold {rs['tickets_in_those']:,} "
      f"tickets ({_pct(rs['share_of_tickets'])} of all).\n")
    ta = dg["terminal_asymmetry"]
    a(f"### Terminal asymmetry\n\n{ta['routes_with_known_ratio']} of {ta['routes']} route directions have a known "
      f"terminal alighting ratio (median {_num(ta['median_ratio'], 2)}, 90th percentile {_num(ta['p90_ratio'], 2)}); "
      f"{ta['routes_corrected']} were corrected ({ta['moved_passengers']:,.0f} passengers moved); "
      f"{ta['alighting_sensitive_routes']} are alighting-sensitive and show Rough guess at best on their last "
      f"stretches.\n")
    sh = dg["null_vs_linked_split_half"]
    a(f"### Vehicle-linked vs unlinked tickets\n\nOn {sh['route_hours']:,} weekday route-hours with at least 5 "
      f"tickets in each half, the two halves correlate at {_num(sh['pearson'], 3)} (Pearson) and "
      f"{_num(sh['spearman'], 3)} (Spearman); the hourly profile correlates at "
      f"{_num(sh['hourly_profile_correlation'], 3)}.\n")
    gd = dg["gps_rho"]
    if gd["status"] == "available":
        a("### GPS: share of scheduled trips that ran, and run times\n")
        a("A trip counts as run when one vehicle passes at least 80% of the route's stops in order (positions "
          "interpolated between pings, 75 m), on ten sample days (six weekdays, four weekend days). The share is "
          "observed trips divided by scheduled trips times coverage, and is set only where at least 80% of the "
          "route's ticket-linked vehicles appear in the feed; other routes keep the schedule.\n")
        rows = []
        for dt in ("weekday", "weekend"):
            x = gd[dt]
            qq = x["route_rho_quantiles"]
            rows.append((dt, f"{x['routes_with_coverage_80']:,} of {x['routes']:,} ({_pct(x['share_coverage_80'])})",
                         _num(qq["p10"], 2), _num(qq["p50"], 2), _num(qq["p90"], 2),
                         _num(x["scheduled_weighted_rho"], 2),
                         f"{_num(x['first_third'], 2)} / {_num(x['middle_third'], 2)} / {_num(x['last_third'], 2)}"))
        a(_tbl(["Day type", "Routes with coverage 0.8+", "Route share 10th pct", "Median", "90th pct",
                "Trip-weighted share", "First / middle / last third"], rows))
        a("\nRun time, GPS against the ticket-pair clock (1.00 means they agree; trip-weighted mean over route-hours, "
          "weekdays):\n")
        rt = gd["runtime_ratio_by_hour"]
        hrs = sorted(rt)
        a(_tbl(["Hour"] + [f"{h_:02d}" for h_ in hrs], [("Ratio",) + tuple(_num(rt[h_]["ratio"], 2) for h_ in hrs)]))
        a("")
    a("### Not available yet\n\n" + ("Choice " if gd["status"] == "available" else "GPS rho distribution and run-time cross-check (GPS aggregates "
                                                   "not built); choice ") +
      "stability for alternatives with the same origin, destination and hour (planner not built).\n")
    text = "\n".join(L)
    for w_ in FORBIDDEN:
        if w_.lower() in text.lower():
            raise GateError(f"validation_report.md contains a forbidden word: {w_!r}")
    return text


def render_dq(con, rep: dict) -> str:
    L = []
    a = L.append
    a("# Data quality\n")
    a("Every table here is read from the pipeline's own tables (`dq_*` and the tables they describe).\n")
    daily = con.execute("SELECT date, tickets, pax, null_share, ac_pax, nonac_pax FROM dq_daily ORDER BY date").df()
    a("## Clean\n")
    a(f"{int(daily['tickets'].sum()):,} tickets and {int(daily['pax'].sum()):,} passengers on {len(daily)} dates; "
      f"{_pct(float((daily['null_share'] * daily['tickets']).sum() / daily['tickets'].sum()))} of tickets carry no "
      f"vehicle number. Excluded dates: 2 and 20 October; excluded windows are cut from every rider count.\n")
    a(_tbl(["Date", "Tickets", "Passengers", "No vehicle", "AC passengers", "Non-AC passengers"],
           [(str(r.date), f"{r.tickets:,}", f"{r.pax:,}", _pct(r.null_share), f"{r.ac_pax:,}", f"{r.nonac_pax:,}")
            for r in daily.itertuples()]))
    res = con.execute("SELECT reason, tickets, pax FROM dq_resolve ORDER BY tickets DESC").fetchall()
    c = rep["gates"]["ticket_conservation"]
    a("\n## Resolve\n")
    a(f"{c['clean']:,} clean tickets = {c['resolved']:,} resolved + {c['rejected']:,} rejected "
      f"(match rate {_pct(c['resolved'] / c['clean'])}).\n")
    a(_tbl(["Rejected because", "Tickets", "Passengers"], [(r[0], f"{r[1]:,}", f"{r[2]:,}") for r in res]))
    a("\n## Network\n")
    dqn = _dq(con, "dq_network")
    mix = {k.removeprefix("bus_mix_"): v for k, v in dqn.items() if k.startswith("bus_mix_")}
    cls = {k.removeprefix("service_class_"): v for k, v in dqn.items() if k.startswith("service_class_")}
    a("Bus mix basis (routes):\n")
    a(_tbl(["Basis", "Routes"], [(k, f"{int(v):,}") for k, v in sorted(mix.items())]))
    a("\nService class (routes):\n")
    a(_tbl(["Class", "Routes"], [(k, f"{int(v):,}") for k, v in sorted(cls.items())]))
    other = {k: v for k, v in dqn.items() if not k.startswith(("bus_mix_", "service_class_"))}
    a("\nOther:\n")
    a(_tbl(["Name", "Value"], [(k, f"{v:,.0f}") for k, v in other.items()]))
    dqc = _dq(con, "dq_clock")
    a("\nTravel-time clock:\n")
    a(_tbl(["Name", "Value"], [(k, f"{v:,.4f}" if abs(v) < 10 else f"{v:,.0f}") for k, v in dqc.items()]))
    pw = rep["diagnostics"]["pair_ratio_window"]
    a(f"\nTicket-pair ratio window {pw['default']['window'][0]:g}-{pw['default']['window'][1]:g} "
      f"({pw['default']['pairs']:,} pairs); with {pw['wide']['window'][0]:g}-{pw['wide']['window'][1]:g} there "
      f"would be {pw['wide']['pairs']:,} pairs and the largest operator-hour factor changes by "
      f"{_pct(pw['max_relative_difference'])}.\n")
    a("## Riders\n")
    dqr = _dq(con, "dq_riders")
    a(_tbl(["Name", "Value"], [(k, f"{v:,.0f}") for k, v in dqr.items()]))
    a(f"\nRider-minute gate deviation: {rep['gates']['rider_minutes']['deviation']:.4%} (limit 0.5%).\n")
    a("## Levels\n")
    dql = _dq(con, "dq_levels")
    a(_tbl(["Name", "Value"], [(k, f"{v:,.4f}" if abs(v) < 100 else f"{v:,.0f}") for k, v in dql.items()]))
    h = rep["headline_numbers"]
    a(f"\nThe E* ceiling is {h['e_scale_ceiling_multiplier']:g} x E_op. DTC: ceiling "
      f"{'binds' if h['ceiling_bound_dtc'] else 'does not bind'}, unallocated {_pct(h['unallocated_share_dtc'])}. "
      f"Cluster: ceiling {'binds' if h['ceiling_bound_dimts'] else 'does not bind'}, unallocated "
      f"{_pct(h['unallocated_share_dimts'])} of published ridership.\n")
    text = "\n".join(L)
    for w_ in FORBIDDEN:
        if w_.lower() in text.lower():
            raise GateError(f"data_quality.md contains a forbidden word: {w_!r}")
    return text


# =================================================================== stage entry

class Report(dict):
    def __str__(self) -> str:
        h = self["headline_numbers"]
        return (f"{h['corridor_hits_total']}/{h['corridors_total']} corridors, unchanged {_pct(h['unchanged_level_share'])}, "
                f"bus-km {h['dtc_bus_km_model']:,.0f}, load factor {h['load_factor_model']:.3f}, "
                f"{self['diagnostics']['runtime_seconds']:.0f}s")


def run(con, paths, **_) -> Report:
    t0 = time.perf_counter()
    paths.processed.mkdir(parents=True, exist_ok=True)
    timings = {}

    def lap(name, t=[t0]):
        now = time.perf_counter()
        timings[name] = round(now - t[0], 1)
        t[0] = now
        print(f"validate: {name} {timings[name]}s")

    gates = run_gates(con)
    lap("gates")
    loads._eligible(con)
    _scx(con)
    exp = load_expectations(Path(paths.repo) / "validation" / "expectations.yaml")
    exp_res = {
        "peaks": peak_rule(_hourly(con, "weekday"), exp.peaks["am"], exp.peaks["pm"]),
        "weekend": weekend_rule(_hourly(con, "weekday"), _hourly(con, "weekend")),
        "radial": radial(con),
        "corridors": corridors(con, exp),
        "gps_stoptime": {"status": "not available", "note": "GPS aggregates do not exist yet; not counted as a miss",
                         "rho_min": exp.gps_stoptime_rho_min},
        "weekday_hourly_crowded_rider_min": _hourly(con, "weekday").round(1).tolist(),
        "weekend_hourly_crowded_rider_min": _hourly(con, "weekend").round(1).tolist(),
    }
    pub = published(con, exp)
    lap("expectations_and_published")
    repro = _reproduction(con)
    lap("base_case")
    _weights(con)
    sens = sensitivity(con, paths)
    lap("sensitivity")
    rep = repeatability(con)
    lap("repeatability")
    diag = diagnostics(con)
    lap("diagnostics")
    diag["runtime_seconds"] = round(time.perf_counter() - t0, 1)
    diag["timings"] = timings
    report = Report(
        gates=gates, expectations=exp_res, repeatability=rep,
        independent={"dtc_bus_km": pub["dtc_bus_km"], "load_factor": pub["load_factor"],
                     "corridors": exp_res["corridors"]["by_grade"],
                     "gps_stoptime": exp_res["gps_stoptime"],
                     "field_count": "not possible; no on-bus counts exist"},
        sensitivity=sens, diagnostics=diag, coverage_summary=coverage_summary(con), reproduction=repro,
        headline_numbers={})
    report["headline_numbers"] = headline(con, gates, exp_res, rep, pub, sens, diag, repro)
    report["headline_numbers"]["validation_runtime_seconds"] = diag["runtime_seconds"]
    (paths.processed / "validation_report.json").write_text(
        json.dumps(_jsonable(report), indent=1, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    (paths.processed / "validation_report.md").write_text(render_md(report), encoding="utf-8")
    (paths.processed / "data_quality.md").write_text(render_dq(con, report), encoding="utf-8")
    return report
