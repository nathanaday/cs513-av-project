# Record and replay a CARLA run

A headless server shows nothing on screen. This page records a run to a file, then plays the file back in the [Rerun](https://rerun.io) viewer: the roads, buildings, and parked cars, the ego, the traffic, and the pedestrians, all in motion, with a timeline you can drag.

To see a run before you install anything, open the demo capture in your browser: [town10-bus-collision in the Rerun web viewer](https://app.rerun.io/version/0.38.1/?url=https://huggingface.co/datasets/nadayusc/carla-rerun-scenarios/resolve/main/captures/town10-bus-collision/run.rrd). Published captures are in the public dataset [nadayusc/carla-rerun-scenarios](https://huggingface.co/datasets/nadayusc/carla-rerun-scenarios) on Hugging Face.

Run every command from the `carla-work` folder.

## What you need

- A running server: `scripts/carla-server` (see [headless-carla.md](headless-carla.md)). Any mode works.
- `uv`, to run the viewer in native macOS Python: `brew install uv`.

The first `scripts/carla-replay` installs Python 3.12 and the pinned packages (`rerun-sdk` 0.38.1) into `replay/.venv`. This takes a minute. Later runs start at once. The versions are fixed in `replay/uv.lock`, so every machine gets the same viewer.

## Record a run

With the server up, in a second terminal:

```bash
scripts/carla-python client-runners/demo/test_data_capture.py
```

The script spawns 30 background vehicles under Traffic Manager and 30 pedestrians, then drives the ego with `BasicAgent` to a destination. It records every tick to `runs/<UTC time>.jsonl.gz`. To record a drive in rain, low sun, heavy traffic, or another situation, run a demo scenario instead: see [scenarios.md](scenarios.md).

```
ego vehicle.tesla.model3 id=271  spawn 0  vehicles 30  walkers 30
recording to runs/demo.jsonl.gz
  sim_s   km/h        x        y   thr   brk  steer
   0.05    8.8    -64.6     24.5  0.75  0.00   0.01
   6.40 EVENT lane_invasion: {'markings': ['Broken']}
   7.10 EVENT lane_invasion: {'markings': ['Broken']}
  15.20 EVENT lane_invasion: {'markings': ['NONE']}
  26.50 EVENT collision: {'other_id': 287, 'other_type': 'vehicle.mitsubishi.fusorosa', 'impulse': 84.5}
  60.00    0.0     46.0     67.0  0.00  0.50   0.22
 120.00    0.0     46.0     67.0  0.00  0.50   0.22
 180.00    0.0     46.0     67.0  0.00  0.50   0.22
summary  sim 235.7 s  wall 57.6 s  ratio 4.09  distance 395 m  collisions 1  lane_invasions 3  arrived
```

In this run the ego hits a bus at 26.5 s and waits behind it for almost three minutes. The replay shows why.

Options:

| Option | Default | Effect |
|---|---|---|
| `--vehicles N` | 30 | Background vehicles. |
| `--walkers M` | 30 | Pedestrians. |
| `--log PATH` | `runs/<UTC time>.jsonl.gz` | Where to write the run file. |
| `--no-log` | off | Record nothing. |
| `--seed N` | 0 | Seed for the destination and the traffic. |
| `--spawn I` | 0 | Spawn point of the ego. |
| `--ticks N` | 0 | Stop after N ticks. 0 drives until the ego arrives. |
| `--speed K` | 30 | Target speed of the ego in km/h. |
| `--every S` | 5 | Simulated seconds between telemetry lines. |

Stop a run with Ctrl+C. On every exit the script destroys everything it spawned, restores the world settings, and closes the run file, so the file stays readable.

`runs/` is not in git. To keep a run, copy the file somewhere else.

## Open a run

```bash
scripts/carla-replay runs/demo.jsonl.gz
```

```
Town10HD_Opt: 4714 ticks (235.7 sim s), 83 actors; opened in the Rerun viewer
```

The viewer opens with the map seen from above. Press play in the time panel at the bottom, or drag the time cursor to any moment. Scroll to zoom, and drag to turn the view. Click an object to see its name and id.

| Color | Object |
|---|---|
| Red-orange, labeled | The ego. Its path is the orange line. |
| Blue | Background vehicles. Dark blue: trucks and buses. Purple: motorcycles and bicycles. |
| Green | Pedestrians. |
| Gray-blue | Parked vehicles. They are part of the map, not actors. |
| Red, yellow, green cube | A traffic light, in its state at that moment. |
| Orange outline | A junction. |
| White outline | A crosswalk. |

The panels on the right show the ego's speed and the events: collisions and lane crossings.

To make the 3D view follow the ego, add `--follow`.

## Write a .rrd file

```bash
scripts/carla-replay runs/demo.jsonl.gz --rrd demo.rrd
```

A `.rrd` file opens in any Rerun viewer of version 0.38.1 or later: `rerun demo.rrd`, or drag the file into the [web viewer](https://www.rerun.io/viewer). To share a run as a link, publish it as a capture: see [publishing.md](publishing.md). The demo run is 3.2 MB as a run file and 9.0 MB as `.rrd`. Keep and share the run file. The `.rrd` file can always be made again from it.

## Rerun's usage data

Rerun sends anonymous usage data by default. To turn it off:

```bash
uv run --project replay rerun analytics disable
```

## Measurements

Measured on 2026-10-04 on a MacBook Pro M4 Pro, 48 GB, with the default server mode and the run above: 30 vehicles, 30 walkers, 4,714 ticks.

| | With `--log` | With `--no-log` |
|---|---|---|
| Wall time, three runs | 56.3 s, 56.0 s, 56.9 s | 52.5 s, 52.6 s, 53.2 s |
| Simulated seconds per wall second | 4.18 (mean) | 4.44 (mean) |
| Run file | 3.2 MB | none |

Logging adds about 7% to the wall time. The scene record and the per-tick records add little: the traffic itself is what slows the run, from about 20 simulated seconds per wall second with the ego alone to about 4.4.

`scripts/carla-replay` reads and converts this run in about 1 second.

## Files

| File | Purpose |
|---|---|
| `client-runners/demo/test_data_capture.py` | Drives the ego among traffic and records the run. |
| `client-runners/scenario.py` | The runner that `test_data_capture.py` and the scenarios share: spawn, drive, record, clean up. |
| `client-runners/scenarios/` | The demo scenarios. See [scenarios.md](scenarios.md). |
| `client-runners/runlog.py` | Writes a run file. Any client script can use it (see below). |
| `docs/run-format.md` | The run file format. |
| `scripts/carla-replay` | Opens a run file in the viewer, or writes `.rrd`. |
| `scripts/carla-publish` | Publishes a run as a capture in the public dataset. See [publishing.md](publishing.md). |
| `replay/` | The viewer's Python project: `carla_replay.py`, `carla_publish.py`, `pyproject.toml`, `uv.lock`. |

## Record your own script

`scripts/carla-python` puts `client-runners` on the Python path, so any client script can import `runlog`. Run the world in synchronous mode, and call `tick` once after each `world.tick()`:

```python
from runlog import RunLog

with RunLog("runs/my-run.jsonl.gz", client, world, ego=vehicle, argv=sys.argv) as log:
    while driving:
        world.tick()
        log.tick(world.get_snapshot())
```

Call `log.event(kind, timestamp, **fields)` to record an event, such as a collision from a sensor callback.
