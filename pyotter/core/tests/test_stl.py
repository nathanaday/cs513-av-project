import math
import unittest

from pyotter.core.utilities.stl import always, eventually, signal

TRACE = {"time_s": [0.0, 1.0, 2.0, 3.0, 4.0], "gap": [9.0, 5.0, 3.0, 6.0, 8.0], "speed": [0.0, 2.0, 4.0, 4.0, 1.0]}


class Robustness(unittest.TestCase):
    def test_predicates_measure_the_distance_to_the_bound(self):
        self.assertEqual((signal("gap") >= 4.0).robustness(TRACE), [5.0, 1.0, -1.0, 2.0, 4.0])
        self.assertEqual((signal("gap") <= 4.0).robustness(TRACE), [-5.0, -1.0, 1.0, -2.0, -4.0])
        self.assertEqual((signal("speed") <= signal("gap") + 1.0).robustness(TRACE), [10.0, 4.0, 0.0, 3.0, 8.0])

    def test_always_and_eventually_look_at_the_rest_of_the_trace(self):
        self.assertEqual(always(signal("gap") >= 4.0).robustness(TRACE), [-1.0, -1.0, -1.0, 2.0, 4.0])
        self.assertEqual(eventually(signal("gap") <= 4.0).robustness(TRACE), [1.0, 1.0, 1.0, -2.0, -4.0])

    def test_time_bounds_are_in_seconds_from_each_sample(self):
        self.assertEqual(always(signal("gap") >= 4.0, 0, 1).robustness(TRACE), [1.0, -1.0, -1.0, 2.0, 4.0])
        self.assertEqual(eventually(signal("speed") >= 4.0, 1, 2).robustness(TRACE), [0.0, 0.0, 0.0, -3.0, -math.inf])

    def test_connectives(self):
        near, moving = signal("gap") <= 4.0, signal("speed") >= 3.0
        self.assertEqual((near & moving).robustness(TRACE), [-5.0, -1.0, 1.0, -2.0, -4.0])
        self.assertEqual((near | moving).robustness(TRACE), [-3.0, -1.0, 1.0, 1.0, -2.0])
        self.assertEqual((~near).robustness(TRACE), [5.0, 1.0, -1.0, 2.0, 4.0])
        self.assertEqual(near.implies(moving).robustness(TRACE), [5.0, 1.0, 1.0, 2.0, 4.0])

    def test_formulas_print_as_stl(self):
        self.assertEqual(str(always(signal("gap") >= 2.0)), "always (gap >= 2)")
        self.assertEqual(str(always((signal("gap") <= 4.0).implies(eventually(signal("speed") <= 1.0, 0, 2)))),
                         "always ((gap <= 4) -> (eventually[0,2] (speed <= 1)))")
        self.assertEqual(str(signal("speed") <= signal("limit") + 0.5), "speed <= (limit + 0.5)")

    def test_bad_inputs(self):
        with self.assertRaises(KeyError):
            always(signal("missing") >= 0.0).robustness(TRACE)
        with self.assertRaises(ValueError):
            always(signal("gap") >= 0.0, 2, 1)


if __name__ == "__main__":
    unittest.main()
