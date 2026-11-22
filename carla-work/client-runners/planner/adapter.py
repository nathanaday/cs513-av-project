"""Runner-side CARLA adapter. The offline planner never imports this module."""

import math

from .carla_map import map_hash, sample_point
from .core import PlanningError, fingerprint, number, validate_catalog


def project_progress(points, progress, location, window=15.0):
    """Project onto the nearby forward portion of a route; never jump across a loop."""
    best = (math.inf, progress)
    for a, b in zip(points, points[1:]):
        if b[3] < progress - 2 or a[3] > progress + window:
            continue
        vector = [b[i] - a[i] for i in range(3)]
        norm = sum(v * v for v in vector)
        if norm < 1e-12:
            continue
        ratio = max(0.0, min(1.0, sum((location[i] - a[i]) * vector[i] for i in range(3)) / norm))
        along = a[3] + ratio * (b[3] - a[3])
        if along > progress + window:
            continue
        distance = sum((location[i] - a[i] - ratio * vector[i]) ** 2 for i in range(3))
        best = min(best, (distance, along))
    if best[0] > 25:
        raise PlanningError("vehicle is more than 5 m from the nearby planned route")
    return max(progress, best[1])


class PlanFollower:
    def __init__(self, cmap, catalog, plan, *, allow_unverified=False):
        import carla
        from agents.navigation.local_planner import RoadOption
        validate_catalog(catalog)
        if plan.get("schema_version") != 1 or plan.get("catalog_hash") != fingerprint(catalog):
            raise PlanningError("plan does not match this catalog")
        if map_hash(cmap.to_opendrive()) != catalog.get("map_hash"):
            raise PlanningError("live map does not match the exported catalog")
        if not plan.get("segments"):
            raise PlanningError("driving requires a nonempty plan")
        self.plan, self.points, self.route, self.boundaries = plan, [], [], []
        self.progress = 0.0
        self.last_target = None
        total = 0.0
        steps = plan["segments"]
        for index, step in enumerate(steps):
            sid = step["segment_id"]
            if sid not in catalog["segments"]:
                raise PlanningError(f"unknown planned segment: {sid}")
            segment = catalog["segments"][sid]
            if not allow_unverified and segment.get("speed_limit_verified") is not True:
                raise PlanningError(f"unverified speed limit on {sid}; use the explicit prototype override")
            start = number(step["start_offset_m"], "start offset", maximum=segment["length_m"])
            end = number(step["end_offset_m"], "end offset", minimum=start, maximum=segment["length_m"])
            speed = number(step["target_speed_kmh"], "target speed", positive=True,
                           maximum=segment["speed_limit_kmh"])
            if end <= start:
                raise PlanningError("plan contains an empty traversal")
            if index:
                previous = steps[index - 1]
                prior = catalog["segments"][previous["segment_id"]]
                if sid not in prior["successors"] or abs(previous["end_offset_m"] - prior["length_m"]) > 0.01 or start > 0.01:
                    raise PlanningError("plan has a disconnected or partially skipped transition")
            option = RoadOption.LANEFOLLOW
            if segment["junction"]:
                before, after = index, index
                while before > 0 and catalog["segments"][steps[before]["segment_id"]]["junction"]:
                    before -= 1
                while after < len(steps) - 1 and catalog["segments"][steps[after]["segment_id"]]["junction"]:
                    after += 1
                incoming = catalog["segments"][steps[before]["segment_id"]]["geometry"]
                outgoing = catalog["segments"][steps[after]["segment_id"]]["geometry"]
                u = [incoming[-1][k] - incoming[-2][k] for k in ("x", "y")]
                v = [outgoing[1][k] - outgoing[0][k] for k in ("x", "y")]
                angle = math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]))
                option = RoadOption.STRAIGHT if abs(angle) < 35 else (RoadOption.LEFT if angle < 0 else RoadOption.RIGHT)
            samples = [sample_point(segment, start)]
            samples += [p for p in segment["geometry"] if start < p["distance_m"] < end]
            samples.append(sample_point(segment, end))
            for point in samples:
                waypoint = cmap.get_waypoint_xodr(segment["road_id"], segment["lane_id"], point["s"])
                if waypoint is None:
                    # CARLA can emit a lane-end s that rounds just beyond the road.
                    # Move one millimeter inward, preserving the selected road/lane.
                    middle_s = (segment["geometry"][0]["s"] + segment["geometry"][-1]["s"]) / 2
                    inward = point["s"] + math.copysign(0.001, middle_s - point["s"])
                    waypoint = cmap.get_waypoint_xodr(segment["road_id"], segment["lane_id"], inward)
                if waypoint is None:
                    raise PlanningError(f"cannot reconstruct waypoint on {sid}")
                self.route.append((waypoint, option))
                self.points.append((point["x"], point["y"], point["z"], total + point["distance_m"] - start))
            total += end - start
            self.boundaries.append((total, speed, sid))
        first = self.route[0][0].transform
        self.spawn = carla.Transform(carla.Location(first.location.x, first.location.y, first.location.z + 0.5), first.rotation)
        self.metadata = {"plan_hash": fingerprint(plan), "catalog_id": catalog["catalog_id"],
                         "catalog_hash": plan["catalog_hash"], "forecast_id": plan["forecast_id"],
                         "forecast_hash": plan["forecast_hash"], "config_hash": plan["config_hash"],
                         "mode": plan["mode"], "trip": plan["trip"],
                         "estimated_time_s": plan["estimated_time_s"], "predicted_penalty": plan["predicted_penalty"],
                         "prototype_unverified_limits": allow_unverified}

    def install(self, agent):
        agent.follow_speed_limits(False)
        agent.set_global_plan(self.route, stop_waypoint_creation=True, clean_queue=True)

    def update(self, agent, vehicle):
        location = vehicle.get_location()
        self.progress = project_progress(self.points, self.progress, (location.x, location.y, location.z))
        boundary = self.boundaries[-1]
        for candidate in self.boundaries:
            if self.progress < candidate[0] - 0.01:
                boundary = candidate
                break
        _, speed, sid = boundary
        # The driver's live speed limit can lower a target, but never raise it.
        live_limit = vehicle.get_speed_limit()
        commanded = min(speed, live_limit) if live_limit > 0 else speed
        agent.set_target_speed(commanded)
        target = (sid, speed, commanded)
        if target != self.last_target:
            self.last_target = target
            return {"segment_id": sid, "target_speed_kmh": commanded,
                    "planned_speed_kmh": speed, "live_speed_limit_kmh": live_limit,
                    "progress_m": self.progress}
        return None
