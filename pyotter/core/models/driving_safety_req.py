from __future__ import annotations

from dataclasses import dataclass, fields

from ..utilities.config import CONFIG


@dataclass(frozen=True)
class DrivingSafetyReq:
    """The limits a drive must stay within.

    The driver aims to keep them, and the evaluation checks them.

    Attributes:
        min_gap_m: The least distance allowed between the car's body and any
            other road user.
        max_deceleration_mps2: The hardest braking allowed.
        max_acceleration_mps2: The hardest speeding up allowed.
        speed_tolerance_kmh: How far over a speed limit still counts as keeping it.
    """

    min_gap_m: float = CONFIG.safety.min_gap_m
    max_deceleration_mps2: float = CONFIG.safety.max_deceleration_mps2
    max_acceleration_mps2: float = CONFIG.safety.max_acceleration_mps2
    speed_tolerance_kmh: float = CONFIG.safety.speed_tolerance_kmh

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
            if not is_number or not value >= 0:
                raise ValueError(f"{field.name} must be a number of 0 or more, got {value!r}")
        if self.max_deceleration_mps2 == 0 or self.max_acceleration_mps2 == 0:
            raise ValueError("the acceleration and deceleration limits must be above 0")
