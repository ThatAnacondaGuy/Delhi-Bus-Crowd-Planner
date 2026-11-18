"""Every constant and sourced assumption for the pipeline lives here."""
from datetime import datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo

TZ = "Asia/Kolkata"
_IST = ZoneInfo(TZ)


class BusSpec(NamedTuple):
    seats: int
    rated_total: int
    crush: int
    comfortable: int


BUS_SPECS: dict[str, BusSpec] = {
    "12m_ac": BusSpec(35, 63, 100, 77),
    "9m_devi": BusSpec(23, 36, 42, 32),
    "12m_nonac": BusSpec(37, 63, 100, 79),
}


class Source(NamedTuple):
    value: float
    year: str
    url: str
    note: str


PUBLISHED_RIDERSHIP: dict[str, Source] = {
    "DTC": Source(2_429_000, "FY2025-26", "", "Published average daily DTC ridership; add citation URL from research notes."),
    "DIMTS": Source(1_530_000, "FY2024-25", "", "Published average daily DIMTS (cluster) ridership; add citation URL from research notes."),
}
PUBLISHED_DTC_BUS_KM = Source(501_000, "2025-26", "", "Published DTC daily bus-km; add citation URL from research notes.")
PUBLISHED_LOAD_FACTOR_BAND = (0.78, 0.89)

# Calendar
EXCLUDED_DATES = ["2026-10-02", "2026-10-20"]


def _ist(y, mo, d, h, mi) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=_IST)


EXCLUDED_WINDOWS: list[tuple[datetime, datetime]] = [
    (_ist(2026, 10, 6, 9, 15), _ist(2026, 10, 6, 11, 0)),
    (_ist(2026, 10, 17, 11, 45), _ist(2026, 10, 19, 10, 0)),
    (_ist(2026, 10, 29, 19, 0), _ist(2026, 10, 30, 0, 0)),
]
WEEK_BLOCKS = [
    ("2026-10-05", "2026-10-09"),
    ("2026-10-12", "2026-10-16"),
    ("2026-10-21", "2026-10-23"),
    ("2026-10-26", "2026-10-30"),
]


class WindowSpec(NamedTuple):
    step_min: int
    base_min: int


WINDOWS = {"weekday": WindowSpec(30, 90), "weekend": WindowSpec(60, 120)}

# Model constants
SEATS_FRACTION = 0.7
SCALE_RANGE = (0.7, 1.3)
BOUND_PERCENTILE = 0.95
BOUND_MIN_TICKETS = 30
RUNTIME_MIN_PAIRS = 30
RUNTIME_MIN_GAP_S = 600
RUNTIME_GATE_TOL = 0.15
CONSERVATION_TOL = 0.005
S0_MAX_SHARE = 0.01
LOW_APP_USE_FRACTION = 1 / 3
NO_DATA_PERCENTILE = 0.25
DEVI_ROUTE_RE = r"^D-\d"
DEVI_VEHICLE_MIN_TICKETS = 5
DEVI_ROUTE_SHARE = 0.5
PLACE_RADIUS_M = 400

# GPS and planner constants
GPS_COVERAGE_MIN = 0.8
GPS_TRIP_STOP_SHARE = 0.8
GPS_STOPTIME_RHO_MIN = 0.3
LESS_CROWDED_SLACK = (15, 0.30)
LEAVE_LATER_SHIFTS = (10, 20, 30, 40)
HEADLINE_MIN_MINUTES = 5
NIGHT_START_H = 23
NIGHT_END_H = 5

# Commuter copy (EN, HI)
LEVEL_COPY: dict[str, tuple[str, str]] = {
    "seats": ("Usually seats", "आमतौर पर सीट मिल जाती है"),
    "standing": ("Usually standing", "आमतौर पर खड़े होकर जाना पड़ता है"),
    "crowded": ("Usually crowded", "आमतौर पर भारी भीड़"),
    "no_data": ("No data", "जानकारी नहीं"),
}
EVIDENCE_COPY: dict[str, tuple[str, str]] = {
    "many_tickets": ("Based on many tickets", "कई टिकटों पर आधारित"),
    "rough": ("Rough guess", "अंदाज़ा (कम टिकट)"),
    "none": ("No data", "जानकारी नहीं"),
}
FULL_COPY = ("Full buses may not stop", "भरी बस शायद न रुके")
