# Teams

The project has three teams of two people: World, Planner, and Runner. [Fair matching](fair-matching/README.md) assigns the members to the teams.

```
World ──Risk API──────────► Planner ──Plan API──► Runner
  └────Scenario API (rolled hazards)───────────────► Runner
```

The planner reads only the Risk API. The Scenario API holds the hazards that actually happen in the drive, and only the Runner team uses it.

## World

Builds:

- Scenarios where the risky situations (weather, pedestrians, visibility, wet roads) are rolled for each road segment from a seed when the scenario starts. Every driver then meets the same hazards.
- A real effect in CARLA for each hazard: scripted pedestrian crossings, low tire friction on wet segments, and a visibility level for each segment. See [Hazards in CARLA](concepts.md#hazards-in-carla).

Delivers:

- **Risk API**: the probability of each hazard class on each directed road segment, and at each time if the forecast changes during a drive.
- **Scenario API**: loads a scenario in CARLA and builds the world with the hazards rolled from its seed.

The scenarios use the same world geometry and vary the conditions: weather, traffic, and time of day. They cover every level of risk, from almost no risk to very dangerous. The [demo scenarios](../carla-work/docs/scenarios.md) show what CARLA can do.

## Planner

Builds:

- The [penalty model](concepts.md#penalty-model), which is the planner's predicted cost.
- The [route-and-speed search](concepts.md#route-and-speed-search).

Delivers:

- **Plan API**: takes the origin, the destination, the departure time, and λ. Returns the road segments to drive, with a target speed for each segment. It reads only the Risk API.

Until the real Risk API is ready, the Planner team works against a mock Risk API with made-up risk on the real Town10 road graph.

## Runner

Builds:

- The driver engine. It follows a plan at the target speeds, brakes for pedestrians, and sees only what the [visibility filter](concepts.md#visibility-filter) allows.
- The runs: the naive, always-cautious, and risk-aware drivers on the same scenarios and seeds.
- The evaluation metrics, from CARLA ground truth: collisions, near-misses (time-to-collision), hard braking, pedestrian close calls, and travel time. The evaluation code never imports the penalty model.

Delivers:

- **Eval engine**: travel time and the measured outcome counts for each drive.
- **Results and plots**: travel time against measured risk for each driver, and the λ sweep.

The Runner team starts from the existing scenario runner (`carla-work/client-runners/scenario.py`) on a fixed route. Its first check: the scenario runner drives with `BasicAgent`, which does not brake for pedestrians. Confirm that `BehaviorAgent` does in CARLA 0.9.16, or add pedestrian braking.

---

## Comments

The World team has the most unknowns early, and the Runner team has the most work late. The Runner team can build the visibility filter early to balance the load.

---

## Exchange Formats

All three teams agree on these before they build much:

- **Segment IDs.** The unit of the project is the directed road segment from CARLA's road graph (`map.get_topology()`).
- **Run record.** The existing run file format ([run-format.md](../carla-work/docs/run-format.md)), extended with the hazards that triggered and the outcome events.
- **Risk API and plan format.** When these two are written down, all three teams can start at the same time.
