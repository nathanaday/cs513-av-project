"""Shared drawing for pyotter's map figures. matplotlib is imported only when a figure is made."""

from __future__ import annotations

from ..models.world_road_graph import WorldRoadGraph

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


def hue_ramp(index: int) -> tuple[str, str, str]:
    return HAZARD_RAMPS[index] if index < len(HAZARD_RAMPS) else HAZARD_RAMPS[0]


def matplotlib_tools(caller: str):
    try:
        from matplotlib import cm, colors, lines, patches, pyplot
    except ImportError:
        raise ImportError(f"{caller} needs matplotlib: pip install 'pyotter[view]'") from None

    class Tools:
        LinearSegmentedColormap, ListedColormap, Normalize = colors.LinearSegmentedColormap, colors.ListedColormap, colors.Normalize
        ScalarMappable, Line2D, Rectangle = cm.ScalarMappable, lines.Line2D, patches.Rectangle

    return pyplot, Tools


def draw_lanes(axes, graph: WorldRoadGraph, values: dict[str, float], ramp, scale, show_junctions: bool, tools) -> None:
    """Draw every lane: shaded by its value on the ramp, or thin and gray where it has none."""
    axes.set_facecolor(SURFACE)
    if show_junctions:
        for junction in graph.get_junctions():
            axes.add_patch(tools.Rectangle((junction.x - junction.extent_x, junction.y - junction.extent_y),
                                           2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                                           facecolor="none", edgecolor=AXIS, linestyle="--", linewidth=0.7))
    for sid in sorted(graph.segments, key=lambda sid: values.get(sid, 0.0)):
        line, value = graph.segments[sid].centerline, values.get(sid, 0.0)
        xs, ys = [p.x for p in line], [p.y for p in line]
        if value > 0.005:
            axes.plot(xs, ys, color=ramp(scale(value)), linewidth=2.8, solid_capstyle="round", zorder=2)
        else:
            axes.plot(xs, ys, color=AXIS, linewidth=0.8, zorder=1)


def style_map(axes, title: str, lines: list[str]) -> None:
    """Title, up to two subtitle lines, and the shared look of a map in meters."""
    axes.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=38)
    axes.text(0.0, 1.015, "\n".join(lines + [""] * (2 - len(lines))), transform=axes.transAxes, fontsize=9.5, color=INK_SECONDARY,
              ha="left", va="bottom", linespacing=1.4)
    axes.set_aspect("equal")
    axes.invert_yaxis()
    axes.set_xlabel("x (m)", color=INK_SECONDARY)
    axes.set_ylabel("y (m)", color=INK_SECONDARY)
    axes.tick_params(colors=INK_MUTED, labelsize=8)
    axes.grid(True, linewidth=0.4, color=GRID)
    for spine in axes.spines.values():
        spine.set_color(AXIS)


def scale_bar(figure, axes, scale, ramp, label: str, tools, *, own_axes: bool = False) -> None:
    """Draw the scale under `axes`, or inside it when `own_axes` says the axes is reserved for the scale."""
    where = {"cax": axes} if own_axes else {"ax": axes, "fraction": 0.035, "pad": 0.03, "aspect": 40}
    bar = figure.colorbar(tools.ScalarMappable(norm=scale, cmap=ramp), orientation="horizontal", **where)
    bar.set_label(label, color=INK_SECONDARY, fontsize=9.5)
    bar.ax.tick_params(colors=INK_MUTED, labelsize=8)
    bar.outline.set_visible(False)
