"""
The FORM BUDGET — how much form a requested length can hold, and whether a chart fits it.

A stated length is a hard number the LLM is bad at: the composers think in sections, but a
piece's duration is `avartans x matras x 60 / bpm`, and nobody does that arithmetic reliably
mid-argument. So code owns it — the same split as the tala's accent grid. The budget is
computed once from the brief, rendered into the composer prompt (the ask), and checked by the
composer guardrail (the enforcement), so the two always agree.

A short piece also cannot carry the full gat form: the full form's 3-avartan intro alone is
22.5 s at 128 bpm in teentaal. Under `SHORT_FORM_MAX_S` the budget relaxes the minimums that
only make sense at length — the intro may be one avartan, a returning mukhada one avartan, and
the climax is one taan. What stays non-negotiable at any length: the mukhada is stated and
RETURNS (that is what makes it a gat), and the raga's grammar.

The gat is OPTIONAL (Sujit, 2026-10-11): a chart may declare the SONG form instead. The intro
and return minimums are gat rules (the alap, the mukhada's return), so the composer guardrail
applies them to the gat form only; the length and the taan_long cap hold for both forms.

Pure — no LLM, no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Optional

from talas import TALAS

# Below this stated length the piece is composed in the short form (Sujit, 2026-10-11:
# a 60-second opener cannot hold a 3-avartan alap plus the full gat cycle; raised from 90 the
# same day so a 90-second opener keeps a short intro — at 128 bpm the full form's alap alone
# would be a quarter of it, with the live guitarist waiting through all of it).
SHORT_FORM_MAX_S: Final = 120
# A chart may miss the target by this many avartans either way: the composers balance it
# against the form, and the ending's final stroke adds a beat anyway.
LENGTH_TOLERANCE_AVARTANS: Final = 1
# An alap needs TIME to establish a raga, whatever the clip's length (Sujit, 2026-10-12: "even
# if the user asks for a smaller audio, allocate enough time for the alap, or remove the alap if
# it's not possible to fit everything"). The 2026-10-12 Darbari intro was one short-form avartan
# — ~10 s left to compose after code's pause — and came back as two phrases and eleven notes
# (GPT: "an exercise rather than a raga exposition"). Raised 18 -> 30 the same day: the floor
# counts the whole intro SECTION, and a clean-guitar lead-in (up to an avartan) plus code's
# breath before the gat come out of it — at 120 bpm an 18 s floor left ~13 s of actual alap,
# where GPT's second review asked for 24-32 s of active development. 30 s leaves ~21 s.
# A floor, not a target: how the time is split is the composer's call.
INTRO_MIN_S: Final = 30.0


@dataclass(frozen=True)
class FormBudget:
    """The form minimums for one brief, plus its target length when the user stated one.

    `duration_s` is the requested length in seconds (None = no length asked for, so no length
    check); `fixed_bpm` is the user's tempo when they fixed it — the draft's own bpm counts
    otherwise, because a draft that chooses its tempo also chooses its avartan length."""
    min_intro_bars: int
    min_return_bars: int
    max_taan_long: int
    short: bool = False
    duration_s: Optional[int] = None
    fixed_bpm: Optional[int] = None


FULL_FORM: Final = FormBudget(min_intro_bars=3, min_return_bars=2, max_taan_long=2)
_SHORT_FORM: Final = FormBudget(min_intro_bars=1, min_return_bars=1, max_taan_long=1, short=True)


def form_budget(duration_s: Optional[int], fixed_bpm: Optional[int] = None) -> FormBudget:
    """The budget for a requested length: the full form when no length (or a long one) was
    asked for, the short form under `SHORT_FORM_MAX_S`. Either way it carries the target."""
    base = _SHORT_FORM if duration_s is not None and duration_s < SHORT_FORM_MAX_S else FULL_FORM
    return FormBudget(base.min_intro_bars, base.min_return_bars, base.max_taan_long,
                      short=base.short, duration_s=duration_s, fixed_bpm=fixed_bpm)


def avartan_seconds(tala: str, bpm: int) -> float:
    """One tala cycle in seconds — a matra is one quarter-note beat."""
    return TALAS[tala]["matras"] * 60.0 / bpm


def target_avartans(budget: FormBudget, tala: str, bpm: int) -> Optional[int]:
    """How many avartans the requested length is at this tala and tempo (at least one), or
    None when no length was asked for."""
    if budget.duration_s is None:
        return None
    return max(1, round(budget.duration_s / avartan_seconds(tala, budget.fixed_bpm or bpm)))


def min_intro_bars(budget: FormBudget, tala: str, bpm: int, form: str = "gat") -> int:
    """The fewest avartans an alap may have: never under `INTRO_MIN_S` at this tala and tempo,
    and in the gat form never under the form's own minimum (a gat rule)."""
    floor = math.ceil(INTRO_MIN_S / avartan_seconds(tala, budget.fixed_bpm or bpm) - 1e-9)
    return max(budget.min_intro_bars, floor) if form == "gat" else floor


