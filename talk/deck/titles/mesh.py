"""The title motif (2026-10-18, Sujit's call): a mesh of straight lines, with nodes routing through it.

Thin straight lines run edge to edge across the slide, around the text; every crossing is a junction.
Small amber and cyan nodes travel the mesh, and at some junctions a node turns onto the crossing
line — always the smaller turn, so it keeps moving forward — until it leaves at an edge. Each node
takes its own route through the same mesh: loosely, agents choosing paths, without drawing a
workflow. Routes are chosen in code by a fixed rule (no randomness at render time), so the slide
plays the same every time.

Pure geometry; SVG children for a 1920 x 1080 viewBox (SMIL `animateMotion`, no script).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

Point = tuple[float, float]


@dataclass(frozen=True)
class Palette:
    line: str
    line_opacity: float
    nodes: tuple[str, ...]


SOFT: Final = Palette(line="#FEFCFA", line_opacity=0.32, nodes=("#E0AA55", "#79B8CC"))
TERRA: Final = Palette(line="#D26F5D", line_opacity=0.75, nodes=("#E0AA55", "#79B8CC"))

# Each line runs edge to edge. The mesh may cross the whole slide, but never the text: these are
# the title slide's text boxes (title_slides.py), padded, and `clear_of_text` holds every line to them.
TEXT_BOXES: Final[tuple[tuple[float, float, float, float], ...]] = (
    (128, 120, 560, 205),       # DevDay logo
    (128, 290, 990, 645),       # the title, three lines
    (128, 820, 420, 878),       # the speaker
    (128, 930, 290, 1004),      # Sahaj logo
)
TEXT_PAD: Final = 40

LINES: Final[tuple[tuple[Point, Point], ...]] = (
    ((0, 62), (1920, 8)),           # across the top, above the logo
    ((700, 0), (1920, 420)),        # down from the top, above the title
    ((0, 712), (1920, 790)),        # between the title and the speaker
    ((0, 1068), (1920, 1010)),      # under the Sahaj logo
    ((1060, 1080), (1520, 0)),
    ((1360, 1080), (1150, 0)),
    ((1920, 150), (1130, 1080)),
    ((1240, 0), (1920, 760)),
    ((1700, 1080), (1880, 0)),
    ((470, 1080), (1920, 294)),     # rising from the bottom, right of the speaker
)
WIDTH: Final = 3
SPEED: Final = 190.0            # px per second along a route
# Which junctions a node turns at: node n turns at its k-th junction when (n + k) % TURN_EVERY == 0.
TURN_EVERY: Final = 2
# (start line, start at which end: 0 = first point, 1 = second, begin offset in s)
NODES: Final = ((2, 0, 0.0), (0, 0, 2.2), (4, 0, 4.1), (6, 1, 1.3), (9, 0, 3.0), (1, 0, 5.2),
                (3, 1, 6.4), (2, 0, 7.7))


def _hits_box(a: Point, b: Point, box: tuple[float, float, float, float]) -> bool:
    """Whether segment a-b passes through the box (sampled finely: the boxes are large)."""
    x0, y0, x1, y1 = box
    steps = int(math.dist(a, b) / 4) + 1
    return any(x0 <= a[0] + (b[0] - a[0]) * i / steps <= x1 and y0 <= a[1] + (b[1] - a[1]) * i / steps <= y1
               for i in range(steps + 1))


def clear_of_text() -> list[int]:
    """The lines that cross a padded text box (empty == the motif never touches the text)."""
    boxes = [(x0 - TEXT_PAD, y0 - TEXT_PAD, x1 + TEXT_PAD, y1 + TEXT_PAD) for x0, y0, x1, y1 in TEXT_BOXES]
    return [i for i, (a, b) in enumerate(LINES) if any(_hits_box(a, b, box) for box in boxes)]


def _intersect(a: tuple[Point, Point], b: tuple[Point, Point]) -> tuple[float, float] | None:
    """Where segment a meets segment b, as (t along a, u along b) in (0, 1), or None."""
    (x1, y1), (x2, y2) = a
    (x3, y3), (x4, y4) = b
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
    return (t, u) if 0 < t < 1 and 0 < u < 1 else None


def _at(line: tuple[Point, Point], t: float) -> Point:
    (x1, y1), (x2, y2) = line
    return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t


def _junctions(i: int) -> list[tuple[float, int, float]]:
    """Every crossing on line i: (t along line i, the other line, u along it), in order of t."""
    out = []
    for j, other in enumerate(LINES):
        hit = None if j == i else _intersect(LINES[i], other)
        if hit is not None:
            out.append((hit[0], j, hit[1]))
    return sorted(out)


def _direction(line: tuple[Point, Point], forward: bool) -> Point:
    (x1, y1), (x2, y2) = line
    dx, dy = (x2 - x1, y2 - y1) if forward else (x1 - x2, y1 - y2)
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def route(node: int, line: int, from_end: int) -> list[Point]:
    """A node's path: along its line; at every TURN_EVERY-th junction it turns onto the crossing
    line in the direction of the smaller turn; it ends where its line meets the slide's edge."""
    forward, t = from_end == 0, (0.0 if from_end == 0 else 1.0)
    points, k, visited = [_at(LINES[line], t)], 0, {line}
    while True:
        ahead = [j for j in _junctions(line) if (j[0] > t + 1e-9 if forward else j[0] < t - 1e-9)]
        ahead.sort(key=lambda j: j[0] if forward else -j[0])
        turned = False
        for jt, other, u in ahead:
            k += 1
            if (node + k) % TURN_EVERY == 0 and other not in visited:
                here = _at(LINES[line], jt)
                d = _direction(LINES[line], forward)
                go = _direction(LINES[other], True)
                points.append(here)
                forward = d[0] * go[0] + d[1] * go[1] >= 0     # the smaller turn keeps going forward
                line, t, turned = other, u, True
                visited.add(other)
                break
        if not turned:
            points.append(_at(LINES[line], 1.0 if forward else 0.0))
            return points


def _length(points: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def _node(points: list[Point], color: str, begin: float) -> str:
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    dur = _length(points) / SPEED
    return (f'<circle r="11" fill="{color}"><animateMotion path="{d}" dur="{dur:.2f}s" '
            f'begin="{-begin:.2f}s" repeatCount="indefinite"/></circle>')


def mesh(pal: Palette = SOFT, *, animated: bool = True) -> str:
    """The motif as SVG children. Refuses to draw a line across the text."""
    if clear_of_text():
        raise ValueError(f"mesh lines {clear_of_text()} cross the title slide's text")
    out = [f'<path d="M{a[0]} {a[1]} L{b[0]} {b[1]}" stroke="{pal.line}" stroke-opacity="{pal.line_opacity}" '
           f'stroke-width="{WIDTH}" stroke-linecap="round"/>' for a, b in LINES]
    if animated:
        out += [_node(route(n, line, end), pal.nodes[n % len(pal.nodes)], begin)
                for n, (line, end, begin) in enumerate(NODES)]
    return "".join(out)
