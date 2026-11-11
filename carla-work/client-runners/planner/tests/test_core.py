import copy
import math
import sys
import unittest

from planner.core import PlanningError, make_plan, price, DEFAULT_CONFIG
from planner.examples import tiny_example, mock_forecast


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.catalog, self.forecast, self.trip = tiny_example()

    def plan(self, weight=0, **kwargs):
        return make_plan(self.catalog, self.forecast, dict(self.trip, risk_weight=weight), **kwargs)

    def test_units_and_hand_calculated_cost(self):
        # 100 meters at 36 km/h is 10 s; one certain hazard gives 0.25 + 1.44 = 1.69 points/s.
        result = price(100, 36, {"pedestrian": 1, "visibility": 0, "wet_road": 0}, 2, DEFAULT_CONFIG)
        self.assertAlmostEqual(result["estimated_time_s"], 10)
        self.assertAlmostEqual(result["predicted_penalty"], 16.9)
        self.assertAlmostEqual(result["objective"], 43.8)

    def test_quickest_and_detour(self):
        fast, safe = self.plan(), self.plan(2)
        self.assertEqual([s["segment_id"] for s in fast["segments"]], ["start", "shortcut", "finish"])
        self.assertAlmostEqual(fast["estimated_time_s"], 10.8)
        self.assertEqual([s["segment_id"] for s in safe["segments"]], ["start", "detour", "finish"])
        self.assertAlmostEqual(safe["estimated_time_s"], 16.2)
        self.assertEqual(safe["predicted_penalty"], 0)

    def test_slowing_when_no_detour(self):
        self.catalog["segments"]["start"]["successors"] = ["shortcut"]
        result = self.plan(2)
        speeds = {s["segment_id"]: s["target_speed_kmh"] for s in result["segments"]}
        # v* = 30 * sqrt(1 / (lambda * H) + a) = 30 * sqrt(0.5 + 0.25) = 25.98 km/h
        self.assertEqual(speeds, {"start": 40, "shortcut": 26, "finish": 40})

    def test_zero_risk_and_cautious_route(self):
        self.forecast = mock_forecast(self.catalog, clear=True)
        self.assertEqual(self.plan(100)["segments"], self.plan()["segments"])
        cautious, naive = self.plan(mode="cautious"), self.plan(mode="naive")
        self.assertEqual([s["segment_id"] for s in cautious["segments"]],
                         [s["segment_id"] for s in naive["segments"]])
        self.assertAlmostEqual(cautious["estimated_time_s"], 2 * naive["estimated_time_s"])

    def test_partial_endpoints(self):
        self.trip["origin"]["offset_m"] = 5
        self.trip["destination"]["offset_m"] = 4
        result = self.plan()
        self.assertAlmostEqual(sum(s["distance_m"] for s in result["segments"]), 109)
        self.assertAlmostEqual(result["estimated_time_s"], 9.81)

    def test_same_segment_and_upstream_loop(self):
        self.trip["origin"] = {"segment_id": "shortcut", "offset_m": 80}
        self.trip["destination"] = {"segment_id": "shortcut", "offset_m": 90}
        self.assertAlmostEqual(self.plan()["estimated_time_s"], 0.9)
        self.trip["destination"]["offset_m"] = 80
        self.assertEqual(self.plan()["segments"], [])
        self.trip["destination"]["offset_m"] = 20
        with self.assertRaisesRegex(PlanningError, "no legal route"):
            self.plan()
        self.catalog["segments"]["finish"]["successors"] = ["start"]
        result = self.plan()
        self.assertEqual([s["segment_id"] for s in result["segments"]],
                         ["shortcut", "finish", "start", "shortcut"])
        self.assertAlmostEqual(sum(s["distance_m"] for s in result["segments"]), 60)

    def test_no_wrong_way_route(self):
        self.trip["origin"], self.trip["destination"] = self.trip["destination"], self.trip["origin"]
        with self.assertRaises(PlanningError):
            self.plan()

    def test_complete_probability_coverage(self):
        del self.forecast["segments"]["detour"]
        with self.assertRaisesRegex(PlanningError, "cover exactly"):
            self.plan()

    def test_invalid_numbers(self):
        for bad in (-1, 1.01, math.nan, math.inf, True):
            with self.subTest(bad=bad):
                self.forecast["segments"]["shortcut"]["pedestrian"] = bad
                with self.assertRaises(PlanningError):
                    self.plan()

    def test_limit_below_candidate_speeds(self):
        self.catalog["segments"]["shortcut"]["speed_limit_kmh"] = 10
        self.catalog["segments"]["start"]["successors"] = ["shortcut"]
        result = self.plan()
        self.assertEqual(result["segments"][1]["target_speed_kmh"], 10)
        with self.assertRaisesRegex(PlanningError, "not verified"):
            self.plan(require_verified_limits=True)

    def test_repeatable_and_lambda_tradeoff(self):
        self.assertEqual(self.plan(2), self.plan(2))
        previous_time, previous_penalty = 0, math.inf
        for weight in [0, 0.5, 1, 2, 5, 10]:
            result = self.plan(weight)
            self.assertGreaterEqual(result["estimated_time_s"] + 1e-9, previous_time)
            self.assertLessEqual(result["predicted_penalty"], previous_penalty + 1e-9)
            previous_time, previous_penalty = result["estimated_time_s"], result["predicted_penalty"]

    def test_catalog_order_does_not_change_route(self):
        first = self.plan()
        self.catalog["segments"] = dict(reversed(list(self.catalog["segments"].items())))
        self.assertEqual(first, self.plan())

    def test_inputs_not_mutated(self):
        original = copy.deepcopy((self.catalog, self.forecast, self.trip))
        self.plan(mode="cautious")
        self.assertEqual(original, (self.catalog, self.forecast, self.trip))

    def test_core_does_not_import_carla(self):
        self.assertNotIn("carla", sys.modules)

    def test_malformed_json_shapes_fail_clearly(self):
        for bad_catalog, bad_forecast, bad_trip, bad_config in (
            ([], self.forecast, self.trip, None),
            (self.catalog, [], self.trip, None),
            (self.catalog, self.forecast, [], None),
            (self.catalog, self.forecast, self.trip, []),
            (self.catalog, self.forecast, dict(self.trip, origin=None), None),
        ):
            with self.assertRaises(PlanningError):
                make_plan(bad_catalog, bad_forecast, bad_trip, bad_config)


