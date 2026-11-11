"""Run a driving scenario: spawn the ego and background traffic, drive the ego with
BasicAgent, and record the run with runlog.

A scenario file declares a Scenario and runs it:

    import sys
    from scenario import Scenario, run

    SCENARIO = Scenario("heavy-rain", "Heavy rain at noon.", weather={"precipitation": 100.0})

    if __name__ == "__main__":
        sys.exit(run(SCENARIO))

See docs/scenarios.md.
"""

import argparse
import dataclasses
import datetime
import os
import queue
import random
import sys
import time
from typing import Callable, Optional, Union

import carla
from agents.navigation.basic_agent import BasicAgent

from runlog import WEATHER, RunLog

DELTA = 0.05
CONTACT_GAP = 1.0
FOLLOW_BACK, FOLLOW_UP, FOLLOW_PITCH = 8.0, 3.0, -12.0
RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs")


@dataclasses.dataclass
class Scenario:
    """What makes a scenario different. The command line overrides the counts and the limit.

    weather: fields of carla.WeatherParameters over the ClearNoon preset, or a function of
        the ego's start transform that returns them. None leaves the world's weather as it is.
    setup: called after every actor is spawned, with a Context. For each change it makes to
        the world, it registers the undo with context.on_exit before it makes the change.
    step: called after every tick, with the Context and the simulated seconds since the start.
    """
    name: Optional[str]
    description: str
    vehicles: int = 30
    walkers: int = 30
    speed: float = 30.0
    ticks: int = 0
    spawn: int = 0
    seed: int = 0
    weather: Union[dict, Callable, None] = None
    setup: Optional[Callable] = None
    step: Optional[Callable] = None


@dataclasses.dataclass
class Context:
    """What setup and step can use. route is the ego's planned waypoints; state is free
    storage that setup fills and step reads."""
    client: carla.Client
    world: carla.World
    tm: carla.TrafficManager
    ego: carla.Actor
    route: list
    vehicles: list
    walkers: list
    rng: random.Random
    settings: dict
    state: dict = dataclasses.field(default_factory=dict)
    exits: list = dataclasses.field(default_factory=list)

    def on_exit(self, undo):
        """Run undo when the scenario ends, however it ends. The last registered runs first."""
        self.exits.append(undo)


def run_all(steps):
    """Run every clean-up step, even after one fails, then raise the first error."""
    first = None
    for step in steps:
        try:
            step()
        except Exception as error:
            print(f"clean-up step failed: {error!r}", file=sys.stderr)
            first = first or error
    if first is not None:
        raise first


def parse_args(scenario):
    parser = argparse.ArgumentParser(description=scenario.description)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--tm-port", type=int, default=8000, help="Traffic Manager port")
    parser.add_argument("--ticks", type=int, default=scenario.ticks,
                        help=f"stop after N ticks; 0 drives until arrival (default {scenario.ticks})")
    parser.add_argument("--every", type=float, default=5.0, help="simulated seconds between telemetry lines")
    parser.add_argument("--speed", type=float, default=scenario.speed, help="target speed in km/h")
    parser.add_argument("--spawn", type=int, default=scenario.spawn,
                        help=f"index of the ego's spawn point (default {scenario.spawn})")
    parser.add_argument("--seed", type=int, default=scenario.seed,
                        help=f"seed for the destination and the traffic (default {scenario.seed})")
    parser.add_argument("--vehicles", type=int, default=scenario.vehicles,
                        help=f"background vehicles under Traffic Manager (default {scenario.vehicles})")
    parser.add_argument("--walkers", type=int, default=scenario.walkers,
                        help=f"pedestrians with the walker AI (default {scenario.walkers})")
    parser.add_argument("--log", default=None,
                        help="run file to write (default: runs/" + (f"{scenario.name}-" if scenario.name else "")
                        + "<UTC time>.jsonl.gz)")
    parser.add_argument("--no-log", action="store_true", help="record nothing, to compare wall time")
    parser.add_argument("--no-follow", action="store_true",
                        help="leave the spectator free; by default it follows behind the ego")
    parser.add_argument("--timeout", type=float, default=60.0, help="client timeout in seconds")
    return parser.parse_args()


def run_path(scenario, args):
    if args.log:
        return args.log
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{scenario.name}-{stamp}" if scenario.name else stamp
    return os.path.normpath(os.path.join(RUNS, f"{name}.jsonl.gz"))


def make_weather(world, values):
    unknown = set(values) - set(WEATHER)
    if unknown:
        raise ValueError(f"unknown weather fields: {', '.join(sorted(unknown))}")
    preset = carla.WeatherParameters.ClearNoon
    weather = world.get_weather()
    for name in WEATHER:
        if hasattr(weather, name):
            setattr(weather, name, values.get(name, getattr(preset, name)))
    return weather


