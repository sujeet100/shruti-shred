"""The DevDay title slide (2026-10-18), on last year's DevDay talk template.

The 2025 data-engineering talk slides: an indigo field, pipes running in from the left edge (a
different shape per talk), the title in Zilla Slab in a column to their right, a short description
in Mulish, and the DevDay corner mark bottom right. This year's theme is Agentic AI, so the pipes
title's picture is DevDay's own LED pixels gaining agency (`titles/pixel_field.py`). The DevDay logo is
the official file (`titles/devday-logo.png`, uploaded; its blob id in `titles/assets.json`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from motif import FIELD, SKY, SOFT, WHITE
from titles.bot import bot

TITLES: Final = Path(__file__).resolve().parent / "titles"
SERIF: Final = "'Zilla Slab', Georgia, serif"
SANS: Final = "'Mulish', Arial, sans-serif"
COLUMN: Final = 560                           # the text column's left edge, after the 2025 template


DEVDAY_LOGO: Final = json.loads((TITLES / "assets.json").read_text())["devday-logo"]   # the official file


def devday(left: int, top: int, width: int = 432) -> str:
    """The official DevDay logo (white, transparent), cropped to its lettering (712 x 140)."""
    return (f'<img src="{DEVDAY_LOGO}" alt="DevDay" style="position:absolute;left:{left}px;top:{top}px;'
            f'width:{width}px;height:{round(width * 140 / 712)}px;object-fit:contain">')


def sahaj_logo(left: int, top: int, height: int = 84) -> str:
    svg = (TITLES / "sahaj-logo.inline.svg").read_text()
    for old, new in (("#33357d", WHITE), ("#27235a", SOFT), ("#707171", SOFT)):
        svg = svg.replace(f'fill="{old}"', f'fill="{new}"')
    width = round(height * 162.33 / 72.859)
    return svg.replace("<svg ", f'<svg aria-label="Sahaj Software" style="position:absolute;left:{left}px;'
                       f'top:{top}px;width:{width}px;height:{height}px" ', 1)


def s_title() -> str:
    """Title, author, branding, and one picture: the DevDay bot, playing a sitar."""
    art = (f'<svg aria-label="The DevDay bot, a small geometric robot, plays a sitar and nods its head in time" '
           f'style="position:absolute;left:0px;top:0px;width:1920px;height:1080px" viewBox="0 0 1920 1080">'
           f'{bot(1300, 300)}</svg>')
    inner = [art, devday(128, 120),
             f'<h1 style="position:absolute;left:128px;top:290px;width:1100px;font-family:{SERIF};font-size:112px;'
             f'font-weight:700;line-height:1.05;color:{WHITE}">Lessons from an<br>Agentic AI<br>Raga-Metal Band</h1>',
             f'<p style="position:absolute;left:128px;top:820px;width:700px;font-size:44px;font-weight:700;color:{WHITE}">Sujit Kamthe</p>',
             sahaj_logo(128, 930, 72)]
    style = f"background:{FIELD};color:{WHITE};font-family:{SANS};padding:128px;display:flex;flex-direction:column"
    return (f'<section id="title" data-transition="fade" style="{style}">\n' + "\n".join(inner)
            + "\n<aside>On screen as the room fills. The DevDay bot, this talk's version: a musician playing a sitar, "
              "nodding in time (it is a metal band).</aside>\n</section>\n")


def title_slides() -> dict[str, str]:
    return {"title": s_title()}
