"""
The REPAIRS an arranger may make when the riff and the melody fight — enumerated, applied
and bounded in CODE, so the only thing left for an agent is the musical choice.

`crew/coexistence.py` finds the clashes; this module answers "what may be done about one?"
and "who moves?". Both halves are deliberately code:

  * WHO MOVES is the RIGHT OF WAY rule, decided from the arrangement's own `anchor` plus
    the section's gat role — never negotiated between two agents. Two voices each able to
    demand changes of the other is a loop with no referee, and this repo's standing rule is
    that every loop's terminator lives in code. `gat_first` means the riff yields (the
    melody is the source of the piece, it is already certified by the gat verifiers, and
    re-rolling it would discard that verification and spend the slowest agent); `riff_first`
    means the melody bends around the hook. A section whose role makes one voice the
    identity overrides the anchor — nothing re-pitches a taan, and nothing softens a
    breakdown's crush.
  * WHICH REPAIRS EXIST is legality, and legality is checkable. Every option offered is
    already raga-legal, so an agent cannot choose an illegal one: the worst it can do is
    choose a legal repair that sounds worse than another legal repair.

What the agent decides is only which offered repair serves the music — including KEEP, since
a clash the arranger judges expressive should survive. That is the taste half.

Reseating deliberately refuses any swara the raga admits in only ONE direction
(`directional_varjya`): a repair is a local nudge with no view of the phrase's direction, so
introducing a direction-sensitive swara could break a rule this module cannot see. Refusing
them costs a few candidates and cannot produce a violation.

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional

from crew.coexistence import Chase, Grind
from crew.contracts import Layer, Note, Section
from crew.generators import HARSH_INTERVAL_CLASSES, damp_note, sounding_pitch
from raga import RAGAS, directional_varjya, semitone

# Damping (`generators.damp_note`) is the always-available repair and the fallback when
# nothing better is legal — one definition, shared with the last-ditch guard that runs after
# this pass, so the two can never drift into disagreeing about what "damped" means.
# A melody note may be nudged only to a NEIGHBOUR — this is an inflection, not a rewrite.
_LEAD_NUDGE_MAX_ST: Final[int] = 2


class Yielder(str, Enum):
    """Which voice gives way where the two fight."""
    RIFF = "riff"
    LEAD = "lead"


# Gat roles where one voice IS the section's identity, overriding the anchor. The melody
# carries a taan and an alap outright, so the riff yields there however the piece is
# anchored; a breakdown and a tihai are the riff's own statement, so the melody bends.
_MELODY_OWNS: Final[frozenset[str]] = frozenset({"taan_short", "taan_long", "intro", "manjha"})
_RIFF_OWNS: Final[frozenset[str]] = frozenset({"breakdown", "tihai"})


def right_of_way(section: Section, anchor: str) -> Yielder:
    """Who gives way in this section: the section's role first, then the piece's anchor."""
    if section.form_role in _MELODY_OWNS:
        return Yielder.RIFF
    if section.form_role in _RIFF_OWNS:
        return Yielder.LEAD
    return Yielder.LEAD if anchor == "riff_first" else Yielder.RIFF


class RepairKind(str, Enum):
    """What may be done about one finding. KEEP is always offered — an arranger who judges
    a clash expressive must be able to say so."""
    KEEP = "keep"
    DAMP = "damp"                # riff: strip the stack, clip to a chug, soften
    DROP_TONE = "drop_tone"      # riff: remove just the grinding chord tone
    RESEAT_RIFF = "reseat_riff"  # riff: move the root to a consonant, legal swara
    HOLD_ROOT = "hold_root"      # riff: keep the previous root through the melody's movement
    RESEAT_LEAD = "reseat_lead"  # melody: nudge to a consonant, legal neighbour


@dataclass(frozen=True)
class Repair:
    """One offered repair. `swara` is the replacement (reseat) or the tone to drop."""
    kind: RepairKind
    swara: Optional[str] = None

    @property
    def id(self) -> str:
        return self.kind.value if self.swara is None else f"{self.kind.value}:{self.swara}"


def _reseat_candidates(raga: str, avoid: list[int], *, near: Optional[int] = None,
                       within: Optional[int] = None) -> list[str]:
    """Raga swaras clashing with none of `avoid` (pitch classes), nearest to `near` first.

    Direction-sensitive swaras are refused outright (see the module docstring). `within`
    caps the semitone reach, which is what keeps a melody repair an inflection rather than
    a recomposition.
    """
    varjya = directional_varjya(raga)
    scored: list[tuple[int, str]] = []
    for swara in RAGAS[raga]["allowed"]:
        if swara in varjya:
            continue
        pitch = semitone(swara)
        if any((pitch - other) % 12 in HARSH_INTERVAL_CLASSES for other in avoid):
            continue
        distance = 0 if near is None else min((pitch - near) % 12, (near - pitch) % 12)
        if within is not None and distance > within:
            continue
        scored.append((distance, swara))
    return [swara for _, swara in sorted(scored)]


def _lead_pitches_under(note: Note, lead_notes: list[Note]) -> list[int]:
    """Pitch classes of every melody note sounding during this riff note — a reseat must
    clear ALL of them, or it trades one grind for another."""
    end = note.start + note.dur
    return [sounding_pitch(ln) % 12 for ln in lead_notes
            if note.start < ln.start + ln.dur and ln.start < end]


def grind_repairs(grind: Grind, *, yielder: Yielder, raga: str, riff_notes: list[Note],
                  lead_notes: list[Note]) -> list[Repair]:
    """The legal repairs for one grind, best first. KEEP always closes the list."""
    repairs: list[Repair] = []
    if yielder is Yielder.LEAD:
        repairs += _lead_repairs(grind, raga=raga, lead_notes=lead_notes)
    if not repairs:                       # the melody had no legal neighbour — the riff moves
        repairs += _riff_repairs(grind, raga=raga, riff_notes=riff_notes,
                                 lead_notes=lead_notes)
    repairs.append(Repair(RepairKind.KEEP))
    return repairs


def _lead_repairs(grind: Grind, *, raga: str, lead_notes: list[Note]) -> list[Repair]:
    """Nudge the melody note to a consonant neighbour — offered only when the riff has
    right of way, and only within a tone, so the raga line is inflected, not rewritten."""
    if grind.lead_index >= len(lead_notes):
        return []
    lead = lead_notes[grind.lead_index]
    pitch = sounding_pitch(lead) % 12
    candidates = _reseat_candidates(raga, [semitone(grind.riff_swara)],
                                    near=pitch, within=_LEAD_NUDGE_MAX_ST)
    return [Repair(RepairKind.RESEAT_LEAD, swara) for swara in candidates[:2]
            if swara != lead.swara]


def _riff_repairs(grind: Grind, *, raga: str, riff_notes: list[Note],
                  lead_notes: list[Note]) -> list[Repair]:
    """The riff's ways of giving way, cheapest damage first: drop just the offending chord
    tone, move the root somewhere consonant, or damp the note to a percussive touch."""
    if grind.from_chord:
        return [Repair(RepairKind.DROP_TONE, grind.riff_swara), Repair(RepairKind.DAMP)]
    note = riff_notes[grind.riff_index]
    avoid = _lead_pitches_under(note, lead_notes)
    candidates = _reseat_candidates(raga, avoid, near=semitone(note.swara))
    ranked = _rank_roots([s for s in candidates if s != note.swara],
                         previous=_previous_swara(riff_notes, grind.riff_index))
    reseats = [Repair(RepairKind.RESEAT_RIFF, s) for s in ranked[:2]]
    # THE GROUND DOES NOT MOVE. A riff's ground is the pitch it keeps returning to, and that
    # repetition is most of what makes it read as metal rather than as a melody — so when the
    # ground itself clashes, the guitarist damps it (a percussive touch) exactly as the old
    # guard did, and only a MOVEMENT note is worth relocating. Measured on the 2026-07-20
    # piece, offering the reseat first moved 88 ground strokes onto the leading tone: a
    # different riff, dressed up as a repair.
    if note.swara == _ground_swara(riff_notes):
        return [Repair(RepairKind.DAMP)] + reseats
    return reseats + [Repair(RepairKind.DAMP)]


def _ground_swara(riff_notes: list[Note]) -> Optional[str]:
    """The riff's ground — the pitch it returns to most often."""
    counts = Counter(n.swara for n in riff_notes)
    return counts.most_common(1)[0][0] if counts else None


