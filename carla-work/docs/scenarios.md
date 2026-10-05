# Demo driving scenarios

Each scenario drives the ego with CARLA's `BasicAgent` in a different situation and records the run. Open the run in the replay viewer ([replay.md](replay.md)), or publish it as a capture ([publishing.md](publishing.md)).

The scenarios are in `client-runners/scenarios/`. They all use the loaded map, Town10HD_Opt.

Run every command from the `carla-work` folder.

## Run a scenario

Start the server (see [headless-carla.md](headless-carla.md)), then run the scenario's file in a second terminal:

```bash
scripts/carla-python client-runners/scenarios/jaywalker_swarm.py
```

```
scenario jaywalker-swarm: Jaywalker swarm: pedestrians walk back and forth across the road along the ego's route, away from crosswalks.
ego vehicle.tesla.model3 id=4217  spawn 0  vehicles 10  walkers 60
recording to Z:\Users\...\carla-work\runs\jaywalker-swarm-20261005-003018.jsonl.gz
  sim_s   km/h        x        y   thr   brk  steer
   0.05    8.8    -64.6     24.5  0.75  0.00   0.01
...
  15.05 EVENT collision: {'other_id': 3966, 'other_type': 'walker.pedestrian.0047', 'impulse': 0.0}
...
summary  sim 52.4 s  wall 18.1 s  ratio 2.90  distance 395 m  collisions 1  lane_invasions 4  arrived
```

The run file is `runs/<scenario>-<UTC time>.jsonl.gz`. The run ends when the ego arrives, or at the scenario's time limit. The last word of the summary says which: `arrived` or `stopped`.

Every scenario takes the options of `test_data_capture.py` (see [replay.md](replay.md)). An option on the command line overrides the scenario's value:

```bash
scripts/carla-python client-runners/scenarios/high_traffic.py --vehicles 80 --seed 3
```

The same seed gives the same actors at the same start positions and the same weather. Later positions can drift between runs: one headless drive arrived after 49.2 to 55.2 simulated seconds over several runs.

On every exit the scenario restores what it changed in the world: the synchronous mode, the weather, and the traffic lights. It destroys every actor it spawned.

## The scenarios

| File | Name | What it sets | Time limit |
|---|---|---|---|
| `heavy_rain.py` | `heavy-rain` | Rain 100, standing water 90, wetness 100, cloud 100, wind 100, fog 25. Noon sun. 30 vehicles, 30 pedestrians. | 180 s |
| `low_sun.py` | `low-sun` | Sun 5° above the horizon, ahead of the ego at its start. Fog 15, more haze. Spawn point 18, which faces west on an open road, and seed 38, whose route heads into the sun for 189 of its 500 m. 30 vehicles, 30 pedestrians. | 180 s |
| `high_traffic.py` | `high-traffic` | 120 vehicles, 30 pedestrians. | 180 s |
| `crowded_sidewalks.py` | `crowded-sidewalks` | 10 vehicles, 150 pedestrians. | 180 s |
| `red_light_runners.py` | `red-light-runners` | 60 vehicles. Traffic Manager makes each one ignore traffic lights. The ego still stops at red. | 180 s |
| `blackout.py` | `blackout` | 60 vehicles. Every traffic light is off and frozen. | 180 s |
| `jaywalker_swarm.py` | `jaywalker-swarm` | 10 vehicles, 60 pedestrians on the sidewalks, and a jaywalker every 15 m of the ego's route, away from junctions and crosswalks. Each jaywalker waits a random time, then walks across the road and back, again and again. Their `role_name` is `"jaywalker"`. | 180 s |
| `black_ice.py` | `black-ice` | Tire friction 0.5 on every wheel of every vehicle, the ego included. The default is 3.5. Cold, overcast, wet road. 30 vehicles, 30 pedestrians. | 180 s |

`BasicAgent` brakes for vehicles and red lights, not for pedestrians. In `jaywalker-swarm` the ego hits jaywalkers.

## What the runs show

Measured on 2026-10-05 with each scenario's default seed and spawn point (0 and 0, except `low-sun`), in the default server mode, except `low-sun` in the window mode:

| Scenario | End | What the run file shows |
|---|---|---|
| `heavy-rain` | stopped at 180 s | The ego hits a bus at 26.5 s and waits behind it. The same happens in a clear run with this seed. |
| `low-sun` | arrived at 99.3 s | Spawn 18, seed 38 (its defaults). The sun is within 30° of the ego's heading for 189 m of the 500 m drive. |
| `high-traffic` | arrived at 62.8 s | 120 vehicles. |
| `crowded-sidewalks` | arrived at 52.3 s | 150 pedestrians. 0.4% of pedestrian positions are on a driving lane outside a crosswalk. |
| `red-light-runners` | stopped at 180 s | Vehicles near a red light were stopped in 1,256 vehicle-ticks, against 14,006 in a run where they obey the lights. The ego hits the bus at 26.5 s. |
| `blackout` | arrived at 50.9 s | Every light is `Off` at every tick. The ego touches the bus at 18 s and drives on. |
| `jaywalker-swarm` | arrived at 52.3 s | 17 jaywalkers. 11.9% of pedestrian positions are on a driving lane outside a crosswalk. The ego hits a jaywalker at 15 s. |
| `black-ice` | arrived at 60.2 s | The ego needs 6.5 m and 10.4 m to stop from 30 km/h, against 5.0 m on a dry road. It slides into a bus at 18 s. |

