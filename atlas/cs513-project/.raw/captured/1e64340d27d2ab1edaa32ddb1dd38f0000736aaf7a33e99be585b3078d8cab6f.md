# Brainstorm v2: penalty system, eval score, and baseline driver

Date: 2026-09-18

This file records two rounds of a brainstorm between Nathan Aday and Claude. Each round has Nathan's notes, then Claude's response. The text is verbatim, except that the closing question of each response ("do you want me to save this?") is removed.

State: brainstorm. The group has not agreed on this plan. The CARLA details come from memory of the 0.9.x Python API. Check the names against the 0.9.16 install.

---

# Round 1

## Nathan's notes

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

## Claude's response

Yes, this is tangible enough to proceed. It has the three things a pre-proposal needs: a mechanism, an experiment, and a headline result. The three-way comparison is the best part, because it separates the value of the trip planner from the value of the real-time feedback.

Fix four things before you write it up. The first two can sink the project.

### 1. Risk alone is not a valid headline

A planner that lowers risk by driving slowly, or by taking a long route, always wins your comparison. The result is true and says nothing.

- Report **risk and trip time together**. Plot each of the three systems as a point on a risk-against-time chart. The claim becomes: "the full planner gets most of the risk reduction of cautious driving at a fraction of the time cost."
- Add a fourth baseline: **always-conservative**, the most cautious profile on the quickest path. Without it, nobody can tell whether the planner is smart or only slow.

### 2. The planner must not be scored with its own metric

If the planner minimizes your risk score and you then measure that same score, the result is circular. Keep two things apart:

- **Predicted risk**: the score the planner uses. It is a model, and it can be wrong.
- **Measured outcome**: collisions, minimum time-to-collision, hard-braking events, STL violations. The simulator produces these, and the planner never sees them.

This gives you a second result at no extra cost: how well does the predicted risk correlate with the measured outcomes? That is the validation of your difficulty metric.

### 3. Decide how degradation causes harm in the simulator

This is the main feasibility question. In CARLA, rain and sun angle change the camera image, and rain changes tire friction a little. If your agent reads ground-truth object positions from the simulator, weather has no effect on it, and the experiment shows nothing.

You have two options:

- **A. Real perception.** Run a camera detector and let weather degrade it naturally. It is realistic, but it becomes the perception project that you said you do not want.
- **B. A parametric sensor model, which I recommend.** Take ground truth and degrade it with a model: detection range and miss probability as functions of rain, fog, and the sun's angle against the vehicle heading. It needs no training, gives you full control, and keeps the work in planning and control. You can calibrate the model once against a real detector to defend the numbers.

With option B, the real-time difficulty scorer can stay simple. It can estimate the conditions from image statistics or from detector confidence.

### 4. The budget still has no definition

Your notes say "profile and budget" but do not say what the vehicle spends. My proposal is:

- The trip has a **risk budget**. The planner selects the route and the profile for each segment that **minimize trip time, subject to expected risk within the budget**.
- In real time, the vehicle tracks how much risk it has used against the plan. If an unexpected obstruction uses more than planned, the vehicle tightens its profile or reroutes for the rest of the trip.

This makes the budget a real constraint, and it gives the feedback loop a defined task. It also answers the Option A or Option B question from my last message: your notes describe Option B.

### Smaller points

- **Sun angle is your most distinctive item.** Route heading and time of day predict it exactly. A planner that avoids an eastbound road at sunrise is an easy demo to understand. CARLA exposes sun azimuth and altitude.
- **Keep demand and capability apart in the model.** Weather and sun reduce capability. Construction and left turns raise demand. Risk is a function of both. Your list mixes them under "degradation modes".
- **An average across scenarios hides the tail.** Report the distribution and the worst cases also. Run each scenario with the same random seeds for all systems, so the comparison is paired. Your falsification campaign then searches for scenarios where the full planner does worse than a baseline.
- **Action costs need a source.** Left turns and lane changes can get their costs from your own simulator runs: measure the outcome rate for each action under each condition. This is more defensible than numbers you pick by hand, and it is a good task for October.

