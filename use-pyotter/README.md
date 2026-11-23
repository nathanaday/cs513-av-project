# use-pyotter

The lab around pyotter: notebooks that build scenarios, a scenario library and a telemetry library on Hugging Face, and commands that drive scenarios on CARLA 0.9.16. The reader is a teammate who wants telemetry for a scenario and has a CARC Discovery account.

## Drive a Scenario on CARC

On a Discovery login node, from this folder:

```bash
uv sync
uv run carla-server                         # queues a GPU job, returns when CARLA answers
uv run otter-drive town10-seed1227-naive    # queues the drive, prints its job id
tail -f logs/JOB.log
```

When the drive ends, its telemetry and evaluation are in `runs/telemetry/` and in the telemetry library. Nothing else needs to be installed, copied, or downloaded by hand.

```
$ uv run otter-drive town10-seed1227-naive runs/town10-seed1227-risk-aware.json.gz
✓ Added town10-seed1227-risk-aware.8be52dc548aa to the scenario library.
✓ Queued 2 on the CARLA server (job 4101). They run one at a time.

job    scenario                     fingerprint
4102   town10-seed1227-naive        f6d948589e74
4103   town10-seed1227-risk-aware   8be52dc548aa

  Watch    tail -f logs/4102.log
  Queue    squeue --me
  Results  runs/telemetry/town10-seed1227-naive.f6d948589e74/
  Library  https://huggingface.co/datasets/nadayusc/otter-telemetry
```

A `SCENARIO` is a name from the library, the first characters of a fingerprint, or a scenario file. A file is added to the library before it is driven.

### First Time on CARC

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # uv, once per account
git clone https://github.com/nathanaday/cs513-av-project.git && cd cs513-av-project/use-pyotter
uv sync
uv run hf auth login                               # a token with write access
uv run otter-check
```

`otter-check` lists what is set up and what is missing, with the command that fixes each item. The first `carla-server` also fetches the toolchain image, so that one start takes longer.

### The Server

| Command | Effect |
|---|---|
| `uv run carla-server` | Queue a server and wait until it answers. With one already queued or running, wait for that one |
| `uv run carla-server --time 4:00:00` | The same, kept for four hours in place of the default two |
| `uv run carla-server status` | Say where the server stands |
| `uv run carla-server stop` | End it and free the GPU |

Ctrl-C during the wait stops the watching and leaves the job in the queue. One server drives one scenario at a time, so drives queued on it run in order. Stop the server when the queue is empty: it holds a GPU until its time runs out.

## The Scenario Library

Every scenario file is kept in the Hugging Face dataset named by `scenarios_repo` in `otter.yaml`. A scenario's fingerprint is the SHA-256 of its `.json.gz` file. pyotter writes the same scenario to the same bytes every time, so the fingerprint identifies the scenario's content, and two files with the same bytes are stored once.

```bash
uv run otter-scenarios                        # list
uv run otter-scenarios push runs/*.json.gz    # add files
uv run otter-scenarios show f6d9              # map, seed, route, conditions, events
uv run otter-scenarios pull f6d9              # download to runs/scenarios/
```

Build scenario files with `drive_scenario.ipynb`. A file is stored as `scenarios/NAME.SHORT.json.gz`, where NAME is the file's name and SHORT is the first 12 characters of its fingerprint. When two scenarios share a name, refer to them by fingerprint.

## The Telemetry Library

Every run is kept in the dataset named by `results_repo`, as `telemetry/NAME.SHORT/RUN-telemetry.json.gz` with `RUN-evaluation.json` beside it. RUN is the UTC time the drive started and the Slurm job that drove it. The telemetry file also records the full fingerprint of its scenario (`scenario_fingerprint`), so any run can be traced to the exact file that produced it and driven again with `otter-drive FINGERPRINT`.

```bash
uv run otter-results                      # list every run
uv run otter-results list f6d9            # the runs of one scenario
uv run otter-results pull                 # download to runs/telemetry/
uv run otter-results sync                 # upload local results the library lacks
uv run otter-results push FILE-telemetry.json.gz    # add a run driven outside the cluster
```

A drive job uploads its own result. If that upload fails, the job ends with status 3, the files stay in `runs/telemetry/`, and `otter-results sync` uploads them later. The library commands need no cluster, so they also work on a laptop.

## How It Works

`carla-server` submits a GPU job that runs CARLA from the toolchain image under Apptainer and writes its node and port to `.otter/`. `otter-drive` submits one small CPU job per scenario. Each waits for the server, runs `python -m pyotter drive` in the same image against the server's node, evaluates the telemetry, and uploads it. The drive jobs of one server share a job name and the `singleton` dependency, which is how Slurm is told to run them one at a time.

The toolchain image (`carla/image/`) holds the CARLA server and a Python 3.10 with the CARLA client. The client runs in the image because its wheel needs glibc 2.31, which Discovery's own system lacks. pyotter is imported from this checkout, so a change to pyotter takes effect on the next drive without a new image.

| Path | Holds |
|---|---|
| `otter.yaml` | Every setting: the two datasets, the image, the Slurm account and resources, CARLA's arguments |
| `otterlab/` | The commands |
| `carla/` | The toolchain image, and the macOS and Docker launchers ([carla/README.md](carla/README.md)) |
| `runs/` | Scenario files and telemetry, not in git |
| `logs/` | One log per job, not in git |

Set `OTTER_HOME` to keep the converted image somewhere other than the `storage` folder in `otter.yaml`. It needs about 15 GB.

## Status

On November 22, 2026 the commands were run from end to end against stand-ins for Slurm, Apptainer, and Hugging Face, and the image's Python layer was built and ran pyotter with the CARLA client. Nothing has run on Discovery yet. These points rest on assumptions and are the first to check there:

- A drive job on the `main` partition can reach CARLA's port on a `gpu` node. If it cannot, add `--nodelist` for the server's node to `slurm.drive.options`.
- Compute nodes can reach `ghcr.io` and `huggingface.co`.
- CARLA 0.9.16 starts under Apptainer with `--nv` and `-RenderOffScreen` on Discovery's GPUs.
- The GitHub Actions runner has room to build the image.

## Maintainer Setup

These steps are done once for the team.

1. Merge `.github/workflows/toolchain-image.yml` to `main`. It builds the image and pushes it under the name in `otter.yaml`. To publish a changed image, raise the tag in `otter.yaml` in the same change.
2. Make the package public in its settings on GitHub, since the repository is private. Otherwise each user exports `APPTAINER_DOCKER_USERNAME` and `APPTAINER_DOCKER_PASSWORD` (a token with `read:packages`) before the first `carla-server`.
3. Create the two datasets:

   ```bash
   uv run hf repos create nadayusc/otter-scenarios --repo-type dataset
   uv run hf repos create nadayusc/otter-telemetry --repo-type dataset
   ```

   Hugging Face grants write access per organization, not per dataset of a user. For teammates to upload, create the datasets under a shared organization and set the two names in `otter.yaml`, or share a write token through `HF_TOKEN`.

## Tests

```bash
uv run python -m unittest discover -s otterlab -t .
```
