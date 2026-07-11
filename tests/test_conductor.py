"""
Tests for the Conductor — the triage and the BOUNDED DEBATE, with no LLM (free).

`arbitrate` takes injected `debate_fn`/`rule_fn`, so the whole referee flow is tested
with fakes: does an illegal piece force a revise with NO debate; does a legal + sound
piece get accepted with NO debate; does a legal-but-weak piece open the bounded debate
(Rasik first, alternating), always terminating with the Conductor's ruling; and does
the round cap guarantee termination? The real debate is exercised live via
`uv run python -m crew.conductor`, not here.

Runs as a script (`uv run python tests/test_conductor.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.conductor import (  # noqa: E402
    Conflict,
    Critic,
    _weak_criteria,
    arbitrate,
    detect_conflict,
)
from crew.contracts import (  # noqa: E402
    Composition,
    ConductorRuling,
    DebateTurn,
    EventType,
    Layer,
    Note,
    RasikScores,
    RasikVerdict,
    UstadVerdict,
    Violation,
)


def _comp() -> Composition:
    return Composition(
        raga="darbari", sa=62, bpm=90, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[
            Layer(role="drone", notes=[Note(swara="S", oct=-2, start=0.0, dur=16.0)]),
            Layer(role="lead", notes=[Note(swara="S", oct=0, start=0.0, dur=1.0)])])


def _legal() -> UstadVerdict:
    return UstadVerdict(verdict="legal", violations=[], explanation="clean")


def _illegal() -> UstadVerdict:
    return UstadVerdict(verdict="illegal", explanation="a foreign note",
                        violations=[Violation(layer="lead", swara="R", start_beat=1.0,
                                              kind="note", reason="R is illegal in Darbari")])


def _rasik(pakad=4, idiom=4, mood=4, coherence=4, notes="") -> RasikVerdict:
    return RasikVerdict(scores=RasikScores(pakad=pakad, idiom=idiom, mood=mood, coherence=coherence),
                        notes=notes)


def _fake_debate(*turns: DebateTurn):
    """A fake debate_fn replaying canned turns; records the speaker order."""
    calls: list[Critic] = []
    it = iter(turns)

    def fn(critic, transcript):
        calls.append(critic)
        return next(it)

    return fn, calls


def _fake_rule(ruling: ConductorRuling):
    calls: list[list] = []

    def fn(transcript):
        calls.append(transcript)
        return ruling

    return fn, calls


def _turn(stance="revise", layer="lead", argument="x") -> DebateTurn:
    return DebateTurn(argument=argument, stance=stance, target_layer=layer)


_NEVER = _fake_debate()[0]          # a debate_fn that must never be called
_NEVER_RULE = _fake_rule(ConductorRuling(directive="accept"))[0]


# --- triage (pure, no fns) ---------------------------------------------------

def test_weak_criteria_flags_below_the_pass_line():
    assert _weak_criteria(RasikScores(pakad=2, idiom=3, mood=5, coherence=1)) == ["pakad", "coherence"]
    assert _weak_criteria(RasikScores(pakad=3, idiom=3, mood=3, coherence=3)) == []  # 3 passes


def test_detect_conflict_illegal_is_forced_revise():
    assert detect_conflict(_illegal(), _rasik(pakad=5, idiom=5, mood=5, coherence=5)) is Conflict.FORCED_REVISE


def test_detect_conflict_legal_and_strong_is_none():
    assert detect_conflict(_legal(), _rasik()) is Conflict.NONE


def test_detect_conflict_legal_but_weak_is_aesthetic():
    assert detect_conflict(_legal(), _rasik(idiom=2)) is Conflict.AESTHETIC


# --- arbitrate: the two no-debate branches ----------------------------------

def test_illegal_forces_revise_without_debate():
    ruling, events = arbitrate(_illegal(), _rasik(), _comp(),
                               debate_fn=_NEVER, rule_fn=_NEVER_RULE)
    assert ruling.directive == "revise"
    assert ruling.layer == "lead"                       # targets the violating voice
    assert not any(e.type == EventType.DEBATE for e in events)   # no debate happened
    assert events[-1].type == EventType.VERDICT and events[-1].verdict == "revise"


def test_legal_and_sound_is_accepted_without_debate():
    ruling, events = arbitrate(_legal(), _rasik(), _comp(),
                               debate_fn=_NEVER, rule_fn=_NEVER_RULE)
    assert ruling.directive == "accept"
    assert not any(e.type == EventType.DEBATE for e in events)


# --- arbitrate: the bounded debate (the money moment) -----------------------

def test_aesthetic_conflict_runs_the_bounded_debate_then_rules():
    debate, calls = _fake_debate(_turn(stance="revise"), _turn(stance="accept"))
    rule, rule_calls = _fake_rule(ConductorRuling(directive="revise", layer="lead",
                                                  reason="regenerate the lead idiomatically"))
    ruling, events = arbitrate(_legal(), _rasik(idiom=2), _comp(),
                               debate_fn=debate, rule_fn=rule, max_rounds=2)
    assert calls == [Critic.RASIK, Critic.USTAD]         # Rasik opens, then alternate
    assert len(rule_calls) == 1                          # the Conductor ruled exactly once
    assert ruling.directive == "revise" and ruling.layer == "lead"
    debate_events = [e for e in events if e.type == EventType.DEBATE]
    assert [e.agent for e in debate_events] == ["Rasik", "Ustad"]
    assert debate_events[0].verdict == "revise"          # the turn's stance rides the event


def test_debate_turn_count_follows_max_rounds():
    debate, calls = _fake_debate(_turn(), _turn(), _turn())
    rule, _ = _fake_rule(ConductorRuling(directive="accept", reason="good enough"))
    arbitrate(_legal(), _rasik(idiom=1), _comp(), debate_fn=debate, rule_fn=rule, max_rounds=3)
    assert calls == [Critic.RASIK, Critic.USTAD, Critic.RASIK]   # capped at 3, Rasik-first


def test_conductor_always_rules_even_if_critics_never_concede():
    # both debate turns insist "revise"; the referee still terminates with one ruling
    debate, _ = _fake_debate(_turn(stance="revise"), _turn(stance="revise"))
    rule, rule_calls = _fake_rule(ConductorRuling(directive="accept", reason="not worth a pass"))
    ruling, _ = arbitrate(_legal(), _rasik(idiom=2), _comp(),
                          debate_fn=debate, rule_fn=rule, max_rounds=2)
    assert ruling.directive == "accept"                  # the clock, not consensus, ended it
    assert len(rule_calls) == 1


def test_max_rounds_must_be_positive():
    try:
        arbitrate(_legal(), _rasik(idiom=2), _comp(),
                  debate_fn=_NEVER, rule_fn=_NEVER_RULE, max_rounds=0)
        assert False, "expected ValueError"
    except ValueError:
        pass


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
