"""The pieces of the driver's figure: each run's signals and the safety limits."""

from __future__ import annotations

from ..driver.models.driving_scenario_telemetry import NO_GAP_M, DrivingScenarioTelemetry, Signal, TelemetryEventKind
from .utilities import THEME, series_color

KMH_PER_MPS = 3.6


def draw_run(speed_axes, gap_axes, force_axes, run: DrivingScenarioTelemetry, index: int) -> None:
    color = series_color(index)
    times = run.signals[Signal.TIME_S]
    speeds_kmh = [speed * KMH_PER_MPS for speed in run.signals[Signal.SPEED_MPS]]
    # A sample with no other road user leaves a break in the gap line.
    gaps = [gap if gap < NO_GAP_M else float("nan") for gap in run.signals[Signal.GAP_M]]
    speed_axes.plot(times, speeds_kmh, color=color, linewidth=1.8, label=run.scenario_name or f"run {index + 1}")
    gap_axes.plot(times, gaps, color=color, linewidth=1.8)
    force_axes.plot(times, run.signals[Signal.ACCELERATION_MPS2], color=color, linewidth=1.2)
    hits = [event.time_s for event in run.events_of(TelemetryEventKind.COLLISION)]
    gap_axes.scatter(hits, [0.0] * len(hits), marker="x", s=70, color=color, linewidths=2.0, zorder=5, clip_on=False)


def draw_limits(speed_axes, gap_axes, force_axes, run: DrivingScenarioTelemetry) -> None:
    """Draw one run's speed limit and safety limits as dashed lines."""
    safety = run.driver.safety
    limits_kmh = [limit * KMH_PER_MPS for limit in run.signals[Signal.SPEED_LIMIT_MPS]]
    speed_axes.plot(run.signals[Signal.TIME_S], limits_kmh, color=THEME.ink_muted, linewidth=1.0, linestyle="--",
                    label="speed limit")
    draw_limit(gap_axes, safety.min_gap_m, f" minimum gap {safety.min_gap_m:g} m")
    draw_limit(force_axes, safety.max_acceleration_mps2, f" acceleration limit {safety.max_acceleration_mps2:g} m/s2")
    draw_limit(force_axes, -safety.max_deceleration_mps2, f" braking limit {safety.max_deceleration_mps2:g} m/s2")


def draw_limit(axes, value: float, label: str) -> None:
    axes.axhline(value, color=THEME.ink_muted, linewidth=1.0, linestyle="--")
    axes.text(0.0, value, label, color=THEME.ink_secondary, fontsize=8.5, va="bottom")
