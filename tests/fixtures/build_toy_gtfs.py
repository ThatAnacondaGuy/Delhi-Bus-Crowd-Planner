"""Build the toy GTFS feed in tests/fixtures/toy_gtfs/. Run: venv/bin/python tests/fixtures/build_toy_gtfs.py"""
import csv
from pathlib import Path

OUT = Path(__file__).parent / "toy_gtfs"

STOPS = {
    1: ("Alpha Terminal", 28.6000, 77.2000),
    2: ("Bravo Market", 28.61349, 77.2000),
    3: ("Charlie Chowk", 28.62698, 77.2000),
    4: ("Delta Metro", 28.64047, 77.2000),
    5: ("Echo Depot", 28.65396, 77.2000),
    6: ("Foxtrot Nagar", 28.62698, 77.21531),
    7: ("Charlie Chowk Opp", 28.62700, 77.20030),
    8: ("Connaught Place", 28.6700, 77.2000),      # walk-only
    9: ("ISBT Anand Vihar", 28.5900, 77.2000),     # walk-only
}
# (agency, route_id, short, long, stops, first, last, headway_min)
ROUTES = [
    ("DTC", 101, "101UP", "Alpha to Echo", [1, 2, 3, 4, 5], "06:00", "21:45", 15),
    ("DTC", 102, "101DOWN", "Echo to Alpha", [5, 4, 3, 2, 1], "06:00", "21:45", 15),
    ("DIMTS", 201, "202UP", "Bravo to Foxtrot", [2, 3, 6], "06:00", "21:30", 30),
    ("DIMTS", 202, "202DOWN", "Foxtrot to Bravo", [6, 3, 2], "06:00", "21:30", 30),
    ("DTC", 301, "D-005UP", "Alpha to Charlie", [1, 2, 3], "07:00", "20:00", 20),
    ("DTC", 401, "OMS(+)UP", "Ring", [2, 3, 6, 2], "06:00", "21:30", 30),
    ("DTC", 501, "909UP", "Delta to Echo", [4, 5], "06:00", "21:00", 60),
    ("DTC", 601, "DS-12DOWN", "Delta to Echo night", [4, 5], "07:00", "09:00", 60),
    ("DTC", 701, "SPL-1UP", "School Special", [1, 2], "07:00", "09:00", 60),
]
SEG_S = 300
RING_CLOSE_S = 424   # stop 6 -> stop 2


def hms(sec):
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def mins(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def write(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write("agency.txt", ["agency_id", "agency_name", "agency_url", "agency_timezone"],
          [["DTC", "DTC", "https://example.invalid/dtc", "Asia/Kolkata"],
           ["DIMTS", "DIMTS", "https://example.invalid/dimts", "Asia/Kolkata"]])
    write("stops.txt", ["stop_id", "stop_name", "stop_lat", "stop_lon"],
          [[i, n, la, lo] for i, (n, la, lo) in STOPS.items()])
    write("routes.txt", ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
          [[r, a, s, ln, 3] for a, r, s, ln, *_ in ROUTES])
    write("calendar.txt",
          ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
           "start_date", "end_date"],
          [[1, 1, 1, 1, 1, 1, 1, 1, "20250101", "20400101"]])
    trips, times, shapes = [], [], []
    for a, rid, short, _ln, stops, first, last, hw in ROUTES:
        shape_id = f"shp{rid}"
        for seq, s in enumerate(stops, 1):
            shapes.append([shape_id, STOPS[s][1], STOPS[s][2], seq])
        offsets = [0]
        for i in range(1, len(stops)):
            ring_close = stops[i - 1] == 6 and stops[i] == 2
            offsets.append(offsets[-1] + (RING_CLOSE_S if ring_close else SEG_S))
        for dep in range(mins(first), mins(last) + 1, hw):
            tid = f"{short}_{dep // 60:02d}{dep % 60:02d}"
            trips.append([rid, 1, tid, shape_id])
            for seq, (s, off) in enumerate(zip(stops, offsets), 1):
                t = hms(dep * 60 + off)
                times.append([tid, t, t, s, seq])
    write("trips.txt", ["route_id", "service_id", "trip_id", "shape_id"], trips)
    write("stop_times.txt", ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"], times)
    write("shapes.txt", ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"], shapes)


if __name__ == "__main__":
    main()
