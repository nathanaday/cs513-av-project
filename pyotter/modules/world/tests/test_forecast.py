import math
import tempfile
import unittest
from pathlib import Path

from pyotter import Planner, World
from pyotter.core import ConditionForecast, RoadGraphError, WorldHazardLibrary, WorldRoadGraph
from pyotter.core.utilities.config import CONFIG
from pyotter.core.utilities.sun import expected_visibility_loss
from pyotter.modules.world import WorldHazardProbability


class Forecast(unittest.TestCase):
    def setUp(self):
        self.hazards = WorldHazardLibrary()
        self.graph = WorldRoadGraph.from_template("town10")

    def test_every_named_forecast_fits_town10_and_rolls(self):
        names = World.forecast_names()
        self.assertEqual(names[0], "clear-noon")
        self.assertEqual(names[-1], "storm-crowds")
        hashes = set()
        for name in names:
            graph = WorldRoadGraph.from_template("town10")
            World.forecast(graph, name)
            spawns = World.roll_hazards(graph, self.hazards, seed=3, duration_s=60.0)
            self.assertEqual(spawns.probabilities_hash, graph.forecast_hash())
            hashes.add(graph.forecast_hash())
        self.assertEqual(len(hashes), len(names))

    def test_applying_a_forecast_replaces_the_old_one(self):
        World.forecast(self.graph, "storm-crowds")
        World.forecast(self.graph, "clear-noon")
        self.assertEqual(set(self.graph.conditions), set())
        self.assertEqual(self.graph.time_of_day_h, 12.0)
        self.assertEqual(self.graph.event_ids(), {"pedestrian"})

    def test_conditions_come_from_the_config(self):
        forecast = World.forecast(self.graph, "heavy-rain")
        wet = self.graph.get_condition("wet_road")
        self.assertEqual((wet.probability, wet.variability), (1.0, 0.1))
        self.assertAlmostEqual(wet.severity, 5 / 6)
        self.assertEqual(forecast.time_of_day_h, 15.0)

    def test_pedestrians_scale_with_length_junctions_and_hotspots(self):
        forecast = WorldHazardProbability("test", pedestrians_per_km_s=0.1, junction_factor=3.0, hotspots=((189, 2.0),))
        expected = lambda segment, factor: 1.0 - math.exp(-0.1 * segment.length_m / 1000 * factor)
        road = self.graph.get_segment("r15.s0.l-1")
        busy = self.graph.segments_in_junction(189)[0]
        quiet = self.graph.segments_in_junction(841)[0]
        self.assertAlmostEqual(forecast.pedestrian_probability(road), expected(road, 1.0))
        self.assertAlmostEqual(forecast.pedestrian_probability(busy), expected(busy, 6.0))
        self.assertAlmostEqual(forecast.pedestrian_probability(quiet), expected(quiet, 3.0))

    def test_no_pedestrians_assigns_no_event(self):
        wet = ConditionForecast("wet_road", 1.0, 0.5)
        forecast = WorldHazardProbability("dry", conditions=(wet,), time_of_day_h=10.0)
        World.forecast(self.graph, forecast)
        self.assertEqual(self.graph.event_ids(), set())
        self.assertEqual(self.graph.hazard_ids(), {"wet_road"})

    def test_a_forecast_saves_and_loads_to_the_same_forecast(self):
        forecast = WorldHazardProbability.from_config("storm-crowds")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "storm-crowds.json"
            forecast.save(path)
            self.assertEqual(WorldHazardProbability.load(path), forecast)
        with self.assertRaises(RoadGraphError):
            WorldHazardProbability.from_dict({"name": "x"})

    def test_rejects_unknown_names_hotspots_and_negative_rates(self):
        with self.assertRaises(RoadGraphError):
            World.forecast(self.graph, "sunny-mars")
        with self.assertRaises(RoadGraphError):
            World.forecast(self.graph, WorldHazardProbability("x", pedestrians_per_km_s=0.1, hotspots=((99999, 2.0),)))
        with self.assertRaises(RoadGraphError):
            WorldHazardProbability("x", pedestrians_per_km_s=-1.0)


class Night(unittest.TestCase):
    def setUp(self):
        self.hazards = WorldHazardLibrary()
        self.graph = WorldRoadGraph.from_template("town10")
        self.graph.set_condition(self.hazards.wet_road, probability=1.0, severity=0.5)

    def roll(self, hour):
        self.graph.set_time_of_day(hour)
        return World.roll_hazards(self.graph, self.hazards, seed=5, duration_s=10.0).sun

    def test_the_dark_costs_visibility_only_at_night(self):
        self.assertEqual(self.roll(12.0).night_loss, 0.0)
        self.assertEqual(self.roll(17.5).night_loss, 0.0)
        self.assertAlmostEqual(self.roll(22.0).night_loss, CONFIG.world.sun.night_visibility_loss)
        dusk = self.roll(18.25).night_loss
        self.assertTrue(0.0 < dusk < CONFIG.world.sun.night_visibility_loss)

    def test_the_planner_sees_the_night_in_the_forecast(self):
        self.graph.set_time_of_day(12.0)
        day = expected_visibility_loss(self.graph)
        self.graph.set_time_of_day(22.0)
        night = expected_visibility_loss(self.graph)
        self.assertTrue(all(night[sid] > day[sid] for sid in day))

    def test_a_night_world_still_plans(self):
        World.forecast(self.graph, "foggy-night")
        start, end = self.graph.spawn_points[18], self.graph.spawn_points[127]
        naive = Planner.route(start, end, self.graph, mode="naive")
        careful = Planner.route(start, end, self.graph, mode="risk-aware", risk_scale=2.0)
        self.assertGreaterEqual(careful.estimated_time_s, naive.estimated_time_s)


if __name__ == "__main__":
    unittest.main()
