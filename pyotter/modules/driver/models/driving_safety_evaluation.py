"""Driving safety evaluation: whether a run kept each safety requirement, and by how much."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ....core.utilities.stl import Formula
from .driving_scenario_telemetry import Outcome, Signal


@dataclass(frozen=True)
class SafetyRequirement:
    """One safety requirement, as a condition that must hold at every sample of a run.

    Attributes:
        unit: The unit of the condition's robustness.
        limit: The size of the limit, for comparing margins across requirements.
        watched: The signal to report at the moment of least margin.
        condition: The formula that must always hold.
    """

    name: str
    unit: str
    limit: float
    watched: Signal
    condition: Formula


@dataclass(frozen=True)
class RequirementResult:
    """One requirement checked against one run.

    Attributes:
        formula: The requirement, written in signal temporal logic.
        robustness: In the requirement's unit. Positive is the spare margin,
            and negative is how far past the limit the run went.
        margin_ratio: The robustness divided by the limit, so that requirements
            in different units can be compared.
        worst_time_s: When the run came closest to, or went furthest past, the limit.
        worst_value: The watched signal at that time.
    """

    name: str
    formula: str
    unit: str
    limit: float
    robustness: float
    margin_ratio: float
    worst_time_s: float
    worst_value: float

    @property
    def satisfied(self) -> bool:
        return self.robustness >= 0.0


@dataclass(frozen=True)
class DrivingSafetyEvaluation:
    """Every requirement checked against one run."""

    scenario_name: str
    outcome: Outcome
    duration_s: float
    distance_m: float
    collisions: int
    requirements: tuple[RequirementResult, ...]

    @property
    def satisfied(self) -> bool:
        return all(result.satisfied for result in self.requirements)

    @property
    def breached(self) -> list[RequirementResult]:
        return [result for result in self.requirements if not result.satisfied]

    @property
    def closest(self) -> RequirementResult:
        """The requirement with the least margin: the worst breach, or else the nearest miss."""
        return min(self.requirements, key=lambda result: result.margin_ratio)

    def get(self, name: str) -> RequirementResult:
        """The result of the requirement of that name.

        Raises:
            KeyError: If there is none.
        """
        for result in self.requirements:
            if result.name == name:
                return result
        raise KeyError(name)

    def summary(self) -> str:
        """The evaluation as text: one headline, then one line per requirement."""
        verdict = "all requirements kept" if self.satisfied else "BREACHED"
        lines = [
            f"{self.scenario_name or 'run'}: {self.outcome}, {self.duration_s:.1f} s, {self.distance_m:.0f} m, "
            f"{self.collisions} collisions, {verdict}"
        ]
        for result in self.requirements:
            kept = "sat  " if result.satisfied else "unsat"
            lines.append(
                f"  {result.name:15} {kept} margin {result.robustness:+8.2f} {result.unit:6} "
                f"({result.margin_ratio:+7.0%}) worst at {result.worst_time_s:6.1f} s   {result.formula}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        data["satisfied"] = self.satisfied
        for raw, result in zip(data["requirements"], self.requirements):
            raw["satisfied"] = result.satisfied
        return data

    def save(self, path: str | Path) -> None:
        """Write the evaluation as indented JSON, for reading."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
