from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Iterator


class HazardKind(str, Enum):
    """How a hazard exists on a segment, which also fixes what its probability means.

    CONDITION: a state of the segment that holds for the whole run. Its
    probability is the chance that the state is present in a run.
    EVENT: something that happens at a moment. Its probability is the chance,
    per second, that one occurrence starts on the segment.
    """

    CONDITION = "condition"
    EVENT = "event"


@dataclass(frozen=True)
class Hazard:
    """A risk situation on a segment, defined without reference to the car or to any outcome."""

    id: str
    kind: HazardKind
    description: str


LOW_VISIBILITY = "low_visibility"

DEFAULT_HAZARDS = (
    Hazard("pedestrian", HazardKind.EVENT, "A pedestrian is on or entering the roadway"),
    Hazard(LOW_VISIBILITY, HazardKind.CONDITION, "Detection range is reduced"),
    Hazard("wet_road", HazardKind.CONDITION, "Tire friction is reduced"),
)


class WorldHazardLibrary:
    """Every hazard OTTER supports. Hazards are attributes: `library.pedestrian`."""

    def __init__(self, hazards: Iterable[Hazard] = DEFAULT_HAZARDS):
        self._hazards = {hazard.id: hazard for hazard in hazards}

    def __getattr__(self, name: str) -> Hazard:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._hazards[name]
        except KeyError:
            raise AttributeError(f"unknown hazard: {name}") from None

    def __iter__(self) -> Iterator[Hazard]:
        return iter(self._hazards.values())

    def __contains__(self, hazard: Hazard | str) -> bool:
        return (hazard if isinstance(hazard, str) else hazard.id) in self._hazards

    def get(self, hazard_id: str) -> Hazard:
        return self._hazards[hazard_id]

    def of_kind(self, kind: HazardKind) -> list[Hazard]:
        return [hazard for hazard in self._hazards.values() if hazard.kind is kind]
