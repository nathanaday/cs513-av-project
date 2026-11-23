"""Route and speed search over a world road graph and its hazard forecast.

The planner reads the forecast on the graph and nothing else. It never sees the
hazards rolled for a run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ...core.models.world_hazard_library import LOW_VISIBILITY
from ...core.models.world_road_graph import SegmentPosition, WorldRoadGraph
from ...core.utilities.mapview import (
    THEME,
    draw_lanes,
    hue_ramp,
    matplotlib_tools,
    scale_bar,
    series_color,
    style_chart,
    style_map,
)
from ...core.utilities.sun import expected_visibility_loss
from .models.planner_computed_waypoints import PlannerComputedWaypoints, RouteStep
from .models.planner_config import PlannerConfig
from .models.route_mode import RouteMode
from .utilities import (
    PlanningError,
    build_edges,
    cheapest_path,
    check_config,
    check_limits_verified,
    check_number,
    check_position,
    price_step,
)

if TYPE_CHECKING:
    from matplotlib.figure import Figure

SHORTEST_STEP_M = 1e-9


class Planner:
    @staticmethod
    def hazard_scores(graph: WorldRoadGraph, config: PlannerConfig | None = None) -> dict[str, float]:
        """Reduce the forecast to one weighted number per segment, which is all the pricing reads.

        A segment's score adds each event's chance per second there, the
        expected visibility loss on that lane, and the expected severity of
        every other condition, each times its weight.

        Args:
            graph: The world, with its forecast.
            config: The tuning, for the weights. Defaults to `PlannerConfig()`.

        Returns:
            The score by segment id.
        """
        config = config or PlannerConfig()
        visibility_loss = expected_visibility_loss(graph)
        everywhere = 0.0
        for hazard_id, forecast in graph.conditions.items():
            if hazard_id != LOW_VISIBILITY:
                everywhere += config.weight(hazard_id) * forecast.expected_severity()
        scores = {}
        for sid, segment in graph.segments.items():
            events = sum(config.weight(item.hazard_id) * item.probability for item in segment.hazard_probabilities)
            scores[sid] = everywhere + config.weight(LOW_VISIBILITY) * visibility_loss[sid] + events
        return scores

    @staticmethod
    def route(origin: SegmentPosition, destination: SegmentPosition, graph: WorldRoadGraph, *,
              risk_scale: float = 1.0, mode: RouteMode | str = RouteMode.RISK_AWARE,
              config: PlannerConfig | None = None, require_verified_limits: bool = False) -> PlannerComputedWaypoints:
        """Choose the segments to drive and a target speed on each.

        Args:
            origin: Where the route starts.
            destination: Where the route ends.
            graph: The world, with its forecast.
            risk_scale: The weight of the predicted penalty against time, in
                the risk-aware mode. The other modes ignore it.
            mode: How the route is chosen. See `RouteMode`.
            config: The tuning. Defaults to `PlannerConfig()`.
            require_verified_limits: Whether to refuse a graph with a speed
                limit that was not read from the simulator.

        Returns:
            The route, with a target speed on each stretch.

        Raises:
            PlanningError: If an input is invalid, or no legal route exists.
        """
        config = config or PlannerConfig()
        mode = _route_mode(mode)
        check_number(risk_scale, "risk scale")
        check_position(origin, "origin", graph)
        check_position(destination, "destination", graph)
        check_config(config)
        if require_verified_limits:
            check_limits_verified(graph)

        if mode is not RouteMode.RISK_AWARE:
            risk_scale = 0.0
        scores = Planner.hazard_scores(graph, config)
        edges = build_edges(graph, origin, destination, scores, risk_scale, config)
        steps = [step for step in cheapest_path(edges) if step.distance_m > SHORTEST_STEP_M]
        if mode is RouteMode.CAUTIOUS:
            # Capping the speed after the search keeps the cautious route on the naive route.
            steps = [_capped(step, graph, config) for step in steps]
        return PlannerComputedWaypoints(
            graph_id=graph.graph_id,
            forecast_hash=graph.forecast_hash(),
            origin=origin,
            destination=destination,
            mode=mode,
            risk_scale=float(risk_scale),
            config=config,
            steps=tuple(steps),
        )

    @staticmethod
    def view_routes(graph: WorldRoadGraph, routes: PlannerComputedWaypoints | Iterable[PlannerComputedWaypoints], *,
                    show_junctions: bool = True) -> Figure:
        """Draw one map per route, shaded by target speed, and every route's speed along its distance.

        A and B mark the origin and the destination. Segments where an event
        is forecast carry a wide pale band.

        Args:
            graph: The world the routes were planned on.
            routes: One route, or several to compare.
            show_junctions: Whether to outline each junction's bounding box.

        Returns:
            The figure.

        Raises:
            PlanningError: If there is no route, or one was planned on another map.
        """
        pyplot, tools = matplotlib_tools("view_routes")
        routes = [routes] if isinstance(routes, PlannerComputedWaypoints) else list(routes)
        if not routes:
            raise PlanningError("no routes to draw")
        for route in routes:
            if route.graph_id != graph.graph_id:
                raise PlanningError("a route was planned on a different map")
        fastest = max(graph.segments[step.segment_id].speed_limit_kmh for route in routes for step in route.steps)
        ramp = tools.LinearSegmentedColormap.from_list("speed", hue_ramp(0))
        scale = tools.Normalize(vmin=0.0, vmax=fastest)

        figure = pyplot.figure(figsize=(6.5 * len(routes), 10.6), dpi=130, facecolor=THEME.surface,
                               layout="constrained")
        # Rows: the maps, the keys, and one speed chart across the figure.
        grid = figure.add_gridspec(3, len(routes), height_ratios=(7.6, 0.16, 2.2))
        for column, route in enumerate(routes):
            axes = figure.add_subplot(grid[0, column])
            _draw_route_map(axes, graph, route, ramp, scale, show_junctions, tools)
        scale_bar(figure, figure.add_subplot(grid[1, 0]), scale, ramp, "target speed (km/h)", tools, own_axes=True)
        if len(routes) > 1:
            _draw_event_key(figure.add_subplot(grid[1, 1]), tools)
        _draw_speed_profiles(figure.add_subplot(grid[2, :]), graph, routes, fastest)
        figure.suptitle(f"{graph.map_name}: planned route from A to B", x=0.02, ha="left", fontsize=14,
                        color=THEME.ink)
        return figure


def _route_mode(mode: RouteMode | str) -> RouteMode:
    try:
        return RouteMode(mode)
    except ValueError:
        known = ", ".join(known_mode.value for known_mode in RouteMode)
        raise PlanningError(f"unknown mode: {mode}; use one of {known}") from None


def _capped(step: RouteStep, graph: WorldRoadGraph, config: PlannerConfig) -> RouteStep:
    """The same stretch, priced again at the cautious speed or the segment's limit, whichever is lower."""
    segment = graph.segments[step.segment_id]
    speed_kmh = min(config.cautious_speed_kmh, segment.speed_limit_kmh)
    return price_step(segment, step.start_offset_m, step.end_offset_m, speed_kmh, step.hazard_score, config)


