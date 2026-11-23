from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.models.world_road_graph import WorldRoadGraph

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class World:
    @staticmethod
    def view_topology(graph: WorldRoadGraph, *, label_segments: bool = False) -> Figure:
        """Draw the graph from above, in meters. Call `.savefig(path)` or `pyplot.show()` on the result."""
        try:
            from matplotlib import pyplot
        except ImportError:
            raise ImportError("view_topology needs matplotlib: pip install 'pyotter[view]'") from None

        figure, axes = pyplot.subplots(figsize=(10, 10))
        for segment in graph.get_segments():
            line = segment.centerline
            color = "tab:orange" if segment.in_junction else "tab:blue"
            axes.plot([p.x for p in line], [p.y for p in line], color=color, linewidth=1.2)
            middle, after = line[(len(line) - 1) // 2], line[(len(line) - 1) // 2 + 1]
            axes.annotate("", xy=(after.x, after.y), xytext=(middle.x, middle.y),
                          arrowprops={"arrowstyle": "->", "color": color, "linewidth": 1.2})
            if label_segments:
                axes.annotate(segment.id, (middle.x, middle.y), fontsize=5, ha="center", va="center")
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