def _previous_swara(riff_notes: list[Note], index: int) -> Optional[str]:
    return riff_notes[index - 1].swara if index > 0 else None


def _rank_roots(candidates: list[str], *, previous: Optional[str]) -> list[str]:
    """Order the places a riff root may move to, most musical first.

    Nearest-pitch alone is not musical here: it treats every legal swara as interchangeable
    and will happily rebuild a riff around whichever one the raga happens to list first
    (measured on the 2026-07-20 piece: 95 roots reseated onto tivra Ma, which is a different
    riff, not a repair). A rhythm guitar's harmony should HOLD, so the previous root wins —
    the floor stays where it was while the melody moves over it — then the ground Sa, and
    only then the nearest pitch to what was written.
    """
    def rank(swara: str) -> int:
        if swara == previous:
            return 0
        return 1 if swara == "S" else 2
    return sorted(candidates, key=rank)


def chase_repairs(chase: Chase) -> list[Repair]:
    """A chase is the riff's own doing whoever has right of way — the harmonic floor moved
    because the tune moved. Either hold the previous root through the movement, or judge
    the change worth it."""
    return [Repair(RepairKind.HOLD_ROOT, chase.from_swara), Repair(RepairKind.KEEP)]


# --------------------------------------------------------------------------- #
# Applying a chosen repair. Every one is a local edit to ONE note: nothing here #
# moves an attack, changes the cell's rhythm or touches another section, so the #
# riff's identity — the thing a listener remembers — cannot be lost to a repair.#
# --------------------------------------------------------------------------- #

