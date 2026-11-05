"""Export CARLA topology as a portable catalog. CARLA is imported only on demand."""

import hashlib
import math
import xml.etree.ElementTree as ET

from .core import PlanningError


def map_hash(opendrive):
    normalized = ET.canonicalize(opendrive, strip_text=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


def segment_id(waypoint):
    return f"r{waypoint.road_id}.s{waypoint.section_id}.l{waypoint.lane_id}"


def _point(waypoint, distance):
    loc = waypoint.transform.location
    return {"x": loc.x, "y": loc.y, "z": loc.z, "s": waypoint.s, "distance_m": distance}


def _declared_limits(opendrive):
    limits = {}
    factors = {"km/h": 1.0, "mph": 1.609344, "m/s": 3.6}
    for road in ET.fromstring(opendrive).findall("road"):
        values = []
        for speed in road.findall("./type/speed"):
            try:
                value = float(speed.attrib["max"]) * factors[speed.get("unit", "m/s")]
            except (KeyError, ValueError):
                continue
            if math.isfinite(value) and value > 0:
                values.append(value)
        if values:
            limits[int(road.attrib["id"])] = min(values)
    return limits


def export_catalog(cmap, *, provenance, resolution=2.0, verified_limits=None):
    """Group physical lane spans before junction branches, retaining every successor.

    Town10 topology repeats the same incoming lane for multiple outgoing turns.
    A hazard belongs to that physical span, not to the driver's later turn choice.
    Reject a map that reuses a lane key for different entry positions rather than
    silently merging distinct physical spans.
    """
    if resolution <= 0:
        raise PlanningError("sampling resolution must be positive")
    opendrive = cmap.to_opendrive()
    digest = map_hash(opendrive)
    groups = {}
    for entry, exit_wp in cmap.get_topology():
        sid = segment_id(entry)
        if sid not in groups:
            groups[sid] = (entry, [])
        original, exits = groups[sid]
        if original.transform.location.distance(entry.transform.location) > 0.05:
            raise PlanningError(f"map has multiple spans for {sid}; extend catalog IDs before using this map")
        exits.append(exit_wp)
    limits = _declared_limits(opendrive)
    segments = {}
    for sid in sorted(groups):
        entry, exits = groups[sid]
        waypoints = [entry] + [w for w in entry.next_until_lane_end(resolution) if segment_id(w) == sid]
        geometry, length = [], 0.0
        for waypoint in waypoints:
            if geometry:
                previous = geometry[-1]
                loc = waypoint.transform.location
                delta = math.dist((previous["x"], previous["y"], previous["z"]), (loc.x, loc.y, loc.z))
                if delta < 1e-7:
                    continue
                length += delta
            geometry.append(_point(waypoint, length))
        if length <= 0:
            raise PlanningError(f"cannot sample {sid}")
        successors = set()
        for exit_wp in exits:
            candidate = segment_id(exit_wp)
            if candidate != sid:
                successors.add(candidate)
            else:
                successors.update(segment_id(w) for w in exit_wp.next(0.5) if segment_id(w) != sid)
        limit = limits.get(entry.road_id, 40.0)
        segments[sid] = {
            "road_id": entry.road_id, "section_id": entry.section_id, "lane_id": entry.lane_id,
            "junction": entry.is_junction, "length_m": length, "geometry": geometry,
            "successors": sorted(successors), "speed_limit_kmh": limit,
            "speed_limit_verified": False,
            "speed_limit_source": "OpenDRIVE declaration; not checked in a drive" if entry.road_id in limits
                                  else "mock 40 km/h; no road speed declaration",
        }
    for sid, segment in segments.items():
        end = segment["geometry"][-1]
        for successor in segment["successors"]:
            if successor not in segments:
                raise PlanningError(f"{sid} has an unexported successor: {successor}")
            start = segments[successor]["geometry"][0]
            gap = math.dist([end[k] for k in ("x", "y", "z")], [start[k] for k in ("x", "y", "z")])
            if gap > 1.0:
                raise PlanningError(f"disconnected geometry: {sid} -> {successor}, gap {gap:.2f} m")
    catalog = {"schema_version": 1, "map": cmap.name.split("/")[-1], "carla_version": "0.9.16",
               "map_hash": digest, "catalog_id": f"Town10HD_Opt:{digest[:16]}",
               "sampling_resolution_m": resolution, "provenance": provenance,
               "segments": segments, "spawn_points": []}
    if catalog["map"] != "Town10HD_Opt":
        raise PlanningError(f"expected Town10HD_Opt, got {catalog['map']}")
    if verified_limits is not None:
        if verified_limits.get("catalog_id") != catalog["catalog_id"]:
            raise PlanningError("speed-limit overrides belong to a different catalog")
        from .core import number
        for sid, value in verified_limits.get("limits", {}).items():
            if sid not in segments:
                raise PlanningError(f"unknown speed-limit segment: {sid}")
            segments[sid].update(speed_limit_kmh=number(value, f"limit {sid}", positive=True),
                                 speed_limit_verified=True, speed_limit_source="explicit verified override")
    for index, transform in enumerate(cmap.get_spawn_points()):
        waypoint = cmap.get_waypoint(transform.location)
        sid = segment_id(waypoint)
        if sid in segments:
            catalog["spawn_points"].append({"index": index, "segment_id": sid,
                                             "offset_m": offset_for_s(segments[sid], waypoint.s)})
    return catalog


def offset_for_s(segment, s):
    geometry = segment["geometry"]
    for a, b in zip(geometry, geometry[1:]):
        if min(a["s"], b["s"]) <= s <= max(a["s"], b["s"]):
            ratio = (s - a["s"]) / (b["s"] - a["s"])
            return a["distance_m"] + ratio * (b["distance_m"] - a["distance_m"])
    nearest = min(geometry, key=lambda p: abs(p["s"] - s))
    return nearest["distance_m"]


def sample_point(segment, offset):
    geometry = segment["geometry"]
    for a, b in zip(geometry, geometry[1:]):
        if a["distance_m"] <= offset <= b["distance_m"]:
            ratio = (offset - a["distance_m"]) / (b["distance_m"] - a["distance_m"])
            return {k: a[k] + ratio * (b[k] - a[k]) for k in ("x", "y", "z", "s", "distance_m")}
    return geometry[0] if offset <= 0 else geometry[-1]
