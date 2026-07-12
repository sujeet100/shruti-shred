"""
Tests for the Riff generator — its DETERMINISTIC parts, all pure (no key, no cost).

The riff's job is to LOCK to the tala: `place_riff` takes one cycle and repeats it
across the section's bars (every bar re-landing on the sam) and punches the notes
that fall on the accent grid, so the riff interlocks with the kick. That, plus the
fan-out over rhythm-active sections and the legality guardrail, is proven here
without the LLM. The real riff is exercised live via `uv run python -m crew.riff`.

Runs as a script (`uv run python tests/test_riff.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    EventType,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import VOICES  # noqa: E402
from crew.riff import _accent_beats, _riff_guardrail, generate_riff, place_riff  # noqa: E402


def _arr(*section_layers: tuple[str, ...], tala: str = "teentaal") -> Arrangement:
    """A real Malkauns chart with one section per arg (teentaal -> 16-beat cycles)."""
    sections = [
        Section(kind=SectionKind.RIFF, bars=1, layers=list(layers),
                foreground="rhythm" if "rhythm" in layers else layers[0])
        for layers in section_layers
    ]
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala=tala, bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _pattern(*swaras: str, dur: float = 0.5) -> RiffPattern:
    return RiffPattern(notes=[RiffNote(swara=s, dur=dur) for s in swaras])


def _fake(patterns: list[RiffPattern]):
    calls: list = []
    it = iter(patterns)

    def fn(span, arr):
        calls.append(span)
        return next(it)

    return fn, calls


class _FakeOutput:
    def __init__(self, pattern: RiffPattern) -> None:
        self.pydantic = pattern
        self.raw = pattern.model_dump_json()


# --- place_riff: repeat across bars, lock to the accent grid -------------------

def test_place_riff_repeats_one_cycle_across_bars():
    # one 4-beat cycle of 8th notes (8 notes), repeated over 2 bars of a 4-beat cycle
    notes = [RiffNote(swara="S", dur=0.5) for _ in range(8)]
    placed = place_riff(notes, start=0.0, bars=2, cycle_beats=4.0, register=-3,
                        accent_beats=set())
    assert len(placed) == 16                       # 8 notes x 2 bars
    assert placed[0].start == 0.0
    assert placed[8].start == 4.0                  # second bar re-lands on the sam
    assert all(n.oct == -3 for n in placed)        # seated in the rhythm register


def test_place_riff_offsets_by_section_start():
    placed = place_riff([RiffNote(swara="S", dur=1.0)], start=16.0, bars=1,
                        cycle_beats=4.0, register=-3, accent_beats=set())
    assert placed[0].start == 16.0


def test_place_riff_punches_accented_matras():
    # note onsets at beats 0,1,2,3; accent the sam (0) and a tali (2)
    notes = [RiffNote(swara="S", dur=1.0, vel=100) for _ in range(4)]
    placed = place_riff(notes, start=0.0, bars=1, cycle_beats=4.0, register=-3,
                        accent_beats={0.0, 2.0})
    vels = {n.start: n.vel for n in placed}
    assert vels[0.0] > 100 and vels[2.0] > 100     # accented onsets punched up
    assert vels[1.0] == 100 and vels[3.0] == 100   # off-accent notes untouched


def test_sequence_cycle_truncates_an_overrunning_pattern():
    # three 2-beat notes = 6 beats crammed into a 4-beat cycle -> last note clipped, third dropped
    notes = [RiffNote(swara="S", dur=2.0), RiffNote(swara="g", dur=2.0), RiffNote(swara="m", dur=2.0)]
    placed = place_riff(notes, start=0.0, bars=1, cycle_beats=4.0, register=0, accent_beats=set())
    assert [n.start for n in placed] == [0.0, 2.0]
    assert placed[-1].dur == 2.0


def test_short_pattern_is_filled_to_the_cycle_for_a_seamless_loop():
    # a 3-beat pattern in a 4-beat cycle: the last note extends to the edge so there
    # is no silent gap at the downbeat where the loop repeats.
    notes = [RiffNote(swara="S", dur=1.0), RiffNote(swara="g", dur=1.0), RiffNote(swara="m", dur=1.0)]
    placed = place_riff(notes, start=0.0, bars=2, cycle_beats=4.0, register=0, accent_beats=set())
    first_cycle = [n for n in placed if n.start < 4.0]
    assert [n.start for n in first_cycle] == [0.0, 1.0, 2.0]
    assert first_cycle[-1].dur == 2.0                  # extended 1.0 -> 2.0 to fill the cycle
    assert first_cycle[-1].start + first_cycle[-1].dur == 4.0   # no gap before the loop
    assert placed[3].start == 4.0                      # the second bar re-lands on the sam


def test_accent_beats_are_the_sam_and_tali():
    beats = _accent_beats(_arr(("rhythm", "drone")))   # teentaal: sam beat 0, tali beats 4, 12
    assert beats == {0.0, 4.0, 12.0}


# --- generate_riff: fan out over the rhythm-active sections --------------------

def test_generate_riff_fills_only_rhythm_active_sections():
    arr = _arr(("rhythm", "drone"), ("lead", "drone"), ("rhythm", "drone"))
    fn, calls = _fake([_pattern("S", "S"), _pattern("g", "g")])
    layer, _events = generate_riff(arr, gen_fn=fn)
    assert len(calls) == 2                          # the lead-only section is skipped
    assert layer is not None and layer.role == "rhythm"


def test_generate_riff_returns_none_when_no_rhythm_sections():
    arr = _arr(("lead", "drone"))
    fn, calls = _fake([])
    layer, events = generate_riff(arr, gen_fn=fn)
    assert layer is None and calls == []
    assert any("no rhythm" in e.text.lower() for e in events)


def test_generate_riff_uses_the_rhythm_voice_and_register():
    arr = _arr(("rhythm", "drone"))
    fn, _ = _fake([_pattern("S")])
    layer, _ = generate_riff(arr, gen_fn=fn)
    assert (layer.instrument, layer.program, layer.channel) == (
        VOICES["rhythm"].instrument, VOICES["rhythm"].program, VOICES["rhythm"].channel)
    assert layer.notes[0].oct == arr.registers["rhythm"]


def test_generate_riff_emits_a_propose_event():
    arr = _arr(("rhythm", "drone"))
    fn, _ = _fake([_pattern("S", "g")])
    _, events = generate_riff(arr, gen_fn=fn)
    proposes = [e for e in events if e.type == EventType.PROPOSE]
    assert len(proposes) == 1 and proposes[0].agent == "Riff"


# --- chords + techniques: carried through placement, legality-checked ----------

def test_place_riff_carries_chord_and_technique_through():
    # a power-chord chug must survive the cycle-repeat + accent pass unchanged.
    notes = [RiffNote(swara="S", dur=1.0, chord=["S"], technique="palm_mute"),
             RiffNote(swara="g", dur=1.0, technique="slide")]
    placed = place_riff(notes, start=0.0, bars=2, cycle_beats=2.0, register=-3,
                        accent_beats={0.0})
    assert placed[0].chord == ["S"] and placed[0].technique == "palm_mute"
    assert placed[1].chord is None and placed[1].technique == "slide"
    # the accent boost still applies to the chorded sam note, chord intact
    assert placed[0].vel > notes[0].vel
    # and the second bar's repeat keeps the voicing too
    assert placed[2].chord == ["S"] and placed[2].technique == "palm_mute"


def test_guardrail_passes_a_legal_chord():
    pattern = RiffPattern(notes=[RiffNote(swara="S", dur=1.0, chord=["S", "m"])])
    ok, value = _riff_guardrail("malkauns")(_FakeOutput(pattern))
    assert ok is True and isinstance(value, RiffPattern)


def test_guardrail_rejects_an_illegal_chord_tone():
    # the root 'S' is legal but the chord tone 'P' is not in Malkauns -> rejected.
    pattern = RiffPattern(notes=[RiffNote(swara="S", dur=1.0, chord=["P"])])
    ok, msg = _riff_guardrail("malkauns")(_FakeOutput(pattern))
    assert ok is False and "illegal" in msg.lower() and "P" in msg


def test_riffnote_rejects_an_unknown_chord_swara():
    try:
        RiffNote(swara="S", dur=1.0, chord=["Q"])
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "chord" in str(e).lower()


# --- the legality guardrail ----------------------------------------------------

def test_guardrail_passes_a_legal_riff():
    ok, value = _riff_guardrail("malkauns")(_FakeOutput(_pattern("S", "g", "m", "S")))
    assert ok is True and isinstance(value, RiffPattern)


def test_guardrail_rejects_an_illegal_swara():
    # 'P' is absent from Malkauns -> the domain guardrail rejects it for a retry.
    ok, msg = _riff_guardrail("malkauns")(_FakeOutput(_pattern("S", "P")))
    assert ok is False and "illegal" in msg.lower() and "P" in msg


# --- the RiffNote contract -----------------------------------------------------

def test_riffnote_rejects_nonpositive_duration():
    try:
        RiffNote(swara="S", dur=0.0)
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "greater than 0" in str(e).lower()


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
