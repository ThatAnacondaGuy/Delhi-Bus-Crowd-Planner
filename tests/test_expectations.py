import csv
from pathlib import Path

import pytest

from src.pipeline.expectations import load_expectations

YAML = Path(__file__).parent.parent / "validation" / "expectations.yaml"
STOPS = Path(__file__).parent.parent / "data/raw/gtfs/delhi_buses_static_gtfs_v1/stops.txt"


def test_schema():
    e = load_expectations(YAML)
    assert len(e.corridors) == 10
    grades = [c.grade for c in e.corridors]
    assert grades.count("strong") == 2
    assert grades.count("moderate") == 4
    assert grades.count("weak") == 4
    assert e.corridors[0].peak == ["am"]
    assert e.corridors[1].peak == ["pm"]
    assert e.corridors[1].direction == "eastbound"
    assert e.dtc_bus_km == (400_800, 601_200)
    assert e.load_factor_band == (0.78, 0.89)
    assert e.gps_stoptime_rho_min == 0.3
    assert e.peaks == {"am": [8, 10], "pm": [17, 20]}
    assert all(c.sources for c in e.corridors)


def test_matches_config():
    from src.pipeline import config
    e = load_expectations(YAML)
    assert e.dtc_bus_km == (config.PUBLISHED_DTC_BUS_KM.value * 0.8,
                            config.PUBLISHED_DTC_BUS_KM.value * 1.2)
    assert e.load_factor_band == config.PUBLISHED_LOAD_FACTOR_BAND
    assert e.gps_stoptime_rho_min == config.GPS_STOPTIME_RHO_MIN


@pytest.mark.skipif(not STOPS.exists(), reason="real GTFS absent")
def test_stop_names_exist():
    with open(STOPS, encoding="utf-8-sig", newline="") as f:
        names = {r["stop_name"] for r in csv.DictReader(f)}
    for c in load_expectations(YAML).corridors:
        found = [n for n in c.gtfs_stop_names if n in names]
        assert len(found) >= 3, c.name
        assert found == c.gtfs_stop_names, (c.name, set(c.gtfs_stop_names) - names)
