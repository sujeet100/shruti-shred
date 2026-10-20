"""Small drawn pictures for the deck: icons and charts as inline SVG, in the Sahaj palette.

Every picture here stands for something the slide argues (a check, a judge, a room, a measured
number), never decoration. Pure: each function returns an SVG string sized by its caller.
"""
from __future__ import annotations

from typing import Final

INDIGO, CARD, LINE, SUNK, MUTED = "#33357D", "#FEFCFA", "#DDD8CF", "#E7E3DB", "#6E6A66"
TERRA, MUSTARD, SKY, PURPLE, DANGER, INK = "#D26F5D", "#E0AA55", "#79B8CC", "#715397", "#C0392B", "#434343"
SANS: Final = "Mulish"
MONO: Final = "JetBrains Mono"


def svg(w: int, h: int, body: str, label: str = "", vb: tuple[int, int] | None = None) -> str:
    """An inline SVG shown at w x h; `vb` is the drawing's own size when it is drawn in fixed
    coordinates (an icon), so it scales instead of clipping."""
    vw, vh = vb or (w, h)
    return f'<svg aria-label="{label}" style="width:{w}px;height:{h}px" viewBox="0 0 {vw} {vh}">{body}</svg>'


def text(x: float, y: float, s: str, size: int = 32, color: str = INK, weight: int = 700,
         anchor: str = "start", family: str = SANS) -> str:
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{s}</text>')


# ---- icons ------------------------------------------------------------------------------
def braces_check(w: int = 220, h: int = 180, color: str = INDIGO) -> str:
    """Code that decides: a tick between braces."""
    return svg(w, h, f'<g stroke="{color}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round" fill="none">'
                     f'<path d="M60 20 C34 20 34 36 34 58 L34 74 C34 84 26 90 14 90 C26 90 34 96 34 106 L34 122 C34 144 34 160 60 160"/>'
                     f'<path d="M160 20 C186 20 186 36 186 58 L186 74 C186 84 194 90 206 90 C194 90 186 96 186 106 L186 122 C186 144 186 160 160 160"/></g>'
                     f'<path d="M74 92 L100 118 L148 62" stroke="{MUSTARD}" stroke-width="18" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
               "code decides", (220, 180))


def stars(n_on: int = 4, w: int = 300, h: int = 70) -> str:
    """A judge's score: five stars, `n_on` lit."""
    def star(cx: float, on: bool) -> str:
        pts = []
        import math
        for k in range(10):
            r = 30 if k % 2 == 0 else 13
            a = math.radians(-90 + 36 * k)
            pts.append(f"{cx + r * math.cos(a):.1f},{35 + r * math.sin(a):.1f}")
        return f'<polygon points="{" ".join(pts)}" fill="{MUSTARD if on else SUNK}"/>'
    return svg(w, h, "".join(star(32 + i * 58, i < n_on) for i in range(5)), f"{n_on} of 5 stars", (300, 70))


def crowd(w: int = 320, h: int = 170) -> str:
    """The room: heads and shoulders, the ear that decides."""
    people = [(50, 120, TERRA), (120, 100, SKY), (190, 120, MUSTARD), (260, 100, PURPLE)]
    body = "".join(f'<circle cx="{x}" cy="{y - 48}" r="24" fill="{c}"/><path d="M{x - 38} {y + 40} A38 38 0 0 1 {x + 38} {y + 40} Z" fill="{c}"/>'
                   for x, y, c in people)
    return svg(w, h, body, "the room", (320, 170))


def bubble(w: int = 200, h: int = 160, color: str = SKY) -> str:
    """A model: a speech bubble with three dots."""
    return svg(w, h, f'<circle cx="{w / 2}" cy="{h / 2 - 8}" r="{min(w, h) / 2 - 14}" fill="{color}"/>'
                     f'<path d="M{w / 2 - 36} {h - 34} L{w / 2 - 58} {h - 4} L{w / 2 - 6} {h - 26} Z" fill="{color}"/>'
                     + "".join(f'<circle cx="{w / 2 + dx}" cy="{h / 2 - 8}" r="11" fill="{CARD}"/>' for dx in (-34, 0, 34)),
               "a model")


def doc(w: int = 150, h: int = 180, label: str = "data") -> str:
    """A data file with its folded corner."""
    return svg(w, h, f'<path d="M14 10 H100 L136 46 V170 H14 Z" fill="{CARD}" stroke="{INDIGO}" stroke-width="6" stroke-linejoin="round"/>'
                     f'<path d="M100 10 V46 H136" fill="none" stroke="{INDIGO}" stroke-width="6" stroke-linejoin="round"/>'
                     + "".join(f'<rect x="34" y="{70 + i * 24}" width="{78 - (i % 2) * 22}" height="9" rx="4" fill="{SKY}"/>' for i in range(4)),
               label, (150, 180))


