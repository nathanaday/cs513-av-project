"""Check a CARLA run file against the upload contract and publish it as a capture.

The dataset, its layout, and the contract are described in docs/publishing.md.
Without --upload nothing leaves this machine.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

import rerun as rr
from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

import carla_replay

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT_DOC = os.path.join(HERE, "..", "docs", "run-format.md")
STAGING = os.path.join(HERE, "..", ".carla", "publish")
DEFAULT_REPO = "nadayusc/carla-rerun-scenarios"
LICENSE = "CC-BY-4.0"
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ID_MAX = 64
TITLE_MAX = 80
DESCRIPTION_MIN = 40
CATALOG_FIELDS = ("id", "title", "scenario", "map", "sim_seconds", "actors", "events",
                  "rerun_version", "viewer_url", "contributor", "published_utc")
# A folder path names the contributor's machine and often their user name.
FOLDER_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/|~|\\\\)|[\\/](?:Users|home)[\\/]")


class ContractError(Exception):
    pass


def check_contract(records, args, catalog):
    """Return the broken rules of the upload contract, as messages."""
    problems = []
    header = records[0]
    ticks = sum(1 for r in records if r["type"] == "tick")
    if records[-1]["type"] != "end":
        problems.append("the run has no end record: it was cut off; record it again")
    if ticks == 0:
        problems.append("the run has no ticks")
    for value in _strings(header):
        if FOLDER_PATH.search(value):
            problems.append(f"the header holds a folder path, {value!r}; record the run again "
                            "with the current runlog, which keeps only the script's file name")
    if not ID_PATTERN.match(args.id) or len(args.id) > ID_MAX:
        problems.append(f"the id {args.id!r} must be lowercase words joined by hyphens, "
                        f"at most {ID_MAX} characters, such as town10-bus-collision")
    if not args.title.strip() or len(args.title) > TITLE_MAX or "\n" in args.title:
        problems.append(f"the title must be one line of 1 to {TITLE_MAX} characters")
    if len(args.description.strip()) < DESCRIPTION_MIN:
        problems.append(f"the description must say what happens in the run, in at least "
                        f"{DESCRIPTION_MIN} characters")
    if any(entry["id"] == args.id for entry in catalog) and not args.replace:
        problems.append(f"the capture {args.id!r} exists in the dataset; add --replace to replace it")
    return problems


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def summarize(records):
    header, end = records[0], records[-1]
    ticks = [r for r in records if r["type"] == "tick"]
    actors = [r for r in records if r["type"] == "actor"]
    kinds = Counter()
    for actor in actors:
        type_id = actor["type_id"]
        if actor["id"] == header.get("ego_id"):
            kinds["ego"] += 1
        elif type_id.startswith("vehicle."):
            kinds["vehicles"] += 1
        elif type_id.startswith("walker."):
            kinds["walkers"] += 1
        elif type_id == "traffic.traffic_light":
            kinds["traffic_lights"] += 1
        else:
            kinds["traffic_signs"] += 1
    events = Counter(r["kind"] for r in records if r["type"] == "event")
    return {
        "scenario": header.get("scenario"),
        "settings": header.get("settings"),
        "weather": header.get("weather"),
        "map": header["map"],
        "carla_version": header["server_version"],
        "run_format_version": header["version"],
        "ticks": len(ticks),
        "delta_s": header["delta_s"],
        "sim_seconds": round(ticks[-1]["t"], 2) if ticks else 0.0,
        "actors": {k: kinds.get(k, 0) for k in ("ego", "vehicles", "walkers", "traffic_lights", "traffic_signs")},
        "events": {k: events.get(k, 0) for k in ("collision", "lane_invasion")},
        "end_reason": end.get("reason", ""),
        "recorded_utc": header["started_utc"],
        "recorder_argv": header["argv"],
    }


def viewer_url(repo, capture_id, rerun_version):
    rrd = f"https://huggingface.co/datasets/{repo}/resolve/main/captures/{capture_id}/run.rrd"
    return f"https://app.rerun.io/version/{rerun_version}/?url={rrd}"


def file_info(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return {"bytes": os.path.getsize(path), "sha256": digest.hexdigest()}


def read_catalog(api, repo):
    """The dataset's catalog entries, or [] when the dataset or the catalog does not exist yet."""
    if not api.repo_exists(repo, repo_type="dataset") or \
            not api.file_exists(repo, "catalog.jsonl", repo_type="dataset"):
        return []
    path = hf_hub_download(repo, "catalog.jsonl", repo_type="dataset", force_download=True)
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dataset_card(repo, catalog):
    rows = "\n".join(
        f"| [{e['title']}](captures/{e['id']}/capture.json) | `{e['id']}` | {e.get('scenario') or '-'} | {e['map']} | "
        f"{e['sim_seconds']:.0f} s | {e['actors']['vehicles']} / {e['actors']['walkers']} | "
        f"[open in Rerun]({e['viewer_url']}) |"
        for e in sorted(catalog, key=lambda e: e["id"]))
    return f"""---
license: cc-by-4.0
pretty_name: CARLA scenario captures for Rerun
tags:
  - carla
  - rerun
  - autonomous-driving
  - simulation
---

# CARLA scenario captures for Rerun

Recorded scenarios from the [CARLA](https://carla.org) driving simulator, ready to open in the [Rerun](https://rerun.io) viewer. Each capture is one drive: the static scene (roads, junctions, crosswalks, buildings, parked vehicles), the ego vehicle, background traffic and pedestrians, traffic light states, and the ego's collisions and lane crossings, on every simulation tick.

Use them to look at CARLA data without running CARLA, to see how a scenario plays out, or as sample data for your own tools.

## Open a capture

Click **open in Rerun** in the table. The capture opens in the Rerun web viewer, in your browser, with nothing to install. Press play in the time panel, or drag the time cursor. To use the native viewer: `pip install rerun-sdk`, download a capture's `run.rrd`, and run `rerun run.rrd`.

## Captures

| Capture | Id | Scenario | Map | Length | Vehicles / walkers | |
|---|---|---|---|---|---|---|
{rows}

The viewer shows where everything is, not the weather or the light. Each capture's `capture.json` holds the scenario that recorded it, the scenario's settings (such as the seed or the tire friction), and the weather at the start of the run.

## Layout

```
catalog.jsonl            one line per capture
FORMAT.md                the run file format
captures/<id>/
    run.jsonl.gz         the run file: every tick, in CARLA coordinates
    run.rrd              the same run for Rerun, built with the version in capture.json
    capture.json         title, description, scenario, settings, weather, map, versions,
                         counts, file hashes, viewer link
```

`run.jsonl.gz` is gzip-compressed JSON lines, described in [FORMAT.md](FORMAT.md). Read it with any language to use the data outside Rerun.

## License and credit

The captures are under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). They show CARLA maps and assets, which CARLA publishes under CC BY. The captures come from the CSCI 513 group project at the University of Southern California.
"""


