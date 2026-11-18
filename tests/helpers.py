import csv
from pathlib import Path

TICKET_COLUMNS = [
    "passenger_count", "amount", "vehicle_number", "ticket_type_id",
    "end_stop_name", "route", "start_stop_name", "created_at", "is_ac",
]
_DEFAULTS = {
    "passenger_count": 1,
    "amount": 9.0,
    "vehicle_number": "NULL",
    "ticket_type_id": 1,
    "is_ac": True,
}


def make_tickets(tmp_path, rows: list[dict]) -> Path:
    """Write a tickets CSV with the real file's header order; return its path."""
    path = Path(tmp_path) / "tickets.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(TICKET_COLUMNS)
        for r in rows:
            merged = {**_DEFAULTS, **r}
            w.writerow([merged.get(c, "") for c in TICKET_COLUMNS])
    return path
