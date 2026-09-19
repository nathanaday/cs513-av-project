---
type: source
title: "Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan"
status: developing
created: 2026-09-18
updated: 2026-09-18
tags:
  - source
  - project/cs513-project
  - brainstorm
source_type: conversation
author: Nathan Aday and Claude
date_published: 2026-09-18
url: 
source_id: src-8ca84d55ad29d23a4202
---

# Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan

Category: group project. This page belongs to [[cs513-project]], not to the course material.

## Summary

A verbatim record of two brainstorm rounds on 2026-09-18 between Nathan Aday and Claude. The file in the project repository is `docs/brainstorm-v2-penalty-eval-driver-plan.md`. Each round has Nathan's notes, then Claude's response. The rounds turn [[Project Idea v2 - Demand Against Capability]] into a working design: a penalty system, an evaluation score, and a baseline driver in CARLA.

Authority: synthetic. The design statements are proposals from a conversation. The group has not agreed on them. Claude wrote the CARLA details from memory of the 0.9.x Python API, and nobody has checked them against the 0.9.16 install.

## Key claims

### Round 1: Nathan's outline

- Capability degradation modes: weather, sun angle, construction or obstruction.
- A risk or difficulty metric creates the profile and the budget.
- Common actions have a cost: left turns, creeping around obstructions, lane changes.
- An upfront planner predicts route difficulty from known construction zones, the weather forecast, and a sun angle model.
- A perception pipeline scores difficulty in real time for unexpected weather and unexpected obstructions.
- The action planning changes in real time.
- The study compares three systems on simulated test tracks: the quickest path with no planner, the planner with no real-time feedback, and the full planner with feedback. The headline compares risk exposure across all scenarios.

### Round 1: Claude's four fixes

