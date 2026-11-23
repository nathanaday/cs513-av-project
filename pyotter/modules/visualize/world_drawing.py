"""The pieces of the world's figures: the topology, the forecast, and the roll."""

from __future__ import annotations

import math

from ...core.models.world_hazard_library import LOW_VISIBILITY, Hazard, HazardKind, WorldHazardLibrary
from ...core.models.world_road_graph import ConditionForecast, RoadSegment, WorldRoadGraph, severity_level
from ...core.utilities.sun import low_sun_factor, low_sun_factor_at, sun_position, visibility_loss_by_segment
from ..world.models.world_hazard_spawns import SunGlare, WorldHazardSpawns
from ..world.world import World
from .models.forecast_map import ForecastMap
from .utilities import THEME, draw_lanes, hue_ramp, scale_bar


def shown_hazards(graph: WorldRoadGraph, library: WorldHazardLibrary) -> list[tuple[int, Hazard]]:
    """The hazards to draw a map for, each with its position in the library, which fixes its hue."""
    World.check_forecast(graph, library)
    shown = graph.hazard_ids()
    if graph.time_of_day_h is not None:
        shown.add(LOW_VISIBILITY)
    return [(index, hazard) for index, hazard in enumerate(library) if hazard.id in shown]


def forecast_map(graph: WorldRoadGraph, hazard: Hazard) -> ForecastMap:
    """The forecast of one hazard, as values to draw on the map."""
    forecast = graph.get_condition(hazard)
    if hazard.kind is HazardKind.EVENT:
        values = {segment.id: segment.hazard_probability(hazard) for segment in graph.get_segments()}
        assigned = sum(value > 0 for value in values.values())
        lines = [f"event · assigned on {assigned} of {len(values)} segments"]
        return ForecastMap(values, max(values.values()), lines, "chance per second that one starts")
    if hazard.id == LOW_VISIBILITY:
        fog = forecast.expected_severity() if forecast else 0.0
        values = visibility_loss_by_segment(graph, fog, low_sun_factor_at(graph.time_of_day_h))
        lines = [forecast_text(forecast), sun_text(graph.time_of_day_h)]
        return ForecastMap(values, 1.0, lines, "expected visibility loss (0 none, 1 total)")
    values = dict.fromkeys(graph.segments, forecast.expected_severity())
    return ForecastMap(values, 1.0, [forecast_text(forecast)], "expected severity (chance x severity)")


def rolled_visibility_loss(graph: WorldRoadGraph, spawns: WorldHazardSpawns) -> dict[str, float]:
    """Visibility loss on each lane in one run, from the rolled rain or fog and the sun."""
    fog = spawns.condition_severity(LOW_VISIBILITY)
    low_sun = 0.0
    if spawns.sun and fog < 1.0:
        # The rolled strength is already dimmed by the fog; undo that to get the low-sun factor.
        low_sun = spawns.sun.strength / (1.0 - fog)
    return visibility_loss_by_segment(graph, fog, low_sun)


