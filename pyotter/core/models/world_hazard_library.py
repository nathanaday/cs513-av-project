from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from ..utilities.text_enum import TextEnum

PEDESTRIAN = "pedestrian"
LOW_VISIBILITY = "low_visibility"
WET_ROAD = "wet_road"


class HazardKind(TextEnum):
    """How a hazard exists in the world, which also fixes what its forecast means.

    Attributes:
        CONDITION: A state of the whole world that holds for a whole run. It is
            forecast as the chance that it is present, and its severity.
        EVENT: Something that happens at a moment on a segment. It is forecast
            as the chance, per second, that one occurrence starts there.
    """

    CONDITION = "condition"
    EVENT = "event"


@dataclass(frozen=True)
class Hazard:
    """A risk situation, defined without reference to the car or to any outcome."""

    id: str
    kind: HazardKind
    description: str


DEFAULT_HAZARDS = (
    Hazard(PEDESTRIAN, HazardKind.EVENT, "A pedestrian is on or entering the roadway"),
    Hazard(LOW_VISIBILITY, HazardKind.CONDITION, "Detection range is reduced"),
    Hazard(WET_ROAD, HazardKind.CONDITION, "Tire friction is reduced"),
)


class WorldHazardLibrary:
    """Every hazard OTTER supports. Hazards are attributes: `library.pedestrian`."""

    def __init__(self, hazards: Iterable[Hazard] = DEFAULT_HAZARDS):
        self._hazards = {hazard.id: hazard for hazard in hazards}

    def __getattr__(self, name: str) -> Hazard:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._hazards:
            raise AttributeError(f"unknown hazard: {name}")
        return self._hazards[name]

    def __iter__(self) -> Iterator[Hazard]:
        return iter(self._hazards.values())

    def __contains__(self, hazard: Hazard | str) -> bool:
        return hazard_id_of(hazard) in self._hazards

    def get(self, hazard_id: str) -> Hazard:
        return self._hazards[hazard_id]

    def of_kind(self, kind: HazardKind) -> list[Hazard]:
        return [hazard for hazard in self._hazards.values() if hazard.kind is kind]


def hazard_id_of(hazard: Hazard | str) -> str:
    """The id of a hazard given as either a `Hazard` or its id."""
    if isinstance(hazard, Hazard):
        return hazard.id
    return hazard
