"""
Tests for the ORCHESTRA generator (crew/orchestra.py) — all PURE (no LLM, no cost).

What must hold: the capability GATE (`uses_orchestra`) fires only on a chart that lists the
`orchestra` layer; the expander turns a whole-chart intent into one Layer per SOUNDING family,
every pitch legal in the raga BY CONSTRUCTION (voicings built up the raga's own ladder, a
descent-only swara re-seated), notes seated in the orchestra register and inside each section
window; the countermelody is placed and answers on the strings; the grammar guardrail catches
an out-of-raga swara or a wrong-side countermelody entry; the generator loop runs with an
injected fake (no LLM) and RE-ROLLS an illegal score fed the exact violation; and band assembly
carries the orchestra while staying backward compatible (default empty).

Runs as a script (`uv run python tests/test_orchestra.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from pydantic import ValidationError  # noqa: E402

from crew.band import band_layers  # noqa: E402
from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    LeadNote,
    OrchestraScore,
    Section,
    SectionKind,
    SectionOrchestra,
    build_arrangement,
)
from crew.generators import assemble_composition, drone_layer, section_spans  # noqa: E402
from crew.orchestra import (  # noqa: E402
    _orchestra_grammar_error,
    generate_orchestra,
    orchestra_layers_from,
    uses_orchestra,
)
from raga import RAGAS, validate_composition  # noqa: E402


def _arr(sections, raga="kirwani", subgenre="symphonic", tala="keherwa", motif=("S", "R", "g", "m", "P")):
    draft = ArrangementDraft(raga=raga, subgenre=subgenre, tala=tala, bpm=120,
                             motif=list(motif), sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="epic"))


def _orch_sec(kind=SectionKind.RIFF, bars=2, extra=("rhythm", "drums"), foreground="rhythm",
              form_role="mukhada"):
    layers = ["orchestra", "drone", *extra]
    return Section(kind=kind, bars=bars, layers=layers, foreground=foreground, form_role=form_role)


def _full_score(indices=(0,)):
    """A score exercising every family + a legal Kirwani countermelody (S R g m P d N)."""
    return OrchestraScore(sections=[
        SectionOrchestra(section_index=i, strings="pad", string_swaras=["S", "g", "P"],
                         brass="stabs", brass_swaras=["S", "P"], choir="swell",
                         choir_swaras=["S", "P"], timpani=True, dynamic="ff",
                         countermelody=[LeadNote(swara="P", oct=0, dur=1.0),
                                        LeadNote(swara="d", oct=0, dur=1.0),
                                        LeadNote(swara="P", oct=0, dur=1.0)])
        for i in indices])


# --- the contract -----------------------------------------------------------------

def _raises(exc, fn):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"expected {exc.__name__}")


def test_intent_rejects_unknown_swara():
    _raises(ValidationError, lambda: SectionOrchestra(section_index=0, string_swaras=["Z"]))
    _raises(ValidationError, lambda: SectionOrchestra(section_index=0, choir_swaras=["Q"]))


def test_intent_defaults_are_sane():
    s = SectionOrchestra(section_index=1)
    assert s.strings == "pad" and s.brass == "silent" and s.choir == "silent"
    assert s.dynamic == "mf" and s.timpani is False and s.countermelody == []


# --- the capability gate ----------------------------------------------------------

def test_uses_orchestra_gates_on_the_layer():
    with_orch = _arr([_orch_sec()])
    without = _arr([Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                            foreground="rhythm", form_role="mukhada")])
    assert uses_orchestra(with_orch) is True
    assert uses_orchestra(without) is False


# --- the expander -----------------------------------------------------------------

def test_a_layer_per_sounding_family():
    arr = _arr([_orch_sec()])
    layers = orchestra_layers_from(arr, _full_score())
    roles = {la.role for la in layers}
    assert roles == {"orch_strings", "orch_brass", "orch_choir", "orch_timpani"}


def test_silent_families_produce_no_layer():
    arr = _arr([_orch_sec()])
    score = OrchestraScore(sections=[
        SectionOrchestra(section_index=0, strings="pad", brass="silent", choir="silent",
                         timpani=False)])
    roles = {la.role for la in orchestra_layers_from(arr, score)}
    assert roles == {"orch_strings"}   # only the pad sounds


def test_empty_score_yields_no_layers():
    arr = _arr([_orch_sec()])
    assert orchestra_layers_from(arr, OrchestraScore()) == []


def test_intent_for_a_non_orchestra_section_is_ignored():
    # section 0 uses the orchestra; section 1 does not — an intent for 1 must be dropped.
    arr = _arr([_orch_sec(),
                Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                        foreground="rhythm", form_role="mukhada")])
    score = OrchestraScore(sections=[SectionOrchestra(section_index=1, strings="pad")])
    assert orchestra_layers_from(arr, score) == []


def test_notes_stay_in_their_section_window():
    arr = _arr([_orch_sec(bars=2)])
    span = section_spans(arr)[0]
    for la in orchestra_layers_from(arr, _full_score()):
        for n in la.notes:
            assert span.start - 1e-6 <= n.start < span.end + 1e-6
            assert n.start + n.dur <= span.end + 1e-6


def test_countermelody_lands_on_the_strings_layer():
    arr = _arr([_orch_sec()])
    strings = next(la for la in orchestra_layers_from(arr, _full_score())
                   if la.role == "orch_strings")
    swaras = {n.swara for n in strings.notes}
    assert {"P", "d"} <= swaras   # the countermelody's P and d weave through the pad


# --- legality by construction -----------------------------------------------------

def _legal(arr, layers):
    comp = assemble_composition(arr, [drone_layer(arr), *layers])
    return validate_composition(comp.model_dump(exclude_none=True))


def test_orchestra_layers_are_raga_legal_kirwani():
    arr = _arr([_orch_sec()])
    assert _legal(arr, orchestra_layers_from(arr, _full_score())) == []


def test_defaults_are_legal_in_every_raga():
    # empty swara lists -> code default voicings; must be legal in EVERY raga.
    for raga in RAGAS:
        arr = _arr([_orch_sec()], raga=raga, motif=(RAGAS[raga]["allowed"][0],))
        score = OrchestraScore(sections=[
            SectionOrchestra(section_index=0, strings="pad", brass="sustain", choir="sustained",
                             timpani=True)])
        assert _legal(arr, orchestra_layers_from(arr, score)) == [], raga


def test_descent_only_swara_is_reseated_not_sustained():
    # Bageshree's P is descent-only; a pad asked to hold P must re-seat it to a legal,
    # ascendable tone rather than sustain the one-directional swara.
    arr = _arr([_orch_sec()], raga="bageshree", motif=("S", "g", "m"))
    score = OrchestraScore(sections=[
        SectionOrchestra(section_index=0, strings="pad", string_swaras=["S", "P"])])
    layers = orchestra_layers_from(arr, score)
    assert _legal(arr, layers) == []
    # P (descent-only) was lifted off the sustained pad — no held P in the strings.
    strings = next(la for la in layers if la.role == "orch_strings")
    assert all(n.swara != "P" for n in strings.notes)


# --- the grammar guardrail --------------------------------------------------------

def test_grammar_error_catches_an_illegal_swara():
    # 'R' is not in Malkauns (S g m d n) — a string pad asked to hold it must fail.
    illegal = OrchestraScore(sections=[SectionOrchestra(section_index=0, string_swaras=["S", "R"])])
    err = _orchestra_grammar_error(illegal, "malkauns")
    assert err is not None and "R" in err
    assert _orchestra_grammar_error(_full_score(), "kirwani") is None


def test_grammar_error_catches_a_wrong_side_countermelody_entry():
    # Bageshree's P is descent-only; a countermelody ASCENDING m -> P enters it from below.
    score = OrchestraScore(sections=[
        SectionOrchestra(section_index=0, strings="silent",
                         countermelody=[LeadNote(swara="m", oct=0, dur=1.0),
                                        LeadNote(swara="P", oct=0, dur=1.0)])])
    err = _orchestra_grammar_error(score, "bageshree")
    assert err is not None and "countermelody" in err


# --- the generator loop (LLM injected) --------------------------------------------

def test_generate_orchestra_with_injected_fn():
    arr = _arr([_orch_sec()])
    calls: list[str | None] = []

    def fake(a, lead_layers, rhythm, *, feedback=None):
        calls.append(feedback)
        return _full_score()

    layers, events = generate_orchestra(arr, gen_fn=fake)
    assert {la.role for la in layers} == {"orch_strings", "orch_brass", "orch_choir", "orch_timpani"}
    assert len(events) == 1 and events[0].agent == "Orchestra"
    assert calls == [None]   # legal first time -> no re-roll


def test_generate_orchestra_rerolls_an_illegal_score_with_feedback():
    arr = _arr([_orch_sec()])
    seen: list[str | None] = []
    illegal = OrchestraScore(sections=[SectionOrchestra(section_index=0, string_swaras=["r"])])  # r illegal in Kirwani

    def fake(a, lead_layers, rhythm, *, feedback=None):
        seen.append(feedback)
        return illegal if feedback is None else _full_score()

    layers, _ = generate_orchestra(arr, gen_fn=fake)
    assert len(seen) == 2 and seen[0] is None and seen[1] is not None  # re-rolled, fed the violation
    assert _legal(arr, layers) == []                                   # the clean re-roll won


# --- band assembly ----------------------------------------------------------------

def test_band_layers_carries_the_orchestra_and_is_backward_compatible():
    arr = _arr([_orch_sec()])
    orchestra_layers = orchestra_layers_from(arr, _full_score())
    with_orch = band_layers(arr, [], None, orchestra_layers)
    without = band_layers(arr, [], None)
    orch_roles = {"orch_strings", "orch_brass", "orch_choir", "orch_timpani"}
    assert orch_roles <= {la.role for la in with_orch}
    assert not (orch_roles & {la.role for la in without})   # default empty -> no orchestra


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
