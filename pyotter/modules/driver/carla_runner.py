"""Drive a scenario on a CARLA server and record its telemetry. Only this module imports carla.

What each rolled hazard does in the simulator:

- wet_road lowers the car's tire friction.
- low_visibility and the sun's glare shorten how far ahead the driver notices other road users.
- a pedestrian event puts a walker at the roadside at its start time and walks it across the lane.

The weather is also set to match, but that changes only what a camera would see.
"""

from __future__ import annotations

import hashlib
import math
import queue
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable

from ...core.models.world_hazard_library import LOW_VISIBILITY, WET_ROAD
from ...core.models.world_road_graph import WorldRoadGraph
from ...core.utilities.config import CONFIG
from ...core.utilities.sun import facing_factor
from ..world.models.world_hazard_spawns import EventSpawn, SunGlare
from .controller import (
    RouteFollower, SpeedControl, allowed_speed, anticipated, box_gap, lookahead_m, sight_speed, steer_toward,
    walker_too_close,
)
from .models.driving_scenario import DrivingScenario
from .models.driving_scenario_telemetry import NO_GAP_M, DrivingScenarioTelemetry, Outcome, TelemetryEventKind

SERVER = CONFIG.carla
SETTINGS = CONFIG.driver.runner
SUN_GLARE = "sun_glare"


def wait_for_server(host: str = SERVER.host, port: int = SERVER.port,
                    timeout_s: float = SERVER.wait_timeout_s) -> str:
    """Block until a CARLA server answers.

    Returns:
        The server's version.

    Raises:
        RuntimeError: If no server answers within `timeout_s`.
    """
    import carla

    deadline = time.monotonic() + timeout_s
    error = None
    while time.monotonic() < deadline:
        try:
            client = carla.Client(host, port)
            client.set_timeout(SERVER.wait_probe_timeout_s)
            return client.get_server_version()
        except RuntimeError as failure:
            error = failure
            time.sleep(SERVER.wait_retry_s)
    raise RuntimeError(f"no CARLA server at {host}:{port} after {timeout_s:g} s: {error}")


def run_scenario(scenario: DrivingScenario, *, host: str = SERVER.host, port: int = SERVER.port,
                 timeout_s: float = SERVER.drive_timeout_s,
                 log: Callable[[str], None] = print) -> DrivingScenarioTelemetry:
    """Drive a scenario on a running CARLA server.

    The server's settings and weather are restored, and every actor the run
    spawned is removed, whether or not the run succeeds.

    Args:
        scenario: The run to drive.
        host: Where the server is.
        port: The server's port.
        timeout_s: The client's timeout for one call to the server.
        log: Receives one line of progress at a time.

    Returns:
        The telemetry of the run.

    Raises:
        RuntimeError: If the client or server is the wrong CARLA version, the
            server's map is not the scenario's map, or the car cannot be placed.
    """
    import carla

    client = carla.Client(host, port)
    client.set_timeout(timeout_s)
    versions = {"client": client.get_client_version(), "server": client.get_server_version()}
    if set(versions.values()) != {SERVER.version}:
        raise RuntimeError(f"the client and the server must both be CARLA {SERVER.version}, got {versions}")
    world = _world_with_map(client, scenario.graph, log)
    provenance = {"carla_client": versions["client"], "carla_server": versions["server"], "host": host}

    run = _ScenarioRun(carla, client, world, scenario, provenance, log)
    try:
        run.set_up()
        run.drive()
    finally:
        run.clean_up()
    return run.telemetry


def _world_with_map(client, graph: WorldRoadGraph, log: Callable[[str], None]):
    """The server's world, on the graph's map. Loads the map if another is up."""
    world = client.get_world()
    if world.get_map().name.split("/")[-1] != graph.map_name:
        log(f"loading {graph.map_name}")
        world = client.load_world(graph.map_name)
    opendrive = ET.canonicalize(world.get_map().to_opendrive(), strip_text=True)
    if hashlib.sha256(opendrive.encode()).hexdigest() != graph.map_hash:
        raise RuntimeError("the server's map is not the map this scenario's road graph was made from")
    return world


@dataclass
class _CarState:
    x: float
    y: float
    z: float
    yaw_deg: float
    speed_mps: float


