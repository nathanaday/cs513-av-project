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

## Predicted-only results

The supplied Town10 example uses invented probabilities (seed 0). These figures are
model outputs; **no actual travel-time or safety improvement is established**.

| λ | Estimated seconds | Predicted penalty |
|---|---:|---:|
| 0 | 44.41 | 284.69 |
| 0.5 | 73.62 | 157.28 |
| 1 | 108.81 | 106.38 |
| 2 | 118.43 | 99.04 |
| 5 | 119.96 | 98.50 |
| 10 | 119.96 | 98.50 |

The route changes between λ=0 and λ=0.5; further changes mostly reduce speeds.
Some speed limits come from unchecked OpenDRIVE declarations and some are explicit mock
40 km/h limits. Runner must verify limits before the final comparison.

Reproduce with the commands in [Planner usage](planner.md). The CSV and generated plans
go under ignored run outputs, while the input catalog, forecast, trip, and sample plan
are supplied with the code.

## Still required

- Authenticate to Discovery, prepare the separate 0.9.16 image/environment, and verify GPU startup.
- Complete an arriving, zero-collision smoke test, inspect the replay, and repeat in a new allocation.
- Export the authoritative HPC catalog and reproduce planning from it on the Mac.
- Drive constant-speed and speed-change plans; compare the recorded `plan_target` events
  with physical progress and actual speed, allowing acceleration/braking delay.
- Integrate World probabilities and Runner's common driver, visibility filter, and evaluator.
- Run paired seeds and held-out scenarios. Report failed/incomplete runs and outcome spread.

## Planner report outline

1. **Question:** can route/speed selection approach cautious driving's measured safety
   with less travel time?
2. **Method:** directed graph, fixed forecast, experimental penalty, candidate speeds,
   nonnegative Dijkstra search, partial endpoints, and λ sweep.
3. **Controls:** identical World hazard rolls and Runner engine across the three drivers;
   no realized hazards available to Planner; evaluator independent of the penalty function.
4. **Implementation:** shared catalog/forecast/plan formats and reproducible HPC manifests.
5. **Correctness evidence:** hand-calculated fixtures, graph/endpoint checks, and adapter checks.
6. **Measured results:** populate only after Runner provides actual outcomes, seed counts,
   failures, and uncertainty. Keep the predicted-only table separate.
7. **Limitations:** experimental weights, static forecasts, no discretionary lane changes,
   unmodeled delays/dynamics, simulator variability, and any unresolved integration limitations.

Keep the presentation's downloaded replay and exact source/input identifiers with the
final report evidence. Freeze parameters before the held-out comparison.
