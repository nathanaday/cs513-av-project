"""World road graph: pyotter's one representation of a CARLA map's drivable lanes.

A segment is one directed lane span between two branch points. Event
probabilities live on the segments, and condition forecasts and the time of day
live on the graph, so a graph with them is one world instance and a graph
without them is a map template.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from ..utilities.config import CONFIG
from ..utilities.json_file import read_json, write_json
from .world_hazard_library import Hazard, HazardKind, hazard_id_of

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
OFFSET_TOLERANCE_M = 1e-6
LENGTH_TOLERANCE_M = 1e-3


class RoadGraphError(ValueError):
    pass


@dataclass(frozen=True)
class CenterlinePoint:
    """One point of a lane's centerline, in CARLA world coordinates in meters.

    Attributes:
        s: The OpenDRIVE road coordinate of the point.
        distance_m: Meters from the start of the segment, in the driving direction.
    """

    x: float
    y: float
    z: float
    s: float
    distance_m: float


@dataclass(frozen=True)
class SegmentPosition:
    """A point on a segment, measured in the driving direction from its start."""

    segment_id: str
    offset_m: float


def severity_level(severity: float) -> str:
    """The name of the band of the 0 to 1 scale that a severity falls in."""
    levels = CONFIG.world.severity_levels
    for index, level in enumerate(levels):
        if severity < (index + 1) / len(levels):
            return level
    return levels[-1]


def severity_of_level(level: str) -> float:
    """The severity at the center of a named band.

    Raises:
        RoadGraphError: If the level is not one of the configured names.
    """
    levels = CONFIG.world.severity_levels
    if level not in levels:
        raise RoadGraphError(f"unknown severity level: {level}; use one of {', '.join(levels)}")
    return (levels.index(level) + 0.5) / len(levels)


@dataclass(frozen=True)
class HazardProbability:
    """An event's probability on one segment: the chance per second that one starts."""

    hazard_id: str
    probability: float


@dataclass(frozen=True)
class ConditionForecast:
    """What a condition may be in a run of this world. Every value is between 0 and 1.

    Attributes:
        probability: The chance that the condition is present in a run.
        severity: The center of the severity the condition has when present.
        variability: How far either side of `severity` a run's severity may
            fall. It is drawn evenly from that range and kept within 0 and 1.
    """

    hazard_id: str
    probability: float
    severity: float
    variability: float = 0.0

    def severity_range(self) -> tuple[float, float]:
        low = max(0.0, self.severity - self.variability)
        high = min(1.0, self.severity + self.variability)
        return low, high

    def severity_at(self, draw: float) -> float:
        """The severity for a draw between 0 and 1."""
        severity = self.severity + (2.0 * draw - 1.0) * self.variability
        return min(1.0, max(0.0, severity))

    def expected_severity(self) -> float:
        """Mean severity over runs, counting a run without the condition as 0."""
        steps = CONFIG.world.expected_severity_steps
        total = sum(self.severity_at((step + 0.5) / steps) for step in range(steps))
        return self.probability * total / steps


@dataclass(frozen=True)
class Junction:
    """An intersection from the map.

    The box is axis-aligned, in meters, and encloses the junction's lanes.
    `x` and `y` are its center, and the extents are half its size.
    """

    id: int
    x: float
    y: float
    extent_x: float
    extent_y: float

    def contains(self, x: float, y: float) -> bool:
        return abs(x - self.x) <= self.extent_x and abs(y - self.y) <= self.extent_y


