"""Risk API v0 (World team).

Serves the odds of each hazard on each directed road segment to the Planner.

Every p_* value is the probability, per second, that one incident of that hazard
starts while the car is on the segment. Convert with r = -ln(1 - p):
    expected incidents over T seconds = r * T
    P(at least one incident)          = 1 - (1 - p) ** T

Reads only the two CSV files. It never touches CARLA, rolls or scenario state
(Wall 1), and it has no dependencies beyond the standard library.

Files
    hazards.csv   registry: one row per hazard (name, penalty_mode, tier, enabled, ...)
    risk_*.csv    odds: segment_id, start_node, end_node, p_* columns,
                  and optionally t_from_s, t_to_s for time-varying odds
"""
import csv
import math
import sys
import warnings
from collections import defaultdict

WARN_ABOVE = 0.05   # per second; above this a 12 s pass almost always triggers
REQUIRED = ("segment_id",)   # start_node / end_node are optional labels


def _rate(p):
    """Rate r = -ln(1 - p), per second."""
    return math.inf if p >= 1.0 else -math.log1p(-p)


class RiskAPI:
    def __init__(self, odds_csv, hazards_csv):
        self.registry = self._read_registry(hazards_csv)
        self.hazards = list(self.registry)
        self._nodes = {}
        self._windows = {}   # segment_id -> [(t_from, t_to, {hazard: p})]
        self._read_odds(odds_csv)

    # ------------------------------------------------------------ loading
    @staticmethod
    def _read_registry(path):
        reg = {}
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                reg[row["hazard"].strip()] = {
                    "penalty_mode": row["penalty_mode"].strip(),
                    "tier": int(row["tier"]),
                    "enabled": row["enabled"].strip() == "1",
                }
        if not reg:
            raise ValueError(f"{path}: no hazards listed")
        return reg

    def _read_odds(self, path):
        windows = defaultdict(list)
        ignored = set()
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            missing = [c for c in REQUIRED if c not in cols]
            if missing:
                raise ValueError(f"{path}: missing columns {missing}")
            p_cols = [c for c in cols if c.startswith("p_")]
            unknown = [c for c in p_cols if c not in self.registry]
            if unknown:
                raise ValueError(f"{path}: hazards not in registry: {unknown}")
            absent = [h for h, m in self.registry.items()
                      if m["enabled"] and h not in p_cols]
            if absent:
                raise ValueError(f"{path}: enabled hazards missing: {absent}")
            has_t0, has_t1 = "t_from_s" in cols, "t_to_s" in cols
            if has_t0 != has_t1:
                raise ValueError(f"{path}: give both t_from_s and t_to_s, or neither")

            for n, row in enumerate(reader, start=2):
                where = f"{path} line {n}"
                seg = row["segment_id"].strip()
                nodes = ((row.get("start_node") or "").strip(),
                         (row.get("end_node") or "").strip())
                if self._nodes.setdefault(seg, nodes) != nodes:
                    raise ValueError(f"{where}: {seg} has two different node pairs")
                t0 = float(row["t_from_s"]) if has_t0 else 0.0
                t1 = math.inf
                if has_t1 and row["t_to_s"].strip() != "":
                    t1 = float(row["t_to_s"])
                probs = {}
                for h in self.hazards:
                    if h not in p_cols:          # disabled hazard left out: zero
                        probs[h] = 0.0
                        continue
                    try:
                        p = float(row[h])
                    except (TypeError, ValueError):
                        raise ValueError(f"{where}: {h} is not a number") from None
                    if not 0.0 <= p <= 1.0:
                        raise ValueError(f"{where}: {h}={p} is outside [0, 1]")
                    if p > WARN_ABOVE:
                        warnings.warn(f"{where}: {h}={p} per second is very high")
                    if p > 0.0 and not self.registry[h]["enabled"]:
                        ignored.add(h)           # not made real in CARLA: count as 0
                        p = 0.0
                    probs[h] = p
                windows[seg].append((t0, t1, probs))

        if not windows:
            raise ValueError(f"{path}: no rows")
        self.ignored_disabled = sorted(ignored)
        if ignored:
            warnings.warn(f"{path}: disabled hazards with nonzero odds were set to 0: "
                          f"{self.ignored_disabled}")
        for seg, wins in windows.items():
            wins.sort(key=lambda w: w[0])
            for a, b in zip(wins, wins[1:]):
                if a[1] > b[0]:
                    raise ValueError(f"{path}: {seg} has overlapping time windows")
        self._windows = dict(windows)

    # ------------------------------------------------------------ queries
    @property
    def segment_ids(self):
        return list(self._windows)

    def edges(self):
        """(segment_id, start_node, end_node) for every directed segment.
        Node labels are empty strings if the file has no node columns."""
        return [(s, *self._nodes[s]) for s in self._windows]

    def get(self, segment_id, t=0.0):
        """Per-second probability of each hazard on a segment at time t.

        Outside the published time windows, the nearest window is used."""
        wins = self._windows.get(segment_id)
        if wins is None:
            raise KeyError(f"unknown segment_id {segment_id!r}")
        for t0, t1, probs in wins:
            if t0 <= t < t1:
                return dict(probs)
        return dict(wins[0][2] if t < wins[0][0] else wins[-1][2])

    def get_all(self, t=0.0):
        """Whole graph in one call, for Dijkstra or A*."""
        return {s: self.get(s, t) for s in self._windows}

    def rates(self, segment_id, t=0.0):
        """Rate r = -ln(1 - p) per second, per hazard."""
        return {h: _rate(p) for h, p in self.get(segment_id, t).items()}

    def expected_events(self, segment_id, seconds, t=0.0):
        """Expected incidents of each hazard if the car spends `seconds` there."""
        return {h: r * seconds for h, r in self.rates(segment_id, t).items()}

    def prob_any(self, segment_id, seconds, t=0.0):
        """P(at least one incident of any hazard) over `seconds` on the segment."""
        return 1.0 - math.exp(-sum(self.rates(segment_id, t).values()) * seconds)

    def rate_by_mode(self, segment_id, t=0.0):
        """Summed rate per penalty_mode, so the Planner can price each mode."""
        out = defaultdict(float)
        for h, r in self.rates(segment_id, t).items():
            out[self.registry[h]["penalty_mode"]] += r
        return dict(out)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python risk_api.py <odds.csv> <hazards.csv>")
    api = RiskAPI(sys.argv[1], sys.argv[2])
    n_on = sum(m["enabled"] for m in api.registry.values())
    print(f"{len(api.segment_ids)} segments, {len(api.hazards)} hazards ({n_on} enabled)")
    for seg, a, b in api.edges():
        label = f" {a}->{b}" if a or b else ""
        print(f"{seg}{label}: P(any incident in 12 s) = {api.prob_any(seg, 12):.1%}")
