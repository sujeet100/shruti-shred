"""
Tests for the HARMONY step 1 (2026-10-12 harmony brief): chord shapes built inside the raga, the
composers' chord timeline and its behaviours realised by the chord floor, conservative shapes
under a swaying sitar note, and the guardrail on a timeline. Pure, no LLM.

Runs as a script (`uv run python tests/test_voicings.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.chord_floor import floor_spans, on_floor  # noqa: E402
from crew.composers import _harmony_error  # noqa: E402
from crew.contracts import ArrangementDraft, HarmonyPlan, Note  # noqa: E402
from crew.voicings import voice  # noqa: E402
from tests.test_chord_floor import _arr, _riff, _sec, _sitar  # noqa: E402

_HEAD = [{"root": "S", "matras": 8}, {"root": "d", "matras": 4, "voicing": "triad"},
         {"root": "n", "matras": 2}, {"root": "P", "matras": 2, "voicing": "sus4"}]


def _timed(behaviour: str | None = "slow", chords: list[dict] = _HEAD, role: str = "mukhada"):
    sec = _sec(role, bars=1)
    sec = sec.model_copy(update={"harmony": HarmonyPlan(behaviour=behaviour, chords=chords)})
    return _arr(sec)


def _chords(arr, sitar=None) -> list[tuple[float, str, str]]:
    return [(s.start, s.root, s.voicing) for s in floor_spans(arr, sitar or _sitar(end=16.0))]


# --- shapes inside the raga ---------------------------------------------------------------------

def test_a_shape_with_a_tone_outside_the_raga_falls_back():
    assert voice("R", "power", "darbari") == ("octave", ["R"])     # E5 would hold B natural
    assert voice("R", "fourths", "darbari") == ("fourths", ["P", "R"])   # Re's suspended shape
    assert voice("d", "sus4", "darbari")[0] == "power"             # Eb is not in Darbari
    assert voice("S", "triad", "darbari") == ("triad", ["g", "P"])  # the raga's own third


def test_a_conservative_shape_is_kept_plain():
    assert voice("S", "triad", "darbari", conservative=True)[0] == "power"
    assert voice("S", "fifth", "darbari", conservative=True)[0] == "fifth"


# --- the timeline and its behaviours ------------------------------------------------------------

def test_the_composers_timeline_plays_with_its_shapes():
    assert _chords(_timed()) == [(0.0, "S", "power"), (8.0, "d", "triad"),
                                 (12.0, "n", "power"), (14.0, "P", "sus4")]


def test_a_pedal_keeps_every_chord_on_home():
    assert {root for _, root, _ in _chords(_timed("pedal"))} == {"S"}


def test_tension_hangs_the_departures_and_a_breakdown_keeps_them_plain():
    tense = _chords(_timed("tension", [{"root": "S", "matras": 8}, {"root": "n", "matras": 8}]))
    assert tense[1][1:] == ("n", "sus4")
    plain = _chords(_timed("breakdown"))
    assert {shape for *_, shape in plain} <= {"power", "octave", "fifth"}


def test_a_phrase_responsive_change_moves_to_the_sitars_arrival():
    sitar = _sitar(Note(swara="S", oct=0, start=0.0, dur=7.0),
                   Note(swara="g", oct=0, start=9.0, dur=4.0, andolan=True),
                   Note(swara="R", oct=0, start=13.0, dur=3.0))
    spans = _chords(_timed("phrase", [{"root": "S", "matras": 8}, {"root": "n", "matras": 8}]),
                    sitar)
    assert spans[1][0] == 9.0                                     # 8 -> the held Ga at 9


def test_a_chord_under_a_swaying_sitar_note_is_plain():
    sitar = _sitar(Note(swara="g", oct=0, start=8.0, dur=4.0, andolan=True))
    spans = _chords(_timed(), sitar)
    assert spans[1][1:] == ("d", "power")                          # the triad gave way


def test_a_timeline_that_does_not_fill_the_avartan_falls_back_to_the_default():
    spans = _chords(_timed("slow", [{"root": "S", "matras": 8}, {"root": "d", "matras": 4}]))
    assert spans[0][1:] == ("S", "power") and all(sh == "power" for *_, sh in spans)


def test_the_strokes_take_the_timelines_shapes():
    arr = _timed()
    out = on_floor(_riff(16), _sitar(end=16.0), arr)
    triad = [n for n in out.notes if 8 <= n.start < 12]
    assert {n.swara for n in triad} == {"d"} and all(n.chord == ["S", "g"] for n in triad)   # Bb D F


# --- the guardrail ------------------------------------------------------------------------------

def _draft(chords: list[dict]) -> ArrangementDraft:
    sec = _sec("mukhada", bars=1).model_copy(
        update={"harmony": HarmonyPlan(behaviour="slow", chords=chords)})
    return ArrangementDraft(raga="darbari", subgenre="progressive", tala="teentaal", bpm=120,
                            motif=["g", "m", "R", "S"], sections=[sec])


def test_the_guardrail_wants_raga_roots_that_fill_one_avartan():
    assert _harmony_error(_draft(_HEAD)) is None
    assert "add up to 16" in _harmony_error(_draft(_HEAD[:3]))
    bad = [{"root": "G", "matras": 16}]                            # shuddha Ga: not Darbari
    assert "illegal in raga darbari" in _harmony_error(_draft(bad))


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
