"""How the HEAD RIFF develops across its statements — faithful first, then the guitar's own.

The head riff (`crew/riff_from_mukhada.py`) is the sitar's mukhada carried onto the guitar. A
listener only hears it as the head's child if the FIRST guitar statement is recognisably the
head; after that the guitar may grow away from it — that is development, not collage. So the
statements of a head-derived slot follow their own policy (the generic riff family,
`crew/riff_family.py`, keeps every other slot):

  * the FIRST guitar-led statement plays the derived cycle as it is (faithful);
  * later guitar-led statements alternate HEAVY (every off-accent stroke palm-muted, the chug
    fills dropped onto a pedal of the sam root — the accent roots still name the head) and
    SYNCOPATED (heavy, with the last tali PUSHED an eighth early — the jolt that says the guitar
    now owns the figure);
  * under the SITAR (the lead in the section and not behind the guitar) the riff makes SPACE:
    only the accent strokes remain, struck open and left ringing to the next one, so the sitar's
    andolan and meend have room; the head's pauses stay pauses;
  * the role cases the riff family already decides win first: a short taan thins ("stripped"),
    the long taan drives on a pedal, the very last bar of the piece doubles.

Only guitar-led statements advance the count, so a statement under the sitar never uses up the
faithful one.

A RIFF_FIRST piece has no head riff (the head quotes the riff instead), so its main riff used to
take the generic family, which plays a 2-bar section as "base, base": on
`fusion_20261012_152048` one 16-beat cycle ran eight times, unchanged, under a head, a manjha
and an antara (both the GPT review and ours flagged it). `riff_first_variant` develops it by the
section's ROLE with the same statements: faithful under every first statement of the head (the
head is the riff sung), a syncopated reprise after it, SPACE under the manjha (the sitar goes
down into the guitar's register), and heavy then syncopated under the antara, where the sitar
leaves the head's contour and the guitar stops tracing it. Every transform reuses the cycle's own roots and is re-voiced inside the raga; one
that would enter a root against the raga's direction rule falls back to a pitch-safe variant
(`prime` for the heavy ones, a sam-root pedal for space). Pure: no LLM, no I/O.
"""

from __future__ import annotations

from typing import Final

from crew.contracts import RiffNote, RiffPattern, Section
from crew.riff_family import apply_variant, variant_for_bar
from crew.riff_from_mukhada import guitar_led
from crew.riff_voicing import voice_riff
from raga import direction_violations

PUSH: Final = 0.5                 # how early the syncopated statement strikes its last tali
_MUTE_MAX: Final = 1.0            # a palm mute only on a stroke this long or shorter
_PITCH_MOVES: Final = frozenset({"slide", "long_slide", "pick_scrape", "bend", "hammer_on", "pull_off"})
_FAMILY_FIRST: Final = frozenset({"stripped", "pedal", "double"})
_STATEMENTS: Final = frozenset({"base", "heavy", "syncopated"})
_EPS: Final = 1e-6


def _onsets(notes: list[RiffNote]) -> list[float]:
    t, out = 0.0, []
    for note in notes:
        out.append(t)
        t += note.dur
    return out


def _on(beat: float, accents: frozenset[float]) -> bool:
    return any(abs(beat - a) < _EPS for a in accents)


def _bare(note: RiffNote, **update: object) -> RiffNote:
    """A copy to be RE-VOICED: its chord cleared, so the voicing pass seats it for its new role."""
    return note.model_copy(update={"chord": None, **update})


def _heavy(notes: list[RiffNote], accents: frozenset[float]) -> list[RiffNote]:
    """Accent strokes kept as written; every other stroke palm-muted (when short enough), and a
    stroke that only RE-STRIKES the root already sounding drops onto the pedal (the sam root)."""
    sounding = [n for n in notes if not n.rest]
    if not sounding:
        return list(notes)
    pedal = (sounding[0].swara, sounding[0].oct)
    out: list[RiffNote] = []
    melodic: tuple[str, int] | None = None
    for note, onset in zip(notes, _onsets(notes)):
        if note.rest:
            out.append(note.model_copy())
            continue
        here = (note.swara, note.oct)
        mute = "palm_mute" if note.dur <= _MUTE_MAX + _EPS else None
        if _on(onset, accents):
            out.append(note.model_copy())
        elif here == melodic:
            out.append(_bare(note, swara=pedal[0], oct=pedal[1], technique=mute))
        else:
            technique = None if note.technique in _PITCH_MOVES else mute
            out.append(_bare(note, technique=technique))
        melodic = here
    return out


def _push_last_tali(notes: list[RiffNote], accents: frozenset[float]) -> list[RiffNote]:
    """The last accent after the sam struck `PUSH` early: the strokes before it give up the time
    (the shortest vanish), never the sam stroke itself. Unchanged when there is no room."""
    onsets = _onsets(notes)
    target = next((i for i in range(len(notes) - 1, 0, -1)
                   if not notes[i].rest and onsets[i] > _EPS and _on(onsets[i], accents)), None)
    if target is None or onsets[target] - notes[0].dur < PUSH - _EPS:
        return list(notes)
    out = [n.model_copy() for n in notes]
    need, j = PUSH, target - 1
    while need > _EPS and j >= 1:
        take = min(out[j].dur, need)
        need -= take
        remaining = round(out[j].dur - take, 4)
        if remaining <= _EPS:
            out.pop(j)
            target -= 1
        else:
            out[j] = out[j].model_copy(update={"dur": remaining})
        j -= 1
    if need > _EPS:
        return list(notes)
    pushed = out[target]
    out[target] = pushed.model_copy(update={"dur": round(pushed.dur + PUSH, 4)})
    return out


