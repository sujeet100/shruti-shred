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
    CanvasMove,
    CompositionBrief,
    EventType,
    LeadNote,
    LeadPhrase,
    PhrasePlan,
    RiffNote,
    RiffPattern,
    Section,
    SectionCanvas,
    SectionKind,
    build_arrangement,
)
from crew.generators import VOICES, section_spans  # noqa: E402
from crew.riff import (  # noqa: E402
    RiffMemo,
    _RiffContext,
    _accent_beats,
    _render_canvas_for_riff,
    _render_previous,
    _riff_guardrail,
    generate_riff,
    place_riff,
    rhythm_layer_from,
    slot_for,
    studio_riff_fn,
)


def _arr(*section_layers: tuple[str, ...], tala: str = "teentaal",
         slots: list | None = None) -> Arrangement:
    """A real Malkauns chart with one section per arg (teentaal -> 16-beat cycles).

    `slots[i]` sets section i's `riff_slot` (None -> default, which is the kind)."""
    sections = []
    for i, layers in enumerate(section_layers):
        slot = slots[i] if slots and i < len(slots) else None
        sections.append(Section(kind=SectionKind.RIFF, bars=1, layers=list(layers),
                                foreground="rhythm" if "rhythm" in layers else layers[0],
                                riff_slot=slot))
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala=tala, bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _pattern(*swaras: str, dur: float = 0.5) -> RiffPattern:
    return RiffPattern(notes=[RiffNote(swara=s, dur=dur) for s in swaras])


def _fake(patterns: list[RiffPattern]):
    calls: list = []
    seen_memory: list = []
    it = iter(patterns)

    def fn(span, arr, memory):
        calls.append(span)
        seen_memory.append(memory)
        return next(it)

    fn.seen_memory = seen_memory
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
    # two rhythm sections with distinct slots -> two riffs; the lead-only section is skipped
    arr = _arr(("rhythm", "drone"), ("lead", "drone"), ("rhythm", "drone"),
               slots=["main", None, "chorus"])
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


# --- the riff library: one riff per slot, reused where the slot recurs ----------

def test_generate_riff_threads_the_slot_library_as_memory():
    # three DISTINCT slots -> the library (other slots realized so far) accrues as memory
    arr = _arr(("rhythm", "drone"), ("rhythm", "drone"), ("rhythm", "drone"),
               slots=["main", "chorus", "breakdown"])
    first, second, third = _pattern("S", "S"), _pattern("g", "g"), _pattern("m", "m")
    fn, _ = _fake([first, second, third])
    generate_riff(arr, gen_fn=fn)
    assert fn.seen_memory[0] == []
    assert [m.pattern for m in fn.seen_memory[1]] == [first]
    assert [m.pattern for m in fn.seen_memory[2]] == [first, second]
    assert all(isinstance(m, RiffMemo) for m in fn.seen_memory[2])


def test_same_slot_reuses_one_riff_and_reprises():
    # two sections share the "main" slot -> the riff is written ONCE and replayed
    arr = _arr(("rhythm", "drone"), ("rhythm", "drone"), slots=["main", "main"])
    fn, calls = _fake([_pattern("S", "g")])            # only one pattern is ever needed
    layer, events = generate_riff(arr, gen_fn=fn)
    assert len(calls) == 1                             # the main riff is written once...
    reprises = [e for e in events if e.data and e.data.get("reprise")]
    assert len(reprises) == 1 and "main" in reprises[0].text   # ...and reprised on its return
    assert len([e for e in events if e.type == EventType.PROPOSE]) == 1
    # both sections play the SAME riff: 2 sections x 2 notes/cycle x 1 bar = 4 notes over {S,g}
    assert len(layer.notes) == 4 and {n.swara for n in layer.notes} == {"S", "g"}


def test_default_slot_is_the_kind_so_same_kind_sections_reprise():
    arr = _arr(("rhythm", "drone"), ("rhythm", "drone"))   # both RIFF, no explicit slot
    fn, calls = _fake([_pattern("S")])
    _, events = generate_riff(arr, gen_fn=fn)
    assert len(calls) == 1                                  # same kind -> same slot -> one riff
    assert any(e.data and e.data.get("reprise") for e in events)


