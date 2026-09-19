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

2026-09-18. Filed the working design for version two of the group project [[cs513-project]].

## Key Recent Facts

- The knowledge base has two categories: the CSCI 513 course material and the group project. Group project pages carry the tag `project/cs513-project`.
- Version one of the idea budgets compute ([[CS513 Project Proposal Draft]]). The group will probably not pursue it.
- Version two is [[Project Idea v2 - Demand Against Capability]]. It now has a working design in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. The group has not agreed on it.
- Design in brief: three stacks (A basic driver, B plus upfront planner, C plus real-time recalculation) and an always-cautious baseline. Penalty = demand × capability multiplier, in units of expected risk events. The planner minimizes `time + λ × penalty`; λ sets the risk budget. The score joins ETA and measured risk events, and a violation fails the run.
- Baseline driver: the CARLA `BehaviorAgent`. A parametric sensor model is required, because the agent reads ground truth.
- Go or no-go test: the sensor model must make rain and glare raise the event rate of Stack A.
- The CARLA statements in the design are from memory. Check them against 0.9.16.
- The course asks for one page: title, cluster (C1 to C8), team members, abstract of 5 to 6 lines, key milestones. ([[CSCI 513 Project Registration Instructions]]) The version one draft lists the pitch for Sep 21.

## Recent Changes

- Created [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]].
- Added the working design to [[Project Idea v2 - Demand Against Capability]] and [[cs513-project]].

## Active Threads

- Discuss the working design with the group.
- Write the formal pre-proposal: title, cluster, abstract, milestones.
- Find sources for difficulty-aware routing for the literature survey.
- Ingest the course introduction deck that lists the clusters.
