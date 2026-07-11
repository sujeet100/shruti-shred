"""
Tests for the intake RESOLVER — the deterministic half of the Interpreter.

`resolve_brief` is pure (no LLM, no network), so it's fully testable here: known
ragas resolve, unknown ones fail loudly, keys map to Sa, subgenres fall back to
the raga's affinity, and out-of-range BPMs clamp. The LLM extraction half is
exercised live via `uv run python -m crew.intake`, not in this suite.

Runs as a script (`uv run python tests/test_intake.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import RawIntent, resolve_brief  # noqa: E402
from subgenres import SUBGENRES  # noqa: E402 (available via crew package path bootstrap)


def test_full_query_resolves():
    brief, problems = resolve_brief(RawIntent(raga="Malkauns", key="D", subgenre="doom", bpm=72))
    assert problems == []
    assert brief.raga == "malkauns"
    assert brief.sa == 62            # D
    assert brief.subgenre == "doom"
    assert brief.bpm == 72           # in doom's range, honored
    assert brief.instruments        # defaulted, non-empty


def test_unknown_raga_is_a_problem():
    brief, problems = resolve_brief(RawIntent(raga="Shred Major"))
    assert brief is None
    assert problems and "not one of" in problems[0]


def test_display_name_matches_key():
    brief, _ = resolve_brief(RawIntent(raga="Darbari Kanada"))
    assert brief.raga == "darbari"


def test_subgenre_defaults_from_affinity():
    # No subgenre given -> pick one whose affinity lists this raga; record assumption.
    brief, _ = resolve_brief(RawIntent(raga="malkauns"))
    assert brief.subgenre in {sg for sg, p in SUBGENRES.items() if "malkauns" in p["raga_affinity"]}
    assert any("subgenre" in a for a in brief.assumptions)


def test_key_defaults_to_D_when_absent():
    brief, _ = resolve_brief(RawIntent(raga="bhairav"))
    assert brief.sa == 62
    assert any("key" in a for a in brief.assumptions)


def test_bpm_clamped_to_subgenre_range():
    lo, hi = SUBGENRES["doom"]["bpm"]
    brief, _ = resolve_brief(RawIntent(raga="malkauns", subgenre="doom", bpm=999))
    assert brief.bpm == hi
    assert any("clamped" in a for a in brief.assumptions)


def test_bpm_defaults_to_range_midpoint():
    lo, hi = SUBGENRES["thrash"]["bpm"]
    brief, _ = resolve_brief(RawIntent(raga="bhairavi", subgenre="thrash"))
    assert brief.bpm == (lo + hi) // 2


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
