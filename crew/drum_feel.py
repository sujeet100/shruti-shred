"""
The kit's FEEL per section — chosen by the rhythm-section call, played by code (2026-10-20).

The drums are code and lock to the guitar's attacks, but WHICH groove a section gets (tight verse,
full drive, climax wash, half-time) was a fixed lookup by section kind and gat role — so the one
agent that hears the finished sitar and writes the guitar had no say in how hard the kit pushes
under it, and a song-form section with no gat role got no energy shaping at all (GPT's review).
Now the rhythm section names a `drum_feel` per section; `crew/groove.py` plays it, and
`crew/dynamics.py` takes the section's energy from it where the chart declares no gat role. A
section without one keeps code's default. Pure.
"""
from __future__ import annotations

from typing import Final

from crew.contracts import Arrangement

# A feel's energy for the dynamics arc, on `crew/dynamics.py`'s 0-1 scale — used only where a
# section has no gat role (a gat role keeps its own place in the arc).
FEEL_ENERGY: Final[dict[str, float]] = {"verse": 0.60, "half": 0.75, "drive": 0.85, "climax": 1.00}


def drum_feels(arr: Arrangement) -> dict[int, str]:
    """Section index -> the feel the rhythm section chose: its own, else the part it replays
    (`same_as`). Empty without a composed rhythm section. Pure."""
    rs = arr.rhythm_section
    if rs is None:
        return {}
    parts = {p.section: p for p in rs.parts}
    feels: dict[int, str] = {}
    for p in rs.parts:
        feel = p.drum_feel
        if feel is None and p.same_as is not None and p.same_as in parts:
            feel = parts[p.same_as].drum_feel
        if feel is not None:
            feels[p.section] = feel
    return feels
