"""Low sun ahead of the ego through haze: the ego starts driving into the glare. Default traffic."""

import sys

from scenario import Scenario, run

ALTITUDE = 5.0
# Added to the ego's start yaw to put the sun ahead of it. Checked by eye in the window mode.
AZIMUTH_OFFSET = 180.0


def weather(start):
    return {
        "sun_altitude_angle": ALTITUDE,
        "sun_azimuth_angle": (start.rotation.yaw + AZIMUTH_OFFSET) % 360.0,
        "cloudiness": 10.0,
        "fog_density": 15.0,
        "fog_distance": 20.0,
        "mie_scattering_scale": 0.3,
    }


SCENARIO = Scenario("low-sun", __doc__, ticks=3600, weather=weather)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
