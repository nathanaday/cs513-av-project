---
type: source
title: "CS513 Pre-Proposal Draft - Demand Against Capability"
status: developing
created: 2026-09-20
updated: 2026-09-20
tags:
  - source
  - project/cs513-project
  - pre-proposal
source_type: document
author: CS513 project team, as named in the draft
date_published: 2026-09-18
url: 
source_id: src-fc28a8e2eaf6b90f0c2f
---

# CS513 Pre-Proposal Draft - Demand Against Capability

Category: group project. This page belongs to [[cs513-project]], not to the course material.

## Summary

The draft of the one-page pre-proposal for version two of the project idea, [[Project Idea v2 - Demand Against Capability]]. Title: "Demand Against Capability: Risk-Budgeted Route Planning and Adaptive Behavior for Autonomous Driving". Cluster: C4 Autonomous Driving. It has the five items that [[CSCI 513 Project Registration Instructions]] asks for, and it adds a task breakdown.

The original stays in the project repository, in `docs/prepreposal/`, as three files: `pre-proposal-draft.md`, `pre-proposal-draft.tex`, and `pre-proposal-draft.pdf`. Only the Markdown file is captured and read here. The LaTeX text has the same content as the Markdown file. The PDF is one page and shows the same text. The Markdown file moved from `docs/` to `docs/prepreposal/` on 2026-09-20 with no change to its text.

Authority: primary. It is the team's own document. It is a draft. No source in the knowledge base says that the group approved it or that anyone submitted it.

## Key claims

### Title, cluster, team

- Cluster: C4 Autonomous Driving. (Cluster section)
- Team: Nathan Aday, Illy Hoang, Yonsoo Kim, Rachel Lin, Tomohiko Uemura, Jeslyn Yang. (Team Members section)

### Abstract

- The system sets its caution from the difficulty of the road and its own current capability. (Abstract)
- A route planner predicts the risk of each route from known factors: sun glare, forecast weather, and unprotected left turns. It selects a route within a risk budget. (Abstract)
- An adaptive driver re-plans and changes its driving profile in real time when conditions degrade unexpectedly. (Abstract)
- Three systems run in the CARLA simulator: basic driving, upfront risk-aware planning, and planning with real-time adaptation. (Abstract)
- Hard violations, such as collisions and running red lights, fail the test. The other runs are scored on travel time and on measured risk events, such as near-collisions and hard braking. (Abstract)
- Goal: to find out whether adaptive planning gives the safety of consistently cautious driving at a lower cost in travel time. (Abstract)

### Task breakdown

1. Install CARLA 0.9.16 on all machines and pin the environments. Run the baseline driver, the CARLA `BehaviorAgent`, on a fixed route. Build the evaluator that logs violations, risk events, and travel time.
2. Build the sensor degradation model for rain, fog, and sun glare. Confirm that degraded conditions raise the risk event rate of the basic driving system.
3. Build the test tracks and scenarios. Measure the cost of each action (unprotected left turn, lane change, passing a stopped vehicle) and the multiplier of each condition. Keep the calibration tracks apart from the test tracks.
4. Build the route planner. It predicts route risk from sun angle, forecast weather, and known construction zones. It selects the quickest route within the risk budget.
5. Build the real-time adaptation: estimate the current conditions, switch the driving profile, and re-plan the route. Add hysteresis so the profile does not oscillate. Handle an obstruction that appears during a maneuver.
6. Implement online monitors and run the falsification campaign. Report counterexamples before and after fixes, and scenario coverage. Run the final paired comparison. Produce the statistics, figures, and a side-by-side demo dashboard.

### Schedule

| Dates | Milestones |
| :---- | :---- |
| Sep 21 | Project pitch due |
| Sep 22 - Oct 4 | CARLA tested on all machines; specs, metrics, and risk events defined; basic driving system and evaluator running; sensor model go or no-go test complete |
| Oct 5 - Oct 18 | Test tracks built; action costs and condition multipliers calibrated; route planner working |
| Oct 19 - Nov 1 | Real-time adaptation running end to end; basic and always-cautious baselines measured; check-in demo (date TBA) |
| Nov 2 - Nov 15 | Falsification campaign; counterexamples fixed; planner and thresholds refined |
| Nov 16 - Nov 29 | Final runs, figures, demo dashboard, video |
| Nov 30 / Dec 1 | 5-minute video uploaded / demo day |
| Dec 10 | 15-page final report due |

## Notes

Synthesis from a comparison with other sources in the knowledge base.

- **Same as the working design.** The three systems, the `BehaviorAgent` baseline, the required sensor model with its go or no-go test, calibration tracks apart from test tracks, action costs and condition multipliers, profile switch with hysteresis, and the always-cautious baseline all come from [[Brainstorm v2 - Penalty, Eval Score, and Baseline Driver Plan]]. The order of the schedule follows the order of work in that source.
- **Budget wording differs.** This draft says the planner "selects the quickest route within the risk budget", which reads as a constraint. The design source has the planner minimize `time + λ × penalty`, where each λ is one risk budget. Both trade time against risk. No source says which the group chose.
- **Falsification stays.** Task 6 keeps the online monitors and the falsification campaign from [[CS513 Project Proposal Draft]]. The design source mentions them only as outcome measures and as a search for scenarios where the full planner does worse than a baseline.
- **Not in the draft.** The score formula (`α`, ETA score, safety score), the risk event thresholds, the number of test tracks and seeds, and the VLM or VLA layer. The abstract also does not name the always-cautious baseline, but the schedule measures it.
- **Course limits.** [[CSCI 513 Project Registration Instructions]] asks for one page and an abstract of 5 to 6 lines. The PDF is one page. The abstract has six sentences and runs to about eight lines in the PDF. The milestones name no lead for each milestone, and the course example does. The task breakdown names no owners.
- **Version one items resolved.** The draft names the cluster (C4) and the simulator (CARLA 0.9.16). [[CS513 Project Proposal Draft]] left both open. The mapping of C4 to the course's cluster list is not checked, because the knowledge base does not hold the cluster list.
- **Unverified.** The statements about CARLA 0.9.16 carry over from the design source. Nobody has checked them against the install.
- **Open.** The draft lists Sep 21 as "Project pitch due", as version one did. No source says whether the pitch and the one-page registration are the same submission.
