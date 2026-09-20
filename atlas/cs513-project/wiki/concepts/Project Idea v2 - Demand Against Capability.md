---
type: concept
title: "Project Idea v2 - Demand Against Capability"
status: developing
assessment: provisional
created: 2026-09-18
updated: 2026-09-20
aliases:
  - Brainstorm version two
  - Project Idea v2
tags:
  - concept
  - project/cs513-project
  - brainstorm
---

# Project Idea v2 - Demand Against Capability

Category: group project. This page belongs to [[cs513-project]], not to the course material.

This page records brainstorm version two of the project idea. It comes from conversations on 2026-09-18 between Nathan Aday and Claude, and from a message that Nathan shared with the group. The group has not agreed on it. A draft of the formal pre-proposal now exists: [[CS513 Pre-Proposal Draft - Demand Against Capability]]. Nathan's document [[Basic Phases]] sets the phases and separates the immediate goals from a stretch goal. Version one is [[CS513 Project Proposal Draft]].

## Definition

The vehicle compares the **demand** of the driving situation with its own **capability**, and sets how much risk it accepts from the result.

- Demand: the predicted difficulty of a route segment or of the current scene.
- Capability: what the vehicle can do now. It drops when conditions degrade, for example when bad weather arrives or the sun causes high glare.
- Response: the vehicle switches to a more risk-averse profile. The profile changes the thresholds for decisions and planning on board. No model or compute path changes.

Nathan's message to the group states the mechanism: "instead of the compute path/model switching, it just switches its threshold for certain decisions and in many ways that's much easier and more elegant."

## Why version one changed

Version one budgets compute: it switches between a Nano and a Heavy perception path. The group lead rejected that story for these reasons, stated in the conversation:

- A passenger vehicle has a fixed compute load, designed to run near maximum performance at all times. The hardware is designed for a steady load, not a bursty one.
- Switching models during operation has its own cost.
- The compute-budget story therefore does not transfer to real self-driving systems.

No source in the knowledge base supports these statements. They are the group lead's conclusion from his own research.

## What the group wants to keep

Stated by Nathan in the conversation:

- The self-driving domain, with the option to work with camera, LiDAR, and radar.
- A planner and a risk assessment pipeline. A higher level scores route difficulty.
- Several layers of planning, or decisions made under a constraint. Nathan names this as what makes the project fruitful.
- A budget for a resource other than compute.
- A control focus that fits a CPS course. Most of the work is a vehicle agent in the simulator that makes these decisions. The project is not a perception and classification project.
- The CARLA simulator. The group has used it and likes it.
- Little or no machine learning training.
- The team supplies its own thresholds. The agent scores the risk of the current situation and compares it with what the vehicle is willing to do at that moment.
- Some experience with VLA models or world models, if a place for them exists.

Goal of the story: the group does not expect a novel contribution. It wants a project that is realistic or transferable enough to start a conversation with people in industry.

## Difficulty-aware routing

Nathan places the idea in the domain of difficulty-aware routing. His example: AV taxis avoid routes with many left turns, because left turns are more dangerous than right turns, and this changes the route they select. No source in the knowledge base supports this yet. A source for it belongs in the literature survey.

## Working design

