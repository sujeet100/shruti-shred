"""
Tests for the Interpreter's RESOLVER — its deterministic half.

`resolve_brief` is pure (no LLM), so it's fully testable here. Its contract:
extract & validate ONLY what the user stated, invent nothing, always succeed.
NOTHING is required (mood-only is fine). A stated raga/subgenre is kept only if
supported (else noted, left open); a stated key -> Sa; bpm/instruments/mood pass
through; everything unstated stays None = "open for the composers." The LLM
extraction half is exercised live via `uv run python -m crew.interpreter`, not here.

Runs as a script (`uv run python tests/test_interpreter.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import RawIntent, resolve_brief  # noqa: E402


def test_stated_fields_are_kept_verbatim():
    brief = resolve_brief(RawIntent(raga="Malkauns", key="D", subgenre="doom", bpm=72))
    assert brief.raga == "malkauns"
    assert brief.key == "D" and brief.sa == 62
    assert brief.subgenre == "doom"
    assert brief.bpm == 72


def test_mood_only_query_resolves_everything_open():
    # "a romantic metal fusion" -> nothing but a mood; the composers pick it all.
    brief = resolve_brief(RawIntent(mood="romantic"))
    assert brief.mood == "romantic"
    assert brief.raga is None and brief.subgenre is None and brief.bpm is None


def test_unstated_dimensions_stay_open():
    brief = resolve_brief(RawIntent(raga="malkauns"))
    assert brief.subgenre is None
    assert brief.bpm is None
    assert brief.instruments is None
    assert brief.sa is None


def test_unsupported_raga_left_open_with_note():
    # Raga is optional now: an unsupported one is noted and left open, not blocked.
    brief = resolve_brief(RawIntent(raga="Yaman"))
    assert brief.raga is None
    assert any("not supported" in n for n in brief.notes)


def test_display_name_matches_key():
    brief = resolve_brief(RawIntent(raga="Darbari Kanada"))
    assert brief.raga == "darbari"


def test_unsupported_subgenre_left_open_with_note():
    brief = resolve_brief(RawIntent(raga="bhairav", subgenre="black metal"))
    assert brief.subgenre is None
    assert any("not supported" in n for n in brief.notes)


def test_stated_bpm_is_not_clamped():
    brief = resolve_brief(RawIntent(raga="malkauns", subgenre="doom", bpm=180))
    assert brief.bpm == 180


def test_mood_does_not_pick_a_subgenre():
    brief = resolve_brief(RawIntent(raga="darbari", mood="heavy"))
    assert brief.mood == "heavy"
    assert brief.subgenre is None


def test_unrecognized_key_left_open_with_note():
    brief = resolve_brief(RawIntent(raga="bhairav", key="H"))
    assert brief.key is None and brief.sa is None
    assert any("key" in n for n in brief.notes)


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