@dataclass
class _Walker:
    actor: object
    control: object
    end_s: float
    detail: dict


class _Walkers:
    """The pedestrians of a run: each rolled event becomes a walker crossing the lane."""

    def __init__(self, carla, world, graph: WorldRoadGraph, events: tuple[EventSpawn, ...],
                 telemetry: DrivingScenarioTelemetry):
        self.carla = carla
        self.world = world
        self.graph = graph
        self.telemetry = telemetry
        self.pending = list(events)
        self.walking: list[_Walker] = []
        self.attempts = 0
        blueprints = world.get_blueprint_library().filter("walker.pedestrian.*")
        self.blueprints = sorted(blueprints, key=lambda blueprint: blueprint.id)

    def update(self, now_s: float) -> None:
        """Start the events that are due, keep the walkers walking, and remove those that have crossed."""
        while self.pending and self.pending[0].start_s <= now_s:
            self._start(self.pending.pop(0), now_s)
        for walker in list(self.walking):
            if now_s >= walker.end_s:
                walker.actor.destroy()
                self.walking.remove(walker)
                self.telemetry.add_event(now_s, TelemetryEventKind.HAZARD_ENDED, **walker.detail)
            else:
                walker.actor.apply_control(walker.control)

    def _start(self, event: EventSpawn, now_s: float) -> None:
        """Place a walker to the right of the lane, facing across it, and set it walking."""
        carla = self.carla
        settings = SETTINGS.walker
        segment = self.graph.get_segment(event.position.segment_id)
        x, y, z = segment.point_at(event.position.offset_m)
        heading = math.radians(segment.heading_at(event.position.offset_m))
        right_x = -math.sin(heading)
        right_y = math.cos(heading)
        location = carla.Location(
            x + right_x * settings.start_off_m,
            y + right_y * settings.start_off_m,
            z + settings.spawn_lift_m,
        )
        place = carla.Transform(location, carla.Rotation(yaw=math.degrees(heading) - 90.0))
        blueprint = self.blueprints[self.attempts % len(self.blueprints)]
        self.attempts += 1
        actor = self.world.try_spawn_actor(blueprint, place)
        detail = {
            "hazard_id": event.hazard_id,
            "segment_id": segment.id,
            "offset_m": round(event.position.offset_m, 2),
        }
        if actor is None:
            self.telemetry.add_event(now_s, TelemetryEventKind.HAZARD_BLOCKED, **detail)
            return
        self.telemetry.add_event(now_s, TelemetryEventKind.HAZARD_STARTED, **detail)
        control = carla.WalkerControl(direction=carla.Vector3D(-right_x, -right_y, 0.0), speed=settings.speed_mps)
        end_s = now_s + settings.walk_m / settings.speed_mps
        self.walking.append(_Walker(actor, control, end_s, detail))

    def circles(self) -> list[tuple[float, float, float]]:
        """Each walker now, as (x, y, radius)."""
        circles = []
        for walker in self.walking:
            location = walker.actor.get_location()
            circles.append((location.x, location.y, SETTINGS.walker.radius_m))
        return circles

    def motions(self) -> list[tuple[float, float, float, float, float]]:
        """Each walker now, as (x, y, radius, vx, vy). A walker keeps walking straight at its set speed."""
        motions = []
        for walker in self.walking:
            location = walker.actor.get_location()
            direction, speed = walker.control.direction, walker.control.speed
            motions.append((location.x, location.y, SETTINGS.walker.radius_m, direction.x * speed, direction.y * speed))
        return motions

    def actor_ids(self) -> list[int]:
        return [walker.actor.id for walker in self.walking]


