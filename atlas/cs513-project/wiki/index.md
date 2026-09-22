---
type: meta
title: Wiki Index
status: evergreen
created: 2026-09-16
updated: 2026-09-20
tags:
  - meta
  - index
---

# Wiki Index

Every page in this knowledge base is listed here. Completed operations keep it current.

This knowledge base holds the CSCI 513 group project only. Course material belongs in the knowledge base `cs513-course`. See [[overview]].

## Sources

- [[CSCI 513 Project Registration Instructions]]: course guidance on the one-page project registration, with an example.
- [[CS513 Project Proposal Draft]]: the team's brainstorm document, version one of the idea (compute budget). Probably not pursued.
- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]: verbatim design rounds for version two. Penalty system, score, risk budget, and the CARLA baseline driver.
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]: the team's one-page pre-proposal draft for version two. Title, cluster C4, abstract, six tasks, and the schedule to Dec 10.
- [[Basic Phases]]: Nathan's phased plan for version two. Four immediate phases, one stretch phase (real-time recompute), and the first-pass penalty models.

## Concepts

- [[Project Idea v2 - Demand Against Capability]]: brainstorm version two. The vehicle switches to a risk-averse decision profile when its capability drops below the demand of the situation.

## Entities

- [[cs513-project]]: the group project, with its idea versions, components, phases, dates, and submission gaps.
- [[Naive Driver]]: the baseline CARLA driver. It optimizes ETA only. Stack A.
- [[Risk-Aware Planned Driver]]: the driver that follows a route from the planning algorithm. Stack B.
- [[Risk Exposure Model]]: the scoring of a drive and the risk types it covers. Also called the penalty model.
- [[Risk-Aware Planning Algorithm]]: the optimization that finds the route from ETA and risk exposure.
