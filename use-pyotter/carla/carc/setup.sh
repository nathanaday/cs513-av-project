#!/usr/bin/env bash
# Prepare CARC Discovery once: the CARLA server image and a Python environment with the client and pyotter.
#
# Usage, on a compute node (after salloc), from the repo root:
#   module load conda apptainer
#   bash use-pyotter/carla/carc/setup.sh
#
# Environment:
#   OTTER_HOME   where the image and the environment go
#                (default: /project2/jdeshmuk_786/$USER/otter)

set -euo pipefail
command -v conda >/dev/null || { echo "load the conda module first" >&2; exit 2; }
command -v apptainer >/dev/null || { echo "load the apptainer module first" >&2; exit 2; }

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
OTTER_HOME="${OTTER_HOME:-/project2/jdeshmuk_786/$USER/otter}"
mkdir -p "$OTTER_HOME"
export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$OTTER_HOME/apptainer-cache}"
IMAGE="$OTTER_HOME/carla-0.9.16.sif"
ENV="$OTTER_HOME/env"

[[ -f "$IMAGE" ]] || apptainer pull "$IMAGE" docker://carlasim/carla:0.9.16
[[ -x "$ENV/bin/python" ]] || conda create --yes --prefix "$ENV" python=3.10 pip
"$ENV/bin/python" -m pip install carla==0.9.16
"$ENV/bin/python" -m pip install -e "$REPO"
"$ENV/bin/python" -c 'import carla, pyotter; print("client ready")'
echo "setup complete in $OTTER_HOME"
