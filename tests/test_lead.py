"""
Tests for the Lead generator — its DETERMINISTIC parts, all pure (no key, no cost).

Two things are worth proving without the LLM: (1) `place_phrase` lays a phrase onto
a section window correctly — sequencing durations, seating notes in the lead's
register, and truncating at the window edge (the "code enforces" half of the
split); and (2) `generate_lead` fans out over the right sections, and the legality
guardrail catches an out-of-raga swara with a precise, retryable error. The real
LLM phrase is exercised live via `uv run python -m crew.lead`, not here.

Runs as a script (`uv run python tests/test_lead.py`) or under pytest.
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
    LeadNote,
    LeadPhrase,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import VOICES  # noqa: E402
from crew.lead import Voicing, _lead_guardrail, _voice_line, generate_lead, place_phrase  # noqa: E402


def _arr(*section_layers: tuple[str, ...], kind: SectionKind = SectionKind.ALAAP,
         raga: str = "malkauns") -> Arrangement:
    """A real chart (teentaal, 16-beat cycles) with one section per arg. Default kind
    is ALAAP, which voices as solo sitar -> a single lead layer."""
    sections = [
        Section(kind=kind, bars=1, layers=list(layers),
                foreground="lead" if "lead" in layers else layers[0])
        for layers in section_layers
    ]
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _phrase(*swaras: str, dur: float = 2.0) -> LeadPhrase:
    return LeadPhrase(notes=[LeadNote(swara=s, dur=dur) for s in swaras])


def _fake(phrases: list[LeadPhrase]):
    """A fake gen_fn that replays canned phrases and records the spans it saw."""
    calls: list = []
    it = iter(phrases)

    def fn(span, arr):
        calls.append(span)
        return next(it)

    return fn, calls


class _FakeOutput:
    """Stand-in for a CrewAI TaskOutput carrying an output_pydantic-parsed phrase."""
    def __init__(self, phrase: LeadPhrase) -> None:
        self.pydantic = phrase
        self.raw = phrase.model_dump_json()


# --- place_phrase: the "code enforces" half ------------------------------------

def test_place_phrase_sequences_and_seats_in_register():
    notes = [LeadNote(swara="S", oct=0, dur=2.0), LeadNote(swara="m", oct=1, dur=3.0)]
    placed = place_phrase(notes, start=4.0, end=100.0, register=-1)
    assert [(n.start, n.dur) for n in placed] == [(4.0, 2.0), (6.0, 3.0)]
    assert placed[0].oct == -1                    # register (-1) + local 0
    assert placed[1].oct == 0                     # register (-1) + local +1


def test_place_phrase_truncates_at_window_end():
    notes = [LeadNote(swara="S", dur=4.0), LeadNote(swara="m", dur=4.0),
             LeadNote(swara="g", dur=4.0)]
    placed = place_phrase(notes, start=0.0, end=6.0, register=0)
    assert len(placed) == 2                        # third note starts past the window
    assert placed[1].start == 4.0 and placed[1].dur == 2.0   # straddling note clipped


def test_place_phrase_carries_ornaments():
    placed = place_phrase([LeadNote(swara="g", dur=2.0, grace=["S"], meend="m")],
                          start=0.0, end=8.0, register=0)
    assert placed[0].grace == ["S"] and placed[0].meend == "m"


def test_place_phrase_keeps_string_meend_same_octave():
    # A bare-string meend needs no shift — the renderer glides to it in the note's
    # (already register-seated) octave.
    placed = place_phrase([LeadNote(swara="g", oct=0, dur=2.0, meend="m")],
                          start=0.0, end=8.0, register=-1)
    assert placed[0].meend == "m"


def test_place_phrase_shifts_cross_octave_meend_by_register():
    # A {"swara","oct"} meend carries a LOCAL octave; placement shifts it by the
    # register, exactly like the note's own octave, so the glide lands in the right
    # absolute octave. Here: note local 0 -> abs -1; meend local +1 -> abs 0.
    placed = place_phrase([LeadNote(swara="m", oct=0, dur=2.0, meend={"swara": "S", "oct": 1})],
                          start=0.0, end=8.0, register=-1)
    assert placed[0].oct == -1
    assert placed[0].meend == {"swara": "S", "oct": 0}


def test_leadnote_accepts_a_cross_octave_meend_dict():
    note = LeadNote(swara="m", dur=2.0, meend={"swara": "S", "oct": 1})
    assert note.meend == {"swara": "S", "oct": 1}


def test_leadnote_rejects_unknown_swara_in_a_meend_dict():
    try:
        LeadNote(swara="S", dur=1.0, meend={"swara": "Z", "oct": 1})
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "unknown meend" in str(e).lower()


# --- generate_lead: fan out over the lead-active sections ----------------------

def test_generate_lead_fills_only_lead_active_sections():
    arr = _arr(("lead", "drone"), ("rhythm", "drone"), ("lead", "drone"))  # ALAAP -> solo sitar
    fn, calls = _fake([_phrase("S", "m"), _phrase("g", "d")])
    layers, _events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2                         # the rhythm-only section is skipped
    assert len(layers) == 1 and layers[0].role == "lead"
    starts = [n.start for n in layers[0].notes]
    assert starts[0] == 0.0                        # first lead section starts at beat 0
    assert any(s >= 32.0 for s in starts)          # third section's window is 32..48


def test_generate_lead_returns_empty_when_no_lead_sections():
    arr = _arr(("rhythm", "drone"), ("drums", "rhythm"))
    fn, calls = _fake([])
    layers, events = generate_lead(arr, gen_fn=fn)
    assert layers == [] and calls == []
    assert any("no lead" in e.text.lower() for e in events)


def test_generate_lead_seats_notes_in_the_lead_register():
    arr = _arr(("lead", "drone"))
    fn, _ = _fake([_phrase("S")])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert layers[0].notes[0].oct == arr.registers["lead"]


def test_generate_lead_emits_a_propose_event_per_section():
    arr = _arr(("lead", "drone"), ("lead", "drone"))
    fn, _ = _fake([_phrase("S"), _phrase("m")])
    _, events = generate_lead(arr, gen_fn=fn)
    proposes = [e for e in events if e.type == EventType.PROPOSE]
    assert len(proposes) == 2 and all(e.agent == "Lead" for e in proposes)


# --- voicing: sitar and/or lead guitar per section kind ------------------------

def test_alaap_is_voiced_as_solo_sitar():
    arr = _arr(("lead", "drone"))                  # ALAAP -> SITAR
    fn, _ = _fake([_phrase("S", "m")])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 1
    v = VOICES["sitar"]
    assert (layers[0].instrument, layers[0].program, layers[0].channel) == (
        v.instrument, v.program, v.channel)


def test_solo_is_voiced_on_lead_guitar_only():
    arr = _arr(("lead", "drone"), kind=SectionKind.SOLO)   # SOLO -> GUITAR
    fn, _ = _fake([_phrase("S", "m")])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 1
    assert layers[0].instrument == VOICES["lead_guitar"].instrument


def test_melody_is_voiced_in_unison_on_two_layers():
    arr = _arr(("lead", "drone"), kind=SectionKind.MELODY)  # MELODY -> UNISON
    fn, _ = _fake([_phrase("S", "m")])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 2
    assert [[n.swara for n in x.notes] for x in layers] == [["S", "m"], ["S", "m"]]


def test_taan_is_voiced_as_a_harmonized_third_on_two_layers():
    arr = _arr(("lead", "drone"), kind=SectionKind.TAAN, raga="darbari")  # TAAN -> THIRD
    fn, _ = _fake([_phrase("S", "R", "g")])        # legal in darbari
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 2
    sitar = next(x for x in layers if x.instrument == VOICES["sitar"].instrument)
    guitar = next(x for x in layers if x.instrument == VOICES["lead_guitar"].instrument)
    assert [n.swara for n in sitar.notes] == ["S", "R", "g"]
    # a raga-diatonic third up in darbari (S R g m P d n): S->g, R->m, g->P
    assert [n.swara for n in guitar.notes] == ["g", "m", "P"]


def test_voice_line_octave_puts_the_guitar_an_octave_up():
    sitar, guitar = _voice_line([Note(swara="S", oct=0, start=0.0, dur=1.0)],
                                Voicing.OCTAVE, "malkauns")
    assert (sitar[0].swara, sitar[0].oct) == ("S", 0)
    assert (guitar[0].swara, guitar[0].oct) == ("S", 1)


def test_voice_line_third_wraps_the_octave_at_the_top_of_the_ladder():
    # darbari ladder S R g m P d n; n + a diatonic third wraps to R an octave up
    _, guitar = _voice_line([Note(swara="n", oct=0, start=0.0, dur=1.0)], Voicing.THIRD, "darbari")
    assert (guitar[0].swara, guitar[0].oct) == ("R", 1)


def test_harmony_strips_ornaments_but_the_melody_keeps_them():
    line = [Note(swara="S", oct=0, start=0.0, dur=1.0, grace=["g"], meend="m")]
    sitar, guitar = _voice_line(line, Voicing.THIRD, "malkauns")
    assert sitar[0].grace == ["g"] and sitar[0].meend == "m"    # melody keeps its ornaments
    assert guitar[0].grace is None and guitar[0].meend is None  # the harmony is clean


# --- the legality guardrail: the hard line -------------------------------------

def test_guardrail_passes_a_legal_phrase():
    ok, value = _lead_guardrail("malkauns")(_FakeOutput(_phrase("d", "n", "S", "m")))
    assert ok is True and isinstance(value, LeadPhrase)


def test_guardrail_rejects_illegal_swara_with_a_precise_error():
    # 'P' is a valid symbol but ABSENT from Malkauns, so the DOMAIN guardrail — not
    # the schema — rejects it, handing back the swara for a bounded retry.
    ok, msg = _lead_guardrail("malkauns")(_FakeOutput(_phrase("S", "P")))
    assert ok is False and "illegal" in msg.lower() and "P" in msg


def test_guardrail_checks_grace_and_meend_swaras_too():
    # An illegal swara hiding in a meend target must not slip past the guardrail.
    phrase = LeadPhrase(notes=[LeadNote(swara="S", dur=1.0, meend="P")])
    ok, msg = _lead_guardrail("malkauns")(_FakeOutput(phrase))
    assert ok is False and "P" in msg


def test_guardrail_reads_the_swara_out_of_a_cross_octave_meend():
    # The dict form must not blind the guardrail: an illegal cross-octave target
    # (P is absent from Malkauns) is still caught.
    phrase = LeadPhrase(notes=[LeadNote(swara="S", dur=1.0, meend={"swara": "P", "oct": 1})])
    ok, msg = _lead_guardrail("malkauns")(_FakeOutput(phrase))
    assert ok is False and "P" in msg


# --- the LeadNote contract: boundary shape checks ------------------------------

def test_leadnote_rejects_nonpositive_duration():
    try:
        LeadNote(swara="S", dur=0.0)
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "greater than 0" in str(e).lower()


def test_leadnote_rejects_unknown_swara():
    try:
        LeadNote(swara="Z", dur=1.0)
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "unknown swara" in str(e).lower()


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
