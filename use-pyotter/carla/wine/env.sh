# Wine environment for the CARLA wrapper on macOS. Sourced by the scripts beside it.
#
# Adapted from github.com/nathanaday/carla-mac-os (scripts/carla-python).
#
# Environment:
#   CARLA_APP   wrapper bundle (default: ~/Applications/Sikarugir/CARLA.app)
#
# The settings mirror what Sikarugir sets when it launches CARLA. WINEMSYNC and
# WINEESYNC must match the running wineserver, or every Wine process exits at
# once with status 136 and no message.

APP="${CARLA_APP:-$HOME/Applications/Sikarugir/CARLA.app}"
SS="$APP/Contents/SharedSupport"
FW="$APP/Contents/Frameworks"

if [[ ! -x "$SS/wine/bin/wine" ]]; then
  echo "${0##*/}: no wrapper at $APP (set CARLA_APP)" >&2
  exit 2
fi

export WINEPREFIX="$SS/prefix"
export WINELOADER="$SS/wine/bin/wine"
export WINEDLLPATH="$SS/wine/lib/x86_64-windows:$SS/wine/lib/i386-windows:$SS/wine/lib/x86_64-unix"
export DYLD_FALLBACK_LIBRARY_PATH="$SS/wine/lib:$SS/wine/lib64:$FW:$FW/GStreamer.framework/Libraries:/usr/lib:/usr/libexec:/usr/lib/system"
export PATH="$SS/wine/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export WINEMSYNC=1 WINEESYNC=1 ROSETTA_ADVERTISE_AVX=1
export WINEDEBUG="${WINEDEBUG:--all}"

DRIVE_C="$WINEPREFIX/drive_c"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

# The CARLA folder name depends on how it was moved in: CARLA_0.9.16 or CARLA_0.
CARLA_DIR="$(find "$DRIVE_C/Program Files" -maxdepth 2 -name CarlaUE4.exe -exec dirname {} \; | head -1)"
WINDOWS_PYTHON="$(find "$DRIVE_C/Program Files" -maxdepth 2 -name python.exe -path '*Python3*' | sort | tail -1)"

to_windows() {
  local abs
  abs="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
  if [[ "$abs" == "$DRIVE_C"/* ]]; then
    abs="C:${abs#"$DRIVE_C"}"
  else
    abs="Z:$abs"
  fi
  printf '%s' "${abs//\//\\}"
}
