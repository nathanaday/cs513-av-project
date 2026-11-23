"""The lab's settings and the folders it works in."""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from pyotter.core.utilities.config import load_config

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
SETTINGS = load_config(LAB / "otter.yaml")

RUNS = LAB / "runs"
LOGS = LAB / "logs"
STATE = LAB / ".otter"


def storage() -> Path:
    """Where the converted toolchain image is kept."""
    override = os.environ.get("OTTER_HOME")
    if override:
        return Path(override).expanduser()
    return Path(SETTINGS.storage.format(user=getpass.getuser()))


def relative(path: Path) -> str:
    """A path as the user would type it from where they stand."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)
