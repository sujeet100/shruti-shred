"""
Tests for the COMPACT RIFF NOTATION (2026-10-13) — one avartan cycle as one short string, the
rhythm-section call's output format, read back into the RiffNotes the pipeline plays. Pure, no LLM.

Runs as a script (`uv run python tests/test_riff_notation.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import RhythmSectionDraft, RiffNote, SectionPartDraft  # noqa: E402
from crew.rhythm_section import from_draft  # noqa: E402
from crew.rhythm_section_call import rhythm_section_guardrail  # noqa: E402
from crew.riff_notation import NotationError, parse_cycle, render_cycle  # noqa: E402
from tests.test_rhythm_section import _arr, _good  # noqa: E402


def test_every_form_of_a_token_reads():
    notes = parse_cycle("d[2] d[.5]pm! P(+1)[1]@100 S+P[2] -[1] R(-1)[0.5]sl")
    assert notes[0] == RiffNote(swara="d", dur=2.0)
    assert notes[1].technique == "palm_mute" and notes[1].single and notes[1].dur == 0.5
    assert notes[2].oct == 1 and notes[2].vel == 100
    assert notes[3].chord == ["P"]
    assert notes[4].rest and notes[4].dur == 1.0
    assert notes[5].oct == -1 and notes[5].technique == "slide"


def test_full_technique_names_work_too():
    assert parse_cycle("d[.5]palm_mute")[0].technique == "palm_mute"


def test_render_and_parse_are_inverses():
    text = "d[1]@120 d[.5]pm d[.5]pm P(+1)[1] -[.5] n[.5]! S+g+n[2] R[1]ho"
    assert render_cycle(parse_cycle(text)) == text


def test_an_unreadable_token_names_itself():
    for bad, words in (("d2", "not a note"), ("x[1]", "not a note"), ("d[1]zz", "not a technique"),
                       ("d[1]@200", "velocity 200"), ("d[0]", "no length"), ("", "empty")):
        try:
            parse_cycle(bad)
        except NotationError as exc:
            assert words in str(exc), (bad, str(exc))
        else:
            raise AssertionError(f"{bad!r} parsed")


def test_a_draft_reads_back_into_the_parts_the_pipeline_plays():
    good = _good()
    draft = RhythmSectionDraft(reasoning=good.reasoning, parts=[
        SectionPartDraft(section=p.section, role=p.role, same_as=p.same_as,
                         guitar=[render_cycle(c) for c in p.guitar],
                         bass=[render_cycle(c) for c in p.bass]) for p in good.parts])
    rs, faults = from_draft(draft)
    assert faults == [] and rs == good


def test_the_guardrail_sends_an_unreadable_cycle_back_by_name():
    draft = RhythmSectionDraft(parts=[SectionPartDraft(section=1, guitar=["d[2] d2"])])
    ok, message = rhythm_section_guardrail(_arr())(SimpleNamespace(pydantic=draft, raw=None))
    assert not ok and "section 1 guitar cycle 1" in message and "'d2'" in message


def test_an_octave_on_a_chord_tone_is_refused_with_the_rule_that_fixes_it():
    # the notes debate's guitarist wrote S(-1)+P(-1) twice (2026-10-19) on an error that named no rule
    try:
        parse_cycle("S(-1)+P(-1)[2]")
        raise AssertionError("an octave on a chord tone should not read")
    except NotationError as exc:
        assert "root only" in str(exc)
    assert parse_cycle("S(-1)+P[2]")[0].chord == ["P"]


def test_the_compact_cycle_is_a_fraction_of_the_json():
    # the 074703 answer spelled every field of every note (~110 characters a note)
    notes = parse_cycle("d[2]@115 d[.5]pm! d[.5]pm! P[.5]pm! d[.5]pm! -[1] m[2] S[1]")
    as_json = "[" + ", ".join(n.model_dump_json() for n in notes) + "]"
    assert len(render_cycle(notes)) * 5 < len(as_json)


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
