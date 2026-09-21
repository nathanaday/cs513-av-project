
> The following is the whatsapp message regarding the [[wiki/sources/Basic Phases|Basic Phases]] document



### Soo Kim

Hihiii sorry my assignment really got me and I find a time to read what was discussed so far. I am still on the page 3 of the pdf and probably not gonna spend time on the section (5) stretch part just yet but here is my understanding so far if you can review:

A risk-aware planner for autonomous vehicle 
•⁠  ⁠Trade time to get the destination safer (slower in areas like construction scene, re-routing to avoid accidents or crowded places → variable includes weather, brightness/darkness of the road (low sunlight), pedestrians, road conditions (wet, icy, etc) 
•⁠  ⁠Deliverable: baseline vs. the planner mounted simulation 

Simulator: CARLA 

Algo: < the penalty function >
•⁠  ⁠penalty score vs. time graph as a eval, visualization preferred 
•⁠  ⁠The scenario runner encompassing the variables above (weather, brightness/darkness of the road (low sunlight), pedestrians, road conditions (wet, icy, etc))
•⁠  ⁠Penalty model design: measures include speed, pedestrian proximity (or essentially object proximity because you don’t want to hit something by a car anyways?), turns (left/right → makes sense because I don’t like to go to a stop sign where I need to make a left turn!), weather exposure 
    - **TODO: find some resources (library for scoring a drive’s safety or open source to fine-tune) and literature for each model 

Building the risk aware planner <so this uses the penalty function and kind of a bigger picture?>
•⁠  ⁠Constructing a planning module that finds the optimal route based on risk exposure and ETA 
•⁠  ⁠World variables could be some sort of statistic data based & similar to how to make ML model 

I think I got confused the distinction between the risk aware planner and the penalty algo and just skim through the rest of the doc, it is not penalty function $\in$ the risk aware planner but the algo (our product) = the penalty algo + risk aware planner?


### Nathan Aday

Thanks for reading and yeah you basically have the right idea. I can try to clarify a few of the confusion points.

The penalty model is a standalone function. It's also helpful to think of it in terms of the individual penalty modes we would support:
- `visibility_penalty(t)` - take a visibility severity score (example, 1-5 scale) and the vehicle speed to produce the penalty points for driving at this speed in this visibility (as an example). Those working on the penalty model would work out the best way to score the penalty points
- `wet_road_penalty(t)` - same idea
- `ped_prox_penalty(t)` - same idea

So the overall penalty you accumulate on the drive is the sum of each penalty mode and maybe weighted as needed. Those working on the penalty model will also handle the weighting, etc.

`total_penalty(t) = w1 * visibility_penalty(t) + w2 * wet_road_penalty(t) + ...`

This also gets into the TODO we both mentioned: if there is a well-known system of scoring a drive quality/safety that's in the same spirit as this, we can import that instead of designing one from scratch. Otherwise, designing one is still a good experience and interesting.

How the planner is different:
- The planner produces waypoints, like lon/lat style directions
- The penalty model only produces integers representing the penalty points, but with no concept of where to go next
- The planner generates its waypoints by using the penalty function on proposed routes