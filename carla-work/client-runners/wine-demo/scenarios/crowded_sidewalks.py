"""Crowded sidewalks: 150 pedestrians and only 10 background vehicles."""

import sys

from scenario import Scenario, run

SCENARIO = Scenario("crowded-sidewalks", __doc__, vehicles=10, walkers=150, ticks=3600)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
