"""
Tests for WHEN the notes debate runs (crew/debate_trigger.py) — pure, no LLM.
Runs as a script or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import ProducerScores, ProducerVerdict, RasikScores, RasikVerdict, RevisionPlan  # noqa: E402
from crew.debate_trigger import debate_concerns  # noqa: E402


def _producer(independence: int = 4, decision: str = "accept") -> ProducerVerdict:
    scores = ProducerScores(structure=4, dynamics=4, climax=4, motif=4, hook=4, balance=4,
                            independence=independence, mood_fit=4, repetition=4, performance=4)
    plan = RevisionPlan(voice="riff", instruction="x") if decision == "revise" else None
    return ProducerVerdict(scores=scores, notes="the guitar shadows the sitar", decision=decision, plan=plan)


def _rasik(pakad: int = 4) -> RasikVerdict:
    return RasikVerdict(scores=RasikScores(pakad=pakad, idiom=4, rasa=4), notes="no pakad anywhere")


def test_a_healthy_accepted_take_calls_no_debate():
    assert debate_concerns(_producer(), _rasik()) == []


def test_a_weak_relationship_score_calls_the_debate_in_the_producers_words():
    [concern] = debate_concerns(_producer(independence=3), _rasik())
    assert "independence" in concern and "the guitar shadows the sitar" in concern


def test_a_take_the_producer_is_revising_is_not_debated_for_its_scores():
    assert debate_concerns(_producer(independence=2, decision="revise"), _rasik()) == []


def test_a_raga_flag_calls_the_debate():
    [concern] = debate_concerns(_producer(), _rasik(pakad=2))
    assert "Rasik" in concern and "no pakad anywhere" in concern


def test_missing_reviews_call_nothing():
    assert debate_concerns(None, None) == []


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
