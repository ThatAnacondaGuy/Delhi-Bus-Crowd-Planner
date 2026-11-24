"""Golden journeys: the five demo trips on the real data, so a code change that moves a headline shows up here.

The expected roles and levels were recorded from the planner on the real processed data (Task 21b). They are the exact
answers the live demo shows. If the data or the model is changed on purpose, re-record them with the helper at the bottom
of this file and say why in the commit. The tests skip cleanly when the real data is not on this machine.
"""
import pytest

from src.pipeline.paths import Paths
from src.routing.planner import Planner

PATHS = Paths.default()
NEEDED = [PATHS.processed / "stretch_crowding.parquet", PATHS.planner_dir / "canonical_stops.parquet",
          PATHS.planner_dir / "places.parquet"]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in NEEDED), reason="real processed data is not present")

# (from, to, depart, day) -> the resolved place names, then one (roles, headline level, evidence) per option, in order.
GOLDEN = {
    ("ISBT Anand Vihar", "Connaught Place", "18:00", "weekday"): (
        ("ISBT Anand Vihar", "Shivaji Stadium Terminal"),
        [(["fastest"], "standing", "rough"), (["less_crowded"], "seats", "rough")]),
    ("Connaught Place", "ISBT Anand Vihar", "18:00", "weekday"): (
        ("Shivaji Stadium Terminal", "ISBT Anand Vihar"),
        [(["fastest", "less_crowded"], "crowded", "rough"), (["leave_later"], "standing", "rough")]),
    ("Ambedkar Nagar", "ITO", "09:00", "weekday"): (
        ("Ambedkar Nagar Terminal", "ITO Ring Road"),
        [(["fastest"], "standing", "rough")]),
    ("Mandi House", "Laxmi Nagar", "18:00", "weekday"): (
        ("Mandi House", "Laxmi Nagar X-ing"),
        [(["fastest"], "crowded", "rough"), (["leave_later"], "standing", "many_tickets")]),
    ("Ambedkar Nagar", "AIIMS", "09:00", "weekday"): (
        ("Ambedkar Nagar Terminal", "AIIMS"),
        [(["fastest"], "crowded", "rough"), (["less_crowded"], "standing", "rough")]),
}


@pytest.fixture(scope="module")
def planner():
    return Planner.load(PATHS)


def observed(plan):
    return [(o["roles"], o["headline"]["level"], o["headline"]["evidence"]) for o in plan["options"]]


@pytest.mark.parametrize("journey", list(GOLDEN), ids=lambda j: f"{j[0]}->{j[1]}@{j[3]}-{j[2]}")
def test_demo_journey_keeps_its_roles_and_headline_levels(planner, journey):
    places, options = GOLDEN[journey]
    plan = planner.plan(*journey)
    assert (plan["query"]["from"]["name"], plan["query"]["to"]["name"]) == places
    assert observed(plan) == options


def test_every_demo_journey_has_a_fastest_option_and_no_blank_headline(planner):
    for journey in GOLDEN:
        options = planner.plan(*journey)["options"]
        assert any("fastest" in o["roles"] for o in options)
        assert all(o["headline"]["level"] in {"seats", "standing", "crowded", "no_data"} for o in options)