def wave(w: int = 260, h: int = 120, color: str = INDIGO) -> str:
    """Sound: a short waveform."""
    import math
    pts = " ".join(f"{x},{h / 2 + math.sin(x / 9) * (h / 2 - 12) * math.sin(math.pi * x / w):.1f}" for x in range(0, w + 1, 3))
    return svg(w, h, f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round"/>', "sound")


def stamp(word: str, color: str = DANGER, w: int = 360, h: int = 110, tilt: float = -8) -> str:
    """A rubber stamp over evidence."""
    return svg(w, h, f'<g transform="rotate({tilt} {w / 2} {h / 2})"><rect x="12" y="14" width="{w - 24}" height="{h - 28}" rx="12" '
                     f'fill="none" stroke="{color}" stroke-width="7"/>{text(w / 2, h / 2 + 15, word, 44, color, 800, "middle")}</g>', word)


def arrow(w: int = 120, h: int = 60, color: str = MUTED, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="4 14"' if dashed else ""
    return svg(w, h, f'<path d="M8 {h / 2} H{w - 30}" stroke="{color}" stroke-width="8" stroke-linecap="round"{dash}/>'
                     f'<path d="M{w - 40} {h / 2 - 20} L{w - 10} {h / 2} L{w - 40} {h / 2 + 20}" fill="none" stroke="{color}" '
                     f'stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>', "")


def cross(size: int = 70, color: str = DANGER) -> str:
    return svg(size, size, f'<g stroke="{color}" stroke-width="12" stroke-linecap="round"><path d="M14 14 L{size - 14} {size - 14}"/>'
                           f'<path d="M{size - 14} 14 L14 {size - 14}"/></g>', "no")


# ---- charts -------------------------------------------------------------------------------
def hbars(rows: list[tuple[str, float, str]], w: int = 900, unit: str = "%", vmax: float = 100,
          rh: int = 96) -> str:
    """Horizontal bars: (label, value, colour), labels left, values at the bar's end."""
    lw = 300
    body = ""
    for i, (lab, v, c) in enumerate(rows):
        y = i * rh
        bw = (w - lw - 140) * v / vmax
        bh = rh * 0.6
        body += (text(0, y + rh / 2 + 14, lab, 40, INDIGO, 800)
                 + f'<rect x="{lw}" y="{y + (rh - bh) / 2:.0f}" width="{w - lw - 140}" height="{bh:.0f}" rx="12" fill="{SUNK}"/>'
                 + f'<rect x="{lw}" y="{y + (rh - bh) / 2:.0f}" width="{bw:.0f}" height="{bh:.0f}" rx="12" fill="{c}"/>'
                 + text(lw + bw + 16, y + rh / 2 + 16, f"{v:g}{unit}", 44, c, 800))
    return svg(w, rh * len(rows), body, "bar chart")


def lines(series: list[tuple[str, list[float], str]], xlabels: list[str], w: int = 700, h: int = 330,
          vmax: float = 60) -> str:
    """A small line chart: (label, values, colour) per series."""
    x0, y0, x1, y1 = 40, 50, w - 230, h - 60
    X = lambda i, n: x0 + (x1 - x0) * i / (n - 1)
    Y = lambda v: y1 - (y1 - y0) * v / vmax
    body = f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{LINE}" stroke-width="4"/>'
    for i, lab in enumerate(xlabels):
        body += text(X(i, len(xlabels)), h - 18, lab, 28, MUTED, 700, "middle")
    for lab, vals, c in series:
        pts = " ".join(f"{X(i, len(vals)):.0f},{Y(v):.0f}" for i, v in enumerate(vals))
        body += f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
        for i, v in enumerate(vals):
            body += f'<circle cx="{X(i, len(vals)):.0f}" cy="{Y(v):.0f}" r="11" fill="{c}"/>'
        body += text(x1 + 22, Y(vals[-1]) + 12, lab, 32, c, 800)
        body += text(X(len(vals) - 1, len(vals)), Y(vals[-1]) - 22, f"{vals[-1]:g}", 32, c, 800, "middle")
    return svg(w, h, body, "line chart")


def vbars(values: list[float], color: str = TERRA, w: int = 720, h: int = 300, vmax: float = 20,
          labels: list[str] | None = None) -> str:
    """Vertical bars, one per call."""
    n = len(values)
    bw = (w - 40) / n - 14
    body = f'<line x1="0" y1="{h - 40}" x2="{w}" y2="{h - 40}" stroke="{LINE}" stroke-width="4"/>'
    for i, v in enumerate(values):
        x = 20 + i * (bw + 14)
        bh = (h - 70) * v / vmax
        body += f'<rect x="{x:.0f}" y="{h - 40 - bh:.0f}" width="{bw:.0f}" height="{bh:.0f}" rx="8" fill="{color}"/>'
        if labels:
            body += text(x + bw / 2, h - 8, labels[i], 26, MUTED, 700, "middle")
    return svg(w, h, body, "bar chart")


def tracks(rows: list[tuple[str, list[tuple[float, float]], str]], w: int = 760, h: int = 260) -> str:
    """Parts as lanes of bars (start, length in 0..1): misaligned parts show they never listened."""
    rh = h / len(rows)
    body = ""
    for i, (lab, segs, c) in enumerate(rows):
        y = i * rh
        body += f'<rect x="0" y="{y + 10:.0f}" width="{w}" height="{rh - 20:.0f}" rx="10" fill="{SUNK}"/>'
        for s0, ln in segs:
            body += f'<rect x="{s0 * w:.0f}" y="{y + 18:.0f}" width="{ln * w:.0f}" height="{rh - 36:.0f}" rx="8" fill="{c}"/>'
    return svg(w, h, body, "parts on a timeline")
