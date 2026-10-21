# Concepts

The ideas that the three [teams](teams.md) build on. The goal and the drivers are in [plan.md](plan.md).

## Demand against capability

The vehicle compares the **demand** of the driving situation with its own **capability**:

- Demand is the predicted difficulty of a road segment or of the current scene.
- Capability is what the vehicle can do now. It drops when conditions degrade, for example in rain or in sun glare.

When demand is high or capability is low, the vehicle accepts less risk: it changes its route and its speed. It does not change its models or its compute.

## Penalty model

The penalty model turns speed and exposure to hazards into penalty points. It is a standalone function: it produces penalty points and does not decide where to go. The Planner team owns it.

Each penalty mode weighs the exposure to one hazard as a function of speed:

| Mode | What it weighs |
| :--- | :--- |
| Pedestrian proximity | Exposure to pedestrians within `P` meters of the vehicle. Higher speed near pedestrians gives a higher penalty. |
| Visibility | Exposure to poor visibility from rain, fog, direct sun within `M` degrees of the horizon, or night. |
| Wet surface | Time on wet roads. Higher speed on a wet road gives a higher penalty per second. |

The total is a weighted sum of the modes:

```
total_penalty(t) = w1 * visibility_penalty(t) + w2 * wet_road_penalty(t) + ...
```

The first pass holds off on left turns, obstruction sneaking, and other single risky events. They are harder to model in the simulator and harder to justify as part of the risk assessment.

## Route-and-speed search

The planner finds the route and the speeds that minimize `time + λ × penalty`. It does a graph search (Dijkstra or A*) over CARLA's directed road segments.

The penalty modes depend on speed, so the planner also chooses a speed for each segment. For a segment of length `L`, it tries a few speeds `v` (for example 20, 30, and 40 km/h) and keeps the cheapest:

```
segment cost(v) = L/v + λ × rate(v, conditions) × L/v
```

`rate` is the penalty per second at speed `v`, from the penalty model and the Risk API probabilities for that segment. The cheapest cost is the edge weight for the search. The output is a route with a target speed for each segment.

- λ is the weight of risk against time. Each value of λ gives one plan. A sweep of λ gives a curve of travel time against risk.
- The naive driver gets the quickest route at the speed limit.
- The planner needs no training. The road graph comes from CARLA, the team writes the penalty model, and the Risk API gives the probabilities, so the search finds the exact best route in milliseconds.

## What the planner may know

The planner reads only the Risk API. It knows the true probabilities that the World team samples hazards from. It does not know the outcome of each roll. A planner that reads the Scenario API knows where each pedestrian will cross and beats the naive driver for a reason that has nothing to do with planning.

The Risk API answers for each directed road segment, because the planner searches over segments. "Directed" matters because sun glare depends on the direction of travel. The World team can model pedestrian density on a grid and add it up for each segment.

## Hazards in CARLA

A hazard in the risk model must have a real effect in CARLA. If it has none, the measured risk is always zero. Measured in CARLA 0.9.16 on Town10:

| Hazard | Effect in CARLA now | What the scenario needs |
| :--- | :--- | :--- |
| Pedestrians | Almost none. CARLA's AI walkers stand on driving lanes only inside junctions, in 0.4% of samples. | Scripted crossings with `carla.WalkerControl`, as `jaywalker_swarm.py` does. In the risk model, pedestrian density means the chance of a crossing. |
| Wet road | Yes. At tire friction 0.5, a stop from 30 km/h took 10.2 m, against 4.7 m and 6.3 m on a dry road. | Low tire friction on wet segments, and something that makes the car brake there. |
| Rain, fog, low sun | None. The driver reads true actor positions. A heavy-rain run and a clear run with the same seed hit the same bus at 26.5 s. | A visibility level for each segment, applied by the [visibility filter](#visibility-filter). |

- CARLA weather applies to the whole map. Fog on one segment can exist only in the visibility filter.
- A low sun needs an open view. Buildings hide a sun 5° above the horizon on most Town10 streets. `sun_azimuth_angle` set to the ego's heading yaw + 180 puts the sun ahead of the ego.
- `BasicAgent` brakes for vehicles and red lights, not for pedestrians. With a driver that does not brake for pedestrians, every crossing on the route is a collision for every driver.

### Seeded hazards

The World team rolls the hazards of every segment from the seed when the scenario starts. For example: "segment 42: a pedestrian crosses when the ego is within 30 m." Each driver meets what was rolled on the segments it drives. A different route does not change the rolls, so the runs of different drivers stay paired.

CARLA is not deterministic. One scenario with one seed arrived in 56.0 s, stopped in a gridlock, and arrived in 54.1 s in three runs. Run several seeds for each scenario and report the spread, not one run.

## Visibility filter

The visibility filter hides the actors that the driver cannot see. It starts from CARLA's true actor list and removes the actors beyond a detection range. The visibility level of the segment sets the range: the range drops as rain or fog thickens, or as the sun comes into view ahead. The filter can also add missed detections. It applies to every driver in the same way. The Runner team builds it into the driver engine.

## Predicted risk and measured outcome

- **Predicted risk** is the penalty model. The planner minimizes it. The results report it only as a diagnostic.
- **Measured outcome** is what the Runner team counts from CARLA ground truth: collisions, near-misses (time-to-collision below a threshold), hard braking, pedestrian close calls, and travel time.

The evaluation must not use the penalty model. If it did, the risk-aware driver would win by definition, because it minimizes that same score, and the study would show only that the search works.

Pedestrian proximity in the evaluation means close calls: a pedestrian in the ego's path within some distance. Time spent near pedestrians is exposure, which belongs to the penalty model.

A comparison of predicted risk with measured outcome shows how good the penalty model is.

Starting thresholds, not yet measured: time-to-collision below 1.5 s, deceleration above 4 m/s², a gap to another actor below 1 m.
