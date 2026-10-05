"""Jaywalker swarm: 120 pedestrians who cross the road anywhere, not only at crosswalks."""

import sys

from scenario import Scenario, run

SCENARIO = Scenario("jaywalker-swarm", __doc__, vehicles=10, walkers=120, ticks=3600, cross_factor=1.0)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
