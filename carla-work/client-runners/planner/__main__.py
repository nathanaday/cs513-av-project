"""Offline CLI. Only export connects to CARLA; other commands need no simulator."""

import argparse
import csv
import json
from pathlib import Path
import sys

from .core import PlanningError, make_plan
from .examples import mock_forecast, tiny_example
from .files import read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("examples", help="write and solve the three hand-checkable fixtures")
    example.add_argument("--output", required=True)
    mock = commands.add_parser("mock", help="invent a forecast for a catalog")
    mock.add_argument("--catalog", required=True)
    mock.add_argument("--output", required=True)
    mock.add_argument("--seed", type=int, default=0)
    mock.add_argument("--hazard-segment", action="append", default=[])
    mock.add_argument("--clear", action="store_true")
    for name in ("plan", "sweep"):
        sub = commands.add_parser(name)
        for item in ("catalog", "forecast", "trip", "output"):
            sub.add_argument(f"--{item}", required=True)
        sub.add_argument("--config")
        sub.add_argument("--require-verified-limits", action="store_true")
        if name == "plan":
            sub.add_argument("--lambda", dest="risk_weight", type=float)
            sub.add_argument("--mode", choices=["risk-aware", "naive", "cautious"], default="risk-aware")
        else:
            sub.add_argument("--lambdas", type=float, nargs="+", default=[0, 0.5, 1, 2, 5, 10])
    export = commands.add_parser("export", help="export a live map or a local OpenDRIVE file")
    export.add_argument("--output", required=True)
    export.add_argument("--host", default="127.0.0.1")
    export.add_argument("--port", type=int, default=2000)
    export.add_argument("--xodr", help="offline file; provenance is labeled local, not HPC")
    export.add_argument("--speed-limits", help="verified per-segment speed-limit overrides")
    limits = commands.add_parser("limits", help="probe live speed limits on a running server; write overrides")
    limits.add_argument("--catalog", required=True)
    limits.add_argument("--output", required=True, help="overrides for export --speed-limits")
    limits.add_argument("--evidence", help="raw probe record (default: <output stem>-evidence.json)")
    limits.add_argument("--host", default="127.0.0.1")
    limits.add_argument("--port", type=int, default=2000)
    risk = commands.add_parser("risk-api", help="convert World's Risk API v0 CSV to a Planner forecast")
    template = commands.add_parser("risk-template", help="write an all-zero Risk API v0 CSV with every catalog segment")
    for sub in (risk, template):
        sub.add_argument("--catalog", required=True)
        sub.add_argument("--hazards", required=True, help="World's hazards.csv registry")
        sub.add_argument("--output", required=True)
    risk.add_argument("--odds", required=True, help="World's risk_<scenario>.csv")
    risk.add_argument("--time", type=float, default=0.0, help="seconds; which time window to use (default 0)")
    risk.add_argument("--forecast-id")
    args = parser.parse_args()
    try:
        if args.command == "examples":
            output = Path(args.output)
            catalog, forecast, trip = tiny_example()
            write_json(output / "catalog.json", catalog)
            write_json(output / "hazards.json", forecast)
            write_json(output / "trip.json", trip)
            clear = mock_forecast(catalog, clear=True)
            write_json(output / "clear.json", clear)
            for label, risks, weight in (("clear", clear, 2), ("shortcut", forecast, 0), ("detour", forecast, 2)):
                result = make_plan(catalog, risks, dict(trip, risk_weight=weight))
                write_json(output / f"plan-{label}.json", result)
                summary(result, label)
            # Removing the detour makes slowing down the only way to trade time for penalty.
            single = json.loads(json.dumps(catalog))
            del single["segments"]["detour"]
            single["segments"]["start"]["successors"] = ["shortcut"]
            single["catalog_id"] = "single-route-v1"
            risks = mock_forecast(single, hazardous=["shortcut"])
            result = make_plan(single, risks, dict(trip, risk_weight=2))
            write_json(output / "single-catalog.json", single)
            write_json(output / "single-forecast.json", risks)
            write_json(output / "plan-slow.json", result)
            summary(result, "slow")
        elif args.command == "mock":
            write_json(args.output, mock_forecast(read_json(args.catalog), seed=args.seed,
                                                  hazardous=args.hazard_segment, clear=args.clear))
        elif args.command == "export":
            import carla
            from .carla_map import export_catalog
            if args.xodr:
                cmap = carla.Map("Town10HD_Opt", Path(args.xodr).read_text())
                provenance = "local OpenDRIVE export; HPC verification pending"
            else:
                import os
                client = carla.Client(args.host, args.port)
                client.set_timeout(30.0)
                if client.get_client_version() != "0.9.16" or client.get_server_version() != "0.9.16":
                    raise PlanningError("client and server must both be CARLA 0.9.16")
                cmap = client.get_world().get_map()
                provenance = f"live CARLA; Slurm job {os.environ.get('SLURM_JOB_ID', 'none')}"
            catalog = export_catalog(cmap, provenance=provenance,
                                     verified_limits=read_json(args.speed_limits) if args.speed_limits else None)
            write_json(args.output, catalog)
            print(f"{catalog['catalog_id']}: {len(catalog['segments'])} segments, {len(catalog['spawn_points'])} spawn points")
        elif args.command == "limits":
            import carla
            from .live_limits import overrides_from_probe, probe
            client = carla.Client(args.host, args.port)
            client.set_timeout(30.0)
            if client.get_client_version() != "0.9.16" or client.get_server_version() != "0.9.16":
                raise PlanningError("client and server must both be CARLA 0.9.16")
            catalog = read_json(args.catalog)
            evidence = probe(client.get_world(), catalog)
            output = Path(args.output)
            evidence_path = Path(args.evidence) if args.evidence else output.with_name(
                output.name.split(".")[0] + "-evidence.json")
            write_json(evidence_path, evidence)
            print(f"probe: {len(evidence['segments'])} segments, default limit {evidence['default_limit_kmh']:g} km/h, "
                  f"sign actors {evidence['sign_actors']}, speed-limit landmarks {len(evidence['speed_limit_landmarks'])}; "
                  f"wrote {evidence_path}")
            overrides = overrides_from_probe(catalog, evidence)
            write_json(output, overrides)
            print(f"overrides: {len(overrides['limits'])} segments at "
                  f"{overrides['evidence']['distinct_live_limits_kmh']} km/h; wrote {output}")
        elif args.command == "risk-template":
            from .world_risk import read_registry, write_template
            count, enabled = write_template(read_json(args.catalog), read_registry(args.hazards), args.output)
            print(f"{count} segments, {len(enabled)} enabled hazards, all odds 0; wrote {args.output}")
        elif args.command == "risk-api":
            from .world_risk import forecast_from_risk_api, read_odds, read_registry
            registry = read_registry(args.hazards)
            forecast = forecast_from_risk_api(read_json(args.catalog), registry, read_odds(args.odds, registry),
                                              time_s=args.time, forecast_id=args.forecast_id,
                                              name=Path(args.odds).stem)
            write_json(args.output, forecast)
            info = forecast["risk_api"]
            print(f"{forecast['forecast_id']}: {len(forecast['segments'])} segments, "
                  f"mean hazard sum {info['mean_hazard_sum']:.4f} per second; "
                  f"priced: {', '.join(sorted(info['mode_map']))}; "
                  f"not priced: {', '.join(sorted(info['unpriced_modes'])) or 'none'}")
            if info["disabled_hazards_with_odds"]:
                print(f"switched off in hazards.csv but with nonzero odds, still counted: "
                      f"{', '.join(info['disabled_hazards_with_odds'])}")
        else:
            catalog, forecast, trip = (read_json(getattr(args, name)) for name in ("catalog", "forecast", "trip"))
            config = read_json(args.config) if args.config else None
            if args.command == "plan":
                if args.risk_weight is not None:
                    trip["risk_weight"] = args.risk_weight
                result = make_plan(catalog, forecast, trip, config, mode=args.mode,
                                   require_verified_limits=args.require_verified_limits)
                write_json(args.output, result)
                summary(result)
            else:
                output = Path(args.output)
                output.mkdir(parents=True, exist_ok=True)
                rows = []
                for weight in args.lambdas:
                    result = make_plan(catalog, forecast, dict(trip, risk_weight=weight), config,
                                       require_verified_limits=args.require_verified_limits)
                    write_json(output / f"lambda-{weight:g}.json", result)
                    rows.append([weight, result["estimated_time_s"], result["predicted_penalty"],
                                 ";".join(s["segment_id"] for s in result["segments"])])
                with (output / "predicted-only.csv").open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["lambda", "estimated_time_s", "predicted_penalty", "route"])
                    writer.writerows(rows)
                print("Wrote predicted-only sweep; these are not measured safety outcomes.")
    except (PlanningError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"error: {error}\n")


def summary(plan, label="plan"):
    route = " -> ".join(f"{s['segment_id']}@{s['target_speed_kmh']:g}" for s in plan["segments"])
    print(f"{label}: {plan['estimated_time_s']:.3f} estimated s; "
          f"{plan['predicted_penalty']:.3f} predicted penalty; {route}")


if __name__ == "__main__":
    sys.exit(main())
