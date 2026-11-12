"""
Sprint 1: GTFS-Ticketing Entity Resolution & Canonical Stop-Sequence Mapping
Transport Stack Hackathon 2026 - Phase 1 (Problem 2)
Crowdedness-Aware Bus Journey Planner for Delhi (DTC/Cluster)

Modules:
  Step A: Canonical Route Stop Sequences (Max stop count trip per route_id)
  Step B: Route Normalization & Route-Scoped Stop Resolution (ETM text normalizer + RapidFuzz)
  Step C: Directional Order & Trip-Leg Validation (orig_seq < dest_seq)
  Step D: Parquet & JSON Artifact Export
"""

import os
import re
import json
import time
from datetime import datetime
import duckdb
import pandas as pd
from rapidfuzz import process, fuzz

def resolve_project_paths():
    """Resolve workspace and dataset paths."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    gtfs_dir = os.path.join(base_dir, "data", "raw", "gtfs", "delhi_buses_static_gtfs_v1")
    if not os.path.exists(os.path.join(gtfs_dir, "routes.txt")):
        gtfs_dir = os.path.join(base_dir, "data", "raw", "gtfs")
        
    csv_candidates = [
        os.path.join(base_dir, "data", "raw", "October-Delhi.csv", "October-Delhi.csv"),
        os.path.join(base_dir, "data", "raw", "October-Delhi.csv")
    ]
    csv_path = None
    for cand in csv_candidates:
        if os.path.isfile(cand):
            csv_path = cand
            break
            
    processed_dir = os.path.join(base_dir, "data", "processed")
    os.makedirs(processed_dir, exist_ok=True)
    
    canonical_parquet = os.path.join(processed_dir, "canonical_route_stops.parquet")
    resolved_tickets_parquet = os.path.join(processed_dir, "resolved_tickets.parquet")
    report_json = os.path.join(processed_dir, "sprint1_resolution_report.json")
    
    return gtfs_dir, csv_path, canonical_parquet, resolved_tickets_parquet, report_json

def normalize_transit_text(text: str) -> str:
    """
    Delhi transit domain text normalizer.
    Expands abbreviations, standardizes transit acronyms, and removes punctuation.
    """
    if not text or pd.isna(text):
        return ""
    t = str(text).lower()
    
    # Standardize phases
    t = re.sub(r'\bph(?:ase)?[- ]?iv\b', 'phase 4', t)
    t = re.sub(r'\bph(?:ase)?[- ]?iii\b', 'phase 3', t)
    t = re.sub(r'\bph(?:ase)?[- ]?ii\b', 'phase 2', t)
    t = re.sub(r'\bph(?:ase)?[- ]?i\b', 'phase 1', t)
    
    # Common ETM transit abbreviations
    t = re.sub(r'\bsec\b|\bsec\.|\bsect\b', 'sector', t)
    t = re.sub(r'\bstn\b|\bstn\.', 'station', t)
    t = re.sub(r'\bxing\b|\bx-ing\b', 'crossing', t)
    t = re.sub(r'\bmkr\b|\bmkt\b|\bmkt\.', 'market', t)
    t = re.sub(r'\bhosp\b|\bhosp\.', 'hospital', t)
    t = re.sub(r'\bvhr\b|\bvhr\.', 'vihar', t)
    t = re.sub(r'\bng\b|\bng\.', 'nagar', t)
    t = re.sub(r'\bextn\b|\bext\b|\bext\.|\bexten\b', 'extension', t)
    t = re.sub(r'\brd\b|\brd\.', 'road', t)
    t = re.sub(r'\bclny\b|\bcol\b', 'colony', t)
    t = re.sub(r'\bdep\b|\bdept\b', 'depot', t)
    t = re.sub(r'\bt-point\b|\bt\.point\b|\bt point\b', 't point', t)
    t = re.sub(r'\(t\)', 'terminal', t)
    t = re.sub(r'\bt\b|\bt\.', 'terminal', t)
    
    # Clean non-alphanumeric except spaces and slashes
    t = re.sub(r'[^a-z0-9\s/]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def build_route_normalizer(gtfs_dir: str, con: duckdb.DuckDBPyConnection):
    """
    Maps ticketing route strings to GTFS route_id and canonical route_short_name.
    """
    print("\n[Step A.1] Building Route Normalization Dictionary from GTFS...")
    routes_sql_path = os.path.join(gtfs_dir, "routes.txt").replace("\\", "/")
    g_routes = con.execute(f"""
        SELECT route_id, route_short_name, route_long_name 
        FROM read_csv_auto('{routes_sql_path}')
    """).fetchall()
    
    gtfs_short_to_meta = {r[1]: (r[0], r[1]) for r in g_routes}
    gtfs_long_to_meta = {r[2]: (r[0], r[1]) for r in g_routes}
    
    def map_route_string(raw_route: str):
        if not raw_route:
            return None, None, "empty"
        r = raw_route.strip()
        
        # 1. Exact match on short name
        if r in gtfs_short_to_meta:
            rid, sname = gtfs_short_to_meta[r]
            return rid, sname, "exact_short"
            
        # 2. Exact match on long name
        if r in gtfs_long_to_meta:
            rid, sname = gtfs_long_to_meta[r]
            return rid, sname, "exact_long"
            
        # 3. Strip trailing numeric trip variant (e.g., 522BDOWN2 -> 522BDOWN)
        r_strip_num = re.sub(r'\d+$', '', r)
        if r_strip_num in gtfs_short_to_meta:
            rid, sname = gtfs_short_to_meta[r_strip_num]
            return rid, sname, "strip_trailing_digits"
            
        # 4. Strip STL before UP/DOWN (e.g., 567BSTLUP -> 567BUP)
        r_strip_stl = re.sub(r'STL(?=UP|DOWN)', '', r)
        if r_strip_stl in gtfs_short_to_meta:
            rid, sname = gtfs_short_to_meta[r_strip_stl]
            return rid, sname, "strip_stl"
            
        # 5. Strip STL and trailing digits
        r_strip_stl_num = re.sub(r'STL(?=UP|DOWN)', '', r_strip_num)
        if r_strip_stl_num in gtfs_short_to_meta:
            rid, sname = gtfs_short_to_meta[r_strip_stl_num]
            return rid, sname, "strip_stl_and_digits"
            
        # 6. Strip LSTL (e.g., 588LSTLDOWN -> 588DOWN)
        r_strip_lstl = re.sub(r'LSTL(?=UP|DOWN)', '', r)
        if r_strip_lstl in gtfs_short_to_meta:
            rid, sname = gtfs_short_to_meta[r_strip_lstl]
            return rid, sname, "strip_lstl"
            
        return None, None, "unmatched"
        
    return map_route_string

def extract_canonical_route_stops(gtfs_dir: str, con: duckdb.DuckDBPyConnection, output_parquet: str):
    """
    Step A: Extract the canonical ordered stop sequence for each route_id.
    Selects the representative trip_id with the maximum stop count per route_id.
    Computes scheduled inter-stop travel duration in seconds.
    """
    print("\n[Step A.2] Extracting Canonical Route Stop Sequences from GTFS...")
    trips_sql_path = os.path.join(gtfs_dir, "trips.txt").replace("\\", "/")
    stop_times_sql_path = os.path.join(gtfs_dir, "stop_times.txt").replace("\\", "/")
    stops_sql_path = os.path.join(gtfs_dir, "stops.txt").replace("\\", "/")
    routes_sql_path = os.path.join(gtfs_dir, "routes.txt").replace("\\", "/")
    out_parquet_sql = output_parquet.replace("\\", "/")
    
    t0 = time.time()
    # Query representative trip with max stops per route_id and compute inter-stop duration
    query = f"""
    WITH trip_counts AS (
        SELECT 
            t.route_id, 
            t.trip_id, 
            COUNT(st.stop_id) AS stop_count
        FROM read_csv_auto('{trips_sql_path}') t
        JOIN read_csv_auto('{stop_times_sql_path}') st ON t.trip_id = st.trip_id
        GROUP BY t.route_id, t.trip_id
    ),
    ranked_trips AS (
        SELECT 
            route_id, 
            trip_id, 
            stop_count,
            ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY stop_count DESC, trip_id ASC) AS rnk
        FROM trip_counts
    ),
    scheduled_stops AS (
        SELECT 
            rt.route_id,
            r.route_short_name,
            r.agency_id,
            rt.trip_id,
            st.stop_sequence,
            s.stop_id,
            s.stop_code,
            s.stop_name,
            CAST(s.stop_lat AS DOUBLE) AS stop_lat,
            CAST(s.stop_lon AS DOUBLE) AS stop_lon,
            st.arrival_time,
            st.departure_time,
            (CAST(SPLIT_PART(st.arrival_time, ':', 1) AS INTEGER) * 3600 + 
             CAST(SPLIT_PART(st.arrival_time, ':', 2) AS INTEGER) * 60 + 
             CAST(SPLIT_PART(st.arrival_time, ':', 3) AS INTEGER)) AS arr_sec,
            (CAST(SPLIT_PART(st.departure_time, ':', 1) AS INTEGER) * 3600 + 
             CAST(SPLIT_PART(st.departure_time, ':', 2) AS INTEGER) * 60 + 
             CAST(SPLIT_PART(st.departure_time, ':', 3) AS INTEGER)) AS dep_sec
        FROM ranked_trips rt
        JOIN read_csv_auto('{routes_sql_path}') r ON rt.route_id = r.route_id
        JOIN read_csv_auto('{stop_times_sql_path}') st ON rt.trip_id = st.trip_id
        JOIN read_csv_auto('{stops_sql_path}') s ON st.stop_id = s.stop_id
        WHERE rt.rnk = 1
    )
    SELECT 
        route_id,
        route_short_name,
        agency_id,
        trip_id,
        stop_sequence,
        stop_id,
        stop_code,
        stop_name,
        stop_lat,
        stop_lon,
        arrival_time,
        departure_time,
        COALESCE(arr_sec - LAG(dep_sec, 1) OVER (PARTITION BY route_id ORDER BY stop_sequence), 0) AS scheduled_travel_sec
    FROM scheduled_stops
    ORDER BY route_id, stop_sequence
    """
    
    # Save canonical parquet
    con.execute(f"COPY ({query}) TO '{out_parquet_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    canonical_df = con.execute(f"SELECT * FROM read_parquet('{out_parquet_sql}')").fetchdf()
    elapsed = time.time() - t0
    
    unique_routes = canonical_df["route_id"].nunique()
    total_stops = len(canonical_df)
    avg_stops = total_stops / unique_routes if unique_routes else 0
    print(f"  Canonical Route Stops Exported: {total_stops:,} rows across {unique_routes:,} routes in {elapsed:.2f}s")
    print(f"  Average stops per route: {avg_stops:.1f} (min {canonical_df.groupby('route_id').size().min()}, max {canonical_df.groupby('route_id').size().max()})")
    print(f"  Saved to: {output_parquet}")
    
    return canonical_df

def resolve_stops_route_scoped(ticketing_pairs, route_map_dict, canonical_df):
    """
    Step B: Route-Scoped Stop Name Resolution.
    Matches unique (route_id, raw_stop_name) pairs against candidate stops of that specific route.
    Uses exact normalized string match, slash-separated token match, and RapidFuzz WRatio / token_sort_ratio (>= 78).
    """
    print("\n[Step B] Executing Route-Scoped Stop Name Resolution...")
    t0 = time.time()
    
    # Pre-index candidate stops by route_id
    # route_id -> (cand_dict, cand_norm_list)
    print("  Pre-indexing route candidate stop dictionaries...")
    route_candidate_index = {}
    for rid, group in canonical_df.groupby("route_id"):
        cand_dict = {}       # norm_string -> (stop_id, stop_sequence, orig_stop_name)
        cand_norm_list = []  # list of norm_strings for rapidfuzz
        
        for _, row in group.iterrows():
            s_id = str(row["stop_id"])
            s_seq = int(row["stop_sequence"])
            s_orig = str(row["stop_name"])
            s_norm = normalize_transit_text(s_orig)
            
            val = (s_id, s_seq, s_orig)
            if s_norm and s_norm not in cand_dict:
                cand_dict[s_norm] = val
                cand_norm_list.append(s_norm)
                
            # If candidate stop name contains slash '/', add each sub-token
            if "/" in s_orig:
                for token in s_orig.split("/"):
                    t_norm = normalize_transit_text(token)
                    if t_norm and t_norm not in cand_dict:
                        cand_dict[t_norm] = val
                        cand_norm_list.append(t_norm)
                        
        route_candidate_index[rid] = (cand_dict, cand_norm_list)
        
    print(f"  Indexed candidate stops for {len(route_candidate_index):,} canonical routes.")
    
    # Process unique (route, raw_stop_name) pairs
    resolved_pairs = []
    exact_count = 0
    fuzzy_count = 0
    unmatched_count = 0
    
    total_pairs = len(ticketing_pairs)
    print(f"  Resolving {total_pairs:,} unique (route, raw_stop) pairs...")
    
    for idx, (route_str, raw_stop) in enumerate(ticketing_pairs):
        # Route mapping
        rid, r_sname, r_method = route_map_dict.get(route_str, (None, None, "unmatched"))
        
        if not rid or rid not in route_candidate_index:
            resolved_pairs.append({
                "route": route_str,
                "raw_stop_name": raw_stop,
                "route_id": rid,
                "stop_id": None,
                "stop_sequence": None,
                "matched_stop_name": None,
                "match_score": 0.0,
                "match_method": "unmatched_route"
            })
            unmatched_count += 1
            continue
            
        cand_dict, cand_norm_list = route_candidate_index[rid]
        
        # Generate query variants (full normalized text, plus slash tokens)
        norm_full = normalize_transit_text(raw_stop)
        q_vars = [norm_full] if norm_full else []
        if "/" in raw_stop:
            for part in raw_stop.split("/"):
                pn = normalize_transit_text(part)
                if pn and pn not in q_vars:
                    q_vars.append(pn)
                    
        match_result = None
        
        # 1. Exact match pass
        for qv in q_vars:
            if qv in cand_dict:
                s_id, s_seq, s_orig = cand_dict[qv]
                match_result = (s_id, s_seq, s_orig, 100.0, "exact")
                exact_count += 1
                break
                
        # 2. Fuzzy match pass (score threshold >= 78)
        if not match_result and cand_norm_list:
            best_score = -1.0
            best_cand_norm = None
            
            for qv in q_vars:
                # WRatio & token_sort_ratio
                res = process.extractOne(qv, cand_norm_list, scorer=fuzz.WRatio)
                if res:
                    m_str, score, _ = res
                    # Also try token_sort_ratio if close
                    ts_score = fuzz.token_sort_ratio(qv, m_str)
                    final_score = max(score, ts_score)
                    if final_score >= 78.0 and final_score > best_score:
                        best_score = final_score
                        best_cand_norm = m_str
                        
            if best_cand_norm:
                s_id, s_seq, s_orig = cand_dict[best_cand_norm]
                match_result = (s_id, s_seq, s_orig, round(best_score, 1), "fuzzy")
                fuzzy_count += 1
                
        if match_result:
            s_id, s_seq, s_orig, score, method = match_result
            resolved_pairs.append({
                "route": route_str,
                "raw_stop_name": raw_stop,
                "route_id": rid,
                "stop_id": s_id,
                "stop_sequence": s_seq,
                "matched_stop_name": s_orig,
                "match_score": score,
                "match_method": method
            })
        else:
            resolved_pairs.append({
                "route": route_str,
                "raw_stop_name": raw_stop,
                "route_id": rid,
                "stop_id": None,
                "stop_sequence": None,
                "matched_stop_name": None,
                "match_score": 0.0,
                "match_method": "unmatched_stop"
            })
            unmatched_count += 1
            
    elapsed = time.time() - t0
    resolved_df = pd.DataFrame(resolved_pairs)
    matched_total = exact_count + fuzzy_count
    match_pct = (matched_total / total_pairs) * 100 if total_pairs else 0
    print(f"  Resolved {total_pairs:,} pairs in {elapsed:.2f}s:")
    print(f"    - Total Matched:  {matched_total:,} ({match_pct:.2f}%)")
    print(f"    - Exact Matched:  {exact_count:,} ({(exact_count*100.0/total_pairs):.2f}%)")
    print(f"    - Fuzzy Matched:  {fuzzy_count:,} ({(fuzzy_count*100.0/total_pairs):.2f}%)")
    print(f"    - Unmatched:      {unmatched_count:,} ({(unmatched_count*100.0/total_pairs):.2f}%)")
    
    return resolved_df

def process_and_validate_tickets(csv_path: str, route_map_df: pd.DataFrame, resolved_stops_df: pd.DataFrame, 
                                 out_tickets_parquet: str, con: duckdb.DuckDBPyConnection):
    """
    Step C: Directional Order & Trip-Leg Validation.
    Maps tickets against resolved route_id, origin_stop_id, destination_stop_id, and checks orig_seq < dest_seq.
    Exports resolved valid tickets to Parquet.
    """
    print("\n[Step C] Directional Order & Trip-Leg Validation (orig_seq < dest_seq)...")
    t0 = time.time()
    csv_sql_path = csv_path.replace("\\", "/")
    out_parquet_sql = out_tickets_parquet.replace("\\", "/")
    
    # Register in-memory tables into DuckDB
    con.register("route_map", route_map_df)
    con.register("stop_map", resolved_stops_df)
    
    # 1. Full ticketing joining query
    join_query = f"""
    CREATE OR REPLACE TEMPORARY TABLE ticket_resolution AS
    SELECT 
        rm.route_id,
        rm.route_short_name,
        t.route AS raw_route,
        sm_orig.stop_sequence AS orig_seq,
        sm_dest.stop_sequence AS dest_seq,
        sm_orig.stop_id AS orig_stop_id,
        sm_dest.stop_id AS dest_stop_id,
        sm_orig.matched_stop_name AS orig_stop_name,
        sm_dest.matched_stop_name AS dest_stop_name,
        t.start_stop_name AS raw_start_stop,
        t.end_stop_name AS raw_end_stop,
        t.passenger_count,
        CASE WHEN UPPER(TRIM(t.vehicle_number)) = 'NULL' THEN NULL ELSE t.vehicle_number END AS vehicle_number,
        t.created_at,
        t.is_ac,
        t.amount,
        t.ticket_type_id
    FROM read_csv_auto('{csv_sql_path}') t
    LEFT JOIN route_map rm ON t.route = rm.raw_route
    LEFT JOIN stop_map sm_orig ON t.route = sm_orig.route AND t.start_stop_name = sm_orig.raw_stop_name
    LEFT JOIN stop_map sm_dest ON t.route = sm_dest.route AND t.end_stop_name = sm_dest.raw_stop_name
    """
    con.execute(join_query)
    
    # 2. Validation breakdown
    val_stats = con.execute("""
    SELECT 
        COUNT(*) AS total_tickets,
        SUM(passenger_count) AS total_passengers,
        
        -- Vehicle Null check (treating literal 'NULL' as null)
        COUNT(CASE WHEN vehicle_number IS NULL THEN 1 END) AS true_vehicle_null_count,
        ROUND(COUNT(CASE WHEN vehicle_number IS NULL THEN 1 END) * 100.0 / COUNT(*), 4) AS true_vehicle_null_pct,
        
        -- Valid forward travel
        COUNT(CASE WHEN orig_seq IS NOT NULL AND dest_seq IS NOT NULL AND orig_seq < dest_seq THEN 1 END) AS valid_forward_tx,
        SUM(CASE WHEN orig_seq IS NOT NULL AND dest_seq IS NOT NULL AND orig_seq < dest_seq THEN passenger_count ELSE 0 END) AS valid_forward_pax,
        
        -- Reversed sequence travel
        COUNT(CASE WHEN orig_seq IS NOT NULL AND dest_seq IS NOT NULL AND orig_seq > dest_seq THEN 1 END) AS reversed_tx,
        SUM(CASE WHEN orig_seq IS NOT NULL AND dest_seq IS NOT NULL AND orig_seq > dest_seq THEN passenger_count ELSE 0 END) AS reversed_pax,
        
        -- Same stop travel
        COUNT(CASE WHEN orig_seq IS NOT NULL AND dest_seq IS NOT NULL AND orig_seq = dest_seq THEN 1 END) AS same_stop_tx,
        SUM(CASE WHEN orig_seq IS NOT NULL AND dest_seq IS NOT NULL AND orig_seq = dest_seq THEN passenger_count ELSE 0 END) AS same_stop_pax,
        
        -- Unresolved routes or stops
        COUNT(CASE WHEN orig_seq IS NULL OR dest_seq IS NULL THEN 1 END) AS unresolved_tx,
        SUM(CASE WHEN orig_seq IS NULL OR dest_seq IS NULL THEN passenger_count ELSE 0 END) AS unresolved_pax
    FROM ticket_resolution
    """).fetchdf().iloc[0].to_dict()
    
    tot_tx = val_stats["total_tickets"]
    tot_pax = val_stats["total_passengers"]
    
    print("\n  Trip-Leg Directional Order Validation Results:")
    print(f"    - Total Ticketing Records:        {int(tot_tx):,}")
    print(f"    - Total Passengers:               {int(tot_pax):,}")
    print(f"    - True Vehicle Number Nulls:      {int(val_stats['true_vehicle_null_count']):,} ({val_stats['true_vehicle_null_pct']:.2f}%)")
    print(f"    - Valid Forward (orig_seq < dest):{int(val_stats['valid_forward_tx']):,} tx ({(val_stats['valid_forward_tx']*100.0/tot_tx):.2f}%) | {int(val_stats['valid_forward_pax']):,} pax ({(val_stats['valid_forward_pax']*100.0/tot_pax):.2f}%)")
    print(f"    - Reversed Seq (orig_seq > dest): {int(val_stats['reversed_tx']):,} tx ({(val_stats['reversed_tx']*100.0/tot_tx):.2f}%) | {int(val_stats['reversed_pax']):,} pax ({(val_stats['reversed_pax']*100.0/tot_pax):.2f}%)")
    print(f"    - Same-Stop Seq (orig_seq = dest):{int(val_stats['same_stop_tx']):,} tx ({(val_stats['same_stop_tx']*100.0/tot_tx):.2f}%) | {int(val_stats['same_stop_pax']):,} pax ({(val_stats['same_stop_pax']*100.0/tot_pax):.2f}%)")
    print(f"    - Unresolved Route/Stop:          {int(val_stats['unresolved_tx']):,} tx ({(val_stats['unresolved_tx']*100.0/tot_tx):.2f}%) | {int(val_stats['unresolved_pax']):,} pax ({(val_stats['unresolved_pax']*100.0/tot_pax):.2f}%)")
    
    # 3. Export valid forward tickets to Parquet
    print(f"\n[Step D] Exporting clean valid forward tickets to {out_tickets_parquet}...")
    export_query = f"""
    COPY (
        SELECT 
            route_id,
            route_short_name,
            orig_seq,
            dest_seq,
            orig_stop_id,
            dest_stop_id,
            passenger_count,
            vehicle_number,
            created_at,
            is_ac,
            amount,
            ticket_type_id
        FROM ticket_resolution
        WHERE orig_seq IS NOT NULL 
          AND dest_seq IS NOT NULL 
          AND orig_seq < dest_seq
        ORDER BY route_id, created_at
    ) TO '{out_parquet_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """
    con.execute(export_query)
    parquet_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out_parquet_sql}')").fetchone()[0]
    print(f"  Exported {parquet_count:,} valid forward tickets in {time.time()-t0:.2f}s")
    
    # 4. Top 15 Unmatched or Anomaly Stop Pairs for inspection
    top_unresolved_pairs = con.execute("""
    SELECT 
        raw_route,
        raw_start_stop,
        raw_end_stop,
        COUNT(*) AS transaction_count,
        SUM(passenger_count) AS passenger_volume,
        CASE 
            WHEN orig_seq IS NULL AND dest_seq IS NULL THEN 'Both Stops Unresolved'
            WHEN orig_seq IS NULL THEN 'Origin Unresolved'
            WHEN dest_seq IS NULL THEN 'Destination Unresolved'
            WHEN orig_seq > dest_seq THEN 'Reversed Sequence'
            WHEN orig_seq = dest_seq THEN 'Same Stop Loop'
            ELSE 'Other'
        END AS anomaly_category
    FROM ticket_resolution
    WHERE orig_seq IS NULL OR dest_seq IS NULL OR orig_seq >= dest_seq
    GROUP BY raw_route, raw_start_stop, raw_end_stop, anomaly_category
    ORDER BY transaction_count DESC
    LIMIT 15
    """).fetchdf()
    
    print("\nTop 15 Unmatched / Anomaly Stop Pairs (for Inspection):")
    print(top_unresolved_pairs.to_string(index=False))
    
    return val_stats, top_unresolved_pairs

