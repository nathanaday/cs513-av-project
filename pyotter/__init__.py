from .core.utilities.config import CONFIG
from .modules.driver.driver import Driver
from .modules.planner.planner import Planner
from .modules.world.world import World

__version__ = CONFIG.version

__all__ = ["CONFIG", "Driver", "Planner", "World", "__version__"]
