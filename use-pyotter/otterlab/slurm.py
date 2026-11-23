"""The three Slurm commands the lab uses: sbatch, squeue and scancel."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .console import LabError
from .settings import LAB, LOGS, SETTINGS

JOB_SCRIPT = Path(__file__).with_name("job.sbatch")
WAITING = ("PENDING", "CONFIGURING")
ALIVE = WAITING + ("RUNNING",)


@dataclass(frozen=True)
class Job:
    """A job as squeue reports it.

    Attributes:
        state: Slurm's state name, such as PENDING or RUNNING.
        node: The node it runs on, or empty while it waits.
        reason: Why it waits.
        elapsed: How long it has run, as Slurm prints it.
        left: How long until its time limit, as Slurm prints it.
    """

    job_id: str
    state: str
    node: str
    reason: str
    elapsed: str
    left: str

    @property
    def alive(self) -> bool:
        return self.state in ALIVE

    @property
    def running(self) -> bool:
        return self.state == "RUNNING"


def require() -> None:
    """Refuse to go on where there is no Slurm.

    Raises:
        LabError: If sbatch is not on the path.
    """
    if shutil.which("sbatch") is None:
        raise LabError(
            "This command queues Slurm jobs, and there is no sbatch here.",
            "Run it on a CARC Discovery login node. On macOS, use carla/wine/server instead.",
        )


def log_path(job_id: str) -> Path:
    return LOGS / f"{job_id}.log"


def submit(name: str, kind: str, arguments: list[str], time: str | None = None,
           dependency: str = "") -> str:
    """Queue the lab's job script and return the job id.

    Args:
        name: The job's name in the queue.
        kind: `server` or `drive`: which resources in the settings to ask for.
        arguments: What the job runs, passed to `python -m otterlab.jobs`.
        time: A time limit to use in place of the configured one.
        dependency: A Slurm dependency expression, or empty.

    Raises:
        LabError: If Slurm refuses the job.
    """
    resources = getattr(SETTINGS.slurm, kind)
    LOGS.mkdir(parents=True, exist_ok=True)
    command = [
        "sbatch", "--parsable", "--export=ALL",
        f"--job-name={name}",
        f"--account={SETTINGS.slurm.account}",
        f"--partition={resources.partition}",
        "--nodes=1", "--ntasks=1",
        f"--cpus-per-task={resources.cpus}",
        f"--mem={resources.memory}",
        f"--time={time or resources.time}",
        f"--output={LOGS}/%j.log",
        f"--chdir={LAB}",
    ]
    if dependency:
        command.append(f"--dependency={dependency}")
    command.extend(resources.options)
    command.append(str(JOB_SCRIPT))
    command.extend(arguments)
    environment = dict(os.environ)
    environment["OTTER_PYTHON"] = sys.executable
    environment["OTTER_MODULES"] = " ".join(SETTINGS.slurm.modules)
    done = subprocess.run(command, capture_output=True, text=True, env=environment)
    if done.returncode != 0:
        raise LabError(
            f"Slurm refused the job: {done.stderr.strip() or done.stdout.strip()}",
            "Check the account and partition in otter.yaml against `myaccount` and `sinfo`.",
        )
    return done.stdout.strip().split(";")[0]


def find(job_id: str) -> Job | None:
    """The job as it stands in the queue, or None once it has left."""
    done = subprocess.run(
        ["squeue", "--noheader", "--jobs", job_id, "--format", "%T|%N|%r|%M|%L"],
        capture_output=True, text=True,
    )
    line = done.stdout.strip()
    if done.returncode != 0 or not line:
        return None
    state, node, reason, elapsed, left = line.splitlines()[0].split("|")
    return Job(job_id, state, node, reason, elapsed, left)


def cancel(job_id: str) -> None:
    subprocess.run(["scancel", job_id], capture_output=True, text=True)