With seed 0, two scenarios end behind the bus. For a drive that arrives, try another `--seed`.

## What shows in each server mode

The default server mode (`-nullrhi`) draws nothing. The weather and the sun change only the image, and `BasicAgent` reads the true positions of the other actors, so they do not change the drive. A `heavy-rain` run and a clear run with the same seed drove the same path and hit the same bus at 26.5 s. The run file records the weather in its header, so a reader knows the conditions.

| Scenario | In the run file (any mode) | Only in the window or off-screen mode |
|---|---|---|
| `heavy-rain`, `low-sun` | The weather values in the header. | The rain, the wet road, the fog, the low sun and its glare. |
| `high-traffic`, `crowded-sidewalks`, `jaywalker-swarm` | The vehicles and the pedestrians, and where they go. | Nothing more. |
| `red-light-runners`, `blackout` | The vehicles, and the state of every light at each tick. | Nothing more. |
| `black-ice` | Longer stops, slides, and collisions. The friction is in the header's `settings`. | The wet road. |

To see the weather, run the server with `scripts/carla-server --window` (see [headless-carla.md](headless-carla.md) for the memory each mode needs). Use the default Epic quality for `low-sun`. At `--quality low` the server draws little of the haze and no bloom, so the low sun barely affects what you see. Camera frames from the same spot show the difference. The scenario moves the spectator to a point behind the ego on every tick, so the window shows the drive. To move the camera yourself, add `--no-follow`.

## The run header

A scenario writes three fields into the header of its run file (see [run-format.md](run-format.md)):

- `scenario`: the scenario's name, such as `"black-ice"`.
- `settings`: the counts, the speed, the limit, the seed, the spawn point, and the values that the scenario adds, such as `"tire_friction": 0.5` or `"jaywalkers": 17`.
- `weather`: every weather value at the start of the run.

## Write a new scenario

Add a file to `client-runners/scenarios/`. It declares a `Scenario` and runs it:

```python
"""Foggy midnight: dense fog, no sun, an empty town."""

import sys

from scenario import Scenario, run

SCENARIO = Scenario(
    "foggy-midnight",
    __doc__,
    vehicles=5,
    walkers=5,
    ticks=3600,
    weather={"sun_altitude_angle": -90.0, "fog_density": 80.0, "fog_distance": 5.0},
)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
```

The fields of `Scenario`, in `client-runners/scenario.py`:

| Field | Default | Meaning |
|---|---|---|
| `name` | required | The name in the header and in the run file's name. Lowercase words joined by hyphens. |
| `description` | required | One line. The script prints it and uses it as its `--help` text. |
| `vehicles`, `walkers` | 30, 30 | Background vehicles and pedestrians. |
| `speed` | 30 | Target speed of the ego in km/h. |
| `ticks` | 0 | The time limit in ticks of 0.05 s. 0 drives until the ego arrives. |
| `spawn`, `seed` | 0, 0 | The ego's spawn point, and the seed for its destination and the traffic. |
| `weather` | `None` | Fields of `carla.WeatherParameters`, set over the `ClearNoon` preset. Or a function that takes the ego's start transform and returns them, as in `low_sun.py`. `None` leaves the weather as it is. |
| `setup` | `None` | A function called once after every actor is spawned, with a `Context`. Before it changes the world or spawns an actor, it must register a function that undoes the change: `context.on_exit(undo)`. See `blackout.py`. |
| `step` | `None` | A function called after every tick, with the `Context` and the simulated seconds since the start. See `jaywalker_swarm.py`. |

The `Context` holds `client`, `world`, `tm` (Traffic Manager), `ego`, `route` (the ego's planned waypoints), `vehicles`, `walkers`, `rng`, `settings`, and `state`. Add each value that `setup` chooses to `settings`, so the header records it. Use `state` to pass data from `setup` to `step`.

The runner calls every registered undo when the scenario ends, however it ends, the last one first. It then destroys the actors and restores the settings and the weather. If one clean-up step fails, the runner still runs the others, then reports the first error.

Do not spawn a camera sensor: it crashes a `-nullrhi` server.

CARLA's `world.set_pedestrians_cross_factor` is not used: with 120 pedestrians over 180 s it gave the same pedestrian positions as no factor. To put pedestrians on the road, steer them with `carla.WalkerControl`, as `jaywalker_swarm.py` does.
