"""Draw the figures used in the README and the technical note, straight from the pipeline outputs.

    python docs/make_figures.py                       # data/processed -> docs/assets/fig-*.svg
    python docs/make_figures.py --data DIR --out DIR

Pure Python (DuckDB is only used to read parquet, which the project already depends on); no plotting library.
Every number in a title or label is computed here from `validation_report.json`, `coverage.csv` and the planner
tables, so a rebuilt dataset gives rebuilt figures. If an input is missing the figure is skipped with a message.
Each figure carries its own light card, so it reads well on a light or a dark page.
One message per chart, direct labels, thin marks, a colour-blind-safe pairing (teal against warm grey / amber).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[1]
FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif'

BG, EDGE, INK, MUTED, GRID = "#fbfaf7", "#e3e0d6", "#1d2327", "#566069", "#e6e3d9"
SEATS, STANDING, CROWDED, NODATA = "#0f766e", "#b45309", "#8f1d1d", "#8a929a"
TEAL, GREY = "#0f766e", "#9aa3ab"
W = 760


class MissingData(Exception):
    pass


def esc(s) -> str:
    return escape(str(s))


def wrap(text: str, n: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > n and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return out + ([cur] if cur else [])


class Fig:
    """A small SVG canvas with a title block and a source line."""

    def __init__(self, title: str, subtitle: str, height: int, source: str):
        self.h, self.parts, self.source = height, [], source
        lines = wrap(title, 68)
        y = 34
        for ln in lines:
            self.parts.append(f'<text x="24" y="{y}" class="ti">{esc(ln)}</text>')
            y += 24
        self.parts.append(f'<text x="24" y="{y - 2}" class="su">{esc(subtitle)}</text>')
        self.top = y + 22

    def add(self, s: str):
        self.parts.append(s)

    def text(self, x, y, s, cls="lb", anchor="start", fill=None):
        f = f' fill="{fill}"' if fill else ""
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}"{f}>{esc(s)}</text>')

    def svg(self, name: str) -> str:
        css = (f"text{{font-family:{FONT};fill:{INK}}}.ti{{font-size:17px;font-weight:700}}.su{{font-size:12.5px;fill:{MUTED}}}"
               f".lb{{font-size:12px}}.ax{{font-size:11px;fill:{MUTED}}}.src{{font-size:10.5px;fill:{MUTED}}}.bd{{font-size:12px;font-weight:700}}")
        lines = wrap(self.source, 135)
        src = "".join(f'<text x="24" y="{self.h - 14 - 14 * (len(lines) - 1 - i)}" class="src">{esc(ln)}</text>' for i, ln in enumerate(lines))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {self.h}" width="{W}" height="{self.h}" role="img" '
                f'aria-label="{esc(name)}"><title>{esc(name)}</title><style>{css}</style>'
                f'<rect width="{W}" height="{self.h}" rx="14" fill="{BG}" stroke="{EDGE}"/>' + "".join(self.parts) + src + "</svg>\n")


def lin(d0, d1, r0, r1):
    return lambda v: r0 + (v - d0) * (r1 - r0) / (d1 - d0)


def grid_y(f: Fig, y, x0, x1, ticks, fmt):
    for v in ticks:
        f.add(f'<line x1="{x0}" y1="{y(v):.1f}" x2="{x1}" y2="{y(v):.1f}" stroke="{GRID}"/>')
        f.text(x0 - 8, y(v) + 4, fmt(v), "ax", "end")


# ----------------------------------------------------------------------------- loading


def load_report(data: Path) -> dict:
    p = data / "validation_report.json"
    if not p.exists():
        raise MissingData(f"{p} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def read_parquet(path: Path, sql: str):
    if not path.exists():
        raise MissingData(f"{path} not found")
    import duckdb

    con = duckdb.connect()
    try:
        return con.execute(sql.replace("{p}", "'" + str(path).replace("'", "''") + "'")).fetchall()
    finally:
        con.close()


# ----------------------------------------------------------------------------- figures


def fig_levels_by_hour(data: Path, report: dict) -> str:
    p = data / "coverage.csv"
    if not p.exists():
        raise MissingData(f"{p} not found")
    km: dict[int, dict[str, float]] = {}
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["day_type"] != "weekday":
                continue
            km.setdefault(int(r["hour"]), {}).setdefault(r["level"], 0.0)
            km[int(r["hour"])][r["level"]] += float(r["bus_km"])
    hours = [h for h in range(5, 24) if h in km and sum(km[h].values()) > 0]
    if not hours:
        raise MissingData("coverage.csv has no weekday rows")
    share = {h: {lv: km[h].get(lv, 0.0) / sum(km[h].values()) for lv in ("seats", "standing", "crowded", "no_data")} for h in hours}
    peak = max(hours, key=lambda h: share[h]["crowded"])
    f = Fig(f"Crowded stretches peak at {peak:02d}:00, when {share[peak]['crowded']:.0%} of bus-km is crowded",
            "Weekday share of scheduled bus-km by crowding level, by hour of day (both operators)", 470,
            "Source: data/processed/coverage.csv, October 2026 weekdays. Crowded cells are a conservative lower estimate where scale-up is capped.")
    x0, x1, yb, yt = 64, 736, f.top + 270, f.top + 28
    y = lin(0, 1, yb, yt)
    grid_y(f, y, x0, x1, [0, .25, .5, .75, 1], lambda v: f"{v:.0%}")
    bw = (x1 - x0) / len(hours)
    order = [("seats", SEATS), ("standing", STANDING), ("crowded", CROWDED), ("no_data", NODATA)]
    for i, h in enumerate(hours):
        base = 0.0
        x = x0 + i * bw + 2
        for lv, col in order:
            v = share[h][lv]
            if v <= 0:
                continue
            y_top, y_bot = y(base + v), y(base)
            hgt = max(y_bot - y_top - 1.2, 0.5)
            extra = ' opacity=".55"' if lv == "no_data" else ""
            f.add(f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bw - 4:.1f}" height="{hgt:.1f}" fill="{col}"{extra}/>')
            base += v
        if h % 2 == 0:
            f.text(x + (bw - 4) / 2, yb + 16, f"{h:02d}", "ax", "middle")
    f.text((x0 + x1) / 2, yb + 34, "hour of day (starting hour)", "ax", "middle")
    ly = yb + 58
    lx = x0
    for lv, col in order:
        label = {"seats": "Usually seats", "standing": "Usually standing", "crowded": "Usually crowded", "no_data": "No data"}[lv]
        f.add(f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" rx="2" fill="{col}"{" opacity=\".55\"" if lv == "no_data" else ""}/>')
        f.text(lx + 18, ly + 1, label, "lb")
        lx += 150
    return f.svg("Crowding level by hour of day, weekdays")


def fig_trips_ran(data: Path, report: dict) -> str:
    rows = read_parquet(data / "planner" / "gps_rho_fill.parquet",
                        "select hour, avg(rho), count(*) from {p} where day_type='weekday' and rho_src='cell' group by 1 order by 1")
    rows = [(int(h), float(v), int(n)) for h, v, n in rows if 5 <= int(h) <= 23]
    if not rows:
        raise MissingData("no GPS-measured weekday cells")
    hi = max(rows, key=lambda r: r[1])
    lo = min(rows, key=lambda r: r[1])
    f = Fig(f"At best {hi[1]:.0%} of timetabled trips ran ({hi[0]:02d}:00); at {lo[0]:02d}:00 only {lo[1]:.0%}",
            "Share of scheduled trips that ran, from GPS on the sample days (weekdays, average over route-hour cells)", 380,
            "Source: data/processed/planner/gps_rho_fill.parquet, GPS-measured cells only. The model counts only trips that ran.")
    x0, x1, yb, yt = 64, 736, f.top + 210, f.top + 20
    top = max(0.8, max(v for _, v, _ in rows) * 1.25)
    y = lin(0, top, yb, yt)
    x = lin(5, 23, x0 + 10, x1 - 40)
    grid_y(f, y, x0, x1, [t for t in (0, .2, .4, .6, .8, 1.0) if t <= top], lambda v: f"{v:.0%}")
    pts = " ".join(f"{x(h):.1f},{y(v):.1f}" for h, v, _ in rows)
    f.add(f'<polyline points="{pts}" fill="none" stroke="{TEAL}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
    for h, v, _ in rows:
        f.add(f'<circle cx="{x(h):.1f}" cy="{y(v):.1f}" r="3.2" fill="{TEAL}" stroke="{BG}" stroke-width="1.5"/>')
    f.text(x(hi[0]), y(hi[1]) - 12, f"{hi[1]:.0%} at {hi[0]:02d}:00", "bd", "middle")
    f.text(x(lo[0]), y(lo[1]) + 24, f"{lo[1]:.0%} at {lo[0]:02d}:00", "bd", "middle")
    for h in range(5, 24, 2):
        f.text(x(h), yb + 16, f"{h:02d}", "ax", "middle")
    f.text((x0 + x1) / 2, yb + 34, "hour of day (starting hour)", "ax", "middle")
    return f.svg("Share of scheduled trips that ran, by hour")


def fig_time_factor(data: Path, report: dict) -> str:
    rows = read_parquet(data / "planner" / "runtime_factors.parquet",
                        "select key, hour, factor from {p} where scope='operator' order by key, hour")
    series: dict[str, dict[int, float]] = {}
    for k, h, v in rows:
        series.setdefault(k, {})[int(h)] = float(v)
    if "DTC" not in series or "DIMTS" not in series:
        raise MissingData("runtime factors for both operators are needed")
    peak_h = max(series["DTC"], key=series["DTC"].get)
    f = Fig(f"Buses take {series['DTC'][peak_h]:.2f}x the timetable run time at {peak_h:02d}:00, against {series['DTC'].get(8, float('nan')):.2f}x at 08:00",
            "Observed run time divided by the timetable run time, from consecutive ticket pairs (1.0 = on the timetable)", 380,
            f"Source: data/processed/planner/runtime_factors.parquet. Pair-ratio window {report['headline_numbers']['pair_ratio_window']}; the {report['headline_numbers']['pair_ratio_window_alternative']} alternative is in the technical note." if "pair_ratio_window" in report["headline_numbers"] else "Source: data/processed/planner/runtime_factors.parquet.")
    x0, x1, yb, yt = 64, 700, f.top + 210, f.top + 20
    lo, hi = 0.5, max(1.6, max(max(s.values()) for s in series.values()) * 1.08)
    y = lin(lo, hi, yb, yt)
    x = lin(0, 23, x0 + 10, x1 - 10)
    grid_y(f, y, x0, x1 + 30, [0.5, 1.0, 1.5], lambda v: f"{v:.1f}x")
    f.add(f'<line x1="{x0}" y1="{y(1):.1f}" x2="{x1 + 30}" y2="{y(1):.1f}" stroke="{INK}" stroke-width="1" stroke-dasharray="5 4"/>')
    f.text(x0 + 6, y(1) - 6, "timetable", "ax")
    for key, col, lab, dash in (("DTC", TEAL, "DTC", ""), ("DIMTS", STANDING, "Cluster", ' stroke-dasharray="7 4"')):
        s = series[key]
        pts = " ".join(f"{x(h):.1f},{y(v):.1f}" for h, v in sorted(s.items()))
        f.add(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.4" stroke-linejoin="round"{dash}/>')
        last = max(s)
        f.text(x(last) + 8, y(s[last]) + (-2 if key == "DTC" else 16), lab, "bd", fill=col)
    for h in range(0, 24, 3):
        f.text(x(h), yb + 16, f"{h:02d}", "ax", "middle")
    f.text((x0 + x1) / 2, yb + 34, "hour of day (starting hour)", "ax", "middle")
    return f.svg("Travel-time factor by hour, DTC and cluster")


def fig_load_factor(data: Path, report: dict) -> str:
    n = report["headline_numbers"]
    need = ["load_factor_model", "load_factor_full_allocation_capped_at_crush", "load_factor_full_allocation",
            "load_factor_band_low", "load_factor_band_high"]
    for k in need:
        if k not in n:
            raise MissingData(f"headline number {k} missing")
    lo, hi = n["load_factor_band_low"], n["load_factor_band_high"]
    def where(v):
        return "below the published band" if v < lo else ("above the published band" if v > hi else "inside the published band")

    m, cap, full = n["load_factor_model"], n["load_factor_full_allocation_capped_at_crush"], n["load_factor_full_allocation"]
    pts = [("Model as is", m, SEATS, where(m) + ": it only places riders it can place"),
           ("Full allocation, capped at crush", cap, STANDING, where(cap)),
           ("Full allocation, no cap", full, CROWDED, f"{full / hi:.1f}x the top of the band: more riders than buses can hold")]
    between = m < lo and cap > hi
    f = Fig(f"The published load factor ({lo:.0%}-{hi:.0%}) lies between what the model places and full allocation" if between
            else f"Model load factor {m:.0%} against the published {lo:.0%}-{hi:.0%}",
            "Weekday passenger-km divided by seat-km, scheduled service on commuter-facing cells", 370,
            "Source: validation_report.json (headline numbers). Definitions differ from the published survey figure, so this is a rough check.")
    x0, x1 = 64, 720
    top = max(2.0, max(p[1] for p in pts) * 1.1)
    x = lin(0, top, x0, x1)
    base = f.top + 175
    f.add(f'<rect x="{x(lo):.1f}" y="{f.top + 6}" width="{x(hi) - x(lo):.1f}" height="{base - f.top - 6 + 20}" fill="{TEAL}" opacity=".13"/>')
    f.text((x(lo) + x(hi)) / 2, f.top + 2, f"published {lo:.0%}-{hi:.0%}", "bd", "middle", TEAL)
    f.add(f'<line x1="{x0}" y1="{base + 14}" x2="{x1}" y2="{base + 14}" stroke="{MUTED}"/>')
    for v in [0, .5, 1, 1.5, 2]:
        if v <= top:
            f.add(f'<line x1="{x(v):.1f}" y1="{base + 14}" x2="{x(v):.1f}" y2="{base + 19}" stroke="{MUTED}"/>')
            f.text(x(v), base + 33, f"{v:.0%}", "ax", "middle")
    for i, (lab, v, col, note) in enumerate(pts):
        yy = f.top + 40 + i * 52
        f.add(f'<line x1="{x0}" y1="{yy}" x2="{x(v):.1f}" y2="{yy}" stroke="{col}" stroke-width="3" stroke-linecap="round"/>')
        f.add(f'<circle cx="{x(v):.1f}" cy="{yy}" r="6" fill="{col}" stroke="{BG}" stroke-width="2"/>')
        f.text(x0, yy - 10, f"{lab}: {v:.0%}", "bd", "start", col)
        f.text(x0, yy + 18, note, "ax", "start")
    return f.svg("Load-factor bracket against the published band")


def fig_corridors(data: Path, report: dict) -> str:
    n = report["headline_numbers"]
    need = ["corridor_hits_total", "corridors_total", "corridor_hits_chance_expected", "corridor_hits_both_ends",
            "corridor_top_decile_share", "corridor_top_decile_chance"]
    for k in need:
        if k not in n:
            raise MissingData(f"headline number {k} missing")
    f = Fig(f"Passing the corridor rule is easy by chance, so we also check enrichment: {n['corridor_top_decile_share']:.0%} of "
            f"corridor stretches are in the busiest tenth", "Ten outside-evidence corridors tested against the model's busiest stretches", 410,
            f"Source: validation_report.json. Chance baseline: {n['corridor_hits_chance_method']}.")
    total = n["corridors_total"]
    # panel 1: counts
    px0, px1 = 64, 360
    base = f.top + 215
    ymax = max(total, n["corridor_hits_chance_expected"]) * 1.0
    y = lin(0, ymax, base, f.top + 40)
    f.text(px0, f.top + 14, f"Corridors passing the rule (of {total})", "bd")
    items = [("Model", n["corridor_hits_total"], TEAL), ("Chance", n["corridor_hits_chance_expected"], GREY), ("Both ends", n["corridor_hits_both_ends"], TEAL)]
    bw = 62
    for i, (lab, v, col) in enumerate(items):
        x = px0 + 20 + i * 96
        f.add(f'<rect x="{x}" y="{y(v):.1f}" width="{bw}" height="{base - y(v):.1f}" rx="3" fill="{col}"{" opacity=\".7\"" if lab == "Both ends" else ""}/>')
        f.text(x + bw / 2, y(v) - 7, f"{v:.2f}" if lab == "Chance" else f"{int(v)}", "bd", "middle")
        f.text(x + bw / 2, base + 18, lab, "lb", "middle")
    f.add(f'<line x1="{px0}" y1="{base}" x2="{px1}" y2="{base}" stroke="{MUTED}"/>')
    f.text(px0, base + 40, "Both ends: only stretches with both stops on the corridor.", "ax")
    # panel 2: shares
    qx0, qx1 = 440, 736
    ymax2 = max(n["corridor_top_decile_share"], n["corridor_top_decile_chance"]) * 1.25
    y2 = lin(0, ymax2, base, f.top + 40)
    f.text(qx0, f.top + 14, "Corridor stretches in the network's busiest 10%", "bd")
    for i, (lab, v, col) in enumerate([("Model", n["corridor_top_decile_share"], TEAL), ("Chance", n["corridor_top_decile_chance"], GREY)]):
        x = qx0 + 40 + i * 120
        f.add(f'<rect x="{x}" y="{y2(v):.1f}" width="{bw}" height="{base - y2(v):.1f}" rx="3" fill="{col}"/>')
        f.text(x + bw / 2, y2(v) - 7, f"{v:.0%}", "bd", "middle")
        f.text(x + bw / 2, base + 18, lab, "lb", "middle")
    f.add(f'<line x1="{qx0}" y1="{base}" x2="{qx1}" y2="{base}" stroke="{MUTED}"/>')
    f.text(qx0, base + 40, f"{n['corridor_top_decile_share'] / n['corridor_top_decile_chance']:.1f}x the chance level is the signal; the pass count is not.", "ax")
    return f.svg("Corridor check against its chance baseline")


FIGURES = [
    ("fig-levels-by-hour.svg", fig_levels_by_hour),
    ("fig-trips-ran-by-hour.svg", fig_trips_ran),
    ("fig-travel-time-factor.svg", fig_time_factor),
    ("fig-load-factor-bracket.svg", fig_load_factor),
    ("fig-corridor-check.svg", fig_corridors),
]


def build(data: Path, out: Path) -> tuple[list[Path], list[str]]:
    """Write every figure that its inputs allow. Returns (files written, messages about skipped ones)."""
    data, out = Path(data), Path(out)
    written, skipped = [], []
    try:
        report = load_report(data)
    except MissingData as e:
        return [], [f"all figures skipped: {e}"]
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in FIGURES:
        try:
            svg = fn(data, report)
        except MissingData as e:
            skipped.append(f"{name} skipped: {e}")
            continue
        p = out / name
        p.write_text(svg, encoding="utf-8")
        written.append(p)
    return written, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=str(REPO / "data" / "processed"))
    ap.add_argument("--out", default=str(REPO / "docs" / "assets"))
    a = ap.parse_args(argv)
    written, skipped = build(Path(a.data), Path(a.out))
    for p in written:
        print(f"wrote {p} ({p.stat().st_size} bytes)")
    for m in skipped:
        print(m, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
