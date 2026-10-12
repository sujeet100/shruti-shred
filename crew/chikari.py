"""
CHIKARI — the sitar's drone-string strokes, placed by the phrase and rung on their own strings.

A sitarist's right hand does two jobs. It plucks the melody string, and in the matras the melody
leaves empty it sweeps the CHIKARI, the high drone strings tuned to the raga
(`raga.chikari_swaras`: strings 1-2 Sa, 3-4 the raga's colour). Those strokes are punctuation
and pulse rather than melody: they answer a phrase ending, fill a rest, keep time under a held
note, and ring on until the next stroke re-strikes them.

Until now a chikari rendered as ONE taar-Sa note on the melodic sitar channel, a melody note in
disguise that every meend, andolan or gesture on that channel bent along with it (the pitch
wheel is channel-wide). This module makes it the instrument it is, in two halves:

  * WHERE (`chikari_strokes`, a pure planner) reads the PLACED sitar line and each section's
    role, never a fixed grid:
      - ALAP (the intro, or an alaap-kind section): sparse — at most one stroke an avartan, a
        breath after a phrase ENDS, in the cycle's longest silence;
      - HEAD (the mukhada, or the song form's hook): ONE pattern derived from the head's own
        right hand — the matras its stroke_line leaves empty ("-", rests, held notes) — so every
        return of the head brings the same chikari back with it (melodic + chikari identity);
      - LIGHT (manjha, antara, every other sitar section): one stroke an avartan, preferring
        the silence straight after a phrase, then a held note, for continuity;
      - CLIMAX (taan_long): a little more — two an avartan, still only in empty matras. Never
        jhala on every beat: the code-built jhala's own chikari strokes already do that job.
    The composer's own `bol: "chikari"` (and the jhala's) are always kept, count toward each
    cap, and are never doubled: a planned stroke lands only in a matra with no attack at all.
  * HOW (`chikari_layer`): each stroke is a fast strum, string 1 (the high Sa) first and a
    touch strongest, a few ms per string, on its OWN channel that no wheel gesture touches.
    The attack is the note-on and the resonance is the note's length — a ringing string needs
    no new note, so it decays in the sample until the next stroke re-strikes it or a cap.

`right_hand_rhythm` and `head_right_hand` expose the COMBINED right hand (melody strokes plus
chikari strokes) for a section or for one avartan of the head, for a reader such as the riff
that may later lock to the head's whole right hand rather than its melody alone.

No source measures chikari density, strum speed or ring, so every number below is inference for
the ear to tune. Pure — Notes in, Notes out.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

from crew.anchor import is_song_hook
from crew.contracts import Arrangement, Layer, Note, Section, SectionKind
from crew.generators import VOICES, SectionSpan, section_spans
from raga import CHIKARI_STRING_WEIGHTS, chikari_swaras

CHIKARI_ROLE: Final = "chikari"
_LEAD_ROLE: Final = "lead"
_EPS: Final = 1e-6

# A strum, not a chord: four strings ~6 ms apart sweep in ~18 ms, which the ear hears as ONE
# bright stroke with a grain to it; a block chord (0 ms) reads as a keyboard, and past ~30 ms
# the strings separate into an arpeggio.
STRUM_MS: Final = 6.0
# A stroke CODE planned sounds only the two Sa strings: four strings on every planned stroke read
# as "a layered open-string chord, a resonance wash" rather than chikari (GPT, 2026-10-12). The
# raga's colour strings sound on the strokes the COMPOSER wrote — an intentional accent.
PLANNED_STRINGS: Final = 2
# Two strokes closer than this crowd each other: the chikari punctuates, it does not chatter.
MIN_SPACING_BEATS: Final = 2.0
# The alap: a stroke waits this long after a phrase ends, needs a silence at least this long to
# be worth punctuating, and must leave this much before the next phrase.
ALAP_BREATH_BEATS: Final = 1.0
ALAP_MIN_GAP_BEATS: Final = 2.0
ALAP_TAIL_BEATS: Final = 1.0


class SectionRole(Enum):
    """How busy the chikari is in a section — decided by the section's place in the form."""
    ALAP = "alap"
    HEAD = "head"
    LIGHT = "light"
    CLIMAX = "climax"


