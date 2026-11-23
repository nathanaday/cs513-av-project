"""Driving scenario: everything one run needs, in one file.

It carries the world as rolled (the road graph and the hazards that occur),
the route to follow, and the driver. The driver reads the actual conditions and
spawns here, never the forecast's probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ....core.models.world_road_graph import RoadGraphError, WorldRoadGraph
from ....core.utilities.config import CONFIG
from ....core.utilities.json_file import file_fingerprint, read_json, write_json
from ...planner.models.planner_computed_waypoints import PlannerComputedWaypoints
from ...world.models.world_hazard_spawns import WorldHazardSpawns
from .driver_model import DriverModel


@dataclass
class DrivingScenario:
    """One run to drive.

    Attributes:
        graph: The world the run takes place in.
        spawns: The hazards that occur in the run, rolled on that graph.
        route: The route to follow, planned on that graph.
        driver: What the driver can see and how it brakes.
        name: A label for the run, carried into its telemetry.
        delta_s: The length of one simulation tick.
        fingerprint: The SHA-256 of the file the scenario was loaded from or
            saved to, and empty before either. It identifies the scenario in
            the telemetry of its runs. It is not part of the file.
    """

    graph: WorldRoadGraph
    spawns: WorldHazardSpawns
    route: PlannerComputedWaypoints
    driver: DriverModel = field(default_factory=DriverModel)
    name: str = ""
    delta_s: float = CONFIG.driver.tick_s
    schema_version: int = CONFIG.schema_version
    fingerprint: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        self.validate()

    @property
    def duration_s(self) -> float:
        """When the run ends if the car has not arrived: the time the hazards were rolled for."""
        return self.spawns.duration_s

    def validate(self) -> None:
        """Check that the spawns, the route and the graph belong together.

        Raises:
            RoadGraphError: On the first problem found.
        """
        graph = self.graph
        if self.spawns.graph_id != graph.graph_id or self.spawns.probabilities_hash != graph.forecast_hash():
            raise RoadGraphError("the spawns were rolled from a different map or a different forecast")
        if self.route.graph_id != graph.graph_id:
            raise RoadGraphError("the route was planned on a different map")
        if not self.route.steps:
            raise RoadGraphError("the route is empty")
        for step in self.route.steps:
            graph.get_segment(step.segment_id)
        longest_tick_s = CONFIG.driver.longest_tick_s
        if not 0.0 < self.delta_s <= longest_tick_s:
            raise RoadGraphError(f"the tick must be above 0 and at most {longest_tick_s:g} s")
        if self.route.estimated_time_s > self.duration_s:
            raise RoadGraphError(
                f"the route needs about {self.route.estimated_time_s:.0f} s but the hazards were "
                f"rolled for {self.duration_s:g} s; roll a longer run"
            )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "delta_s": self.delta_s,
            "graph": self.graph.to_dict(),
            "spawns": self.spawns.to_dict(),
            "route": self.route.to_dict(),
            "driver": self.driver.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> DrivingScenario:
        return cls(
            graph=WorldRoadGraph.from_dict(data["graph"]),
            spawns=WorldHazardSpawns.from_dict(data["spawns"]),
            route=PlannerComputedWaypoints.from_dict(data["route"]),
            driver=DriverModel.from_dict(data["driver"]),
            name=data.get("name", ""),
            delta_s=data["delta_s"],
            schema_version=data["schema_version"],
        )

    def save(self, path: str | Path) -> None:
        write_json(path, self.to_dict())
        self.fingerprint = file_fingerprint(path)

    @classmethod
    def load(cls, path: str | Path) -> DrivingScenario:
        scenario = cls.from_dict(read_json(path))
        scenario.fingerprint = file_fingerprint(path)
        return scenario
