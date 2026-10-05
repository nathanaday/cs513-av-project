"""Drive the ego with BasicAgent among background traffic and record the run with runlog.

Run from carla-work:
  scripts/carla-python client-runners/demo/test_data_capture.py [--vehicles N] [--walkers M] [--log PATH]
Open the run with scripts/carla-replay.
"""

import sys

from scenario import Scenario, run

SCENARIO = Scenario(None, __doc__.splitlines()[0])

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
