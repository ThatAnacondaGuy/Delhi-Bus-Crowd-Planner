"""API v1 for the crowding-aware bus journey planner.

Serves the planner and the crowding outputs. Reads the pipeline outputs in DATA_DIR (default data/processed).
No ticket-level or vehicle-level data leaves this service: every response is an aggregate by route, stretch,
corridor or scheduled trip.
"""
from __future__ import annotations

import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from src.pipeline.config import WINDOWS
from src.pipeline.db import connect
from src.pipeline.paths import Paths
from src.routing.planner import PlaceNotFound, Planner

FRONTEND = Paths.default().repo / "frontend"
CREDIT = "Data: Transport Stack / IIIT Delhi; ticketing from ONDC e-ticketing."
HHMM = r"^([01]?\d|2[0-3]):[0-5]\d$"
Day = Literal["weekday", "weekend"]
OPERATOR_COLUMNS = ["route_id", "short_name", "operator", "direction", "day_type", "depart", "depart_min",
                    "crowded_rider_min_removed", "riders_moved_down", "max_load_section", "peak_load_factor",
                    "evidence_share", "flags"]


class PlanQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: str = Field(alias="from", min_length=1, max_length=120)
    to: str = Field(min_length=1, max_length=120)
    depart: str = Field(pattern=HHMM)
    day: Day


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=1, max_length=120)
    limit: int = Field(8, ge=1, le=20)


class CrowdingQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: int
    day: Day
    window: str = Field(pattern=HHMM)


class StretchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: str = Field(alias="from", min_length=1, max_length=40)
    to: str = Field(min_length=1, max_length=40)
    day: Day


class CorridorQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: Day
    window: str = Field(pattern=HHMM)
    limit: int = Field(500, ge=1, le=5000)


class OperatorQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: Day
    operator: str | None = Field(None, max_length=40)
    limit: int = Field(100, ge=1, le=5000)


def _hhmm(minute: int) -> str:
    return f"{int(minute) // 60:02d}:{int(minute) % 60:02d}"


def _window_start(window: str, day: str) -> int:
    h, m = window.split(":")
    step = WINDOWS[day].step_min
    t = int(h) * 60 + int(m)
    return t // step * step


def _num(x, nd=2):
    return None if pd.isna(x) else round(float(x), nd)


class State:
    """Everything loaded once at start-up."""

    def __init__(self, paths: Paths):
        self.paths = paths
        self.processed = Path(paths.processed)
        self.planner = Planner.load(paths)
        self.version = self.planner.version
        self.manifest = self._json(self.processed / "manifest.json")
        self.validation = self._json(self.processed / "validation_report.json")
        gj = self._json(self.processed / "corridor_geometry.geojson")
        self.geometry = {f["id"]: f["geometry"] for f in gj.get("features", [])} if gj else {}

    @staticmethod
    def _json(p: Path):
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return None

    def file(self, name: str) -> Path:
        p = self.processed / name
        if not p.exists():
            raise HTTPException(503, f"{name} is not available in this data build")
        return p

    def query(self, sql: str, params: list) -> pd.DataFrame:
        con = connect()
        try:
            return con.execute(sql, params).df()
        finally:
            con.close()

    def count(self, name: str) -> int | None:
        p = self.processed / name
        if not p.exists():
            return None
        return int(self.query(f"SELECT count(*) FROM read_parquet('{p}')", []).iloc[0, 0])

    def health(self) -> dict:
        head = (self.validation or {}).get("headline_numbers", {})
        pl = self.planner
        stages = (self.manifest or {}).get("stages", {})
        return {
            "status": "ok",
            "data_version": self.version,
            "stages_done": sorted(k for k, v in stages.items() if v.get("done")),
            "counts": {
                "routes": len(pl.route_ids),
                "stops": int(len(pl.stop_lat)),
                "places": len(pl.place_stops),
                "stretch_rows": self.count("stretch_crowding.parquet"),
                "corridor_pairs": len(self.geometry),
                "operator_trips": self.count("operator_trips.parquet"),
            },
            "data": {
                "ticket_days": head.get("clean_days"),
                "tickets_resolved": head.get("tickets_resolved"),
                "gps_available": head.get("gps_available"),
            },
            "credit": CREDIT,
        }


def _placeholder(title: str) -> str:
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            f"content=\"width=device-width,initial-scale=1\"><title>{title}</title></head><body>"
            f"<h1>{title}</h1><p>This page is not built yet. The data is served at "
            f"<a href=\"/v1/health\">/v1/health</a>.</p><p>{CREDIT}</p></body></html>")


def _page(name: str, title: str) -> HTMLResponse:
    f = FRONTEND / name
    return HTMLResponse(f.read_text(encoding="utf-8") if f.is_file() else _placeholder(title))


