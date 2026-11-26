"""The pieces of the driver's figures: one chart of a signal over time, with every run on it."""

from __future__ import annotations

import math
from typing import Iterable

from ...core.utilities.config import CONFIG
from ..driver.models.driving_safety_evaluation import SafetyRequirement
from ..driver.models.driving_scenario_telemetry import NO_GAP_M, DrivingScenarioTelemetry, Signal, TelemetryEventKind
from .utilities import THEME, series_color, style_chart

KMH_PER_MPS = 3.6


def checked_runs(telemetry: DrivingScenarioTelemetry | Iterable[DrivingScenarioTelemetry]
                 ) -> list[DrivingScenarioTelemetry]:
    """One run or several, as a list.

    Raises:
        ValueError: If there is no run, or a run has no samples.
    """
    runs = [telemetry] if isinstance(telemetry, DrivingScenarioTelemetry) else list(telemetry)
    if not runs or not all(len(run) for run in runs):
        raise ValueError("every run needs at least one sample")
    return runs


def run_name(run: DrivingScenarioTelemetry, index: int) -> str:
    return run.scenario_name or f"run {index + 1}"


def speeds_kmh(run: DrivingScenarioTelemetry) -> list[float]:
    return [speed * KMH_PER_MPS for speed in run.signals[Signal.SPEED_MPS]]


def speed_limits_kmh(run: DrivingScenarioTelemetry) -> list[float]:
    return [limit * KMH_PER_MPS for limit in run.signals[Signal.SPEED_LIMIT_MPS]]


def gaps_m(run: DrivingScenarioTelemetry) -> list[float]:
    """The gap at each sample. A sample with no other road user is NaN, which leaves a break in the line."""
    return [gap if gap < NO_GAP_M else float("nan") for gap in run.signals[Signal.GAP_M]]


def collision_times(run: DrivingScenarioTelemetry) -> list[float]:
    return [event.time_s for event in run.events_of(TelemetryEventKind.COLLISION)]


def time_chart(pyplot, runs: list[DrivingScenarioTelemetry], title: str, label: str):
    """Start a chart over simulation time, wide enough for the longest run.

    Returns:
        The figure and its axes.
    """
    settings = THEME.telemetry
    figure, axes = pyplot.subplots(figsize=(settings.width_in, settings.height_in), dpi=settings.dpi,
                                   facecolor=THEME.surface, layout="constrained")
    style_chart(axes)
    axes.set_xlim(0.0, max(run.signals[Signal.TIME_S][-1] for run in runs))
    axes.set_xlabel("simulation time (s)", color=THEME.ink_secondary)
    axes.set_ylabel(label, color=THEME.ink_secondary, fontsize=9.5)
    figure.suptitle(title, x=0.02, ha="left", fontsize=14, color=THEME.ink)
    return figure, axes


def draw_series(axes, runs: list[DrivingScenarioTelemetry], values_of, *, linewidth: float = 1.8) -> None:
    """Draw one line per run, in the run's color, from the values `values_of` reads off it."""
    for index, run in enumerate(runs):
        axes.plot(run.signals[Signal.TIME_S], values_of(run), color=series_color(index), linewidth=linewidth,
                  label=run_name(run, index))


def draw_limit(axes, value: float, label: str) -> None:
    """Draw a safety limit as a dashed line across the chart, named at its left end."""
    axes.axhline(value, color=THEME.ink_muted, linewidth=1.0, linestyle="--")
    axes.annotate(label, xy=(0.0, value), xycoords=("axes fraction", "data"), xytext=(4, 3),
                  textcoords="offset points", color=THEME.ink_secondary, fontsize=8.5, va="bottom")


def fit_values(axes, values: list[float], *, from_zero: bool = False) -> None:
    """Set the value axis to hold every value given, with a margin, so that no line is cut off."""
    finite = [value for value in values if value == value]
    low = min(finite)
    high = max(finite)
    if from_zero:
        low = min(low, 0.0)
    margin = THEME.telemetry.value_margin * ((high - low) or 1.0)
    axes.set_ylim(low if from_zero and low == 0.0 else low - margin, high + margin)


