"""The riff that GROWS OUT OF the gat head — motivic development through instrumental change.

Until this module a gat_first piece told the riff model to be "the head's rhythmic reduction" and
hoped: the riff that came back was a new idea that interrupted the mukhada instead of emerging from
it. Here CODE derives the guitar's first statement from the realised head, deterministically, by a
preservation hierarchy (`crew/head_anatomy.py` decides what is identity):

  * rhythmic identity — kept STRONGLY: every pluck of the head (each stroke of a dir or dadir)
    is a riff stroke at the same matra, every pause stays a pause, and the sam is always struck;
  * structural notes — kept STRONGLY: each becomes a power-chord root on the same beat, in the
    same order, so the contour, direction and resolution survive;
  * ornaments — a passing/neighbour note keeps its STROKE but not its pitch (a palm-muted chug on
    the root already sounding: the right hand keeps time, the left stays put); a chikari is a chug;
    the first unaccented meend becomes a guitar slide into its target, the rest land plainly;
  * flexible — octave, exact durations, density: the root is seated low (above `RHYTHM_FLOOR`), a
    held sitar note becomes a strike and a run of palm-muted chugs (the head's accent stays, the
    density rises), an inward stroke (da) rings open and the outward return (ra) chugs.

The roots then pass the raga's DIRECTION rule (a root that would be entered the wrong way holds
the previous root instead) and the existing voicing pass (`riff_voicing.voice_riff`) gives every
stroke its power chord inside the raga — so a fifth the raga forbids becomes a fourth or the octave.

Which slots inherit it (`derived_slots`): the slot of every mukhada section that plays the rhythm
guitar, and every guitar-led section after the first mukhada (the guitar TAKES OVER the head),
unless the section is a deliberate contrast (a breakdown or tihai) — those stay the model's, shown
the head riff as material to contrast against. How each statement then develops is
`crew/riff_statements.py`. Pure: no LLM, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from crew.anchor import render_accents, riff_accents, slot_of
from crew.contracts import RHYTHM_FLOOR, Arrangement, LeadPhrase, RiffNote, RiffPattern, Section, SectionKind
from crew.head_anatomy import HeadNote, accent_beats, head_anatomy, structural_notes
from crew.riff_playability import playability_check
from crew.riff_texture import verify_riff
from crew.riff_voicing import home_root, voice_riff
from raga import RAGAS, direction_violations

PULSE: Final = 0.5               # the chug subdivision a held note is broken into
HOLD_SPLIT: Final = 1.0          # a single-stroke note longer than this becomes strike + chugs
ACCENT_RING: Final = 1.0         # an accented held note rings this long before its chugs
MAX_LOCAL_OCT: Final = 1         # the highest local octave a derived root may take
MIN_LOCAL_OCT: Final = -1        # ...and the lowest (the floor may raise it)
_SLIDES_PER_CYCLE: Final = 1     # meends that become a guitar slide (the sitar bends; you anchor)
VEL_ACCENT: Final = 124
VEL_STRONG: Final = 112
VEL_SOFT: Final = 100
VEL_CHUG_ON: Final = 106         # a chug on the beat — the picking hand leans in...
VEL_CHUG_OFF: Final = 96         # ...and eases off between (never one flat velocity)
_RHYTHM: Final = "rhythm"
_LEAD: Final = "lead"
_MUKHADA: Final = "mukhada"
_CONTRAST_ROLES: Final = frozenset({"breakdown", "tihai"})
_PITCH_MOVES: Final = frozenset({"slide", "long_slide", "pick_scrape", "bend", "hammer_on", "pull_off"})
_EPS: Final = 1e-6


# --------------------------------------------------------------------------- #
# Which slots inherit the head.                                                #
# --------------------------------------------------------------------------- #

def guitar_led(section: Section) -> bool:
    """The guitar holds the foreground: no sitar in the section, or the rhythm guitar leads it."""
    return _LEAD not in section.layers or section.foreground == _RHYTHM


def is_contrast(section: Section) -> bool:
    """A section that DEPARTS on purpose — the breakdown and the tihai keep their own riff."""
    return section.kind is SectionKind.BREAKDOWN or section.form_role in _CONTRAST_ROLES


def derived_slots(arr: Arrangement) -> frozenset[str]:
    """The riff slots that play the head riff: every rhythm-playing mukhada section's slot, and
    every guitar-led, non-contrast rhythm section's slot after the first mukhada. Empty when the
    chart states no mukhada (a song form, a demo chart). Pure."""
    first = next((i for i, s in enumerate(arr.sections) if s.form_role == _MUKHADA), None)
    if first is None:
        return frozenset()
    slots: set[str] = set()
    for i, section in enumerate(arr.sections):
        if _RHYTHM not in section.layers:
            continue
        if section.form_role == _MUKHADA or (i > first and guitar_led(section)
                                              and not is_contrast(section)):
            slots.add(slot_of(section))
    return frozenset(slots)


# --------------------------------------------------------------------------- #
# The derivation.                                                              #
# --------------------------------------------------------------------------- #

def _seat(octave: int, home: int, register: int) -> int:
    """The root's local octave: the head's contour relative to its sam note, seated low — never
    under `RHYTHM_FLOOR`, never above `MAX_LOCAL_OCT`."""
    low = max(MIN_LOCAL_OCT, RHYTHM_FLOOR - register)
    return min(max(octave - home, low), MAX_LOCAL_OCT)


def _stroke(root: tuple[str, int], length: float, *, accent: bool, strong: bool) -> RiffNote:
    """One riff stroke on `root`: an accent or an inward stroke rings OPEN, the outward return
    chugs (a mute only ever on a stroke of a beat or less — it cannot sustain)."""
    mute = not accent and not strong and length <= HOLD_SPLIT + _EPS
    vel = VEL_ACCENT if accent else VEL_STRONG if strong else VEL_SOFT
    return RiffNote(swara=root[0], oct=root[1], dur=round(length, 4), vel=vel,
                    technique="palm_mute" if mute else None)


def _chug(root: tuple[str, int], length: float, onset: float) -> RiffNote:
    on_beat = abs(onset - round(onset)) < _EPS
    return RiffNote(swara=root[0], oct=root[1], dur=round(length, 4),
                    vel=VEL_CHUG_ON if on_beat else VEL_CHUG_OFF,
                    technique="palm_mute" if length <= HOLD_SPLIT + _EPS else None)


def _chug_run(root: tuple[str, int], length: float, onset: float) -> list[RiffNote]:
    """Palm-muted chugs at `PULSE` filling `length` beats from `onset` (a shorter last one)."""
    run: list[RiffNote] = []
    t = 0.0
    while length - t > _EPS:
        piece = min(PULSE, length - t)
        run.append(_chug(root, piece, onset + t))
        t += piece
    return run


def _structural(note: HeadNote, root: tuple[str, int]) -> list[RiffNote]:
    """A structural note as strokes: a compound bol plays the head's own strokes; a held single
    stroke becomes its strike (a ring on an accent) followed by a chug run; a short one, one stroke."""
    if len(note.plucks) > 1:
        return [_stroke(root, p.length, accent=note.accent and k == 0, strong=p.strong)
                for k, p in enumerate(note.plucks)]
    strong = note.plucks[0].strong
    if note.dur <= HOLD_SPLIT + _EPS:
        return [_stroke(root, note.dur, accent=note.accent, strong=strong)]
    strike = ACCENT_RING if note.accent else PULSE
    return ([_stroke(root, strike, accent=note.accent, strong=True)]
            + _chug_run(root, note.dur - strike, note.onset + strike))


def _ornament(note: HeadNote, root: tuple[str, int]) -> list[RiffNote]:
    """An ornament keeps its strokes, not its pitch: chugs on the root already sounding."""
    return [_chug(root, p.length, note.onset + p.offset) for p in note.plucks]


def _with_slide(strokes: list[RiffNote]) -> list[RiffNote]:
    """The meend, on guitar: its first stroke slides into the target (single note — the voicing
    leaves it unchorded, and the renderer starts the slide from the previous pitch)."""
    first = strokes[0].model_copy(update={"technique": "slide"})
    return [first, *strokes[1:]]


class _Deriver:
    """Walks the head's anatomy once, carrying the root that sounds and the slide budget."""

    def __init__(self, anatomy: list[HeadNote], register: int) -> None:
        structural = structural_notes(anatomy)
        self._home = structural[0].oct if structural else 0
        self._register = register
        self._root = self._root_of(structural[0]) if structural else ("S", 0)
        self._sam_root = self._root
        self._slides = _SLIDES_PER_CYCLE

    def _root_of(self, note: HeadNote) -> tuple[str, int]:
        return note.swara, _seat(note.oct, self._home, self._register)

    def strokes(self, note: HeadNote) -> list[RiffNote]:
        if note.role == "rest":
            if note.onset < _EPS:                    # the sam is ALWAYS struck — metal lands it
                return [_stroke(self._sam_root, note.dur, accent=True, strong=True)]
            return [RiffNote(swara="S", dur=round(note.dur, 4), rest=True)]
        if note.role == "ornamental":
            return _ornament(note, self._root)
        previous, self._root = self._root, self._root_of(note)
        out = _structural(note, self._root)
        if (note.meend and not note.accent and self._slides > 0 and self._root != previous
                and out[0].technique is None):
            self._slides -= 1
            out = _with_slide(out)
        return out


