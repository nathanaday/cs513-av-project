#!/usr/bin/env bash
# Drive scenario files on CARC Discovery: start a CARLA server, drive, write telemetry, stop the server.
#
# Usage, on a GPU compute node, from the repo root:
#   module load apptainer
#   bash use-pyotter/carla/carc/run.sh use-pyotter/runs/SCENARIO.json.gz [more scenarios ...]
#
# Telemetry is written beside each scenario file. Run setup.sh once first.
#
# Environment:
#   OTTER_HOME   where setup.sh put the image and the environment
#   OTTER_PORT   the server's port (default 2000); change it if the node is shared

set -euo pipefail
[[ $# -gt 0 ]] || { sed -n 2,13p "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

OTTER_HOME="${OTTER_HOME:-/project2/jdeshmuk_786/$USER/otter}"
PORT="${OTTER_PORT:-2000}"
IMAGE="$OTTER_HOME/carla-0.9.16.sif"
PYTHON="$OTTER_HOME/env/bin/python"
[[ -f "$IMAGE" && -x "$PYTHON" ]] || { echo "run use-pyotter/carla/carc/setup.sh first (OTTER_HOME=$OTTER_HOME)" >&2; exit 2; }
command -v apptainer >/dev/null || { echo "load the apptainer module first" >&2; exit 2; }

LOG="$(dirname "$1")/carla-server-${SLURM_JOB_ID:-$$}.log"
# The launcher's folder differs between CARLA images, so look for it.
apptainer exec --nv --cleanenv "$IMAGE" bash -c '
  for root in /workspace /home/carla /opt/carla /carla; do
    if [ -f "$root/CarlaUE4.sh" ]; then
      cd "$root" && exec bash ./CarlaUE4.sh -RenderOffScreen -nosound -quality-level=Low -carla-rpc-port='"$PORT"'
    fi
  done
  echo "cannot find CarlaUE4.sh in the image" >&2
  exit 1
' > "$LOG" 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true; pkill -P "$SERVER" 2>/dev/null || true; pkill -u "$USER" -f CarlaUE4 2>/dev/null || true' EXIT
echo "CARLA server starting on port $PORT; log: $LOG"

"$PYTHON" -m pyotter wait --port "$PORT" --timeout 600
"$PYTHON" -m pyotter drive "$@" --port "$PORT"
