"""World's Risk API v0 files converted to a Planner forecast; offline.

data/world-risk-v0/ holds byte-exact copies of World's own example files
(`carla-work/risk_api/` on origin/planner-risk-api at fd72d20, Jeslyn Yang).
"""

import contextlib
import csv
import io
import math
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

from planner import __main__ as cli
from planner.core import PlanningError, make_plan
from planner.files import read_json
from planner.world_risk import forecast_from_risk_api, read_odds, read_registry, write_template

WORK = Path(__file__).resolve().parents[3]
EXAMPLE = Path(__file__).resolve().parent / "data/world-risk-v0"
LIVE = WORK / "risk_api"  # present once World's branch is merged
TOWN10 = WORK / "planner-data/town10-mac.json.gz"

# World's example graph: r1 A->B, r2 B->C, r3 B->D, r4 D->E.
TINY = {"schema_version": 1, "catalog_id": "world-example", "map": "synthetic",
        "segments": {sid: {"length_m": 100.0, "successors": successors, "speed_limit_kmh": 30.0,
                           "speed_limit_verified": True}
                     for sid, successors in {"r1_f_0": ["r2_f_0", "r3_f_0"], "r2_f_0": [],
                                             "r3_f_0": ["r4_f_0"], "r4_f_0": []}.items()}}
TRIP = {"origin": {"segment_id": "r1_f_0", "offset_m": 0.0},
        "destination": {"segment_id": "r4_f_0", "offset_m": 100.0},
        "departure_time_s": 0.0, "risk_weight": 50.0}


def any_of(*probabilities):
    """P(at least one incident starts in a second), for independent hazards."""
    return 1.0 - math.prod(1.0 - p for p in probabilities)


def convert(catalog, folder=EXAMPLE, odds="risk_odds_example.csv", **options):
    registry = read_registry(folder / "hazards.csv")
    return forecast_from_risk_api(catalog, registry, read_odds(folder / odds, registry), **options)


class ExampleFileTests(unittest.TestCase):
    def test_registry_is_read_with_modes_and_switches(self):
        registry = read_registry(EXAMPLE / "hazards.csv")
        self.assertEqual(len(registry), 16)
        self.assertEqual(registry["p_fog"], {"penalty_mode": "visibility", "enabled": True})
        self.assertEqual([h for h, row in registry.items() if not row["enabled"]], ["p_snow", "p_heat"])

    def test_example_converts_by_penalty_mode(self):
        forecast = convert(TINY)
        self.assertEqual((forecast["schema_version"], forecast["catalog_id"]), (1, "world-example"))
        self.assertEqual(set(forecast["segments"]), set(TINY["segments"]))
        r1, r2 = forecast["segments"]["r1_f_0"], forecast["segments"]["r2_f_0"]
        self.assertAlmostEqual(r1["pedestrian"], any_of(0.01, 0.003))           # pedestrian, cyclist
        self.assertAlmostEqual(r1["visibility"], any_of(0.004, 0.002, 0.001))   # fog, low light, blind corner
        self.assertAlmostEqual(r1["wet_road"], 0.02)                            # rain
        self.assertAlmostEqual(r2["visibility"], any_of(0.004, 0.002, 0.03))    # fog, low light, sun glare
        self.assertEqual(set(r1), {"pedestrian", "visibility", "wet_road"})

    def test_values_equal_worlds_summed_rate_per_mode(self):
        # World: r = -ln(1 - p), summed per penalty_mode (RiskAPI.rate_by_mode).
        rate = -math.log(1 - 0.004) - math.log(1 - 0.002) - math.log(1 - 0.001)
        self.assertAlmostEqual(convert(TINY)["segments"]["r1_f_0"]["visibility"], 1 - math.exp(-rate))

    def test_unpriced_modes_and_scale_are_reported(self):
        info = convert(TINY)["risk_api"]
        self.assertEqual(info["mode_map"], {"pedestrian_proximity": "pedestrian", "visibility": "visibility",
                                            "wet_surface": "wet_road"})
        self.assertEqual(sorted(info["unpriced_modes"]), ["obstruction", "traffic_conflict", "vehicle_dynamics"])
        traffic = info["unpriced_modes"]["traffic_conflict"]
        self.assertEqual(traffic["hazards"], ["p_traffic", "p_intersection_conflict", "p_aggressive_driver"])
        rows = ((0.015, 0.006, 0.002), (0.008, 0.002, 0.001), (0.004, 0.001, 0.001), (0.002, 0, 0))
        self.assertAlmostEqual(traffic["mean_p_per_s"], sum(any_of(*row) for row in rows) / 4)
        self.assertEqual(info["disabled_hazards_with_odds"], [])
        self.assertAlmostEqual(info["mean_hazard_sum"],
                               sum(sum(s.values()) for s in convert(TINY)["segments"].values()) / 4)

    def test_converted_example_plans(self):
        plan = make_plan(TINY, convert(TINY), TRIP, require_verified_limits=True)
        self.assertEqual([s["segment_id"] for s in plan["segments"]], ["r1_f_0", "r3_f_0", "r4_f_0"])
        self.assertLess(min(s["target_speed_kmh"] for s in plan["segments"]), 30.0)

    def test_segment_ids_must_be_the_catalogs(self):
        with self.assertRaises(PlanningError) as caught:
            convert(read_json(TOWN10))
        message = str(caught.exception)
        self.assertIn("4 segment IDs are not in the catalog (r1_f_0, r2_f_0, r3_f_0, …)", message)
        self.assertIn("168 catalog segments have no row (r0.s0.l-1, ", message)

    @unittest.skipUnless((LIVE / "hazards.csv").exists(), "World's risk_api folder is not in this checkout")
    def test_worlds_current_files_still_convert(self):
        self.assertEqual(set(convert(TINY, folder=LIVE)["segments"]), set(TINY["segments"]))


