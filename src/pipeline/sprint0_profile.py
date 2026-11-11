"""
Sprint 0 Data Profiling Pipeline
Transport Stack Hackathon 2026 - Phase 1 (Problem 2)
Crowdedness-Aware Bus Journey Planner for Delhi (DTC/Cluster)
"""

import os
import json
import csv
from datetime import datetime
import duckdb

def resolve_paths():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    # Check GTFS directory
    gtfs_candidates = [
        os.path.join(base_dir, "data", "raw", "gtfs", "delhi_buses_static_gtfs_v1"),
        os.path.join(base_dir, "data", "raw", "gtfs")
    ]
    gtfs_dir = None
    for cand in gtfs_candidates:
        if os.path.exists(os.path.join(cand, "routes.txt")):
            gtfs_dir = cand
            break
            
    # Check October-Delhi.csv
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
    json_out = os.path.join(processed_dir, "sprint0_profile.json")
    
    return gtfs_dir, csv_path, json_out

def profile_gtfs(gtfs_dir):
    print("=" * 70)
    print("GTFS STATIC DATA PROFILING")
    print(f"Directory: {gtfs_dir}")
    print("=" * 70)
    
    gtfs_files = [
        "routes.txt", "stops.txt", "trips.txt", "stop_times.txt", 
        "shapes.txt", "agency.txt", "calendar.txt", "feed_info.txt"
    ]
    gtfs_profile = {}
    
    for filename in gtfs_files:
        fpath = os.path.join(gtfs_dir, filename)
        if not os.path.exists(fpath):
            print(f"[-] {filename}: NOT FOUND")
            continue
            
        file_size = os.path.getsize(fpath)
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                headers = []
            
            samples = []
            row_count = 0
            for row in reader:
                if row_count < 3:
                    samples.append(row)
                row_count += 1
                
        gtfs_profile[filename] = {
            "file_size_bytes": file_size,
            "headers": headers,
            "row_count": row_count,
            "sample_rows": samples
        }
        
        print(f"\n[+] {filename} (Size: {file_size:,} bytes, Rows: {row_count:,})")
        print(f"    Headers: {headers}")
        print("    Sample Rows (First 3):")
        for idx, sample in enumerate(samples, 1):
            print(f"      {idx}. {sample}")
            
    return gtfs_profile

