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


# Sources: research notes section 2 (DTC e-bus RFP cl. 28.2 and 2.1, CESL tender,
# PTI/electrive for DEVI 23+13, JBM Ecolife e9 42).
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


_ES = "https://delhiplanning.delhi.gov.in/sites/default/files/Planning/12_chapter_12_transport.pdf"
PUBLISHED_RIDERSHIP: dict[str, Source] = {
    "DTC": Source(2_429_000, "FY2025-26", _ES,
                  "Economic Survey of Delhi 2025-26, ch. 12; see also "
                  "https://www.millenniumpost.in/delhi/delhi-vehicle-count-up-79-to-876-lakh-653097"),
    "DIMTS": Source(1_530_000, "FY2024-25",
                    "https://www.newsbytesapp.com/news/auto/economic-survey-2025-26-finds-delhi-bus-ridership-down-nearly-20/story",
                    "Reports Economic Survey of Delhi 2025-26 figures."),
}
PUBLISHED_DTC_BUS_KM = Source(501_000, "2025-26", _ES,
                              "Economic Survey of Delhi 2025-26, ch. 12; see also "
                              "https://dailypioneer.com/news/delhis-vehicle-count-hits-87-6-lakh-8-rise-in-2025-26")
# Economic Survey of Delhi 2025-26, ch. 12: DTC 88.33-88.77% in 2024-26, cluster 78% in 2024-25.
# Definitions differ from ours; rough check only.
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
VEHICLE_RULE_MIN_TICKETS = 5  # a non-D route needs this many vehicle-linked tickets for the vehicle rule
PLACE_RADIUS_M = 400

# Ticket resolution (design §5.3)
STOP_FUZZY_MIN_SCORE = 78.0  # assumption: route-scoped RapidFuzz floor kept from the old resolver (93% stop match)
ALIAS_MIN_IN_ORDER = 0.8     # an alias needs >= 80% of its tickets resolving in stop order on the route
MERGE_MIN_ORDERED = 0.9      # two GTFS routes merge only at >= 90% ordered stop match and the same termini
REMAP_MIN_REVERSED = 0.5     # a route string swaps to its opposite when MORE than half its resolvable tickets are reversed
# Variant tokens dropped from route names to find alias candidates (ruling R16): STL/LSTL, EXT/EXTN, EXP, SPL.
ROUTE_VARIANT_TOKENS = r"L?STL|EXTN?|EXP|SPL"

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

# Network assets (Task 8)
IS_AC_MIN_TICKETS = 5   # a route's non-AC share comes from is_ac only with at least this many tickets
# Service classes, matched case-insensitively against route_short_name and route_long_name; first match wins
# in this order. Built from the real routes.txt (route_desc holds stop names, so it is not matched).
# school: MSB (Modern School Barakhamba), SPV (Sardar Patel Vidyalaya), MSVV (Modern School Vasant Vihar),
#   AS (Anchal School), or "school" in the long name. daf: DAF- (Delhi Administration Flats).
# office_special: DS-, U-SPL- (university specials) and CV- (Central Vista office circulars); weekdays only.
SERVICE_CLASS_PATTERNS: dict[str, str] = {
    "daf": r"^DAF-",
    "school": r"^(MSB|SPV|MSVV|AS)\d|\bSCHOOL\b",
    "office_special": r"^(DS|U-SPL|CV)-",
}
HUB_STOP_CATEGORIES = {"metro": r"\bmetro\b", "rail": r"\b(railway|rly)\b"}

# R19: a reverse route with fewer terminal boardings than this (month) is uninformative for the alighting correction
ALIGHTING_MIN_REVERSE_BOARD = 5

# Task 10: levels and outputs
ALIGHTING_LAST_STRETCHES = 2   # an alighting-sensitive route's last stretches are Rough guess at best
CORRIDOR_SIMPLIFY_M = 3.0      # Douglas-Peucker tolerance for corridor_geometry.geojson
SUPPLY_WIDEN_MIN = 30          # S = 0 fallback: widen the base by this many minutes each side
PLANNER_TABLES = ("canonical_stops", "segment_shapes", "places", "hub_alias", "passings", "service_hours",
                  "service_class", "runtime_factors", "bus_mix", "route_specs")
E_SCALE_CEILING_MULT = 3.0     # R21 modelling assumption: E*_op <= 3 x E_op (Task 12 varies it); the total may then fall short
