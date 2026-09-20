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

2026-09-20. Ingested the pre-proposal draft and cleared the inbox. This knowledge base holds the group project [[cs513-project]] only.

## Key Recent Facts

- Course material belongs in the separate knowledge base `cps-course`, not here. See [[overview]].
- Version one of the idea budgets compute ([[CS513 Project Proposal Draft]]). The group will probably not pursue it.
- Version two is [[Project Idea v2 - Demand Against Capability]]. It has a working design in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. The group has not agreed on it.
- Design in brief: three stacks (A basic driver, B plus upfront planner, C plus real-time recalculation) and an always-cautious baseline. Penalty = demand × capability multiplier, in units of expected risk events. The planner minimizes `time + λ × penalty`; λ sets the risk budget. The score joins ETA and measured risk events, and a violation fails the run.
- Baseline driver: the CARLA `BehaviorAgent`. A parametric sensor model is required, because the agent reads ground truth.
- Go or no-go test: the sensor model must make rain and glare raise the event rate of Stack A.
- The CARLA statements in the design are from memory. Check them against 0.9.16.
- Pre-proposal draft: [[CS513 Pre-Proposal Draft - Demand Against Capability]]. Cluster C4 Autonomous Driving, six team members, six tasks, schedule to the Dec 10 report. The originals stay in `docs/prepreposal/` (Markdown, LaTeX, PDF). The PDF is one page. The pitch is due Sep 21.
- The draft differs from the working design in the budget: it selects the quickest route within the risk budget, where the design minimizes `time + λ × penalty`. It also keeps the falsification campaign from version one.
- The draft abstract is about eight lines. The course asks for 5 to 6. ([[CSCI 513 Project Registration Instructions]])

## Recent Changes

- Filed the pre-proposal draft, and updated [[cs513-project]], [[Project Idea v2 - Demand Against Capability]], and [[index]].
- The inbox note "CS513 Project Brainstorm" has the same text as Nathan's notes in the v2 brainstorm source. It is captured and adds no page.
- The v2 brainstorm file reappeared in the inbox. It was already ingested, so no new page.

## Active Threads

- Discuss the working design and the pre-proposal draft with the group.
- Decide the budget form: a constraint or a weighted cost.
- Shorten the abstract to the course limit, and name a lead for each milestone.
- Find sources for difficulty-aware routing for the literature survey.
