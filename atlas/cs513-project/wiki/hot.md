---
type: meta
title: Hot Cache
status: developing
created: 2026-09-16
updated: 2026-09-18
tags:
  - meta
  - hot-cache
---

# Recent Context

## Last Updated

2026-09-18. The knowledge base was renamed to `cps-project-kb` and moved into the project repository. It now holds the group project [[cs513-project]] only.

## Key Recent Facts

- Course material belongs in the separate knowledge base `cps-course`, not here. See [[overview]].
- Version one of the idea budgets compute ([[CS513 Project Proposal Draft]]). The group will probably not pursue it.
- Version two is [[Project Idea v2 - Demand Against Capability]]. It has a working design in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. The group has not agreed on it.
- Design in brief: three stacks (A basic driver, B plus upfront planner, C plus real-time recalculation) and an always-cautious baseline. Penalty = demand × capability multiplier, in units of expected risk events. The planner minimizes `time + λ × penalty`; λ sets the risk budget. The score joins ETA and measured risk events, and a violation fails the run.
- Baseline driver: the CARLA `BehaviorAgent`. A parametric sensor model is required, because the agent reads ground truth.
- Go or no-go test: the sensor model must make rain and glare raise the event rate of Stack A.
- The CARLA statements in the design are from memory. Check them against 0.9.16.
- A pre-proposal draft exists in the repository: `docs/pre-proposal-draft.md`, with a LaTeX copy and a one-page PDF. Title: "Demand Against Capability: Risk-Budgeted Route Planning and Adaptive Behavior for Autonomous Driving". Cluster: C4 Autonomous Driving. It is not ingested yet.
- The course asks for one page: title, cluster, team members, abstract of 5 to 6 lines, key milestones. ([[CSCI 513 Project Registration Instructions]]) The version one draft lists the pitch for Sep 21.

## Recent Changes

- Rewrote [[overview]] and [[index]] for the project-only scope.

## Active Threads

- Discuss the working design and the pre-proposal draft with the group.
- Ingest the pre-proposal when the group agrees on it.
- Find sources for difficulty-aware routing for the literature survey.
