"""A fixed-forecast, nonnegative-cost planner over directed road segments."""

import hashlib
import json
import math

import networkx as nx

HAZARDS = ("pedestrian", "visibility", "wet_road")
DEFAULT_CONFIG = {
    "candidate_speeds_kmh": [20.0, 30.0, 40.0],
    "reference_speed_kmh": 30.0,
    "cautious_speed_kmh": 20.0,
    "weights": {name: 1.0 for name in HAZARDS},
}


class PlanningError(ValueError):
    """Invalid input, unsupported catalog, or unreachable destination."""


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def number(value, name, minimum=0.0, maximum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanningError(f"{name} must be a number")
    if not math.isfinite(value) or value < minimum or (positive and value == 0):
        raise PlanningError(f"invalid {name}: {value}")
    if maximum is not None and value > maximum:
        raise PlanningError(f"{name} must be <= {maximum}")
    return float(value)


def validate_catalog(catalog, require_verified_limits=False):
    if not isinstance(catalog, dict):
        raise PlanningError("catalog must be a JSON object")
    if catalog.get("schema_version") != 1 or not catalog.get("catalog_id"):
        raise PlanningError("catalog needs schema_version=1 and catalog_id")
    segments = catalog.get("segments")
    if not isinstance(segments, dict) or not segments:
        raise PlanningError("catalog has no segments")
    for sid, segment in segments.items():
        if not isinstance(sid, str) or not sid:
            raise PlanningError("segment IDs must be nonempty strings")
        if not isinstance(segment, dict):
            raise PlanningError(f"{sid} must be a segment object")
        number(segment.get("length_m"), f"{sid}.length_m", positive=True)
        number(segment.get("speed_limit_kmh"), f"{sid}.speed_limit_kmh", positive=True)
        if require_verified_limits and segment.get("speed_limit_verified") is not True:
            raise PlanningError(f"speed limit is not verified: {sid}")
        successors = segment.get("successors")
        if not isinstance(successors, list) or any(not isinstance(s, str) or s not in segments for s in successors):
            raise PlanningError(f"unknown or invalid successor of {sid}")
    return segments


def validate_inputs(catalog, forecast, trip, config, require_verified_limits=False):
    segments = validate_catalog(catalog, require_verified_limits)
    if not isinstance(forecast, dict) or not isinstance(trip, dict):
        raise PlanningError("forecast and trip must be JSON objects")
    if forecast.get("schema_version") != 1 or not forecast.get("forecast_id"):
        raise PlanningError("forecast needs schema_version=1 and forecast_id")
    if forecast.get("catalog_id") != catalog["catalog_id"]:
        raise PlanningError("forecast belongs to a different catalog")
    risks = forecast.get("segments", {})
    if not isinstance(risks, dict) or set(risks) != set(segments):
        raise PlanningError("forecast must cover exactly the catalog's segment IDs")
    for sid, risks_here in risks.items():
        if not isinstance(risks_here, dict):
            raise PlanningError(f"{sid} risk must be an object")
        for hazard in HAZARDS:
            number(risks_here.get(hazard), f"{sid}.{hazard}", maximum=1.0)
    for name in ("origin", "destination"):
        point = trip.get(name, {})
        if not isinstance(point, dict):
            raise PlanningError(f"{name} must be an endpoint object")
        sid = point.get("segment_id")
        if not isinstance(sid, str) or sid not in segments:
            raise PlanningError(f"unknown {name} segment: {sid}")
        number(point.get("offset_m"), f"{name}.offset_m", maximum=segments[sid]["length_m"])
    number(trip.get("departure_time_s"), "departure_time_s")
    number(trip.get("risk_weight"), "risk_weight")
    if set(config) != set(DEFAULT_CONFIG):
        raise PlanningError("configuration must contain the documented four fields")
    if not isinstance(config["candidate_speeds_kmh"], list) or not config["candidate_speeds_kmh"]:
        raise PlanningError("candidate_speeds_kmh must be a nonempty list")
    for speed in config["candidate_speeds_kmh"]:
        number(speed, "candidate speed", positive=True)
    number(config["reference_speed_kmh"], "reference speed", positive=True)
    number(config["cautious_speed_kmh"], "cautious speed", positive=True)
    if not isinstance(config["weights"], dict) or set(config["weights"]) != set(HAZARDS):
        raise PlanningError("weights must cover the three hazard modes")
    for hazard in HAZARDS:
        number(config["weights"][hazard], f"weight.{hazard}")
    return segments


def price(distance_m, speed_kmh, risks, risk_weight, config):
    duration = distance_m / (speed_kmh / 3.6)
    hazard_score = sum(config["weights"][h] * risks[h] for h in HAZARDS)
    rate = hazard_score * (speed_kmh / config["reference_speed_kmh"]) ** 2
    penalty = rate * duration
    return {"distance_m": distance_m, "target_speed_kmh": speed_kmh,
            "estimated_time_s": duration, "predicted_penalty": penalty,
            "objective": duration + risk_weight * penalty}


def best_price(distance, segment, risks, risk_weight, config):
    limit = segment["speed_limit_kmh"]
    speeds = sorted({limit, *(v for v in config["candidate_speeds_kmh"] if v <= limit)})
    choices = [price(distance, v, risks, risk_weight, config) for v in speeds]
    return min(choices, key=lambda p: (p["objective"], p["estimated_time_s"], -p["target_speed_kmh"]))


def make_plan(catalog, forecast, trip, config=None, *, mode="risk-aware", require_verified_limits=False):
    """Return a JSON-compatible plan, including partial endpoints and provenance.

    Each segment has entry/exit nodes and a priced traversal edge. Connections
    cost zero. Separate query nodes allow an upstream destination on the same
    segment to be reached through a legal loop rather than by driving backwards.
    """
    if config is not None and not isinstance(config, dict):
        raise PlanningError("config must be a JSON object")
    config = json.loads(json.dumps(DEFAULT_CONFIG if config is None else config))
    segments = validate_inputs(catalog, forecast, trip, config, require_verified_limits)
    if mode not in ("naive", "cautious", "risk-aware"):
        raise PlanningError(f"unknown mode: {mode}")
    trip = json.loads(json.dumps(trip))
    if mode != "risk-aware":
        trip["risk_weight"] = 0.0
    risk_weight = trip["risk_weight"]
    graph = nx.DiGraph()
    source, target = ("query", "start"), ("query", "end")

    def traversal(a, b, sid, start, end):
        priced = best_price(end - start, segments[sid], forecast["segments"][sid], risk_weight, config)
        step = {"segment_id": sid, "start_offset_m": start, "end_offset_m": end, **priced}
        graph.add_edge(a, b, weight=priced["objective"], step=step)

    # Sorted insertion makes equal-cost choices repeatable across JSON orderings.
    for sid in sorted(segments):
        traversal((sid, "in"), (sid, "out"), sid, 0.0, segments[sid]["length_m"])
        for successor in sorted(set(segments[sid]["successors"])):
            graph.add_edge((sid, "out"), (successor, "in"), weight=0.0)
    origin, destination = trip["origin"], trip["destination"]
    first, last = origin["segment_id"], destination["segment_id"]
    traversal(source, (first, "out"), first, origin["offset_m"], segments[first]["length_m"])
    traversal((last, "in"), target, last, 0.0, destination["offset_m"])
    if first == last and destination["offset_m"] >= origin["offset_m"]:
        traversal(source, target, first, origin["offset_m"], destination["offset_m"])
    try:
        path = nx.dijkstra_path(graph, source, target, weight="weight")
    except nx.NetworkXNoPath as error:
        raise PlanningError("no legal route from origin to destination") from error
    steps = [graph[a][b]["step"] for a, b in zip(path, path[1:])
             if "step" in graph[a][b] and graph[a][b]["step"]["distance_m"] > 1e-9]
    if mode == "cautious":
        # Keep the naive route; changing the cap must not change its route search.
        for step in steps:
            sid = step["segment_id"]
            speed = min(config["cautious_speed_kmh"], segments[sid]["speed_limit_kmh"])
            step.update(price(step["distance_m"], speed, forecast["segments"][sid], 0.0, config))
    return {
        "schema_version": 1, "mode": mode, "catalog_id": catalog["catalog_id"],
        "catalog_hash": fingerprint(catalog), "forecast_id": forecast["forecast_id"],
        "forecast_hash": fingerprint(forecast), "config_hash": fingerprint(config),
        "config": config, "trip": trip, "segments": steps,
        "estimated_time_s": sum(s["estimated_time_s"] for s in steps),
        "predicted_penalty": sum(s["predicted_penalty"] for s in steps),
        "objective": sum(s["objective"] for s in steps),
        "speed_limits_verified": all(segments[s["segment_id"]].get("speed_limit_verified") is True
                                     for s in steps),
        "forecast_source": forecast.get("source", "unspecified"),
    }
