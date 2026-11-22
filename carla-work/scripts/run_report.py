"""Summarize a carla-run recording as Markdown for a run report.

Outcome, time, stops, and, for a Planner drive, the plan against the drive per segment.
Standard library only, so any native Python 3.10+ runs it; CARLA is not needed.
The plan and catalog default to plan.json and catalog.json.gz next to the run file,
which is where the HPC helper saves them.
"""

import argparse
import bisect
import gzip
import json
import math
from pathlib import Path
import sys

STOPPED_KMH = 0.5        # below this the ego counts as stopped
MOVED_KMH = 2.0          # stops count only after the ego first moves faster than this
MIN_STOP_S = 1.0         # shorter pauses are not stops
STEADY_KMH_PER_S = 1.0   # cruise ticks for speed tracking: |acceleration| below this


def load(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as stream:
        return json.load(stream)


def read_run(path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def summarize(rows, plan=None, catalog=None):
    header = rows[0]
    if header.get("type") != "header":
        raise ValueError("not a carla-run file: the first row is not a header")
    ego, dt = header["ego_id"], header["delta_s"]
    end = next((row for row in rows if row["type"] == "end"), None)
    lights = {row["id"]: row["pose"][:2] for row in rows
              if row["type"] == "actor" and row["type_id"].startswith("traffic.traffic_light")}
    ticks, track = [], []
    for row in rows:
        if row["type"] == "tick":
            actor = next((a for a in row["actors"] if a[0] == ego), None)
            if actor is not None:
                ticks.append(row)
                track.append((actor[1], actor[2], math.hypot(actor[7], actor[8]) * 3.6))
    events = [row for row in rows if row["type"] == "event"]
    targets = [e for e in events if e["kind"] == "plan_target"]
    speed = [kmh for _, _, kmh in track]
    step = [math.dist(track[i][:2], track[i + 1][:2]) for i in range(len(track) - 1)] + [0.0]
    sim_s = ticks[-1]["t"] if ticks else 0.0
    wall_s = end.get("wall_s") if end else None

    stops, i, moved = [], 0, False
    while i < len(speed):
        moved = moved or speed[i] > MOVED_KMH
        if not (moved and speed[i] < STOPPED_KMH):
            i += 1
            continue
        j = i
        while j < len(speed) and speed[j] < STOPPED_KMH:
            j += 1
        if (j - i) * dt >= MIN_STOP_S and j < len(speed):
            stop = {"t": ticks[i]["t"], "duration_s": (j - i) * dt, "light_m": None, "light_state": None}
            if lights:
                near = min(lights, key=lambda k: math.dist(track[i][:2], lights[k]))
                stop["light_m"] = math.dist(track[i][:2], lights[near])
                stop["light_state"] = dict(map(tuple, ticks[i].get("lights", []))).get(near)
            stops.append(stop)
        i = j
    stopped_s = sum(stop["duration_s"] for stop in stops)

    # Each plan_target starts a span that lasts until the next one, or the end of the run.
    numbers = [row["tick"] for row in ticks]
    starts = [bisect.bisect_left(numbers, e["tick"]) for e in targets] + [len(ticks)]
    segments, commanded = [], {}
    for n, event in enumerate(targets):
        a, b = starts[n], starts[n + 1]
        moving = [v for v in speed[a:b] if v > STOPPED_KMH]
        limit = (catalog or {}).get("segments", {}).get(event["segment_id"], {}).get("speed_limit_kmh")
        segments.append({"segment_id": event["segment_id"], "planned_kmh": event["planned_speed_kmh"],
                         "commanded_kmh": event["target_speed_kmh"],
                         "live_limit_kmh": event["live_speed_limit_kmh"], "catalog_limit_kmh": limit,
                         "driven_m": sum(step[a:b]), "time_s": (b - a) * dt,
                         "mean_moving_kmh": sum(moving) / len(moving) if moving else 0.0,
                         "max_kmh": max(speed[a:b]) if b > a else 0.0})
        commanded.update((k, event["target_speed_kmh"]) for k in range(a, b))
    errors = [speed[k] - commanded[k] for k in sorted(commanded)
              if k > 0 and speed[k] > STOPPED_KMH and abs(speed[k] - speed[k - 1]) / dt < STEADY_KMH_PER_S]
    tracking = ({"n": len(errors), "mean": sum(errors) / len(errors),
                 "mean_abs": sum(map(abs, errors)) / len(errors)} if errors else None)

    planner = header.get("settings", {}).get("planner")
    warnings, route = [], None
    if end is None:
        warnings.append("no end record: the run is incomplete")
    if plan is not None:
        planned = [s["segment_id"] for s in plan["segments"]]
        driven = list(dict.fromkeys(e["segment_id"] for e in targets))
        route = {"driven": len(driven), "planned": len(planned), "in_order": driven == planned[:len(driven)]}
        if planner and plan.get("catalog_hash") != planner.get("catalog_hash"):
            warnings.append("the plan's catalog hash differs from the recording's: a different plan?")
    if catalog is not None and planner and catalog.get("catalog_id") != planner.get("catalog_id"):
        warnings.append("the catalog's id differs from the recording's: limits may not apply")
    return {"map": header.get("map"), "scenario": header.get("scenario"), "started_utc": header.get("started_utc"),
            "reason": end["reason"] if end else "incomplete", "ticks": end["ticks"] if end else len(ticks),
            "sim_s": sim_s, "wall_s": wall_s, "ratio": sim_s / wall_s if wall_s else None,
            "distance_m": sum(step), "max_kmh": max(speed) if speed else 0.0,
            "collisions": sum(e["kind"] == "collision" for e in events),
            "lane_invasions": sum(e["kind"] == "lane_invasion" for e in events),
            "stops": stops, "stopped_s": stopped_s, "moving_s": sim_s - stopped_s,
            "planner": planner, "segments": segments, "route": route, "tracking": tracking, "warnings": warnings}


def number(value, digits=1):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(s):
    stops = f"{len(s['stops'])} stop" + ("" if len(s["stops"]) == 1 else "s")
    lines = ["## Summary", "", "| | |", "|---|---|",
             f"| Map | {s['map'] or '—'} |", f"| Scenario | {s['scenario'] or '—'} |",
             f"| Started (UTC) | {s['started_utc'] or '—'} |",
             f"| End | {s['reason']} after {s['ticks']:,} ticks |",
             f"| Collisions / lane invasions | {s['collisions']} / {s['lane_invasions']} |",
             f"| Distance driven | {s['distance_m']:.0f} m |",
             f"| Simulated / wall time | {s['sim_s']:.1f} s / {number(s['wall_s'], 2)} s"
             + (f" ({s['ratio']:.1f}× real time) |" if s["ratio"] else " |"),
             f"| Moving / stopped time | {s['moving_s']:.1f} s / {s['stopped_s']:.1f} s in {stops} |",
             f"| Maximum speed | {s['max_kmh']:.1f} km/h |"]
    planner = s["planner"]
    if planner:
        estimate = planner.get("estimated_time_s")
        versus = f", moving time {100 * (s['moving_s'] / estimate - 1):+.1f}%" if estimate else ""
        lines.append(f"| Planner | {planner.get('mode')}, λ = {planner.get('trip', {}).get('risk_weight', 0):g}; "
                     f"plan `{planner.get('plan_hash', '')[:8]}`, catalog `{planner.get('catalog_id')}`; "
                     f"estimate {number(estimate)} s{versus}; predicted penalty {number(planner.get('predicted_penalty'), 2)} |")
    if s["tracking"]:
        t = s["tracking"]
        lines.append(f"| Speed tracking at cruise | mean error {t['mean']:+.2f} km/h, mean absolute {t['mean_abs']:.2f} km/h, "
                     f"{t['n']} steady ticks |")
    for warning in s["warnings"]:
        lines.append(f"| Warning | {warning} |")
    if s["stops"]:
        lines += ["", "## Stops", "", "| Stop at | Duration | Nearest traffic light | Its state when the stop began |",
                  "|---|---|---|---|"]
        lines += [f"| {stop['t']:.1f} s | {stop['duration_s']:.1f} s | {number(stop['light_m'])} m | "
                  f"{stop['light_state'] or '—'} |" for stop in s["stops"]]
    if s["segments"]:
        lines += ["", "## Plan vs drive", "",
                  "| # | Segment | Planned km/h | Commanded | Live limit | Catalog limit | Driven m | Time s "
                  "| Mean moving km/h | Max km/h |", "|---|---|---|---|---|---|---|---|---|---|"]
        lines += [f"| {n} | `{g['segment_id']}` | {g['planned_kmh']:g} | {g['commanded_kmh']:g} | "
                  f"{g['live_limit_kmh']:g} | {number(g['catalog_limit_kmh'])} | {g['driven_m']:.0f} | "
                  f"{g['time_s']:.1f} | {g['mean_moving_kmh']:.1f} | {g['max_kmh']:.1f} |"
                  for n, g in enumerate(s["segments"], 1)]
        if s["route"]:
            r = s["route"]
            lines += ["", f"{r['driven']} of {r['planned']} planned segments driven, "
                          + ("in plan order." if r["in_order"] else "**not in plan order**.")]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, help="run file (*.jsonl.gz)")
    parser.add_argument("--plan", type=Path, help="Planner plan (default: plan.json next to the run)")
    parser.add_argument("--catalog", type=Path, help="road catalog (default: catalog.json.gz next to the run)")
    args = parser.parse_args(argv)
    plan_path = args.plan or args.run.parent / "plan.json"
    catalog_path = args.catalog or args.run.parent / "catalog.json.gz"
    plan = load(plan_path) if plan_path.exists() else None
    catalog = load(catalog_path) if catalog_path.exists() else None
    sys.stdout.write(markdown(summarize(read_run(args.run), plan, catalog)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
