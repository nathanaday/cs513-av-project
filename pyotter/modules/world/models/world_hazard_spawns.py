"""World hazard spawns: the hazards that actually occur in one run, rolled from the forecast and a seed.

The spawns are kept apart from the road graph so that a planner, which may
read only the forecast, cannot see them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ....core.models.world_hazard_library import Hazard, hazard_id_of
from ....core.models.world_road_graph import RoadGraphError, SegmentPosition, severity_level
from ....core.utilities.config import CONFIG
from ....core.utilities.json_file import read_json, write_json


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
    """The sun for the run.

    Attributes:
        strength: The visibility lost, from 0 to 1, when facing straight at the sun.
    """

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
    """Everything one roll produced.

    Attributes:
        graph_id: The road graph the spawns were rolled on.
        probabilities_hash: The forecast hash of that graph when they were rolled.
        duration_s: The length of simulation time the events were rolled for.
        events: The event starts, in time order.
        sun: The sun, or None for a world with no time of day.
    """

    graph_id: str
    probabilities_hash: str
    seed: int
    duration_s: float
    conditions: tuple[ConditionSpawn, ...]
    events: tuple[EventSpawn, ...]
    sun: SunGlare | None = None
    schema_version: int = CONFIG.schema_version

    def condition_severity(self, hazard: Hazard | str) -> float:
        """The condition's severity this run, or 0 if it is not present."""
        wanted = hazard_id_of(hazard)
        for spawn in self.conditions:
            if spawn.hazard_id == wanted:
                return spawn.severity
        return 0.0

    def events_of(self, hazard: Hazard | str) -> list[EventSpawn]:
        wanted = hazard_id_of(hazard)
        return [spawn for spawn in self.events if spawn.hazard_id == wanted]

    def events_on(self, segment_id: str) -> list[EventSpawn]:
        return [spawn for spawn in self.events if spawn.position.segment_id == segment_id]

    def hazard_ids(self) -> set[str]:
        return {spawn.hazard_id for spawn in self.conditions + self.events}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> WorldHazardSpawns:
        """Build spawns from the output of `to_dict`.

        Raises:
            RoadGraphError: If a field is missing or unknown.
        """
        try:
            fields = dict(data)
            fields["conditions"] = tuple(ConditionSpawn(**raw) for raw in data["conditions"])
            fields["events"] = tuple(_event_from_dict(raw) for raw in data["events"])
            fields["sun"] = SunGlare(**data["sun"]) if data.get("sun") else None
            return cls(**fields)
        except (KeyError, TypeError) as error:
            raise RoadGraphError(f"malformed hazard spawns: {error}") from None

    def save(self, path: str | Path) -> None:
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> WorldHazardSpawns:
        return cls.from_dict(read_json(path))


def _event_from_dict(raw: dict) -> EventSpawn:
    return EventSpawn(raw["hazard_id"], SegmentPosition(**raw["position"]), raw["start_s"])
