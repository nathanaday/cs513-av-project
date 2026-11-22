"""Quiet-world integration demo; BasicAgent is not the final safety evaluator."""

import sys

from scenario import Scenario, run


if __name__ == "__main__":
    if "--plan" not in sys.argv or "--catalog" not in sys.argv:
        sys.exit("Supply --plan and --catalog. See docs/planner.md.")
    sys.exit(run(Scenario("planner-demo", __doc__, vehicles=0, walkers=0, ticks=6000)))
