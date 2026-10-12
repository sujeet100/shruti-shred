"""
Tests for the RHYTHM SECTION call's pure half — the prompt inputs (every placeholder the template
names is given), and the guardrail that turns the hard checks into one bounded retry. No LLM.

Runs as a script (`uv run python tests/test_rhythm_section_call.py`) or under pytest.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import RhythmSection, SectionPart  # noqa: E402
from crew.rhythm_section_call import rhythm_section_guardrail, rhythm_section_inputs  # noqa: E402
from tests.test_rhythm_section import _arr, _cycle, _good, _head, _sitar  # noqa: E402

_TASK = yaml.safe_load((Path(__file__).parent.parent / "crew" / "config" / "tasks.yaml")
                       .read_text())["compose_rhythm_section"]


def test_every_placeholder_in_the_template_is_an_input_it_receives():
    # 2026-10-12: a brace in a legend killed a live run at Rasik; this template may contain no
    # placeholder it is not given
    wanted = set(re.findall(r"\{([^{}]*)\}", _TASK["description"] + _TASK["expected_output"]))
    given = set(rhythm_section_inputs(_arr(), _sitar(*_head(16.0))))
    assert wanted <= given, wanted - given
    assert given <= wanted, given - wanted                      # nothing computed and unused


def test_the_inputs_carry_the_sitar_the_chart_and_its_harmony_plans():
    inputs = rhythm_section_inputs(_arr(), _sitar(*_head(16.0)))
    assert "2 (m)g~[4]" in inputs["sitar_line"]
    assert "section 1: mukhada, 2 avartans, guitar plays" in inputs["chart"]
    assert "section 0: intro, 1 avartan, NO guitar" in inputs["chart"]
    assert "beat 0 sam" in inputs["accents"] and "khali" in inputs["accents"]
    assert "none" in inputs["seed_riff"]
    assert "first take" in inputs["repair"]


def test_a_retry_names_the_faults_it_must_fix():
    inputs = rhythm_section_inputs(_arr(), _sitar(), feedback=["section 2 guitar cycle 1: short"])
    assert "section 2 guitar cycle 1: short" in inputs["repair"]


def test_the_guardrail_passes_a_playable_part_and_returns_it():
    ok, value = rhythm_section_guardrail(_arr())(SimpleNamespace(pydantic=_good(), raw=None))
    assert ok and value == _good()


def test_the_guardrail_bounces_an_unplayable_part_with_its_faults():
    bad = RhythmSection(parts=[SectionPart(section=1, guitar=[_cycle(("S", 8.0))])])
    ok, message = rhythm_section_guardrail(_arr())(SimpleNamespace(pydantic=bad, raw=None))
    assert not ok and "section 1 guitar cycle 1" in message and "section 2" in message


def test_the_guardrail_asks_again_for_an_unparseable_answer():
    ok, message = rhythm_section_guardrail(_arr())(SimpleNamespace(pydantic=None, raw="not json"))
    assert not ok and "RhythmSection" in message


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
