"""
Tests for the SEED DEBATE experiment (crew/seed_debate.py, seed_measures.py, seed_debate_crew.py,
audition.py) — pure, no LLM: every model call is a fake.

The experiment asks whether two composers who hear and argue with each other beat one composer
given more attempts, so the arms must be FAIR (equal budgets, the same starting nudges), the
selector must not reward a candidate's position, and the audition must be the seed itself.

Runs as a script (`uv run python tests/test_seed_debate.py`) or under pytest.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.audition import audition_composition  # noqa: E402
from crew.contracts import DebateTurn, EventType, LeadNote, SeedChoice  # noqa: E402
from crew.seed_debate import (  # noqa: E402
    APPROACHES,
    GAT_FIRST,
    RIFF_FIRST,
    best_of,
    debate,
    select,
    single_seed,
)
from crew.seed_debate_crew import _debate_task_config, _yaml, choice_guardrail, turn_guardrail  # noqa: E402
from crew.seed_measures import measure_seed, render_seed  # noqa: E402
from tests.test_composer import _BRIEF, _seed  # noqa: E402


def _seed_fn(log: list):
    """Fresh, distinguishable seeds; records each call's approach."""
    def fn(brief, approach):
        log.append(approach)
        return _seed(reasoning=f"seed {len(log)}")
    return fn


def _select_fn(log: list, pick=lambda count, call: 1):
    def fn(brief, candidates, count):
        log.append(candidates)
        return SeedChoice(reasoning="r", choice=pick(count, len(log)))
    return fn


def test_the_baseline_is_one_call_with_no_nudge():
    log: list = []
    result = single_seed(_BRIEF, seed_fn=_seed_fn(log))
    assert log == [""] and result.calls == 1 and result.arm == "single"


def test_both_contenders_spend_six_calls_and_share_the_same_nudges():
    seeds_b, judge_b, seeds_c, judge_c, turns = [], [], [], [], []

    def turn_fn(brief, own, rival, both):
        turns.append(both)
        return DebateTurn(argument="kept", changed=False, seed=own)

    b = best_of(_BRIEF, seed_fn=_seed_fn(seeds_b), select_fn=_select_fn(judge_b))
    c = debate(_BRIEF, seed_fn=_seed_fn(seeds_c), turn_fn=turn_fn, select_fn=_select_fn(judge_c))
    assert b.calls == c.calls == 6
    assert len(seeds_b) + len(judge_b) == 6 and len(seeds_c) + len(turns) + len(judge_c) == 6
    assert seeds_b == [RIFF_FIRST, GAT_FIRST, RIFF_FIRST, GAT_FIRST]   # alternating, like...
    assert seeds_c == list(APPROACHES)                                  # ...the debate's two


def test_the_selector_is_asked_twice_with_the_order_reversed():
    log: list = []
    seeds = [_seed(reasoning="first idea"), _seed(reasoning="second idea")]
    # it names "the first label" both times — a pure position preference
    chosen, events = select(_BRIEF, seeds, select_fn=_select_fn(log))
    assert log[0].index("first idea") < log[0].index("second idea")
    assert log[1].index("second idea") < log[1].index("first idea")
    assert events[0].data["tie"] is True and chosen == 0          # code breaks the tie


def test_an_agreed_choice_wins_whatever_its_position():
    # the judge picks the SECOND candidate forwards and the FIRST backwards: the same seed
    pick = lambda count, call: 2 if call == 1 else 1             # noqa: E731
    chosen, events = select(_BRIEF, [_seed(), _seed()], select_fn=_select_fn([], pick))
    assert chosen == 1 and "both orders chose seed 2" in events[0].text


def test_a_dead_judge_is_a_missing_vote_broken_by_code():
    def dead(brief, candidates, count):
        raise RuntimeError("504")
    chosen, events = select(_BRIEF, [_seed(), _seed()], select_fn=dead)
    assert chosen == 0 and events[0].data["tie"] is True


def test_each_composer_argues_from_both_seeds_and_code_measurements():
    seen: list = []

    def turn_fn(brief, own, rival, both):
        seen.append((own.reasoning, both))
        return DebateTurn(argument=f"I keep {own.reasoning}", changed=own.reasoning == "seed 2",
                          seed=own.model_copy(update={"reasoning": own.reasoning + " revised"}))

    result = debate(_BRIEF, seed_fn=_seed_fn([]), turn_fn=turn_fn, select_fn=_select_fn([]))
    assert [r for r, _ in seen] == ["seed 1", "seed 2"]
    for _, both in seen:
        assert "YOUR SEED" in both and "THE RIVAL'S SEED" in both
        assert "strokes:" in both and "with the riff:" in both       # the measurements, both seeds
    assert [s.reasoning for s in result.candidates] == ["seed 1 revised", "seed 2 revised"]
    debates = [e for e in result.events if e.type is EventType.DEBATE]
    assert [e.data["changed"] for e in debates] == [False, True]


