"""The DevDay 2026 (Agentic AI) motif and corner mark, drawn as SVG for the slides.

Last year's data-engineering DevDay ran pipes in from the slide's left edge, a different shape for
every talk, with the DevDay corner mark (a lavender pill over a quarter-circle cluster and a dot
grid) bottom right. This year's equivalent is the ROUTE: an agent's path in from the edge, bending
like a pipe elbow, through decision points where the branches it did not take stay faint, to a
goal. `route_art` draws any set of routes from grid polylines, so each slide can have its own shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

FIELD, WHITE, SOFT = "#33357D", "#FEFCFA", "#C9CAE6"
TERRA, MUSTARD, SKY, PURPLE = "#D26F5D", "#E0AA55", "#79B8CC", "#715397"
LAVENDER, PALE_MUSTARD, PALE_SKY = "#8E90BF", "#EBD3A6", "#C4DCE6"
STROKE: Final = 34
RADIUS: Final = 46


@dataclass(frozen=True)
class Route:
    """One path: grid points in px (it may start or end off the slide), its colour, the decision
    points on it (indices into `points`), the branches not taken ((from index, end point)), and
    whether it ends at a goal."""
    points: tuple[tuple[float, float], ...]
    color: str
    decisions: tuple[int, ...] = ()
    branches: tuple[tuple[int, tuple[float, float]], ...] = ()
    goal: bool = False
    extra: dict = field(default_factory=dict)


def _rounded(points: tuple[tuple[float, float], ...], r: float = RADIUS) -> str:
    """A polyline with every corner rounded into a pipe-elbow arc."""
    d = f"M{points[0][0]} {points[0][1]}"
    for (x0, y0), (x1, y1), (x2, y2) in zip(points, points[1:], points[2:]):
        ax, ay = x1 - x0, y1 - y0
        bx, by = x2 - x1, y2 - y1
        la, lb = max(abs(ax), abs(ay)), max(abs(bx), abs(by))
        rr = min(r, la / 2, lb / 2)
        sx, sy = x1 - ax / la * rr, y1 - ay / la * rr
        ex, ey = x1 + bx / lb * rr, y1 + by / lb * rr
        d += f" L{sx:.1f} {sy:.1f} Q{x1} {y1} {ex:.1f} {ey:.1f}"
    return d + f" L{points[-1][0]} {points[-1][1]}"


def _route(rt: Route) -> str:
    out = []
    for i, end in rt.branches:
        sx, sy = rt.points[i]
        out.append(f'<path d="M{sx} {sy} L{end[0]} {end[1]}" stroke="{SOFT}" stroke-opacity="0.35" stroke-width="{STROKE - 10}" '
                   f'stroke-linecap="round"/><circle cx="{end[0]}" cy="{end[1]}" r="14" fill="{SOFT}" fill-opacity="0.35"/>')
    out.append(f'<path d="{_rounded(rt.points)}" stroke="{rt.color}" stroke-width="{STROKE}" stroke-linecap="round" '
               f'stroke-linejoin="round" fill="none"/>')
    for i in rt.decisions:
        x, y = rt.points[i]
        out.append(f'<circle cx="{x}" cy="{y}" r="30" fill="{FIELD}" stroke="{rt.color}" stroke-width="12"/>'
                   f'<circle cx="{x}" cy="{y}" r="9" fill="{WHITE}"/>')
    if rt.goal:
        x, y = rt.points[-1]
        out.append(f'<circle cx="{x}" cy="{y}" r="48" fill="{MUSTARD}"/><circle cx="{x}" cy="{y}" r="30" fill="{FIELD}"/>'
                   f'<circle cx="{x}" cy="{y}" r="13" fill="{TERRA}"/>')
    return "".join(out)


def route_art(routes: list[Route], label: str, width: int = 700) -> str:
    """The motif, pinned to the slide's left edge, full height; routes may bleed off any edge."""
    return (f'<svg aria-label="{label}" style="position:absolute;left:0px;top:0px;width:{width}px;height:1080px" '
            f'viewBox="0 0 {width} 1080">' + "".join(_route(r) for r in routes) + "</svg>")


def corner_mark() -> str:
    """The DevDay corner mark, bottom right: a lavender pill bleeding off the right edge over a
    quarter-circle cluster and a dot grid, after the 2025 talk slides."""
    cx, cy, ro, ri = 1782, 952, 132, 76
    dots = "".join(f'<circle cx="{cx + 22 + c * 27}" cy="{cy + 22 + r * 27}" r="6" fill="{SKY}"/>'
                   for r in range(5) for c in range(5))
    return (f'<svg aria-label="" style="position:absolute;left:1580px;top:660px;width:340px;height:420px" viewBox="1580 660 340 420">'
            f'<rect x="1600" y="688" width="420" height="132" rx="66" fill="{LAVENDER}"/>'
            f'<path d="M{cx - ro} {cy} A{ro} {ro} 0 0 1 {cx + ro} {cy} Z" fill="{MUSTARD}"/>'
            f'<path d="M{cx - ri} {cy} A{ri} {ri} 0 0 1 {cx} {cy - ri} L{cx} {cy} Z" fill="{PURPLE}"/>'
            f'<path d="M{cx} {cy - ri} A{ri} {ri} 0 0 1 {cx + ri} {cy} L{cx} {cy} Z" fill="{PALE_MUSTARD}"/>'
            f'<path d="M{cx - ro} {cy} A{ro} {ro} 0 0 0 {cx} {cy + ro} L{cx} {cy} Z" fill="{SKY}"/>'
            f'<path d="M{cx - ri} {cy} A{ri} {ri} 0 0 0 {cx} {cy + ri} L{cx} {cy} Z" fill="{PALE_SKY}"/>'
            f'<rect x="{cx}" y="{cy}" width="{ro}" height="{ro}" fill="{FIELD}"/>{dots}</svg>')


# ---- the shapes: one per slide that carries the motif, like last year's pipes -----------------
TITLE_ROUTES: Final = [
    Route(((110, -40), (110, 300), (290, 300), (290, 560), (440, 560), (440, 760)), SKY, decisions=(3,),
          branches=((3, (290, 700)),), goal=True),
    Route(((-40, 880), (170, 880), (170, 1120)), TERRA),
    Route(((330, 1120), (330, 950), (460, 950), (460, 1120)), MUSTARD, decisions=(2,), branches=((2, (460, 880)),)),
    Route(((250, -40), (250, 130), (400, 130), (400, 300)), TERRA),
]

DIVIDER_ROUTES: Final = {
    1: [Route(((140, -40), (140, 420), (360, 420), (360, 700)), SKY, decisions=(2,), branches=((2, (360, 300)),), goal=True),
        Route(((-40, 880), (260, 880), (260, 1120)), MUSTARD)],
    2: [Route(((-40, 260), (220, 260), (220, 620), (420, 620), (420, 1120)), TERRA, decisions=(2, 3), branches=((2, (100, 620)), (3, (420, 480)))),
        Route(((330, -40), (330, 120)), SKY)],
    3: [Route(((100, 1120), (100, 700), (300, 700), (300, 380), (480, 380)), MUSTARD, decisions=(2, 3), branches=((2, (420, 700)), (3, (300, 240))), goal=True),
        Route(((240, -40), (240, 180), (-40, 180)), SKY)],
}
