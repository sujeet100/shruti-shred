"""The title motif (2026-10-18, after GPT's "orchestration paths" brief): a transit map of agents.

Thin coloured lines run as one bundle, split into parallel routes through small geometric stations
(the agents), rejoin at ONE amber interchange (the decision), loop back once (the feedback), and
leave together for the output terminus. Drawn the way a metro map is drawn: horizontal, vertical
and 45-degree runs with rounded corners, and a few faint routes behind for the rest of the network.
No music iconography — the talk's subject is agents; the music is the testbed.

The lines enter from the TOP edge: last year's DevDay template ran pipes in from the left, and a
copy of those was rejected. Amber is reserved for decisions. Pure geometry; SVG children for a
1920 x 1080 viewBox, in either palette (`INDIGO` for the DevDay title field, `LIGHT` per the brief).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Palette:
    field: str        # the slide's background (station fill)
    lines: tuple[str, str, str]
    ink: str          # station outlines and the terminus
    faint: str        # the background network
    amber: str        # decisions only


INDIGO: Final = Palette(field="#33357D", lines=("#79B8CC", "#D26F5D", "#B9A3E0"), ink="#FEFCFA",
                        faint="#5C5EA3", amber="#E0AA55")
LIGHT: Final = Palette(field="#FEFCFA", lines=("#4E93A8", "#C2604E", "#715397"), ink="#2B2B33",
                       faint="#E4E2EA", amber="#D99A2B")

WIDTH: Final = 7          # a route's stroke
GAP: Final = 20           # between routes running together
RADIUS: Final = 44        # a corner's rounding


def route(points: list[tuple[float, float]], radius: float = RADIUS) -> str:
    """An SVG path through `points` with every corner rounded (metro style)."""
    d = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"]
    for (ax, ay), (bx, by), (cx, cy) in zip(points, points[1:], points[2:]):
        r = min(radius, math.dist((ax, ay), (bx, by)) / 2, math.dist((bx, by), (cx, cy)) / 2)
        ux, uy = _unit(bx - ax, by - ay)
        vx, vy = _unit(cx - bx, cy - by)
        d.append(f"L{bx - ux * r:.1f} {by - uy * r:.1f} Q{bx:.1f} {by:.1f} {bx + vx * r:.1f} {by + vy * r:.1f}")
    d.append(f"L{points[-1][0]:.1f} {points[-1][1]:.1f}")
    return "".join(d)


def _unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _stroke(d: str, color: str, width: float = WIDTH, extra: str = "") -> str:
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
            f'stroke-linejoin="round"{extra}/>')


def _station(kind: str, x: float, y: float, color: str, pal: Palette, r: float = 15) -> str:
    """A small geometric agent: circle, square or diamond, field-filled, outlined in its line's colour."""
    style = f'fill="{pal.field}" stroke="{color}" stroke-width="6" stroke-linejoin="round"'
    if kind == "circle":
        return f'<circle cx="{x}" cy="{y}" r="{r}" {style}/>'
    if kind == "square":
        return f'<rect x="{x - r}" y="{y - r}" width="{2 * r}" height="{2 * r}" rx="4" {style}/>'
    pts = " ".join(f"{x + r * 1.3 * math.cos(math.radians(90 * k)):.1f},{y + r * 1.3 * math.sin(math.radians(90 * k)):.1f}"
                   for k in range(4))
    return f'<polygon points="{pts}" {style}/>'


def _interchange(x: float, y: float, w: float, h: float, stroke: str, fill: str) -> str:
    return (f'<rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{min(w, h) / 2:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="6"/>')


# The map. Three routes (k = 0, 1, 2), one bundle at x = X0 + k * GAP on the way in and out.
X0: Final = 1260.0
SPLIT_Y: Final = 300.0      # the request's interchange; the bundle splits just below it
JOIN_Y: Final = 780.0       # the decision; the routes rejoin here
OUT_Y: Final = 920.0        # the bundle turns right toward the output


def _xs() -> list[float]:
    return [X0 + k * GAP for k in range(3)]


def _routes() -> list[list[tuple[float, float]]]:
    """Each route from the top edge to the output terminus: in as a bundle, out on its own path,
    back as a bundle at the decision, then right to the terminus."""
    x0, x1, x2 = _xs()
    tail = lambda x, k: [(x, JOIN_Y), (x, OUT_Y + (2 - k) * GAP), (1760, OUT_Y + (2 - k) * GAP)]
    left = [(x0, -20), (x0, 360), (x0 - 150, 510), (x0 - 150, 620), (x0, 770)] + tail(x0, 0)
    middle = [(x1, -20)] + tail(x1, 1)
    right = [(x2, -20), (x2, 330), (x2 + 180, 510), (x2 + 180, 590), (x2, 770)] + tail(x2, 2)
    return [left, middle, right]


