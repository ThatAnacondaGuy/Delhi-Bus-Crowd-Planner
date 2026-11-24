from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.pipeline import clean
from src.pipeline.paths import Paths
from tests.helpers import make_tickets

IST = ZoneInfo("Asia/Kolkata")


def at(d, h, m=0):
    return datetime(2026, 10, d, h, m, tzinfo=IST)


def paths_for(csv, tmp_path):
    p = Paths.default()
    return Paths(p.repo, p.gtfs_dir, csv, p.gps_archive, p.gps_aggregates, tmp_path)


@pytest.fixture
def october(con, tmp_path):
    rows = [{"route": "R1", "created_at": f"2026-10-{d:02d} 08:00:00.000000+05:30"} for d in range(1, 32)]
    clean.run(con, paths_for(make_tickets(tmp_path, rows), tmp_path), None)
    return con


def test_day_types(october):
    got = dict(october.execute("SELECT date, day_type FROM clean_days").fetchall())
    assert got[date(2026, 10, 3)] == "weekend"
    assert got[date(2026, 10, 5)] == "weekday"


def test_excluded():
    assert clean.excluded(at(2, 12))
    assert clean.excluded(at(6, 10)) and not clean.excluded(at(6, 11, 30))
    assert clean.excluded(at(18, 9))
    assert clean.excluded(at(29, 19, 30)) and not clean.excluded(at(29, 18, 30))
    assert not clean.excluded(at(19, 10))  # half-open: window end is clean


def test_clean_day_count(october):
    # Weekdays in Oct 2026: 22. Minus excluded dates 2 and 20 Oct = 20; minus 6 Oct at 10:00
    # (window 09:15-11:00) = 19. 19 Oct 10:00 is the half-open window END, so it stays.
    assert clean.clean_day_count(october, "weekday", 600) == 19
    # Saturdays 3,10,17,24,31 + Sundays 4,11,18,25 = 9; 18 Oct is inside the 17 Oct 11:45 ->
    # 19 Oct 10:00 window, 17 Oct at 10:00 is before it opens: 9 - 1 = 8.
    assert clean.clean_day_count(october, "weekend", 600) == 8
    # At 12:00, 17 Oct is also inside the window: 7.
    assert clean.clean_day_count(october, "weekend", 720) == 7


def test_null_vehicle_and_trim(con, tmp_path):
    rows = [{"vehicle_number": "NULL"}, {"vehicle_number": ""}, {"vehicle_number": " DL1PD6826 "}]
    for i, r in enumerate(rows):
        r["created_at"] = f"2026-10-05 08:0{i}:00+05:30"
    stats = clean.run(con, paths_for(make_tickets(tmp_path, rows), tmp_path), None)
    got = con.execute("SELECT vehicle, channel FROM tickets_clean ORDER BY ticket_id").fetchall()
    assert got == [(None, "null"), (None, "null"), ("DL1PD6826", "linked")]
    assert stats.rows == 3
    assert con.execute("SELECT tickets, null_share FROM dq_daily").fetchone() == (3, pytest.approx(2 / 3))


def test_ist_date_and_sample(con, tmp_path):
    rows = [{"route": "A", "created_at": "2026-10-05 23:30:00+05:30"},
            {"route": "B", "created_at": "2026-10-05 23:30:00+05:30"}]
    clean.run(con, paths_for(make_tickets(tmp_path, rows), tmp_path), ["A"])
    assert con.execute("SELECT route_raw, date FROM tickets_clean").fetchall() == [("A", date(2026, 10, 5))]


def test_ist_date_not_session_dependent(con, tmp_path):
    # Sat 3 Oct 00:30 IST is Fri 2 Oct 19:00 UTC; a UTC session must still give the IST date.
    con.execute("SET TimeZone='UTC'")
    rows = [{"created_at": "2026-10-03 00:30:00+05:30"}]
    clean.run(con, paths_for(make_tickets(tmp_path, rows), tmp_path), None)
    assert con.execute("SELECT date, day_type FROM tickets_clean").fetchall() == [(date(2026, 10, 3), "weekend")]
