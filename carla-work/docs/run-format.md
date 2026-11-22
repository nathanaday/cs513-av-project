# CARLA run file format, version 1

A run file records one CARLA run: the static scene once, then every tick. `client-runners/runlog.py` writes it. `scripts/carla-replay` reads it.

The file is gzip-compressed JSON lines, named `*.jsonl.gz`. Each line is one JSON object, a record. The `type` field names the record type. Records appear in this order:

1. one `header`
2. one `scene`
3. then, in time order, `actor`, `gone`, `tick`, and `event` records
4. one `end`, if the run closed cleanly

A reader must ignore fields it does not know. A new field does not change the version. A change that breaks a reader does.

## Units and coordinates

| Quantity | Unit |
|---|---|
| Position, size | meters |
| Angle | degrees |
| Velocity | meters per second |
| Time | seconds |

Coordinates are CARLA world coordinates, unchanged. CARLA's frame is **left-handed**: x points forward, y points right, z points up. Seen from above with x to the right, y points down the screen. A positive yaw turns from +x toward +y, which is clockwise seen from above.

A viewer with a right-handed frame must flip one axis. Negate y and yaw, or the run appears mirrored.

Values are rounded: positions and velocities to 3 decimals, angles to 2.

**Pose** is `[x, y, z, yaw, pitch, roll]`.

**Box** is `{"center": [x, y, z], "extent": [ex, ey, ez], "rotation": [yaw, pitch, roll]}`. `extent` is half the size along each axis of the box. A box in `scene` is in world coordinates. An actor's box has no `rotation`, and its `center` is relative to the actor's pose.

## `header`

| Field | Meaning |
|---|---|
| `format` | Always `"carla-run"`. |
| `version` | Format version: `1`. |
| `map` | Map name, for example `"Town10HD_Opt"`. |
| `client_version`, `server_version` | CARLA versions, for example `"0.9.16"`. |
| `delta_s` | Simulated seconds per tick. |
| `synchronous` | Whether the world ran in synchronous mode. |
| `ego_id` | Actor id of the ego vehicle, or `null`. |
| `argv` | The command line of the script that recorded the run. The first item is the script's file name, with no folder. |
| `started_utc` | When the recording started, ISO 8601. |
| `scenario` | Name of the scenario that recorded the run, such as `"heavy-rain"`, or `null` for a run not made by a scenario. See [scenarios.md](scenarios.md). |
| `settings` | The scenario's settings for this run, after command-line options: `vehicles`, `walkers`, `speed` (km/h), `ticks` (the limit; 0 means none), `seed`, `spawn`, and values that one scenario adds, such as `tire_friction`. Empty when the recording script gives none. |
| `weather` | The world's weather at the start of the run: every field of CARLA's `WeatherParameters`, such as `precipitation` (0 to 100), `fog_density` (0 to 100), `wetness` (0 to 100), `sun_altitude_angle` (degrees above the horizon), and `sun_azimuth_angle` (degrees). Rounded to 2 decimals. Files written before this field existed do not have it. |

## `scene`

The static scene, written once.

| Field | Meaning |
|---|---|
| `lanes` | Lane center lines. Each is `{"road", "section", "lane", "lane_type", "width", "junction", "points"}`. `points` is a list of `[x, y, z]`, 2 m apart, in driving order. `lane` is negative for lanes that run along the road's direction. `junction` is true for a lane inside a junction. |
| `junctions` | `{"id", ...box}`: the bounding box of each junction. |
| `crosswalks` | Polygons: each is a list of `[x, y, z]` corners. |
| `objects` | Static map objects: `{"id", "class", "name", ...box}`. `class` is a CARLA semantic class, such as `Buildings`, `Sidewalks`, `Poles`, `Fences`, `TrafficSigns`, `Car`, `Truck`, `Motorcycle`, `Bicycle`. Vegetation is left out. The vehicle classes are parked vehicles. They are part of the map, not actors. |

## `actor`

