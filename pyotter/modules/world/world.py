"""The world: check a forecast, and roll the hazards of one run from it."""

from __future__ import annotations

from ...core.models.world_hazard_library import WorldHazardLibrary
from ...core.models.world_road_graph import RoadGraphError, WorldRoadGraph
from ...core.utilities.config import CONFIG
from .models.world_hazard_spawns import WorldHazardSpawns
from .utilities import check_forecast, roll_conditions, roll_events, sun_glare


class World:
    @staticmethod
    def check_forecast(graph: WorldRoadGraph, library: WorldHazardLibrary) -> None:
        """Check that the graph has a forecast, and that it agrees with the library.

        Raises:
            RoadGraphError: If nothing is forecast, a hazard is not in the library,
                or an event and a condition are forecast as each other.
        """
        check_forecast(graph, library)

    @staticmethod
    def roll_hazards(graph: WorldRoadGraph, library: WorldHazardLibrary, seed: int, *,
                     duration_s: float = CONFIG.world.roll_duration_s) -> WorldHazardSpawns:
        """Decide which hazards occur in one run.

        The same graph, seed and duration always give the same spawns. A
        condition is drawn once for the whole world: whether it is present, and
        at what severity. An event is drawn once per second of simulation time
        on each segment, and each success starts within that second at a drawn
        point along the segment. The sun's glare follows from the time of day
        and the rolled visibility.

        Each condition, and each segment and event pair, has its own random
        stream, so changing one forecast leaves every other outcome unchanged,
        and a longer duration only appends events after the earlier ones.

        Args:
            graph: The world, with its forecast.
            library: The hazards the forecast may name.
            seed: Selects the run.
            duration_s: The length of simulation time to roll events for.

        Returns:
            The conditions, event starts and sun of the run.

        Raises:
            RoadGraphError: If the duration is not positive, or the forecast is
                empty or disagrees with the library.
        """
        if duration_s <= 0:
            raise RoadGraphError("duration must be positive")
        check_forecast(graph, library)
        conditions = roll_conditions(graph, seed)
        events = roll_events(graph, seed, duration_s)
        return WorldHazardSpawns(
            graph_id=graph.graph_id,
            probabilities_hash=graph.forecast_hash(),
            seed=seed,
            duration_s=float(duration_s),
            conditions=tuple(conditions),
            events=tuple(events),
            sun=sun_glare(graph, conditions),
        )
