# Example: create a world using the world module
from ..pyotter import World, Planner, Driver
from ..pyotter.core import DrivingSafetyReq, WorldHazardLibrary, WorldRoadGraph
from ..pyotter.world import WorldHazardProbability, WorldHazardSpawns





    

def main():
    
    hazards = WorldHazardLibrary()
    
    wrg = WorldRoadGraph.from_template('town10') # or similar
    
    # view the road graph with dimensions (meters)
    # should be a matplot lib (or similar) object that exposes the usual options to view in a window, or save to disc
    World.view_topology(wrg)
    
    # API (getters)
    wrg.get_segments() # returns all navigable road segments
    
    xyz_seg = wrg.get_segment(sid='xyz') # returns the particular segment by id
    
    # assign hazard probabilities by segment
    # I think this should be a list, not dict; I believe we can assign multiple of the same hazard class to the segment? e.g. probability of 1 person vs probability of 10 people
    xyz_seg.assign_hazard_probability([
        hazards.person, 0.03,
    ])
    
    # save the world road graph from this session
    wrg.save('path/to/disc')
    
    # load a world road graph
    wrg = WorldRoadGraph.load('path/to/disc')
    
    # TODO - have not confirmed this design yet: I think the risk planner takes a weight for how much each penalty should be weighed? In short, we just need some way to produce a dumb route with no risk modelling vs. the risk modeled route
    
    # produce a route that does simple point A to point B routing based on ETA/time optimization only
    naive_waypoints = Planner.route('locA', 'locB', wrg, risk_scale=0)
    
    # produce the risk aware route
    opt_waypoints = Planner.route('locA', 'locB', wrg, risk_scale=1)
    
    # TODO - not designed yet: how to produce the actual runtime map of spawned hazards from seed, not just probabilities
    
    runtime_seed = World.generate_seed(wrg, )
    
    pass