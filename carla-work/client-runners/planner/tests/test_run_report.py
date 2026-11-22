"""The run report on a small hand-checkable recording; no CARLA."""

import contextlib
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

WORK = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("run_report", WORK / "scripts/run_report.py")
run_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_report)

PLANNER = {"mode": "risk-aware", "trip": {"risk_weight": 2.0}, "plan_hash": "ab" * 32,
           "catalog_id": "cat-1", "catalog_hash": "cd" * 32, "estimated_time_s": 2.0,
           "predicted_penalty": 1.5}
# Δt = 0.5 s. The ego drives 10 m at 36 km/h, waits 2 s by a red light 3 m away, then 15 m more.
X = [0, 5, 10, 10, 10, 10, 10, 15, 20, 25]
KMH = [36, 36, 36, 0, 0, 0, 0, 36, 36, 36]


def recording(planner=PLANNER, end=True):
    settings = {"planner": planner} if planner else {}
    rows = [{"type": "header", "map": "Town10HD_Opt", "scenario": "planner-demo", "delta_s": 0.5,
             "ego_id": 1, "started_utc": "2026-11-14T00:00:00+00:00", "settings": settings},
            {"type": "actor", "id": 1, "type_id": "vehicle.test", "pose": [0, 0, 0, 0, 0, 0]},
            {"type": "actor", "id": 9, "type_id": "traffic.traffic_light", "pose": [10, 3, 0, 0, 0, 0]}]
    for tick, (x, kmh) in enumerate(zip(X, KMH)):
        rows.append({"type": "tick", "tick": tick, "t": tick * 0.5, "lights": [[9, "Red" if tick < 7 else "Green"]],
                     "actors": [[1, x, 0, 0, 0, 0, 0, kmh / 3.6, 0, 0]]})
        if planner and tick == 0:
            rows.append({"type": "event", "kind": "plan_target", "tick": 0, "t": 0.0, "segment_id": "a",
                         "planned_speed_kmh": 36.0, "target_speed_kmh": 36.0, "live_speed_limit_kmh": 50.0,
                         "progress_m": 0.0})
        if planner and tick == 5:
            rows.append({"type": "event", "kind": "plan_target", "tick": 5, "t": 2.5, "segment_id": "b",
                         "planned_speed_kmh": 40.0, "target_speed_kmh": 30.0, "live_speed_limit_kmh": 30.0,
                         "progress_m": 10.0})
        if tick == 8:
            rows.append({"type": "event", "kind": "collision", "tick": 8, "t": 4.0})
            rows.append({"type": "event", "kind": "lane_invasion", "tick": 8, "t": 4.0, "markings": ["Solid"]})
    if end:
        rows.append({"type": "end", "ticks": 10, "reason": "arrived", "wall_s": 1.5})
    return rows


PLAN = {"catalog_hash": "cd" * 32, "estimated_time_s": 2.0, "segments": [{"segment_id": "a"}, {"segment_id": "b"}]}
CATALOG = {"catalog_id": "cat-1", "segments": {"a": {"speed_limit_kmh": 40.0}, "b": {"speed_limit_kmh": 64.3738}}}


class RunReportTests(unittest.TestCase):
    def test_outcome_time_and_stops(self):
        s = run_report.summarize(recording())
        self.assertEqual((s["reason"], s["ticks"], s["collisions"], s["lane_invasions"]), ("arrived", 10, 1, 1))
        self.assertAlmostEqual(s["sim_s"], 4.5)
        self.assertAlmostEqual(s["ratio"], 3.0)
        self.assertAlmostEqual(s["distance_m"], 25.0)
        self.assertAlmostEqual(s["max_kmh"], 36.0)
        self.assertEqual(s["stops"], [{"t": 1.5, "duration_s": 2.0, "light_m": 3.0, "light_state": "Red"}])
        self.assertAlmostEqual(s["stopped_s"], 2.0)
        self.assertAlmostEqual(s["moving_s"], 2.5)

    def test_plan_vs_drive(self):
        s = run_report.summarize(recording(), PLAN, CATALOG)
        a, b = s["segments"]
        self.assertEqual((a["segment_id"], a["driven_m"], a["time_s"], a["mean_moving_kmh"]), ("a", 10.0, 2.5, 36.0))
        self.assertEqual((b["planned_kmh"], b["commanded_kmh"], b["live_limit_kmh"]), (40.0, 30.0, 30.0))
        self.assertAlmostEqual(b["catalog_limit_kmh"], 64.3738)
        self.assertEqual((b["driven_m"], b["time_s"]), (15.0, 2.5))
        self.assertEqual(s["route"], {"driven": 2, "planned": 2, "in_order": True})
        # Steady ticks 1, 2 (commanded 36) and 8, 9 (commanded 30, driven 36).
        self.assertEqual(s["tracking"], {"n": 4, "mean": 3.0, "mean_abs": 3.0})
        self.assertEqual(s["warnings"], [])

    def test_markdown_report(self):
        text = run_report.markdown(run_report.summarize(recording(), PLAN, CATALOG))
        for line in ("| End | arrived after 10 ticks |", "| Collisions / lane invasions | 1 / 1 |",
                     "| Moving / stopped time | 2.5 s / 2.0 s in 1 stop |", "risk-aware, λ = 2",
                     "moving time +25.0%", "| 1.5 s | 2.0 s | 3.0 m | Red |",
                     "| 2 | `b` | 40 | 30 | 30 | 64.4 | 15 | 2.5 | 36.0 | 36.0 |",
                     "2 of 2 planned segments driven, in plan order."):
            self.assertIn(line, text)

    def test_mismatches_and_incomplete_runs_are_reported(self):
        plan = {**PLAN, "catalog_hash": "ef" * 32, "segments": [{"segment_id": "b"}, {"segment_id": "a"}]}
        s = run_report.summarize(recording(end=False), plan, {**CATALOG, "catalog_id": "other"})
        self.assertEqual(s["reason"], "incomplete")
        self.assertFalse(s["route"]["in_order"])
        self.assertEqual(len(s["warnings"]), 3)
        self.assertIn("incomplete", run_report.markdown(s))

    def test_smoke_run_has_no_plan_section(self):
        s = run_report.summarize(recording(planner=None))
        self.assertEqual((s["segments"], s["route"], s["tracking"]), ([], None, None))
        self.assertNotIn("Plan vs drive", run_report.markdown(s))

    def test_cli_reads_plan_and_catalog_next_to_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with gzip.open(root / "run.jsonl.gz", "wt") as stream:
                stream.writelines(json.dumps(row) + "\n" for row in recording())
            (root / "plan.json").write_text(json.dumps(PLAN))
            with gzip.open(root / "catalog.json.gz", "wt") as stream:
                json.dump(CATALOG, stream)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(run_report.main([str(root / "run.jsonl.gz")]), 0)
        self.assertIn("| 2 | `b` | 40 | 30 | 30 | 64.4 |", out.getvalue())


if __name__ == "__main__":
    unittest.main()
