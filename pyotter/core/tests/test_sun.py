import unittest

from pyotter.core import WorldRoadGraph
from pyotter.core.utilities.sun import (
    facing_factor, glare_strength, low_sun_factor, segment_sun_exposure, sun_position,
)


class Sun(unittest.TestCase):
    def test_position_through_the_day(self):
        self.assertEqual(sun_position(6.0), (0.0, 0.0))
        altitude, azimuth = sun_position(12.0)
        self.assertAlmostEqual(altitude, 60.0)
        self.assertAlmostEqual(azimuth, 90.0)
        self.assertAlmostEqual(sun_position(18.0)[1], 180.0)
        self.assertLess(sun_position(22.0)[0], 0.0)

    def test_low_sun_factor_is_full_at_the_horizon_and_zero_when_high_or_down(self):
        self.assertEqual([low_sun_factor(a) for a in (-5.0, 0.0, 5.0, 15.0, 25.0, 60.0)], [0.0, 1.0, 1.0, 0.5, 0.0, 0.0])

    def test_facing_factor_falls_off_with_the_angle_from_the_sun(self):
        self.assertAlmostEqual(facing_factor(180.0, 180.0), 1.0)
        self.assertAlmostEqual(facing_factor(120.0, 180.0), 0.0)
        self.assertEqual(facing_factor(0.0, 180.0), 0.0)
        self.assertTrue(0.0 < facing_factor(150.0, 180.0) < 1.0)

    def test_rain_or_fog_removes_the_glare(self):
        self.assertAlmostEqual(glare_strength(18.0, 0.0), 1.0)
        self.assertAlmostEqual(glare_strength(18.0, 0.75), 0.25)
        self.assertEqual(glare_strength(18.0, 1.0), 0.0)
        self.assertEqual(glare_strength(12.0, 0.0), 0.0)

    def test_a_lane_is_exposed_only_when_it_heads_toward_the_sun(self):
        graph = WorldRoadGraph.from_template("town10")
        west, east = graph.get_segment("r20.s0.l4"), graph.get_segment("r20.s0.l-1")
        self.assertGreater(segment_sun_exposure(west, 180.0), 0.95)
        self.assertEqual(segment_sun_exposure(east, 180.0), 0.0)
        self.assertGreater(segment_sun_exposure(east, 0.0), 0.95)


if __name__ == "__main__":
    unittest.main()
