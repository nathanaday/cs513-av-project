from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ...core.models.world_hazard_library import HazardKind, WorldHazardLibrary
from ...core.models.world_road_graph import RoadGraphError, RoadSegment, WorldRoadGraph

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class World:
    @staticmethod
    def view_topology(graph: WorldRoadGraph, *, label_segments: bool = False, show_junctions: bool = True) -> Figure:
        """Draw the graph from above, in meters. Call `.savefig(path)` or `pyplot.show()` on the result.

        With `label_segments`, the figure is larger and each lane carries its segment id.
        With `show_junctions`, each junction's bounding box is outlined and tagged with its id.
        """
        try:
            from matplotlib import pyplot
            from matplotlib.patches import Rectangle
        except ImportError:
            raise ImportError("view_topology needs matplotlib: pip install 'pyotter[view]'") from None

        size, dpi = (24, 200) if label_segments else (10, 100)
        figure, axes = pyplot.subplots(figsize=(size, size), dpi=dpi)
        placed: list[tuple[float, float]] = []
        if show_junctions:
            for junction in graph.get_junctions():
                left, top = junction.x - junction.extent_x, junction.y - junction.extent_y
                axes.add_patch(Rectangle((left, top), 2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                                         facecolor="0.93", edgecolor="0.4", linestyle="--", linewidth=0.9))
                axes.text(left, top - 1.0, f"junction {junction.id}", fontsize=8, color="0.25", ha="left", va="bottom",
                          bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.85})
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
        if show_junctions and graph.junctions:
            axes.plot([], [], color="0.4", linestyle="--", linewidth=0.9, label="junction bounds")
        axes.legend(loc="upper right")
        axes.set_aspect("equal")
        axes.invert_yaxis()  # CARLA's frame is left-handed: +y is to the right of +x
        axes.set_xlabel("x (m)")
        axes.set_ylabel("y (m)")
        axes.set_title(graph.map_name)
        axes.grid(True, linewidth=0.3)
        return figure

    @staticmethod
    def view_hazards(graph: WorldRoadGraph, library: WorldHazardLibrary, *, show_junctions: bool = True) -> Figure:
        """Draw one map per assigned hazard, with each segment shaded by that hazard's probability.

        Every hazard keeps its own hue and its own scale, because an event's
        probability is per second and a condition's is per run.
        """
        try:
            from matplotlib import pyplot
            from matplotlib.cm import ScalarMappable
            from matplotlib.colors import LinearSegmentedColormap, Normalize
            from matplotlib.patches import Rectangle
        except ImportError:
            raise ImportError("view_hazards needs matplotlib: pip install 'pyotter[view]'") from None

        assigned = graph.hazard_ids()
        if not assigned:
            raise RoadGraphError("no hazard probabilities are assigned; assign some before viewing hazards")
        unknown = sorted(assigned - {hazard.id for hazard in library})
        if unknown:
            raise RoadGraphError(f"hazards not in the library: {', '.join(unknown)}")
        shown = [(index, hazard) for index, hazard in enumerate(library) if hazard.id in assigned]

        figure, panels = pyplot.subplots(1, len(shown), figsize=(6.5 * len(shown), 7.4), dpi=130,
                                         squeeze=False, facecolor=SURFACE, layout="constrained")
        for axes, (index, hazard) in zip(panels[0], shown):
            ramp = LinearSegmentedColormap.from_list(hazard.id, HAZARD_RAMPS[index] if index < len(HAZARD_RAMPS) else HAZARD_RAMPS[0])
            values = {s.id: s.hazard_probability(hazard) for s in graph.get_segments() if s.hazard_probability(hazard) > 0}
            scale = Normalize(vmin=0.0, vmax=max(values.values()))
            axes.set_facecolor(SURFACE)
            if show_junctions:
                for junction in graph.get_junctions():
                    axes.add_patch(Rectangle((junction.x - junction.extent_x, junction.y - junction.extent_y),
                                             2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                                             facecolor="none", edgecolor=AXIS, linestyle="--", linewidth=0.7))
            for segment in graph.get_segments():
                if segment.id not in values:
                    axes.plot([p.x for p in segment.centerline], [p.y for p in segment.centerline],
                              color=AXIS, linewidth=0.8, zorder=1)
            for sid in sorted(values, key=values.get):
                line = graph.get_segment(sid).centerline
                axes.plot([p.x for p in line], [p.y for p in line], color=ramp(scale(values[sid])),
                          linewidth=2.8, solid_capstyle="round", zorder=2)
            unit = "chance per second that one starts" if hazard.kind is HazardKind.EVENT else "chance that it holds for the run"
            axes.set_title(hazard.id, loc="left", fontsize=13, fontweight="bold", color=INK, pad=22)
            axes.text(0.0, 1.015, f"{hazard.kind.value} on {len(values)} of {len(graph.segments)} segments",
                      transform=axes.transAxes, fontsize=9.5, color=INK_SECONDARY, ha="left", va="bottom")
            axes.set_aspect("equal")
            axes.invert_yaxis()
            axes.set_xlabel("x (m)", color=INK_SECONDARY)
            axes.set_ylabel("y (m)", color=INK_SECONDARY)
            axes.tick_params(colors=INK_MUTED, labelsize=8)
            axes.grid(True, linewidth=0.4, color=GRID)
            for spine in axes.spines.values():
                spine.set_color(AXIS)
            bar = figure.colorbar(ScalarMappable(norm=scale, cmap=ramp), ax=axes, orientation="horizontal",
                                  fraction=0.035, pad=0.03, aspect=40)
            bar.set_label(unit, color=INK_SECONDARY, fontsize=9.5)
            bar.ax.tick_params(colors=INK_MUTED, labelsize=8)
            bar.outline.set_visible(False)
        figure.suptitle(f"{graph.map_name}: hazard probabilities", x=0.02, ha="left", fontsize=14, color=INK)
        return figure


LABEL_FRACTIONS = (0.3, 0.7, 0.15, 0.85, 0.5, 0.4, 0.6)

SURFACE, INK, INK_SECONDARY, INK_MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

# One light-to-dark ramp per hazard, in library order, so a hazard keeps its hue whichever others are shown.
HAZARD_RAMPS = (
    ("#9ec5f4", "#2a78d6", "#0d366b"),
    ("#f7c3ad", "#eb6834", "#7a2c0c"),
    ("#a4dfca", "#1baf7a", "#0a5038"),
    ("#f8d999", "#eda100", "#6e4b00"),
    ("#f6cadb", "#e87ba4", "#7d2748"),
    ("#99cd99", "#008300", "#003c00"),
    ("#c0b9ef", "#6250d6", "#2a2068"),
    ("#f4b6b6", "#e34948", "#6f1a1a"),
)


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
