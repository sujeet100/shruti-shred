"""The title graphic: DevDay's own LED pixels, gaining agency.

The DEVDAY. mark is square pixels on a grid. For an Agentic AI DevDay the pixels leave the grid:
a quiet field of squares sits in place (rules, structure), and a stream lifts out of it, each square
tilting freer and warming from sky to terracotta as it goes, until together they draw a sound wave
(this talk: a band). Units that leave a rigid structure and make something on their own.

Pure geometry; deterministic (hash-jittered, never random). One <path> per colour/opacity tier,
so the whole picture is a handful of SVG elements.
"""
from __future__ import annotations

import math
import zlib
from typing import Final

FIELD, WHITE = "#33357D", "#FEFCFA"
SKY, MUSTARD, TERRA = "#79B8CC", "#E0AA55", "#D26F5D"
PITCH, CELL = 32, 15
GRID_X0: Final = 1260        # the field's soft left edge; it bleeds off the right edge
CLEAR: Final = (1560, 60, 1920, 220)   # no grid behind the logo


def _h(*k: object) -> float:
    """A stable pseudo-random number in [0, 1) for a key."""
    return (zlib.crc32(":".join(map(str, k)).encode()) % 10007) / 10007


def _square(cx: float, cy: float, size: float, angle: float) -> str:
    c, s, r = math.cos(math.radians(angle)), math.sin(math.radians(angle)), size / 2
    pts = [(cx + dx * c - dy * s, cy + dx * s + dy * c) for dx, dy in ((-r, -r), (r, -r), (r, r), (-r, r))]
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z"


def _wave(t: float, cy: float, amp: float, cycles: float, phase: float) -> float:
    """The sound wave's centre at t in [0, 1] (0 = still in the grid, 1 = fully free): it swells
    as the pixels get free, a fundamental with a little second harmonic."""
    env = math.sin(math.pi * (0.08 + 0.84 * t)) ** 0.6
    return cy + amp * env * (math.sin(2 * math.pi * cycles * t + phase) + 0.25 * math.sin(2 * math.pi * 2 * cycles * t))


def _snap(v: float) -> float:
    return round(v / PITCH) * PITCH


def field(cy: float = 810, amp: float = 130, cycles: float = 2.2, phase: float = 0.4, x_end: float = 860,
          seed: str = "") -> str:
    """The grid (with holes where its pixels left), then the ribbon of pixels: locked to grid cells
    at the right, lifting out, tilting and warming as they go left."""
    stream: dict[str, list[str]] = {SKY: [], MUSTARD: [], TERRA: []}
    taken: set[tuple[float, float]] = set()
    n, rows = 86, 4
    for i in range(n):
        t = i / (n - 1)
        x, y = 1904 - t * (1904 - x_end), _wave(t, cy, amp, cycles, phase)
        free = min(1.0, t * 1.25) ** 1.4
        for k in range(rows):
            if _h("drop", i, k, seed) < 0.15 + 0.58 * free:   # thinning as they get free: individuals, not a mass
                continue
            oy = (k - (rows - 1) / 2) * PITCH * (1 + 0.5 * free)
            gx, gy = _snap(x), _snap(y + oy)
            if x > GRID_X0:
                taken.add((gx, gy))
            jx, jy = (_h("x", i, k, seed) - 0.5) * 44 * free, (_h("y", i, k, seed) - 0.5) * 44 * free
            px, py = gx + (x - gx) * free + jx, gy + (y + oy - gy) * free + jy
            size = CELL + 13 * free * (0.7 + 0.6 * _h("s", i, k, seed))
            angle = (_h("a", i, k, seed) - 0.5) * 90 * free
            colour = SKY if t < 0.34 else MUSTARD if t < 0.68 else TERRA
            stream[colour].append(_square(px, py, size, angle))
    tiers: list[list[str]] = [[], [], []]
    x0, y0, x1, y1 = CLEAR
    for gx in range(GRID_X0 - GRID_X0 % PITCH, 1920 + PITCH, PITCH):
        for gy in range(0, 1080 + PITCH, PITCH):
            if (gx, gy) in taken or (x0 <= gx <= x1 and y0 <= gy <= y1):
                continue
            edge = (gx - GRID_X0) / 300                     # 0 at the soft edge, 1 well inside
            keep = min(1.0, max(0.0, edge)) - _h("g", gx, gy) * 0.55
            if keep <= 0:
                continue
            tier = 0 if keep > 0.55 else 1 if keep > 0.25 else 2
            tiers[tier].append(f"M{gx - CELL / 2:g} {gy - CELL / 2:g}h{CELL}v{CELL}h-{CELL}z")
    grid = "".join(f'<path d="{"".join(sq)}" fill="{WHITE}" fill-opacity="{op}"/>'
                   for sq, op in zip(tiers, (0.13, 0.08, 0.045)))
    moving = "".join(f'<path d="{"".join(sq)}" fill="{c}"/>' for c, sq in stream.items())
    return grid + moving
