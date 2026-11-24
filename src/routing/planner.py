"""Frequency-based journey planner over the pipeline's exported files.

Reads only `<processed>/planner/*.parquet` and `<processed>/stretch_crowding.parquet` (never work.duckdb) and
returns up to three options per query: fastest, less crowded, leave later (design 5.9). Buses here ignore
timetables, so the search is a round-based label search where a wait is half the headway (scheduled passings
at the boarding stop and hour, times the GPS share of trips that actually ran).
"""
from __future__ import annotations

import difflib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.pipeline.config import BUS_SPECS, MIN_DAILY_TRIPS, PLACE_RADIUS_M, WINDOWS
from src.pipeline.loads import _level_v, evidence as _evidence, level as _level
from src.pipeline.network import Clock

# ---------------------------------------------------------------- constants

WALK_MPS = 1.2                  # walking speed
ACCESS_M = 400.0                # walk from the typed place to the first stop, and from the last stop to the place
TRANSFER_M = 300.0              # walk between two stops when changing buses
TRANSFER_BUFFER_MIN = 2.0       # slack added to a walk between different stops
WALK_ONLY_M = 500.0             # places this close are one walk, never a bus
MAX_BUSES = 3
MAX_TRIP_MIN = 200.0            # labels later than this after departure are dropped
BETAS = (0.0, 1.0, 3.0)
WEIGHT = {"seats": 0.0, "standing": 0.5, "crowded": 1.5, "no_data": 0.5}
RANK = {"seats": 0, "standing": 1, "crowded": 2}
LATE_OFFSETS = (10, 20, 30, 40)
NIGHT_BEFORE, NIGHT_AFTER = 5 * 60, 23 * 60
NO_DATA_CUTOFF = 0.5            # R28: above this share of riding minutes the headline is no_data
MAX_EXTRA_WORDS = 2             # a partial match may add at most this many words to what was typed
HEADLINE_MIN = 5.0              # a level counts toward the headline from this many minutes
EARLY_WAIT_MIN = 30.0           # a rider may wait this long for a route's first bus
RHO_CLIP = (0.2, 1.5)
GRID = 10                       # minutes per slot of the search's crowding-weight grid
NSLOT = 1440 // GRID
HOURS = 30                      # passings can run past midnight
DAYS = ("weekday", "weekend")
INF = float("inf")


class PlaceNotFound(KeyError):
    """A typed place could not be matched safely; `.suggestions` lists names to try."""

    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.suggestions = list(suggestions or [])

    def __str__(self) -> str:
        return self.message


@dataclass
class _Spec:
    seats: float
    rated_total: float
    crush: float


@dataclass
class _Place:
    id: str
    name: str
    stops: list[int]


# ---------------------------------------------------------------- pure helpers

def compute_bus_fare(dist_km: float, is_ac: bool) -> int:
    """Official DTC / cluster fare by distance band (AC and non-AC)."""
    if is_ac:
        return 10 if dist_km <= 4.0 else 15 if dist_km <= 8.0 else 20 if dist_km <= 12.0 else 25
    return 5 if dist_km <= 4.0 else 10 if dist_km <= 10.0 else 15


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _r(x: float) -> int:
    return int(math.floor(x + 0.5))


def _hhmm(minute: float) -> str:
    m = _r(minute)
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def _parse_depart(depart: str) -> int:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(depart))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("depart must be HH:MM between 00:00 and 23:59")
    return int(m.group(1)) * 60 + int(m.group(2))


def _dist_m(lat1, lon1, lat2, lon2):
    """Equirectangular distance in metres (numpy-friendly; within 0.1% over a few km)."""
    k = 111_320.0
    dy = (np.asarray(lat2) - lat1) * k
    dx = (np.asarray(lon2) - lon1) * k * math.cos(math.radians(lat1))
    return np.hypot(dx, dy)


def headline_of(segs: list[dict], field: str) -> dict:
    """Worst level the rider spends at least HEADLINE_MIN minutes in, plus the longest run at that level.

    `segs` are ride stretches in order with minutes, a level under `field`, evidence and stop names."""
    mins: dict[str, float] = {}
    for s in segs:
        mins[s[field]] = mins.get(s[field], 0.0) + s["minutes"]
    known = {k: v for k, v in mins.items() if k != "no_data"}
    total = sum(mins.values())
    if total > 0 and mins.get("no_data", 0.0) > NO_DATA_CUTOFF * total:   # R28: mostly unknown ride
        lv = "no_data"
        best, run = None, []
        for s in segs + [None]:
            if s is not None and s[field] == lv and (not run or run[-1]["leg"] == s["leg"]):
                run.append(s)
                continue
            if run and (best is None or sum(x["minutes"] for x in run) > sum(x["minutes"] for x in best)):
                best = run
            run = [s] if s is not None and s[field] == lv else []
        return {"level": "no_data", "evidence": "none", "stretch": {"from": best[0]["from_name"],
                "to": best[-1]["to_name"], "minutes": _r(sum(x["minutes"] for x in best))}}
    qual = [k for k in ("crowded", "standing", "seats") if mins.get(k, 0.0) >= HEADLINE_MIN]
    if qual:
        lv = qual[0]
    elif known and sum(known.values()) >= mins.get("no_data", 0.0):
        lv = max(known, key=lambda k: (known[k], RANK[k]))
    else:
        lv = "no_data"
    if lv == "no_data":
        return {"level": "no_data", "evidence": "none", "stretch": None}
    ev = "rough" if any(s["evidence"] != "many_tickets" for s in segs if s[field] == lv) else "many_tickets"
    stretch = None
    if lv in ("crowded", "standing"):
        best, run = None, []
        for s in segs + [None]:
            if s is not None and s[field] == lv and (not run or run[-1]["leg"] == s["leg"]):
                run.append(s)
                continue
            if run and (best is None or sum(x["minutes"] for x in run) > sum(x["minutes"] for x in best)):
                best = run
            run = [s] if s is not None and s[field] == lv else []
        stretch = {"from": best[0]["from_name"], "to": best[-1]["to_name"],
                   "minutes": _r(sum(x["minutes"] for x in best))}
    return {"level": lv, "evidence": ev, "stretch": stretch}


