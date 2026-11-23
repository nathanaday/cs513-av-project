"""The pieces of the planner's figure: the route maps and the speed chart."""

from __future__ import annotations

from ...core.models.world_road_graph import WorldRoadGraph
from ..planner.models.planner_computed_waypoints import PlannerComputedWaypoints
from ..planner.models.route_mode import RouteMode
from .utilities import THEME, draw_lanes, series_color, style_chart, style_map


def route_name(route: PlannerComputedWaypoints) -> str:
    if route.mode is RouteMode.RISK_AWARE:
        return f"risk-aware, risk scale {route.risk_scale:g}"
    return route.mode.value


def draw_route_map(axes, graph: WorldRoadGraph, route: PlannerComputedWaypoints, ramp, scale,
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
    style_map(axes, route_name(route), [
        f"{route.estimated_time_s:.0f} s · {route.distance_m:.0f} m · {len(route.steps)} segments",
        f"predicted penalty {route.predicted_penalty:.1f}",
    ])


def draw_event_key(axes, tools) -> None:
    band = tools.Line2D([], [], color=THEME.grid, linewidth=7.0, label="segment with an event forecast")
    axes.axis("off")
    axes.legend(handles=[band], loc="center", frameon=False, fontsize=9, labelcolor=THEME.ink_secondary)


def draw_speed_profiles(axes, graph: WorldRoadGraph, routes: list[PlannerComputedWaypoints],
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
                  label=route_name(route))
    axes.set_ylim(0, fastest_kmh * 1.15)
    axes.set_xlim(0, None)
    axes.set_xlabel("distance along the route (m)", color=THEME.ink_secondary)
    axes.set_ylabel("target speed (km/h)", color=THEME.ink_secondary)
    axes.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=len(routes) + 1, frameon=False,
                fontsize=9, labelcolor=THEME.ink_secondary)
