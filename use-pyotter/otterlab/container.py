"""The toolchain image under Apptainer: fetch it once, and build the commands that run in it."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .console import LabError
from .settings import REPO, SETTINGS, storage

# Set by the image (carla/image/Dockerfile).
SERVER = "carla-server"
PYTHON = "/opt/otter/venv/bin/python"


def image_path() -> Path:
    """Where the converted image is, or will be. A new image name gives a new file."""
    name = re.sub(r"[^A-Za-z0-9.]+", "-", SETTINGS.image.split("/")[-1])
    return storage() / "images" / f"{name}.sif"


def prepare_storage() -> Path:
    """Create the image folder.

    Raises:
        LabError: If it cannot be created or written.
    """
    folder = image_path().parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise LabError(
            f"Cannot create {folder} for the toolchain image ({error.strerror}).",
            "Set OTTER_HOME to a folder of yours with about 15 GB free, or change `storage` in otter.yaml.",
        ) from error
    if not os.access(folder, os.W_OK):
        raise LabError(f"Cannot write to {folder}.", "Set OTTER_HOME to a folder of yours with about 15 GB free.")
    return folder


def ensure_image() -> Path:
    """Convert the toolchain image to a file Apptainer can run, unless that is already done.

    The image is written under a temporary name and renamed when complete, so
    an interrupted pull never leaves a file that looks finished.

    Raises:
        LabError: If the pull fails.
    """
    image = image_path()
    if image.exists():
        return image
    prepare_storage()
    partial = image.with_name(f".{image.name}.{os.getpid()}.partial")
    command = ["apptainer", "pull", "--disable-cache", str(partial), f"docker://{SETTINGS.image}"]
    done = subprocess.run(command)
    if done.returncode != 0 or not partial.exists():
        partial.unlink(missing_ok=True)
        raise LabError(
            f"Could not pull {SETTINGS.image}.",
            "If the image is private, export APPTAINER_DOCKER_USERNAME (your GitHub user) and "
            "APPTAINER_DOCKER_PASSWORD (a token with read:packages), then start the server again.",
        )
    partial.replace(image)
    return image


def run_in_image(image: Path, command: list[str], gpu: bool = False) -> list[str]:
    """The Apptainer command that runs `command` in the image.

    The repository is visible inside at its own path and pyotter is imported
    from it, so the code that drives is the code in this checkout.
    """
    start = ["apptainer", "exec", "--cleanenv"]
    if gpu:
        start.append("--nv")
    start.extend(["--bind", str(REPO), "--env", f"PYTHONPATH={REPO}", str(image)])
    return start + command


def server_command(image: Path, port: int) -> list[str]:
    arguments = list(SETTINGS.carla.arguments)
    arguments.append(f"-carla-rpc-port={port}")
    return run_in_image(image, [SERVER] + arguments, gpu=True)


def pyotter_command(image: Path, arguments: list[str]) -> list[str]:
    return run_in_image(image, [PYTHON, "-u", "-m", "pyotter"] + arguments)
