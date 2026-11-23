"""The two libraries on Hugging Face: scenario files, and the telemetry of their runs.

A scenario is stored as `scenarios/NAME.SHORT.json.gz`, where SHORT is the
first 12 characters of its fingerprint. The runs of a scenario are stored as
`telemetry/NAME.SHORT/RUN-telemetry.json.gz`, each with its evaluation beside
it. The `runs/` folder of the lab mirrors both layouts.
"""

from __future__ import annotations

import re
import shutil
import string
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError, RepositoryNotFoundError

from pyotter import Driver
from pyotter.core.utilities.json_file import file_fingerprint
from pyotter.modules.driver import DrivingScenario, DrivingScenarioTelemetry

from .console import LabError
from .settings import RUNS, SETTINGS

DATASET = "dataset"
SCENARIOS = "scenarios"
TELEMETRY = "telemetry"
SCENARIO_SUFFIX = ".json.gz"
TELEMETRY_SUFFIX = "-telemetry.json.gz"
EVALUATION_SUFFIX = "-evaluation.json"
SHORT = 12
SHORTEST_PREFIX = 4


@dataclass(frozen=True)
class ScenarioEntry:
    """One scenario in the library.

    Attributes:
        short: The first 12 characters of the fingerprint.
        fingerprint: The whole fingerprint when the library reports it, or else empty.
        size: The file's size in bytes.
    """

    name: str
    short: str
    fingerprint: str = ""
    size: int = 0

    @property
    def label(self) -> str:
        """The name with the short fingerprint, which no other scenario shares."""
        return f"{self.name}.{self.short}"

    @property
    def path(self) -> str:
        return f"{SCENARIOS}/{self.label}{SCENARIO_SUFFIX}"

    @property
    def local(self) -> Path:
        return RUNS / self.path


@dataclass(frozen=True)
class RunEntry:
    """The telemetry of one run in the library."""

    scenario: str
    run_id: str
    size: int


@contextmanager
def _hub(repo: str) -> Iterator[None]:
    """Turn a failed Hugging Face request into an error that says what to do."""
    try:
        yield
    except RepositoryNotFoundError as error:
        raise LabError(
            f"The dataset {repo} does not exist, or your login cannot see it.",
            f"Log in with `uv run hf auth login`. To create it: "
            f"`uv run hf repos create {repo} --repo-type dataset`.",
        ) from error
    except HfHubHTTPError as error:
        status = error.response.status_code if error.response is not None else 0
        if status in (401, 403):
            raise LabError(
                f"Your Hugging Face login cannot write to {repo}.",
                "Log in with a token that has write access: `uv run hf auth login`.",
            ) from error
        raise LabError(f"Hugging Face refused the request for {repo}: {error}") from error
    except OSError as error:
        raise LabError(f"Cannot reach Hugging Face ({error}).", "Check the network, then try again.") from error


def clean_name(text: str) -> str:
    """A library name from any text: lowercase letters, digits, dots, hyphens and underscores."""
    name = re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")
    return name or "scenario"


def _is_fingerprint_prefix(text: str) -> bool:
    return len(text) >= SHORTEST_PREFIX and all(character in string.hexdigits for character in text)


class ScenarioLibrary:
    """Every scenario file, each under its fingerprint."""

    def __init__(self, repo: str = SETTINGS.scenarios_repo, api: HfApi | None = None):
        self.repo = repo
        self.api = api or HfApi()

    def entries(self) -> list[ScenarioEntry]:
        """Every scenario, sorted by name."""
        entries = []
        with _hub(self.repo):
            try:
                files = list(self.api.list_repo_tree(self.repo, SCENARIOS, repo_type=DATASET))
            except EntryNotFoundError:
                files = []
        for file in files:
            entry = _scenario_entry(file)
            if entry is not None:
                entries.append(entry)
        return sorted(entries, key=lambda entry: entry.label)

    def resolve(self, reference: str) -> ScenarioEntry:
        """The one scenario a reference means.

        Args:
            reference: A name, a name with its short fingerprint, or at least
                the first four characters of a fingerprint.

        Raises:
            LabError: If no scenario matches, or more than one does.
        """
        matches = [entry for entry in self.entries() if _matches(entry, reference)]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise LabError(
                f"No scenario in {self.repo} matches '{reference}'.",
                "See them all with `uv run otter-scenarios list`.",
            )
        labels = ", ".join(entry.label for entry in matches)
        raise LabError(
            f"'{reference}' matches {len(matches)} scenarios: {labels}.",
            "Use the fingerprint instead of the name.",
        )

    def push(self, path: Path) -> tuple[ScenarioEntry, bool]:
        """Add a scenario file to the library, unless a file with the same bytes is already there.

        Returns:
            The entry, and whether it was added now.

        Raises:
            LabError: If the file is not a valid scenario, or the upload fails.
        """
        try:
            scenario = DrivingScenario.load(path)
        except Exception as error:
            raise LabError(f"{path} is not a scenario file ({error}).") from error
        for entry in self.entries():
            if scenario.fingerprint.startswith(entry.short):
                return entry, False
        name = clean_name(path.name.removesuffix(SCENARIO_SUFFIX))
        entry = ScenarioEntry(name, scenario.fingerprint[:SHORT], scenario.fingerprint, path.stat().st_size)
        with _hub(self.repo):
            self.api.upload_file(
                path_or_fileobj=str(path), path_in_repo=entry.path, repo_id=self.repo, repo_type=DATASET,
                commit_message=f"Add scenario {entry.label}",
            )
        entry.local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, entry.local)
        return entry, True

    def fetch(self, entry: ScenarioEntry) -> Path:
        """The scenario's file in `runs/scenarios/`, downloaded unless it is already there.

        Raises:
            LabError: If the download fails, or the file does not have the entry's fingerprint.
        """
        if not _has_fingerprint(entry.local, entry):
            with _hub(self.repo):
                hf_hub_download(self.repo, entry.path, repo_type=DATASET, local_dir=RUNS)
        if not _has_fingerprint(entry.local, entry):
            raise LabError(f"{entry.path} in {self.repo} does not have the fingerprint in its name.")
        return entry.local


