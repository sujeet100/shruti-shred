"""
Tests for the lean Gemini provider and the per-tier thinking levels — pure, no API call (the
provider is constructed and asked for its request config, never sent).

CrewAI marks every schema property required (OpenAI strict mode), so Gemini wrote all ten fields
of every lead note — 148 characters where ~25 carry the information. `LeanGemini` keeps Pydantic's
own `required`; the tiers keep `medium` thinking for the few calls that conceive and judge.

Runs as a script (`uv run python tests/test_lean_gemini.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("GEMINI_API_KEY", "unused")    # the client is built, never called

from crew.config import build_llm, composer_llm, critic_llm, generator_llm  # noqa: E402
from crew.contracts import LeadPhrase, RiffPattern, SongSeed  # noqa: E402
from crew.lean_gemini import LeanGemini, lean_schema  # noqa: E402


def _items(schema: dict) -> dict:
    return schema["properties"]["notes"]["items"]


def test_a_note_requires_only_what_carries_information():
    assert _items(lean_schema(LeadPhrase))["required"] == ["swara", "dur"]
    assert set(_items(lean_schema(RiffPattern))["required"]) <= {"swara", "dur"}


def test_everything_but_the_notes_and_the_plan_stays_fully_required():
    seed = lean_schema(SongSeed)
    section = seed["properties"]["chart"]["properties"]["sections"]["items"]
    assert set(section["required"]) == set(section["properties"])   # form_role, intent... all asked for
    assert set(seed["required"]) == set(seed["properties"])


def test_the_request_keeps_the_reasoning_first_order():
    llm = build_llm("gemini/gemini-3.8-flash")
    assert isinstance(llm, LeanGemini)
    config = llm._prepare_generation_config(response_model=LeadPhrase)
    assert config.response_json_schema["propertyOrdering"] == ["phrase_plan", "notes"]
    assert _items(config.response_json_schema)["required"] == ["swara", "dur"]


def _level(llm) -> str:
    return llm.thinking_config.thinking_level.value.lower()


def test_conception_and_judging_think_while_the_generators_stay_fast():
    for var in ("RMA_CONCEPTION_THINKING", "RMA_JUDGE_THINKING", "RMA_REASONING_EFFORT"):
        os.environ.pop(var, None)
    assert _level(composer_llm()) == "medium" and _level(critic_llm()) == "medium"
    assert _level(generator_llm()) == "low"
    os.environ["RMA_JUDGE_THINKING"] = "high"
    try:
        assert _level(critic_llm()) == "high"
    finally:
        os.environ.pop("RMA_JUDGE_THINKING")


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