def create_app(paths: Paths | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.s = State(paths or Paths.from_env())
        yield

    app = FastAPI(title="Delhi bus crowding planner", version="1", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
                       allow_credentials=False)

    def S(request: Request) -> State:
        return request.app.state.s

    @app.exception_handler(PlaceNotFound)
    async def _place_missing(request: Request, exc: PlaceNotFound):
        return JSONResponse({"detail": exc.message, "suggestions": exc.suggestions}, status_code=404)

    @app.get("/v1/health")
    def health(request: Request):
        return S(request).health()

    @app.get("/v1/plan")
    def plan(request: Request, q: Annotated[PlanQuery, Query()]):
        try:
            return S(request).planner.plan(q.from_, q.to, q.depart, q.day)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/v1/places/search")
    def places_search(request: Request, q: Annotated[SearchQuery, Query()]):
        s = S(request)
        return {"data_version": s.version, "query": q.q, "places": s.planner.search_places(q.q, q.limit)}

    @app.get("/v1/crowding")
    def crowding(request: Request, q: Annotated[CrowdingQuery, Query()]):
        s = S(request)
        w = _window_start(q.window, q.day)
        df = s.query(f"""SELECT * FROM read_parquet('{s.file("stretch_crowding.parquet")}')
                         WHERE route_id = ? AND day_type = ? AND window_start_min = ? ORDER BY seq""",
                     [q.route_id, q.day, w])
        if df.empty:
            raise HTTPException(404, f"No crowding data for route {q.route_id} on a {q.day} at {_hhmm(w)}")
        return {"data_version": s.version, "route_id": q.route_id, "route": df.short_name.iloc[0],
                "operator": df.operator.iloc[0], "day": q.day, "window": {"start": _hhmm(w)},
                "stretches": [_stretch(r) for r in df.itertuples()]}

    @app.get("/v1/crowding/stretch")
    def crowding_stretch(request: Request, q: Annotated[StretchQuery, Query()]):
        s = S(request)
        df = s.query(f"""SELECT * FROM read_parquet('{s.file("stretch_crowding.parquet")}')
                         WHERE from_stop_id = ? AND to_stop_id = ? AND day_type = ?
                         ORDER BY window_start_min, route_id""", [q.from_, q.to, q.day])
        if df.empty:
            raise HTTPException(404, f"No crowding data between stops {q.from_} and {q.to} on a {q.day}")
        windows = [{"start": _hhmm(w), "routes": [dict(route_id=int(r.route_id), route=r.short_name, **_stretch(r))
                                                 for r in g.itertuples()]}
                   for w, g in df.groupby("window_start_min")]
        return {"data_version": s.version, "from": {"stop_id": q.from_, "name": df.from_name.iloc[0]},
                "to": {"stop_id": q.to, "name": df.to_name.iloc[0]}, "day": q.day, "windows": windows}

    @app.get("/v1/corridors")
    def corridors(request: Request, q: Annotated[CorridorQuery, Query()]):
        s = S(request)
        w = _window_start(q.window, q.day)
        df = s.query(f"""SELECT * FROM read_parquet('{s.file("corridor_values.parquet")}')
                         WHERE day_type = ? AND window_start_min = ?
                         ORDER BY crowded_rider_min DESC, pair_id LIMIT {int(q.limit)}""", [q.day, w])
        feats = [{"type": "Feature", "id": r.pair_id, "geometry": s.geometry.get(r.pair_id),
                  "properties": {"from_stop_id": r.from_stop_id, "to_stop_id": r.to_stop_id,
                                 "load_ratio": _num(r.load_ratio), "share_crowded": _num(r.share_crowded, 3),
                                 "crowded_rider_min": _num(r.crowded_rider_min, 1), "buses": _num(r.buses),
                                 "routes": int(r.routes)}} for r in df.itertuples()]
        return {"type": "FeatureCollection", "data_version": s.version, "day": q.day,
                "window": {"start": _hhmm(w)}, "features": feats}

    def operator_frame(s: State, q: OperatorQuery) -> pd.DataFrame:
        sql = f"""SELECT * FROM read_parquet('{s.file("operator_trips.parquet")}') WHERE day_type = ?"""
        args: list = [q.day]
        if q.operator:
            sql += " AND upper(operator) = upper(?)"
            args.append(q.operator)
        # weekday and weekend are ranked separately (ruling R23): the day filter is mandatory
        sql += f" ORDER BY crowded_rider_min_removed DESC, route_id, depart_min LIMIT {int(q.limit)}"
        df = s.query(sql, args)
        df["depart"] = df.depart_min.map(_hhmm)
        return df[OPERATOR_COLUMNS]

    @app.get("/v1/operator/trips")
    def operator_trips(request: Request, q: Annotated[OperatorQuery, Query()]):
        s = S(request)
        df = operator_frame(s, q)
        rows = json.loads(df.to_json(orient="records"))
        return {"data_version": s.version, "day": q.day, "operator": q.operator, "count": len(rows), "trips": rows}

    @app.get("/v1/operator/trips.csv")
    def operator_trips_csv(request: Request, q: Annotated[OperatorQuery, Query()]):
        buf = io.StringIO()
        operator_frame(S(request), q).to_csv(buf, index=False)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="operator_trips_{q.day}.csv"',
                                 "X-Data-Version": S(request).version})

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _page("index.html", "Delhi bus crowding planner")

    @app.get("/operator", response_class=HTMLResponse)
    def operator_page():
        return _page("operator.html", "Operator view")

    if FRONTEND.is_dir():
        app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
    return app


def _stretch(r) -> dict:
    return {"seq": int(r.seq), "from_stop_id": r.from_stop_id, "to_stop_id": r.to_stop_id,
            "from_name": r.from_name, "to_name": r.to_name, "level": r.level, "evidence": r.evidence,
            "people": [_num(r.people_low, 0), _num(r.people_mid, 0), _num(r.people_high, 0)],
            "seats": _num(r.seats, 0), "rated_total": _num(r.rated_total, 0), "crush": _num(r.crush, 0),
            "flags": [f for f in (r.flags if isinstance(r.flags, str) else "").split(",") if f]}


app = create_app()