### Schedule

The draft lists the pitch for Sep 21, which is three days from now. These notes, with fixes 1 and 4 applied, are enough for the one-page registration. Fixes 2 and 3 can go in as design decisions to be made by early October.

---

# Round 2

## Nathan's notes

Yeah i think we do need to get a little more specific about a few of cases we want to optimize for. for the sake of the project, it does not have to be an exhaustive list of all risks to avoid, but just picking a few cases that are easy to measure. So we have this concept of what we want to penalize the vehicle for doing, but we have not solidifed what it is, but we have some ideas.

Then one exercise I like to do is I just invent an eval table to get me thinking about what needs to be measured and how to measure.

### Safety Score Concepts

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

### Driving Models

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

### Budget Factors

Penalties
- Weather
- Rain
- Fog
- Snow
- Strong winds
- High heat (car engine temps)
- Left turns (protected vs. unprotected)
- Traffic density
- Street width
- Speed limit
- Time of day (early morning vs. late at night)
- Sunset (sun shines directly into cameras potentially)
- People nearby (pedestrians or cyclists)
- Hard breaking

Absolute Punishments
- Collisions
- Into other cars
- Into people
- Run a red light

### Request

With this in mind, can we come up with some more specific plans? I'd like to be more specific about:
- how the penality system works
- how the weighted eval score works (as you mentioned it has to optimize on two constraints, not just risk, so ETA and trip time is a good one)
- what our default NPC style driver looks like in CARLA - I'd like to define an off the sehlf model that obeys basic driving rules so we can start there, but it should be pluggable enough that we can slowly add our planning resources to the model

## Claude's response

Your eval table has the right columns. Below is a specific plan for each of the three items. I wrote the CARLA details from memory of the 0.9.x Python API, so check the names against your 0.9.16 install.

### First: sort the factor list

Your "Budget Factors" list mixes four different kinds of thing. The penalty system needs them apart.

| Kind | What it is | From your list | Keep for the project |
| :---- | :---- | :---- | :---- |
| **Condition** | Lowers capability | Rain, fog, snow, wind, heat, time of day, sunset | Sun glare, one visibility scale (rain and fog together), night |
| **Road attribute** | Raises demand, known from the map | Traffic density, street width, speed limit, people nearby | Pedestrian-dense segments. Others optional. |
| **Action** | Raises demand, selected by the planner | Left turns, lane changes, creeping around obstructions | Unprotected left, lane change, pass a stopped vehicle |
| **Outcome** | Measured after the fact | Hard braking, collisions, red lights | All of them, but only in the evaluator |

Drop snow, wind, and heat. CARLA has no snow, wind only moves foliage, and heat has no effect on anything.

### 1. The penalty system

**Formula.** Penalty is demand multiplied by a capability factor:

- Each action has a base cost `d` (demand).
- Each condition set gives a multiplier `m ≥ 1`. Clear daylight is 1.
- An action costs `d × m`. A segment costs `rate × time × m`.

The multiplier is why "unprotected left, facing a low sun" costs more than the two penalties added. That interaction is the demand-against-capability idea in one line.

**Units.** Do not select the weights by hand. Define one penalty point as one **expected risk event**, then measure:

1. Run Stack A on a set of calibration tracks, under each condition.
2. Count risk events for each action type: time-to-collision below 1.5 s, deceleration above 4 m/s², a gap to another actor below 1 m.
3. `d` = events per action in clear conditions. `m` = the rate under the condition divided by the clear rate.

Keep the calibration tracks separate from the 50 test tracks. The planner then predicts on tracks it was never tuned on, and the circularity problem is gone.

**Two CARLA constraints:**

- The degradation must cause harm. Your baseline driver reads ground-truth actor positions, so rain changes nothing for it. Add the sensor model from my last message: it cuts detection range and adds misses as visibility drops or the sun is ahead. Without it every `m` measures as 1.
- CARLA weather is global, not regional. A route cannot avoid a rain zone. Sun glare works natively, because it depends on heading. For weather, either make the forecast temporal ("rain starts at minute 5") or put rain zones in the sensor model only.