class BadFileTests(unittest.TestCase):
    HEADER = "segment_id,start_node,end_node,p_pedestrian,p_rain\n"
    REGISTRY = ("hazard,source,penalty_mode,occurrence,carla_effect,tier,enabled\n"
                "p_pedestrian,x,pedestrian_proximity,x,x,1,1\np_rain,x,wet_surface,x,x,1,1\n"
                "p_snow,x,wet_surface,x,x,3,0\n")

    def load(self, odds, registry=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hazards.csv").write_text(registry or self.REGISTRY)
            (root / "risk.csv").write_text(odds)
            return convert(dict(TINY, segments={"a": TINY["segments"]["r2_f_0"]}), folder=root, odds="risk.csv")

    def test_good_small_file(self):
        self.assertEqual(self.load(self.HEADER + "a,A,B,0.01,0.02\n")["segments"],
                         {"a": {"pedestrian": 0.01, "visibility": 0.0, "wet_road": 0.02}})

    def test_each_problem_is_named(self):
        cases = {
            "column not in registry": (self.HEADER.replace("p_rain", "p_meteor") + "a,A,B,0.01,0.02\n",
                                       r"hazards not in hazards.csv: p_meteor"),
            "enabled hazard missing": ("segment_id,start_node,end_node,p_pedestrian\na,A,B,0.01\n",
                                       r"enabled hazards have no column: p_rain"),
            "not a number": (self.HEADER + "a,A,B,lots,0.02\n", r"line 2: p_pedestrian is not a number"),
            "out of range": (self.HEADER + "a,A,B,0.01,1.5\n", r"line 2: p_rain=1.5 is outside 0 to 1"),
            "no segment column": ("id,p_pedestrian,p_rain\na,0.01,0.02\n", r"missing columns: segment_id"),
            "one time column": (self.HEADER.rstrip() + ",t_from_s\na,A,B,0.01,0.02,0\n",
                                r"both t_from_s and t_to_s, or neither"),
            "duplicate row": (self.HEADER + "a,A,B,0.01,0.02\na,A,B,0.03,0.02\n", r"line 3: a appears twice"),
            "overlapping windows": (self.HEADER.rstrip() + ",t_from_s,t_to_s\na,A,B,0.01,0.02,0,60\n"
                                    "a,A,B,0.03,0.02,30,\n", r"a has overlapping time windows"),
            "empty": (self.HEADER, r"no rows"),
        }
        for name, (odds, message) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(PlanningError, message):
                self.load(odds)

    def test_disabled_hazard_with_odds_counts_as_world_counts_it_and_is_flagged(self):
        forecast = self.load(self.HEADER.rstrip() + ",p_snow\na,A,B,0.01,0.02,0.05\n")
        self.assertAlmostEqual(forecast["segments"]["a"]["wet_road"], any_of(0.02, 0.05))
        self.assertEqual(forecast["risk_api"]["disabled_hazards_with_odds"], ["p_snow"])

    def test_time_windows_use_the_requested_time(self):
        odds = (self.HEADER.rstrip() + ",t_from_s,t_to_s\na,A,B,0.01,0.02,0,60\na,A,B,0.04,0.02,60,120\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hazards.csv").write_text(self.REGISTRY)
            (root / "risk.csv").write_text(odds)
            catalog = dict(TINY, segments={"a": TINY["segments"]["r2_f_0"]})
            for time_s, expected in ((0.0, 0.01), (59.9, 0.01), (60.0, 0.04), (500.0, 0.04)):
                with self.subTest(time_s=time_s):
                    forecast = convert(catalog, folder=root, odds="risk.csv", time_s=time_s)
                    self.assertEqual(forecast["segments"]["a"]["pedestrian"], expected)
                    self.assertEqual(forecast["risk_api"]["time_s"], time_s)


class Town10Tests(unittest.TestCase):
    """A Town10-sized file in World's format, made from the Planner's template."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = read_json(TOWN10)
        cls.registry = read_registry(EXAMPLE / "hazards.csv")

    def filled_template(self, root):
        write_template(self.catalog, self.registry, root / "risk_template.csv")
        with (root / "risk_template.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        rng = random.Random(0)
        for row in rows:
            for column in row:
                if column.startswith("p_"):
                    row[column] = f"{rng.uniform(0.001, 0.05):.4f}"   # World's stated sensible range
        with (root / "risk_town10.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return rows

    def test_template_lists_every_segment_and_enabled_hazard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_template(self.catalog, self.registry, root / "risk_template.csv")
            with (root / "risk_template.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual({row["segment_id"] for row in rows}, set(self.catalog["segments"]))
            enabled = [h for h, row in self.registry.items() if row["enabled"]]
            self.assertEqual(list(rows[0]), ["segment_id", "start_node", "end_node", *enabled])
            self.assertEqual({row[h] for row in rows for h in enabled}, {"0"})
            first = self.catalog["segments"][rows[0]["segment_id"]]["geometry"][0]
            self.assertEqual(rows[0]["start_node"], f"{first['x']:.1f}:{first['y']:.1f}")
            empty = forecast_from_risk_api(self.catalog, self.registry,
                                           read_odds(root / "risk_template.csv", self.registry))
            self.assertEqual({v for s in empty["segments"].values() for v in s.values()}, {0.0})

    def test_town10_sized_file_plans_with_verified_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.filled_template(root)
            forecast = forecast_from_risk_api(self.catalog, self.registry,
                                              read_odds(root / "risk_town10.csv", self.registry))
        self.assertEqual(len(forecast["segments"]), 168)
        self.assertLess(forecast["risk_api"]["mean_hazard_sum"], 0.3)
        trip = read_json(WORK / "planner-data/town10-trip.json")
        speeds = {}
        for weight in (2.0, 50.0):
            plan = make_plan(self.catalog, forecast, dict(trip, risk_weight=weight), require_verified_limits=True)
            speeds[weight] = [s["target_speed_kmh"] for s in plan["segments"]]
        # At World's per-second scale, λ = 2 still drives at the limit; a larger λ slows down.
        self.assertEqual(set(speeds[2.0]), {30.0})
        self.assertLess(min(speeds[50.0]), 30.0)

    def test_commands_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common = ["--catalog", str(TOWN10), "--hazards", str(EXAMPLE / "hazards.csv")]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                with patch.object(sys, "argv", ["planner", "risk-template", *common,
                                                "--output", str(root / "risk_template.csv")]):
                    cli.main()
                self.filled_template(root)
                with patch.object(sys, "argv", ["planner", "risk-api", *common, "--odds",
                                                str(root / "risk_town10.csv"), "--output", str(root / "f.json")]):
                    cli.main()
            forecast = read_json(root / "f.json")
            self.assertEqual(len(forecast["segments"]), 168)
            self.assertEqual(forecast["forecast_id"], "risk-api-v0:risk_town10@t=0")
            self.assertIn("168 segments", out.getvalue())
            self.assertIn("not priced: obstruction, traffic_conflict, vehicle_dynamics", out.getvalue())


if __name__ == "__main__":
    unittest.main()
