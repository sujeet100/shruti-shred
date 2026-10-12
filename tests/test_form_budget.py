"""
Tests for the FORM BUDGET — a stated length becomes an avartan budget the composers are told
and the guardrail enforces; a short length relaxes only the minimums that need length. No LLM.

Runs as a script (`uv run python tests/test_form_budget.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.composers import _PromptContext, Composer, brief_budget, turn_guardrail  # noqa: E402
from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    ComposerTurn,
    RawIntent,
    Section,
    SectionKind,
    resolve_brief,
)
from crew.form_budget import (  # noqa: E402
    FULL_FORM,
    avartan_seconds,
    form_budget,
    length_error,
    render_budget,
    target_avartans,
)

_LAYERS = ["lead", "rhythm", "drums", "drone"]


def _section(role: str, bars: int, kind: SectionKind = SectionKind.MELODY) -> Section:
    return Section(kind=kind, bars=bars, layers=list(_LAYERS), foreground="lead",
                   riff_slot="main", form_role=role)


def _opener(*, intro: int = 1, taan: int = 2, last: int = 2) -> ArrangementDraft:
    """The Bhairav opener's shape: intro -> mukhada -> taan (+ tihai) -> mukhada."""
    return ArrangementDraft(
        raga="bhairav", subgenre="heavy", tala="teentaal", bpm=128, motif=["S", "r", "G"],
        sections=[_section("intro", intro, SectionKind.ALAAP), _section("mukhada", 3),
                  _section("taan_long", taan, SectionKind.TAAN), _section("mukhada", last)])


def _check(budget, draft: ArrangementDraft):
    return turn_guardrail(budget)(SimpleNamespace(pydantic=ComposerTurn(draft=draft, note="x")))


# --- the arithmetic ---------------------------------------------------------------------

def test_sixty_seconds_at_128_in_teentaal_is_eight_avartans():
    assert avartan_seconds("teentaal", 128) == 7.5
    assert target_avartans(form_budget(60), "teentaal", 128) == 8


def test_a_fixed_tempo_wins_over_the_drafts():
    # the user fixed 128; a draft that wandered to 64 still gets the 128-bpm budget
    assert target_avartans(form_budget(60, fixed_bpm=128), "teentaal", 64) == 8


def test_no_length_means_no_length_check():
    assert target_avartans(form_budget(None), "teentaal", 128) is None
    assert length_error(form_budget(None), "teentaal", 128, 40) is None


def test_length_tolerates_one_avartan_either_way():
    budget = form_budget(60)
    for bars in (7, 8, 9):
        assert length_error(budget, "teentaal", 128, bars) is None
    error = length_error(budget, "teentaal", 128, 12)
    assert error and "add up to 8" in error and "12" in error


# --- which form ---------------------------------------------------------------------------

def test_a_short_request_relaxes_the_form():
    short = form_budget(60)
    assert short.short and short.min_intro_bars == 1 and short.min_return_bars == 1
    assert short.max_taan_long == 1


def test_a_ninety_second_opener_is_still_short_form():
    assert form_budget(90).short and form_budget(119).short


def test_no_length_or_a_long_one_keeps_the_full_form():
    for seconds in (None, 120, 240):
        budget = form_budget(seconds)
        assert not budget.short
        assert (budget.min_intro_bars, budget.min_return_bars, budget.max_taan_long) == (
            FULL_FORM.min_intro_bars, FULL_FORM.min_return_bars, FULL_FORM.max_taan_long)


# --- the guardrail enforces it -----------------------------------------------------------

