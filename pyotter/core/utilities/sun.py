"""Low-sun glare: how much facing a low sun degrades visibility, as a scalar from 0 to 1.

Angles are in the map frame, like a CARLA yaw: 0 points along +x and 90 along
+y. East is taken as +x and south as +y.
"""

from __future__ import annotations

import math

from ..models.world_hazard_library import LOW_VISIBILITY
from ..models.world_road_graph import RoadSegment, WorldRoadGraph
from .config import CONFIG

SUN = CONFIG.world.sun


def sun_position(time_of_day_h: float) -> tuple[float, float]:
    """Where the sun is at a time of day.

    Returns:
        The altitude above the horizon and the azimuth toward the sun, in
        degrees. The altitude is negative at night.
    """
    day = (time_of_day_h - SUN.sunrise_h) / (SUN.sunset_h - SUN.sunrise_h)
    altitude = SUN.noon_altitude_deg * math.sin(math.pi * day)
    azimuth = (180.0 * day) % 360.0
    return altitude, azimuth


def low_sun_factor(altitude_deg: float) -> float:
    """1 when the sun sits on the horizon, falling to 0 once it is high. 0 at night."""
    if altitude_deg < 0.0:
        return 0.0
    span = SUN.no_glare_above_deg - SUN.full_glare_below_deg
    return min(1.0, max(0.0, (SUN.no_glare_above_deg - altitude_deg) / span))


def low_sun_factor_at(time_of_day_h: float | None) -> float:
    """The low-sun factor at a time of day, or 0 for a world with no sun model."""
    if time_of_day_h is None:
        return 0.0
    altitude, _ = sun_position(time_of_day_h)
    return low_sun_factor(altitude)


def facing_factor(heading_deg: float, azimuth_deg: float) -> float:
    """1 when driving straight at the sun, falling to 0 once it is far enough off the heading."""
    off = math.cos(math.radians(heading_deg - azimuth_deg))
    edge = math.cos(math.radians(SUN.no_glare_beyond_deg))
    return min(1.0, max(0.0, (off - edge) / (1.0 - edge)))


def glare_strength(time_of_day_h: float, visibility_severity: float) -> float:
    """Visibility lost when facing the sun. Rain or fog already hides the sun, so it scales the glare down."""
    altitude, _ = sun_position(time_of_day_h)
    return low_sun_factor(altitude) * (1.0 - visibility_severity)


def segment_sun_exposure(segment: RoadSegment, azimuth_deg: float) -> float:
    """The facing factor averaged along the lane, so a curve counts only where it points at the sun."""
    total = 0.0
    for before, after in zip(segment.centerline, segment.centerline[1:]):
        heading = math.degrees(math.atan2(after.y - before.y, after.x - before.x))
        total += facing_factor(heading, azimuth_deg) * (after.distance_m - before.distance_m)
    return total / segment.length_m


def visibility_loss_by_segment(graph: WorldRoadGraph, fog: float, low_sun: float) -> dict[str, float]:
    """Visibility loss on each lane: the rain or fog everywhere, plus the low sun on what they leave clear.

    Args:
        graph: The world, whose time of day places the sun.
        fog: Severity of the rain or fog, from 0 to 1.
        low_sun: The low-sun factor, from 0 to 1.

    Returns:
        The loss, from 0 to 1, by segment id.
    """
    if graph.time_of_day_h is None or low_sun <= 0.0:
        return dict.fromkeys(graph.segments, fog)
    _, azimuth = sun_position(graph.time_of_day_h)
    losses = {}
    for sid, segment in graph.segments.items():
        exposure = segment_sun_exposure(segment, azimuth)
        losses[sid] = fog + (1.0 - fog) * low_sun * exposure
    return losses


def expected_visibility_loss(graph: WorldRoadGraph) -> dict[str, float]:
    """The forecast's mean visibility loss per lane, from the rain or fog forecast and the time of day."""
    forecast = graph.conditions.get(LOW_VISIBILITY)
    fog = forecast.expected_severity() if forecast else 0.0
    return visibility_loss_by_segment(graph, fog, low_sun_factor_at(graph.time_of_day_h))
