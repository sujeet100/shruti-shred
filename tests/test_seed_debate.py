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

from crew.audition import audition_composition, head_arrangement  # noqa: E402
from crew.contracts import DebateTurn, EventType, LeadNote, SeedChoice  # noqa: E402
from crew.seed_debate import (  # noqa: E402
    APPROACHES,
    realised,
    GAT_FIRST,
    RIFF_FIRST,
    best_of,
    debate,
    select,
    single_seed,
)
from crew.seed_debate_crew import _debate_task_config, _yaml, choice_guardrail, turn_guardrail  # noqa: E402
from crew.seed_measures import measure_seed, render_seed  # noqa: E402
from tests.test_composer import _BRIEF, _gat_seed, _good_head, _idea, _seed  # noqa: E402


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



# --- gat seeds are REALISED: the debate argues, and the ear hears, the composed head ----------

def _gat_seed_fn(log: list):
    def fn(brief, approach):
        log.append(approach)
        return _gat_seed(reasoning=f"gat seed {len(log)}")
    return fn


def _head_fn(log: list):
    def fn(seed, brief):
        log.append(seed.reasoning)
        return _good_head()
    return fn


def test_every_gat_seed_gets_its_head_composed_before_it_is_weighed():
    seeds, judge, heads = [], [], []
    result = best_of(_BRIEF, seed_fn=_gat_seed_fn(seeds), select_fn=_select_fn(judge), head_fn=_head_fn(heads))
    assert len(heads) == 4 and all(c.hook is not None for c in result.candidates)
    assert result.calls == 4 + 4 + 2
    assert "hook (one avartan" in judge[0]                 # the selector reads the composed notes


def test_a_debate_recomposes_only_the_head_its_argument_changed():
    heads: list = []
    revised = _gat_seed(reasoning="A, persuaded", head=_idea(sam_swara="m"))

    def turn_fn(brief, own, rival, both):
        if own.reasoning == "gat seed 1":
            return DebateTurn(argument="the rival's cell is stronger", changed=True, seed=revised)
        return DebateTurn(argument="kept", changed=False, seed=own.model_copy(update={"hook": None}))

    result = debate(_BRIEF, seed_fn=_gat_seed_fn([]), turn_fn=turn_fn, select_fn=_select_fn([]),
                    head_fn=_head_fn(heads))
    assert heads == ["gat seed 1", "gat seed 2", "A, persuaded"]     # B kept its composed head
    assert all(f.hook is not None for f in result.candidates)
    assert result.calls == 2 + 2 + 2 + 1 + 2


def test_a_gat_seed_that_also_sketched_a_hook_still_gets_its_head_composed():
    # the 2026-10-18 run: the composer wrote a hook AND a head idea; the system ignores the sketch
    heads: list = []
    sketched = _gat_seed(hook=_seed().hook)
    seed, calls = realised(sketched, _BRIEF, _head_fn(heads))
    assert calls == 1 and heads and seed.hook == _good_head()


def test_a_failed_head_call_stops_the_run_rather_than_audition_a_headless_seed():
    def dead(seed, brief):
        raise RuntimeError("504")
    try:
        realised(_gat_seed(), _BRIEF, dead)
        raise AssertionError("a dead head call must stop the run")
    except RuntimeError as e:
        assert str(e) == "504"


def test_a_song_seed_needs_no_head_call():
    heads: list = []
    result = single_seed(_BRIEF, seed_fn=_seed_fn([]), head_fn=_head_fn(heads))
    assert heads == [] and result.calls == 1


def test_the_head_chart_carries_the_idea_and_a_realised_seed_can_be_heard():
    arr = head_arrangement(_gat_seed(), _BRIEF)
    assert arr.seed_head == _idea() and arr.seed_hook is None
    assert any(s.form_role == "mukhada" for s in arr.sections)
    seed, _ = realised(_gat_seed(), _BRIEF, lambda s, b: _good_head())
    assert audition_composition(seed, _BRIEF).layers           # no longer refused
    assert measure_seed(seed, _BRIEF).sam_note is not None     # note-level measures, not the idea's

def test_each_side_of_a_cross_model_debate_runs_its_own_calls():
    """Two debaters can be two models end to end: A's seed, turn and head go through A's calls,
    B's through B's, including the head a persuaded debater's revised seed needs."""
    from crew.seed_debate import Side
    calls: list = []

    def side(name: str) -> Side:
        def seed(brief, approach):
            calls.append((name, "seed"))
            return _gat_seed(reasoning=f"{name} seed")

        def turn(brief, own, rival, both):
            calls.append((name, "turn"))
            changed = name == "A"
            return DebateTurn(argument="a", changed=changed,
                              seed=_gat_seed(reasoning="A, revised") if changed else own)

        def head(seed_, brief):
            calls.append((name, "head"))
            return _good_head()
        return Side(seed, turn, head)

    result = debate(_BRIEF, seed_fn=None, turn_fn=None, select_fn=_select_fn([]),
                    sides=(side("A"), side("B")), arm="debate-cross")
    assert calls == [("A", "seed"), ("A", "head"), ("B", "seed"), ("B", "head"),
                     ("A", "turn"), ("B", "turn"), ("A", "head")]
    assert result.arm == "debate-cross" and result.calls == 2 + 2 + 2 + 1 + 2


def test_the_composer_override_is_scoped_to_its_block():
    from crew.config import composer_llm, composer_override, flash_model
    with composer_override("gemini/gemini-3.7-flash", "high"):
        inside = composer_llm().model
    assert inside == "gemini-3.7-flash"
    assert composer_llm().model == flash_model().removeprefix("gemini/")


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
