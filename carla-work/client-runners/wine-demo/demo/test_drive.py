"""Drive one ego vehicle with BasicAgent on a headless CARLA server and print telemetry.

Run from carla-work: scripts/carla-python client-runners/demo/test_drive.py [--ticks N] [--every S]
"""

import argparse
import queue
import random
import sys
import time

import carla
from agents.navigation.basic_agent import BasicAgent

DELTA = 0.05
CONTACT_GAP = 1.0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--ticks", type=int, default=0, help="stop after N ticks; 0 drives until arrival")
    parser.add_argument("--every", type=float, default=1.0, help="simulated seconds between telemetry lines")
    parser.add_argument("--speed", type=float, default=30.0, help="target speed in km/h")
    parser.add_argument("--spawn", type=int, default=0, help="index of the spawn point")
    parser.add_argument("--seed", type=int, default=0, help="seed for the destination choice")
    parser.add_argument("--timeout", type=float, default=60.0, help="client timeout in seconds")
    return parser.parse_args()


def connect(args):
    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout)
    world = client.get_world()
    client_version, server_version = client.get_client_version(), client.get_server_version()
    if client_version != server_version:
        print(f"warning: client {client_version} != server {server_version}", file=sys.stderr)
    return client, world


def watch(world, vehicle, events):
    library = world.get_blueprint_library()
    collision = world.spawn_actor(library.find("sensor.other.collision"), carla.Transform(), attach_to=vehicle)
    invasion = world.spawn_actor(library.find("sensor.other.lane_invasion"), carla.Transform(), attach_to=vehicle)

    def on_collision(event):
        impulse = event.normal_impulse.length()
        events.put(("collision", event.timestamp, event.other_actor.id,
                    f"{event.other_actor.type_id}  impulse {impulse:.0f} N*s"))

    def on_invasion(event):
        markings = ", ".join(sorted({str(m.type) for m in event.crossed_lane_markings}))
        events.put(("lane_invasion", event.timestamp, None, markings))

    collision.listen(on_collision)
    invasion.listen(on_invasion)
    return [collision, invasion]


def route_left(agent, location):
    points = [location] + [waypoint.transform.location for waypoint, _ in agent.get_local_planner().get_plan()]
    return sum(a.distance(b) for a, b in zip(points, points[1:]))


def drive(args, world, vehicle, start, destination, events, stats):
    agent = BasicAgent(vehicle, target_speed=args.speed)
    agent.set_destination(destination.location)
    print(f"ego {vehicle.type_id} id={vehicle.id}  spawn {args.spawn}  "
          f"route {route_left(agent, start.location):.0f} m")
    print(f"{'sim_s':>7} {'km/h':>6} {'x':>8} {'y':>8} {'thr':>5} {'brk':>5} {'steer':>6} {'to_go_m':>8}")

    last = vehicle.get_location()
    contacts = {}
    next_print = 0.0
    while args.ticks == 0 or stats["ticks"] < args.ticks:
        if agent.done():
            stats["arrived"] = True
            break
        vehicle.apply_control(agent.run_step())
        world.tick()
        stats["ticks"] += 1
        stats["sim_s"] = world.get_snapshot().timestamp.elapsed_seconds - stats["t0"]

        location = vehicle.get_location()
        stats["distance_m"] += location.distance(last)
        last = location

        while not events.empty():
            kind, timestamp, other, detail = events.get()
            sim_s = timestamp - stats["t0"]
            if kind == "collision":
                # The sensor fires on every tick of a contact; report a contact once,
                # and again only after a second without touching that actor.
                previous, contacts[other] = contacts.get(other), sim_s
                if previous is not None and sim_s - previous <= CONTACT_GAP:
                    continue
            stats[kind] += 1
            print(f"{sim_s:7.2f} EVENT {kind}: {detail}")

        if stats["sim_s"] + 1e-9 >= next_print:
            control = vehicle.get_control()
            speed = 3.6 * vehicle.get_velocity().length()
            to_go = route_left(agent, location)
            print(f"{stats['sim_s']:7.2f} {speed:6.1f} {location.x:8.1f} {location.y:8.1f} "
                  f"{control.throttle:5.2f} {control.brake:5.2f} {control.steer:6.2f} {to_go:8.1f}")
            next_print += args.every


def main():
    args = parse_args()
    client, world = connect(args)
    original = world.get_settings()
    actors = []
    events = queue.Queue()
    stats = {"ticks": 0, "sim_s": 0.0, "distance_m": 0.0, "collision": 0, "lane_invasion": 0,
             "arrived": False, "t0": 0.0}
    status = 0
    wall_start = time.monotonic()
    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = DELTA
        world.apply_settings(settings)

        spawns = world.get_map().get_spawn_points()
        start = spawns[args.spawn % len(spawns)]
        destination = random.Random(args.seed).choice(
            [s for s in spawns if s.location.distance(start.location) > 100.0] or spawns)
        blueprint = world.get_blueprint_library().find("vehicle.tesla.model3")
        blueprint.set_attribute("role_name", "hero")
        vehicle = world.try_spawn_actor(blueprint, start)
        if vehicle is None:
            raise RuntimeError(f"spawn point {args.spawn} is occupied; try another --spawn")
        actors.append(vehicle)
        actors.extend(watch(world, vehicle, events))
        world.tick()
        stats["t0"] = world.get_snapshot().timestamp.elapsed_seconds

        drive(args, world, vehicle, start, destination, events, stats)
    except KeyboardInterrupt:
        print("interrupted")
        status = 130
    finally:
        for actor in reversed(actors):
            if actor.type_id.startswith("sensor."):
                actor.stop()
        if actors:
            client.apply_batch_sync([carla.command.DestroyActor(a) for a in actors])
        world.apply_settings(original)

    wall = time.monotonic() - wall_start
    print(f"summary  sim {stats['sim_s']:.1f} s  wall {wall:.1f} s  ratio {stats['sim_s'] / wall:.2f}  "
          f"distance {stats['distance_m']:.0f} m  collisions {stats['collision']}  "
          f"lane_invasions {stats['lane_invasion']}  "
          f"{'arrived' if stats['arrived'] else 'stopped'}")
    return status


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        # The carla module raises RuntimeError for timeouts and refused spawns.
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