@dataclass(frozen=True)
class _Policy:
    per_cycle: int     # most strokes (written + planned) in one avartan
    vel: int           # string 1's velocity on a planned stroke (the others weigh in under it)
    ring_ms: float     # how long a stroke rings before the next must re-strike it


# The alap lets its few strokes ring longest and softest; the head's pattern is its pulse; the
# climax strikes hardest and rings shortest, because it is busy and the band is loud.
# Sujit, 2026-10-12, on fusion_20261012_213455: "the chikari sounds a bit thin — it needs more
# reverb/sustain, and the volume felt less". Measured: a median stroke of 64 against the sitar's
# 86, on a channel 16 below it, cut off after 1.6 s in the head. Every stroke now strikes 12
# harder and rings half as long again (still re-struck by the next stroke).
_POLICY: Final[dict[SectionRole, _Policy]] = {
    SectionRole.ALAP: _Policy(per_cycle=1, vel=78, ring_ms=4500.0),
    SectionRole.HEAD: _Policy(per_cycle=3, vel=92, ring_ms=2400.0),
    SectionRole.LIGHT: _Policy(per_cycle=1, vel=84, ring_ms=2400.0),
    SectionRole.CLIMAX: _Policy(per_cycle=2, vel=98, ring_ms=1800.0),
}


@dataclass(frozen=True)
class ChikariStroke:
    """One chikari stroke: when string 1 is struck, how hard, how long it may ring, and whether
    the composer wrote it (`bol: "chikari"`, or the jhala's) or the planner placed it."""
    start: float
    vel: int
    ring_ms: float
    written: bool


@dataclass(frozen=True)
class RightHandStroke:
    """One stroke of the sitar's right hand: `beat` after the section's (or the avartan's)
    start, on the melody string or on the chikari."""
    beat: float
    kind: Literal["melody", "chikari"]


@dataclass(frozen=True)
class _Line:
    """The placed sitar line as the planner reads it: its melody strokes, the chikari strokes
    the composer wrote, and the head's chikari matras."""
    melody: tuple[Note, ...]
    written: tuple[Note, ...]
    head: tuple[int, ...]


@dataclass(frozen=True)
class _Slot:
    """An EMPTY matra (no attack at all) a planned stroke could fill. `rank` orders the
    candidates: 0 = the silence straight after a phrase ends, 1 = any other silence,
    2 = under a held note."""
    offset: int
    rank: int


# --------------------------------------------------------------------------- #
# Reading the sitar line                                                      #
# --------------------------------------------------------------------------- #

def section_role(section: Section, arr: Arrangement) -> SectionRole:
    """The section's chikari role, from its place in the form."""
    if section.form_role == "intro" or section.kind is SectionKind.ALAAP:
        return SectionRole.ALAP
    if section.form_role == "mukhada" or is_song_hook(section, arr):
        return SectionRole.HEAD
    if section.form_role == "taan_long":
        return SectionRole.CLIMAX
    return SectionRole.LIGHT


def split_sitar_line(lead_layers: Iterable[Layer]) -> tuple[list[Note], list[Note]]:
    """(melody notes, written chikari strokes) of the SITAR lead layer(s), in time order. A
    written chikari is a placed Note marked `chikari` (crew/lead.py `_placed_note`)."""
    sitar = VOICES["sitar"].instrument
    notes = sorted((n for ly in lead_layers if ly.role == _LEAD_ROLE and ly.instrument == sitar
                    for n in ly.notes or []), key=lambda n: n.start)
    return [n for n in notes if not n.chikari], [n for n in notes if n.chikari]


def without_chikari(lead_layers: Iterable[Layer]) -> list[Layer]:
    """The lead layers with every written chikari lifted off the melody (they sound on the
    chikari layer instead). A layer left with no notes is dropped."""
    out: list[Layer] = []
    for layer in lead_layers:
        if not layer.notes:
            out.append(layer)
            continue
        notes = [n for n in layer.notes if not n.chikari]
        if len(notes) == len(layer.notes):
            out.append(layer)
        elif notes:
            out.append(layer.model_copy(update={"notes": notes}))
    return out


