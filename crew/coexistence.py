"""
DO THE LEAD AND THE RIFF COEXIST? — the third question nobody was asking.

The riff composer asks "is this a good metal riff?" and the lead composer asks "is this a
good raga line?", and both can answer yes while the two lines grind against each other.
Nothing in the pipeline asked whether they work TOGETHER: `validate_composition` judges each
note against the raga (both voices are legal), Rasik judges authenticity, and the Producer
judges the song's shape — none of them compares a riff note with the melody note sounding
over it at that instant.

Measured on `out/fusion_20260720_183403.json` (2026-09-14): 86% of riff notes sound
underneath a lead note, and a THIRD of those moments sit at a semitone, tritone or major
seventh against it. `generators.harmonize_riff_to_lead` catches part of that — but only
under lead notes held a beat or longer (62 of the 163 harsh moments; the other 101 it never
looks at), and it only DAMPENS: the clash becomes a duller chug, nothing is recomposed, and
no evidence survives. The guard is damage control, so the failure is invisible to every
critic and to us.

This module makes it visible. It is pure detection — the CHECKABLE half, which by our
standing rule belongs in code: interval arithmetic against the melody, classified by what
the melody is doing at that moment. It fixes nothing and judges no taste. Whether a flagged
moment should be repaired, and how, is the musical question an arranger pass answers later;
this report is the evidence it reads (`render_coexistence`), and the trigger that decides
whether it needs to run at all (a clean section costs no tokens).

TWO findings, deliberately separate because they have different cures:

  * GRIND — a riff pitch at a harsh interval class under a SETTLED melody note. The ear
    tunes to a held note, so a semitone underneath it is heard as wrong; under a passing
    note the same interval is ordinary metal movement and is NOT reported.
  * CHASE — the riff changing root where the melody is in MOTION. Harmony that moves
    because the tune moved is what makes chords feel random: the floor should hold through
    movement and change at arrivals. (Sujit, 2026-09-14: "the chords feel random even when
    every chord is legal".)

Interval CLASS is octave-invariant, so this needs no knowledge of how the renderer seats a
chord tone — `_seat_chord_tone` only moves octaves. Chord tones are therefore checked
alongside roots, which the existing guard never did.

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Iterable, Optional

from crew.contracts import Arrangement, Composition, Layer, Note
from crew.generators import HARSH_INTERVAL_CLASSES, section_spans, sounding_pitch
from raga import SWARAS

# What the melody is DOING at an instant — the ear's willingness to hear a clash under it.
_HELD_MIN: Final[float] = 1.0      # a note this long is a tone the ear tunes to
_STABLE_MIN: Final[float] = 0.5    # ...this long has settled; shorter is movement


class LeadStability(str, Enum):
    """How settled the melody is where a riff note sounds under it."""
    HELD = "held"         # the ear tunes to it — a grind underneath is heard as wrong
    STABLE = "stable"     # settled enough to carry harmony
    PASSING = "passing"   # movement — dissonance under it is idiomatic, not a fault


_REPORTED: Final[frozenset[LeadStability]] = frozenset(
    {LeadStability.HELD, LeadStability.STABLE})


def _stability(note: Note) -> LeadStability:
    if note.dur >= _HELD_MIN:
        return LeadStability.HELD
    return LeadStability.STABLE if note.dur >= _STABLE_MIN else LeadStability.PASSING


@dataclass(frozen=True)
class Grind:
    """One riff pitch sounding a harsh interval under a settled melody note.

    `riff_index` indexes the PRIMARY rhythm layer's time-sorted notes — a repair is
    surgical, so it must name the note and not just the beat (two voices can attack on
    the same beat, and a chord tone repair targets one swara of one note)."""
    riff_index: int
    lead_index: int            # into `lead_notes_of(leads)` — a repair may move the MELODY
    beat: float
    riff_swara: str            # the offending riff pitch (a root, or one of its chord tones)
    from_chord: bool           # was it a chord tone rather than the struck root?
    lead_swara: str            # what the melody is sounding there
    interval_class: int        # 1 = semitone, 6 = tritone, 11 = major seventh
    stability: LeadStability


@dataclass(frozen=True)
class Chase:
    """The riff changing root where the melody is in motion — harmony following the tune."""
    riff_index: int
    beat: float
    from_swara: str
    to_swara: str


@dataclass(frozen=True)
class SectionCoexistence:
    """One section's verdict. `passing_grinds` is context, not a finding: harsh intervals
    under a moving melody are ordinary, and counting them keeps a quiet section honest."""
    index: int
    kind: str
    form_role: Optional[str]
    start: float
    grinds: tuple[Grind, ...]
    chases: tuple[Chase, ...]
    passing_grinds: int
    riff_notes: int

    @property
    def clean(self) -> bool:
        return not self.grinds and not self.chases


@dataclass(frozen=True)
class CoexistenceReport:
    sections: tuple[SectionCoexistence, ...]

    @property
    def flagged(self) -> tuple[SectionCoexistence, ...]:
        """The sections an arranger pass would need to look at — everything else costs
        nothing, which is the point of detecting in code before spending a token."""
        return tuple(s for s in self.sections if not s.clean)

    @property
    def clean(self) -> bool:
        return not self.flagged


def _riff_layer(comp: Composition) -> Optional[Layer]:
    """The rhythm guitar's PRIMARY take. The double-track is the same performance nudged
    late and detuned (`generators.double_track`), so counting both would double every
    finding; the double carries `detune_cents` and the original does not."""
    rhythm = [ly for ly in comp.layers if ly.role == "rhythm" and ly.notes]
    return next((ly for ly in rhythm if ly.detune_cents is None), rhythm[0] if rhythm else None)


def _sounding_under(note: Note, leads: Iterable[Note]) -> list[tuple[int, Note]]:
    """The melody notes sounding during this riff note, with their index — interval
    overlap, not onset, so a sustained note counts wherever it is still ringing."""
    end = note.start + note.dur
    return [(i, ln) for i, ln in enumerate(leads)
            if note.start < ln.start + ln.dur and ln.start < end]


def lead_notes_of(leads: list[Layer]) -> list[Note]:
    """Every melody note across the lead layers in time order — the ordering
    `Grind.lead_index` indexes. One definition, shared by the detector and any repair."""
    return sorted((n for ly in leads for n in (ly.notes or [])), key=lambda n: n.start)


def _riff_pitches(note: Note) -> list[tuple[str, int, bool]]:
    """Every pitch this riff note sounds — the struck root plus each chord tone — as
    (swara, pitch, from_chord). Chord tones count: the renderer seats them consonantly
    against their ROOT and never against the melody, so a stack can grind where its root
    does not."""
    root = sounding_pitch(note)
    pitches = [(note.swara, root, False)]
    pitches += [(swara, SWARAS[swara] + 12 * note.oct, True) for swara in (note.chord or [])]
    return pitches


# A short, unchorded, palm-muted note is a percussive TOUCH, not a sounding harmony: it is
# over before the ear can tune it against the melody. That is exactly what the old guard
# reduced a clash to, and what a guitarist does when their ground note fights the tune — so
# a touch is not a finding, and a repair that produces one has genuinely resolved the clash.
_TOUCH_MAX_BEATS: Final[float] = 0.5


def _is_touch(note: Note) -> bool:
    return (note.technique == "palm_mute" and note.dur <= _TOUCH_MAX_BEATS
            and not note.chord)


def _grinds_for(index: int, note: Note, leads: list[Note]) -> tuple[list[Grind], int]:
    """This riff note's reportable grinds, plus how many fell under a PASSING melody note
    (context, not a fault). At most one finding per (pitch, melody note) pair."""
    found: list[Grind] = []
    passing = 0
    if _is_touch(note):
        return found, passing
    for lead_index, lead in _sounding_under(note, leads):
        stability = _stability(lead)
        lead_pitch = sounding_pitch(lead)
        for swara, pitch, from_chord in _riff_pitches(note):
            if (pitch - lead_pitch) % 12 not in HARSH_INTERVAL_CLASSES:
                continue
            if stability in _REPORTED:
                found.append(Grind(riff_index=index, lead_index=lead_index,
                                   beat=round(note.start, 4), riff_swara=swara,
                                   from_chord=from_chord, lead_swara=lead.swara,
                                   interval_class=(pitch - lead_pitch) % 12,
                                   stability=stability))
            else:
                passing += 1
    return found, passing


def _chases_for(riff: list[tuple[int, Note]], leads: list[Note]) -> list[Chase]:
    """Root changes landing where the melody is moving. The harmonic floor should hold
    through a run and change at an arrival; a root that turns over mid-phrase is harmony
    chasing the tune."""
    chases: list[Chase] = []
    for (_, previous), (index, current) in zip(riff, riff[1:]):
        if current.swara == previous.swara:
            continue
        under = _sounding_under(current, leads)
        if under and all(_stability(ln) is LeadStability.PASSING for _, ln in under):
            chases.append(Chase(riff_index=index, beat=round(current.start, 4),
                                from_swara=previous.swara, to_swara=current.swara))
    return chases


def riff_notes_of(riff: Optional[Layer]) -> list[Note]:
    """The primary riff's notes in time order — the ordering `Grind.riff_index` indexes.
    One definition, so the detector and any repair agree on what note 7 means."""
    return sorted(riff.notes or [], key=lambda n: n.start) if riff else []


def coexistence_of(riff: Optional[Layer], leads: list[Layer],
                   arr: Arrangement) -> CoexistenceReport:
    """The core: where the riff and the melody fail to coexist, per section.

    Takes LAYERS because the repair pass runs mid-assembly (before the bass and the
    double-track derive from the riff, so they inherit any repair), where there is no
    Composition yet. Detection only — repairs nothing, ranks no taste. Pure.
    """
    riff_notes = riff_notes_of(riff)
    lead_notes = lead_notes_of(leads)
    indexed = list(enumerate(riff_notes))
    sections: list[SectionCoexistence] = []
    for span in section_spans(arr):
        in_span = [(i, n) for i, n in indexed if span.start <= n.start < span.end]
        grinds: list[Grind] = []
        passing = 0
        for index, note in in_span:
            found, ignored = _grinds_for(index, note, lead_notes)
            grinds += found
            passing += ignored
        sections.append(SectionCoexistence(
            index=span.index, kind=span.section.kind.value,
            form_role=span.section.form_role, start=round(span.start, 4),
            grinds=tuple(grinds), chases=tuple(_chases_for(in_span, lead_notes)),
            passing_grinds=passing, riff_notes=len(in_span)))
    return CoexistenceReport(sections=tuple(sections))


def coexistence_report(comp: Composition, arr: Arrangement) -> CoexistenceReport:
    """The same report for a FINISHED composition — the diagnostic adapter (and what the
    Producer-style tooling reads). Pure."""
    return coexistence_of(_riff_layer(comp),
                          [ly for ly in comp.layers if ly.role == "lead"], arr)


_IC_NAMES: Final[dict[int, str]] = {1: "semitone", 6: "tritone", 11: "major 7th"}


def _render_section(section: SectionCoexistence) -> list[str]:
    head = f"  section {section.index} ({section.kind}"
    head += f"/{section.form_role}" if section.form_role else ""
    head += f", beat {section.start:g}): "
    if section.clean:
        return [head + "the riff and the melody coexist."]
    lines = [head + f"{len(section.grinds)} grind(s), {len(section.chases)} chase(s) "
                    f"of {section.riff_notes} riff notes"]
    for grind in section.grinds:
        where = "chord tone" if grind.from_chord else "root"
        lines.append(f"    beat {grind.beat:g}: riff {where} {grind.riff_swara} is a "
                     f"{_IC_NAMES[grind.interval_class]} under the {grind.stability.value} "
                     f"melody note {grind.lead_swara}")
    for chase in section.chases:
        lines.append(f"    beat {chase.beat:g}: root moves {chase.from_swara} -> "
                     f"{chase.to_swara} while the melody is still moving")
    return lines


def render_coexistence(report: CoexistenceReport) -> str:
    """The report as the prompt block an arranger pass reads — code measures, the LLM
    decides the repair. Flagged sections only; a clean piece says so in one line."""
    if report.clean:
        return "COEXISTENCE: the riff and the melody coexist in every section."
    lines = ["COEXISTENCE — where the riff and the melody fight (code-measured):"]
    for section in report.flagged:
        lines += _render_section(section)
    return "\n".join(lines)
