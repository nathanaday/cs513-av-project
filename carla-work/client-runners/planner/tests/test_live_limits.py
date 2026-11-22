"""Verified speed limits from a live probe; offline, with probe evidence written by hand."""

import copy
import unittest
from pathlib import Path

from planner.carla_map import apply_speed_limits
from planner.core import PlanningError, make_plan
from planner.files import read_json
from planner.live_limits import overrides_from_probe

DATA = Path(__file__).resolve().parents[3] / "planner-data"


def evidence_for(catalog, limit=30.0, **changes):
    evidence = {"map": "Town10HD_Opt", "map_hash": catalog["map_hash"], "catalog_id": catalog["catalog_id"],
                "probed_utc": "2026-11-15T02:00:00+00:00", "vehicle": "vehicle.tesla.model3",
                "default_limit_kmh": limit, "sign_actors": {"traffic.stop": 3, "traffic.traffic_light": 15},
                "speed_limit_landmarks": [],
                "segments": {sid: {"waypoint_segment": sid, "live_limit_kmh": limit} for sid in catalog["segments"]}}
    evidence.update(changes)
    return evidence


TINY = {"catalog_id": "Town10HD_Opt:test", "map_hash": "ab" * 32,
        "segments": {"a": {"speed_limit_kmh": 64.3738, "speed_limit_verified": False, "speed_limit_source": "OpenDRIVE"},
                     "b": {"speed_limit_kmh": 40.0, "speed_limit_verified": False, "speed_limit_source": "mock 40"}}}


class OverridesFromProbeTests(unittest.TestCase):
    def test_every_segment_gets_its_probed_limit(self):
        overrides = overrides_from_probe(TINY, evidence_for(TINY))
        self.assertEqual(overrides["catalog_id"], TINY["catalog_id"])
        self.assertEqual(overrides["limits"], {"a": 30.0, "b": 30.0})
        self.assertIn("vehicle.tesla.model3", overrides["source"])
        self.assertIn("2026-11-15", overrides["source"])
        self.assertEqual(overrides["evidence"]["distinct_live_limits_kmh"], [30.0])

    def test_speed_limit_signs_make_fixed_limits_invalid(self):
        cases = {"sign actor": {"sign_actors": {"traffic.speed_limit.60": 1}},
                 "landmark": {"speed_limit_landmarks": [{"id": "7", "road_id": 1, "s": 0.0, "value": 60.0}]}}
        for name, change in cases.items():
            with self.subTest(name), self.assertRaisesRegex(PlanningError, "speed-limit signs"):
                overrides_from_probe(TINY, evidence_for(TINY, **change))

    def test_incomplete_or_mismatched_probes_are_rejected(self):
        missing = evidence_for(TINY)
        del missing["segments"]["b"]
        moved = evidence_for(TINY)
        moved["segments"]["a"]["waypoint_segment"] = "b"
        zero = evidence_for(TINY)
        zero["segments"]["b"]["live_limit_kmh"] = 0.0
        cases = {"missing segment": (missing, "not probed: b"), "wrong lane": (moved, "landed on b"),
                 "no limit": (zero, "no live limit on b"),
                 "other map": (evidence_for(TINY, map_hash="cd" * 32), "different map")}
        for name, (evidence, message) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(PlanningError, message):
                overrides_from_probe(TINY, evidence)


class ApplySpeedLimitsTests(unittest.TestCase):
    def test_overrides_mark_segments_verified_with_their_source(self):
        catalog = copy.deepcopy(TINY)
        apply_speed_limits(catalog, {"catalog_id": TINY["catalog_id"], "limits": {"a": 30}, "source": "probe X"})
        self.assertEqual(catalog["segments"]["a"]["speed_limit_kmh"], 30.0)
        self.assertIs(catalog["segments"]["a"]["speed_limit_verified"], True)
        self.assertEqual(catalog["segments"]["a"]["speed_limit_source"], "probe X")
        self.assertIs(catalog["segments"]["b"]["speed_limit_verified"], False)
        apply_speed_limits(catalog, {"catalog_id": TINY["catalog_id"], "limits": {"b": 25}})
        self.assertEqual(catalog["segments"]["b"]["speed_limit_source"], "explicit verified override")

    def test_wrong_catalog_or_segment_is_rejected(self):
        for overrides, message in (({"catalog_id": "other", "limits": {}}, "different catalog"),
                                   ({"catalog_id": TINY["catalog_id"], "limits": {"zz": 30}}, "unknown speed-limit segment")):
            with self.subTest(message), self.assertRaisesRegex(PlanningError, message):
                apply_speed_limits(copy.deepcopy(TINY), overrides)


class VerifiedTown10Tests(unittest.TestCase):
    def test_probed_town10_catalog_plans_with_required_verified_limits(self):
        catalog = read_json(DATA / "town10-local.json.gz")
        forecast = read_json(DATA / "town10-mock.json")
        trip = read_json(DATA / "town10-trip.json")
        with self.assertRaises(PlanningError):
            make_plan(catalog, forecast, trip, require_verified_limits=True)
        apply_speed_limits(catalog, overrides_from_probe(catalog, evidence_for(catalog)))
        for mode in ("naive", "cautious", "risk-aware"):
            with self.subTest(mode):
                plan = make_plan(catalog, forecast, dict(trip, risk_weight=2), mode=mode, require_verified_limits=True)
                speeds = {s["target_speed_kmh"] for s in plan["segments"]}
                self.assertLessEqual(max(speeds), 30.0)
                if mode == "naive":
                    self.assertEqual(speeds, {30.0})
                if mode == "cautious":
                    self.assertEqual(speeds, {20.0})


if __name__ == "__main__":
    unittest.main()