def length_error(budget: FormBudget, tala: str, bpm: int, total_bars: int) -> Optional[str]:
    """The guardrail's length check: an exact, actionable error when the chart's total
    avartans miss the target by more than the tolerance, else None."""
    target = target_avartans(budget, tala, bpm)
    if target is None or abs(total_bars - target) <= LENGTH_TOLERANCE_AVARTANS:
        return None
    effective_bpm = budget.fixed_bpm or bpm
    seconds = total_bars * avartan_seconds(tala, effective_bpm)
    return (f"The piece must last about {budget.duration_s} s. At {effective_bpm} bpm in {tala} "
            f"one avartan is {avartan_seconds(tala, effective_bpm):.1f} s, so the sections' bars "
            f"must add up to {target} (±{LENGTH_TOLERANCE_AVARTANS}); yours add up to "
            f"{total_bars} ({seconds:.0f} s). Resize the sections and resend.")


def render_budget(budget: FormBudget, tala: Optional[str], bpm: Optional[int]) -> str:
    """The budget as a composer-prompt block: the length (exact when tala and tempo are known,
    the formula otherwise) and the form minimums the guardrail will enforce (the intro/return
    minimums for the gat form only)."""
    lines = [_render_length(budget, tala, bpm)]
    form = "SHORT FORM" if budget.short else "FULL FORM"
    lines.append(f"  {form}: at most {budget.max_taan_long} 'taan_long' section(s) in either "
                 f"form. IN THE GAT FORM a mukhada returning after a manjha is at least "
                 f"{budget.min_return_bars} avartan(s), and the mukhada is stated and RETURNS.")
    lines.append(f"  THE ALAP is optional, but never rushed: an intro the sitar plays gets at "
                 f"least {_render_intro_floor(budget, tala, bpm)}. When the length cannot give "
                 f"it that AND state the head, bring it back and reach the climax, leave the "
                 f"alap OUT — no alap is better than a hurried one. How the rest of the time "
                 f"is split between the parts is your call.")
    if budget.short:
        lines.append("  A short piece states ONE idea and lands it — usually the SONG form (one "
                     "main riff, developed and brought back); a short gat skips manjha/antara "
                     "detours unless they fit. One climb into the climax, every section "
                     "earning its avartans.")
    return "\n".join(lines)


def _render_intro_floor(budget: FormBudget, tala: Optional[str], bpm: Optional[int]) -> str:
    effective_bpm = budget.fixed_bpm or bpm
    if tala and effective_bpm:
        bars = min_intro_bars(budget, tala, effective_bpm)
        return (f"{bars} avartan(s) of {tala} at {effective_bpm} bpm "
                f"(≈{bars * avartan_seconds(tala, effective_bpm):.0f} s)")
    return f"{INTRO_MIN_S:.0f} s (round up to whole avartans at your tala and tempo)"


def _render_length(budget: FormBudget, tala: Optional[str], bpm: Optional[int]) -> str:
    if budget.duration_s is None:
        return "  length: OPEN — size the form to the music"
    effective_bpm = budget.fixed_bpm or bpm
    if tala and effective_bpm:
        target = target_avartans(budget, tala, effective_bpm)
        return (f"  length: FIXED ≈ {budget.duration_s} s = {target} avartans of {tala} at "
                f"{effective_bpm} bpm — the sections' bars must add up to {target} "
                f"(±{LENGTH_TOLERANCE_AVARTANS}); code checks it")
    return (f"  length: FIXED ≈ {budget.duration_s} s — one avartan lasts matras x 60 / bpm "
            f"seconds, so the sections' bars must add up to about {budget.duration_s} / that "
            f"(±{LENGTH_TOLERANCE_AVARTANS}) at the tala and tempo you choose; code checks it")
