from __future__ import annotations

import hashlib
import json
import math
import random
from typing import TYPE_CHECKING

from ...core.models.world_hazard_library import Hazard, HazardKind, WorldHazardLibrary
from ...core.models.world_road_graph import (
    RoadGraphError, RoadSegment, SegmentPosition, WorldRoadGraph, severity_level,
)
from ...core.utilities.sun import glare_strength, low_sun_factor, segment_sun_exposure, sun_position
from .models.world_hazard_spawns import ConditionSpawn, EventSpawn, SunGlare, WorldHazardSpawns

if TYPE_CHECKING:
    from matplotlib.figure import Figure

VISIBILITY = "low_visibility"


class World:
    @staticmethod
    def roll_hazards(graph: WorldRoadGraph, library: WorldHazardLibrary, seed: int, *,
                     duration_s: float = 300.0) -> WorldHazardSpawns:
        """Decide which hazards occur in one run. The same graph, seed and duration always give the same spawns.

        A condition is drawn once for the whole world: whether it is present,
        and at what severity. An event is drawn once per second of simulation
        time on each segment; each success starts within that second at a drawn
        point along the segment. The sun's glare follows from the time of day
        and the rolled visibility.

        Each condition, and each segment and event pair, has its own random
        stream, so changing one forecast leaves every other outcome unchanged,
        and a longer duration only appends events after the earlier ones.
        """
        if duration_s <= 0:
            raise RoadGraphError("duration must be positive")
        _check_assigned(graph, library)
        conditions = []
        for hazard_id in sorted(graph.conditions):
            forecast, stream = graph.conditions[hazard_id], _stream(seed, "*", hazard_id)
            present, draw = stream.random(), stream.random()
            if present < forecast.probability:
                conditions.append(ConditionSpawn(hazard_id, forecast.severity_at(draw)))
        events = []
        for sid in sorted(graph.segments):
            segment = graph.segments[sid]
            for item in sorted(segment.hazard_probabilities, key=lambda item: item.hazard_id):
                stream = _stream(seed, sid, item.hazard_id)
                for second in range(math.ceil(duration_s)):
                    occurs, fraction, along = stream.random(), stream.random(), stream.random()
                    start = second + fraction
                    if occurs < item.probability and start < duration_s:
                        events.append(EventSpawn(item.hazard_id, SegmentPosition(sid, along * segment.length_m), start))
        events.sort(key=lambda spawn: (spawn.start_s, spawn.position.segment_id, spawn.hazard_id))
        sun = None
        if graph.time_of_day_h is not None:
            altitude, azimuth = sun_position(graph.time_of_day_h)
            fog = next((spawn.severity for spawn in conditions if spawn.hazard_id == VISIBILITY), 0.0)
            sun = SunGlare(graph.time_of_day_h, altitude, azimuth, glare_strength(graph.time_of_day_h, fog))
        return WorldHazardSpawns(graph.graph_id, _probabilities_hash(graph), seed, float(duration_s),
                                 tuple(conditions), tuple(events), sun)

    @staticmethod
    def view_topology(graph: WorldRoadGraph, *, label_segments: bool = False, show_junctions: bool = True) -> Figure:
        """Draw the graph from above, in meters. Call `.savefig(path)` or `pyplot.show()` on the result.

        With `label_segments`, the figure is larger and each lane carries its segment id.
        With `show_junctions`, each junction's bounding box is outlined and tagged with its id.
        """
        try:
            from matplotlib import pyplot
            from matplotlib.patches import Rectangle
        except ImportError:
            raise ImportError("view_topology needs matplotlib: pip install 'pyotter[view]'") from None

        size, dpi = (24, 200) if label_segments else (10, 100)
        figure, axes = pyplot.subplots(figsize=(size, size), dpi=dpi)
        placed: list[tuple[float, float]] = []
        if show_junctions:
            for junction in graph.get_junctions():
                left, top = junction.x - junction.extent_x, junction.y - junction.extent_y
                axes.add_patch(Rectangle((left, top), 2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                                         facecolor="0.93", edgecolor="0.4", linestyle="--", linewidth=0.9))
                axes.text(left, top - 1.0, f"junction {junction.id}", fontsize=8, color="0.25", ha="left", va="bottom",
                          bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.85})
        for segment in graph.get_segments():
            line = segment.centerline
            color = "tab:orange" if segment.in_junction else "tab:blue"
            axes.plot([p.x for p in line], [p.y for p in line], color=color, linewidth=1.2)
            middle, after = line[(len(line) - 1) // 2], line[(len(line) - 1) // 2 + 1]
            axes.annotate("", xy=(after.x, after.y), xytext=(middle.x, middle.y),
                          arrowprops={"arrowstyle": "->", "color": color, "linewidth": 1.2})
            if label_segments:
                x, y, angle = _label_anchor(segment, placed)
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
        """
        pyplot, tools = _matplotlib("view_hazards")
        panes = _panes(graph, library)
        figure, axes_row = pyplot.subplots(1, len(panes), figsize=(6.5 * len(panes), 7.6), dpi=130,
                                           squeeze=False, facecolor=SURFACE, layout="constrained")
        for axes, (index, hazard) in zip(axes_row[0], panes):
            ramp = tools.LinearSegmentedColormap.from_list(hazard.id, _ramp(index))
            forecast = graph.get_condition(hazard)
            if hazard.kind is HazardKind.EVENT:
                values = {s.id: s.hazard_probability(hazard) for s in graph.get_segments()}
                scale = tools.Normalize(vmin=0.0, vmax=max(values.values()))
                lines = [f"event · assigned on {sum(v > 0 for v in values.values())} of {len(values)} segments"]
                unit = "chance per second that one starts"
            elif hazard.id == VISIBILITY:
                expected = forecast.expected_severity() if forecast else 0.0
                values = _visibility_loss(graph, expected, _low_sun(graph.time_of_day_h))
                scale = tools.Normalize(vmin=0.0, vmax=1.0)
                lines = [_forecast_text(forecast), _sun_text(graph.time_of_day_h)]
                unit = "expected visibility loss (0 none, 1 total)"
            else:
                values = dict.fromkeys(graph.segments, forecast.expected_severity())
                scale = tools.Normalize(vmin=0.0, vmax=1.0)
                lines = [_forecast_text(forecast)]
                unit = "expected severity (chance x severity)"
            _draw_lanes(axes, graph, values, ramp, scale, show_junctions, tools)
            if hazard.id == VISIBILITY:
                _sun_arrow(axes, graph.time_of_day_h)
            _style_map(axes, hazard, lines)
            _scale_bar(figure, axes, scale, ramp, unit, tools)
        figure.suptitle(f"{graph.map_name}: hazard forecast", x=0.02, ha="left", fontsize=14, color=INK)
        return figure

    @staticmethod
    def view_spawns(graph: WorldRoadGraph, library: WorldHazardLibrary, spawns: WorldHazardSpawns, *,
                    show_junctions: bool = True) -> Figure:
        """Draw what a roll produced: one map per hazard, and a timeline of event starts.

        On an event's map, each dot is one start. A condition's map shades the
        world by its severity this run. The visibility map adds the low sun,
        lane by lane, by how directly each lane faces it.
        """
        pyplot, tools = _matplotlib("view_spawns")
        if spawns.graph_id != graph.graph_id or spawns.probabilities_hash != _probabilities_hash(graph):
            raise RoadGraphError("these spawns were rolled from a different map or a different forecast")
        panes = _panes(graph, library)
        event_rows = [(index, hazard) for index, hazard in panes if hazard.kind is HazardKind.EVENT]
        present = {spawn.hazard_id for spawn in spawns.conditions}

        figure = pyplot.figure(figsize=(6.5 * len(panes), 8.0 + (1.6 if event_rows else 0.0)), dpi=130,
                               facecolor=SURFACE, layout="constrained")
        heights = (7.6, 0.16) + ((0.35 + 0.35 * len(event_rows),) if event_rows else ())
        grid = figure.add_gridspec(len(heights), len(panes), height_ratios=heights)
        for column, (index, hazard) in enumerate(panes):
            axes, below = figure.add_subplot(grid[0, column]), figure.add_subplot(grid[1, column])
            pale, solid, _ = _ramp(index)
            ramp = tools.LinearSegmentedColormap.from_list(hazard.id, _ramp(index))
            scale = tools.Normalize(vmin=0.0, vmax=1.0)
            severity = spawns.condition_severity(hazard)
            if hazard.kind is HazardKind.EVENT:
                possible = {s.id: 1.0 for s in graph.get_segments() if s.hazard_probability(hazard) > 0}
                _draw_lanes(axes, graph, possible, tools.ListedColormap([pale]), scale, show_junctions, tools)
                starts = [spawn for spawn in spawns.events if spawn.hazard_id == hazard.id]
                points = [graph.get_segment(s.position.segment_id).point_at(s.position.offset_m) for s in starts]
                axes.scatter([p[0] for p in points], [p[1] for p in points], s=26, color=solid,
                             edgecolors=SURFACE, linewidths=0.8, zorder=4)
                lines = [f"event · started {len(starts)} times in {spawns.duration_s:g} s, "
                         f"on {len(possible)} segments that could have it"]
                keys = [tools.Line2D([], [], color=solid, marker="o", linestyle="none", markersize=6, label="one start"),
                        tools.Line2D([], [], color=pale, linewidth=2.8, label="segment where it can occur")]
                below.axis("off")
                below.legend(handles=keys, loc="center", ncols=2, frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
            elif hazard.id == VISIBILITY:
                strength = spawns.sun.strength / (1.0 - severity) if spawns.sun and severity < 1.0 else 0.0
                values = _visibility_loss(graph, severity, strength)
                _draw_lanes(axes, graph, values, ramp, scale, show_junctions, tools)
                _sun_arrow(axes, graph.time_of_day_h)
                lines = [_spawn_text(hazard, severity, present), _sun_text(graph.time_of_day_h, spawns.sun)]
                _scale_bar(figure, below, scale, ramp, "visibility loss this run (0 none, 1 total)", tools, own_axes=True)
            else:
                _draw_lanes(axes, graph, dict.fromkeys(graph.segments, severity), ramp, scale, show_junctions, tools)
                lines = [_spawn_text(hazard, severity, present)]
                _scale_bar(figure, below, scale, ramp, "severity this run", tools, own_axes=True)
            _style_map(axes, hazard, lines)
        if event_rows:
            timeline = figure.add_subplot(grid[2, :])
            timeline.set_facecolor(SURFACE)
            for row, (index, hazard) in enumerate(event_rows):
                times = [spawn.start_s for spawn in spawns.events if spawn.hazard_id == hazard.id]
                timeline.eventplot(times, lineoffsets=row, linelengths=0.7, linewidths=1.0, colors=_ramp(index)[1])
            timeline.set_yticks(range(len(event_rows)), [hazard.id for _, hazard in event_rows])
            timeline.set_ylim(len(event_rows) - 0.5, -0.5)
            timeline.set_xlim(0, spawns.duration_s)
            timeline.set_xlabel("simulation time when each event starts (s)", color=INK_SECONDARY)
            timeline.tick_params(colors=INK_MUTED, labelsize=8)
            timeline.tick_params(axis="y", colors=INK_SECONDARY, labelsize=9.5, length=0)
            for name, spine in timeline.spines.items():
                spine.set_visible(name == "bottom")
                spine.set_color(AXIS)
        figure.suptitle(f"{graph.map_name}: hazards rolled with seed {spawns.seed}", x=0.02, ha="left",
                        fontsize=14, color=INK)
        return figure


LABEL_FRACTIONS = (0.3, 0.7, 0.15, 0.85, 0.5, 0.4, 0.6)

SURFACE, INK, INK_SECONDARY, INK_MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

# One light-to-dark ramp per hazard, in library order, so a hazard keeps its hue whichever others are shown.
HAZARD_RAMPS = (
    ("#9ec5f4", "#2a78d6", "#0d366b"),
    ("#f7c3ad", "#eb6834", "#7a2c0c"),
    ("#a4dfca", "#1baf7a", "#0a5038"),
    ("#f8d999", "#eda100", "#6e4b00"),
    ("#f6cadb", "#e87ba4", "#7d2748"),
    ("#99cd99", "#008300", "#003c00"),
    ("#c0b9ef", "#6250d6", "#2a2068"),
    ("#f4b6b6", "#e34948", "#6f1a1a"),
)


def _label_anchor(segment: RoadSegment, placed: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Pick the point along the lane farthest from the labels already placed, and the lane's screen angle there."""
    best = None
    for fraction in LABEL_FRACTIONS:
        offset = fraction * segment.length_m
        x, y, _ = segment.point_at(offset)
        clearance = min((math.hypot(x - px, y - py) for px, py in placed), default=math.inf)
        if best is None or clearance > best[0]:
            best = (clearance, x, y, offset)
        if clearance >= 6.0:
            break
    _, x, y, offset = best
    placed.append((x, y))
    ahead = segment.point_at(min(offset + 1.0, segment.length_m))
    behind = segment.point_at(max(offset - 1.0, 0.0))
    angle = math.degrees(math.atan2(-(ahead[1] - behind[1]), ahead[0] - behind[0]))  # y axis is inverted
    if not -90.0 < angle <= 90.0:
        angle += 180.0
    return x, y, angle



def _ramp(index: int) -> tuple[str, str, str]:
    return HAZARD_RAMPS[index] if index < len(HAZARD_RAMPS) else HAZARD_RAMPS[0]


def _matplotlib(caller: str):
    try:
        from matplotlib import cm, colors, lines, patches, pyplot
    except ImportError:
        raise ImportError(f"{caller} needs matplotlib: pip install 'pyotter[view]'") from None

    class Tools:
        LinearSegmentedColormap, ListedColormap, Normalize = colors.LinearSegmentedColormap, colors.ListedColormap, colors.Normalize
        ScalarMappable, Line2D, Rectangle = cm.ScalarMappable, lines.Line2D, patches.Rectangle

    return pyplot, Tools


def _check_assigned(graph: WorldRoadGraph, library: WorldHazardLibrary) -> None:
    if not graph.hazard_ids() and graph.time_of_day_h is None:
        raise RoadGraphError("no events are assigned, no conditions are set, and there is no time of day")
    unknown = sorted(graph.hazard_ids() - {hazard.id for hazard in library})
    if unknown:
        raise RoadGraphError(f"hazards not in the library: {', '.join(unknown)}")
    for hazard_id in sorted(graph.event_ids()):
        if library.get(hazard_id).kind is not HazardKind.EVENT:
            raise RoadGraphError(f"{hazard_id} is a condition; set it for the whole world with set_condition")
    for hazard_id in sorted(graph.conditions):
        if library.get(hazard_id).kind is not HazardKind.CONDITION:
            raise RoadGraphError(f"{hazard_id} is an event; assign it to segments")


def _panes(graph: WorldRoadGraph, library: WorldHazardLibrary) -> list[tuple[int, Hazard]]:
    _check_assigned(graph, library)
    shown = graph.hazard_ids() | ({VISIBILITY} if graph.time_of_day_h is not None else set())
    return [(index, hazard) for index, hazard in enumerate(library) if hazard.id in shown]


def _stream(seed: int, scope: str, hazard_id: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}|{scope}|{hazard_id}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _probabilities_hash(graph: WorldRoadGraph) -> str:
    events = sorted((sid, item.hazard_id, item.probability)
                    for sid, segment in graph.segments.items() for item in segment.hazard_probabilities)
    conditions = sorted((f.hazard_id, f.probability, f.severity, f.variability) for f in graph.conditions.values())
    return hashlib.sha256(json.dumps([events, conditions, graph.time_of_day_h]).encode()).hexdigest()


def _low_sun(time_of_day_h: float | None) -> float:
    return 0.0 if time_of_day_h is None else low_sun_factor(sun_position(time_of_day_h)[0])


def _visibility_loss(graph: WorldRoadGraph, fog: float, low_sun: float) -> dict[str, float]:
    """Per lane: the rain or fog everywhere, plus the low sun on what the rain or fog leaves clear."""
    if graph.time_of_day_h is None or low_sun <= 0.0:
        return dict.fromkeys(graph.segments, fog)
    azimuth = sun_position(graph.time_of_day_h)[1]
    return {sid: fog + (1.0 - fog) * low_sun * segment_sun_exposure(segment, azimuth)
            for sid, segment in graph.segments.items()}


def _clock(time_of_day_h: float) -> str:
    minutes = round(time_of_day_h * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _forecast_text(forecast) -> str:
    if forecast is None:
        return "condition · not forecast"
    low, high = forecast.severity_range()
    spread = f"{low:.2f} to {high:.2f}" if high > low else f"{low:.2f}"
    return f"condition · {forecast.probability:.0%} chance · severity {spread} ({severity_level(forecast.severity)})"


def _spawn_text(hazard: Hazard, severity: float, present: set[str]) -> str:
    if hazard.id not in present:
        return "condition · not present this run"
    return f"condition · present this run at severity {severity:.2f} ({severity_level(severity)})"


def _sun_text(time_of_day_h: float | None, sun: SunGlare | None = None) -> str:
    if time_of_day_h is None:
        return "sun · no time of day set"
    altitude = sun_position(time_of_day_h)[0]
    if altitude < 0:
        return f"sun · {_clock(time_of_day_h)}, below the horizon, no glare"
    where = f"sun · {_clock(time_of_day_h)}, {altitude:.0f} degrees above the horizon"
    if sun is not None:
        return f"{where} · facing it loses {sun.strength:.2f}"
    return f"{where} · low-sun factor {low_sun_factor(altitude):.2f}"


def _draw_lanes(axes, graph: WorldRoadGraph, values: dict[str, float], ramp, scale, show_junctions: bool, tools) -> None:
    axes.set_facecolor(SURFACE)
    if show_junctions:
        for junction in graph.get_junctions():
            axes.add_patch(tools.Rectangle((junction.x - junction.extent_x, junction.y - junction.extent_y),
                                           2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                                           facecolor="none", edgecolor=AXIS, linestyle="--", linewidth=0.7))
    for sid in sorted(graph.segments, key=lambda sid: values.get(sid, 0.0)):
        line, value = graph.segments[sid].centerline, values.get(sid, 0.0)
        xs, ys = [p.x for p in line], [p.y for p in line]
        if value > 0.005:
            axes.plot(xs, ys, color=ramp(scale(value)), linewidth=2.8, solid_capstyle="round", zorder=2)
        else:
            axes.plot(xs, ys, color=AXIS, linewidth=0.8, zorder=1)


def _sun_arrow(axes, time_of_day_h: float | None) -> None:
    """An arrow in the corner pointing the way to the sun, when the sun is low enough to matter."""
    if _low_sun(time_of_day_h) <= 0.0:
        return
    azimuth = math.radians(sun_position(time_of_day_h)[1])
    dx, dy = 0.055 * math.cos(azimuth), -0.055 * math.sin(azimuth)  # the y axis is inverted
    axes.annotate("", xy=(0.93 + dx, 1.07 + dy), xytext=(0.93 - dx, 1.07 - dy), xycoords="axes fraction",
                  annotation_clip=False, arrowprops={"arrowstyle": "-|>", "color": INK, "linewidth": 1.6})
    axes.text(0.86, 1.07, "to the sun", transform=axes.transAxes, fontsize=9.5, color=INK_SECONDARY,
              ha="right", va="center")


def _style_map(axes, hazard: Hazard, lines: list[str]) -> None:
    axes.set_title(hazard.id, loc="left", fontsize=13, fontweight="bold", color=INK, pad=38)
    axes.text(0.0, 1.015, "\n".join(lines + [""] * (2 - len(lines))), transform=axes.transAxes, fontsize=9.5, color=INK_SECONDARY,
              ha="left", va="bottom", linespacing=1.4)
    axes.set_aspect("equal")
    axes.invert_yaxis()
    axes.set_xlabel("x (m)", color=INK_SECONDARY)
    axes.set_ylabel("y (m)", color=INK_SECONDARY)
    axes.tick_params(colors=INK_MUTED, labelsize=8)
    axes.grid(True, linewidth=0.4, color=GRID)
    for spine in axes.spines.values():
        spine.set_color(AXIS)


def _scale_bar(figure, axes, scale, ramp, label: str, tools, *, own_axes: bool = False) -> None:
    """Draw the scale under `axes`, or inside it when `own_axes` says the axes is reserved for the scale."""
    where = {"cax": axes} if own_axes else {"ax": axes, "fraction": 0.035, "pad": 0.03, "aspect": 40}
    bar = figure.colorbar(tools.ScalarMappable(norm=scale, cmap=ramp), orientation="horizontal", **where)
    bar.set_label(label, color=INK_SECONDARY, fontsize=9.5)
    bar.ax.tick_params(colors=INK_MUTED, labelsize=8)
    bar.outline.set_visible(False)
