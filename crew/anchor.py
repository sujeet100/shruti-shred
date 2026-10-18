"""The ANCHOR seam — which creative voice seeds the piece, and what the other one is shown.

The composers declare `Arrangement.anchor`: `gat_first` (the sitar's mukhada is the source and
the main riff is its rhythmic reduction) or `riff_first` (the riff is the source and the
mukhada QUOTES its accented notes). Until this module the declaration was decorative: the lead
was always composed first and every mukhada riff was told it "reduces" the head, so a
`riff_first` piece was still composed gat-first.

The order itself now follows the anchor (`crew.band.compose_creative_voices`), and this module
is the pure half of the seam: it reads the riff's ACCENTED ROOTS — the swaras sounding on the
sam and the tali, the beats the kick lands with — and renders the gat's view of the source.
The quote is then checked by code (`crew.gat_verifier.verify_riff_quote`), so "the head is the
riff sung" is a verified fact rather than a hope in a prompt. Pure: no LLM, no I/O.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Final

from crew.head_brief import withheld
from crew.contracts import (Arrangement, DebateEvent, HeadIdea, LeadNote, LeadPhrase, RiffNote,
                            RiffPattern, Section)
from gats import stroke_motif

# The accents a quoting head must answer — the sam and the clapped tali, the same matras the
# riff punches. The khali (the "empty" wave) is the tala's breath, never a landing.
QUOTED_ACCENTS: Final = ("sam", "tali")
# Event-data keys the two voices publish their seeds under (the head, the main riff).
HOOK_EVENT_KEY: Final = "mukhada_cell"
RIFF_EVENT_KEY: Final = "mukhada_riff"
_RHYTHM: Final = "rhythm"
_LEAD: Final = "lead"


@dataclass(frozen=True)
class RiffAccent:
    """One accented beat of the riff's cycle and the swara the riff SOUNDS there."""
    beat: float
    kind: str
    swara: str


def _swara_at(pattern: RiffPattern, beat: float) -> str | None:
    """The swara the riff sounds at `beat` of its cycle, or None in a rest.

    Mirrors `riff._sequence_cycle`'s layout: notes laid end-to-end from beat 0, and a
    pattern that falls short has its LAST note extended to the cycle edge."""
    t = 0.0
    for note in pattern.notes:
        if t <= beat < t + note.dur:
            return None if note.rest else note.swara
        t += note.dur
    last = pattern.notes[-1]
    return None if last.rest else last.swara


def riff_accents(pattern: RiffPattern, arr: Arrangement) -> list[RiffAccent]:
    """The riff's accented roots, in cycle order — one per sam/tali beat where it SOUNDS.

    A rest on an accent is omitted: the riff states nothing there, so there is nothing to
    quote. These are the swaras a `riff_first` mukhada must sing on the same beats."""
    found: list[RiffAccent] = []
    for accent in arr.accent_grid:
        if accent.kind not in QUOTED_ACCENTS:
            continue
        swara = _swara_at(pattern, accent.beat)
        if swara is not None:
            found.append(RiffAccent(beat=accent.beat, kind=accent.kind, swara=swara))
    return found


def render_accents(accents: list[RiffAccent]) -> str:
    """The accent table as one prompt/feedback line: `sam beat 0 S, tali beat 4 m`."""
    return ", ".join(f"{a.kind} beat {a.beat:g} {a.swara}" for a in accents)