Written once per actor, at the first tick the actor exists. Actors with a `type_id` that starts with `vehicle.`, `walker.`, or `traffic.` are recorded. Sensors, AI controllers, and the spectator are not.

| Field | Meaning |
|---|---|
| `id` | Actor id. |
| `type_id` | Blueprint, for example `vehicle.tesla.model3`, `walker.pedestrian.0012`, `traffic.traffic_light`. |
| `base_type` | For vehicles, the blueprint's class as CARLA gives it, such as `"car"`, `"van"`, `"truck"`, `"Bus"`, `"motorcycle"`, or `"bicycle"`. Compare it without case. Some blueprints leave it empty. Empty for other actors. |
| `role_name` | `"hero"` for the ego, `"background"` for traffic from `test_data_capture.py` and the scenarios, `"jaywalker"` for the jaywalkers of `jaywalker-swarm`, else the blueprint's value. |
| `tick` | The tick at which the actor was first seen. |
| `pose` | Pose at that tick. For `traffic.*` actors, which do not move, this is their only pose. |
| `box` | Bounding box, with `center` relative to the pose. |

## `tick`

One record per simulation tick.

| Field | Meaning |
|---|---|
| `tick` | Tick number, from 0. |
| `frame` | CARLA frame number. |
| `t` | Simulated seconds since tick 0. |
| `actors` | One row per vehicle and walker: `[id, x, y, z, yaw, pitch, roll, vx, vy, vz]`. |
| `lights` | One row per traffic light: `[id, state]`. `state` is `"Red"`, `"Yellow"`, `"Green"`, `"Off"`, or `"Unknown"`. |

## `gone`

`{"id", "tick"}`: a vehicle or walker that existed on the previous tick and is missing from this one.

## `event`

An event of the ego, at the tick it was recorded.

| Field | Meaning |
|---|---|
| `kind` | `"collision"`, `"lane_invasion"`, or `"plan_target"`. Readers may ignore unknown kinds. |
| `tick`, `t` | Tick and simulated seconds. |
| `other_id`, `other_type`, `impulse` | For a collision: the other actor and the impulse in N·s. A contact is recorded once, and again only after one simulated second without contact with that actor. |
| `markings` | For a lane invasion: the crossed marking types, such as `"Broken"`, `"Solid"`, or `"NONE"` where the road has no paint. |
| `segment_id`, `target_speed_kmh`, `planned_speed_kmh`, `live_speed_limit_kmh`, `progress_m` | For `plan_target`: a change in the Planner segment or speed command. The live speed limit can lower the command. These are instructions/diagnostics, not measured safety events. |

## `end`

| Field | Meaning |
|---|---|
| `ticks` | Number of tick records. |
| `reason` | `"arrived"`, `"stopped"`, `"interrupted"`, or `"error"`. |
| `wall_s` | Wall-clock seconds of the run, or `null`. |

A file with no `end` record was cut off, for example by `kill -9`. Its records up to the cut are still valid, but the last line can be incomplete.

## Read a run file

For a run report, `scripts/run-report RUN.jsonl.gz [--plan PLAN.json] [--catalog CATALOG.json.gz]`
prints Markdown summarizing the run. It covers the outcome, distance, simulated and wall time,
moving and stopped time, stops with the nearest traffic light, and speed tracking. For a Planner
drive it also prints a per-segment table: planned and commanded speed, live and catalog limits,
distance, time, and speed. The plan and catalog default to `plan.json` and `catalog.json.gz`
next to the run file, as the HPC helper saves them. It uses only the standard library, so any
native Python 3.10+ runs it.

To read the format directly:

```python
import gzip
import json

actors, positions = {}, {}
with gzip.open("runs/example.jsonl.gz", "rt") as f:
    for line in f:
        record = json.loads(line)
        if record["type"] == "actor":
            actors[record["id"]] = record["type_id"]
        elif record["type"] == "tick":
            for actor_id, x, y, *_ in record["actors"]:
                positions.setdefault(actor_id, []).append((record["t"], x, y))

print(len(actors), "actors;", sum(map(len, positions.values())), "positions")
```
