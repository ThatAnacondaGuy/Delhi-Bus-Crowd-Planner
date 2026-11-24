"""Pure-Python helpers for ticket route strings (no DB)."""
from __future__ import annotations

import re
from typing import NamedTuple

from src.pipeline.config import DEVI_ROUTE_RE

_RING_RE = re.compile(r"\(\+\)|\(-\)|PLUS|MINUS")
_DIR_RE = re.compile(r"^(.+?)(UP|DOWN)(\d)?$")
_OPP_DIR = {"UP": "DOWN", "DOWN": "UP", "CW": "ACW", "ACW": "CW"}


class ParsedRoute(NamedTuple):
    base: str
    direction: str | None
    variant: str | None


def _norm(raw: str) -> str:
    return (raw or "").strip().upper().replace("−", "-").replace(" ", "")


def parse_route(raw: str) -> ParsedRoute:
    s = _norm(raw)
    m = _RING_RE.search(s)
    if m and m.start() > 0:
        direction = "CW" if m.group() in ("(+)", "PLUS") else "ACW"
        rest = s[m.end():].strip("-")
        if rest in ("UP", "DOWN", ""):
            rest = None
        return ParsedRoute(s[: m.start()], direction, rest)
    m = _DIR_RE.match(s)
    if m:
        return ParsedRoute(m.group(1), m.group(2), m.group(3))
    return ParsedRoute(s, None, None)


def alias_key(raw: str) -> str:
    s = _norm(raw)
    s = re.sub(r"\(\+\)|PLUS", "\x01", s)
    s = re.sub(r"\(-\)|MINUS", "\x02", s)
    s = re.sub(r"[^A-Z0-9\x01\x02]", "", s)
    s = re.sub(r"(?<!\d)0+(?=\d)", "", s)
    s = re.sub(r"(UP|DOWN)\d$", r"\1", s)
    return s.replace("\x01", "(+)").replace("\x02", "(-)")


def is_devi(short_name: str) -> bool:
    return re.match(DEVI_ROUTE_RE, _norm(short_name)) is not None


def _flip_variant(v: str | None) -> str | None:
    if not v:
        return v
    if "-" in v:
        parts = v.split("-")
        return "-".join(reversed(parts))
    if len(v) == 2 and v.isalpha():
        return v[::-1]
    return v


def opposite(p: ParsedRoute) -> ParsedRoute:
    return ParsedRoute(p.base, _OPP_DIR.get(p.direction, p.direction), _flip_variant(p.variant))


def pair_key(p: ParsedRoute) -> str:
    ring = "R" if p.direction in ("CW", "ACW") else "L"
    v = p.variant or ""
    f = _flip_variant(p.variant) or ""
    return f"{alias_key(p.base)}|{ring}|{min(v, f)}"
