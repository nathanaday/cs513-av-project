"""The lab's commands.

    carla-server [start|status|stop]      the CARLA server job on the cluster
    otter-drive SCENARIO ...              queue drives on that server
    otter-scenarios [list|push|show|pull] the scenario library
    otter-results [list|pull|sync|push]   the telemetry library
    otter-check                           what is set up, and what is missing
    otter-build [FORECAST ...]            write the scenario set to runs/scenario-set/
"""

from __future__ import annotations

import argparse
import functools
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi

from pyotter.modules.driver import DrivingScenario, DrivingScenarioTelemetry

from pyotter import World

from . import build, container, drive, server, slurm
from .console import FAIL, NOTE, OK, LabError, console, next_steps, show_error, size_text, table
from .library import (
    SCENARIOS, TELEMETRY, TELEMETRY_SUFFIX, ResultsLibrary, ScenarioEntry, ScenarioLibrary,
    require_current_schema, web_address,
)
from .settings import SETTINGS, relative

INTERRUPTED = 130


def command(run):
    """Make a command of a function: report a `LabError` in one line, and exit quietly on Ctrl-C."""

    @functools.wraps(run)
    def entry() -> None:
        try:
            sys.exit(run(sys.argv[1:]) or 0)
        except LabError as error:
            show_error(error)
            sys.exit(1)
        except KeyboardInterrupt:
            console.print()
            sys.exit(INTERRUPTED)

    return entry


def _parse(parser: argparse.ArgumentParser, argv: list[str], default: str) -> argparse.Namespace:
    """Parse, taking `default` as the action when none is named."""
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv = [default] + argv
    return parser.parse_args(argv)


# carla-server

@command
def carla_server(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="carla-server", description="Run a CARLA server as a job on the cluster.")
    actions = parser.add_subparsers(dest="action", required=True)
    start = actions.add_parser("start", help="queue a server and wait until it answers (the default)")
    start.add_argument("--time", help=f"how long to keep it, as H:MM:SS (default {SETTINGS.slurm.server.time})")
    actions.add_parser("status", help="say where the server stands")
    actions.add_parser("stop", help="end the server")
    args = _parse(parser, argv, "start")
    slurm.require()
    if args.action == "status":
        return _server_status()
    if args.action == "stop":
        return _server_stop()
    return _server_start(args.time)


def _server_start(time: str | None) -> int:
    job = server.live_job()
    if job is not None:
        console.print(f"{NOTE} A CARLA server is already here: job {job.job_id}.")
        job_id = job.job_id
    else:
        container.prepare_storage()
        job_id = slurm.submit("otter-carla", "server", ["serve"], time=time)
        server.remember(job_id)
        console.print(f"{OK} Queued the CARLA server as job [bold]{job_id}[/bold].")
    log = relative(slurm.log_path(job_id))
    try:
        with console.status("waiting in the queue") as spinner:
            status = server.wait_until_ready(job_id, on_change=spinner.update)
    except KeyboardInterrupt:
        console.print(f"{NOTE} Stopped watching. Job {job_id} goes on without you.")
        next_steps([("Look again", "uv run carla-server status"), ("Log", f"tail -f {log}")])
        return INTERRUPTED
    left = slurm.find(job_id).left
    console.print(f"{OK} CARLA is ready on [bold]{status.host}:{status.port}[/bold], with {left} left.")
    next_steps([
        ("Drive", "uv run otter-drive SCENARIO"),
        ("Scenarios", "uv run otter-scenarios"),
        ("Stop", "uv run carla-server stop"),
        ("Log", f"tail -f {log}"),
    ])
    return 0


def _server_status() -> int:
    job = server.live_job()
    if job is None:
        console.print(f"{NOTE} No CARLA server is running.")
        last = server.last_job_id()
        if last and server.read_status(last).phase == server.FAILED:
            console.print(f"  [dim]The last one (job {last}) failed: {server.read_status(last).detail} "
                          f"Its log is {relative(slurm.log_path(last))}.[/dim]")
        next_steps([("Start one", "uv run carla-server")])
        return 1
    status = server.read_status(job.job_id)
    line = server.describe(job, status)
    mark = OK if status.phase == server.READY else NOTE
    console.print(f"{mark} Job {job.job_id}: {line}, with {job.left} left.")
    return 0