def requirement_values(requirement: SafetyRequirement, run: DrivingScenarioTelemetry) -> list[float]:
    """The value a requirement compares against its threshold, as the evaluation sees it.

    A gap sample with no road user to measure, or taken while the car stood
    still, reads as the cap in the evaluation and is drawn as NaN.
    """
    from ..driver.driver import Driver

    values = requirement.values(Driver.trace(run))
    if requirement.watched not in (Signal.GAP_M, Signal.GAP_AHEAD_M):
        return values
    cap_m = CONFIG.driver.evaluation.gap_cap_m
    return [value if value < min(cap_m, NO_GAP_M) else float("nan") for value in values]


def draw_requirement(axes, runs: list[DrivingScenarioTelemetry], requirement: SafetyRequirement) -> None:
    """Draw a requirement's value for each run, its threshold, and each run's least margin.

    An arrow runs from the threshold to the value at the moment a run came
    closest to it, or went furthest past it, and carries the margin.
    """
    from ..driver.driver import Driver

    unit = f" {requirement.unit}" if requirement.unit else ""
    shown = [requirement.threshold]
    for index, run in enumerate(runs):
        times = run.signals[Signal.TIME_S]
        values = requirement_values(requirement, run)
        margins = requirement.margins(Driver.trace(run))
        worst = margins.index(min(margins))
        margin = margins[worst]
        measured = values[worst] == values[worst]
        verdict = "kept" if margin >= 0.0 else "breached"
        outcome = f"{verdict}, {margin:+.2f}{unit}" if measured else f"{verdict}, no road user to measure"
        color = series_color(index)
        axes.plot(times, values, color=color, linewidth=1.6, label=f"{run_name(run, index)}: {outcome}")
        shown += values
        if measured:
            draw_margin(axes, times[worst], requirement.threshold, values[worst], margin, color)
    fit_values(axes, shown)
    widen_scale(axes, shown, requirement.limit)
    draw_limit(axes, requirement.threshold, f"threshold {requirement.threshold:.3g}{unit}")
    draw_legend(axes, len(runs))


def draw_margin(axes, time_s: float, threshold: float, value: float, margin: float, color: str) -> None:
    """Draw an arrow from the threshold to a value, with the margin written beside it."""
    axes.annotate("", xy=(time_s, value), xytext=(time_s, threshold), zorder=6,
                  arrowprops={"arrowstyle": "-|>", "color": color, "linewidth": 1.6, "shrinkA": 0, "shrinkB": 0})
    axes.scatter([time_s], [value], s=22, color=color, edgecolors=THEME.surface, linewidths=0.8, zorder=7)
    axes.annotate(f"{margin:+.2f}", xy=(time_s, value), xytext=(7, 0), textcoords="offset points", color=color,
                  fontsize=10, fontweight="bold", va="center", zorder=7,
                  bbox={"facecolor": THEME.surface, "edgecolor": "none", "pad": 1.0, "alpha": 0.85})


def widen_scale(axes, values: list[float], limit: float) -> None:
    """Keep the margin readable when the values range far beyond the limit.

    Such an axis becomes linear near the limit and logarithmic beyond it, so
    that it still holds every value.
    """
    settings = THEME.requirements
    finite = [value for value in values if value == value]
    low = min(finite)
    high = max(finite)
    if limit <= 0.0 or high - low <= settings.wide_range_ratio * limit:
        return
    linear_to = settings.linear_limits * limit
    margin = THEME.telemetry.value_margin
    axes.set_yscale("symlog", linthresh=linear_to)
    # On the linear part a margin is a distance, and on the logarithmic part it is a factor.
    bottom = low - margin * linear_to if low > -linear_to else low * (1.0 + margin)
    top = high * (1.0 + margin) if high > linear_to else high + margin * linear_to
    ticks = [-linear_to, 0.0, limit, linear_to]
    decade = 10.0 ** (math.floor(math.log10(linear_to)) + 1)
    while decade <= top:
        ticks.append(decade)
        decade *= 10.0
    axes.set_yticks([tick for tick in sorted(set(ticks)) if bottom <= tick <= top])
    axes.set_ylim(bottom, top)
    axes.yaxis.set_major_formatter("{x:g}")
    axes.minorticks_off()


def draw_legend(axes, entries: int) -> None:
    axes.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=entries, frameon=False, fontsize=9,
                labelcolor=THEME.ink_secondary)
