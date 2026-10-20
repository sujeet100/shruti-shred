"""The twelve notes as a keyboard, in the deck's Sahaj style — one drawing for the music-101 slides
AND for the frames of their clips (`talk/audio/keyboard_video.py`), so each clip sits seamlessly on
its slide and every key appears or lights at the moment its note sounds.

Geometry is fixed (the clips crop `KB_REGION` out of a full-slide screenshot).
"""
from __future__ import annotations

from typing import Final

PAGE, CARD, LINE, SUNK = "#F3F0EA", "#FEFCFA", "#DDD8CF", "#E7E3DB"
INDIGO, MUTED, TERRA, MUSTARD, SKY = "#33357D", "#6E6A66", "#D26F5D", "#E0AA55", "#79B8CC"
LIGHT: Final = "#FEFCFA"
DEVA: Final = "'Noto Sans Devanagari', sans-serif"
SANS: Final = "'Mulish', Arial, sans-serif"

KB_X0, KB_W, KB_H, KB_BW, KB_BH, KB_Y = 236, 206, 340, 124, 210, 290
KB_REGION: Final = (228, 282, 1460, 356)            # x, y, w, h of the keyboard on the slide = the clip's crop
WHITES: Final = [("S", "सा", "Sa"), ("R", "रे", "Re"), ("G", "ग", "Ga"), ("m", "म", "Ma"), ("P", "प", "Pa"),
                 ("D", "ध", "Dha"), ("N", "नि", "Ni")]
# (key, the white key it follows, Devanagari, latin, colour): komal (flat) in terracotta, tivra (sharp) in sky
BLACKS: Final = [("r", 0, "<u>रे</u>", "re", TERRA), ("g", 1, "<u>ग</u>", "ga", TERRA), ("M", 3, "म॑", "Ma", SKY),
                 ("d", 4, "<u>ध</u>", "dha", TERRA), ("n", 5, "<u>नि</u>", "ni", TERRA)]
SHUDDHA: Final = frozenset(k for k, *_ in WHITES)
KOMAL: Final = frozenset({"r", "g", "d", "n"})
ALL: Final = SHUDDHA | KOMAL | {"M"}


def keyboard(visible: set[str], lit: set[str] | str | None = None, achal: bool = False,
             dim: set[str] | None = None) -> list[str]:
    """The keys as pinned divs: `visible` keys drawn, `lit` ones glowing mustard, `dim` ones faded
    (a raga's forbidden notes), `achal` rings Sa and Pa (the two notes that never move). White keys
    first, so the black keys sit on top of them."""
    lit_set = {lit} if isinstance(lit, str) else set(lit or ())
    dim = dim or set()
    out: list[str] = []
    for i, (k, d, l) in enumerate(WHITES):
        if k not in visible:
            continue
        on, ring, off = k in lit_set, achal and k in ("S", "P"), k in dim
        bg = MUSTARD if on else (SUNK if off else CARD)
        ink = MUTED if off else INDIGO
        out.append(f'<div style="position:absolute;left:{KB_X0 + i * KB_W}px;top:{KB_Y}px;width:{KB_W - 8}px;height:{KB_H}px;'
                   f'background:{bg};border:{8 if ring else 3}px solid {MUSTARD if ring else LINE};border-radius:0px 0px 18px 18px;'
                   f'display:flex;flex-direction:column;justify-content:end;align-items:center;padding:0px 0px {12 if ring else 16}px 0px">'
                   f'<p style="font-family:{DEVA};font-size:52px;line-height:1.2;color:{ink}">{d}</p>'
                   f'<p style="font-family:{SANS};font-size:30px;font-weight:700;color:{ink}">{l}</p></div>')
    for k, after, d, l, c in BLACKS:
        if k not in visible:
            continue
        on, off = k in lit_set, k in dim
        x = KB_X0 + (after + 1) * KB_W - KB_BW // 2 - 4
        bg = MUSTARD if on else ("#8E8FBF" if off else INDIGO)
        ink = INDIGO if on else LIGHT
        out.append(f'<div style="position:absolute;left:{x}px;top:{KB_Y}px;width:{KB_BW}px;height:{KB_BH}px;background:{bg};'
                   f'border:4px solid {c};border-radius:0px 0px 14px 14px;display:flex;flex-direction:column;justify-content:end;'
                   f'align-items:center;padding:0px 0px 12px 0px">'
                   f'<p style="font-family:{DEVA};font-size:44px;line-height:1.2;color:{ink}">{d}</p>'
                   f'<p style="font-family:{SANS};font-size:30px;font-weight:700;color:{ink}">{l}</p></div>')
    return out
