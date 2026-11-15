import gzip
import importlib.util
import json
import math
from pathlib import Path
import socket
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from planner.adapter import project_progress
from planner.carla_map import map_hash, sample_point
from planner.core import fingerprint, make_plan
from planner.files import read_json

WORK = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("hpc_run", WORK / "scripts/hpc_run.py")
hpc_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hpc_run)


def assert_same_plan(test, actual, expected, path="plan"):
    """Exact structure, ids, hashes, and strings; floats may differ in the last bits across machines."""
    if isinstance(expected, float) or isinstance(actual, float):
        test.assertTrue(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12),
                        f"{path}: {actual!r} != {expected!r}")
    elif isinstance(expected, dict):
        test.assertEqual(sorted(actual), sorted(expected), f"{path}: keys differ")
        for key in expected:
            assert_same_plan(test, actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        test.assertEqual(len(actual), len(expected), f"{path}: lengths differ")
        for index, (a, e) in enumerate(zip(actual, expected)):
            assert_same_plan(test, a, e, f"{path}[{index}]")
    else:
        test.assertEqual(actual, expected, path)


class IntegrationHelperTests(unittest.TestCase):
    def test_map_hash_ignores_formatting(self):
        self.assertEqual(map_hash('<map a="1"><road id="2"/></map>'),
                         map_hash('<map a="1">\n <road id="2"></road>\n</map>'))

    def test_projection_does_not_jump_to_later_loop(self):
        points = [(0, 0, 0, 0), (10, 0, 0, 10), (10, 10, 0, 20),
                  (0, 10, 0, 30), (0, 0, 0, 40), (10, 0, 0, 50)]
        self.assertAlmostEqual(project_progress(points, 1, (2, 0, 0)), 2)
        self.assertAlmostEqual(project_progress(points, 41, (2, 0, 0)), 42)
        self.assertEqual(project_progress(points, 3, (2, 0, 0)), 3)

    def test_capture_requires_end_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl.gz"
            rows = [{"type": "event", "kind": "collision"}]
            with gzip.open(path, "wt") as stream:
                stream.write(json.dumps(rows[0]) + "\n")
            self.assertEqual(hpc_run.capture_summary(path), {"reason": "incomplete", "collisions": 1})
            with gzip.open(path, "wt") as stream:
                for row in rows + [{"type": "end", "reason": "stopped", "ticks": 100}]:
                    stream.write(json.dumps(row) + "\n")
            self.assertEqual(hpc_run.capture_summary(path)["reason"], "stopped")

    def test_port_conflict_is_detected(self):
        with socket.socket() as held:
            held.bind(("127.0.0.1", 0))
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                hpc_run.check_ports([held.getsockname()[1]])

    def test_source_fingerprint_ignores_run_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "code.py").write_text("first")
            original = hpc_run.source_hash(root)
            (root / "runs").mkdir()
            (root / "runs/output.json").write_text("new result")
            self.assertEqual(original, hpc_run.source_hash(root))
            (root / "code.py").write_text("second")
            self.assertNotEqual(original, hpc_run.source_hash(root))


class Town10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read_json(WORK / "planner-data/town10-local.json.gz")

    def test_real_graph_geometry(self):
        self.assertEqual(len(self.catalog["segments"]), 168)
        for sid, segment in self.catalog["segments"].items():
            with self.subTest(segment=sid):
                geometry = segment["geometry"]
                measured = sum(math.dist([a[k] for k in ("x", "y", "z")], [b[k] for k in ("x", "y", "z")])
                               for a, b in zip(geometry, geometry[1:]))
                self.assertAlmostEqual(measured, segment["length_m"])
                middle = sample_point(segment, measured / 2)
                self.assertAlmostEqual(middle["distance_m"], measured / 2)
                for nxt in segment["successors"]:
                    a, b = geometry[-1], self.catalog["segments"][nxt]["geometry"][0]
                    self.assertLess(math.dist([a[k] for k in ("x", "y", "z")], [b[k] for k in ("x", "y", "z")]), 1)

    def test_saved_town10_plan_reproduces(self):
        forecast = read_json(WORK / "planner-data/town10-mock.json")
        trip = read_json(WORK / "planner-data/town10-trip.json")
        expected = read_json(WORK / "planner-data/town10-plan.json")
        actual = make_plan(self.catalog, forecast, trip)
        assert_same_plan(self, actual, expected)
        self.assertEqual(actual["catalog_hash"], fingerprint(self.catalog))
        self.assertGreater(len(actual["segments"]), 2)


class HpcLifecycleTests(unittest.TestCase):
    """Exercise lifecycle and manifests using owned stand-in processes, not CARLA."""

    def run_helper(self, reason="arrived", startup_error=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.sif"
            image.write_text("test image")
            stat = image.stat()
            environment = {"image": str(image), "image_size": stat.st_size,
                           "image_mtime_ns": stat.st_mtime_ns, "image_sha256": "test-only",
                           "server_root": "/test", "agents_root": str(root), "python": sys.executable}
            (root / "environment.json").write_text(json.dumps(environment))
            real_popen = subprocess.Popen
            processes = []

            def launch(command, **kwargs):
                if command[0] == "apptainer":
                    code = "import time; time.sleep(60)"
                else:
                    code = ("import os,gzip,json; from pathlib import Path; "
                            "p=Path(os.environ['CARLA_RUN_DIR'])/'run.jsonl.gz'; "
                            f"f=gzip.open(p,'wt'); f.write(json.dumps({{'type':'end','reason':{reason!r},'ticks':1}})+'\\n'); f.close()")
                child = real_popen([sys.executable, "-c", code], **kwargs)
                processes.append(child)
                return child

            handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
            try:
                with patch.object(sys, "argv", ["hpc_run", "--home", str(root), "smoke"]), \
                     patch.object(hpc_run, "check_allocation", return_value=("123", "test GPU")), \
                     patch.object(hpc_run, "check_ports"), \
                     patch.object(hpc_run, "source_hash", return_value="test-source"), \
                     patch.object(hpc_run, "wait_ready", side_effect=RuntimeError("startup failed") if startup_error else None,
                                  return_value={"server_version": "0.9.16"}), \
                     patch.object(hpc_run.subprocess, "Popen", side_effect=launch):
                    code = hpc_run.main()
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
                for child in processes:
                    self.assertIsNotNone(child.poll(), "helper left an owned process running")
            manifests = list(root.glob("runs/*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            return code, json.loads(manifests[0].read_text())

    def test_success_and_cleanup(self):
        code, manifest = self.run_helper()
        self.assertEqual(code, 0)
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["simulation"]["reason"], "arrived")

    def test_tick_limit_not_counted_as_success(self):
        code, manifest = self.run_helper(reason="stopped")
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "incomplete")

    def test_startup_failure_cleans_server(self):
        code, manifest = self.run_helper(startup_error=True)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["error"], "startup failed")


if __name__ == "__main__":
    unittest.main()
