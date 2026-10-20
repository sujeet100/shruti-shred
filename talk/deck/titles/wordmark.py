"""Outline a line of text in a font as one SVG path (shaped with HarfBuzz), so a display face
can appear on a slide without spending one of the deck's four typeface slots.

    uv run --with fonttools --with uharfbuzz python wordmark.py FONT.ttf "TEXT" SIZE OUT.path [AXIS=VALUE ...]

Prints "width height ascent" in px. Variable fonts are instanced first (e.g. wght=600 ROND=100).
"""
from __future__ import annotations

import io
import sys

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


def load(path: str, axes: dict[str, float]) -> tuple[TTFont, bytes]:
    tt = TTFont(path)
    if axes and "fvar" in tt:
        tt = instantiateVariableFont(tt, axes)
    buf = io.BytesIO()
    tt.save(buf)
    data = buf.getvalue()
    return TTFont(io.BytesIO(data)), data


def wordmark(path: str, text: str, size: float, axes: dict[str, float]) -> tuple[str, float, float, float]:
    tt, data = load(path, axes)
    font = hb.Font(hb.Face(data))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})
    gs, order = tt.getGlyphSet(), tt.getGlyphOrder()
    k = size / tt["head"].unitsPerEm
    asc, desc = tt["hhea"].ascent * k, -tt["hhea"].descent * k
    pen, x = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip(".")), 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        tp = TransformPen(pen, (k, 0, 0, -k, x + pos.x_offset * k, asc - pos.y_offset * k))
        gs[order[info.codepoint]].draw(tp)
        x += pos.x_advance * k
    return pen.getCommands(), x, asc, desc


if __name__ == "__main__":
    axes = {a.split("=")[0]: float(a.split("=")[1]) for a in sys.argv[5:]}
    d, w, a, de = wordmark(sys.argv[1], sys.argv[2], float(sys.argv[3]), axes)
    print(f"{w:.1f} {a + de:.1f} {a:.1f}")
    open(sys.argv[4], "w").write(d)
