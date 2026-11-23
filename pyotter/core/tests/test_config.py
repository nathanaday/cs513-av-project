import re
import subprocess
import sys
import unittest
from pathlib import Path

import pyotter
from pyotter.core import WorldRoadGraph
from pyotter.core.utilities.config import CONFIG, CONFIG_PATH, Config, load_config
from pyotter.modules.driver import DriverModel
from pyotter.modules.planner import PlannerConfig

PYPROJECT = Path(pyotter.__file__).resolve().parents[1] / "pyproject.toml"


class Settings(unittest.TestCase):
    def test_settings_are_read_by_attribute_and_cannot_be_changed(self):
        self.assertEqual(CONFIG.safety.min_gap_m, 2.0)
        self.assertEqual(CONFIG.world.severity_levels, ("low", "mid", "high"))
        self.assertIsInstance(CONFIG.view.hazard_ramps[0], tuple)
        self.assertEqual(dict(CONFIG.planner.hazard_weights.items()), {})
        with self.assertRaises(AttributeError) as raised:
            CONFIG.driver.controller.speed_gian
        self.assertIn("config.driver.controller has no setting named speed_gian", str(raised.exception))

    def test_the_file_loads_to_the_same_settings(self):
        again = load_config(CONFIG_PATH)
        self.assertIsInstance(again.carla, Config)
        self.assertEqual(again.carla.port, CONFIG.carla.port)

    def test_one_schema_version_and_one_library_version_serve_every_model(self):
        self.assertEqual(pyotter.__version__, CONFIG.version)
        self.assertEqual(WorldRoadGraph.from_template("town10").schema_version, CONFIG.schema_version)
        if PYPROJECT.exists():
            declared = re.search(r'^version = "(.+)"$', PYPROJECT.read_text(), re.MULTILINE).group(1)
            self.assertEqual(declared, CONFIG.version)

    def test_model_defaults_come_from_the_settings(self):
        self.assertEqual(DriverModel().detection_range_m, CONFIG.driver.model.detection_range_m)
        self.assertEqual(PlannerConfig().cautious_speed_kmh, CONFIG.planner.cautious_speed_kmh)
        self.assertEqual(PlannerConfig().candidate_speeds_kmh, tuple(float(speed) for speed in range(1, 101)))

    def test_the_command_line_runs_as_a_module(self):
        done = subprocess.run([sys.executable, "-m", "pyotter", "--version"], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, f"pyotter {CONFIG.version}"))


if __name__ == "__main__":
    unittest.main()