def _server_stop() -> int:
    job = server.live_job()
    if job is None:
        console.print(f"{NOTE} No CARLA server is running.")
        return 0
    slurm.cancel(job.job_id)
    console.print(f"{OK} Stopped the CARLA server (job {job.job_id}). Drives still queued on it will fail.")
    return 0


# otter-drive

@command
def otter_drive(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="otter-drive",
        description="Queue one drive per scenario on the running CARLA server. "
                    f"Telemetry goes to runs/{TELEMETRY}/ and to the telemetry library.",
    )
    parser.add_argument("scenarios", nargs="+", metavar="SCENARIO",
                        help="a name or fingerprint from the library, or a scenario file (added to the library first)")
    parser.add_argument("--time", help=f"time limit of each drive, as H:MM:SS (default {SETTINGS.slurm.drive.time})")
    args = parser.parse_args(argv)
    slurm.require()
    job = server.live_job()
    if job is None:
        raise LabError("No CARLA server is running.", "Start one with `uv run carla-server`.")
    library = ScenarioLibrary()
    entries = [_entry_for(library, reference) for reference in args.scenarios]
    files = [library.fetch(entry) for entry in entries]

    queued = table("job", "scenario", "fingerprint")
    job_ids = []
    for entry, file in zip(entries, files):
        job_id = drive.submit(file, entry.label, job.job_id, time=args.time)
        job_ids.append(job_id)
        queued.add_row(f"[bold]{job_id}[/bold]", entry.name, entry.short)
    console.print(f"{OK} Queued {len(job_ids)} on the CARLA server (job {job.job_id}). They run one at a time.")
    console.print()
    console.print(queued)
    next_steps([
        ("Watch", f"tail -f {relative(slurm.log_path(job_ids[0]))}"),
        ("Queue", "squeue --me"),
        ("Results", f"{relative(ResultsLibrary.telemetry_path(entries[0].label, 'RUN').parent)}/"),
        ("Library", web_address(SETTINGS.results_repo)),
    ])
    return 0


def _entry_for(library: ScenarioLibrary, reference: str) -> ScenarioEntry:
    """The library entry a reference means. A file is added to the library first."""
    path = Path(reference)
    if not path.is_file():
        return library.resolve(reference)
    entry, added = library.push(path)
    if added:
        console.print(f"{OK} Added {entry.label} to the scenario library.")
    return entry


# otter-scenarios

@command
def otter_scenarios(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="otter-scenarios", description=f"The scenario library, {SETTINGS.scenarios_repo}.")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="every scenario (the default)")
    push = actions.add_parser("push", help="add scenario files")
    push.add_argument("files", nargs="+", type=Path, metavar="FILE")
    show = actions.add_parser("show", help="what a scenario holds")
    show.add_argument("scenario", metavar="SCENARIO")
    pull = actions.add_parser("pull", help=f"download scenarios to runs/{SCENARIOS}/")
    pull.add_argument("scenarios", nargs="+", metavar="SCENARIO")
    args = _parse(parser, argv, "list")
    library = ScenarioLibrary()
    if args.action == "push":
        return _scenarios_push(library, args.files)
    if args.action == "show":
        return _scenarios_show(library, args.scenario)
    if args.action == "pull":
        for reference in args.scenarios:
            console.print(f"{OK} {relative(library.fetch(library.resolve(reference)))}")
        return 0
    return _scenarios_list(library)


def _scenarios_list(library: ScenarioLibrary) -> int:
    entries = library.entries()
    if not entries:
        console.print(f"{NOTE} {library.repo} has no scenarios yet.")
        next_steps([("Add one", "uv run otter-scenarios push FILE.json.gz")])
        return 0
    listing = table("scenario", "fingerprint", "size")
    for entry in entries:
        listing.add_row(entry.name, entry.short, size_text(entry.size))
    console.print(listing)
    next_steps([("Drive", "uv run otter-drive SCENARIO"), ("Inspect", "uv run otter-scenarios show SCENARIO")])
    return 0


def _scenarios_push(library: ScenarioLibrary, files: list[Path]) -> int:
    for path in files:
        if not path.is_file():
            raise LabError(f"There is no file {path}.")
    for path in files:
        entry, added = library.push(path)
        if added:
            console.print(f"{OK} Added [bold]{entry.name}[/bold]  {entry.short}")
        else:
            console.print(f"{NOTE} Already in the library as [bold]{entry.name}[/bold]  {entry.short}")
    return 0


