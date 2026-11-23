from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlannerConfig:
    """The planner's tuning.

    Each segment is priced at every candidate speed at or below its limit, and
    at the limit itself. `exposure_baseline` is the share of a hazard that
    accrues per second whatever the speed; with it above 0 the penalty is lowest
    at `reference_speed_kmh * sqrt(exposure_baseline)` and rises again below
    that, so a fine speed grid cannot push the plan toward a standstill.
    """

    candidate_speeds_kmh: tuple[float, ...] = tuple(float(v) for v in range(1, 101))
    reference_speed_kmh: float = 30.0
    cautious_speed_kmh: float = 20.0
    exposure_baseline: float = 0.25
    weights: dict[str, float] = field(default_factory=dict)

    def weight(self, hazard_id: str) -> float:
        """A hazard with no listed weight counts at 1."""
        return self.weights.get(hazard_id, 1.0)
