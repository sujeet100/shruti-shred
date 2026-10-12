"""
Tests for the RHYTHM SECTION in the pipeline — the call made safe (any failure falls back to the
riff path), which riff calls are skipped, the composed part carried on the chart and played as
written with its own bass, the section-by-section revise, and the Flow storing the part. No LLM.

Runs as a script (`uv run python tests/test_rhythm_voice.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.band import band_layers  # noqa: E402
from crew.contracts import Layer, RevisionPlan, RhythmSection, SectionPart  # noqa: E402
from crew.flow import compose_flow  # noqa: E402
from crew.rhythm_section import realise, rhythm_section_from_events, with_rhythm_section  # noqa: E402
from crew.rhythm_voice import (  # noqa: E402
    compose_rhythm_voice,
    creative_voices_with_rhythm_section,
    no_riff,
    revise_rhythm_voice,
    rhythm_section_event,
)
from tests.test_flow import _accept, _fake_stages  # noqa: E402
from tests.test_rhythm_section import _HOME, _MOVE, _arr, _cycle, _good, _head, _sitar  # noqa: E402

_LEGACY = Layer(role="rhythm", notes=[])


def _legacy(marks: list[str]):
    def run():
        marks.append("legacy")
        return _LEGACY, []
    return run


# --- the call, made safe ------------------------------------------------------------------------

def test_a_playable_answer_is_realised_and_published():
    marks: list[str] = []
    guitar, events = compose_rhythm_voice(_arr(), _sitar(*_head(16.0)),
                                          call=lambda arr, lead, **kw: _good(),
                                          legacy=_legacy(marks))
    assert marks == [] and guitar == realise(_good(), _arr())[0]
    assert rhythm_section_from_events(events) == _good()


def test_a_call_that_raises_falls_back_to_the_riff_path():
    marks: list[str] = []
    def boom(arr, lead, **kw):
        raise RuntimeError("guardrail retries exhausted")
    guitar, events = compose_rhythm_voice(_arr(), _sitar(), call=boom, legacy=_legacy(marks))
    assert marks == ["legacy"] and guitar is _LEGACY
    assert "riff path plays" in events[0].text and rhythm_section_from_events(events) is None


def test_an_unplayable_answer_falls_back_too():
    marks: list[str] = []
    bad = RhythmSection(parts=[SectionPart(section=1, guitar=[_cycle(("S", 8.0))])])
    guitar, _ = compose_rhythm_voice(_arr(), _sitar(), call=lambda arr, lead, **kw: bad,
                                     legacy=_legacy(marks))
    assert marks == ["legacy"] and guitar is _LEGACY


# --- which riff calls run -----------------------------------------------------------------------

def _voices(seen: dict):
    def voices(arr, *, riff_fn=None, announce=None, emit=None):
        seen["riff_fn"] = riff_fn
        return _sitar(*_head(16.0)), (None if riff_fn is no_riff else _LEGACY), []
    return voices


def test_a_gat_first_piece_skips_the_per_section_riff():
    seen: dict = {}
    _, rhythm, events = creative_voices_with_rhythm_section(
        _arr(), voices=_voices(seen), composer=False, call=lambda arr, lead, **kw: _good(),
        legacy_riff=lambda arr, events: (_LEGACY, []))
    assert seen["riff_fn"] is no_riff and rhythm_section_from_events(events) == _good()


def test_a_riff_first_head_still_gets_its_riff_and_that_riff_is_the_fallback():
    seen: dict = {}
    arr = _arr().model_copy(update={"anchor": "riff_first"})
    calls: list[str] = []
    _, rhythm, _ = creative_voices_with_rhythm_section(
        arr, voices=_voices(seen), composer=False,
        call=lambda arr, lead, **kw: (_ for _ in ()).throw(ValueError("no")),
        legacy_riff=lambda arr, events: calls.append("legacy riff") or (None, []))
    assert seen["riff_fn"] is None                  # the real riff ran: the head quotes it
    assert rhythm is _LEGACY and calls == []        # ...and it is the fallback, not a 2nd call


def test_the_composer_path_never_runs_the_riff_first():
    seen: dict = {}
    arr = _arr().model_copy(update={"anchor": "riff_first"})
    creative_voices_with_rhythm_section(arr, voices=_voices(seen), composer=True,
                                        call=lambda arr, lead, **kw: _good(),
                                        legacy_riff=lambda arr, events: (None, []))
    assert seen["riff_fn"] is no_riff               # the seed riff is on the chart already


# --- the part on the chart, played as written ---------------------------------------------------

def test_a_composed_part_plays_as_written_with_its_own_bass():
    arr = with_rhythm_section(_arr(), [rhythm_section_event(_good(), "x")])
    guitar, bass = realise(_good(), arr)
    layers = band_layers(arr, _sitar(*_head(16.0)), guitar)
    rhythm = next(ly for ly in layers if ly.role == "rhythm")
    played = next(ly for ly in layers if ly.role == "bass")
    assert [(n.start, n.swara) for n in rhythm.notes][:3] == [(n.start, n.swara) for n in guitar.notes][:3]
    assert [n.swara for n in played.notes if 16 <= n.start < 32][:2] == ["S", "P"]   # its bass


# --- the revise ---------------------------------------------------------------------------------

def test_a_revise_rewrites_only_the_named_sections():
    arr = with_rhythm_section(_arr(), [rhythm_section_event(_good(), "x")])
    plan = RevisionPlan(voice="riff", sections=[2], instruction="move to the low roots",
                        preserve=["the head's pattern"])
    asked: dict = {}
    def call(arr, lead, *, feedback=None):
        asked["feedback"] = feedback
        return RhythmSection(parts=[SectionPart(section=2, guitar=[_HOME]),
                                    SectionPart(section=1, guitar=[_MOVE])])   # 1 is ignored
    _, events = revise_rhythm_voice(arr, arr, plan, _sitar(), call=call)
    new = rhythm_section_from_events(events)
    assert {p.section: p for p in new.parts}[2].guitar == [_HOME]
    assert {p.section: p for p in new.parts}[1] == _good().parts[0]
    assert "section(s) 2 only" in asked["feedback"][0] and "the head's pattern" in asked["feedback"][0]


def test_an_unplayable_revise_keeps_the_part():
    arr = with_rhythm_section(_arr(), [rhythm_section_event(_good(), "x")])
    plan = RevisionPlan(voice="riff", sections=[2], instruction="x")
    bad = RhythmSection(parts=[SectionPart(section=2, guitar=[_cycle(("S", 3.0))])])
    _, events = revise_rhythm_voice(arr, arr, plan, _sitar(), call=lambda arr, lead, **kw: bad)
    assert rhythm_section_from_events(events) == _good() and "the part stands" in events[0].text


# --- the Flow keeps it on the chart -------------------------------------------------------------

def test_the_flow_stores_the_composed_part_on_the_chart_before_assembling():
    counts: dict = {}
    fake = _fake_stages([_accept()], counts=counts)
    seen: dict = {}
    stages = replace(
        fake,
        generate=lambda arr: ([Layer(role="lead")], Layer(role="rhythm"), [],
                              [rhythm_section_event(_good(), "x")], []),
        assemble=lambda arr, *rest: seen.setdefault("arr", arr) and fake.assemble(arr, *rest))
    state = compose_flow("q", stages=stages, max_rounds=1)
    assert state.arrangement.rhythm_section == _good()
    assert seen["arr"].rhythm_section == _good()


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
