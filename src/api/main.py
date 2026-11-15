"""
Sprint 4: FastAPI REST Service for Crowdedness-Aware Bus Journey Planner
Transport Stack Hackathon 2026 — Phase 1 (Problem 2)
Crowdedness-Aware Bus Journey Planner for Delhi (DTC/Cluster)
"""

import os
# Limit thread usage for BLAS libraries to avoid memory allocation errors in constrained environments
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import json
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
import numpy as np

from src.routing.mcraptor import McRaptorRouter

# ──────────────────────── Global Singletons & Cache ───────────────────────────

_router_instance: Optional[McRaptorRouter] = None
_metrics_cache: Optional[Dict[str, Any]] = None
_rsn_to_ridx_cache: Optional[Dict[str, int]] = None

def get_base_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_router(base_dir: Optional[str] = None) -> McRaptorRouter:
    global _router_instance
    if _router_instance is None:
        if base_dir is None:
            base_dir = get_base_dir()
        _router_instance = McRaptorRouter(base_dir=base_dir)
    return _router_instance

def get_metrics(base_dir: Optional[str] = None) -> Dict[str, Any]:
    global _metrics_cache
    if _metrics_cache is None:
        if base_dir is None:
            base_dir = get_base_dir()
        proc_dir = os.path.join(base_dir, "data", "processed")
        sprint1_rpt_path = os.path.join(proc_dir, "sprint1_resolution_report.json")
        sprint2_rpt_path = os.path.join(proc_dir, "sprint2_validation_report.json")

        sprint1_data = {}
        if os.path.exists(sprint1_rpt_path):
            with open(sprint1_rpt_path, "r", encoding="utf-8") as f:
                sprint1_data = json.load(f)

        sprint2_data = {}
        if os.path.exists(sprint2_rpt_path):
            with open(sprint2_rpt_path, "r", encoding="utf-8") as f:
                sprint2_data = json.load(f)

        _metrics_cache = {
            "sprint1": sprint1_data,
            "sprint2": sprint2_data,
        }
    return _metrics_cache

def get_rsn_to_ridx(base_dir: Optional[str] = None) -> Dict[str, int]:
    global _rsn_to_ridx_cache
    if _rsn_to_ridx_cache is None:
        router = get_router(base_dir)
        rsn_dict = {}
        for r_idx in range(router.n_routes):
            r_id = router.idx_to_route_id[r_idx]
            meta = router.route_meta.get(r_id, {})
            rsn = meta.get("route_short_name", "")
            if rsn:
                rsn_dict[rsn.upper()] = r_idx
        _rsn_to_ridx_cache = rsn_dict
    return _rsn_to_ridx_cache

