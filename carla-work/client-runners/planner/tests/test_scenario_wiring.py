"""Offline checks of the scenario runner's Planner options; CARLA is stubbed, not run."""

import contextlib
import importlib.util
import io
import os
import queue
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

RUNNERS = Path(__file__).resolve().parents[2]


def load_scenario():
    runlog = types.ModuleType("runlog")
    runlog.WEATHER, runlog.RunLog = (), object
    stubs = {"carla": MagicMock(), "agents": MagicMock(), "agents.navigation": MagicMock(),
             "agents.navigation.basic_agent": MagicMock(), "runlog": runlog}
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("scenario_under_test", RUNNERS / "scenario.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


scenario = load_scenario()
DEMO = scenario.Scenario("wiring-test", "offline wiring test")


def parse(*argv, env=None):
    with patch.object(sys, "argv", ["scenario.py", *argv]), patch.dict(os.environ, env or {}):
        return scenario.parse_args(DEMO)


class ParseArgsTests(unittest.TestCase):
    def test_plan_and_catalog_must_come_together(self):
        for argv in (["--plan", "plan.json"], ["--catalog", "catalog.json.gz"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parse(*argv)

    def test_plan_options_parse(self):
        args = parse("--plan", "plan.json", "--catalog", "catalog.json.gz")
        self.assertEqual((args.plan, args.catalog), ("plan.json", "catalog.json.gz"))
        self.assertFalse(args.allow_unverified_limits)
        self.assertTrue(parse("--plan", "p", "--catalog", "c", "--allow-unverified-limits")
                        .allow_unverified_limits)

    def test_without_plan_nothing_changes(self):
        args = parse()
        self.assertIsNone(args.plan)
        self.assertIsNone(args.catalog)

    def test_tm_port_default_follows_environment(self):
        with patch.dict(os.environ):
            os.environ.pop("CARLA_TM_PORT", None)
            self.assertEqual(parse().tm_port, 8000)
        self.assertEqual(parse(env={"CARLA_TM_PORT": "8123"}).tm_port, 8123)
        self.assertEqual(parse("--tm-port", "9000", env={"CARLA_TM_PORT": "8123"}).tm_port, 9000)


class RunPathTests(unittest.TestCase):
    def test_run_dir_from_helper(self):
        with patch.dict(os.environ, {"CARLA_RUN_DIR": "/runs/job-1"}):
            self.assertEqual(scenario.run_path(DEMO, parse()), "/runs/job-1/run.jsonl.gz")
            self.assertEqual(scenario.run_path(DEMO, parse("--log", "mine.jsonl.gz")), "mine.jsonl.gz")

    def test_default_without_run_dir(self):
        with patch.dict(os.environ):
            os.environ.pop("CARLA_RUN_DIR", None)
            path = scenario.run_path(DEMO, parse())
        self.assertTrue(os.path.basename(path).startswith("wiring-test-"))


class FakeLocation:
    x = y = z = 0.0

    def distance(self, other):
        return 0.5


class FakeVehicle:
    def __init__(self):
        self.controls = []

    def get_location(self):
        return FakeLocation()

    def apply_control(self, control):
        self.controls.append(control)

    def get_control(self):
        return SimpleNamespace(throttle=0.0, brake=0.0, steer=0.0)

    def get_velocity(self):
        return SimpleNamespace(length=lambda: 5.0)


class FakeWorld:
    def __init__(self):
        self.t = 0.0

    def tick(self):
        self.t = round(self.t + scenario.DELTA, 6)

    def get_snapshot(self):
        return SimpleNamespace(timestamp=SimpleNamespace(elapsed_seconds=self.t))


class FakeAgent:
    def __init__(self, steps):
        self.left = steps

    def done(self):
        return self.left <= 0

    def run_step(self):
        self.left -= 1
        return "control"


class FakeLog:
    def __init__(self):
        self.ticks, self.events = 0, []

    def tick(self, snapshot):
        self.ticks += 1

    def event(self, kind, timestamp, **detail):
        self.events.append((kind, timestamp, detail))


class FakeFollower:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), 0

    def update(self, agent, vehicle):
        # Called before the control of the same tick is applied.
        assert len(vehicle.controls) == self.calls
        self.calls += 1
        return self.outputs.pop(0) if self.outputs else None


def drive(follower, steps=3):
    args = SimpleNamespace(ticks=0, no_follow=True, every=1e9)
    stats = {"ticks": 0, "sim_s": 0.0, "distance_m": 0.0, "collision": 0, "lane_invasion": 0,
             "arrived": False, "t0": 0.0}
    vehicle, log = FakeVehicle(), FakeLog()
    with contextlib.redirect_stdout(io.StringIO()):
        scenario.drive(args, FakeWorld(), FakeAgent(steps), vehicle, queue.Queue(), stats, log, None, follower)
    return stats, log, vehicle


class DriveTests(unittest.TestCase):
    def test_target_changes_are_logged_as_plan_target(self):
        first = {"segment_id": "a", "target_speed_kmh": 30.0, "planned_speed_kmh": 30.0,
                 "live_speed_limit_kmh": 40.0, "progress_m": 0.0}
        second = {**first, "segment_id": "b", "target_speed_kmh": 20.0, "planned_speed_kmh": 20.0,
                  "progress_m": 12.0}
        follower = FakeFollower([first, None, second])
        stats, log, vehicle = drive(follower)
        self.assertTrue(stats["arrived"])
        self.assertEqual(follower.calls, 3)
        self.assertEqual(len(vehicle.controls), 3)
        self.assertEqual(log.events, [("plan_target", 0.05, first), ("plan_target", 0.15, second)])

    def test_no_follower_logs_no_plan_target(self):
        stats, log, vehicle = drive(None)
        self.assertTrue(stats["arrived"])
        self.assertEqual((log.ticks, log.events, len(vehicle.controls)), (3, [], 3))


if __name__ == "__main__":
    unittest.main()
