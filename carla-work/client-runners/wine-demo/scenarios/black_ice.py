"""Black ice: every vehicle, the ego included, has a fraction of its normal tire grip on a cold, wet road."""

import sys

from scenario import Scenario, run

TIRE_FRICTION = 0.5


def setup(context):
    for vehicle in [context.ego] + context.vehicles:
        physics = vehicle.get_physics_control()
        wheels = physics.wheels
        for wheel in wheels:
            wheel.tire_friction = TIRE_FRICTION
        physics.wheels = wheels
        vehicle.apply_physics_control(physics)
    context.settings["tire_friction"] = TIRE_FRICTION


SCENARIO = Scenario(
    "black-ice",
    __doc__,
    ticks=3600,
    setup=setup,
    weather={
        "cloudiness": 80.0,
        "wetness": 60.0,
        "precipitation_deposits": 20.0,
        "sun_altitude_angle": 15.0,
        "fog_density": 10.0,
    },
)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
