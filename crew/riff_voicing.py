"""Riff VOICING — every bare stroke becomes a power chord, inside the raga, by its FUNCTION.

The evidence (talk/HANDOVER.md §2-3, measured 2026-10-11): the riff Sujit judged best (song A,
one bare model call) put a power chord on EVERY stroke; our pipeline's riff chorded 15% of its
strokes and played the rest as single low notes — thin, however good the rhythm. A's only
out-of-raga notes were those chords' fifths (sitar, bass and every root were legal); Sujit chose
STRICT RAGA over that "fusion harmony" by ear, so every tone here stays inside the grammar. A
FOURTH is as consonant under distortion as a fifth (it is the power chord inverted), so a root
whose fifth is illegal can still carry weight.

So voicing is CODE, not something the model must remember: the model writes roots and rhythm,
and this pass gives each bare stroke root + dyad + octave. A chord the model wrote deliberately
(a colour voicing) is kept as written. Pure: no LLM, no I/O.

The choice follows the stroke's FUNCTION (the GPT review's algorithm, strict mode — 2026-10-11):
  * a TRANSITION (a slide, bend or legato note) and a rest stay SINGLE — the pitch wheel is
    channel-wide, so a chord would silently disarm the gesture (src/render.py). A legato that
    could never sound (cycle start, after a rest, onto the same pitch, on a chord) is first
    stripped to a plain stroke, so it does not cost the riff its weight;
  * a CHUG (palm-muted, off the accents) takes the fifth, else the OCTAVE — the octave is the
    chug's natural weight, and a fourth adds nothing a muted stroke can carry;
  * a MOVE (an open, short stroke) takes the fifth, else the fourth, else the octave;
  * an ACCENT (on the sam or a tali) or a SUSTAINED chord (open, a beat or longer) takes the
    fifth, else the fourth, and only then a ONE-DIRECTION tone (Todi's Pa — "allow Sa–Pa
    selectively", never on every stroke), else the octave.
  A dyad tone is never an ANDOLAN swara on a stroke longer than a beat (a held tempered tone
  fights the sitar's sway). Bageshree's Sa still takes Sa–Ma (its idiomatic dyad): the fourth is
  free there, so its descent-only Pa is never reached.

`home_root` names the swara a riff should circle, from the raga's own resting notes.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from crew.contracts import RiffNote, RiffPattern
from raga import NYAS, RAGAS, SWARAS, directional_varjya

_FIFTH: Final = 7
_FOURTH: Final = 5
# Techniques that move pitch or slur — a chord would disarm them, so their notes stay single.
_SINGLE_ONLY: Final = frozenset({"slide", "long_slide", "pick_scrape", "bend",
                                 "hammer_on", "pull_off"})
_LEGATO: Final = frozenset({"hammer_on", "pull_off"})
# A stroke this long is SUSTAINED when open, and an andolan swara may not be held in it.
_HELD_BEATS: Final = 1.0
_BY_SEMITONE: Final = {semi: name for name, semi in SWARAS.items()}
_ONSET_TOLERANCE: Final = 1e-6


class StrokeRole(str, Enum):
    """What a stroke DOES in the riff — it decides how heavily it is voiced."""
    CHUG = "chug"              # palm-muted, off the accents
    MOVE = "move"              # an open, short stroke
    ACCENT = "accent"          # on the sam or a tali
    SUSTAINED = "sustained"    # open, a beat or longer
    TRANSITION = "transition"  # carries a slide/bend/legato — stays single


# The dyad search per role: (interval, may use a one-direction tone), in order of preference.
_SEARCH: Final[dict[StrokeRole, tuple[tuple[int, bool], ...]]] = {
    StrokeRole.CHUG: ((_FIFTH, False),),
    StrokeRole.MOVE: ((_FIFTH, False), (_FOURTH, False)),
    StrokeRole.ACCENT: ((_FIFTH, False), (_FOURTH, False), (_FIFTH, True), (_FOURTH, True)),
    StrokeRole.SUSTAINED: ((_FIFTH, False), (_FOURTH, False), (_FIFTH, True), (_FOURTH, True)),
    StrokeRole.TRANSITION: (),
}


def stroke_role(note: RiffNote, *, on_accent: bool) -> StrokeRole:
    """A stroke's function, from its articulation, length and place in the cycle."""
    if note.technique in _SINGLE_ONLY:
        return StrokeRole.TRANSITION
    if on_accent:
        return StrokeRole.ACCENT
    if note.technique == "palm_mute":
        return StrokeRole.CHUG
    return StrokeRole.SUSTAINED if note.dur >= _HELD_BEATS else StrokeRole.MOVE


def _usable(tone: str, dur: float, raga: str, *, one_way_ok: bool) -> bool:
    """Is `tone` a legal dyad tone here — in the raga, direction-free unless the role allows
    a one-direction tone, and not an andolan swara held under the sitar?"""
    facts = RAGAS[raga]
    if tone not in facts["allowed"]:
        return False
    if tone in directional_varjya(raga) and not one_way_ok:
        return False
    return not (tone in (facts.get("andolan") or []) and dur > _HELD_BEATS)


