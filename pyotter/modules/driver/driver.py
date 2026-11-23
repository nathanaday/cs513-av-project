"""The driver: follow a route through a rolled world, record the run, and check it against the safety requirements."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ...core.models.driving_safety_req import DrivingSafetyReq
from ...core.models.world_road_graph import WorldRoadGraph
from ...core.utilities.config import CONFIG
from ...core.utilities.mapview import THEME, matplotlib_tools, series_color, style_chart
from ...core.utilities.stl import always, eventually, signal
from ..planner.models.planner_computed_waypoints import PlannerComputedWaypoints
from ..world.models.world_hazard_spawns import WorldHazardSpawns
from .models.driver_model import DriverModel
from .models.driving_safety_evaluation import DrivingSafetyEvaluation, RequirementResult, SafetyRequirement
from .models.driving_scenario import DrivingScenario
from .models.driving_scenario_telemetry import NO_GAP_M, DrivingScenarioTelemetry, Signal, TelemetryEventKind

if TYPE_CHECKING:
    from matplotlib.figure import Figure

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

    @staticmethod
    def view_telemetry(telemetry: DrivingScenarioTelemetry | Iterable[DrivingScenarioTelemetry]) -> Figure:
        """Draw runs over time: speed, the gap to the nearest other road user, and acceleration.

        Dashed lines are the safety limits of the first run. A cross marks a collision.

        Args:
            telemetry: One run, or several to compare.

        Returns:
            The figure.

        Raises:
            ValueError: If there is no run, or a run has no samples.
        """
        pyplot, _ = matplotlib_tools("view_telemetry")
        runs = [telemetry] if isinstance(telemetry, DrivingScenarioTelemetry) else list(telemetry)
        if not runs or not all(len(run) for run in runs):
            raise ValueError("every run needs at least one sample")
        figure, (speed_axes, gap_axes, force_axes) = pyplot.subplots(
            3, 1, figsize=(13, 9), dpi=130, sharex=True, facecolor=THEME.surface, layout="constrained",
        )
        for index, run in enumerate(runs):
            _draw_run(speed_axes, gap_axes, force_axes, run, index)
        _draw_limits(speed_axes, gap_axes, force_axes, runs[0])

        gap_shown_m = THEME.gap_shown_m
        labels = {
            speed_axes: "speed (km/h)",
            gap_axes: f"gap to nearest road user (m), up to {gap_shown_m:g}",
            force_axes: "acceleration (m/s2)",
        }
        for axes, label in labels.items():
            style_chart(axes)
            axes.set_ylabel(label, color=THEME.ink_secondary, fontsize=9.5)
        safety = runs[0].driver.safety
        speed_axes.set_ylim(0.0, None)
        gap_axes.set_ylim(0.0, gap_shown_m)
        force_axes.set_ylim(-safety.max_deceleration_mps2 * 1.3, safety.max_acceleration_mps2 * 1.6)
        force_axes.set_xlabel("simulation time (s)", color=THEME.ink_secondary)
        speed_axes.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=len(runs) + 1, frameon=False,
                          fontsize=9, labelcolor=THEME.ink_secondary)
        figure.suptitle("Driving telemetry", x=0.02, ha="left", fontsize=14, color=THEME.ink)
        return figure


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


def _draw_run(speed_axes, gap_axes, force_axes, run: DrivingScenarioTelemetry, index: int) -> None:
    color = series_color(index)
    times = run.signals[Signal.TIME_S]
    speeds_kmh = [speed * KMH_PER_MPS for speed in run.signals[Signal.SPEED_MPS]]
    # A sample with no other road user leaves a break in the gap line.
    gaps = [gap if gap < NO_GAP_M else float("nan") for gap in run.signals[Signal.GAP_M]]
    speed_axes.plot(times, speeds_kmh, color=color, linewidth=1.8, label=run.scenario_name or f"run {index + 1}")
    gap_axes.plot(times, gaps, color=color, linewidth=1.8)
    force_axes.plot(times, run.signals[Signal.ACCELERATION_MPS2], color=color, linewidth=1.2)
    hits = [event.time_s for event in run.events_of(TelemetryEventKind.COLLISION)]
    gap_axes.scatter(hits, [0.0] * len(hits), marker="x", s=70, color=color, linewidths=2.0, zorder=5, clip_on=False)


def _draw_limits(speed_axes, gap_axes, force_axes, run: DrivingScenarioTelemetry) -> None:
    """Draw one run's speed limit and safety limits as dashed lines."""
    safety = run.driver.safety
    limits_kmh = [limit * KMH_PER_MPS for limit in run.signals[Signal.SPEED_LIMIT_MPS]]
    speed_axes.plot(run.signals[Signal.TIME_S], limits_kmh, color=THEME.ink_muted, linewidth=1.0, linestyle="--",
                    label="speed limit")
    _draw_limit(gap_axes, safety.min_gap_m, f" minimum gap {safety.min_gap_m:g} m")
    _draw_limit(force_axes, safety.max_acceleration_mps2, f" acceleration limit {safety.max_acceleration_mps2:g} m/s2")
    _draw_limit(force_axes, -safety.max_deceleration_mps2, f" braking limit {safety.max_deceleration_mps2:g} m/s2")


def _draw_limit(axes, value: float, label: str) -> None:
    axes.axhline(value, color=THEME.ink_muted, linewidth=1.0, linestyle="--")
    axes.text(0.0, value, label, color=THEME.ink_secondary, fontsize=8.5, va="bottom")
