"""Command line for pyotter: drive a scenario on a CARLA server, and evaluate its telemetry.

    python -m pyotter drive scenario.json.gz
    python -m pyotter evaluate runs/*-telemetry.json.gz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.utilities.config import CONFIG
from .modules.driver.driver import Driver
from .modules.driver.models.driving_safety_evaluation import DrivingSafetyEvaluation
from .modules.driver.models.driving_scenario import DrivingScenario
from .modules.driver.models.driving_scenario_telemetry import DrivingScenarioTelemetry


def main(argv: list[str] | None = None) -> int:
    """Run one command.

    Returns:
        The exit status: 0, or 1 when `evaluate` finds a breached requirement.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "wait":
        return _wait(args)
    if args.command == "drive":
        if args.output and len(args.scenarios) > 1 and args.output.suffix:
            parser.error("with several scenarios, --output must be a folder")
        return _drive(args)
    return _evaluate(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyotter", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"pyotter {CONFIG.version}")
    commands = parser.add_subparsers(dest="command", required=True)

    drive = commands.add_parser("drive", help="drive scenario files on a running CARLA server and save their telemetry")
    drive.add_argument("scenarios", nargs="+", type=Path)
    drive.add_argument("-o", "--output", type=Path,
                       help="telemetry file for one scenario, or a folder (default: beside each scenario)")
    _add_server_options(drive, CONFIG.carla.drive_timeout_s)

    evaluate = commands.add_parser("evaluate", help="check telemetry files against the safety requirements")
    evaluate.add_argument("telemetry", nargs="+", type=Path)
    evaluate.add_argument("--save", action="store_true", help="also write each evaluation beside its telemetry as JSON")

    wait = commands.add_parser("wait", help="wait until a CARLA server answers")
    _add_server_options(wait, CONFIG.carla.wait_timeout_s)
    return parser


def _add_server_options(parser: argparse.ArgumentParser, timeout_s: float) -> None:
    parser.add_argument("--host", default=CONFIG.carla.host)
    parser.add_argument("--port", type=int, default=CONFIG.carla.port)
    parser.add_argument("--timeout", type=float, default=timeout_s, help=f"seconds (default {timeout_s:g})")


def _beside(path: Path, suffix: str) -> Path:
    """A file beside another, named after it: `run.json.gz` gives `run-telemetry.json.gz`."""
    stem = path.name.split(".")[0]
    return path.with_name(f"{stem}{suffix}")


def _wait(args: argparse.Namespace) -> int:
    from .modules.driver.carla_runner import wait_for_server

    version = wait_for_server(args.host, args.port, args.timeout)
    print("CARLA server", version, "is ready")
    return 0


def _drive(args: argparse.Namespace) -> int:
    for path in args.scenarios:
        scenario = DrivingScenario.load(path)
        output = _beside(path, "-telemetry.json.gz")
        if args.output and args.output.suffix:
            output = args.output
        elif args.output:
            output = args.output / output.name
        print(f"=== {path}")
        telemetry = Driver.run(scenario, host=args.host, port=args.port, timeout_s=args.timeout)
        telemetry.save(output)
        print(f"telemetry: {output}")
        print(Driver.evaluate(telemetry).summary())
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    evaluations = []
    for path in args.telemetry:
        evaluation = Driver.evaluate(DrivingScenarioTelemetry.load(path))
        evaluations.append(evaluation)
        print(f"=== {path}")
        print(evaluation.summary())
        if args.save:
            evaluation.save(_beside(path, "-evaluation.json"))
    if len(evaluations) > 1:
        _print_totals(evaluations)
    if all(evaluation.satisfied for evaluation in evaluations):
        return 0
    return 1


def _print_totals(evaluations: list[DrivingSafetyEvaluation]) -> None:
    """Print, for each requirement, the share of runs that kept it and the least margin seen."""
    print(f"=== {len(evaluations)} runs: share that kept each requirement, and the least margin seen")
    for index, first in enumerate(evaluations[0].requirements):
        results = [evaluation.requirements[index] for evaluation in evaluations]
        kept = sum(result.satisfied for result in results) / len(results)
        least = min(result.robustness for result in results)
        print(f"  {first.name:15} {kept:6.0%}   least margin {least:+8.2f} {first.unit}")


if __name__ == "__main__":
    sys.exit(main())