def _direction_safe(notes: list[RiffNote], raga: str) -> list[RiffNote]:
    """Roots that obey the raga: a root outside the raga, or entered against its direction rule
    (Bageshree's descent-only Pa from below), HOLDS the previous root instead — a re-strike is
    always legal. The head itself was legal; dropping its ornaments can create a new approach."""
    allowed = set(RAGAS[raga]["allowed"])
    out: list[RiffNote] = []
    prev: tuple[str, int] | None = None
    for note in notes:
        if not note.rest:
            here = (note.swara, note.oct)
            bad = note.swara not in allowed or (prev is not None
                                                and direction_violations([prev, here], raga))
            if bad:
                hold = prev or (home_root(raga), 0)
                technique = None if note.technique in _PITCH_MOVES else note.technique
                note = note.model_copy(update={"swara": hold[0], "oct": hold[1],
                                               "technique": technique})
            prev = (note.swara, note.oct)
        out.append(note)
    return out


def _split_at(notes: list[RiffNote], onsets: Sequence[float]) -> list[RiffNote]:
    """Add a chug wherever an extra right-hand stroke (a chikari) falls INSIDE a sounding stroke:
    the stroke is cut there and the rest of it re-struck palm-muted on the same root."""
    cuts = sorted(set(round(o, 4) for o in onsets))
    out: list[RiffNote] = []
    t = 0.0
    for note in notes:
        pieces = [note]
        if not note.rest:
            inner = [c - t for c in cuts if t + _EPS < c < t + note.dur - _EPS]
            pieces, start = [], 0.0
            for cut in [*inner, note.dur]:
                length = round(cut - start, 4)
                piece = (note.model_copy(update={"dur": length}) if start == 0.0
                         else _chug((note.swara, note.oct), length, t + start))
                pieces.append(piece)
                start = cut
        out.extend(pieces)
        t += note.dur
    return out


