"""
THE TAKEOVER — when the sitar stops and the guitar carries the gat, the guitar plays the MUKHADA.

Sujit's review of fusion_20261012_213455 (2026-10-12): at 1:20 the sitar stopped and the guitars
played an independent low riff; the composition seemed to change pieces. A section the composer
marks `form_role: "takeover"` is the guitarist arranging the ACTUAL realised head (the chart's
`seed_hook`, stored by the Flow from the lead's events): low power chords where it lands,
mid-register single notes where it moves, its strokes and pauses kept
(`riff_from_mukhada.interpret_mukhada`), the second avartan developing the first and ending on the
head's own approach into the sam where the sitar returns (`riff_statements.takeover_cycles`).

One post-pass in the band assembly, so EVERY path obeys it — the per-section riff, the
rhythm-section call, gat_first or riff_first: the head is the source of truth, never a regenerated
riff. Without a realised head the section keeps whatever the guitar wrote. Pure.
"""

from __future__ import annotations

from typing import Final

from crew.contracts import Arrangement, Layer, Note
from crew.generators import VOICES, SectionSpan, section_spans
from crew.head_anatomy import accent_beats
from crew.riff import place_cycles
from crew.riff_from_mukhada import TAKEOVER, takeover_pattern
from crew.riff_statements import takeover_cycles

_RHYTHM: Final = "rhythm"
_EPS: Final = 1e-6


def takeover_spans(arr: Arrangement) -> list[SectionSpan]:
    """The sections where the guitar carries the gat."""
    return [s for s in section_spans(arr)
            if s.section.form_role == TAKEOVER and _RHYTHM in s.section.layers]


def _inside(n: Note, spans: list[SectionSpan]) -> bool:
    return any(s.start - _EPS <= n.start < s.end - _EPS for s in spans)


def with_takeover(rhythm: Layer | None, arr: Arrangement) -> Layer | None:
    """The rhythm layer with every takeover section playing the arranged head (see the module
    docstring). Unchanged when there is no takeover or no realised head. Pure."""
    spans = takeover_spans(arr)
    pattern = takeover_pattern(arr, arr.seed_hook) if spans else None
    if pattern is None:
        return rhythm
    accents = accent_beats(arr)
    notes = [n for n in (rhythm.notes if rhythm else []) if not _inside(n, spans)]
    for span in spans:
        cycles = takeover_cycles(list(pattern.notes), span.section.bars, raga=arr.raga,
                                 accents=accents, cycle_beats=arr.beats_per_bar)
        notes += place_cycles(cycles, start=span.start, cycle_beats=arr.beats_per_bar,
                              register=arr.registers[_RHYTHM], accent_beats=set(accents),
                              raga=arr.raga)
    notes.sort(key=lambda n: n.start)
    if rhythm is not None:
        return rhythm.model_copy(update={"notes": notes})
    voice = VOICES[_RHYTHM]
    return Layer(role=_RHYTHM, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)