def watch(world, vehicle, events, actors):
    """Attach the collision and lane invasion sensors, adding each to actors as it spawns."""
    library = world.get_blueprint_library()
    collision = world.spawn_actor(library.find("sensor.other.collision"), carla.Transform(), attach_to=vehicle)
    actors.append(collision)
    invasion = world.spawn_actor(library.find("sensor.other.lane_invasion"), carla.Transform(), attach_to=vehicle)
    actors.append(invasion)

    def on_collision(event):
        events.put(("collision", event.timestamp, event.other_actor.id, {
            "other_id": event.other_actor.id, "other_type": event.other_actor.type_id,
            "impulse": round(event.normal_impulse.length(), 1)}))

    def on_invasion(event):
        events.put(("lane_invasion", event.timestamp, None, {
            "markings": sorted({str(m.type) for m in event.crossed_lane_markings})}))

    collision.listen(on_collision)
    invasion.listen(on_invasion)


def spawn_vehicles(client, world, tm, count, spawns, rng):
    library = world.get_blueprint_library().filter("vehicle.*")
    batch = []
    for spawn in spawns[:count]:
        blueprint = rng.choice(library)
        blueprint.set_attribute("role_name", "background")
        batch.append(carla.command.SpawnActor(blueprint, spawn)
                     .then(carla.command.SetAutopilot(carla.command.FutureActor, True, tm.get_port())))
    return [r.actor_id for r in client.apply_batch_sync(batch, True) if not r.error]


def spawn_walkers(world, count, rng, walkers, controllers):
    """Spawn walkers with the walker AI into the given lists, so the caller can destroy
    them even when a spawn fails partway."""
    library = world.get_blueprint_library()
    for _ in range(count * 2):
        if len(walkers) == count:
            break
        location = world.get_random_location_from_navigation()
        if location is None:
            continue
        walker = world.try_spawn_actor(rng.choice(library.filter("walker.pedestrian.*")),
                                       carla.Transform(location + carla.Location(z=1.0)))
        if walker is not None:
            walkers.append(walker)
    world.tick()
    controller = library.find("controller.ai.walker")
    for w in walkers:
        controllers.append(world.spawn_actor(controller, carla.Transform(), attach_to=w))
    world.tick()
    for c in controllers:
        c.start()
        c.go_to_location(world.get_random_location_from_navigation())
        c.set_max_speed(1.0 + rng.random())


def follow(spectator, vehicle):
    transform = vehicle.get_transform()
    forward = transform.get_forward_vector()
    location = transform.location
    spectator.set_transform(carla.Transform(
        carla.Location(x=location.x - FOLLOW_BACK * forward.x, y=location.y - FOLLOW_BACK * forward.y,
                       z=location.z + FOLLOW_UP),
        carla.Rotation(pitch=FOLLOW_PITCH, yaw=transform.rotation.yaw)))


def drive(args, world, agent, vehicle, events, stats, log, step):
    spectator = None if args.no_follow else world.get_spectator()
    print(f"{'sim_s':>7} {'km/h':>6} {'x':>8} {'y':>8} {'thr':>5} {'brk':>5} {'steer':>6}")

    last = vehicle.get_location()
    contacts = {}
    next_print = 0.0
    while args.ticks == 0 or stats["ticks"] < args.ticks:
        if agent.done():
            stats["arrived"] = True
            break
        vehicle.apply_control(agent.run_step())
        world.tick()
        snapshot = world.get_snapshot()
        if log:
            log.tick(snapshot)
        stats["ticks"] += 1
        stats["sim_s"] = snapshot.timestamp.elapsed_seconds - stats["t0"]
        if step:
            step(stats["sim_s"])
        if spectator:
            follow(spectator, vehicle)

        location = vehicle.get_location()
        stats["distance_m"] += location.distance(last)
        last = location

        while not events.empty():
            kind, timestamp, other, detail = events.get()
            sim_s = timestamp - stats["t0"]
            if kind == "collision":
                # The sensor fires on every tick of a contact; keep a contact once,
                # and again only after a second without touching that actor.
                previous, contacts[other] = contacts.get(other), sim_s
                if previous is not None and sim_s - previous <= CONTACT_GAP:
                    continue
            stats[kind] += 1
            if log:
                log.event(kind, timestamp, **detail)
            print(f"{sim_s:7.2f} EVENT {kind}: {detail}")

        if stats["sim_s"] + 1e-9 >= next_print:
            control = vehicle.get_control()
            speed = 3.6 * vehicle.get_velocity().length()
            print(f"{stats['sim_s']:7.2f} {speed:6.1f} {location.x:8.1f} {location.y:8.1f} "
                  f"{control.throttle:5.2f} {control.brake:5.2f} {control.steer:6.2f}")
            next_print += args.every