_STATIONS: Final = (("circle", 0, 1110, 565), ("square", 1, 1280, 470), ("diamond", 1, 1280, 620),
                    ("square", 2, 1480, 550))


def _loop() -> list[tuple[float, float]]:
    x2 = _xs()[2]
    return [(x2 + 40, JOIN_Y), (1660, JOIN_Y), (1660, SPLIT_Y + 60), (x2 + 40, SPLIT_Y + 60)]


def _feedback(pal: Palette) -> str:
    """The loop: from the decision back up to just below the split, dashed amber."""
    return _stroke(route(_loop(), 60), pal.amber, 6, ' stroke-dasharray="2 16"')


# --------------------------------------------------------------------------- #
# The flow: work travelling the map (SVG animateMotion — no script, no clip).  #
# --------------------------------------------------------------------------- #

PERIOD_S: Final = 7.0       # one request, end to end
AT_DECISION: Final = 0.6    # the share of the period at which every route reaches the decision
LOOP_SPAN: Final = (0.62, 0.86)  # when the amber token runs the feedback loop


def _share_to_decision(points: list[tuple[float, float]]) -> float:
    """How far along its route (by length) a route reaches the decision."""
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    upto = next(i for i, (_, y) in enumerate(points) if y == JOIN_Y)
    return sum(lengths[:upto]) / sum(lengths)


def _token(path_id: str, color: str, key_points: str, key_times: str, r: float = 9,
           extra: str = "") -> str:
    return (f'<circle r="{r}" fill="{color}"{extra}><animateMotion dur="{PERIOD_S:g}s" '
            f'repeatCount="indefinite" calcMode="linear" keyPoints="{key_points}" keyTimes="{key_times}">'
            f'<mpath href="#{path_id}"/></animateMotion></circle>')


def _flow(pal: Palette, ids: list[str], loop_id: str) -> str:
    """One token per route, timed so all three reach the decision at the same moment (parallel
    work converging), then on to the output; an amber token runs the feedback loop after it."""
    tokens = [_token(pid, pal.ink, f"0;{_share_to_decision(r):.4f};1", f"0;{AT_DECISION};1")
              for pid, r in zip(ids, _routes())]
    a, b = LOOP_SPAN
    show = (f'<animate attributeName="opacity" dur="{PERIOD_S:g}s" repeatCount="indefinite" '
            f'calcMode="discrete" values="0;1;0" keyTimes="0;{a};{b}"/>')
    loop = (f'<circle r="11" fill="{pal.amber}" opacity="0">{show}<animateMotion dur="{PERIOD_S:g}s" '
            f'repeatCount="indefinite" calcMode="linear" keyPoints="0;0;1;1" keyTimes="0;{a};{b};1">'
            f'<mpath href="#{loop_id}"/></animateMotion></circle>')
    return "".join(tokens) + loop


def _network(pal: Palette) -> str:
    """The rest of the map, faint: routes that are not this talk's."""
    faint = [[(1000, 170), (1420, 170), (1560, 30), (1560, -20)],
             [(1940, 420), (1800, 420), (1700, 520), (1700, 1100)],
             [(1060, 1100), (1060, 900), (1160, 800), (1160, 760)]]
    return "".join(_stroke(route(f), pal.faint, 5) for f in faint)


def metro(pal: Palette = INDIGO, *, animated: bool = True, prefix: str = "metro") -> str:
    """The title motif, as SVG children; `animated` adds the flowing tokens. `prefix` keeps the
    path ids unique when two slides carry the motif."""
    ids = [f"{prefix}-r{k}" for k in range(3)]
    loop_id = f"{prefix}-loop"
    out = [_network(pal), _feedback(pal).replace("<path ", f'<path id="{loop_id}" ', 1)]
    out += [_stroke(route(r), c).replace("<path ", f'<path id="{pid}" ', 1)
            for r, c, pid in zip(_routes(), pal.lines, ids)]
    out.append(_interchange(X0 + GAP, SPLIT_Y, 3 * GAP + 30, 34, pal.ink, pal.field))      # the request
    out += [_station(kind, x, y, pal.lines[k], pal) for kind, k, x, y in _STATIONS]
    out.append(_interchange(X0 + GAP, JOIN_Y, 3 * GAP + 44, 48, pal.amber, pal.amber))     # the decision
    out.append(f'<circle cx="{X0 + GAP}" cy="{JOIN_Y}" r="8" fill="{pal.field}"/>')
    ty = OUT_Y + GAP
    out.append(_interchange(1780, ty, 34, 3 * GAP + 30, pal.ink, pal.field))               # the output
    if animated:
        out.append(_flow(pal, ids, loop_id))
    return "".join(out)
