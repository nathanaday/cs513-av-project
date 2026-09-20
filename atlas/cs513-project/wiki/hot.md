---
type: meta
title: Hot Cache
status: developing
created: 2026-09-16
updated: 2026-09-20
tags:
  - meta
  - hot-cache
---

# Recent Context

## Last Updated

2026-09-20. Ingested the pre-proposal draft and the [[Basic Phases]] document. This knowledge base holds the group project [[cs513-project]] only.

## Key Recent Facts

- Course material belongs in the separate knowledge base `cps-course`, not here. See [[overview]].
- Version one of the idea budgets compute ([[CS513 Project Proposal Draft]]). The group will probably not pursue it.
- Version two is [[Project Idea v2 - Demand Against Capability]]. It has a working design in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. The group has not agreed on it.
- Design in brief: three stacks (A basic driver, B plus upfront planner, C plus real-time recalculation) and an always-cautious baseline. Penalty = demand × capability multiplier, in units of expected risk events. The planner minimizes `time + λ × penalty`; λ sets the risk budget. The score joins ETA and measured risk events, and a violation fails the run.
- Baseline driver: the CARLA `BehaviorAgent`. A parametric sensor model is required, because the agent reads ground truth.
- Go or no-go test: the sensor model must make rain and glare raise the event rate of Stack A.
- The CARLA statements in the design are from memory. Check them against 0.9.16.
- Pre-proposal draft: [[CS513 Pre-Proposal Draft - Demand Against Capability]]. Cluster C4 Autonomous Driving, six team members, six tasks, schedule to the Dec 10 report. The originals stay in `docs/prepreposal/`. The PDF is one page. The pitch is due Sep 21. The abstract is about eight lines; the course asks for 5 to 6.
- [[Basic Phases]] (Nathan, 2026-09-20; original at `ideas/Basic Phases.md`, which the group reads): phases 1 to 4 are the immediate goals (CARLA base driver, penalty model, risk-aware planner, scenarios that compare naive against risk-aware). Phase 5, real-time recompute, is a stretch goal.
- First-pass penalty models in [[Basic Phases]]: pedestrian proximity, visibility, wet surface, each scaled by speed. Left turns and obstruction sneaking wait.
- Conflicts between the plans, none resolved: real-time recompute is core in the pre-proposal and stretch in [[Basic Phases]]; the always-cautious baseline is absent from [[Basic Phases]]; left turns and lane changes are measured in the pre-proposal and deferred in [[Basic Phases]]; the budget is a risk budget, a constraint, or an ETA budget depending on the source; [[Basic Phases]] does not mention a sensor model.

## Recent Changes

- Filed [[Basic Phases]] and updated [[cs513-project]], [[Project Idea v2 - Demand Against Capability]], and [[index]].
- Filed the pre-proposal draft. The inbox is clear.

## Active Threads

- Discuss the working design, the pre-proposal draft, and [[Basic Phases]] with the group. Settle the scope of real-time recompute.
- Decide the budget form.
- Shorten the abstract to the course limit, and name a lead for each milestone.
- Find an existing library or theory that scores drive safety, and sources for difficulty-aware routing, for the literature survey.
