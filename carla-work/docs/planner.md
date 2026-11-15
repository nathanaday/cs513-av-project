# Planner: offline search and Runner handoff

Illy leads implementation; Tomo provides optional reviews and test cases. Start with
the offline examples, then use [the Discovery runbook](hpc.md) for a driven plan.

**Implemented:** graph export, mock forecasts, route/speed search, three baseline modes,
JSON interchange, predicted-only sweeps, waypoint conversion, and a quiet-world runner hook.
**Pending:** live HPC verification, World API agreement, verified speed limits, common
Runner integration, measured comparisons, and independent reproduction.

## Offline quick start on the Mac

Use a native Python 3.10 or newer. CARLA is not required for planning from a saved
catalog; the only dependency is NetworkX 3.4.2 (`requirements-planner.txt`). Create the
ignored `carla-work/.venv` once:

```bash
cd /Users/illyhoang/Projects/cs513-av-project/carla-work
python3 -m venv .venv
.venv/bin/pip install -r requirements-planner.txt
```

Then activate it in each new shell, so `python3` below is the venv's:

```bash
cd /Users/illyhoang/Projects/cs513-av-project/carla-work/client-runners
source ../.venv/bin/activate
python3 -m unittest discover -s planner/tests -v
python3 -m planner examples --output ../runs/planner-examples
```

All tests run offline; CARLA is stubbed where `scenario.py` is checked. Do not install
the CARLA requirements into this venv or the mini-project environment.

Hand-checkable example: the common start and finish are 10 m each. The shortcut is
100 m, while the detour is 160 m. All limits are mocked as 40 km/h. The shortcut has
pedestrian probability 1; other probabilities are zero.

| Case | Expected plan | Estimated time | Predicted penalty |
|---|---|---|---|
| All clear | Shortcut at 40 km/h | 10.8 s | 0 |
| Hazard, λ = 0 | Shortcut at 40 km/h | 10.8 s | 18.25 |
| Hazard, λ = 2 | Detour at 40 km/h | 16.2 s | 0 |
| No detour, λ = 2 | Shortcut at 26 km/h; endpoints at 40 | 15.65 s | 13.86 |

These are arithmetic demonstrations, not measured safety results.

## Real Town10 example

The included compressed catalog contains 168 directed physical lane spans and their
legal junction connections. It was exported from the installed CARLA 0.9.16 OpenDRIVE
file without running the server. It has no live spawn-point list and does not claim HPC validation.

```bash
cd /Users/illyhoang/Projects/cs513-av-project/carla-work/client-runners
python3 -m planner plan --catalog ../planner-data/town10-local.json.gz \
  --forecast ../planner-data/town10-mock.json --trip ../planner-data/town10-trip.json \
  --output ../runs/town10-plan.json
python3 -m planner sweep --catalog ../planner-data/town10-local.json.gz \
  --forecast ../planner-data/town10-mock.json --trip ../planner-data/town10-trip.json \
  --output ../runs/town10-sweep
```

The sweep writes one plan per λ and `predicted-only.csv`. Runtime and predicted penalty
exclude traffic signals, congestion, acceleration, and interactions with other actors.

## Public interfaces, version 1

Use `make_plan(catalog, forecast, trip, config=None, mode="risk-aware")`. It returns a
JSON-compatible dictionary and raises `PlanningError` for invalid inputs or no route.
The core imports no CARLA module and has no access to realized scenario hazards.

### Road catalog

The root has `schema_version`, `catalog_id`, map identity/hash, provenance, `segments`,
and optional `spawn_points`. The segment dictionary maps IDs to:

- `length_m`, `successors`, `speed_limit_kmh`, `speed_limit_verified`.
- CARLA road/section/lane identifiers and `junction`.
- Sampled `geometry`: `x`, `y`, `z`, OpenDRIVE `s`, and cumulative `distance_m`.

Topology can repeat an incoming lane for several junction exits. The exporter groups
the same physical span and retains every successor, so the hazard on an approach does
not change with the chosen turn. Distinct entry positions sharing an ID cause an error.
Consumers use the exported catalog, not actor IDs or independently numbered graphs.
Lengths are measured from geometry, not CARLA GlobalRoutePlanner's sample-count weights.

OpenDRIVE speed declarations are converted to km/h. Undeclared limits use an explicit
mock 40 km/h value. All are initially unverified. Runner can supply an override JSON:

```json
{"catalog_id": "the-exported-id", "limits": {"r296.s0.l-1": 30.0}}
```

Pass this to `planner export --speed-limits FILE`. Mark limits verified only after a
real check. `planner plan --require-verified-limits` rejects catalogs with unverified limits.

