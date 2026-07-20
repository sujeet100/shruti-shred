"""
Tests for the gat-form library — the stroke (bol) frames as testable knowledge.

All pure (no key, no cost). The same discipline as the raga/tala knowledge tests:
every encoded fact that CAN be asserted IS asserted — the Masitkhani grid matches its
sourced structure (the 8-bol unit twice, dir on 4/6/12/14, the mukhda anacrusis on
12-16), the Razakhani entry stays grid-less (flexibility is the sourced fact), and the
laya mapping sends doom to Masitkhani and every faster subgenre to Razakhani.

Runs as a script (`uv run python tests/test_gats.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from gats import GAT_FRAMES, check_gat_frame_consistency, frame_for_bpm  # noqa: E402
from subgenres import SUBGENRES  # noqa: E402


def test_frames_are_internally_consistent():
    assert check_gat_frame_consistency() == []


def test_masitkhani_grid_matches_the_sourced_structure():
    f = GAT_FRAMES["masitkhani"]
    assert len(f["bols"]) == f["matras"] == 16
    # the 8-bol unit "da da ra dir da dir da ra" (written from the sam) stated twice
    assert f["bols"][:8] == f["bols"][8:] == ["da", "da", "ra", "dir", "da", "dir", "da", "ra"]
    # the mukhda = matras 12-16, the anacrusis "dir da dir da ra" into the next sam
    assert f["mukhda_start"] == 12
    assert f["bols"][11:16] == ["dir", "da", "dir", "da", "ra"]
    assert f["double_stroke_matras"] == [4, 6, 12, 14]


def test_razakhani_encodes_vocabulary_not_an_invented_grid():
    f = GAT_FRAMES["razakhani"]
    assert f["bols"] is None                       # no verified matra map — never guess one
    assert "dir" in f["bol_phrase"]                # Parikh's canonical bol set is recorded
    assert f["mukhda_starts"] == [1, 7, 9]         # sam, matra 7, khali — the sanctioned options


def test_every_frame_records_at_least_two_sources():
    for f in GAT_FRAMES.values():
        assert len(f["sources"]) >= 2


def test_frame_for_bpm_splits_the_slow_laya_from_the_fast():
    doom_lo, _ = SUBGENRES["doom"]["bpm"]
    assert frame_for_bpm(doom_lo) == frame_for_bpm(72) == "masitkhani"   # doom's home range
    assert frame_for_bpm(90) == "razakhani"    # the boundary: symphonic STARTS at 90 (laya rules, not genre)
    for name, s in SUBGENRES.items():
        if name == "doom":
            continue
        lo, hi = s["bpm"]
        assert frame_for_bpm(lo) == frame_for_bpm(hi) == "razakhani", name


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
