# pyotter


## OTTER

**Optimizing Travel Through Environmental Risk**

A python library for risk-aware navigation in CARLA

## Architecture

### Global / Base Class

Global entities:
- world hazard library (WHL)- specifies all hazards supported in OTTER
- world road graph (WRG) - a list of road segments in the provided CARLA map
- driving safety requirements (DSR) - the driving safety requirement spec (stopping distance, aceeleration)


### World module

The world module handles risk modelling and world generation.

World module entities:
- world hazard spawns (WHS) - the hazards that occur in one run, rolled from the probabilities and a seed

The forecast is stored on the WRG, not in a separate entity. Event probabilities are per segment. Condition forecasts (chance, severity, variability) and the time of day are per world.


### Planning module

The planning module creates a risk-optimized waypoint route given the enviornmental probability model.

Planning module entities:
- Planner computed waypoints (PCW) - a list of navigation segments and their target speeds


### Driving module

The driving module runs ego actors in CARLA based on the provided entities and configurations

Driving module entities:
- Driving scenario telemetry (DST) - the telemetry (speed, acceleration, bounds) of a scenario run
- Driving safety evaluation (DSE) - evaluated score based on the safety critera 


## Concepts

### Hazards

- Events are modeled per segment using a probability vs. time distribution (e.g. probability of a pedestrian spawning on that segment at that second)
- Conditions are modeled at the world level: one forecast per condition (chance, severity, how much severity can vary), and applies to the whole run
- Sun is a time-of-day setting whose glare is computed per lane from the lane's heading, and scaled down by rain/fog.


## Guidelines

### Modules

Each module should follow a template:
- models - contains all schema, entities
- api - contians runnable entrypoints for module usage
- tests - contains module-specific tests
- docs - contains module-specific usage
- utilities.py - for internal module utilities (private to the module, no export)
- {classname}.py - include a dedicated python file per class

### Core

- For public utilies used in all classes, define and export them in `core/utilities/`
- For public schema, models, include them in `core/models/`

### Configuration

`config.yaml` holds the library version, the schema version of every file pyotter writes, and every tunable value. Read it by attribute:

```python
from pyotter.core.utilities.config import CONFIG

CONFIG.safety.min_gap_m
CONFIG.driver.controller.speed_gain
```

- A model's default comes from the config (`min_gap_m: float = CONFIG.safety.min_gap_m`), so a value is tuned in one place
- A scenario file stores the driver and planner values it was made with, so a saved run does not change when the config does
- Names with a fixed set of values are enums built on `TextEnum` (`core/utilities/text_enum.py`), which read and write as plain text

### Code Style

- Use google style python docstrings
- Do not declare tunable parameters as globals in the same file; use the yaml config
- Keep classes short, reable, and favor clarity over compacted synatx
