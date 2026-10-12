"""
Tests for the Flow — the orchestration and the BOUNDED REVISE LOOP, no LLM (free).

`ComposeFlow` takes an injected `Stages` bundle, so the whole propose->critique->
decide->(revise)->render loop is kicked off here with fakes: does an ACCEPT skip revise and
render once; does a revise-then-accept run exactly one revise; and — the live-safety
property — does an always-revise decider get capped at MAX_ROUNDS and still terminate
(rendering the last version)? (The pure revision and triage helpers have their own tests:
test_revision.py, test_triage.py.) The real end-to-end run is exercised live via
`uv run python -m crew.flow`, not here.

Runs as a script (`uv run python tests/test_flow.py`) or under pytest.
"""

from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    Composition,
    CompositionBrief,
    DebateEvent,
    EventType,
    Layer,
    Note,
    ProducerScores,
    ProducerVerdict,
    RasikScores,
    RasikVerdict,
    RevisionPlan,
    Section,
    SectionKind,
    UstadVerdict,
    build_arrangement,
)
from crew.flow import Stages, compose_flow  # noqa: E402


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


def _fake_stages(decisions: list[RevisionPlan | None], *, counts: dict):
    """Fake Stages that ignore inputs and replay a scripted sequence of decisions (a plan =
    revise, None = accept); `counts` records how many times each looping stage ran."""
    arr, comp = _arr(), _comp()
    decision_iter = iter(decisions)

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

    def decide(_u, _r, _p, _c, _a):
        counts["decide"] = counts.get("decide", 0) + 1
        return next(decision_iter), [_ev("decide")]

    def regenerate(_arr, lead, rhythm, orchestra, plan, canvases, history=()):
        counts["regenerate"] = counts.get("regenerate", 0) + 1
        counts.setdefault("revise_voices", []).append(plan.voice)
        return lead, rhythm, orchestra, [_ev("regenerate")], canvases

    def render(_comp):
        counts["render"] = counts.get("render", 0) + 1
        return "out/fake.wav"

    return Stages(
        interpret=interpret,
        compose=lambda brief: (arr, [_ev("compose")]),
        generate=lambda arr: ([Layer(role="lead")], Layer(role="rhythm"), [], [_ev("generate")], []),
        assemble=lambda arr, lead, rhythm, orchestra: comp,
        critique=critique, decide=decide, regenerate=regenerate, render=render)


def _accept() -> None:
    return None


def _revise(voice: str = "lead") -> RevisionPlan:
    return RevisionPlan(voice=voice, instruction=f"redo the {voice}")


# --- the loop --------------------------------------------------------------

def test_accept_skips_revise_and_renders_once():
    counts: dict = {}
    state = compose_flow("q", stages=_fake_stages([_accept()], counts=counts), max_rounds=2)
    assert counts.get("regenerate", 0) == 0                      # no revise
    assert counts["critique"] == 1 and counts["decide"] == 1
    assert counts["render"] == 1 and state.wav_path == "out/fake.wav"
    assert state.round == 0


def test_revise_then_accept_runs_exactly_one_revise():
    counts: dict = {}
    state = compose_flow("q", stages=_fake_stages([_revise("lead"), _accept()], counts=counts),
                         max_rounds=2)
    assert counts["regenerate"] == 1
    assert counts["critique"] == 2 and counts["decide"] == 2    # re-critiqued after the revise
    assert counts["revise_voices"] == ["lead"]
    assert state.decision == "accept"
    assert state.round == 1 and counts["render"] == 1


def test_always_revise_is_capped_and_still_terminates():
    counts: dict = {}
    # the decider would revise forever; the router cap must stop it and still render
    state = compose_flow("q", stages=_fake_stages([_revise()] * 9, counts=counts), max_rounds=2)
    assert counts["regenerate"] == 2                             # capped at max_rounds revises
    assert counts["critique"] == 3                               # initial + one per revise
    assert state.round == 2 and counts["render"] == 1            # terminated, rendered the last


