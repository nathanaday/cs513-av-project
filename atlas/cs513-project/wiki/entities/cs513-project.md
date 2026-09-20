---
type: entity
title: "cs513-project"
status: seed
created: 2026-09-18
updated: 2026-09-18
aliases:
  - CS513 group project
  - CSCI 513 group project
tags:
  - entity
  - project
  - project/cs513-project
---

# cs513-project

Category: group project. Every page with the tag `project/cs513-project` belongs to this project and not to the CSCI 513 course material.

## Overview

The group project of a six-person team in CSCI 513 at USC. The project is in the self-driving domain and runs in a driving simulator. The idea is still in brainstorm, and it has two versions.

State on 2026-09-18: the team is brainstorming the pre-proposal. The project has no title and no implementation. The group writes the formal pre-proposal when version two is ready.

Team: Yonsoo Kim, Nathan Aday, Tomohiko Uemura, Rachel Lin, Jeslyn Yang, Illy Hoang. ([[CS513 Project Proposal Draft]])

## Idea versions

| Version | Idea | State | Page |
| :---- | :---- | :---- | :---- |
| v1 | Budget compute: a scheduler switches between a Nano and a Heavy perception path. | Probably not pursued. The compute-budget story does not transfer to real self-driving systems. | [[CS513 Project Proposal Draft]] |
| v2 | Demand against capability: the vehicle compares situation difficulty with its own capability and switches to a more risk-averse decision profile when capability drops. Includes difficulty-aware routing and several planning layers. | Current brainstorm, with a working design. Not agreed by the group. | [[Project Idea v2 - Demand Against Capability]] |

The working design of version two is in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]: three driving stacks (A, B, C) on the CARLA `BehaviorAgent`, a penalty system in units of expected risk events, a risk budget, and a score that joins trip time and measured risk events.

## Plan from version one

These items come from version one. [[Project Idea v2 - Demand Against Capability]] proposes to keep the simulator loop, the STL monitors, the falsification campaign, and the logging, and to replace the baseline.

- Success criterion: less compute and energy than an always-Heavy baseline, with safety no worse than that baseline. The safety measures are collisions, minimum time-to-collision, and specification violations. The result must hold in easy and in hard scenarios. ([[CS513 Project Proposal Draft]], Expected Outcome)
- Trigger metrics: wake-up latency, missed anomalies, false alarms. ([[CS513 Project Proposal Draft]], Task Breakdown)
- Fallback: when uncertain, go Heavy and slow down. ([[CS513 Project Proposal Draft]], Task Breakdown)
- Verification: online STL monitors and a falsification campaign, with counterexamples reported before and after fixes. ([[CS513 Project Proposal Draft]], Task Breakdown)
- Measurement: all official latency and power numbers come from one reference machine. ([[CS513 Project Proposal Draft]], Resources Required)

## Dates

| Date | Event | Source |
| :---- | :---- | :---- |
| Sep 21 | Project pitch due | [[CS513 Project Proposal Draft]], Schedule |
| Early October | Simulator decided | [[CS513 Project Proposal Draft]], Task Breakdown |
| TBA | Check-in demo | [[CS513 Project Proposal Draft]], Schedule |
| Nov 30 / Dec 1 | 5-minute video uploaded / demo day | [[CS513 Project Proposal Draft]], Schedule |
| Dec 10 | 15-page final report due | [[CS513 Project Proposal Draft]], Schedule |

The example in [[CSCI 513 Project Registration Instructions]] also shows Dec 1 for the final presentation and Dec 10 for the final report.

## Submission gaps

Synthesis from a comparison of the two sources. [[CSCI 513 Project Registration Instructions]] asks for one page with five items. The state of each item in [[CS513 Project Proposal Draft]]:

| Required item | State in the draft |
| :---- | :---- |
| Project title | Missing. The draft shows the placeholder "Project Title". |
| Cluster (C1 to C8) | Missing. The cluster list is in a course deck that the knowledge base does not hold. |
| Names of team members | Present. |
| Abstract, 5 to 6 lines | Missing. The Purpose section holds the content but is a bullet list. |
| Key project milestones | Present as a schedule table. It names no lead for each milestone; the course example does. |
| One-page limit | The draft has six sections and is likely longer than one page when formatted. |

The pre-proposal for version two must fill the same five items. The purpose and the task breakdown need a rewrite for version two. The order of work in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]] is a starting point for the milestones.

## Open questions

- Is the "project pitch" of Sep 21 the same submission as the one-page registration? No source in the knowledge base says so.
- Which cluster does the project belong to?
- Does the group accept the version two working design? See [[Project Idea v2 - Demand Against Capability]] for the open questions of version two.
- Which simulator? Version one requires Apple Silicon support, camera rendering, and scripted scenarios. ([[CS513 Project Proposal Draft]], Resources Required) The version two design assumes CARLA 0.9.16.
- Which STL monitoring library and falsification tool?
- Which papers go in the literature survey? The draft needs at least 3.

## Relationships

- Course: CSCI 513 at USC. The course sets the submission requirements. ([[CSCI 513 Project Registration Instructions]])
- Compute: USC CARC cluster, planned for falsification batches. ([[CS513 Project Proposal Draft]], Resources Required)

## Sources

- [[CSCI 513 Project Registration Instructions]]: course guidance on the project registration page.
- [[CS513 Project Proposal Draft]]: the team's brainstorm document, version one of the idea.
- [[Project Idea v2 - Demand Against Capability]]: version two, saved from a conversation.
- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]: the verbatim design rounds for version two.
