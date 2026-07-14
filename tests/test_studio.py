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
    Arrangement,
    ArrangementDraft,
    CanvasMove,
    CompositionBrief,
    DebateEvent,
    EventType,
    LeadNote,
    LeadPhrase,
    PhrasePlan,
    RiffNote,
    RiffPattern,
    Section,
    SectionCanvas,
    SectionIntent,
    SectionKind,
    build_arrangement,
)
from crew.studio import (  # noqa: E402
    StudioResult,
    Turn,
    active_roles,
    collaboration_schedule,
    follower_of,
    leader_for,
    run_studio,
    section_turns,
    session_canvas,
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


# --- the cooperative LOOP: active_roles / section_turns / run_studio -----------
# The loop is PURE — the note-writing is injected as `contribute`, so these tests
# drive it with a fake that records the turn order and stubs a line onto the canvas.

def _section(kind: SectionKind, layers: list[str], foreground: str) -> Section:
    return Section(kind=kind, bars=1, layers=layers, foreground=foreground)


def _arr(sections: list[Section]) -> Arrangement:
    """A real Arrangement (through the composer contract) to run the loop over, so
    section_spans / beats_per_bar are genuine. Darbari × teentaal."""
    draft = ArrangementDraft(raga="darbari", subgenre="progressive", tala="teentaal",
                             bpm=120, motif=["S", "R", "g", "m", "P"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _recorder():
    """A fake `contribute`: records each (role, move, #completed-canvases) call, writes a
    stub line so the canvas fills, and returns one event per turn. Returns (calls, fn)."""
    calls: list[tuple[str, CanvasMove, int]] = []

    def contribute(role, move, canvas, done):
        calls.append((role, move, len(done)))
        if role == "lead":
            canvas.lead = _lead_line()
        else:
            canvas.riff = _riff_line()
        return [DebateEvent(type=EventType.PROPOSE, agent=role.capitalize(),
                            role="generator", text=move.value, data={"move": move.value})]

    return calls, contribute


def test_active_roles_both_present_leader_first():
    riff = _section(SectionKind.RIFF, ["rhythm", "lead", "drums"], "rhythm")
    assert active_roles(riff) == ["rhythm", "lead"]        # leader (rhythm) first
    taan = _section(SectionKind.TAAN, ["lead", "rhythm", "drums"], "lead")
    assert active_roles(taan) == ["lead", "rhythm"]        # leader (lead) first


def test_active_roles_filters_a_voice_that_lays_out():
    # An alaap with no rhythm layer: only the lead is active (the riff lays out).
    alaap = _section(SectionKind.ALAAP, ["lead", "drone"], "lead")
    assert active_roles(alaap) == ["lead"]


def test_active_roles_none_when_no_creative_voice():
    drums_only = _section(SectionKind.BREAKDOWN, ["drums", "drone"], "drums")
    assert active_roles(drums_only) == []


def test_section_turns_two_active_is_the_full_schedule():
    riff = _section(SectionKind.RIFF, ["rhythm", "lead"], "rhythm")
    assert section_turns(riff, passes=3) == collaboration_schedule(SectionKind.RIFF, passes=3)


def test_section_turns_one_active_is_a_solo_propose():
    alaap = _section(SectionKind.ALAAP, ["lead", "drone"], "lead")
    assert section_turns(alaap) == [Turn("lead", CanvasMove.PROPOSE)]


def test_section_turns_none_active_is_empty():
    drums_only = _section(SectionKind.BREAKDOWN, ["drums", "drone"], "drums")
    assert section_turns(drums_only) == []


def test_session_canvas_carries_span_and_bandleader_rule():
    arr = _arr([_section(SectionKind.TAAN, ["lead", "rhythm"], "lead")])
    from crew.generators import section_spans
    span = section_spans(arr)[0]
    canvas = session_canvas(span)
    assert canvas.index == 0 and canvas.kind is SectionKind.TAAN
    assert canvas.leader == "lead" and canvas.follower == "rhythm"
    assert canvas.window == span.length


def test_run_studio_fills_a_canvas_per_section_and_orders_turns():
    arr = _arr([
        _section(SectionKind.RIFF, ["rhythm", "lead", "drums"], "rhythm"),
        _section(SectionKind.TAAN, ["lead", "rhythm", "drums"], "lead"),
    ])
    calls, contribute = _recorder()
    result = run_studio(arr, contribute=contribute, passes=3)

    assert isinstance(result, StudioResult)
    assert len(result.canvases) == 2
    assert result.canvases[0].lead is not None and result.canvases[0].riff is not None
    # The turn order is the two sections' schedules, back to back (roles + moves only).
    moves = [(role, move) for role, move, _ in calls]
    assert moves == [
        ("rhythm", CanvasMove.PROPOSE), ("lead", CanvasMove.RESPOND), ("rhythm", CanvasMove.REFINE),
        ("lead", CanvasMove.PROPOSE), ("rhythm", CanvasMove.RESPOND), ("lead", CanvasMove.REFINE),
    ]


def test_run_studio_threads_completed_canvases_as_memory():
    arr = _arr([
        _section(SectionKind.RIFF, ["rhythm", "lead"], "rhythm"),
        _section(SectionKind.TAAN, ["lead", "rhythm"], "lead"),
    ])
    calls, contribute = _recorder()
    run_studio(arr, contribute=contribute, passes=3)
    # Section 0's turns see 0 completed canvases; section 1's turns see exactly 1.
    prior_counts = [n for _, _, n in calls]
    assert prior_counts == [0, 0, 0, 1, 1, 1]


def test_run_studio_solo_section_runs_only_the_active_voice():
    arr = _arr([_section(SectionKind.ALAAP, ["lead", "drone"], "lead")])
    calls, contribute = _recorder()
    result = run_studio(arr, contribute=contribute)
    assert [(role, move) for role, move, _ in calls] == [("lead", CanvasMove.PROPOSE)]
    assert result.canvases[0].riff is None            # the riff laid out


def test_run_studio_skips_a_section_with_no_creative_voice():
    arr = _arr([_section(SectionKind.BREAKDOWN, ["drums", "drone"], "drums")])
    calls, contribute = _recorder()
    result = run_studio(arr, contribute=contribute)
    assert calls == []                                 # nobody wrote a note
    assert len(result.canvases) == 1                   # but the canvas still exists on the timeline


def test_run_studio_fast_mode_one_pass_is_leader_only():
    arr = _arr([_section(SectionKind.RIFF, ["rhythm", "lead"], "rhythm")])
    calls, contribute = _recorder()
    run_studio(arr, contribute=contribute, passes=1)
    assert [(role, move) for role, move, _ in calls] == [("rhythm", CanvasMove.PROPOSE)]


def test_run_studio_publishes_events_to_a_live_sink():
    # With a live sink installed, run_studio streams exactly the events it returns, in order —
    # this is what lets the UI show the collaboration AS IT HAPPENS, not only at the end.
    from crew.live import live_sink
    arr = _arr([
        _section(SectionKind.RIFF, ["rhythm", "lead", "drums"], "rhythm"),
        _section(SectionKind.TAAN, ["lead", "rhythm", "drums"], "lead"),
    ])
    _, contribute = _recorder()
    captured: list = []
    with live_sink(captured.append):
        result = run_studio(arr, contribute=contribute, passes=3)
    assert captured == result.events                 # everything streamed, same order


def test_run_studio_emits_a_framing_event_per_section():
    arr = _arr([
        _section(SectionKind.RIFF, ["rhythm", "lead"], "rhythm"),
        _section(SectionKind.ALAAP, ["lead", "drone"], "lead"),
    ])
    _, contribute = _recorder()
    result = run_studio(arr, contribute=contribute)
    framing = [e for e in result.events if e.agent == "Studio"]
    assert len(framing) == 2
    assert all(e.type is EventType.INFO for e in framing)
    assert "leads" in framing[0].text and "solo" in framing[1].text


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
