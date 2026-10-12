"""
Tests for the user's request reaching every agent that makes a musical decision — no LLM (free).

The Interpreter extracts what the system can enforce; everything else the user said (the form,
the ending, who plays what) used to stop there. The request now rides the brief and the
Arrangement verbatim, and one renderer quotes it into every musical agent's prompt. These tests
pin the three links of that chain: code copies the words (never the LLM), the chart carries
them, and every template that asks for `{user_request}` gets it — a placeholder with no input
would otherwise surface only as a crash in a live call.

Runs as a script (`uv run python tests/test_user_request.py`) or under pytest.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

import yaml  # noqa: E402

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    Composition,
    CompositionBrief,
    Layer,
    Note,
    ProducerScores,
    ProducerVerdict,
    RasikScores,
    RasikVerdict,
    RawIntent,
    Section,
    SectionKind,
    UstadVerdict,
    build_arrangement,
    resolve_brief,
)
from crew.user_request import render_request  # noqa: E402

_REQUEST = ("Compose a 60-second Raag Bhairav x heavy-metal piece.\n"
            "\n"
            "Finish with a tihai landing exactly on sam.")

_TASKS = yaml.safe_load(
    (Path(__file__).parents[1] / "crew" / "config" / "tasks.yaml").read_text())

# Every agent that makes a MUSICAL decision reads the request. Legality (Ustad) is pure code
# since the 2026-10-11 redesign, so there is no prompt for the request to leak into, and the
# final call is the Producer's (assess_composition), which reads it.
_MUSICAL_TASKS = ("compose_turn", "generate_lead", "generate_gat", "generate_riff",
                  "compose_orchestra", "assess_taste", "assess_composition")


def _placeholders(task: str) -> set[str]:
    cfg = _TASKS[task]
    return set(re.findall(r"\{([a-z_]+)\}", cfg["description"] + cfg["expected_output"]))


def _brief() -> CompositionBrief:
    return resolve_brief(RawIntent(raga="bhairav", key="E", bpm=128), request=_REQUEST)


def _arr():
    draft = ArrangementDraft(
        raga="bhairav", subgenre="heavy", tala="teentaal", bpm=128, motif=["S", "r", "G"],
        sections=[
            Section(kind=SectionKind.MELODY, bars=2, layers=["lead", "rhythm", "drums", "drone"],
                    foreground="lead", form_role="mukhada", intent="state the head"),
            Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "rhythm", "drums", "drone"],
                    foreground="lead", form_role="taan_long", intent="the climax")])
    return build_arrangement(draft, _brief())


def _comp() -> Composition:
    lead = [Note(swara=sw, oct=0, start=float(i), dur=1.0) for i, sw in enumerate("S r G m P".split())]
    riff = [Note(swara="S", oct=-1, start=float(i), dur=1.0) for i in range(8)]
    return Composition(raga="bhairav", sa=52, bpm=128,
                       tala={"name": "teentaal", "beats_per_bar": 16.0},
                       layers=[Layer(role="lead", notes=lead), Layer(role="rhythm", notes=riff)])


def _verdicts():
    ustad = UstadVerdict(verdict="legal", violations=[], explanation="All legal.")
    rasik = RasikVerdict(scores=RasikScores(pakad=4, idiom=2, rasa=3), notes="thin idiom")
    producer = ProducerVerdict(
        scores=ProducerScores(structure=4, dynamics=4, climax=4, motif=4, hook=4, balance=4,
                              independence=4, mood_fit=4, repetition=4, performance=4),
        notes="it works")
    return ustad, rasik, producer


# --- the renderer -----------------------------------------------------------------------

def test_render_quotes_every_line_verbatim():
    block = render_request(_REQUEST)
    for line in _REQUEST.splitlines():
        if line.strip():
            assert f"| {line}" in block
    assert block.count("\n") == _REQUEST.count("\n")      # blank lines kept, not collapsed


def test_render_without_a_request_is_a_benign_line():
    assert "no free-text request" in render_request("")
    assert "no free-text request" in render_request("   \n  ")


# --- the chain: code copies, the chart carries ---------------------------------------------

def test_the_brief_carries_the_words_not_a_paraphrase():
    assert _brief().request == _REQUEST


def test_the_arrangement_carries_the_request_from_the_brief():
    assert _arr().request == _REQUEST


def test_a_revise_keeps_the_request():
    from crew.contracts import RevisionPlan
    from crew.flow import revise_arrangement
    plan = RevisionPlan(voice="lead", instruction="more pakad")
    assert revise_arrangement(_arr(), plan).request == _REQUEST


# --- which templates ask for it ---------------------------------------------------------

def test_every_musical_agent_asks_for_the_request():
    missing = [t for t in _MUSICAL_TASKS if "user_request" not in _placeholders(t)]
    assert not missing, f"musical tasks without the request: {missing}"


def test_legality_is_code_and_needs_no_request():
    # Ustad is pure code now: no prompt exists for the request to reach, and none is needed
    from crew.ustad import critique_legality
    assert "assess_legality" not in _TASKS
    verdict, _ = critique_legality(_comp())
    assert verdict.verdict in ("legal", "illegal")


# --- every context supplies it (and every other placeholder it asks for) ---------------

def _assert_supplies(task: str, inputs: dict) -> None:
    missing = _placeholders(task) - set(inputs)
    assert not missing, f"{task}: placeholders with no input: {sorted(missing)}"
    assert inputs["user_request"] == render_request(_REQUEST), f"{task}: wrong request block"


def test_composers_get_the_request():
    from crew.composers import Composer, _PromptContext
    inputs = _PromptContext(_brief(), max_turns=3).inputs_for(Composer.PANDIT, 1, None, [])
    _assert_supplies("compose_turn", inputs)


def test_lead_gets_the_request():
    from crew.generators import section_spans
    from crew.lead import _LeadContext
    arr = _arr()
    _assert_supplies("generate_lead", _LeadContext(arr).inputs_for(section_spans(arr)[0], []))


def test_gat_gets_the_request():
    from crew.lead import _GatContext
    inputs = _GatContext(_arr()).inputs_for(needs_manjha=False, needs_antara=False,
                                            needs_amad=False)
    _assert_supplies("generate_gat", inputs)


def test_riff_gets_the_request():
    from crew.generators import section_spans
    from crew.riff import _RiffContext
    arr = _arr()
    _assert_supplies("generate_riff", _RiffContext(arr).inputs_for(section_spans(arr)[0], []))


def test_orchestra_gets_the_request():
    from crew.orchestra import _OrchestraContext
    inputs = _OrchestraContext(_arr()).inputs_for([], None)
    _assert_supplies("compose_orchestra", inputs)


def test_rasik_gets_the_request():
    from crew.rasik import judge_inputs
    _assert_supplies("assess_taste", judge_inputs(_comp(), _REQUEST))


def test_producer_gets_the_request():
    from crew.producer import judge_inputs
    _assert_supplies("assess_composition", judge_inputs(_comp(), _arr()))


def test_the_flow_hands_the_decider_the_chart():
    # the Decide stage receives the Arrangement, which is where the request lives (the Producer,
    # who makes the final call, read it in its own prompt)
    from crew.flow import Stages, compose_flow
    arr, comp = _arr(), _comp()
    seen: list[str] = []

    def decide(_u, _r, _p, _c, a):
        seen.append(a.request)
        return None, []

    stages = Stages(
        interpret=lambda q: (_brief(), []), compose=lambda b: (arr, []),
        generate=lambda a: ([], None, [], [], []), assemble=lambda *a: comp,
        critique=lambda c, a: (*_verdicts(), []), decide=decide,
        regenerate=lambda *a: ([], None, [], [], []), render=lambda c: None)
    compose_flow(_REQUEST, stages=stages)
    assert seen == [_REQUEST]


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
