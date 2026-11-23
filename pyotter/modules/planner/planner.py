"""Route and speed search over a world road graph and its hazard forecast.

The planner reads the forecast on the graph and nothing else. It never sees the
hazards rolled for a run.
"""

from __future__ import annotations

import heapq
import math
from typing import TYPE_CHECKING, Iterable

from ...core.models.world_hazard_library import LOW_VISIBILITY
from ...core.models.world_road_graph import RoadSegment, SegmentPosition, WorldRoadGraph
from ...core.utilities.mapview import (
    AXIS, GRID, INK, INK_MUTED, INK_SECONDARY, SURFACE, draw_lanes, hue_ramp, matplotlib_tools, scale_bar, style_map,
)
from ...core.utilities.sun import expected_visibility_loss
from .models.planner_computed_waypoints import PlannerComputedWaypoints, RouteStep
from .models.planner_config import PlannerConfig

if TYPE_CHECKING:
    from matplotlib.figure import Figure

MODES = ("risk-aware", "naive", "cautious")
ROUTE_COLORS = ("#2a78d6", "#eb6834", "#1baf7a")


class PlanningError(ValueError):
    """Invalid input, or no legal route from the origin to the destination."""


class Planner:
    @staticmethod
    def hazard_scores(graph: WorldRoadGraph, config: PlannerConfig | None = None) -> dict[str, float]:
        """The forecast as one weighted number per segment, which is all the pricing reads.

        It adds each event's chance per second on the segment, the expected
        visibility loss on that lane, and the expected severity of every other
        condition, each times its weight.
        """
        config = config or PlannerConfig()
        visibility = expected_visibility_loss(graph)
        everywhere = sum(config.weight(hazard_id) * forecast.expected_severity()
                         for hazard_id, forecast in graph.conditions.items() if hazard_id != LOW_VISIBILITY)
        return {
            sid: everywhere + config.weight(LOW_VISIBILITY) * visibility[sid]
            + sum(config.weight(item.hazard_id) * item.probability for item in segment.hazard_probabilities)
            for sid, segment in graph.segments.items()
        }

    @staticmethod
    def route(origin: SegmentPosition, destination: SegmentPosition, graph: WorldRoadGraph, *,
              risk_scale: float = 1.0, mode: str = "risk-aware", config: PlannerConfig | None = None,
              require_verified_limits: bool = False) -> PlannerComputedWaypoints:
        """Choose the segments to drive and a target speed on each.

        `risk-aware` minimizes time plus `risk_scale` times the predicted
        penalty. `naive` takes the quickest route at the speed limits.
        `cautious` keeps the naive route and caps its speed.

        Each segment has an entry and an exit node joined by a priced edge, and
        connections cost nothing. Separate start and end nodes let a destination
        behind the origin on the same segment be reached through a legal loop.
        """
        config = config or PlannerConfig()
        _check_inputs(origin, destination, graph, risk_scale, mode, config, require_verified_limits)
        weight = risk_scale if mode == "risk-aware" else 0.0
        scores = Planner.hazard_scores(graph, config)
        edges: dict[tuple, list[tuple[tuple, float, RouteStep | None]]] = {}
        source, target = ("query", "start"), ("query", "end")

        def traversal(a: tuple, b: tuple, sid: str, start: float, end: float) -> None:
            step = _best_step(graph.segments[sid], start, end, scores[sid], weight, config)
            cost = step.estimated_time_s + weight * step.predicted_penalty
            edges.setdefault(a, []).append((b, cost, step))

        # Sorted insertion makes equal-cost choices repeatable.
        for sid in sorted(graph.segments):
            segment = graph.segments[sid]
            traversal((sid, "in"), (sid, "out"), sid, 0.0, segment.length_m)
            for successor in sorted(set(segment.successors)):
                edges.setdefault((sid, "out"), []).append(((successor, "in"), 0.0, None))
        first, last = origin.segment_id, destination.segment_id
        traversal(source, (first, "out"), first, origin.offset_m, graph.segments[first].length_m)
        traversal((last, "in"), target, last, 0.0, destination.offset_m)
        if first == last and destination.offset_m >= origin.offset_m:
            traversal(source, target, first, origin.offset_m, destination.offset_m)

        steps = [step for step in _cheapest_path(edges, source, target) if step.distance_m > 1e-9]
        if mode == "cautious":
            # Keep the naive route; the cap must not change the route search.
            steps = [_step(graph.segments[s.segment_id], s.start_offset_m, s.end_offset_m,
                           min(config.cautious_speed_kmh, graph.segments[s.segment_id].speed_limit_kmh),
                           s.hazard_score, config) for s in steps]
        return PlannerComputedWaypoints(graph.graph_id, graph.forecast_hash(), origin, destination, mode,
                                        float(weight), config, tuple(steps))

    @staticmethod
    def view_routes(graph: WorldRoadGraph, routes: PlannerComputedWaypoints | Iterable[PlannerComputedWaypoints], *,
                    show_junctions: bool = True) -> Figure:
        """Draw one map per route, shaded by target speed, and every route's speed along its distance.

        A and B mark the origin and the destination. The wide pale band marks
        segments where an event is forecast.
        """
        pyplot, tools = matplotlib_tools("view_routes")
        routes = [routes] if isinstance(routes, PlannerComputedWaypoints) else list(routes)
        if not routes:
            raise PlanningError("no routes to draw")
        for route in routes:
            if route.graph_id != graph.graph_id:
                raise PlanningError("a route was planned on a different map")
        fastest = max(graph.segments[s.segment_id].speed_limit_kmh for route in routes for s in route.steps)
        ramp = tools.LinearSegmentedColormap.from_list("speed", hue_ramp(0))
        scale = tools.Normalize(vmin=0.0, vmax=fastest)
        eventful = [segment for segment in graph.get_segments() if segment.hazard_probabilities]

        figure = pyplot.figure(figsize=(6.5 * len(routes), 10.6), dpi=130, facecolor=SURFACE, layout="constrained")
        grid = figure.add_gridspec(3, len(routes), height_ratios=(7.6, 0.16, 2.2))
        for column, route in enumerate(routes):
            axes = figure.add_subplot(grid[0, column])
            draw_lanes(axes, graph, {}, ramp, scale, show_junctions, tools)
            for segment in eventful:
                axes.plot([p.x for p in segment.centerline], [p.y for p in segment.centerline],
                          color=GRID, linewidth=7.0, solid_capstyle="round", zorder=0.5)
            for step in route.steps:
                points = graph.segments[step.segment_id].points_between(step.start_offset_m, step.end_offset_m)
                axes.plot([p[0] for p in points], [p[1] for p in points], color=ramp(scale(step.target_speed_kmh)),
                          linewidth=3.4, solid_capstyle="round", zorder=3)
            for name, position in (("A", route.origin), ("B", route.destination)):
                x, y, _ = graph.get_segment(position.segment_id).point_at(position.offset_m)
                axes.scatter([x], [y], s=210, color=INK, edgecolors=SURFACE, linewidths=1.6, zorder=5)
                axes.text(x, y, name, color=SURFACE, fontsize=9, fontweight="bold", ha="center", va="center", zorder=6)
            style_map(axes, _name(route), [
                f"{route.estimated_time_s:.0f} s · {route.distance_m:.0f} m · {len(route.steps)} segments",
                f"predicted penalty {route.predicted_penalty:.1f}",
            ])
        keys = figure.add_subplot(grid[1, 0])
        scale_bar(figure, keys, scale, ramp, "target speed (km/h)", tools, own_axes=True)
        if len(routes) > 1:
            note = figure.add_subplot(grid[1, 1])
            note.axis("off")
            note.legend(handles=[tools.Line2D([], [], color=GRID, linewidth=7.0, label="segment with an event forecast")],
                        loc="center", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)

        profile = figure.add_subplot(grid[2, :])
        profile.set_facecolor(SURFACE)
        for index, route in enumerate(routes):
            color = ROUTE_COLORS[index] if index < len(ROUTE_COLORS) else INK_MUTED
            distances, speeds, limits, travelled = [], [], [], 0.0
            for step in route.steps:
                distances += [travelled, travelled + step.distance_m]
                speeds += [step.target_speed_kmh] * 2
                limits += [graph.segments[step.segment_id].speed_limit_kmh] * 2
                travelled += step.distance_m
            profile.plot(distances, limits, color=AXIS, linewidth=1.0, linestyle="--", zorder=1,
                         label="speed limit" if index == 0 else None)
            profile.plot(distances, speeds, color=color, linewidth=2.0, zorder=2 + index, label=_name(route))
        profile.set_ylim(0, fastest * 1.15)
        profile.set_xlim(0, None)
        profile.set_xlabel("distance along the route (m)", color=INK_SECONDARY)
        profile.set_ylabel("target speed (km/h)", color=INK_SECONDARY)
        profile.tick_params(colors=INK_MUTED, labelsize=8)
        profile.grid(True, axis="y", linewidth=0.4, color=GRID)
        for name, spine in profile.spines.items():
            spine.set_visible(name in ("left", "bottom"))
            spine.set_color(AXIS)
        profile.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=len(routes) + 1, frameon=False,
                       fontsize=9, labelcolor=INK_SECONDARY)
        figure.suptitle(f"{graph.map_name}: planned route from A to B", x=0.02, ha="left", fontsize=14, color=INK)
        return figure