def derive_riff_from_mukhada(head: LeadPhrase, *, raga: str, cycle_beats: float,
                             accents: frozenset[float], register: int,
                             extra_onsets: Sequence[float] = ()) -> RiffPattern:
    """The head's FAITHFUL first statement on guitar — one voiced cycle, raga-legal, seated low.

    `accents` are the sam/tali beats (`head_anatomy.accent_beats`); `register` the rhythm voice's
    base octave (for the floor). `extra_onsets` is a SEAM: other right-hand strokes in the cycle (the
    sitar's chikari, laid by another layer) — each one inside a stroke adds a chug there. Pure."""
    anatomy = head_anatomy(head, cycle_beats=cycle_beats, accents=accents)
    deriver = _Deriver(anatomy, register)
    notes = [stroke for note in anatomy for stroke in deriver.strokes(note)]
    notes = _split_at(_direction_safe(notes, raga), extra_onsets)
    roots = " ".join(n.swara for n in structural_notes(anatomy))
    pattern = RiffPattern(reasoning=f"derived by code from the gat head — its strokes are the "
                                    f"rhythm, its structural swaras ({roots}) the roots",
                          notes=notes)
    return voice_riff(pattern, raga, accents)


# --------------------------------------------------------------------------- #
# The head riff for a chart — what the riff generator and its prompt read.     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HeadRiff:
    """The head riff of a chart: the voiced cycle, the slots that inherit it, and any HARD check
    it fails (a derived cycle that fails is never played — the model writes that slot instead,
    shown this cycle as its material)."""
    pattern: RiffPattern
    slots: frozenset[str]
    violations: tuple[str, ...]

    @property
    def playable(self) -> bool:
        return not self.violations


