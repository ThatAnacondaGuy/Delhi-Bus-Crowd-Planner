"""Resumable pipeline CLI: python -m src.pipeline.run --until <stage>."""
import argparse
import importlib
import inspect

from . import manifest
from .db import connect
from .paths import Paths

# Stage name -> "module:function", in pipeline order. Later tasks wire their modules.
STAGES = {
    "clean": "src.pipeline.clean:run",
    "resolve": "src.pipeline.resolve:run",
    "network": "src.pipeline.network:run",
    "loads": "src.pipeline.loads:run",
    "operator": "src.pipeline.operator:run",
    "validate": "src.pipeline.validate:run",
    "render": "src.pipeline.render:run",
}


def stage_inputs(paths: Paths) -> dict[str, str]:
    return {"tickets_csv": str(paths.tickets_csv)}


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
    inputs = stage_inputs(paths)
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
            if fn is None:
                print(f"stage {name}: not implemented yet, skipped")
            elif not args.force and manifest.is_done(name, inputs, params, path=mpath):
                print(f"stage {name}: up to date, skipped")
            else:
                accepted = inspect.signature(fn).parameters
                result = fn(con, paths, **{k: v for k, v in opts.items() if k in accepted})
                print(f"stage {name}: done {result if result is not None else ''}".rstrip())
                manifest.mark_done(name, inputs, [str(paths.work_db)], params, path=mpath)
            if name == args.until:
                break
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
