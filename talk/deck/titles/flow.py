"""The title motif, simplified (2026-10-18, GPT's second note): three flowing lines and moving dots.

A title motif does not need to explain agentic AI; it needs to be distinctive, loosely on theme and
easy to vary per talk (last year's pipes worked as simple shapes, not as accurate pipelines). So:
three coloured lines rise together from the bottom edge, separate, braid across each other and come
back together, then leave off the top-right corner, with small white dots travelling along them. No
nodes, no loop, no connectors. The braid is a loose rhythm, not a waveform or any music iconography.

Each line is a centre curve plus a sideways sway: the sway is zero where the lines run together
and swells in the middle, and the three are a third of a turn apart, so they cross. Another talk
gets another composition by changing the centre curve, the sway or the turns. Pure geometry; SVG
children for a 1920 x 1080 viewBox.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Palette:
    lines: tuple[str, str, str]
    dot: str


INDIGO: Final = Palette(lines=("#79B8CC", "#D26F5D", "#B9A3E0"), dot="#FEFCFA")

# The centre curve: a cubic Bezier rising from the bottom edge and leaving off the top-right corner.
CENTRE: Final = ((1200.0, 1120.0), (1150.0, 500.0), (1500.0, 300.0), (1980.0, -40.0))
GAP: Final = 20.0           # between the lines where they run together
SWAY: Final = 130.0         # the largest sideways sway, at the middle of the braid
TURNS: Final = 1.8          # how many times the braid twists along the curve
WIDTH: Final = 8
SAMPLES: Final = 160
PERIOD_S: Final = 6.5       # one dot's journey
DOTS_PER_LINE: Final = 2


def _bezier(t: float) -> tuple[float, float]:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = CENTRE
    u = 1 - t
    return (u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
            u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3)


def _normal(t: float) -> tuple[float, float]:
    (ax, ay), (bx, by) = _bezier(max(0.0, t - 1e-3)), _bezier(min(1.0, t + 1e-3))
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy) or 1.0
    return -dy / n, dx / n


def _swell(t: float) -> float:
    """0 where the lines run together (both ends), 1 at the middle of the braid."""
    return math.sin(math.pi * min(1.0, max(0.0, (t - 0.12) / 0.76))) ** 2


def line_points(k: int) -> list[tuple[float, float]]:
    """Line k (0, 1, 2): the centre curve offset sideways by its bundle place, plus its sway."""
    points = []
    for i in range(SAMPLES + 1):
        t = i / SAMPLES
        s = _swell(t)
        offset = (k - 1) * GAP * (1 - s) + SWAY * s * math.sin(2 * math.pi * (TURNS * t + k / 3))
        (x, y), (nx, ny) = _bezier(t), _normal(t)
        points.append((x + nx * offset, y + ny * offset))
    return points


def _path(points: list[tuple[float, float]]) -> str:
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)


def _dot(path_id: str, color: str, begin: float) -> str:
    return (f'<circle r="9" fill="{color}"><animateMotion dur="{PERIOD_S:g}s" begin="{begin:.2f}s" '
            f'repeatCount="indefinite"><mpath href="#{path_id}"/></animateMotion></circle>')


def flow(pal: Palette = INDIGO, *, animated: bool = True, prefix: str = "flow") -> str:
    """The motif as SVG children; `prefix` keeps path ids unique per slide."""
    out, dots = [], []
    for k, color in enumerate(pal.lines):
        pid = f"{prefix}-{k}"
        out.append(f'<path id="{pid}" d="{_path(line_points(k))}" fill="none" stroke="{color}" '
                   f'stroke-width="{WIDTH}" stroke-linecap="round" stroke-linejoin="round"/>')
        # staggered so a dot is always somewhere on every line; negative begins start mid-journey
        dots += [_dot(pid, pal.dot, -PERIOD_S * (j / DOTS_PER_LINE + k / 7)) for j in range(DOTS_PER_LINE)]
    return "".join(out + (dots if animated else []))
