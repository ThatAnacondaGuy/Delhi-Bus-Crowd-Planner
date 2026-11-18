import csv
import datetime as dt

import yaml

from src.pipeline import config
from src.pipeline.config import (
    BUS_SPECS, EVIDENCE_COPY, EXCLUDED_WINDOWS, LEVEL_COPY, PUBLISHED_RIDERSHIP,
    WINDOWS, BusSpec, WindowSpec,
)
from src.pipeline.db import connect
from src.pipeline.errors import GateError, RenderError
from tests.helpers import make_tickets


def _rows(d, name):
    with open(d / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _secs(t):
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def test_bus_specs():
    assert BUS_SPECS["12m_ac"] == BusSpec(35, 63, 100, 77)
    assert BUS_SPECS["9m_devi"] == BusSpec(23, 36, 42, 32)
    assert BUS_SPECS["12m_nonac"] == BusSpec(37, 63, 100, 79)


def test_timezone_pinned(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    assert connect().execute("select hour(timestamptz '2026-10-15 08:10:00+05:30')").fetchone()[0] == 8


def test_copy_exact():
    assert LEVEL_COPY["seats"] == ("Usually seats", "आमतौर पर सीट मिल जाती है")
    assert LEVEL_COPY["no_data"] == ("No data", "जानकारी नहीं")
    assert EVIDENCE_COPY["rough"] == ("Rough guess", "अंदाज़ा (कम टिकट)")
    assert config.FULL_COPY == ("Full buses may not stop", "भरी बस शायद न रुके")


def test_constants_and_calendar():
    assert PUBLISHED_RIDERSHIP["DTC"].value == 2_429_000
    assert PUBLISHED_RIDERSHIP["DIMTS"].value == 1_530_000
    assert WINDOWS["weekday"] == WindowSpec(30, 90)
    assert WINDOWS["weekend"] == WindowSpec(60, 120)
    assert config.PUBLISHED_LOAD_FACTOR_BAND == (0.78, 0.89)
    assert config.LOW_APP_USE_FRACTION == 1 / 3
    assert len(EXCLUDED_WINDOWS) == 3
    start, end = EXCLUDED_WINDOWS[1]
    assert start == dt.datetime(2026, 10, 17, 11, 45, tzinfo=start.tzinfo)
    assert start.utcoffset() == dt.timedelta(hours=5, minutes=30)
    assert end - start == dt.timedelta(hours=46, minutes=15)
    assert len(config.WEEK_BLOCKS) == 4


def test_errors():
    assert issubclass(GateError, RuntimeError) and issubclass(RenderError, RuntimeError)


def test_toy_template_is_300s(toy_gtfs_dir):
    st = [r for r in _rows(toy_gtfs_dir, "stop_times.txt") if r["trip_id"].startswith("101UP")]
    assert st
    by_trip = {}
    for r in st:
        by_trip.setdefault(r["trip_id"], []).append(r)
    for rows in by_trip.values():
        rows.sort(key=lambda r: int(r["stop_sequence"]))
        assert [r["stop_id"] for r in rows] == ["1", "2", "3", "4", "5"]
        gaps = [_secs(b["arrival_time"]) - _secs(a["arrival_time"]) for a, b in zip(rows, rows[1:])]
        assert gaps == [300] * 4


def test_toy_ring_closing_segment_424s(toy_gtfs_dir):
    rows = [r for r in _rows(toy_gtfs_dir, "stop_times.txt") if r["trip_id"].startswith("OMS")]
    first = sorted([r for r in rows if r["trip_id"] == rows[0]["trip_id"]], key=lambda r: int(r["stop_sequence"]))
    assert [r["stop_id"] for r in first] == ["2", "3", "6", "2"]
    gaps = [_secs(b["arrival_time"]) - _secs(a["arrival_time"]) for a, b in zip(first, first[1:])]
    assert gaps == [300, 300, 424]


def test_toy_routes_and_schedules(toy_gtfs_dir):
    routes = {r["route_id"]: r for r in _rows(toy_gtfs_dir, "routes.txt")}
    assert {k: (v["agency_id"], v["route_short_name"]) for k, v in routes.items()} == {
        "101": ("DTC", "101UP"), "102": ("DTC", "101DOWN"), "201": ("DIMTS", "202UP"),
        "202": ("DIMTS", "202DOWN"), "301": ("DTC", "D-005UP"), "401": ("DTC", "OMS(+)UP"),
        "501": ("DTC", "909UP"), "601": ("DTC", "DS-12DOWN"), "701": ("DTC", "SPL-1UP"),
    }
    assert routes["701"]["route_long_name"] == "School Special"
    trips = _rows(toy_gtfs_dir, "trips.txt")
    count = lambda rid: sum(t["route_id"] == rid for t in trips)
    assert count("101") == 64 and count("102") == 64      # 06:00-21:45 every 15
    assert count("201") == 32 and count("401") == 32      # 06:00-21:30 every 30
    assert count("301") == 40                             # 07:00-20:00 every 20
    assert count("501") == 16                             # 06:00-21:00 hourly
    assert count("601") == 3 and count("701") == 3


def test_toy_stops_and_walk_only_stops(toy_gtfs_dir):
    stops = {r["stop_id"]: r for r in _rows(toy_gtfs_dir, "stops.txt")}
    assert stops["1"]["stop_name"] == "Alpha Terminal"
    assert stops["8"]["stop_name"] == "Connaught Place"
    assert stops["9"]["stop_name"] == "ISBT Anand Vihar"
    served = {r["stop_id"] for r in _rows(toy_gtfs_dir, "stop_times.txt")}
    assert "8" not in served and "9" not in served and served == {"1", "2", "3", "4", "5", "6"}
    cal = _rows(toy_gtfs_dir, "calendar.txt")[0]
    assert cal["start_date"] == "20250101" and cal["end_date"] == "20400101"


def test_hubs_match_walk_only_stops(toy_gtfs_dir):
    from pathlib import Path
    hubs = yaml.safe_load((Path(config.__file__).parent / "hubs.yaml").read_text(encoding="utf-8"))
    for must in ["Connaught Place", "ISBT Anand Vihar", "Kashmere Gate", "Sarai Kale Khan", "AIIMS",
                 "ITO", "Mandi House", "Nehru Place", "Dhaula Kuan", "Laxmi Nagar", "Chirag Delhi",
                 "Ambedkar Nagar", "Mori Gate", "Badarpur Border", "Saket", "Karkardooma"]:
        assert must in hubs
        assert hubs[must]["aliases"] and hubs[must]["gtfs_stems"]
    stops = {r["stop_id"]: r["stop_name"].lower() for r in _rows(toy_gtfs_dir, "stops.txt")}
    for sid, hub in [("8", "Connaught Place"), ("9", "ISBT Anand Vihar")]:
        assert any(s.lower() in stops[sid] for s in hubs[hub]["gtfs_stems"])


def test_make_tickets_header_and_defaults(tmp_path):
    p = make_tickets(tmp_path, [{"route": "101UP", "start_stop_name": "A", "end_stop_name": "B",
                                 "created_at": "2026-10-14 08:00:00+05:30"}])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ('"passenger_count","amount","vehicle_number","ticket_type_id",'
                        '"end_stop_name","route","start_stop_name","created_at","is_ac"')
    assert lines[1] == '"1","9.0","NULL","1","B","101UP","A","2026-10-14 08:00:00+05:30","True"'


def test_published_sources_have_urls():
    for src in [*PUBLISHED_RIDERSHIP.values(), config.PUBLISHED_DTC_BUS_KM]:
        assert src.url.startswith("https://")