def test_a_short_clip_gives_the_alap_real_time_or_leaves_it_out():
    # Sujit, 2026-10-12: a one-avartan alap (7.5 s at 128 bpm) is refused even in a 60 s clip;
    # the composer either drops the alap or gives it 3 avartans and tightens the rest
    budget = form_budget(60, fixed_bpm=128)
    ok, msg = _check(budget, _opener())
    assert not ok and "leave the alap out" in msg
    no_alap = _opener()
    no_alap.sections.pop(0)
    ok, value = _check(budget, no_alap)
    assert ok, value
    ok, value = _check(budget, _opener(intro=3, last=1).model_copy(update={"sections": [
        _section("intro", 3, SectionKind.ALAAP), _section("mukhada", 2),
        _section("taan_long", 2, SectionKind.TAAN), _section("mukhada", 1)]}))
    assert ok, value


def test_a_short_budget_rejects_a_chart_that_runs_long():
    ok, msg = _check(form_budget(60, fixed_bpm=128), _opener(intro=3, taan=1, last=8))
    assert not ok and "about 60 s" in msg


def test_a_short_budget_still_caps_the_climax_at_one_taan():
    draft = _opener()
    draft.sections.insert(2, _section("taan_long", 1, SectionKind.TAAN))
    draft.sections[1] = _section("mukhada", 2)
    ok, msg = _check(form_budget(60, fixed_bpm=128), draft)
    assert not ok and "taan_long" in msg


def test_the_full_form_still_wants_a_three_avartan_intro():
    ok, msg = _check(FULL_FORM, _opener())
    assert not ok and "at least 3" in msg


# --- intake carries it, the prompt shows it ----------------------------------------------

def test_intake_drops_junk_lengths_and_only_an_explicit_yes_makes_it_playable():
    assert RawIntent(duration_s=60).duration_s == 60
    for junk in ("sixty", 2, 99999, None):
        assert RawIntent(duration_s=junk).duration_s is None
    assert RawIntent(playable_rhythm=True).playable_rhythm is True
    assert RawIntent(playable_rhythm="true").playable_rhythm is True
    for no in (False, "false", "not stated", None):
        assert RawIntent(playable_rhythm=no).playable_rhythm is None


def test_the_brief_carries_length_and_playability():
    brief = resolve_brief(RawIntent(bpm=128, duration_s=60, playable_rhythm=True))
    assert brief.duration_s == 60 and brief.playable_rhythm
    assert brief_budget(brief).short and brief_budget(brief).fixed_bpm == 128
    assert not resolve_brief(RawIntent()).playable_rhythm


def test_the_composers_are_told_the_exact_budget():
    brief = resolve_brief(RawIntent(tala="teentaal", bpm=128, duration_s=60,
                                    playable_rhythm=True))
    inputs = _PromptContext(brief, max_turns=2).inputs_for(Composer.PANDIT, 1, None, [])
    assert "8 avartans" in inputs["form_budget"] and "SHORT FORM" in inputs["form_budget"]
    assert "playable by a human" in inputs["brief_context"]


def test_an_open_tempo_gets_the_formula_not_a_number():
    text = render_budget(form_budget(60), None, None)
    assert "matras x 60 / bpm" in text



def test_the_alap_and_return_minimums_are_gat_rules_the_taan_cap_is_not():
    text = render_budget(form_budget(60), "teentaal", 128)
    assert "in either form" in text and "IN THE GAT FORM" in text
    assert "THE ALAP is optional, but never rushed" in text and "3 avartan(s)" in text
    assert "SONG form" in text                       # a short piece is steered to one idea

# --- the intro window survives a one-avartan intro ---------------------------------------

def test_a_one_avartan_intro_keeps_its_alap_window():
    from crew.lead import _intro_lead_in_beats
    one = Section(kind=SectionKind.ALAAP, bars=1, layers=["lead", "clean", "drone"],
                  foreground="lead", form_role="intro")
    three = one.model_copy(update={"bars": 3})
    two = one.model_copy(update={"bars": 2})
    assert _intro_lead_in_beats(one, 16.0, 4.0) == 0.0
    assert _intro_lead_in_beats(two, 16.0, 4.0) == 4.0          # one vibhag
    assert _intro_lead_in_beats(three, 16.0, 4.0) == 16.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
