"""Planner computed waypoints: the route through a world road graph, with a target speed on each stretch."""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ....core.models.world_road_graph import SegmentPosition
from .planner_config import PlannerConfig

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RouteStep:
    """One stretch of one segment, driven at one target speed. Offsets run in the driving direction."""

    segment_id: str
    start_offset_m: float
    end_offset_m: float
    target_speed_kmh: float
    estimated_time_s: float
    predicted_penalty: float
    hazard_score: float

    @property
    def distance_m(self) -> float:
        return self.end_offset_m - self.start_offset_m


@dataclass(frozen=True)
class PlannerComputedWaypoints:
    graph_id: str
    forecast_hash: str
    origin: SegmentPosition
    destination: SegmentPosition
    mode: str
    risk_scale: float
    config: PlannerConfig
    steps: tuple[RouteStep, ...]
    schema_version: int = SCHEMA_VERSION

    @property
    def distance_m(self) -> float:
        return sum(step.distance_m for step in self.steps)

    @property
    def estimated_time_s(self) -> float:
        return sum(step.estimated_time_s for step in self.steps)

    @property
    def predicted_penalty(self) -> float:
        return sum(step.predicted_penalty for step in self.steps)

    @property
    def objective(self) -> float:
        """What the search minimized: time plus the risk scale times the penalty."""
        return self.estimated_time_s + self.risk_scale * self.predicted_penalty

    @property
    def segment_ids(self) -> list[str]:
        return [step.segment_id for step in self.steps]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PlannerComputedWaypoints:
        config = dict(data["config"], candidate_speeds_kmh=tuple(data["config"]["candidate_speeds_kmh"]))
        return cls(**{
            **data,
            "origin": SegmentPosition(**data["origin"]),
            "destination": SegmentPosition(**data["destination"]),
            "config": PlannerConfig(**config),
            "steps": tuple(RouteStep(**raw) for raw in data["steps"]),
        })

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "wt", encoding="utf-8") as stream:
            json.dump(self.to_dict(), stream, sort_keys=True)

    @classmethod
    def load(cls, path: str | Path) -> PlannerComputedWaypoints:
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))
