import tempfile
import unittest
from pathlib import Path

from pyotter import Planner
from pyotter.core import CenterlinePoint, RoadSegment, SegmentPosition, WorldHazardLibrary, WorldRoadGraph
from pyotter.modules.planner import PlannerComputedWaypoints, PlannerConfig, PlanningError

try:
    import matplotlib
    matplotlib.use("Agg")
except ImportError:
    matplotlib = None

START, SHORTCUT, DETOUR, FINISH = "r1.s0.l-1", "r2.s0.l-1", "r3.s0.l-1", "r4.s0.l-1"


def lane(road, length, successors):
    line = (CenterlinePoint(0.0, 0.0, 0.0, 0.0, 0.0), CenterlinePoint(float(length), 0.0, 0.0, float(length), float(length)))
    return RoadSegment(road, 0, -1, None, float(length), 40.0, False, tuple(successors), line)


def tiny(detour=True, hazard=True):
    """A 100 m shortcut and a 160 m detour between a 10 m start and a 10 m finish, all limited to 40 km/h."""
    segments = {START: lane(1, 10, [SHORTCUT, DETOUR] if detour else [SHORTCUT]),
                SHORTCUT: lane(2, 100, [FINISH]), FINISH: lane(4, 10, [])}
    if detour:
        segments[DETOUR] = lane(3, 160, [FINISH])
    graph = WorldRoadGraph("tiny", "synthetic", "none", "0.9.16", "hand-built", segments)
    if hazard:
        graph.get_segment(SHORTCUT).assign_hazard_probability([("pedestrian", 1.0)])
    return graph


A, B = SegmentPosition(START, 0.0), SegmentPosition(FINISH, 10.0)


class HandCheckedExample(unittest.TestCase):
    def check(self, route, segments, speeds, time_s, penalty):
        self.assertEqual(route.segment_ids, segments)
        self.assertEqual([step.target_speed_kmh for step in route.steps], speeds)
        self.assertAlmostEqual(route.estimated_time_s, time_s, places=2)
        self.assertAlmostEqual(route.predicted_penalty, penalty, places=2)

    def test_clear_road_takes_the_shortcut_at_the_limit(self):
        self.check(Planner.route(A, B, tiny(hazard=False), risk_scale=2), [START, SHORTCUT, FINISH], [40, 40, 40], 10.8, 0.0)

    def test_without_a_risk_scale_the_hazard_is_ignored(self):
        self.check(Planner.route(A, B, tiny(), risk_scale=0), [START, SHORTCUT, FINISH], [40, 40, 40], 10.8, 18.25)
        self.check(Planner.route(A, B, tiny(), risk_scale=5, mode="naive"), [START, SHORTCUT, FINISH], [40, 40, 40], 10.8, 18.25)

    def test_with_a_risk_scale_the_detour_wins(self):
        self.check(Planner.route(A, B, tiny(), risk_scale=2), [START, DETOUR, FINISH], [40, 40, 40], 16.2, 0.0)

    def test_with_no_detour_the_hazard_is_driven_slower(self):
        self.check(Planner.route(A, B, tiny(detour=False), risk_scale=2), [START, SHORTCUT, FINISH], [40, 26, 40], 15.65, 13.86)

    def test_cautious_keeps_the_naive_route_and_caps_its_speed(self):
        route = Planner.route(A, B, tiny(), mode="cautious")
        self.assertEqual(route.segment_ids, [START, SHORTCUT, FINISH])
        self.assertEqual({step.target_speed_kmh for step in route.steps}, {20.0})
        self.assertAlmostEqual(route.estimated_time_s, 21.6)

    def test_objective_is_time_plus_scaled_penalty(self):
        route = Planner.route(A, B, tiny(detour=False), risk_scale=2)
        self.assertAlmostEqual(route.objective, route.estimated_time_s + 2 * route.predicted_penalty)
        self.assertAlmostEqual(route.distance_m, 120.0)