### 2. The score

**Three columns stay, one splits:**

| Column | Definition |
| :---- | :---- |
| Violations | Count of failed runs. Collision, red light, stop sign, off-route. Use the criteria classes from CARLA `scenario_runner`; they detect all of these already. |
| ETA score | `100 × T_ref / T_actual`, capped at 100. `T_ref` is the free-flow time of the quickest route on that track. |
| Predicted penalty | What the planner's model expected. A diagnostic, not a result. |
| **Measured risk events** | What the evaluator counted from ground truth. This is the safety result. |

Plot predicted against measured. If they correlate, your difficulty metric is valid. That is a second finding for no extra work.

**Total score.** A failed run scores 0. Otherwise `Total = α × ETA + (1 − α) × Safety`, where `Safety = 100 × max(0, 1 − events / cap)` and the cap comes from the calibration runs. Fix `α = 0.5` before you run anything, then show the ranking for α from 0.2 to 0.8. If C beats B beats A across that range, nobody can say you tuned the weight. This format is close to the CARLA Leaderboard driving score, which helps in a conversation with industry people.

**The budget.** The planner minimizes `time + λ × penalty`. Each λ is equal to one risk budget, so a sweep of λ gives a curve of time against risk. The strongest form of your headline is: curve C is below curve B, and both are below the points for Stack A and an always-cautious driver. Add that always-cautious baseline; it proves the planner is not only slow.

**Statistics.** Collisions are rare, so 50 runs cannot separate 0 from 2. Run each track with 3 to 5 seeds, use the same seeds for every stack, and report risk events with confidence intervals.

### 3. The baseline driver

Use **`BehaviorAgent`** from `PythonAPI/carla/agents/navigation/`. Do not use the Traffic Manager autopilot, which is built for background traffic and is hard to extend.

- It obeys traffic lights, stop signs, and speed limits. It follows and brakes for vehicles and pedestrians.
- It ships three profiles, `Cautious`, `Normal`, and `Aggressive`, in `behavior_types.py`. Each is a small class of numbers: maximum speed, safety time, braking distance, minimum proximity. **This is your profile switch, already built.**
- It routes with `GlobalRoutePlanner`, which runs A* on a `networkx` graph with edge weight equal to length. Each edge carries its maneuver type: left, right, straight, lane change. **This is your trip planner hook.** Replace the weight with `time + λ × penalty`.
- It is weak at unprotected left turns. That is useful, because Stack A must fail somewhere for the comparison to show anything.

**Four interfaces make it pluggable.** Each stack is a different set of implementations around the same driver:

| Interface | Stack A | Stack B | Stack C |
| :---- | :---- | :---- | :---- |
| `Router`: map, origin, destination → route | Quickest path | Minimize time + λ × predicted penalty, from forecast | Same, called again when conditions change |
| `ProfilePolicy`: segment, conditions → driver parameters | `Normal` always | Set for each segment up front | Updated at about 1 Hz from observed conditions |
| `WorldView`: what the driver can see | Degraded by the sensor model | Same | Same |
| `Evaluator`: ground truth → violations, events, time | Same for all | Same | Same |

`WorldView` is a small subclass of `BehaviorAgent` that filters the actor list before the obstacle checks. The `Evaluator` reads the simulator directly and never shares code with the planner.

For Stack C, add hysteresis to the profile switch, for example hold a new profile for at least 5 seconds. Without it the driver can oscillate between profiles at a threshold.

### Order of work

1. Get `BehaviorAgent` driving a fixed route, with the `Evaluator` logging violations, events, and time. This is Stack A, and it needs nothing else.
2. Add the sensor model. Confirm that rain and glare raise the event rate. If they do not, the project has no effect to study, so find that out in week one.
3. Calibrate `d` and `m`.
4. Add the `Router` cost. That is Stack B.
5. Add real-time updates. That is Stack C.

Steps 1 and 2 can run in parallel with two pairs of people. Step 2 is the go or no-go test for the whole idea.
