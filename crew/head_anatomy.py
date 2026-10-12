"""The gat head's ANATOMY — which parts of a mukhada are its identity and which are decoration.

A guitar that takes up the sitar's head inherits its IDENTITY, not every note (the review behind
`crew/riff_from_mukhada.py`). That needs a deterministic answer to "what is identity here?", and
this module gives it, note by note, over one avartan of the realised head:

  * the RIGHT HAND — every pluck's onset, including each stroke of a compound bol (dir, dadir...),
    in the same ratios `gats.bol_onsets` gives the renderer. Strokes and pauses are the head's
    rhythmic fingerprint, preserved most strongly of all;
  * the ACCENTS — notes struck on the sam or a tali, the beats the kick lands with;
  * STRUCTURAL notes — the contour's pitches: every accented note, every note at a phrase edge
    (next to a rest, first, last), every note half a beat or longer, and every short note at a
    turn of direction;
  * ORNAMENTAL notes — a short, unaccented PASSING note (between same-direction neighbours) or
    NEIGHBOUR note (out and back to the same pitch), and every chikari (a drone-string stroke with
    no melodic pitch). A kan (`grace`), a murki/khatka flick and a gamak live ON a note and are
    simply not part of its pitch here; a MEEND counts at its ARRIVAL (the target the renderer
    sounds, `coexistence.sounding_pitch`), so the glide's source is decoration.

Pure: no LLM, no I/O. Shared by the derivation and the kinship measurement, so the two always
agree on what the head's identity is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from crew.anchor import QUOTED_ACCENTS
from crew.contracts import Arrangement, LeadNote, LeadPhrase
from gats import BOL_WORDS, INWARD_STROKES, bol_onsets
from raga import SWARAS

ORNAMENT_MAX_BEATS: Final = 0.5     # a note this short (or shorter) MAY be a passing/neighbour ornament
_CHIKARI: Final = "chikari"
_EPS: Final = 1e-6

NoteRole = Literal["structural", "ornamental", "rest"]


@dataclass(frozen=True)
class Pluck:
    """One stroke of the right hand inside a note: where it falls, how long, how hard."""
    offset: float           # beats from the note's onset
    length: float
    strong: bool            # an inward stroke (da / di) — the soft return is ra / r


@dataclass(frozen=True)
class HeadNote:
    """One entry of the head's avartan as the guitar reads it. `swara`/`oct` are the pitch the
    note ARRIVES on (a meend's target), octave LOCAL to the lead register; a rest has no plucks."""
    onset: float
    dur: float
    role: NoteRole
    swara: str
    oct: int
    accent: bool
    plucks: tuple[Pluck, ...]
    meend: bool = False
    chikari: bool = False

    @property
    def pitch(self) -> int:
        return SWARAS[self.swara] + 12 * self.oct


def accent_beats(arr: Arrangement) -> frozenset[float]:
    """The within-cycle beats of the sam and the talis — the accents a head is anchored to."""
    return frozenset(a.beat for a in arr.accent_grid if a.kind in QUOTED_ACCENTS)


def _on(beat: float, beats: frozenset[float]) -> bool:
    return any(abs(beat - b) < _EPS for b in beats)


def _laid(notes: list[LeadNote], cycle_beats: float) -> list[tuple[LeadNote, float, float]]:
    """(note, onset, duration) laid end-to-end over exactly one cycle — clipped at the edge, and a
    head that falls short rings its last entry to the edge (as the lead's placement does)."""
    laid: list[tuple[LeadNote, float, float]] = []
    t = 0.0
    for note in notes:
        if t >= cycle_beats - _EPS:
            break
        laid.append((note, t, min(note.dur, cycle_beats - t)))
        t += note.dur
    if laid and t < cycle_beats - _EPS:
        note, onset, _ = laid[-1]
        laid[-1] = (note, onset, cycle_beats - onset)
    return laid


def _arrival(note: LeadNote) -> tuple[str, int]:
    """The pitch a note lands on: a meend's target (in its own octave unless one is given)."""
    if note.meend_swara is not None:
        return note.meend_swara, note.meend_oct if note.meend_oct is not None else note.oct
    return note.swara, note.oct


def _pitch(note: LeadNote) -> int:
    swara, octave = _arrival(note)
    return SWARAS[swara] + 12 * octave


def _plucks(note: LeadNote, dur: float) -> tuple[Pluck, ...]:
    """The right hand on one note: a bol word's strokes in its ratios, a chikari as one soft
    stroke, an unmarked note as one strong stroke."""
    if note.bol in BOL_WORDS:
        return tuple(Pluck(offset, length, stroke in INWARD_STROKES)
                     for offset, length, stroke in bol_onsets(note.bol, dur))
    return (Pluck(0.0, dur, note.bol != _CHIKARI),)


def _melodic(note: LeadNote | None) -> bool:
    return note is not None and not note.rest and note.bol != _CHIKARI


def _is_ornament(prev: LeadNote | None, note: LeadNote, nxt: LeadNote | None, *, dur: float,
                 accent: bool) -> bool:
    """A short, unaccented passing or neighbour note between two sounding melodic neighbours."""
    if accent or dur > ORNAMENT_MAX_BEATS + _EPS or not (_melodic(prev) and _melodic(nxt)):
        return False
    a, b, c = _pitch(prev), _pitch(note), _pitch(nxt)          # type: ignore[arg-type]
    passing = a < b < c or a > b > c
    neighbour = a == c and b != a
    return passing or neighbour


def head_anatomy(head: LeadPhrase, *, cycle_beats: float,
                 accents: frozenset[float]) -> list[HeadNote]:
    """The head's avartan, entry by entry, with each note's role, accent and right hand. Pure."""
    laid = _laid(list(head.notes), cycle_beats)
    out: list[HeadNote] = []
    for i, (note, onset, dur) in enumerate(laid):
        accent = _on(onset, accents)
        if note.rest:
            out.append(HeadNote(onset, dur, "rest", "S", 0, accent, ()))
            continue
        prev = laid[i - 1][0] if i > 0 else None
        nxt = laid[i + 1][0] if i + 1 < len(laid) else None
        chikari = note.bol == _CHIKARI
        ornament = chikari or _is_ornament(prev, note, nxt, dur=dur, accent=accent)
        swara, octave = _arrival(note)
        out.append(HeadNote(onset, dur, "ornamental" if ornament else "structural", swara, octave,
                            accent, _plucks(note, dur), meend=note.meend_swara is not None,
                            chikari=chikari))
    return out


def head_onsets(anatomy: list[HeadNote], extra_onsets: Sequence[float] = ()) -> tuple[float, ...]:
    """The head's rhythmic fingerprint: every pluck's onset in the cycle, sorted. `extra_onsets`
    (the seam for the sitar's chikari strokes, laid by another layer) join it — the combined right
    hand is the rhythm a guitar would answer."""
    plucks = {round(n.onset + p.offset, 4) for n in anatomy for p in n.plucks}
    return tuple(sorted(plucks | {round(o, 4) for o in extra_onsets}))


def structural_notes(anatomy: list[HeadNote]) -> list[HeadNote]:
    return [n for n in anatomy if n.role == "structural"]


def accented_notes(anatomy: list[HeadNote]) -> list[HeadNote]:
    """The structural notes struck on the sam or a tali — the head's accent structure."""
    return [n for n in anatomy if n.role == "structural" and n.accent]
