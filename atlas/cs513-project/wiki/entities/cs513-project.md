---
type: entity
title: "cs513-project"
status: seed
created: 2026-09-18
updated: 2026-09-20
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

The group project of a six-person team in CSCI 513 at USC. The project is in the self-driving domain and runs in a driving simulator. The idea has two versions. Version two has a draft pre-proposal.

State on 2026-09-20: the pre-proposal draft has a title ("Demand Against Capability: Risk-Budgeted Route Planning and Adaptive Behavior for Autonomous Driving"), a cluster (C4 Autonomous Driving), the team, an abstract, six tasks, and a schedule. It is one page as a PDF. The project has no implementation. No source says that the group approved the draft or that anyone submitted it. ([[CS513 Pre-Proposal Draft - Demand Against Capability]])

Team: Yonsoo Kim, Nathan Aday, Tomohiko Uemura, Rachel Lin, Jeslyn Yang, Illy Hoang. ([[CS513 Project Proposal Draft]]; the same six names are in [[CS513 Pre-Proposal Draft - Demand Against Capability]].)

## Idea versions

| Version | Idea | State | Page |
| :---- | :---- | :---- | :---- |
| v1 | Budget compute: a scheduler switches between a Nano and a Heavy perception path. | Probably not pursued. The compute-budget story does not transfer to real self-driving systems. | [[CS513 Project Proposal Draft]] |
| v2 | Demand against capability: the vehicle compares situation difficulty with its own capability and switches to a more risk-averse decision profile when capability drops. Includes difficulty-aware routing and several planning layers. | Working design, and a draft pre-proposal built on it. Not agreed by the group. | [[Project Idea v2 - Demand Against Capability]] |

The working design of version two is in [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]: three driving stacks (A, B, C) on the CARLA `BehaviorAgent`, a penalty system in units of expected risk events, a risk budget, and a score that joins trip time and measured risk events. The draft pre-proposal follows it. The draft says the planner selects the quickest route within the risk budget. The working design minimizes `time + λ × penalty`. ([[CS513 Pre-Proposal Draft - Demand Against Capability]], Notes)

The repository holds the draft in `docs/prepreposal/` as Markdown, LaTeX, and PDF.

## Plan from version one

These items come from version one. [[Project Idea v2 - Demand Against Capability]] proposes to keep the simulator loop, the STL monitors, the falsification campaign, and the logging, and to replace the baseline. The pre-proposal draft keeps the monitors and the campaign in its task 6.

- Success criterion: less compute and energy than an always-Heavy baseline, with safety no worse than that baseline. The safety measures are collisions, minimum time-to-collision, and specification violations. The result must hold in easy and in hard scenarios. ([[CS513 Project Proposal Draft]], Expected Outcome)
- Trigger metrics: wake-up latency, missed anomalies, false alarms. ([[CS513 Project Proposal Draft]], Task Breakdown)
- Fallback: when uncertain, go Heavy and slow down. ([[CS513 Project Proposal Draft]], Task Breakdown)
- Verification: online STL monitors and a falsification campaign, with counterexamples reported before and after fixes. ([[CS513 Project Proposal Draft]], Task Breakdown)
- Measurement: all official latency and power numbers come from one reference machine. ([[CS513 Project Proposal Draft]], Resources Required)

## Dates

From the pre-proposal draft, Schedule. ([[CS513 Pre-Proposal Draft - Demand Against Capability]])

| Date | Event |
| :---- | :---- |
| Sep 21 | Project pitch due |
| Sep 22 - Oct 4 | CARLA tested on all machines; specs, metrics, and risk events defined; basic driving system and evaluator running; sensor model go or no-go test complete |
| Oct 5 - Oct 18 | Test tracks built; action costs and condition multipliers calibrated; route planner working |
| Oct 19 - Nov 1 | Real-time adaptation running end to end; basic and always-cautious baselines measured; check-in demo (date TBA) |
| Nov 2 - Nov 15 | Falsification campaign; counterexamples fixed; planner and thresholds refined |
| Nov 16 - Nov 29 | Final runs, figures, demo dashboard, video |
| Nov 30 / Dec 1 | 5-minute video uploaded / demo day |
| Dec 10 | 15-page final report due |

Version one had the same dates for the pitch, the video, the demo day, and the report, and a simulator decision in early October. ([[CS513 Project Proposal Draft]], Schedule and Task Breakdown) The example in [[CSCI 513 Project Registration Instructions]] also shows Dec 1 for the final presentation and Dec 10 for the final report.

## Submission gaps

Synthesis from a comparison of the sources. [[CSCI 513 Project Registration Instructions]] asks for one page with five items. The state of each item:

| Required item | Version one draft | Pre-proposal draft |
| :---- | :---- | :---- |
| Project title | Missing. The draft shows the placeholder "Project Title". | Present. |
| Cluster (C1 to C8) | Missing. The cluster list is in a course deck that the knowledge base does not hold. | Present: C4 Autonomous Driving. The knowledge base cannot check it against the cluster list. |
| Names of team members | Present. | Present. |
| Abstract, 5 to 6 lines | Missing. The Purpose section holds the content but is a bullet list. | Present, but longer than the limit: six sentences, about eight lines in the PDF. |
| Key project milestones | Present as a schedule table. It names no lead for each milestone; the course example does. | Present as a schedule table. It names no lead either. |
| One-page limit | The draft has six sections and is likely longer than one page when formatted. | Met: the PDF is one page. |

## Open questions

- Is the "project pitch" of Sep 21 the same submission as the one-page registration? No source in the knowledge base says so.
- Does the group accept the version two working design and the draft built on it? See [[Project Idea v2 - Demand Against Capability]] for the open questions of version two.
- Is the risk budget a constraint on the route or a weight in its cost?
- Does the abstract shrink to the 5 to 6 lines that the course asks for?
- Who leads each milestone?
- Does the group confirm CARLA? The pre-proposal draft names CARLA 0.9.16. Version one required Apple Silicon support, camera rendering, and scripted scenarios. ([[CS513 Project Proposal Draft]], Resources Required)
- Which STL monitoring library and falsification tool?
- Which papers go in the literature survey? Version one needs at least 3. The pre-proposal draft does not mention a survey.

## Relationships

- Course: CSCI 513 at USC. The course sets the submission requirements. ([[CSCI 513 Project Registration Instructions]])
- Compute: USC CARC cluster, planned for falsification batches. ([[CS513 Project Proposal Draft]], Resources Required)

## Sources

- [[CSCI 513 Project Registration Instructions]]: course guidance on the project registration page.
- [[CS513 Project Proposal Draft]]: the team's brainstorm document, version one of the idea.
- [[Project Idea v2 - Demand Against Capability]]: version two, saved from a conversation.
- [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]: the verbatim design rounds for version two.
- [[CS513 Pre-Proposal Draft - Demand Against Capability]]: the draft one-page pre-proposal for version two.
