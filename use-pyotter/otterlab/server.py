"""The CARLA server job: what the lab knows about it, and the job itself.

Two files in `.otter/` describe the server. `server.json` names the job that
was submitted last. `server-JOB.json` is written by that job as it goes through
its phases. Whether the job is alive is always asked of Slurm.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import container, slurm
from .console import LabError
from .settings import SETTINGS, STATE, relative

POINTER = STATE / "server.json"

PULLING = "pulling"
STARTING = "starting"
READY = "ready"
STOPPED = "stopped"
FAILED = "failed"

STOP_GRACE_S = 10.0


@dataclass(frozen=True)
class ServerStatus:
    """What the server job last said about itself.

    Attributes:
        phase: One of pulling, starting, ready, stopped and failed, or empty
            before the job has started.
        host: The node the server runs on.
        port: The port the server answers on.
        detail: Why it failed.
    """

    phase: str = ""
    host: str = ""
    port: int = 0
    detail: str = ""


def _status_path(job_id: str) -> Path:
    return STATE / f"server-{job_id}.json"


def remember(job_id: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps({"job_id": job_id}) + "\n", encoding="utf-8")


def last_job_id() -> str:
    """The server job submitted last, or empty if there never was one."""
    if not POINTER.exists():
        return ""
    return json.loads(POINTER.read_text(encoding="utf-8"))["job_id"]


def read_status(job_id: str) -> ServerStatus:
    path = _status_path(job_id)
    if not path.exists():
        return ServerStatus()
    try:
        return ServerStatus(**json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        # The job is in the middle of writing it.
        return ServerStatus()


def write_status(job_id: str, status: ServerStatus) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    partial = _status_path(job_id).with_suffix(".partial")
    partial.write_text(json.dumps(asdict(status)) + "\n", encoding="utf-8")
    partial.replace(_status_path(job_id))


def live_job() -> slurm.Job | None:
    """The server job, if it is waiting or running."""
    job_id = last_job_id()
    if not job_id:
        return None
    job = slurm.find(job_id)
    if job is None or not job.alive:
        return None
    return job


def describe(job: slurm.Job, status: ServerStatus) -> str:
    """One line on where a live server job stands."""
    if not job.running:
        return f"waiting in the queue ({job.reason})"
    if status.phase == PULLING:
        return f"fetching the toolchain image on {job.node} (first start only)"
    if status.phase == READY:
        return f"ready on {status.host}:{status.port}"
    return f"starting CARLA on {job.node}"


def wait_until_ready(job_id: str, on_change=None) -> ServerStatus:
    """Block until the server answers.

    The time allowed for CARLA to start is counted from when the job launches
    it, so time in the queue and time fetching the image are not held against it.

    Args:
        on_change: Called with one line whenever the job's standing changes.

    Raises:
        LabError: If the job fails, leaves the queue, or does not answer in time.
    """
    log = relative(slurm.log_path(job_id))
    said = ""
    started_at = None
    while True:
        job = slurm.find(job_id)
        status = read_status(job_id)
        if status.phase == FAILED:
            raise LabError(f"The CARLA server failed: {status.detail}", f"Its log is {log}.")
        if job is None or not job.alive:
            raise LabError(
                f"The CARLA server (job {job_id}) is no longer running.",
                f"Its log is {log}. Start a new one with `uv run carla-server`.",
            )
        if status.phase == READY:
            return status
        if status.phase == STARTING and started_at is None:
            started_at = time.monotonic()
        allowed_s = SETTINGS.carla.start_timeout_s + 2 * SETTINGS.watch.poll_s
        if started_at is not None and time.monotonic() - started_at > allowed_s:
            raise LabError(
                f"CARLA did not answer within {SETTINGS.carla.start_timeout_s:g} s.",
                f"Its log is {log}.",
            )
        line = describe(job, status)
        if on_change is not None and line != said:
            on_change(line)
            said = line
        time.sleep(SETTINGS.watch.poll_s)


def _free_port() -> int:
    """The first port, from the configured one upward, whose next two are also free.

    CARLA listens on its port and the two after it.

    Raises:
        LabError: If none is free.
    """
    settings = SETTINGS.carla
    for attempt in range(settings.port_attempts):
        port = settings.port + attempt * settings.port_step
        if all(_is_free(port + offset) for offset in range(3)):
            return port
    raise LabError(f"No free port found from {settings.port} upward on {socket.gethostname()}.")


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("", port))
        except OSError:
            return False
    return True


def _stop(process: subprocess.Popen) -> None:
    """End CARLA and everything it started."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=STOP_GRACE_S)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def serve() -> int:
    """Run the server for the life of the job. This is the body of the server job.

    Slurm ends a job by signalling every process in it at once, so CARLA may
    exit before this process has handled its own signal. An exit after the
    signal is therefore a stop, and only an exit without one is a failure.

    Returns:
        The job's exit status.
    """
    job_id = os.environ["SLURM_JOB_ID"]
    host = socket.gethostname()
    asked_to_stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda signum, frame: asked_to_stop.set())
    server = None
    try:
        if not container.image_path().exists():
            write_status(job_id, ServerStatus(PULLING, host))
            print(f"==> fetching {SETTINGS.image}", flush=True)
        image = container.ensure_image()
        port = _free_port()
        write_status(job_id, ServerStatus(STARTING, host, port))
        print(f"==> starting CARLA on {host}:{port}", flush=True)
        server = subprocess.Popen(container.server_command(image, port), start_new_session=True)
        _await_answer(server, image, port, asked_to_stop)
        write_status(job_id, ServerStatus(READY, host, port))
        print(f"==> ready on {host}:{port}", flush=True)
        while server.poll() is None and not asked_to_stop.is_set():
            asked_to_stop.wait(1.0)
        if not asked_to_stop.is_set():
            raise LabError(f"CARLA exited with status {server.returncode}.")
    except LabError as error:
        if not asked_to_stop.is_set():
            write_status(job_id, ServerStatus(FAILED, host, detail=str(error)))
            print(f"==> failed: {error} {error.hint}", flush=True)
            return 1
    finally:
        if server is not None:
            _stop(server)
    write_status(job_id, ServerStatus(STOPPED, host))
    print("==> stopped", flush=True)
    return 0


def _await_answer(server: subprocess.Popen, image: Path, port: int, asked_to_stop: threading.Event) -> None:
    """Wait until the server answers a client.

    Raises:
        LabError: If CARLA exits first, does not answer in time, or the job is asked to stop.
    """
    timeout_s = SETTINGS.carla.start_timeout_s
    arguments = ["wait", "--port", str(port), "--timeout", f"{timeout_s:g}"]
    client = subprocess.Popen(container.pyotter_command(image, arguments))
    try:
        while client.poll() is None:
            if asked_to_stop.is_set():
                raise LabError("The job was stopped before CARLA answered.")
            if server.poll() is not None:
                raise LabError(f"CARLA exited with status {server.returncode} before it answered.")
            time.sleep(1.0)
    finally:
        if client.poll() is None:
            client.kill()
    if client.returncode != 0:
        raise LabError(f"CARLA did not answer within {timeout_s:g} s.")
