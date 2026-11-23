#!/usr/bin/env bash
# The body of every lab job. `carla-server` and `otter-drive` submit it with the
# resources from otter.yaml; it is not meant to be submitted by hand.
#
# Environment, set by the submitting command:
#   OTTER_PYTHON    the lab's Python
#   OTTER_MODULES   the modules to load, separated by spaces

set -euo pipefail
module purge > /dev/null 2>&1 || true
for name in $OTTER_MODULES; do
  module load "$name"
done
exec "$OTTER_PYTHON" -u -m otterlab.jobs "$@"
