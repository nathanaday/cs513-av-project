# Publish a capture

A capture is one recorded CARLA run, published so that anyone can open it in the Rerun web viewer. Captures go to the public Hugging Face dataset [nadayusc/carla-rerun-scenarios](https://huggingface.co/datasets/nadayusc/carla-rerun-scenarios). The dataset is for anyone who wants to see CARLA data in Rerun, not only for this project. So write each title and description for a reader who does not know CS513.

`scripts/carla-publish` checks a run against the upload contract below, builds the capture's files, and uploads them. Run it from the `carla-work` folder.

The first dataset, [nadayusc/cs513-carla-runs](https://huggingface.co/datasets/nadayusc/cs513-carla-runs), holds the original demo run. It stays online so that its link keeps working. Do not add files to it.

## The dataset

```
README.md                the dataset card: purpose, how to open, the capture table
catalog.jsonl            one line per capture
FORMAT.md                a copy of docs/run-format.md
captures/<id>/
    run.jsonl.gz         the run file, byte for byte as the contributor checked it
    run.rrd              the run converted for Rerun
    capture.json         the capture's description, counts, versions, and file hashes
```

The license is CC BY 4.0. CARLA publishes its maps and assets under CC BY, so captures of them carry the same terms.

`catalog.jsonl` is the source of truth. `carla-publish` writes `README.md` from it on every upload, and copies `FORMAT.md` from this repository. Do not edit these three files by hand.

### `capture.json`

| Field | Meaning |
|---|---|
| `id` | The capture's name and folder: lowercase words joined by hyphens, at most 64 characters. |
| `title` | One line, at most 80 characters. |
| `description` | What happens in the run, for a reader who does not know the project. |
| `scenario`, `settings`, `weather` | Copied from the run header (see [run-format.md](run-format.md)): the scenario that recorded the run, its settings (counts, speed, limit, seed, spawn point, and the scenario's own values), and the weather at the start. `null` for a run whose header has no such field. The viewer does not show the weather, so this is where a reader finds it. |
| `map` | CARLA map, for example `Town10HD_Opt`. |
| `carla_version` | Server version from the run header. |
| `run_format_version` | Version of the run file format. |
| `ticks`, `delta_s`, `sim_seconds` | Number of ticks, seconds per tick, and the simulated length. |
| `actors` | Counts: `ego`, `vehicles`, `walkers`, `traffic_lights`, `traffic_signs` (stop, yield, and other `traffic.*` actors). |
| `events` | Counts of the ego's `collision` and `lane_invasion` events. |
| `end_reason` | How the run ended: `arrived`, `stopped`, `interrupted`, or `error`. |
| `recorded_utc` | When the run was recorded. |
| `recorder_argv` | The command line that recorded the run, with the script's file name only. |
| `rerun_version` | The Rerun version that built `run.rrd`. |
| `viewer_url` | The web-viewer link. It pins `rerun_version`, so a later Rerun release cannot break it. |
| `license` | `CC-BY-4.0`. |
| `contributor` | Who published the capture: the Hugging Face user, or `--contributor`. |
| `published_utc` | When the capture was published. |
| `files` | Size in bytes and SHA-256 of `run.jsonl.gz` and `run.rrd`. |

### `catalog.jsonl`

One line per capture, sorted by id, with these fields of `capture.json`: `id`, `title`, `scenario`, `map`, `sim_seconds`, `actors`, `events`, `rerun_version`, `viewer_url`, `contributor`, `published_utc`. A capture published before a field existed has `null` for it.

## The upload contract

A run can be published only when all of these are true. `carla-publish` checks each rule before it builds anything, and names every rule the run breaks.

1. The file is a run file of format version 1 (see [run-format.md](run-format.md)).
2. The run is complete: it has at least one tick and ends with an `end` record. A run cut off by `kill -9` or a crash has no `end` record.
3. The header holds no folder path. Runs recorded before the fix in `runlog.py` (2026-10-04) store the script's full path, which names the user's home folder. Record such a run again.
4. The id is lowercase words joined by hyphens, at most 64 characters, and not in the catalog yet. To replace a capture, add `--replace`.
5. The title is one line of 1 to 80 characters.
6. The description says what happens in the run, in at least 40 characters.
7. You agree to publish the capture under CC BY 4.0.

`carla-publish` copies the run file unchanged. It does not clean or rewrite a run.

## Publish

You need `uv` (see [replay.md](replay.md)) and, to upload, a Hugging Face login with Write permission to the dataset.

1. Record a run with `test_data_capture.py` or your own script (see [replay.md](replay.md)). Open it with `scripts/carla-replay` and check that it shows what you want to share.
2. Do a dry run. It checks the contract and stages the files in `.carla/publish/<id>/`. Nothing leaves your machine:

   ```bash
   scripts/carla-publish runs/demo.jsonl.gz --id town10-bus-collision \
     --title "Town10: the ego hits a bus and waits" \
     --description "The ego drives Town10HD_Opt with BasicAgent at 30 km/h among 30 Traffic Manager vehicles and 30 pedestrians. At 26.5 s it hits a bus that pulls out, stops behind it for almost three minutes, then completes its 395 m route."
   ```

   ```
   capture town10-bus-collision for nadayusc/carla-rerun-scenarios, staged in .carla/publish/town10-bus-collision:
          5,863 B  FORMAT.md
          2,187 B  README.md
            510 B  catalog.jsonl
          1,435 B  captures/town10-bus-collision/capture.json
      3,195,909 B  captures/town10-bus-collision/run.jsonl.gz
      8,972,619 B  captures/town10-bus-collision/run.rrd
   catalog entry:
     {"id": "town10-bus-collision", "title": "Town10: the ego hits a bus and waits", "map": "Town10HD_Opt", ...}
   viewer link: https://app.rerun.io/version/0.38.1/?url=https://huggingface.co/datasets/nadayusc/carla-rerun-scenarios/resolve/main/captures/town10-bus-collision/run.rrd
   dry run: nothing uploaded. Check the files, then run again with --upload.
   ```

3. Read the staged `capture.json` and `README.md`. Open the staged `run.rrd` with `uv run --project replay rerun .carla/publish/<id>/captures/<id>/run.rrd` if you want to see exactly what will be published.
4. Run the same command with `--upload`. The capture folder, the catalog, the card, and `FORMAT.md` go up in one commit, and the command prints the commit's URL.
5. Open the viewer link in a browser.

When a run breaks the contract, the command lists each broken rule and exits with status 2:

```
carla-publish: the run does not meet the upload contract (docs/publishing.md):
  - the id 'Town10_Bus' must be lowercase words joined by hyphens, at most 64 characters, such as town10-bus-collision
  - the description must say what happens in the run, in at least 40 characters
```

Options:

| Option | Effect |
|---|---|
| `--id`, `--title`, `--description` | Required. See the contract. |
| `--contributor NAME` | The name on the capture. Default: your Hugging Face user. |
| `--replace` | Replace the capture that has the same id. |
| `--upload` | Upload. Without it, nothing leaves your machine. |
| `--repo REPO` | Another dataset, for example a test dataset of your own. |

## Log in to Hugging Face

1. Create a token with **Write** permission at https://huggingface.co/settings/tokens.
2. Run `hf auth login` and paste the token. (`hf` comes with `pip install huggingface_hub`, or use `uv run --project replay hf auth login`.)

The dataset belongs to the user `nadayusc`. To publish to it, a teammate needs write access from its owner. Until then, send the run file and the description to the owner, or publish to a dataset of your own with `--repo`.

| Message | Fix |
|---|---|
| `no Hugging Face login` | Log in as above. |
| `your login (...) cannot write to ...` | The token is read-only, or you have no write access to the dataset. |
| `the dataset ... does not exist or your login cannot see it` | Check `--repo`, or create the dataset: `hf repos create <repo> --repo-type dataset --public`. |

## Remove a capture

`carla-publish` does not remove captures. Delete the capture's folder and its line in `catalog.jsonl` on the dataset's Hugging Face page, then publish any capture again with `--replace` to rewrite the card. A removed capture stays in the dataset's git history.