def _scenarios_show(library: ScenarioLibrary, reference: str) -> int:
    entry = library.resolve(reference)
    path = library.fetch(entry)
    scenario = DrivingScenario.load(path)
    spawns, route = scenario.spawns, scenario.route
    conditions = ", ".join(f"{condition.hazard_id} {condition.severity:.2f}" for condition in spawns.conditions)
    facts = table("", "")
    facts.show_header = False
    facts.add_row("[dim]scenario[/dim]", f"[bold]{entry.name}[/bold]")
    facts.add_row("[dim]fingerprint[/dim]", scenario.fingerprint)
    facts.add_row("[dim]map[/dim]", scenario.graph.map_name)
    facts.add_row("[dim]seed[/dim]", str(spawns.seed))
    facts.add_row("[dim]route[/dim]", f"{route.mode.value}, risk scale {route.risk_scale:g}, "
                                      f"{len(route.steps)} segments, about {route.estimated_time_s:.0f} s")
    facts.add_row("[dim]conditions[/dim]", conditions or "none")
    facts.add_row("[dim]events[/dim]", f"{len(spawns.events)} in {spawns.duration_s:g} s")
    facts.add_row("[dim]file[/dim]", relative(path))
    console.print(facts)
    return 0


# otter-results

@command
def otter_results(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="otter-results", description=f"The telemetry library, {SETTINGS.results_repo}.")
    actions = parser.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list", help="every run (the default)")
    listing.add_argument("scenario", nargs="?", default="", metavar="SCENARIO")
    pull = actions.add_parser("pull", help=f"download runs to runs/{TELEMETRY}/")
    pull.add_argument("scenario", nargs="?", default="", metavar="SCENARIO")
    actions.add_parser("sync", help="upload local results the library does not have")
    push = actions.add_parser("push", help="add telemetry files driven outside the cluster")
    push.add_argument("files", nargs="+", type=Path, metavar="TELEMETRY")
    args = _parse(parser, argv, "list")
    results = ResultsLibrary()
    if args.action == "sync":
        return _results_sync(results)
    if args.action == "push":
        return _results_push(results, args.files)
    label = ""
    if args.scenario:
        label = ScenarioLibrary().resolve(args.scenario).label
    if args.action == "pull":
        folder = results.pull(label)
        console.print(f"{OK} The runs are in {relative(folder)}/")
        next_steps([("Evaluate", f"uv run python -m pyotter evaluate {relative(folder)}/*/*{TELEMETRY_SUFFIX}")])
        return 0
    return _results_list(results, label)


def _results_list(results: ResultsLibrary, label: str) -> int:
    runs = results.runs(label)
    if not runs:
        console.print(f"{NOTE} {results.repo} has no runs{' of ' + label if label else ''} yet.")
        return 0
    listing = table("scenario", "fingerprint", "run", "size")
    for run in runs:
        name, _, short = run.scenario.rpartition(".")
        listing.add_row(name, short, run.run_id, size_text(run.size))
    console.print(listing)
    next_steps([("Download", "uv run otter-results pull [SCENARIO]")])
    return 0


def _results_sync(results: ResultsLibrary) -> int:
    pending = results.pending()
    if not pending:
        console.print(f"{OK} {results.repo} already has every local result.")
        return 0
    address = results.upload(pending, f"Add {len(pending)} result files")
    console.print(f"{OK} Uploaded {len(pending)} files: {address}")
    return 0


def _results_push(results: ResultsLibrary, files: list[Path]) -> int:
    """File telemetry driven elsewhere under its scenario, evaluate it, and upload it."""
    entries = ScenarioLibrary().entries()
    filed = []
    for path in files:
        try:
            telemetry = DrivingScenarioTelemetry.load(path)
        except Exception as error:
            raise LabError(f"{path} is not a telemetry file ({error}).") from error
        require_current_schema(telemetry.schema_version, path)
        entry = _scenario_of(telemetry, entries, path)
        driven = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = results.telemetry_path(entry.label, f"{driven}-local")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        filed.extend([target, results.evaluate(target)])
        console.print(f"{OK} {path.name} is a run of [bold]{entry.name}[/bold]  {entry.short}")
    address = results.upload(filed, f"Add {len(files)} runs driven outside the cluster")
    console.print(f"{OK} Uploaded: {address}")
    return 0


