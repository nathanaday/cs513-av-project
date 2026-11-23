import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pyotter import Driver, Planner, World
from pyotter.core import WorldHazardLibrary, WorldRoadGraph
from pyotter.modules.driver import DrivingScenario

from otterlab import container, drive, library, server, slurm
from otterlab.console import LabError
from otterlab.library import ResultsLibrary, ScenarioEntry, ScenarioLibrary
from otterlab.settings import REPO, SETTINGS


def scenario_file(folder: Path, name: str, seed: int = 5) -> Path:
    hazards, graph = WorldHazardLibrary(), WorldRoadGraph.from_template("town10")
    graph.set_condition(hazards.wet_road, probability=1.0, severity=0.8)
    route = Planner.route(graph.spawn_points[18], graph.spawn_points[127], graph)
    spawns = World.roll_hazards(graph, hazards, seed=seed, duration_s=120)
    path = folder / f"{name}.json.gz"
    Driver.scenario(graph, spawns, route, name=name).save(path)
    return path


class FakeHub:
    """A dataset held in memory, answering the calls the libraries make."""

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def list_repo_tree(self, repo, path_in_repo=None, recursive=False, repo_type=None):
        return [
            SimpleNamespace(path=path, size=len(data), lfs=None)
            for path, data in sorted(self.files.items()) if path.startswith(f"{path_in_repo}/")
        ]

    def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message):
        self.files[path_in_repo] = Path(path_or_fileobj).read_bytes()

    def upload_folder(self, repo_id, repo_type, folder_path, allow_patterns, commit_message):
        for pattern in allow_patterns:
            self.files[pattern] = (Path(folder_path) / pattern).read_bytes()
        return SimpleNamespace(commit_url=f"https://example.test/{repo_id}/commit/1")