def _space(notes: list[RiffNote], accents: frozenset[float]) -> list[RiffNote]:
    """Only the accent strokes, struck open and ringing to the next one; every other stroke folds
    into the ring before it (or into silence after a pause)."""
    out: list[RiffNote] = []
    for note, onset in zip(notes, _onsets(notes)):
        if note.rest:
            out.append(note.model_copy())
        elif _on(onset, accents) or not out:
            out.append(_bare(note, technique=None))
        else:                                   # the ring (or the pause) before it lasts longer
            out[-1] = out[-1].model_copy(update={"dur": round(out[-1].dur + note.dur, 4)})
    return out


def _sam_pedal(notes: list[RiffNote]) -> list[RiffNote]:
    """Every stroke on the sam root — a single pitch can never break a direction rule."""
    first = next((n for n in notes if not n.rest), None)
    if first is None:
        return list(notes)
    return [n.model_copy() if n.rest else _bare(n, swara=first.swara, oct=first.oct)
            for n in notes]


def _legal(notes: list[RiffNote], raga: str) -> bool:
    return not direction_violations([(n.swara, n.oct) for n in notes if not n.rest], raga)


def _voiced(notes: list[RiffNote], raga: str, accents: frozenset[float]) -> list[RiffNote]:
    return list(voice_riff(RiffPattern(notes=notes), raga, accents).notes)


def apply_statement(notes: list[RiffNote], variant: str, *, raga: str,
                    accents: frozenset[float]) -> list[RiffNote]:
    """The cycle as the named statement — heavy, syncopated or space — voiced inside the raga,
    or its pitch-safe fallback when the transform would break the direction rule. Any other name
    is a riff-family variant (`apply_variant`). Pure."""
    if variant == "heavy":
        candidate, fallback = _heavy(notes, accents), apply_variant(notes, "prime")
    elif variant == "syncopated":
        candidate = _push_last_tali(_heavy(notes, accents), accents)
        fallback = apply_variant(notes, "prime")
    elif variant == "space":
        candidate, fallback = _space(notes, accents), _space(_sam_pedal(notes), accents)
    else:
        return apply_variant(notes, variant)                     # type: ignore[arg-type]
    chosen = candidate if _legal(candidate, raga) else fallback
    return _voiced(chosen, raga, accents)


def under_sitar(section: Section) -> bool:
    """The sitar plays over the riff here — the riff makes room for it."""
    return not guitar_led(section)


def statement_variant(section: Section, bar_index: int, bars: int, *, is_final_rhythm: bool,
                      statement: int) -> str:
    """The POLICY for one bar of a head-derived slot. `statement` counts the guitar-led statements
    already played by this slot, piece-wide. Pure."""
    family = variant_for_bar(section, bar_index, bars, is_final_rhythm=is_final_rhythm)
    if family in _FAMILY_FIRST:
        return family
    if under_sitar(section):
        return "space"
    if statement == 0:
        return "base"
    return "heavy" if statement % 2 == 1 else "syncopated"


_ROLE_STATEMENTS: Final = {"manjha": ("space",), "antara": ("heavy", "syncopated")}


def riff_first_variant(section: Section, bar_index: int, bars: int, *, is_final_rhythm: bool,
                       reprise: bool) -> str:
    """The POLICY for one bar of a riff_first piece's main riff. `reprise` is True from the second
    mukhada section on. Pure."""
    family = variant_for_bar(section, bar_index, bars, is_final_rhythm=is_final_rhythm)
    if family in _FAMILY_FIRST:
        return family
    if section.form_role == "mukhada":
        return "syncopated" if reprise and bar_index % 2 == 1 else "base"
    cycle = _ROLE_STATEMENTS.get(section.form_role or "")
    return cycle[bar_index % len(cycle)] if cycle else family


def develop_riff_first(base: list[RiffNote], section: Section, *, is_final_rhythm: bool,
                       reprise: bool, raga: str,
                       accents: frozenset[float]) -> list[list[RiffNote]]:
    """A riff_first section's per-bar cycles of the main riff, each the statement
    `riff_first_variant` selects. Pure."""
    return [apply_statement(base, riff_first_variant(section, bar, section.bars,
                                                     is_final_rhythm=is_final_rhythm,
                                                     reprise=reprise),
                            raga=raga, accents=accents)
            for bar in range(section.bars)]


def develop_statements(base: list[RiffNote], section: Section, *, is_final_rhythm: bool,
                       first_statement: int, raga: str,
                       accents: frozenset[float]) -> tuple[list[list[RiffNote]], int]:
    """A head-derived section's per-bar cycles, and the statement count after it (the caller
    threads it to the slot's next section). Pure."""
    cycles: list[list[RiffNote]] = []
    statement = first_statement
    for bar in range(section.bars):
        variant = statement_variant(section, bar, section.bars, is_final_rhythm=is_final_rhythm,
                                    statement=statement)
        cycles.append(apply_statement(base, variant, raga=raga, accents=accents))
        if variant in _STATEMENTS:
            statement += 1
    return cycles, statement