def render_gat_source(arr: Arrangement, riff: RiffPattern | None) -> str:
    """The gat composer's view of the anchor — what seeds its mukhada.

    `gat_first`: the head IS the source and the riff will reduce it afterwards, so its sam
    and tali swaras become the band's roots. `riff_first` with a riff: the riff's cycle and
    its accented roots, and the instruction to QUOTE them. `riff_first` with no riff on the
    chart (no rhythm-active mukhada) degrades to the gat_first line — there is nothing to
    quote, so the head leads."""
    if arr.anchor != "riff_first" or riff is None:
        return ("  gat_first — YOUR mukhada is the source. The band's main riff is written "
                "afterwards as its rhythmic reduction: the swaras you place on the sam and the "
                "tali become the guitar's low roots, so make them deliberate.")
    cycle = " ".join("-" if n.rest else f"{n.swara}({n.dur:g})" for n in riff.notes)
    accents = riff_accents(riff, arr)
    return (f"  riff_first — the band's MAIN RIFF came first and seeds the piece. Its cycle, "
            f"swara(beats): {cycle}\n"
            f"  Its accented roots: {render_accents(accents)}.\n"
            f"  Your mukhada QUOTES the riff: sound those swaras on those same beats (most of "
            f"them, the sam above all), and sing the raga's melody between them — the listener "
            f"should hear the riff's skeleton sung by the sitar, ornamented and phrased.")


# --------------------------------------------------------------------------- #
# The SEEDS — the core idea carried on the chart (Arrangement.seed_riff / seed_hook). #
# --------------------------------------------------------------------------- #

def slot_of(section: Section) -> str:
    """The riff SLOT a section plays — its explicit `riff_slot`, else its kind."""
    return section.riff_slot or section.kind.value


def main_riff_slot(arr: Arrangement) -> str | None:
    """The slot that RECURS most among the rhythm sections (ties: the first heard) — the main
    riff, which the seed's `main_riff` IS. None when no section plays the rhythm guitar."""
    slots = [slot_of(s) for s in arr.sections if _RHYTHM in s.layers]
    if not slots:
        return None
    counts = Counter(slots)
    return max(dict.fromkeys(slots), key=lambda slot: counts[slot])


def is_song_hook(section: Section, arr: Arrangement) -> bool:
    """In the SONG form the sitar's hook RECURS with the main riff: a lead section over the main
    slot replays `seed_hook` (the gat form's equivalent is the mukhada). False without a seed,
    and False for a section with a role of its own — an intro, a taan, a tihai or an outro is
    NOT the hook even over the main riff (2026-10-12: the Darbari song's intro, taan and outro
    sat on 'main', so the alap was composed as a one-avartan hook cell — nine seconds of sitar in
    a 24-second intro — and the climax taan replayed the hook verbatim)."""
    return (arr.form == "song" and arr.seed_hook is not None and _LEAD in section.layers
            and section.form_role is None and slot_of(section) == main_riff_slot(arr))


def hook_from_events(events: list[DebateEvent]) -> LeadPhrase | None:
    """The head a lead run published on its event stream, or None."""
    data = next(((e.data or {})[HOOK_EVENT_KEY] for e in events
                 if (e.data or {}).get(HOOK_EVENT_KEY)), None)
    return LeadPhrase.model_validate(data) if data else None


def riff_from_events(events: list[DebateEvent]) -> RiffPattern | None:
    """The mukhada section's riff a riff run published on its event stream, or None."""
    data = next(((e.data or {})[RIFF_EVENT_KEY] for e in events
                 if (e.data or {}).get(RIFF_EVENT_KEY)), None)
    return RiffPattern.model_validate(data) if data else None


def with_realized_seeds(arr: Arrangement, events: list[DebateEvent]) -> Arrangement:
    """The chart with the REALIZED head and main riff stored as its seeds, where it had none —
    so a later revise hands the riff its head (gat_first) and the gat its riff (riff_first)
    instead of nothing. A seed already set (the Composer's) is never overwritten. Pure."""
    update: dict = {}
    if arr.seed_hook is None and (hook := hook_from_events(events)) is not None:
        update["seed_hook"] = hook
    if arr.seed_riff is None and (riff := riff_from_events(events)) is not None:
        update["seed_riff"] = riff
    return arr.model_copy(update=update) if update else arr


