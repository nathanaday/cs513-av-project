"""Replay a CARLA run file (docs/run-format.md) in the Rerun viewer, or write it as .rrd."""

import argparse
import gzip
import json
import os
import sys
import zlib
from collections import defaultdict

import numpy as np
import rerun as rr
import rerun.blueprint as rrb

FORMAT, VERSION = "carla-run", 1
TIMELINE = "sim"

EGO = (255, 80, 40)
VEHICLE = (70, 140, 255)
TRUCK = (40, 90, 200)
TWO_WHEEL = (180, 110, 255)
WALKER = (60, 200, 90)
PARKED = (110, 130, 160)
LIGHT = {"Red": (230, 40, 40), "Yellow": (240, 200, 30), "Green": (40, 210, 70)}
LIGHT_OFF = (90, 90, 90)
OBJECT_COLORS = {
    "Buildings": (150, 140, 130), "Sidewalks": (95, 95, 100), "Walls": (140, 130, 120),
    "Fences": (120, 110, 90), "Poles": (170, 170, 170), "TrafficSigns": (220, 220, 60),
    "TrafficLight": (200, 200, 200), "Static": (130, 120, 110), "Dynamic": (160, 110, 80),
}
PARKED_CLASSES = {"Car", "Truck", "Bus", "Motorcycle", "Bicycle", "Rider"}
SKIPPED_CLASSES = {"Roads", "RoadLines", "Ground", "Terrain", "Water", "Sky", "NONE"}


class RunFileError(Exception):
    pass


def read_run(path):
    """Return the records of a run file. A cut-off last line is dropped."""
    records = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    break
    except FileNotFoundError:
        raise RunFileError(f"no such file: {path}")
    except (OSError, EOFError, zlib.error) as error:
        if not records:
            raise RunFileError(f"{path} is not a gzip run file ({error})")
    if not records or records[0].get("type") != "header" or records[0].get("format") != FORMAT:
        raise RunFileError(f"{path} is not a {FORMAT} file")
    if records[0].get("version") != VERSION:
        raise RunFileError(f"{path} has format version {records[0].get('version')}; this tool reads {VERSION}")
    return records


# CARLA's frame is left-handed (x forward, y right, z up). Rerun's is right-handed,
# so y and yaw change sign; otherwise the replay is mirrored.
def flip(points):
    points = np.asarray(points, dtype=np.float32).reshape(-1, 3).copy()
    points[:, 1] *= -1
    return points


def yaw_quaternions(yaw_degrees):
    half = -np.radians(np.asarray(yaw_degrees, dtype=np.float64)) / 2
    q = np.zeros((len(half), 4), dtype=np.float32)
    q[:, 2], q[:, 3] = np.sin(half), np.cos(half)
    return q


def box_centers(xyz, yaw_degrees, offset):
    """World centers, in CARLA's frame, of boxes whose center is offset from the actor's pose."""
    yaw = np.radians(yaw_degrees)
    c, s = np.cos(yaw), np.sin(yaw)
    ox, oy, oz = offset
    return np.column_stack([xyz[:, 0] + ox * c - oy * s, xyz[:, 1] + ox * s + oy * c, xyz[:, 2] + oz])


def actor_color(actor, ego_id):
    if actor["id"] == ego_id:
        return EGO
    if actor["type_id"].startswith("walker."):
        return WALKER
    base = actor.get("base_type", "").lower()
    if base in ("motorcycle", "bicycle"):
        return TWO_WHEEL
    if base in ("truck", "bus"):
        return TRUCK
    return VEHICLE


def actor_group(actor, ego_id):
    if actor["id"] == ego_id:
        return "ego"
    return "walkers" if actor["type_id"].startswith("walker.") else "vehicles"


