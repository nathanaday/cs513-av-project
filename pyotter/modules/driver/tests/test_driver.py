import math
import tempfile
import unittest
from pathlib import Path

from pyotter import Driver, Planner, World
from pyotter.core import DrivingSafetyReq, RoadGraphError, WorldHazardLibrary, WorldRoadGraph
from pyotter.modules.driver import (
    NO_GAP_M, DriverModel, DrivingScenario, DrivingScenarioTelemetry, Outcome, Signal, TelemetryEventKind,
)
from pyotter.modules.driver.controller import (
    RouteFollower, SpeedControl, allowed_speed, box_gap, lookahead_m, steer_toward,
)


def world():
    hazards, graph = WorldHazardLibrary(), WorldRoadGraph.from_template("town10")
    for segment in graph.segments_in_junction(189):
        segment.assign_hazard_probability([(hazards.pedestrian, 0.03)])
    graph.set_condition(hazards.wet_road, probability=1.0, severity=0.8)
    graph.set_time_of_day(17.5)
    return hazards, graph


def telemetry(samples=200, **changes):
    """A steady, uneventful drive at 8 m/s, with chosen signals replaced."""
    record = DrivingScenarioTelemetry("steady", "g", "Town10HD_Opt", 1, "naive", 0.0, DriverModel(), 0.05, outcome="arrived")
    for tick in range(samples):
        sample = {signal.value: 0.0 for signal in Signal}
        sample.update(time_s=tick * 0.05, speed_mps=8.0, speed_limit_mps=8.33, target_speed_mps=8.0,
                      allowed_speed_mps=8.0, progress_m=tick * 0.4, gap_m=NO_GAP_M, gap_ahead_m=NO_GAP_M, detection_range_m=60.0)
        sample.update({name: values[tick] for name, values in changes.items()})
        record.add_sample(**sample)
    return record


