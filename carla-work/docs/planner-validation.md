# Planner validation and report notes

## Verified locally on November 4, 2026

- The offline core runs with native Python 3.12 and NetworkX 3.4.2 without importing CARLA.
- Automated tests cover known optimal routes, units, speed selection, cautious-route
  preservation, partial endpoints, upstream loops, direction, missing/invalid inputs,
  deterministic output, real-map geometry, and saved-plan reproduction.
- HPC lifecycle tests use temporary stand-in processes. They verify owned-process cleanup,
  persistent manifests, port conflicts, startup failure, and tick-limit incompleteness.
  They do not test Discovery, Apptainer, Vulkan, or the actual CARLA server.
- The installed CARLA 0.9.16 map was exported offline: 168 physical directed lane spans,
  with legal junction successors and geometry checked for continuity. Provenance is local.
- The sample risk-aware Town10 plan reconstructs into 364 CARLA waypoints over 20 segments
  and approximately 666.47 m. This is a waypoint reconstruction check, not a driven result.
- A CARLA lane-end rounding case was found and fixed by moving an otherwise invalid
  endpoint one millimeter inward on the same road/lane.

## Driven on the Mac, November 14–15, 2026

Headless CARLA 0.9.16 (`-nullrhi`) on an Apple M4 with 16 GB, Town10HD_Opt, empty world,
BasicAgent, seed 0. Each run has its own report in the vault's `Test runs` folder; the
tables come from `scripts/run-report`.

- **Runner connection:** `scenario.py` and `PlanFollower` drove cautious, naive and λ = 2
  plans end to end. All 5 drives arrived with 0 collisions, and every drive followed all
  20 planned segments in order. The naive drive had one lane invasion on unpainted junction road.
- **Speed limits:** the live limit read 30 km/h on every segment, while the catalog declared
  40–80.5 km/h. `planner limits` placed a probe vehicle on all 168 segments: every one
  reads 30 km/h, and the map has no speed-limit signs or OpenDRIVE maximum-speed landmarks.
  CARLA changes a vehicle's limit only at such signs, so 30 km/h is its fixed limit here.
  `planner-data/town10-mac.json.gz` is the live export with all 168 limits verified at 30 km/h.
- **With verified limits** the commanded speed equals the planned speed on every segment.
  Before, the live limit capped one segment from 33 to 30 km/h.
- **Time:** moving time was within +2.3% (20 km/h) to +6.8% (30 km/h) of the plan's
  estimate. Traffic-light stops added 56–86 s per trip, a third to a half of the total, and
  the planner does not model them. Naive was planned 39.4 s faster than cautious, but was only
  6.8 s faster overall, because it reached one more light on red.
- **Speed tracking at cruise:** mean absolute error 0.5–0.7 km/h.
- **Repeatability:** the same plan on two days gave the same simulated drive. Stops agreed
  within 0.1 s and segments within 1 m; the λ = 2 repeat was identical.

## Predicted-only results

Regenerated on November 15 with the exposure term (`a = 0.25`) and the verified catalog
`town10-mac.json.gz`, which has a 30 km/h limit everywhere. The probabilities are invented
(the mock forecast, seed 0). These figures are model outputs; **no actual travel-time or
safety improvement is established**.

| λ | Estimated seconds | Predicted penalty | Speeds, km/h |
|---|---:|---:|---|
| 0 | 78.76 | 188.04 | 30 |
| 0.5 | 79.98 | 184.69 | 30 |
| 1 | 90.13 | 171.31 | 24–30 |
| 2 | 109.38 | 157.63 | 20–30 |
| 5 | 132.12 | 150.20 | 17–24 |
| 10 | 144.41 | 148.45 | 16–20 |

The route changes between λ = 0 and λ = 0.5; higher λ lowers the speeds on hazardous
segments. On the unverified `town10-local` catalog, with limits up to 80.5 km/h, the λ ≤ 2
rows differ: λ = 0 gives 44.41 s and 305.87. The λ ≥ 5 rows are identical on both catalogs,
because those speeds are already below 30 km/h. An earlier table on this page predated the
exposure term and is superseded.

Reproduce with the commands in [Planner usage](planner.md). The CSV and generated plans
go under ignored run outputs, while the input catalogs, forecast, trip, limit evidence,
and sample plan are supplied with the code.

## Still required

- Agree with Runner that the comparison uses CARLA's live limit (30 km/h in Town10), or
  decide how to apply the OpenDRIVE 40/50 mph declarations.
- Authenticate to Discovery, prepare the separate 0.9.16 image/environment, and verify GPU startup.
- Complete an arriving, zero-collision smoke test, inspect the replay, and repeat in a new allocation.
- Export the HPC catalog, run `planner limits` against it, re-export with `--speed-limits`,
  and drive the three plans there.
- Integrate World probabilities and Runner's common driver, visibility filter, and evaluator.
- Run paired seeds and varied departure times or light phases. Single runs are dominated by
  light timing. Report failed/incomplete runs and outcome spread.
- Freeze `a`, `v_ref` and the λ set before the held-out comparison (by November 27).

## Planner report outline

1. **Question:** can route/speed selection approach cautious driving's measured safety
   with less travel time?
2. **Method:** directed graph, fixed forecast, experimental penalty, candidate speeds,
   nonnegative Dijkstra search, partial endpoints, and λ sweep.
3. **Controls:** identical World hazard rolls and Runner engine across the three drivers;
   no realized hazards available to Planner; evaluator independent of the penalty function.
4. **Implementation:** shared catalog/forecast/plan formats and reproducible HPC manifests.
5. **Correctness evidence:** hand-calculated fixtures, graph/endpoint checks, adapter checks,
   the live speed-limit probe, and Mac drives comparing `plan_target` commands with measured speed.
6. **Measured results:** populate only after Runner provides actual outcomes, seed counts,
   failures, and uncertainty. Keep the predicted-only table separate.
7. **Limitations:** experimental weights, static forecasts, no discretionary lane changes,
   unmodeled delays/dynamics, simulator variability, and any unresolved integration limitations.

Keep the presentation's downloaded replay and exact source/input identifiers with the
final report evidence. Freeze parameters before the held-out comparison.
