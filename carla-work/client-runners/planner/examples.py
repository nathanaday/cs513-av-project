"""Explicit mock probabilities and hand-checkable examples, never safety results."""

import random

from .core import HAZARDS


def mock_forecast(catalog, *, seed=0, hazardous=(), clear=False):
    rng = random.Random(seed)
    hazardous = set(hazardous)
    if not hazardous <= set(catalog["segments"]):
        raise ValueError("mock hazard references an unknown segment")
    values = {}
    for sid in sorted(catalog["segments"]):
        values[sid] = {h: 0.0 for h in HAZARDS}
        if sid in hazardous:
            values[sid]["pedestrian"] = 1.0
        elif not clear and not hazardous:
            values[sid] = {h: round(rng.random(), 3) for h in HAZARDS}
    return {"schema_version": 1, "catalog_id": catalog["catalog_id"],
            "forecast_id": f"mock-{seed}-" + ("clear" if clear else "hazards"),
            "source": "mock; probabilities are invented, not measured", "segments": values}


def tiny_example():
    # The shortcut is 100 m, the detour is 160 m; both share 10 m at either end.
    specs = {"start": (10, ["shortcut", "detour"]), "shortcut": (100, ["finish"]),
             "detour": (160, ["finish"]), "finish": (10, [])}
    catalog = {"schema_version": 1, "catalog_id": "tiny-v1", "map": "synthetic",
               "segments": {sid: {"length_m": length, "successors": successors,
                                  "speed_limit_kmh": 40.0, "speed_limit_verified": False}
                            for sid, (length, successors) in specs.items()}}
    trip = {"origin": {"segment_id": "start", "offset_m": 0.0},
            "destination": {"segment_id": "finish", "offset_m": 10.0},
            "departure_time_s": 0.0, "risk_weight": 0.0}
    return catalog, mock_forecast(catalog, hazardous=["shortcut"]), trip