def test_a_dead_turn_keeps_the_composers_seed():
    def dead(brief, own, rival, both):
        raise RuntimeError("timeout")
    result = debate(_BRIEF, seed_fn=_seed_fn([]), turn_fn=dead, select_fn=_select_fn([]))
    assert [s.reasoning for s in result.candidates] == ["seed 1", "seed 2"]


def test_the_measurements_include_the_stroke_motif_and_the_riff_relationship():
    hook = _seed().hook
    figure = [LeadNote(swara="S", dur=1.0, bol="dir"), LeadNote(swara="S", dur=1.0, bol="dir"),
              LeadNote(swara="g", dur=1.5, bol="dar")]
    tail = sum(n.dur for n in figure) * 2
    stroked = hook.model_copy(update={"notes": figure * 2 + [
        LeadNote(swara="m", dur=16.0 - tail, bol="da")]})
    m = measure_seed(_seed(hook=stroked), _BRIEF)
    assert m.stroke_motif == ("dir", "dir", "dar") and m.compound_figures == 6
    assert m.sam_note == "S" and 0.0 <= m.shared_attack_share <= 1.0
    text = render_seed("1", _seed(hook=stroked), _BRIEF)
    assert "stroke motif: dir dir dar" in text and "S:dir(1)" in text


def test_the_record_measures_how_different_the_drafts_were():
    from crew.seed_measures import diversity
    same = diversity([_seed(), _seed()])
    assert same["hook_swaras"] == 1.0 and same["forms"] == 1
    other = _seed(hook=_seed().hook.model_copy(update={"notes": list(reversed(_seed().hook.notes))}))
    assert diversity([_seed(), other])["hook_swaras"] < 1.0
    result = debate(_BRIEF, seed_fn=_seed_fn([]), select_fn=_select_fn([]),
                    turn_fn=lambda b, own, rival, both: DebateTurn(argument="x", changed=True,
                                                                  seed=own.model_copy(update={"reasoning": "revised"})))
    assert [s.reasoning for s in result.drafts] == ["seed 1", "seed 2"]   # the pre-debate drafts are kept


def test_the_guardrails_hold_the_hard_lines_only():
    bad_seed = _seed().model_copy(update={"main_riff": _seed().main_riff.model_copy(
        update={"notes": [_seed().main_riff.notes[0].model_copy(update={"swara": "r", "dur": 16.0})]})})

    class _Out:
        def __init__(self, value):
            self.pydantic, self.raw = value, value.model_dump_json()

    ok, _ = turn_guardrail(_BRIEF)(_Out(DebateTurn(argument="a", seed=_seed())))
    assert ok
    ok, msg = turn_guardrail(_BRIEF)(_Out(DebateTurn(argument="a", seed=bad_seed)))
    assert not ok and "main riff" in msg
    assert choice_guardrail(2)(_Out(SeedChoice(choice=2)))[0]
    assert not choice_guardrail(2)(_Out(SeedChoice(choice=3)))[0]


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{([a-z_]+)\}", text))


def test_every_prompt_placeholder_is_supplied():
    from crew.composer import SeedContext
    config = _debate_task_config()
    needed = _placeholders(config["description"] + config["expected_output"])
    assert "debate" in needed and needed <= set(SeedContext(_BRIEF).inputs()) | {"debate"}
    select_cfg = _yaml("tasks.yaml")["select_seed"]
    assert _placeholders(select_cfg["description"] + select_cfg["expected_output"]) == {
        "user_request", "candidates", "count"}


def test_the_audition_is_the_seed_itself_and_calls_no_model():
    comp = audition_composition(_seed(), _BRIEF)
    by_role = {(layer.role, layer.instrument) for layer in comp.layers}
    assert ("lead", "sitar") in by_role and ("lead", "dist_guitar_lead") not in by_role
    assert any(layer.role == "rhythm" for layer in comp.layers)
    sitar = next(layer for layer in comp.layers if layer.instrument == "sitar")
    assert min(n.start for n in sitar.notes) >= 16.0     # the riff plays one avartan alone first


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
