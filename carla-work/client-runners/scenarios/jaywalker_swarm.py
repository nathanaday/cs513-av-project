"""Jaywalker swarm: pedestrians walk back and forth across the road along the ego's route, away from crosswalks."""

import sys

import carla

from scenario import Scenario, run

SPACING = 15.0
CROSSWALK_GAP = 10.0
SPEED = 1.4
PAUSE = 2.0
PROBE = 0.5
MAX_WIDTH = 30.0


def offset(location, direction, meters):
    return carla.Location(x=location.x + direction.x * meters, y=location.y + direction.y * meters,
                          z=location.z + direction.z * meters)


def crossing_length(cmap, curb, direction):
    """Meters from the curb to one meter past the far edge of the road."""
    last = None
    for i in range(1, int(MAX_WIDTH / PROBE)):
        meters = i * PROBE
        on_road = cmap.get_waypoint(offset(curb, direction, meters), project_to_road=False,
                                    lane_type=carla.LaneType.Driving) is not None
        if on_road:
            last = meters
        elif last is not None and meters - last > 2.0:
            break
    return None if last is None else last + 1.0


def curbs(cmap, route):
    """A point on the right sidewalk every SPACING meters of the route, away from junctions
    and crosswalks, with the direction across the road."""
    crosswalks = cmap.get_crosswalks()
    previous = None
    for waypoint in route:
        location = waypoint.transform.location
        if waypoint.is_junction or (previous and location.distance(previous) < SPACING):
            continue
        if any(location.distance(c) < CROSSWALK_GAP for c in crosswalks):
            continue
        previous = location
        edge = waypoint
        while (right := edge.get_right_lane()) is not None and right.lane_type == carla.LaneType.Driving:
            edge = right
        right = edge.transform.get_right_vector()
        across = carla.Vector3D(-right.x, -right.y, 0.0)
        yield offset(edge.transform.location, right, edge.lane_width / 2 + 1.0), across


def setup(context):
    world = context.world
    cmap = world.get_map()
    library = world.get_blueprint_library().filter("walker.pedestrian.*")
    jaywalkers = []
    for curb, across in curbs(cmap, context.route):
        length = crossing_length(cmap, curb, across)
        if length is None:
            continue
        blueprint = context.rng.choice(library)
        blueprint.set_attribute("role_name", "jaywalker")
        walker = world.try_spawn_actor(blueprint, carla.Transform(curb + carla.Location(z=1.0)))
        if walker is None:
            continue
        crossing = length / SPEED
        jaywalkers.append({"walker": walker, "across": across, "crossing": crossing,
                           "period": 2 * (crossing + PAUSE),
                           "delay": context.rng.uniform(0.0, 2 * (crossing + PAUSE)), "control": None})
    context.state["jaywalkers"] = jaywalkers
    context.settings["jaywalkers"] = len(jaywalkers)

    def undo():
        context.client.apply_batch_sync([carla.command.DestroyActor(j["walker"].id) for j in jaywalkers])

    return undo


def step(context, sim_s):
    for j in context.state["jaywalkers"]:
        t = (sim_s - j["delay"]) % j["period"]
        if sim_s < j["delay"]:
            control = "wait"
        elif t < j["crossing"]:
            control = "over"
        elif t < j["crossing"] + PAUSE:
            control = "wait"
        elif t < 2 * j["crossing"] + PAUSE:
            control = "back"
        else:
            control = "wait"
        if control == j["control"]:
            continue
        j["control"] = control
        a = j["across"]
        direction = {"over": a, "back": carla.Vector3D(-a.x, -a.y, 0.0), "wait": a}[control]
        j["walker"].apply_control(carla.WalkerControl(direction, 0.0 if control == "wait" else SPEED))


SCENARIO = Scenario("jaywalker-swarm", __doc__, vehicles=10, walkers=60, ticks=3600, setup=setup, step=step)

if __name__ == "__main__":
    sys.exit(run(SCENARIO))
