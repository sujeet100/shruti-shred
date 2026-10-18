"""
What the gat head is handed of the seed — the MOTIF experiment's switch (Sujit, 2026-10-18).

Every seed in the cross-model run chose the same head: the seed picks a cell from the raga's facts
(Darbari's pakad, avaroha and chalan all close on g m R S) and the head prompt then says "derive the
mukhada from it", with the seed's stroke line to play. Two models given that funnel wrote the same
head. The experiment asks each composer to DEFINE its own motif and develop the gat from it, with
one arm still handed the seed's cell and stroke line and the other not:

  * default (no mode) — today's prompts, byte for byte;
  * GUIDED — the seed's cell, stroke line and riff as today, plus "define your motif first";
  * FREE   — no motif, no cell, no stroke line, no riff notes; the sam swara and the idea's mood
             stay. The stroke FRAME (the Masitkhani grid) stays in both: it is the form's knowledge,
             like the tala, not the seed's choice.

Set for a block with `head_brief(mode)`, read by the prompt builders (`crew/lead.py`,
`crew/anchor.py`) — the same ContextVar seam as `config.composer_override`. Pure otherwise.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final, Literal

Mode = Literal["guided", "free"]
_MODE: ContextVar[Mode | None] = ContextVar("head_brief", default=None)

_DEFINE: Final = ("Define the head's MOTIF first, as phrase_plan.seed: a short figure (its swaras, rhythm "
                  "and strokes) that only this raga plays — then develop the mukhada FROM it.")
_DEFAULT_MOTIF_LINE: Final = "THE MOTIF (your seed — quote/derive the mukhada from it and the raga's pakad): {motif}"
_DEFAULT_CORE_IDEA: Final = (
    "THE SONG'S CORE IDEA (when the Composer seeded the piece, YOU wrote it — build on it. When it\n"
    "holds a hook, that hook IS the mukhada: copy it verbatim and compose the other parts around it.\n"
    "When it holds the gat HEAD'S IDEA, the mukhada is yours to compose FROM it, with your full\n"
    "attention: its first note the sam swara, its core cell recurring, the idea's stroke line as the\n"
    "mukhada's stroke_line — refine it only where the melody truly asks):")
_FREE_CORE_IDEA: Final = (
    "THE SONG'S CORE IDEA (when the Composer seeded the piece, YOU wrote it — build on it). It holds\n"
    "the gat HEAD'S IDEA: compose the mukhada FROM it, with your full attention — its first note the\n"
    "sam swara; the motif and the stroke line are yours to define:")


@contextmanager
def head_brief(mode: Mode) -> Iterator[None]:
    """Brief the gat head in `mode` for the duration of the block."""
    token = _MODE.set(mode)
    try:
        yield
    finally:
        _MODE.reset(token)


def mode() -> Mode | None:
    return _MODE.get()


def withheld() -> bool:
    """True when the head is NOT handed the seed's motif, cell, stroke line or riff (FREE)."""
    return _MODE.get() == "free"


def motif_line(motif: list[str]) -> str:
    """The gat prompt's MOTIF line."""
    current = _MODE.get()
    if current == "free":
        return (f"THE MOTIF is yours to define — none is given. {_DEFINE} Use the pakad and chalan as "
                "vocabulary to choose from, not as a script to quote.")
    line = _DEFAULT_MOTIF_LINE.format(motif=" ".join(motif))
    if current == "guided":
        line += f"\n{_DEFINE} Build it from the seed's cell if that serves the piece."
    return line


def motif_value(motif: list[str]) -> str:
    """The motif as the lead prompt's "motif (the common melodic seed)" field shows it."""
    return "(none given — the gat head defines it)" if withheld() else " ".join(motif)


def core_idea_header() -> str:
    """The gat prompt's paragraph introducing the seed's core idea."""
    return _FREE_CORE_IDEA if withheld() else _DEFAULT_CORE_IDEA
