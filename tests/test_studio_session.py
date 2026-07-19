"""
Tests for the LLM-backed studio session (crew/studio_session.py) — all pure (no key,
no cost). The generation is INJECTED as fake lead/riff functions, so these prove the
COOPERATION wiring without the LLM: that each voice sees the other's line on the canvas,
that the riff-slot recurrence reprises a returning hook without regenerating it, that
cross-section memory accumulates, that fast mode plays the leader only, and that
`compose_studio` assembles the filled canvases into the band's (lead layers, rhythm)
shape. The real generators are exercised live via the Flow, not here.

Runs as a script (`uv run python tests/test_studio_session.py`) or under pytest.
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
    LeadNote,
    LeadPhrase,
    PhrasePlan,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.studio import run_studio  # noqa: E402
from crew.studio_session import (  # noqa: E402
    compose_studio,
    make_contributor,
    regenerate_layer,
)


# --- fixtures: a real chart + fake, recording generators -----------------------

def _arr(*sections: Section) -> Arrangement:
    draft = ArrangementDraft(raga="darbari", subgenre="progressive", tala="teentaal",
                             bpm=120, motif=["S", "R", "g"], sections=list(sections))
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _section(kind: SectionKind, layers: list[str], foreground: str,
             slot: str | None = None) -> Section:
    return Section(kind=kind, bars=1, layers=layers, foreground=foreground, riff_slot=slot)


def _lead_phrase(*sw: str) -> LeadPhrase:
    notes = [LeadNote(swara=s, dur=1.0) for s in sw] or [LeadNote(swara="S", dur=1.0)]
    return LeadPhrase(phrase_plan=PhrasePlan(seed=["S"], contour="arch",
                      transformations=["repeat"], climax_and_sam="x"), notes=notes)


def _riff_pattern(*sw: str) -> RiffPattern:
    notes = [RiffNote(swara=s, dur=0.5) for s in sw] or [RiffNote(swara="S", dur=0.5)]
    return RiffPattern(reasoning="x", notes=notes)


def _fake_lead():
    calls: list[dict] = []

    def fn(span, memory, canvas, move):
        calls.append({"index": span.index, "move": move, "mem": len(memory),
                      "saw_riff": canvas.riff is not None})
        return _lead_phrase("S", "g")

    fn.calls = calls
    return fn


def _fake_riff():
    calls: list[dict] = []

    def fn(span, memory, canvas, move):
        calls.append({"index": span.index, "move": move, "mem": len(memory),
                      "saw_lead": canvas.lead is not None})
        return _riff_pattern("S", "S")

    fn.calls = calls
    return fn


_RIFF_SEC = _section(SectionKind.RIFF, ["rhythm", "lead", "drone"], "rhythm")
_TAAN_SEC = _section(SectionKind.TAAN, ["lead", "rhythm", "drone"], "lead")
_MELODY_SEC = _section(SectionKind.MELODY, ["lead", "rhythm", "drone"], "lead")


# --- compose_studio: the assembled band shape ----------------------------------

def test_compose_studio_returns_the_generate_tuple_shape():
    arr = _arr(_RIFF_SEC, _TAAN_SEC)
    lead_layers, rhythm, events, canvases = compose_studio(
        arr, lead_fn=_fake_lead(), riff_fn=_fake_riff())
    assert isinstance(lead_layers, list) and lead_layers          # lead played
    assert rhythm is not None and rhythm.role == "rhythm"
    assert events and all(e.data is not None for e in events if e.agent in ("Lead", "Riff"))
    assert len(canvases) == 2                                     # one filled canvas per section


# --- cooperation: each voice sees the other's line on the canvas ----------------

def test_lead_responds_to_the_riff_on_the_canvas():
    # RIFF section: the rhythm leads, so the lead's RESPOND sees the riff already down.
    lead_fn, riff_fn = _fake_lead(), _fake_riff()
    compose_studio(_arr(_RIFF_SEC), lead_fn=lead_fn, riff_fn=riff_fn, passes=2)
    respond = [c for c in lead_fn.calls if c["move"] is CanvasMove.RESPOND]
    assert respond and respond[0]["saw_riff"] is True


def test_riff_responds_to_the_lead_in_a_lead_led_section():
    # TAAN section: the lead leads, so the riff's RESPOND sees the lead already down.
    lead_fn, riff_fn = _fake_lead(), _fake_riff()
    compose_studio(_arr(_TAAN_SEC), lead_fn=lead_fn, riff_fn=riff_fn, passes=2)
    respond = [c for c in riff_fn.calls if c["move"] is CanvasMove.RESPOND]
    assert respond and respond[0]["saw_lead"] is True


# --- riff-slot recurrence: a returning hook reprises, it isn't regenerated ------

def test_recurring_slot_reprises_without_regenerating():
    # Two RIFF sections default to the same slot ("riff"): only the first is generated.
    lead_fn, riff_fn = _fake_lead(), _fake_riff()
    _, _, events, _ = compose_studio(_arr(_RIFF_SEC, _RIFF_SEC),
                                     lead_fn=lead_fn, riff_fn=riff_fn, passes=3)
    assert all(c["index"] == 0 for c in riff_fn.calls)           # section 1 never regenerated
    assert len([c for c in riff_fn.calls if c["move"] is CanvasMove.PROPOSE]) == 1
    assert any(e.data and e.data.get("reprise") for e in events)  # the hook returns


def test_distinct_slots_are_generated_separately():
    lead_fn, riff_fn = _fake_lead(), _fake_riff()
    arr = _arr(_section(SectionKind.RIFF, ["rhythm", "lead", "drone"], "rhythm", slot="main"),
               _section(SectionKind.RIFF, ["rhythm", "lead", "drone"], "rhythm", slot="chorus"))
    compose_studio(arr, lead_fn=lead_fn, riff_fn=riff_fn, passes=2)
    proposed = {c["index"] for c in riff_fn.calls if c["move"] is CanvasMove.PROPOSE}
    assert proposed == {0, 1}                                     # both slots generated


def test_reprised_riff_holds_its_shape_across_refine_turns():
    arr = _arr(_RIFF_SEC, _RIFF_SEC)                              # same slot
    contribute = make_contributor(arr, lead_fn=_fake_lead(), riff_fn=_fake_riff())
    result = run_studio(arr, contribute=contribute, passes=3)
    # The returning section replays the FIRST section's (refined) riff, identity intact.
    assert result.canvases[1].riff is result.canvases[0].riff


# --- cross-section memory accumulates -------------------------------------------

def test_lead_memory_accumulates_across_sections():
    lead_fn, riff_fn = _fake_lead(), _fake_riff()
    compose_studio(_arr(_MELODY_SEC, _MELODY_SEC),
                   lead_fn=lead_fn, riff_fn=riff_fn, passes=2)
    first_mem = {}
    for c in lead_fn.calls:
        first_mem.setdefault(c["index"], c["mem"])
    assert first_mem[0] == 0 and first_mem[1] == 1               # section 1 sees section 0's lead


# --- fast mode: the leader only -------------------------------------------------

def test_fast_mode_one_pass_plays_only_the_leader():
    lead_fn, riff_fn = _fake_lead(), _fake_riff()
    lead_layers, rhythm, _, _ = compose_studio(_arr(_RIFF_SEC),
                                               lead_fn=lead_fn, riff_fn=riff_fn, passes=1)
    assert riff_fn.calls and lead_fn.calls == []                 # only the rhythm leader played
    assert rhythm is not None and lead_layers == []             # the lead laid out -> no lead layer


# --- canvas-aware revise: the collaboration survives a regeneration -------------

def test_regenerate_layer_lets_the_lead_see_the_riff_on_the_canvas():
    # After a studio run, regenerating the LEAD sees the riff already on each canvas and
    # REFINES against it — so the collaboration survives the revise (the whole point of step 5).
    arr = _arr(_RIFF_SEC, _TAAN_SEC)
    _, _, _, canvases = compose_studio(arr, lead_fn=_fake_lead(), riff_fn=_fake_riff())
    saw: list[tuple] = []

    def regen_lead(span, memory, canvas, move):
        saw.append((move, canvas.riff is not None))
        return _lead_phrase("S", "m")

    lead_layers, rhythm, events, out = regenerate_layer(
        arr, canvases, "lead", lead_fn=regen_lead, riff_fn=_fake_riff())
    assert saw and all(move is CanvasMove.REFINE for move, _ in saw)   # a rework, not a fresh open
    assert all(saw_riff for _, saw_riff in saw)                        # each saw the riff it answers
    assert lead_layers and out is canvases                            # updated in place & returned


def test_regenerate_layer_touches_only_the_flagged_voice():
    arr = _arr(_RIFF_SEC, _TAAN_SEC)
    _, _, _, canvases = compose_studio(arr, lead_fn=_fake_lead(), riff_fn=_fake_riff())
    riffs_before = [c.riff for c in canvases]
    regenerate_layer(arr, canvases, "lead", lead_fn=_fake_lead(), riff_fn=_fake_riff())
    assert [c.riff for c in canvases] == riffs_before                 # the riff lines untouched


def test_regenerate_layer_reprises_recurring_riff_slots():
    arr = _arr(_RIFF_SEC, _RIFF_SEC)                                  # both sections share a slot
    _, _, _, canvases = compose_studio(arr, lead_fn=_fake_lead(), riff_fn=_fake_riff())
    regen_calls: list[int] = []

    def regen_riff(span, memory, canvas, move):
        regen_calls.append(span.index)
        return _riff_pattern("S", "g")

    regenerate_layer(arr, canvases, "rhythm", lead_fn=_fake_lead(), riff_fn=regen_riff)
    assert regen_calls == [0]                                         # the slot regenerated once
    assert canvases[1].riff is canvases[0].riff                       # the reprise propagated


# --- end-to-end: the studio output assembles into a legal Composition -----------

def test_studio_output_assembles_into_a_legal_composition():
    # The whole point of matching `_generate`'s shape: the studio's layers flow straight
    # through band assembly into a raga-legal Composition (all the live run adds is audio).
    from crew.band import band_layers
    from crew.generators import assemble_composition
    from raga import validate_composition
    arr = _arr(_RIFF_SEC, _TAAN_SEC)
    lead_layers, rhythm, _, _ = compose_studio(arr, lead_fn=_fake_lead(), riff_fn=_fake_riff())
    comp = assemble_composition(arr, band_layers(arr, lead_layers, rhythm))
    assert validate_composition(comp.model_dump(exclude_none=True)) == []


# --- events carry the move ------------------------------------------------------

def test_contribution_events_carry_the_move():
    _, _, events, _ = compose_studio(_arr(_RIFF_SEC),
                                     lead_fn=_fake_lead(), riff_fn=_fake_riff(), passes=2)
    moves = [e.data.get("move") for e in events if e.data and "move" in e.data]
    assert "propose" in moves and "respond" in moves


# --- end-to-end through the real Flow: a revise stays canvas-aware --------------

def test_flow_revise_stays_canvas_aware():
    # Drive the REAL Flow (studio generate + canvas-aware regenerate) with fake, no-LLM
    # voices and a scripted revise-then-accept. The revised lead must still SEE the riff on
    # the canvas — proving the collaboration survives the critique loop (the step-5 fix).
    from crew.contracts import (
        ConductorRuling, ProducerScores, ProducerVerdict, RasikScores, RasikVerdict, UstadVerdict)
    from crew.flow import Stages, compose_flow

    arr = _arr(_RIFF_SEC, _TAAN_SEC)
    gen_lead, gen_riff, rev_lead = _fake_lead(), _fake_riff(), _fake_lead()

    def assemble(a, lead, rhythm, orchestra):
        from crew.band import band_layers
        from crew.generators import assemble_composition
        return assemble_composition(a, band_layers(a, lead, rhythm, orchestra))

    def generate(_a):
        # the studio path produces no orchestra; thread an empty orchestra slot into the
        # Flow's (lead, rhythm, orchestra, events, canvases) contract.
        lead, rhythm, events, canvases = compose_studio(arr, lead_fn=gen_lead, riff_fn=gen_riff)
        return lead, rhythm, [], events, canvases

    def regenerate(_a, lead, rhythm, orchestra, ruling, canvases):
        new_lead, new_rhythm, events, new_canvases = regenerate_layer(
            arr, canvases, ruling.layer, lead_fn=rev_lead, riff_fn=gen_riff)
        return new_lead, new_rhythm, orchestra, events, new_canvases

    rulings = iter([ConductorRuling(directive="revise", layer="lead", reason="more space"),
                    ConductorRuling(directive="accept", reason="good")])
    stages = Stages(
        interpret=lambda q: (CompositionBrief(mood="dark"), []),
        compose=lambda b: (arr, []),
        generate=generate,
        assemble=assemble,
        critique=lambda _c, _a: (
            UstadVerdict(verdict="legal", explanation="clean"),
            RasikVerdict(scores=RasikScores(pakad=3, idiom=3, rasa=3)),
            ProducerVerdict(scores=ProducerScores(
                structure=3, dynamics=3, climax=3, motif=3, hook=3,
                balance=3, independence=3, mood_fit=3, repetition=3)),
            []),
        arbitrate=lambda u, r, p, c: (next(rulings), []),
        regenerate=regenerate,
        render=lambda c: None)

    state = compose_flow("q", stages=stages, max_rounds=2)
    assert state.round == 1 and state.composition is not None       # exactly one revise, then accept
    assert rev_lead.calls                                            # the revise regenerated the lead
    assert all(c["saw_riff"] for c in rev_lead.calls)               # it SAW the riff (canvas-aware)
    assert all(c["move"] is CanvasMove.REFINE for c in rev_lead.calls)
    assert state.canvases and len(state.canvases) == 2              # canvases retained in Flow state


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