1. Risk alone is not a valid headline, because a slow planner always wins. Report risk and trip time together. Add an always-conservative baseline.
2. Do not score the planner with its own metric. Keep predicted risk (the planner's model) apart from measured outcome (collisions, minimum time-to-collision, hard braking, STL violations). The correlation of the two validates the difficulty metric.
3. Decide how degradation causes harm in the simulator. An agent that reads ground-truth positions is not affected by weather. Option A: real camera perception. Option B, recommended: a parametric sensor model that reduces detection range and adds misses as a function of rain, fog, and sun angle against heading.
4. Define the budget. Proposal: a risk budget for the trip. The planner minimizes trip time with expected risk inside the budget. In real time the vehicle tracks risk used against the plan, and tightens its profile or reroutes.

Smaller points: sun angle is the most distinctive condition, because heading and time of day predict it exactly. Keep demand and capability apart in the model. Report distributions and worst cases, with paired seeds. Get action costs from simulator runs.

### Round 2: Nathan's eval concepts

- Violation concept: things the vehicle must never do, such as collide, speed, or run a red light. A violation is an instant failure on the test course.
- Penalty concept: things that are not violations but accumulate penalties. Examples: time facing a low sun, time in bad weather, creeping around stopped vehicles, lane changes, left turns.
- Three driving stacks:
  - **A**: a basic driving algorithm. It avoids collisions and reaches the destination as fast as possible without violations.
  - **B**: A plus upfront planning that reduces penalties over the trip. No real-time adaptation.
  - **C**: B plus real-time recalculation. A perception pipeline reads the risk penalty accumulated and recomputes the optimal path.
- An eval table with invented numbers over 50 test tracks. Columns: number of violations, weighted ETA score, weighted penalty points, weighted total score. Nathan states that the numbers are fictional.
- A candidate list of budget factors (weather, left turns, traffic density, street width, speed limit, time of day, sunset, people nearby, hard braking) and absolute punishments (collisions with cars or people, running a red light).
- Nathan asks for specific plans for the penalty system, the weighted eval score, and an off-the-shelf, pluggable default driver in CARLA.

### Round 2: factor taxonomy

| Kind | What it is | Keep for the project |
| :---- | :---- | :---- |
| Condition | Lowers capability | Sun glare, one visibility scale (rain and fog together), night |
| Road attribute | Raises demand, known from the map | Pedestrian-dense segments. Others optional. |
| Action | Raises demand, selected by the planner | Unprotected left, lane change, pass a stopped vehicle |
| Outcome | Measured after the fact | All of them, but only in the evaluator |

Drop snow, wind, and heat. The source says CARLA has no snow, wind only moves foliage, and heat has no effect.

### Round 2: penalty system

- Penalty is demand multiplied by a capability factor. Each action has a base cost `d`. Each condition set gives a multiplier `m ≥ 1`, with clear daylight equal to 1. An action costs `d × m`. A segment costs `rate × time × m`.
- One penalty point is one expected risk event. Risk events: time-to-collision below 1.5 s, deceleration above 4 m/s², a gap to another actor below 1 m.
- Calibration: run Stack A on calibration tracks under each condition. `d` = events per action in clear conditions. `m` = the event rate under the condition divided by the clear rate.
- Calibration tracks stay separate from the 50 test tracks. This removes the circularity.
- CARLA constraint: the baseline driver reads ground truth, so the sensor model is required. Without it every `m` measures as 1.
- CARLA constraint: weather is global, not regional. Sun glare varies with heading and works natively. For weather, make the forecast temporal or put rain zones in the sensor model only.

### Round 2: score

| Column | Definition |
| :---- | :---- |
| Violations | Count of failed runs: collision, red light, stop sign, off-route. The CARLA `scenario_runner` criteria classes detect these. |
| ETA score | `100 × T_ref / T_actual`, capped at 100. `T_ref` is the free-flow time of the quickest route on the track. |
| Predicted penalty | What the planner's model expected. A diagnostic, not a result. |
| Measured risk events | What the evaluator counted from ground truth. The safety result. |

- Total score: a failed run scores 0. Otherwise `Total = α × ETA + (1 − α) × Safety`, with `Safety = 100 × max(0, 1 − events / cap)`. The cap comes from the calibration runs.
- Fix `α = 0.5` before any run. Show the ranking for α from 0.2 to 0.8.
- Budget: the planner minimizes `time + λ × penalty`. Each λ is equal to one risk budget. A sweep of λ gives a curve of time against risk. Headline: curve C is below curve B, and both are below the points for Stack A and an always-cautious driver.
- Statistics: collisions are rare, so 50 runs cannot separate 0 from 2. Run each track with 3 to 5 seeds, the same seeds for every stack. Report risk events with confidence intervals.
- The source says the score format is close to the CARLA Leaderboard driving score.

### Round 2: baseline driver

- Use `BehaviorAgent` from `PythonAPI/carla/agents/navigation/`. Do not use the Traffic Manager autopilot.
- `BehaviorAgent` obeys traffic lights, stop signs, and speed limits, and brakes for vehicles and pedestrians.
- It has three profiles, `Cautious`, `Normal`, and `Aggressive`, in `behavior_types.py`. Each is a class of numbers. This is the profile switch.
- It routes with `GlobalRoutePlanner`: A* on a `networkx` graph, edge weight equal to length, each edge tagged with its maneuver type. Replace the weight with `time + λ × penalty`. This is the trip planner hook.
- It is weak at unprotected left turns, so Stack A fails somewhere.

| Interface | Stack A | Stack B | Stack C |
| :---- | :---- | :---- | :---- |
| `Router`: map, origin, destination → route | Quickest path | Minimize time + λ × predicted penalty, from forecast | Same, called again when conditions change |
| `ProfilePolicy`: segment, conditions → driver parameters | `Normal` always | Set for each segment up front | Updated at about 1 Hz from observed conditions |
| `WorldView`: what the driver can see | Degraded by the sensor model | Same | Same |
| `Evaluator`: ground truth → violations, events, time | Same for all | Same | Same |

- `WorldView` is a subclass of `BehaviorAgent` that filters the actor list before the obstacle checks. The `Evaluator` shares no code with the planner.
- Stack C needs hysteresis on the profile switch, for example a hold of 5 seconds.

### Round 2: order of work

1. `BehaviorAgent` on a fixed route with the `Evaluator` logging. This is Stack A.
2. Add the sensor model. Confirm that rain and glare raise the event rate. This is the go or no-go test for the idea, to run in week one.
3. Calibrate `d` and `m`.
4. Add the `Router` cost. This is Stack B.
5. Add real-time updates. This is Stack C.

## Notes

- Every threshold in the source (1.5 s, 4 m/s², 1 m, 5 s, α = 0.5, 3 to 5 seeds) is a starting value that Claude proposed. None comes from a measurement or a cited standard.
- The statements about CARLA behavior (global weather, no snow, `BehaviorAgent` internals, `GlobalRoutePlanner` edge weights, `scenario_runner` criteria) have no source in the knowledge base. Check them against CARLA 0.9.16 before the group relies on them.
- The source replaces the always-Heavy baseline of [[CS513 Project Proposal Draft]] with Stack A and an always-cautious driver.
