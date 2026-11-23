"""Private helpers of the planner module: input checks, pricing, and the route search.

The search runs over nodes. Each segment has an entry node and an exit node
joined by a priced edge, and a connection from one segment to the next costs
nothing. Separate start and end nodes let a destination behind the origin on
the same segment be reached through a legal loop.
"""

from __future__ import annotations

import heapq
import math

from ...core.models.world_road_graph import RoadSegment, SegmentPosition, WorldRoadGraph
from .models.planner_computed_waypoints import RouteStep
from .models.planner_config import PlannerConfig

Node = tuple[str, str]
Edge = tuple[Node, float, "RouteStep | None"]

START: Node = ("query", "start")
END: Node = ("query", "end")
OFFSET_TOLERANCE_M = 1e-6


class PlanningError(ValueError):
    """Invalid input, or no legal route from the origin to the destination."""


def check_number(value: object, name: str, *, positive: bool = False) -> None:
    """Check that a value is a finite number of 0 or more, or above 0 with `positive`.

    Raises:
        PlanningError: If it is not.
    """
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not is_number or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise PlanningError(f"invalid {name}: {value!r}")


def check_position(position: SegmentPosition, name: str, graph: WorldRoadGraph) -> None:
    if position.segment_id not in graph.segments:
        raise PlanningError(f"unknown {name} segment: {position.segment_id}")
    check_number(position.offset_m, f"{name} offset")
    if position.offset_m > graph.segments[position.segment_id].length_m + OFFSET_TOLERANCE_M:
        raise PlanningError(f"{name} offset is past the end of {position.segment_id}")


def check_config(config: PlannerConfig) -> None:
    if not config.candidate_speeds_kmh:
        raise PlanningError("the configuration needs at least one candidate speed")
    for speed in config.candidate_speeds_kmh:
        check_number(speed, "candidate speed", positive=True)
    check_number(config.reference_speed_kmh, "reference speed", positive=True)
    check_number(config.cautious_speed_kmh, "cautious speed", positive=True)
    check_number(config.exposure_baseline, "exposure baseline")
    for hazard_id, value in config.weights.items():
        check_number(value, f"weight of {hazard_id}")


def check_limits_verified(graph: WorldRoadGraph) -> None:
    unverified = sorted(sid for sid, segment in graph.segments.items() if not segment.speed_limit_verified)
    if unverified:
        raise PlanningError(f"speed limit is not verified: {unverified[0]}")


def price_step(segment: RoadSegment, start_m: float, end_m: float, speed_kmh: float, hazard_score: float,
               config: PlannerConfig) -> RouteStep:
    """Price one stretch of a segment at one speed.

    The penalty accrues per second at the hazard score times
    (exposure baseline + (speed / reference speed) squared).
    """
    duration_s = (end_m - start_m) / (speed_kmh / 3.6)
    speed_ratio = speed_kmh / config.reference_speed_kmh
    penalty_rate = hazard_score * (config.exposure_baseline + speed_ratio ** 2)
    return RouteStep(segment.id, start_m, end_m, speed_kmh, duration_s, penalty_rate * duration_s, hazard_score)


def cheapest_step(segment: RoadSegment, start_m: float, end_m: float, hazard_score: float, risk_scale: float,
                  config: PlannerConfig) -> RouteStep:
    """Price a stretch at its cheapest speed. Equal costs prefer the shorter time, then the higher speed."""
    limit = segment.speed_limit_kmh
    speeds = {limit}
    for speed in config.candidate_speeds_kmh:
        if speed <= limit:
            speeds.add(speed)

    def preference(step: RouteStep) -> tuple[float, float, float]:
        cost = step.estimated_time_s + risk_scale * step.predicted_penalty
        return cost, step.estimated_time_s, -step.target_speed_kmh

    choices = [price_step(segment, start_m, end_m, speed, hazard_score, config) for speed in sorted(speeds)]
    return min(choices, key=preference)


def build_edges(graph: WorldRoadGraph, origin: SegmentPosition, destination: SegmentPosition,
                scores: dict[str, float], risk_scale: float, config: PlannerConfig) -> dict[Node, list[Edge]]:
    """Build the search graph for one query.

    Returns:
        For each node, its outgoing edges as (next node, cost, the priced step
        or None for a free connection).
    """
    edges: dict[Node, list[Edge]] = {}

    def add_stretch(here: Node, there: Node, sid: str, start_m: float, end_m: float) -> None:
        step = cheapest_step(graph.segments[sid], start_m, end_m, scores[sid], risk_scale, config)
        cost = step.estimated_time_s + risk_scale * step.predicted_penalty
        edges.setdefault(here, []).append((there, cost, step))

    # Sorted insertion makes equal-cost choices repeatable.
    for sid in sorted(graph.segments):
        segment = graph.segments[sid]
        add_stretch((sid, "in"), (sid, "out"), sid, 0.0, segment.length_m)
        for successor in sorted(set(segment.successors)):
            edges.setdefault((sid, "out"), []).append(((successor, "in"), 0.0, None))

    first = origin.segment_id
    last = destination.segment_id
    add_stretch(START, (first, "out"), first, origin.offset_m, graph.segments[first].length_m)
    add_stretch((last, "in"), END, last, 0.0, destination.offset_m)
    if first == last and destination.offset_m >= origin.offset_m:
        add_stretch(START, END, first, origin.offset_m, destination.offset_m)
    return edges


def cheapest_path(edges: dict[Node, list[Edge]]) -> list[RouteStep]:
    """Find the cheapest path from the start node to the end node, by Dijkstra's algorithm.

    Returns:
        The priced steps on the path, in driving order.

    Raises:
        PlanningError: If the end cannot be reached.
    """
    best_cost = {START: 0.0}
    arrived_by: dict[Node, tuple[Node, RouteStep | None]] = {}
    # The counter breaks ties between equal costs in the order nodes were found.
    queue = [(0.0, 0, START)]
    counter = 1
    done = set()
    while queue:
        cost, _, node = heapq.heappop(queue)
        if node in done:
            continue
        done.add(node)
        if node == END:
            break
        for neighbor, edge_cost, step in edges.get(node, ()):
            reached = cost + edge_cost
            if reached < best_cost.get(neighbor, math.inf):
                best_cost[neighbor] = reached
                arrived_by[neighbor] = (node, step)
                heapq.heappush(queue, (reached, counter, neighbor))
                counter += 1
    if END not in arrived_by:
        raise PlanningError("no legal route from the origin to the destination")

    steps = []
    node = END
    while node != START:
        node, step = arrived_by[node]
        if step is not None:
            steps.append(step)
    steps.reverse()
    return steps