def log_scene(scene):
    rr.log("/", rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
    lanes = [lane for lane in scene["lanes"] if len(lane["points"]) > 1]
    surfaces = [flip(lane["points"]) - [0, 0, 0.05] for lane in lanes]
    rr.log("scene/roads", rr.LineStrips3D(surfaces, radii=[lane["width"] / 2 for lane in lanes],
                                           colors=(55, 55, 60)), static=True)
    rr.log("scene/lane_centers", rr.LineStrips3D([flip(lane["points"]) for lane in lanes],
                                                  radii=0.05, colors=(200, 200, 120)), static=True)
    crosswalks = [np.vstack([flip(p), flip(p[:1])]) + [0, 0, 0.05] for p in scene["crosswalks"]]
    rr.log("scene/crosswalks", rr.LineStrips3D(crosswalks, radii=0.3, colors=(235, 235, 235)), static=True)
    junctions = scene["junctions"]
    if junctions:
        rr.log("scene/junctions", rr.Boxes3D(
            centers=flip([j["center"] for j in junctions]), half_sizes=[j["extent"] for j in junctions],
            quaternions=yaw_quaternions([j["rotation"][0] for j in junctions]),
            colors=(240, 160, 60, 140), radii=0.12, fill_mode=rr.components.FillMode.MajorWireframe,
            labels=[f"junction {j['id']}" for j in junctions], show_labels=False),
            static=True)

    by_class = defaultdict(list)
    for obj in scene["objects"]:
        if obj["class"] not in SKIPPED_CLASSES:
            by_class[obj["class"]].append(obj)
    for cls, objects in sorted(by_class.items()):
        parked = cls in PARKED_CLASSES
        path = f"scene/parked/{cls}" if parked else f"scene/objects/{cls}"
        rr.log(path, rr.Boxes3D(
            centers=flip([o["center"] for o in objects]), half_sizes=[o["extent"] for o in objects],
            quaternions=yaw_quaternions([o["rotation"][0] for o in objects]),
            colors=PARKED if parked else OBJECT_COLORS.get(cls, (120, 120, 120)),
            fill_mode=rr.components.FillMode.Solid if parked or cls == "Buildings" else None,
            labels=[o["name"] for o in objects], show_labels=False), static=True)


def log_actors(actors, rows, gone, ego_id):
    for actor_id, actor in actors.items():
        if actor_id not in rows:
            continue
        group = actor_group(actor, ego_id)
        path = f"actors/{group}/{actor_id}"
        data = np.asarray(rows[actor_id], dtype=np.float64)
        t, xyz, yaw = data[:, 0], data[:, 1:4], data[:, 4]
        centers = flip(box_centers(xyz, yaw, actor["box"]["center"]))
        rr.log(path, rr.Boxes3D(half_sizes=[actor["box"]["extent"]], colors=actor_color(actor, ego_id),
                                fill_mode=rr.components.FillMode.Solid,
                                labels=f"{actor['type_id']} ({actor_id})", show_labels=group == "ego"),
               static=True)
        rr.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=t)],
                        columns=rr.Boxes3D.columns(centers=centers, quaternions=yaw_quaternions(yaw)))
        if actor_id in gone:
            rr.set_time(TIMELINE, duration=gone[actor_id])
            rr.log(path, rr.Clear(recursive=False))
        if group == "ego":
            rr.log("actors/ego_path", rr.LineStrips3D([flip(xyz)], radii=0.2, colors=(255, 150, 90)), static=True)
            speed = np.linalg.norm(data[:, 7:10], axis=1) * 3.6
            rr.send_columns("ego/speed_kmh", indexes=[rr.TimeColumn(TIMELINE, duration=t)],
                            columns=rr.Scalars.columns(scalars=speed))


def log_lights(actors, light_states):
    for light_id, changes in light_states.items():
        actor = actors.get(light_id)
        if actor is None:
            continue
        x, y, z, yaw = actor["pose"][:4]
        path = f"traffic_lights/{light_id}"
        rr.log(path, rr.Boxes3D(centers=flip([x, y, z + 3.0]), half_sizes=[0.6, 0.6, 0.6],
                                fill_mode=rr.components.FillMode.Solid), static=True)
        times = np.array([t for t, _ in changes])
        colors = [LIGHT.get(state, LIGHT_OFF) for _, state in changes]
        rr.send_columns(path, indexes=[rr.TimeColumn(TIMELINE, duration=times)],
                        columns=rr.Boxes3D.columns(colors=colors))


def log_signs(actors):
    signs = [a for a in actors.values() if a["type_id"] in ("traffic.stop", "traffic.yield")]
    if signs:
        rr.log("traffic_signs", rr.Points3D(
            flip([a["pose"][:3] for a in signs]), radii=0.8,
            colors=[(230, 50, 50) if a["type_id"] == "traffic.stop" else (240, 200, 30) for a in signs],
            labels=[a["type_id"].split(".")[1] for a in signs], show_labels=False), static=True)