def _scenario_entry(file) -> ScenarioEntry | None:
    """Read an entry from a file of the library, or None for anything else kept there."""
    filename = file.path.split("/")[-1]
    if not filename.endswith(SCENARIO_SUFFIX):
        return None
    name, _, short = filename.removesuffix(SCENARIO_SUFFIX).rpartition(".")
    if not name or len(short) != SHORT:
        return None
    fingerprint = ""
    large_file = getattr(file, "lfs", None)
    if large_file is not None:
        fingerprint = large_file.sha256
    return ScenarioEntry(name, short, fingerprint, getattr(file, "size", 0) or 0)


def _matches(entry: ScenarioEntry, reference: str) -> bool:
    if reference in (entry.name, entry.label):
        return True
    if not _is_fingerprint_prefix(reference):
        return False
    reference = reference.lower()
    if len(reference) > SHORT and entry.fingerprint:
        return entry.fingerprint.startswith(reference)
    return entry.short.startswith(reference[:SHORT])


def _has_fingerprint(path: Path, entry: ScenarioEntry) -> bool:
    if not path.is_file():
        return False
    fingerprint = file_fingerprint(path)
    if entry.fingerprint:
        return fingerprint == entry.fingerprint
    return fingerprint.startswith(entry.short)


class ResultsLibrary:
    """The telemetry and the evaluation of every run."""

    def __init__(self, repo: str = SETTINGS.results_repo, api: HfApi | None = None):
        self.repo = repo
        self.api = api or HfApi()

    @staticmethod
    def telemetry_path(scenario: str, run_id: str) -> Path:
        """Where a run's telemetry is kept locally."""
        return RUNS / TELEMETRY / scenario / f"{run_id}{TELEMETRY_SUFFIX}"

    @staticmethod
    def evaluate(telemetry_file: Path) -> Path:
        """Write a run's evaluation beside its telemetry and return its path."""
        evaluation = Driver.evaluate(DrivingScenarioTelemetry.load(telemetry_file))
        target = telemetry_file.with_name(telemetry_file.name.removesuffix(TELEMETRY_SUFFIX) + EVALUATION_SUFFIX)
        evaluation.save(target)
        return target

    def runs(self, scenario: str = "") -> list[RunEntry]:
        """Every run, or those of the scenarios whose label starts with `scenario`."""
        return [run for run in self._remote() if run.scenario.startswith(scenario)]

    def pending(self) -> list[Path]:
        """Local result files that the library does not have."""
        remote = set()
        with _hub(self.repo):
            try:
                for file in self.api.list_repo_tree(self.repo, TELEMETRY, recursive=True, repo_type=DATASET):
                    remote.add(file.path)
            except EntryNotFoundError:
                pass
        local = sorted((RUNS / TELEMETRY).glob(f"*/*{TELEMETRY_SUFFIX}"))
        local += sorted((RUNS / TELEMETRY).glob(f"*/*{EVALUATION_SUFFIX}"))
        return [path for path in local if path.relative_to(RUNS).as_posix() not in remote]

    def upload(self, files: list[Path], message: str) -> str:
        """Add result files to the library in one commit and return the commit's address.

        Args:
            files: Files under `runs/telemetry/`.

        Raises:
            LabError: If the upload fails. The files stay where they are.
        """
        patterns = [path.relative_to(RUNS).as_posix() for path in files]
        with _hub(self.repo):
            commit = self.api.upload_folder(
                repo_id=self.repo, repo_type=DATASET, folder_path=str(RUNS), allow_patterns=patterns,
                commit_message=message,
            )
        return commit.commit_url

    def pull(self, scenario: str = "") -> Path:
        """Download every run, or those of the scenarios whose label starts with `scenario`."""
        with _hub(self.repo):
            snapshot_download(self.repo, repo_type=DATASET, local_dir=RUNS, allow_patterns=[f"{TELEMETRY}/{scenario}*/*"])
        return RUNS / TELEMETRY

    def _remote(self) -> list[RunEntry]:
        runs = []
        with _hub(self.repo):
            try:
                files = list(self.api.list_repo_tree(self.repo, TELEMETRY, recursive=True, repo_type=DATASET))
            except EntryNotFoundError:
                files = []
        for file in files:
            parts = file.path.split("/")
            if len(parts) == 3 and parts[2].endswith(TELEMETRY_SUFFIX):
                runs.append(RunEntry(parts[1], parts[2].removesuffix(TELEMETRY_SUFFIX), getattr(file, "size", 0) or 0))
        return sorted(runs, key=lambda run: (run.scenario, run.run_id))


def web_address(repo: str) -> str:
    return f"https://huggingface.co/datasets/{repo}"