def _rank(level: str) -> int:
    return RANK.get(level, -1)


# ---------------------------------------------------------------- the planner

class Planner:
    """Everything is read once in `load`; `plan` and `search_places` are then pure lookups and searches."""

    # -------------------------------------------------------------- loading

    @classmethod
    def load(cls, paths) -> "Planner":
        self = cls()
        d = Path(paths.planner_dir)

        def rd(name, optional=False):
            f = d / f"{name}.parquet"
            if optional and not f.exists():
                return None
            return pd.read_parquet(f)

        canon = rd("canonical_stops").sort_values(["route_id", "seq"]).reset_index(drop=True)
        self.version = self._data_version(paths)
        places = rd("places")
        self._load_network(canon, rd("runtime_factors"), places)
        self._load_service(rd("passings"), rd("service_class", True), rd("gps_rho_fill", True))
        self._load_specs(rd("route_specs"), rd("bus_mix", True), rd("segment_shapes", True))
        self._load_places(places, rd("hub_alias", True))
        self._load_crowding(Path(paths.processed) / "stretch_crowding.parquet")
        self._load_footpaths()
        return self

    @staticmethod
    def _data_version(paths) -> str:
        try:
            m = json.loads(Path(paths.processed, "manifest.json").read_text())
        except (OSError, ValueError):
            return "unknown"
        return str(m.get("run_id") or m.get("stages", {}).get("loads", {}).get("finished_at") or "unknown")

    def _load_network(self, canon: pd.DataFrame, factors: pd.DataFrame, places: pd.DataFrame) -> None:
        clock = Clock.from_frames(canon[["route_id", "seq", "template_s", "operator"]], factors)
        codes, uniq = pd.factorize(canon["stop_id"].astype(str))
        self.stop_ids = [str(x) for x in uniq]
        self.stop_idx = {s: i for i, s in enumerate(self.stop_ids)}
        first = canon.assign(code=codes).drop_duplicates("code").sort_values("code")
        self.stop_name = first["stop_name"].astype(str).tolist()
        self.stop_lat = first["lat"].to_numpy(dtype=float)
        self.stop_lon = first["lon"].to_numpy(dtype=float)
        extra = places[~places["stop_id"].astype(str).isin(self.stop_idx)]      # walk-only stops: no bus calls there
        for sid, name, lat, lon in zip(extra["stop_id"], extra["name"], extra["lat"], extra["lon"]):
            self.stop_idx[str(sid)] = len(self.stop_ids)
            self.stop_ids.append(str(sid))
            self.stop_name.append(str(name))
        self.stop_lat = np.r_[self.stop_lat, extra["lat"].to_numpy(dtype=float)]
        self.stop_lon = np.r_[self.stop_lon, extra["lon"].to_numpy(dtype=float)]
        self.n_stops = len(self.stop_ids)
        rids = canon["route_id"].to_numpy()
        starts = np.flatnonzero(np.r_[True, rids[1:] != rids[:-1]])
        ends = np.r_[starts[1:], len(rids)]
        pos_in_route = canon.groupby("route_id").cumcount().to_numpy() + 1
        if not (pos_in_route == canon["seq"].to_numpy()).all():
            raise ValueError("canonical_stops seq must run 1..N per route")
        self.n_rows = len(canon)
        self.route_ids, self.route_ri = [], {}
        self.r_short, self.r_operator, self.r_stops, self.r_row0, self.r_ring = [], [], [], [], []
        self.r_segs, self.r_crow, self.r_fac = [], [], []
        self.r_last_name = []
        for ri, (a, b) in enumerate(zip(starts, ends)):
            rid, n = int(rids[a]), int(b - a)
            stops = codes[a:b].tolist()
            ring = n >= 3 and (stops[0] == stops[-1] or float(_dist_m(
                self.stop_lat[stops[0]], self.stop_lon[stops[0]], self.stop_lat[stops[-1]], self.stop_lon[stops[-1]])) <= PLACE_RADIUS_M)
            length = 2 * n - 1 if ring else n
            self.route_ids.append(rid)
            self.route_ri[rid] = ri
            self.r_short.append(str(canon["short_name"].iat[a]))
            self.r_operator.append(str(canon["operator"].iat[a]))
            self.r_stops.append(stops)
            self.r_row0.append(int(a))
            self.r_ring.append(ring)
            self.r_segs.append([0.0] + [clock.template(rid, p + 1) for p in range(1, length)])
            real = [p if p < n else p - (n - 1) for p in range(length)]
            self.r_crow.append([-1] + [int(a) + real[p] - 1 for p in range(1, length)])
            self.r_fac.append(clock.hour_factors(rid))
            self.r_last_name.append(self.stop_name[stops[-1]])
        self.n_routes = len(self.route_ids)
        self.clock = clock

    def _load_service(self, pas: pd.DataFrame, classes, rho) -> None:
        start = pd.Series(self.r_row0, index=self.route_ids)
        pas = pas[pas["route_id"].isin(start.index)]
        rows = (pas["route_id"].map(start).to_numpy() + pas["seq"].to_numpy() - 1).astype(np.int64)
        minute = pas["minute"].to_numpy().astype(np.int64)
        cnt = np.zeros((self.n_rows, HOURS), dtype=np.int16)
        h = np.clip(minute // 60, 0, HOURS - 1)
        flat = rows * HOURS + h
        u, c = np.unique(flat, return_counts=True)
        cnt.reshape(-1)[u] = c
        first = np.full(self.n_rows, 10 ** 6, dtype=np.int64)
        last = np.full(self.n_rows, -1, dtype=np.int64)
        np.minimum.at(first, rows, minute)
        np.maximum.at(last, rows, minute)
        self.cnt, self.first, self.last = cnt.tolist(), first.tolist(), last.tolist()
        # R29: scheduled trips a day = the most passings any stop of the route sees (a short-turn trip skips stops)
        per_row = np.bincount(rows, minlength=self.n_rows)
        self.r_trips = np.maximum.reduceat(per_row, np.asarray(self.r_row0)).tolist()
        cls = dict(zip(classes["route_id"], classes["class"])) if classes is not None else {}
        self.r_class = [cls.get(rid, "regular") for rid in self.route_ids]
        self.stop_routes = {}
        for day in DAYS:
            sr = [[] for _ in range(self.n_stops)]
            for ri, stops in enumerate(self.r_stops):
                if not self._allowed(ri, day):
                    continue
                for pos, s in enumerate(stops):
                    sr[s].append((ri, pos))
            self.stop_routes[day] = sr
        self.rho_eff, self.rho_fb = {}, {}
        for day in DAYS:
            arr = np.full((self.n_routes, 24), np.nan)
            if rho is not None:
                g = rho[rho["day_type"] == day]
                ri = g["route_id"].map(self.route_ri)
                ok = ri.notna().to_numpy()
                arr[ri[ok].astype(int).to_numpy(), g["hour"].to_numpy()[ok].astype(int) % 24] = g["rho"].to_numpy()[ok]
            fb = np.isnan(arr)
            n_ok = (~fb).sum(axis=1)
            mean = np.where(n_ok > 0, np.where(fb, 0.0, arr).sum(axis=1) / np.maximum(n_ok, 1), 1.0)
            eff = np.where(fb, mean[:, None], arr)
            self.rho_eff[day] = np.clip(eff, *RHO_CLIP).tolist()
            self.rho_fb[day] = fb.tolist()
        self.has_rho = rho is not None

    def _load_specs(self, specs: pd.DataFrame, mix, shapes) -> None:
        by = {int(r.route_id): _Spec(float(r.seats), float(r.rated_total), float(r.crush)) for r in specs.itertuples()}
        dflt = BUS_SPECS["12m_ac"]
        self.r_spec = [by.get(rid, _Spec(dflt.seats, dflt.rated_total, dflt.crush)) for rid in self.route_ids]
        self.r_bus_type, self.r_is_ac = ["12m_ac"] * self.n_routes, [True] * self.n_routes
        if mix is not None:
            for r in mix.itertuples():
                ri = self.route_ri.get(int(r.route_id))
                if ri is None:
                    continue
                shares = {"9m_devi": float(r.share_9m), "12m_nonac": float(r.share_12m_nonac), "12m_ac": float(r.share_12m_ac)}
                self.r_bus_type[ri] = max(shares, key=lambda k: (shares[k], k == "12m_ac"))
                self.r_is_ac[ri] = shares["12m_ac"] + shares["9m_devi"] >= 0.5
        self.shape = {}
        if shapes is not None:
            self.shape = {(int(a), int(b)): (c, float(d)) for a, b, c, d in
                          zip(shapes["route_id"], shapes["seq"], shapes["coords"], shapes["length_m"])}

    def _load_places(self, places: pd.DataFrame, alias) -> None:
        self.place_name, self.place_stops = {}, {}
        for pid, name, sid in zip(places["place_id"], places["name"], places["stop_id"]):
            idx = self.stop_idx.get(str(sid))
            if idx is None:
                continue
            self.place_name.setdefault(int(pid), str(name))
            self.place_stops.setdefault(int(pid), []).append(idx)
        self.place_routes = {}
        for pid, stops in self.place_stops.items():
            rs = {ri for s in stops for day in DAYS for ri, _ in self.stop_routes[day][s]}
            self.place_routes[pid] = len(rs)
        self.alias, self.alias_c = {}, {}
        if alias is not None:
            for a, pid in zip(alias["alias"], alias["place_id"]):
                if int(pid) in self.place_stops:
                    self.alias.setdefault(_norm(a), int(pid))
                    self.alias_c.setdefault(_norm(a).replace(" ", ""), int(pid))
        self.name_idx, uniq = [], {}
        for pid, name in self.place_name.items():
            for part in {name, *name.split("/")}:
                n = _norm(part)
                if n:
                    self.name_idx.append((n, n.replace(" ", ""), tuple(n.split()), pid))
                    uniq.setdefault(n, pid)
        self.uniq_names = list(uniq)
        self.hub_names = sorted({self.place_name[p] for p in self.alias.values()},
                                key=lambda n: -max(self.place_routes[p] for p, nm in self.place_name.items() if nm == n))

    def _load_crowding(self, f: Path) -> None:
        cols = ["route_id", "seq", "day_type", "window_start_min", "people_low", "people_mid", "people_high", "flags"]
        sc = pd.read_parquet(f, columns=cols)
        start = pd.Series(self.r_row0, index=self.route_ids)
        self.crowd, self.wgrid = {}, {}
        seats = np.repeat([s.seats for s in self.r_spec], np.diff(self.r_row0 + [self.n_rows]))
        rated = np.repeat([s.rated_total for s in self.r_spec], np.diff(self.r_row0 + [self.n_rows]))
        self.flag_names = [""]
        for day in DAYS:
            step = WINDOWS[day].step_min
            nwin = 1440 // step
            g = sc[sc["day_type"] == day]
            ri = g["route_id"].map(start)
            ok = ri.notna().to_numpy()
            g, row = g[ok], (ri[ok].to_numpy() + g["seq"].to_numpy() - 1).astype(np.int64)
            j = (g["window_start_min"].to_numpy() // step).astype(np.int64)
            arrs = {}
            for k in ("people_low", "people_mid", "people_high"):
                a = np.full((self.n_rows, nwin), np.nan, dtype=np.float32)
                a[row, j] = g[k].to_numpy(dtype=np.float32)
                arrs[k] = a
            fl = np.zeros((self.n_rows, nwin), dtype=np.uint16)
            codes = []
            for s in g["flags"].fillna("").astype(str):
                if s not in self.flag_names:
                    self.flag_names.append(s)
                codes.append(self.flag_names.index(s))
            fl[row, j] = np.asarray(codes, dtype=np.uint16)
            self.crowd[day] = dict(step=step, nwin=nwin, low=arrs["people_low"], mid=arrs["people_mid"],
                                   high=arrs["people_high"], flag=fl)
            self.wgrid[day] = self._weight_grid(self.crowd[day], seats, rated)

    @staticmethod
    def _interp_vec(a: np.ndarray, j0: np.ndarray, j1: np.ndarray, f: np.ndarray):
        """a[:, j0], a[:, j1] and the blend (NaN where a neighbour is unknown and is not the nearer one)."""
        x0, x1 = a[:, j0], a[:, j1]
        ok0, ok1 = ~np.isnan(x0), ~np.isnan(x1)
        both = ok0 & ok1
        with np.errstate(invalid="ignore"):
            blend = (1 - f) * x0 + f * x1
        out = np.where(both, blend, np.where(ok0 & (f < 0.5), x0, np.where(ok1 & (f >= 0.5), x1, np.nan)))
        return out

    def _weight_grid(self, c: dict, seats: np.ndarray, rated: np.ndarray) -> np.ndarray:
        step, nwin = c["step"], c["nwin"]
        t = np.arange(NSLOT) * GRID + GRID / 2
        u = t / step
        j0 = np.minimum(np.floor(u).astype(int), nwin - 1)
        j1 = np.minimum(j0 + 1, nwin - 1)
        f = np.where(j1 == j0, 0.0, u - j0)
        w = np.zeros((self.n_rows, NSLOT), dtype=np.float32)
        for a in range(0, self.n_rows, 8192):
            sl = slice(a, a + 8192)
            hi = self._interp_vec(c["high"][sl], j0, j1, f)
            lv = _level_v(np.nan_to_num(hi, nan=0.0), seats[sl][:, None], rated[sl][:, None])
            wt = np.where(lv == "seats", WEIGHT["seats"], np.where(lv == "standing", WEIGHT["standing"], WEIGHT["crowded"]))
            w[sl] = np.where(np.isnan(hi), WEIGHT["no_data"], wt)
        return w

    def _load_footpaths(self) -> None:
        order = np.argsort(self.stop_lat)
        self._lat_sorted = self.stop_lat[order]
        self._lat_order = order
        self.footpaths = []
        for i in range(self.n_stops):
            near = self._within([i], TRANSFER_M)
            near.pop(i, None)
            self.footpaths.append([(j, m / WALK_MPS / 60 + TRANSFER_BUFFER_MIN, m) for j, m in near.items()])

    def _within(self, stops: list[int], radius: float) -> dict[int, float]:
        out: dict[int, float] = {}
        dlat = radius / 111_320.0
        for s in stops:
            lat, lon = self.stop_lat[s], self.stop_lon[s]
            lo = int(np.searchsorted(self._lat_sorted, lat - dlat))
            hi = int(np.searchsorted(self._lat_sorted, lat + dlat, side="right"))
            cand = self._lat_order[lo:hi]
            dist = _dist_m(lat, lon, self.stop_lat[cand], self.stop_lon[cand])
            for j, m in zip(cand[dist <= radius].tolist(), dist[dist <= radius].tolist()):
                if m < out.get(j, INF):
                    out[j] = m
        return out

    def _allowed(self, ri: int, day: str) -> bool:
        cls = self.r_class[ri]
        return (cls not in ("school", "daf") and (cls != "office_special" or day == "weekday")
                and self.r_trips[ri] >= MIN_DAILY_TRIPS)

    def routes_for_day(self, day: str) -> set[str]:
        """Short names of the routes the planner may use on that day type (school, DAF, weekend specials and
        timetable-only routes with fewer than MIN_DAILY_TRIPS trips a day out)."""
        return {self.r_short[ri] for ri in range(self.n_routes) if self._allowed(ri, day)}

    # -------------------------------------------------------------- places

    def _rank_places(self, q: str) -> list[tuple]:
        """(tier, extra, -routes, name, pid), best first. Tiers: 0 alias, 1 exact name, 2 whole words,
        3 word prefixes, 4 fuzzy."""
        qn = _norm(q)
        if not qn:
            return []
        qc, qt = qn.replace(" ", ""), qn.split()
        best: dict[int, tuple] = {}

        def put(pid, tier, extra):
            if pid not in best or (tier, extra) < best[pid]:
                best[pid] = (tier, extra)

        pid = self.alias.get(qn) or self.alias_c.get(qc)
        if pid is not None:
            put(pid, 0, 0)
        qset = set(qt)
        for nn, nc, toks, pid in self.name_idx:
            if nn == qn or nc == qc:
                put(pid, 1, 0)
            elif len(toks) - len(qt) > MAX_EXTRA_WORDS or len(qn) < 3:
                continue                     # too loose to trust: 'new delhi' is not 'The British School New Delhi'
            elif qset <= set(toks):
                put(pid, 2, len(toks) - len(qt))
            elif all(len(w) >= 3 and any(x.startswith(w) for x in toks) for w in qt):
                put(pid, 3, len(toks) - len(qt))
        if not best:
            for nm in difflib.get_close_matches(qn, self.uniq_names, n=8, cutoff=0.7):
                ratio = difflib.SequenceMatcher(None, qn, nm).ratio()
                for nn, _nc, _t, pid in self.name_idx:
                    if nn == nm:
                        put(pid, 4, int(round((1 - ratio) * 100)))
        rows = [(t, e, -self.place_routes.get(p, 0), self.place_name[p], p) for p, (t, e) in best.items()]
        return sorted(rows)

    def _suggest(self, q: str, rows: list[tuple]) -> list[str]:
        names = []
        for r in rows:
            if r[3] not in names:
                names.append(r[3])
        if len(names) < 3:
            for nm in difflib.get_close_matches(_norm(q), self.uniq_names, n=5, cutoff=0.5):
                for nn, _c, _t, pid in self.name_idx:
                    if nn == nm and self.place_name[pid] not in names:
                        names.append(self.place_name[pid])
                        break
        if not names:
            names = list(self.hub_names)
        return names[:5]

    def _routes_at(self, pid: int, limit: int = 6) -> list[dict]:
        seen, out = set(), []
        for s in self.place_stops[pid]:
            for day in DAYS:
                for ri, pos in self.stop_routes[day][s]:
                    key = self.r_short[ri]
                    if key not in seen and pos < len(self.r_stops[ri]) - 1:
                        seen.add(key)
                        out.append({"route": key, "towards": self.r_last_name[ri]})
        return sorted(out, key=lambda x: x["route"])[:limit]

    def search_places(self, q: str, limit: int = 8) -> list[dict]:
        names = ("alias", "exact", "words", "prefix", "fuzzy")
        out = []
        for tier, _e, _r2, name, pid in self._rank_places(q)[: max(0, int(limit))]:
            st = self.place_stops[pid]
            out.append({"id": f"place:{pid}", "name": name, "lat": float(np.mean(self.stop_lat[st])),
                        "lon": float(np.mean(self.stop_lon[st])), "routes": self._routes_at(pid), "match": names[tier]})
        return out

    def _resolve(self, ref: str, notes: list[str]) -> _Place:
        raw = str(ref or "").strip()
        m = re.fullmatch(r"place:(\d+)", raw, re.I)
        if m:
            pid = int(m.group(1))
            if pid not in self.place_stops:
                raise PlaceNotFound(f"Unknown place {raw}", self.hub_names[:5])
            return _Place(f"place:{pid}", self.place_name[pid], self.place_stops[pid])
        m = re.fullmatch(r"stop:(.+)", raw, re.I)
        if m:
            idx = self.stop_idx.get(m.group(1).strip())
            if idx is None:
                raise PlaceNotFound(f"Unknown stop {raw}", self.hub_names[:5])
            return _Place(f"stop:{self.stop_ids[idx]}", self.stop_name[idx], [idx])
        rows = self._rank_places(raw)
        if not rows:
            raise PlaceNotFound(f"No place matches '{raw}'", self._suggest(raw, rows))
        tier = rows[0][0]
        same = [r for r in rows if r[0] == tier]
        if tier in (0, 1):
            pick = same[0]                                   # sorted: the one served by most routes comes first
            if len({r[4] for r in same}) > 1:
                notes.append(f"Several places are called '{pick[3]}'; using the one with most bus routes.")
        else:
            gap_ok = len(same) == 1 or (same[0][1] < same[1][1])
            if tier == 4:
                gap_ok = gap_ok and same[0][1] <= 14 and (len(same) == 1 or same[1][1] - same[0][1] >= 4)
            if not gap_ok:
                raise PlaceNotFound(f"'{raw}' matches several places", self._suggest(raw, same))
            pick = same[0]
        if _norm(pick[3]) != _norm(raw):
            notes.append(f"Using '{pick[3]}' for '{raw}'.")
        pid = pick[4]
        return _Place(f"place:{pid}", self.place_name[pid], self.place_stops[pid])

    # -------------------------------------------------------------- crowding lookup

    def crowd_at(self, route_id: int, from_seq: int, t_min: float, day: str):
        """(low, mid, high, flag_set) for the stretch leaving `from_seq`, interpolated linearly between the two
        neighbouring window centres; None when unknown (a missing neighbour is used only if it is the nearer one)."""
        ri = self.route_ri[int(route_id)]
        return self._crowd_row(self.r_row0[ri] + from_seq - 1, t_min, day)

    def _crowd_row(self, row: int, t_min: float, day: str):
        c = self.crowd[day]
        step, nwin = c["step"], c["nwin"]
        u = (t_min % 1440) / step
        j0 = min(int(u), nwin - 1)
        j1 = min(j0 + 1, nwin - 1)
        f = 0.0 if j1 == j0 else u - j0
        ok0, ok1 = not np.isnan(c["high"][row, j0]), not np.isnan(c["high"][row, j1])
        if ok0 and ok1:
            use = ((j0, 1 - f), (j1, f))
        elif ok0 and f < 0.5:
            use = ((j0, 1.0),)
        elif ok1 and f >= 0.5:
            use = ((j1, 1.0),)
        else:
            return None
        vals = [sum(float(c[k][row, j]) * wt for j, wt in use) for k in ("low", "mid", "high")]
        flags = set()
        for j, _ in use:
            flags.update(x for x in self.flag_names[int(c["flag"][row, j])].split(",") if x)
        return vals[0], vals[1], vals[2], flags

    # -------------------------------------------------------------- waits

    def _board(self, ri: int, pos: int, t: float, day: str):
        """(boarding minute, wait minutes, rho_was_fallback) or None when the route does not run at t here."""
        row = self.r_row0[ri] + pos
        if t > self.last[row]:
            return None
        first = self.first[row]
        if t < first:
            if first - t <= EARLY_WAIT_MIN:
                return first, first - t, False
            if t + 1440 <= self.last[row]:               # after-midnight passings (minute >= 1440) serve 00:00-04:59
                got = self._board(ri, pos, t + 1440, day)
                return None if got is None else (got[0] - 1440, got[1], got[2])
            return None
        h = int(t // 60)
        cnt = self.cnt[row]
        n = cnt[h] if h < HOURS else 0
        if n == 0:
            n = max(cnt[h - 1] if 0 < h <= HOURS else 0, cnt[h + 1] if 0 <= h + 1 < HOURS else 0, 1)
        rho = self.rho_eff[day][ri][h % 24]
        wait = 30.0 / (n * rho)
        return _r(t + wait), wait, self.rho_fb[day][ri][h % 24]

    # -------------------------------------------------------------- search

    def _access(self, place: _Place) -> dict[int, float]:
        near = self._within(place.stops, ACCESS_M)
        for s in place.stops:
            near[s] = 0.0
        return near

    def _raptor(self, org: dict[int, float], dst: dict[int, float], dep: float, day: str, beta: float):
        """One label search with in-vehicle minutes weighted by (1 + beta * w(level)). Returns one
        leg list per round that improved the best known cost at the destination."""
        K, n = MAX_BUSES, self.n_stops
        best = [INF] * n
        cost = [[INF] * n for _ in range(K + 1)]
        tm = [[INF] * n for _ in range(K + 1)]
        par = [dict() for _ in range(K + 1)]
        egress = {s: m / WALK_MPS / 60 for s, m in dst.items()}
        tlim = dep + MAX_TRIP_MIN
        marked = []
        for s, m in org.items():
            w = m / WALK_MPS / 60
            cost[0][s], tm[0][s], best[s] = w, dep + w, w
            par[0][s] = ("org", m)
            marked.append(s)
        best_dest = INF
        sr, fps, grid = self.stop_routes[day], self.footpaths, self.wgrid[day]
        weigh = grid.item
        found = []
        for k in range(1, K + 1):
            rts: dict[int, int] = {}
            for p in marked:
                for ri, pos in sr[p]:
                    cur = rts.get(ri)
                    if cur is None or pos < cur:
                        rts[ri] = pos
            pc, pt, ck, tk, pk = cost[k - 1], tm[k - 1], cost[k], tm[k], par[k]
            newm: set[int] = set()
            for ri, start in rts.items():
                stops, segs, crow, fac = self.r_stops[ri], self.r_segs[ri], self.r_crow[ri], self.r_fac[ri]
                nr = len(stops)
                end = min(start + nr - 1, len(segs) - 1) if self.r_ring[ri] else nr - 1
                boarded = False
                cc = ct = 0.0
                bpos = bstop = 0
                bt = 0
                for p in range(start, end + 1):
                    s = stops[p if p < nr else p - (nr - 1)]
                    if boarded:
                        m = segs[p] * fac[int(ct // 60) % 24] / 60.0
                        if beta:
                            cc += m * (1.0 + beta * weigh(crow[p], int((ct + m * 0.5) // GRID) % NSLOT))
                        else:
                            cc += m
                        ct += m
                        if cc < best[s] and cc < best_dest and ct < tlim:
                            ck[s], tk[s], best[s] = cc, ct, cc
                            pk[s] = ("bus", ri, bpos, p, bstop, bt)
                            newm.add(s)
                            e = egress.get(s)
                            if e is not None and cc + e < best_dest:
                                best_dest = cc + e
                    if p < nr:
                        c0 = pc[s]
                        if c0 < best_dest and pt[s] < tlim:
                            got = self._board(ri, p, pt[s], day)
                            if got is not None:
                                cand = c0 + got[1]
                                if not boarded or cand < cc:
                                    boarded, bpos, bstop, bt = True, p, s, got[0]
                                    cc, ct = cand, float(got[0])
            fnew: set[int] = set()
            for p in newm:
                c, t = ck[p], tk[p]
                for v, wm, dm in fps[p]:
                    cc = c + wm
                    if cc < best[v] and cc < best_dest and t + wm < tlim:
                        ck[v], tk[v], best[v] = cc, t + wm, cc
                        pk[v] = ("fp", p, dm)
                        fnew.add(v)
                        e = egress.get(v)
                        if e is not None and cc + e < best_dest:
                            best_dest = cc + e
            marked = list(newm | fnew)
            pick = min(((ck[s] + e, s) for s, e in egress.items() if ck[s] < INF), default=None)
            if pick is not None:
                found.append(self._legs_from(par, k, pick[1], dst[pick[1]]))
            if not marked:
                break
        return found

    def _legs_from(self, par, k: int, s: int, egress_m: float) -> list[tuple]:
        legs: list[tuple] = []
        if egress_m > 0:
            legs.append(("walk", egress_m, False))
        guard = 0
        while guard < 10_000:
            guard += 1
            p = par[k][s]
            if p[0] == "org":
                if p[1] > 0:
                    legs.append(("walk", p[1], False))
                break
            if p[0] == "fp":
                legs.append(("walk", p[2], True))
                s = p[1]
                continue
            _, ri, bpos, apos, bstop, _bt = p
            legs.append(("bus", ri, bpos, apos, bstop, s))
            s, k = bstop, k - 1
        return legs[::-1]

    # -------------------------------------------------------------- evaluation

    def _run(self, legs: list[tuple], dep: float, day: str):
        """Walk the legs forward from `dep`; None if a bus no longer runs. Returns the trip with its stretches."""
        t = float(dep)
        out_legs, segs, fare = [], [], 0
        fallback = []
        for leg in legs:
            if leg[0] == "walk":
                minutes = leg[1] / WALK_MPS / 60 + (TRANSFER_BUFFER_MIN if leg[2] else 0.0)
                out_legs.append({"mode": "walk", "meters": _r(leg[1]), "minutes": max(1, _r(minutes))})
                t += minutes
                continue
            _, ri, bpos, apos, bstop, astop = leg
            got = self._board(ri, bpos, t, day)
            if got is None:
                return None
            bt, _wait, fb = got
            if fb:
                fallback.append((self.r_short[ri], int(bt // 60) % 24))
            t = float(bt)
            stops, fac, spec = self.r_stops[ri], self.r_fac[ri], self.r_spec[ri]
            nr = len(stops)
            rid = self.route_ids[ri]
            lseg, dist = [], 0.0
            for p in range(bpos + 1, apos + 1):
                m = self.r_segs[ri][p] * fac[int(t // 60) % 24] / 60.0
                a_stop = stops[(p - 1) if (p - 1) < nr else (p - 1) - (nr - 1)]
                b_stop = stops[p if p < nr else p - (nr - 1)]
                real = p if p < nr else p - (nr - 1)
                key = (rid, real + 1)
                shape = self.shape.get(key)
                dist += shape[1] if shape else float(_dist_m(self.stop_lat[a_stop], self.stop_lon[a_stop],
                                                             self.stop_lat[b_stop], self.stop_lon[b_stop]))
                got_c = self._crowd_row(self.r_crow[ri][p], t + m / 2, day)
                rec = dict(from_stop_id=self.stop_ids[a_stop], to_stop_id=self.stop_ids[b_stop], minutes=m,
                           from_name=self.stop_name[a_stop], to_name=self.stop_name[b_stop], key=key,
                           ends=(a_stop, b_stop), seats=int(round(spec.seats)), rated_total=int(round(spec.rated_total)),
                           leg=len(out_legs))
                if got_c is None:
                    rec.update(people=None, lvl="no_data", lvl_lo="no_data", lvl_hi="no_data", evidence="none", flags=[])
                else:
                    low, mid, high, flags = got_c
                    fl = sorted(flags)
                    rec.update(people=[_r(low), _r(mid), _r(high)], lvl=_level(mid, spec), lvl_lo=_level(low, spec),
                               lvl_hi=_level(high, spec), evidence=_evidence(low, high, spec, fl, False), flags=fl)
                lseg.append(rec)
                segs.append(rec)
                t += m
            fare += compute_bus_fare(dist / 1000.0, self.r_is_ac[ri])
            out_legs.append({"mode": "bus", "route": self.r_short[ri], "bus_type": self.r_bus_type[ri],
                             "from": {"stop_id": self.stop_ids[bstop], "name": self.stop_name[bstop]},
                             "to": {"stop_id": self.stop_ids[astop], "name": self.stop_name[astop]},
                             "depart": _hhmm(bt), "arrive": _hhmm(t), "segments": lseg, "_depart_min": bt})
        buses = [l for l in legs if l[0] == "bus"]
        total = sum(s["minutes"] for s in segs)
        nod = sum(s["minutes"] for s in segs if s["lvl"] == "no_data")
        hi = [s["lvl_hi"] for s in segs]

        def tally(pess=False):
            c = sum(s["minutes"] for s, h in zip(segs, hi) if h == "crowded" or (pess and "low_app_use" in s["flags"]))
            st = sum(s["minutes"] for s, h in zip(segs, hi) if h == "standing" and not (pess and "low_app_use" in s["flags"]))
            return (c, st)

        return {"legs": out_legs, "segs": segs, "arrive": t, "arrive_r": _r(t), "dep": dep, "fare": fare,
                "changes": max(0, len(buses) - 1), "no_data_share": (nod / total) if total else 1.0,
                "tally": tally(), "tally_pess": tally(True), "spec": legs, "fallback": fallback,
                "sig": tuple((l[1], l[4], l[5]) for l in buses),
                "uncertain": any(l["_depart_min"] < NIGHT_BEFORE or l["_depart_min"] >= NIGHT_AFTER
                                 for l in out_legs if l["mode"] == "bus")}

    # -------------------------------------------------------------- plan

    def plan(self, from_ref: str, to_ref: str, depart: str, day: str) -> dict:
        if day not in DAYS:
            raise ValueError("day must be weekday or weekend")
        dep = _parse_depart(depart)
        notes: list[str] = []
        o, d = self._resolve(from_ref, notes), self._resolve(to_ref, notes)
        query = {"from": {"id": o.id, "name": o.name}, "to": {"id": d.id, "name": d.name},
                 "depart": _hhmm(dep), "day": day}
        res = {"data_version": self.version, "query": query, "options": [], "notes": notes}
        if o.id == d.id:
            raise ValueError("Pick two different places.")
        gap = min(self._pair_m(o.stops, d.stops), WALK_ONLY_M + 1) if o.stops and d.stops else INF
        if set(o.stops) & set(d.stops) or gap <= WALK_ONLY_M:
            res["options"] = [self._walk_option(dep, gap)]
            notes.append("These places are within walking distance; no bus needed.")
            return res
        org, dst = self._access(o), self._access(d)
        trips: dict[tuple, dict] = {}
        for beta in BETAS:
            for legs in self._raptor(org, dst, dep, day, beta):
                trip = self._run(legs, dep, day)
                if trip is not None and trip["sig"] not in trips:
                    trips[trip["sig"]] = trip
        if not trips:
            notes.append(self._no_service_note(org, dep, o.name))
            return res
        cands = list(trips.values())
        fastest = min(cands, key=lambda t: (t["arrive"], t["changes"], t["tally"]))
        fast_min = fastest["arrive"] - dep
        chosen: list[tuple[dict, list[str]]] = []
        less = self._less_crowded(fastest, cands, dep)
        if less is fastest:
            chosen.append((fastest, ["fastest", "less_crowded"]))
        else:
            chosen.append((fastest, ["fastest"]))
            if less is not None:
                chosen.append((less, ["less_crowded"]))
        later = self._leave_later(fastest, dep, day)
        if later is not None:
            chosen.append((later, ["leave_later"]))
        res["options"] = [self._render(t, roles, fastest, t["dep"], fast_min) for t, roles in chosen]
        seen = set()
        for t, _roles in chosen:
            for short, hour in t["fallback"]:
                if (short, hour) not in seen:
                    seen.add((short, hour))
                    notes.append(f"No live frequency data for route {short} at {hour:02d}:00; "
                                 "the wait is estimated from the timetable.")
        if not self.has_rho and not any("frequency" in n for n in notes):
            notes.append("Waits are estimated from the timetable; live frequency data is not loaded.")
        return res

    def _pair_m(self, a: list[int], b: list[int]) -> float:
        best = INF
        for s in a:
            best = min(best, float(_dist_m(self.stop_lat[s], self.stop_lon[s], self.stop_lat[b], self.stop_lon[b]).min()))
        return best

    def _no_service_note(self, org: dict[int, float], dep: float, name: str) -> str:
        rows = [self.r_row0[ri] + pos for s in org for day in DAYS for ri, pos in self.stop_routes[day][s]]
        firsts = [self.first[r] for r in rows if self.last[r] >= 0]
        lasts = [self.last[r] for r in rows if self.last[r] >= 0]
        if not firsts or (dep > max(lasts) and dep + 1440 > max(lasts)) or \
                (dep < min(firsts) - EARLY_WAIT_MIN and dep + 1440 > max(lasts)):
            span = f" Buses near {name} run about {_hhmm(min(firsts))} to {_hhmm(max(lasts))}." if firsts else ""
            return f"No scheduled service at {_hhmm(dep)} near {name}.{span}"
        return f"No bus journey with up to {MAX_BUSES} buses was found at {_hhmm(dep)}; try another time."

    def _walk_option(self, dep: float, meters: float) -> dict:
        minutes = _r(meters / WALK_MPS / 60)
        return {"roles": ["fastest"], "depart": _hhmm(dep), "arrive": _hhmm(dep + minutes), "minutes": minutes,
                "changes": 0, "fare_inr": 0, "headline": None, "tradeoff": "Walk", "timetable_uncertain": False,
                "legs": [{"mode": "walk", "meters": _r(meters), "minutes": minutes}]}

    # -------------------------------------------------------------- roles

    def _less_crowded(self, fastest: dict, cands: list[dict], dep: float):
        """The trip with the fewest crowded, then standing, minutes (upper end) within the time budget; None when
        no eligible alternative exists. Returns `fastest` itself when it wins against a real alternative."""
        if fastest["no_data_share"] > NO_DATA_CUTOFF:
            return None                      # nothing to compare an alternative against
        budget = max(fastest["arrive"] - dep + 15.0, (fastest["arrive"] - dep) * 1.3)
        alts = []
        for t in cands:
            if t is fastest or t["arrive"] - dep > budget or t["no_data_share"] > NO_DATA_CUTOFF:
                continue
            if t["tally"] < fastest["tally"] and t["tally_pess"] >= fastest["tally"] and \
                    any("low_app_use" in s["flags"] for s in t["segs"]):
                continue                     # its advantage rests on legs flagged low app use
            alts.append(t)
        if not alts:
            return None
        pool = alts + [fastest]
        return min(pool, key=lambda t: (t["tally"], t["arrive"], t is not fastest))

    def _leave_later(self, fastest: dict, dep: float, day: str):
        base = self._headline_of_trip(fastest)["level"]
        if base not in RANK or base == "seats":
            return None
        for off in LATE_OFFSETS:
            if dep + off >= 1440:
                break
            t = self._run(fastest["spec"], dep + off, day)
            if t is None or t["no_data_share"] > NO_DATA_CUTOFF:
                continue
            fast_min = fastest["arrive"] - dep
            if t["arrive"] - t["dep"] > fast_min + max(10.0, 0.25 * fast_min):
                continue                     # waiting for a rare bus can make it hours slower; not a useful offer
            lo, mid, hi = (headline_of(t["segs"], f)["level"] for f in ("lvl_lo", "lvl", "lvl_hi"))
            if lo == mid == hi and _rank(mid) >= 0 and _rank(mid) < RANK[base]:
                return t
        return None

    @staticmethod
    def _headline_of_trip(t: dict) -> dict:
        return headline_of(t["segs"], "lvl")

    def _render(self, t: dict, roles: list[str], fastest: dict, dep: float, fast_min: float) -> dict:
        legs = []
        for leg in t["legs"]:
            if leg["mode"] == "walk":
                legs.append(dict(leg))
                continue
            segs = []
            for s in leg["segments"]:
                shape = self.shape.get(s["key"])
                a, b = s["ends"]
                coords = json.loads(shape[0]) if shape else [[float(self.stop_lat[a]), float(self.stop_lon[a])],
                                                             [float(self.stop_lat[b]), float(self.stop_lon[b])]]
                segs.append({"from_stop_id": s["from_stop_id"], "to_stop_id": s["to_stop_id"],
                             "minutes": round(s["minutes"], 1), "level": s["lvl"], "evidence": s["evidence"],
                             "people": s["people"], "seats": s["seats"], "rated_total": s["rated_total"],
                             "flags": s["flags"], "coords": coords})
            legs.append({k: v for k, v in leg.items() if k not in ("segments", "_depart_min")} | {"segments": segs})
        head = self._headline_of_trip(t)
        minutes = t["arrive_r"] - _r(dep)
        fast_minutes = fastest["arrive_r"] - _r(fastest["dep"])
        return {"roles": roles, "depart": _hhmm(dep), "arrive": _hhmm(t["arrive"]), "minutes": minutes,
                "changes": t["changes"], "fare_inr": t["fare"], "headline": head,
                "tradeoff": self._tradeoff(roles, t, fastest, minutes, fast_minutes, head),
                "timetable_uncertain": bool(t["uncertain"] or dep < NIGHT_BEFORE or dep >= NIGHT_AFTER),
                "legs": legs}

    @staticmethod
    def _tradeoff(roles, t, fastest, minutes, fast_minutes, head) -> str:
        if roles == ["fastest"]:
            return "Fastest"
        if roles == ["fastest", "less_crowded"]:
            return "Fastest and least crowded"
        if roles == ["leave_later"]:
            word = {"seats": "seats", "standing": "standing", "crowded": "crowded"}[head["level"]]
            return f"Leave {_hhmm(t['dep'])} · usually {word} · arrive {_hhmm(t['arrive'])}"
        extra = minutes - fast_minutes
        lead = f"+{extra} min" if extra > 0 else "Same time"
        c, s = t["tally"]
        fc, fs = fastest["tally"]
        if fc - c >= 1:
            tail = "no crowded stretch" if c == 0 else f"{_r(fc - c)} fewer crowded min"
        elif fc == c and fs - s >= 1:
            tail = f"{_r(fs - s)} fewer standing min"
        else:
            tail = "similar crowding"
        return f"{lead}, {tail}"
