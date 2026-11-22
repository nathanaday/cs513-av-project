# Demand Against Capability

**Risk-Budgeted Route Planning and Adaptive Behavior for Autonomous Driving**

A group project for CSCI 513 (USC), cluster C4 Autonomous Driving.

Team: Nathan Aday, Illy Hoang, Yonsoo Kim, Rachel Lin, Tomohiko Uemura, Jeslyn Yang

## About

A careful human driver does not drive the same way everywhere. They slow down in fog, avoid a hard left turn when the sun is in their eyes, and pick an easier route when the weather is bad. Most simulated driving agents do none of this: they take the quickest route and drive it the same way in all conditions.

This project builds a risk-aware route planner that sets its caution from the difficulty of the road and the vehicle's current capability. The planner predicts the risk of each road segment from known hazards such as pedestrians, wet roads, rain, fog, and low sun. It then picks the route and a speed for each segment that minimize travel time plus weighted risk.

We compare three drivers in the CARLA simulator on the same scenarios: a naive driver that takes the quickest route at the speed limit, an always-cautious driver that drives the same route slowly, and the risk-aware driver. We score each drive on travel time and on outcomes measured from the simulator, such as collisions, near-misses, and hard braking. The goal is to find out whether the risk-aware planner gets close to the safety of the cautious driver at close to the travel time of the naive one.

## Status

Early implementation. CARLA runs headless on the team's Macs ([recipe](carla-work/docs/headless-carla.md)), and the demo scenarios record and replay. The [Planner prototype](carla-work/docs/planner.md) selects routes and speeds from mock hazard probabilities. Its naive, cautious, and risk-aware plans have been driven on the Mac's headless CARLA, with Town10 speed limits verified against the live server ([validation](carla-work/docs/planner-validation.md)). [USC Discovery helpers](carla-work/docs/hpc.md) prepare a separate CARLA 0.9.16 environment and run a server/client pair inside an allocation. Live HPC verification, the World API, Runner's common driver, and measured safety evaluation remain pending.

## Plan

- [Project plan](docs/plan.md): the goal, the drivers, the method, and how the team judges the results.
- [Teams](docs/teams.md): the World, Planner, and Runner teams, what each builds, and the APIs between them.
- [Concepts](docs/concepts.md): the penalty model, the route-and-speed search, hazards in CARLA, and why the evaluation never uses the penalty model.

[Basic Phases](docs/Basic%20Phases.md) is the plan of record. The [pre-proposal](docs/prepreposal/pre-proposal-draft.md) was an early pitch, and its schedule does not apply.

| Date | Milestone |
| :---- | :---- |
| Dec 1 | Project presentations |
| Dec 10 | Final report due |

## Documentation

- [Planner and team interfaces](carla-work/docs/planner.md): offline examples, graph export, experimental penalty model, and Runner handoff.
- [CARLA on USC Discovery](carla-work/docs/hpc.md): allocate a GPU node, prepare CARLA 0.9.16, run and record there, then review locally.
- [Headless CARLA on Apple Silicon](carla-work/docs/headless-carla.md): run the CARLA server with no window, drive a car from Python, and read its telemetry. Start here to set up a team machine.
- [Record and replay a CARLA run](carla-work/docs/replay.md): record a drive among traffic and pedestrians, then watch it in the Rerun viewer. The file format is in [run-format.md](carla-work/docs/run-format.md).
- [Demo driving scenarios](carla-work/docs/scenarios.md): record a drive in heavy rain, low sun, heavy traffic, crowds, a traffic light blackout, among red-light runners or jaywalkers, or on black ice.
- [Reinforcement learning tutorial](carla-work/docs/reinforcement-learning.md): train a DQN agent to steer from the front camera, after the pythonprogramming.net CARLA tutorial, and drive the trained model. Needs the server with rendering.
- [Publish a capture](carla-work/docs/publishing.md): share a recorded run in the public dataset [nadayusc/carla-rerun-scenarios](https://huggingface.co/datasets/nadayusc/carla-rerun-scenarios), where anyone can open it in the Rerun web viewer.
- [Pre-proposal draft](docs/prepreposal/pre-proposal-draft.md), the one-page course submission, written before work began. Also as [LaTeX](docs/prepreposal/pre-proposal-draft.tex) and [PDF](docs/prepreposal/pre-proposal-draft.pdf). The submitted version is [pre-proposal-submission-1.pdf](docs/prepreposal/pre-proposal-submission-1.pdf).
- [Basic Phases](docs/Basic%20Phases.md): the phased plan of record, with a stretch goal. Also as [PDF](docs/Basic%20Phases.pdf).
- [Fair matching](docs/fair-matching/README.md): assign the six members to the World, Planner, and Runner teams from their ranked choices.
- [Registration instructions](docs/CSCI%20513%20Project%20Registration%20Instructions.docx): the course handout for the one-page registration.
- Background papers: [`papers/`](papers/)


External:

- [CARLA](https://github.com/carla-simulator/carla), the driving simulator
- [CARLA on Apple Silicon](https://github.com/nathanaday/carla-mac-os), how the team runs CARLA on M-series Macs
