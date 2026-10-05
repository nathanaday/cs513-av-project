"""High traffic: about 120 background vehicles on Town10's roads, with the default pedestrians."""

import sys

from scenario import Scenario, run

SCENARIO = Scenario("high-traffic", __doc__, vehicles=120, walkers=30, ticks=3600)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
