# Demand Against Capability: Risk-Budgeted Route Planning and Adaptive Behavior for Autonomous Driving

## Cluster

C4 Autonomous Driving 

## Team Members

Nathan Aday, Illy Hoang, Yonsoo Kim, Rachel Lin, Tomohiko Uemura, Jeslyn Yang

## Abstract

This project proposes a risk-aware autonomous driving system that sets its caution from the difficulty of the road and its own current capability. A route planner predicts the risk of each route from known factors such as sun glare, forecast weather, and unprotected left turns, and selects a route within a risk budget. An adaptive driver then re-plans and changes its driving profile in real time when conditions degrade unexpectedly. We will compare three systems in the CARLA simulator: basic driving, upfront risk-aware planning, and planning with real-time adaptation. Hard violations, such as collisions and running red lights, fail the test. We evaluate the remaining runs on travel time and on measured risk events, such as near-collisions and hard braking. The goal is to determine whether adaptive planning achieves the safety of consistently cautious driving at a lower cost in travel time.

## Task Breakdown

1. Install CARLA 0.9.16 on all machines. Pin environments so runs reproduce across machines. Get the baseline driver (CARLA `BehaviorAgent`) driving a fixed route. Build the evaluator that logs violations, risk events, and travel time. 
2. Build the sensor degradation model, which reduces what the driver detects in rain, fog, and sun glare. Confirm that degraded conditions raise the risk event rate of the basic driving system.
3. Build the test tracks and scenarios. Measure the cost of each action (unprotected left turn, lane change, passing a stopped vehicle) and the multiplier of each condition. Use calibration tracks that are separate from the test tracks.
4. Build the route planner. It predicts route risk from sun angle, forecast weather, and known construction zones, and selects the quickest route within the risk budget.
5. Build the real-time adaptation. Estimate current conditions, switch the driving profile, and re-plan the route. Add hysteresis so the profile does not oscillate. Handle edge cases such as an obstruction that appears during a maneuver.
6. Implement online monitors and run the falsification campaign. Report counterexamples before and after fixes, plus scenario coverage. Run the final paired comparison, and produce the statistics, figures, and side-by-side demo dashboard.

## Schedule

| Dates | Milestones |
| :---- | :---- |
| Sep 21 | Project pitch due |
| Sep 22 – Oct 4 | CARLA tested on all machines; specs, metrics, and risk events defined; basic driving system and evaluator running; sensor model go or no-go test complete |
| Oct 5 – Oct 18 | Test tracks built; action costs and condition multipliers calibrated; route planner working |
| Oct 19 – Nov 1 | Real-time adaptation running end to end; basic and always-cautious baselines measured; check-in demo (date TBA) |
| Nov 2 – Nov 15 | Falsification campaign; counterexamples fixed; planner and thresholds refined |
| Nov 16 – Nov 29 | Final runs, figures, demo dashboard, video |
| Nov 30 / Dec 1 | 5-min video uploaded / demo day |
| Dec 10 | 15-page final report due |
