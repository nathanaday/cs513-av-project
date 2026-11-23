"""World hazard spawns: the hazards that actually occur in one run, rolled from the probabilities and a seed.

The spawns are kept apart from the road graph so that a planner, which may
read only probabilities, cannot see them.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ....core.models.world_hazard_library import Hazard
from ....core.models.world_road_graph import RoadGraphError, SegmentPosition, severity_level

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ConditionSpawn:
    """A condition that holds everywhere for the whole run, at a severity from 0 to 1."""

    hazard_id: str
    severity: float

    @property
    def level(self) -> str:
        return severity_level(self.severity)


@dataclass(frozen=True)
class SunGlare:
    """The sun for the run. `strength` is the visibility lost, from 0 to 1, when facing straight at it."""

    time_of_day_h: float
    altitude_deg: float
    azimuth_deg: float
    strength: float


@dataclass(frozen=True)
class EventSpawn:
    """One occurrence of an event: where on the map, and when in simulation time, it starts."""

    hazard_id: str
    position: SegmentPosition
    start_s: float


@dataclass(frozen=True)
class WorldHazardSpawns:
    graph_id: str
    probabilities_hash: str
    seed: int
    duration_s: float
    conditions: tuple[ConditionSpawn, ...]
    events: tuple[EventSpawn, ...]
    sun: SunGlare | None = None
    schema_version: int = SCHEMA_VERSION

    def condition_severity(self, hazard: Hazard | str) -> float:
        """The condition's severity this run, or 0 if it is not present."""
        wanted = hazard if isinstance(hazard, str) else hazard.id
        return next((spawn.severity for spawn in self.conditions if spawn.hazard_id == wanted), 0.0)

    def events_on(self, segment_id: str) -> list[EventSpawn]:
        return [spawn for spawn in self.events if spawn.position.segment_id == segment_id]

    def hazard_ids(self) -> set[str]:
        return {spawn.hazard_id for spawn in self.conditions + self.events}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> WorldHazardSpawns:
        try:
            return cls(**{
                **data,
                "conditions": tuple(ConditionSpawn(**raw) for raw in data["conditions"]),
                "events": tuple(
                    EventSpawn(raw["hazard_id"], SegmentPosition(**raw["position"]), raw["start_s"])
                    for raw in data["events"]
                ),
                "sun": SunGlare(**data["sun"]) if data.get("sun") else None,
            })
        except (KeyError, TypeError) as error:
            raise RoadGraphError(f"malformed hazard spawns: {error}") from None

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "wt", encoding="utf-8") as stream:
            json.dump(self.to_dict(), stream, sort_keys=True)

    @classmethod
    def load(cls, path: str | Path) -> WorldHazardSpawns:
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))
