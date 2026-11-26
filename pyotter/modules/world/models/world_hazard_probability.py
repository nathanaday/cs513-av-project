"""World hazard probability: a whole forecast in a few numbers, to put on a road graph.

The named forecasts in `config.yaml` (`world.forecasts`) are the scenario set:
the same map under conditions from almost no risk to very dangerous.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

from ....core.models.world_hazard_library import PEDESTRIAN
from ....core.models.world_road_graph import (
    ConditionForecast, RoadGraphError, RoadSegment, WorldRoadGraph, severity_of_level,
)
from ....core.utilities.config import CONFIG
from ....core.utilities.json_file import read_json, write_json

FORECASTS = CONFIG.world.forecasts


@dataclass(frozen=True)
class WorldHazardProbability:
    """A recipe for a world's forecast.

    Attributes:
        name: What the forecast is called, such as "heavy-rain".
        pedestrians_per_km_s: Pedestrian starts per second on each kilometer of lane.
        junction_factor: How many times busier a lane inside a junction is.
            The crosswalks are at the junctions.
        hotspots: (junction id, factor) pairs for junctions busier still. The
            factor multiplies the junction factor.
        conditions: The condition forecasts for the whole world.
        time_of_day_h: Hours from midnight, or None for a world with no sun.
    """

    name: str
    pedestrians_per_km_s: float = 0.0
    junction_factor: float = 1.0
    hotspots: tuple[tuple[int, float], ...] = ()
    conditions: tuple[ConditionForecast, ...] = ()
    time_of_day_h: float | None = None

    def __post_init__(self) -> None:
        factors = [self.pedestrians_per_km_s, self.junction_factor] + [factor for _, factor in self.hotspots]
        if any(not math.isfinite(value) or value < 0.0 for value in factors):
            raise RoadGraphError(f"{self.name}: pedestrian rates and factors must be 0 or more")

    def pedestrian_probability(self, segment: RoadSegment) -> float:
        """The chance per second that a pedestrian starts on a segment.

        Starts arrive at a steady rate, so the chance that at least one starts
        within a second is 1 - exp(-rate). A longer lane gets more of them.
        """
        rate = self.pedestrians_per_km_s * segment.length_m / 1000.0
        if segment.in_junction:
            rate *= self.junction_factor * dict(self.hotspots).get(segment.junction_id, 1.0)
        return 1.0 - math.exp(-rate)

    def apply(self, graph: WorldRoadGraph) -> None:
        """Replace the graph's forecast with this one.

        Raises:
            RoadGraphError: If a hotspot is not a junction of the graph, or a
                value is out of range.
        """
        for junction_id, _ in self.hotspots:
            graph.get_junction(junction_id)
        graph.clear_hazard_probabilities()
        for segment in graph.get_segments():
            probability = self.pedestrian_probability(segment)
            if probability > 0.0:
                segment.assign_hazard_probability([(PEDESTRIAN, probability)])
        for forecast in self.conditions:
            graph.set_condition(forecast.hazard_id, probability=forecast.probability,
                                severity=forecast.severity, variability=forecast.variability)
        graph.set_time_of_day(self.time_of_day_h)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> WorldHazardProbability:
        """Build a forecast from the output of `to_dict`.

        Raises:
            RoadGraphError: If a field is missing or unknown.
        """
        try:
            fields = dict(data)
            fields["hotspots"] = tuple((int(junction_id), float(factor)) for junction_id, factor in data["hotspots"])
            fields["conditions"] = tuple(ConditionForecast(**raw) for raw in data["conditions"])
            return cls(**fields)
        except (KeyError, TypeError, ValueError) as error:
            raise RoadGraphError(f"malformed forecast: {error}") from None

    def save(self, path: str | Path) -> None:
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> WorldHazardProbability:
        return cls.from_dict(read_json(path))

    @staticmethod
    def names() -> list[str]:
        """The forecasts in `config.yaml`, from least risk to most."""
        return [name for name, _ in FORECASTS.items()]

    @classmethod
    def from_config(cls, name: str) -> WorldHazardProbability:
        """The named forecast from `config.yaml`.

        Raises:
            RoadGraphError: If there is no forecast of that name.
        """
        values = dict(FORECASTS.items()).get(name)
        if values is None:
            raise RoadGraphError(f"unknown forecast: {name}; use one of {', '.join(cls.names())}")
        settings = dict(values.items())
        hotspots = settings.get("hotspots")
        conditions = settings.get("conditions")
        return cls(
            name=name,
            pedestrians_per_km_s=float(settings.get("pedestrians_per_km_s", 0.0)),
            junction_factor=float(settings.get("junction_factor", 1.0)),
            hotspots=tuple((int(key), float(factor)) for key, factor in hotspots.items()) if hotspots else (),
            conditions=tuple(_condition(key, raw) for key, raw in conditions.items()) if conditions else (),
            time_of_day_h=settings.get("time_of_day_h"),
        )


def _condition(hazard_id: str, raw) -> ConditionForecast:
    """A condition forecast from its entry in `config.yaml`, where severity may be a level name."""
    severity = raw.severity
    if isinstance(severity, str):
        severity = severity_of_level(severity)
    variability = dict(raw.items()).get("variability", 0.0)
    return ConditionForecast(hazard_id, float(raw.probability), float(severity), float(variability))
