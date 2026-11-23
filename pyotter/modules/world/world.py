"""The world: roll the hazards of one run from a forecast, and draw the map, the forecast and the roll."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.models.world_hazard_library import LOW_VISIBILITY, Hazard, HazardKind, WorldHazardLibrary
from ...core.models.world_road_graph import RoadGraphError, RoadSegment, WorldRoadGraph
from ...core.utilities.config import CONFIG
from ...core.utilities.mapview import THEME, draw_lanes, hue_ramp, matplotlib_tools, scale_bar, style_map
from .models.world_hazard_spawns import WorldHazardSpawns
from .utilities import (
    check_forecast,
    draw_sun_arrow,
    forecast_map,
    label_anchor,
    roll_conditions,
    roll_events,
    rolled_visibility_loss,
    shown_hazards,
    spawn_text,
    sun_glare,
    sun_text,
)

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class World:
    @staticmethod
    def roll_hazards(graph: WorldRoadGraph, library: WorldHazardLibrary, seed: int, *,
                     duration_s: float = CONFIG.world.roll_duration_s) -> WorldHazardSpawns:
        """Decide which hazards occur in one run.

        The same graph, seed and duration always give the same spawns. A
        condition is drawn once for the whole world: whether it is present, and
        at what severity. An event is drawn once per second of simulation time
        on each segment, and each success starts within that second at a drawn
        point along the segment. The sun's glare follows from the time of day
        and the rolled visibility.

        Each condition, and each segment and event pair, has its own random
        stream, so changing one forecast leaves every other outcome unchanged,
        and a longer duration only appends events after the earlier ones.

        Args:
            graph: The world, with its forecast.
            library: The hazards the forecast may name.
            seed: Selects the run.
            duration_s: The length of simulation time to roll events for.

        Returns:
            The conditions, event starts and sun of the run.

        Raises:
            RoadGraphError: If the duration is not positive, or the forecast is
                empty or disagrees with the library.
        """
        if duration_s <= 0:
            raise RoadGraphError("duration must be positive")
        check_forecast(graph, library)
        conditions = roll_conditions(graph, seed)
        events = roll_events(graph, seed, duration_s)
        return WorldHazardSpawns(
            graph_id=graph.graph_id,
            probabilities_hash=graph.forecast_hash(),
            seed=seed,
            duration_s=float(duration_s),
            conditions=tuple(conditions),
            events=tuple(events),
            sun=sun_glare(graph, conditions),
        )

    @staticmethod
    def view_topology(graph: WorldRoadGraph, *, label_segments: bool = False, show_junctions: bool = True) -> Figure:
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
        pyplot, tools = matplotlib_tools("view_topology")
        settings = CONFIG.view.topology
        size = settings.labelled_size_in if label_segments else settings.size_in
        dpi = settings.labelled_dpi if label_segments else settings.dpi
        figure, axes = pyplot.subplots(figsize=(size, size), dpi=dpi)
        if show_junctions:
            _draw_junction_boxes(axes, graph, tools)
        placed_labels: list[tuple[float, float]] = []
        for segment in graph.get_segments():
            color = "tab:orange" if segment.in_junction else "tab:blue"
            _draw_lane_with_arrow(axes, segment, color)
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
    def view_hazards(graph: WorldRoadGraph, library: WorldHazardLibrary, *, show_junctions: bool = True) -> Figure:
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
        pyplot, tools = matplotlib_tools("view_hazards")
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
    def view_spawns(graph: WorldRoadGraph, library: WorldHazardLibrary, spawns: WorldHazardSpawns, *,
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
        pyplot, tools = matplotlib_tools("view_spawns")
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
                lines = _draw_event_starts(axes, key_axes, graph, spawns, hazard, index, show_junctions, tools)
            else:
                lines = _draw_condition(figure, axes, key_axes, graph, spawns, hazard, index, show_junctions, tools)
            style_map(axes, hazard.id, lines)
        if events:
            _draw_timeline(figure.add_subplot(grid[2, :]), spawns, events)
        figure.suptitle(f"{graph.map_name}: hazards rolled with seed {spawns.seed}", x=0.02, ha="left",
                        fontsize=14, color=THEME.ink)
        return figure


def _draw_junction_boxes(axes, graph: WorldRoadGraph, tools) -> None:
    for junction in graph.get_junctions():
        left = junction.x - junction.extent_x
        top = junction.y - junction.extent_y
        axes.add_patch(tools.Rectangle((left, top), 2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                                       facecolor="0.93", edgecolor="0.4", linestyle="--", linewidth=0.9))
        axes.text(left, top - 1.0, f"junction {junction.id}", fontsize=8, color="0.25", ha="left", va="bottom",
                  bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.85})


def _draw_lane_with_arrow(axes, segment: RoadSegment, color: str) -> None:
    """Draw a lane's centerline, with an arrow at its middle showing the driving direction."""
    line = segment.centerline
    axes.plot([point.x for point in line], [point.y for point in line], color=color, linewidth=1.2)
    middle = line[(len(line) - 1) // 2]
    after = line[(len(line) - 1) // 2 + 1]
    axes.annotate("", xy=(after.x, after.y), xytext=(middle.x, middle.y),
                  arrowprops={"arrowstyle": "->", "color": color, "linewidth": 1.2})


def _draw_event_starts(axes, key_axes, graph: WorldRoadGraph, spawns: WorldHazardSpawns, hazard: Hazard,
                       index: int, show_junctions: bool, tools) -> list[str]:
    """Draw the segments an event can start on and a dot at each start. Returns the map's subtitle."""
    pale, solid, _ = hue_ramp(index)
    possible = {segment.id: 1.0 for segment in graph.get_segments() if segment.hazard_probability(hazard) > 0}
    scale = tools.Normalize(vmin=0.0, vmax=1.0)
    draw_lanes(axes, graph, possible, tools.ListedColormap([pale]), scale, show_junctions, tools)
    starts = spawns.events_of(hazard)
    points = [graph.get_segment(start.position.segment_id).point_at(start.position.offset_m) for start in starts]
    axes.scatter([point[0] for point in points], [point[1] for point in points], s=26, color=solid,
                 edgecolors=THEME.surface, linewidths=0.8, zorder=4)
    keys = [
        tools.Line2D([], [], color=solid, marker="o", linestyle="none", markersize=6, label="one start"),
        tools.Line2D([], [], color=pale, linewidth=2.8, label="segment where it can occur"),
    ]
    key_axes.axis("off")
    key_axes.legend(handles=keys, loc="center", ncols=2, frameon=False, fontsize=9, labelcolor=THEME.ink_secondary)
    return [f"event · started {len(starts)} times in {spawns.duration_s:g} s, "
            f"on {len(possible)} segments that could have it"]


def _draw_condition(figure, axes, key_axes, graph: WorldRoadGraph, spawns: WorldHazardSpawns, hazard: Hazard,
                    index: int, show_junctions: bool, tools) -> list[str]:
    """Shade the map by a condition's severity in one run. Returns the map's subtitle."""
    ramp = tools.LinearSegmentedColormap.from_list(hazard.id, hue_ramp(index))
    scale = tools.Normalize(vmin=0.0, vmax=1.0)
    lines = [spawn_text(hazard, spawns)]
    if hazard.id == LOW_VISIBILITY:
        draw_lanes(axes, graph, rolled_visibility_loss(graph, spawns), ramp, scale, show_junctions, tools)
        draw_sun_arrow(axes, graph.time_of_day_h)
        lines.append(sun_text(graph.time_of_day_h, spawns.sun))
        label = "visibility loss this run (0 none, 1 total)"
    else:
        severity = spawns.condition_severity(hazard)
        draw_lanes(axes, graph, dict.fromkeys(graph.segments, severity), ramp, scale, show_junctions, tools)
        label = "severity this run"
    scale_bar(figure, key_axes, scale, ramp, label, tools, own_axes=True)
    return lines


def _draw_timeline(axes, spawns: WorldHazardSpawns, events: list[tuple[int, Hazard]]) -> None:
    """Draw one row per event, with a tick at the time of each start."""
    axes.set_facecolor(THEME.surface)
    for row, (index, hazard) in enumerate(events):
        times = [spawn.start_s for spawn in spawns.events_of(hazard)]
        _, solid, _ = hue_ramp(index)
        axes.eventplot(times, lineoffsets=row, linelengths=0.7, linewidths=1.0, colors=solid)
    axes.set_yticks(range(len(events)), [hazard.id for _, hazard in events])
    axes.set_ylim(len(events) - 0.5, -0.5)
    axes.set_xlim(0, spawns.duration_s)
    axes.set_xlabel("simulation time when each event starts (s)", color=THEME.ink_secondary)
    axes.tick_params(colors=THEME.ink_muted, labelsize=8)
    axes.tick_params(axis="y", colors=THEME.ink_secondary, labelsize=9.5, length=0)
    for name, spine in axes.spines.items():
        spine.set_visible(name == "bottom")
        spine.set_color(THEME.axis)