def test_the_same_edit_asked_again_without_gain_stops_the_loop():
    # the 2026-10-11 run: the judge chased the taan's scalar runs three rounds running, flat scores
    counts: dict = {}
    stages = _fake_stages([], counts=counts)
    taan = RevisionPlan(voice="lead", sections=[1], instruction="vakra, not scalar")
    scores = ProducerScores(structure=4, dynamics=4, climax=4, motif=3, hook=4, balance=4,
                            independence=4, mood_fit=4, repetition=4, performance=4)

    def critique(_comp, _arr):
        counts["critique"] = counts.get("critique", 0) + 1
        return (UstadVerdict(verdict="legal", explanation="clean"),
                RasikVerdict(scores=RasikScores(pakad=3, idiom=3, rasa=3)),
                ProducerVerdict(scores=scores, decision="revise", plan=taan), [_ev("critique")])

    stages = dataclasses.replace(stages, critique=critique,
                                 decide=lambda u, r, p, c, a: (p.plan, [_ev("decide")]))
    state = compose_flow("q", stages=stages, max_rounds=3)
    assert counts["regenerate"] == 1 and counts["critique"] == 2   # one revise, then stop
    assert any("same edit" in e.text for e in state.events) and counts["render"] == 1


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


def test_the_flow_never_calls_an_arranger():
    """Sujit kept the riff/sitar grinds by ear (2026-10-11): the generated lines go on as
    composed, so the default path is exactly lead + riff, nothing that rewrites either."""
    import crew.flow as flow
    assert not hasattr(flow, "arrange_against_lead")
    import importlib.util
    assert importlib.util.find_spec("crew.arranger") is None


def test_generate_routes_to_parallel_by_default():
    import crew.flow as flow
    import crew.lead as lead_mod
    import crew.riff as riff_mod
    marks: list = []
    ol, orr = lead_mod.compose_lead, riff_mod.compose_riff
    lead_mod.compose_lead = lambda arr, riff=None: marks.append("lead") or ([], [])
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
    lead_mod.compose_lead = lambda a, riff=None: ([], [])
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


def test_regenerate_reworks_the_orchestra_when_planned():
    import crew.flow as flow
    import crew.orchestra as orch_mod
    marks: list = []
    oo = orch_mod.compose_orchestra
    choir = Layer(role="orch_choir", notes=[Note(swara="S", oct=0, start=0.0, dur=4.0)])
    orch_mod.compose_orchestra = lambda a, **kw: marks.append("orch") or ([choir], [])
    try:
        lead = [Layer(role="lead")]
        rhythm = Layer(role="rhythm")
        orch = [Layer(role="orch_strings", notes=[Note(swara="S", oct=0, start=0.0, dur=4.0)])]
        plan = RevisionPlan(voice="orchestra", instruction="thin the strings")
        new_lead, new_rhythm, new_orch, _events, _canvases = flow._regenerate(
            _symphonic_arr(), lead, rhythm, orch, plan, [])
        assert marks == ["orch"]                             # the orchestra re-scored
        assert [la.role for la in new_orch] == ["orch_choir"]  # its one section was replaced
        assert new_lead is lead and new_rhythm is rhythm     # the other voices stand
    finally:
        orch_mod.compose_orchestra = oo



def test_the_listening_pass_runs_after_the_render_and_never_gates():
    # advisory: it hears the accepted render once, adds its report to the events, and the
    # decision it cannot influence is already made
    import dataclasses
    from crew.flow import ComposeFlow
    counts: dict = {}
    heard: list = []

    def listen(wav, arr):
        heard.append(wav)
        return [_ev("listened")]

    stages = dataclasses.replace(_fake_stages([_accept()], counts=counts), listen=listen)
    flow = ComposeFlow(stages)
    flow.kickoff(inputs={"query": "q"})
    assert heard == ["out/fake.wav"] and counts["render"] == 1
    assert flow.state.events[-1].text == "listened"


def test_the_listening_pass_is_off_unless_the_flag_is_set():
    import os
    from crew.flow import production_stages
    os.environ.pop("RMA_LISTEN", None)
    assert production_stages(name="x").listen is None
    os.environ["RMA_LISTEN"] = "1"
    try:
        assert production_stages(name="x").listen is not None
    finally:
        os.environ.pop("RMA_LISTEN", None)

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
