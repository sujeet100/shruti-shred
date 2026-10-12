"""
Tests for the final call (crew/triage.py) — pure, no LLM.

No Conductor and no debate since the 2026-10-11 redesign: an illegal piece is a forced revise of
the voice holding the most violations (code decides), otherwise the Producer's decision stands,
and a revise with no plan is nothing actionable (accept). One VERDICT event carries the call.

Runs as a script (`uv run python tests/test_triage.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    Composition,
    CompositionBrief,
    EventType,
    Layer,
    Note,
    ProducerScores,
    ProducerVerdict,
    RevisionPlan,
    Section,
    SectionKind,
    UstadVerdict,
    Violation,
    build_arrangement,
)
from crew.triage import decide, legality_plan  # noqa: E402

_SCORES = ProducerScores(structure=3, dynamics=3, climax=3, motif=3, hook=3, balance=3,
                         independence=3, mood_fit=3, repetition=3, performance=3)
_LEGAL = UstadVerdict(verdict="legal")


def _violation(layer: str, swara: str = "M") -> Violation:
    return Violation(layer=layer, swara=swara, start_beat=0.0, kind="note", reason="out of raga")


def _producer(decision: str = "accept", plan: RevisionPlan | None = None) -> ProducerVerdict:
    return ProducerVerdict(scores=_SCORES, decision=decision, plan=plan)


def test_an_illegal_piece_is_a_forced_revise_of_the_worst_voice():
    ustad = UstadVerdict(verdict="illegal", violations=[
        _violation("rhythm", "M"), _violation("bass", "M"), _violation("lead", "g")])
    plan, events = decide(ustad, _producer("accept"))         # the Producer cannot overrule it
    assert plan is not None and plan.voice == "riff"          # rhythm + bass both derive from it
    assert "M" in plan.instruction
    assert events[0].type is EventType.VERDICT and events[0].agent == "Ustad"


def test_orchestra_roles_map_to_the_orchestra_voice():
    assert legality_plan([_violation("orch_strings")]).voice == "orchestra"


def test_an_illegal_code_voice_has_nothing_to_regenerate():
    # the drone / clean guitar are code: a violation there is a bug, not a re-roll
    assert legality_plan([_violation("drone"), _violation("clean")]) is None
    plan, events = decide(UstadVerdict(verdict="illegal", violations=[_violation("drone")]),
                          _producer())
    assert plan is None and events[0].data["decision"] == "accept"


def test_a_legal_piece_follows_the_producer():
    edit = RevisionPlan(voice="lead", sections=[2], instruction="hold komal dha",
                        preserve=["the mukhada"])
    plan, events = decide(_LEGAL, _producer("revise", edit))
    assert plan == edit
    assert events[0].agent == "Producer" and events[0].data["plan"]["preserve"] == ["the mukhada"]
    assert decide(_LEGAL, _producer("accept"))[0] is None


def test_a_revise_without_a_plan_is_an_accept():
    plan, events = decide(_LEGAL, _producer("revise", None))
    assert plan is None and events[0].verdict == "accept"


# --- the starved lead: a physical fault, forced like an illegal note -------------

def _chart():
    """Two 3-cycle sections (48 beats each): 0 = a riff with the lead under a rhythm spotlight,
    1 = a taan with the lead in the spotlight."""
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=72, motif=["S", "R", "g"],
        sections=[Section(kind=SectionKind.RIFF, bars=3, layers=["lead", "rhythm", "drone"],
                          foreground="rhythm"),
                  Section(kind=SectionKind.TAAN, bars=3, layers=["lead", "rhythm", "drone"],
                          foreground="lead")])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _held_lead() -> Composition:
    """The first live run's fault: one 48-beat sitar note in each section — on the page a
    melody, in the audio ~4 beats of pluck and then silence."""
    notes = [Note(swara="S", oct=0, start=0.0, dur=48.0), Note(swara="P", oct=0, start=48.0, dur=48.0)]
    return Composition(raga="darbari", sa=62, bpm=72,
                       tala={"name": "teentaal", "beats_per_bar": 16.0},
                       layers=[Layer(role="lead", instrument="sitar", notes=notes)])


def test_a_starved_lead_spotlight_is_a_forced_lead_revise_of_only_that_section():
    plan, events = decide(_LEGAL, _producer("accept"), _held_lead(), _chart())
    assert plan is not None and plan.voice == "lead"
    assert plan.sections == [1]                   # the taan; the riff's lead is not in the spotlight
    assert "hold no note longer" in plan.instruction and "fades" in plan.instruction
    assert events[0].type is EventType.VERDICT and events[0].data["plan"]["sections"] == [1]
    assert "section(s) 1" in events[0].text      # numbered as THE STRUCTURE shows it (0-based)
    from crew.revision import target_sections     # the plan's indices are what the revise reads
    assert target_sections(_chart(), plan) == [1]


def test_the_starved_lead_outranks_the_producers_own_plan():
    riff_edit = RevisionPlan(voice="riff", instruction="tighten the chugs")
    plan, _ = decide(_LEGAL, _producer("revise", riff_edit), _held_lead(), _chart())
    assert plan is not None and plan.voice == "lead"


def test_legality_outranks_the_starved_lead():
    ustad = UstadVerdict(verdict="illegal", violations=[_violation("rhythm", "M")])
    plan, events = decide(ustad, _producer(), _held_lead(), _chart())
    assert plan is not None and plan.voice == "riff" and events[0].agent == "Ustad"


def test_an_audible_lead_leaves_the_call_to_the_producer():
    dense = Composition(raga="darbari", sa=62, bpm=72,
                        tala={"name": "teentaal", "beats_per_bar": 16.0},
                        layers=[Layer(role="lead", instrument="sitar", notes=[
                            Note(swara="S", oct=0, start=float(i), dur=1.0) for i in range(96)])])
    assert decide(_LEGAL, _producer("accept"), dense, _chart())[0] is None


def test_without_the_composition_the_starved_check_is_skipped():
    # backward compatible: the two-argument call is the old decision exactly
    assert decide(_LEGAL, _producer("accept"))[0] is None


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