def build(args, records, catalog, contributor, rerun_version):
    capture_dir = os.path.join(STAGING, args.id)
    shutil.rmtree(capture_dir, ignore_errors=True)
    files = os.path.join(capture_dir, "captures", args.id)
    os.makedirs(files)
    run_copy = os.path.join(files, "run.jsonl.gz")
    shutil.copyfile(args.run, run_copy)
    rrd = os.path.join(files, "run.rrd")
    subprocess.run([sys.executable, os.path.join(HERE, "carla_replay.py"), run_copy, "--rrd", rrd,
                    "--recording-id", args.id], check=True, stdout=subprocess.DEVNULL)

    url = viewer_url(args.repo, args.id, rerun_version)
    capture = {
        "id": args.id, "title": args.title.strip(), "description": args.description.strip(),
        **summarize(records),
        "rerun_version": rerun_version, "viewer_url": url, "license": LICENSE,
        "contributor": contributor,
        "published_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "files": {"run.jsonl.gz": file_info(run_copy), "run.rrd": file_info(rrd)},
    }
    with open(os.path.join(files, "capture.json"), "w", encoding="utf-8") as f:
        json.dump(capture, f, indent=2)
        f.write("\n")

    entry = {k: capture[k] for k in CATALOG_FIELDS}
    catalog = [{k: e.get(k) for k in CATALOG_FIELDS} for e in catalog if e["id"] != args.id] + [entry]
    with open(os.path.join(capture_dir, "catalog.jsonl"), "w", encoding="utf-8") as f:
        for e in sorted(catalog, key=lambda e: e["id"]):
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    with open(os.path.join(capture_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(dataset_card(args.repo, catalog))
    shutil.copyfile(FORMAT_DOC, os.path.join(capture_dir, "FORMAT.md"))
    return capture_dir, entry


def staged_files(capture_dir):
    for folder, _, names in os.walk(capture_dir):
        for name in sorted(names):
            path = os.path.join(folder, name)
            yield os.path.relpath(path, capture_dir).replace(os.sep, "/"), path


def login(api):
    """The user name of the stored Hugging Face login, or None."""
    try:
        return api.whoami()["name"]
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="run file (*.jsonl.gz)")
    parser.add_argument("--id", required=True, help="capture id: lowercase words joined by hyphens")
    parser.add_argument("--title", required=True, help="one-line title")
    parser.add_argument("--description", required=True, help="what happens in the run")
    parser.add_argument("--contributor", help="name shown on the capture (default: your Hugging Face user)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"dataset (default: {DEFAULT_REPO})")
    parser.add_argument("--replace", action="store_true", help="replace a capture with the same id")
    parser.add_argument("--upload", action="store_true", help="upload; without it nothing leaves this machine")
    args = parser.parse_args()

    try:
        records = carla_replay.read_run(args.run)
    except carla_replay.RunFileError as error:
        print(f"carla-publish: {error}", file=sys.stderr)
        return 2

    api = HfApi()
    user = login(api)
    if args.upload and user is None:
        print("carla-publish: no Hugging Face login. Create a token with Write permission at "
              "https://huggingface.co/settings/tokens, run 'hf auth login', then run this again.",
              file=sys.stderr)
        return 2
    try:
        catalog = read_catalog(api, args.repo)
    except HfHubHTTPError as error:
        print(f"carla-publish: cannot read the catalog of {args.repo}: {error}", file=sys.stderr)
        return 1

    problems = check_contract(records, args, catalog)
    if problems:
        print("carla-publish: the run does not meet the upload contract (docs/publishing.md):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    contributor = args.contributor or user or "unknown"
    capture_dir, entry = build(args, records, catalog, contributor, rr.__version__)

    print(f"capture {args.id} for {args.repo}, staged in {os.path.relpath(capture_dir)}:")
    for name, path in staged_files(capture_dir):
        print(f"  {os.path.getsize(path):>10,} B  {name}")
    print("catalog entry:")
    print("  " + json.dumps(entry, separators=(", ", ": ")))
    print(f"viewer link: {entry['viewer_url']}")

    if not args.upload:
        print("dry run: nothing uploaded. Check the files, then run again with --upload.")
        return 0

    operations = [CommitOperationAdd(path_in_repo=name, path_or_fileobj=path)
                  for name, path in staged_files(capture_dir)]
    verb = "Replace" if any(e["id"] == args.id for e in catalog) else "Add"
    try:
        commit = api.create_commit(args.repo, operations, repo_type="dataset",
                                   commit_message=f"{verb} capture {args.id}",
                                   commit_description=f"{args.title.strip()}\n\nContributor: {contributor}")
    except RepositoryNotFoundError:
        print(f"carla-publish: the dataset {args.repo} does not exist or your login cannot see it. "
              f"Create it with: hf repos create {args.repo} --repo-type dataset --public",
              file=sys.stderr)
        return 1
    except HfHubHTTPError as error:
        if error.response is not None and error.response.status_code in (401, 403):
            print(f"carla-publish: your login ({user}) cannot write to {args.repo}. Use a token with "
                  "Write permission (https://huggingface.co/settings/tokens) and run 'hf auth login'.",
                  file=sys.stderr)
            return 1
        raise
    print(f"uploaded: {commit.commit_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
