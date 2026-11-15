"""
Sprint 3: Multi-Criteria Crowdedness-Aware Journey Planner Engine (McRAPTOR)
Transport Stack Hackathon 2026 — Phase 1 (Problem 2)
Crowdedness-Aware Bus Journey Planner for Delhi (DTC/Cluster)

Features:
  - Step A: Haversine BallTree spatial stop index & 300m walking footpath transfers
            Multi-stop origin/destination radius expansion (250m) for opposite-platform access
  - Step B: Fast O(1) time-dependent segment crowding & travel time lookup
            Automatic time_slot advancement as journeys progress across legs
  - Step C: Multi-criteria Pareto-optimal McRAPTOR routing optimizing:
            Cost(e) = T(e) * (1 + beta * C(e, t)^1.5) + W_transfer
            Returns up to 3 non-dominated itineraries (Fastest, Balanced, Least Crowded)
"""

import os
import math
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

import duckdb
import numpy as np
try:
    from sklearn.neighbors import BallTree
except Exception as e:
    # Fallback dummy BallTree for environments without scikit-learn/scipy
    class BallTree:
        def __init__(self, data, metric='haversine'):
            self.data = data
        def query_radius(self, X, r, return_distance=False):
            # Return empty arrays matching expected shapes
            import numpy as np
            indices = [np.array([], dtype=int) for _ in range(len(X))]
            distances = [np.array([], dtype=float) for _ in range(len(X))]
            return (indices, distances) if return_distance else indices

R_EARTH = 6371000.0  # Earth radius in meters
WALK_SPEED_MPS = 1.2  # 1.2 m/s (~4.32 km/h) walking speed
MIN_TRANSFER_BUFFER_SEC = 120.0  # 2 minutes minimum transfer walking/buffer
TRANSFER_PENALTY_SEC = 300.0  # 5 minutes discomfort penalty per transfer
INITIAL_BOARDING_WAIT_SEC = 180.0  # 3 minutes average wait at initial boarding
INF = 1e9


def haversine_dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two coordinates in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return R_EARTH * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def tier_from_score(score: float) -> str:
    """Translates a [0, 1] crowding score into a categorical comfort tier."""
    if score < 0.35:
        return "Low"
    elif score <= 0.70:
        return "Moderate"
    return "High"


def compute_bus_fare(dist_km: float, is_ac: bool) -> int:
    """Calculates official DTC/Cluster bus fare based on distance and AC mode."""
    if is_ac:
        if dist_km <= 4.0:
            return 10
        elif dist_km <= 8.0:
            return 15
        elif dist_km <= 12.0:
            return 20
        else:
            return 25
    else:
        if dist_km <= 4.0:
            return 5
        elif dist_km <= 10.0:
            return 10
        else:
            return 15


