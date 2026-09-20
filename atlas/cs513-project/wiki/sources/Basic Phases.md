---
type: source
title: "Basic Phases"
status: developing
created: 2026-09-20
updated: 2026-09-20
tags:
  - source
  - project/cs513-project
  - plan
source_type: document
author: Nathan Aday
date_published: 2026-09-20
url: 
source_id: src-26c9a50defb89b0215ac
---

# Basic Phases

Category: group project. This page belongs to [[cs513-project]], not to the course material.

## Summary

Nathan Aday's plan for version two of the project idea, [[Project Idea v2 - Demand Against Capability]]. It gives a base concept and five phases. Phases 1 to 4 are the immediate goals. Phase 5, real-time risk recompute, is a stretch goal.

Project components in this document: the [[Naive Driver]], the [[Risk-Aware Planned Driver]], the [[Risk Exposure Model]], and the [[Risk-Aware Planning Algorithm]].

The document says it has no AI-generated content and is fully human written, with AI agents used for collaboration and proofreading. (Callout at the top)

The original stays in the project at `ideas/Basic Phases.md`, where the group reads it. `ideas/Basic Phases.pdf` has the same text. This knowledge base holds a captured copy of the Markdown file.

Authority: primary. The document has open `#TODO` items, so it is a working draft.

## Key claims

### Base concept

- A self-driving vehicle can get from A to B quickly and without breaking hard rules, but it has no sense of risk aversion. (The [[Naive Driver]])
- Skilled human drivers sometimes give up ETA for a safer drive when conditions are difficult.
- Proposal: a risk-aware planner that trades from an ETA budget for added safety. It drives slower in degraded visibility, and it re-routes to avoid crowded areas. (The [[Risk-Aware Planning Algorithm]] and the [[Risk-Aware Planned Driver]])
- The study compares a risk-aware drive with a naive driver. The scores are risk exposure, ETA, and the number of collision incidents.

### The five phases

| Phase | Goal | Kind |
| :---- | :---- | :---- |
| 1. CARLA with base driver and Scenario Runner | Get a basic driver working as the baseline ([[Naive Driver]]). Run a scenario drive. Measure data and report a drive summary. | Immediate |
| 2. Design the penalty model | Build all the eval modules that produce a penalty score versus time graph for a scenario drive ([[Risk Exposure Model]]). | Immediate |
| 3. Build the risk-aware planner | A planner that finds the optimal route from risk exposure and ETA. It outputs navigation waypoints ([[Risk-Aware Planning Algorithm]]). | Immediate |
| 4. Build the sim scenarios | The test set. Run each scenario with the naive driver and the risk-aware planner ([[Risk-Aware Planned Driver]]). | Immediate |
| 5. Real-time risk recompute | Recompute the route with the algorithm from phase 3 while the drive runs. | Stretch |

### Phase 1

- The baseline driving case. A `#TODO` asks for a link to a public CARLA document or tutorial on a basic driver.
- Run a scenario drive and get comfortable with measuring data and reporting the summary.

### Phase 2: penalty model

See [[Risk Exposure Model]] for the modules as a page of their own.

- Program the scenario runner so the basic drive routes from A to B in a test world. The drive includes a bit of each penalty situation: weather, low sun, pedestrians, wet roads.
- The penalty model scores and penalizes the drive on events. It measures speed, pedestrian proximity, turns, weather exposure, and more.
- Three modules for the first pass:

| Module | What it weighs | Variables |
| :---- | :---- | :---- |
| Pedestrian proximity | Aggregated exposure to pedestrian traffic within `P` meters of the ego vehicle, as a function of speed. Higher speed near pedestrians gives a higher penalty. | Speed; `IsSurfaceWet` (bool, simpler); `SurfaceWetSeverity` only if CARLA gives it easily |
| Visibility | Aggregated exposure to poor visibility from rain, fog, and direct sun within `M` degrees of the horizon, or at night. | Speed; `VisibilitySeverity` |
| Wet surface | Aggregated time on wet surfaces as a function of speed. A faster speed on a wet surface gives a higher penalty per second. | None listed |

- Hold off on these for the first pass: left turns, obstruction sneaking, and other single-event risky events. The document says they may be harder to prove as part of the risk assessment and to model in the sim, unless a third-party module already gives them.
- Then run the test drive with the penalty model, tune it, and debug it.
- Two `#TODO` items: split the penalty model into specific modules with definitions, as in the table; and find out whether a well-known module, library, or theory already scores the safety of a drive.

