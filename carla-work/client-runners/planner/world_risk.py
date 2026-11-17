"""World's Risk API v0 files, converted to a Planner forecast.

World publishes, for every directed segment, the probability per second that an incident
of each hazard starts (`p_*` columns), and a registry (`hazards.csv`) that gives each
hazard a penalty mode. The Planner prices three of those modes. A mode's value is the
probability per second that at least one of its hazards starts: 1 - prod(1 - p). That
equals 1 - exp(-r), where r is World's summed rate for the mode (`RiskAPI.rate_by_mode`).

Segment IDs must be the catalog's. Modes the Planner does not price are left out of the
forecast and reported in its `risk_api` block, so nothing is dropped silently.
"""

import csv
import math
from pathlib import Path

from .core import HAZARDS, PlanningError

MODE_TO_HAZARD = {"pedestrian_proximity": "pedestrian", "visibility": "visibility", "wet_surface": "wet_road"}
assert set(MODE_TO_HAZARD.values()) == set(HAZARDS)


def _rows(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        return [c.strip() for c in reader.fieldnames or []], list(reader)


def _some(ids):
    return ", ".join(ids[:3]) + (", …" if len(ids) > 3 else "")


def read_registry(path):
    """hazards.csv: hazard name -> its penalty mode and whether World has it switched on."""
    name = Path(path).name
    columns, rows = _rows(path)
    missing = [c for c in ("hazard", "penalty_mode", "enabled") if c not in columns]
    if missing:
        raise PlanningError(f"{name}: missing columns: {', '.join(missing)}")
    registry = {}
    for row in rows:
        hazard = row["hazard"].strip()
        if not hazard or hazard in registry:
            raise PlanningError(f"{name}: empty or repeated hazard name: {hazard!r}")
        registry[hazard] = {"penalty_mode": row["penalty_mode"].strip(), "enabled": row["enabled"].strip() == "1"}
    if not registry:
        raise PlanningError(f"{name}: no hazards listed")
    return registry


def read_odds(path, registry):
    """risk_*.csv: segment ID -> time windows [(from_s, to_s, {hazard: p})], in time order."""
    name = Path(path).name
    columns, rows = _rows(path)
    if "segment_id" not in columns:
        raise PlanningError(f"{name}: missing columns: segment_id")
    hazards = [c for c in columns if c.startswith("p_")]
    unknown = [h for h in hazards if h not in registry]
    if unknown:
        raise PlanningError(f"{name}: hazards not in hazards.csv: {', '.join(unknown)}")
    absent = [h for h, row in registry.items() if row["enabled"] and h not in hazards]
    if absent:
        raise PlanningError(f"{name}: enabled hazards have no column: {', '.join(absent)}")
    timed = "t_from_s" in columns
    if timed != ("t_to_s" in columns):
        raise PlanningError(f"{name}: give both t_from_s and t_to_s, or neither")
    windows = {}
    for line, row in enumerate(rows, start=2):
        where = f"{name} line {line}"
        segment = (row.get("segment_id") or "").strip()
        if not segment:
            raise PlanningError(f"{where}: segment_id is empty")
        odds = {}
        for hazard in hazards:
            try:
                p = float(row[hazard])
            except (TypeError, ValueError):
                raise PlanningError(f"{where}: {hazard} is not a number") from None
            if not 0.0 <= p <= 1.0:
                raise PlanningError(f"{where}: {hazard}={p:g} is outside 0 to 1")
            odds[hazard] = p
        start, end = 0.0, math.inf
        if timed:
            try:
                start = float(row["t_from_s"])
                end = float(row["t_to_s"]) if (row["t_to_s"] or "").strip() else math.inf
            except (TypeError, ValueError):
                raise PlanningError(f"{where}: t_from_s or t_to_s is not a number") from None
            if not start < end:
                raise PlanningError(f"{where}: t_to_s must be after t_from_s")
        elif segment in windows:
            raise PlanningError(f"{where}: {segment} appears twice")
        windows.setdefault(segment, []).append((start, end, odds))
    if not windows:
        raise PlanningError(f"{name}: no rows")
    for segment, spans in windows.items():
        spans.sort(key=lambda span: span[0])
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            raise PlanningError(f"{name}: {segment} has overlapping time windows")
    return windows


def _at(spans, time_s):
    """The window covering time_s; before the first window the first, otherwise the latest started."""
    chosen = spans[0]
    for span in spans:
        if span[0] <= time_s:
            chosen = span
    return chosen[2]


def _any(probabilities):
    """Probability that at least one of the independent hazards starts in a second."""
    return round(1.0 - math.prod(1.0 - p for p in probabilities), 12)


def forecast_from_risk_api(catalog, registry, odds, *, time_s=0.0, forecast_id=None, name="risk"):
    """A version 1 forecast for `catalog`, fixed at `time_s` because the Planner uses one forecast per trip."""
    segments = catalog["segments"]
    extra, lacking = sorted(set(odds) - set(segments)), sorted(set(segments) - set(odds))
    if extra or lacking:
        problems = []
        if extra:
            problems.append(f"{len(extra)} segment IDs are not in the catalog ({_some(extra)})")
        if lacking:
            problems.append(f"{len(lacking)} catalog segments have no row ({_some(lacking)})")
        raise PlanningError(f"risk file does not match catalog {catalog['catalog_id']}: " + "; ".join(problems))
    chosen = {sid: _at(odds[sid], time_s) for sid in sorted(segments)}
    listed = [h for h in registry if any(h in row for row in chosen.values())]
    by_mode = {}
    for hazard in listed:
        by_mode.setdefault(registry[hazard]["penalty_mode"], []).append(hazard)
    values = {sid: {MODE_TO_HAZARD[mode]: _any(row.get(h, 0.0) for h in by_mode.get(mode, ()))
                    for mode in MODE_TO_HAZARD} for sid, row in chosen.items()}
    unpriced = {mode: {"hazards": hazards,
                       "mean_p_per_s": sum(_any(row.get(h, 0.0) for h in hazards) for row in chosen.values()) / len(chosen)}
                for mode, hazards in sorted(by_mode.items()) if mode not in MODE_TO_HAZARD}
    disabled = [h for h in listed if not registry[h]["enabled"] and any(row.get(h, 0.0) > 0 for row in chosen.values())]
    return {"schema_version": 1, "catalog_id": catalog["catalog_id"],
            "forecast_id": forecast_id or f"risk-api-v0:{name}@t={time_s:g}",
            "source": f"World Risk API v0 file {name} at t = {time_s:g} s; per-second probabilities by penalty mode",
            "risk_api": {"format": "v0", "time_s": time_s, "mode_map": dict(MODE_TO_HAZARD),
                         "unpriced_modes": unpriced, "disabled_hazards_with_odds": disabled,
                         "mean_hazard_sum": sum(sum(v.values()) for v in values.values()) / len(values)},
            "segments": values}


def write_template(catalog, registry, path):
    """An all-zero Risk API v0 file with one row per catalog segment, for World to fill in.

    Node columns hold each segment's end coordinates as x:y in CARLA metres. They are
    labels for locating a segment, not graph keys; the catalog's `successors` hold the graph.
    """
    enabled = [hazard for hazard, row in registry.items() if row["enabled"]]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["segment_id", "start_node", "end_node", *enabled])
        for sid in sorted(catalog["segments"]):
            geometry = catalog["segments"][sid].get("geometry")
            ends = ([f"{p['x']:.1f}:{p['y']:.1f}" for p in (geometry[0], geometry[-1])] if geometry
                    else [f"{sid}:start", f"{sid}:end"])
            writer.writerow([sid, *ends, *("0" for _ in enabled)])
    return len(catalog["segments"]), enabled
