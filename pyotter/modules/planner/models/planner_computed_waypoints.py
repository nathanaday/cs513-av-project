"""Planner computed waypoints: the route through a world road graph, with a target speed on each stretch."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ....core.models.world_road_graph import SegmentPosition
from ....core.utilities.config import CONFIG
from ....core.utilities.json_file import read_json, write_json
from .planner_config import PlannerConfig
from .route_mode import RouteMode


@dataclass(frozen=True)
class RouteStep:
    """One stretch of one segment, driven at one target speed.

    Attributes:
        start_offset_m: Where the stretch starts, in the driving direction.
        end_offset_m: Where the stretch ends.
        predicted_penalty: The penalty the planner expects on the stretch.
        hazard_score: The segment's weighted forecast, which the penalty is priced from.
    """

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
    """A planned route.

    Attributes:
        graph_id: The road graph the route was planned on.
        forecast_hash: The forecast hash of that graph when it was planned.
        risk_scale: The weight the search gave the predicted penalty. It is 0
            in the naive and cautious modes.
        config: The tuning the route was planned with.
        steps: The stretches to drive, in order.
    """

    graph_id: str
    forecast_hash: str
    origin: SegmentPosition
    destination: SegmentPosition
    mode: RouteMode
    risk_scale: float
    config: PlannerConfig
    steps: tuple[RouteStep, ...]
    schema_version: int = CONFIG.schema_version

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
        data = asdict(self)
        data["mode"] = self.mode.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> PlannerComputedWaypoints:
        config = dict(data["config"])
        config["candidate_speeds_kmh"] = tuple(config["candidate_speeds_kmh"])
        fields = dict(data)
        fields["origin"] = SegmentPosition(**data["origin"])
        fields["destination"] = SegmentPosition(**data["destination"])
        fields["mode"] = RouteMode(data["mode"])
        fields["config"] = PlannerConfig(**config)
        fields["steps"] = tuple(RouteStep(**raw) for raw in data["steps"])
        return cls(**fields)

    def save(self, path: str | Path) -> None:
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> PlannerComputedWaypoints:
        return cls.from_dict(read_json(path))