def _run(scenario, args):
    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout)
    world = client.get_world()
    original = world.get_settings()
    original_weather = world.get_weather()
    rng = random.Random(args.seed)
    tm = None
    log = None
    context = None
    ego_actors, vehicles, walkers, controllers = [], [], [], []
    events = queue.Queue()
    stats = {"ticks": 0, "sim_s": 0.0, "distance_m": 0.0, "collision": 0, "lane_invasion": 0,
             "arrived": False, "t0": 0.0}
    settings = {"vehicles": args.vehicles, "walkers": args.walkers, "speed": args.speed,
                "ticks": args.ticks, "seed": args.seed, "spawn": args.spawn}
    status, reason = 0, "stopped"
    wall_start = time.monotonic()
    try:
        world_settings = world.get_settings()
        world_settings.synchronous_mode = True
        world_settings.fixed_delta_seconds = DELTA
        world.apply_settings(world_settings)
        tm = client.get_trafficmanager(args.tm_port)
        tm.set_synchronous_mode(True)
        tm.set_random_device_seed(args.seed)
        world.set_pedestrians_seed(args.seed)

        spawns = world.get_map().get_spawn_points()
        start = spawns[args.spawn % len(spawns)]
        destination = random.Random(args.seed).choice(
            [s for s in spawns if s.location.distance(start.location) > 100.0] or spawns)
        if scenario.weather is not None:
            values = scenario.weather(start) if callable(scenario.weather) else scenario.weather
            world.set_weather(make_weather(world, values))

        blueprint = world.get_blueprint_library().find("vehicle.tesla.model3")
        blueprint.set_attribute("role_name", "hero")
        ego = world.try_spawn_actor(blueprint, start)
        if ego is None:
            raise RuntimeError(f"spawn point {args.spawn} is occupied; try another --spawn")
        ego_actors.append(ego)
        watch(world, ego, events, ego_actors)

        others = [s for s in spawns if s.location.distance(start.location) > 10.0]
        rng.shuffle(others)
        vehicles = spawn_vehicles(client, world, tm, args.vehicles, others, rng)
        spawn_walkers(world, args.walkers, rng, walkers, controllers)
        agent = BasicAgent(ego, target_speed=args.speed)
        agent.set_destination(destination.location)
        route = [waypoint for waypoint, _ in agent.get_local_planner().get_plan()]
        context = Context(client, world, tm, ego, route, list(world.get_actors(vehicles)), walkers, rng, settings)
        if scenario.setup is not None:
            returned = scenario.setup(context)
            if returned is not None:
                if callable(returned):
                    context.on_exit(returned)
                raise TypeError(f"{scenario.name}: setup returned a value; register undo steps "
                                "with context.on_exit instead")
        step = (lambda sim_s: scenario.step(context, sim_s)) if scenario.step else None
        world.tick()
        stats["t0"] = world.get_snapshot().timestamp.elapsed_seconds
        if scenario.name:
            print(f"scenario {scenario.name}: {scenario.description}")
        print(f"ego {ego.type_id} id={ego.id}  spawn {args.spawn}  "
              f"vehicles {len(vehicles)}  walkers {len(walkers)}")

        if not args.no_log:
            log = RunLog(run_path(scenario, args), client, world, ego=ego, argv=sys.argv,
                         scenario=scenario.name, settings=settings)
            print(f"recording to {log.path}")
        drive(args, world, agent, ego, events, stats, log, step)
        reason = "arrived" if stats["arrived"] else "stopped"
    except KeyboardInterrupt:
        print("interrupted")
        status, reason = 130, "interrupted"
    except Exception:
        reason = "error"
        raise
    finally:
        wall = time.monotonic() - wall_start
        steps = []
        if log:
            steps.append(lambda: log.close(reason, wall))
        if context is not None:
            steps.extend(reversed(context.exits))
        steps.extend(c.stop for c in controllers)
        steps.extend(a.stop for a in ego_actors if a.type_id.startswith("sensor."))
        ids = [c.id for c in controllers] + [w.id for w in walkers] + vehicles + [a.id for a in reversed(ego_actors)]
        if ids:
            steps.append(lambda: client.apply_batch_sync([carla.command.DestroyActor(i) for i in ids]))
        if tm is not None:
            steps.append(lambda: tm.set_synchronous_mode(False))
        if scenario.weather is not None:
            steps.append(lambda: world.set_weather(original_weather))
        steps.append(lambda: world.apply_settings(original))
        run_all(steps)

    print(f"summary  sim {stats['sim_s']:.1f} s  wall {wall:.1f} s  ratio {stats['sim_s'] / wall:.2f}  "
          f"distance {stats['distance_m']:.0f} m  collisions {stats['collision']}  "
          f"lane_invasions {stats['lane_invasion']}  {reason}")
    return status


def run(scenario):
    """Run a scenario with the command line's options. Returns the exit status."""
    args = parse_args(scenario)
    try:
        return _run(scenario, args)
    except RuntimeError as error:
        # The carla module raises RuntimeError for timeouts and refused spawns.
        print(f"error: {error}", file=sys.stderr)
        return 1