def _attacks(melody: Sequence[Note], written: Sequence[Note]) -> list[float]:
    """Every right-hand attack: each melody note (a compound bol or a gamak cell is already one
    Note per stroke; a kan is unstruck) and each written chikari."""
    return sorted(n.start for n in [*melody, *written])


def _sounding_at(t: float, melody: Sequence[Note]) -> bool:
    return any(n.start <= t + _EPS and t < n.start + n.dur - _EPS for n in melody)


def _ended_within(t0: float, t1: float, melody: Sequence[Note]) -> bool:
    return any(t0 - _EPS <= n.start + n.dur <= t1 + _EPS for n in melody)


# --------------------------------------------------------------------------- #
# Where: the planner                                                          #
# --------------------------------------------------------------------------- #

def chikari_strokes(arr: Arrangement, lead_layers: Iterable[Layer]) -> list[ChikariStroke]:
    """Every chikari stroke of the piece, written and planned, in time order. Pure."""
    melody, written = split_sitar_line(lead_layers)
    line = _Line(tuple(melody), tuple(written), _head_pattern(arr, melody, written))
    strokes: list[ChikariStroke] = []
    for span in section_spans(arr):
        if any(_inside(n.start, span) for n in [*melody, *written]):
            strokes += _section_strokes(span, arr, line)
    return sorted(strokes, key=lambda s: s.start)


def _inside(t: float, span: SectionSpan) -> bool:
    return span.start - _EPS <= t < span.end - _EPS


def _in_bar(t: float, start: float, cycle: float) -> bool:
    return start - _EPS <= t < start + cycle - _EPS


def _section_strokes(span: SectionSpan, arr: Arrangement, line: _Line) -> list[ChikariStroke]:
    """The section's written strokes, plus the planned ones avartan by avartan."""
    role = section_role(span.section, arr)
    policy = _POLICY[role]
    cycle = arr.beats_per_bar
    planned = [t for bar in range(span.section.bars)
               for t in _plan_bar(role, span.start + bar * cycle, cycle, line)]
    return ([ChikariStroke(n.start, n.vel, policy.ring_ms, written=True)
             for n in line.written if _inside(n.start, span)]
            + [ChikariStroke(t, policy.vel, policy.ring_ms, written=False) for t in planned])


def _plan_bar(role: SectionRole, start: float, cycle: float, line: _Line) -> list[float]:
    """The planned stroke beats of one avartan, by the section's role; the written strokes
    already in it count toward the role's cap."""
    taken = [n.start - start for n in line.written if _in_bar(n.start, start, cycle)]
    room = _POLICY[role].per_cycle - len(taken)
    if room <= 0:
        return []
    if role is SectionRole.ALAP:
        return _alap_beats(start, cycle, line.melody)
    slots = _slots(start, cycle, line.melody, line.written)
    if role is SectionRole.HEAD:
        free = {s.offset for s in slots}
        return [start + o for o in line.head if o in free and _spaced(o, taken)]
    if not any(n.start < start + cycle and n.start + n.dur > start for n in line.melody):
        return []                                 # the sitar has laid out for this avartan
    return [start + o for o in _select(slots, room, taken)]


def _slots(start: float, cycle: float, melody: Sequence[Note],
           written: Sequence[Note]) -> list[_Slot]:
    """The avartan's EMPTY matras — no melody attack and no written chikari anywhere in the
    matra — each ranked by what the melody is doing there."""
    attacks = _attacks(melody, written)
    out: list[_Slot] = []
    for m in range(int(math.floor(cycle + _EPS))):
        t = start + m
        if any(t - _EPS <= a < t + 1 - _EPS for a in attacks):
            continue
        if _sounding_at(t, melody):
            out.append(_Slot(m, 2))
        else:
            out.append(_Slot(m, 0 if _ended_within(t - 1, t, melody) else 1))
    return out


def _spaced(offset: float, others: Iterable[float]) -> bool:
    return all(abs(offset - o) >= MIN_SPACING_BEATS - _EPS for o in others)


