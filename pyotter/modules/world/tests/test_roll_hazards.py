import tempfile
import unittest
from pathlib import Path

from pyotter import World
from pyotter.core import RoadGraphError, WorldHazardLibrary, WorldRoadGraph
from pyotter.modules.world import WorldHazardSpawns

try:
    import matplotlib
    matplotlib.use("Agg")
except ImportError:
    matplotlib = None


class RollHazards(unittest.TestCase):
    def setUp(self):
        self.hazards = WorldHazardLibrary()
        self.graph = WorldRoadGraph.from_template("town10")
        for segment in self.graph.segments_in_junction(189):
            segment.assign_hazard_probability([(self.hazards.pedestrian, 0.05)])
        self.graph.set_condition(self.hazards.wet_road, probability=0.9, severity="high", variability=0.1)
        self.graph.set_condition(self.hazards.low_visibility, probability=0.5, severity="mid", variability=0.4)
        self.graph.set_time_of_day(17.5)

    def roll(self, seed=1221, duration_s=120.0, graph=None):
        return World.roll_hazards(graph or self.graph, self.hazards, seed, duration_s=duration_s)

    def test_same_seed_gives_the_same_spawns_and_another_seed_does_not(self):
        self.assertEqual(self.roll(), self.roll())
        self.assertNotEqual(self.roll(), self.roll(seed=1222))

    def test_events_lie_on_their_segments_and_inside_the_run(self):
        spawns = self.roll()
        self.assertTrue(70 <= len(spawns.events) <= 150)  # 18 lanes x 120 s at 0.05
        for event in spawns.events:
            segment = self.graph.get_segment(event.position.segment_id)
            self.assertEqual(segment.junction_id, 189)
            self.assertTrue(0.0 <= event.position.offset_m <= segment.length_m)
            self.assertTrue(0.0 <= event.start_s < 120.0)
        self.assertEqual([e.start_s for e in spawns.events], sorted(e.start_s for e in spawns.events))

    def test_conditions_follow_their_chance_and_severity_range(self):
        rolls = [self.roll(seed=seed, duration_s=1.0) for seed in range(400)]
        wet = [r.condition_severity("wet_road") for r in rolls if r.condition_severity("wet_road") > 0]
        fog = [r.condition_severity("low_visibility") for r in rolls if r.condition_severity("low_visibility") > 0]
        self.assertTrue(340 <= len(wet) <= 380)  # 400 runs at 0.9
        self.assertTrue(165 <= len(fog) <= 235)  # 400 runs at 0.5
        low, high = self.graph.get_condition("wet_road").severity_range()
        self.assertTrue(all(low <= value <= high for value in wet))
        self.assertTrue(min(fog) < 0.2 and max(fog) > 0.8)
        self.assertEqual({"low", "mid", "high"}, {c.level for r in rolls for c in r.conditions if c.hazard_id == "low_visibility"})

    def test_certain_and_impossible_forecasts(self):
        segment = self.graph.get_segment("r296.s0.l-1")
        segment.assign_hazard_probability([(self.hazards.pedestrian, 1.0)])
        self.graph.set_condition(self.hazards.wet_road, probability=1.0, severity=0.9)
        self.graph.set_condition(self.hazards.low_visibility, probability=0.0, severity=0.9)
        spawns = self.roll(duration_s=30.0)
        self.assertEqual(len(spawns.events_on(segment.id)), 30)
        self.assertEqual(spawns.condition_severity(self.hazards.wet_road), 0.9)
        self.assertEqual(spawns.condition_severity(self.hazards.low_visibility), 0.0)
        self.assertEqual(spawns.hazard_ids(), {"pedestrian", "wet_road"})

    def test_sun_glare_is_what_rain_or_fog_leaves_of_the_low_sun(self):
        self.graph.set_condition(self.hazards.low_visibility, probability=0.0, severity=0.5)
        clear = self.roll().sun
        self.assertAlmostEqual(clear.strength, 0.86, places=2)
        self.assertAlmostEqual(clear.azimuth_deg, 172.5)
        self.graph.set_condition(self.hazards.low_visibility, probability=1.0, severity=0.75)
        self.assertAlmostEqual(self.roll().sun.strength, clear.strength * 0.25)
        self.graph.set_condition(self.hazards.low_visibility, probability=1.0, severity=1.0)
        self.assertEqual(self.roll().sun.strength, 0.0)
        self.graph.set_time_of_day(12.0)
        self.assertEqual(self.roll().sun.strength, 0.0)
        self.graph.set_time_of_day(None)
        self.assertIsNone(self.roll().sun)

    def test_changing_one_forecast_leaves_the_others_unchanged(self):
        before = self.roll()
        changed = "r296.s0.l-1"
        self.graph.get_segment(changed).assign_hazard_probability([(self.hazards.pedestrian, 0.5)])
        self.graph.set_condition(self.hazards.low_visibility, probability=1.0, severity=1.0)
        after = self.roll()
        self.assertNotEqual(before.events_on(changed), after.events_on(changed))
        self.assertEqual(before.condition_severity("wet_road"), after.condition_severity("wet_road"))
        self.assertEqual([e for e in before.events if e.position.segment_id != changed],
                         [e for e in after.events if e.position.segment_id != changed])

    def test_longer_run_keeps_the_earlier_events(self):
        short, long = self.roll(duration_s=60.0), self.roll(duration_s=120.0)
        self.assertEqual(list(short.events), [e for e in long.events if e.start_s < 60.0])
        self.assertEqual(short.conditions, long.conditions)

    def test_save_and_load(self):
        spawns = self.roll()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spawns.json.gz"
            spawns.save(path)
            self.assertEqual(WorldHazardSpawns.load(path), spawns)

    def test_rejects_an_empty_forecast_and_hazards_of_the_wrong_kind(self):
        with self.assertRaises(RoadGraphError):
            self.roll(graph=WorldRoadGraph.from_template("town10"))
        self.graph.get_segment("r296.s0.l-1").assign_hazard_probability([("wet_road", 0.1)])
        with self.assertRaises(RoadGraphError):
            self.roll()

    @unittest.skipIf(matplotlib is None, "matplotlib is not installed")
    def test_view_draws_one_dot_per_event_and_rejects_spawns_from_another_world(self):
        spawns = self.roll()
        figure = World.view_spawns(self.graph, self.hazards, spawns)
        maps = [axes for axes in figure.axes if axes.get_xlabel() == "x (m)"]
        self.assertEqual([axes.get_title(loc="left") for axes in maps], ["pedestrian", "low_visibility", "wet_road"])
        self.assertEqual(len(maps[0].collections[0].get_offsets()), len(spawns.events))
        self.graph.set_condition(self.hazards.wet_road, probability=0.2, severity="low")
        with self.assertRaises(RoadGraphError):
            World.view_spawns(self.graph, self.hazards, spawns)


if __name__ == "__main__":
    unittest.main()
