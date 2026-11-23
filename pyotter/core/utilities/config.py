"""Reader for `config.yaml`, the one place pyotter's tunable values are declared."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ItemsView

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class Config:
    """One section of the settings, read by attribute.

    A nested section is another `Config` and a list is a tuple, so settings
    cannot be changed after they are loaded.
    """

    def __init__(self, values: dict[str, Any], name: str = "config"):
        self._name = name
        self._values = {key: _freeze(value, f"{name}.{key}") for key, value in values.items()}

    def __getattr__(self, key: str) -> Any:
        if key.startswith("_"):
            raise AttributeError(key)
        if key not in self._values:
            raise AttributeError(f"{self._name} has no setting named {key}")
        return self._values[key]

    def items(self) -> ItemsView[str, Any]:
        return self._values.items()


def _freeze(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return Config(value, name)
    if isinstance(value, list):
        return tuple(_freeze(item, name) for item in value)
    return value


def load_config(path: Path = CONFIG_PATH) -> Config:
    with open(path, encoding="utf-8") as stream:
        return Config(yaml.safe_load(stream))


CONFIG = load_config()