def clock(time_of_day_h: float) -> str:
    minutes = round(time_of_day_h * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def forecast_text(forecast: ConditionForecast | None) -> str:
    if forecast is None:
        return "condition · not forecast"
    low, high = forecast.severity_range()
    spread = f"{low:.2f} to {high:.2f}" if high > low else f"{low:.2f}"
    level = severity_level(forecast.severity)
    return f"condition · {forecast.probability:.0%} chance · severity {spread} ({level})"


def spawn_text(hazard: Hazard, spawns: WorldHazardSpawns) -> str:
    if hazard.id not in {spawn.hazard_id for spawn in spawns.conditions}:
        return "condition · not present this run"
    severity = spawns.condition_severity(hazard)
    return f"condition · present this run at severity {severity:.2f} ({severity_level(severity)})"


def sun_text(time_of_day_h: float | None, sun: SunGlare | None = None) -> str:
    """Describe the sun: for a forecast, or for one run when its rolled `sun` is given."""
    if time_of_day_h is None:
        return "sun · no time of day set"
    altitude, _ = sun_position(time_of_day_h)
    if altitude < 0:
        return f"sun · {clock(time_of_day_h)}, below the horizon, no glare"
    where = f"sun · {clock(time_of_day_h)}, {altitude:.0f} degrees above the horizon"
    if sun is not None:
        return f"{where} · facing it loses {sun.strength:.2f}"
    return f"{where} · low-sun factor {low_sun_factor(altitude):.2f}"


def draw_sun_arrow(axes, time_of_day_h: float | None) -> None:
    """Draw an arrow above the map pointing the way to the sun, when the sun is low enough to matter."""
    if low_sun_factor_at(time_of_day_h) <= 0.0:
        return
    _, azimuth_deg = sun_position(time_of_day_h)
    azimuth = math.radians(azimuth_deg)
    dx = 0.055 * math.cos(azimuth)
    dy = -0.055 * math.sin(azimuth)  # the y axis is inverted
    axes.annotate("", xy=(0.93 + dx, 1.07 + dy), xytext=(0.93 - dx, 1.07 - dy), xycoords="axes fraction",
                  annotation_clip=False, arrowprops={"arrowstyle": "-|>", "color": THEME.ink, "linewidth": 1.6})
    axes.text(0.86, 1.07, "to the sun", transform=axes.transAxes, fontsize=9.5, color=THEME.ink_secondary,
              ha="right", va="center")


def label_anchor(segment: RoadSegment, placed: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Choose where a segment's label goes, and record it in `placed`.

    Tries the configured points along the lane, and takes the first that is
    clear of the labels already placed, or else the clearest.

    Returns:
        The x and y of the label, and the lane's angle on screen there, in degrees.
    """
    settings = THEME.topology
    best_clearance = None
    for fraction in settings.label_fractions:
        offset = fraction * segment.length_m
        x, y, _ = segment.point_at(offset)
        clearance = min((math.hypot(x - px, y - py) for px, py in placed), default=math.inf)
        if best_clearance is None or clearance > best_clearance:
            best_clearance = clearance
            best = (x, y, offset)
        if clearance >= settings.label_clearance_m:
            break
    x, y, offset = best
    placed.append((x, y))
    ahead = segment.point_at(min(offset + 1.0, segment.length_m))
    behind = segment.point_at(max(offset - 1.0, 0.0))
    angle = math.degrees(math.atan2(-(ahead[1] - behind[1]), ahead[0] - behind[0]))  # the y axis is inverted
    if not -90.0 < angle <= 90.0:
        angle += 180.0
    return x, y, angle


def draw_junction_boxes(axes, graph: WorldRoadGraph, tools) -> None:
    for junction in graph.get_junctions():
        left = junction.x - junction.extent_x
        top = junction.y - junction.extent_y
        axes.add_patch(tools.Rectangle((left, top), 2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                                       facecolor="0.93", edgecolor="0.4", linestyle="--", linewidth=0.9))
        axes.text(left, top - 1.0, f"junction {junction.id}", fontsize=8, color="0.25", ha="left", va="bottom",
                  bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.85})


def draw_lane_with_arrow(axes, segment: RoadSegment, color: str) -> None:
    """Draw a lane's centerline, with an arrow at its middle showing the driving direction."""
    line = segment.centerline
    axes.plot([point.x for point in line], [point.y for point in line], color=color, linewidth=1.2)
    middle = line[(len(line) - 1) // 2]
    after = line[(len(line) - 1) // 2 + 1]
    axes.annotate("", xy=(after.x, after.y), xytext=(middle.x, middle.y),
                  arrowprops={"arrowstyle": "->", "color": color, "linewidth": 1.2})


def draw_event_starts(axes, key_axes, graph: WorldRoadGraph, spawns: WorldHazardSpawns, hazard: Hazard,
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


def draw_condition(figure, axes, key_axes, graph: WorldRoadGraph, spawns: WorldHazardSpawns, hazard: Hazard,
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


def draw_timeline(axes, spawns: WorldHazardSpawns, events: list[tuple[int, Hazard]]) -> None:
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
