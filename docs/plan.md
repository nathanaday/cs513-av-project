# Project Plan

This page states what the project builds and how the team will judge it. [Basic Phases](Basic%20Phases.md) is the plan of record. The [pre-proposal](prepreposal/pre-proposal-draft.md) was an early pitch from before work began. Its task list and schedule do not apply.

## Goal

A self-driving vehicle can get from A to B quickly without breaking hard rules, but it has no sense of risk. A skilled human driver sometimes gives up some travel time for a safer drive when conditions are difficult.

The project builds a risk-aware planner for CARLA that does the same. It drives slower in poor visibility and routes around crowded or hazardous roads. The study measures whether this planner gets close to the safety of a cautious driver at close to the travel time of a fast one.

## The drivers

Every scenario runs with each driver. All drivers use the same low-level driver, and only the plan changes. So a difference in the results comes from risk awareness, not from driving skill.

| Driver | Route | Speed |
| :--- | :--- | :--- |
| Naive | Quickest route | Speed limit |
| Always-cautious | Quickest route | Slow everywhere (a speed cap) |
| Risk-aware | From the planner | A target speed for each segment, from the planner |
| Risk-aware with re-compute (stretch goal) | Re-computed during the drive | Same as risk-aware |

The naive and always-cautious drivers mark the two ends of the result: fast and risky, safe and slow. Without the always-cautious driver, nobody can tell a smart planner from a slow one.

## Method

- The planner minimizes `time + λ × penalty` with a graph search (Dijkstra or A*) over CARLA's road graph. λ is the weight of risk against time.
- The [penalty model](concepts.md#penalty-model) is the planner's cost. It is a standalone function. It is not built into the driver.
- The project uses no reinforcement learning. The road graph, the cost, and the risk probabilities are all known, so a search finds the exact best route. The [RL tutorial](../carla-work/docs/reinforcement-learning.md) in this repository is a separate experiment.

The details are in [concepts.md](concepts.md).

## Results

- The Runner team measures outcomes from CARLA ground truth: collisions, near-misses, hard braking, pedestrian close calls, and travel time. The evaluation never uses the penalty model. See [Predicted risk and measured outcome](concepts.md#predicted-risk-and-measured-outcome).
- Plot each driver as a point of travel time against measured risk. A sweep of λ draws the risk-aware planner as a curve.
- A good result puts the risk-aware curve near the always-cautious driver's risk at near the naive driver's time.
- If the team wants one combined score, fix its formula and weights before any run.

## Stretch goal

Re-compute the route during the drive when hazards differ from the forecast, for example when more pedestrians are present than the planner expected. Re-computing the route is not the hard part. Building scenarios where the hazards differ from the forecast is. The study is complete without this goal. See phase 5 of [Basic Phases](Basic%20Phases.md).

## Teams

Three teams of two people build the project: World, Planner, and Runner. See [teams.md](teams.md).

## Open questions

- How many seeds to run for each scenario. Five is a starting point.
- Whether `BehaviorAgent` brakes for pedestrians in CARLA 0.9.16.
- The values of `P` and `M` and the weights of the penalty modes.
- Whether a collision fails a run or only counts against it.
- The formula of a combined score, if the team wants one.
