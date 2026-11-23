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
| CARC Discovery | Rehearsed against stand-ins for Slurm and Apptainer, not yet run on the cluster |
| Docker on Linux with an NVIDIA GPU | Written, not yet run |

## CARC Discovery

See [the lab's README](../README.md). In short, from `use-pyotter/` on a login node:

```bash
uv sync
uv run carla-server
uv run otter-drive SCENARIO
```

## The Toolchain Image

`image/` builds one image for CARC and Docker: the `carlasim/carla:0.9.16` server, a `carla-server` command that starts it without a window, and a Python 3.10 at `/opt/otter/venv` with the CARLA client and PyYAML. pyotter is not in the image. It is imported from the checkout through `PYTHONPATH`.

`.github/workflows/toolchain-image.yml` builds the image and pushes it to the GitHub container registry under the name in `use-pyotter/otter.yaml`.

## macOS with the Wine Wrapper

```bash
use-pyotter/carla/wine/server start
use-pyotter/carla/wine/pyotter drive use-pyotter/runs/town10-seed1227-naive.json.gz
use-pyotter/carla/wine/server stop
```

`server start` returns once the server answers, which takes a few minutes. The server runs without rendering, so the weather has no visible effect, and camera sensors are not available. `server stop` ends every Wine process of the wrapper. Set `CARLA_APP` if the wrapper is not at `~/Applications/Sikarugir/CARLA.app`.

The wrapper's Windows Python runs pyotter from this repo, so it needs PyYAML, which pyotter reads its config with. The toolchain image has it for CARC and Docker. In the wrapper, install it once with that Python's own pip (`python.exe -m pip install pyyaml`) if `import yaml` fails.

## Docker

On Linux with Docker and the NVIDIA container toolkit:

```bash
use-pyotter/carla/docker/run town10-seed1227-naive.json.gz
```

The scenario files must be in `use-pyotter/runs/`. The script starts the server and the client from the toolchain image, building it first if it is not available, then drives and stops the server.

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