def profile_ticketing(csv_path, gtfs_dir):
    print("\n" + "=" * 70)
    print("OCTOBER-DELHI TICKETING DATA PROFILING (via DuckDB)")
    print(f"CSV Path: {csv_path}")
    print("=" * 70)
    
    csv_sql_path = csv_path.replace("\\", "/")
    routes_gtfs_path = os.path.join(gtfs_dir, "routes.txt").replace("\\", "/")
    trips_gtfs_path = os.path.join(gtfs_dir, "trips.txt").replace("\\", "/")
    stops_gtfs_path = os.path.join(gtfs_dir, "stops.txt").replace("\\", "/")
    
    con = duckdb.connect()
    
    # 1. Column headers and types
    desc = con.execute(f"DESCRIBE SELECT * FROM read_csv_auto('{csv_sql_path}', sample_size=10000)").fetchall()
    columns_info = [{"column_name": row[0], "column_type": row[1], "null": row[2]} for row in desc]
    col_names = [row[0] for row in desc]
    print("\nColumns detected:")
    for col in columns_info:
        print(f"  - {col['column_name']} ({col['column_type']})")
        
    # 2. Total row count, sum passenger_count, min/max created_at, revenue
    agg_query = f"""
    SELECT 
        COUNT(*) AS total_rows,
        SUM(passenger_count) AS total_passenger_count,
        MIN(created_at) AS min_created_at,
        MAX(created_at) AS max_created_at,
        SUM(amount) AS total_revenue,
        AVG(amount) AS avg_fare,
        MIN(amount) AS min_fare,
        MAX(amount) AS max_fare,
        COUNT(CASE WHEN amount = 0 THEN 1 END) AS zero_fare_count,
        AVG(passenger_count) AS avg_passenger_count,
        MIN(passenger_count) AS min_passenger_count,
        MAX(passenger_count) AS max_passenger_count,
        COUNT(CASE WHEN passenger_count = 1 THEN 1 END) AS single_passenger_count,
        COUNT(CASE WHEN passenger_count > 1 THEN 1 END) AS multi_passenger_count,
        COUNT(DISTINCT vehicle_number) AS distinct_vehicles,
        COUNT(DISTINCT route) AS distinct_routes,
        COUNT(DISTINCT start_stop_name) AS distinct_start_stops,
        COUNT(DISTINCT end_stop_name) AS distinct_end_stops
    FROM read_csv_auto('{csv_sql_path}')
    """
    agg = con.execute(agg_query).fetchdf().iloc[0].to_dict()
    
    print("\nOverall Aggregations:")
    print(f"  Total Rows:                {int(agg['total_rows']):,}")
    print(f"  Total Passenger Count:     {int(agg['total_passenger_count']):,}")
    print(f"  Total Fare Amount:         INR {agg['total_revenue']:,.2f}")
    print(f"  Date Range (Min):          {agg['min_created_at']}")
    print(f"  Date Range (Max):          {agg['max_created_at']}")
    print(f"  Distinct Vehicles:         {int(agg['distinct_vehicles']):,}")
    print(f"  Distinct Routes:           {int(agg['distinct_routes']):,}")
    print(f"  Distinct Start Stops:      {int(agg['distinct_start_stops']):,}")
    print(f"  Distinct End Stops:        {int(agg['distinct_end_stops']):,}")
    print(f"  Average Fare / Ticket:     INR {agg['avg_fare']:.2f}")
    print(f"  Average Passengers / Tx:   {agg['avg_passenger_count']:.4f}")
    print(f"  Single Passenger Txs:      {int(agg['single_passenger_count']):,} ({agg['single_passenger_count']*100.0/agg['total_rows']:.2f}%)")
    print(f"  Multi Passenger Txs:       {int(agg['multi_passenger_count']):,} ({agg['multi_passenger_count']*100.0/agg['total_rows']:.2f}%)")
    
    # 3. Exact NULL percentages and empty string checks
    print("\nNull & Blank Percentages per Column:")
    null_exprs = [f"COUNT(CASE WHEN {col} IS NULL THEN 1 END) AS null_{col}" for col in col_names]
    empty_exprs = [f"COUNT(CASE WHEN TRIM(CAST({col} AS VARCHAR)) = '' THEN 1 END) AS empty_{col}" for col in col_names]
    
    quality_query = f"SELECT {', '.join(null_exprs)}, {', '.join(empty_exprs)} FROM read_csv_auto('{csv_sql_path}')"
    q_row = con.execute(quality_query).fetchdf().iloc[0].to_dict()
    
    null_profile = {}
    for col in col_names:
        null_cnt = int(q_row[f"null_{col}"])
        empty_cnt = int(q_row[f"empty_{col}"])
        pct = (null_cnt / agg['total_rows']) * 100
        empty_pct = (empty_cnt / agg['total_rows']) * 100
        null_profile[col] = {
            "null_count": null_cnt,
            "null_pct": round(pct, 4),
            "empty_string_count": empty_cnt,
            "empty_string_pct": round(empty_pct, 4)
        }
        print(f"  - {col:18}: Nulls = {null_cnt:,} ({pct:5.2f}%) | Blank = {empty_cnt:,} ({empty_pct:5.2f}%)")
        
    # 4. Value distributions: is_ac
    print("\nDistribution of is_ac:")
    is_ac_df = con.execute(f"""
        SELECT 
            is_ac, 
            COUNT(*) AS count, 
            ROUND(COUNT(*) * 100.0 / {agg['total_rows']}, 2) AS percentage,
            SUM(passenger_count) as total_passengers
        FROM read_csv_auto('{csv_sql_path}')
        GROUP BY is_ac
        ORDER BY count DESC
    """).fetchdf()
    print(is_ac_df.to_string(index=False))
    
    # 5. Value distributions: ticket_type_id
    ticket_col = "ticket_type_id" if "ticket_type_id" in col_names else "ticket_type"
    print(f"\nDistribution of {ticket_col}:")
    ticket_df = con.execute(f"""
        SELECT 
            {ticket_col}, 
            COUNT(*) AS count, 
            ROUND(COUNT(*) * 100.0 / {agg['total_rows']}, 2) AS percentage,
            SUM(passenger_count) as total_passengers
        FROM read_csv_auto('{csv_sql_path}')
        GROUP BY {ticket_col}
        ORDER BY count DESC
    """).fetchdf()
    print(ticket_df.to_string(index=False))
    
    # 6. Top 15 route strings
    print("\nTop 15 Route Strings in October-Delhi.csv:")
    top_routes_df = con.execute(f"""
        SELECT 
            route, 
            COUNT(*) AS ticket_tx_count, 
            ROUND(COUNT(*) * 100.0 / {agg['total_rows']}, 2) AS percentage,
            SUM(passenger_count) AS total_passengers
        FROM read_csv_auto('{csv_sql_path}')
        GROUP BY route
        ORDER BY ticket_tx_count DESC
        LIMIT 15
    """).fetchdf()
    print(top_routes_df.to_string(index=False))
    
    # 7. Route string analysis vs GTFS routes and trips
    print("\nCross-Validation: Ticketing 'route' vs GTFS routes & trips:")
    gtfs_routes_match = con.execute(f"""
        WITH t_routes AS (
            SELECT DISTINCT route FROM read_csv_auto('{csv_sql_path}') WHERE route IS NOT NULL
        ),
        g_routes AS (
            SELECT 
                route_id, 
                route_short_name, 
                route_long_name 
            FROM read_csv_auto('{routes_gtfs_path}')
        )
        SELECT 
            COUNT(DISTINCT t.route) AS total_ticketing_routes,
            COUNT(DISTINCT CASE WHEN g1.route_short_name IS NOT NULL THEN t.route END) AS match_on_short_name,
            COUNT(DISTINCT CASE WHEN g2.route_long_name IS NOT NULL THEN t.route END) AS match_on_long_name,
            COUNT(DISTINCT CASE WHEN g1.route_short_name IS NOT NULL OR g2.route_long_name IS NOT NULL THEN t.route END) AS match_on_either,
            ROUND(COUNT(DISTINCT CASE WHEN g1.route_short_name IS NOT NULL THEN t.route END) * 100.0 / COUNT(DISTINCT t.route), 2) AS match_percentage
        FROM t_routes t
        LEFT JOIN g_routes g1 ON t.route = g1.route_short_name
        LEFT JOIN g_routes g2 ON t.route = g2.route_long_name
    """).fetchdf()
    print(gtfs_routes_match.to_string(index=False))
    
    # Passenger & tx volume coverage of matched routes
    volume_coverage = con.execute(f"""
        WITH t_routes AS (
            SELECT route, count(*) as tx_count, sum(passenger_count) as total_pax
            FROM read_csv_auto('{csv_sql_path}')
            GROUP BY route
        ),
        g_routes AS (
            SELECT DISTINCT route_short_name FROM read_csv_auto('{routes_gtfs_path}')
        )
        SELECT 
            COUNT(CASE WHEN g.route_short_name IS NOT NULL THEN 1 END) as matched_routes_count,
            COUNT(CASE WHEN g.route_short_name IS NULL THEN 1 END) as unmatched_routes_count,
            SUM(CASE WHEN g.route_short_name IS NOT NULL THEN t.tx_count ELSE 0 END) as matched_tx_count,
            SUM(CASE WHEN g.route_short_name IS NULL THEN t.tx_count ELSE 0 END) as unmatched_tx_count,
            ROUND(SUM(CASE WHEN g.route_short_name IS NOT NULL THEN t.tx_count ELSE 0 END) * 100.0 / SUM(t.tx_count), 2) as matched_tx_pct,
            ROUND(SUM(CASE WHEN g.route_short_name IS NOT NULL THEN t.total_pax ELSE 0 END) * 100.0 / SUM(t.total_pax), 2) as matched_pax_pct
        FROM t_routes t
        LEFT JOIN g_routes g ON t.route = g.route_short_name
    """).fetchdf()
    print("\nVolume Coverage of Matched Routes:")
    print(volume_coverage.to_string(index=False))
    
    # Direction ID in trips.txt
    trips_direction_dist = con.execute(f"""
        SELECT 
            direction_id, 
            COUNT(*) AS trip_count 
        FROM read_csv_auto('{trips_gtfs_path}', all_varchar=true)
        GROUP BY direction_id
    """).fetchdf()
    print("\nDirection ID distribution in trips.txt:")
    print(trips_direction_dist.to_string(index=False))
    
    # Ticketing Route Suffix Breakdown
    route_suffix_df = con.execute(f"""
        WITH t_routes AS (
            SELECT DISTINCT route FROM read_csv_auto('{csv_sql_path}') WHERE route IS NOT NULL
        )
        SELECT 
            CASE 
                WHEN route LIKE '%UP' THEN 'Ends with UP'
                WHEN route LIKE '%DOWN' THEN 'Ends with DOWN'
                WHEN route LIKE '%DOW' THEN 'Ends with DOW'
                WHEN route LIKE '%U' THEN 'Ends with U'
                ELSE 'Other / No Suffix'
            END AS direction_suffix,
            COUNT(*) AS distinct_routes
        FROM t_routes
        GROUP BY 1
        ORDER BY distinct_routes DESC
    """).fetchdf()
    print("\nTicketing Route Direction Suffix Breakdown:")
    print(route_suffix_df.to_string(index=False))
    
    # 8. Stop Name Match against GTFS stops.txt
    stop_match_df = con.execute(f"""
        WITH t_stops AS (
            SELECT DISTINCT start_stop_name AS stop_name FROM read_csv_auto('{csv_sql_path}')
            UNION
            SELECT DISTINCT end_stop_name AS stop_name FROM read_csv_auto('{csv_sql_path}')
        ),
        g_stops AS (
            SELECT DISTINCT stop_name FROM read_csv_auto('{stops_gtfs_path}')
        )
        SELECT 
            COUNT(t.stop_name) AS total_ticketing_stops,
            COUNT(g.stop_name) AS exact_case_insensitive_matched,
            ROUND(COUNT(g.stop_name) * 100.0 / COUNT(t.stop_name), 2) AS match_pct
        FROM t_stops t
        LEFT JOIN g_stops g ON LOWER(TRIM(t.stop_name)) = LOWER(TRIM(g.stop_name))
    """).fetchdf()
    print("\nStop Name Matching with GTFS stops.txt:")
    print(stop_match_df.to_string(index=False))
    
    ticketing_profile = {
        "csv_path": csv_path,
        "aggregations": {
            "total_rows": int(agg["total_rows"]),
            "total_passenger_count": int(agg["total_passenger_count"]),
            "total_revenue_inr": float(agg["total_revenue"]),
            "avg_fare_inr": float(agg["avg_fare"]),
            "min_fare_inr": float(agg["min_fare"]),
            "max_fare_inr": float(agg["max_fare"]),
            "zero_fare_count": int(agg["zero_fare_count"]),
            "avg_passenger_count": float(agg["avg_passenger_count"]),
            "single_passenger_txs": int(agg["single_passenger_count"]),
            "multi_passenger_txs": int(agg["multi_passenger_count"]),
            "distinct_vehicles": int(agg["distinct_vehicles"]),
            "distinct_routes": int(agg["distinct_routes"]),
            "distinct_start_stops": int(agg["distinct_start_stops"]),
            "distinct_end_stops": int(agg["distinct_end_stops"]),
            "date_range": {
                "min": str(agg["min_created_at"]),
                "max": str(agg["max_created_at"])
            }
        },
        "columns": columns_info,
        "null_and_quality_analysis": null_profile,
        "is_ac_distribution": is_ac_df.to_dict(orient="records"),
        "ticket_type_distribution": ticket_df.to_dict(orient="records"),
        "top_15_routes": top_routes_df.to_dict(orient="records"),
        "gtfs_route_matching": gtfs_routes_match.to_dict(orient="records")[0],
        "volume_coverage": volume_coverage.to_dict(orient="records")[0],
        "trips_direction_distribution": trips_direction_dist.to_dict(orient="records"),
        "route_suffix_distribution": route_suffix_df.to_dict(orient="records"),
        "stop_matching": stop_match_df.to_dict(orient="records")[0]
    }
    
    return ticketing_profile

