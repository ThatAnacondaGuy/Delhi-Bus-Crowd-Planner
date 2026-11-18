import pytest

from src.pipeline.routes import (
    ParsedRoute,
    alias_key,
    is_devi,
    opposite,
    pair_key,
    parse_route,
)


def test_brief_assertions():
    assert parse_route("522BDOWN2") == ParsedRoute("522B", "DOWN", "2")
    assert parse_route("8UP") == ParsedRoute("8", "UP", None)
    assert parse_route("OMS(+)UP").direction == "CW"
    assert parse_route("OMS(-)DOWN").direction == "ACW"
    assert parse_route("YMSPLUS") == ParsedRoute("YMS", "CW", None)
    assert alias_key("ML96UP") == alias_key("ML-96UP")
    assert alias_key("D-005UP") == alias_key("D-0005UP")
    assert is_devi("D-0002STLUP") and is_devi("D-9101UP")
    assert not is_devi("817NUP") and not is_devi("DS-12DOWN")
    assert opposite(parse_route("8UP")).direction == "DOWN"
    assert opposite(parse_route("OMS(+)UP")).direction == "ACW"


def test_ring_variants_and_unicode_minus():
    assert parse_route("OMS(+)BURARI-DHAULAKUAN") == ParsedRoute("OMS", "CW", "BURARI-DHAULAKUAN")
    assert parse_route("OMSEV(-)BH") == ParsedRoute("OMSEV", "ACW", "BH")
    assert parse_route("OMS(−)DOWN") == ParsedRoute("OMS", "ACW", None)
    assert parse_route("TMS(+)UP") == ParsedRoute("TMS", "CW", None)
    assert parse_route("YMS(+)UP") == ParsedRoute("YMS", "CW", None)


def test_non_ring_bases():
    assert parse_route("801STL-DW-2UP").base == "801STL-DW-2"
    assert parse_route("801-IND-IGIUP") == ParsedRoute("801-IND-IGI", "UP", None)
    assert parse_route("D-034UP") == ParsedRoute("D-034", "UP", None)
    assert parse_route("525STLDOWN") == ParsedRoute("525STL", "DOWN", None)


def test_opposite():
    p = parse_route("OMS(+)BURARI-DHAULAKUAN")
    assert opposite(p) == ParsedRoute("OMS", "ACW", "DHAULAKUAN-BURARI")
    assert opposite(parse_route("OMSEV(-)BH")) == ParsedRoute("OMSEV", "CW", "HB")
    assert opposite(parse_route("522BDOWN2")) == ParsedRoute("522B", "UP", "2")


def test_pair_key_same_both_directions():
    for s in ["525STLUP", "OMS(+)UP", "OMSEV(-)BH", "OMS(+)BURARI-DHAULAKUAN", "522BDOWN2"]:
        p = parse_route(s)
        assert pair_key(p) == pair_key(opposite(p))
    assert pair_key(parse_route("525STLUP")) == pair_key(parse_route("525STLDOWN"))
    assert pair_key(parse_route("8UP")) != pair_key(parse_route("9UP"))


@pytest.mark.parametrize("s", [
    "525STLDOWN", "525STLUP", "OMS(-)DOWN", "OMS(+)UP", "OMS(+)BURARI-DHAULAKUAN",
    "801-IND-IGIUP", "D-034UP", "118EXTDOWN", "D-1103UP", "OMSEV(-)BH", "OMSEV(-)HB",
    "990EXTDOWN", "TMS(+)UP", "TMS(-)DOWN", "ML06UP", "801STL-DW-2UP", "567BSTLUP",
    "D-9101UP", "D-2202UP", "628STLDOWN", "YMS(+)UP", "YMSPLUS", "522BDOWN2", "8UP",
    "WEIRD", "", "UP",
])
def test_real_strings_never_crash(s):
    p = parse_route(s)
    assert isinstance(p, ParsedRoute)
    opposite(p)
    pair_key(p)
    alias_key(s)


def test_no_direction():
    assert parse_route("WEIRD").direction is None