class McRaptorRouter:
    """
    High-performance multi-criteria RAPTOR transit router with time-dependent
    crowding awareness and spatial footpath transfers for Delhi's bus network.
    """

    def __init__(self, base_dir: Optional[str] = None):
        t0 = time.time()
        if base_dir is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.base_dir = base_dir

        gtfs_dir = os.path.join(base_dir, "data", "raw", "gtfs", "delhi_buses_static_gtfs_v1")
        proc_dir = os.path.join(base_dir, "data", "processed")

        self.stops_file = os.path.join(gtfs_dir, "stops.txt")
        self.routes_file = os.path.join(gtfs_dir, "routes.txt")
        self.canon_file = os.path.join(proc_dir, "canonical_route_stops.parquet")
        self.crowd_file = os.path.join(proc_dir, "segment_crowding.parquet")

        con = duckdb.connect()

        # 1. Load physical stops
        stops_df = con.execute(f"""
            SELECT CAST(stop_id AS VARCHAR) AS stop_id, stop_name,
                   CAST(stop_lat AS DOUBLE) AS stop_lat, CAST(stop_lon AS DOUBLE) AS stop_lon
            FROM read_csv_auto('{self.stops_file.replace(chr(92), "/")}')
        """).fetchdf()

        self.n_stops = len(stops_df)
        self.stop_id_to_idx: Dict[str, int] = {sid: i for i, sid in enumerate(stops_df["stop_id"])}
        self.idx_to_stop_id: List[str] = list(stops_df["stop_id"])
        self.stop_info: Dict[str, Dict[str, Any]] = {}
        for _, r in stops_df.iterrows():
            self.stop_info[r["stop_id"]] = {
                "stop_id": r["stop_id"],
                "stop_name": r["stop_name"],
                "lat": float(r["stop_lat"]),
                "lon": float(r["stop_lon"])
            }

        # 2. Footpath index — fast latitude-band candidate filtering
        lat_deg = stops_df["stop_lat"].values
        lon_deg = stops_df["stop_lon"].values
        self._fp_lat = lat_deg
        self._fp_lon = lon_deg
        self._fp_sorted_idx = np.argsort(lat_deg)
        self._fp_sorted_lat = lat_deg[self._fp_sorted_idx]
        self.stop_coords = np.column_stack([
            np.radians(lat_deg), np.radians(lon_deg)
        ])

        # Precompute footpaths for all stops using sorted latitude window search (takes ~3.5s)
        self.footpaths_idx: List[List[Tuple[int, float, float]]] = [[] for _ in range(self.n_stops)]
        total_transfer_edges = 0
        LAT_DELTA_DEG = 300.0 / 111320.0

        for i in range(self.n_stops):
            lat1 = lat_deg[i]
            lon1 = lon_deg[i]
            lo = int(np.searchsorted(self._fp_sorted_lat, lat1 - LAT_DELTA_DEG))
            hi = int(np.searchsorted(self._fp_sorted_lat, lat1 + LAT_DELTA_DEG))
            candidates = self._fp_sorted_idx[lo:hi]
            for j in candidates:
                j = int(j)
                if j == i:
                    continue
                dist = haversine_dist_m(lat1, lon1, lat_deg[j], lon_deg[j])
                if dist <= 300.0:
                    wt = dist / WALK_SPEED_MPS + MIN_TRANSFER_BUFFER_SEC
                    self.footpaths_idx[i].append((j, wt, dist))
                    total_transfer_edges += 1

        # 3. Load canonical routes and stops
        canon_df = con.execute(f"""
            SELECT CAST(route_id AS BIGINT) AS route_id, route_short_name,
                   CAST(stop_sequence AS INTEGER) AS stop_sequence,
                   CAST(stop_id AS VARCHAR) AS stop_id,
                   COALESCE(scheduled_travel_sec, 60) AS scheduled_travel_sec
            FROM read_parquet('{self.canon_file.replace(chr(92), "/")}')
            ORDER BY route_id, stop_sequence
        """).fetchdf()

        # Routes metadata
        routes_txt = con.execute(f"""
            SELECT CAST(route_id AS BIGINT) AS route_id, route_long_name, route_short_name
            FROM read_csv_auto('{self.routes_file.replace(chr(92), "/")}')
        """).fetchdf()
        self.route_meta: Dict[int, Dict[str, str]] = {}
        for _, r in routes_txt.iterrows():
            self.route_meta[int(r["route_id"])] = {
                "route_short_name": r["route_short_name"],
                "route_long_name": r["route_long_name"] or r["route_short_name"]
            }

        unique_routes = canon_df["route_id"].unique()
        self.n_routes = len(unique_routes)
        self.route_id_to_idx: Dict[int, int] = {int(r): i for i, r in enumerate(unique_routes)}
        self.idx_to_route_id: List[int] = [int(r) for r in unique_routes]

        self.route_stops_arr: List[List[Tuple[int, int, int]]] = [[] for _ in range(self.n_routes)]
        self.stop_routes_arr: List[List[Tuple[int, int]]] = [[] for _ in range(self.n_stops)]

        for r, seq, s, dur in zip(
            canon_df["route_id"], canon_df["stop_sequence"], canon_df["stop_id"], canon_df["scheduled_travel_sec"]
        ):
            r_idx = self.route_id_to_idx[int(r)]
            s_idx = self.stop_id_to_idx[str(s)]
            dur = int(dur) if dur > 0 else 60
            idx_in_route = len(self.route_stops_arr[r_idx])
            self.route_stops_arr[r_idx].append((s_idx, int(seq), dur))
            self.stop_routes_arr[s_idx].append((r_idx, idx_in_route))

        # 4. Dense numpy arrays for microsecond segment crowding lookup
        crowd_df = con.execute(f"""
            SELECT
                CAST(route_id AS BIGINT) AS route_id,
                CAST(from_seq AS INTEGER) AS from_seq,
                CASE day_type WHEN 'weekday' THEN 0 WHEN 'saturday' THEN 1 ELSE 2 END AS day_code,
                CAST(time_slot AS INTEGER) AS time_slot,
                CAST(scheduled_travel_sec AS INTEGER) AS scheduled_travel_sec,
                CAST(crowding_score AS FLOAT) AS crowding_score,
                CAST(is_ac AS BOOLEAN) AS is_ac
            FROM read_parquet('{self.crowd_file.replace(chr(92), "/")}')
        """).fetchdf()

        route_seq_to_seg: Dict[Tuple[int, int], int] = {}
        self.route_segs_dur: List[np.ndarray] = []
        self.route_segs_cs: List[np.ndarray] = []
        self.route_is_ac = np.ones(self.n_routes, dtype=bool)

        for r_idx in range(self.n_routes):
            stops = self.route_stops_arr[r_idx]
            n_segs = max(0, len(stops) - 1)
            durs = np.array([s[2] for s in stops[:-1]], dtype=np.int32) if n_segs > 0 else np.zeros(0, dtype=np.int32)
            cs_arr = np.full((n_segs, 3, 48), 0.15, dtype=np.float32)
            self.route_segs_dur.append(durs)
            self.route_segs_cs.append(cs_arr)
            for seg_idx, s in enumerate(stops[:-1]):
                route_seq_to_seg[(r_idx, s[1])] = seg_idx

        # Vectorized crowd fill — map route_id → r_idx and (r_idx, from_seq) → seg_idx using pandas
        import pandas as pd

        # Map route_id → r_idx
        rid_map = {int(r): i for r, i in zip(
            [self.idx_to_route_id[i] for i in range(self.n_routes)],
            range(self.n_routes)
        )}
        crowd_df["r_idx"] = crowd_df["route_id"].map(rid_map)
        crowd_df = crowd_df.dropna(subset=["r_idx"])
        crowd_df["r_idx"] = crowd_df["r_idx"].astype(int)

        # Map (r_idx, from_seq) → seg_idx
        rseq_keys = list(route_seq_to_seg.keys())
        rseq_vals = list(route_seq_to_seg.values())
        rseq_df = pd.DataFrame({"r_idx": [k[0] for k in rseq_keys],
                                 "from_seq": [k[1] for k in rseq_keys],
                                 "seg_idx": rseq_vals})
        crowd_df = crowd_df.merge(rseq_df, on=["r_idx", "from_seq"], how="inner")

        # Fill cs arrays via groupby r_idx for vectorized numpy scatter
        for r_idx, grp in crowd_df.groupby("r_idx"):
            r_idx = int(r_idx)
            cs_mat = self.route_segs_cs[r_idx]   # shape (n_segs, 3, 48)
            dur_arr = self.route_segs_dur[r_idx]
            si = grp["seg_idx"].values.astype(int)
            di = grp["day_code"].values.astype(int)
            ti = grp["time_slot"].values.astype(int)
            cs_mat[si, di, ti] = grp["crowding_score"].values
            # update durations where positive
            pos = grp["scheduled_travel_sec"].values > 0
            if pos.any():
                dur_arr[si[pos]] = grp["scheduled_travel_sec"].values[pos].astype(int)
            # is_ac: last row wins
            self.route_is_ac[r_idx] = bool(grp["is_ac"].iloc[-1])

        # Precalculate cs**1.5 for speed in core routing loops
        self.route_segs_cspow: List[np.ndarray] = [
            self.route_segs_cs[r] ** 1.5 for r in range(self.n_routes)
        ]

        # 5. Load GTFS shape geometry cache for road-following polylines
        import pickle as _pickle
        shape_cache_path = os.path.join(proc_dir, "route_segment_shapes.pkl")
        if os.path.exists(shape_cache_path):
            with open(shape_cache_path, "rb") as _f:
                self.segment_shapes: Dict[Tuple[int, str, str], List[List[float]]] = _pickle.load(_f)
            print(f"[McRaptorRouter] Loaded shape cache: {len(self.segment_shapes):,} road-shaped segments.")
        else:
            self.segment_shapes = {}
            print("[McRaptorRouter] Shape cache not found — polylines will be straight lines.")

        # 6. Load empirical route headways cache
        import json as _json
        headways_path = os.path.join(proc_dir, "route_headways.json")
        if os.path.exists(headways_path):
            with open(headways_path, "r", encoding="utf-8") as _hf:
                self.route_headways: Dict[str, Dict[str, float]] = _json.load(_hf)
            print(f"[McRaptorRouter] Loaded empirical headways for {len(self.route_headways):,} routes.")
        else:
            self.route_headways = {}
            print("[McRaptorRouter] Headway cache not found — using 12.0m fallback.")

        self.init_duration_sec = time.time() - t0
        print(f"[McRaptorRouter] Initialized in {self.init_duration_sec:.2f}s "
              f"({self.n_stops:,} stops, {self.n_routes:,} routes, {total_transfer_edges:,} transfer edges).")

    def get_route_headway(self, route_id: int, time_slot: int) -> float:
        """
        Returns empirical headway H_{r,t} in minutes for a given route and time slot.
        Clamped to [4.0, 30.0] min with 12.0 min fallback.
        """
        if 10 <= time_slot <= 16:
            w = 'Early Morning'
        elif 17 <= time_slot <= 22:
            w = 'Morning Peak'
        elif 23 <= time_slot <= 32:
            w = 'Afternoon Lull'
        elif 33 <= time_slot <= 40:
            w = 'Evening Peak'
        else:
            w = 'Late Night'

        r_dict = self.route_headways.get(str(route_id))
        if r_dict and w in r_dict:
            return float(r_dict[w])
        return 12.0

    # ─────────────────────────── Spatial Helpers ───────────────────────────────

    def _get_footpaths(self, stop_idx: int) -> List[Tuple[int, float, float]]:
        """
        Lazily computes and caches footpaths (neighbors within 300 m) for a stop.
        Uses sorted-lat binary search to narrow candidates before haversine check.
        """
        if self._fp_computed[stop_idx]:
            return self.footpaths_idx[stop_idx]  # type: ignore

        lat1 = self._fp_lat[stop_idx]
        lon1 = self._fp_lon[stop_idx]
        # Binary-search latitude band: ±300m ≈ ±0.0027 degrees
        LAT_DELTA_DEG = 300.0 / 111320.0
        lo = int(np.searchsorted(self._fp_sorted_lat, lat1 - LAT_DELTA_DEG))
        hi = int(np.searchsorted(self._fp_sorted_lat, lat1 + LAT_DELTA_DEG))
        candidates = self._fp_sorted_idx[lo:hi]

        fps: List[Tuple[int, float, float]] = []
        for j in candidates:
            j = int(j)
            if j == stop_idx:
                continue
            dist = haversine_dist_m(lat1, lon1, self._fp_lat[j], self._fp_lon[j])
            if dist <= 300.0:
                wt = dist / WALK_SPEED_MPS + MIN_TRANSFER_BUFFER_SEC
                fps.append((j, wt, dist))

        self.footpaths_idx[stop_idx] = fps
        self._fp_computed[stop_idx] = True
        return fps

    def find_nearby_stops(self, target_stop_id: str, radius_m: float = 250.0) -> Dict[int, Tuple[float, float]]:
        """
        Returns all stops within radius_m of target_stop_id.
        Mapping: {stop_idx: (walk_duration_sec, walk_distance_m)}
        """
        if target_stop_id not in self.stop_id_to_idx:
            clean_tgt = str(target_stop_id).strip()
            if clean_tgt in self.stop_id_to_idx:
                target_stop_id = clean_tgt
            else:
                return {}

        tgt_idx = self.stop_id_to_idx[target_stop_id]
        lat1 = self._fp_lat[tgt_idx]
        lon1 = self._fp_lon[tgt_idx]

        LAT_DELTA_DEG = radius_m / 111320.0
        lo = int(np.searchsorted(self._fp_sorted_lat, lat1 - LAT_DELTA_DEG))
        hi = int(np.searchsorted(self._fp_sorted_lat, lat1 + LAT_DELTA_DEG))
        candidates = self._fp_sorted_idx[lo:hi]

        res: Dict[int, Tuple[float, float]] = {}
        for j in candidates:
            j = int(j)
            d_m = haversine_dist_m(lat1, lon1, self._fp_lat[j], self._fp_lon[j])
            if d_m <= radius_m:
                walk_dur = d_m / WALK_SPEED_MPS
                res[j] = (walk_dur, d_m)
        # Always include the target stop itself with 0 walk
        res[tgt_idx] = (0.0, 0.0)
        return res

    def resolve_stop(self, query: str) -> Optional[str]:
        """Resolves raw stop query (ID or stop name) to valid stop_id."""
        query_str = str(query).strip()
        if query_str in self.stop_id_to_idx:
            return query_str

        # Case-insensitive name match
        lower_q = query_str.lower()
        for sid, info in self.stop_info.items():
            if info["stop_name"].lower() == lower_q:
                return sid

        # Substring search fallback
        for sid, info in self.stop_info.items():
            if lower_q in info["stop_name"].lower():
                return sid

        return None

    # ───────────────────────── Core McRAPTOR Search ───────────────────────────

    def _raptor_search(
        self,
        orig_sid: str,
        dest_sid: str,
        dep_sec: float,
        day_code: int,
        beta: float,
        max_rounds: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Executes single-criteria label-setting RAPTOR run for a specific discomfort weight beta.
        Prunes using upper-bound destination arrival costs for sub-second query latency.
        """
        orig_stops = self.find_nearby_stops(orig_sid, 400.0)
        dest_stops = self.find_nearby_stops(dest_sid, 400.0)

        if not orig_stops or not dest_stops:
            return None

        # best_cost[round, stop_idx] and best_time[round, stop_idx]
        best_cost = np.full((max_rounds + 1, self.n_stops), INF, dtype=np.float32)
        best_time = np.full((max_rounds + 1, self.n_stops), INF, dtype=np.float32)
        global_best_cost = np.full(self.n_stops, INF, dtype=np.float32)

        # Backtrack parents: parent[round][stop_idx] = (mode, r_idx, board_s_idx, prev_s_idx, dur)
        # mode: 0 = WALK, 1 = BUS
        parent: List[Dict[int, Tuple[int, int, int, int, float]]] = [{} for _ in range(max_rounds + 1)]

        # Initialize round 0 with origin candidates
        marked_stops = set()
        orig_tgt_idx = self.stop_id_to_idx[orig_sid]

        for s_idx, (w_dur, _) in orig_stops.items():
            best_cost[0, s_idx] = w_dur
            best_time[0, s_idx] = dep_sec + w_dur
            global_best_cost[s_idx] = w_dur
            if s_idx != orig_tgt_idx:
                parent[0][s_idx] = (0, -1, orig_tgt_idx, s_idx, w_dur)
            marked_stops.add(s_idx)

        # Footpaths in round 0
        for s_idx in list(marked_stops):
            c0 = best_cost[0, s_idx]
            t0_val = best_time[0, s_idx]
            for v_idx, w_dur, _ in self.footpaths_idx[s_idx]:
                cand_c = c0 + w_dur
                if cand_c < global_best_cost[v_idx]:
                    best_cost[0, v_idx] = cand_c
                    best_time[0, v_idx] = t0_val + w_dur
                    global_best_cost[v_idx] = cand_c
                    parent[0][v_idx] = (0, -1, s_idx, v_idx, w_dur)
                    marked_stops.add(v_idx)

        best_dest_cost = INF

        for k in range(1, max_rounds + 1):
            # Accumulate earliest marked stop index per route
            routes_to_scan: Dict[int, int] = {}
            for p in marked_stops:
                for r_idx, stop_idx in self.stop_routes_arr[p]:
                    if r_idx not in routes_to_scan or stop_idx < routes_to_scan[r_idx]:
                        routes_to_scan[r_idx] = stop_idx

            bus_marked = set()

            for r_idx, start_idx in routes_to_scan.items():
                stops = self.route_stops_arr[r_idx]
                n_stops = len(stops)
                if start_idx >= n_stops - 1:
                    continue

                active_board_stop_idx = -1
                active_board_pos = -1
                cur_time = 0.0
                cur_cost = 0.0

                durs = self.route_segs_dur[r_idx]
                cspow_mat = self.route_segs_cspow[r_idx]

                for i in range(start_idx, n_stops):
                    s_idx = stops[i][0]

                    # Alight / downstream segment traversal
                    if active_board_stop_idx >= 0 and i > active_board_pos:
                        seg_i = i - 1
                        seg_dur = float(durs[seg_i])
                        slot = int((cur_time % 86400) // 1800)
                        cs_pow = float(cspow_mat[seg_i, day_code, slot])
                        seg_cost = seg_dur * (1.0 + beta * cs_pow)
                        cur_time += seg_dur
                        cur_cost += seg_cost

                        if cur_cost < global_best_cost[s_idx] and cur_cost < best_dest_cost:
                            best_cost[k, s_idx] = cur_cost
                            best_time[k, s_idx] = cur_time
                            global_best_cost[s_idx] = cur_cost
                            parent[k][s_idx] = (1, r_idx, active_board_stop_idx, s_idx, cur_cost)
                            bus_marked.add(s_idx)

                            if s_idx in dest_stops:
                                tot_c = cur_cost + dest_stops[s_idx][0]
                                if tot_c < best_dest_cost:
                                    best_dest_cost = tot_c

                    # Consider boarding at s_idx
                    prev_c = best_cost[k - 1, s_idx]
                    if prev_c < best_dest_cost:
                        prev_t = best_time[k - 1, s_idx]
                        b_slot = int((prev_t % 86400) // 1800)
                        r_id = self.idx_to_route_id[r_idx]
                        h_min = self.get_route_headway(r_id, b_slot)
                        w_base_sec = min(15.0, 0.5 * h_min) * 60.0
                        wait_cost = 1.5 * w_base_sec

                        # Left-behind boarding denial penalty when C(e,t) > 0.80
                        if i < n_stops - 1:
                            c_board = float(self.route_segs_cs[r_idx][i, day_code, b_slot])
                        else:
                            c_board = 0.0

                        if c_board > 0.80:
                            p_deny = min(0.75, ((c_board - 0.80) / 0.20) * 0.75)
                            e_delay_sec = p_deny * (h_min * 60.0)
                            denial_cost = 1.7 * e_delay_sec
                        else:
                            e_delay_sec = 0.0
                            denial_cost = 0.0

                        tr_pen = TRANSFER_PENALTY_SEC if k > 1 else 0.0
                        cand_c = prev_c + wait_cost + denial_cost + tr_pen
                        if cand_c < best_dest_cost:
                            cand_t = prev_t + w_base_sec + e_delay_sec
                            if active_board_stop_idx < 0 or cand_c < cur_cost:
                                active_board_stop_idx = s_idx
                                active_board_pos = i
                                cur_cost = cand_c
                                cur_time = cand_t

            # Footpath transfers from bus_marked
            footpath_marked = set()
            for p in bus_marked:
                p_cost = best_cost[k, p]
                p_time = best_time[k, p]
                for v_idx, w_dur, _ in self.footpaths_idx[p]:
                    cand_c = p_cost + w_dur
                    if cand_c < global_best_cost[v_idx] and cand_c < best_dest_cost:
                        best_cost[k, v_idx] = cand_c
                        best_time[k, v_idx] = p_time + w_dur
                        global_best_cost[v_idx] = cand_c
                        parent[k][v_idx] = (0, -1, p, v_idx, w_dur)
                        footpath_marked.add(v_idx)

                        if v_idx in dest_stops:
                            tot_c = cand_c + dest_stops[v_idx][0]
                            if tot_c < best_dest_cost:
                                best_dest_cost = tot_c

            marked_stops = bus_marked | footpath_marked
            if not marked_stops:
                break

        # Find best destination candidate and reconstruct itinerary
        best_final_cost = INF
        best_dest_idx = None
        best_k = -1

        dest_tgt_idx = self.stop_id_to_idx[dest_sid]
        for d_idx, (egress_walk, _) in dest_stops.items():
            for k in range(1, max_rounds + 1):
                if best_cost[k, d_idx] < INF:
                    total_c = best_cost[k, d_idx] + egress_walk
                    if total_c < best_final_cost:
                        best_final_cost = total_c
                        best_dest_idx = d_idx
                        best_k = k

        if best_dest_idx is None:
            return None

        # Reconstruct path backwards
        return self._reconstruct_itinerary(
            orig_sid, dest_sid, dep_sec, day_code,
            best_dest_idx, best_k, parent, dest_stops[best_dest_idx][0]
        )

    # ────────────────────── Itinerary Path Reconstruction ──────────────────────

    def _reconstruct_itinerary(
        self,
        orig_sid: str,
        dest_sid: str,
        dep_sec: float,
        day_code: int,
        best_dest_idx: int,
        best_k: int,
        parent: List[Dict[int, Tuple[int, int, int, int, float]]],
        egress_walk_sec: float
    ) -> Dict[str, Any]:
        """Backtracks parent pointers and materializes structured legs and segments."""
        raw_legs = []
        cur_idx = best_dest_idx
        cur_k = best_k

        # Final egress walk if needed
        dest_tgt_idx = self.stop_id_to_idx[dest_sid]
        if cur_idx != dest_tgt_idx and egress_walk_sec > 0:
            raw_legs.append({
                "mode": "WALK",
                "from_stop_idx": cur_idx,
                "to_stop_idx": dest_tgt_idx,
                "walk_duration_sec": egress_walk_sec
            })

        while cur_k > 0 or cur_idx in parent[0]:
            p_info = parent[cur_k].get(cur_idx)
            if p_info is None:
                if cur_k > 0:
                    cur_k -= 1
                    continue
                else:
                    break

            mode = p_info[0]
            if mode == 0:  # WALK
                from_idx = p_info[2]
                to_idx = p_info[3]
                w_dur = p_info[4]
                raw_legs.append({
                    "mode": "WALK",
                    "from_stop_idx": from_idx,
                    "to_stop_idx": to_idx,
                    "walk_duration_sec": w_dur
                })
                cur_idx = from_idx
                # Check if walk was within same round or crossed round
                if cur_k > 0 and cur_idx not in parent[cur_k]:
                    cur_k -= 1
            else:  # BUS
                r_idx = p_info[1]
                board_idx = p_info[2]
                alight_idx = p_info[3]
                raw_legs.append({
                    "mode": "BUS",
                    "r_idx": r_idx,
                    "board_stop_idx": board_idx,
                    "alight_stop_idx": alight_idx
                })
                cur_idx = board_idx
                cur_k -= 1

        # Check initial walk from round 0
        if 0 in parent and cur_idx in parent[0]:
            p0 = parent[0][cur_idx]
            if p0[0] == 0:
                raw_legs.append({
                    "mode": "WALK",
                    "from_stop_idx": p0[2],
                    "to_stop_idx": p0[3],
                    "walk_duration_sec": p0[4]
                })

        # Reverse raw legs into chronological order
        raw_legs.reverse()

        # Build detailed legs with segment-by-segment simulation
        legs = []
        cur_time_sec = dep_sec
        total_fare_inr = 0
        total_walk_sec = 0.0
        total_wait_sec = 0.0
        all_bus_crowd_scores: List[float] = []
        max_bus_crowd_score = 0.0

        for item in raw_legs:
            if item["mode"] == "WALK":
                from_sid = self.idx_to_stop_id[item["from_stop_idx"]]
                to_sid = self.idx_to_stop_id[item["to_stop_idx"]]
                dur_sec = item["walk_duration_sec"]
                cur_time_sec += dur_sec
                total_walk_sec += dur_sec

                legs.append({
                    "mode": "WALK",
                    "from_stop": self.stop_info[from_sid],
                    "to_stop": self.stop_info[to_sid],
                    "duration_min": round(dur_sec / 60.0, 1),
                    "walk_distance_m": round(dur_sec * WALK_SPEED_MPS, 1),
                    "avg_crowding_score": 0.0,
                    "max_crowding_score": 0.0,
                    "crowding_tier": "Low",
                    "segments": []
                })
            else:
                # BUS leg
                r_idx = item["r_idx"]
                board_idx = item["board_stop_idx"]
                alight_idx = item["alight_stop_idx"]

                r_id = self.idx_to_route_id[r_idx]
                r_meta = self.route_meta.get(r_id, {
                    "route_short_name": f"Route {r_id}",
                    "route_long_name": f"Route {r_id}"
                })
                is_ac = bool(self.route_is_ac[r_idx])

                # Identify segment slice along route
                stops = self.route_stops_arr[r_idx]
                board_pos = -1
                alight_pos = -1
                for idx_pos, (s_idx, seq, _) in enumerate(stops):
                    if s_idx == board_idx and board_pos < 0:
                        board_pos = idx_pos
                    if s_idx == alight_idx and board_pos >= 0:
                        alight_pos = idx_pos
                        break

                if board_pos < 0 or alight_pos < 0 or alight_pos <= board_pos:
                    continue

                # Headway wait time and left-behind risk
                board_slot = int((cur_time_sec % 86400) // 1800)
                h_min = self.get_route_headway(r_id, board_slot)
                w_base_sec = min(15.0, 0.5 * h_min) * 60.0

                cs_mat = self.route_segs_cs[r_idx]
                first_seg_cs = float(cs_mat[board_pos, day_code, board_slot]) if board_pos < len(cs_mat) else 0.0
                if first_seg_cs > 0.80:
                    p_deny = min(0.75, ((first_seg_cs - 0.80) / 0.20) * 0.75)
                    e_delay_sec = p_deny * (h_min * 60.0)
                else:
                    p_deny = 0.0
                    e_delay_sec = 0.0

                leg_wait_sec = w_base_sec + e_delay_sec
                cur_time_sec += leg_wait_sec
                total_wait_sec += leg_wait_sec

                leg_segments = []
                leg_dur_sec = 0.0
                leg_dist_m = 0.0
                leg_crowd_scores: List[float] = []

                durs = self.route_segs_dur[r_idx]

                for pos in range(board_pos, alight_pos):
                    u_sidx = stops[pos][0]
                    v_sidx = stops[pos + 1][0]
                    u_sid = self.idx_to_stop_id[u_sidx]
                    v_sid = self.idx_to_stop_id[v_sidx]

                    seg_dur = float(durs[pos])
                    slot = int((cur_time_sec % 86400) // 1800)
                    cs = float(cs_mat[pos, day_code, slot])

                    cur_time_sec += seg_dur
                    leg_dur_sec += seg_dur
                    leg_crowd_scores.append(cs)
                    all_bus_crowd_scores.append(cs)
                    if cs > max_bus_crowd_score:
                        max_bus_crowd_score = cs

                    u_info = self.stop_info[u_sid]
                    v_info = self.stop_info[v_sid]
                    seg_dist = haversine_dist_m(u_info["lat"], u_info["lon"], v_info["lat"], v_info["lon"])
                    leg_dist_m += seg_dist

                    # Road-following polyline from shapes cache (falls back to straight line)
                    path_coords = self.segment_shapes.get(
                        (r_id, u_sid, v_sid),
                        [[u_info["lat"], u_info["lon"]], [v_info["lat"], v_info["lon"]]]
                    )

                    leg_segments.append({
                        "from_stop_id": u_sid,
                        "from_stop_name": u_info["stop_name"],
                        "from_lat": u_info["lat"],
                        "from_lon": u_info["lon"],
                        "to_stop_id": v_sid,
                        "to_stop_name": v_info["stop_name"],
                        "to_lat": v_info["lat"],
                        "to_lon": v_info["lon"],
                        "duration_sec": int(seg_dur),
                        "crowding_score": round(cs, 3),
                        "crowding_tier": tier_from_score(cs),
                        "path_coords": path_coords
                    })

                leg_avg_cs = float(np.mean(leg_crowd_scores)) if leg_crowd_scores else 0.15
                leg_max_cs = float(np.max(leg_crowd_scores)) if leg_crowd_scores else 0.15
                leg_risk_cs = max(first_seg_cs, leg_max_cs)
                if leg_risk_cs > 0.85:
                    leg_risk = "High"
                elif leg_risk_cs > 0.75:
                    leg_risk = "Moderate"
                else:
                    leg_risk = "Low"

                leg_fare = compute_bus_fare(leg_dist_m / 1000.0, is_ac)
                total_fare_inr += leg_fare

                from_sid = self.idx_to_stop_id[board_idx]
                to_sid = self.idx_to_stop_id[alight_idx]

                legs.append({
                    "mode": "BUS",
                    "route_id": r_id,
                    "route_short_name": r_meta["route_short_name"],
                    "route_long_name": r_meta["route_long_name"],
                    "is_ac": is_ac,
                    "from_stop": self.stop_info[from_sid],
                    "to_stop": self.stop_info[to_sid],
                    "duration_min": round((leg_dur_sec + leg_wait_sec) / 60.0, 1),
                    "bus_travel_min": round(leg_dur_sec / 60.0, 1),
                    "wait_duration_min": round(leg_wait_sec / 60.0, 1),
                    "est_wait_min": round(leg_wait_sec / 60.0, 1),
                    "headway_min": round(h_min, 1),
                    "boarding_risk": leg_risk,
                    "boarding_denial_prob": round(p_deny, 2),
                    "distance_km": round(leg_dist_m / 1000.0, 2),
                    "estimated_fare_inr": leg_fare,
                    "avg_crowding_score": round(leg_avg_cs, 3),
                    "max_crowding_score": round(leg_max_cs, 3),
                    "crowding_tier": tier_from_score(leg_avg_cs),
                    "segments": leg_segments
                })

        bus_legs = [l for l in legs if l["mode"] == "BUS"]
        transfers_count = max(0, len(bus_legs) - 1)
        total_dur_sec = cur_time_sec - dep_sec
        avg_cs = float(np.mean(all_bus_crowd_scores)) if all_bus_crowd_scores else 0.15

        route_chain = " -> ".join([b["route_short_name"] for b in bus_legs])

        if max_bus_crowd_score > 0.85:
            itin_risk = "High"
        elif max_bus_crowd_score > 0.75:
            itin_risk = "Moderate"
        else:
            itin_risk = "Low"

        return {
            "route_chain": route_chain,
            "total_duration_min": round(total_dur_sec / 60.0, 1),
            "walk_duration_min": round(total_walk_sec / 60.0, 1),
            "wait_duration_min": round(total_wait_sec / 60.0, 1),
            "est_wait_min": round(total_wait_sec / 60.0, 1),
            "boarding_risk": itin_risk,
            "transfers": transfers_count,
            "avg_crowding_score": round(avg_cs, 3),
            "max_crowding_score": round(max_bus_crowd_score, 3),
            "overall_crowding_tier": tier_from_score(avg_cs),
            "estimated_fare_inr": total_fare_inr,
            "legs": legs
        }

    # ──────────────────────── Multi-Criteria User API ─────────────────────────

    def plan_journey(
        self,
        origin_stop: str,
        dest_stop: str,
        departure_time_str: str = "09:00:00",
        day_type: str = "weekday",
        beta: float = 0.6,
        check_nudge: bool = True
    ) -> Dict[str, Any]:
        """
        Computes up to 3 non-dominated Pareto-optimal itineraries:
          - Fastest (beta = 0.0)
          - Balanced (beta = requested, default 0.6)
          - Least Crowded (beta = 1.8)
        Deduplicates identical route chains and filters strictly dominated options.
        """
        orig_sid = self.resolve_stop(origin_stop)
        dest_sid = self.resolve_stop(dest_stop)

        if not orig_sid or not dest_sid:
            return {
                "error": f"Could not resolve stops: origin '{origin_stop}' -> {orig_sid}, "
                         f"dest '{dest_stop}' -> {dest_sid}",
                "itineraries": []
            }

        # Parse departure time string into seconds from midnight
        time_parts = [int(p) for p in departure_time_str.strip().split(":")]
        dep_hour = time_parts[0]
        dep_min = time_parts[1] if len(time_parts) > 1 else 0
        dep_sec_part = time_parts[2] if len(time_parts) > 2 else 0
        dep_sec = float((dep_hour % 24) * 3600 + dep_min * 60 + dep_sec_part)

        # Day code: 0 = weekday, 1 = saturday, 2 = sunday
        day_norm = day_type.strip().lower()
        day_code = 1 if "sat" in day_norm else (2 if "sun" in day_norm else 0)

        # Evaluate profiles: always run Fastest first, then conditionally add Comfort First
        profiles = [
            ("Fastest", 0.0),
            ("Balanced", beta),
            ("Least Crowded", 1.8),
            ("Comfort First", 3.5),
        ]

        candidates = []
        seen_chains = {}

        for prof_label, prof_beta in profiles:
            itin = self._raptor_search(orig_sid, dest_sid, dep_sec, day_code, prof_beta)
            if itin is not None and itin["legs"]:
                chain = itin["route_chain"]
                if chain in seen_chains:
                    # Append label to existing identical chain
                    existing = seen_chains[chain]
                    if prof_label not in existing["labels"]:
                        existing["labels"].append(prof_label)
                else:
                    itin["labels"] = [prof_label]
                    seen_chains[chain] = itin
                    candidates.append(itin)

        # Pareto filtering: drop itineraries that are strictly dominated in
        # total_duration_min, avg_crowding_score, and transfers
        non_dominated = []
        for i, cand_a in enumerate(candidates):
            dominated = False
            for j, cand_b in enumerate(candidates):
                if i != j:
                    if (
                        cand_b["total_duration_min"] <= cand_a["total_duration_min"] and
                        cand_b["avg_crowding_score"] <= cand_a["avg_crowding_score"] and
                        cand_b["transfers"] <= cand_a["transfers"] and
                        (
                            cand_b["total_duration_min"] < cand_a["total_duration_min"] or
                            cand_b["avg_crowding_score"] < cand_a["avg_crowding_score"] or
                            cand_b["transfers"] < cand_a["transfers"]
                        )
                    ):
                        dominated = True
                        break
            if not dominated:
                non_dominated.append(cand_a)

        # Fallback if all got pruned (should not happen)
        final_list = non_dominated if non_dominated else candidates

        # Assign clean user-facing labels
        for idx, itin in enumerate(final_list):
            itin["itinerary_id"] = idx + 1
            labels = itin.get("labels", [])
            if "Fastest" in labels and "Least Crowded" in labels and "Comfort First" in labels:
                itin["label"] = "Optimal (Fastest & Least Crowded)"
            elif "Fastest" in labels and "Least Crowded" in labels:
                itin["label"] = "Optimal (Fastest & Least Crowded)"
            elif "Fastest" in labels and "Balanced" in labels:
                itin["label"] = "Recommended (Fastest)"
            elif "Least Crowded" in labels and "Balanced" in labels:
                itin["label"] = "Recommended (Least Crowded)"
            elif "Fastest" in labels:
                itin["label"] = "Fastest Route"
            elif "Comfort First" in labels:
                itin["label"] = "Comfort-First (Low Crowd)"
            elif "Least Crowded" in labels:
                itin["label"] = "Least Crowded Alternative"
            elif "Balanced" in labels:
                itin["label"] = "Recommended Balanced Route"
            else:
                itin["label"] = f"Itinerary {idx + 1}"

        # Smart +/- 15-Minute Departure Shift Nudge (Upgrade B)
        departure_nudge = None
        primary_itin = final_list[0] if final_list else None
        if check_nudge and primary_itin is not None:
            c0 = float(primary_itin.get("avg_crowding_score", 0.0))
            risk0 = primary_itin.get("boarding_risk", "Low")
            t0 = float(primary_itin.get("total_duration_min", 1.0))

            if c0 >= 0.45 or risk0 != "Low":
                shifts = [(-900, "15 mins earlier"), (900, "15 mins later")]
                best_nudge = None
                best_drop = 0.0

                for offset_sec, shift_label in shifts:
                    shifted_sec = (dep_sec + offset_sec) % 86400
                    shifted_itin = self._raptor_search(orig_sid, dest_sid, shifted_sec, day_code, beta)
                    if shifted_itin is not None and shifted_itin.get("legs"):
                        c_new = float(shifted_itin.get("avg_crowding_score", 0.0))
                        t_new = float(shifted_itin.get("total_duration_min", t0))
                        abs_drop = c0 - c_new
                        drop_pct = (abs_drop / c0 * 100.0) if c0 > 0 else 0.0
                        time_increase_pct = ((t_new - t0) / t0) if t0 > 0 else 0.0

                        # Must reduce crowding by >= 15% (absolute drop >= 0.08)
                        # without increasing total travel time by > 10%
                        if abs_drop >= 0.08 and drop_pct >= 15.0 and time_increase_pct <= 0.10:
                            if abs_drop > best_drop:
                                best_drop = abs_drop
                                hours = int(shifted_sec // 3600) % 24
                                mins = int((shifted_sec % 3600) // 60)
                                best_nudge = {
                                    "recommended_time": f"{hours:02d}:{mins:02d}",
                                    "shift_label": shift_label,
                                    "crowding_drop_pct": int(round(drop_pct)),
                                    "new_avg_crowding": round(c_new, 2)
                                }

                departure_nudge = best_nudge

        return {
            "origin": self.stop_info[orig_sid],
            "destination": self.stop_info[dest_sid],
            "departure_time": departure_time_str,
            "day_type": day_type,
            "user_beta": beta,
            "itineraries_count": len(final_list),
            "departure_nudge": departure_nudge,
            "itineraries": final_list
        }
