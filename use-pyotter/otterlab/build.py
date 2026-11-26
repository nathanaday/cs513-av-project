"""Build the scenario set: each named forecast, a few seeds, and every way of choosing a route.

The scenarios of one forecast and seed share their rolled hazards, so the
naive, cautious and risk-aware drives of them can be compared directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyotter import Driver, Planner, World
from pyotter.core import WorldHazardLibrary, WorldRoadGraph
from pyotter.modules.planner import PlannerConfig, RouteMode

from .console import LabError
from .settings import RUNS, SETTINGS

BUILT = RUNS / "scenario-set"


@dataclass(frozen=True)
class Built:
    """One scenario file that was written.

    Attributes:
        path: Where the file is.
        forecast: The forecast's name.
        seed: The seed its hazards were rolled from.
        mode: How its route was chosen.
        planned_s: The planner's estimate of the drive's time.
        events: How many events were rolled.
        fingerprint: The SHA-256 of the file's bytes.
    """

    path: Path
    forecast: str
    seed: int
    mode: RouteMode
    planned_s: float
    events: int
    fingerprint: str


def build(forecasts: list[str], seeds: list[int], output: Path = BUILT) -> list[Built]:
    """Write one scenario file per forecast, seed and route mode.

    The trip, the planner's weights and how long to roll hazards for come
    from `build` in `otter.yaml`.

    Args:
        forecasts: Names from `world.forecasts` in pyotter's `config.yaml`.
        seeds: The seeds to roll each forecast with.
        output: The folder to write into.

    Returns:
        What was written, in order.

    Raises:
        LabError: If a forecast is unknown, or a seed was given twice.
    """
    known = World.forecast_names()
    unknown = [name for name in forecasts if name not in known]
    if unknown:
        raise LabError(f"Unknown forecast: {', '.join(unknown)}.", f"Use any of {', '.join(known)}.")
    if len(set(seeds)) != len(seeds):
        raise LabError("A seed was given twice.")
    hazards = WorldHazardLibrary()
    built = []
    for forecast in forecasts:
        for seed in seeds:
            built += _build_one(forecast, seed, output, hazards)
    return built


def _build_one(forecast: str, seed: int, output: Path, hazards: WorldHazardLibrary) -> list[Built]:
    """The three scenarios of one forecast and seed, sharing one roll of the hazards."""
    settings = SETTINGS.build
    graph = WorldRoadGraph.from_template(settings.template)
    World.forecast(graph, forecast)
    spawns = World.roll_hazards(graph, hazards, seed=seed, duration_s=settings.duration_s)
    start, end = graph.spawn_points[settings.start_spawn], graph.spawn_points[settings.end_spawn]
    config = PlannerConfig(weights=dict(settings.hazard_weights.items()))
    built = []
    for mode in RouteMode:
        route = Planner.route(start, end, graph, mode=mode, risk_scale=settings.risk_scale, config=config)
        name = f"{settings.template}-{forecast}-seed{seed}-{mode.value}"
        scenario = Driver.scenario(graph, spawns, route, name=name)
        path = output / f"{name}.json.gz"
        scenario.save(path)
        built.append(Built(path, forecast, seed, mode, route.estimated_time_s, len(spawns.events),
                           scenario.fingerprint))
    return built