@dataclass
class RoadSegment:
    """One directed lane span, with the event probabilities assigned to it.

    Attributes:
        junction_id: The junction the lane crosses, or None on a road.
        speed_limit_verified: Whether the limit was read from the simulator.
        successors: Ids of the segments that may be driven next.
    """

    road_id: int
    section_id: int
    lane_id: int
    junction_id: int | None
    length_m: float
    speed_limit_kmh: float
    speed_limit_verified: bool
    successors: tuple[str, ...]
    centerline: tuple[CenterlinePoint, ...]
    hazard_probabilities: list[HazardProbability] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"r{self.road_id}.s{self.section_id}.l{self.lane_id}"

    @property
    def in_junction(self) -> bool:
        return self.junction_id is not None

    def assign_hazard_probability(self, assignments: Iterable[HazardProbability | tuple[Hazard | str, float]]) -> None:
        """Set the probability of each given event, replacing an earlier value for the same event.

        Args:
            assignments: Each is a `HazardProbability`, or a pair of an event
                (or its id) and its chance per second, from 0 to 1.

        Raises:
            RoadGraphError: If a hazard is a condition, or a probability is not
                between 0 and 1.
        """
        current = {item.hazard_id: item for item in self.hazard_probabilities}
        for assignment in assignments:
            item = self._as_hazard_probability(assignment)
            _check_probability(self.id, item)
            current[item.hazard_id] = item
        self.hazard_probabilities = list(current.values())

    def _as_hazard_probability(self, assignment: HazardProbability | tuple[Hazard | str, float]) -> HazardProbability:
        if isinstance(assignment, HazardProbability):
            return assignment
        hazard, probability = assignment
        if isinstance(hazard, Hazard) and hazard.kind is not HazardKind.EVENT:
            raise RoadGraphError(f"{hazard.id} is a condition; set it for the whole world with set_condition")
        return HazardProbability(hazard_id_of(hazard), float(probability))

    def hazard_probability(self, hazard: Hazard | str) -> float:
        """The chance per second that the event starts here, or 0 if it is not assigned."""
        wanted = hazard_id_of(hazard)
        for item in self.hazard_probabilities:
            if item.hazard_id == wanted:
                return item.probability
        return 0.0

    def clear_hazard_probabilities(self) -> None:
        self.hazard_probabilities = []

    def points_between(self, start_m: float, end_m: float) -> list[tuple[float, float, float]]:
        """The centerline from one offset to another, including both ends."""
        inside = [(point.x, point.y, point.z) for point in self.centerline if start_m < point.distance_m < end_m]
        return [self.point_at(start_m), *inside, self.point_at(end_m)]

    def s_at(self, offset_m: float) -> float:
        """The OpenDRIVE road coordinate at an offset, for finding the same point in CARLA."""
        for before, after in zip(self.centerline, self.centerline[1:]):
            if offset_m <= after.distance_m:
                ratio = (offset_m - before.distance_m) / (after.distance_m - before.distance_m)
                return before.s + ratio * (after.s - before.s)
        return self.centerline[-1].s

    def heading_at(self, offset_m: float) -> float:
        """The driving direction at an offset, in degrees in the map frame."""
        behind = self.point_at(max(0.0, offset_m - 0.5))
        ahead = self.point_at(min(self.length_m, offset_m + 0.5))
        return math.degrees(math.atan2(ahead[1] - behind[1], ahead[0] - behind[0]))

    def point_at(self, offset_m: float) -> tuple[float, float, float]:
        """The (x, y, z) of the centerline at an offset.

        Raises:
            RoadGraphError: If the offset is outside the segment.
        """
        if not 0.0 <= offset_m <= self.length_m + OFFSET_TOLERANCE_M:
            raise RoadGraphError(f"{self.id}: offset {offset_m} is outside 0 to {self.length_m}")
        for before, after in zip(self.centerline, self.centerline[1:]):
            if offset_m <= after.distance_m:
                ratio = (offset_m - before.distance_m) / (after.distance_m - before.distance_m)
                return (
                    before.x + ratio * (after.x - before.x),
                    before.y + ratio * (after.y - before.y),
                    before.z + ratio * (after.z - before.z),
                )
        end = self.centerline[-1]
        return (end.x, end.y, end.z)


