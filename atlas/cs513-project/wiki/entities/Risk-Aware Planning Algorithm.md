---
type: entity
title: "Risk-Aware Planning Algorithm"
status: seed
created: 2026-09-20
updated: 2026-09-20
aliases:
  - Risk-aware planner
  - Route planner
  - Router
tags:
  - entity
  - project/cs513-project
  - component
---

# Risk-Aware Planning Algorithm

Category: group project. This page belongs to [[cs513-project]], not to the course material.

## Overview

The algorithm that finds the route from A to B with the best trade of ETA against risk exposure. It uses the [[Risk Exposure Model]] to cost a route, and it outputs a set of navigation waypoints. The [[Risk-Aware Planned Driver]] follows them. ([[Basic Phases]], phase 3)

Status on 2026-09-20: not designed. [[Basic Phases]] calls it an optimization problem and names no algorithm.

Names in the sources: risk-aware planner ([[Basic Phases]]), `Router` ([[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]), route planner ([[CS513 Pre-Proposal Draft - Demand Against Capability]]).

## Inputs

From [[Basic Phases]], phase 3. The team may build these in the simulation layer and assume what statistics the planner can access.

| Input | Description |
| :---- | :---- |
| Pedestrian probability | Likelihood that a pedestrian is present in an `M × M` grid cell of the sim world |
| Weather forecast | Likelihood that a road surface is wet and visibility is impaired |
| Sun angle | Deterministic from the building geometry and the time of day |

The algorithm can be simpler if it knows the real state of the world map, instead of only probabilities. The pre-proposal draft, task 4, lists sun angle, forecast weather, and known construction zones as inputs.

## Objective

The sources state the objective in four ways. The group has not chosen one.

| Source | Statement |
| :---- | :---- |
| [[Basic Phases]] | The quickest route from A to B with minimal risk exposure. The base concept says the planner trades from an ETA budget for added safety. |
| [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]] | Minimize `time + λ × penalty`. Each λ is one risk budget. A sweep of λ gives a curve of time against risk. Proposed as a replacement of the edge weight in the CARLA `GlobalRoutePlanner`, an A* search on a `networkx` graph. This statement is unchecked against CARLA 0.9.16. |
| [[CS513 Pre-Proposal Draft - Demand Against Capability]] | The quickest route within the risk budget. |

## Output

A set of navigation waypoints. The vehicle drives them. ([[Basic Phases]], phase 3)

## Variant: real-time recompute

- [[Basic Phases]], phase 5, a stretch goal: run the same algorithm again while the drive runs. The recompute is not the hard part. The hard part is to simulate unexpected scenarios that need it. The algorithm must then plan from probabilities, and the recompute takes effect when the prediction is at an extreme, for example more pedestrians than expected.
- Working design, Stack C: the `Router` runs again when conditions change, and the driver profile updates at about 1 Hz. The profile switch needs hysteresis.
- The pre-proposal draft, task 5, makes it a core task.

## Open questions

- Which algorithm? No source picks one.
- Constraint, weighted sum, or ETA budget? See the table above.
- Does the planner know the true world state, or only probabilities? [[Basic Phases]] allows the simpler case for phase 3.
- Does it also set the driving profile for each segment, as in the working design?
- Is the recompute core or stretch?

## Relationships

- Costs routes with the [[Risk Exposure Model]].
- Produces the route of the [[Risk-Aware Planned Driver]]. The [[Naive Driver]] does not use it.
- Part of [[Project Idea v2 - Demand Against Capability]].

## Sources

- [[Basic Phases]]
- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]
