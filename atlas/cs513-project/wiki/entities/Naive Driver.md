---
type: entity
title: "Naive Driver"
status: seed
created: 2026-09-20
updated: 2026-09-20
aliases:
  - Stack A
  - Basic driver
  - Baseline driver
  - Basic driving system
tags:
  - entity
  - project/cs513-project
  - component
---

# Naive Driver

Category: group project. This page belongs to [[cs513-project]], not to the course material.

## Overview

The baseline driver of the project, in the CARLA simulator. It gets from A to B as fast as it can and obeys the hard rules, but it has no sense of risk aversion. It optimizes ETA only. It is the comparison point for [[Risk-Aware Planned Driver]]. ([[Basic Phases]], Base Concept and phase 4)

Status on 2026-09-20: not built. The sources give a role and a candidate implementation, and no results.

The sources use these names for the same thing: naive driver ([[Basic Phases]]), Stack A ([[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]), and basic driving system or baseline driver ([[CS513 Pre-Proposal Draft - Demand Against Capability]]). This page uses "Naive Driver".

## What the sources say

[[Basic Phases]]:

- Phase 1 is to get a basic driver working as the baseline driving case, run a scenario drive, and report the drive summary. A `#TODO` asks for a link to a public CARLA document or tutorial on a basic driver.
- Phase 4 lists it as "Naive (optimizes only ETA)" in the result table, next to the risk-aware driver. The score cells are empty.
- Phase 2 runs the first test drive with the [[Risk Exposure Model]] on the basic drive.

[[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]] (Stack A, a proposal from Claude, not agreed):

- It uses the CARLA `BehaviorAgent` and not the Traffic Manager autopilot.
- It follows the quickest path and keeps the `Normal` profile throughout.
- It obeys traffic lights, stop signs, and speed limits, and brakes for vehicles and pedestrians.
- It is weak at unprotected left turns, so it fails somewhere.
- A sensor model degrades what it sees. The `BehaviorAgent` reads ground truth, so without the sensor model weather does not affect it.
- Its runs on calibration tracks give the parameters of the penalty system.

[[CS513 Pre-Proposal Draft - Demand Against Capability]]: task 1 runs the baseline driver, the CARLA `BehaviorAgent`, on a fixed route. Task 2 checks that degraded conditions raise its risk event rate.

## Not the always-cautious baseline

The working design and the pre-proposal schedule also measure an always-cautious driver. It is a different baseline. It shows whether the planner is smart or only slow. It is not the Naive Driver. [[Basic Phases]] does not mention it.

## Open questions

- Which CARLA driver? [[Basic Phases]] names none and asks for a tutorial link. `BehaviorAgent` comes from the working design and the pre-proposal. The CARLA statements are unchecked against 0.9.16.
- Does the sensor model apply to this driver? [[Basic Phases]] does not mention a sensor model.

## Relationships

- Compared with [[Risk-Aware Planned Driver]], which follows a route from [[Risk-Aware Planning Algorithm]].
- Scored by the [[Risk Exposure Model]].
- Part of [[Project Idea v2 - Demand Against Capability]].

## Sources

- [[Basic Phases]]
- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]
