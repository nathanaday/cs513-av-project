"""The driver: follow a route through a rolled world, record the run, and check it against the safety requirements."""

from __future__ import annotations

from ...core.models.driving_safety_req import DrivingSafetyReq
from ...core.models.world_road_graph import WorldRoadGraph
from ...core.utilities.config import CONFIG
from ...core.utilities.stl import always, eventually, signal
from ..planner.models.planner_computed_waypoints import PlannerComputedWaypoints
from ..world.models.world_hazard_spawns import WorldHazardSpawns
from .models.driver_model import DriverModel
from .models.driving_safety_evaluation import DrivingSafetyEvaluation, RequirementResult, SafetyRequirement
from .models.driving_scenario import DrivingScenario
from .models.driving_scenario_telemetry import DrivingScenarioTelemetry, Signal, TelemetryEventKind

KMH_PER_MPS = 3.6
# A collision signal is 0 or 1, so the midpoint separates the two with equal margin.
COLLISION_THRESHOLD = 0.5


class Driver:
    @staticmethod
    def scenario(graph: WorldRoadGraph, spawns: WorldHazardSpawns, route: PlannerComputedWaypoints, *,
                 driver: DriverModel | None = None, name: str = "") -> DrivingScenario:
        """Bundle one run: the rolled world, the route, and the driver.

        Args:
            graph: The world the run takes place in.
            spawns: The hazards that occur, rolled on that graph.
            route: The route to follow, planned on that graph.
            driver: What the driver can see and how it brakes. Defaults to `DriverModel()`.
            name: A label for the run.

        Raises:
            RoadGraphError: If the spawns, the route and the graph do not belong together.
        """
        return DrivingScenario(graph, spawns, route, driver or DriverModel(), name)

    @staticmethod
    def run(scenario: DrivingScenario, *, host: str = CONFIG.carla.host, port: int = CONFIG.carla.port,
            timeout_s: float = CONFIG.carla.drive_timeout_s) -> DrivingScenarioTelemetry:
        """Drive the scenario on a running CARLA server and return what was recorded."""
        from .carla_runner import run_scenario

        return run_scenario(scenario, host=host, port=port, timeout_s=timeout_s)

    @staticmethod
    def requirements(safety: DrivingSafetyReq) -> list[SafetyRequirement]:
        """Write the safety limits as conditions that must hold at every sample of a run.

        Acceleration is the change in speed from one tick to the next, so a
        single tick can spike when the car's gears engage or it touches
        something. The two acceleration limits therefore count as breached only
        when exceeded for the configured sustained time without a break.
        """
        settings = CONFIG.driver.evaluation
        sustained_s = settings.sustained_s
        tolerance_mps = safety.speed_tolerance_kmh / KMH_PER_MPS
        acceleration = signal(Signal.ACCELERATION_MPS2)
        return [
            SafetyRequirement(
                name="no_collision",
                unit="",
                limit=COLLISION_THRESHOLD,
                watched=Signal.COLLISION,
                condition=signal(Signal.COLLISION) <= COLLISION_THRESHOLD,
            ),
            SafetyRequirement(
                name="min_gap",
                unit="m",
                limit=safety.min_gap_m,
                watched=Signal.GAP_M,
                condition=signal(Signal.GAP_M) >= safety.min_gap_m,
            ),
            SafetyRequirement(
                name="braking",
                unit="m/s2",
                limit=safety.max_deceleration_mps2,
                watched=Signal.ACCELERATION_MPS2,
                condition=eventually(acceleration >= -safety.max_deceleration_mps2, 0.0, sustained_s),
            ),
            SafetyRequirement(
                name="acceleration",
                unit="m/s2",
                limit=safety.max_acceleration_mps2,
                watched=Signal.ACCELERATION_MPS2,
                condition=eventually(acceleration <= safety.max_acceleration_mps2, 0.0, sustained_s),
            ),
            SafetyRequirement(
                name="speed_limit",
                unit="m/s",
                limit=max(tolerance_mps, settings.least_speed_scale_mps),
                watched=Signal.SPEED_MPS,
                condition=signal(Signal.SPEED_MPS) <= signal(Signal.SPEED_LIMIT_MPS) + tolerance_mps,
            ),
        ]

    @staticmethod
    def evaluate(telemetry: DrivingScenarioTelemetry,
                 safety: DrivingSafetyReq | None = None) -> DrivingSafetyEvaluation:
        """Check a run against the safety requirements, each written as `always (condition)`.

        Args:
            telemetry: The run.
            safety: The limits to check. Defaults to those the run was driven with.

        Returns:
            Whether each requirement was kept, by what margin, and when the
            margin was least.

        Raises:
            ValueError: If the telemetry has no samples.
        """
        if not len(telemetry):
            raise ValueError("the telemetry has no samples")
        safety = safety or telemetry.driver.safety
        results = [_check(requirement, telemetry) for requirement in Driver.requirements(safety)]
        return DrivingSafetyEvaluation(
            scenario_name=telemetry.scenario_name,
            outcome=telemetry.outcome,
            duration_s=telemetry.duration_s,
            distance_m=telemetry.distance_m,
            collisions=len(telemetry.events_of(TelemetryEventKind.COLLISION)),
            requirements=tuple(results),
        )


def _check(requirement: SafetyRequirement, telemetry: DrivingScenarioTelemetry) -> RequirementResult:
    """Check one requirement against a run, and find the sample where its margin was least."""
    trace = telemetry.signals
    formula = always(requirement.condition)
    robustness = formula.robustness(trace)[0]
    margins = requirement.condition.robustness(trace)
    worst = margins.index(min(margins))
    return RequirementResult(
        name=requirement.name,
        formula=str(formula),
        unit=requirement.unit,
        limit=requirement.limit,
        robustness=robustness,
        margin_ratio=robustness / requirement.limit,
        worst_time_s=trace[Signal.TIME_S][worst],
        worst_value=trace[requirement.watched][worst],
    )