def _select(slots: Sequence[_Slot], room: int, taken: Sequence[float]) -> list[int]:
    """Up to `room` slots, best rank first (earliest on a tie), each clear of the others and
    of the strokes already `taken` (beats from the avartan's start)."""
    chosen: list[int] = []
    for slot in sorted(slots, key=lambda s: (s.rank, s.offset)):
        if len(chosen) >= room:
            break
        if _spaced(slot.offset, [*taken, *chosen]):
            chosen.append(slot.offset)
    return sorted(chosen)


# The head --------------------------------------------------------------------

def _head_bars(arr: Arrangement) -> list[float]:
    """The sam of every avartan the head is stated on, in time order."""
    return [span.start + bar * arr.beats_per_bar for span in section_spans(arr)
            if section_role(span.section, arr) is SectionRole.HEAD
            for bar in range(span.section.bars)]


def _written_offsets(start: float, cycle: float, written: Sequence[Note]) -> tuple[float, ...]:
    return tuple(round(n.start - start, 4) for n in written if _in_bar(n.start, start, cycle))


def canonical_head_bar(arr: Arrangement, melody: Sequence[Note],
                       written: Sequence[Note]) -> float | None:
    """The sam of the head statement whose right hand recurs most often (the earliest on a
    tie) — the head as it is heard, robust to a statement a taan fill or a tihai's landing
    reshaped. None when the piece has no head that the sitar plays."""
    cycle = arr.beats_per_bar
    played = [b for b in _head_bars(arr) if any(_in_bar(n.start, b, cycle) for n in melody)]
    if not played:
        return None
    shape = {b: (tuple(_slots(b, cycle, melody, written)), _written_offsets(b, cycle, written))
             for b in played}
    common = Counter(shape.values()).most_common(1)[0][0]
    return next(b for b in played if shape[b] == common)


def _head_pattern(arr: Arrangement, melody: list[Note], written: list[Note]) -> tuple[int, ...]:
    """The matras of the head's avartan the chikari fills — chosen ONCE, from the canonical
    statement, so every return of the head carries the same strokes."""
    sam = canonical_head_bar(arr, melody, written)
    if sam is None:
        return ()
    cycle = arr.beats_per_bar
    taken = _written_offsets(sam, cycle, written)
    room = _POLICY[SectionRole.HEAD].per_cycle - len(taken)
    return tuple(_select(_slots(sam, cycle, melody, written), room, taken)) if room > 0 else ()


# The alap ----------------------------------------------------------------------

def _silences(start: float, end: float, melody: Sequence[Note]) -> list[tuple[float, float]]:
    """The silences in [start, end) that FOLLOW a phrase — each opens where a melody note
    ends — longest first. A silence before the first phrase (the arpeggio's lead-in) has no
    phrase to answer, so it is not one of them."""
    out: list[tuple[float, float]] = []
    for n in melody:
        gap_start = n.start + n.dur
        if not start - _EPS <= gap_start < end - _EPS or _sounding_at(gap_start, melody):
            continue
        nxt = min((m.start for m in melody if m.start > gap_start + _EPS), default=end)
        out.append((gap_start, min(nxt, end)))
    return sorted(set(out), key=lambda g: (-(g[1] - g[0]), g[0]))


def _alap_beats(start: float, cycle: float, melody: Sequence[Note]) -> list[float]:
    """At most one alap stroke this avartan: a breath into its longest post-phrase silence,
    on the beat, with time left to ring before the next phrase."""
    for gap_start, gap_end in _silences(start, start + cycle, melody):
        if gap_end - gap_start < ALAP_MIN_GAP_BEATS - _EPS:
            break
        t = float(math.ceil(gap_start + ALAP_BREATH_BEATS - _EPS))
        if t <= gap_end - ALAP_TAIL_BEATS + _EPS:
            return [t]
    return []


# --------------------------------------------------------------------------- #
# How: the strum                                                              #
# --------------------------------------------------------------------------- #

