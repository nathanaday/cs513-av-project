"""Read and write pyotter's JSON files. A path ending in `.gz` is compressed.

The same data always gives the same bytes: keys are sorted and the compressed
form carries no timestamp or file name. A file's fingerprint is the SHA-256 of
those bytes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


def write_json(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, sort_keys=True).encode("utf-8")
    if path.suffix == ".gz":
        text = gzip.compress(text, mtime=0)
    path.write_bytes(text)


def read_json(path: str | Path) -> dict:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def file_fingerprint(path: str | Path) -> str:
    """The SHA-256 of a file's bytes, as 64 hexadecimal characters."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
