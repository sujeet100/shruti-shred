"""
Tests for the composer DIALOGUE LOOP — its deterministic control flow.

`run_dialogue` takes an injected `turn_fn`, so the whole bounded loop is tested
here with a FAKE composer (canned turns, no LLM, no key, no cost): does Pandit
open, do the speakers alternate, does the draft thread turn-to-turn, does it stop
early on agreement, and — the live-safety property — does the turn cap ALWAYS
terminate it? The real LLM turn is exercised live via `uv run python -m
crew.composers`, not here.

Runs as a script (`uv run python tests/test_composers.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.composers import Composer, _validate_turn, run_dialogue  # noqa: E402
from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    ComposerTurn,
    EventType,
    Section,
    SectionKind,
    build_arrangement,
)
from talas import TALAS  # noqa: E402


def _draft(raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
           motif=("d", "n", "S", "m"), anchor="gat_first") -> ArrangementDraft:
    # A minimal but VALID gat: a mukhada that RETURNS (stated, developed, brought back).
    # The mukhada sections carry the lead — a section that rests the lead may run at most
    # 2 bars (the lead-less cap), and a real mukhada is the lead's hook anyway.
    return ArrangementDraft(
        raga=raga, subgenre=subgenre, tala=tala, bpm=bpm, motif=list(motif), anchor=anchor,
        sections=[
            Section(kind=SectionKind.RIFF, bars=4, layers=["lead", "rhythm", "drums", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.MELODY, bars=2, layers=["lead", "drone"],
                    foreground="lead", form_role="manjha"),
            Section(kind=SectionKind.RIFF, bars=4, layers=["lead", "rhythm", "drums", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada")])


def _turn(agree=False, note="x", **draft_over) -> ComposerTurn:
    return ComposerTurn(draft=_draft(**draft_over), note=note, agree=agree)


def _scripted(turns):
    """A fake turn_fn that replays canned turns and records how it was called."""
    calls: list[dict] = []
    it = iter(turns)

    def fn(speaker, draft, transcript):
        calls.append({"speaker": speaker, "draft": draft, "transcript": transcript})
        return next(it)

    return fn, calls


_BRIEF = CompositionBrief(mood="dark")


def test_pandit_opens_and_speakers_alternate():
    fn, calls = _scripted([_turn(), _turn(), _turn()])
    run_dialogue(_BRIEF, turn_fn=fn, max_turns=3)
    assert [c["speaker"] for c in calls] == [Composer.PANDIT, Composer.RIFFSMITH, Composer.PANDIT]


def test_turn_cap_always_terminates():
    fn, calls = _scripted([_turn(agree=False)] * 3)   # nobody ever agrees
    arr, events = run_dialogue(_BRIEF, turn_fn=fn, max_turns=3)
    assert len(calls) == 3
    assert any("cap" in e.text.lower() for e in events)
    assert arr is not None


def test_stops_early_on_agreement():
    fn, calls = _scripted([_turn(), _turn(agree=True), _turn()])
    _, events = run_dialogue(_BRIEF, turn_fn=fn, max_turns=3)
    assert len(calls) == 2                              # stopped after the 2nd turn agreed
    assert any("agrees" in e.text.lower() for e in events)


def test_opening_turn_cannot_short_circuit():
    # Pandit "agreeing" on turn 1 is meaningless (nothing to agree with) — ignored.
    fn, calls = _scripted([_turn(agree=True), _turn(agree=False), _turn(agree=False)])
    run_dialogue(_BRIEF, turn_fn=fn, max_turns=3)
    assert len(calls) == 3


def test_evolving_draft_is_threaded_turn_to_turn():
    fn, calls = _scripted([_turn(bpm=72), _turn(bpm=100), _turn(bpm=140)])
    run_dialogue(_BRIEF, turn_fn=fn, max_turns=3)
    assert calls[0]["draft"] is None                   # the opener has no draft
    assert calls[1]["draft"].bpm == 72                 # Riffsmith sees Pandit's draft
    assert calls[2]["draft"].bpm == 100                # Pandit sees Riffsmith's draft


def test_arrangement_built_from_last_draft_and_honors_brief():
    brief = CompositionBrief(raga="bhairav", bpm=190)
    turn = ComposerTurn(
        draft=ArrangementDraft(
            raga="bhairav", subgenre="thrash", tala="keherwa", bpm=72,
            motif=["G", "m", "d", "d", "P"],
            sections=[Section(kind=SectionKind.RIFF, bars=4,
                              layers=["rhythm", "drums", "drone"], foreground="rhythm")]),
        note="last", agree=False)
    fn, _ = _scripted([turn, turn, turn])
    arr, _events = run_dialogue(brief, turn_fn=fn, max_turns=3)
    assert arr.raga == "bhairav"
    assert arr.bpm == 190                              # brief's fixed bpm overrides the draft
    assert arr.tala == "keherwa"
    assert len(arr.accent_grid) == TALAS["keherwa"]["matras"]


def test_events_stream_the_transcript():
    fn, _ = _scripted([_turn(note="open"), _turn(note="counter", agree=True)])
    _, events = run_dialogue(_BRIEF, turn_fn=fn, max_turns=3)
    turns = [e for e in events if e.type in (EventType.PROPOSE, EventType.DEBATE)]
    assert [e.text for e in turns] == ["open", "counter"]
    assert turns[0].type == EventType.PROPOSE and turns[0].agent == "Pandit"
    assert turns[1].type == EventType.DEBATE and turns[1].agent == "Riffsmith"


def test_max_turns_must_be_positive():
    fn, _ = _scripted([])
    try:
        run_dialogue(_BRIEF, turn_fn=fn, max_turns=0)
        assert False, "expected ValueError"
    except ValueError:
        pass


class _FakeOutput:
    """Stand-in for a CrewAI TaskOutput carrying an output_pydantic-parsed turn."""
    def __init__(self, turn: ComposerTurn) -> None:
        self.pydantic = turn
        self.raw = turn.model_dump_json()


def test_guardrail_passes_a_legal_motif():
    ok, value = _validate_turn(_FakeOutput(_turn(motif=("d", "n", "S", "m"))))  # legal in Malkauns
    assert ok is True
    assert isinstance(value, ComposerTurn)


def test_guardrail_rejects_an_illegal_motif_with_a_precise_error():
    # 'R' (shuddha Re) is a valid symbol (so the draft parses) but illegal in Malkauns,
    # so the DOMAIN guardrail — not the schema — is what rejects it, for a bounded retry.
    ok, msg = _validate_turn(_FakeOutput(_turn(motif=("d", "R", "S"))))
    assert ok is False
    assert "illegal" in msg.lower() and "R" in msg


def test_guardrail_rejects_a_rhythm_section_without_a_slot():
    # a legal motif, but a rhythm section names no riff -> the song-form guardrail bounces it
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[Section(kind=SectionKind.RIFF, bars=4, layers=["rhythm", "drone"],
                          foreground="rhythm")])   # no riff_slot
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "riff_slot" in msg


def test_guardrail_allows_a_lead_only_section_without_a_slot():
    # a lead-only section needs no riff_slot; the rest still forms a valid gat (mukhada returns;
    # the single lead-less riff section stays within the 2-bar cap)
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.ALAAP, bars=3, layers=["lead", "drone"],
                    foreground="lead", form_role="intro"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada")])
    ok, value = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is True and isinstance(value, ComposerTurn)


def test_guardrail_requires_a_roomy_intro():
    # a 2-avartan alap was heard as rushed — the aochar needs at least 3
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.ALAAP, bars=2, layers=["lead", "drone"],
                    foreground="lead", form_role="intro"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada")])
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "intro" in msg.lower() and "3" in msg


def test_guardrail_requires_two_bars_of_mukhada_after_a_manjha():
    # the head must re-establish itself (2+ loops) after the manjha before anything else
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.MELODY, bars=2, layers=["lead", "drone"],
                    foreground="lead", form_role="manjha"),
            Section(kind=SectionKind.RIFF, bars=1, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada")])
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "re-establish" in msg


def test_guardrail_allows_at_most_one_leadless_section():
    # one riff-only interlude is a contrast; a second is a hole in the gat
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.BREAKDOWN, bars=2, layers=["rhythm", "drone"],
                    foreground="rhythm", riff_slot="breakdown", form_role="breakdown")])
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "At most 1 lead-less" in msg


def test_guardrail_rejects_a_manjha_not_followed_by_a_mukhada():
    # the manjha is the head's complement: the mukhada must re-enter IMMEDIATELY after it
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.MELODY, bars=2, layers=["lead", "drone"],
                    foreground="lead", form_role="manjha"),
            Section(kind=SectionKind.BREAKDOWN, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="breakdown", form_role="breakdown"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada")])
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "manjha" in msg.lower() and "immediately" in msg.lower()


def test_guardrail_rejects_a_manjha_before_the_first_mukhada():
    # a manjha develops the head — it cannot appear before the head has been stated
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.MELODY, bars=2, layers=["lead", "drone"],
                    foreground="lead", form_role="manjha"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada")])
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "manjha" in msg.lower()


def test_guardrail_caps_leadless_sections_at_two_bars():
    # a riff-only interlude is a short contrast — the gat must never vanish for long
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.RIFF, bars=3, layers=["rhythm", "drone"],
                    foreground="rhythm", riff_slot="breakdown", form_role="breakdown"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada")])
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "lead-less" in msg.lower()


def _gat_sections(*roles: str) -> list[Section]:
    """Sections carrying the given form_roles; rhythm-bearing ones get a slot and every
    section carries the lead, so only the form_role rule under test is what fails (not the
    riff_slot / lead-less rules)."""
    return [Section(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role=role) for role in roles]


def test_guardrail_requires_a_form_role_on_every_section():
    # a valid gat except one section is left without a form_role -> bounced
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drone"],
                    foreground="rhythm", riff_slot="main", form_role="mukhada"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drone"],
                    foreground="rhythm", riff_slot="main"),  # no form_role
        ])
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "form_role" in msg


def test_guardrail_requires_the_mukhada_to_return():
    # every section has a form_role, but the mukhada is stated only once -> no hook return
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=_gat_sections("mukhada", "breakdown"))
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "mukhada" in msg.lower()


def test_guardrail_accepts_a_returning_mukhada():
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=_gat_sections("mukhada", "manjha", "mukhada"))
    ok, value = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is True and isinstance(value, ComposerTurn)


def test_guardrail_rejects_more_than_one_long_taan():
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=_gat_sections("mukhada", "taan_long", "taan_long", "mukhada"))
    ok, msg = _validate_turn(_FakeOutput(ComposerTurn(draft=draft, note="x")))
    assert ok is False and "taan_long" in msg


def test_anchor_defaults_to_gat_first_and_round_trips_to_the_arrangement():
    assert build_arrangement(_draft(), CompositionBrief(mood="dark")).anchor == "gat_first"
    assert build_arrangement(_draft(anchor="riff_first"), CompositionBrief()).anchor == "riff_first"


def test_reasoning_monologue_is_carried_into_the_turn_event():
    turn = ComposerTurn(reasoning="respect the tempo, push the alaap", draft=_draft(), note="counter")
    fn, _ = _scripted([_turn(), turn])
    _, events = run_dialogue(_BRIEF, turn_fn=fn, max_turns=2)
    debate = [e for e in events if e.type == EventType.DEBATE][0]
    assert debate.data["reasoning"] == "respect the tempo, push the alaap"


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
