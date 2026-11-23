from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ForecastMap:
    """What one map of the forecast figure shows.

    Attributes:
        values: The value to shade each segment by.
        top: The value at the dark end of the scale.
        lines: The subtitle lines.
        unit: The label of the scale.
    """

    values: dict[str, float]
    top: float
    lines: list[str]
    unit: str
