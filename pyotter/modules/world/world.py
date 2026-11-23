from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ...core.models.world_road_graph import RoadSegment, WorldRoadGraph

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class World:
    @staticmethod
    def view_topology(graph: WorldRoadGraph, *, label_segments: bool = False) -> Figure:
        """Draw the graph from above, in meters. Call `.savefig(path)` or `pyplot.show()` on the result.

        With `label_segments`, the figure is larger and each lane carries its segment id.
        """
        try:
            from matplotlib import pyplot
        except ImportError:
            raise ImportError("view_topology needs matplotlib: pip install 'pyotter[view]'") from None

        size, dpi = (24, 200) if label_segments else (10, 100)
        figure, axes = pyplot.subplots(figsize=(size, size), dpi=dpi)
        placed: list[tuple[float, float]] = []
        for segment in graph.get_segments():
            line = segment.centerline
            color = "tab:orange" if segment.in_junction else "tab:blue"
            axes.plot([p.x for p in line], [p.y for p in line], color=color, linewidth=1.2)
            middle, after = line[(len(line) - 1) // 2], line[(len(line) - 1) // 2 + 1]
            axes.annotate("", xy=(after.x, after.y), xytext=(middle.x, middle.y),
                          arrowprops={"arrowstyle": "->", "color": color, "linewidth": 1.2})
            if label_segments:
                x, y, angle = _label_anchor(segment, placed)
                axes.text(x, y, segment.id, fontsize=5.5, color=color, ha="center", va="center",
                          rotation=angle, rotation_mode="anchor",
                          bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.4, "alpha": 0.85})
        axes.plot([], [], color="tab:blue", label="road lane")
        axes.plot([], [], color="tab:orange", label="junction lane")
        axes.legend(loc="upper right")
        axes.set_aspect("equal")
        axes.invert_yaxis()  # CARLA's frame is left-handed: +y is to the right of +x
        axes.set_xlabel("x (m)")
        axes.set_ylabel("y (m)")
        axes.set_title(f"{graph.map_name}: {len(graph.segments)} segments")
        axes.grid(True, linewidth=0.3)
        return figure


LABEL_FRACTIONS = (0.3, 0.7, 0.15, 0.85, 0.5, 0.4, 0.6)


def _label_anchor(segment: RoadSegment, placed: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Pick the point along the lane farthest from the labels already placed, and the lane's screen angle there."""
    best = None
    for fraction in LABEL_FRACTIONS:
        offset = fraction * segment.length_m
        x, y, _ = segment.point_at(offset)
        clearance = min((math.hypot(x - px, y - py) for px, py in placed), default=math.inf)
        if best is None or clearance > best[0]:
            best = (clearance, x, y, offset)
        if clearance >= 6.0:
            break
    _, x, y, offset = best
    placed.append((x, y))
    ahead = segment.point_at(min(offset + 1.0, segment.length_m))
    behind = segment.point_at(max(offset - 1.0, 0.0))
    angle = math.degrees(math.atan2(-(ahead[1] - behind[1]), ahead[0] - behind[0]))  # y axis is inverted
    if not -90.0 < angle <= 90.0:
        angle += 180.0
    return x, y, angle
