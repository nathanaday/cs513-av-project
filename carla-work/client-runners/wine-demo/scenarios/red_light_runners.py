"""Red-light runners: every background vehicle ignores traffic lights. The ego still stops at red."""

import sys

from scenario import Scenario, run


def setup(context):
    for vehicle in context.vehicles:
        context.tm.ignore_lights_percentage(vehicle, 100.0)
    context.settings["ignore_lights_percentage"] = 100.0


SCENARIO = Scenario("red-light-runners", __doc__, vehicles=60, ticks=3600, setup=setup)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