def _name(route: PlannerComputedWaypoints) -> str:
    return f"risk-aware, risk scale {route.risk_scale:g}" if route.mode == "risk-aware" else route.mode


def _number(value, name: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or value < 0 or (positive and value == 0):
        raise PlanningError(f"invalid {name}: {value!r}")


def _check_inputs(origin: SegmentPosition, destination: SegmentPosition, graph: WorldRoadGraph, risk_scale: float,
                  mode: str, config: PlannerConfig, require_verified_limits: bool) -> None:
    if mode not in MODES:
        raise PlanningError(f"unknown mode: {mode}; use one of {', '.join(MODES)}")
    _number(risk_scale, "risk scale")
    for name, position in (("origin", origin), ("destination", destination)):
        if position.segment_id not in graph.segments:
            raise PlanningError(f"unknown {name} segment: {position.segment_id}")
        _number(position.offset_m, f"{name} offset")
        if position.offset_m > graph.segments[position.segment_id].length_m + 1e-6:
            raise PlanningError(f"{name} offset is past the end of {position.segment_id}")
    if not config.candidate_speeds_kmh:
        raise PlanningError("the configuration needs at least one candidate speed")
    for speed in config.candidate_speeds_kmh:
        _number(speed, "candidate speed", positive=True)
    _number(config.reference_speed_kmh, "reference speed", positive=True)
    _number(config.cautious_speed_kmh, "cautious speed", positive=True)
    _number(config.exposure_baseline, "exposure baseline")
    for hazard_id, value in config.weights.items():
        _number(value, f"weight of {hazard_id}")
    if require_verified_limits:
        unverified = sorted(sid for sid, segment in graph.segments.items() if not segment.speed_limit_verified)
        if unverified:
            raise PlanningError(f"speed limit is not verified: {unverified[0]}")


def _step(segment: RoadSegment, start: float, end: float, speed_kmh: float, hazard_score: float,
          config: PlannerConfig) -> RouteStep:
    """Price one stretch at one speed: the penalty rate is the hazard score times (baseline + speed ratio squared)."""
    duration = (end - start) / (speed_kmh / 3.6)
    rate = hazard_score * (config.exposure_baseline + (speed_kmh / config.reference_speed_kmh) ** 2)
    return RouteStep(segment.id, start, end, speed_kmh, duration, rate * duration, hazard_score)


def _best_step(segment: RoadSegment, start: float, end: float, hazard_score: float, risk_scale: float,
               config: PlannerConfig) -> RouteStep:
    """The cheapest speed for a stretch. Equal costs prefer the shorter time, then the higher speed."""
    limit = segment.speed_limit_kmh
    speeds = sorted({limit, *(v for v in config.candidate_speeds_kmh if v <= limit)})
    choices = [_step(segment, start, end, speed, hazard_score, config) for speed in speeds]
    return min(choices, key=lambda s: (s.estimated_time_s + risk_scale * s.predicted_penalty,
                                       s.estimated_time_s, -s.target_speed_kmh))


def _cheapest_path(edges: dict, source: tuple, target: tuple) -> list[RouteStep]:
    """Dijkstra over nonnegative edge costs. Returns the steps on the cheapest path."""
    best = {source: 0.0}
    arrived_by: dict[tuple, tuple[tuple, RouteStep | None]] = {}
    queue, order, done = [(0.0, 0, source)], 1, set()
    while queue:
        cost, _, node = heapq.heappop(queue)
        if node in done:
            continue
        done.add(node)
        if node == target:
            break
        for neighbor, edge_cost, step in edges.get(node, ()):
            reached = cost + edge_cost
            if reached < best.get(neighbor, math.inf):
                best[neighbor] = reached
                arrived_by[neighbor] = (node, step)
                heapq.heappush(queue, (reached, order, neighbor))
                order += 1
    if target not in arrived_by:
        raise PlanningError("no legal route from the origin to the destination")
    steps, node = [], target
    while node != source:
        node, step = arrived_by[node]
        if step is not None:
            steps.append(step)
    return steps[::-1]
