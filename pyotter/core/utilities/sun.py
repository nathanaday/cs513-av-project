"""Low-sun glare: how much facing a low sun degrades visibility, as a scalar from 0 to 1.

Angles are in the map frame, like a CARLA yaw: 0 points along +x and 90 along
+y. East is taken as +x and south as +y.
"""

from __future__ import annotations

import math

from ..models.world_hazard_library import LOW_VISIBILITY
from ..models.world_road_graph import RoadSegment, WorldRoadGraph

SUNRISE_H, SUNSET_H = 6.0, 18.0
NOON_ALTITUDE_DEG = 60.0
FULL_GLARE_BELOW_DEG, NO_GLARE_ABOVE_DEG = 5.0, 25.0
NO_GLARE_BEYOND_DEG = 60.0


def sun_position(time_of_day_h: float) -> tuple[float, float]:
    """Altitude above the horizon and azimuth toward the sun, in degrees. Altitude is negative at night."""
    day = (time_of_day_h - SUNRISE_H) / (SUNSET_H - SUNRISE_H)
    return NOON_ALTITUDE_DEG * math.sin(math.pi * day), (180.0 * day) % 360.0


def low_sun_factor(altitude_deg: float) -> float:
    """1 when the sun sits on the horizon, falling to 0 once it is high. 0 at night."""
    if altitude_deg < 0.0:
        return 0.0
    span = NO_GLARE_ABOVE_DEG - FULL_GLARE_BELOW_DEG
    return min(1.0, max(0.0, (NO_GLARE_ABOVE_DEG - altitude_deg) / span))


def facing_factor(heading_deg: float, azimuth_deg: float) -> float:
    """1 when driving straight at the sun, falling to 0 when it is 60 degrees or more off the heading."""
    off = math.cos(math.radians(heading_deg - azimuth_deg))
    edge = math.cos(math.radians(NO_GLARE_BEYOND_DEG))
    return min(1.0, max(0.0, (off - edge) / (1.0 - edge)))


def glare_strength(time_of_day_h: float, visibility_severity: float) -> float:
    """Degradation when facing the sun. Rain or fog already hides the sun, so it scales the glare down."""
    altitude, _ = sun_position(time_of_day_h)
    return low_sun_factor(altitude) * (1.0 - visibility_severity)


def segment_sun_exposure(segment: RoadSegment, azimuth_deg: float) -> float:
    """The facing factor averaged along the lane, so a curve counts only where it points at the sun."""
    total = 0.0
    for a, b in zip(segment.centerline, segment.centerline[1:]):
        heading = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
        total += facing_factor(heading, azimuth_deg) * (b.distance_m - a.distance_m)
    return total / segment.length_m


def visibility_loss_by_segment(graph: WorldRoadGraph, fog: float, low_sun: float) -> dict[str, float]:
    """Per lane: the rain or fog everywhere, plus the low sun on what the rain or fog leaves clear."""
    if graph.time_of_day_h is None or low_sun <= 0.0:
        return dict.fromkeys(graph.segments, fog)
    azimuth = sun_position(graph.time_of_day_h)[1]
    return {sid: fog + (1.0 - fog) * low_sun * segment_sun_exposure(segment, azimuth)
            for sid, segment in graph.segments.items()}


def expected_visibility_loss(graph: WorldRoadGraph) -> dict[str, float]:
    """The forecast's mean visibility loss per lane, from the rain or fog forecast and the time of day."""
    forecast = graph.conditions.get(LOW_VISIBILITY)
    fog = forecast.expected_severity() if forecast else 0.0
    low_sun = 0.0 if graph.time_of_day_h is None else low_sun_factor(sun_position(graph.time_of_day_h)[0])
    return visibility_loss_by_segment(graph, fog, low_sun)
