"""Chart styling and pitch plots, defined once for every notebook.

Two rules shape everything here.

**GitHub's notebook view is the audience.** A reviewer reads the rendered
notebook on github.com, so charts are static matplotlib PNGs with an opaque
light surface — a transparent background would disappear against GitHub's dark
theme, and Plotly's JavaScript renders blank there (CLAUDE.md §3).

**Understat's coordinates are already normalized to [0, 1]**, which is Opta's
0-100 system divided by 100. That makes the conversion a single multiplication,
and it puts the penalty spot at Opta's own x=88.5 — so a correctly oriented
shot map has every penalty sitting on the painted spot (CLAUDE.md §5, trap 10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import matplotlib as mpl

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# --- palette ---------------------------------------------------------------
# One accent hue plus greys. Every chart in the profile is a single series, so
# there is no categorical palette to keep colourblind-safe: identity is carried
# by the axis labels, not by hue.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#52514e"
ACCENT = "#2a78d6"
ACCENT_SOFT = "#a8c9ee"
GRID = "#e4e3df"
GOAL = "#eb6834"


def apply_style() -> None:
    """Set the rcParams every notebook chart inherits. Call once per notebook."""
    mpl.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "figure.dpi": 110,
            "font.size": 10,
            "text.color": INK,
            # Recessive frame: keep the data the loudest thing on the canvas.
            "axes.edgecolor": GRID,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelcolor": INK_MUTED,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.frameon": False,
            "lines.linewidth": 2.0,
            "lines.markersize": 5,
        }
    )


def annotate_source(ax: Axes, citation: str) -> None:
    """Stamp the snapshot's provenance under a chart.

    CLAUDE.md §7 asks every result to state the snapshot's ``match_date``
    range. A chart is a result, so it carries the citation with it rather than
    relying on a sentence somewhere above it.
    """
    ax.figure.text(
        0.005,
        -0.02,
        citation,
        transform=ax.figure.transFigure,
        fontsize=7.5,
        color=INK_MUTED,
        va="top",
    )


def title_block(ax: Axes, title: str, subtitle: str | None = None) -> None:
    """A bold left-aligned title with an optional plain-language subtitle."""
    ax.set_title(title, pad=18 if subtitle else 8)
    if subtitle:
        ax.annotate(
            subtitle,
            xy=(0, 1),
            xycoords="axes fraction",
            xytext=(0, 8),
            textcoords="offset points",
            fontsize=9,
            color=INK_MUTED,
            va="bottom",
        )


# --- pitch plots -----------------------------------------------------------

# Understat [0, 1] -> Opta [0, 100]. Opta's own penalty spot is x=88.5, which is
# why a correctly oriented map puts penalties exactly on it.
UNDERSTAT_TO_OPTA = 100.0
PENALTY_SPOT_OPTA = (88.5, 50.0)


def to_opta(x: Any, y: Any) -> tuple[Any, Any]:
    """Scale Understat's normalized coordinates onto mplsoccer's Opta pitch."""
    return x * UNDERSTAT_TO_OPTA, y * UNDERSTAT_TO_OPTA


def half_pitch(
    figsize: tuple[float, float] = (7.0, 5.0), *, crop: float = -20.0
) -> tuple[Figure, Axes, Any]:
    """An attacking-half pitch in Opta coordinates, ready for shot markers.

    Returns ``(figure, axes, pitch)``. The pitch object is handed back so a
    caller can use its own helpers (``pitch.scatter``, ``pitch.kdeplot``)
    without re-deriving the coordinate system.

    ``crop`` trims empty grass off the halfway end: almost no shots are taken
    from the defensive two-thirds of the attacking half, and the blank space
    only shrinks the part of the picture a reader is looking at. Pass ``0`` for
    the full half.
    """
    from mplsoccer import VerticalPitch

    pitch = VerticalPitch(
        pitch_type="opta",
        half=True,
        pitch_color=SURFACE,
        line_color="#b9b8b3",
        linewidth=1.0,
        pad_bottom=crop,
    )
    fig, ax = pitch.draw(figsize=figsize)
    fig.set_facecolor(SURFACE)
    return fig, ax, pitch


def mark_penalty_spot(ax: Axes, pitch: Any) -> None:
    """Ring the penalty spot, so trap 10's check is visible rather than asserted.

    Understat's coordinates are only useful if they are the way round you think
    they are. Drawing the spot the data *should* land on turns "trust me" into
    something a reader checks by eye. Deliberately unlabelled: a leader line
    into the busiest part of a shot map costs more than it explains, so the
    caller names the spot in the subtitle instead.
    """
    spot_x, spot_y = PENALTY_SPOT_OPTA
    # A pale halo under the ring keeps it legible over dense markers.
    for size, colour, width in ((700, SURFACE, 3.4), (700, INK, 1.6)):
        pitch.scatter(
            [spot_x],
            [spot_y],
            s=size,
            ax=ax,
            facecolors="none",
            edgecolors=colour,
            linewidth=width,
            linestyle="--" if colour == INK else "-",
            zorder=6,
        )


def shot_map(
    shots: pd.DataFrame,
    *,
    x: str = "x",
    y: str = "y",
    xg: str = "xg",
    result: str = "result",
    figsize: tuple[float, float] = (7.0, 5.0),
    show_penalty_spot: bool = False,
) -> tuple[Figure, Axes]:
    """Plot shots on an attacking-half pitch, sized by xG, goals picked out.

    ``shots`` holds Understat coordinates in [0, 1]. Marker area is
    proportional to xG so a tap-in does not read like a 30-yard shot, and goals
    take the one contrasting hue — everything else stays in the accent.

    ``show_penalty_spot`` overlays the orientation check from trap 10.
    """
    fig, ax, pitch = half_pitch(figsize=figsize)

    opta_x, opta_y = to_opta(shots[x], shots[y])
    is_goal = shots[result].eq("Goal")
    # >=8px markers per the mark spec, scaled by xG from there.
    sizes = 24 + shots[xg].fillna(0) * 260

    for mask, colour, edge, label in (
        (~is_goal, ACCENT_SOFT, ACCENT, "Shot"),
        (is_goal, GOAL, "#8f3512", "Goal"),
    ):
        if not mask.any():
            continue
        pitch.scatter(
            opta_x[mask],
            opta_y[mask],
            s=sizes[mask],
            ax=ax,
            color=colour,
            edgecolors=edge,
            # A 2px surface ring keeps overlapping markers separable.
            linewidth=0.9,
            alpha=0.85,
            zorder=3 if label == "Shot" else 4,
            label=label,
        )

    if show_penalty_spot:
        mark_penalty_spot(ax, pitch)

    ax.legend(loc="lower left", fontsize=8.5, labelcolor=INK_MUTED, markerscale=0.9)
    return fig, ax
