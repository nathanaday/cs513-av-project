#!/usr/bin/env bash
# Drive scenario files as a CARC Discovery batch job.
#
# Usage, from the repo root on a login node:
#   sbatch use-pyotter/carla/carc/job.sbatch use-pyotter/runs/SCENARIO.json.gz [more scenarios ...]
#
#SBATCH --account=jdeshmuk_786
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --gpus-per-task=a40:1
#SBATCH --time=01:00:00
#SBATCH --job-name=otter
#SBATCH --output=otter-%j.out

set -euo pipefail
module purge
module load apptainer
cd "$SLURM_SUBMIT_DIR"
bash use-pyotter/carla/carc/run.sh "$@"