def test_distinct_slots_get_distinct_riffs():
    arr = _arr(("rhythm", "drone"), ("rhythm", "drone"), slots=["main", "breakdown"])
    fn, calls = _fake([_pattern("S", "S"), _pattern("m", "m")])
    layer, events = generate_riff(arr, gen_fn=fn)
    assert len(calls) == 2
    proposes = [e for e in events if e.type == EventType.PROPOSE]
    assert {e.data["slot"] for e in proposes} == {"main", "breakdown"}
    assert {n.swara for n in layer.notes} == {"S", "m"}


def test_render_previous_shows_prior_riffs_with_chords():
    memory = [RiffMemo("riff", RiffPattern(notes=[RiffNote(swara="S", dur=1.0, chord=["S"]),
                                                  RiffNote(swara="g", oct=-1, dur=1.0)]))]
    text = _render_previous(memory)
    assert "riff: S+S" in text and "g(-1)" in text


def test_render_previous_is_explicit_when_empty():
    assert "FIRST" in _render_previous([])


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


# --- rhythm_layer_from / slot_for: assemble from already-generated riffs --------

def test_rhythm_layer_from_places_each_cycle_by_index():
    arr = _arr(("rhythm", "drone"), ("rhythm", "drone"))
    layer = rhythm_layer_from({0: _pattern("S", "S", "S", "S"),
                               1: _pattern("g", "g", "g", "g")}, arr)
    assert layer is not None and layer.role == "rhythm"
    assert any(n.start >= 16.0 for n in layer.notes)             # section 1 placed at/after 16


def test_rhythm_layer_from_skips_missing_and_returns_none_when_empty():
    arr = _arr(("rhythm", "drone"))
    assert rhythm_layer_from({}, arr) is None


def test_slot_for_prefers_riff_slot_then_falls_back_to_kind():
    explicit = Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm"],
                       foreground="rhythm", riff_slot="main")
    assert slot_for(explicit) == "main"
    default = Section(kind=SectionKind.BREAKDOWN, bars=1, layers=["rhythm"], foreground="rhythm")
    assert slot_for(default) == "breakdown"


# --- canvas awareness: the riff LISTENS to the shared canvas -------------------

def _lead_on_canvas(*swaras: str) -> LeadPhrase:
    return LeadPhrase(
        phrase_plan=PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"],
                               climax_and_sam="lands on Sa"),
        notes=[LeadNote(swara=s, dur=1.0) for s in swaras])


def _canvas_for_riff(lead=None, riff=None) -> SectionCanvas:
    return SectionCanvas(index=0, kind=SectionKind.TAAN, start=0.0, end=16.0,
                         leader="lead", follower="rhythm", lead=lead, riff=riff)


def test_render_canvas_for_riff_opens_without_a_canvas_or_when_proposing():
    assert "OPEN" in _render_canvas_for_riff(None, CanvasMove.PROPOSE)


def test_render_canvas_for_riff_respond_shows_the_lead_and_asks_to_lock():
    canvas = _canvas_for_riff(lead=_lead_on_canvas("g", "m", "d"))
    text = _render_canvas_for_riff(canvas, CanvasMove.RESPOND)
    assert "the Lead is playing" in text and "LOCK" in text
    assert "g" in text


def test_render_canvas_for_riff_refine_shows_its_own_riff():
    canvas = _canvas_for_riff(lead=_lead_on_canvas("g"), riff=_pattern("S", "S"))
    text = _render_canvas_for_riff(canvas, CanvasMove.REFINE)
    assert "your current riff" in text and "REFINE" in text


def test_riff_inputs_for_carries_the_move_and_the_canvas():
    arr = _arr(("rhythm", "lead", "drone"))
    inputs = _RiffContext(arr).inputs_for(
        section_spans(arr)[0], [], canvas=_canvas_for_riff(lead=_lead_on_canvas("g", "m")),
        move=CanvasMove.RESPOND)
    assert inputs["move"] == "respond" and "the Lead is playing" in inputs["canvas"]


def test_riff_inputs_for_defaults_to_solo_without_a_canvas():
    arr = _arr(("rhythm", "drone"))
    inputs = _RiffContext(arr).inputs_for(section_spans(arr)[0], [])
    assert inputs["move"] == "propose" and "OPEN" in inputs["canvas"]


def test_studio_riff_fn_builds_a_callable_without_an_llm():
    arr = _arr(("rhythm", "lead", "drone"))
    assert callable(studio_riff_fn(arr))


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
