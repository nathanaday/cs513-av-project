# Headless CARLA on Apple Silicon

This recipe runs the CARLA 0.9.16 server with no window on an Apple Silicon Mac. A Python script then drives a car and prints what happens as text: speed, position, controls, collisions, and lane crossings.

Use it when your Mac cannot run the windowed simulator well. In the default mode the server needs about 6 GB of memory, so a 16 GB Mac should run it. The cost: in that mode, camera sensors do not work.

Both the server and the Python client run inside a Wine wrapper. There is no native macOS build of either.

## What you need

Install the wrapper first. Follow the [CARLA on Apple Silicon guide](https://github.com/nathanaday/carla-mac-os/blob/main/carla-on-apple-silicon.md), Steps 1 to 6 and Step 8 up to the Python install. Use these exact versions:

| Item | Version |
|---|---|
| CARLA | 0.9.16, Windows package (`CARLA_0.9.16.zip`) |
| Wine wrapper | Sikarugir, engine `WS12WineSikarugir10.0_6`, wrapper at `~/Applications/Sikarugir/CARLA.app` |
| Python in the wrapper | Windows Python 3.10.11, 64-bit |
| macOS | 26.6.2 (tested here). The guide also reports successes on 26.2. macOS 15 is not tested. The guide reports one failure on 15.6 with 16 GB (a black window, heavy swap, and Town10 never appears), and its cause is not known. |

You do not need to set launch flags in `Configure.app` (guide, Step 7). The server script in this repository passes its own flags.

If your wrapper is somewhere else, set `CARLA_APP` to its path before you run the scripts.

## Install the client

From the root of this repository:

```bash
scripts/carla-python -m pip install -r requirements-carla.txt
```

This installs `carla==0.9.16`, `numpy==1.26.4`, `networkx==3.4.2`, and `shapely==2.1.2` into the wrapper's Python. Do not change these versions: the team's runs must match across machines.

`scripts/carla-python` runs the wrapper's Windows Python from a macOS terminal. It takes the same arguments as `python`. It also puts CARLA's driving agents (`agents.navigation`) on the path. Each call prints two `msync:` lines to stderr. Ignore them.

Check the install:

```bash
scripts/carla-python -c "import carla, agents.navigation.basic_agent; print('ok')"
```

## Start, check, and stop the server

Start the server with no window:

```bash
scripts/carla-server start
```

```
starting CARLA (nullrhi) on port 2000; log: .../cs513-project/.carla/server.log
up after 6s, server memory 2473 MB
```

The command returns when the server accepts connections on port 2000. If the port is still closed after 30 minutes, it exits with an error and leaves the server running. Set a shorter limit with `--timeout <seconds>`.

The server then loads the map when the first client connects. Its memory grows to about 6 GB at that point.

Check the server:

```bash
scripts/carla-server status
```

```
up: nullrhi, port 2000, server memory 5878 MB
```

Stop the server:

```bash
scripts/carla-server stop
```

`stop` ends every Wine process of the wrapper, including any client script that is still running. It takes about one second. A hung server can take up to 30 seconds.

### Modes

| Mode | Command | Use it for |
|---|---|---|
| No rendering (default) | `scripts/carla-server start` | Telemetry, collisions, lane crossings, routes, agents. Any work that does not need images. |
| Off-screen rendering | `scripts/carla-server start --offscreen` | Camera sensors. Needs about 15 GB for the server, so not on a 16 GB Mac. |

The default mode runs the server with `-nullrhi`. The server draws nothing, so it needs no graphics memory and compiles no shaders. **A client that spawns a camera sensor in this mode crashes the server** (see Troubleshooting).

The off-screen mode runs `-RenderOffScreen -quality-level=Low` through Apple's D3DMetal. Cameras work. On the first launch, D3DMetal compiles shaders; on a Mac with little memory that can take 20 to 30 minutes.

## Drive a car

With the server up:

```bash
scripts/carla-python scripts/headless_drive.py --every 5
```

The script turns on synchronous mode, spawns a Tesla Model 3 at spawn point 0, and drives it with CARLA's `BasicAgent` to a destination. It prints one telemetry line every 5 simulated seconds, each event when it happens, and a summary:

```
INFO:  Found the required file in cache!  Carla/Maps/Nav/Town10HD_Opt.bin
ego vehicle.tesla.model3 id=24  spawn 0  route 402 m
  sim_s   km/h        x        y   thr   brk  steer  to_go_m
   0.05    3.5    -64.6     24.5  0.00  0.00   0.00    401.3
   5.00   30.2    -33.4     24.7  0.03  0.00   0.12    369.8
   6.45 EVENT lane_invasion: Broken
   7.15 EVENT lane_invasion: Broken
  10.00   29.7      7.3     28.2  0.51  0.00  -0.00    328.8
  15.00   29.0     39.7     43.1  0.75  0.00   0.04    286.0
  15.30 EVENT lane_invasion: NONE
  20.00   30.0     61.9     69.6  0.00  0.18  -0.01    243.3
  25.00   30.1     97.6     79.9  0.36  0.00   0.09    200.2
  25.70 EVENT lane_invasion: Solid
  30.00   30.2     88.8    118.7  0.33  0.00   0.04    158.8
  35.00   30.2     51.2    130.6  0.35  0.00  -0.00    117.3
  40.00   30.2     10.2    130.3  0.34  0.00  -0.01     76.2
  45.00   30.2    -30.8    130.0  0.34  0.00  -0.00     35.2
summary  sim 49.3 s  wall 2.5 s  ratio 19.72  distance 395 m  collisions 0  lane_invasions 4  arrived
```

| Column | Meaning |
|---|---|
| `sim_s` | Simulated seconds since the car spawned. One tick is 0.05 s. |
| `km/h` | Speed. |
| `x`, `y` | Position in meters, in map coordinates. |
| `thr`, `brk`, `steer` | The control the agent applied: throttle and brake from 0 to 1, steer from -1 to 1. |
| `to_go_m` | Meters left along the planned route. |

Events:

- `EVENT collision: <actor type>  impulse <N*s>`: the car touched another actor. The script reports a contact once, and again only after one second without contact with that actor.
- `EVENT lane_invasion: <marking types>`: the car crossed a lane marking. `NONE` means a crossing where the road has no painted marking, such as in a junction.

The summary line gives the simulated time, the wall time, their ratio, the distance driven, the event counts, and `arrived` or `stopped`.

Options:

| Option | Default | Effect |
|---|---|---|
| `--ticks N` | 0 | Stop after N ticks. 0 drives until the car arrives. |
| `--every S` | 1.0 | Simulated seconds between telemetry lines. |
| `--speed K` | 30 | Target speed in km/h. |
| `--spawn I` | 0 | Index of the spawn point. |
| `--seed N` | 0 | Seed for the choice of destination. |
| `--host`, `--port` | `localhost`, 2000 | Where the server is. |
| `--timeout S` | 60 | Seconds the client waits for the server. |

Stop a drive with Ctrl+C. On every exit the script destroys its car and sensors and restores the world settings, so you can run it again at once.

Exit status: 0 on arrival or at the tick limit, 1 on an error, 130 after Ctrl+C.

## Measurements

Measured on 2026-10-04 on a MacBook Pro M4 Pro (Mac16,7), 48 GB, macOS 26.6.2, with the drive above: Town10HD_Opt, 402 m at 30 km/h.

| | No rendering (default) | Off-screen rendering |
|---|---|---|
| Start until port 2000 is open | Usually 5 to 7 s; one start took 14 s | 6 to 7 s in three starts, 13 s in a fourth. Shaders were already compiled. |
| Server memory when the port opens | 2.5 GB | about 3 GB |
| Server memory, settled and during the drive | 5.9 GB settled, 6.4 GB peak | 15 GB, of which about 12 GB is graphics memory |
| Simulated time per wall second | 19.9 | 4.0 |
| Camera sensor | Crashes the server | Works |

The cause of the slow starts (14 s and 13 s) is not known.

Server memory is the physical footprint from `footprint -p <pid>`, the number that `carla-server` prints. The number that `start` prints is too early to judge by: the server keeps growing after the port opens. In the default mode it grows when the first client loads the map. In the off-screen mode it grows from about 3 GB to 15 GB within 6 to 10 seconds after the port opens, with no client. Run `scripts/carla-server status` after the first drive to see the settled number. Do not use the RSS from `ps` or Activity Monitor's default column: it leaves out graphics memory and showed 2.9 GB for the off-screen server.

**On a 16 GB Mac:** the default mode leaves about 10 GB for macOS and your other programs, so it should fit. The off-screen mode does not fit. No cohort member has confirmed a 16 GB run yet. If you do, add your numbers here.

## Troubleshooting

Each entry gives the symptom, the cause, and the fix. Check the server log at `.carla/server.log` first.

| Symptom | Cause | Fix |
|---|---|---|
| `carla-server start` prints `port 2000 is already open`. Or every client call times out although port 2000 is open. | An old server still runs. Closing `CARLA.app` can leave `CarlaUE4-Win64-Shipping.exe` and `wineserver` alive. | `scripts/carla-server stop`, then `scripts/carla-server start`. |
| `carla-server status` says `loading` long after start, and the port stays closed. | The server hung. | `scripts/carla-server stop` (up to 30 s for a hung server), then `start`. |
| A Windows dialog "Fatal error!" appears. The client fails with `time-out of ...ms while waiting for the simulator`. | A client spawned a camera sensor (`sensor.camera.*`) while the server ran with no rendering. The server crashes with `EXCEPTION_ACCESS_VIOLATION`. | Click OK. Run `scripts/carla-server stop`. Remove the camera from your script, or start with `--offscreen` on a Mac with enough memory. UE4 writes crash reports to `drive_c/users/Sikarugir/AppData/Local/CarlaUE4/Saved/Crashes/` inside the wrapper. |
| After a client died, other clients hang, and `world.wait_for_tick()` times out. | The client died while synchronous mode was on, for example from `kill -9` or a closed terminal. The server waits for ticks that never come. `headless_drive.py` still runs, because it ticks the world itself. | Restart the server: `scripts/carla-server stop`, then `start`. |
| A client script ends at once and prints nothing. The world does not change. | numpy 2.x crashes on import under this Wine build. | `scripts/carla-python -m pip install -r requirements-carla.txt`. It pins `numpy==1.26.4`. |
| `wine` run from a terminal exits with status 136 and prints nothing. | Its Wine sync settings do not match the running `wineserver`, which uses `WINEMSYNC=1` and `WINEESYNC=1`. | Run Python through `scripts/carla-python`, never through a bare `wine`. |
| `ModuleNotFoundError: No module named 'agents'` | The agents package ships with CARLA in `PythonAPI/carla`, not in the `carla` wheel. Python ran without it on the path. | Run the script through `scripts/carla-python`. |
| `error: time-out of 60000ms while waiting for the simulator` right after start. | The server still loads the map, or compiles shaders on the first off-screen launch. | Wait. Run `scripts/carla-server status` until it says `up`. Raise the client limit with `--timeout`. |
| The Mac slows down, and `sysctl vm.swapusage` shows swap that grows. The server hangs or quits. | Memory pressure. The off-screen server alone needs about 15 GB. | Use the default mode. Quit other programs. Check `scripts/carla-server status` for the server memory. |
| `warning: client 0.9.16 != server <version>` | The `carla` package and the server are different versions. API calls can fail or behave differently. | Install CARLA 0.9.16 in the wrapper and run the pinned install above. |
| `carla-server: no wrapper at ... (set CARLA_APP)` | The wrapper is not at `~/Applications/Sikarugir/CARLA.app`. | `export CARLA_APP=/path/to/CARLA.app`. |
| `wineserver` fails with `Library not loaded: @rpath/libinotify.0.dylib`. | Wine ran through `nohup` or another protected macOS binary, which strips the `DYLD_*` variables. | Start the server with `scripts/carla-server start`, not your own `nohup` command. |

## Files

| File | Purpose |
|---|---|
| `scripts/carla-env.sh` | The Wine environment of the wrapper. The other two scripts source it. |
| `scripts/carla-python` | Runs the wrapper's Python. Copied from [carla-mac-os](https://github.com/nathanaday/carla-mac-os) at `8606c8f`. |
| `scripts/carla-server` | Starts, checks, and stops the headless server. |
| `scripts/headless_drive.py` | Drives one car and prints telemetry and events. |
| `requirements-carla.txt` | The pinned client packages. |
