# CARLA 0.9.16 on USC Discovery

Illy's workflow: edit and test offline on the Mac, allocate a Discovery GPU node,
run the server and Python client there, then download recordings for review.
Tomo can reproduce these steps independently when available.

**Status:** helpers are implemented; a live Discovery allocation and a second-allocation
smoke test are still required. The course's CARLA 0.9.15 image/environment is not changed.
The Mac Wine launchers are separate from these Linux helpers.

## 1. Transfer the code

Connect to USC's network or Research VPN. From the Mac:

```bash
rsync -av --exclude=.git --exclude=.venv --exclude=.carla \
  --exclude=runs --exclude=__pycache__ --exclude=models \
  /Users/illyhoang/Projects/cs513-av-project/ discovery.usc.edu:cs513-av-project/
ssh discovery.usc.edu
```

This copies the working tree, including uncommitted Planner code, without deleting
remote files. Keep the remote checkout personal; do not edit the same copy from two
machines during a run. Each run records a hash of the transferred source snapshot.

## 2. Request an allocation

On the login node, check the account, quota, and GPU type names:

```bash
myaccount
myquota
sinfo -p gpu -o '%N %G'
```

After confirming `jdeshmuk_786` is available to you and the A40 resource name is
`a40`, request:

```bash
salloc --account=jdeshmuk_786 --partition=gpu --nodes=1 --ntasks=1 \
  --cpus-per-task=8 --mem=32G --gpus-per-task=a40:1 --time=02:00:00
```

Wait for the compute-node shell. Confirm it before starting CARLA:

```bash
hostname
echo "$SLURM_JOB_ID"
nvidia-smi
squeue --me
```

The helpers verify that the hostname belongs to the allocation. Pure Planner tests
can run on the Mac while the job is queued. Queue wait is separate from allocation runtime.

## 3. Prepare the separate environment once

On the allocated node:

```bash
module load conda apptainer
export CARLA_HPC_HOME="/project2/jdeshmuk_786/$USER/cs513-av-hpc"
cd "$HOME/cs513-av-project/carla-work"
bash scripts/carla-hpc-setup
```

Use a personal writable persistent directory with sufficient quota. If the default
project location is unavailable, set `CARLA_HPC_HOME` to your own storage location
before setup and use that same value in every subsequent allocation. Container
downloads and conversion need space for both the image and Apptainer cache.

Setup creates only its own paths beneath `CARLA_HPC_HOME`:

- `images/carla-0.9.16.sif`: converted from `docker://carlasim/carla:0.9.16`.
- `env-0.9.16`: Python 3.10 and the repo's pinned client dependencies.
- `pythonapi/agents`: matching navigation-agent sources extracted from the image.
- `environment.json`: image checksum, actual launcher path, Python path, dependency versions.
- `runs/`: persistent output directories.

The helper locates the launcher inside the image rather than assuming the course
image's `/home/carla` layout. Server and client are on the same compute node;
the server uses Apptainer, and the client uses the separate Linux Python environment.

## 4. Run and verify a smoke test

```bash
bash scripts/carla-hpc smoke
```

This starts one off-screen server at low quality, waits for CARLA's API, checks both
versions are 0.9.16, loads Town10HD_Opt if needed, and records a quiet drive.
It stops its own server/client processes afterward; your allocation remains available.

Pass criteria:

1. Client and server both report 0.9.16.
2. The capture ends with `arrived` and has zero collision events.
3. The helper exits successfully and its manifest says `completed`.
4. `nvidia-smi` shows the server using the allocated GPU during the drive.
5. The downloaded capture opens in Rerun.
6. The same command passes in a fresh allocation without running setup again.

Each run prints its persistent directory. It contains `manifest.json`, `server.log`,
`unreal.log`, `client.log`, and `run.jsonl.gz`. Planner drives also save the plan and
catalog. `completed` means the command/run finished; it is not evidence of improved safety.

The manifest starts as incomplete. Interruptions, server failures, missing capture end
records, and drives stopped at the tick limit do not count as a completed simulation.
If the allocation is killed without allowing cleanup, a manifest left at `running`
must also be treated as incomplete. Completed files remain in persistent storage.

## 5. Export the authoritative HPC map

In an allocation, after the smoke test:

```bash
bash scripts/carla-hpc -- -m planner export \
  --output "$CARLA_HPC_HOME/town10-hpc.json.gz"
```

This export includes live-map spawn-point references. The supplied `town10-local`
catalog was generated from the Mac's installed 0.9.16 map and is explicitly labeled
as local. Regenerate the forecast and plan for the HPC catalog; plans check the
entire catalog hash and must not silently reuse a different export.

See [Planner usage](planner.md) for creating a trip, forecast, and plan. `scenario.py`
accepts `--plan`, `--catalog`, and `--allow-unverified-limits`, and inside the helper it
saves the plan, catalog, and recording in the run folder. These options are covered by
offline tests (`planner/tests/test_scenario_wiring.py`) but have not yet been driven
against a live server. After these files have been transferred to the HPC workspace:

```bash
bash scripts/carla-hpc -- -m planner.drive \
  --catalog "$CARLA_HPC_HOME/town10-hpc.json.gz" \
  --plan "$CARLA_HPC_HOME/plan.json" --allow-unverified-limits --no-follow
```

`--allow-unverified-limits` is an explicit prototype flag. Final comparisons require
verified limits and Runner's common driver, visibility filter, and outcome evaluator.
The demo uses BasicAgent and does not establish pedestrian safety.

To select different ports on a shared node, use helper options before `--`:

```bash
bash scripts/carla-hpc --port 2100 --tm-port 8100 smoke
```

The helper passes the RPC port to the client and exposes the Traffic Manager port to
the scenario runner. It checks RPC, streaming, secondary, and Traffic Manager ports.

## 6. Download, review, and release resources

The allocated job's `exit` releases its resources after the helper has stopped.
For a pending or stuck job, `scancel JOB_ID` cancels that specific job.

From the Mac, replace `RUN_DIRECTORY` with the exact directory printed by the helper:

```bash
mkdir -p /Users/illyhoang/Projects/cs513-av-project/carla-work/runs/hpc
rsync -av discovery.usc.edu:/project2/jdeshmuk_786/illyhoan/cs513-av-hpc/runs/RUN_DIRECTORY/ \
  /Users/illyhoang/Projects/cs513-av-project/carla-work/runs/hpc/RUN_DIRECTORY/
cd /Users/illyhoang/Projects/cs513-av-project/carla-work
scripts/carla-replay runs/hpc/RUN_DIRECTORY/run.jsonl.gz
```

The manifest, plan, and logs travel with the recording. Keep a downloaded successful
replay for the presentation so it does not depend on a new allocation.

## Batch runs, after interactive verification

Submit from the remote `carla-work` directory:

```bash
export CARLA_HPC_HOME="/project2/jdeshmuk_786/$USER/cs513-av-hpc"
sbatch scripts/carla-hpc-batch smoke
```

Pass the same `-- -m planner.drive ...` arguments for a planned drive. The batch wrapper
uses the same lifecycle helper and requests a termination signal before its time limit.
Submit one run per job initially. Runner owns the paired experiment matrix and seed list.

## Troubleshooting

| Symptom | Check |
|---|---|
| Host does not resolve | USC network/Research VPN connection. |
| SSH needs password/Duo | Complete login interactively; never put credentials in a script. |
| Account or GPU request rejected | `myaccount` and the current `sinfo` GPU resource names. |
| Container pull or setup fails | Quota, available space, registry access, and the separate environment path. |
| Server exits or times out | `server.log`, `unreal.log`, allocated GPU, and `nvidia-smi`; image/driver compatibility is still a runtime check. |
| Port unavailable | Select a free RPC triplet and Traffic Manager port with the helper options. |
| Version mismatch | Recheck the image and separate client environment; do not use the course 0.9.15 environment. |
| Map/catalog mismatch | Export the active map again, then regenerate its forecast and plan. |
| Tick limit reached | Inspect the recording; this is an incomplete drive, not an arrival. |

Sources: [USC jobs](https://www.carc.usc.edu/user-guides/hpc-systems/using-our-hpc-systems/running-jobs),
[USC Apptainer](https://www.carc.usc.edu/user-guides/hpc-systems/software/apptainer),
[Discovery resources](https://www.carc.usc.edu/user-guides/hpc-systems/discovery/resource-overview-discovery),
[CARLA 0.9.16 containers](https://carla.readthedocs.io/en/0.9.16/build_docker/).
