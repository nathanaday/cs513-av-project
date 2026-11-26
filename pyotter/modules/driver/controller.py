"""The driver's decisions, as plain geometry and arithmetic with no simulator.

Angles follow CARLA: yaw is in degrees, 0 along +x, turning toward +y, and a
positive steer turns the same way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ...core.models.world_road_graph import WorldRoadGraph
from ...core.utilities.config import CONFIG
from ..planner.models.planner_computed_waypoints import PlannerComputedWaypoints
from .models.driver_model import DriverModel

SETTINGS = CONFIG.driver.controller
KMH_PER_MPS = 3.6


@dataclass(frozen=True)
class RoutePoint:
    """One point of the line to follow, with its distance along the route."""

    x: float
    y: float
    z: float
    along_m: float


@dataclass(frozen=True)
class RouteStretch:
    """The plan for one stretch of the route, up to `end_m` along it."""

    end_m: float
    target_mps: float
    limit_mps: float
    segment_id: str


class RouteFollower:
    """A route as one line to follow, with the planned speed along it."""

    def __init__(self, graph: WorldRoadGraph, route: PlannerComputedWaypoints):
        """Join the route's steps into one line.

        Raises:
            ValueError: If the route has fewer than two distinct points.
        """
        self.points: list[RoutePoint] = []
        self.stretches: list[RouteStretch] = []
        for step in route.steps:
            segment = graph.get_segment(step.segment_id)
            for x, y, z in segment.points_between(step.start_offset_m, step.end_offset_m):
                self._add_point(x, y, z)
            self.stretches.append(RouteStretch(
                end_m=self.points[-1].along_m,
                target_mps=step.target_speed_kmh / KMH_PER_MPS,
                limit_mps=segment.speed_limit_kmh / KMH_PER_MPS,
                segment_id=segment.id,
            ))
        if len(self.points) < 2:
            raise ValueError("the route is too short to follow")
        self.length_m = self.points[-1].along_m

    def _add_point(self, x: float, y: float, z: float) -> None:
        """Append a point, unless it repeats the last one."""
        if not self.points:
            self.points.append(RoutePoint(x, y, z, 0.0))
            return
        last = self.points[-1]
        gap = math.dist((last.x, last.y, last.z), (x, y, z))
        if gap >= 1e-6:
            self.points.append(RoutePoint(x, y, z, last.along_m + gap))

    def _pieces(self) -> zip:
        """Each straight piece of the line, as its two end points."""
        return zip(self.points, self.points[1:])

    def locate(self, x: float, y: float, progress_m: float) -> float:
        """Find how far along the route a position is.

        Only the route just around the last known progress is searched, so
        that a route crossing itself cannot be skipped ahead on.

        Args:
            x: The position's x.
            y: The position's y.
            progress_m: The last known distance along the route.

        Returns:
            Meters along the route, never less than `progress_m`.
        """
        nearest_off = math.inf
        nearest_along = progress_m
        for start, end in self._pieces():
            if end.along_m < progress_m - SETTINGS.locate_behind_m:
                continue
            if start.along_m > progress_m + SETTINGS.locate_ahead_m:
                continue
            along, off = _project(start, end, x, y)
            if (off, along) < (nearest_off, nearest_along):
                nearest_off = off
                nearest_along = along
        return max(progress_m, min(nearest_along, self.length_m))

    def point_at(self, along_m: float) -> tuple[float, float]:
        """The (x, y) of the line at a distance along the route."""
        along_m = min(max(along_m, 0.0), self.length_m)
        for start, end in self._pieces():
            if along_m <= end.along_m:
                ratio = (along_m - start.along_m) / (end.along_m - start.along_m)
                return start.x + ratio * (end.x - start.x), start.y + ratio * (end.y - start.y)
        return self.points[-1].x, self.points[-1].y

    def heading_at(self, along_m: float) -> float:
        """The direction of the line at a distance along the route, in degrees."""
        ahead = self.point_at(along_m + 0.5)
        behind = self.point_at(along_m - 0.5)
        return math.degrees(math.atan2(ahead[1] - behind[1], ahead[0] - behind[0]))

    def plan_at(self, along_m: float) -> tuple[float, float, str]:
        """The plan at a distance along the route.

        Returns:
            The target speed and the speed limit, in m/s, and the segment id.
        """
        chosen = self.stretches[-1]
        for stretch in self.stretches:
            if along_m < stretch.end_m - 0.01:
                chosen = stretch
                break
        return chosen.target_mps, chosen.limit_mps, chosen.segment_id

    def gap_ahead(self, progress_m: float, others: list[tuple[float, float, float]], reach_m: float) -> float | None:
        """Find the nearest other road user in the car's path.

        One is in the path when it lies within the path's half width of the
        route line, no further ahead than `reach_m`.

        Args:
            progress_m: The car's distance along the route.
            others: Each other road user, as (x, y, radius).
            reach_m: How far ahead the driver can see.

        Returns:
            Meters along the route to the nearest one, or None if the path is clear.
        """
        pieces = [
            (start, end) for start, end in self._pieces()
            if end.along_m >= progress_m and start.along_m <= progress_m + reach_m
        ]
        nearest = None
        for x, y, radius in others:
            off = math.inf
            along = 0.0
            for start, end in pieces:
                piece_along, piece_off = _project(start, end, x, y)
                if (piece_off, piece_along) < (off, along):
                    off = piece_off
                    along = piece_along
            ahead = along - progress_m
            in_path = off <= SETTINGS.path_half_width_m + radius
            if in_path and 0.0 <= ahead <= reach_m:
                gap = ahead - radius
                if nearest is None or gap < nearest:
                    nearest = gap
        return nearest


def anticipated(movers: list[tuple[float, float, float, float, float]], horizon_s: float,
                step_s: float) -> list[tuple[float, float, float]]:
    """Where each road user will be over the next `horizon_s` seconds, if it keeps its velocity.

    Args:
        movers: Each road user now, as (x, y, radius, vx, vy).
        horizon_s: How far ahead to predict. 0 gives only where they are now.
        step_s: The time between predicted positions.

    Returns:
        Each road user as (x, y, radius), now and at every step up to the horizon.
    """
    steps = int(horizon_s / step_s + 1e-9) if horizon_s > 0 else 0
    return [(x + vx * k * step_s, y + vy * k * step_s, radius)
            for x, y, radius, vx, vy in movers for k in range(steps + 1)]


def walker_too_close(car: tuple[float, float, float], half_length: float, half_width: float,
                     movers: list[tuple[float, float, float, float, float]], lookahead_s: float,
                     clearance_m: float) -> bool:
    """Whether any walker is, or soon will be, within arm's length of the car's body, in any direction.

    Args:
        car: The car as (x, y, yaw_deg).
        half_length: Half the car's length.
        half_width: Half the car's width.
        movers: Each walker now, as (x, y, radius, vx, vy).
        lookahead_s: How far ahead to look along each walker's walk.
        clearance_m: The least room allowed between the car's body and a walker.
    """
    x, y, yaw_deg = car
    for walker_x, walker_y, radius, vx, vy in movers:
        for after_s in (0.0, lookahead_s):
            gap = box_gap(x, y, yaw_deg, half_length, half_width,
                          walker_x + vx * after_s, walker_y + vy * after_s, radius)
            if gap < clearance_m:
                return True
    return False


def _project(start: RoutePoint, end: RoutePoint, x: float, y: float) -> tuple[float, float]:
    """Find the point on one straight piece of the line nearest to (x, y).

    Returns:
        Meters along the route of that point, and meters from it to (x, y).
    """
    dx = end.x - start.x
    dy = end.y - start.y
    ratio = ((x - start.x) * dx + (y - start.y) * dy) / (dx * dx + dy * dy)
    ratio = min(1.0, max(0.0, ratio))
    along = start.along_m + ratio * (end.along_m - start.along_m)
    off = math.hypot(x - start.x - ratio * dx, y - start.y - ratio * dy)
    return along, off


def box_gap(x: float, y: float, yaw_deg: float, half_length: float, half_width: float,
            other_x: float, other_y: float, other_radius: float) -> float:
    """Meters between a car's body, as a box, and another road user, as a circle. Negative when they overlap."""
    yaw = math.radians(yaw_deg)
    dx = other_x - x
    dy = other_y - y
    forward = dx * math.cos(yaw) + dy * math.sin(yaw)
    sideways = -dx * math.sin(yaw) + dy * math.cos(yaw)
    beyond_length = max(abs(forward) - half_length, 0.0)
    beyond_width = max(abs(sideways) - half_width, 0.0)
    return math.hypot(beyond_length, beyond_width) - other_radius


