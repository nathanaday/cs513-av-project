"""Traffic light blackout: every traffic light is off, so no junction has a signal."""

import sys

import carla

from scenario import Scenario, run


def setup(context):
    world = context.world
    world.freeze_all_traffic_lights(True)
    for light in world.get_actors().filter("traffic.traffic_light"):
        light.set_state(carla.TrafficLightState.Off)
    context.settings["traffic_lights"] = "Off"

    def undo():
        world.freeze_all_traffic_lights(False)
        world.reset_all_traffic_lights()

    return undo


SCENARIO = Scenario("blackout", __doc__, vehicles=60, ticks=3600, setup=setup)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
