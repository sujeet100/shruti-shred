"""
Tests for the studio session's BANDLEADER + CLOCK — all pure (no key, no cost).

The whole thesis of the cooperative-collaboration pattern is that CODE, not the
agents, decides the order and the stopping point. So the two things worth proving
without any LLM are exactly those: (1) `leader_for` assigns each section kind a
leader and `follower_of` is always the other voice — the rotation is total and
deterministic; and (2) `collaboration_schedule` lays out a BOUNDED plan (leader
proposes, follower responds, then alternating refines) that truncates to `passes`
— the guaranteed terminator. Plus the `SectionCanvas` blackboard's basic shape.
The real cooperative LOOP (the LLM turns) is exercised in a later sub-step.

Runs as a script (`uv run python tests/test_studio.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.config import CANVAS_PASSES  # noqa: E402
from crew.contracts import (  # noqa: E402
    CanvasMove,
    LeadNote,
    LeadPhrase,
    PhrasePlan,
    RiffNote,
    RiffPattern,
    SectionCanvas,
    SectionIntent,
    SectionKind,
)
from crew.studio import (  # noqa: E402
    Turn,
    collaboration_schedule,
    follower_of,
    leader_for,
)

_RHYTHM_LED = (SectionKind.RIFF, SectionKind.BREAKDOWN)


# --- leader_for / follower_of: the rotation is total and deterministic ---------

def test_leader_for_rhythm_driven_kinds():
    for kind in _RHYTHM_LED:
        assert leader_for(kind) == "rhythm", kind


def test_leader_for_melodic_kinds():
    for kind in (SectionKind.ALAAP, SectionKind.MELODY, SectionKind.TAAN,
                 SectionKind.SOLO, SectionKind.OUTRO):
        assert leader_for(kind) == "lead", kind


def test_every_section_kind_has_a_valid_leader():
    # No kind falls through to a bogus leader — the rotation covers the whole vocabulary.
    for kind in SectionKind:
        assert leader_for(kind) in ("lead", "rhythm"), kind


def test_follower_is_always_the_other_voice():
    assert follower_of("lead") == "rhythm"
    assert follower_of("rhythm") == "lead"
    for kind in SectionKind:
        leader = leader_for(kind)
        assert follower_of(leader) != leader, kind


# --- collaboration_schedule: bounded, ordered, always terminating --------------

def test_schedule_opens_leader_propose_then_follower_respond():
    # A rhythm-led section: Riff proposes, Lead responds — the seed exchange.
    plan = collaboration_schedule(SectionKind.RIFF, passes=3)
    assert plan[0] == Turn("rhythm", CanvasMove.PROPOSE)
    assert plan[1] == Turn("lead", CanvasMove.RESPOND)
    assert plan[2] == Turn("rhythm", CanvasMove.REFINE)   # the leader integrates last


def test_schedule_follows_the_leader_for_a_melodic_kind():
    # A lead-led section flips who opens: Lead proposes, Riff responds.
    plan = collaboration_schedule(SectionKind.TAAN, passes=3)
    assert plan[0] == Turn("lead", CanvasMove.PROPOSE)
    assert plan[1] == Turn("rhythm", CanvasMove.RESPOND)
    assert plan[2] == Turn("lead", CanvasMove.REFINE)


def test_schedule_seed_exchange_at_two_passes():
    plan = collaboration_schedule(SectionKind.TAAN, passes=2)
    assert plan == [Turn("lead", CanvasMove.PROPOSE), Turn("rhythm", CanvasMove.RESPOND)]


def test_schedule_leader_only_at_one_pass():
    # Degenerate but well-defined: the follower never plays (documented in studio.py).
    plan = collaboration_schedule(SectionKind.TAAN, passes=1)
    assert plan == [Turn("lead", CanvasMove.PROPOSE)]


def test_schedule_refines_alternate_leader_first():
    plan = collaboration_schedule(SectionKind.RIFF, passes=5)
    moves = [(t.role, t.move) for t in plan]
    assert moves == [
        ("rhythm", CanvasMove.PROPOSE),
        ("lead", CanvasMove.RESPOND),
        ("rhythm", CanvasMove.REFINE),   # leader refines first
        ("lead", CanvasMove.REFINE),     # then the follower
        ("rhythm", CanvasMove.REFINE),   # then the leader again
    ]


def test_schedule_length_is_exactly_passes():
    for passes in range(1, 7):
        assert len(collaboration_schedule(SectionKind.MELODY, passes=passes)) == passes


def test_schedule_default_uses_canvas_passes():
    assert len(collaboration_schedule(SectionKind.MELODY)) == CANVAS_PASSES


# --- SectionCanvas: the blackboard's shape -------------------------------------

def _lead_line() -> LeadPhrase:
    return LeadPhrase(
        phrase_plan=PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"],
                               climax_and_sam="lands on Sa"),
        notes=[LeadNote(swara="S", dur=1.0)])


def _riff_line() -> RiffPattern:
    return RiffPattern(reasoning="root chug", notes=[RiffNote(swara="S", dur=0.5)])


def test_canvas_window_is_end_minus_start():
    canvas = SectionCanvas(index=0, kind=SectionKind.RIFF, start=4.0, end=20.0,
                           leader="rhythm", follower="lead")
    assert canvas.window == 16.0


def test_canvas_lines_start_empty_then_read_back():
    canvas = SectionCanvas(index=1, kind=SectionKind.TAAN, start=0.0, end=8.0,
                           leader="lead", follower="rhythm")
    assert canvas.lead is None and canvas.riff is None
    assert canvas.line_for("lead") is None and canvas.line_for("rhythm") is None
    assert canvas.log == []

    canvas.lead = _lead_line()
    canvas.riff = _riff_line()
    assert canvas.line_for("lead") is canvas.lead
    assert canvas.line_for("rhythm") is canvas.riff


# --- SectionIntent: the semantic layer, with grounded/closed vocab -------------

def _intent(**overrides) -> SectionIntent:
    base = dict(phrase_shape="question", energy=6, tension="rising",
                target_resolution="S", groove="syncopated")
    base.update(overrides)
    return SectionIntent(**base)


def test_section_intent_full_construction():
    intent = _intent(motif=["S", "R", "g"], rhythm_pattern=[0.5, 0.5, 1.0])
    assert intent.phrase_shape == "question" and intent.energy == 6
    assert intent.tension == "rising" and intent.groove == "syncopated"
    assert intent.target_resolution == "S"
    assert intent.motif == ["S", "R", "g"] and intent.rhythm_pattern == [0.5, 0.5, 1.0]


def test_section_intent_motif_defaults_empty():
    # Empty = inherit the piece motif (so the per-section cell can't drift from arr.motif).
    assert _intent().motif == [] and _intent().rhythm_pattern == []


def test_section_intent_energy_is_bounded_1_to_10():
    for good in (1, 6, 10):
        assert _intent(energy=good).energy == good
    for bad in (0, 11):
        try:
            _intent(energy=bad)
            assert False, f"expected energy {bad} to be rejected"
        except Exception:  # noqa: BLE001
            pass


def test_section_intent_motif_rejects_unknown_swara():
    try:
        _intent(motif=["S", "Z"])
        assert False, "expected an unknown motif swara to be rejected"
    except Exception as e:  # noqa: BLE001
        assert "unknown" in str(e).lower()


def test_section_intent_target_resolution_must_be_a_known_swara():
    assert _intent(target_resolution="P").target_resolution == "P"
    try:
        _intent(target_resolution="Q")
        assert False, "expected an unknown target_resolution to be rejected"
    except Exception as e:  # noqa: BLE001
        assert "target_resolution" in str(e).lower()


def test_section_intent_rhythm_pattern_beats_must_be_positive():
    try:
        _intent(rhythm_pattern=[0.5, 0.0])
        assert False, "expected a non-positive rhythm beat to be rejected"
    except Exception as e:  # noqa: BLE001
        assert "positive" in str(e).lower()


def test_section_intent_rejects_out_of_vocabulary_values():
    for field, bad in (("phrase_shape", "solo"), ("tension", "spicy"), ("groove", "shuffle")):
        try:
            _intent(**{field: bad})
            assert False, f"expected {field}={bad!r} to be rejected"
        except Exception:  # noqa: BLE001
            pass


def test_canvas_intent_defaults_none_then_reads_back():
    canvas = SectionCanvas(index=0, kind=SectionKind.RIFF, start=0.0, end=16.0,
                           leader="rhythm", follower="lead")
    assert canvas.intent is None
    canvas.intent = _intent(motif=["S"], groove="gallop")
    assert canvas.intent.groove == "gallop" and canvas.intent.motif == ["S"]


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
