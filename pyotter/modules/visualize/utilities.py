"""Private helpers of the visualize module: the theme, and the drawing every figure shares.

matplotlib is imported only when a figure is made.
"""

from __future__ import annotations

from ...core.models.world_road_graph import WorldRoadGraph
from ...core.utilities.config import CONFIG

THEME = CONFIG.view


def hue_ramp(index: int) -> tuple[str, str, str]:
    """The light, middle and dark colors of the ramp at a position in the hazard library."""
    ramps = THEME.hazard_ramps
    if index < len(ramps):
        return ramps[index]
    return ramps[0]


def series_color(index: int) -> str:
    """The color of the line at a position among those that share a chart."""
    colors = THEME.series_colors
    if index < len(colors):
        return colors[index]
    return THEME.ink_muted


def matplotlib_tools(caller: str):
    """Import matplotlib for a figure.

    Args:
        caller: The name of the function that needs it, for the error message.

    Returns:
        `pyplot`, and a namespace of the matplotlib classes the figures use.

    Raises:
        ImportError: If matplotlib is not installed.
    """
    try:
        from matplotlib import cm, colors, lines, patches, pyplot
    except ImportError:
        raise ImportError(f"{caller} needs matplotlib: pip install 'pyotter[view]'") from None

    class Tools:
        LinearSegmentedColormap = colors.LinearSegmentedColormap
        ListedColormap = colors.ListedColormap
        Normalize = colors.Normalize
        ScalarMappable = cm.ScalarMappable
        Line2D = lines.Line2D
        Rectangle = patches.Rectangle

    return pyplot, Tools


def draw_lanes(axes, graph: WorldRoadGraph, values: dict[str, float], ramp, scale, show_junctions: bool, tools) -> None:
    """Draw every lane: shaded by its value on the ramp, or thin and gray where it has none.

    Args:
        axes: The axes to draw on.
        graph: The map.
        values: A value by segment id. A segment left out has none.
        ramp: The colormap for the values.
        scale: The normalizer that places a value on the ramp.
        show_junctions: Whether to outline each junction's bounding box.
        tools: The namespace from `matplotlib_tools`.
    """
    axes.set_facecolor(THEME.surface)
    if show_junctions:
        for junction in graph.get_junctions():
            corner = (junction.x - junction.extent_x, junction.y - junction.extent_y)
            axes.add_patch(tools.Rectangle(
                corner, 2 * junction.extent_x, 2 * junction.extent_y, zorder=0,
                facecolor="none", edgecolor=THEME.axis, linestyle="--", linewidth=0.7,
            ))
    # Lowest values first, so that the strongest shading is drawn on top.
    for sid in sorted(graph.segments, key=lambda sid: values.get(sid, 0.0)):
        value = values.get(sid, 0.0)
        xs = [point.x for point in graph.segments[sid].centerline]
        ys = [point.y for point in graph.segments[sid].centerline]
        if value > THEME.shaded_above:
            axes.plot(xs, ys, color=ramp(scale(value)), linewidth=2.8, solid_capstyle="round", zorder=2)
        else:
            axes.plot(xs, ys, color=THEME.axis, linewidth=0.8, zorder=1)


def style_map(axes, title: str, lines: list[str]) -> None:
    """Give a map its title, up to two subtitle lines, and the shared look of a map in meters."""
    subtitle = "\n".join(lines + [""] * (2 - len(lines)))
    axes.set_title(title, loc="left", fontsize=13, fontweight="bold", color=THEME.ink, pad=38)
    axes.text(0.0, 1.015, subtitle, transform=axes.transAxes, fontsize=9.5, color=THEME.ink_secondary,
              ha="left", va="bottom", linespacing=1.4)
    axes.set_aspect("equal")
    axes.invert_yaxis()  # CARLA's frame is left-handed: +y is to the right of +x
    axes.set_xlabel("x (m)", color=THEME.ink_secondary)
    axes.set_ylabel("y (m)", color=THEME.ink_secondary)
    axes.tick_params(colors=THEME.ink_muted, labelsize=8)
    axes.grid(True, linewidth=0.4, color=THEME.grid)
    for spine in axes.spines.values():
        spine.set_color(THEME.axis)


def style_chart(axes) -> None:
    """Give a chart over time or distance its shared look: horizontal grid lines and two spines."""
    axes.set_facecolor(THEME.surface)
    axes.tick_params(colors=THEME.ink_muted, labelsize=8)
    axes.grid(True, axis="y", linewidth=0.4, color=THEME.grid)
    for name, spine in axes.spines.items():
        spine.set_visible(name in ("left", "bottom"))
        spine.set_color(THEME.axis)


def scale_bar(figure, axes, scale, ramp, label: str, tools, *, own_axes: bool = False) -> None:
    """Draw the color scale for a map.

    Args:
        figure: The figure.
        axes: The map's axes, under which the scale is drawn, or the axes
            reserved for the scale.
        scale: The normalizer of the values.
        ramp: The colormap of the values.
        label: What the values are.
        tools: The namespace from `matplotlib_tools`.
        own_axes: Whether `axes` is reserved for the scale.
    """
    if own_axes:
        where = {"cax": axes}
    else:
        where = {"ax": axes, "fraction": 0.035, "pad": 0.03, "aspect": 40}
    bar = figure.colorbar(tools.ScalarMappable(norm=scale, cmap=ramp), orientation="horizontal", **where)
    bar.set_label(label, color=THEME.ink_secondary, fontsize=9.5)
    bar.ax.tick_params(colors=THEME.ink_muted, labelsize=8)
    bar.outline.set_visible(False)
