"""Drive the ego with BasicAgent among background traffic and record the run with runlog.

Run from carla-work:
  scripts/carla-python client-runners/demo/test_data_capture.py [--vehicles N] [--walkers M] [--log PATH]
Open the run with scripts/carla-replay.
"""

import argparse
import datetime
import os
import queue
import random
import sys
import time

import carla
from agents.navigation.basic_agent import BasicAgent

from runlog import RunLog

DELTA = 0.05
CONTACT_GAP = 1.0
RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "runs")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--tm-port", type=int, default=8000, help="Traffic Manager port")
    parser.add_argument("--ticks", type=int, default=0, help="stop after N ticks; 0 drives until arrival")
    parser.add_argument("--every", type=float, default=5.0, help="simulated seconds between telemetry lines")
    parser.add_argument("--speed", type=float, default=30.0, help="target speed in km/h")
    parser.add_argument("--spawn", type=int, default=0, help="index of the ego's spawn point")
    parser.add_argument("--seed", type=int, default=0, help="seed for the destination and the traffic")
    parser.add_argument("--vehicles", type=int, default=30, help="background vehicles under Traffic Manager")
    parser.add_argument("--walkers", type=int, default=30, help="pedestrians with the walker AI")
    parser.add_argument("--log", default=None, help="run file to write (default: runs/<UTC time>.jsonl.gz)")
    parser.add_argument("--no-log", action="store_true", help="record nothing, to compare wall time")
    parser.add_argument("--timeout", type=float, default=60.0, help="client timeout in seconds")
    return parser.parse_args()


def run_path(args):
    if args.log:
        return args.log
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return os.path.normpath(os.path.join(RUNS, f"{stamp}.jsonl.gz"))


def watch(world, vehicle, events):
    library = world.get_blueprint_library()
    collision = world.spawn_actor(library.find("sensor.other.collision"), carla.Transform(), attach_to=vehicle)
    invasion = world.spawn_actor(library.find("sensor.other.lane_invasion"), carla.Transform(), attach_to=vehicle)

    def on_collision(event):
        events.put(("collision", event.timestamp, event.other_actor.id, {
            "other_id": event.other_actor.id, "other_type": event.other_actor.type_id,
            "impulse": round(event.normal_impulse.length(), 1)}))

    def on_invasion(event):
        events.put(("lane_invasion", event.timestamp, None, {
            "markings": sorted({str(m.type) for m in event.crossed_lane_markings})}))

    collision.listen(on_collision)
    invasion.listen(on_invasion)
    return [collision, invasion]


def spawn_vehicles(client, world, tm, count, spawns, rng):
    library = world.get_blueprint_library().filter("vehicle.*")
    batch = []
    for spawn in spawns[:count]:
        blueprint = rng.choice(library)
        blueprint.set_attribute("role_name", "background")
        batch.append(carla.command.SpawnActor(blueprint, spawn)
                     .then(carla.command.SetAutopilot(carla.command.FutureActor, True, tm.get_port())))
    return [r.actor_id for r in client.apply_batch_sync(batch, True) if not r.error]


def spawn_walkers(world, count, rng):
    library = world.get_blueprint_library()
    walkers = []
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
    controllers = [world.spawn_actor(controller, carla.Transform(), attach_to=w) for w in walkers]
    world.tick()
    for c in controllers:
        c.start()
        c.go_to_location(world.get_random_location_from_navigation())
        c.set_max_speed(1.0 + rng.random())
    return walkers, controllers


def drive(args, world, vehicle, destination, events, stats, log):
    agent = BasicAgent(vehicle, target_speed=args.speed)
    agent.set_destination(destination.location)
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


def main():
    args = parse_args()
    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout)
    world = client.get_world()
    original = world.get_settings()
    rng = random.Random(args.seed)
    tm = None
    log = None
    ego_actors, vehicles, walkers, controllers = [], [], [], []
    events = queue.Queue()
    stats = {"ticks": 0, "sim_s": 0.0, "distance_m": 0.0, "collision": 0, "lane_invasion": 0,
             "arrived": False, "t0": 0.0}
    status, reason = 0, "stopped"
    wall_start = time.monotonic()
    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = DELTA
        world.apply_settings(settings)
        tm = client.get_trafficmanager(args.tm_port)
        tm.set_synchronous_mode(True)
        tm.set_random_device_seed(args.seed)
        world.set_pedestrians_seed(args.seed)

        spawns = world.get_map().get_spawn_points()
        start = spawns[args.spawn % len(spawns)]
        destination = random.Random(args.seed).choice(
            [s for s in spawns if s.location.distance(start.location) > 100.0] or spawns)
        blueprint = world.get_blueprint_library().find("vehicle.tesla.model3")
        blueprint.set_attribute("role_name", "hero")
        ego = world.try_spawn_actor(blueprint, start)
        if ego is None:
            raise RuntimeError(f"spawn point {args.spawn} is occupied; try another --spawn")
        ego_actors.append(ego)
        ego_actors.extend(watch(world, ego, events))

        others = [s for s in spawns if s.location.distance(start.location) > 10.0]
        rng.shuffle(others)
        vehicles = spawn_vehicles(client, world, tm, args.vehicles, others, rng)
        walkers, controllers = spawn_walkers(world, args.walkers, rng)
        world.tick()
        stats["t0"] = world.get_snapshot().timestamp.elapsed_seconds
        print(f"ego {ego.type_id} id={ego.id}  spawn {args.spawn}  "
              f"vehicles {len(vehicles)}  walkers {len(walkers)}")

        if not args.no_log:
            log = RunLog(run_path(args), client, world, ego=ego, argv=sys.argv)
            print(f"recording to {log.path}")
        drive(args, world, ego, destination, events, stats, log)
        reason = "arrived" if stats["arrived"] else "stopped"
    except KeyboardInterrupt:
        print("interrupted")
        status, reason = 130, "interrupted"
    except Exception:
        reason = "error"
        raise
    finally:
        wall = time.monotonic() - wall_start
        if log:
            log.close(reason, wall)
        for c in controllers:
            c.stop()
        for actor in ego_actors:
            if actor.type_id.startswith("sensor."):
                actor.stop()
        ids = [c.id for c in controllers] + [w.id for w in walkers] + vehicles + [a.id for a in reversed(ego_actors)]
        if ids:
            client.apply_batch_sync([carla.command.DestroyActor(i) for i in ids])
        if tm is not None:
            tm.set_synchronous_mode(False)
        world.apply_settings(original)

    print(f"summary  sim {stats['sim_s']:.1f} s  wall {wall:.1f} s  ratio {stats['sim_s'] / wall:.2f}  "
          f"distance {stats['distance_m']:.0f} m  collisions {stats['collision']}  "
          f"lane_invasions {stats['lane_invasion']}  {reason}")
    return status


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        # The carla module raises RuntimeError for timeouts and refused spawns.
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