class Scenario(unittest.TestCase):
    def setUp(self):
        self.hazards, self.graph = world()
        self.a, self.b = self.graph.spawn_points[18], self.graph.spawn_points[127]
        self.route = Planner.route(self.a, self.b, self.graph, risk_scale=2)
        self.spawns = World.roll_hazards(self.graph, self.hazards, seed=5, duration_s=120)

    def test_scenario_is_one_file_holding_the_rolled_world_the_route_and_the_driver(self):
        driver = DriverModel(safety=DrivingSafetyReq(min_gap_m=3.0), detection_range_m=40.0)
        scenario = Driver.scenario(self.graph, self.spawns, self.route, driver=driver, name="demo")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scenario.json.gz"
            scenario.save(path)
            loaded = DrivingScenario.load(path)
        self.assertEqual((loaded.spawns, loaded.route, loaded.driver, loaded.name), (self.spawns, self.route, driver, "demo"))
        self.assertEqual(loaded.graph, self.graph)
        self.assertEqual(loaded.duration_s, 120.0)

    def test_a_scenario_file_has_one_fingerprint_however_often_it_is_written(self):
        scenario = Driver.scenario(self.graph, self.spawns, self.route, name="demo")
        self.assertEqual(scenario.fingerprint, "")
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "first.json.gz", Path(folder) / "second.json.gz"
            scenario.save(first)
            saved = scenario.fingerprint
            DrivingScenario.load(first).save(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(DrivingScenario.load(second).fingerprint, saved)
        self.assertEqual(len(saved), 64)
        other = Driver.scenario(self.graph, self.spawns, self.route, name="other")
        with tempfile.TemporaryDirectory() as folder:
            other.save(Path(folder) / "other.json.gz")
        self.assertNotEqual(other.fingerprint, saved)

    def test_scenario_rejects_parts_that_do_not_belong_together(self):
        other = WorldRoadGraph.from_template("town10")
        other.set_time_of_day(8.0)
        with self.assertRaises(RoadGraphError):
            Driver.scenario(other, self.spawns, self.route)
        short = World.roll_hazards(self.graph, self.hazards, seed=5, duration_s=20)
        with self.assertRaises(RoadGraphError):
            Driver.scenario(self.graph, short, self.route)

    def test_driver_model_turns_conditions_into_range_and_braking(self):
        driver = DriverModel()
        self.assertEqual(driver.detection_range(0.0), 60.0)
        self.assertEqual(driver.detection_range(0.5), 30.0)
        self.assertEqual(driver.detection_range(1.0), 5.0)
        self.assertEqual(driver.planned_deceleration(0.0), 3.0)
        self.assertEqual(driver.planned_deceleration(1.0), 1.5)
        with self.assertRaises(ValueError):
            DrivingSafetyReq(min_gap_m=-1.0)


class Control(unittest.TestCase):
    def setUp(self):
        _, graph = world()
        route = Planner.route(graph.spawn_points[18], graph.spawn_points[127], graph, risk_scale=2)
        self.route, self.follower = route, RouteFollower(graph, route)

    def test_follower_measures_the_route_and_reads_the_plan_along_it(self):
        self.assertAlmostEqual(self.follower.length_m, self.route.distance_m, delta=0.5)
        first, last = self.route.steps[0], self.route.steps[-1]
        self.assertEqual(self.follower.plan_at(0.0), (first.target_speed_kmh / 3.6, 30 / 3.6, first.segment_id))
        self.assertEqual(self.follower.plan_at(self.follower.length_m)[2], last.segment_id)

    def test_locate_follows_the_car_and_never_goes_back(self):
        x, y = self.follower.point_at(50.0)
        self.assertAlmostEqual(self.follower.locate(x, y, 45.0), 50.0, delta=0.01)
        self.assertEqual(self.follower.locate(x, y, 58.0), 58.0)

    def test_gap_ahead_sees_only_what_is_in_the_path_and_in_reach(self):
        x, y = self.follower.point_at(40.0)
        self.assertAlmostEqual(self.follower.gap_ahead(10.0, [(x, y, 0.4)], 60.0), 29.6, delta=0.05)
        self.assertIsNone(self.follower.gap_ahead(10.0, [(x, y, 0.4)], 20.0))
        self.assertIsNone(self.follower.gap_ahead(50.0, [(x, y, 0.4)], 60.0))
        self.assertIsNone(self.follower.gap_ahead(10.0, [(x + 30.0, y + 30.0, 0.4)], 60.0))

    def test_steering_turns_toward_the_target(self):
        self.assertEqual(steer_toward(0, 0, 0, (10.0, 0.0), 2.9, 70.0), 0.0)
        self.assertGreater(steer_toward(0, 0, 0, (10.0, 3.0), 2.9, 70.0), 0.0)
        self.assertLess(steer_toward(0, 0, 0, (10.0, -3.0), 2.9, 70.0), 0.0)
        self.assertEqual(steer_toward(0, 0, 0, (0.0, 3.0), 2.9, 30.0), 1.0)
        self.assertEqual((lookahead_m(0.0), lookahead_m(30.0)), (3.0, 8.0))

    def test_allowed_speed_lets_the_car_stop_in_the_room_it_has(self):
        self.assertEqual(allowed_speed(8.0, None, 3.0), 8.0)
        self.assertAlmostEqual(allowed_speed(8.0, 6.0, 3.0), 6.0)
        self.assertEqual(allowed_speed(8.0, -1.0, 3.0), 0.0)
        self.assertEqual(allowed_speed(8.0, 100.0, 3.0), 8.0)

    def test_speed_control_stays_inside_the_safety_limits(self):
        throttle, brake = SpeedControl(DriverModel()).command(0.0, 8.0, 0.05)
        self.assertAlmostEqual(throttle, 3.0 / 9.0)   # asks for the acceleration limit, not full throttle
        self.assertEqual(brake, 0.0)
        throttle, brake = SpeedControl(DriverModel()).command(8.0, 0.0, 0.05)
        self.assertEqual(throttle, 0.0)
        self.assertAlmostEqual(brake, (6.0 - 0.037 * 8.0 * 9.0) / 8.0)
        holding, _ = SpeedControl(DriverModel()).command(8.0, 8.0, 0.05)
        self.assertAlmostEqual(holding, 0.037 * 8.0)

    def test_an_obstacle_too_close_for_gentle_braking_gets_harder_braking(self):
        _, gentle = SpeedControl(DriverModel()).command(6.0, 5.0, 0.05)
        _, firm = SpeedControl(DriverModel()).command(6.0, 5.0, 0.05, stop_within_m=4.0)
        _, limit = SpeedControl(DriverModel()).command(6.0, 5.0, 0.05, stop_within_m=0.5)
        self.assertEqual(gentle, 0.0)
        self.assertAlmostEqual(firm, (6.0 ** 2 / 8.0 - 0.037 * 6.0 * 9.0) / 8.0)
        self.assertAlmostEqual(limit, (6.0 - 0.037 * 6.0 * 9.0) / 8.0)
        _, slippery = SpeedControl(DriverModel(), grip=0.5).command(6.0, 5.0, 0.05, stop_within_m=4.0)
        self.assertAlmostEqual(slippery, 2 * firm)
        self.assertEqual(SpeedControl(DriverModel()).command(0.1, 0.0, 0.05), (0.0, 0.6))

    def test_box_gap_is_measured_from_the_body(self):
        self.assertAlmostEqual(box_gap(0, 0, 0, 2.4, 1.0, 10.0, 0.0, 0.4), 7.2)
        self.assertAlmostEqual(box_gap(0, 0, 0, 2.4, 1.0, 0.0, 3.0, 0.4), 1.6)
        self.assertAlmostEqual(box_gap(0, 0, 90, 2.4, 1.0, 0.0, 10.0, 0.4), 7.2)
        self.assertLess(box_gap(0, 0, 0, 2.4, 1.0, 1.0, 0.5, 0.4), 0.0)


class Evaluation(unittest.TestCase):
    def test_an_uneventful_drive_keeps_every_requirement(self):
        result = Driver.evaluate(telemetry())
        self.assertTrue(result.satisfied)
        self.assertEqual([r.name for r in result.requirements], ["no_collision", "min_gap", "min_gap_ahead", "braking", "acceleration", "speed_limit"])
        self.assertEqual(result.get("braking").robustness, 6.0)
        self.assertAlmostEqual(result.get("speed_limit").robustness, 8.33 + 3 / 3.6 - 8.0)
        self.assertEqual(result.get("min_gap").formula, "always (gap_m >= 2)")

    def test_a_near_miss_is_kept_but_reported_as_the_closest(self):
        gaps = [NO_GAP_M] * 200
        gaps[100:110] = [6.0, 4.0, 3.0, 2.6, 2.4, 2.6, 3.0, 4.0, 6.0, 9.0]
        result = Driver.evaluate(telemetry(gap_m=gaps))
        gap = result.get("min_gap")
        self.assertTrue(result.satisfied)
        self.assertAlmostEqual(gap.robustness, 0.4)
        self.assertAlmostEqual(gap.margin_ratio, 0.2)
        self.assertAlmostEqual(gap.worst_time_s, 104 * 0.05)
        self.assertEqual(result.closest.name, "min_gap")

    def test_breaches_are_named_with_how_far_and_when(self):
        gaps, braking, hits = [NO_GAP_M] * 200, [0.0] * 200, [0.0] * 200
        gaps[50], hits[150] = 0.5, 1.0
        braking[115:130] = [-7.5] * 15   # 0.75 s of braking past the limit
        record = telemetry(gap_m=gaps, acceleration_mps2=braking, collision=hits)
        record.add_event(7.5, "collision", other="walker.pedestrian.0001")
        result = Driver.evaluate(record)
        self.assertFalse(result.satisfied)
        self.assertEqual([r.name for r in result.breached], ["no_collision", "min_gap", "braking"])
        self.assertAlmostEqual(result.get("min_gap").robustness, -1.5)
        self.assertAlmostEqual(result.get("braking").robustness, -1.5)
        self.assertEqual((result.get("braking").worst_time_s, result.get("braking").worst_value), (5.75, -7.5))
        self.assertEqual(result.collisions, 1)
        self.assertEqual(result.closest.name, "no_collision")
        self.assertIn("BREACHED", result.summary())

    def test_one_tick_of_acceleration_past_the_limit_is_not_a_breach(self):
        spike = [0.0] * 200
        spike[20], spike[90] = 11.0, -9.0
        result = Driver.evaluate(telemetry(acceleration_mps2=spike))
        self.assertTrue(result.satisfied)
        self.assertEqual(result.get("braking").robustness, 6.0)
        self.assertEqual(result.get("acceleration").formula, "always (eventually[0,0.5] (acceleration_mps2 <= 3))")

    def test_gap_ahead_is_checked_along_the_route_against_its_own_limit(self):
        ahead = [NO_GAP_M] * 200
        ahead[60:63] = [9.0, 6.5, 8.0]
        result = Driver.evaluate(telemetry(gap_ahead_m=ahead))
        self.assertTrue(result.satisfied)
        self.assertEqual(result.get("min_gap_ahead").formula, "always (gap_ahead_m >= 5)")
        self.assertAlmostEqual(result.get("min_gap_ahead").robustness, 1.5)
        self.assertAlmostEqual(result.get("min_gap_ahead").worst_time_s, 61 * 0.05)
        strict = Driver.evaluate(telemetry(gap_ahead_m=ahead), DrivingSafetyReq(min_gap_ahead_m=8.0))
        self.assertEqual([r.name for r in strict.breached], ["min_gap_ahead"])

    def test_a_requirement_gives_the_value_it_compares_against_its_threshold(self):
        slow = [0.0] * 200
        slow[100:120] = [-4.0] * 20      # 1 s of braking, longer than the sustained time
        slow[150] = -9.0                 # one tick, which the sustained time ignores
        trace = telemetry(acceleration_mps2=slow).signals
        by_name = {requirement.name: requirement for requirement in Driver.requirements(DrivingSafetyReq())}
        braking = by_name["braking"]
        self.assertEqual((braking.threshold, braking.stay_above), (-6.0, True))
        self.assertEqual(min(braking.values(trace)), -4.0)
        self.assertEqual(min(braking.margins(trace)), 2.0)
        speed = by_name["speed_limit"]
        self.assertAlmostEqual(speed.values(trace)[0], 8.0 - 8.33)
        self.assertEqual(by_name["min_gap"].values(trace), trace[Signal.GAP_M])

    def test_other_requirements_can_be_applied_to_the_same_run(self):
        gaps = [4.0] * 200
        self.assertTrue(Driver.evaluate(telemetry(gap_m=gaps)).satisfied)
        strict = Driver.evaluate(telemetry(gap_m=gaps), DrivingSafetyReq(min_gap_m=5.0))
        self.assertEqual([r.name for r in strict.breached], ["min_gap"])

    def test_telemetry_survives_a_save_and_an_empty_one_is_refused(self):
        record = telemetry()
        record.scenario_fingerprint = "ab" * 32
        record.add_event(1.0, "hazard_started", hazard_id="pedestrian")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "telemetry.json.gz"
            record.save(path)
            loaded = DrivingScenarioTelemetry.load(path)
        self.assertEqual(loaded, record)
        self.assertEqual(Driver.evaluate(loaded).scenario_fingerprint, "ab" * 32)
        self.assertAlmostEqual(loaded.duration_s, 199 * 0.05)
        self.assertTrue(math.isclose(loaded.distance_m, 199 * 0.4))
        with self.assertRaises(ValueError):
            Driver.evaluate(telemetry(samples=0))
        self.assertIs(loaded.outcome, Outcome.ARRIVED)
        self.assertEqual(loaded.events_of(TelemetryEventKind.HAZARD_STARTED), loaded.events_of("hazard_started"))

    def test_telemetry_with_uneven_or_unknown_signals_is_refused(self):
        record = telemetry()
        record.add_sample(time_s=1.0)
        with self.assertRaises(ValueError):
            record.validate()
        with self.assertRaises(KeyError):
            record.add_sample(altitude_m=1.0)
        with self.assertRaises(ValueError):
            DrivingScenarioTelemetry("x", "g", "Town10HD_Opt", 1, "naive", 0.0, DriverModel(), 0.05, outcome="lost")


if __name__ == "__main__":
    unittest.main()
