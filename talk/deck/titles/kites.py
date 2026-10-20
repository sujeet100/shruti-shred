"""The title graphic: agents as KITES.

A kite flies on its own (it rides the wind, finds its height, goes where the air takes it), and
every kite is on a string someone holds. That is agentic AI — autonomy inside limits someone
decides — and the talk's thesis: the architecture decides who holds the string. The strings
converge on ONE spool. Flat, two-tone diamonds in the Sahaj accents, after the logo's two-tone
letterforms; tails of small dots. No music in it: this is the DevDay theme, not the talk's domain.

Pure geometry; deterministic. Returns SVG children for a 1920 x 1080 viewBox.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

FIELD, WHITE, SOFT = "#33357D", "#FEFCFA", "#C9CAE6"
TERRA, MUSTARD, SKY, PURPLE = "#D26F5D", "#E0AA55", "#79B8CC", "#9B7FC4"
DARK: Final = {TERRA: "#B4513F", MUSTARD: "#C08A30", SKY: "#4F96AD", PURPLE: "#715397", WHITE: "#C9CAE6"}
SPOOL: Final = (1180.0, 1010.0)


@dataclass(frozen=True)
class Kite:
    x: float            # the bridle point (where the string ties on)
    y: float
    size: float         # half the kite's width
    tilt: float         # degrees, clockwise
    color: str
    sway: float = 0.0   # how far the string bows (a longer, freer line bows more)


KITES: Final = (Kite(1500, 250, 92, 14, TERRA, 0.10), Kite(1745, 420, 66, -10, MUSTARD, 0.06),
                Kite(1320, 520, 58, 22, SKY, 0.05), Kite(1640, 700, 46, -4, WHITE, 0.04),
                Kite(1810, 160, 40, 8, PURPLE, 0.12))


def _rot(px: float, py: float, cx: float, cy: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def _pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def kite(k: Kite) -> str:
    s, cx, cy = k.size, k.x, k.y
    top, right, bottom, left = (cx, cy - 1.25 * s), (cx + s, cy), (cx, cy + 1.7 * s), (cx - s, cy)
    r = lambda p: _rot(p[0], p[1], cx, cy, k.tilt)
    T, R, B, L, C = r(top), r(right), r(bottom), r(left), (cx, cy)
    halves = (f'<polygon points="{_pts([T, L, B])}" fill="{k.color}"/>'
              f'<polygon points="{_pts([T, R, B])}" fill="{DARK[k.color]}"/>')
    spars = (f'<line x1="{T[0]:.1f}" y1="{T[1]:.1f}" x2="{B[0]:.1f}" y2="{B[1]:.1f}" stroke="{FIELD}" stroke-opacity="0.35" stroke-width="3"/>'
             f'<line x1="{L[0]:.1f}" y1="{L[1]:.1f}" x2="{R[0]:.1f}" y2="{R[1]:.1f}" stroke="{FIELD}" stroke-opacity="0.35" stroke-width="3"/>')
    tail = "".join(f'<circle cx="{B[0] + math.sin(i * 0.9) * s * 0.18:.1f}" cy="{B[1] + i * s * 0.32:.1f}" r="{max(3.0, s * 0.06):.1f}" '
                   f'fill="{k.color}" fill-opacity="{1 - i * 0.12:.2f}"/>' for i in range(1, 7))
    return halves + spars + tail


def string(k: Kite, spool_at: tuple[float, float] = SPOOL) -> str:
    """The line from the spool up to the kite, bowed by the wind (a quadratic curve)."""
    sx, sy = spool_at
    mx, my = (sx + k.x) / 2, (sy + k.y) / 2
    bow = k.sway * math.hypot(k.x - sx, k.y - sy)
    return (f'<path d="M{sx} {sy} Q{mx + bow:.1f} {my + bow * 0.6:.1f} {k.x} {k.y}" fill="none" stroke="{SOFT}" '
            f'stroke-opacity="0.75" stroke-width="2.5"/>')


def spool(at: tuple[float, float] = SPOOL) -> str:
    sx, sy = at
    return (f'<circle cx="{sx}" cy="{sy}" r="34" fill="{MUSTARD}"/><circle cx="{sx}" cy="{sy}" r="20" fill="{FIELD}"/>'
            f'<circle cx="{sx}" cy="{sy}" r="8" fill="{MUSTARD}"/>')


def kites(flock: tuple[Kite, ...] = KITES, spool_at: tuple[float, float] = SPOOL) -> str:
    return ("".join(string(k, spool_at) for k in flock) + spool(spool_at) + "".join(kite(k) for k in flock))


_COLORS: Final = (TERRA, MUSTARD, SKY, WHITE, PURPLE)
SPOOL_ACT: Final = (1500.0, 1040.0)


def _flock(points: list[tuple[float, float, float]], tilt: float, sway: float) -> tuple[Kite, ...]:
    return tuple(Kite(x, y, s, tilt * (-1) ** i, _COLORS[i % len(_COLORS)], sway * (-1) ** i)
                 for i, (x, y, s) in enumerate(points))


# The acts, told by the kites: eleven with tangled strings; one high above a tangle; seven calm.
ACT_FLOCKS: Final = {
    1: _flock([(1180, 300, 34), (1300, 210, 30), (1420, 330, 36), (1540, 180, 28), (1660, 300, 34), (1790, 220, 30),
               (1240, 470, 30), (1380, 520, 34), (1520, 430, 30), (1660, 520, 32), (1800, 450, 28)], 18, 0.38),
    2: (Kite(1640, 190, 96, 10, TERRA, 0.05),) + _flock([(1300, 640, 30), (1400, 700, 28), (1500, 620, 32),
                                                          (1360, 780, 26), (1470, 800, 28)], 24, 0.45),
    3: _flock([(1220, 380, 44), (1360, 260, 44), (1500, 170, 44), (1640, 260, 44), (1780, 380, 44),
               (1290, 560, 40), (1710, 560, 40)], 6, 0.03),
}
