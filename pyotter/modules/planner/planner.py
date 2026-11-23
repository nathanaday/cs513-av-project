"""Route and speed search over a world road graph and its hazard forecast.

The planner reads the forecast on the graph and nothing else. It never sees the
hazards rolled for a run.
"""

from __future__ import annotations

from ...core.models.world_hazard_library import LOW_VISIBILITY
from ...core.models.world_road_graph import SegmentPosition, WorldRoadGraph
from ...core.utilities.sun import expected_visibility_loss
from .models.planner_computed_waypoints import PlannerComputedWaypoints, RouteStep
from .models.planner_config import PlannerConfig
from .models.route_mode import RouteMode
from .utilities import (
    PlanningError,
    build_edges,
    cheapest_path,
    check_config,
    check_limits_verified,
    check_number,
    check_position,
    price_step,
)

SHORTEST_STEP_M = 1e-9


class Planner:
    @staticmethod
    def hazard_scores(graph: WorldRoadGraph, config: PlannerConfig | None = None) -> dict[str, float]:
        """Reduce the forecast to one weighted number per segment, which is all the pricing reads.

        A segment's score adds each event's chance per second there, the
        expected visibility loss on that lane, and the expected severity of
        every other condition, each times its weight.

        Args:
            graph: The world, with its forecast.
            config: The tuning, for the weights. Defaults to `PlannerConfig()`.

        Returns:
            The score by segment id.
        """
        config = config or PlannerConfig()
        visibility_loss = expected_visibility_loss(graph)
        everywhere = 0.0
        for hazard_id, forecast in graph.conditions.items():
            if hazard_id != LOW_VISIBILITY:
                everywhere += config.weight(hazard_id) * forecast.expected_severity()
        scores = {}
        for sid, segment in graph.segments.items():
            events = sum(config.weight(item.hazard_id) * item.probability for item in segment.hazard_probabilities)
            scores[sid] = everywhere + config.weight(LOW_VISIBILITY) * visibility_loss[sid] + events
        return scores

    @staticmethod
    def route(origin: SegmentPosition, destination: SegmentPosition, graph: WorldRoadGraph, *,
              risk_scale: float = 1.0, mode: RouteMode | str = RouteMode.RISK_AWARE,
              config: PlannerConfig | None = None, require_verified_limits: bool = False) -> PlannerComputedWaypoints:
        """Choose the segments to drive and a target speed on each.

        Args:
            origin: Where the route starts.
            destination: Where the route ends.
            graph: The world, with its forecast.
            risk_scale: The weight of the predicted penalty against time, in
                the risk-aware mode. The other modes ignore it.
            mode: How the route is chosen. See `RouteMode`.
            config: The tuning. Defaults to `PlannerConfig()`.
            require_verified_limits: Whether to refuse a graph with a speed
                limit that was not read from the simulator.

        Returns:
            The route, with a target speed on each stretch.

        Raises:
            PlanningError: If an input is invalid, or no legal route exists.
        """
        config = config or PlannerConfig()
        mode = _route_mode(mode)
        check_number(risk_scale, "risk scale")
        check_position(origin, "origin", graph)
        check_position(destination, "destination", graph)
        check_config(config)
        if require_verified_limits:
            check_limits_verified(graph)

        if mode is not RouteMode.RISK_AWARE:
            risk_scale = 0.0
        scores = Planner.hazard_scores(graph, config)
        edges = build_edges(graph, origin, destination, scores, risk_scale, config)
        steps = [step for step in cheapest_path(edges) if step.distance_m > SHORTEST_STEP_M]
        if mode is RouteMode.CAUTIOUS:
            # Capping the speed after the search keeps the cautious route on the naive route.
            steps = [_capped(step, graph, config) for step in steps]
        return PlannerComputedWaypoints(
            graph_id=graph.graph_id,
            forecast_hash=graph.forecast_hash(),
            origin=origin,
            destination=destination,
            mode=mode,
            risk_scale=float(risk_scale),
            config=config,
            steps=tuple(steps),
        )


def _route_mode(mode: RouteMode | str) -> RouteMode:
    try:
        return RouteMode(mode)
    except ValueError:
        known = ", ".join(known_mode.value for known_mode in RouteMode)
        raise PlanningError(f"unknown mode: {mode}; use one of {known}") from None


def _capped(step: RouteStep, graph: WorldRoadGraph, config: PlannerConfig) -> RouteStep:
    """The same stretch, priced again at the cautious speed or the segment's limit, whichever is lower."""
    segment = graph.segments[step.segment_id]
    speed_kmh = min(config.cautious_speed_kmh, segment.speed_limit_kmh)
    return price_step(segment, step.start_offset_m, step.end_offset_m, speed_kmh, step.hazard_score, config)
