"""One allocated-node CARLA server/client pair with persistent logs and cleanup."""

import argparse
from datetime import datetime, timezone
import hashlib
import gzip
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def source_hash(root):
    digest = hashlib.sha256()
    excluded = {".git", ".venv", ".carla", "runs", "__pycache__", "models"}
    for directory, children, names in os.walk(root):
        children[:] = sorted(c for c in children if c not in excluded)
        for name in sorted(names):
            path = Path(directory) / name
            if name == ".DS_Store" or (name.startswith("slurm-") and name.endswith(".out")) or path.is_symlink():
                continue
            digest.update(str(path.relative_to(root)).encode() + b"\0")
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
    return digest.hexdigest()


def check_allocation():
    job = os.environ.get("SLURM_JOB_ID")
    nodes = os.environ.get("SLURM_JOB_NODELIST")
    if not job or not nodes or sys.platform != "linux":
        raise RuntimeError("Use salloc or sbatch on a Linux compute node first")
    allowed = subprocess.check_output(["scontrol", "show", "hostnames", nodes], text=True).split()
    if socket.gethostname().split(".")[0] not in allowed:
        raise RuntimeError("Current host is not a compute node in this allocation")
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid", "--format=csv,noheader"], text=True)
    if not gpu.strip():
        raise RuntimeError("No GPU visible in the allocation")
    return job, gpu.strip()


def check_ports(ports):
    held = []
    try:
        for port in ports:
            sock = socket.socket()
            held.append(sock)
            sock.bind(("0.0.0.0", port))
    except OSError as error:
        raise RuntimeError(f"Port {port} is unavailable; choose another --port/--tm-port") from error
    finally:
        for sock in held:
            sock.close()


def stop_process(process):
    if process is None:
        return
    # Signal only the process group created by this helper, including its children.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    # A wrapper may exit before its server children. Reap any remaining group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def wait_ready(server, port, timeout):
    import carla
    client = carla.Client("127.0.0.1", port)
    client.set_timeout(2.0)
    deadline = time.monotonic() + timeout
    while True:
        if server.poll() is not None:
            raise RuntimeError("CARLA exited during startup; inspect server.log")
        try:
            version = client.get_server_version()
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError("CARLA readiness timeout; inspect server.log")
            time.sleep(1)
    if version != "0.9.16" or client.get_client_version() != "0.9.16":
        raise RuntimeError(f"Version mismatch: client {client.get_client_version()}, server {version}")
    client.set_timeout(60.0)
    if client.get_world().get_map().name.split("/")[-1] != "Town10HD_Opt":
        client.load_world("Town10HD_Opt")
    if client.get_world().get_map().name.split("/")[-1] != "Town10HD_Opt":
        raise RuntimeError("Town10HD_Opt did not load")
    return {"client_version": client.get_client_version(), "server_version": version,
            "map": client.get_world().get_map().name}


def stream_output(pipe, destination):
    with destination.open("w", buffering=1) as log:
        for line in iter(pipe.readline, ""):
            log.write(line)
            print(line, end="", flush=True)
    pipe.close()


