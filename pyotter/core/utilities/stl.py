"""Signal temporal logic over a sampled trace, with robustness.

A formula's robustness at a sample is positive when the formula holds there
and negative when it does not. Its size is how far the trace is from the
other verdict, in the signal's own units.

    spec = always(signal("gap_m") >= 2.0)
    spec.robustness(trace)[0]      # the verdict for the whole trace

A trace maps signal names to equal-length lists, with sample times under
"time_s". Temporal bounds are in seconds and are measured from each sample.
"""

from __future__ import annotations

import math
from typing import Callable, Mapping, Sequence

Trace = Mapping[str, Sequence[float]]
TIME = "time_s"
TIME_TOLERANCE_S = 1e-9


class Formula:
    """A statement about a trace. Combine formulas with `&`, `|`, `~` and `implies`."""

    def robustness(self, trace: Trace) -> list[float]:
        """The robustness of the formula at each sample of the trace."""
        raise NotImplementedError

    def __and__(self, other: Formula) -> Formula:
        return _Combine("and", min, self, other)

    def __or__(self, other: Formula) -> Formula:
        return _Combine("or", max, self, other)

    def __invert__(self) -> Formula:
        return _Not(self)

    def implies(self, other: Formula) -> Formula:
        return _Combine("->", max, ~self, other, shown=(self, other))


class _Value:
    """A signal, or a signal shifted or negated, awaiting a comparison.

    Attributes:
        text: How the value is written in a formula.
        values: Reads the value's samples from a trace.
    """

    def __init__(self, text: str, values: Callable[[Trace], Sequence[float]]):
        self.text = text
        self.values = values

    def __ge__(self, bound: _Value | float) -> Formula:
        return _Predicate(self, ">=", bound)

    def __le__(self, bound: _Value | float) -> Formula:
        return _Predicate(self, "<=", bound)

    def __add__(self, amount: float) -> _Value:
        def shifted(trace: Trace) -> list[float]:
            return [value + amount for value in self.values(trace)]

        return _Value(f"({self.text} + {amount:g})", shifted)

    def __neg__(self) -> _Value:
        def negated(trace: Trace) -> list[float]:
            return [-value for value in self.values(trace)]

        return _Value(f"-{self.text}", negated)


def signal(name: str) -> _Value:
    """A named signal of the trace, to compare with `>=` or `<=`.

    Reading it raises `KeyError` if the trace has no signal of that name.
    """
    def values(trace: Trace) -> Sequence[float]:
        if name not in trace:
            raise KeyError(f"the trace has no signal named {name}")
        return trace[name]

    return _Value(name, values)


def _constant(amount: float) -> _Value:
    def values(trace: Trace) -> list[float]:
        return [amount] * len(trace[TIME])

    return _Value(f"{amount:g}", values)


class _Predicate(Formula):
    def __init__(self, left: _Value, comparison: str, right: _Value | float):
        self.left = left
        self.comparison = comparison
        self.right = right if isinstance(right, _Value) else _constant(right)

    def robustness(self, trace: Trace) -> list[float]:
        sign = 1.0 if self.comparison == ">=" else -1.0
        pairs = zip(self.left.values(trace), self.right.values(trace))
        return [sign * (left - right) for left, right in pairs]

    def __str__(self) -> str:
        return f"{self.left.text} {self.comparison} {self.right.text}"


class _Not(Formula):
    def __init__(self, inner: Formula):
        self.inner = inner

    def robustness(self, trace: Trace) -> list[float]:
        return [-value for value in self.inner.robustness(trace)]

    def __str__(self) -> str:
        return f"not ({self.inner})"


class _Combine(Formula):
    """Two formulas joined by `and` (the lesser robustness) or `or` (the greater)."""

    def __init__(self, word: str, choose: Callable, left: Formula, right: Formula,
                 shown: tuple[Formula, Formula] | None = None):
        self.word = word
        self.choose = choose
        self.left = left
        self.right = right
        self.shown = shown or (left, right)

    def robustness(self, trace: Trace) -> list[float]:
        pairs = zip(self.left.robustness(trace), self.right.robustness(trace))
        return [self.choose(left, right) for left, right in pairs]

    def __str__(self) -> str:
        return f"({self.shown[0]}) {self.word} ({self.shown[1]})"


class _Temporal(Formula):
    """`always` (the least robustness in a time window) or `eventually` (the greatest).

    Attributes:
        empty: The robustness when the window holds no sample.
    """

    def __init__(self, word: str, choose: Callable, empty: float, inner: Formula, start_s: float, end_s: float):
        if start_s < 0 or end_s < start_s:
            raise ValueError("a time bound must start at 0 or later and end no earlier than it starts")
        self.word = word
        self.choose = choose
        self.empty = empty
        self.inner = inner
        self.start_s = start_s
        self.end_s = end_s

    @property
    def unbounded(self) -> bool:
        return self.start_s == 0 and math.isinf(self.end_s)

    def robustness(self, trace: Trace) -> list[float]:
        inner = self.inner.robustness(trace)
        if self.unbounded:
            return self._over_the_rest(inner)
        return self._over_windows(inner, trace[TIME])

    def _over_the_rest(self, inner: list[float]) -> list[float]:
        """At each sample, the choice over that sample and every later one."""
        result = [0.0] * len(inner)
        running = self.empty
        for index in reversed(range(len(inner))):
            running = self.choose(running, inner[index])
            result[index] = running
        return result

    def _over_windows(self, inner: list[float], times: Sequence[float]) -> list[float]:
        """At each sample, the choice over the samples from `start_s` to `end_s` after it."""
        result = []
        first = 0
        last = 0
        for index, now in enumerate(times):
            first = max(first, index)
            while first < len(times) and times[first] < now + self.start_s - TIME_TOLERANCE_S:
                first += 1
            last = max(last, first)
            while last < len(times) and times[last] <= now + self.end_s + TIME_TOLERANCE_S:
                last += 1
            window = inner[first:last]
            result.append(self.choose(window) if window else self.empty)
        return result

    def __str__(self) -> str:
        bounds = "" if self.unbounded else f"[{self.start_s:g},{self.end_s:g}]"
        return f"{self.word}{bounds} ({self.inner})"


def always(inner: Formula, start_s: float = 0.0, end_s: float = math.inf) -> Formula:
    """The formula holds at every sample from `start_s` to `end_s` seconds after each sample."""
    return _Temporal("always", min, math.inf, inner, start_s, end_s)


def eventually(inner: Formula, start_s: float = 0.0, end_s: float = math.inf) -> Formula:
    """The formula holds at some sample from `start_s` to `end_s` seconds after each sample."""
    return _Temporal("eventually", max, -math.inf, inner, start_s, end_s)