The full record is [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. All of it is a proposal. Summary:

- **Three stacks.** A: a basic driver on the quickest path. B: A plus an upfront planner that reduces penalties over the trip. C: B plus real-time recalculation. An always-cautious driver is a fourth baseline. It shows whether the planner is smart or only slow.
- **Violations and penalties.** A violation (collision, red light) fails the run. A penalty accumulates. Nathan set this split.
- **Penalty formula.** Penalty = demand × capability multiplier. An action costs `d × m`. One penalty point is one expected risk event. `d` and `m` come from calibration runs of Stack A, on tracks that are separate from the test tracks.
- **Budget.** The budgeted resource is risk. The planner minimizes `time + λ × penalty`, and each λ is equal to one risk budget. A sweep of λ gives a curve of time against risk for each stack.
- **Score.** Predicted penalty (the planner's model) stays apart from measured risk events (the evaluator's count from ground truth). `Total = α × ETA + (1 − α) × Safety`, and a failed run scores 0. Fix α before the runs and show a sweep.
- **Conditions kept.** Sun glare, one visibility scale for rain and fog, night. Actions kept: unprotected left, lane change, pass a stopped vehicle.
- **Sensor model.** A parametric model degrades what the driver sees, as a function of visibility and sun angle against heading. It is required, because the baseline driver reads ground truth and weather does not affect it.
- **Baseline driver.** The CARLA `BehaviorAgent`. Its `Cautious`, `Normal`, and `Aggressive` profiles are the profile switch. The edge weights of its `GlobalRoutePlanner` are the trip planner hook. Four interfaces make the stacks pluggable: `Router`, `ProfilePolicy`, `WorldView`, `Evaluator`.
- **First test.** Confirm in week one that the sensor model makes rain and glare raise the event rate of Stack A. If it does not, the project has no effect to study.

## In the pre-proposal draft

[[CS513 Pre-Proposal Draft - Demand Against Capability]] turns the working design into the one-page form and a schedule from Sep 21 to Dec 10. It keeps the three systems, the `BehaviorAgent` baseline, the sensor model with its go or no-go test, the calibration tracks, and the profile switch with hysteresis. Differences from the working design:

- The draft says the planner "selects the quickest route within the risk budget". The working design minimizes `time + λ × penalty`. The group has not chosen between a constraint and a weighted sum.
- The draft keeps the online monitors and the falsification campaign from version one, as task 6.
- The draft does not give the score formula, the risk event thresholds, or a role for a VLM or VLA.

## Phases and the stretch goal

[[Basic Phases]] gives five phases. Phases 1 to 4 are the immediate goals: a CARLA base driver, a penalty model, a risk-aware planner, and the test scenarios that compare the naive driver with the risk-aware planner. Phase 5, real-time risk recompute, is a stretch goal. In terms of the working design, phases 1 to 4 are Stack A against Stack B, and phase 5 is Stack C.

The document and the earlier sources differ on these points:

- **Scope of Stack C.** Stretch in [[Basic Phases]]. Core in the working design and in the pre-proposal draft, which schedules it for Oct 19 to Nov 1.
- **Baselines.** [[Basic Phases]] compares two drivers. It has no always-cautious baseline.
- **First-pass penalties.** [[Basic Phases]] scores exposure to pedestrians, poor visibility, and wet surfaces, scaled by speed. It holds off on left turns and obstruction sneaking. The pre-proposal draft measures action costs for left turns, lane changes, and passing a stopped vehicle in task 3.
- **Budget wording.** [[Basic Phases]] says the planner trades from an ETA budget. The working design budgets risk.
- **Sensor model.** [[Basic Phases]] does not mention one.

The details are in the Notes of [[Basic Phases]]. No source in the knowledge base says which plan the group follows.

## Earlier proposals, not part of the working design

Claude proposed these in the first conversation. The working design does not use them so far.

- Other resources to budget: time slack against an arrival deadline; human attention, such as remote-assist calls or L3 takeover requests; EV energy, judged a weak fit.
- A VLM in a behavior layer at about 1 Hz that revises the difficulty estimate. Its latency is acceptable at that rate.
- The CPS question "what happens to closed-loop safety when a slow layer is late or wrong?", a runtime assurance problem (Simplex architecture).
- Carried over from version one: the latency-faithful loop, STL monitors, the falsification campaign, logging, and the dashboard. The working design mentions STL violations as a measured outcome and falsification as a search for scenarios where the full planner does worse than a baseline. The pre-proposal draft keeps the monitors, the campaign, and the dashboard.
- World models: no cheap place found. CARLA-trained driving VLMs need a strong NVIDIA GPU, which conflicts with the Apple Silicon requirement in version one.

## Open questions

- Does the group accept the working design, and risk as the budgeted resource? The draft is written on it, but no source says the group approved either.
- Is real-time recompute (Stack C) a core goal or a stretch goal?
- Is the budget a constraint on the route, a weight in its cost, or an ETA budget?
- Does the sensor model produce a measurable effect? This is the go or no-go test.
- Are the CARLA statements correct for version 0.9.16? See the notes in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]].
- How does the project show weather that a route can avoid, when CARLA weather is global? The options are a temporal forecast or rain zones in the sensor model only.
- Where do the risk event thresholds come from, and how does the group justify them? Is there an existing library or theory that scores the safety of a drive? ([[Basic Phases]] asks the second question.)
- Does a VLM or VLA have a role?
- Which papers support difficulty-aware routing and the left-turn example?

## Related

- [[cs513-project]]: the project.
- [[CS513 Project Proposal Draft]]: version one, the compute-budget idea.
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]: the draft pre-proposal for this version.
- [[Basic Phases]]: the phased plan with the stretch goal.
- [[CSCI 513 Project Registration Instructions]]: what the formal pre-proposal must contain.

## Sources

- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]: the verbatim record of the design rounds. Authority: synthetic.
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]: the team's draft. Authority: primary.
- [[Basic Phases]]: Nathan's phased plan. Authority: primary.
- The first conversation on 2026-09-18, including the message Nathan shared with the group. No captured source.