def main():
    print("=" * 70)
    print("STARTING SPRINT 0 PROFILING: DELHI BUS DATASET & GTFS")
    print("=" * 70)
    
    gtfs_dir, csv_path, json_out = resolve_paths()
    print(f"Base directories resolved:\n  GTFS: {gtfs_dir}\n  CSV:  {csv_path}\n  OUT:  {json_out}\n")
    
    if not gtfs_dir or not os.path.exists(gtfs_dir):
        raise FileNotFoundError(f"GTFS directory could not be located at {gtfs_dir}")
    if not csv_path or not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Ticketing CSV could not be located at {csv_path}")
        
    gtfs_profile = profile_gtfs(gtfs_dir)
    ticketing_profile = profile_ticketing(csv_path, gtfs_dir)
    
    combined_summary = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "script": "src/pipeline/sprint0_profile.py",
            "project": "Crowdedness-Aware Bus Journey Planner for Delhi (Transport Stack Hackathon 2026 - Problem 2)"
        },
        "gtfs_profile": gtfs_profile,
        "ticketing_profile": ticketing_profile
    }
    
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(combined_summary, f, indent=2, default=str)
        
    print("\n" + "=" * 70)
    print(f"SUCCESS: Machine-readable summary saved to:\n  {json_out}")
    print("=" * 70)

if __name__ == "__main__":
    main()
