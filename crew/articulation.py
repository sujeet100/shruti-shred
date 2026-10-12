"""
PHRASE-AWARE ARTICULATION — the rhythm guitar plays around what the sitar is doing.

Measured on `fusion_20261012_152048` (2026-10-12): not one rhythm-guitar note in the piece lasted
longer than a beat (176 strokes, half of them palm-muted), and 70% of the sitar's attacks under the
head landed on a guitar attack. The riff fitted the melody and ignored it: it struck through every
andolan and gamak, and never let a chord ring under a sitar phrase. Sujit's own Yaman recording
does the opposite (a GPT review of it, and his 2026-07-16 rule that the guitar's melodic budget
is inverse to the lead's): the guitar holds a chord while the sitar sings, gets out of the way of
an ornament, and hits hard where a phrase arrives.

So, beat by beat, under a section the sitar leads:
  * the SAM is always struck — the cycle's anchor;
  * an attack INSIDE an expressive sitar event (a note held a beat or more, an andolan, a gamak,
    a gesture, a meend), or inside a sitar BURST (`density.BUSY_MOVES` swara changes in the beat),
    is not played: the chord already sounding is opened up and RINGS through it;
  * an attack on the ARRIVAL of an expressive sitar note is opened up (no palm mute): a chord
    lands with the phrase;
  * everywhere else — the sitar resting or moving plainly — the riff plays as written, which is
    where it answers the sitar.

Only attacks and sustain change, never a pitch: Sujit kept the riff-sitar grinds by ear
(2026-10-11), so a ringing chord is always one the riff was already playing. Sections the guitar
owns are left alone — guitar-led sections, the breakdown and tihai, and the taans, where Sujit's
rule is that the band simplifies harmonically, not rhythmically (f65dbce). The bass and the kit
keep following the riff as written (`band_layers`), so the drive stays while the guitar rings.

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from typing import Final, Sequence

from crew.coexistence import LeadStability, stability_of
from crew.contracts import Arrangement, Layer, Note, Section
from crew.density import BUSY_MOVES, moves_per_beat
from crew.generators import section_spans, total_beats
from crew.riff_from_mukhada import guitar_led, is_contrast

_EPS: Final = 1e-6
_OWN_ROLES: Final = frozenset({"taan_long", "taan_short"})   # the band drives there (f65dbce)
_PITCH_MOVES: Final = frozenset({"slide", "long_slide", "pick_scrape", "bend",
                                 "hammer_on", "pull_off"})


def sitar_leads(section: Section) -> bool:
    """The sitar sings over the riff here, so the riff plays around it."""
    return not (guitar_led(section) or is_contrast(section) or section.form_role in _OWN_ROLES)


def _expressive(note: Note) -> bool:
    """A sitar note the ear follows THROUGH its length — held, swung, or bent."""
    return bool(not note.chikari and (stability_of(note) is LeadStability.HELD or note.andolan
                                      or note.gamak_with or note.gesture or note.meend_swara))


def expressive_spans(melody: Sequence[Note]) -> list[tuple[float, float]]:
    """(start, end) of each expressive sitar event, consecutive notes of one swara merged (a gamak
    cell struck twice is one event). Pure."""
    spans: list[tuple[float, float, str, int]] = []
    for note in sorted((n for n in melody if _expressive(n)), key=lambda n: n.start):
        end = note.start + note.dur
        last = spans[-1] if spans else None
        if last and (last[2], last[3]) == (note.swara, note.oct) and note.start <= last[1] + _EPS:
            spans[-1] = (last[0], max(last[1], end), last[2], last[3])
        else:
            spans.append((note.start, end, note.swara, note.oct))
    return [(a, b) for a, b, _, _ in spans]


def _inside(t: float, spans: Sequence[tuple[float, float]]) -> bool:
    return any(a + _EPS < t < b - _EPS for a, b in spans)


def _arrives(t: float, spans: Sequence[tuple[float, float]]) -> bool:
    return any(abs(t - a) < _EPS for a, _ in spans)


def _opened(note: Note, end: float | None = None) -> Note:
    """The stroke left to ring: no palm mute, no pitch gesture, held to `end` when given."""
    update: dict[str, object] = {}
    if note.technique == "palm_mute" or note.technique in _PITCH_MOVES:
        update["technique"] = None
    if end is not None and end > note.start + note.dur + _EPS:
        update["dur"] = round(end - note.start, 4)
    return note.model_copy(update=update) if update else note


def _section_of(t: float, arr: Arrangement) -> tuple[float, Section] | None:
    """(start, section) of the section sounding at `t`."""
    return next(((s.start, s.section) for s in section_spans(arr)
                 if s.start - _EPS <= t < s.end - _EPS), None)


def _on_sam(t: float, section_start: float, cycle: float) -> bool:
    phase = (t - section_start) % cycle
    return phase < _EPS or cycle - phase < _EPS


class _SitarMap:
    """Where the sitar is singing something the guitar should not strike through."""

    def __init__(self, sitar: Sequence[Note], arr: Arrangement) -> None:
        self.spans = expressive_spans(sitar)
        moves = moves_per_beat(list(sitar), int(total_beats(arr)) + 1)
        self.busy = frozenset(beat for beat, m in enumerate(moves) if m >= BUSY_MOVES)

    def quiet(self, t: float) -> bool:
        """The guitar holds its chord here instead of striking a new one."""
        return _inside(t, self.spans) or int(t + _EPS) in self.busy

    def arrival(self, t: float) -> bool:
        return _arrives(t, self.spans)


def _ring_through(out: list[Note], held: list[int], group: list[Note]) -> None:
    """The ringing stroke covers this one instead of it being played."""
    end = max(n.start + n.dur for n in group)
    for i in held:
        out[i] = _opened(out[i], end)


def articulate(rhythm: Layer | None, melody: Sequence[Layer], arr: Arrangement) -> Layer | None:
    """The rhythm layer played around the sitar (see the module docstring). None in, None out;
    a piece with no sitar line is returned unchanged. Pure."""
    sitar = sorted((n for ly in melody for n in (ly.notes or []) if not n.chikari),
                   key=lambda n: n.start)
    if rhythm is None or not rhythm.notes or not sitar:
        return rhythm
    sitar_map = _SitarMap(sitar, arr)
    out: list[Note] = []
    held: list[int] = []                      # indices in `out` of the stroke now ringing
    for start in sorted({n.start for n in rhythm.notes}):
        group = [n for n in rhythm.notes if abs(n.start - start) < _EPS]
        where = _section_of(start, arr)
        led = where is not None and sitar_leads(where[1])
        if led and held and out[held[0]].start >= where[0] - _EPS and sitar_map.quiet(start) \
                and not _on_sam(start, where[0], arr.beats_per_bar):
            _ring_through(out, held, group)
            continue
        held = list(range(len(out), len(out) + len(group))) if led else []
        out.extend(_opened(n) if led and sitar_map.arrival(start) else n for n in group)
    return rhythm.model_copy(update={"notes": out})