def log_events(events):
    for event in events:
        if event.get("t") is None:
            continue
        rr.set_time(TIMELINE, duration=event["t"])
        if event["kind"] == "collision":
            text = f"collision with {event.get('other_type')} ({event.get('other_id')}), impulse {event.get('impulse')} N*s"
            rr.log("events", rr.TextLog(text, level=rr.TextLogLevel.WARN))
        elif event["kind"] == "plan_target":
            text = (f"plan {event['segment_id']}: target {event['target_speed_kmh']:g} km/h "
                    f"(planned {event['planned_speed_kmh']:g}, limit {event['live_speed_limit_kmh']:g})")
            rr.log("events", rr.TextLog(text, level=rr.TextLogLevel.INFO))
        else:
            rr.log("events", rr.TextLog(f"{event['kind']}: {', '.join(event.get('markings', []))}",
                                        level=rr.TextLogLevel.INFO))


def blueprint(scene, ego_track):
    points = np.vstack([flip(lane["points"]) for lane in scene["lanes"] if lane["points"]])
    center = (points.min(axis=0) + points.max(axis=0)) / 2
    span = float(np.ptp(points[:, :2], axis=0).max())
    eye = rrb.EyeControls3D(position=center + [0, -0.05 * span, 1.1 * span], look_target=center,
                            eye_up=[0, 0, 1], tracking_entity="actors/ego" if ego_track else None)
    return rrb.Blueprint(
        rrb.Horizontal(
            rrb.Spatial3DView(name="Run", origin="/", eye_controls=eye, line_grid=False),
            rrb.Vertical(rrb.TimeSeriesView(name="Ego speed (km/h)", origin="ego"),
                         rrb.TextLogView(name="Events", origin="events")),
            column_shares=[3, 1]),
        rrb.TimePanel(expanded=True, timeline=TIMELINE),
        collapse_panels=False)


def convert(records, ego_track=False):
    header, scene = records[0], records[1]
    ego_id = header.get("ego_id")
    actors, rows, gone, light_states, events = {}, defaultdict(list), {}, {}, []
    tick_t = {}
    for record in records[2:]:
        kind = record["type"]
        if kind == "actor":
            actors[record["id"]] = record
        elif kind == "tick":
            t = record["t"]
            tick_t[record["tick"]] = t
            for row in record["actors"]:
                rows[row[0]].append([t, *row[1:]])
            for light_id, state in record["lights"]:
                changes = light_states.setdefault(light_id, [])
                if not changes or changes[-1][1] != state:
                    changes.append((t, state))
        elif kind == "gone":
            gone[record["id"]] = tick_t.get(record["tick"], tick_t.get(record["tick"] - 1, 0.0))
        elif kind == "event":
            events.append(record)

    log_scene(scene)
    log_actors(actors, rows, gone, ego_id)
    log_lights(actors, light_states)
    log_signs(actors)
    log_events(events)
    # After the data, so the viewer knows the timeline the layout names.
    rr.send_blueprint(blueprint(scene, ego_track))
    return header, len(tick_t), len(actors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="run file (*.jsonl.gz)")
    parser.add_argument("--rrd", metavar="OUT", help="write a .rrd file instead of opening the viewer")
    parser.add_argument("--follow", action="store_true", help="the 3D view follows the ego")
    parser.add_argument("--recording-id", help="Rerun recording id (default: the run file's name)")
    args = parser.parse_args()
    try:
        records = read_run(args.run)
    except RunFileError as error:
        print(f"carla-replay: {error}", file=sys.stderr)
        return 2

    rr.init("carla-replay", recording_id=args.recording_id or os.path.basename(args.run))
    if args.rrd:
        rr.save(args.rrd)
    else:
        # The spawned viewer shares this terminal; keep its info logs out of it.
        os.environ.setdefault("RUST_LOG", "warn")
        rr.spawn()
    header, ticks, actors = convert(records, ego_track=args.follow)
    duration = ticks * (header.get("delta_s") or 0)
    print(f"{header['map']}: {ticks} ticks ({duration:.1f} sim s), {actors} actors"
          + (f"; wrote {args.rrd}" if args.rrd else "; opened in the Rerun viewer"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
