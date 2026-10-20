"""
Tests for the SECOND LOOK (crew/second_look.py) — where Rasik's and the Producer's independent
reviews meet. Pure, no LLM (the look is injected). Runs as a script or under pytest.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ProducerScores,
    ProducerSecondLook,
    ProducerVerdict,
    RasikScores,
    RasikSuggestion,
    RasikVerdict,
    RevisionPlan,
)
from crew.second_look import fan_in, rasik_flags, render_consultation, second_look_inputs  # noqa: E402
from tests.test_producer import _arr, _comp  # noqa: E402

_SCORES = ProducerScores(structure=4, dynamics=4, climax=4, motif=4, hook=4, balance=4, independence=4,
                         mood_fit=4, repetition=4, performance=4)
_PLAN = RevisionPlan(voice="riff", sections=[0], instruction="the hook never lands")
_LEAD_PLAN = RevisionPlan(voice="lead", sections=[1], instruction="the line never sounds like Darbari")


def _rasik(low: int = 4) -> RasikVerdict:
    return RasikVerdict(scores=RasikScores(pakad=low, idiom=4, rasa=4), notes="pakad missing",
                        suggestions=[RasikSuggestion(section=1, change="state the pakad", why="its signature")])


def _never(*_a):
    raise AssertionError("the second look must not be called")


def test_a_producer_revision_stands_without_a_second_look():
    producer = ProducerVerdict(scores=_SCORES, decision="revise", plan=_PLAN)
    merged, events = fan_in(_comp(), _arr(), producer, _rasik(1), look_fn=_never)
    assert merged is producer and events == []


def test_no_second_look_when_rasik_flags_nothing():
    producer = ProducerVerdict(scores=_SCORES)
    merged, events = fan_in(_comp(), _arr(), producer, _rasik(4), look_fn=_never)
    assert merged is producer and events == [] and not rasik_flags(_rasik(4))


def test_a_flagged_raga_problem_can_turn_an_accept_into_a_lead_revision():
    producer = ProducerVerdict(scores=_SCORES, notes="it works")
    seen = {}

    def look(comp, arr, prod, rasik):
        seen["inputs"] = second_look_inputs(comp, arr, prod, rasik)
        return ProducerSecondLook(reasoning="a listener hears a generic minor line", decision="revise", plan=_LEAD_PLAN)
    merged, events = fan_in(_comp(), _arr(), producer, _rasik(2), look_fn=look)
    assert merged.decision == "revise" and merged.plan == _LEAD_PLAN
    assert merged.scores == _SCORES                                         # the first pass's scores stand
    assert "You decided: accept" in seen["inputs"]["own_verdict"]           # it sees its own verdict first...
    assert "pakad 2" in seen["inputs"]["consultation"]                      # ...and Rasik's notes beside it
    assert events and "After reading Rasik" in events[0].text


def test_the_second_look_may_keep_the_accept():
    producer = ProducerVerdict(scores=_SCORES)
    merged, _ = fan_in(_comp(), _arr(), producer, _rasik(1),
                       look_fn=lambda *a: ProducerSecondLook(reasoning="a nuance only", decision="accept"))
    assert merged.decision == "accept" and merged.plan is None


def test_a_failed_second_look_keeps_the_first_verdict():
    producer = ProducerVerdict(scores=_SCORES)

    def dead(*a):
        raise TimeoutError("503")
    merged, events = fan_in(_comp(), _arr(), producer, _rasik(1), look_fn=dead)
    assert merged is producer and "skipped" in events[0].text


def test_a_revise_without_a_plan_is_read_as_accept():
    producer = ProducerVerdict(scores=_SCORES)
    merged, _ = fan_in(_comp(), _arr(), producer, _rasik(1),
                       look_fn=lambda *a: ProducerSecondLook(decision="revise", plan=None))
    assert merged.decision == "accept"


def test_every_placeholder_is_supplied():
    import re

    import yaml
    task = yaml.safe_load((Path(__file__).resolve().parents[1] / "crew/config/tasks.yaml").read_text())["reconsider_with_rasik"]
    wanted = set(re.findall(r"\{(\w+)\}", task["description"] + task["expected_output"]))
    inputs = second_look_inputs(_comp(), _arr(), ProducerVerdict(scores=_SCORES), _rasik(2))
    assert wanted <= set(inputs), wanted - set(inputs)
    assert "section 1: state the pakad" in render_consultation(_rasik(2))


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