def _route_name(route: PlannerComputedWaypoints) -> str:
    if route.mode is RouteMode.RISK_AWARE:
        return f"risk-aware, risk scale {route.risk_scale:g}"
    return route.mode.value


def _draw_route_map(axes, graph: WorldRoadGraph, route: PlannerComputedWaypoints, ramp, scale,
                    show_junctions: bool, tools) -> None:
    draw_lanes(axes, graph, {}, ramp, scale, show_junctions, tools)
    for segment in graph.get_segments():
        if segment.hazard_probabilities:
            axes.plot([point.x for point in segment.centerline], [point.y for point in segment.centerline],
                      color=THEME.grid, linewidth=7.0, solid_capstyle="round", zorder=0.5)
    for step in route.steps:
        points = graph.segments[step.segment_id].points_between(step.start_offset_m, step.end_offset_m)
        axes.plot([point[0] for point in points], [point[1] for point in points],
                  color=ramp(scale(step.target_speed_kmh)), linewidth=3.4, solid_capstyle="round", zorder=3)
    for name, position in (("A", route.origin), ("B", route.destination)):
        x, y, _ = graph.get_segment(position.segment_id).point_at(position.offset_m)
        axes.scatter([x], [y], s=210, color=THEME.ink, edgecolors=THEME.surface, linewidths=1.6, zorder=5)
        axes.text(x, y, name, color=THEME.surface, fontsize=9, fontweight="bold", ha="center", va="center", zorder=6)
    style_map(axes, _route_name(route), [
        f"{route.estimated_time_s:.0f} s · {route.distance_m:.0f} m · {len(route.steps)} segments",
        f"predicted penalty {route.predicted_penalty:.1f}",
    ])


def _draw_event_key(axes, tools) -> None:
    band = tools.Line2D([], [], color=THEME.grid, linewidth=7.0, label="segment with an event forecast")
    axes.axis("off")
    axes.legend(handles=[band], loc="center", frameon=False, fontsize=9, labelcolor=THEME.ink_secondary)


def _draw_speed_profiles(axes, graph: WorldRoadGraph, routes: list[PlannerComputedWaypoints],
                         fastest_kmh: float) -> None:
    """Draw each route's target speed, and its speed limit, against the distance along the route."""
    style_chart(axes)
    for index, route in enumerate(routes):
        distances = []
        speeds = []
        limits = []
        travelled = 0.0
        for step in route.steps:
            distances += [travelled, travelled + step.distance_m]
            speeds += [step.target_speed_kmh] * 2
            limits += [graph.segments[step.segment_id].speed_limit_kmh] * 2
            travelled += step.distance_m
        axes.plot(distances, limits, color=THEME.axis, linewidth=1.0, linestyle="--", zorder=1,
                  label="speed limit" if index == 0 else None)
        axes.plot(distances, speeds, color=series_color(index), linewidth=2.0, zorder=2 + index,
                  label=_route_name(route))
    axes.set_ylim(0, fastest_kmh * 1.15)
    axes.set_xlim(0, None)
    axes.set_xlabel("distance along the route (m)", color=THEME.ink_secondary)
    axes.set_ylabel("target speed (km/h)", color=THEME.ink_secondary)
    axes.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=len(routes) + 1, frameon=False,
                fontsize=9, labelcolor=THEME.ink_secondary)
