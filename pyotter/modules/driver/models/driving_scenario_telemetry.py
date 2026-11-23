"""Driving scenario telemetry: what the car did in one run, tick by tick."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from ....core.utilities.config import CONFIG
from ....core.utilities.json_file import read_json, write_json
from ....core.utilities.text_enum import TextEnum
from .driver_model import DriverModel

NO_GAP_M = 1000.0


class Signal(TextEnum):
    """The columns of a run, sampled once per tick. Units are in the names.

    Attributes:
        TIME_S: Simulation time since the run started.
        SPEED_MPS: Speed along the car's heading.
        ACCELERATION_MPS2: The change in speed since the tick before.
        TARGET_SPEED_MPS: The route's planned speed here.
        ALLOWED_SPEED_MPS: The speed the driver chose, at or below the target.
        PROGRESS_M: Distance driven along the route.
        GAP_M: Distance from the car's body to the nearest other road user, or
            `NO_GAP_M` when there is none.
        GAP_AHEAD_M: Distance along the route to the nearest road user the
            driver has noticed in its path, or `NO_GAP_M`.
        DETECTION_RANGE_M: How far ahead the driver could see.
        COLLISION: 1 on a tick with a contact and 0 otherwise.
    """

    TIME_S = "time_s"
    X = "x"
    Y = "y"
    Z = "z"
    YAW_DEG = "yaw_deg"
    SPEED_MPS = "speed_mps"
    ACCELERATION_MPS2 = "acceleration_mps2"
    TARGET_SPEED_MPS = "target_speed_mps"
    SPEED_LIMIT_MPS = "speed_limit_mps"
    ALLOWED_SPEED_MPS = "allowed_speed_mps"
    THROTTLE = "throttle"
    BRAKE = "brake"
    STEER = "steer"
    PROGRESS_M = "progress_m"
    REMAINING_M = "remaining_m"
    GAP_M = "gap_m"
    GAP_AHEAD_M = "gap_ahead_m"
    DETECTION_RANGE_M = "detection_range_m"
    COLLISION = "collision"


class Outcome(TextEnum):
    """How a run ended. A run is an error until it arrives or runs out of time."""

    ARRIVED = "arrived"
    TIMED_OUT = "timed_out"
    ERROR = "error"


class TelemetryEventKind(TextEnum):
    """What happened at a moment of a run.

    Attributes:
        HAZARD_STARTED: A rolled event began in the simulator.
        HAZARD_BLOCKED: A rolled event could not begin, because its place was occupied.
        HAZARD_ENDED: A started event finished.
    """

    COLLISION = "collision"
    HAZARD_STARTED = "hazard_started"
    HAZARD_BLOCKED = "hazard_blocked"
    HAZARD_ENDED = "hazard_ended"
    ARRIVED = "arrived"


@dataclass(frozen=True)
class TelemetryEvent:
    time_s: float
    kind: TelemetryEventKind
    detail: dict = field(default_factory=dict)


def _empty_signals() -> dict[Signal, list[float]]:
    return {signal: [] for signal in Signal}


@dataclass
class DrivingScenarioTelemetry:
    """The record of one run.

    Attributes:
        route_mode: The mode of the route that was driven.
        route_risk_scale: The risk scale of that route.
        driver: The driver the run was driven with.
        delta_s: The length of one simulation tick.
        conditions: The severity of each condition in the run, by name.
        provenance: Where the run was driven: client, server and host.
        signals: Equal-length columns, one value per tick.
    """

    scenario_name: str
    graph_id: str
    map_name: str
    seed: int
    route_mode: str
    route_risk_scale: float
    driver: DriverModel
    delta_s: float
    conditions: dict[str, float] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    outcome: Outcome = Outcome.ERROR
    signals: dict[Signal, list[float]] = field(default_factory=_empty_signals)
    events: list[TelemetryEvent] = field(default_factory=list)
    schema_version: int = CONFIG.schema_version

    def __post_init__(self) -> None:
        self.outcome = Outcome(self.outcome)

    def add_sample(self, **values: float) -> None:
        """Append one tick. Give every signal by name: `add_sample(time_s=0.0, x=1.5, ...)`."""
        for name, value in values.items():
            self.signals[name].append(float(value))

    def add_event(self, time_s: float, kind: TelemetryEventKind, **detail) -> None:
        self.events.append(TelemetryEvent(float(time_s), TelemetryEventKind(kind), detail))

    def __len__(self) -> int:
        return len(self.signals[Signal.TIME_S])

    @property
    def duration_s(self) -> float:
        times = self.signals[Signal.TIME_S]
        if not times:
            return 0.0
        return times[-1] - times[0]

    @property
    def distance_m(self) -> float:
        progress = self.signals[Signal.PROGRESS_M]
        if not progress:
            return 0.0
        return progress[-1]

    def events_of(self, kind: TelemetryEventKind) -> list[TelemetryEvent]:
        return [event for event in self.events if event.kind == kind]

    def validate(self) -> None:
        """Check that every signal is present and all have the same length.

        Raises:
            ValueError: If not.
        """
        lengths = {len(column) for column in self.signals.values()}
        if set(self.signals) != set(Signal) or len(lengths) != 1:
            raise ValueError("telemetry needs every signal, all of the same length")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        data["signals"] = {signal.value: column for signal, column in self.signals.items()}
        for raw, event in zip(data["events"], self.events):
            raw["kind"] = event.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> DrivingScenarioTelemetry:
        """Build and validate telemetry from the output of `to_dict`.

        Raises:
            ValueError: If a signal, outcome or event kind is unknown, or the
                signals are incomplete.
        """
        fields = dict(data)
        fields["driver"] = DriverModel.from_dict(data["driver"])
        fields["outcome"] = Outcome(data["outcome"])
        fields["signals"] = {Signal(name): column for name, column in data["signals"].items()}
        fields["events"] = [
            TelemetryEvent(raw["time_s"], TelemetryEventKind(raw["kind"]), raw["detail"]) for raw in data["events"]
        ]
        telemetry = cls(**fields)
        telemetry.validate()
        return telemetry

    def save(self, path: str | Path) -> None:
        self.validate()
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path) -> DrivingScenarioTelemetry:
        return cls.from_dict(read_json(path))
