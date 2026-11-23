"""Private helpers of the world module: the random draws of a roll, and the pieces of its figures."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

from ...core.models.world_hazard_library import LOW_VISIBILITY, Hazard, HazardKind, WorldHazardLibrary
from ...core.models.world_road_graph import (
    ConditionForecast,
    RoadGraphError,
    RoadSegment,
    SegmentPosition,
    WorldRoadGraph,
    severity_level,
)
from ...core.utilities.config import CONFIG
from ...core.utilities.mapview import THEME
from ...core.utilities.sun import (
    glare_strength,
    low_sun_factor,
    low_sun_factor_at,
    sun_position,
    visibility_loss_by_segment,
)
from .models.world_hazard_spawns import ConditionSpawn, EventSpawn, SunGlare, WorldHazardSpawns

WORLD_SCOPE = "*"


def check_forecast(graph: WorldRoadGraph, library: WorldHazardLibrary) -> None:
    """Check that the graph has a forecast, and that it agrees with the library.

    Raises:
        RoadGraphError: If nothing is forecast, a hazard is not in the library,
            or an event and a condition are forecast as each other.
    """
    if not graph.hazard_ids() and graph.time_of_day_h is None:
        raise RoadGraphError("no events are assigned, no conditions are set, and there is no time of day")
    known = {hazard.id for hazard in library}
    unknown = sorted(graph.hazard_ids() - known)
    if unknown:
        raise RoadGraphError(f"hazards not in the library: {', '.join(unknown)}")
    for hazard_id in sorted(graph.event_ids()):
        if library.get(hazard_id).kind is not HazardKind.EVENT:
            raise RoadGraphError(f"{hazard_id} is a condition; set it for the whole world with set_condition")
    for hazard_id in sorted(graph.conditions):
        if library.get(hazard_id).kind is not HazardKind.CONDITION:
            raise RoadGraphError(f"{hazard_id} is an event; assign it to segments")


def random_stream(seed: int, scope: str, hazard_id: str) -> random.Random:
    """The random stream of one hazard in one scope: a segment id, or the whole world."""
    digest = hashlib.sha256(f"{seed}|{scope}|{hazard_id}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def roll_conditions(graph: WorldRoadGraph, seed: int) -> list[ConditionSpawn]:
    """Draw each forecast condition once: whether it is present, and at what severity."""
    spawns = []
    for hazard_id in sorted(graph.conditions):
        forecast = graph.conditions[hazard_id]
        stream = random_stream(seed, WORLD_SCOPE, hazard_id)
        present = stream.random()
        draw = stream.random()
        if present < forecast.probability:
            spawns.append(ConditionSpawn(hazard_id, forecast.severity_at(draw)))
    return spawns


def roll_events(graph: WorldRoadGraph, seed: int, duration_s: float) -> list[EventSpawn]:
    """Draw each event once per second on each segment it is assigned to.

    Every second takes the same three draws whether or not an event starts, so
    a longer duration only appends events after the earlier ones.

    Returns:
        The event starts, in time order.
    """
    spawns = []
    for sid in sorted(graph.segments):
        segment = graph.segments[sid]
        for item in sorted(segment.hazard_probabilities, key=lambda item: item.hazard_id):
            stream = random_stream(seed, sid, item.hazard_id)
            for second in range(math.ceil(duration_s)):
                occurs = stream.random()
                fraction = stream.random()
                along = stream.random()
                start_s = second + fraction
                if occurs < item.probability and start_s < duration_s:
                    position = SegmentPosition(sid, along * segment.length_m)
                    spawns.append(EventSpawn(item.hazard_id, position, start_s))
    spawns.sort(key=lambda spawn: (spawn.start_s, spawn.position.segment_id, spawn.hazard_id))
    return spawns


def sun_glare(graph: WorldRoadGraph, conditions: list[ConditionSpawn]) -> SunGlare | None:
    """The sun for a run, dimmed by the rain or fog that was rolled. None with no time of day."""
    if graph.time_of_day_h is None:
        return None
    fog = 0.0
    for spawn in conditions:
        if spawn.hazard_id == LOW_VISIBILITY:
            fog = spawn.severity
    altitude, azimuth = sun_position(graph.time_of_day_h)
    return SunGlare(graph.time_of_day_h, altitude, azimuth, glare_strength(graph.time_of_day_h, fog))


def shown_hazards(graph: WorldRoadGraph, library: WorldHazardLibrary) -> list[tuple[int, Hazard]]:
    """The hazards to draw a map for, each with its position in the library, which fixes its hue."""
    check_forecast(graph, library)
    shown = graph.hazard_ids()
    if graph.time_of_day_h is not None:
        shown.add(LOW_VISIBILITY)
    return [(index, hazard) for index, hazard in enumerate(library) if hazard.id in shown]


@dataclass
class ForecastMap:
    """What one map of the forecast figure shows.

    Attributes:
        values: The value to shade each segment by.
        top: The value at the dark end of the scale.
        lines: The subtitle lines.
        unit: The label of the scale.
    """

    values: dict[str, float]
    top: float
    lines: list[str]
    unit: str


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
    settings = CONFIG.view.topology
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