def _scenario_of(telemetry: DrivingScenarioTelemetry, entries: list[ScenarioEntry], path: Path) -> ScenarioEntry:
    fingerprint = telemetry.scenario_fingerprint
    if not fingerprint:
        raise LabError(
            f"{path} does not name the scenario it was driven from.",
            "Drive the scenario again from its file; telemetry now records the file's fingerprint.",
        )
    for entry in entries:
        if fingerprint.startswith(entry.short):
            return entry
    raise LabError(
        f"The scenario of {path} ({fingerprint[:12]}) is not in the library.",
        "Add it first with `uv run otter-scenarios push FILE.json.gz`.",
    )


# otter-build

@command
def otter_build(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="otter-build",
        description="Write the scenario set: each forecast, rolled with each seed, for every way of choosing a route. "
                    "The trip and weights are in otter.yaml.",
    )
    parser.add_argument("forecasts", nargs="*", metavar="FORECAST",
                        help=f"forecasts from pyotter's config.yaml (default all: {', '.join(World.forecast_names())})")
    parser.add_argument("--seeds", nargs="+", type=int, metavar="SEED",
                        help=f"seeds to roll with (default {' '.join(str(seed) for seed in SETTINGS.build.seeds)})")
    parser.add_argument("--output", type=Path, default=build.BUILT,
                        help=f"folder to write to (default {relative(build.BUILT)})")
    args = parser.parse_args(argv)
    forecasts = args.forecasts or World.forecast_names()
    seeds = args.seeds or list(SETTINGS.build.seeds)
    with console.status("building"):
        built = build.build(forecasts, seeds, args.output)
    listing = table("scenario", "planned", "events", "fingerprint")
    for item in built:
        listing.add_row(item.path.name.removesuffix(".json.gz"), f"{item.planned_s:.0f} s", str(item.events),
                        item.fingerprint[:12])
    console.print(listing)
    console.print(f"{OK} Wrote {len(built)} scenarios to {relative(args.output)}/")
    files = f"{relative(args.output)}/*.json.gz"
    next_steps([("Add them", f"uv run otter-scenarios push {files}"), ("Drive them", f"uv run otter-drive {files}")])
    return 0


# otter-check

@command
def otter_check(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="otter-check", description="Check what the lab commands need.").parse_args(argv)
    checks = [_check_login(), _check_repo(SETTINGS.scenarios_repo), _check_repo(SETTINGS.results_repo)]
    on_cluster = shutil.which("sbatch") is not None
    if on_cluster:
        checks += [_check_storage(), _check_image(), _check_server()]
    failed = 0
    for passed, line, hint in checks:
        console.print(f"{OK if passed else FAIL} {line}")
        if hint:
            console.print(f"  [dim]{hint}[/dim]")
        failed += not passed
    if not on_cluster:
        console.print(f"{NOTE} No Slurm here, so carla-server and otter-drive are for the cluster. "
                      "The library commands work.")
    return 1 if failed else 0


def _check_login() -> tuple[bool, str, str]:
    try:
        user = HfApi().whoami()["name"]
    except OSError:
        return False, "Hugging Face: not logged in", "Run `uv run hf auth login` with a token that can write."
    return True, f"Hugging Face: logged in as {user}", ""


def _check_repo(repo: str) -> tuple[bool, str, str]:
    try:
        HfApi().repo_info(repo, repo_type="dataset")
    except OSError:
        return False, f"{repo}: missing, or hidden from your login", \
            f"To create it: `uv run hf repos create {repo} --repo-type dataset`."
    return True, f"{repo}: reachable", ""


def _check_storage() -> tuple[bool, str, str]:
    try:
        folder = container.prepare_storage()
    except LabError as error:
        return False, str(error), error.hint
    return True, f"Image folder: {folder}", ""


def _check_image() -> tuple[bool, str, str]:
    image = container.image_path()
    if image.exists():
        return True, f"Toolchain image: {image.name}", ""
    return True, "Toolchain image: not fetched yet", "The first `uv run carla-server` fetches it, which takes a while."


def _check_server() -> tuple[bool, str, str]:
    job = server.live_job()
    if job is None:
        return True, "CARLA server: not running", "Start one with `uv run carla-server`."
    return True, f"CARLA server: job {job.job_id}, {server.describe(job, server.read_status(job.job_id))}", ""
