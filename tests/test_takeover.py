"""
Tests for the TAKEOVER (2026-10-12): when the guitar carries the gat, it plays the realised mukhada
arranged for guitar — low power chords where the head lands, its melody as mid-register single
notes, its strokes kept — the second avartan developing the first into a heavy cadence, on every
path (the band assembly replaces whatever the guitar wrote there). Pure, no LLM.

Runs as a script (`uv run python tests/test_takeover.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.band import band_layers  # noqa: E402
from crew.composers import _roleless_error, _gat_role_error  # noqa: E402
from crew.form_budget import FULL_FORM  # noqa: E402
from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    LeadNote,
    LeadPhrase,
    PhrasePlan,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.head_anatomy import accent_beats  # noqa: E402
from crew.riff_from_mukhada import interpret_mukhada  # noqa: E402
from crew.riff_statements import APPROACH_SHARE, takeover_cycles  # noqa: E402
from crew.takeover import with_takeover  # noqa: E402
from tests.test_chord_floor import _riff, _sitar  # noqa: E402

_PLAN = PhrasePlan(seed=["R"], contour="wave", transformations=["repeat"], climax_and_sam="x")


def _head() -> LeadPhrase:
    """fusion_20261012_213455's realised head: R | g m PP | g(held) m PP | d n PP m | P g R SS."""
    spec = [("R", 1, "da"), ("g", 1, "da"), ("m", 1, "ra"), ("P", 1, "dir"), ("g", 2, "da"),
            ("m", 1, "ra"), ("P", 1, "dir"), ("d", 1, "da"), ("n", 1, "ra"), ("P", 1, "dir"),
            ("m", 1, "da"), ("P", 1, "dar"), ("g", 1, "da"), ("R", 1, "ra"), ("S", 1, "dir")]
    return LeadPhrase(phrase_plan=_PLAN,
                      notes=[LeadNote(swara=sw, dur=d, bol=b) for sw, d, b in spec])


def _arr(*, with_head: bool = True):
    def sec(role: str, layers: list[str], fg: str, kind=SectionKind.MELODY) -> Section:
        return Section(kind=kind, bars=2, layers=layers, foreground=fg, riff_slot="main",
                       form_role=role)
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=120, motif=["g", "m", "R", "S"],
        sections=[sec("mukhada", ["lead", "rhythm", "drums", "drone"], "lead"),
                  sec("takeover", ["rhythm", "drums", "drone"], "rhythm", SectionKind.RIFF),
                  sec("mukhada", ["lead", "rhythm", "drums", "drone"], "lead")])
    arr = build_arrangement(draft, CompositionBrief(sa=62))
    return arr.model_copy(update={"seed_hook": _head()}) if with_head else arr


def _interpret(arr):
    return interpret_mukhada(_head(), raga="darbari", cycle_beats=16.0,
                             accents=accent_beats(arr), register=arr.registers["rhythm"])


def test_the_heads_landings_are_low_chords_and_its_movement_single_notes():
    arr = _arr()
    pattern = _interpret(arr)
    t, chords, singles = 0.0, [], []
    for n in pattern.notes:
        (singles if n.single else chords).append((t, n.swara))
        t += n.dur
    assert (0.0, "R") in chords and (4.0, "g") in chords        # the sam and the held tali Ga
    assert [sw for _, sw in singles][:3] == ["g", "m", "P"]       # its melody, in order
    assert all(not n.chord for n in pattern.notes if n.single)    # never voiced as a chord
    assert all(n.chord for n in pattern.notes if not n.single and not n.rest)


def test_the_head_keeps_its_rhythm_on_guitar():
    arr = _arr()
    t, onsets = 0.0, set()
    for n in _interpret(arr).notes:
        onsets.add(round(t, 3))
        t += n.dur
    assert t == 16.0
    assert {0.0, 1.0, 2.0, 3.0, 3.5, 4.0} <= onsets               # its strokes, its dir doubling


def test_the_second_cycle_develops_the_first_into_a_heavy_cadence():
    arr = _arr()
    first, second = takeover_cycles(list(_interpret(arr).notes), 2, raga="darbari",
                                    accents=accent_beats(arr), cycle_beats=16.0)
    assert sum(n.dur for n in second) == 16.0
    assert len(second) > len(first)                               # the right hand doubles
    t, approach = 0.0, []
    for n in second:
        if t >= 16.0 * (1 - APPROACH_SHARE) - 1e-6 and not n.rest:
            approach.append(n)
        t += n.dur
    assert approach and all(not n.single and n.chord for n in approach)   # the cadence is heavy


def test_the_band_plays_the_arranged_head_in_a_takeover_whatever_the_guitar_wrote():
    arr = _arr()
    out = with_takeover(_riff(48), arr)
    takeover = [n for n in out.notes if 32 <= n.start < 64]
    assert takeover and takeover[0].swara == "R"                  # the head's sam note, not the riff
    assert {n.swara for n in out.notes if n.start < 32} == {n.swara for n in _riff(48).notes
                                                             if n.start < 32}
    layers = band_layers(arr, _sitar(end=96.0), _riff(48))
    rhythm = next(ly for ly in layers if ly.role == "rhythm")
    assert any(n.start >= 32 and n.start < 64 and n.swara == "R" for n in rhythm.notes)


def test_without_a_realised_head_the_section_keeps_its_riff():
    arr = _arr(with_head=False)
    riff = _riff(48)
    assert with_takeover(riff, arr) == riff


def test_takeover_is_a_gat_role_the_composer_may_name():
    def draft(form: str) -> ArrangementDraft:
        return ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=120,
                                motif=["g", "m", "R", "S"], form=form,
                                sections=[Section(kind=SectionKind.RIFF, bars=2,
                                                  layers=["rhythm", "drums"], foreground="rhythm",
                                                  riff_slot="main", form_role="takeover")])
    assert _roleless_error(draft("gat"), FULL_FORM) is None
    assert "takeover" in _gat_role_error(draft("song"), FULL_FORM)   # it plays the GAT's head


def test_the_takeovers_chords_stay_inside_the_raga():
    from raga import RAGAS
    allowed = set(RAGAS["darbari"]["allowed"])
    for n in _interpret(_arr()).notes:
        assert n.rest or ({n.swara, *(n.chord or [])} <= allowed)


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
