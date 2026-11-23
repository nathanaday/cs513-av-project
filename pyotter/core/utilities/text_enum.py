from __future__ import annotations

from enum import Enum


class TextEnum(str, Enum):
    """An enum whose members are their text values.

    A member equals its value, prints as its value, and is written to JSON as
    its value, on every supported Python version.
    """

    def __str__(self) -> str:
        return self.value
