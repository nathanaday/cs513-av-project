---
type: source
title: "CS513 Project Proposal Draft"
status: developing
created: 2026-09-18
updated: 2026-09-18
tags:
  - source
  - project/cs513-project
  - brainstorm
  - superseded
source_type: conversation
author: Yonsoo Kim, Nathan Aday, Tomohiko Uemura, Rachel Lin, Jeslyn Yang, Illy Hoang
date_published: 
url: 
source_id: src-68493c3fa8a0290bfda1
---

# CS513 Project Proposal Draft

Category: group project. This page belongs to [[cs513-project]], not to the course material.

> [!warning] Version one: the group will probably not pursue this idea
> This draft is brainstorm version one, the compute-budget idea. On 2026-09-18 the group lead judged that the compute-budget story does not transfer to real self-driving systems. The current idea is [[Project Idea v2 - Demand Against Capability]]. The schedule, the team list, and much of the tooling in this draft can still apply.

## Summary

A markdown copy of the team's Google Doc, file name `Copy of CS513 Project Proposal Template.md`, captured on 2026-09-18. The team uses the document to brainstorm the pre-proposal. It is a working draft: the title is still the placeholder "Project Title" and the literature survey is empty. Read every statement here as the team's plan on the capture date, not as a decision.

## Key claims

Team: Yonsoo Kim, Nathan Aday, Tomohiko Uemura, Rachel Lin, Jeslyn Yang, Illy Hoang.

Purpose:

- Build a scheduler that switches between two perception paths. The Nano path (small model, low FPS) runs on quiet roads. The Heavy path (large model, high FPS) runs in busy or risky conditions.
- Problem statement: "how fast and how accurately can low-power mode wake the Heavy model when something unexpected happens?"

Task breakdown:

1. Decide on a simulator by early October. Pin the environments so that runs reproduce across machines. Build a "latency-faithful loop" that holds each action back by the inference time of its model.
2. Profile accuracy and latency on simulator frames. Freeze a fixed latency profile for each path.
3. Build the trigger. Measure wake-up latency, missed anomalies, and false alarms. False alarms count because they waste compute. Plot the trade-off curve.
4. Implement and tune thresholds. Define the fallback behavior: when uncertain, go Heavy and slow down. Handle edge cases such as an anomaly that arrives during a switch.
5. Build the logging pipeline and the statistical comparison. Take power readings on one reference machine only. Produce figures and a side-by-side demo dashboard.
6. Implement online monitors and run a falsification campaign. Report counterexamples before and after fixes, and scenario coverage.

Schedule:

| Dates | Milestones |
| :---- | :---- |
| Sep 21 | Project pitch due |
| Sep 22 – Oct 4 | Simulator shortlisted and tested on all machines; specs, metrics, and model candidates defined; simulator decided |
| Oct 5 – Oct 18 | Both perception paths, anomaly trigger, and mode state machine working independently |
| Oct 19 – Nov 1 | End-to-end loop running; always-Heavy baseline measured; check-in demo (date TBA) |
| Nov 2 – Nov 15 | Falsification campaign; counterexamples fixed; scheduler refined |
| Nov 16 – Nov 29 | Final runs, figures, demo dashboard, video |
| Nov 30 / Dec 1 | 5-min video uploaded / demo day |
| Dec 10 | 15-page final report due |

Expected outcome:

- The project succeeds if the scheduler uses less compute and energy than always-Heavy and still reaches the goal with safety no worse than always-Heavy. The safety measures are collisions, minimum time-to-collision (TTC), and specification violations.
- The result must hold in easy scenarios (open highway with a sudden anomaly) and in hard scenarios (dense urban).

Resources, hardware:

- Team laptops, including Apple Silicon MacBooks. The draft recommends 16 GB or more of memory, because each machine runs the simulator and two models at the same time.
- One reference machine. All official latency and power measurements come from it.
- USC CARC cluster access for large batches of falsification runs later in the semester.

Resources, software:

- A cross-platform driving simulator that runs on Apple Silicon, renders camera images, and supports scripted scenarios.
- A deep learning framework that runs on Apple Silicon and on NVIDIA GPUs. The draft gives TensorFlow as an example.
- A pretrained object detector family with small and large variants, for the Nano and Heavy paths.
- A Signal Temporal Logic (STL) monitoring library for runtime specification checks.
- A scenario generation and falsification tool that works with the chosen simulator.
- Compute profiling tools for FLOPs counting and power measurement on each platform.
- A Git repository, a pinned environment manager, and Python for logging and plotting.

Literature survey: empty. The section still holds the template prompt, which asks for at least 3 surveyed papers, reports, blog posts, or websites.

## Notes

- The draft uses a template with the sections Purpose, Task Breakdown, Schedule, Expected Outcome, Resources Required, and Literature Survey. [[CSCI 513 Project Registration Instructions]] asks for a different set: title, cluster, team members, abstract, milestones. See [[cs513-project]] for the gaps.
- One schedule cell ends mid-sentence in the source: "simulator of-choice is decided by". The table above drops the dangling word. The task breakdown gives the deadline as "early October".
- The draft names no simulator, no detector family, no STL library, and no falsification tool. All four are open choices.