### Risk API / forecast

```json
{
  "schema_version": 1,
  "catalog_id": "the-exported-id",
  "forecast_id": "world-forecast-001",
  "source": "World probability model",
  "segments": {
    "r296.s0.l-1": {"pedestrian": 0.2, "visibility": 0.1, "wet_road": 0.3}
  }
}
```

The example is abbreviated: a real forecast must cover exactly every catalog segment.
Probabilities must be finite and between 0 and 1. A missing value is an error, not zero.
World must define the three hazard events and supply the probabilities behind its
scenario sampling. Actor locations, crossing times, and sampled outcomes do not belong here.

Create an explicitly labeled mock with `planner mock --catalog FILE --seed 0 --output FILE`.
Use `--clear` for all-zero risks or repeat `--hazard-segment ID` to mark chosen segments.

### Trip request

```json
{
  "origin": {"segment_id": "r296.s0.l-1", "offset_m": 2.0},
  "destination": {"segment_id": "r476.s0.l-1", "offset_m": 19.0},
  "departure_time_s": 0.0,
  "risk_weight": 2.0
}
```

Offsets run in the driving direction, from zero to the segment's measured length.
Use the live catalog's `spawn_points` references or the map adapter to resolve endpoints.
Departure time is retained, but version 1 uses a fixed forecast throughout the trip.
An upstream destination on the same segment requires a legal loop; an identical origin
and destination returns an empty plan. Partial first/last segments are charged by actual distance.

### Configuration and plan

The default configuration has candidate speeds of every integer from 1 to 100 km/h,
reference speed 30 km/h, cautious cap 20 km/h, weight 1 for each hazard, and exposure
baseline `a = 0.25`. The penalty rate is the weighted probability sum `H` multiplied by
`a + (speed / reference_speed)^2`.

The exposure baseline is hazard accrued per second regardless of speed, so a longer stay
costs more. Without it, the penalty `H × d × v / v_ref²` falls without limit as speed
falls, and a fine speed grid drives hazardous segments toward a standstill (about 6 km/h
on the Town10 mock at λ = 10). With it, the penalty is U-shaped and lowest at
`v_ref × √a` (15 km/h for the default). The chosen speed is about
`v_ref × √(1/(λH) + a)`, clamped to the limit. Omitting `exposure_baseline` from a
configuration means 0, the version 1 behavior.

For each traversed segment, the planner evaluates candidates at or below its limit,
plus the limit itself. Cost is `distance / speed + λ × penalty_rate × distance / speed`,
with speed converted to m/s for duration. Dijkstra chooses the route using these costs.
Equal speed costs prefer shorter travel time; sorted graph construction makes route ties repeatable.

Plan output includes ordered traversals with start/end offsets, target speeds, estimated
time, predicted penalty, and total objective. It also records the trip, mode, configuration,
and catalog/forecast/configuration hashes. The modes are:

- `risk-aware`: minimizes time plus weighted penalty.
- `naive`: sets λ to zero and uses the quickest route at segment limits.
- `cautious`: preserves the naive route and applies the cautious speed cap.

### Runner integration

The existing scenario runner accepts `--plan FILE --catalog FILE`. The adapter verifies
map and catalog identity, reconstructs CARLA waypoints and junction directions, and
calls the agent's existing route/speed hooks. It tracks nearby physical route progress,
not elapsed time, to select the target speed. Live lower speed limits clamp the target.

For quiet integration tests use `python -m planner.drive ...` through the HPC helper.
`--allow-unverified-limits` is required for prototype catalogs. Final runs omit it.
The run header includes Planner provenance; `plan_target` events record planned speed,
commanded speed, live limit, segment, and route progress. Existing replay readers can
ignore this additional event kind. The scenario runner's behavior without `--plan` is unchanged.

BasicAgent still lacks pedestrian braking. World hazard effects, Runner's visibility
filter, and measured evaluation are external integration requirements. This demo cannot
establish safety merely because a plan has a lower predicted penalty.

## Handoff checklist

- World: agree on catalog IDs and hazard meanings; supply a complete probability file.
- Runner: consume the route/speed output, verify speed limits, and apply one common
  driver and visibility filter to every baseline.
- Evaluation: calculate collisions, near-misses, braking, close calls, and actual time
  from ground truth, without importing this penalty function.
- Illy: retain source/input hashes, configuration, seed, and Slurm job ID with each run.
- Tomo: check a small fixture manually, reproduce instructions, or inspect a discrepancy.

Real-time replanning and discretionary lane changes are outside this release. A successful
search test demonstrates the optimization; measured outcome comparisons test the hypothesis.
