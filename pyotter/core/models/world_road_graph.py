"""World road graph: pyotter's one representation of a CARLA map's drivable lanes.

A segment is one directed lane span between two branch points. Event
probabilities live on the segments, and condition forecasts and the time of day
live on the graph, so a graph with them is one world instance and a graph
without them is a map template.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .world_hazard_library import Hazard, HazardKind

SCHEMA_VERSION = 1
SEVERITY_LEVELS = {"low": 1 / 6, "mid": 1 / 2, "high": 5 / 6}
TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


class RoadGraphError(ValueError):
    pass


@dataclass(frozen=True)
class CenterlinePoint:
    """CARLA world coordinates in meters; `s` is the OpenDRIVE road coordinate."""

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
    return "low" if severity < 1 / 3 else "mid" if severity < 2 / 3 else "high"


@dataclass(frozen=True)
class HazardProbability:
    """An event's probability on one segment: the chance per second that one starts."""

    hazard_id: str
    probability: float


@dataclass(frozen=True)
class ConditionForecast:
    """What a condition may be in a run of this world. Every value is between 0 and 1.

    `probability` is the chance that the condition is present. When it is, its
    severity for the run is drawn evenly from `severity` plus or minus
    `variability`, kept within 0 and 1.
    """

    hazard_id: str
    probability: float
    severity: float
    variability: float = 0.0

    def severity_range(self) -> tuple[float, float]:
        return max(0.0, self.severity - self.variability), min(1.0, self.severity + self.variability)

    def severity_at(self, draw: float) -> float:
        """The severity for a draw between 0 and 1."""
        return min(1.0, max(0.0, self.severity + (2.0 * draw - 1.0) * self.variability))

    def expected_severity(self) -> float:
        """Mean severity over runs, counting a run without the condition as 0."""
        steps = 200
        return self.probability * sum(self.severity_at((i + 0.5) / steps) for i in range(steps)) / steps


@dataclass(frozen=True)
class Junction:
    """An intersection from the map. The box is axis-aligned, in meters, and encloses the junction's lanes."""

    id: int
    x: float
    y: float
    extent_x: float
    extent_y: float

    def contains(self, x: float, y: float) -> bool:
        return abs(x - self.x) <= self.extent_x and abs(y - self.y) <= self.extent_y


@dataclass
class RoadSegment:
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
        """Set the probability of each given event, replacing an earlier value for the same event."""
        current = {item.hazard_id: item for item in self.hazard_probabilities}
        for item in assignments:
            if not isinstance(item, HazardProbability):
                hazard, probability = item
                if isinstance(hazard, Hazard) and hazard.kind is not HazardKind.EVENT:
                    raise RoadGraphError(f"{hazard.id} is a condition; set it for the whole world with set_condition")
                item = HazardProbability(_hazard_id(hazard), float(probability))
            _check_probability(self.id, item)
            current[item.hazard_id] = item
        self.hazard_probabilities = list(current.values())

    def hazard_probability(self, hazard: Hazard | str) -> float:
        wanted = _hazard_id(hazard)
        return next((item.probability for item in self.hazard_probabilities if item.hazard_id == wanted), 0.0)

    def clear_hazard_probabilities(self) -> None:
        self.hazard_probabilities = []

    def points_between(self, start_m: float, end_m: float) -> list[tuple[float, float, float]]:
        """The centerline from one offset to another, including both ends."""
        inside = [(p.x, p.y, p.z) for p in self.centerline if start_m < p.distance_m < end_m]
        return [self.point_at(start_m), *inside, self.point_at(end_m)]

    def point_at(self, offset_m: float) -> tuple[float, float, float]:
        if not 0.0 <= offset_m <= self.length_m + 1e-6:
            raise RoadGraphError(f"{self.id}: offset {offset_m} is outside 0 to {self.length_m}")
        for a, b in zip(self.centerline, self.centerline[1:]):
            if offset_m <= b.distance_m:
                ratio = (offset_m - a.distance_m) / (b.distance_m - a.distance_m)
                return (a.x + ratio * (b.x - a.x), a.y + ratio * (b.y - a.y), a.z + ratio * (b.z - a.z))
        end = self.centerline[-1]
        return (end.x, end.y, end.z)


