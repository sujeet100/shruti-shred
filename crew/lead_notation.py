"""
The sitar line as an LLM reads it — one token per note, its ornaments written in.

Shared by every agent that reads the realised lead (Rasik judges it; the rhythm section plays
around it), so they all see the same thing: a bare swara list hid exactly what makes a raga
recognisable and what an accompanist has to leave room for — whether a komal Ga is held and
swayed or merely passed. Pure.
"""

from __future__ import annotations

from typing import Final

from crew.contracts import Note
from gestures import gesture_named

HOLD_BEATS: Final = 1.0           # a note this long or longer shows its length in the line


def swara_with_oct(swara: str, oct_: int) -> str:
    return swara if oct_ == 0 else f"{swara}({oct_:+d})"


def note_token(n: Note) -> str:
    """One lead note: `(R)g~[1.5]` — kan in front (Parrikar's notation), `{m}` a measured gesture
    visiting m and back, `<>m` a gamak stroke swinging with m, `~` an andolan, `>S` a meend into S,
    `[beats]` a hold."""
    token = swara_with_oct(n.swara, n.oct)
    if n.grace:
        token = f"({''.join(n.grace)}){token}"
    gesture = gesture_named(n.gesture) if n.gesture else None
    if gesture is not None:
        token += f"{{{gesture.toward}}}"
    elif n.gamak_with and n.pitch_path:
        token += f"<>{n.gamak_with}"
    if n.andolan:
        token += "~"
    if n.meend_swara:
        token += f">{n.meend_swara}"
    if n.dur >= HOLD_BEATS:
        token += f"[{n.dur:g}]"
    return token