def steer_toward(x: float, y: float, yaw_deg: float, target: tuple[float, float], wheelbase_m: float,
                 max_steer_deg: float) -> float:
    """Pure pursuit: the steer, from -1 to 1, that curves the car through a point ahead."""
    reach = math.hypot(target[0] - x, target[1] - y)
    if reach < 1e-6:
        return 0.0
    off = math.atan2(target[1] - y, target[0] - x) - math.radians(yaw_deg)
    wheel_deg = math.degrees(math.atan2(2.0 * wheelbase_m * math.sin(off), reach))
    return max(-1.0, min(1.0, wheel_deg / max_steer_deg))


def lookahead_m(speed_mps: float) -> float:
    """How far ahead on the route to steer toward: further at speed, within fixed bounds."""
    wanted = SETTINGS.lookahead_base_m + SETTINGS.lookahead_per_mps * speed_mps
    return max(SETTINGS.shortest_lookahead_m, min(SETTINGS.longest_lookahead_m, wanted))


def allowed_speed(target_mps: float, stop_within_m: float | None, deceleration_mps2: float) -> float:
    """The planned speed, or less if the car must be able to stop within a distance at its planned braking."""
    if stop_within_m is None:
        return target_mps
    stoppable = math.sqrt(2.0 * deceleration_mps2 * max(0.0, stop_within_m))
    return min(target_mps, stoppable)


