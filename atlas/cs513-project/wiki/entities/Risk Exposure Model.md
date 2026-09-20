---
type: entity
title: "Risk Exposure Model"
status: seed
created: 2026-09-20
updated: 2026-09-20
aliases:
  - Penalty model
  - Penalty system
  - Risk exposure score
tags:
  - entity
  - project/cs513-project
  - component
---

# Risk Exposure Model

Category: group project. This page belongs to [[cs513-project]], not to the course material.

## Overview

The scoring system that turns a drive into risk exposure over time. Nathan's phase 2 develops all the software eval modules that produce the penalty score against time for a scenario drive. ([[Basic Phases]]) The [[Risk-Aware Planning Algorithm]] uses it as its cost. The result tables report its output as the risk exposure score, for the [[Naive Driver]] and the [[Risk-Aware Planned Driver]].

Status on 2026-09-20: designed in outline, not built. No parameter has a value.

The sources use different names: penalty model and risk exposure score ([[Basic Phases]]), penalty system ([[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]). This page uses "Risk Exposure Model".

## Risk types covered in the first pass

From [[Basic Phases]], phase 2. Each module weighs exposure accumulated over the drive. Speed scales each one.

| Risk type | What it weighs | Variables |
| :---- | :---- | :---- |
| Pedestrian proximity | Exposure to pedestrian traffic within `P` meters of the ego vehicle. Higher speed near pedestrians gives a higher penalty. | Speed; `IsSurfaceWet` (bool, simpler); `SurfaceWetSeverity` only if CARLA gives it easily |
| Visibility | Exposure to poor visibility from rain, fog, and direct sun within `M` degrees of the horizon, or at night. | Speed; `VisibilitySeverity` |
| Wet surface | Time on wet surfaces. A faster speed on a wet surface gives a higher penalty per second. | None listed |

The test drive of phase 2 includes a bit of each penalty situation: weather, low sun, pedestrians, wet roads.

## Risk types held back

[[Basic Phases]] holds these off for the first pass: left turns, obstruction sneaking, and other single-event risky events. Reason given: it may be hard to prove that they belong to the risk assessment and to model them in the sim, unless a third-party module already gives them.

## What each source names

Synthesis from a comparison of the sources.

| Risk type | [[Basic Phases]] | [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]] | [[CS513 Pre-Proposal Draft - Demand Against Capability]] |
| :---- | :---- | :---- | :---- |
| Pedestrians | First pass | Optional road attribute (pedestrian-dense segments) | Not named |
| Rain and fog (visibility) | First pass | Kept, as one visibility scale | Sensor model; forecast weather |
| Sun glare, low sun | First pass, inside visibility | Kept | Kept |
| Night | First pass, inside visibility | Kept | Not named |
| Wet surface | First pass | Not listed | Not named |
| Unprotected left turn | Held back | Kept, as an action | Kept, as an action |
| Lane change | Not named | Kept, as an action | Kept, as an action |
| Passing a stopped vehicle, obstruction sneaking | Held back | Kept, as an action | Kept, as an action |
| Construction zones | Not named | Named in Nathan's first round | Planner input |
| Hard braking | Not named | A measured risk event | A measured risk event |

The working design drops snow, wind, and heat. Its source says CARLA has no snow, wind only moves foliage, and heat has no effect. That statement is unchecked.

## Form of the model

- [[Basic Phases]]: exposure accumulates over time, scaled by speed. The output is a penalty score against time graph, and a risk exposure score per drive.
- Working design: penalty is demand times a capability multiplier. An action costs `d × m`. One penalty point is one expected risk event. `d` and `m` come from calibration runs of the [[Naive Driver]]. Risk events are time-to-collision below 1.5 s, deceleration above 4 m/s², and a gap below 1 m. All thresholds are Claude's starting values.

No source reconciles the two forms.

## Open questions

- Does the planner use the same model that scores the result? [[Basic Phases]] has the algorithm use the phase 2 model. The working design keeps the planner's predicted penalty apart from the evaluator's measured risk events, so that the planner is not scored with its own metric.
- Is there a well-known module, library, or theory that scores the safety of a drive? `#TODO` in [[Basic Phases]]. No source in the knowledge base answers it.
- What are the modules and their definitions? `#TODO` in [[Basic Phases]]. The values of `P` and `M` are open.
- Does CARLA give surface wetness severity easily?
- Do the first-pass modules include the action penalties that the pre-proposal measures?

## Relationships

- Scores the [[Naive Driver]] and the [[Risk-Aware Planned Driver]].
- Used as the cost of the [[Risk-Aware Planning Algorithm]].
- Part of [[Project Idea v2 - Demand Against Capability]].

## Sources

- [[Basic Phases]]
- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]