class _ScenarioRun:
    """One scenario on one server: set up, drive, clean up."""

    def __init__(self, carla, client, world, scenario: DrivingScenario, provenance: dict[str, str],
                 log: Callable[[str], None]):
        self.carla = carla
        self.client = client
        self.world = world
        self.scenario = scenario
        self.log = log
        self.original_settings = world.get_settings()
        self.original_weather = world.get_weather()
        self.actors = []
        self.collisions = queue.Queue()
        self.last_contact_s: dict[int, float] = {}

        spawns = scenario.spawns
        self.wet = spawns.condition_severity(WET_ROAD)
        self.fog = spawns.condition_severity(LOW_VISIBILITY)
        self.grip = 1.0 - SETTINGS.wet_friction_loss * self.wet
        self.telemetry = DrivingScenarioTelemetry(
            scenario_name=scenario.name,
            graph_id=scenario.graph.graph_id,
            map_name=scenario.graph.map_name,
            seed=spawns.seed,
            route_mode=scenario.route.mode.value,
            route_risk_scale=scenario.route.risk_scale,
            driver=scenario.driver,
            delta_s=scenario.delta_s,
            conditions={
                WET_ROAD: self.wet,
                LOW_VISIBILITY: self.fog,
                SUN_GLARE: spawns.sun.strength if spawns.sun else 0.0,
            },
            provenance=provenance,
            scenario_fingerprint=scenario.fingerprint,
        )
        self.follower = RouteFollower(scenario.graph, scenario.route)
        self.speed_control = SpeedControl(scenario.driver, self.grip)
        self.walkers = _Walkers(carla, world, scenario.graph, spawns.events, self.telemetry)

    def set_up(self) -> None:
        """Fix the tick, set the weather, and place the car with its collision sensor."""
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = self.scenario.delta_s
        self.world.apply_settings(settings)
        self.world.set_weather(_weather(self.world.get_weather(), self.wet, self.fog, self.scenario.spawns.sun))
        self._spawn_car()
        self._attach_collision_sensor()
        self._apply_wet_road()
        extent = self.ego.bounding_box.extent
        self.half_length = extent.x
        self.half_width = extent.y
        self.wheelbase_m = SETTINGS.wheelbase_per_half_length * self.half_length

    def _spawn_car(self) -> None:
        blueprint = self.world.get_blueprint_library().find(self.scenario.driver.vehicle_blueprint)
        blueprint.set_attribute("role_name", "hero")
        self.ego = self.world.try_spawn_actor(blueprint, self._start_transform())
        if self.ego is None:
            raise RuntimeError("the route's starting point is occupied")
        self.actors.append(self.ego)

    def _start_transform(self):
        """The CARLA transform of the route's first point, on its own lane, lifted clear of the road."""
        carla_map = self.world.get_map()
        step = self.scenario.route.steps[0]
        segment = self.scenario.graph.get_segment(step.segment_id)
        s = segment.s_at(step.start_offset_m)
        waypoint = carla_map.get_waypoint_xodr(segment.road_id, segment.lane_id, s)
        if waypoint is None:
            # An s at the very end of a lane can round just past the road; move a millimeter inward.
            middle = segment.s_at(segment.length_m / 2.0)
            inward = s + math.copysign(0.001, middle - s)
            waypoint = carla_map.get_waypoint_xodr(segment.road_id, segment.lane_id, inward)
        if waypoint is None:
            raise RuntimeError(f"cannot find the route's start on {segment.id} in the server's map")
        location = waypoint.transform.location
        lifted = self.carla.Location(location.x, location.y, location.z + SETTINGS.spawn_lift_m)
        return self.carla.Transform(lifted, waypoint.transform.rotation)

    def _attach_collision_sensor(self) -> None:
        blueprint = self.world.get_blueprint_library().find("sensor.other.collision")
        sensor = self.world.spawn_actor(blueprint, self.carla.Transform(), attach_to=self.ego)
        self.actors.append(sensor)

        def record(event) -> None:
            other = event.other_actor
            self.collisions.put((event.timestamp, other.id, other.type_id, event.normal_impulse.length()))

        sensor.listen(record)

    def _apply_wet_road(self) -> None:
        physics = self.ego.get_physics_control()
        wheels = physics.wheels
        self.max_steer_deg = wheels[0].max_steer_angle
        for wheel in wheels:
            wheel.tire_friction *= self.grip
        physics.wheels = wheels
        self.ego.apply_physics_control(physics)

    def drive(self) -> None:
        """Tick the simulation until the car arrives or the scenario's time runs out."""
        carla = self.carla
        # The car is placed just above the road; hold it still until it has landed before the clock starts.
        for _ in range(SETTINGS.settle_ticks):
            self.ego.apply_control(carla.VehicleControl(brake=1.0))
            self.world.tick()
        self.start_s = self._server_time_s()
        self.progress_m = 0.0
        self.last_speed_mps = 0.0
        self.next_report_s = 0.0
        self.deceleration_mps2 = self.scenario.driver.planned_deceleration(self.wet)
        route = self.scenario.route
        self.log(f"driving {self.follower.length_m:.0f} m, {route.mode} route, seed {self.scenario.spawns.seed}, "
                 f"wet road {self.wet:.2f}, low visibility {self.fog:.2f}, {len(self.walkers.pending)} events rolled")

        while True:
            now_s = self._server_time_s() - self.start_s
            throttle, brake, steer, remaining_m = self._step(now_s)
            if remaining_m <= CONFIG.driver.controller.arrival_m:
                self.telemetry.outcome = Outcome.ARRIVED
                self.telemetry.add_event(now_s, TelemetryEventKind.ARRIVED)
                break
            if now_s >= self.scenario.duration_s:
                self.telemetry.outcome = Outcome.TIMED_OUT
                break
            self.ego.apply_control(carla.VehicleControl(throttle=throttle, steer=steer, brake=brake))
            self.world.tick()
        collisions = len(self.telemetry.events_of(TelemetryEventKind.COLLISION))
        self.log(f"{self.telemetry.outcome} after {self.telemetry.duration_s:.1f} s and "
                 f"{self.telemetry.distance_m:.0f} m, {collisions} collisions")

    def _server_time_s(self) -> float:
        return self.world.get_snapshot().timestamp.elapsed_seconds

    def _step(self, now_s: float) -> tuple[float, float, float, float]:
        """Observe the world, decide the controls, and record one sample.

        Returns:
            Throttle, brake, steer, and the meters left to the destination.
        """
        driver = self.scenario.driver
        sun = self.scenario.spawns.sun
        self.walkers.update(now_s)
        car = self._car_state()
        self.progress_m = self.follower.locate(car.x, car.y, self.progress_m)
        target_mps, limit_mps, _ = self.follower.plan_at(self.progress_m)
        planned_mps = target_mps
        remaining_m = self.follower.length_m - self.progress_m

        others = self.walkers.circles()
        gap_m = NO_GAP_M
        for other in others:
            gap_m = min(gap_m, box_gap(car.x, car.y, car.yaw_deg, self.half_length, self.half_width, *other))
        glare = sun.strength * facing_factor(car.yaw_deg, sun.azimuth_deg) if sun else 0.0
        reach_m = driver.detection_range(min(1.0, self.fog + glare))
        ahead_m = self.follower.gap_ahead(self.progress_m, others, reach_m)
        # Drive no faster than the car can stop for a road user that appears at the edge of its sight.
        if driver.drive_within_sight:
            target_mps = min(target_mps, sight_speed(reach_m, self.half_length, driver.safety.min_gap_m,
                                                     self.deceleration_mps2))

        # Pedestrians the driver can see, and where they will walk over the next few seconds.
        # Only the driving uses this; the recorded gap ahead stays the road user in the path now.
        motions = self.walkers.motions()
        seen = [motion for motion in motions if math.hypot(motion[0] - car.x, motion[1] - car.y) <= reach_m]
        coming = anticipated(seen, driver.anticipation_s, SETTINGS.anticipation_step_s)
        coming_m = self.follower.gap_ahead(self.progress_m, coming, reach_m)
        nearest_m = min((gap for gap in (ahead_m, coming_m) if gap is not None), default=None)

        # Stop for the destination, or short of a road user in the path or about to enter it, whichever is nearer.
        room_m = remaining_m
        blocked_m = None
        if nearest_m is not None:
            blocked_m = nearest_m - self.half_length - driver.safety.min_gap_m - SETTINGS.stop_margin_m
            room_m = min(room_m, blocked_m)
        # A walker at, or about to come within, the minimum gap of the car's body from any side:
        # stop as hard as the braking limit allows, and drive on once it has moved away.
        if walker_too_close((car.x, car.y, car.yaw_deg), self.half_length, self.half_width, motions,
                            SETTINGS.walker_lookahead_s, driver.safety.min_gap_m):
            room_m, blocked_m = 0.0, 0.0
        wanted_mps = allowed_speed(target_mps, room_m, self.deceleration_mps2)
        measured_mps2 = None
        if len(self.telemetry):
            measured_mps2 = (car.speed_mps - self.last_speed_mps) / self.scenario.delta_s
        throttle, brake = self.speed_control.command(car.speed_mps, wanted_mps, self.scenario.delta_s, blocked_m,
                                                     measured_mps2)
        aim = self.follower.point_at(self.progress_m + lookahead_m(car.speed_mps))
        steer = steer_toward(car.x, car.y, car.yaw_deg, aim, self.wheelbase_m, self.max_steer_deg)

        acceleration = 0.0 if measured_mps2 is None else measured_mps2
        self.telemetry.add_sample(
            time_s=now_s,
            x=car.x,
            y=car.y,
            z=car.z,
            yaw_deg=car.yaw_deg,
            speed_mps=car.speed_mps,
            acceleration_mps2=acceleration,
            target_speed_mps=planned_mps,
            speed_limit_mps=limit_mps,
            allowed_speed_mps=wanted_mps,
            throttle=throttle,
            brake=brake,
            steer=steer,
            progress_m=self.progress_m,
            remaining_m=remaining_m,
            gap_m=gap_m,
            gap_ahead_m=NO_GAP_M if ahead_m is None else ahead_m,
            detection_range_m=reach_m,
            collision=1.0 if self._record_collisions() else 0.0,
        )
        self.last_speed_mps = car.speed_mps
        if now_s >= self.next_report_s:
            shown_gap = "-" if gap_m == NO_GAP_M else f"{gap_m:.1f}"
            self.log(f"{now_s:7.2f} s  {self.progress_m:6.1f} of {self.follower.length_m:.0f} m  "
                     f"{car.speed_mps * 3.6:5.1f} km/h  gap {shown_gap}")
            self.next_report_s += SETTINGS.report_every_s
        return throttle, brake, steer, remaining_m

    def _car_state(self) -> _CarState:
        transform = self.ego.get_transform()
        velocity = self.ego.get_velocity()
        yaw = math.radians(transform.rotation.yaw)
        # Speed along the heading, so that rolling backward reads as negative.
        speed = velocity.x * math.cos(yaw) + velocity.y * math.sin(yaw)
        location = transform.location
        return _CarState(location.x, location.y, location.z, transform.rotation.yaw, speed)

    def _record_collisions(self) -> bool:
        """Empty the sensor's queue into telemetry events. Returns whether there was any contact.

        Contacts with the same actor in quick succession count as one collision.
        """
        any_contact = False
        while not self.collisions.empty():
            stamp, other_id, other_type, impulse = self.collisions.get()
            any_contact = True
            when_s = stamp - self.start_s
            if stamp - self.last_contact_s.get(other_id, -math.inf) > SETTINGS.contact_gap_s:
                self.telemetry.add_event(when_s, TelemetryEventKind.COLLISION, other=other_type,
                                         impulse=round(impulse, 1))
                self.log(f"{when_s:7.2f} s  collision with {other_type}")
            self.last_contact_s[other_id] = stamp
        return any_contact

    def clean_up(self) -> None:
        """Undo every change to the server, even when one step fails."""
        carla = self.carla
        steps = [actor.stop for actor in self.actors if actor.type_id.startswith("sensor.")]
        ids = self.walkers.actor_ids() + [actor.id for actor in reversed(self.actors)]
        if ids:
            steps.append(lambda: self.client.apply_batch_sync([carla.command.DestroyActor(i) for i in ids]))
        steps.append(lambda: self.world.set_weather(self.original_weather))
        steps.append(lambda: self.world.apply_settings(self.original_settings))
        for step in steps:
            try:
                step()
            except Exception as error:
                self.log(f"clean-up step failed: {error!r}")


def _weather(weather, wet: float, fog: float, sun: SunGlare | None):
    """Set a CARLA weather to match the run's conditions."""
    percent = SETTINGS.weather
    values = {
        "wetness": percent.wetness * wet,
        "precipitation_deposits": percent.precipitation_deposits * wet,
        "precipitation": percent.precipitation * fog,
        "fog_density": percent.fog_density * fog,
        "cloudiness": percent.clear_cloudiness + percent.fog_cloudiness * fog,
    }
    if sun is not None:
        values["sun_altitude_angle"] = sun.altitude_deg
        values["sun_azimuth_angle"] = sun.azimuth_deg
    for name, value in values.items():
        if hasattr(weather, name):
            setattr(weather, name, value)
    return weather
