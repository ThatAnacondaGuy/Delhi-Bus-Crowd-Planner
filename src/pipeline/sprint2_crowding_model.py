"""
Sprint 2: Passenger Flow Reconstruction & Bus Load Factor Modeling
Transport Stack Hackathon 2026 — Phase 1 (Problem 2)
Crowdedness-Aware Bus Journey Planner for Delhi (DTC/Cluster)

Steps:
  A: Temporal bucketing (day_type, time_slot) + dominant AC mode per route
  B: OD→Segment flow reconstruction via vectorised pandas difference-array
  C: Supply normalisation, NULL-vehicle calibration, Pax/Bus & crowding_score
  D: Automated diurnal spot-check & directional asymmetry validation
  E: Parquet + JSON artefact export
"""

import os
import json
import math
import time
from datetime import datetime

import duckdb
import pandas as pd

# ─────────────────────────── paths ────────────────────────────────────────────

def resolve_paths():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    gtfs = os.path.join(base, "data", "raw", "gtfs", "delhi_buses_static_gtfs_v1")
    proc = os.path.join(base, "data", "processed")
    os.makedirs(proc, exist_ok=True)
    return {
        "base"           : base,
        "gtfs"           : gtfs,
        "tickets"        : os.path.join(proc, "resolved_tickets.parquet"),
        "canon"          : os.path.join(proc, "canonical_route_stops.parquet"),
        "trips_txt"      : os.path.join(gtfs, "trips.txt"),
        "stop_times_txt" : os.path.join(gtfs, "stop_times.txt"),
        "seg_crowd"      : os.path.join(proc, "segment_crowding.parquet"),
        "val_report"     : os.path.join(proc, "sprint2_validation_report.json"),
    }

# ─────────────────────── calibration constants ────────────────────────────────

KAPPA          = 25.0   # penetration-rate inverse: e-ticket share ≈ 4%
CAP_AC         = 70     # seated + standing, AC low-floor
CAP_NON_AC     = 65     # Non-AC standard
NULL_VEH_RATE  = 0.4852 # fraction of records with literal 'NULL' vehicle_number
DAY_COUNTS     = {"weekday": 22, "saturday": 5, "sunday": 4}

def load_ratio_to_crowding(L: float) -> float:
    """
    Sigmoid centred at L=0.65 (bus roughly 60% full after kappa scaling).
    L=0 → 0.00 | L=0.65 → ≈0.50 | L=1.0 → 0.75 | L≥1.4 → 0.93+
    Anchored so that L=0 maps exactly to 0.0.
    """
    base  = 1.0 / (1.0 + math.exp(-3.5 * (-0.65)))
    val   = 1.0 / (1.0 + math.exp(-3.5 * (L  - 0.65)))
    score = (val - base) / (1.0 - base)
    return float(max(0.0, min(1.0, score)))

def tier(cs: float) -> str:
    if cs < 0.35:
        return "Low"
    elif cs <= 0.70:
        return "Moderate"
    return "High"

# ───────────────────────────── Step A ─────────────────────────────────────────

