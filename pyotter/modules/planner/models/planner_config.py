from __future__ import annotations

from dataclasses import dataclass, field

from ....core.utilities.config import CONFIG

SETTINGS = CONFIG.planner


def _default_candidate_speeds() -> tuple[float, ...]:
    speeds = range(SETTINGS.slowest_candidate_kmh, SETTINGS.fastest_candidate_kmh + 1)
    return tuple(float(speed) for speed in speeds)


def _default_weights() -> dict[str, float]:
    return dict(SETTINGS.hazard_weights.items())


@dataclass(frozen=True)
class PlannerConfig:
    """The planner's tuning.

    Attributes:
        candidate_speeds_kmh: The speeds tried on each segment. Only those at
            or below the segment's limit are used, and the limit itself is
            always tried.
        reference_speed_kmh: The speed at which the speed-dependent part of the
            penalty rate equals the hazard score.
        cautious_speed_kmh: The speed cap of the cautious mode.
        exposure_baseline: The share of a hazard that accrues per second
            whatever the speed. With it above 0 the penalty is lowest at
            `reference_speed_kmh * sqrt(exposure_baseline)` and rises again
            below that, so a fine speed grid cannot push the plan toward a
            standstill.
        weights: The weight of each hazard, by id.
    """

    candidate_speeds_kmh: tuple[float, ...] = field(default_factory=_default_candidate_speeds)
    reference_speed_kmh: float = SETTINGS.reference_speed_kmh
    cautious_speed_kmh: float = SETTINGS.cautious_speed_kmh
    exposure_baseline: float = SETTINGS.exposure_baseline
    weights: dict[str, float] = field(default_factory=_default_weights)

    def weight(self, hazard_id: str) -> float:
        """The weight of a hazard, or the default weight if it has none listed."""
        return self.weights.get(hazard_id, SETTINGS.default_hazard_weight)