### Phase 3: planner

See [[Risk-Aware Planning Algorithm]].

- The planner needs these world variables. The team may build them in the simulation layer and assume what statistics the planner can access.

| Model item | Description |
| :---- | :---- |
| Pedestrian probability | Likelihood that a pedestrian is present in an `M × M` grid cell of the sim world |
| Weather forecast | Likelihood that a road surface is wet and visibility is impaired |
| Sun angle | Deterministic from the building geometry and the time of day |

- The algorithm can be simpler if the model knows the real state of the world map, instead of only probabilities.
- The algorithm is an optimization problem. It uses the penalty model from phase 2 to find the quickest route from A to B with minimal risk exposure. It outputs navigation waypoints.
- Then run the vehicle on the planned route.

### Phase 4: scenarios

- Use the same world geometry (buildings, foliage) and vary the conditions: weather, traffic, time of day.
- Curate the scenarios to cover all risk levels, from relatively risk-free to "frightening as hell".
- Run each scenario with the naive driver and the risk-aware planner. Result table: time to destination score, risk exposure score, overall score, for the naive driver (optimizes only ETA) and the risk-aware driver (optimizes both). The cells hold `--` and no numbers.

### Phase 5: stretch

- Nathan calls it a stretch because the study in phases 1 to 4 is complete and interesting, and this phase adds a layer of complexity.
- Recomputing the waypoints is not the hard part. The hard part is to simulate unexpected scenarios that need a recompute. That adds to the scenarios that the team runs and evaluates.
- The algorithm must then plan from probabilities, not from assumed knowledge. The recompute takes effect when the probability prediction is at an extreme, for example when more pedestrians are present than the planner expected.
- Time permitting, report a third row in the same table: risk-aware with continuous recompute.

## Notes

Synthesis from a comparison with the other sources in the knowledge base.

- **Immediate versus stretch.** Phases 1 to 4 correspond to Stack A (naive) against Stack B (upfront planner) in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. Phase 5 corresponds to Stack C. The working design and [[CS513 Pre-Proposal Draft - Demand Against Capability]] treat all three stacks as the core comparison, and the draft schedules real-time adaptation for Oct 19 to Nov 1. This document moves it to a stretch goal.
- **Baselines.** The main study has two drivers. The always-cautious baseline of the working design and the pre-proposal schedule does not appear.
- **Action penalties.** This document holds off on left turns and obstruction sneaking in the first pass. The pre-proposal draft, task 3, measures the cost of unprotected left turns, lane changes, and passing a stopped vehicle. Both sources cannot hold for the first pass. No source says which one the group follows.
- **Penalty form.** This document weighs continuous exposure, scaled by speed, and plots penalty against time. The working design counts expected risk events and calibrates `d` and `m` from Stack A runs. No source reconciles the two forms. Pedestrian proximity and wet surface are new against the working design, where pedestrian-dense segments are an optional road attribute and wet roads are not listed. Night appears in the visibility model here.
- **Sensor model.** This document does not mention a sensor model. The working design requires one, because the baseline driver reads ground truth and weather does not otherwise change its behavior. Here the visibility model weighs exposure. Whether weather changes how the CARLA driver behaves is not addressed.
- **Budget.** This document says the planner trades from an "ETA budget". The working design has a risk budget, with `time + λ × penalty`. The pre-proposal draft says "within the risk budget". These are three wordings, and the group has not chosen one.
- **Violations.** The base concept scores "number of collision incidents". The working design fails a run on a violation. This document states no rule that fails a run.
- **Planner inputs.** Pedestrian probability in a grid is new. Construction zones, an input in the pre-proposal draft and in Nathan's first round, are absent. Sun angle as a deterministic model agrees with the working design.
- **Omniscience.** Phase 3 allows the planner to know the true world state as a simplification. Phase 5 needs probabilities. No other source has this split.
- **Calibration.** The working design and the pre-proposal keep calibration tracks apart from test tracks. This document does not mention calibration.
- **Open lead.** The `#TODO` about an existing scoring library or theory matches the open question about where the risk event thresholds come from. No source in the knowledge base answers it. It belongs in the literature survey.
- **Unverified.** Nothing here says which Scenario Runner the group uses. The working design refers to the CARLA `scenario_runner` criteria. That statement is unchecked against CARLA 0.9.16.
