"""
Tests for PLAYABILITY — the fretboard model (src/fretboard.py) and the riff budgets built on it
(crew/riff_playability.py): reach, stretch, rapid jumps, sixteenth bursts and the open-string
anchor, each measured on the pitches the renderer will actually sound. No LLM.

Runs as a script (`uv run python tests/test_playability.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

import crew  # noqa: E402,F401  — puts src/ on the path
from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.riff_playability import playability_check, render_playability, verify_playable  # noqa: E402
from crew.riff_texture import verified_riff  # noqa: E402
from fretboard import easiest_path, fingerings, placements  # noqa: E402

_E = 64          # Sa = E: at register -2 the riff's Sa is the open low E (MIDI 40)
_D = 62


def _n(swara: str, dur: float = 0.5, oct: int = 0, **kw) -> RiffNote:
    return RiffNote(swara=swara, oct=oct, dur=dur, **kw)


def _cycle(*notes: RiffNote) -> RiffPattern:
    return RiffPattern(notes=list(notes))


def _verify(pattern: RiffPattern, sa: int = _E, register: int = -2) -> list[str]:
    return verify_playable(pattern, sa=sa, register=register,
                           cycle_beats=sum(n.dur for n in pattern.notes))


def _gallop_on_e() -> RiffPattern:
    """A plain Bhairav riff a player can hold: open-E chugs, a power chord, a short move."""
    return _cycle(_n("S", technique="palm_mute"), _n("S", technique="palm_mute"),
                  _n("S", technique="palm_mute"), _n("r"),
                  _n("S", 1.0, chord=["S", "P"]),
                  _n("S", technique="palm_mute"), _n("S", technique="palm_mute"),
                  _n("m"), _n("G"))


# --- the fretboard ------------------------------------------------------------------------

def test_reach_starts_at_the_open_low_e():
    assert placements(40) == [(0, 0)]
    assert placements(39) == []


def test_a_power_chord_has_a_comfortable_shape():
    assert fingerings((40, 47, 52))                 # E5 on the low strings


def test_a_shape_wider_than_a_hand_has_none():
    # E fret 1 and high E fret 6 with every string in between taken: a five-fret stretch
    assert fingerings((41, 45, 50, 55, 59, 70)) == []


def test_the_easiest_path_rides_open_strings():
    path = easiest_path([fingerings((40,)), fingerings((45,)), fingerings((40,))])
    assert path is not None and all(f.position is None for f in path)


# --- the riff budgets -----------------------------------------------------------------------

def test_a_plain_e_anchored_riff_passes():
    assert _verify(_gallop_on_e()) == []


def test_too_many_sixteenths_is_flagged():
    busy = _cycle(*[_n("S", 0.25) for _ in range(8)], _n("S", 1.0))
    found = " ".join(_verify(busy))
    assert "faster than eighths" in found and "run of 8 sixteenths" in found


def test_a_short_burst_of_sixteenths_is_fine():
    riff = _cycle(*[_n("S", technique="palm_mute") for _ in range(6)],
                  *[_n("S", 0.25) for _ in range(2)], _n("S", 1.0, chord=["S", "P"]))
    assert _verify(riff) == []


def test_a_rapid_position_jump_is_flagged():
    # komal re on the low E's first fret, then Ni two octaves up (high E fret 11) half a beat later
    riff = _cycle(*[_n("S", technique="palm_mute") for _ in range(4)], _n("r"), _n("N", oct=2))
    found = " ".join(_verify(riff))
    assert "rapid position jump" in found


def test_the_riff_must_anchor_on_the_open_low_e():
    on_pa = _cycle(*[_n("P", technique="palm_mute") for _ in range(6)], _n("S"), _n("m"))
    assert any("open low E" in v for v in _verify(on_pa))


def test_the_anchor_rule_only_applies_where_sa_is_the_open_string():
    on_pa = _cycle(*[_n("P", technique="palm_mute") for _ in range(6)], _n("S"), _n("m"))
    assert not any("open low E" in v for v in _verify(on_pa, sa=_D, register=-1))


def test_a_note_under_the_open_low_e_is_out_of_reach():
    # in D, register -2 puts Sa at D2 (38) — two semitones under the guitar
    assert any("outside the guitar's range" in v for v in _verify(_gallop_on_e(), sa=_D))


# --- the chart switches it on ---------------------------------------------------------------

def _arr(playable: bool, sa: int = _E):
    draft = ArrangementDraft(
        raga="bhairav", subgenre="heavy", tala="teentaal", bpm=128, motif=["S", "r", "G"],
        sections=[Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                          foreground="rhythm", riff_slot="main", form_role="mukhada")])
    return build_arrangement(draft, CompositionBrief(sa=sa, playable_rhythm=playable))


def test_the_check_exists_only_when_asked_for():
    assert playability_check(_arr(False)) is None
    assert playability_check(_arr(True)) is not None
    assert "no playability constraint" in render_playability(_arr(False))
    assert "open low E" in render_playability(_arr(True))


def test_a_playable_chart_lifts_a_low_key_riff_onto_the_guitar():
    assert _arr(True, sa=_E).registers["rhythm"] == -2        # E2: the open low string
    assert _arr(True, sa=_D).registers["rhythm"] == -1        # D3, not the unplayable D2
    assert _arr(False, sa=_D).registers["rhythm"] == -2       # untouched when not asked


def test_a_playability_miss_drives_the_bounded_reroll():
    takes = [_cycle(*[_n("S", 0.25) for _ in range(12)], _n("S", 1.0)), _gallop_on_e()]
    feedback: list = []

    def gen(fb):
        feedback.append(fb)
        return takes[min(len(feedback) - 1, len(takes) - 1)]

    arr = _arr(True)
    verified_riff(gen, arr.sections[0], arr.beats_per_bar, extra_check=playability_check(arr))
    assert feedback[0] is None
    assert any("sixteenth" in v for v in feedback[1])        # the re-roll was told exactly why



def test_the_open_string_anchor_never_pulls_a_weak_sa_raga_back_onto_sa():
    # Marwa in E: Sa IS the open low string, but Marwa's Sa is deliberately weak (its riff
    # homes on Dha), so the anchor rule is off — no instruction, and no violation for a riff
    # that lives on Dha
    draft = ArrangementDraft(
        raga="marwa", subgenre="heavy", tala="teentaal", bpm=128, motif=["D", "N", "r"],
        sections=[Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                          foreground="rhythm", riff_slot="main", form_role="mukhada")])
    arr = build_arrangement(draft, CompositionBrief(sa=_E, playable_rhythm=True))
    assert "open low E" not in render_playability(arr)
    on_dha = RiffPattern(notes=[RiffNote(swara="D", dur=0.5) for _ in range(32)])
    assert not [v for v in playability_check(arr)(on_dha) if "open low E" in v]

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
