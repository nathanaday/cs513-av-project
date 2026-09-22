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

2026-09-20. Added the four component pages. This knowledge base holds the group project [[cs513-project]] only.

## Key Recent Facts

- Course material belongs in the separate knowledge base `cs513-course`, not here. See [[overview]].
- Version one budgets compute ([[CS513 Project Proposal Draft]]). The group will probably not pursue it.
- Version two is [[Project Idea v2 - Demand Against Capability]]. The working design is in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. The group has not agreed on it.
- Components, each a stub page: [[Naive Driver]] (ETA only, Stack A), [[Risk-Aware Planned Driver]] (Stack B), [[Risk Exposure Model]] (pedestrian proximity, visibility, and wet surface in the first pass), [[Risk-Aware Planning Algorithm]] (not designed yet).
- Design in brief: three stacks and an always-cautious baseline. The planner minimizes `time + λ × penalty`. A violation fails the run. The baseline is the CARLA `BehaviorAgent`. A parametric sensor model is required, because the agent reads ground truth. The go or no-go test: rain and glare must raise the event rate of Stack A. The CARLA statements are from memory; check them against 0.9.16.
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]: cluster C4, six members, six tasks, schedule to Dec 10. The originals stay in `docs/prepreposal/`. The pitch is due Sep 21. The abstract is about eight lines; the course asks for 5 to 6.
- [[Basic Phases]] (Nathan; original at `ideas/Basic Phases.md`, which the group reads): phases 1 to 4 are the immediate goals. Phase 5, real-time recompute, is a stretch goal.
- Conflicts, none resolved: recompute is core in the pre-proposal and stretch in [[Basic Phases]]; the always-cautious baseline is absent from [[Basic Phases]]; left turns are measured in the pre-proposal and held back in [[Basic Phases]]; the budget is a risk budget, a constraint, or an ETA budget; [[Basic Phases]] has no sensor model; the planner may use the same model that scores the result.

## Recent Changes

- Created the four component pages and linked them from the project, concept, index, and source pages.

## Active Threads

- Discuss the plans with the group. Settle the scope of recompute and the form of the budget.
- Shorten the pre-proposal abstract, and name a lead for each milestone.
- Find an existing library or theory that scores drive safety, and sources for difficulty-aware routing.
