"""The title graphic: a musical staff that becomes an agent graph, and music again.

Five staff lines enter carrying a few notes. They branch out to agents (abstract geometric tokens:
circle, square, diamond, hexagon, triangle — no robots, no brains), one of them a decision point
with a feedback loop back to it, then converge, and leave as five staff lines again carrying new
notes. Music -> orchestration -> music: the DevDay Agentic AI motif (orchestration paths) meeting
this talk's subject. Each act divider rearranges the same parts to tell its act.

Pure geometry; returns SVG children for a 1920 x 1080 viewBox on the indigo field.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

FIELD, WHITE, SOFT = "#33357D", "#FEFCFA", "#C9CAE6"
TERRA, MUSTARD, SKY, PURPLE = "#D26F5D", "#E0AA55", "#79B8CC", "#9B7FC4"
SHAPES: Final = ("circle", "square", "diamond", "hexagon", "triangle")
COLORS: Final = (MUSTARD, SKY, TERRA, PURPLE, SKY)


@dataclass(frozen=True)
class Graph:
    staff_x: tuple[float, float]                 # the entering staff, from x to x
    staff_ys: tuple[float, ...]                   # its five lines
    nodes: tuple[tuple[float, float], ...]        # one agent per path
    converge: tuple[float, float]                 # where the paths meet
    out_ys: tuple[float, ...] = ()                # the leaving staff's lines at the right edge
    notes_in: tuple[tuple[float, int], ...] = ()  # (x, staff position: 0 = top line, 8 = bottom line)
    notes_out: tuple[float, ...] = ()             # x positions of the new notes
    loop_to: int | None = None                    # the node a dashed feedback loop returns to
    faded: bool = False                           # the whole graph drawn quietly (a tangle in the background)
    straight: bool = False                        # one clean line through instead of branches
    feed: list[int] = field(default_factory=list)  # which staff line feeds each node (default: spread)


def _shape(kind: str, x: float, y: float, r: float, color: str) -> str:
    if kind == "circle":
        body = f'<circle cx="{x}" cy="{y}" r="{r}"'
    elif kind == "square":
        body = f'<rect x="{x - r * 0.88:.1f}" y="{y - r * 0.88:.1f}" width="{r * 1.76:.1f}" height="{r * 1.76:.1f}" rx="{r * 0.3:.1f}"'
    else:
        n, rot = {"diamond": (4, 0), "hexagon": (6, 30), "triangle": (3, -90)}[kind]
        pts = " ".join(f"{x + r * 1.08 * math.cos(math.radians(rot + 360 * k / n)):.1f},"
                       f"{y + r * 1.08 * math.sin(math.radians(rot + 360 * k / n)):.1f}" for k in range(n))
        body = f'<polygon points="{pts}"'
    return (body + f' fill="{FIELD}" stroke="{color}" stroke-width="{r * 0.36:.1f}" stroke-linejoin="round"/>'
            f'<circle cx="{x}" cy="{y}" r="{r * 0.3:.1f}" fill="{WHITE}"/>')


def _note(x: float, y: float, color: str, up: bool = True) -> str:
    stem = f'<line x1="{x + 13:.1f}" y1="{y - 2:.1f}" x2="{x + 13:.1f}" y2="{y - 66:.1f}" stroke="{color}" stroke-width="4"/>' if up else ""
    return f'<ellipse cx="{x}" cy="{y}" rx="16" ry="11" transform="rotate(-22 {x} {y})" fill="{color}"/>{stem}'


def draw(g: Graph) -> str:
    op = 0.35 if g.faded else 1.0
    line = lambda d, w=5, o=0.85, dash="": (f'<path d="{d}" fill="none" stroke="{WHITE}" stroke-opacity="{o * op:.2f}" '
                                            f'stroke-width="{w}" stroke-linecap="round"{dash}/>')
    x0, x1 = g.staff_x
    out = [line(f"M{x0} {y} L{x1} {y}", 4, 0.6) for y in g.staff_ys]
    gap = (g.staff_ys[-1] - g.staff_ys[0]) / 8
    out += [_note(x, g.staff_ys[0] + pos * gap, WHITE) for x, pos in g.notes_in]
    cx, cy = g.converge
    if g.straight:
        y = g.staff_ys[len(g.staff_ys) // 2]
        out.append(line(f"M{x1} {y} C{x1 + 120} {y}, {cx - 120} {cy}, {cx} {cy}", 7, 1.0))
    else:
        feed = g.feed or [round(i * (len(g.staff_ys) - 1) / max(1, len(g.nodes) - 1)) for i in range(len(g.nodes))]
        for (nx, ny), k in zip(g.nodes, feed):
            sy = g.staff_ys[k]
            out.append(line(f"M{x1} {sy} C{x1 + 90} {sy}, {nx - 110} {ny}, {nx} {ny}"))
            out.append(line(f"M{nx} {ny} C{nx + 120} {ny}, {cx - 130} {cy}, {cx} {cy}"))
    for i, oy in enumerate(g.out_ys):
        out.append(line(f"M{cx} {cy} C{cx + 70} {cy}, {cx + 90} {oy}, {2000} {oy}", 4, 0.6))
    if g.loop_to is not None:
        nx, ny = g.nodes[g.loop_to]
        top = min(ny, cy) - 150
        out.append(f'<path d="M{cx} {cy} C{cx} {top}, {nx} {top}, {nx} {ny - 34}" fill="none" stroke="{MUSTARD}" '
                   f'stroke-opacity="{op:.2f}" stroke-width="5" stroke-dasharray="2 14" stroke-linecap="round"/>'
                   f'<path d="M{nx - 14} {ny - 56} L{nx} {ny - 34} L{nx + 14} {ny - 56}" fill="none" stroke="{MUSTARD}" '
                   f'stroke-opacity="{op:.2f}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
    if not g.straight:
        out += [_shape(SHAPES[i % 5], nx, ny, 26 if not g.faded else 18, COLORS[i % 5]) for i, (nx, ny) in enumerate(g.nodes)]
    if g.out_ys:
        gy = (g.out_ys[-1] - g.out_ys[0]) / 8
        out += [_note(x, g.out_ys[0] + (2 + 3 * (i % 2)) * gy, MUSTARD) for i, x in enumerate(g.notes_out)]
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{30 if not g.faded else 20}" fill="{MUSTARD}" fill-opacity="{op:.2f}"/>'
               f'<circle cx="{cx}" cy="{cy}" r="{11 if not g.faded else 7}" fill="{FIELD}"/>')
    return "".join(out)


STAFF: Final = (380.0, 420.0, 460.0, 500.0, 540.0)

TITLE: Final = Graph(staff_x=(1010, 1220), staff_ys=STAFF,
                     nodes=((1440, 220), (1470, 340), (1490, 460), (1470, 580), (1440, 700)),
                     converge=(1740, 460), out_ys=(400, 430, 460, 490, 520),
                     notes_in=((1060, 1), (1120, 4), (1176, 2)), notes_out=(1830, 1880), loop_to=2)

# Act 1: the band grew to eleven, paths everywhere. Act 2: one clean line past the faded tangle.
# Act 3: the five agents the system has now, converging cleanly.
_ELEVEN = tuple((1300 + 52 * (i % 4) + 28 * (i // 4), 200 + 66 * i) for i in range(11))
ACTS: Final = {
    1: [Graph(staff_x=(1060, 1220), staff_ys=STAFF, nodes=_ELEVEN, converge=(1660, 460),
              feed=[(i * 3) % 5 for i in range(11)], notes_in=((1110, 2), (1170, 5)), loop_to=4)],
    2: [Graph(staff_x=(1060, 1220), staff_ys=STAFF, nodes=_ELEVEN, converge=(1660, 460),
              feed=[(i * 3) % 5 for i in range(11)], faded=True),
        Graph(staff_x=(1060, 1220), staff_ys=STAFF, nodes=(), converge=(1660, 460), straight=True,
              out_ys=(400, 430, 460, 490, 520), notes_in=((1110, 2), (1170, 5)), notes_out=(1760,))],
    3: [Graph(staff_x=(1060, 1220), staff_ys=STAFF,
              nodes=((1450, 250), (1480, 355), (1500, 460), (1480, 565), (1450, 670)),
              converge=(1660, 460), out_ys=(400, 430, 460, 490, 520), notes_in=((1110, 2), (1170, 5)),
              notes_out=(1800, 1850), loop_to=2)],
}


def score_graph(graphs: list[Graph] | Graph = TITLE, shift: float = 0.0) -> str:
    """The graph(s); `shift` moves them right (the act dividers keep a wider text column)."""
    body = "".join(draw(g) for g in (graphs if isinstance(graphs, list) else [graphs]))
    return f'<g transform="translate({shift} 0)">{body}</g>' if shift else body
