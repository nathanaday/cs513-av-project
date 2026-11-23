"""Every figure pyotter draws: the map, the forecast, a roll, planned routes, and the signals of driven runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ...core.models.world_hazard_library import LOW_VISIBILITY, HazardKind, WorldHazardLibrary
from ...core.models.world_road_graph import RoadGraphError, WorldRoadGraph
from ...core.models.driving_safety_req import DrivingSafetyReq
from ..driver.driver import Driver
from ..driver.models.driving_scenario_telemetry import DrivingScenarioTelemetry, Signal
from ..planner.models.planner_computed_waypoints import PlannerComputedWaypoints
from ..planner.planner import PlanningError
from ..world.models.world_hazard_spawns import WorldHazardSpawns
from .driver_drawing import (
    checked_runs,
    collision_times,
    draw_legend,
    draw_limit,
    draw_requirement,
    draw_series,
    fit_values,
    gaps_m,
    speed_limits_kmh,
    speeds_kmh,
    time_chart,
)
from .planner_drawing import draw_event_key, draw_route_map, draw_speed_profiles
from .utilities import THEME, draw_lanes, hue_ramp, matplotlib_tools, scale_bar, series_color, style_map
from .world_drawing import (
    draw_condition,
    draw_event_starts,
    draw_junction_boxes,
    draw_lane_with_arrow,
    draw_sun_arrow,
    draw_timeline,
    forecast_map,
    label_anchor,
    shown_hazards,
)

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class Visualize:
    @staticmethod
    def topology(graph: WorldRoadGraph, *, label_segments: bool = False, show_junctions: bool = True) -> Figure:
        """Draw the graph from above, in meters.

        Args:
            graph: The map.
            label_segments: Whether to make the figure larger and write each
                lane's segment id on it.
            show_junctions: Whether to outline each junction's bounding box and
                tag it with its id.

        Returns:
            The figure. Call `.savefig(path)` on it, or `pyplot.show()`.
        """
        pyplot, tools = matplotlib_tools("Visualize.topology")
        settings = THEME.topology
        size = settings.labelled_size_in if label_segments else settings.size_in
        dpi = settings.labelled_dpi if label_segments else settings.dpi
        figure, axes = pyplot.subplots(figsize=(size, size), dpi=dpi)
        if show_junctions:
            draw_junction_boxes(axes, graph, tools)
        placed_labels: list[tuple[float, float]] = []
        for segment in graph.get_segments():
            color = "tab:orange" if segment.in_junction else "tab:blue"
            draw_lane_with_arrow(axes, segment, color)
            if label_segments:
                x, y, angle = label_anchor(segment, placed_labels)
                axes.text(x, y, segment.id, fontsize=5.5, color=color, ha="center", va="center",
                          rotation=angle, rotation_mode="anchor",
                          bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.4, "alpha": 0.85})
        axes.plot([], [], color="tab:blue", label="road lane")
        axes.plot([], [], color="tab:orange", label="junction lane")
        if show_junctions and graph.junctions:
            axes.plot([], [], color="0.4", linestyle="--", linewidth=0.9, label="junction bounds")
        axes.legend(loc="upper right")
        axes.set_aspect("equal")
        axes.invert_yaxis()  # CARLA's frame is left-handed: +y is to the right of +x
        axes.set_xlabel("x (m)")
        axes.set_ylabel("y (m)")
        axes.set_title(graph.map_name)
        axes.grid(True, linewidth=0.3)
        return figure

    @staticmethod
    def hazards(graph: WorldRoadGraph, library: WorldHazardLibrary, *, show_junctions: bool = True) -> Figure:
        """Draw the forecast: one map per hazard, each with its own hue and scale.

        An event's map shades each segment by its chance per second. A
        condition's map shades the world by expected severity. The visibility
        map adds the low sun, lane by lane, by how directly each lane faces it.

        Args:
            graph: The world, with its forecast.
            library: The hazards the forecast may name.
            show_junctions: Whether to outline each junction's bounding box.

        Returns:
            The figure.

        Raises:
            RoadGraphError: If the forecast is empty or disagrees with the library.
        """
        pyplot, tools = matplotlib_tools("Visualize.hazards")
        hazards = shown_hazards(graph, library)
        figure, axes_row = pyplot.subplots(1, len(hazards), figsize=(6.5 * len(hazards), 7.6), dpi=130,
                                           squeeze=False, facecolor=THEME.surface, layout="constrained")
        for axes, (index, hazard) in zip(axes_row[0], hazards):
            shown = forecast_map(graph, hazard)
            ramp = tools.LinearSegmentedColormap.from_list(hazard.id, hue_ramp(index))
            scale = tools.Normalize(vmin=0.0, vmax=shown.top)
            draw_lanes(axes, graph, shown.values, ramp, scale, show_junctions, tools)
            if hazard.id == LOW_VISIBILITY:
                draw_sun_arrow(axes, graph.time_of_day_h)
            style_map(axes, hazard.id, shown.lines)
            scale_bar(figure, axes, scale, ramp, shown.unit, tools)
        figure.suptitle(f"{graph.map_name}: hazard forecast", x=0.02, ha="left", fontsize=14, color=THEME.ink)
        return figure

    @staticmethod
    def spawns(graph: WorldRoadGraph, library: WorldHazardLibrary, spawns: WorldHazardSpawns, *,
               show_junctions: bool = True) -> Figure:
        """Draw what a roll produced: one map per hazard, and a timeline of event starts.

        On an event's map, each dot is one start. A condition's map shades the
        world by its severity this run. The visibility map adds the low sun,
        lane by lane, by how directly each lane faces it.

        Args:
            graph: The world the spawns were rolled on.
            library: The hazards the forecast may name.
            spawns: The roll.
            show_junctions: Whether to outline each junction's bounding box.

        Returns:
            The figure.

        Raises:
            RoadGraphError: If the spawns were rolled from another map or forecast.
        """
        pyplot, tools = matplotlib_tools("Visualize.spawns")
        if spawns.graph_id != graph.graph_id or spawns.probabilities_hash != graph.forecast_hash():
            raise RoadGraphError("these spawns were rolled from a different map or a different forecast")
        hazards = shown_hazards(graph, library)
        events = [(index, hazard) for index, hazard in hazards if hazard.kind is HazardKind.EVENT]

        height = 8.0 + (1.6 if events else 0.0)
        figure = pyplot.figure(figsize=(6.5 * len(hazards), height), dpi=130, facecolor=THEME.surface,
                               layout="constrained")
        # Rows: the maps, each map's key, and one timeline across the figure when there are events.
        row_heights = [7.6, 0.16]
        if events:
            row_heights.append(0.35 + 0.35 * len(events))
        grid = figure.add_gridspec(len(row_heights), len(hazards), height_ratios=row_heights)
        for column, (index, hazard) in enumerate(hazards):
            axes = figure.add_subplot(grid[0, column])
            key_axes = figure.add_subplot(grid[1, column])
            if hazard.kind is HazardKind.EVENT:
                lines = draw_event_starts(axes, key_axes, graph, spawns, hazard, index, show_junctions, tools)
            else:
                lines = draw_condition(figure, axes, key_axes, graph, spawns, hazard, index, show_junctions, tools)
            style_map(axes, hazard.id, lines)
        if events:
            draw_timeline(figure.add_subplot(grid[2, :]), spawns, events)
        figure.suptitle(f"{graph.map_name}: hazards rolled with seed {spawns.seed}", x=0.02, ha="left",
                        fontsize=14, color=THEME.ink)
        return figure

    @staticmethod
    def routes(graph: WorldRoadGraph, routes: PlannerComputedWaypoints | Iterable[PlannerComputedWaypoints], *,
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
        pyplot, tools = matplotlib_tools("Visualize.routes")
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
            draw_route_map(axes, graph, route, ramp, scale, show_junctions, tools)
        scale_bar(figure, figure.add_subplot(grid[1, 0]), scale, ramp, "target speed (km/h)", tools, own_axes=True)
        if len(routes) > 1:
            draw_event_key(figure.add_subplot(grid[1, 1]), tools)
        draw_speed_profiles(figure.add_subplot(grid[2, :]), graph, routes, fastest)
        figure.suptitle(f"{graph.map_name}: planned route from A to B", x=0.02, ha="left", fontsize=14,
                        color=THEME.ink)
        return figure

    @staticmethod
    def speed(telemetry: DrivingScenarioTelemetry | Iterable[DrivingScenarioTelemetry]) -> Figure:
        """Draw the speed of runs over time. The dashed line is the speed limit along the first run.

        Args:
            telemetry: One run, or several to compare.

        Returns:
            The figure.

        Raises:
            ValueError: If there is no run, or a run has no samples.
        """
        pyplot, _ = matplotlib_tools("Visualize.speed")
        runs = checked_runs(telemetry)
        figure, axes = time_chart(pyplot, runs, "Speed", "speed (km/h)")
        draw_series(axes, runs, speeds_kmh)
        limits = speed_limits_kmh(runs[0])
        axes.plot(runs[0].signals[Signal.TIME_S], limits, color=THEME.ink_muted, linewidth=1.0, linestyle="--",
                  label="speed limit")
        shown = list(limits)
        for run in runs:
            shown += speeds_kmh(run)
        fit_values(axes, shown, from_zero=True)
        draw_legend(axes, len(runs) + 1)
        return figure

    @staticmethod
    def gap(telemetry: DrivingScenarioTelemetry | Iterable[DrivingScenarioTelemetry]) -> Figure:
        """Draw the gap to the nearest other road user over time, at its full range.

        A line breaks where no other road user is present. The dashed line is
        the minimum gap of the first run. A cross marks a collision.

        Args:
            telemetry: One run, or several to compare.

        Returns:
            The figure.

        Raises:
            ValueError: If there is no run, or a run has no samples.
        """
        pyplot, _ = matplotlib_tools("Visualize.gap")
        runs = checked_runs(telemetry)
        figure, axes = time_chart(pyplot, runs, "Gap to the nearest road user", "gap (m)")
        draw_series(axes, runs, gaps_m)
        min_gap_m = runs[0].driver.safety.min_gap_m
        shown = [min_gap_m]
        for index, run in enumerate(runs):
            shown += gaps_m(run)
            hits = collision_times(run)
            axes.scatter(hits, [0.0] * len(hits), marker="x", s=70, color=series_color(index), linewidths=2.0,
                         zorder=5, clip_on=False)
        fit_values(axes, shown, from_zero=True)
        draw_limit(axes, min_gap_m, f"minimum gap {min_gap_m:g} m")
        draw_legend(axes, len(runs))
        return figure

    @staticmethod
    def acceleration(telemetry: DrivingScenarioTelemetry | Iterable[DrivingScenarioTelemetry]) -> Figure:
        """Draw the acceleration of runs over time. Dashed lines are the limits of the first run.

        Args:
            telemetry: One run, or several to compare.

        Returns:
            The figure.

        Raises:
            ValueError: If there is no run, or a run has no samples.
        """
        pyplot, _ = matplotlib_tools("Visualize.acceleration")
        runs = checked_runs(telemetry)
        figure, axes = time_chart(pyplot, runs, "Acceleration", "acceleration (m/s2)")
        draw_series(axes, runs, lambda run: run.signals[Signal.ACCELERATION_MPS2], linewidth=1.2)
        safety = runs[0].driver.safety
        shown = [safety.max_acceleration_mps2, -safety.max_deceleration_mps2]
        for run in runs:
            shown += run.signals[Signal.ACCELERATION_MPS2]
        fit_values(axes, shown)
        draw_limit(axes, safety.max_acceleration_mps2, f"acceleration limit {safety.max_acceleration_mps2:g} m/s2")
        draw_limit(axes, -safety.max_deceleration_mps2, f"braking limit {safety.max_deceleration_mps2:g} m/s2")
        draw_legend(axes, len(runs))
        return figure

    @staticmethod
    def requirements(telemetry: DrivingScenarioTelemetry | Iterable[DrivingScenarioTelemetry],
                     safety: DrivingSafetyReq | None = None) -> dict[str, Figure]:
        """Draw one figure per safety requirement: the value it limits over time, against its threshold.

        The dashed line is the threshold. On each run, an arrow from the
        threshold marks the moment of least margin and carries that margin:
        positive is the room that was left, and negative is how far past the
        threshold the run went. The legend gives each run's verdict.

        Args:
            telemetry: One run, or several to compare.
            safety: The limits to draw. Defaults to those the first run was driven with.

        Returns:
            The figures, by requirement name, in the order the requirements are checked.

        Raises:
            ValueError: If there is no run, or a run has no samples.
        """
        pyplot, _ = matplotlib_tools("Visualize.requirements")
        runs = checked_runs(telemetry)
        safety = safety or runs[0].driver.safety
        figures = {}
        for requirement in Driver.requirements(safety):
            label = f"f(t) ({requirement.unit})" if requirement.unit else "f(t)"
            figure, axes = time_chart(pyplot, runs, f"{requirement.name}: {requirement.formula}", label)
            draw_requirement(axes, runs, requirement)
            figures[requirement.name] = figure
        return figures