class Endpoints(unittest.TestCase):
    def test_partial_first_and_last_segments_are_charged_by_distance(self):
        route = Planner.route(SegmentPosition(START, 4.0), SegmentPosition(FINISH, 2.5), tiny(hazard=False))
        self.assertEqual([(s.start_offset_m, s.end_offset_m) for s in route.steps], [(4.0, 10.0), (0.0, 100.0), (0.0, 2.5)])

    def test_same_segment_ahead_is_one_step_and_same_point_is_empty(self):
        graph = tiny(hazard=False)
        route = Planner.route(SegmentPosition(SHORTCUT, 20.0), SegmentPosition(SHORTCUT, 70.0), graph)
        self.assertEqual([(s.segment_id, s.distance_m) for s in route.steps], [(SHORTCUT, 50.0)])
        self.assertEqual(Planner.route(A, A, graph).steps, ())

    def test_a_destination_behind_the_origin_needs_a_legal_loop(self):
        with self.assertRaises(PlanningError):
            Planner.route(SegmentPosition(SHORTCUT, 70.0), SegmentPosition(SHORTCUT, 20.0), tiny())

    def test_bad_inputs_are_rejected(self):
        graph = tiny()
        for arguments in (
            {"origin": SegmentPosition("r9.s0.l1", 0.0)}, {"origin": SegmentPosition(START, 99.0)},
            {"risk_scale": -1.0}, {"mode": "reckless"}, {"config": PlannerConfig(candidate_speeds_kmh=())},
            {"config": PlannerConfig(weights={"pedestrian": -1.0})}, {"require_verified_limits": True},
        ):
            with self.assertRaises(PlanningError):
                Planner.route(arguments.pop("origin", A), B, graph, **arguments)


class Town10(unittest.TestCase):
    def setUp(self):
        self.hazards = WorldHazardLibrary()
        self.graph = WorldRoadGraph.from_template("town10")
        for segment in self.graph.segments_in_junction(189):
            segment.assign_hazard_probability([(self.hazards.pedestrian, 0.03)])
        self.graph.set_condition(self.hazards.wet_road, probability=0.9, severity="high", variability=0.1)
        self.graph.set_condition(self.hazards.low_visibility, probability=0.5, severity="mid", variability=0.4)
        self.graph.set_time_of_day(17.5)
        self.a, self.b = self.graph.spawn_points[18], self.graph.spawn_points[127]

    def test_hazard_score_adds_events_conditions_and_the_sun(self):
        scores = Planner.hazard_scores(self.graph)
        wet = self.graph.get_condition("wet_road").expected_severity()
        self.assertAlmostEqual(scores["r20.s0.l-1"], wet + 0.25)             # eastbound: rain or fog only
        self.assertGreater(scores["r20.s0.l4"], wet + 0.25 + 0.6)            # westbound at 17:30: sun as well
        self.assertAlmostEqual(scores["r255.s0.l-1"], wet + 0.25 + 0.03)     # eastbound through junction 189
        doubled = Planner.hazard_scores(self.graph, PlannerConfig(weights={"wet_road": 2.0, "low_visibility": 0.0}))
        self.assertAlmostEqual(doubled["r20.s0.l4"], 2 * wet)

    def test_a_uniform_condition_slows_the_route_without_moving_it(self):
        naive = Planner.route(self.a, self.b, self.graph, mode="naive")
        aware = Planner.route(self.a, self.b, self.graph, risk_scale=2)
        self.assertEqual(naive.segment_ids, aware.segment_ids)
        self.assertGreater(aware.estimated_time_s, naive.estimated_time_s)
        self.assertLess(aware.predicted_penalty, naive.predicted_penalty)

    def test_a_weighted_event_moves_the_route_off_its_junction(self):
        config = PlannerConfig(weights={"pedestrian": 20.0})
        naive = Planner.route(self.a, self.b, self.graph, mode="naive", config=config)
        aware = Planner.route(self.a, self.b, self.graph, risk_scale=2, config=config)
        through = lambda route: {self.graph.get_segment(sid).junction_id for sid in route.segment_ids}
        self.assertIn(189, through(naive))
        self.assertNotIn(189, through(aware))
        self.assertTrue(all(step.target_speed_kmh <= 30.0 for step in aware.steps))

    def test_route_names_its_world_and_survives_a_save(self):
        route = Planner.route(self.a, self.b, self.graph, risk_scale=2)
        self.assertEqual((route.graph_id, route.forecast_hash), (self.graph.graph_id, self.graph.forecast_hash()))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "route.json.gz"
            route.save(path)
            self.assertEqual(PlannerComputedWaypoints.load(path), route)

    @unittest.skipIf(matplotlib is None, "matplotlib is not installed")
    def test_view_draws_one_map_per_route(self):
        routes = [Planner.route(self.a, self.b, self.graph, mode=mode, risk_scale=2) for mode in ("naive", "cautious", "risk-aware")]
        figure = Planner.view_routes(self.graph, routes)
        maps = [axes for axes in figure.axes if axes.get_xlabel() == "x (m)"]
        self.assertEqual([axes.get_title(loc="left") for axes in maps], ["naive", "cautious", "risk-aware, risk scale 2"])
        self.assertEqual(len(Planner.view_routes(self.graph, routes[0]).axes), 3)
        with self.assertRaises(PlanningError):
            Planner.view_routes(tiny(), routes)


if __name__ == "__main__":
    unittest.main()
