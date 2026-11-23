# Driving Scenarios in CARLA

This folder holds the launch scripts for driving a pyotter scenario on a CARLA 0.9.16 server. The reader is a teammate who has a scenario file and wants its telemetry.

One command does the driving in every environment:

```bash
python -m pyotter drive SCENARIO.json.gz
```

It connects to a running CARLA server, drives the scenario, writes `SCENARIO-telemetry.json.gz` beside the scenario file, and prints the safety evaluation. The scripts here start a server, run that command, and stop the server.

A scenario file is self-contained: it holds the road graph, the rolled hazards, the route, and the driver. Build one with `use-pyotter/drive_scenario.ipynb`, which writes to `use-pyotter/runs/`.

| Environment | Status on November 22, 2026 |
|---|---|
| macOS with the Wine wrapper | Driven: three scenarios arrived and produced telemetry |
| CARC Discovery | Written, not yet run |
| Docker on Linux with an NVIDIA GPU | Written, not yet run |

## CARC Discovery

Copy the repo to Discovery, then prepare once on a compute node:

```bash
salloc --account=jdeshmuk_786 --partition=gpu --nodes=1 --ntasks=1 \
  --cpus-per-task=8 --mem=32G --gpus-per-task=a40:1 --time=02:00:00
module load conda apptainer
bash use-pyotter/carla/carc/setup.sh
```

`setup.sh` pulls the CARLA 0.9.16 server image and creates a Python 3.10 environment with the CARLA client and pyotter. Both go under `OTTER_HOME`, which defaults to `/project2/jdeshmuk_786/$USER/otter`.

Then drive, either inside an allocation:

```bash
module load apptainer
bash use-pyotter/carla/carc/run.sh use-pyotter/runs/*-naive.json.gz use-pyotter/runs/*-risk-aware.json.gz
```

or as a batch job from a login node:

```bash
sbatch use-pyotter/carla/carc/job.sbatch use-pyotter/runs/town10-seed1227-naive.json.gz
```

`run.sh` starts the server, waits for it, drives every scenario given, and stops the server. The server's log is written beside the first scenario. On a shared node, set `OTTER_PORT` to a free port.

## macOS with the Wine Wrapper

```bash
use-pyotter/carla/wine/server start
use-pyotter/carla/wine/pyotter drive use-pyotter/runs/town10-seed1227-naive.json.gz
use-pyotter/carla/wine/server stop
```

`server start` returns once the server answers, which takes a few minutes. The server runs without rendering, so the weather has no visible effect, and camera sensors are not available. `server stop` ends every Wine process of the wrapper. Set `CARLA_APP` if the wrapper is not at `~/Applications/Sikarugir/CARLA.app`.

The wrapper's Windows Python runs pyotter from this repo, so it needs PyYAML, which pyotter reads its config with. `pip install` handles that on CARC and in Docker. In the wrapper, install it once with that Python's own pip (`python.exe -m pip install pyyaml`) if `import yaml` fails.

## Docker

On Linux with Docker and the NVIDIA container toolkit:

```bash
use-pyotter/carla/docker/run town10-seed1227-naive.json.gz
```

The scenario files must be in `use-pyotter/runs/`. The script starts the `carlasim/carla:0.9.16` server, builds the client image from this repo, drives, and stops the server.

## Evaluating Telemetry

Evaluation needs no simulator and no extra packages:

```bash
python -m pyotter evaluate use-pyotter/runs/*-telemetry.json.gz
```

It prints each run's verdict per safety requirement, and for several runs the share that kept each requirement. The exit status is 1 if any run breached a requirement. Add `--save` to write each evaluation as JSON.

## What a Rolled Hazard Does in the Simulator

| Hazard | Effect |
|---|---|
| `wet_road` | Lowers the car's tire friction in proportion to its severity |
| `low_visibility` | Shortens how far ahead the driver notices other road users |
| Sun glare | Shortens that distance further while the car heads toward the sun |
| `pedestrian` event | Puts a walker at the roadside at the event's time and place, and walks it across the lane |

The weather is also set to match, but that changes only what a camera would see.
