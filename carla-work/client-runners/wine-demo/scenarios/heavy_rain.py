"""Heavy rain at noon: full cloud, standing water, strong wind, and fog. Default traffic."""

import sys

from scenario import Scenario, run

SCENARIO = Scenario(
    "heavy-rain",
    __doc__,
    ticks=3600,
    weather={
        "cloudiness": 100.0,
        "precipitation": 100.0,
        "precipitation_deposits": 90.0,
        "wetness": 100.0,
        "wind_intensity": 100.0,
        "fog_density": 25.0,
        "fog_distance": 10.0,
    },
)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
