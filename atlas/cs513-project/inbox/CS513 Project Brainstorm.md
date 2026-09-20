

Define a few capability degradation modes
- weather 
- Sun angle
- Construction or obstruction 

Define a risk/difficulty metric to create the profile and budget 

Define cost of common actions
- left turns
- Creeping around obstructions 
- Changing lanes
- Etc.

Create a planner that can predict the route difficulty up front
- known construction zones
- Weather forecast
- Sun angle modeling 

Create a perception pipeline that can score the difficulty in realtime
- unexpected weather
- Unexpected obstruction

Change the action planning apparatus in real time 

Study of comparisons
- build a few sim test tracks
- Measure exposed risk on:
- quickest path with no planner (naive baseline)
- With planner only no realtime feedback
- Full planner with feedback

Headline involves comparing risk exposure in an average of all simulated scenarios using the three models





---

## Safety Score Concepts


**Violation Concept**
- Basic things the vehicle must never do, e.g. collide, speed, run red lights, etc.
- Instant failure on the test course


**Penalty Concept**
- Things that are not violations but accumulate penalties
- E.g. time spent facing the low sun angle,
- time spent in bad weather
- creeping around stopped vehicles
- changing lanes
- left turns




---

## Driving Models

**(A) Basic Driving Algorithm (tbd)**
- Baseline to show performance without any planning/adaptive behavior
- Avoids obstacles/collisions using basic mechanics
- Tries to optimize getting to destination as fast as possible without committing violations


**(B) Upfront Planning + Basic Driving**
- Adds a model that tries to reduce the penalties over the course of the trip, but with no real-time adaptation or recalculation


**(C) Upfront Planning + RealTime Recalculation + Basic Driving**
- Adds a perception pipeline that reads the current risk penalty accumulated and continuously recomputes the optimal path

>**These are completely fictional numbers but exist just to give us a sense of what needs to be measured and how**



|         | Number of violation/failures (over 50 test tracks) | Weighted ETA score (over 50 test tracks) | Weighted Penalty Points (over 50 test tracks) | Weighted Total Score (over 50 test tracks) |
| ------- | -------------------------------------------------- | ---------------------------------------- | --------------------------------------------- | ------------------------------------------ |
| Stack A | 6                                                  | 95                                       | 75                                            | 60                                         |
| Stack B | 0                                                  | 85                                       | 35                                            | 70                                         |
| Stack C | 0                                                  | 84                                       | 10                                            | 75                                         |
