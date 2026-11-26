from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ....core.models.driving_safety_req import DrivingSafetyReq
from ....core.utilities.config import CONFIG

SETTINGS = CONFIG.driver.model


@dataclass(frozen=True)
class DriverModel:
    """What the driver can see and how it brakes.

    Attributes:
        safety: The limits the driver aims to keep.
        detection_range_m: How far ahead the driver notices another road user
            in clear conditions. A visibility loss shrinks it in proportion.
        comfortable_deceleration_mps2: The braking the driver plans with, kept
            below the safety limit so that there is something in reserve.
        min_detection_range_m: The least the driver sees, however poor the visibility.
        wet_braking_loss: The share of its planned braking the driver gives up
            on a fully wet road.
        anticipation_s: How many seconds ahead the driver predicts where a
            pedestrian it sees will walk. 0 turns it off.
        drive_within_sight: Whether the driver keeps its speed low enough to stop,
            at its planned braking, short of a road user that appears at the edge of its sight.
        vehicle_blueprint: The CARLA blueprint of the car.
    """

    safety: DrivingSafetyReq = field(default_factory=DrivingSafetyReq)
    detection_range_m: float = SETTINGS.detection_range_m
    comfortable_deceleration_mps2: float = SETTINGS.comfortable_deceleration_mps2
    min_detection_range_m: float = SETTINGS.min_detection_range_m
    wet_braking_loss: float = SETTINGS.wet_braking_loss
    anticipation_s: float = SETTINGS.anticipation_s
    drive_within_sight: bool = SETTINGS.drive_within_sight
    vehicle_blueprint: str = SETTINGS.vehicle_blueprint

    def detection_range(self, visibility_loss: float) -> float:
        """Meters the driver can see, given a visibility loss from 0 (none) to 1 (total)."""
        return max(self.min_detection_range_m, self.detection_range_m * (1.0 - visibility_loss))

    def planned_deceleration(self, wet_severity: float) -> float:
        """The braking the driver plans with on a road of the given wetness, from 0 (dry) to 1."""
        return self.comfortable_deceleration_mps2 * (1.0 - self.wet_braking_loss * wet_severity)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DriverModel:
        fields = dict(data)
        fields["safety"] = DrivingSafetyReq(**data["safety"])
        return cls(**fields)