def exposure_config(a, speeds=None):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["exposure_baseline"] = a
    if speeds is not None:
        config["candidate_speeds_kmh"] = speeds
    return config


class ExposureTests(unittest.TestCase):
    """Optional exposure term: rate = H * (a + (v / v_ref)^2)."""

    def setUp(self):
        self.catalog, self.forecast, self.trip = tiny_example()
        self.catalog["segments"]["start"]["successors"] = ["shortcut"]  # no detour
        self.fine = [float(v) for v in range(1, 41)]

    def plan(self, weight, config):
        return make_plan(self.catalog, self.forecast, dict(self.trip, risk_weight=weight), config)

    def shortcut_speed(self, plan):
        return {s["segment_id"]: s["target_speed_kmh"] for s in plan["segments"]}["shortcut"]

    def test_omitted_exposure_means_zero(self):
        omitted = copy.deepcopy(DEFAULT_CONFIG)
        del omitted["exposure_baseline"]
        without, zero = self.plan(2, omitted), self.plan(2, exposure_config(0.0))
        for key in ("segments", "estimated_time_s", "predicted_penalty", "objective"):
            self.assertEqual(without[key], zero[key])

    def test_hand_calculated_cost(self):
        # 100 m at 30 km/h is 12 s; rate = 1 * (0.5 + 1) = 1.5 /s; penalty 18; J = 12 + 2*18.
        result = price(100, 30, {"pedestrian": 1, "visibility": 0, "wet_road": 0}, 2, exposure_config(0.5))
        self.assertAlmostEqual(result["estimated_time_s"], 12)
        self.assertAlmostEqual(result["predicted_penalty"], 18)
        self.assertAlmostEqual(result["objective"], 48)

    def test_penalty_is_u_shaped(self):
        risks = {"pedestrian": 1, "visibility": 0, "wet_road": 0}
        penalties = {v: price(100, v, risks, 0, exposure_config(0.5))["predicted_penalty"] for v in self.fine}
        self.assertEqual(min(penalties, key=penalties.get), round(30 * math.sqrt(0.5)))  # 21 km/h
        flat = {v: price(100, v, risks, 0, exposure_config(0.0))["predicted_penalty"] for v in self.fine}
        self.assertEqual(min(flat, key=flat.get), 1)  # without exposure, slowest is always safest

    def test_exposure_sets_a_speed_floor(self):
        # lambda * H = 100: v* = 30 * sqrt(1/100 + a) -> 3 km/h with a = 0, 15 km/h with a = 0.25.
        self.assertEqual(self.shortcut_speed(self.plan(100, exposure_config(0.0, self.fine))), 3)
        self.assertEqual(self.shortcut_speed(self.plan(100, exposure_config(0.25, self.fine))), 15)

    def test_invalid_exposure_and_unknown_fields(self):
        for bad in (-0.1, math.nan, math.inf, True, "0.5"):
            with self.subTest(bad=bad), self.assertRaises(PlanningError):
                self.plan(2, exposure_config(bad))
        with self.assertRaisesRegex(PlanningError, "documented"):
            self.plan(2, dict(DEFAULT_CONFIG, unknown=1))


if __name__ == "__main__":
    unittest.main()
