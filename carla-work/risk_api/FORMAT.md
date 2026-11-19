# Risk API format (v0)

The Risk API delivers **the odds of each hazard on each road segment** to the Planner. Nothing else.

## Files

| File | What it holds |
|---|---|
| `hazards.csv` | Registry. One row per hazard: `hazard`, `source`, `penalty_mode`, `occurrence`, `carla_effect`, `tier`, `enabled`. |
| `risk_<scenario_id>.csv` | Odds. One row per directed segment (per time window, if time-varying). |

## Odds columns

| Column | Meaning |
|---|---|
| `segment_id` | The Planner catalog's ID for one directed lane span (e.g. `r296.s0.l-1`). Unique. Every catalog segment needs a row. |
| `start_node`, `end_node` *(optional)* | Labels only. The catalog is authoritative, so never key on nodes. |
| `p_<hazard>` | Probability **per second** that one incident of this hazard starts while the car is on the segment. Decimal, 0 to 1. |
| `t_from_s`, `t_to_s` *(optional, both or neither)* | Time window the row applies to. Blank `t_to_s` means open-ended. Windows must not overlap. |

## Units and maths

- Each `p` is per second, so time spent on a segment counts. Driving slower is never free.
- Rate: `r = -ln(1 - p)`. Expected incidents over `T` seconds = `r * T`.
- P(at least one incident in `T` s) = `1 - (1 - p)^T`.
- Sensible range is **0.001 to 0.05**. At 0.30 per second, a 12 s pass triggers about 98% of the time.
- Hazards are independent columns. A row does not sum to 1.

## Rules

- Every hazard with `enabled = 1` must have a column. Disabled hazards may be left out and read as 0.
- A disabled hazard with nonzero odds is **ignored** (set to 0, with a warning). It is not made real in CARLA, so it must not be priced.
- No blanks: a missing value is an error, not zero.
- A column not in `hazards.csv` is an error.
- Hazards that are the same on every segment (e.g. rain) change how fast to drive, not which route. Route choice only responds to hazards that differ between segments.
- Wall 1: the Risk API holds odds only. Rolls, detection ranges and friction values live in the Scenario API.

## Python

```python
from risk_api import RiskAPI
api = RiskAPI("risk_example.csv", "hazards.csv")
api.get("r1_f_0")                       # {hazard: per-second p}
api.get_all(t=0)                        # whole graph for Dijkstra / A*
api.rates("r1_f_0")                     # {hazard: -ln(1 - p)}
api.rate_by_mode("r1_f_0")              # summed rate per penalty_mode
api.expected_events("r1_f_0", seconds=12)
```
