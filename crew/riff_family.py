"""
The riff FAMILY (step 2 of the gat-led campaign) — DETERMINISTIC variations of a slot's
base riff, so a recurring riff DEVELOPS instead of looping unchanged (the monotony Sujit
heard: one cycle repeated for minutes). The LLM composes ONE cycle per slot (its identity);
CODE varies it across the bars and the reprises. This is the same "code owns the recurrence"
lesson as `riff_slot`, extended from "when does the hook return" to "how does it change when
it does".

Why code, not the LLM: the variations are MECHANICAL (mute the chug, thin the attacks, add
an octave), and doing them in code keeps them free (no extra LLM calls), consistent, and
LEGAL BY CONSTRUCTION — every transform only reuses swaras the base already carries (or adds
a note's OWN swara for the octave power chord), so a family member can never leave the raga
and needs no guardrail.

Pure: RiffNote in, RiffNote out — no LLM, no I/O, fully unit-tested. `apply_variant` names the
transform; `variant_for_bar` is the POLICY (which variant a given bar plays), driven by the
section's `form_role` (from step 1) and its position — so the family engages exactly on a real
gat chart and a form-less demo/fixture is still placed literally (variant "base").
"""

from __future__ import annotations

from typing import Callable, Literal

from crew.contracts import RiffNote, Section

# The family members. "base" = the cycle as written; the rest develop it (see the transforms).
RiffVariant = Literal["base", "prime", "stripped", "double"]


def _base(notes: list[RiffNote]) -> list[RiffNote]:
    """A — the base cycle, unchanged (the statement)."""
    return [n.model_copy() for n in notes]


def _prime(notes: list[RiffNote]) -> list[RiffNote]:
    """A' — the SAME pitches (so the hook is still recognisable), restated as a tighter
    palm-muted chug with a slide turnaround on the last SOUNDING note leading back into the
    loop. Pitch set and rests are untouched, so it is legal by construction; only
    articulation/feel change."""
    if not notes:
        return []
    out = [n.model_copy() if n.rest else n.model_copy(update={"technique": n.technique or "palm_mute"})
           for n in notes]
    for i in range(len(out) - 1, -1, -1):            # the turnaround lands on the last SOUNDING note
        if not out[i].rest:
            out[i] = out[i].model_copy(update={"technique": "slide"})
            break
    return out


def _stripped(notes: list[RiffNote]) -> list[RiffNote]:
    """Thin the riff to half its attacks (keep every other note, sustain each to fill the gap)
    so a taan / melodic line has room to breathe — GPT's "space for the sitar". The kept
    pitches are a SUBSET of the base, so it stays legal by construction. Placement clips any
    overrun, so doubling the durations is safe."""
    if len(notes) <= 1:
        return [n.model_copy() for n in notes]
    return [n.model_copy(update={"dur": n.dur * 2}) for n in notes[::2]]


def _double(notes: list[RiffNote]) -> list[RiffNote]:
    """The HEAVIEST version — an octave power chord on every note (stack the note's OWN swara
    a register up) plus a palm-mute for weight; the climactic version to land the piece on.
    The added chord tone IS the root swara, already legal, so this stays legal by
    construction (the same rule that makes `Note.chord` power chords legal)."""
    out: list[RiffNote] = []
    for n in notes:
        if n.rest:                                      # a rest carries no voicing — leave the space
            out.append(n.model_copy())
            continue
        chord = list(n.chord or [])
        if n.swara not in chord:
            chord.append(n.swara)                       # root + its own octave = a power chord
        out.append(n.model_copy(update={"chord": chord, "technique": n.technique or "palm_mute"}))
    return out


_TRANSFORMS: dict[str, Callable[[list[RiffNote]], list[RiffNote]]] = {
    "base": _base, "prime": _prime, "stripped": _stripped, "double": _double,
}

# The form roles whose riff should be thinned so the melodic line leads (taans, an alaap-like
# intro). A rhythm layer under these makes ROOM rather than competing.
_STRIPPED_ROLES: frozenset[str] = frozenset({"taan_short", "taan_long"})


def apply_variant(notes: list[RiffNote], variant: RiffVariant) -> list[RiffNote]:
    """Return the base cycle transformed into the named family member. Legal by construction."""
    return _TRANSFORMS[variant](notes)


def variant_for_bar(section: Section, bar_index: int, bars: int, *,
                    is_final_rhythm: bool) -> RiffVariant:
    """The POLICY — which family member bar `bar_index` of `section` plays. Pure.

    Reads the section's `form_role` (step 1) and its position, never the notes:
      * no declared gat form (form_role is None) -> "base": place the cycle literally, so a
        legacy/demo chart is unchanged (this is why the whole existing test-suite stays green);
      * a taan section          -> "stripped": thin the riff so the taan leads;
      * the last bar of the final rhythm section -> "double": land the ending on the heaviest hit;
      * every 3rd bar of a section of >=3 bars   -> "prime": vary after two cycles, so no more
        than two identical cycles run back-to-back (GPT: "A, A, then A'");
      * otherwise               -> "base".
    """
    if section.form_role is None:
        return "base"
    if section.form_role in _STRIPPED_ROLES:
        return "stripped"
    if is_final_rhythm and bar_index == bars - 1:
        return "double"
    if bars >= 3 and (bar_index + 1) % 3 == 0:
        return "prime"
    return "base"


def develop_section(base: list[RiffNote], section: Section, *,
                    is_final_rhythm: bool) -> list[list[RiffNote]]:
    """Expand a section's ONE base cycle into its per-bar cycles (one list per bar), each the
    family member `variant_for_bar` selects. This is what turns "repeat the same cycle N times"
    into a developing sequence. Pure."""
    return [apply_variant(base, variant_for_bar(section, i, section.bars,
                                                 is_final_rhythm=is_final_rhythm))
            for i in range(section.bars)]
