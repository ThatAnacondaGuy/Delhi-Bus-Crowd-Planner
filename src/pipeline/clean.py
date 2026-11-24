"""Stage 1: clean the October ticket CSV into Delhi-time tables."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import EXCLUDED_DATES, EXCLUDED_WINDOWS, TZ
from zoneinfo import ZoneInfo

_IST = ZoneInfo(TZ)


@dataclass
class CleanStats:
    rows: int
    dates: int
    null_share: float


def excluded(ts: datetime) -> bool:
    """True when ts (naive = IST) falls on an excluded date or in a half-open [start, end) window."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_IST)
    if ts.astimezone(_IST).strftime("%Y-%m-%d") in EXCLUDED_DATES:
        return True
    return any(start <= ts < end for start, end in EXCLUDED_WINDOWS)


def busiest_routes(con, paths, n: int) -> list[str]:
    rows = con.execute(
        "SELECT route FROM read_csv(?, header=true, all_varchar=true) "
        "GROUP BY route ORDER BY count(*) DESC, route LIMIT ?", [str(paths.tickets_csv), n]).fetchall()
    return [r[0] for r in rows]


def run(con, paths, sample_routes: list[str] | None = None) -> CleanStats:
    src = ("read_csv(?, header=true, types={'passenger_count':'INTEGER','amount':'DOUBLE',"
           "'vehicle_number':'VARCHAR','ticket_type_id':'INTEGER','end_stop_name':'VARCHAR',"
           "'route':'VARCHAR','start_stop_name':'VARCHAR','created_at':'TIMESTAMPTZ','is_ac':'BOOLEAN'})")
    where, params = "", [str(paths.tickets_csv)]
    if sample_routes is not None:
        where = "WHERE route IN (SELECT unnest(?))"
        params.append(list(sample_routes))
    con.execute("DROP TABLE IF EXISTS tickets_clean")
    con.execute(f"""
        CREATE TABLE tickets_clean AS
        WITH raw AS (SELECT * FROM {src} {where}),
        v AS (SELECT *, row_number() OVER () AS ticket_id,
                     CASE WHEN upper(trim(vehicle_number)) IN ('NULL', '') THEN NULL
                          ELSE trim(vehicle_number) END AS vehicle FROM raw)
        SELECT ticket_id::BIGINT AS ticket_id, route AS route_raw, start_stop_name AS start_raw,
               end_stop_name AS end_raw, passenger_count::INTEGER AS pax, amount::DOUBLE AS amount,
               vehicle, is_ac, created_at AS ts, CAST(timezone('Asia/Kolkata', created_at) AS DATE) AS date,
               CASE WHEN isodow(CAST(timezone('Asia/Kolkata', created_at) AS DATE)) >= 6 THEN 'weekend' ELSE 'weekday' END AS day_type,
               CASE WHEN vehicle IS NULL THEN 'null' ELSE 'linked' END AS channel
        FROM v""", params)
    con.execute("DROP TABLE IF EXISTS clean_days")
    con.execute("""
        CREATE TABLE clean_days AS
        SELECT d::DATE AS date,
               CASE WHEN isodow(d::DATE) >= 6 THEN 'weekend' ELSE 'weekday' END AS day_type,
               strftime(d::DATE, '%Y-%m-%d') IN (SELECT unnest(?)) AS is_excluded_date
        FROM (SELECT unnest(generate_series(min(date), max(date), INTERVAL 1 DAY)) AS d
              FROM tickets_clean) t""", [list(EXCLUDED_DATES)])
    con.execute("DROP TABLE IF EXISTS dq_daily")
    con.execute("""
        CREATE TABLE dq_daily AS
        SELECT date, count(*)::BIGINT AS tickets, sum(pax)::BIGINT AS pax,
               avg((channel = 'null')::INT) AS null_share,
               sum(CASE WHEN is_ac THEN pax ELSE 0 END)::BIGINT AS ac_pax,
               sum(CASE WHEN is_ac THEN 0 ELSE pax END)::BIGINT AS nonac_pax
        FROM tickets_clean GROUP BY date ORDER BY date""")
    rows, nulls = con.execute(
        "SELECT count(*), coalesce(avg((channel='null')::INT), 0) FROM tickets_clean").fetchone()
    dates = con.execute("SELECT count(*) FROM clean_days").fetchone()[0]
    return CleanStats(rows=rows, dates=dates, null_share=nulls)


def clean_day_count(con, day_type: str, minute_of_day: int) -> int:
    """Clean dates of day_type whose instant at minute_of_day is not excluded."""
    rows = con.execute("SELECT date FROM clean_days WHERE day_type = ? AND NOT is_excluded_date",
                       [day_type]).fetchall()
    return sum(1 for (d,) in rows
               if not excluded(datetime(d.year, d.month, d.day, tzinfo=_IST) + timedelta(minutes=minute_of_day)))
