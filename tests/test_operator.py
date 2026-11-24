import pandas as pd

from src.pipeline import operator as op
from src.pipeline.paths import Paths


def _toy(con):
    con.execute("CREATE TABLE canonical_stops AS SELECT * FROM (VALUES (1, 1, 0.0, 'DTC'), (1, 2, 600.0, 'DTC'), "
                "(1, 3, 600.0, 'DTC')) t(route_id, seq, template_s, operator)")
    con.execute("CREATE TABLE runtime_factors(scope VARCHAR, key VARCHAR, hour INT, factor DOUBLE, n_pairs INT)")
    con.execute("INSERT INTO runtime_factors SELECT 'operator', 'DTC', h, 1.0, 100 FROM range(24) t(h)")
    con.execute("""CREATE TABLE stretch_crowding AS SELECT * FROM (VALUES
        (1, '101', 'DTC', 'up', 1, 'A', 'B', 'weekday', 480, 2.0, 35.0, 63.0, 100.0, 80.0, 'crowded', 'many_tickets', ''),
        (1, '101', 'DTC', 'up', 2, 'B', 'C', 'weekday', 480, 2.0, 35.0, 63.0, 100.0, 90.0, 'crowded', 'none', ''))
        t(route_id, short_name, operator, direction, seq, from_name, to_name, day_type, window_start_min, buses,
          seats, rated_total, crush, people_mid, level, evidence, flags)""")


def test_extra_trip_ranking(con, tmp_path):
    _toy(con)
    paths = Paths(*(tmp_path,) * 6)
    n = op.run(con, paths)
    df = pd.read_parquet(tmp_path / "operator_trips.parquet")
    assert n == len(df) >= 1
    top = df.iloc[0]
    assert top["depart_min"] == 480 and top["day_type"] == "weekday"
    assert abs(top["riders_moved_down"] - 160) < 1e-6
    assert abs(top["crowded_rider_min_removed"] - 160 * 10) < 1e-6
    assert top["max_load_section"] == "A to B"
    # departures that reach no crowded stretch rank last with 0 (and the none-evidence stretch never counts)
    assert (df["crowded_rider_min_removed"].iloc[1:] == 0).all()
    assert df["crowded_rider_min_removed"].is_monotonic_decreasing