def power_voicing(root: str, dur: float, raga: str,
                  role: StrokeRole = StrokeRole.MOVE) -> list[str]:
    """The power-chord stack for a bare stroke on `root` in this ROLE: [dyad, root] (dyad +
    the octave) when the role's search finds a legal dyad, else [root] (the octave alone).
    Every tone is legal by construction. A TRANSITION gets no stack at all ([])."""
    for interval, one_way_ok in _SEARCH[role]:
        tone = _BY_SEMITONE[(SWARAS[root] + interval) % 12]
        if _usable(tone, dur, raga, one_way_ok=one_way_ok):
            return [tone, root]
    return [] if role is StrokeRole.TRANSITION else [root]


def _is_bare(note: RiffNote) -> bool:
    """A stroke the model left unvoiced: no chord, or only its own octave."""
    return not note.chord or note.chord == [note.swara]


def voice_note(note: RiffNote, raga: str, *, on_accent: bool = False) -> RiffNote:
    """One note, voiced by its function: a bare stroke gains its power chord; a rest, a
    transition or the model's own colour chord is unchanged."""
    if note.rest or not _is_bare(note):
        return note
    role = stroke_role(note, on_accent=on_accent)
    if role is StrokeRole.TRANSITION:
        return note
    chord = power_voicing(note.swara, note.dur, raga, role)
    return note if chord == note.chord else note.model_copy(update={"chord": chord})


def _legato_is_meaningless(note: RiffNote, previous: RiffNote | None) -> bool:
    """Can this hammer-on/pull-off physically happen? A legato note sounds by fretting from a
    string that is ALREADY RINGING at another pitch on the same string, unpicked. So it cannot
    open the cycle (that stroke is the sam — the hardest pick in the riff), follow a rest
    (nothing rings), land on the pitch already sounding (no fret to hammer to), or carry a
    chord (a slur is one string; the renderer's pitch wheel is channel-wide and disarms it)."""
    if previous is None or previous.rest or note.chord:
        return True
    return (note.swara, note.oct) == (previous.swara, previous.oct)


def strip_meaningless_legato(pattern: RiffPattern) -> RiffPattern:
    """The cycle with every physically meaningless hammer_on/pull_off turned into a plain
    stroke, so voicing can give it its power chord. The 2026-10-11 breakdown riff slurred
    nearly every stroke; since a legato note stays single, it left no power chords at all.
    A meaningful slur (a new pitch from a ringing, single note) is kept. Idempotent; pure."""
    notes: list[RiffNote] = []
    previous: RiffNote | None = None
    for note in pattern.notes:
        if (not note.rest and note.technique in _LEGATO
                and _legato_is_meaningless(note, previous)):
            note = note.model_copy(update={"technique": None})
        notes.append(note)
        previous = note
    if notes == list(pattern.notes):
        return pattern
    return pattern.model_copy(update={"notes": notes})


def _onsets(pattern: RiffPattern) -> list[float]:
    """Each note's onset in the cycle — laid end-to-end from beat 0, as the arrangement does."""
    t, out = 0.0, []
    for note in pattern.notes:
        out.append(t)
        t += note.dur
    return out


def voice_riff(pattern: RiffPattern, raga: str,
               accents: frozenset[float] = frozenset()) -> RiffPattern:
    """The cycle with every bare stroke voiced by its function. `accents` are the within-cycle
    beats of the sam and talis (empty = no stroke is an accent). Meaningless legato is
    stripped FIRST (`strip_meaningless_legato`), so a slur that could never sound does not
    keep its stroke single. Idempotent; pure."""
    pattern = strip_meaningless_legato(pattern)
    notes = [voice_note(n, raga, on_accent=any(abs(t - a) < _ONSET_TOLERANCE for a in accents))
             for n, t in zip(pattern.notes, _onsets(pattern))]
    if notes == list(pattern.notes):
        return pattern
    return pattern.model_copy(update={"notes": notes})


def power_weight(root: str, raga: str) -> int:
    """How heavy the strongest legal power chord on `root` is: 2 = fifth, 1 = fourth, 0 = octave."""
    chord = power_voicing(root, _HELD_BEATS, raga, StrokeRole.ACCENT)
    if len(chord) == 1:
        return 0
    return 2 if (SWARAS[chord[0]] - SWARAS[root]) % 12 == _FIFTH else 1


def home_root(raga: str) -> str:
    """The swara a riff circles: Sa when Sa is one of the raga's CORE resting notes (every raga
    on the menu but Marwa), else the core rest with the heaviest legal power chord. Marwa's Sa is
    deliberately weak (its core rests are komal re and Dha), so its riff lives on Dha, which
    carries a full fifth. Derived from `raga.NYAS` (source-verified); pure."""
    core = NYAS[raga]["core"]
    if "S" in core:
        return "S"
    return max(core, key=lambda sw: (power_weight(sw, raga), -core.index(sw)))


def render_power_roots(raga: str) -> str:
    """Which roots carry which power chord — prompt guidance for choosing roots (the
    algorithm's step 4: prefer a root whose full power chord is legal). Pure."""
    by_weight: dict[int, list[str]] = {2: [], 1: [], 0: []}
    for sw in RAGAS[raga]["allowed"]:
        by_weight[power_weight(sw, raga)].append(sw)
    parts = [f"full power chord (root + fifth): {' '.join(by_weight[2]) or '—'}",
             f"inverted (root + fourth): {' '.join(by_weight[1]) or '—'}",
             f"octave only: {' '.join(by_weight[0]) or '—'}"]
    return "  " + "; ".join(parts)
