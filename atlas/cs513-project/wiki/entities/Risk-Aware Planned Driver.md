---
type: entity
title: "Risk-Aware Planned Driver"
status: seed
created: 2026-09-20
updated: 2026-09-20
aliases:
  - Stack B
  - Upfront planned driver
  - Risk-aware driver
  - Upfront risk-aware planning
tags:
  - entity
  - project/cs513-project
  - component
---

# Risk-Aware Planned Driver

Category: group project. This page belongs to [[cs513-project]], not to the course material.

## Overview

The driver that follows a route from [[Risk-Aware Planning Algorithm]]. The planner runs once before the trip. The driver does not recompute during the trip. It is the main system that the project compares with the [[Naive Driver]]. ([[Basic Phases]], phases 3 and 4)

Status on 2026-09-20: not built. No source gives results.

Names in the sources: risk-aware driver ([[Basic Phases]]), Stack B ([[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]), upfront risk-aware planning ([[CS513 Pre-Proposal Draft - Demand Against Capability]]). This page uses "Risk-Aware Planned Driver".

## What the sources say

[[Basic Phases]]:

- Phase 3 ends with a test drive of the vehicle along the planned waypoints.
- Phase 4 lists it as "Risk aware (optimizes both risk and ETA)", with empty score cells.

[[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]] (Stack B, a proposal, not agreed):

- It is Stack A plus upfront planning that reduces penalties over the trip, with no real-time adaptation.
- A `Router` minimizes `time + λ × predicted penalty`, from the forecast.
- A `ProfilePolicy` sets the driver parameters for each segment before the trip.
- The same sensor model that degrades the [[Naive Driver]] degrades this driver.

[[CS513 Pre-Proposal Draft - Demand Against Capability]]: the second of three systems, "upfront risk-aware planning".

## Variant: real-time recompute

The third system adds continuous recompute of the route while the drive runs. In the working design it is Stack C. [[Basic Phases]] makes it a stretch goal (phase 5). The pre-proposal draft makes it a core task. It has no page of its own yet. See [[Risk-Aware Planning Algorithm]] for the recompute.

## Open questions

- Does the driver change its driving profile for each segment, as in the working design, or does it only follow a different route, as [[Basic Phases]] describes? [[Basic Phases]] does not mention profile switching.
- Is the recompute variant core or stretch?

## Relationships

- Follows routes from [[Risk-Aware Planning Algorithm]].
- Compared with the [[Naive Driver]], and scored by the [[Risk Exposure Model]].
- Part of [[Project Idea v2 - Demand Against Capability]].

## Sources

- [[Basic Phases]]
- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]
