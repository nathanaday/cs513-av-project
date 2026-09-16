# Budgeting Compute Resources for Autonomous Vehicle Tasks

A CS513 (USC) course project.

## About

Most autonomous vehicle stacks assume full compute is available at every time step, processing sensor input at a constant, maximum rate. That constant load causes problems: thermal runaway, faster battery degradation, and wasted power on situations that do not need heavy computation. High compute should be reserved for the difficult moments that need it, and scaled back the rest of the time.

This project builds a resource scheduler for a self-driving stack. It switches between a lightweight inference path and a full-power inference path based on how much attention the current driving situation needs.

## Status

Planning stage. The design below is the current plan; no implementation exists yet.

## Approach

The scheduler picks between two paths:

- **Nano path** — smaller models, lower frame rate, for routine driving.
- **Heavy path** — larger models, higher frame rate, for situations that need close attention.

The choice is driven by two inputs:

- **Trip-level planning**, computed once per trip: route, map, weather, and the vehicle's thermal and energy budget.
- **Real-time risk score**, computed continuously from camera input: how demanding the current situation is right now.

We simulate a full self-driving stack in CARLA, or a similar simulator, with camera, LiDAR, and radar sensors. We build the decision-making engine — the scheduler — on top of that simulation.

## Open design questions

Vision-language models (VLMs) and vision-language-action models (VLAs) are appealing for both the risk score and the driving policy, but neither fits cleanly. Using a VLM to compute the risk score defeats the purpose of the scheduler, since the VLM itself is expensive to run continuously. Using a VLM or VLA as the policy makes it hard to switch cleanly between models of different sizes and frame rates. One option: tune a single VLA at execution time — for example, its number of denoising steps or re-querying rate — to throttle its own compute cost, instead of switching between separate models.

## Documentation

- Original brainstorm deck — `CPS-Project-Brainstorm.pptx`
- Background papers — `papers/`
