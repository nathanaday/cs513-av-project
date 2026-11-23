"""What runs inside a lab job: `python -m otterlab.jobs serve` or `... drive FILE LABEL SERVER_JOB`."""

from __future__ import annotations

import sys
from pathlib import Path

from . import drive, server


def main(argv: list[str]) -> int:
    if argv[0] == "serve":
        return server.serve()
    scenario_file, scenario_label, server_job_id = argv[1:]
    return drive.drive(Path(scenario_file), scenario_label, server_job_id)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