def sight_speed(reach_m: float, half_length_m: float, min_gap_m: float, deceleration_mps2: float) -> float:
    """The fastest speed at which the car can still stop min_gap_m short of a road user that
    appears at the edge of its sight, braking at deceleration_mps2. Never quite 0, so that the
    car still creeps forward when it sees almost nothing."""
    room_m = max(reach_m - half_length_m - min_gap_m, SETTINGS.least_stopping_room_m)
    return math.sqrt(2.0 * deceleration_mps2 * room_m)


class SpeedControl:
    """Throttle and brake that hold a speed, within the driver's acceleration and braking limits.

    Attributes:
        grip: The share of dry-road braking the tires still give, from 0 to 1.
        memory: The accumulated speed error, which removes a steady offset.
        brake_trim: Brake pedal added to the pedal model while braking. It grows while the car
            decelerates less than asked, since the real brake is weaker than the model at
            part pedal, and is dropped once the car stops braking.
    """

    def __init__(self, driver: DriverModel, grip: float = 1.0):
        self.driver = driver
        self.grip = grip
        self.memory = 0.0
        self.brake_trim = 0.0
        self.asked_mps2: float | None = None   # the braking asked for on the last tick, if it braked

    def command(self, speed_mps: float, wanted_mps: float, delta_s: float,
                stop_within_m: float | None = None, measured_mps2: float | None = None) -> tuple[float, float]:
        """Choose the pedals for one tick.

        Args:
            speed_mps: The car's speed.
            wanted_mps: The speed to hold.
            delta_s: The length of the tick.
            stop_within_m: Room to an obstacle, if there is one. The car then
                brakes at least hard enough to stop in that room.
            measured_mps2: The car's acceleration over the last tick, if known. While
                braking, the brake is pressed harder until it matches what was asked.

        Returns:
            Throttle and brake, each from 0 to 1.
        """
        error = wanted_mps - speed_mps
        if abs(error) < SETTINGS.speed_memory_band_mps:
            memory = self.memory + error * delta_s
            self.memory = max(-SETTINGS.speed_memory_limit, min(SETTINGS.speed_memory_limit, memory))
        if self.asked_mps2 is not None and measured_mps2 is not None:
            # Single-tick physics spikes are clipped, so that they do not wind the trim down.
            measured = max(-self.driver.safety.max_deceleration_mps2 - SETTINGS.brake_trim_clip_mps2,
                           min(SETTINGS.brake_trim_clip_mps2, measured_mps2))
            trim = self.brake_trim + SETTINGS.brake_trim_gain * (measured - self.asked_mps2) * delta_s
            self.brake_trim = max(0.0, min(1.0, trim))
        self.asked_mps2 = None
        if wanted_mps < SETTINGS.stop_wanted_below_mps:
            self.memory = 0.0
            if speed_mps < SETTINGS.hold_below_mps:
                return 0.0, SETTINGS.hold_brake

        acceleration = SETTINGS.speed_gain * error + SETTINGS.speed_memory_gain * self.memory
        if stop_within_m is not None and speed_mps > wanted_mps:
            room = max(stop_within_m, SETTINGS.least_stopping_room_m)
            acceleration = min(acceleration, -speed_mps ** 2 / (2.0 * room))
        safety = self.driver.safety
        acceleration = max(-safety.max_deceleration_mps2, min(safety.max_acceleration_mps2, acceleration))
        return self._pedals(acceleration, speed_mps)

    def _pedals(self, acceleration_mps2: float, speed_mps: float) -> tuple[float, float]:
        """Turn a wanted acceleration into throttle and brake, from the car's rough pedal response."""
        pedal = acceleration_mps2 / SETTINGS.full_throttle_mps2 + SETTINGS.cruise_throttle_per_mps * speed_mps
        if pedal >= 0.0:
            self.brake_trim = 0.0
            return min(1.0, pedal), 0.0
        full_brake = SETTINGS.full_brake_mps2 * max(self.grip, SETTINGS.least_grip)
        self.asked_mps2 = acceleration_mps2
        return 0.0, min(1.0, -pedal * SETTINGS.full_throttle_mps2 / full_brake + self.brake_trim)