@dataclass
class WorldRoadGraph:
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
    schema_version: int = SCHEMA_VERSION

    def get_segments(self) -> list[RoadSegment]:
        return list(self.segments.values())

    def get_segment(self, sid: str) -> RoadSegment:
        try:
            return self.segments[sid]
        except KeyError:
            raise RoadGraphError(f"unknown segment: {sid}") from None

    def successors_of(self, sid: str) -> list[RoadSegment]:
        return [self.segments[successor] for successor in self.get_segment(sid).successors]

    def get_junctions(self) -> list[Junction]:
        return list(self.junctions.values())

    def get_junction(self, junction_id: int) -> Junction:
        try:
            return self.junctions[junction_id]
        except KeyError:
            raise RoadGraphError(f"unknown junction: {junction_id}") from None

    def segments_in_junction(self, junction_id: int) -> list[RoadSegment]:
        self.get_junction(junction_id)
        return [segment for segment in self.segments.values() if segment.junction_id == junction_id]

    def set_condition(self, hazard: Hazard | str, *, probability: float, severity: float | str,
                      variability: float = 0.0) -> None:
        """Forecast a condition for the whole world. `severity` is 0 to 1, or "low", "mid" or "high"."""
        if isinstance(hazard, Hazard) and hazard.kind is not HazardKind.CONDITION:
            raise RoadGraphError(f"{hazard.id} is an event; assign it to segments with assign_hazard_probability")
        if isinstance(severity, str):
            if severity not in SEVERITY_LEVELS:
                raise RoadGraphError(f"unknown severity level: {severity}; use one of {', '.join(SEVERITY_LEVELS)}")
            severity = SEVERITY_LEVELS[severity]
        forecast = ConditionForecast(_hazard_id(hazard), float(probability), float(severity), float(variability))
        _check_forecast(forecast)
        self.conditions[forecast.hazard_id] = forecast

    def get_condition(self, hazard: Hazard | str) -> ConditionForecast | None:
        return self.conditions.get(_hazard_id(hazard))

    def set_time_of_day(self, time_of_day_h: float | None) -> None:
        """Hours from midnight, 0 up to 24, or None for a world with no sun model."""
        _check_time(time_of_day_h)
        self.time_of_day_h = time_of_day_h

    def event_ids(self) -> set[str]:
        return {item.hazard_id for segment in self.segments.values() for item in segment.hazard_probabilities}

    def hazard_ids(self) -> set[str]:
        return self.event_ids() | set(self.conditions)

    def forecast_hash(self) -> str:
        """Identifies the forecast, so that spawns and routes can name the one they were made from."""
        events = sorted((sid, item.hazard_id, item.probability)
                        for sid, segment in self.segments.items() for item in segment.hazard_probabilities)
        conditions = sorted((f.hazard_id, f.probability, f.severity, f.variability) for f in self.conditions.values())
        return hashlib.sha256(json.dumps([events, conditions, self.time_of_day_h]).encode()).hexdigest()

    def clear_hazard_probabilities(self) -> None:
        for segment in self.segments.values():
            segment.clear_hazard_probabilities()
        self.conditions = {}

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise RoadGraphError(f"unsupported schema version: {self.schema_version}")
        if not self.segments:
            raise RoadGraphError("graph has no segments")
        for sid, segment in self.segments.items():
            _check_segment(sid, segment, self.segments)
            if segment.in_junction and segment.junction_id not in self.junctions:
                raise RoadGraphError(f"{sid}: unknown junction {segment.junction_id}")
        used = {segment.junction_id for segment in self.segments.values()}
        for key, junction in self.junctions.items():
            if key != junction.id or key not in used:
                raise RoadGraphError(f"junction {key}: key does not match its id, or no segment belongs to it")
        for key, forecast in self.conditions.items():
            if key != forecast.hazard_id:
                raise RoadGraphError(f"condition {key}: key does not match its hazard id")
            _check_forecast(forecast)
        _check_time(self.time_of_day_h)
        for position in self.spawn_points:
            segment = self.get_segment(position.segment_id)
            if not 0.0 <= position.offset_m <= segment.length_m + 1e-6:
                raise RoadGraphError(f"spawn point is off {segment.id}: offset {position.offset_m}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> WorldRoadGraph:
        try:
            segments = {
                sid: RoadSegment(**{
                    **raw,
                    "successors": tuple(raw["successors"]),
                    "centerline": tuple(CenterlinePoint(**point) for point in raw["centerline"]),
                    "hazard_probabilities": [HazardProbability(**item) for item in raw.get("hazard_probabilities", [])],
                })
                for sid, raw in data["segments"].items()
            }
            graph = cls(**{
                **data,
                "segments": segments,
                "junctions": {int(key): Junction(**raw) for key, raw in data.get("junctions", {}).items()},
                "spawn_points": tuple(SegmentPosition(**point) for point in data.get("spawn_points", ())),
                "conditions": {key: ConditionForecast(**raw) for key, raw in data.get("conditions", {}).items()},
            })
        except (KeyError, TypeError) as error:
            raise RoadGraphError(f"malformed road graph: {error}") from None
        graph.validate()
        return graph

    def save(self, path: str | Path) -> None:
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "wt", encoding="utf-8") as stream:
            json.dump(self.to_dict(), stream, sort_keys=True)

    @classmethod
    def load(cls, path: str | Path) -> WorldRoadGraph:
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))

    @classmethod
    def from_template(cls, name: str) -> WorldRoadGraph:
        path = TEMPLATES / f"{name}.json.gz"
        if not path.exists():
            known = sorted(p.name.removesuffix(".json.gz") for p in TEMPLATES.glob("*.json.gz"))
            raise RoadGraphError(f"unknown template: {name}; available: {', '.join(known) or 'none'}")
        return cls.load(path)


def _hazard_id(hazard: Hazard | str) -> str:
    return hazard if isinstance(hazard, str) else hazard.id


def _check_probability(sid: str, item: HazardProbability) -> None:
    p = item.probability
    if not isinstance(p, (int, float)) or not math.isfinite(p) or not 0.0 <= p <= 1.0:
        raise RoadGraphError(f"{sid}: probability of {item.hazard_id} must be between 0 and 1, got {p!r}")


def _check_forecast(forecast: ConditionForecast) -> None:
    for name in ("probability", "severity", "variability"):
        value = getattr(forecast, name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
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
    line = segment.centerline
    if len(line) < 2 or line[0].distance_m != 0.0:
        raise RoadGraphError(f"{sid}: centerline needs at least two points and must start at distance 0")
    if any(b.distance_m <= a.distance_m for a, b in zip(line, line[1:])):
        raise RoadGraphError(f"{sid}: centerline distances must increase")
    if abs(line[-1].distance_m - segment.length_m) > 1e-3:
        raise RoadGraphError(f"{sid}: centerline ends at {line[-1].distance_m}, length is {segment.length_m}")
    seen = set()
    for item in segment.hazard_probabilities:
        _check_probability(sid, item)
        if item.hazard_id in seen:
            raise RoadGraphError(f"{sid}: {item.hazard_id} is assigned twice")
        seen.add(item.hazard_id)
