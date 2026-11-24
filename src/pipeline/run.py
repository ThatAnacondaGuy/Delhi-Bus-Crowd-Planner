"""Resumable pipeline CLI: python -m src.pipeline.run --until <stage>."""
import argparse
import importlib
import inspect
import time

from . import manifest
from .db import connect
from .paths import Paths

# Stage name -> "module:function", in pipeline order. Later tasks wire their modules.
STAGES = {
    "clean": "src.pipeline.clean:run",
    "resolve": "src.pipeline.resolve:run",
    "network": "src.pipeline.network:run_network",
    "gps": "src.pipeline.gps:run",
    "loads": "src.pipeline.loads:run_loads",
    "operator": "src.pipeline.operator:run",
    "validate": "src.pipeline.validate:run",
    "render": "src.pipeline.render:run",
}


GTFS_FILES = ("routes.txt", "trips.txt", "stop_times.txt", "stops.txt")

# Files each stage reads itself (stage name -> paths -> {key: file}).
STAGE_INPUTS = {
    "clean": lambda p: {"tickets_csv": p.tickets_csv},
    "resolve": lambda p: {f"gtfs_{f.removesuffix('.txt')}": p.gtfs_dir / f for f in GTFS_FILES},
    "gps": lambda p: {"gps_aggregates": p.gps_aggregates / "gps_route_hour.csv"},
    "render": lambda p: {"validation_report": p.processed / "validation_report.json",
                         **{f"template_{t.name}": t for t in sorted((p.repo / "docs").glob("*.tmpl.md"))},
                         **{f"template_{t.name}": t for t in sorted(p.repo.glob("README.tmpl.md"))}},
}


def stage_inputs(paths: Paths, stage: str) -> dict[str, str]:
    """Files whose change makes `stage` stale: its own inputs plus every earlier stage's."""
    out: dict[str, str] = {}
    for name in STAGES:
        out.update({k: str(v) for k, v in STAGE_INPUTS.get(name, lambda p: {})(paths).items()})
        if name == stage:
            break
    return out


def _load(spec: str):
    mod, fn = spec.split(":")
    try:
        module = importlib.import_module(mod)
    except ModuleNotFoundError as e:
        if e.name == mod:
            return None
        raise
    return getattr(module, fn)


def main(argv=None, paths: Paths | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline")
    ap.add_argument("--until", choices=list(STAGES), default="render")
    ap.add_argument("--sample", type=int, default=None, help="use only the N busiest route strings")
    ap.add_argument("--gps-raw", action="store_true")
    ap.add_argument("--gps-days", default=None, help="comma-separated dates D1,D2,...")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    paths = paths or Paths.from_env()
    paths.processed.mkdir(parents=True, exist_ok=True)
    mpath = paths.processed / "manifest.json"
    params = {"sample": args.sample, "gps_raw": args.gps_raw, "gps_days": args.gps_days}

    con = connect(str(paths.work_db))
    try:
        sample_routes = None
        if args.sample is not None:
            from .clean import busiest_routes
            sample_routes = busiest_routes(con, paths, args.sample)
        opts = {"sample_routes": sample_routes, "gps_raw": args.gps_raw,
                "gps_days": args.gps_days.split(",") if args.gps_days else None, "force": args.force}
        for name, spec in STAGES.items():
            fn = _load(spec)
            inputs = stage_inputs(paths, name)
            if fn is None:
                print(f"stage {name}: not implemented yet, skipped")
            elif not args.force and manifest.is_done(name, inputs, params, path=mpath):
                print(f"stage {name}: up to date, skipped")
            else:
                accepted = inspect.signature(fn).parameters
                if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in accepted.values()):
                    kwargs = dict(opts)
                else:
                    kwargs = {k: v for k, v in opts.items() if k in accepted}
                t0 = time.perf_counter()
                result = fn(con, paths, **kwargs)
                took = time.perf_counter() - t0
                print(f"stage {name}: done {result if result is not None else ''} ({took:.1f} s)".replace("  (", " (").rstrip())
                manifest.mark_done(name, inputs, [str(paths.work_db)], params, path=mpath)
            if name == args.until:
                break
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
