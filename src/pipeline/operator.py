"""Operator view: where one extra departure removes the most crowded rider-minutes (design: operator ranking).

For each route-direction, day type and departure minute (30-min steps) the extra bus is walked down the route
on the corrected clock. At each stretch it reaches, the cell of the window nearest the arrival time gets one
more bus (people per bus x S / (S + 1)); riders whose level improves are counted, and riders leaving the
crowded level contribute rider-minutes (riders x stretch run time).
"""
import numpy as np
import pandas as pd

from .config import WINDOWS
from .loads import _level_v
from .network import Clock

DEPART_STEP_MIN = 30
_RANK = {"seats": 0, "standing": 1, "crowded": 2}
COLUMNS = ["route_id", "short_name", "operator", "direction", "day_type", "depart_min",
           "crowded_rider_min_removed", "riders_moved_down", "max_load_section", "peak_load_factor",
           "evidence_share", "flags"]


def _cells(con) -> pd.DataFrame:
    df = con.execute("""
        SELECT route_id, short_name, operator, direction, seq, from_name, to_name, day_type, window_start_min,
               buses, seats, rated_total, people_mid, evidence, flags
        FROM stretch_crowding WHERE evidence <> 'none' AND people_mid IS NOT NULL AND buses > 0""").df()
    p = df["people_mid"].to_numpy(float)
    s = df["buses"].to_numpy(float)
    old = _level_v(p, df["seats"].to_numpy(float), df["rated_total"].to_numpy(float))
    new = _level_v(p * s / (s + 1.0), df["seats"].to_numpy(float), df["rated_total"].to_numpy(float))
    ro = np.vectorize(_RANK.get)(old)
    rn = np.vectorize(_RANK.get)(new)
    df["riders"] = p * s
    df["dropped_crowded"] = (ro == 2) & (rn < 2)
    df["moved_down"] = rn < ro
    df["load_factor"] = p / df["rated_total"].to_numpy(float)
    return df


def _route_rows(clock: Clock, g: pd.DataFrame, day_type: str) -> list[tuple]:
    """Rows for one route-direction and day type."""
    spec = WINDOWS[day_type]
    nw = (1440 - 1) // spec.step_min + 1
    rid = int(g["route_id"].iloc[0])
    n_st = int(g["seq"].max())
    idx = {}
    for r in g.itertuples(index=False):
        idx[(int(r.seq), int(r.window_start_min) // spec.step_min)] = r
    fac = clock.hour_factors(rid)
    # stretch k (stop k to k+1) takes the template of the segment ending at stop k+1
    tmpl = [0.0] + [clock.template(rid, k + 1) for k in range(1, n_st + 1)]
    head = g.iloc[0]
    out = []
    for d in range(0, 1440, DEPART_STEP_MIN):
        t = float(d)
        removed = moved = 0.0
        peak = None
        n_cells = n_many = 0
        flags: set[str] = set()
        for k in range(1, n_st + 1):
            wi = int(((t % 1440.0) / spec.step_min) + 0.5) % nw
            dur = tmpl[k] * fac[int(t // 60) % 24] / 60.0
            c = idx.get((k, wi))
            if c is not None:
                n_cells += 1
                n_many += c.evidence == "many_tickets"
                lf = c.people_mid / c.rated_total
                if peak is None or lf > peak[0]:
                    peak = (lf, f"{c.from_name} to {c.to_name}")
                if c.moved_down:
                    moved += c.riders
                    flags.update(f for f in str(c.flags).split(",") if f)
                if c.dropped_crowded:
                    removed += c.riders * dur
            t += dur
        if n_cells == 0:
            continue
        out.append((rid, head["short_name"], head["operator"], head["direction"], day_type, d,
                    round(removed, 3), round(moved, 3), peak[1], round(peak[0], 4),
                    round(n_many / n_cells, 4), ",".join(sorted(flags))))
    return out


def run(con, paths, **_) -> int:
    cells = _cells(con)
    clock = Clock.load(con)
    rows: list[tuple] = []
    for (rid, dt), g in cells.groupby(["route_id", "day_type"], sort=False):
        rows.extend(_route_rows(clock, g.sort_values(["seq", "window_start_min"]), dt))
    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.sort_values(["crowded_rider_min_removed", "riders_moved_down", "route_id", "day_type", "depart_min"],
                        ascending=[False, False, True, True, True], kind="stable").reset_index(drop=True)
    paths.processed.mkdir(parents=True, exist_ok=True)
    con.register("_operator_df", df)
    con.execute("CREATE OR REPLACE TABLE operator_trips AS SELECT * FROM _operator_df")
    con.unregister("_operator_df")
    con.execute(f"COPY operator_trips TO '{paths.processed / 'operator_trips.parquet'}' (FORMAT PARQUET)")
    return len(df)