def step_a(con: duckdb.DuckDBPyConnection, paths: dict) -> dict:
    """
    Temporal bucketing verification + dominant AC mode per route_id.
    Returns ac_map dict (route_id → bool) and all_routes DataFrame.
    """
    print("\n[Step A] Temporal bucketing & dominant AC mode …")
    t0  = time.time()
    tkt = paths["tickets"].replace("\\", "/")

    # Day-type date distribution check
    day_counts = con.execute(f"""
        SELECT
            CASE WHEN EXTRACT(DOW FROM created_at) = 0 THEN 'sunday'
                 WHEN EXTRACT(DOW FROM created_at) = 6 THEN 'saturday'
                 ELSE 'weekday' END AS day_type,
            COUNT(DISTINCT CAST(created_at AS DATE)) AS distinct_dates
        FROM read_parquet('{tkt}')
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    print("  October 2026 operational dates by day_type:")
    print(day_counts.to_string(index=False))

    # Dominant AC mode per route
    ac_df = con.execute(f"""
        SELECT
            CAST(route_id AS BIGINT) AS route_id,
            CASE WHEN SUM(CASE WHEN is_ac THEN 1 ELSE 0 END) >= COUNT(*) / 2.0
                 THEN TRUE ELSE FALSE END AS is_ac
        FROM read_parquet('{tkt}')
        WHERE route_id IS NOT NULL
        GROUP BY route_id
    """).fetchdf()

    ac_map = {int(r): bool(a) for r, a in zip(ac_df["route_id"], ac_df["is_ac"])}

    # All canonical routes (may include routes with zero e-tickets)
    all_routes = con.execute(f"""
        SELECT DISTINCT CAST(route_id AS BIGINT) AS route_id, route_short_name
        FROM read_parquet('{paths["canon"].replace(chr(92), "/")}')
    """).fetchdf()
    all_routes["is_ac"] = all_routes["route_id"].apply(lambda r: ac_map.get(int(r), True))

    print(f"  Dominant AC flag assigned to {len(all_routes):,} canonical routes in {time.time()-t0:.2f}s")
    return {"ac_map": ac_map, "all_routes": all_routes}

# ───────────────────────────── Step B ─────────────────────────────────────────

def step_b(con: duckdb.DuckDBPyConnection, paths: dict) -> pd.DataFrame:
    """
    OD → Segment flow via pandas vectorised difference-array.

    For each (route_id, day_type, time_slot):
      • Emit +pax at orig_seq (boarding) and -pax at dest_seq (alighting)
      • Group & cumulative-sum over stop_sequence → in-vehicle pax per segment
    Memory-safe: canonical segments ≈ 80k rows × deltas ≈ 1.2M rows (no CROSS JOIN).
    """
    print("\n[Step B] OD→Segment difference-array expansion (pandas) …")
    t0  = time.time()
    tkt   = paths["tickets"].replace("\\", "/")
    canon = paths["canon"].replace("\\", "/")

    # -- Load canonical segments (adjacent stop pairs) -------------------------
    canon_segs = con.execute(f"""
        SELECT
            CAST(route_id AS BIGINT) AS route_id,
            stop_sequence            AS from_seq,
            LEAD(stop_sequence) OVER (PARTITION BY route_id ORDER BY stop_sequence) AS to_seq,
            CAST(stop_id AS VARCHAR) AS from_stop_id,
            LEAD(CAST(stop_id AS VARCHAR)) OVER (PARTITION BY route_id ORDER BY stop_sequence) AS to_stop_id,
            scheduled_travel_sec
        FROM read_parquet('{canon}')
        ORDER BY route_id, stop_sequence
    """).fetchdf()
    canon_segs = canon_segs.dropna(subset=["to_seq"]).copy()
    canon_segs["route_id"] = canon_segs["route_id"].astype(int)
    canon_segs["from_seq"] = canon_segs["from_seq"].astype(int)
    canon_segs["to_seq"]   = canon_segs["to_seq"].astype(int)
    print(f"  Canonical segments: {len(canon_segs):,}")

    # -- Aggregate OD buckets from resolved tickets ----------------------------
    od_df = con.execute(f"""
        SELECT
            CAST(route_id AS BIGINT) AS route_id,
            CASE WHEN EXTRACT(DOW FROM created_at) = 0 THEN 'sunday'
                 WHEN EXTRACT(DOW FROM created_at) = 6 THEN 'saturday'
                 ELSE 'weekday' END AS day_type,
            CAST(
                EXTRACT(HOUR FROM created_at) * 2 +
                CASE WHEN EXTRACT(MINUTE FROM created_at) >= 30 THEN 1 ELSE 0 END
            AS INTEGER)              AS time_slot,
            CAST(orig_seq AS INTEGER) AS orig_seq,
            CAST(dest_seq AS INTEGER) AS dest_seq,
            SUM(passenger_count)      AS total_pax
        FROM read_parquet('{tkt}')
        WHERE route_id IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5
    """).fetchdf()
    print(f"  OD buckets: {len(od_df):,}")

    # -- Build difference-array delta rows ------------------------------------
    boarding  = od_df[["route_id","day_type","time_slot","orig_seq","total_pax"]].rename(
                    columns={"orig_seq": "seq", "total_pax": "delta"})
    alighting = od_df[["route_id","day_type","time_slot","dest_seq","total_pax"]].rename(
                    columns={"dest_seq": "seq", "total_pax": "delta"})
    alighting = alighting.copy()
    alighting["delta"] = -alighting["delta"]

    deltas = pd.concat([boarding, alighting], ignore_index=True)
    deltas = deltas.groupby(["route_id","day_type","time_slot","seq"],
                            as_index=False)["delta"].sum()
    print(f"  Net delta rows: {len(deltas):,}")

    # -- Merge onto canonical segments & cumulative sum ------------------------
    merged = canon_segs.merge(
        deltas.rename(columns={"seq": "from_seq"}),
        on=["route_id", "from_seq"],
        how="left"
    )
    merged["delta"] = merged["delta"].fillna(0.0)
    merged.sort_values(["route_id","day_type","time_slot","from_seq"], inplace=True)
    merged["cumulative_pax_oct"] = (
        merged.groupby(["route_id","day_type","time_slot"])["delta"]
              .cumsum()
              .clip(lower=0.0)
    )

    # Keep only rows where we actually have a day_type (drop segments
    # that were left-joined with no ticket data at all)
    seg_flow = merged.dropna(subset=["day_type"]).copy()
    print(f"  Segment-flow rows: {len(seg_flow):,} in {time.time()-t0:.2f}s")

    # Sample validation
    sample = seg_flow[
        (seg_flow["route_id"] == 2171) &
        (seg_flow["day_type"] == "weekday") &
        (seg_flow["time_slot"] == 18)
    ][["from_seq","to_seq","cumulative_pax_oct"]].head(5)
    print("  Sample — route 2171 (717AUP) weekday 09:00–09:30:")
    print(sample.to_string(index=False))

    return seg_flow

# ───────────────────────────── Step C ─────────────────────────────────────────

def step_c(con: duckdb.DuckDBPyConnection, paths: dict,
           seg_flow: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """
    Supply normalisation, NULL-vehicle calibration, crowding_score sigmoid mapping.
    """
    print("\n[Step C] Supply normalisation & crowding score computation …")
    t0 = time.time()

    ac_map = meta["ac_map"]
    trips_p  = paths["trips_txt"].replace("\\", "/")
    stimes_p = paths["stop_times_txt"].replace("\\", "/")
    tkt_p    = paths["tickets"].replace("\\", "/")
    canon_p  = paths["canon"].replace("\\", "/")

    # -- C1: GTFS scheduled trips per (route_id, time_slot) -------------------
    print("  C1: GTFS scheduled trips per (route_id, time_slot) …")
    gtfs_supply = con.execute(f"""
        SELECT
            CAST(t.route_id AS BIGINT) AS route_id,
            CAST(
                (CAST(SPLIT_PART(fs.departure_time, ':', 1) AS INTEGER) % 24) * 2 +
                CASE WHEN CAST(SPLIT_PART(fs.departure_time, ':', 2) AS INTEGER) >= 30
                     THEN 1 ELSE 0 END
            AS INTEGER) AS time_slot,
            COUNT(t.trip_id) AS gtfs_trips_in_slot
        FROM read_csv_auto('{trips_p}') t
        JOIN (
            SELECT trip_id, departure_time,
                   ROW_NUMBER() OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS rnk
            FROM read_csv_auto('{stimes_p}')
        ) fs ON t.trip_id = fs.trip_id AND fs.rnk = 1
        GROUP BY 1, 2
    """).fetchdf()
    gtfs_supply["route_id"] = gtfs_supply["route_id"].astype(int)
    gtfs_supply["time_slot"] = gtfs_supply["time_slot"].astype(int)
    print(f"     GTFS supply rows: {len(gtfs_supply):,}")

    # -- C2: Empirical active buses (NULL-corrected) ---------------------------
    print("  C2: empirical active bus counts (NULL-corrected) …")
    empirical = con.execute(f"""
        SELECT
            CAST(route_id AS BIGINT) AS route_id,
            CASE WHEN EXTRACT(DOW FROM created_at) = 0 THEN 'sunday'
                 WHEN EXTRACT(DOW FROM created_at) = 6 THEN 'saturday'
                 ELSE 'weekday' END AS day_type,
            CAST(
                EXTRACT(HOUR FROM created_at) * 2 +
                CASE WHEN EXTRACT(MINUTE FROM created_at) >= 30 THEN 1 ELSE 0 END
            AS INTEGER) AS time_slot,
            CEIL(
                COUNT(DISTINCT CASE WHEN vehicle_number IS NOT NULL
                                    AND vehicle_number != ''
                                    THEN vehicle_number END)
                / (1.0 - {NULL_VEH_RATE})
            ) AS est_active_buses
        FROM read_parquet('{tkt_p}')
        WHERE route_id IS NOT NULL
        GROUP BY 1, 2, 3
    """).fetchdf()
    empirical["route_id"]  = empirical["route_id"].astype(int)
    empirical["time_slot"] = empirical["time_slot"].astype(int)
    print(f"     Empirical supply rows: {len(empirical):,}")

    # -- C3: Merge supply into seg_flow ----------------------------------------
    print("  C3: merging supply into segment flow …")
    df = seg_flow.copy()
    df["route_id"] = df["route_id"].astype(int)

    # Daily average pax on segment in slot
    df["days_in_month"] = df["day_type"].map(DAY_COUNTS).astype(float)
    df["daily_seg_pax"] = df["cumulative_pax_oct"] / df["days_in_month"]

    # Join GTFS supply
    df = df.merge(gtfs_supply[["route_id","time_slot","gtfs_trips_in_slot"]],
                  on=["route_id","time_slot"], how="left")
    # Join empirical supply
    df = df.merge(empirical[["route_id","day_type","time_slot","est_active_buses"]],
                  on=["route_id","day_type","time_slot"], how="left")

    # Best trip frequency estimate: GTFS first, then empirical, then 0.5 fallback
    df["trips_per_slot"] = df["gtfs_trips_in_slot"].fillna(0.0)
    mask_zero = df["trips_per_slot"] == 0.0
    df.loc[mask_zero, "trips_per_slot"] = df.loc[mask_zero, "est_active_buses"].fillna(0.0)
    df.loc[df["trips_per_slot"] == 0.0, "trips_per_slot"] = 0.5

    # AC flag
    df["is_ac"] = df["route_id"].apply(lambda r: ac_map.get(int(r), True))

    # -- C4: Compute est_pax_per_bus & crowding score -------------------------
    print("  C4: computing est_pax_per_bus & sigmoid crowding score …")
    df["est_pax_per_bus"] = (df["daily_seg_pax"] / df["trips_per_slot"]) * KAPPA

    cap = df["is_ac"].map({True: float(CAP_AC), False: float(CAP_NON_AC)}).fillna(float(CAP_AC))
    df["load_ratio"]     = (df["est_pax_per_bus"] / cap).clip(lower=0.0)
    df["crowding_score"] = df["load_ratio"].apply(load_ratio_to_crowding)
    df["crowding_tier"]  = df["crowding_score"].apply(tier)

    print(f"  Segment crowding table: {len(df):,} rows in {time.time()-t0:.2f}s")

    # -- C5: Baseline prior for zero-ticket canonical routes ------------------
    print("  C5: inserting baseline priors for zero-ticket routes …")
    covered = set(df["route_id"].unique().tolist())
    all_canon = con.execute(f"""
        SELECT DISTINCT CAST(route_id AS BIGINT) AS route_id
        FROM read_parquet('{canon_p}')
    """).fetchdf()["route_id"].astype(int).tolist()

    missing = [r for r in all_canon if r not in covered]

    if missing:
        # Load segments for missing routes
        missing_str = ",".join(str(r) for r in missing)
        syn_segs = con.execute(f"""
            SELECT
                CAST(route_id AS BIGINT) AS route_id,
                stop_sequence AS from_seq,
                LEAD(stop_sequence) OVER (PARTITION BY route_id ORDER BY stop_sequence) AS to_seq,
                CAST(stop_id AS VARCHAR) AS from_stop_id,
                LEAD(CAST(stop_id AS VARCHAR)) OVER (PARTITION BY route_id ORDER BY stop_sequence) AS to_stop_id,
                scheduled_travel_sec
            FROM read_parquet('{canon_p}')
            WHERE CAST(route_id AS BIGINT) IN ({missing_str})
            ORDER BY route_id, stop_sequence
        """).fetchdf()
        syn_segs = syn_segs.dropna(subset=["to_seq"])

        syn_rows = []
        for _, row in syn_segs.iterrows():
            rid = int(row["route_id"])
            ac  = True  # default AC for unobserved routes
            for dt in ["weekday", "saturday", "sunday"]:
                # Peak slot: cs=0.20 | Off-peak: cs=0.10
                for ts, cs in [(18, 0.20), (26, 0.10)]:
                    syn_rows.append({
                        "route_id"            : rid,
                        "day_type"            : dt,
                        "time_slot"           : ts,
                        "from_seq"            : int(row["from_seq"]),
                        "to_seq"              : int(row["to_seq"]),
                        "from_stop_id"        : str(row["from_stop_id"]),
                        "to_stop_id"          : str(row["to_stop_id"]),
                        "scheduled_travel_sec": int(row["scheduled_travel_sec"] or 0),
                        "daily_seg_pax"       : 0.0,
                        "trips_per_slot"      : 1.0,
                        "is_ac"               : ac,
                        "est_pax_per_bus"     : 0.0,
                        "load_ratio"          : 0.4 if ts == 18 else 0.2,
                        "crowding_score"      : cs,
                        "crowding_tier"       : tier(cs),
                    })

        if syn_rows:
            syn_df = pd.DataFrame(syn_rows)
            df = pd.concat([df, syn_df], ignore_index=True)
            print(f"  Added {len(syn_df):,} baseline rows for {len(missing):,} zero-ticket routes")

    return df

# ───────────────────────────── Step D ─────────────────────────────────────────

WINDOW_SLOTS = {
    "Early Morning (05:00–07:30)"  : list(range(10, 15)),   # slots 10..14
    "Morning Peak  (08:30–10:30)"  : list(range(17, 21)),   # slots 17..20
    "Afternoon Lull(13:00–15:30)"  : list(range(26, 31)),   # slots 26..30
    "Evening Peak  (17:30–20:00)"  : list(range(35, 40)),   # slots 35..39
    "Late Night    (21:30–23:30)"  : list(range(43, 47)),   # slots 43..46
}

def step_d(df: pd.DataFrame) -> dict:
    """
    Diurnal spot-check: network-wide mean & p90 crowding score per time window.
    Directional asymmetry: UP vs DOWN for top routes, Morning vs Evening peak.
    """
    print("\n[Step D] Diurnal spot-check & directional asymmetry validation …")

    # Merge route_short_name back for asymmetry lookup
    if "route_short_name" not in df.columns:
        # It was dropped; skip asymmetry (shouldn't happen)
        rsn_available = False
    else:
        rsn_available = True

    weekday = df[df["day_type"] == "weekday"].copy()

    # Network-wide diurnal
    diurnal = {}
    print("\n  Network-wide crowding by time window (weekday):")
    print(f"  {'Window':<35} {'Mean CS':>8} {'P90 CS':>8} {'L%':>5} {'M%':>5} {'H%':>5}")
    print("  " + "-" * 72)

    for window, slots in WINDOW_SLOTS.items():
        sub = weekday[weekday["time_slot"].isin(slots)]
        if sub.empty:
            continue
        mean_cs = sub["crowding_score"].mean()
        p90_cs  = sub["crowding_score"].quantile(0.90)
        tc      = sub["crowding_tier"].value_counts().to_dict()
        total   = max(sum(tc.values()), 1)
        L = tc.get("Low", 0) * 100 // total
        M = tc.get("Moderate", 0) * 100 // total
        H = tc.get("High", 0) * 100 // total
        print(f"  {window:<35} {mean_cs:>8.3f} {p90_cs:>8.3f} {L:>4}% {M:>4}% {H:>4}%")
        diurnal[window] = {
            "mean_crowding_score": round(float(mean_cs), 4),
            "p90_crowding_score" : round(float(p90_cs),  4),
            "tier_pct_Low"       : round(tc.get("Low", 0) * 100 / total, 1),
            "tier_pct_Moderate"  : round(tc.get("Moderate", 0) * 100 / total, 1),
            "tier_pct_High"      : round(tc.get("High", 0) * 100 / total, 1),
        }

    # Directional asymmetry
    asym = {}
    route_pairs = [
        ("717AUP",  "717ADOWN"),
        ("729UP",   "729DOWN"),
        ("511AUP",  "511ADOWN"),
        ("578UP",   "578DOWN"),
    ]
    morn_slots = WINDOW_SLOTS["Morning Peak  (08:30–10:30)"]
    eve_slots  = WINDOW_SLOTS["Evening Peak  (17:30–20:00)"]

    if rsn_available:
        print("\n  Directional asymmetry — Morning Peak vs Evening Peak (weekday):")
        hdr = f"  {'Route Pair':<22} {'Morn UP':>8} {'Morn DN':>8} {'Eve UP':>8} {'Eve DN':>8}"
        print(hdr)
        print("  " + "-" * 60)

        for r_up, r_dn in route_pairs:
            def cs_mean(r, slots):
                s = weekday[(weekday["route_short_name"] == r) &
                            (weekday["time_slot"].isin(slots))]["crowding_score"]
                return s.mean() if len(s) > 0 else None

            up_m = cs_mean(r_up, morn_slots)
            dn_m = cs_mean(r_dn, morn_slots)
            up_e = cs_mean(r_up, eve_slots)
            dn_e = cs_mean(r_dn, eve_slots)

            fmt = lambda v: f"{v:.3f}" if v is not None else "  N/A"
            print(f"  {r_up+'/'+r_dn:<22} {fmt(up_m):>8} {fmt(dn_m):>8} {fmt(up_e):>8} {fmt(dn_e):>8}")
            asym[f"{r_up}/{r_dn}"] = {
                "morning_peak_UP"  : round(float(up_m), 4) if up_m is not None else None,
                "morning_peak_DOWN": round(float(dn_m), 4) if dn_m is not None else None,
                "evening_peak_UP"  : round(float(up_e), 4) if up_e is not None else None,
                "evening_peak_DOWN": round(float(dn_e), 4) if dn_e is not None else None,
            }

    # Overall tier distribution
    tier_overall = df["crowding_tier"].value_counts().to_dict()
    total_all    = max(sum(tier_overall.values()), 1)
    print("\n  Overall tier distribution (all day_types, all routes, all slots):")
    for t_name in ["Low", "Moderate", "High"]:
        cnt = tier_overall.get(t_name, 0)
        print(f"    {t_name:8}: {cnt:>8,} ({cnt * 100.0 / total_all:.1f}%)")

    return {
        "diurnal_windows"           : diurnal,
        "directional_asymmetry"     : asym,
        "overall_tier_distribution" : {
            k: {"count": int(v), "pct": round(v * 100.0 / total_all, 2)}
            for k, v in tier_overall.items()
        },
    }

# ───────────────────────────── Step E ─────────────────────────────────────────

def step_e(df: pd.DataFrame, paths: dict, validation: dict) -> None:
    """Export segment_crowding.parquet and sprint2_validation_report.json."""
    print("\n[Step E] Exporting artefacts …")
    t0 = time.time()

    # Compact schema columns
    out_cols = ["route_id","from_seq","to_seq","from_stop_id","to_stop_id",
                "day_type","time_slot","scheduled_travel_sec",
                "est_pax_per_bus","crowding_score","crowding_tier","is_ac"]

    # Add route_short_name if present (useful for debugging in Sprints 3-5)
    if "route_short_name" in df.columns:
        out_cols.insert(1, "route_short_name")

    out_df = df[out_cols].copy()

    # Cast types for compact storage
    out_df["route_id"]             = out_df["route_id"].astype("int64")
    out_df["from_seq"]             = out_df["from_seq"].astype("int32")
    out_df["to_seq"]               = out_df["to_seq"].astype("int32")
    out_df["time_slot"]            = out_df["time_slot"].astype("int8")
    out_df["scheduled_travel_sec"] = out_df["scheduled_travel_sec"].fillna(0).astype("int32")
    out_df["est_pax_per_bus"]      = out_df["est_pax_per_bus"].astype("float32")
    out_df["crowding_score"]       = out_df["crowding_score"].astype("float32")
    out_df["is_ac"]                = out_df["is_ac"].astype(bool)

    seg_path = paths["seg_crowd"]
    out_df.to_parquet(seg_path, engine="pyarrow", compression="zstd", index=False)
    mb = os.path.getsize(seg_path) / 1_048_576
    print(f"  segment_crowding.parquet : {len(out_df):,} rows | {mb:.2f} MB → {seg_path}")

    # Validation report JSON
    report = {
        "metadata": {
            "sprint"      : "Sprint 2",
            "pipeline"    : "src.pipeline.sprint2_crowding_model",
            "executed_at" : datetime.now().isoformat(),
            "status"      : "COMPLETED",
        },
        "model_parameters": {
            "kappa_penetration"       : KAPPA,
            "cap_ac_pax"              : CAP_AC,
            "cap_non_ac_pax"          : CAP_NON_AC,
            "null_vehicle_rate"       : NULL_VEH_RATE,
            "sigmoid_centre_L"        : 0.65,
            "sigmoid_steepness_k"     : 3.5,
            "crowding_tier_thresholds": {
                "Low": "< 0.35", "Moderate": "0.35 – 0.70", "High": "> 0.70"
            },
        },
        "output_rows"  : len(out_df),
        "validation"   : validation,
        "summary_stats": {
            "mean_crowding_score"  : round(float(out_df["crowding_score"].mean()),    4),
            "median_crowding_score": round(float(out_df["crowding_score"].median()),  4),
            "p90_crowding_score"   : round(float(out_df["crowding_score"].quantile(0.90)), 4),
            "max_crowding_score"   : round(float(out_df["crowding_score"].max()),     4),
            "mean_est_pax_per_bus" : round(float(out_df["est_pax_per_bus"].mean()),  2),
            "max_est_pax_per_bus"  : round(float(out_df["est_pax_per_bus"].max()),   2),
        },
    }
    rpt_path = paths["val_report"]
    with open(rpt_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  sprint2_validation_report.json → {rpt_path}")
    print(f"  Export complete in {time.time()-t0:.2f}s")

# ──────────────────────────── main ────────────────────────────────────────────

def main():
    print("=" * 80)
    print("DELHI CROWD-AWARE BUS PLANNER — SPRINT 2: CROWDING MODEL")
    print("=" * 80)
    wall_start = time.time()

    paths = resolve_paths()
    con   = duckdb.connect()

    meta      = step_a(con, paths)
    seg_flow  = step_b(con, paths)

    # Bring route_short_name into seg_flow for Step D asymmetry lookup
    rsn_map = dict(zip(
        meta["all_routes"]["route_id"].astype(int),
        meta["all_routes"]["route_id"]  # placeholder; we need short_name
    ))
    # Actual short name map
    canon_rsn = con.execute(f"""
        SELECT DISTINCT CAST(route_id AS BIGINT) AS route_id, route_short_name
        FROM read_parquet('{paths["canon"].replace(chr(92), "/")}')
    """).fetchdf()
    canon_rsn["route_id"] = canon_rsn["route_id"].astype(int)
    rsn_lookup = dict(zip(canon_rsn["route_id"], canon_rsn["route_short_name"]))
    seg_flow["route_short_name"] = seg_flow["route_id"].apply(lambda r: rsn_lookup.get(int(r), ""))

    crowd_df   = step_c(con, paths, seg_flow, meta)
    validation = step_d(crowd_df)
    step_e(crowd_df, paths, validation)

    total = time.time() - wall_start
    print("\n" + "=" * 80)
    print("SPRINT 2 SUMMARY")
    print("=" * 80)
    print(f"  Total rows in segment_crowding.parquet  : {len(crowd_df):,}")
    print(f"  Overall mean crowding score             : {crowd_df['crowding_score'].mean():.4f}")
    print(f"  Overall p90 crowding score              : {crowd_df['crowding_score'].quantile(0.90):.4f}")
    print(f"  Pipeline wall-clock time                : {total:.1f}s")
    print("=" * 80)

if __name__ == "__main__":
    main()