def chikari_strings(arr: Arrangement) -> list[tuple[str, int, float]]:
    """(swara, absolute octave, velocity weight) per chikari string, string 1 first.

    The two Sa strings sit an octave apart — the high Sa (ati-taar) above the taar Sa the old
    single chikari note sounded — and the colour strings sit in the octave beneath, so every
    string is a distinct pitch (a unison pair on one channel would cut itself off). The octave
    layout is inference from the instrument; the tuning itself is `raga.chikari_swaras`."""
    taar = arr.registers.get(_LEAD_ROLE, 0) + 1
    tuning = chikari_swaras(arr.raga)
    octaves = [taar + 1, taar] + [taar - 1] * (len(tuning) - 2)
    return list(zip(tuning, octaves, CHIKARI_STRING_WEIGHTS))


def _beats(ms: float, bpm: float) -> float:
    return ms * bpm / 60000.0


def strum_notes(strokes: Sequence[ChikariStroke], arr: Arrangement) -> list[Note]:
    """Each stroke as a strum across the chikari strings: string k enters `STRUM_MS` x k after
    string 1, every string at its weight of the stroke's velocity, and rings until the next
    stroke re-strikes it or its ring cap — no re-attack in between. A planned stroke strums only
    the Sa pair (`PLANNED_STRINGS`); a written one, every string. Pure."""
    strings = chikari_strings(arr)
    sweep = _beats(STRUM_MS, arr.bpm)
    ordered = sorted(strokes, key=lambda s: s.start)
    notes: list[Note] = []
    for i, stroke in enumerate(ordered):
        nxt = ordered[i + 1].start if i + 1 < len(ordered) else math.inf
        ring = min(_beats(stroke.ring_ms, arr.bpm), nxt - stroke.start)
        struck = strings if stroke.written else strings[:PLANNED_STRINGS]
        notes += [Note(swara=swara, oct=octave, start=round(stroke.start + k * sweep, 4),
                       dur=round(ring, 4), vel=max(1, min(127, round(stroke.vel * weight))))
                  for k, (swara, octave, weight) in enumerate(struck)]
    return notes


def chikari_layer(arr: Arrangement, lead_layers: Iterable[Layer]) -> Layer | None:
    """The chikari as its own sitar layer and channel, or None when the sitar strikes none."""
    strokes = chikari_strokes(arr, lead_layers)
    if not strokes:
        return None
    voice = VOICES[CHIKARI_ROLE]
    return Layer(role=CHIKARI_ROLE, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=strum_notes(strokes, arr))


# --------------------------------------------------------------------------- #
# The combined right hand — for any later reader (e.g. the riff)              #
# --------------------------------------------------------------------------- #

def _right_hand(start: float, end: float, melody: Sequence[Note],
                strokes: Sequence[ChikariStroke]) -> list[RightHandStroke]:
    out = [RightHandStroke(round(n.start - start, 4), "melody")
           for n in melody if start - _EPS <= n.start < end - _EPS]
    out += [RightHandStroke(round(s.start - start, 4), "chikari")
            for s in strokes if start - _EPS <= s.start < end - _EPS]
    return sorted(out, key=lambda s: (s.beat, s.kind))


def right_hand_rhythm(arr: Arrangement, lead_layers: Iterable[Layer],
                      section_index: int) -> list[RightHandStroke]:
    """The sitar's whole right hand in one section — every melody stroke and every chikari
    stroke, beats from the section's start, in time order. Takes the lead layers as
    `lead_layers_from` builds them (written chikari still marked on the sitar line). Pure."""
    layers = list(lead_layers)
    span = section_spans(arr)[section_index]
    melody, _ = split_sitar_line(layers)
    return _right_hand(span.start, span.end, melody, chikari_strokes(arr, layers))


def head_right_hand(arr: Arrangement, lead_layers: Iterable[Layer]) -> list[RightHandStroke]:
    """ONE avartan of the head's right hand, beats from its sam — the statement every return
    of the head repeats (melody strokes and chikari strokes together). Empty when the piece
    has no head the sitar plays. Pure."""
    layers = list(lead_layers)
    melody, written = split_sitar_line(layers)
    sam = canonical_head_bar(arr, melody, written)
    if sam is None:
        return []
    return _right_hand(sam, sam + arr.beats_per_bar, melody, chikari_strokes(arr, layers))
