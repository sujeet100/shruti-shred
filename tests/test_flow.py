"""
Tests for the Flow — the orchestration and the BOUNDED REVISE LOOP, no LLM (free).

`ComposeFlow` takes an injected `Stages` bundle, so the whole propose->critique->
arbitrate->(revise)->render loop is kicked off here with fakes: does an ACCEPT ruling
skip revise and render once; does a revise-then-accept run exactly one revise; and — the
live-safety property — does an always-revise Conductor get capped at MAX_ROUNDS and
still terminate (rendering the last version)? Plus the pure surgical-revise helper. The
real end-to-end run is exercised live via `uv run python -m crew.flow`, not here.

Runs as a script (`uv run python tests/test_flow.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    Composition,
    CompositionBrief,
    ConductorRuling,
    DebateEvent,
    EventType,
    Layer,
    Note,
    ProducerScores,
    ProducerVerdict,
    RasikScores,
    RasikVerdict,
    Section,
    SectionKind,
    UstadVerdict,
    build_arrangement,
)
from crew.contracts import repair_layer, repair_operation  # noqa: E402
from crew.flow import Stages, compose_flow, revise_arrangement  # noqa: E402


def _arr():
    draft = ArrangementDraft(
        raga="darbari", subgenre="progressive", tala="teentaal", bpm=120,
        motif=["S", "R", "g"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drums", "drone"],
                    foreground="rhythm", intent="main riff"),
            Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "rhythm", "drums", "drone"],
                    foreground="lead", intent="the taan")])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _comp():
    return Composition(raga="darbari", sa=62, bpm=120, tala={"name": "teentaal", "beats_per_bar": 16.0},
                       layers=[Layer(role="lead", notes=[Note(swara="S", oct=0, start=0.0, dur=1.0)])])


def _ev(name: str) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent=name, role="system", text=name)


def _fake_stages(rulings: list[ConductorRuling], *, counts: dict):
    """Fake Stages that ignore inputs and replay a scripted sequence of rulings; the
    `counts` dict records how many times each looping stage ran."""
    arr, comp = _arr(), _comp()
    ruling_iter = iter(rulings)

    def interpret(query):
        counts["query"] = query
        return CompositionBrief(mood="dark"), [_ev("interpret")]

    def critique(_comp, _arr):
        counts["critique"] = counts.get("critique", 0) + 1
        return (UstadVerdict(verdict="legal", explanation="clean"),
                RasikVerdict(scores=RasikScores(pakad=3, idiom=3, rasa=3)),
                ProducerVerdict(scores=ProducerScores(
                    structure=3, dynamics=3, climax=3, motif=3, hook=3,
                    balance=3, independence=3, mood_fit=3, repetition=3, performance=3)),
                [_ev("critique")])

    def arbitrate(_u, _r, _p, _c):
        counts["arbitrate"] = counts.get("arbitrate", 0) + 1
        return next(ruling_iter), [_ev("arbitrate")]

    def regenerate(_arr, lead, rhythm, orchestra, ruling, canvases):
        counts["regenerate"] = counts.get("regenerate", 0) + 1
        counts.setdefault("revise_layers", []).append(ruling.layer)
        return lead, rhythm, orchestra, [_ev("regenerate")], canvases

    def render(_comp):
        counts["render"] = counts.get("render", 0) + 1
        return "out/fake.wav"

    return Stages(
        interpret=interpret,
        compose=lambda brief: (arr, [_ev("compose")]),
        generate=lambda arr: ([Layer(role="lead")], Layer(role="rhythm"), [], [_ev("generate")], []),
        assemble=lambda arr, lead, rhythm, orchestra: comp,
        critique=critique, arbitrate=arbitrate, regenerate=regenerate, render=render)


def _accept():
    return ConductorRuling(directive="accept", reason="good enough")


def _revise(layer="lead"):
    return ConductorRuling(directive="revise", layer=layer, reason=f"redo the {layer}")


# --- the surgical-revise helper (pure) --------------------------------------

def test_revise_arrangement_threads_directive_into_flagged_sections_only():
    arr = _arr()
    revised = revise_arrangement(arr, _revise("lead"))
    by_kind = {s.kind: s for s in revised.sections}
    assert "REVISE" in by_kind[SectionKind.TAAN].intent          # taan has the lead -> annotated
    assert "REVISE" not in by_kind[SectionKind.RIFF].intent      # riff has no lead -> untouched
    # the original chart is not mutated
    assert all("REVISE" not in (s.intent or "") for s in arr.sections)


def test_an_operation_routes_to_the_repair_the_fault_needs():
    """Naming a LAYER could only ever mean 'compose that voice again'. A relationship fault
    — the parts each good but fighting — now routes to the pass that repairs the
    relationship, instead of throwing away a working voice to re-roll the dice."""
    relationship = ConductorRuling(directive="revise", operation="arrange_riff_against_lead",
                                   reason="the guitar argues under the held sitar notes")
    assert repair_operation(relationship) == "arrange_riff_against_lead"
    assert repair_layer(relationship) is None, "a relationship repair regenerates nothing"


def test_a_ruling_that_names_only_a_layer_still_works():
    """The old shape stays valid, so a model answering the previous way is never a failed
    run — it simply means 'regenerate that voice'."""
    assert repair_operation(_revise("lead")) == "regenerate_lead"
    assert repair_operation(_revise("rhythm")) == "regenerate_riff"
    assert repair_layer(_revise("rhythm")) == "rhythm"


def test_an_accept_asks_for_no_repair():
    assert repair_operation(_accept()) is None


def test_a_relationship_repair_threads_no_directive_into_the_chart():
    """A regeneration needs its directive in the section intents; a relationship repair has
    no generator to steer, so the chart must come back untouched."""
    arr = _arr()
    revised = revise_arrangement(
        arr, ConductorRuling(directive="revise", operation="arrange_riff_against_lead",
                             reason="settle the guitar"))
    assert all("REVISE" not in (s.intent or "") for s in revised.sections)


# --- the loop --------------------------------------------------------------

def test_accept_skips_revise_and_renders_once():
    counts: dict = {}
    state = compose_flow("q", stages=_fake_stages([_accept()], counts=counts), max_rounds=2)
    assert counts.get("regenerate", 0) == 0                      # no revise
    assert counts["critique"] == 1 and counts["arbitrate"] == 1
    assert counts["render"] == 1 and state.wav_path == "out/fake.wav"
    assert state.round == 0


def test_revise_then_accept_runs_exactly_one_revise():
    counts: dict = {}
    state = compose_flow("q", stages=_fake_stages([_revise("lead"), _accept()], counts=counts),
                         max_rounds=2)
    assert counts["regenerate"] == 1
    assert counts["critique"] == 2 and counts["arbitrate"] == 2  # re-critiqued after the revise
    assert counts["revise_layers"] == ["lead"]
    assert state.round == 1 and counts["render"] == 1


def test_always_revise_is_capped_and_still_terminates():
    counts: dict = {}
    # the Conductor would revise forever; the router cap must stop it and still render
    state = compose_flow("q", stages=_fake_stages([_revise()] * 9, counts=counts), max_rounds=2)
    assert counts["regenerate"] == 2                             # capped at max_rounds revises
    assert counts["critique"] == 3                               # initial + one per revise
    assert state.round == 2 and counts["render"] == 1            # terminated, rendered the last


def test_query_is_seeded_into_state():
    counts: dict = {}
    state = compose_flow("doom in Malkauns", stages=_fake_stages([_accept()], counts=counts))
    assert counts["query"] == "doom in Malkauns"                 # kickoff seeded state.query
    assert state.query == "doom in Malkauns"


def test_events_accumulate_across_the_pipeline():
    counts: dict = {}
    state = compose_flow("q", stages=_fake_stages([_revise("lead"), _accept()], counts=counts))
    agents = [e.agent for e in state.events]
    # the opening pass, the revise, and the second pass all left events
    assert "interpret" in agents and "compose" in agents and "generate" in agents
    assert agents.count("critique") == 2 and agents.count("regenerate") == 1


# --- generation-path selection: studio (opt-in) vs parallel (default) ----------

def test_studio_enabled_reads_the_env_flag():
    from crew.config import studio_enabled
    for on in ("1", "true", "YES", "on"):
        os.environ["RMA_STUDIO"] = on
        assert studio_enabled() is True, on
    for off in ("0", "", "no", "false"):
        os.environ["RMA_STUDIO"] = off
        assert studio_enabled() is False, off
    os.environ.pop("RMA_STUDIO", None)
    assert studio_enabled() is False                 # unset -> off (parallel is the default)


def test_canvas_passes_default_override_and_fallback():
    from crew.config import CANVAS_PASSES, canvas_passes
    os.environ.pop("RMA_CANVAS_PASSES", None)
    assert canvas_passes() == CANVAS_PASSES
    os.environ["RMA_CANVAS_PASSES"] = "1"
    assert canvas_passes() == 1
    os.environ["RMA_CANVAS_PASSES"] = "-4"           # clamped to >= 1
    assert canvas_passes() == 1
    os.environ["RMA_CANVAS_PASSES"] = "junk"          # non-int -> default, never crash a run
    assert canvas_passes() == CANVAS_PASSES
    os.environ.pop("RMA_CANVAS_PASSES", None)


def test_generate_routes_to_the_studio_when_enabled():
    import crew.flow as flow
    import crew.studio_session as ss
    marks: list = []
    original = ss.compose_studio
    ss.compose_studio = lambda arr, **kw: marks.append(("studio", kw.get("passes"))) or ([], None, [], [])
    os.environ["RMA_STUDIO"] = "1"
    os.environ["RMA_CANVAS_PASSES"] = "2"
    try:
        result = flow._generate(_arr())
        assert marks == [("studio", 2)]              # routed to the studio, passes threaded
        # _arr() uses no orchestra, so orchestra_layers is empty: (lead, rhythm, orchestra, events, canvases)
        assert result == ([], None, [], [], [])
    finally:
        ss.compose_studio = original
        os.environ.pop("RMA_STUDIO", None)
        os.environ.pop("RMA_CANVAS_PASSES", None)


def test_generate_routes_to_parallel_by_default():
    import crew.flow as flow
    import crew.lead as lead_mod
    import crew.riff as riff_mod
    marks: list = []
    ol, orr = lead_mod.compose_lead, riff_mod.compose_riff
    lead_mod.compose_lead = lambda arr: marks.append("lead") or ([], [])
    riff_mod.compose_riff = lambda arr, mukhada=None: marks.append("riff") or (None, [])
    os.environ.pop("RMA_STUDIO", None)               # default: studio OFF
    try:
        flow._generate(_arr())
        assert marks == ["lead", "riff"]             # the parallel generate-in-isolation path
    finally:
        lead_mod.compose_lead = ol
        riff_mod.compose_riff = orr


# --- the orchestra: capability-gated in generate, targetable in a revise ---------

def _symphonic_arr():
    draft = ArrangementDraft(
        raga="kirwani", subgenre="symphonic", tala="keherwa", bpm=120, motif=["S", "g", "P"],
        sections=[Section(kind=SectionKind.RIFF, bars=1,
                          layers=["rhythm", "orchestra", "drone"], foreground="rhythm",
                          intent="symphonic riff")])
    return build_arrangement(draft, CompositionBrief(mood="epic"))


def test_generate_scores_the_orchestra_when_the_chart_uses_it():
    import crew.flow as flow
    import crew.lead as lead_mod
    import crew.orchestra as orch_mod
    import crew.riff as riff_mod
    marks: list = []
    ol, orr, oo = lead_mod.compose_lead, riff_mod.compose_riff, orch_mod.compose_orchestra
    lead_mod.compose_lead = lambda a: ([], [])
    riff_mod.compose_riff = lambda a, mukhada=None: (Layer(role="rhythm"), [])
    orch_mod.compose_orchestra = (
        lambda a, **kw: marks.append("orchestra") or ([Layer(role="orch_strings")], [_ev("orch")]))
    os.environ.pop("RMA_STUDIO", None)
    try:
        _lead, _rhythm, orchestra_layers, _events, _canvases = flow._generate(_symphonic_arr())
        assert marks == ["orchestra"]                        # the capability gate fired
        assert [la.role for la in orchestra_layers] == ["orch_strings"]
    finally:
        lead_mod.compose_lead = ol
        riff_mod.compose_riff = orr
        orch_mod.compose_orchestra = oo


def test_regenerate_reworks_the_orchestra_when_flagged():
    import crew.flow as flow
    import crew.orchestra as orch_mod
    marks: list = []
    oo = orch_mod.compose_orchestra
    orch_mod.compose_orchestra = lambda a, **kw: marks.append("orch") or ([Layer(role="orch_choir")], [])
    try:
        lead = [Layer(role="lead")]
        rhythm = Layer(role="rhythm")
        orch = [Layer(role="orch_strings")]
        ruling = ConductorRuling(directive="revise", layer="orchestra", reason="thin the strings")
        new_lead, new_rhythm, new_orch, _events, _canvases = flow._regenerate(
            _symphonic_arr(), lead, rhythm, orch, ruling, [])
        assert marks == ["orch"]                             # the orchestra re-scored
        assert [la.role for la in new_orch] == ["orch_choir"]
        assert new_lead is lead and new_rhythm is rhythm     # the other voices stand
    finally:
        orch_mod.compose_orchestra = oo


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