def head_riff(arr: Arrangement, head: LeadPhrase | None, *,
              extra_onsets: Sequence[float] = ()) -> HeadRiff | None:
    """The chart's head riff, or None: only a gat_first piece with a realised head and at least
    one slot to inherit it derives one (in riff_first the head QUOTES the riff instead). Pure."""
    if arr.anchor != "gat_first" or head is None:
        return None
    slots = derived_slots(arr)
    if not slots:
        return None
    pattern = derive_riff_from_mukhada(head, raga=arr.raga, cycle_beats=arr.beats_per_bar,
                                       accents=accent_beats(arr), register=arr.registers[_RHYTHM],
                                       extra_onsets=extra_onsets)
    violations = verify_riff(pattern, cycle_beats=arr.beats_per_bar)
    playable = playability_check(arr)
    if playable is not None:
        violations += playable(pattern)
    return HeadRiff(pattern=pattern, slots=slots, violations=tuple(violations))


def _tokens(pattern: RiffPattern) -> str:
    def token(n: RiffNote) -> str:
        pitch = f"{n.swara}{n.oct:+d}" if n.oct else n.swara
        mark = {"palm_mute": ":pm", "slide": ":slide"}.get(n.technique or "", "")
        return f"{pitch}{mark}({n.dur:g})"
    return " ".join(f"-({n.dur:g})" if n.rest else token(n) for n in pattern.notes)


def render_head_riff(riff: HeadRiff | None, arr: Arrangement, slot: str) -> str:
    """The `{mukhada_riff}` prompt block: the head riff as the riff model's STARTING MATERIAL, its
    identity spelled out, and what to do with it in THIS slot. Benign when there is none. Pure."""
    if riff is None:
        return "  (no head riff — this piece's riff is not derived from a gat head; compose it)"
    accents = render_accents(riff_accents(riff.pattern, arr))
    lines = ["  Code derived the guitar's version of the sitar's mukhada — its strokes are the "
             "rhythm, its structural swaras the power-chord roots, its held notes chug runs, its "
             "kan/passing notes dropped (:pm = palm mute):",
             f"    {_tokens(riff.pattern)}",
             f"  Its IDENTITY — the accent roots ({accents}), the order of its roots, its pauses."]
    if slot in riff.slots:
        lines.append("  This slot normally PLAYS that riff (code develops it statement by statement). "
                     "You are reworking it: keep its accent roots and the order of its roots, change "
                     "what the section asks for.")
    else:
        lines.append("  The head's own slot and the guitar-led sections already play it. For THIS "
                     "slot DEVELOP from it: keep its accent structure (the same roots on the sam and "
                     "the talis) and its structural roots, vary the rest (density, palm-mutes, a "
                     "pedal, a syncopated push). If the section is a deliberate CONTRAST (a "
                     "breakdown, a bridge), contrast it — but build the contrast from a fragment of "
                     "it (its sam root, its opening cell), so the piece stays one idea.")
    return "\n".join(lines)
