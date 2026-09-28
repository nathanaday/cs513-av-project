
>[!abstract] Human Writing :)
>This document contains no AI-generated content and is 100% human written.
>However, AI agents are used for collaboration and proofreading.


>[!info] Base Concept
>The base concept provides big-picture clarity on what we are doing:
>- A self driving vehicle may be able to get from A to B rather quickly and without breaking any hard rules, but it has no real sense of risk aversion
>- In reality, skilled human drivers will occasionally sacrifice their ETA for a safer drive when conditions are more difficult
>- We propose a risk-aware planner that trades from ETA budget for added safety, including driving slower in degraded visibility, re-routing to avoid crowded areas, etc.
>- We aim to show the simulation results that compare a risk-aware drive and a naive driver, scored by risk exposure, ETA, and number of collision incidents


# (1) CARLA with Base Driver and Scenario Runner


**Get a basic driver working**
- Baseline driving case
- #TODO add a link to some public CARLA doc or tutorial on a basic driver
- Run a scenario drive and get comfortable measuring data and reporting the drive summary results


# (2) Design the Penalty Model

> In this phase we focus on the penalty function that scores the drive. This phase should develop all software eval modules required to produce the penalty score vs. time graph based on the scenario drive.

### Program the scenario runner
- Get the basic drive to route from A to B on a test world
- Involve a bit of each penalty situation we expect to measure:
	- Weather
	- Low Sun
	- Pedestrians
	- Wet roads

### Create the penalty model
- A system of scoring and penalizing the drive based on events
- Measures speed, pedestrian proximity, turns, weather exposure, etc.
- #TODO I'd like to split this up into the specific modules we would use with definition, like the table below
- #TODO rather than re-invent a scenario scoring situation, is there a well known module, library, or theory that is generally used to score a drive's safety?


| Event                      | Description                                                                                                                                                                              | Variables                                                                                                                         |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Pedestrian Proximity Model | Weighs the aggregated exposure to pedestrian traffic within $P$ meters of the vehicle's ego as a function of speed (higher speed near pedestrians accumulates higher penalty scores)     | Speed (vec)<br><br>IsSurfaceWet (bool) - simpler<br><br>SurfaceWetSeverity (vec) - only if CARLA makes it easy to get these stats |
| Visibility Model           | Weighs the aggregated exposure to poor visibility due to rain, fog, and direct sun with $M$ degrees of the horizon, or at night                                                          | Speed (vec)<br><br>VisibilitySeverity (vec)                                                                                       |
| Wet surface Model          | Weighs the aggregated time spent on wet surfaces as a function of speed, e.g. faster speeds on wet surfaces accumulate higher penalty per second than a slower speed on the same surface |                                                                                                                                   |

*Hold off on these penalty types for the first pass*
- *Left turns, obstruction sneaking, and other single-event risky events*
- It may be harder to prove these are part of the risk assessment and accurately model them in sim, unless there is a 3rd party module that already brings these and similar stats

### Run the test drive with the penalty model
- Tune as necessary, debug, and update penalty model conditions based on new findings



# (3) Build the risk aware planner

> This phase involves constructing a planning module that finds the optimal route based on risk exposure and ETA. This will involve some algorithm fun.


### Accumulate world variables

These are the variables the planner needs to understand. We may have to build this in the simulation layer and make certain assumptions about what statistical data the planner may access.


| Model Item             | Description                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------------- |
| Pedestrian probability | Likelihood`*` that a pedestrian is present in a $M \cdot M$ grid in the sim world                   |
| Weather forecast       | Likelihood`*` that a road surface will be wet, and visibility impaired, due to weather              |
| Sun angle              | Based on the building geometry and time of day, you can deterministically model exposure to low-sun |
`* the algorithm can be simplified, if needed, by assuming the model has some omniscience about the real current state of the world map, not just probability`


### Build the algorithm

This is an optimization problem that using the penalty model (section 2) to determine the quickest route from A to B with minimal risk exposure.

The algorithm generates a set of navigation waypoints.


### Run the vehicle with the planned route

Practice running the test drive using the generated waypoints.


# (4) Build the sim scenarios

> This phase involves building the test set. To keep it simple, we can use the same geometric world (same buildings, foliage, etc.) but vary the conditions (weather, traffic, time of day)

The scenarios should be carefully curated to represent all risk scenarios, including scenarios that are relatively risk-free and scenarios that are frightening as hell.

Once the scenarios are constructed, run each scenario with both the **naive driver** and the **risk aware planner**. 


| Driver                                   | Time to Destination Score | Risk Exposure Score | Overall Score |
| ---------------------------------------- | ------------------------- | ------------------- | ------------- |
| Naive (optimizes only ETA)               | --                        | --                  | --            |
| Risk aware (optimizes both risk and ETA) | --                        | --                  | --            |

# (5) Stretch - Build the realtime risk re-compute

> I added this as a stretch because the study above is complete and interesting, and this adds a layer of complexity. In this phase, we would continuously recompute the optimal route using the algorithm in (3) 

Recomputing the risk-aware waypoints is not necessarily the difficult part, but instead, the difficult part is simulating unexpected scenarios that require re-computation. This requires an addition to the scenarios that we run and eval against.

We would need the algorithm to plan based on probabilities instead of assumed knowledge. That way, the re-compute takes effect when the probability prediction is on an extrema (e.g. more pedestrians present than the planner expected).

Time permitting, we can implement the continuously updating planner model and report in the same eval style:

| Driver                                                             | Time to Destination Score | Risk Exposure Score | Overall Score |
| ------------------------------------------------------------------ | ------------------------- | ------------------- | ------------- |
| Naive (optimizes only ETA)                                         | --                        | --                  | --            |
| Risk aware planner (optimizes both risk and ETA)                   | --                        | --                  | --            |
| Risk aware and continuous re-compute (optimizes both risk and ETA) | --                        | --                  | --            |