# Major transit hubs across Delhi for default empty search
MAJOR_TRANSIT_HUBS = [
    {"stop_id": "2560", "stop_name": "Nehru Place Terminal", "stop_lat": 28.5487, "stop_lon": 77.2570},
    {"stop_id": "2944", "stop_name": "Dhaula Kuan (Ring Road)", "stop_lat": 28.5995, "stop_lon": 77.1625},
    {"stop_id": "4822", "stop_name": "ISBT Kashmere Gate City Bus Terminal", "stop_lat": 28.6668, "stop_lon": 77.2294},
    {"stop_id": "1037", "stop_name": "ITO AGCR /  ITO", "stop_lat": 28.6281, "stop_lon": 77.2450},
    {"stop_id": "365",  "stop_name": "Shivaji Stadium Terminal (Connaught Place)", "stop_lat": 28.6323, "stop_lon": 77.2165},
    {"stop_id": "7975", "stop_name": "Uttam Nagar Terminal (Out Gate)", "stop_lat": 28.6255, "stop_lon": 77.0663},
    {"stop_id": "257",  "stop_name": "GTB Nagar", "stop_lat": 28.6982, "stop_lon": 77.2066},
    {"stop_id": "7563", "stop_name": "Pitampura Metro Station Madhuban Chowk", "stop_lat": 28.7031, "stop_lon": 77.1326},
    {"stop_id": "2672", "stop_name": "Badarpur Village", "stop_lat": 28.5021, "stop_lon": 77.3002},
    {"stop_id": "2829", "stop_name": "AIIMS", "stop_lat": 28.5685, "stop_lon": 77.2078},
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n[FastAPI] Pre-warming McRAPTOR Router and Loading Model Validation Metrics...", flush=True)
    t0 = time.time()
    router = get_router()
    app.state.router = router
    app.state.metrics = get_metrics()
    app.state.rsn_to_ridx = get_rsn_to_ridx()
    print(f"[FastAPI] Lifespan pre-warm complete in {time.time()-t0:.2f}s. Server ready!", flush=True)
    yield
    print("[FastAPI] Shutting down service.", flush=True)

# ────────────────────────── FastAPI App & Middlewares ─────────────────────────

app = FastAPI(
    title="Crowdedness-Aware Bus Journey Planner for Delhi (DTC/Cluster)",
    description="Transport Stack Hackathon 2026 — Phase 1 (Problem 2) Backend API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ───────────────────────────── Pydantic Schemas ───────────────────────────────

class PlanRequest(BaseModel):
    origin_stop_id: str = Field(..., description="GTFS stop_id of the origin stop")
    dest_stop_id: str = Field(..., description="GTFS stop_id of the destination stop")
    departure_time: str = Field(default="09:00", description="Departure time in HH:MM format (default: 09:00)")
    day_type: str = Field(default="weekday", description="'weekday', 'saturday', or 'sunday'")
    beta: float = Field(default=0.6, ge=0.0, le=5.0, description="Discomfort penalty weight (0.0 = Fastest, 0.6 = Balanced, 1.8 = Least Crowded)")

class HealthResponse(BaseModel):
    status: str
    stops_indexed: int
    routes_loaded: int
    transfer_edges: int
    ready: bool

# ──────────────────────────────── API Endpoints ───────────────────────────────

@app.get("/", include_in_schema=False)
def get_frontend():
    """Serves the interactive web UI frontend."""
    base_dir = get_base_dir()
    index_path = os.path.join(base_dir, "frontend", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse({"status": "Frontend index.html under development", "api_docs": "/docs"})

@app.get("/api/health", response_model=HealthResponse)
def get_health():
    """Returns engine health status and dataset indexing summary."""
    router = getattr(app.state, "router", None) or get_router()
    return {
        "status": "healthy",
        "stops_indexed": router.n_stops,
        "routes_loaded": router.n_routes,
        "transfer_edges": sum(len(e) for e in router.footpaths_idx),
        "ready": True
    }

@app.get("/api/stops/search")
def search_stops(
    q: str = Query(default="", description="Search query for stop name or stop_id"),
    limit: int = Query(default=12, ge=1, le=50, description="Max results to return")
):
    """
    Fast prefix, substring, and token search across all 6,862 GTFS stops.
    If query is empty, returns curated list of 10 major transit hubs.
    """
    router = getattr(app.state, "router", None) or get_router()
    clean_q = q.strip().lower()

    if not clean_q:
        return {"query": "", "count": len(MAJOR_TRANSIT_HUBS), "stops": MAJOR_TRANSIT_HUBS[:limit]}

    results = []
    for sid, info in router.stop_info.items():
        name_lower = info["stop_name"].lower()
        score = 0
        if name_lower.startswith(clean_q) or sid.startswith(clean_q):
            score = 100
        elif f" {clean_q}" in name_lower or f"/{clean_q}" in name_lower or f"({clean_q}" in name_lower:
            score = 80
        elif clean_q in name_lower:
            score = 60

        if score > 0:
            results.append({
                "score": score,
                "stop_id": sid,
                "stop_name": info["stop_name"],
                "stop_lat": info["lat"],
                "stop_lon": info["lon"]
            })

    results.sort(key=lambda x: (-x["score"], len(x["stop_name"])))
    truncated = results[:limit]

    return {
        "query": q,
        "count": len(truncated),
        "stops": [{k: v for k, v in r.items() if k != "score"} for r in truncated]
    }

@app.post("/api/plan")
def plan_journey_endpoint(req: PlanRequest):
    """
    Computes multi-criteria Pareto-optimal itineraries between origin and destination:
    - Incorporates empirical headway wait time and left-behind risk (>80% crush load).
    - Returns ranked Pareto itineraries with latency in ms.
    - Evaluates smart +/-15 minute departure shifts and attaches `departure_nudge` if crowding is reduced by >= 15%.
    """
    router = getattr(app.state, "router", None) or get_router()
    t_start = time.time()

    dep_time = req.departure_time.strip()
    if len(dep_time.split(":")) == 2:
        dep_time = f"{dep_time}:00"

    res = router.plan_journey(
        origin_stop=req.origin_stop_id,
        dest_stop=req.dest_stop_id,
        departure_time_str=dep_time,
        day_type=req.day_type,
        beta=req.beta
    )

    elapsed_ms = round((time.time() - t_start) * 1000.0, 1)
    res["query_latency_ms"] = elapsed_ms

    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])

    return res

@app.get("/api/validation/metrics")
def get_validation_metrics():
    """
    Returns pipeline validation metrics and charts data from Sprint 1 and Sprint 2:
    - Diurnal weekday peak/lull crowding table
    - Directional asymmetry metrics (717A, 729, 511A, 578)
    - KPI cards data (passengers modeled, stop resolution rate, etc.)
    """
    metrics = getattr(app.state, "metrics", None) or get_metrics()
    sprint1 = metrics.get("sprint1", {})
    sprint2 = metrics.get("sprint2", {})

    sprint2_val = sprint2.get("validation", {})
    diurnal = sprint2_val.get("diurnal_windows", {})
    asym = sprint2_val.get("directional_asymmetry", {})
    tiers = sprint2_val.get("overall_tier_distribution", {})

    return {
        "kpis": {
            "total_passengers_modeled": "2,574,781",
            "stop_resolution_match_rate": "93.13%",
            "total_segment_slots": "1,209,599",
            "active_bus_fleet": "6,810",
            "mean_query_latency_ms": "~170 ms (Single) / 517 ms (3 Profiles)"
        },
        "diurnal_windows": diurnal,
        "directional_asymmetry": asym,
        "tier_distribution": tiers,
        "sprint1_summary": sprint1.get("summary", {}),
        "sprint2_parameters": sprint2.get("model_parameters", {})
    }

@app.get("/api/routes/{route_short_name}/profile")
def get_route_profile(
    route_short_name: str,
    day_type: str = Query(default="weekday", description="weekday, saturday, or sunday"),
    time_slot: int = Query(default=18, ge=0, le=47, description="Time slot 0..47 (18 = 09:00-09:30)")
):
    """
    Returns stop-by-stop sequence, coordinates, and crowding scores along a specific route.
    """
    router = getattr(app.state, "router", None) or get_router()
    clean_rsn = route_short_name.strip().upper()
    rsn_to_ridx = getattr(app.state, "rsn_to_ridx", None) or get_rsn_to_ridx()

    r_idx = rsn_to_ridx.get(clean_rsn)
    if r_idx is None:
        raise HTTPException(status_code=404, detail=f"Route '{route_short_name}' not found in canonical feed.")

    r_id = router.idx_to_route_id[r_idx]
    r_meta = router.route_meta.get(r_id, {})
    is_ac = bool(router.route_is_ac[r_idx])

    day_norm = day_type.strip().lower()
    day_code = 1 if "sat" in day_norm else (2 if "sun" in day_norm else 0)

    stops = router.route_stops_arr[r_idx]
    durs = router.route_segs_dur[r_idx]
    cs_mat = router.route_segs_cs[r_idx]

    stop_list = []
    seg_list = []

    for idx, (s_idx, seq, _) in enumerate(stops):
        sid = router.idx_to_stop_id[s_idx]
        info = router.stop_info[sid]
        stop_list.append({
            "stop_sequence": seq,
            "stop_id": sid,
            "stop_name": info["stop_name"],
            "lat": info["lat"],
            "lon": info["lon"]
        })

        if idx < len(stops) - 1:
            next_sid = router.idx_to_stop_id[stops[idx + 1][0]]
            next_info = router.stop_info[next_sid]
            seg_dur = int(durs[idx])
            cs = float(cs_mat[idx, day_code, time_slot])

            seg_list.append({
                "from_sequence": seq,
                "from_stop_name": info["stop_name"],
                "from_lat": info["lat"],
                "from_lon": info["lon"],
                "to_sequence": stops[idx + 1][1],
                "to_stop_name": next_info["stop_name"],
                "to_lat": next_info["lat"],
                "to_lon": next_info["lon"],
                "scheduled_duration_sec": seg_dur,
                "crowding_score": round(cs, 3),
                "crowding_tier": "Low" if cs < 0.35 else ("Moderate" if cs <= 0.70 else "High")
            })

    avg_cs = float(np.mean([s["crowding_score"] for s in seg_list])) if seg_list else 0.15
    max_cs = float(np.max([s["crowding_score"] for s in seg_list])) if seg_list else 0.15

    return {
        "route_id": r_id,
        "route_short_name": r_meta.get("route_short_name", clean_rsn),
        "route_long_name": r_meta.get("route_long_name", clean_rsn),
        "is_ac": is_ac,
        "day_type": day_type,
        "time_slot": time_slot,
        "total_stops": len(stop_list),
        "avg_crowding_score": round(avg_cs, 3),
        "max_crowding_score": round(max_cs, 3),
        "stops": stop_list,
        "segments": seg_list
    }