def capture_summary(path):
    """An exit code alone is insufficient: a tick-limited drive may not arrive."""
    result = {"reason": "incomplete", "collisions": 0}
    try:
        with gzip.open(path, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("type") == "event" and row.get("kind") == "collision":
                    result["collisions"] += 1
                elif row.get("type") == "end":
                    result["reason"] = row["reason"]
                    result["ticks"] = row["ticks"]
    except (EOFError, OSError, ValueError):
        result["reason"] = "incomplete"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--tm-port", type=int, default=8000)
    parser.add_argument("--startup-timeout", type=float, default=180)
    parser.add_argument("client", nargs=argparse.REMAINDER, help="smoke, or -- followed by Python arguments")
    args = parser.parse_args()
    server = client_process = None
    output_thread = None
    run_dir = None
    record = {"status": "incomplete", "started_utc": datetime.now(timezone.utc).isoformat()}
    exit_code = 1

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        job, gpu = check_allocation()
        if not (1024 <= args.port <= 65533 and 1024 <= args.tm_port <= 65535):
            raise RuntimeError("Invalid port range")
        ports = [args.port, args.port + 1, args.port + 2, args.tm_port]
        if len(set(ports)) != 4:
            raise RuntimeError("RPC, streaming, secondary, and Traffic Manager ports must differ")
        check_ports(ports)
        home = args.home.resolve()
        environment = json.loads((home / "environment.json").read_text())
        image = Path(environment["image"])
        stat = image.stat()
        if stat.st_size != environment["image_size"] or stat.st_mtime_ns != environment["image_mtime_ns"]:
            raise RuntimeError("Image changed; rerun setup to record its checksum")
        work = Path(__file__).resolve().parent.parent
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        run_dir = home / "runs" / f"{stamp}-job{job}"
        run_dir.mkdir(parents=True)
        parameters = list(args.client)
        if parameters[:1] == ["--"]:
            parameters.pop(0)
        smoke = parameters == ["smoke"]
        if smoke:
            parameters = [str(work / "client-runners/demo/test_data_capture.py"), "--vehicles", "0",
                          "--walkers", "0", "--ticks", "2400", "--speed", "30", "--seed", "0",
                          "--no-follow", "--log", str(run_dir / "run.jsonl.gz")]
        elif not parameters:
            raise RuntimeError("Choose smoke, or provide -- followed by Python client arguments")
        parameters += ["--host", "127.0.0.1", "--port", str(args.port)]
        child_env = dict(os.environ)
        child_env.update(PYTHONPATH=os.pathsep.join([environment["agents_root"], str(work / "client-runners")]),
                         CARLA_RUN_DIR=str(run_dir), CARLA_TM_PORT=str(args.tm_port),
                         PYTHONUNBUFFERED="1")
        command = ["apptainer", "exec", "--cleanenv", "--nv", "--bind", str(home), "--bind", str(work),
                   "--pwd", environment["server_root"]]
        if "CUDA_VISIBLE_DEVICES" in os.environ:
            command += ["--env", "CUDA_VISIBLE_DEVICES=" + os.environ["CUDA_VISIBLE_DEVICES"]]
        command += [str(image), "bash", environment["server_root"] + "/CarlaUE4.sh", "-RenderOffScreen",
                    "-nosound", "-quality-level=Low", f"-carla-rpc-port={args.port}",
                    f"-abslog={run_dir / 'unreal.log'}", f"-userdir={run_dir / 'unreal'}"]
        record.update(job_id=job, hostname=socket.gethostname(), gpu=gpu, environment=environment,
                      source_hash=source_hash(work.parent), client_args=parameters, server_args=command,
                      allocated_gpus=os.environ.get("SLURM_JOB_GPUS"),
                      cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"))
        save(run_dir / "manifest.json", record)
        print(f"Persistent run directory: {run_dir}", flush=True)
        with (run_dir / "server.log").open("w") as server_log:
            server = subprocess.Popen(command, stdout=server_log, stderr=subprocess.STDOUT,
                                      start_new_session=True, env=child_env)
            record["connection"] = wait_ready(server, args.port, args.startup_timeout)
            record["status"] = "running"
            save(run_dir / "manifest.json", record)
            client_process = subprocess.Popen([environment["python"], *parameters], cwd=work, env=child_env,
                                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                              text=True, bufsize=1, start_new_session=True)
            output_thread = threading.Thread(target=stream_output, args=(client_process.stdout, run_dir / "client.log"))
            output_thread.start()
            while client_process.poll() is None:
                if server.poll() is not None:
                    raise RuntimeError("CARLA exited while the client was running")
                time.sleep(0.2)
            exit_code = client_process.returncode
            record["status"] = "completed" if exit_code == 0 else "failed"
            if (run_dir / "run.jsonl.gz").exists():
                record["simulation"] = capture_summary(run_dir / "run.jsonl.gz")
                if record["simulation"]["reason"] != "arrived":
                    record["status"], exit_code = "incomplete", 1
                elif smoke and record["simulation"]["collisions"]:
                    record["status"], exit_code = "failed", 1
    except KeyboardInterrupt:
        record["status"], exit_code = "interrupted", 130
    except Exception as error:
        record.update(status="failed", error=str(error))
        print(f"error: {error}", file=sys.stderr)
    finally:
        # Ignore further termination signals while shutting down our own processes.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        stop_process(client_process)
        stop_process(server)
        if output_thread:
            output_thread.join(timeout=5)
        if run_dir:
            record.update(finished_utc=datetime.now(timezone.utc).isoformat(), exit_code=exit_code)
            save(run_dir / "manifest.json", record)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
