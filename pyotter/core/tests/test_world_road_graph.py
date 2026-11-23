import tempfile
import unittest
from pathlib import Path

from pyotter.core import (
    ConditionForecast, HazardKind, HazardProbability, RoadGraphError, WorldHazardLibrary, WorldRoadGraph, severity_level,
)


class Town10Template(unittest.TestCase):
    def setUp(self):
        self.graph = WorldRoadGraph.from_template("town10")
        self.hazards = WorldHazardLibrary()

    def test_template_is_the_town10_lane_graph(self):
        self.assertEqual(self.graph.map_name, "Town10HD_Opt")
        self.assertEqual(len(self.graph.get_segments()), 168)
        self.assertEqual(self.graph.hazard_ids(), set())
        segment = self.graph.get_segment("r296.s0.l-1")
        self.assertEqual([s.id for s in self.graph.successors_of(segment.id)], ["r15.s0.l-1"])

    def test_junctions_group_their_segments(self):
        self.assertEqual(len(self.graph.get_junctions()), 9)
        segment = self.graph.get_segment("r296.s0.l-1")
        self.assertTrue(segment.in_junction)
        junction = self.graph.get_junction(segment.junction_id)
        members = self.graph.segments_in_junction(junction.id)
        self.assertIn(segment, members)
        self.assertEqual(len(members), 18)
        self.assertTrue(all(junction.contains(*m.point_at(m.length_m / 2)[:2]) for m in members))
        road = self.graph.get_segment("r15.s0.l-1")
        self.assertFalse(road.in_junction)
        self.assertIsNone(road.junction_id)
        self.assertEqual(sum(len(self.graph.segments_in_junction(j.id)) for j in self.graph.get_junctions()), 82)

    def test_segment_in_an_unknown_junction_is_rejected(self):
        data = self.graph.to_dict()
        data["segments"]["r296.s0.l-1"]["junction_id"] = 99999
        with self.assertRaises(RoadGraphError):
            WorldRoadGraph.from_dict(data)

    def test_point_at_interpolates_the_centerline(self):
        segment = self.graph.get_segment("r296.s0.l-1")
        start, end = segment.centerline[0], segment.centerline[-1]
        self.assertEqual(segment.point_at(0.0), (start.x, start.y, start.z))
        self.assertEqual(segment.point_at(segment.length_m), (end.x, end.y, end.z))
        with self.assertRaises(RoadGraphError):
            segment.point_at(segment.length_m + 1.0)

    def test_assignment_replaces_the_same_hazard(self):
        segment = self.graph.get_segment("r296.s0.l-1")
        segment.assign_hazard_probability([(self.hazards.pedestrian, 0.03), ("cyclist", 0.01)])
        segment.assign_hazard_probability([HazardProbability("pedestrian", 0.05)])
        self.assertEqual(segment.hazard_probability(self.hazards.pedestrian), 0.05)
        self.assertEqual(segment.hazard_probability("cyclist"), 0.01)
        self.assertEqual(segment.hazard_probability("scooter"), 0.0)
        self.assertEqual(self.graph.event_ids(), {"pedestrian", "cyclist"})

    def test_conditions_belong_to_the_world_and_events_to_segments(self):
        segment = self.graph.get_segment("r296.s0.l-1")
        with self.assertRaises(RoadGraphError):
            segment.assign_hazard_probability([(self.hazards.wet_road, 0.4)])
        with self.assertRaises(RoadGraphError):
            self.graph.set_condition(self.hazards.pedestrian, probability=0.5, severity=0.5)
        self.graph.set_condition(self.hazards.wet_road, probability=0.9, severity="high", variability=0.1)
        forecast = self.graph.get_condition(self.hazards.wet_road)
        self.assertAlmostEqual(forecast.severity, 5 / 6)
        self.assertEqual(self.graph.hazard_ids(), {"wet_road"})
        self.assertIsNone(self.graph.get_condition("low_visibility"))
        for bad in ({"probability": 1.5, "severity": 0.5}, {"probability": 0.5, "severity": "extreme"},
                    {"probability": 0.5, "severity": 0.5, "variability": -0.1}):
            with self.assertRaises(RoadGraphError):
                self.graph.set_condition("wet_road", **bad)

    def test_condition_severity_varies_around_its_center_within_bounds(self):
        fixed = ConditionForecast("wet_road", 1.0, 0.9, 0.0)
        self.assertEqual((fixed.severity_at(0.0), fixed.severity_at(1.0)), (0.9, 0.9))
        wide = ConditionForecast("wet_road", 0.5, 0.5, 0.4)
        self.assertAlmostEqual(wide.severity_at(0.0), 0.1)
        self.assertAlmostEqual(wide.severity_at(1.0), 0.9)
        self.assertAlmostEqual(wide.expected_severity(), 0.25)
        clipped = ConditionForecast("wet_road", 1.0, 0.9, 0.3)
        low, high = clipped.severity_range()
        self.assertAlmostEqual(low, 0.6)
        self.assertEqual(high, 1.0)
        self.assertEqual(clipped.severity_at(1.0), 1.0)
        self.assertEqual([severity_level(v) for v in (0.1, 0.5, 0.9)], ["low", "mid", "high"])

    def test_time_of_day_is_checked(self):
        self.graph.set_time_of_day(17.5)
        self.assertEqual(self.graph.time_of_day_h, 17.5)
        with self.assertRaises(RoadGraphError):
            self.graph.set_time_of_day(24.0)

    def test_library_separates_conditions_from_events(self):
        self.assertEqual([h.id for h in self.hazards.of_kind(HazardKind.EVENT)], ["pedestrian"])
        self.assertEqual([h.id for h in self.hazards.of_kind(HazardKind.CONDITION)], ["low_visibility", "wet_road"])

    def test_probability_outside_zero_to_one_is_rejected(self):
        segment = self.graph.get_segment("r296.s0.l-1")
        for bad in (-0.1, 1.5, float("nan")):
            with self.assertRaises(RoadGraphError):
                segment.assign_hazard_probability([("pedestrian", bad)])

    def test_save_and_load_keep_assignments(self):
        self.graph.get_segment("r296.s0.l-1").assign_hazard_probability([(self.hazards.pedestrian, 0.03)])
        self.graph.set_condition(self.hazards.low_visibility, probability=0.5, severity="mid", variability=0.4)
        self.graph.set_time_of_day(6.5)
        with tempfile.TemporaryDirectory() as folder:
            for name in ("world.json", "world.json.gz"):
                path = Path(folder) / name
                self.graph.save(path)
                self.assertEqual(WorldRoadGraph.load(path), self.graph)

    def test_unknown_successor_is_rejected(self):
        data = self.graph.to_dict()
        data["segments"]["r296.s0.l-1"]["successors"] = ["r999.s0.l1"]
        with self.assertRaises(RoadGraphError):
            WorldRoadGraph.from_dict(data)

    def test_unknown_names_are_reported(self):
        with self.assertRaises(RoadGraphError):
            self.graph.get_segment("xyz")
        with self.assertRaises(RoadGraphError):
            WorldRoadGraph.from_template("town99")


if __name__ == "__main__":
    unittest.main()
