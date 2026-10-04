"""Record a CARLA run to one gzip-compressed JSON-lines file.

The format is described in docs/run-format.md. Standard library and carla only, so it
runs in the wrapper's Wine Python.

    with RunLog(path, client, world, ego=vehicle, argv=sys.argv) as log:
        while driving:
            world.tick()
            log.tick(world.get_snapshot())
            log.event("collision", event.timestamp, other_id=..., other_type=...)
"""

import datetime
import gzip
import json
import os

import carla

FORMAT = "carla-run"
VERSION = 1
LANE_STEP = 2.0
TRACKED = ("vehicle.", "walker.")
STATIC = ("traffic.",)


def _r(value, digits=3):
    return round(value, digits)


def _xyz(v):
    return [_r(v.x), _r(v.y), _r(v.z)]


def _pose(transform):
    loc, rot = transform.location, transform.rotation
    return [_r(loc.x), _r(loc.y), _r(loc.z), _r(rot.yaw, 2), _r(rot.pitch, 2), _r(rot.roll, 2)]


def _box(bb):
    return {"center": _xyz(bb.location), "extent": _xyz(bb.extent),
            "rotation": [_r(bb.rotation.yaw, 2), _r(bb.rotation.pitch, 2), _r(bb.rotation.roll, 2)]}


def _lanes(cmap):
    lanes = []
    for start, _ in cmap.get_topology():
        points = [start] + start.next_until_lane_end(LANE_STEP)
        lanes.append({"road": start.road_id, "section": start.section_id, "lane": start.lane_id,
                      "lane_type": str(start.lane_type), "width": _r(start.lane_width, 2),
                      "junction": start.is_junction,
                      "points": [_xyz(w.transform.location) for w in points]})
    return lanes


def _junctions(cmap):
    found = {}
    for start, end in cmap.get_topology():
        for waypoint in (start, end):
            if waypoint.is_junction:
                junction = waypoint.get_junction()
                found[junction.id] = {"id": junction.id, **_box(junction.bounding_box)}
    return sorted(found.values(), key=lambda j: j["id"])


def _crosswalks(cmap):
    # get_crosswalks returns the corners of every polygon in one list; each polygon
    # ends where its first corner repeats.
    polygons, current = [], []
    for loc in cmap.get_crosswalks():
        point = _xyz(loc)
        if current and point == current[0] and len(current) > 2:
            polygons.append(current)
            current = []
        else:
            current.append(point)
    if len(current) > 2:
        polygons.append(current)
    return polygons


def _objects(world):
    objects = []
    for obj in world.get_environment_objects(carla.CityObjectLabel.Any):
        kind = str(obj.type)
        if kind == "Vegetation":
            continue
        objects.append({"id": obj.id, "class": kind, "name": obj.name, **_box(obj.bounding_box)})
    return objects


class RunLog:
    def __init__(self, path, client, world, ego=None, argv=None):
        self.world = world
        self.ego_id = ego.id if ego is not None else None
        self.ticks = 0
        self.t0 = None
        self.kinds = {}
        self.present = set()
        self.lights = []
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.file = gzip.open(path, "wt", encoding="utf-8", compresslevel=6)

        settings = world.get_settings()
        cmap = world.get_map()
        self._write({
            "type": "header", "format": FORMAT, "version": VERSION,
            "map": cmap.name.split("/")[-1],
            "client_version": client.get_client_version(),
            "server_version": client.get_server_version(),
            "delta_s": settings.fixed_delta_seconds,
            "synchronous": settings.synchronous_mode,
            "ego_id": self.ego_id,
            "argv": list(argv or []),
            "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        })
        self._write({"type": "scene", "lanes": _lanes(cmap), "junctions": _junctions(cmap),
                     "crosswalks": _crosswalks(cmap), "objects": _objects(world)})

    def _write(self, record):
        self.file.write(json.dumps(record, separators=(",", ":")))
        self.file.write("\n")

    def _kind(self, actor_id):
        """The type_id of an actor, written once as an actor record the first time it is seen."""
        if actor_id in self.kinds:
            return self.kinds[actor_id]
        actor = self.world.get_actor(actor_id)
        kind = actor.type_id if actor is not None else ""
        self.kinds[actor_id] = kind
        if kind.startswith(TRACKED + STATIC):
            self._write({"type": "actor", "id": actor_id, "type_id": kind,
                         "role_name": actor.attributes.get("role_name", ""),
                         "tick": self.ticks, "pose": _pose(actor.get_transform()),
                         "box": {"center": _xyz(actor.bounding_box.location),
                                 "extent": _xyz(actor.bounding_box.extent)}})
            if kind == "traffic.traffic_light":
                self.lights.append(actor)
        return kind

    def tick(self, snapshot):
        """Record one tick. Call once after each world.tick()."""
        if self.t0 is None:
            self.t0 = snapshot.timestamp.elapsed_seconds
        seen, states = set(), []
        for actor in snapshot:
            kind = self._kind(actor.id)
            if not kind.startswith(TRACKED):
                continue
            seen.add(actor.id)
            v = actor.get_velocity()
            states.append([actor.id, *_pose(actor.get_transform()), _r(v.x), _r(v.y), _r(v.z)])
        for gone in sorted(self.present - seen):
            self._write({"type": "gone", "id": gone, "tick": self.ticks})
        self.present = seen
        self._write({"type": "tick", "tick": self.ticks, "frame": snapshot.frame,
                     "t": _r(snapshot.timestamp.elapsed_seconds - self.t0, 4),
                     "actors": states,
                     "lights": [[light.id, str(light.get_state())] for light in self.lights]})
        self.ticks += 1

    def event(self, kind, timestamp, **detail):
        """Record an event of the ego, such as a collision, at its simulated timestamp."""
        t = None if self.t0 is None else _r(timestamp - self.t0, 4)
        self._write({"type": "event", "kind": kind, "tick": max(self.ticks - 1, 0), "t": t, **detail})

    def close(self, reason="", wall_s=None):
        if self.file.closed:
            return
        self._write({"type": "end", "ticks": self.ticks, "reason": reason,
                     "wall_s": None if wall_s is None else _r(wall_s, 2)})
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close("error" if exc_type else "done")
        return False
