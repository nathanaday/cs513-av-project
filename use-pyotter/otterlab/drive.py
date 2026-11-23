"""The drive job: drive one scenario on the running server, evaluate it, and publish the result."""

from __future__ import annotations

import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import container, server, slurm
from .console import LabError
from .library import ResultsLibrary
from .settings import SETTINGS

UPLOAD_FAILED = 3


def job_name(server_job_id: str) -> str:
    """The name shared by every drive on one server, so that Slurm runs them one at a time."""
    return f"otter-drive-{server_job_id}"


def submit(scenario_file: Path, scenario_label: str, server_job_id: str, time: str | None = None) -> str:
    """Queue one drive behind the server job and behind the drives already queued on it.

    Returns:
        The drive's job id.
    """
    arguments = ["drive", str(scenario_file), scenario_label, server_job_id]
    dependency = f"after:{server_job_id},singleton"
    return slurm.submit(job_name(server_job_id), "drive", arguments, time=time, dependency=dependency)


def run_id() -> str:
    """A name for this run: when it started, and the job or machine that drove it."""
    moment = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    origin = os.environ.get("SLURM_JOB_ID") or socket.gethostname().split(".")[0]
    return f"{moment}-{origin}"


def drive(scenario_file: Path, scenario_label: str, server_job_id: str) -> int:
    """Drive a scenario. This is the body of the drive job.

    Returns:
        The job's exit status: 0, 1 if the drive failed, or 3 if only the upload failed.
    """
    try:
        print(f"==> waiting for the CARLA server (job {server_job_id})", flush=True)
        status = server.wait_until_ready(server_job_id, on_change=lambda line: print(f"    {line}", flush=True))
        run = run_id()
        telemetry = ResultsLibrary.telemetry_path(scenario_label, run)
        telemetry.parent.mkdir(parents=True, exist_ok=True)
        print(f"==> driving {scenario_label} on {status.host}:{status.port}", flush=True)
        arguments = ["drive", str(scenario_file), "--output", str(telemetry),
                     "--host", status.host, "--port", str(status.port)]
        done = subprocess.run(container.pyotter_command(container.image_path(), arguments))
        if done.returncode != 0 or not telemetry.exists():
            raise LabError(f"The drive failed with status {done.returncode}.")
        evaluation = ResultsLibrary.evaluate(telemetry)
        print(f"==> saved {telemetry}", flush=True)
    except LabError as error:
        print(f"==> failed: {error} {error.hint}", flush=True)
        return 1
    try:
        address = ResultsLibrary().upload([telemetry, evaluation], f"Add run {run} of {scenario_label}")
    except LabError as error:
        print(f"==> not uploaded: {error}", flush=True)
        print("    The files above are safe. Upload them with `uv run otter-results sync`.", flush=True)
        return UPLOAD_FAILED
    print(f"==> uploaded to {SETTINGS.results_repo}: {address}", flush=True)
    return 0