def riff_seed_for_lead(arr: Arrangement) -> RiffPattern | None:
    """The riff a gat must quote: the seed riff, only in a riff_first piece."""
    return arr.seed_riff if arr.anchor == "riff_first" else None


def hook_seed_for_riff(arr: Arrangement) -> LeadPhrase | None:
    """The head a riff reduces: the seed hook, only in a gat_first piece."""
    return arr.seed_hook if arr.anchor == "gat_first" else None


def riff_tokens(notes: list[RiffNote]) -> str:
    return " ".join("-" if n.rest else f"{n.swara}{n.oct:+d}({n.dur:g})" if n.oct
                    else f"{n.swara}({n.dur:g})" for n in notes)


def lead_tokens(notes: list[LeadNote]) -> str:
    """swara(beats), with the mizrab bol when there is one — `m:dir(1)`: the strokes are half of
    a gat head's identity, so the develop prompts must see them."""
    def token(n: LeadNote) -> str:
        pitch = f"{n.swara}{n.oct:+d}" if n.oct else n.swara
        return f"{pitch}:{n.bol}({n.dur:g})" if n.bol else f"{pitch}({n.dur:g})"
    return " ".join("-" if n.rest else token(n) for n in notes)


def hook_stroke_motif(hook: LeadPhrase) -> tuple[str, ...] | None:
    """The hook's recurring bol figure (`gats.stroke_motif`) over its sounding notes. Pure."""
    return stroke_motif([n.bol for n in hook.notes if not n.rest])


def render_song_seed(arr: Arrangement) -> str:
    """The `{song_seed}` block every develop prompt carries: the form, the energy arc, the main
    riff and the hook — framed as YOUR core idea to develop, never to replace. One benign line
    when the chart carries no seed (the legacy path), so one prompt serves both. Pure."""
    if arr.seed_riff is None and arr.seed_hook is None and arr.seed_head is None:
        return "  (no song seed — develop the chart's motif)"
    lines = [f"  You composed this core idea first — DEVELOP it, never replace it. Form: {arr.form}."]
    if arr.energy_arc:
        lines.append(f"  Energy arc: {arr.energy_arc}")
    if arr.seed_riff is not None and not withheld():          # FREE: no riff notes to borrow from
        lines.append(f"  Main riff (slot '{main_riff_slot(arr)}', one cycle, swara(beats)): "
                     f"{riff_tokens(arr.seed_riff.notes)}")
    if arr.seed_hook is not None:
        lines.append(f"  The hook (one avartan, swara:bol(beats)): {lead_tokens(arr.seed_hook.notes)}")
        motif = hook_stroke_motif(arr.seed_hook)
        if motif:
            lines.append(f"  Its stroke motif — the recurring bol figure, a motif as much as any "
                         f"swaras (bring it back, vary it): {' '.join(motif)}")
    elif arr.seed_head is not None:
        lines += render_head_idea(arr.seed_head)
    return "\n".join(lines)


def render_head_idea(head: HeadIdea) -> list[str]:
    """The gat head's IDEA as the develop prompts read it, until the head itself is composed. In
    the FREE head brief only the idea and its sam swara are shown: the motif and strokes are the
    head's to define (`crew/head_brief.py`). Pure."""
    if withheld():
        return ["  The gat HEAD'S IDEA (the mukhada is composed FROM it — land its sam swara; the motif "
                "and the stroke line are yours):",
                f"    idea: {head.idea.strip() or '(not stated)'}",
                f"    sam swara: {head.sam_swara}"]
    strokes = " ".join(head.stroke_line) if head.stroke_line else "(not planned — plan it)"
    return ["  The gat HEAD'S IDEA (the mukhada is composed FROM it — keep its sam swara, let its "
            "cell recur, play its stroke line):",
            f"    idea: {head.idea.strip() or '(not stated)'}",
            f"    sam swara: {head.sam_swara}    core cell: {' '.join(head.cell)}",
            f"    stroke line (one token per matra): {strokes}"]
