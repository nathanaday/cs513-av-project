from __future__ import annotations

from ....core.utilities.text_enum import TextEnum


class RouteMode(TextEnum):
    """How a route is chosen.

    Attributes:
        RISK_AWARE: Minimize time plus the risk scale times the predicted penalty.
        NAIVE: Take the quickest route at the speed limits.
        CAUTIOUS: Keep the naive route and cap its speed.
    """

    RISK_AWARE = "risk-aware"
    NAIVE = "naive"
    CAUTIOUS = "cautious"
