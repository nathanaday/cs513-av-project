"""Private helpers of the world module: the forecast check, and the random draws of a roll."""

from __future__ import annotations

import hashlib
import math
import random

from ...core.models.world_hazard_library import LOW_VISIBILITY, HazardKind, WorldHazardLibrary
from ...core.models.world_road_graph import RoadGraphError, SegmentPosition, WorldRoadGraph
from ...core.utilities.sun import glare_strength, night_loss_at, sun_position
from .models.world_hazard_spawns import ConditionSpawn, EventSpawn, SunGlare

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
    """The sun for a run, dimmed by the rain or fog that was rolled, and the dark at night. None with no time of day."""
    if graph.time_of_day_h is None:
        return None
    fog = 0.0
    for spawn in conditions:
        if spawn.hazard_id == LOW_VISIBILITY:
            fog = spawn.severity
    altitude, azimuth = sun_position(graph.time_of_day_h)
    strength = glare_strength(graph.time_of_day_h, fog)
    return SunGlare(graph.time_of_day_h, altitude, azimuth, strength, night_loss_at(graph.time_of_day_h))