def main():
    print("=" * 80)
    print("DELHI CROWD-AWARE BUS PLANNER - SPRINT 1: ENTITY RESOLUTION PIPELINE")
    print("=" * 80)
    start_time = time.time()
    
    gtfs_dir, csv_path, canonical_parquet, resolved_tickets_parquet, report_json = resolve_project_paths()
    print(f"Paths Configured:\n  GTFS:     {gtfs_dir}\n  CSV:      {csv_path}\n  Output 1: {canonical_parquet}\n  Output 2: {resolved_tickets_parquet}\n  Output 3: {report_json}")
    
    con = duckdb.connect()
    
    # Step A.1: Route Normalization Dictionary
    route_mapper = build_route_normalizer(gtfs_dir, con)
    distinct_ticketing_routes = con.execute(f"SELECT DISTINCT route FROM read_csv_auto('{csv_path.replace(os.sep, '/')}') WHERE route IS NOT NULL").fetchall()
    
    route_map_list = []
    route_stats = {"exact_short": 0, "exact_long": 0, "strip_trailing_digits": 0, "strip_stl": 0, "strip_stl_and_digits": 0, "strip_lstl": 0, "unmatched": 0}
    route_map_dict = {}
    
    for (r_str,) in distinct_ticketing_routes:
        rid, sname, method = route_mapper(r_str)
        route_map_dict[r_str] = (rid, sname, method)
        route_stats[method] = route_stats.get(method, 0) + 1
        route_map_list.append({"raw_route": r_str, "route_id": rid, "route_short_name": sname, "route_match_method": method})
        
    route_map_df = pd.DataFrame(route_map_list)
    matched_routes = len(distinct_ticketing_routes) - route_stats.get("unmatched", 0)
    print(f"  Route Normalization Completed: {matched_routes:,} of {len(distinct_ticketing_routes):,} routes mapped ({(matched_routes*100.0/len(distinct_ticketing_routes)):.2f}%)")
    for method, cnt in route_stats.items():
        print(f"    - {method:24}: {cnt} routes")
        
    # Step A.2: Canonical Stop Sequences
    canonical_df = extract_canonical_route_stops(gtfs_dir, con, canonical_parquet)
    
    # Step B: Unique (route, raw_stop_name) extraction & resolution
    print("\n[Step B.1] Extracting Unique (route, raw_stop_name) pairs from Ticketing CSV...")
    csv_sql_path = csv_path.replace("\\", "/")
    unique_pairs_query = f"""
    WITH all_stops AS (
        SELECT route, start_stop_name AS raw_stop_name FROM read_csv_auto('{csv_sql_path}')
        UNION
        SELECT route, end_stop_name AS raw_stop_name FROM read_csv_auto('{csv_sql_path}')
    )
    SELECT route, raw_stop_name FROM all_stops WHERE raw_stop_name IS NOT NULL
    """
    ticketing_pairs = con.execute(unique_pairs_query).fetchall()
    print(f"  Found {len(ticketing_pairs):,} unique (route, raw_stop) pairs in ticketing logs.")
    
    # Execute route-scoped resolution
    resolved_stops_df = resolve_stops_route_scoped(ticketing_pairs, route_map_dict, canonical_df)
    
    # Step C & D: Tickets processing, validation and export
    val_stats, top_unresolved_df = process_and_validate_tickets(
        csv_path, route_map_df, resolved_stops_df, resolved_tickets_parquet, con
    )
    
    # Summary JSON Metrics
    tot_tx = val_stats["total_tickets"]
    tot_pax = val_stats["total_passengers"]
    valid_tx = val_stats["valid_forward_tx"]
    valid_pax = val_stats["valid_forward_pax"]
    
    # Calculate Stop Resolution before / after metrics
    unique_stop_count = len(ticketing_pairs)
    matched_stop_count = len(resolved_stops_df[resolved_stops_df["stop_id"].notna()])
    post_res_stop_match_pct = (matched_stop_count / unique_stop_count) * 100
    
    report_data = {
        "metadata": {
            "sprint": "Sprint 1",
            "pipeline": "src.pipeline.sprint1_entity_resolution",
            "executed_at": datetime.now().isoformat(),
            "status": "COMPLETED"
        },
        "vehicle_number_audit": {
            "true_null_count": int(val_stats["true_vehicle_null_count"]),
            "true_null_pct": float(val_stats["true_vehicle_null_pct"]),
            "domain_note": "Literal 'NULL' strings were correctly identified as true unassigned/missing fleet IDs"
        },
        "route_resolution": {
            "total_ticketing_routes": len(distinct_ticketing_routes),
            "matched_routes": matched_routes,
            "route_match_pct": round((matched_routes * 100.0 / len(distinct_ticketing_routes)), 2),
            "method_breakdown": route_stats
        },
        "stop_resolution": {
            "unique_route_stop_pairs": unique_stop_count,
            "raw_gtfs_exact_match_pct_sprint0": 48.27,
            "post_resolution_stop_match_pct_sprint1": round(post_res_stop_match_pct, 2),
            "exact_matched_pairs": int((resolved_stops_df["match_method"] == "exact").sum()),
            "fuzzy_matched_pairs": int((resolved_stops_df["match_method"] == "fuzzy").sum()),
            "unmatched_pairs": int((resolved_stops_df["stop_id"].isna()).sum())
        },
        "directional_trip_leg_validation": {
            "total_ticketing_records": int(tot_tx),
            "total_passengers": int(tot_pax),
            "valid_forward_trips": {
                "transaction_count": int(valid_tx),
                "transaction_pct": round((valid_tx * 100.0 / tot_tx), 2),
                "passenger_volume": int(valid_pax),
                "passenger_pct": round((valid_pax * 100.0 / tot_pax), 2)
            },
            "reversed_sequence_anomalies": {
                "transaction_count": int(val_stats["reversed_tx"]),
                "transaction_pct": round((val_stats["reversed_tx"] * 100.0 / tot_tx), 2),
                "passenger_volume": int(val_stats["reversed_pax"]),
                "passenger_pct": round((val_stats["reversed_pax"] * 100.0 / tot_pax), 2)
            },
            "same_stop_anomalies": {
                "transaction_count": int(val_stats["same_stop_tx"]),
                "transaction_pct": round((val_stats["same_stop_tx"] * 100.0 / tot_tx), 2),
                "passenger_volume": int(val_stats["same_stop_pax"]),
                "passenger_pct": round((val_stats["same_stop_pax"] * 100.0 / tot_pax), 2)
            },
            "unresolved_records": {
                "transaction_count": int(val_stats["unresolved_tx"]),
                "transaction_pct": round((val_stats["unresolved_tx"] * 100.0 / tot_tx), 2),
                "passenger_volume": int(val_stats["unresolved_pax"]),
                "passenger_pct": round((val_stats["unresolved_pax"] * 100.0 / tot_pax), 2)
            }
        },
        "top_15_unmatched_or_anomaly_pairs": top_unresolved_df.to_dict(orient="records")
    }
    
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)
        
    print("\n" + "=" * 80)
    print("SPRINT 1 SUMMARY METRICS TABLE:")
    print("=" * 80)
    print(f"  * Total Ticketing Records:               {tot_tx:,}")
    print(f"  * True vehicle_number NULL %:            {val_stats['true_vehicle_null_pct']:.2f}% ({int(val_stats['true_vehicle_null_count']):,} records)")
    print(f"  * Route Match Rate:                      {report_data['route_resolution']['route_match_pct']:.2f}% ({matched_routes:,} / {len(distinct_ticketing_routes):,} routes)")
    print(f"  * Stop Resolution Match Rate (Jump):     {report_data['stop_resolution']['raw_gtfs_exact_match_pct_sprint0']:.2f}% (raw) -> {report_data['stop_resolution']['post_resolution_stop_match_pct_sprint1']:.2f}% (post-resolution)")
    print(f"  * Valid Forward Passenger Coverage:      {report_data['directional_trip_leg_validation']['valid_forward_trips']['passenger_pct']:.2f}% ({int(valid_pax):,} / {int(tot_pax):,} pax)")
    print(f"  * Clean Resolved Tickets Exported:       {int(valid_tx):,} records -> {resolved_tickets_parquet}")
    print(f"  * Canonical Route Stops Exported:        {len(canonical_df):,} stops -> {canonical_parquet}")
    print(f"  * Detailed Report Saved:                 {report_json}")
    print(f"  * Total Execution Time:                  {time.time()-start_time:.2f}s")
    print("=" * 80)

if __name__ == "__main__":
    main()