class Lab(unittest.TestCase):
    """Each test gets an empty `runs/` and `.otter/` of its own."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        patches = [
            mock.patch.object(library, "RUNS", self.folder / "runs"),
            mock.patch.object(server, "STATE", self.folder / ".otter"),
            mock.patch.object(server, "POINTER", self.folder / ".otter" / "server.json"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.hub = FakeHub()
        self.scenarios = ScenarioLibrary("team/scenarios", self.hub)


class Scenarios(Lab):
    def test_a_pushed_scenario_is_stored_under_its_name_and_fingerprint(self):
        path = scenario_file(self.folder, "Town10 Naive")
        entry, added = self.scenarios.push(path)
        fingerprint = DrivingScenario.load(path).fingerprint
        self.assertTrue(added)
        self.assertEqual((entry.name, entry.short), ("town10-naive", fingerprint[:12]))
        self.assertEqual(list(self.hub.files), [f"{library.PARTITION}/scenarios/town10-naive.{fingerprint[:12]}.json.gz"])
        self.assertEqual(self.scenarios.entries(), [ScenarioEntry("town10-naive", fingerprint[:12], "", path.stat().st_size)])

    def test_the_same_bytes_are_stored_once_whatever_the_file_is_called(self):
        first = scenario_file(self.folder, "first")
        second = self.folder / "second.json.gz"
        second.write_bytes(first.read_bytes())
        self.scenarios.push(first)
        entry, added = self.scenarios.push(second)
        self.assertFalse(added)
        self.assertEqual(entry.name, "first")
        self.assertEqual(len(self.hub.files), 1)

    def test_a_scenario_is_found_by_name_label_or_fingerprint_prefix(self):
        entry, _ = self.scenarios.push(scenario_file(self.folder, "town10-naive"))
        for reference in ("town10-naive", entry.label, entry.short, entry.short[:4], entry.short.upper()):
            self.assertEqual(self.scenarios.resolve(reference).label, entry.label)
        with self.assertRaises(LabError):
            self.scenarios.resolve("town10")
        with self.assertRaises(LabError):
            self.scenarios.resolve(entry.short[:3])

    def test_a_name_shared_by_two_scenarios_must_be_told_apart_by_fingerprint(self):
        (self.folder / "a").mkdir()
        (self.folder / "b").mkdir()
        first, _ = self.scenarios.push(scenario_file(self.folder / "a", "town10", seed=1))
        second, _ = self.scenarios.push(scenario_file(self.folder / "b", "town10", seed=2))
        with self.assertRaises(LabError) as raised:
            self.scenarios.resolve("town10")
        self.assertIn(first.label, str(raised.exception))
        self.assertEqual(self.scenarios.resolve(second.short).label, second.label)

    def test_a_file_that_is_not_a_scenario_is_refused(self):
        path = self.folder / "notes.json.gz"
        path.write_bytes(b"not a scenario")
        with self.assertRaises(LabError):
            self.scenarios.push(path)
        self.assertEqual(self.hub.files, {})

    def test_a_scenario_of_another_schema_version_is_refused(self):
        path = scenario_file(self.folder, "town10-naive")
        with mock.patch.object(library.CONFIG, "schema_version", library.CONFIG.schema_version + 1):
            with self.assertRaises(LabError) as raised:
                self.scenarios.push(path)
        self.assertIn("schema version", str(raised.exception))
        self.assertEqual(self.hub.files, {})

    def test_fetch_uses_the_local_copy_and_refuses_one_with_other_bytes(self):
        entry, _ = self.scenarios.push(scenario_file(self.folder, "town10-naive"))
        self.assertEqual(self.scenarios.fetch(entry), entry.local)
        entry.local.write_bytes(b"changed")
        with mock.patch.object(library, "hf_hub_download") as download:
            with self.assertRaises(LabError):
                self.scenarios.fetch(entry)
        download.assert_called_once()


class Results(Lab):
    def test_only_results_the_library_lacks_are_pending(self):
        results = ResultsLibrary("team/telemetry", self.hub)
        first = results.telemetry_path("town10.abc123abc123", "20261122T000000Z-1")
        second = results.telemetry_path("town10.abc123abc123", "20261122T000000Z-2")
        for path in (first, second):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"telemetry")
        address = results.upload([first], "one")
        self.assertIn("team/telemetry", address)
        self.assertEqual(list(self.hub.files), [f"{library.PARTITION}/telemetry/town10.abc123abc123/{first.name}"])
        self.assertEqual(results.pending(), [second])
        runs = results.runs("town10")
        self.assertEqual([(run.scenario, run.run_id) for run in runs], [("town10.abc123abc123", "20261122T000000Z-1")])
        self.assertEqual(results.runs("other"), [])


class Server(Lab):
    def test_the_job_reports_its_phases_and_slurm_says_whether_it_lives(self):
        self.assertEqual(server.last_job_id(), "")
        server.remember("41")
        self.assertEqual(server.read_status("41"), server.ServerStatus())
        server.write_status("41", server.ServerStatus(server.READY, "a01", 2010))
        waiting = slurm.Job("41", "PENDING", "", "Priority", "0:00", "2:00:00")
        running = slurm.Job("41", "RUNNING", "a01", "None", "0:30", "1:59:30")
        self.assertIn("Priority", server.describe(waiting, server.ServerStatus()))
        self.assertIn("a01:2010", server.describe(running, server.read_status("41")))
        with mock.patch.object(slurm, "find", return_value=running):
            self.assertEqual(server.live_job(), running)
            self.assertEqual(server.wait_until_ready("41").port, 2010)
        with mock.patch.object(slurm, "find", return_value=None):
            self.assertIsNone(server.live_job())
            with self.assertRaises(LabError):
                server.wait_until_ready("41")

    def test_a_failed_server_says_why(self):
        server.write_status("41", server.ServerStatus(server.FAILED, "a01", detail="CARLA exited with status 1."))
        running = slurm.Job("41", "RUNNING", "a01", "None", "0:30", "1:59:30")
        with mock.patch.object(slurm, "find", return_value=running):
            with self.assertRaises(LabError) as raised:
                server.wait_until_ready("41")
        self.assertIn("CARLA exited", str(raised.exception))


class Jobs(unittest.TestCase):
    def test_a_drive_waits_for_the_server_and_for_the_drives_before_it(self):
        done = SimpleNamespace(returncode=0, stdout="77;discovery\n", stderr="")
        with mock.patch.object(slurm.subprocess, "run", return_value=done) as run, \
                mock.patch.object(slurm, "LOGS", Path(tempfile.gettempdir()) / "otter-test-logs"):
            job_id = drive.submit(Path("/x/scenario.json.gz"), "town10.abc123abc123", "41", time="0:10:00")
        command = run.call_args.args[0]
        self.assertEqual(job_id, "77")
        self.assertIn("--dependency=after:41,singleton", command)
        self.assertIn("--job-name=otter-drive-41", command)
        self.assertIn("--time=0:10:00", command)
        self.assertIn(f"--partition={SETTINGS.slurm.drive.partition}", command)
        self.assertEqual(command[-4:], ["drive", "/x/scenario.json.gz", "town10.abc123abc123", "41"])
        self.assertTrue(os.path.isabs(run.call_args.kwargs["env"]["OTTER_PYTHON"]))

    def test_a_refused_job_is_reported_with_slurms_words(self):
        done = SimpleNamespace(returncode=1, stdout="", stderr="sbatch: error: Invalid account\n")
        with mock.patch.object(slurm.subprocess, "run", return_value=done), \
                mock.patch.object(slurm, "LOGS", Path(tempfile.gettempdir()) / "otter-test-logs"):
            with self.assertRaises(LabError) as raised:
                slurm.submit("otter-carla", "server", ["serve"])
        self.assertIn("Invalid account", str(raised.exception))

    def test_commands_run_in_the_image_import_pyotter_from_this_checkout(self):
        image = Path("/images/toolchain.sif")
        client = container.pyotter_command(image, ["wait"])
        self.assertEqual(client[:3], ["apptainer", "exec", "--cleanenv"])
        self.assertIn(f"PYTHONPATH={REPO}", client)
        self.assertNotIn("--nv", client)
        self.assertEqual(client[-5:], [container.PYTHON, "-u", "-m", "pyotter", "wait"])
        game = container.server_command(image, 2010)
        self.assertIn("--nv", game)
        self.assertEqual(game[-1], "-carla-rpc-port=2010")
        with mock.patch.dict(os.environ, {"OTTER_HOME": "/somewhere"}):
            self.assertEqual(container.image_path(), Path("/somewhere/images/carla-toolchain-0.9.16-1.sif"))


if __name__ == "__main__":
    unittest.main()
