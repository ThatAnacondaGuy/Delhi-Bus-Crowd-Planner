"""Toy GPS day file (SQLite, same schema as the feed) and canonical stops for tests/test_gps.py."""
import sqlite3
from pathlib import Path

import pandas as pd

DAY = "2026-10-15"
BASE_TS = 1792000000          # a few hours into 15 Oct IST; tests read hours from the data, not this constant
LAT0, LON0, STEP = 28.600, 77.200, 0.002   # stops ~220 m apart along a line of longitude


def toy_stops() -> pd.DataFrame:
    rows = [(101, "101UP", "DTC", i + 1, f"S{i + 1}", f"Stop {i + 1}", LAT0, LON0 + i * STEP,
             0 if i == 0 else 120, i * 120) for i in range(5)]
    return pd.DataFrame(rows, columns=["route_id", "short_name", "operator", "seq", "stop_id", "stop_name",
                                       "lat", "lon", "template_s", "cum_template_s"])


def ping(vehicle, trip, k, seq, speed=-99.0, off_m=0.0, route=101):
    """A ping at stop `seq` (1-based) at time BASE_TS + k * 11 s, `off_m` metres north of the stop."""
    lat = LAT0 + off_m / 111195.0
    lon = LON0 + (seq - 1) * STEP
    ts = BASE_TS + k * 11
    return (vehicle, str(lat), str(lon), speed, float(route), trip, str(ts), DAY, "10:00:00")


def build_toy_gps(path: Path, extra=()) -> Path:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE vehicle_feed (vehicle_id text, lat text, lng text, speed real, route_id real, "
                "trip_id text, timestamp text, date date, time text)")
    rows = []
    # A passes all 5 stops, B turns back after 4 of 5, C after 3 of 5; D drives the route in reverse
    for veh, seqs in (("A", [1, 2, 3, 4, 5]), ("B", [1, 2, 3, 4]), ("C", [1, 2, 3]), ("D", [5, 4, 3, 2, 1])):
        rows += [ping(veh, f"101_{veh}", 10 * i + j, s) for i, s in enumerate(seqs) for j in (0, 1)]
    rows.append(ping("A", "101_A", 0, 1))                       # exact duplicate poll of A's first ping
    rows += [ping("E", "101_E", i, s, off_m=300.0) for i, s in enumerate([1, 2, 3, 4, 5])]  # 300 m off: no match
    rows += list(extra)
    con.executemany("INSERT INTO vehicle_feed VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path
