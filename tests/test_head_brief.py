"""Pure tests for the motif experiment's switch (`crew/head_brief.py`) and the octave-free hook
measure (`crew/seed_measures.py`). No API."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crew.anchor import render_head_idea  # noqa: E402
from crew.contracts import HeadIdea  # noqa: E402
from crew.head_brief import core_idea_header, head_brief, motif_line, motif_value, withheld  # noqa: E402

_HEAD = HeadIdea(idea="a slow head on Sa", sam_swara="S", cell=["g", "m", "R", "S"],
                 stroke_line=["da", "ra"] * 8)


def test_default_is_todays_prompt():
    assert motif_line(["g", "m", "R", "S"]) == (
        "THE MOTIF (your seed — quote/derive the mukhada from it and the raga's pakad): g m R S")
    assert motif_value(["g", "m"]) == "g m" and not withheld()
    assert "its core cell recurring" in core_idea_header()
    shown = "\n".join(render_head_idea(_HEAD))
    assert "core cell: g m R S" in shown and "da ra" in shown


def test_guided_keeps_the_cell_and_asks_for_a_motif_first():
    with head_brief("guided"):
        line = motif_line(["g", "m", "R", "S"])
        assert "g m R S" in line and "Define the head's MOTIF first" in line
        assert "core cell: g m R S" in "\n".join(render_head_idea(_HEAD))


def test_free_withholds_motif_cell_and_strokes_but_keeps_the_sam():
    with head_brief("free"):
        assert withheld()
        assert "g m R S" not in motif_line(["g", "m", "R", "S"])
        assert motif_value(["g", "m", "R", "S"]) == "(none given — the gat head defines it)"
        shown = "\n".join(render_head_idea(_HEAD))
        assert "sam swara: S" in shown and "core cell" not in shown and "da ra" not in shown
        assert "its core cell recurring" not in core_idea_header()
    assert not withheld()                                     # the block ends, the default returns


def test_the_hook_measure_hears_an_octave_shift_as_the_same_line():
    from crew.contracts import LeadNote, LeadPhrase, PhrasePlan
    from crew.seed_measures import _hook_line, _similarity

    def seed_with(octave: int):
        class _S:                                            # the measure reads only .hook / .head
            head = None
            hook = LeadPhrase(phrase_plan=PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"],
                                                     climax_and_sam="Sa"),
                              notes=[LeadNote(swara=s, oct=octave, dur=1.0) for s in ("S", "g", "m", "R")])
        return _S()
    assert _similarity(_hook_line(seed_with(0)), _hook_line(seed_with(-1))) == 1.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
