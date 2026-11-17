"""Probe the speed limit CARLA reports on every catalog segment, and derive verified overrides.

CARLA changes a vehicle's reported speed limit only when the vehicle passes a speed-limit
sign. With no such signs in the map, the reported limit is the same on every road, so a
fixed per-segment limit is valid. With signs, the limit depends on the route already
driven, and fixed per-segment overrides would be wrong; the probe then refuses.
"""

import datetime

from .carla_map import map_hash, sample_point, segment_id
from .core import PlanningError

MAX_SPEED_LANDMARK = "274"  # OpenDRIVE sign code for a maximum speed


def probe(world, catalog, blueprint="vehicle.tesla.model3", ticks=3, delta=0.05):
    """Place one physics-free vehicle mid-way along each segment and read its live limit."""
    import carla
    cmap = world.get_map()
    signs = {}
    for actor in world.get_actors().filter("traffic.*"):
        signs[actor.type_id] = signs.get(actor.type_id, 0) + 1
    landmarks = [{"id": mark.id, "name": mark.name, "road_id": mark.road_id, "s": mark.s,
                  "value": mark.value, "unit": mark.unit}
                 for mark in cmap.get_all_landmarks_of_type(MAX_SPEED_LANDMARK)]
    evidence = {"map": cmap.name.split("/")[-1], "map_hash": map_hash(cmap.to_opendrive()),
                "catalog_id": catalog["catalog_id"],
                "probed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "vehicle": blueprint, "sign_actors": signs, "speed_limit_landmarks": landmarks, "segments": {}}
    original = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode, settings.fixed_delta_seconds = True, delta
    world.apply_settings(settings)
    vehicle = None
    try:
        library = world.get_blueprint_library()
        for spawn in cmap.get_spawn_points():
            vehicle = world.try_spawn_actor(library.find(blueprint), spawn)
            if vehicle is not None:
                break
        if vehicle is None:
            raise PlanningError("no free spawn point for the probe vehicle")
        for _ in range(ticks):
            world.tick()
        evidence["default_limit_kmh"] = vehicle.get_speed_limit()
        vehicle.set_simulate_physics(False)
        for sid, segment in sorted(catalog["segments"].items()):
            middle = sample_point(segment, segment["length_m"] / 2)
            waypoint = cmap.get_waypoint_xodr(segment["road_id"], segment["lane_id"], middle["s"])
            record = {"waypoint_segment": None, "live_limit_kmh": None}
            if waypoint is not None:
                location = waypoint.transform.location
                vehicle.set_transform(carla.Transform(carla.Location(location.x, location.y, location.z + 0.5),
                                                      waypoint.transform.rotation))
                for _ in range(ticks):
                    world.tick()
                record = {"waypoint_segment": segment_id(waypoint), "live_limit_kmh": vehicle.get_speed_limit()}
            evidence["segments"][sid] = record
    finally:
        if vehicle is not None:
            vehicle.destroy()
        world.apply_settings(original)
    return evidence


def overrides_from_probe(catalog, evidence):
    """Return `export --speed-limits` overrides for every segment, or raise if the probe cannot support them."""
    if evidence.get("map_hash") != catalog.get("map_hash"):
        raise PlanningError("the probe ran on a different map than this catalog")
    signs = sorted(k for k in evidence.get("sign_actors", {}) if k.startswith("traffic.speed_limit"))
    if signs or evidence.get("speed_limit_landmarks"):
        raise PlanningError("speed-limit signs exist; live limits depend on the route driven, "
                            "so fixed per-segment limits cannot be derived")
    limits = {}
    for sid in sorted(catalog["segments"]):
        record = evidence.get("segments", {}).get(sid)
        if record is None:
            raise PlanningError(f"segment not probed: {sid}")
        if record.get("waypoint_segment") != sid:
            raise PlanningError(f"the probe for {sid} landed on {record.get('waypoint_segment')}")
        value = record.get("live_limit_kmh")
        if not value or value <= 0:
            raise PlanningError(f"no live limit on {sid}")
        limits[sid] = float(value)
    distinct = sorted(set(limits.values()))
    source = (f"live CARLA {evidence['vehicle']} speed limit, probed {evidence['probed_utc']} on every segment; "
              "the map has no speed-limit signs or landmarks")
    return {"catalog_id": catalog["catalog_id"], "limits": limits, "source": source,
            "evidence": {"probed_utc": evidence["probed_utc"], "vehicle": evidence["vehicle"],
                         "default_limit_kmh": evidence.get("default_limit_kmh"),
                         "distinct_live_limits_kmh": distinct, "segments": len(limits),
                         "sign_actors": evidence.get("sign_actors", {})}}
