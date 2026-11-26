"""Write a set of scenario files that each change one thing, on a new Town10 route.

Every world uses the same route (spawn point 35 to 2) and the same pedestrian
hotspots, so that a difference between two scenarios comes from the one thing
that differs. Each world is written once per driver (naive, cautious, risk-aware).

    python make_scenarios.py            # writes runs/town10-r35to2-*.json.gz
    python make_scenarios.py --list     # only prints what it would write
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyotter import Driver, Planner, World
from pyotter.core import DrivingSafetyReq, WorldHazardLibrary, WorldRoadGraph
from pyotter.modules.driver import DriverModel
from pyotter.modules.planner import PlannerConfig

OUTPUT = Path("runs")
ORIGIN, DESTINATION = 35, 2
DURATION_S = 150.0
MODES = ("naive", "cautious", "risk-aware")
RISK_SCALE = 2
PEDESTRIAN_WEIGHT = 20.0
# Pedestrian chance per second on every lane of the first two junctions the quickest route crosses.
HOTSPOT_PROBABILITIES = (0.03, 0.01)

NOON, LOW_SUN = 12.0, 17.5

# name: (wet road, low visibility, time of day, seeds). A condition is (probability, severity, variability).
WORLDS = {
    "baseline": (None, None, NOON, (1227,)),                          # dry, clear, sun high: no condition
    "icy": ((1.0, 1.0, 0.0), None, NOON, (1227,)),                    # the wettest road the model has
    "bright-sun": (None, None, LOW_SUN, (1227,)),                     # dry and clear, low sun ahead
    "mixed": ((0.9, "high", 0.1), (0.5, "mid", 0.4), LOW_SUN, (7, 42, 1227)),   # drive_scenario.ipynb's mix
}


def build_graph(hazards: WorldHazardLibrary, wet, fog, time_of_day_h: float) -> tuple[WorldRoadGraph, list[int]]:
    """The Town10 graph with this world's forecast, and the junctions given pedestrian hotspots."""
    graph = WorldRoadGraph.from_template("town10")
    quickest = Planner.route(graph.spawn_points[ORIGIN], graph.spawn_points[DESTINATION], graph, mode="naive")
    junctions = []
    for step in quickest.steps:
        junction = graph.get_segment(step.segment_id).junction_id
        if junction is not None and junction not in junctions:
            junctions.append(junction)
    hotspots = junctions[:len(HOTSPOT_PROBABILITIES)]
    for junction, probability in zip(hotspots, HOTSPOT_PROBABILITIES):
        for lane in graph.segments_in_junction(junction):
            lane.assign_hazard_probability([(hazards.pedestrian, probability)])
    for hazard, forecast in ((hazards.wet_road, wet), (hazards.low_visibility, fog)):
        if forecast is not None:
            probability, severity, variability = forecast
            graph.set_condition(hazard, probability=probability, severity=severity, variability=variability)
    graph.set_time_of_day(time_of_day_h)
    return graph, hotspots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the worlds without writing files")
    args = parser.parse_args()

    hazards = WorldHazardLibrary()
    driver = DriverModel(safety=DrivingSafetyReq())
    config = PlannerConfig(weights={"pedestrian": PEDESTRIAN_WEIGHT})
    OUTPUT.mkdir(exist_ok=True)
    written = []
    for world, (wet, fog, time_of_day_h, seeds) in WORLDS.items():
        graph, hotspots = build_graph(hazards, wet, fog, time_of_day_h)
        origin, destination = graph.spawn_points[ORIGIN], graph.spawn_points[DESTINATION]
        for seed in seeds:
            spawns = World.roll_hazards(graph, hazards, seed=seed, duration_s=DURATION_S)
            conditions = ", ".join(f"{c.hazard_id} {c.severity:.2f}" for c in spawns.conditions) or "none"
            sun = f"sun {spawns.sun.strength:.2f}" if spawns.sun else "no sun"
            print(f"{world:10} seed {seed:4}: hotspots {hotspots}, {conditions}, {sun}, "
                  f"{len(spawns.events)} pedestrian starts")
            for mode in MODES:
                route = Planner.route(origin, destination, graph, mode=mode, risk_scale=RISK_SCALE, config=config)
                name = f"town10-r{ORIGIN}to{DESTINATION}-{world}-seed{seed}-{mode}"
                path = OUTPUT / f"{name}.json.gz"
                if not args.list:
                    Driver.scenario(graph, spawns, route, driver=driver, name=name).save(path)
                print(f"    {path}  {route.estimated_time_s:5.1f} s planned")
                written.append(path)
    print(f"{len(written)} scenario files{' (not written)' if args.list else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
