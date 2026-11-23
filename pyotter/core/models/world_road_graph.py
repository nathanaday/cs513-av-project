"""World road graph: pyotter's one representation of a CARLA map's drivable lanes.

A segment is one directed lane span between two branch points. Hazard
probabilities live on the segment, so a graph with assignments is one world
instance and a graph without them is a map template.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .world_hazard_library import Hazard

SCHEMA_VERSION = 1
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


@dataclass(frozen=True)
class HazardProbability:
    """A hazard's probability on one segment. Its meaning follows the hazard's kind; see HazardKind."""

    hazard_id: str
    probability: float


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
        """Set the probability of each given hazard, replacing an earlier value for the same hazard."""
        current = {item.hazard_id: item for item in self.hazard_probabilities}
        for item in assignments:
            if not isinstance(item, HazardProbability):
                hazard, probability = item
                item = HazardProbability(_hazard_id(hazard), float(probability))
            _check_probability(self.id, item)
            current[item.hazard_id] = item
        self.hazard_probabilities = list(current.values())

    def hazard_probability(self, hazard: Hazard | str) -> float:
        wanted = _hazard_id(hazard)
        return next((item.probability for item in self.hazard_probabilities if item.hazard_id == wanted), 0.0)

    def clear_hazard_probabilities(self) -> None:
        self.hazard_probabilities = []

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

    def hazard_ids(self) -> set[str]:
        return {item.hazard_id for segment in self.segments.values() for item in segment.hazard_probabilities}

    def clear_hazard_probabilities(self) -> None:
        for segment in self.segments.values():
            segment.clear_hazard_probabilities()

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