@dataclass
class WorldRoadGraph:
    """A map's segments and junctions, with the hazard forecast for one world.

    Attributes:
        map_hash: Hash of the map's OpenDRIVE text, to recognize the same map
            on a server.
        spawn_points: The map's recommended places to start a car.
        conditions: The forecast of each condition, by hazard id.
        time_of_day_h: Hours from midnight, or None for a world with no sun model.
    """

    graph_id: str
    map_name: str
    map_hash: str
    carla_version: str
    provenance: str
    segments: dict[str, RoadSegment]
    junctions: dict[int, Junction] = field(default_factory=dict)
    spawn_points: tuple[SegmentPosition, ...] = ()
    conditions: dict[str, ConditionForecast] = field(default_factory=dict)
    time_of_day_h: float | None = None
    schema_version: int = CONFIG.schema_version

    def get_segments(self) -> list[RoadSegment]:
        return list(self.segments.values())

    def get_segment(self, sid: str) -> RoadSegment:
        if sid not in self.segments:
            raise RoadGraphError(f"unknown segment: {sid}")
        return self.segments[sid]

    def successors_of(self, sid: str) -> list[RoadSegment]:
        return [self.segments[successor] for successor in self.get_segment(sid).successors]

    def get_junctions(self) -> list[Junction]:
        return list(self.junctions.values())

    def get_junction(self, junction_id: int) -> Junction:
        if junction_id not in self.junctions:
            raise RoadGraphError(f"unknown junction: {junction_id}")
        return self.junctions[junction_id]

    def segments_in_junction(self, junction_id: int) -> list[RoadSegment]:
        self.get_junction(junction_id)
        return [segment for segment in self.segments.values() if segment.junction_id == junction_id]

    def set_condition(self, hazard: Hazard | str, *, probability: float, severity: float | str,
                      variability: float = 0.0) -> None:
        """Forecast a condition for the whole world.

        Args:
            hazard: The condition, or its id.
            probability: The chance that it is present in a run, from 0 to 1.
            severity: Its severity when present, from 0 to 1, or the name of a
                severity level.
            variability: How far either side of `severity` a run may fall.

        Raises:
            RoadGraphError: If the hazard is an event, or a value is out of range.
        """
        if isinstance(hazard, Hazard) and hazard.kind is not HazardKind.CONDITION:
            raise RoadGraphError(f"{hazard.id} is an event; assign it to segments with assign_hazard_probability")
        if isinstance(severity, str):
            severity = severity_of_level(severity)
        forecast = ConditionForecast(hazard_id_of(hazard), float(probability), float(severity), float(variability))
        _check_forecast(forecast)
        self.conditions[forecast.hazard_id] = forecast

    def get_condition(self, hazard: Hazard | str) -> ConditionForecast | None:
        return self.conditions.get(hazard_id_of(hazard))

    def set_time_of_day(self, time_of_day_h: float | None) -> None:
        """Set the hours from midnight, 0 up to 24, or None for a world with no sun model."""
        _check_time(time_of_day_h)
        self.time_of_day_h = time_of_day_h

    def event_ids(self) -> set[str]:
        """Ids of the events assigned on at least one segment."""
        ids = set()
        for segment in self.segments.values():
            for item in segment.hazard_probabilities:
                ids.add(item.hazard_id)
        return ids

    def hazard_ids(self) -> set[str]:
        """Ids of every hazard in the forecast, events and conditions."""
        return self.event_ids() | set(self.conditions)

    def forecast_hash(self) -> str:
        """Identifies the forecast, so that spawns and routes can name the one they were made from."""
        events = []
        for sid, segment in self.segments.items():
            for item in segment.hazard_probabilities:
                events.append((sid, item.hazard_id, item.probability))
        conditions = [
            (forecast.hazard_id, forecast.probability, forecast.severity, forecast.variability)
            for forecast in self.conditions.values()
        ]
        text = json.dumps([sorted(events), sorted(conditions), self.time_of_day_h])
        return hashlib.sha256(text.encode()).hexdigest()

    def clear_hazard_probabilities(self) -> None:
        """Remove every event probability and every condition forecast."""
        for segment in self.segments.values():
            segment.clear_hazard_probabilities()
        self.conditions = {}

    def validate(self) -> None:
        """Check that the graph is whole and every value is in range.

        Raises:
            RoadGraphError: On the first problem found.
        """
        if self.schema_version != CONFIG.schema_version:
            raise RoadGraphError(f"unsupported schema version: {self.schema_version}")
        if not self.segments:
            raise RoadGraphError("graph has no segments")
        for sid, segment in self.segments.items():
            _check_segment(sid, segment, self.segments)
            if segment.in_junction and segment.junction_id not in self.junctions:
                raise RoadGraphError(f"{sid}: unknown junction {segment.junction_id}")
        self._check_junctions()
        self._check_conditions()
        _check_time(self.time_of_day_h)
        self._check_spawn_points()

    def _check_junctions(self) -> None:
        used = {segment.junction_id for segment in self.segments.values()}
        for key, junction in self.junctions.items():
            if key != junction.id or key not in used:
                raise RoadGraphError(f"junction {key}: key does not match its id, or no segment belongs to it")

    def _check_conditions(self) -> None:
        for key, forecast in self.conditions.items():
            if key != forecast.hazard_id:
                raise RoadGraphError(f"condition {key}: key does not match its hazard id")
            _check_forecast(forecast)

    def _check_spawn_points(self) -> None:
        for position in self.spawn_points:
            segment = self.get_segment(position.segment_id)
            if not 0.0 <= position.offset_m <= segment.length_m + OFFSET_TOLERANCE_M:
                raise RoadGraphError(f"spawn point is off {segment.id}: offset {position.offset_m}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> WorldRoadGraph:
        """Build and validate a graph from the output of `to_dict`.

        Raises:
            RoadGraphError: If a field is missing or unknown, or the graph is invalid.
        """
        try:
            fields = dict(data)
            fields["segments"] = {sid: _segment_from_dict(raw) for sid, raw in data["segments"].items()}
            fields["junctions"] = {int(key): Junction(**raw) for key, raw in data.get("junctions", {}).items()}
            fields["spawn_points"] = tuple(SegmentPosition(**raw) for raw in data.get("spawn_points", ()))
            fields["conditions"] = {key: ConditionForecast(**raw) for key, raw in data.get("conditions", {}).items()}
            graph = cls(**fields)
        except (KeyError, TypeError) as error:
            raise RoadGraphError(f"malformed road graph: {error}") from None
        graph.validate()
        return graph

    def save(self, path: str | Path) -> None:
        self.validate()
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> WorldRoadGraph:
        return cls.from_dict(read_json(path))

    @classmethod
    def from_template(cls, name: str) -> WorldRoadGraph:
        """Load a map that ships with pyotter, with no forecast on it.

        Raises:
            RoadGraphError: If there is no template of that name.
        """
        path = TEMPLATES / f"{name}.json.gz"
        if not path.exists():
            known = sorted(template.name.removesuffix(".json.gz") for template in TEMPLATES.glob("*.json.gz"))
            raise RoadGraphError(f"unknown template: {name}; available: {', '.join(known) or 'none'}")
        return cls.load(path)


def _segment_from_dict(raw: dict) -> RoadSegment:
    fields = dict(raw)
    fields["successors"] = tuple(raw["successors"])
    fields["centerline"] = tuple(CenterlinePoint(**point) for point in raw["centerline"])
    fields["hazard_probabilities"] = [HazardProbability(**item) for item in raw.get("hazard_probabilities", [])]
    return RoadSegment(**fields)


def _is_share(value: object) -> bool:
    """Whether a value is a number from 0 to 1."""
    return isinstance(value, (int, float)) and math.isfinite(value) and 0.0 <= value <= 1.0


def _check_probability(sid: str, item: HazardProbability) -> None:
    if not _is_share(item.probability):
        raise RoadGraphError(
            f"{sid}: probability of {item.hazard_id} must be between 0 and 1, got {item.probability!r}"
        )


def _check_forecast(forecast: ConditionForecast) -> None:
    for name in ("probability", "severity", "variability"):
        value = getattr(forecast, name)
        if not _is_share(value):
            raise RoadGraphError(f"{forecast.hazard_id}: {name} must be between 0 and 1, got {value!r}")


def _check_time(time_of_day_h: float | None) -> None:
    if time_of_day_h is not None and not 0.0 <= time_of_day_h < 24.0:
        raise RoadGraphError(f"time of day must be from 0 up to 24 hours, got {time_of_day_h!r}")


def _check_segment(sid: str, segment: RoadSegment, segments: dict[str, RoadSegment]) -> None:
    if sid != segment.id:
        raise RoadGraphError(f"{sid}: key does not match the segment's id {segment.id}")
    if not segment.length_m > 0 or not segment.speed_limit_kmh > 0:
        raise RoadGraphError(f"{sid}: length and speed limit must be positive")
    for successor in segment.successors:
        if successor not in segments:
            raise RoadGraphError(f"{sid}: unknown successor {successor}")
    _check_centerline(sid, segment)
    seen = set()
    for item in segment.hazard_probabilities:
        _check_probability(sid, item)
        if item.hazard_id in seen:
            raise RoadGraphError(f"{sid}: {item.hazard_id} is assigned twice")
        seen.add(item.hazard_id)


def _check_centerline(sid: str, segment: RoadSegment) -> None:
    line = segment.centerline
    if len(line) < 2 or line[0].distance_m != 0.0:
        raise RoadGraphError(f"{sid}: centerline needs at least two points and must start at distance 0")
    for before, after in zip(line, line[1:]):
        if after.distance_m <= before.distance_m:
            raise RoadGraphError(f"{sid}: centerline distances must increase")
    if abs(line[-1].distance_m - segment.length_m) > LENGTH_TOLERANCE_M:
        raise RoadGraphError(f"{sid}: centerline ends at {line[-1].distance_m}, length is {segment.length_m}")