def _without_tone(note: Note, swara: str) -> Note:
    remaining = [c for c in (note.chord or []) if c != swara]
    return note.model_copy(update={"chord": remaining or None})


def _reseated(note: Note, swara: str) -> Note:
    """Move a note's sounding pitch. A meend sounds at its TARGET, so reseating a gliding
    note moves where it LANDS — changing the written swara would leave the clash in place
    and silently redirect the glide."""
    field = "meend_swara" if note.meend_swara is not None else "swara"
    return note.model_copy(update={field: swara})


def _apply_to_riff(note: Note, repair: Repair) -> Note:
    if repair.kind is RepairKind.DAMP:
        return damp_note(note)
    if repair.kind is RepairKind.DROP_TONE and repair.swara:
        return _without_tone(note, repair.swara)
    if repair.kind in (RepairKind.RESEAT_RIFF, RepairKind.HOLD_ROOT) and repair.swara:
        return note.model_copy(update={"swara": repair.swara})
    return note


def _lead_slots(leads: list[Layer]) -> list[tuple[int, int]]:
    """(layer, note) positions in the same order `coexistence.lead_notes_of` produces, so a
    finding's `lead_index` maps back to the note it named."""
    slots = [(li, ni, n.start) for li, ly in enumerate(leads)
             for ni, n in enumerate(ly.notes or [])]
    return [(li, ni) for li, ni, _ in sorted(slots, key=lambda t: t[2])]


def apply_repairs(riff: Optional[Layer], leads: list[Layer],
                  chosen: list[tuple[int, Repair]], *,
                  lead_targets: Optional[dict[int, int]] = None) -> tuple[Optional[Layer], list[Layer]]:
    """Apply chosen repairs, returning new layers (inputs untouched).

    `chosen` pairs a RIFF note index with its repair; `lead_targets` maps a riff index to
    the melody note a RESEAT_LEAD moves instead. Pure.
    """
    riff_out = riff
    if riff is not None and riff.notes:
        notes = list(riff.notes)
        for index, repair in chosen:
            if repair.kind is not RepairKind.RESEAT_LEAD and index < len(notes):
                notes[index] = _apply_to_riff(notes[index], repair)
        riff_out = riff.model_copy(update={"notes": notes})
    lead_out = _apply_lead_repairs(leads, chosen, lead_targets or {})
    return riff_out, lead_out


def _apply_lead_repairs(leads: list[Layer], chosen: list[tuple[int, Repair]],
                        lead_targets: dict[int, int]) -> list[Layer]:
    moves = [(lead_targets[i], r) for i, r in chosen
             if r.kind is RepairKind.RESEAT_LEAD and r.swara and i in lead_targets]
    if not moves:
        return leads
    slots = _lead_slots(leads)
    notes = [list(ly.notes or []) for ly in leads]
    for lead_index, repair in moves:
        if lead_index < len(slots) and repair.swara:
            layer_pos, note_pos = slots[lead_index]
            notes[layer_pos][note_pos] = _reseated(notes[layer_pos][note_pos], repair.swara)
    return [ly.model_copy(update={"notes": ns}) for ly, ns in zip(leads, notes)]


def safest_repair(repairs: list[Repair]) -> Repair:
    """The repair code picks with no agent: the first offered, which is the least damaging
    legal fix (KEEP only when nothing else is legal). This is the fallback when the agent
    is unavailable, unparseable, or out of rounds — the guaranteed terminator."""
    return repairs[0]
