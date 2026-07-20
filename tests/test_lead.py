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
    CanvasMove,
    CompositionBrief,
    EventType,
    Gat,
    LeadNote,
    LeadPhrase,
    Note,
    PhrasePlan,
    RiffNote,
    RiffPattern,
    Section,
    SectionCanvas,
    SectionKind,
    build_arrangement,
)
from crew.generators import VOICES, section_spans  # noqa: E402
from crew.generators import SectionSpan  # noqa: E402
from crew.lead import (  # noqa: E402
    LeadMemo,
    Voicing,
    _intro_gen_span,
    _LeadContext,
    _lead_guardrail,
    _next_sam,
    _place_intro_phrases,
    _role_briefs,
    _render_canvas_for_lead,
    _render_previous,
    _split_phrases,
    _voice_line,
    apply_ornaments,
    apply_strokes,
    approach_cut,
    generate_lead,
    is_mukhada,
    lead_layers_from,
    make_tihai,
    place_phrase,
    splice_tihai,
    studio_lead_fn,
)


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


def _plan(*seed: str) -> PhrasePlan:
    """A minimal valid phrase plan for fixtures (Sa is legal in every raga)."""
    return PhrasePlan(seed=list(seed) or ["S"], contour="arch",
                      transformations=["repeat", "resolve"], climax_and_sam="peaks, lands on Sa")


def _phrase(*swaras: str, dur: float = 2.0) -> LeadPhrase:
    return LeadPhrase(phrase_plan=_plan(), notes=[LeadNote(swara=s, dur=dur) for s in swaras])


def _fake(phrases: list[LeadPhrase]):
    """A fake gen_fn that replays canned phrases and records the spans + memory + feedback it saw."""
    calls: list = []
    seen_memory: list = []
    seen_feedback: list = []
    it = iter(phrases)

    def fn(span, arr, memory, *, feedback=None):
        calls.append(span)
        seen_memory.append(memory)
        seen_feedback.append(feedback)
        return next(it)

    fn.seen_memory = seen_memory
    fn.seen_feedback = seen_feedback
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
    placed = place_phrase([LeadNote(swara="g", dur=2.0, grace=["S"], meend_swara="m")],
                          start=0.0, end=8.0, register=0)
    assert placed[0].grace == ["S"] and placed[0].meend_swara == "m"


def test_place_phrase_strips_meend_from_a_short_note():
    # A meend needs a long note to speak; a glide crammed onto a fast taan note sags. Code
    # strips the glide from a sub-beat note (keeping the note and its kan), but keeps it on a
    # long one — density/length only, never direction.
    fast = LeadNote(swara="g", dur=0.25, grace=["S"], meend_swara="m")
    held = LeadNote(swara="m", dur=1.5, meend_swara="P")
    placed = place_phrase([fast, held], start=0.0, end=8.0, register=0)
    assert placed[0].meend_swara is None and placed[0].meend_oct is None  # stripped: too short
    assert placed[0].grace == ["S"]                                       # kan is untouched
    assert placed[1].meend_swara == "P"                                   # kept: long enough


def test_place_phrase_strips_meend_when_the_window_clips_a_note_short():
    # A long note clipped by the window edge below the threshold also loses its glide.
    placed = place_phrase([LeadNote(swara="m", dur=4.0, meend_swara="P")],
                          start=0.0, end=0.5, register=0)
    assert placed[0].dur == 0.5 and placed[0].meend_swara is None


def test_place_phrase_keeps_same_octave_meend_unshifted():
    # A glide with no meend_oct needs no shift — the renderer glides to the target in the
    # note's (already register-seated) octave, so meend_oct stays None.
    placed = place_phrase([LeadNote(swara="g", oct=0, dur=2.0, meend_swara="m")],
                          start=0.0, end=8.0, register=-1)
    assert placed[0].meend_swara == "m" and placed[0].meend_oct is None


def test_place_phrase_shifts_cross_octave_meend_by_register():
    # meend_oct is a LOCAL octave; placement shifts it by the register, exactly like the
    # note's own octave, so the glide lands in the right absolute octave. Here: note local
    # 0 -> abs -1; meend_oct local +1 -> abs 0.
    placed = place_phrase([LeadNote(swara="m", oct=0, dur=2.0, meend_swara="S", meend_oct=1)],
                          start=0.0, end=8.0, register=-1)
    assert placed[0].oct == -1
    assert placed[0].meend_swara == "S" and placed[0].meend_oct == 0


def test_leadnote_accepts_a_cross_octave_meend():
    note = LeadNote(swara="m", dur=2.0, meend_swara="S", meend_oct=1)
    assert note.meend_swara == "S" and note.meend_oct == 1


def test_leadnote_absorbs_an_unknown_meend_swara():
    # ABSORB, don't raise (2026-07-20 live failure): a raising validator fires inside the
    # provider's structured-output validation — before any feedback loop — and one junk
    # ornament killed a whole live compose. Junk meend -> the note plays plain.
    n = LeadNote(swara="S", dur=1.0, meend_swara="Z", meend_oct=1)
    assert n.meend_swara is None


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


# --- composition memory: each section sees the realized prior ones -------------

def test_generate_lead_threads_accumulating_memory():
    arr = _arr(("lead", "drone"), ("lead", "drone"), ("lead", "drone"))
    first, second, third = _phrase("S", "m"), _phrase("g", "d"), _phrase("n", "S")
    fn, _ = _fake([first, second, third])
    generate_lead(arr, gen_fn=fn)
    # section 1 has no history; section 2 sees section 1; section 3 sees 1 and 2 (in order)
    assert fn.seen_memory[0] == []
    assert [m.phrase for m in fn.seen_memory[1]] == [first]
    assert [m.phrase for m in fn.seen_memory[2]] == [first, second]
    assert all(isinstance(m, LeadMemo) for m in fn.seen_memory[2])
    assert fn.seen_memory[2][0].kind == "alaap"


def test_memory_passed_to_gen_fn_is_a_copy():
    # a gen_fn that mutates its memory arg must not corrupt the loop's running history
    arr = _arr(("lead", "drone"), ("lead", "drone"))
    received: list[int] = []
    phrases = iter([_phrase("S"), _phrase("m")])

    def fn(span, a, memory, *, feedback=None):
        received.append(len(memory))
        memory.clear()                      # mutate the COPY we were handed
        return next(phrases)

    generate_lead(arr, gen_fn=fn)
    assert received == [0, 1]               # section 2 still saw section 1 despite the clear


def test_render_previous_shows_the_prior_phrases_and_marks_meend():
    memory = [LeadMemo("alaap", _phrase("S", "m")),
              LeadMemo("taan", LeadPhrase(phrase_plan=_plan("g", "m"),
                                          notes=[LeadNote(swara="g", oct=1, dur=1.0),
                                                 LeadNote(swara="m", dur=1.0, meend_swara="P")]))]
    text = _render_previous(memory)
    assert "alaap: S m" in text
    assert "g(+1)" in text and "m~" in text            # local octave + meend mark


def test_render_previous_is_explicit_when_empty():
    assert "FIRST" in _render_previous([])


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
    # a ONE-bar taan has no room to trade — both voices join immediately, guitar a third up
    arr = _arr(("lead", "drone"), kind=SectionKind.TAAN, raga="darbari")
    fn, _ = _fake([_phrase("S", "R", "g")])        # legal in darbari
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 2
    sitar = next(x for x in layers if x.instrument == VOICES["sitar"].instrument)
    guitar = next(x for x in layers if x.instrument == VOICES["lead_guitar"].instrument)
    assert [n.swara for n in sitar.notes] == ["S", "R", "g"]
    # a raga-diatonic third up in darbari (S R g m P d n): S->g, R->m, g->P
    assert [n.swara for n in guitar.notes] == ["g", "m", "P"]


def test_taan_trades_bars_then_joins_in_harmony():
    # a 3-bar taan: bar 0 sitar's CALL (solo), bar 1 guitar's RESPONSE (solo), bar 2 both
    # JOIN — sitar the line, guitar a raga third above (the dramatic arrival)
    arr = _gat_arr((SectionKind.TAAN, 3, "taan_long"), raga="darbari")
    cell = LeadPhrase(phrase_plan=_plan("S"),                # 48 beats: 16 per teentaal bar
                      notes=[LeadNote(swara="d", dur=0.5), LeadNote(swara="n", dur=0.5),
                             LeadNote(swara="S", dur=0.5), LeadNote(swara="m", dur=0.5),
                             LeadNote(swara="m", dur=6.0), LeadNote(swara="R", dur=8.0),
                             LeadNote(swara="g", dur=0.25), LeadNote(swara="m", dur=0.25),
                             LeadNote(swara="P", dur=0.25), LeadNote(swara="d", dur=0.25),
                             LeadNote(swara="n", dur=0.25), LeadNote(swara="S", dur=0.25, oct=1),
                             LeadNote(swara="R", dur=0.25, oct=1), LeadNote(swara="g", dur=0.25, oct=1),
                             LeadNote(swara="g", dur=8.0, oct=1), LeadNote(swara="m", dur=6.0, oct=1),
                             LeadNote(swara="R", dur=4.0, oct=1), LeadNote(swara="n", dur=4.0),
                             LeadNote(swara="d", dur=2.0), LeadNote(swara="P", dur=2.0),
                             LeadNote(swara="d", dur=0.25), LeadNote(swara="n", dur=0.25),
                             LeadNote(swara="d", dur=0.25), LeadNote(swara="P", dur=0.25),
                             LeadNote(swara="m", dur=0.25), LeadNote(swara="g", dur=0.25),
                             LeadNote(swara="R", dur=0.25), LeadNote(swara="g", dur=0.25),
                             LeadNote(swara="S", dur=2.0)])
    fn, _ = _fake([cell])
    layers, _ = generate_lead(arr, gen_fn=fn)
    sitar = next(x for x in layers if x.instrument == VOICES["sitar"].instrument)
    guitar = next(x for x in layers if x.instrument == VOICES["lead_guitar"].instrument)
    assert all(n.start < 16.0 or n.start >= 32.0 for n in sitar.notes)   # sitar sits out bar 1
    assert all(n.start >= 16.0 for n in guitar.notes)                     # guitar enters at bar 1
    join_s = [n for n in sitar.notes if n.start >= 32.0]
    join_g = [n for n in guitar.notes if n.start >= 32.0]
    assert len(join_s) == len(join_g) > 0                                 # both play the join...
    assert [n.swara for n in join_g] != [n.swara for n in join_s]         # ...guitar a third up


def test_taan_trades_hand_off_on_a_resting_note_not_the_barline():
    # Sujit's steer (2026-07-20): a trade ends on a RESTING note (Sa/vadi/samvadi), the next
    # voice then starts fresh — the handoff snaps to a clean landing, NOT an arbitrary bar line.
    # darbari resting notes = {S, R (vadi), P (samvadi)}. This 3-bar cell has NO resting note
    # until R at beat 18 (past the bar line at 16), so the sitar plays INTO bar 1 to land, and
    # the guitar's answer enters only AFTER that landing. (lead_layers_from places+voices the
    # given phrase directly — no verify_taan re-roll — so the test isolates the trade voicing.)
    arr = _gat_arr((SectionKind.TAAN, 3, "taan_long"), raga="darbari")
    cell = LeadPhrase(phrase_plan=_plan("g"),
                      notes=[LeadNote(swara="g", dur=8.0), LeadNote(swara="m", dur=8.0),   # bar 0: no rest
                             LeadNote(swara="d", dur=2.0), LeadNote(swara="R", dur=2.0),    # R lands at 20
                             LeadNote(swara="m", dur=6.0), LeadNote(swara="n", dur=6.0),    # guitar's answer
                             LeadNote(swara="S", dur=8.0, oct=1),                           # join (bar 2)
                             LeadNote(swara="m", dur=8.0, oct=1)])
    layers = lead_layers_from({0: cell}, arr)
    sitar = next(x for x in layers if x.instrument == VOICES["sitar"].instrument)
    guitar = next(x for x in layers if x.instrument == VOICES["lead_guitar"].instrument)
    sitar_trade = [n for n in sitar.notes if n.start < 32.0]           # before the join
    guitar_trade = [n for n in guitar.notes if n.start < 32.0]
    assert max(n.start for n in sitar_trade) >= 16.0                   # sitar plays PAST the bar line...
    assert sitar_trade[-1].swara == "R"                                # ...to land on a resting note
    assert guitar_trade and min(n.start for n in guitar_trade) >= 20.0  # guitar answers only after it


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
    line = [Note(swara="S", oct=0, start=0.0, dur=1.0, grace=["g"], meend_swara="m")]
    sitar, guitar = _voice_line(line, Voicing.THIRD, "malkauns")
    assert sitar[0].grace == ["g"] and sitar[0].meend_swara == "m"    # melody keeps its ornaments
    assert guitar[0].grace is None and guitar[0].meend_swara is None  # the harmony is clean


# --- lead_layers_from: assemble layers from already-generated phrases -----------

def test_lead_layers_from_places_and_voices_by_index():
    arr = _arr(("lead", "drone"), ("lead", "drone"), kind=SectionKind.MELODY)  # UNISON -> 2 layers
    layers = lead_layers_from({0: _phrase("S", "m"), 1: _phrase("g", "d")}, arr)
    assert len(layers) == 2                          # unison: sitar + guitar
    starts = sorted(n.start for n in layers[0].notes)
    assert starts[0] == 0.0 and any(s >= 16.0 for s in starts)   # both sections placed


def test_lead_layers_from_skips_a_section_without_a_phrase():
    arr = _arr(("lead", "drone"), ("lead", "drone"))              # ALAAP -> solo sitar
    layers = lead_layers_from({0: _phrase("S")}, arr)             # only section 0 has a phrase
    assert len(layers) == 1
    assert all(n.start < 16.0 for n in layers[0].notes)          # nothing placed from section 1


def test_lead_layers_from_empty_when_no_phrases():
    assert lead_layers_from({}, _arr(("lead", "drone"))) == []


# --- canvas awareness: the lead LISTENS to the shared canvas -------------------

def _riff_on_canvas(*swaras: str, chord=None) -> RiffPattern:
    return RiffPattern(reasoning="groove",
                       notes=[RiffNote(swara=s, dur=0.5, chord=chord) for s in swaras])


def _canvas_for_lead(riff=None, lead=None) -> SectionCanvas:
    return SectionCanvas(index=0, kind=SectionKind.RIFF, start=0.0, end=16.0,
                         leader="rhythm", follower="lead", riff=riff, lead=lead)


def test_render_canvas_for_lead_opens_without_a_canvas_or_when_proposing():
    assert "OPEN" in _render_canvas_for_lead(None, CanvasMove.PROPOSE)
    # even with a populated canvas, PROPOSE means the lead OPENS the section (ignores it)
    populated = _canvas_for_lead(riff=_riff_on_canvas("S", "g"))
    assert "OPEN" in _render_canvas_for_lead(populated, CanvasMove.PROPOSE)


def test_render_canvas_for_lead_respond_shows_the_riff_and_asks_to_answer():
    canvas = _canvas_for_lead(riff=_riff_on_canvas("S", "g", chord=["S"]))
    text = _render_canvas_for_lead(canvas, CanvasMove.RESPOND)
    assert "the Riff laid down" in text
    assert "S+S" in text                       # a power chord shows its stacked tone
    assert "ANSWER" in text


def test_render_canvas_for_lead_refine_shows_its_own_line():
    canvas = _canvas_for_lead(riff=_riff_on_canvas("S"), lead=_phrase("g", "m"))
    text = _render_canvas_for_lead(canvas, CanvasMove.REFINE)
    assert "your current line" in text and "REFINE" in text


def test_lead_inputs_for_carries_the_move_and_the_canvas():
    arr = _arr(("lead", "rhythm", "drone"), kind=SectionKind.RIFF, raga="darbari")
    span = section_spans(arr)[0]
    inputs = _LeadContext(arr).inputs_for(
        span, [], canvas=_canvas_for_lead(riff=_riff_on_canvas("S", "g")),
        move=CanvasMove.RESPOND)
    assert inputs["move"] == "respond"
    assert "the Riff laid down" in inputs["canvas"]


def test_lead_inputs_for_defaults_to_solo_without_a_canvas():
    # backward compatible: the non-studio path passes no canvas -> propose / open
    arr = _arr(("lead", "drone"))
    inputs = _LeadContext(arr).inputs_for(section_spans(arr)[0], [])
    assert inputs["move"] == "propose" and "OPEN" in inputs["canvas"]


def test_lead_inputs_for_renders_repair_feedback():
    arr = _arr(("lead", "drone"))
    span = section_spans(arr)[0]
    ctx = _LeadContext(arr)
    assert "first attempt" in ctx.inputs_for(span, [])["repair"]            # no feedback -> benign
    fixed = ctx.inputs_for(span, [], feedback=["the mukhada is rhythmically flat"])["repair"]
    assert "FAILED" in fixed and "flat" in fixed                            # the flaw is named back


def test_studio_lead_fn_builds_a_callable_without_an_llm():
    arr = _arr(("lead", "rhythm", "drone"), kind=SectionKind.RIFF)
    assert callable(studio_lead_fn(arr))


# --- role briefs: one section, one set of rules (the 2026-07-16 latency fix) ----

def test_role_brief_prefers_the_gat_role_over_the_kind():
    # a mukhada (kind ALAAP) gets the mukhada's rules, not the alaap kind's
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    brief = _LeadContext(arr).inputs_for(section_spans(arr)[0], [])["role_brief"]
    assert "EXACTLY ONE avartan" in brief
    assert "unfold the seed" not in brief.lower()


def test_role_brief_falls_back_to_the_section_kind():
    arr = _arr(("lead", "drone"), kind=SectionKind.MELODY)
    brief = _LeadContext(arr).inputs_for(section_spans(arr)[0], [])["role_brief"]
    assert "singable theme" in brief


def test_role_briefs_cover_every_gat_role_and_lead_kind():
    briefs = _role_briefs()
    for role in ("mukhada", "manjha", "antara", "amad", "taan_short", "taan_long", "intro", "outro"):
        assert briefs["roles"][role].strip(), f"missing roles.{role}"
    for kind in ("alaap", "melody", "taan", "solo", "outro"):
        assert briefs["kinds"][kind].strip(), f"missing kinds.{kind}"
    assert briefs["default"].strip()


def test_generate_lead_task_placeholders_all_supplied():
    # the prompt contract: every {placeholder} in the task config is a key inputs_for provides
    import re

    import yaml
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "crew", "config", "tasks.yaml")
    with open(cfg_path) as f:
        task = yaml.safe_load(f)["generate_lead"]
    arr = _arr(("lead", "drone"))
    inputs = _LeadContext(arr).inputs_for(section_spans(arr)[0], [])
    placeholders = set(re.findall(r"\{([a-z_]+)\}", task["description"] + task["expected_output"]))
    assert placeholders <= set(inputs), f"unfilled placeholders: {placeholders - set(inputs)}"


# --- the legality guardrail: the hard line -------------------------------------

# --- mizrab bols: apply_strokes realises the stroke as articulation ------------

def test_da_accents_and_ra_softens():
    da, ra = apply_strokes([LeadNote(swara="S", dur=1.0, vel=90, bol="da"),
                            LeadNote(swara="g", dur=1.0, vel=90, bol="ra")])
    assert da.vel > 90 and ra.vel < 90
    assert da.bol is None and ra.bol is None            # the bol is consumed


def test_diri_splits_into_a_double_stroke():
    out = apply_strokes([LeadNote(swara="m", dur=1.0, vel=90, bol="diri")])
    assert len(out) == 2
    assert out[0].dur + out[1].dur == 1.0               # total duration preserved
    assert out[0].vel > out[1].vel                       # da stronger than the ra
    assert all(n.swara == "m" for n in out)


def test_darada_splits_into_a_triplet():
    out = apply_strokes([LeadNote(swara="m", dur=1.5, vel=90, bol="darada")])
    assert len(out) == 3                                 # da-ra-da = three strokes
    assert round(sum(n.dur for n in out), 4) == 1.5      # total preserved
    assert out[0].vel > out[1].vel and out[2].vel > out[1].vel   # accents on the da's


def test_chikari_sounds_taar_sa_without_ornament():
    out = apply_strokes([LeadNote(swara="d", oct=0, dur=0.5, vel=90, bol="chikari",
                                  meend_swara="n", grace=["S"])])
    assert len(out) == 1
    assert out[0].swara == "S" and out[0].oct >= 1       # written swara ignored -> high Sa
    assert out[0].meend_swara is None and out[0].grace is None


def test_no_bol_passes_through_unchanged():
    n = LeadNote(swara="S", dur=1.0, vel=90)
    assert apply_strokes([n]) == [n]


def test_strokes_preserve_total_duration_for_placement():
    notes = [LeadNote(swara="S", dur=1.0, bol="diri"), LeadNote(swara="g", dur=2.0, bol="darada")]
    assert round(sum(n.dur for n in apply_strokes(notes)), 4) == 3.0


def test_guardrail_ignores_a_chikari_notes_written_swara():
    # 'R' is illegal in Malkauns, but on a chikari note it is IGNORED (chikari sounds taar Sa),
    # so the legality guardrail must not flag it
    phrase = LeadPhrase(phrase_plan=_plan(),
                        notes=[LeadNote(swara="d", dur=1.0),
                               LeadNote(swara="R", dur=0.5, bol="chikari")])
    ok, value = _lead_guardrail("malkauns")(_FakeOutput(phrase))
    assert ok is True and isinstance(value, LeadPhrase)


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
    phrase = LeadPhrase(phrase_plan=_plan("S"),
                        notes=[LeadNote(swara="S", dur=1.0, meend_swara="P")])
    ok, msg = _lead_guardrail("malkauns")(_FakeOutput(phrase))
    assert ok is False and "P" in msg


def test_guardrail_catches_an_illegal_cross_octave_meend_target():
    # A cross-octave glide must not blind the guardrail: an illegal target
    # (P is absent from Malkauns) is still caught.
    phrase = LeadPhrase(phrase_plan=_plan("S"),
                        notes=[LeadNote(swara="S", dur=1.0, meend_swara="P", meend_oct=1)])
    ok, msg = _lead_guardrail("malkauns")(_FakeOutput(phrase))
    assert ok is False and "P" in msg


def test_guardrail_enforces_the_direction_rule():
    # Bageshree's P is DESCENT-only (the aroha skips it): m -> P ascends into it and is
    # bounced with the rule named; D -> P -> m is the raga's own descent and passes.
    ok, msg = _lead_guardrail("bageshree")(_FakeOutput(_phrase("m", "P", "S")))
    assert ok is False and "DESCENT-only" in msg and "P" in msg
    ok, value = _lead_guardrail("bageshree")(_FakeOutput(_phrase("D", "P", "m")))
    assert ok is True and isinstance(value, LeadPhrase)


def test_guardrail_catches_a_meend_gliding_up_into_a_descent_only_swara():
    # the glide LANDS on its target, so a meend rising into Bageshree's P is an
    # ascending entry too
    phrase = LeadPhrase(phrase_plan=_plan("S"),
                        notes=[LeadNote(swara="m", dur=2.0, meend_swara="P")])
    ok, msg = _lead_guardrail("bageshree")(_FakeOutput(phrase))
    assert ok is False and "DESCENT-only" in msg


def test_raga_facts_state_the_direction_rule():
    from crew.lead import _render_raga_facts
    facts = _render_raga_facts("bageshree")
    assert "direction rule" in facts and "DESCENT" in facts and "P" in facts
    assert "direction rule" not in _render_raga_facts("malkauns")


def test_guardrail_checks_the_declared_seed_too():
    # The phrase_plan seed is part of what the phrase commits to, so an illegal seed swara
    # (P is absent from Malkauns) is caught even when every NOTE is legal.
    phrase = LeadPhrase(phrase_plan=_plan("S", "P"),
                        notes=[LeadNote(swara="S", dur=1.0)])
    ok, msg = _lead_guardrail("malkauns")(_FakeOutput(phrase))
    assert ok is False and "P" in msg


def test_lead_phrase_requires_a_plan_before_notes():
    # phrase_plan is REQUIRED — the model cannot emit notes without first committing a plan.
    try:
        LeadPhrase(notes=[LeadNote(swara="S", dur=1.0)])
        assert False, "expected a validation error for the missing phrase_plan"
    except Exception as e:  # noqa: BLE001
        assert "phrase_plan" in str(e)


def test_phrase_plan_rejects_an_unknown_seed_swara():
    try:
        PhrasePlan(seed=["S", "Z"], contour="arch", transformations=[], climax_and_sam="x")
        assert False, "expected a validation error for the unknown seed swara"
    except Exception as e:  # noqa: BLE001
        assert "seed" in str(e).lower()


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


def test_leadnote_coerces_junk_meend_swara_to_none():
    # LLMs express "no glide" as null or the STRING 'null'/'none'/'' — and a live run once
    # emitted ':' — ALL junk -> None (the note plays plain), so a stray meend can never
    # hard-fail a generation at the structured-output layer (see _clean_meend_swara).
    for junk in (None, "null", "none", "", ":", "Z", "S:+1"):
        assert LeadNote(swara="S", dur=1.0, meend_swara=junk).meend_swara is None
    # a real target still parses
    assert LeadNote(swara="S", dur=1.0, meend_swara="P").meend_swara == "P"


def test_leadnote_decorations_absorb_junk_and_alias_dir():
    # the same absorb-don't-raise rule for every OPTIONAL decoration: junk bols/ornaments/
    # graces degrade to plain notes; "dir" (the grid's name for the pair) maps to "diri"
    assert LeadNote(swara="S", dur=1.0, bol="dir").bol == "diri"
    assert LeadNote(swara="S", dur=1.0, bol="dara").bol == "darada"
    assert LeadNote(swara="S", dur=1.0, bol="pluck").bol is None
    assert LeadNote(swara="S", dur=1.0, ornament="trill").ornament is None
    assert LeadNote(swara="S", dur=1.0, grace=["S", "Z", "?"]).grace == ["S"]
    assert LeadNote(swara="S", dur=1.0, grace=["Z"]).grace is None


# --- the gat HEAD (mukhada): a cached, looping ~1-avartan cell -----------------

def _gat_arr(*specs: tuple[SectionKind, int, str], raga: str = "malkauns") -> Arrangement:
    """A chart whose sections carry a gat `form_role`. specs = (kind, bars, form_role); every
    section plays lead+drone. Kind ALAAP voices as solo sitar -> one clean lead layer to assert on."""
    sections = [Section(kind=k, bars=b, layers=["lead", "drone"], foreground="lead", form_role=fr)
                for (k, b, fr) in specs]
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


# The clean head's swaras, in order — the sequence tests assert placement against.
_HEAD_SWARAS = ["S", "m", "g", "d", "n", "d", "m", "g", "m", "S"]


def _good_head() -> LeadPhrase:
    # a mukhada that PASSES the gat verifier AND the stroke frame (bpm 72 -> masitkhani):
    # fills the 16-beat teentaal avartan, OPENS on S (the swara every sam restates, struck
    # "da"), lands on S, mixes note values, and carries the frame's dir doublings — double
    # attacks in matras 12 (beats 11-12) and 14 (beats 13-14) — with a bol on every note.
    # Its approach cut falls at beat 11 (the boundary nearest the 5-matra mukhda line), so
    # fills take beats 0-11 and the approach (n d m g m S) re-enters at 11.
    # Used wherever a test needs a clean head so the verify+repair is a no-op.
    return LeadPhrase(phrase_plan=_plan("S"),
                      notes=[LeadNote(swara="S", dur=4.0, bol="da"),
                             LeadNote(swara="m", dur=4.0, bol="da"),
                             LeadNote(swara="g", dur=2.0, bol="ra"),
                             LeadNote(swara="d", dur=1.0, bol="da"),
                             LeadNote(swara="n", dur=0.5, bol="da"),
                             LeadNote(swara="d", dur=0.5, bol="ra"),
                             LeadNote(swara="m", dur=1.0, bol="da"),
                             LeadNote(swara="g", dur=0.5, bol="da"),
                             LeadNote(swara="m", dur=0.5, bol="ra"),
                             LeadNote(swara="S", dur=2.0, bol="da")])


def _flat_head() -> LeadPhrase:
    # lands on Sa and fills the cycle, but every note is the same length -> 1 violation (flat)
    return LeadPhrase(phrase_plan=_plan("S"),
                      notes=[LeadNote(swara="S", dur=4.0), LeadNote(swara="m", dur=4.0),
                             LeadNote(swara="g", dur=4.0), LeadNote(swara="S", dur=4.0)])


def _worse_head() -> LeadPhrase:
    # a fragment, ends off a resting swara (n), and flat -> multiple violations
    return LeadPhrase(phrase_plan=_plan("S"),
                      notes=[LeadNote(swara="n", dur=2.0), LeadNote(swara="n", dur=2.0),
                             LeadNote(swara="n", dur=2.0)])


def _good_fill() -> LeadPhrase:
    # a taan fill that PASSES verify_fill for `_good_head` (an 11-beat front cut): 44
    # sixteenths (0.25) summing to exactly 11, resolving onto n — the swara the head's
    # APPROACH re-enters on at beat 11 (the fill now takes the FRONT of the avartan; the
    # head's own tail lands the next sam).
    swaras = (["m", "g", "m", "d", "n", "d", "m", "g"] * 6)[:43] + ["n"]
    return LeadPhrase(phrase_plan=_plan("m"),
                      notes=[LeadNote(swara=s, dur=0.25) for s in swaras])


def _good_manjha() -> LeadPhrase:
    # a manjha that PASSES verify_manjha against `_good_head()` over the SHORTENED (~12-beat, sub-
    # cycle) window: DIPS into the mandra, stays out of the taar, varied durations, and ends ON the
    # head's first swara (S). Sums to 11.5 beats — inside the shortened manjha window.
    return LeadPhrase(phrase_plan=_plan("d"),
                      notes=[LeadNote(swara="d", dur=1.5, oct=-1), LeadNote(swara="n", dur=1.5, oct=-1),
                             LeadNote(swara="m", dur=2.0), LeadNote(swara="g", dur=1.5),
                             LeadNote(swara="m", dur=2.0), LeadNote(swara="g", dur=1.0),
                             LeadNote(swara="S", dur=2.0)])


def test_is_mukhada_reads_the_form_role():
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"), (SectionKind.ALAAP, 1, "manjha"))
    assert is_mukhada(arr.sections[0]) is True
    assert is_mukhada(arr.sections[1]) is False


def test_generate_lead_writes_the_mukhada_as_ONE_avartan():
    # the LLM is asked for exactly one cycle (bars coerced to 1), not the whole multi-bar window.
    # A 3-bar mukhada also earns a taan FILL, generated right after the head (the second call).
    arr = _gat_arr((SectionKind.ALAAP, 3, "mukhada"))
    fn, calls = _fake([_good_head(), _good_fill()])
    generate_lead(arr, gen_fn=fn)
    assert calls[0].section.bars == 1                       # a one-avartan gen window
    assert calls[0].length == arr.beats_per_bar             # ...spanning a single cycle
    assert calls[1].length == 11.0                          # the fill: the avartan's FRONT, up to
    assert calls[1].section.form_role == "taan_short"       # the head's approach cut (beat 11)


def test_generate_lead_loops_the_mukhada_cell_across_its_bars():
    # code repeats the one-cycle cell across every bar so each avartan re-lands on the sam
    arr = _gat_arr((SectionKind.ALAAP, 2, "mukhada"))       # teentaal -> 16-beat cycles
    fn, _ = _fake([_good_head()])                           # a clean 16-beat head
    layers, _ = generate_lead(arr, gen_fn=fn)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    assert len(notes) == 20                                 # the 10-note cell placed in both bars
    bar0 = [n.swara for n in notes if n.start < 16.0]
    bar1 = [n.swara for n in notes if n.start >= 16.0]
    assert bar0 == bar1 == _HEAD_SWARAS                     # looped verbatim, each avartan on the sam
    assert min(n.start for n in notes if n.start >= 16.0) == 16.0


def test_generate_lead_reuses_the_cached_mukhada_on_return():
    # mukhada -> manjha -> mukhada: the RETURN reuses the cached head, so gen_fn fires only twice
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "manjha"),
                   (SectionKind.ALAAP, 1, "mukhada"))
    fn, calls = _fake([_good_head(), _good_manjha()])        # only TWO phrases: proves the 3rd reused
    layers, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2                                    # the returning mukhada did NOT call gen_fn
    reprises = [e for e in events if e.data.get("reprise")]
    assert len(reprises) == 1 and reprises[0].agent == "Lead"


def test_returning_mukhada_is_verbatim_the_head():
    # the whole point: the return is IDENTICAL to the head (not a regenerated near-miss)
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "mukhada"))
    fn, _ = _fake([_good_head()])                            # one head; the return reuses it
    layers, _ = generate_lead(arr, gen_fn=fn)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    head = [n.swara for n in notes if n.start < 16.0]
    ret = [n.swara for n in notes if n.start >= 16.0]
    assert head == ret == _HEAD_SWARAS


def test_non_mukhada_roles_are_not_looped():
    # a manjha is composed once across its (short, sub-cycle) window — not a looped cell
    arr = _gat_arr((SectionKind.ALAAP, 2, "manjha"))
    manjha = LeadPhrase(phrase_plan=_plan("d"),
                        notes=[LeadNote(swara="d", dur=2.0, oct=-1), LeadNote(swara="n", dur=1.5, oct=-1),
                               LeadNote(swara="m", dur=2.0), LeadNote(swara="g", dur=1.5),
                               LeadNote(swara="m", dur=2.0), LeadNote(swara="S", dur=2.5)])
    fn, calls = _fake([manjha])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert calls[0].section.bars == 2                        # the section's bars are NOT coerced to 1
    assert len(layers[0].notes) == 6                         # placed once, not looped per bar


# --- gat verifier repair: a weak mukhada is RE-ROLLED before it's cached (fix #4) -

def test_generate_lead_rerolls_a_weak_mukhada_and_keeps_the_clean_one():
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, calls = _fake([_flat_head(), _good_head()])         # first weak, the re-roll lands clean
    layers, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2                                   # the hook was re-rolled once
    swaras = [n.swara for n in sorted(layers[0].notes, key=lambda n: n.start)]
    assert swaras == _HEAD_SWARAS                            # the CLEAN head is what got placed
    rr = [e for e in events if e.data.get("gat_verify")]
    assert len(rr) == 1 and rr[0].data["tries"] == 2 and rr[0].data["violations"] == []


def test_generate_lead_keeps_best_of_n_when_every_hook_is_weak():
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, calls = _fake([_worse_head(), _flat_head()])        # both weak; the flat one flags FEWER
    layers, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2
    rr = next(e for e in events if e.data.get("gat_verify"))
    assert rr.data["violations"]                            # kept the best-of-N, but it still flags
    assert len(layers[0].notes) == 4                        # the flat head (fewer viol), not the fragment


def test_generate_lead_accepts_a_clean_mukhada_without_rerolling():
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, calls = _fake([_good_head()])
    layers, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 1                                   # clean on the first try -> no re-roll
    assert not any(e.data.get("gat_verify") for e in events)


def test_reroll_feeds_the_violations_back_to_the_generator():
    # the repair is TARGETED, not blind: the failed head's violations reach the next attempt
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, _ = _fake([_flat_head(), _good_head()])
    generate_lead(arr, gen_fn=fn)
    assert fn.seen_feedback[0] is None                       # first attempt: no feedback
    assert fn.seen_feedback[1] and any("note value" in v for v in fn.seen_feedback[1])  # re-roll sees the flaw


def test_non_mukhada_generation_gets_no_repair_feedback():
    arr = _gat_arr((SectionKind.ALAAP, 1, "manjha"))
    fn, _ = _fake([_phrase("d", "n")])
    generate_lead(arr, gen_fn=fn)
    assert fn.seen_feedback == [None]                        # a manjha is never in the repair loop


# --- rest / nyas: a SILENT beat the lead can rest on ---------------------------

def test_leadnote_accepts_a_rest():
    n = LeadNote(swara="S", dur=1.0, rest=True)
    assert n.rest is True


def test_place_phrase_skips_a_rest_but_keeps_its_time():
    # the rest occupies its duration (the next note lands after it) but sounds nothing
    notes = [LeadNote(swara="S", dur=2.0), LeadNote(swara="S", dur=2.0, rest=True),
             LeadNote(swara="m", dur=2.0)]
    placed = place_phrase(notes, start=0.0, end=16.0, register=0)
    assert [(n.swara, n.start) for n in placed] == [("S", 0.0), ("m", 4.0)]  # rest silent, time held


def test_apply_strokes_passes_a_rest_through_untouched():
    rest = LeadNote(swara="S", dur=1.0, rest=True)
    assert apply_strokes([rest]) == [rest]


def test_guardrail_ignores_a_rests_placeholder_swara():
    # 'P' is illegal in Malkauns, but on a REST it sounds nothing, so the guardrail must not flag it
    phrase = LeadPhrase(phrase_plan=_plan(),
                        notes=[LeadNote(swara="d", dur=1.0),
                               LeadNote(swara="P", dur=1.0, rest=True)])
    ok, value = _lead_guardrail("malkauns")(_FakeOutput(phrase))
    assert ok is True and isinstance(value, LeadPhrase)


def test_render_previous_marks_a_rest_as_a_dash():
    memory = [LeadMemo("mukhada", LeadPhrase(phrase_plan=_plan("S"),
                                             notes=[LeadNote(swara="S", dur=1.0),
                                                    LeadNote(swara="S", dur=1.0, rest=True)]))]
    assert "S -" in _render_previous(memory)


# --- andolan: code flags the raga's oscillating komal swaras on HELD notes ------

def test_place_phrase_flags_andolan_on_a_held_raga_swara():
    notes = [LeadNote(swara="g", dur=2.0), LeadNote(swara="m", dur=2.0)]
    placed = place_phrase(notes, start=0.0, end=16.0, register=0, andolan_swaras=frozenset({"g"}))
    assert placed[0].andolan is True          # a held andolan swara sways
    assert placed[1].andolan is None          # m is not one the raga oscillates


def test_place_phrase_no_andolan_on_a_short_note():
    placed = place_phrase([LeadNote(swara="g", dur=0.25)], start=0.0, end=16.0, register=0,
                          andolan_swaras=frozenset({"g"}))
    assert placed[0].andolan is None          # too short to read as a slow sway


def test_place_phrase_andolan_composes_with_a_meend_resting_on_the_swara():
    # "R -> g~~": the note attacks on R and RESTS on ga, so it sways — the renderer
    # composes glide + settle + sway (the research-correct Darbari entry; a struck
    # kan grace here reads as krintan)
    placed = place_phrase([LeadNote(swara="R", dur=2.0, meend_swara="g")], start=0.0, end=16.0,
                          register=0, andolan_swaras=frozenset({"g"}))
    assert placed[0].meend_swara == "g" and placed[0].andolan is True


def test_place_phrase_no_andolan_when_the_meend_glides_away_from_the_swara():
    # "g -> m" spends its hold on ma, not ga — nothing sways
    placed = place_phrase([LeadNote(swara="g", dur=2.0, meend_swara="m")], start=0.0, end=16.0,
                          register=0, andolan_swaras=frozenset({"g"}))
    assert placed[0].meend_swara == "m" and placed[0].andolan is None


def test_place_phrase_no_andolan_without_a_raga_set():
    # the default (empty) set -> nothing sways (the Bhairavi/Malkauns path, andolan == [])
    placed = place_phrase([LeadNote(swara="g", dur=2.0)], start=0.0, end=16.0, register=0)
    assert placed[0].andolan is None


def test_lead_layers_from_applies_the_ragas_andolan_swaras():
    arr = _arr(("lead", "drone"), raga="darbari")      # darbari sways komal g and d
    layers = lead_layers_from({0: _phrase("g", "m", dur=2.0)}, arr)
    g = next(n for n in layers[0].notes if n.swara == "g")
    m = next(n for n in layers[0].notes if n.swara == "m")
    assert g.andolan is True and m.andolan is None


# --- murki/khatka: an LLM-CHOSEN ornament, realised legally from raga neighbours -

def test_apply_ornaments_realises_a_murki_as_a_neighbour_cluster():
    # a murki on komal g in Bhairavi: upper (m) + lower (r) neighbour crushed, then the note
    out = apply_ornaments([LeadNote(swara="g", dur=2.0, ornament="murki")], "bhairavi")
    assert [n.swara for n in out] == ["m", "r", "g"]        # neighbours (legal), then the main note
    assert round(sum(n.dur for n in out), 4) == 2.0         # total duration preserved
    assert out[-1].ornament is None                          # the ornament is consumed


def test_khatka_is_heavier_and_eats_more_of_the_note_than_a_murki():
    murki = apply_ornaments([LeadNote(swara="g", dur=2.0, vel=90, ornament="murki")], "bhairavi")
    khatka = apply_ornaments([LeadNote(swara="g", dur=2.0, vel=90, ornament="khatka")], "bhairavi")
    assert murki[0].vel < 90 < khatka[0].vel                 # murki softer, khatka accented
    assert khatka[-1].dur < murki[-1].dur                    # khatka's cluster eats more of the note


def test_apply_ornaments_strips_the_flag_on_a_raga_that_does_not_use_them():
    # malkauns uses meend/andolan, NOT murki/khatka -> flag dropped, the note plays plain
    out = apply_ornaments([LeadNote(swara="g", dur=2.0, ornament="murki")], "malkauns")
    assert len(out) == 1 and out[0].swara == "g" and out[0].ornament is None


def test_apply_ornaments_skips_a_note_too_short_to_wrap():
    out = apply_ornaments([LeadNote(swara="g", dur=0.25, ornament="murki")], "bhairavi")
    assert len(out) == 1 and out[0].ornament is None


def test_apply_ornaments_passes_plain_notes_through():
    n = LeadNote(swara="g", dur=2.0)
    assert apply_ornaments([n], "bhairavi") == [n]


def test_lead_layers_from_realises_ornaments_end_to_end():
    arr = _arr(("lead", "drone"), raga="bhairavi")     # bhairavi uses murki/khatka
    phrase = LeadPhrase(phrase_plan=_plan("g"),
                        notes=[LeadNote(swara="g", oct=0, dur=2.0, ornament="murki")])
    layers = lead_layers_from({0: phrase}, arr)
    swaras = [n.swara for n in sorted(layers[0].notes, key=lambda n: n.start)]
    assert swaras == ["m", "r", "g"]                    # the cluster then the main note, all placed


def test_leadnote_accepts_and_normalises_an_ornament():
    assert LeadNote(swara="g", dur=1.0, ornament="murki").ornament == "murki"
    for junk in (None, "null", "none", ""):
        assert LeadNote(swara="g", dur=1.0, ornament=junk).ornament is None


def test_noop_meends_are_stripped_at_placement():
    # meend_swara == the written pitch is schema over-fill, not a glide — placement strips
    # it; a REAL meend (target differs) passes through for the renderer's target-anchored pull
    arr = _arr(("lead", "drone"))
    phrase = LeadPhrase(phrase_plan=_plan("g"),
                        notes=[LeadNote(swara="g", dur=2.0, meend_swara="g"),   # no-op
                               LeadNote(swara="m", dur=2.0, meend_swara="g")])  # real glide
    layers = lead_layers_from({0: phrase}, arr)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    assert notes[0].meend_swara is None
    assert notes[1].meend_swara == "g"


# --- the intro/alap: verified, generated into a SHORTENED window ------------------

def _good_intro() -> LeadPhrase:
    # passes verify_intro (the alap-VISTAR shape): THREE tension-holding phrases developing the
    # ONE motif (n S) — each ends AWAY from home — separated by real rests with the mandra Sa
    # PLUCKED between them; opens on Sa, the melodic line dips into the mandra, STATES the
    # pakad, widest reach (m) late, and only the FINAL phrase comes home. The final Sa starts
    # at beat 13.0 and the cell is 16 beats, so the shortened-window / ring-out tests hold.
    return LeadPhrase(phrase_plan=_plan("n", "S"),
                      notes=[LeadNote(swara="S", dur=0.5), LeadNote(swara="n", dur=1.0, oct=-1),
                             LeadNote(swara="S", dur=0.5), LeadNote(swara="d", dur=1.0, oct=-1),
                             LeadNote(swara="S", dur=1.0, rest=True),
                             LeadNote(swara="S", dur=0.5, oct=-1),               # the low pluck
                             LeadNote(swara="S", dur=1.0, rest=True),
                             LeadNote(swara="d", dur=0.5, oct=-1), LeadNote(swara="n", dur=0.5, oct=-1),
                             LeadNote(swara="S", dur=0.5), LeadNote(swara="g", dur=1.5),
                             LeadNote(swara="S", dur=1.0, rest=True),
                             LeadNote(swara="S", dur=0.5, oct=-1),               # the low pluck
                             LeadNote(swara="S", dur=1.0, rest=True),
                             LeadNote(swara="g", dur=0.5), LeadNote(swara="m", dur=1.0),
                             LeadNote(swara="g", dur=0.5), LeadNote(swara="S", dur=3.0)])


def test_intro_is_generated_into_a_shortened_window():
    # the trailing pause is CODE's: the alap is asked for LESS than its section window
    # (2 teentaal bars = 32 beats; the gap is min(cycle 16, 32 * 0.35) = 11.2)
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    fn, calls = _fake([_good_intro()])
    generate_lead(arr, gen_fn=fn)
    assert calls[0].length == 32 - 11.2


def test_intro_final_sa_rings_through_the_reserved_gap():
    # the 16-beat alap cell's LAST Sa is extended by code to ring (with a fade) across the
    # reserved tail of the 32-beat window — the "struck chord dying away" resolution; every
    # other note stays inside the shortened window
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    fn, _ = _fake([_good_intro()])
    layers, _ = generate_lead(arr, gen_fn=fn)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    last = notes[-1]
    assert last.swara == "S" and last.start == 13.0
    assert last.start + last.dur == 32.0 and last.fade is True   # rings to the section edge
    assert all(n.start + n.dur <= 16.0 for n in notes[:-1])      # the rest end in the window


def test_live_beats_stream_from_inside_the_lead_stage():
    # per-call progress (Sujit's live note): a sink installed around generate_lead hears a
    # RUNNING beat for the cell AND for its re-roll — the UI shows work as it happens, not
    # one flood when the flow node completes. Without a sink, beats are free no-ops.
    from crew.contracts import EventType
    from crew.live import live_sink
    bad = _phrase("g", "m", "d", "n", dur=2.0)
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    seen: list = []
    fn, _ = _fake([bad, _good_intro()])
    with live_sink(seen.append):
        generate_lead(arr, gen_fn=fn)
    running = [e for e in seen if e.type == EventType.RUNNING]
    assert any("composing the intro" in e.text for e in running)
    reroll = next(e for e in running if "re-rolling the intro" in e.text)
    assert "flagged:" in reroll.text and "Sa" in reroll.text      # the ticker SAYS WHY
    assert reroll.data["violations"]                              # ...and carries the full list


def test_intro_is_verified_and_rerolled_with_feedback():
    # a wandering alap (never resolves to Sa) is bounced; the re-roll sees WHY
    bad = _phrase("g", "m", "d", "n", dur=2.0)               # no Sa anywhere, no rests
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    fn, calls = _fake([bad, _good_intro()])
    _, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2
    assert fn.seen_feedback[1] and any("Sa" in v for v in fn.seen_feedback[1])
    rr = next(e for e in events if e.data.get("gat_verify"))
    assert rr.data["cell"] == "intro"


# --- the intro alap LOCKS to the clean arpeggio (Sujit 2026-07-19, avartan-locked) ------

def _intro_arr(*, clean: bool, bars: int = 4) -> Arrangement:
    """A one-section intro chart (teentaal, 16-beat cycles). With `clean` the intro carries the
    arpeggio the alap should lock to; without it, the old flush-left placement stands."""
    layers = ["lead", "clean", "drone"] if clean else ["lead", "drone"]
    sec = Section(kind=SectionKind.ALAAP, bars=bars, layers=layers,
                  foreground="lead", form_role="intro")
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=[sec])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def test_next_sam_snaps_forward_to_the_avartan_grid():
    assert _next_sam(0.0, origin=0.0, cycle_beats=16.0) == 0.0     # already on a sam
    assert _next_sam(0.01, origin=0.0, cycle_beats=16.0) == 16.0   # just past -> next sam
    assert _next_sam(16.0, origin=0.0, cycle_beats=16.0) == 16.0   # exactly on a sam
    assert _next_sam(20.0, origin=0.0, cycle_beats=16.0) == 32.0
    assert _next_sam(5.0, origin=4.0, cycle_beats=16.0) == 20.0    # grid anchored at origin 4


def test_split_phrases_breaks_on_long_rests_only():
    # a >= 1-beat rest ends a phrase (a real breath); a shorter rest stays inside as a micro-gap
    notes = [LeadNote(swara="S", dur=2.0), LeadNote(swara="g", dur=0.5, rest=True),
             LeadNote(swara="m", dur=2.0), LeadNote(swara="S", dur=1.0, rest=True),
             LeadNote(swara="d", dur=2.0), LeadNote(swara="S", dur=3.0)]
    phrases = _split_phrases(notes)
    assert len(phrases) == 2                                       # only the 1.0 rest splits
    assert [n.swara for n in phrases[0]] == ["S", "g", "m"]        # the 0.5 rest is kept inside
    assert [n.swara for n in phrases[1]] == ["d", "S"]


def test_place_intro_phrases_starts_each_phrase_on_a_sam():
    sec = Section(kind=SectionKind.ALAAP, bars=5, layers=["lead", "clean", "drone"],
                  foreground="lead", form_role="intro")
    section_span = SectionSpan(index=0, section=sec, start=0.0, end=80.0)
    gen_span = SectionSpan(index=0, section=sec, start=16.0, end=64.0)   # lead-in 1 avartan
    notes = [LeadNote(swara="S", dur=2.0), LeadNote(swara="g", dur=2.0),
             LeadNote(swara="S", dur=1.5, rest=True),
             LeadNote(swara="m", dur=2.0), LeadNote(swara="d", dur=2.0),
             LeadNote(swara="S", dur=1.5, rest=True),
             LeadNote(swara="S", dur=3.0)]
    placed = _place_intro_phrases(notes, gen_span=gen_span, section_span=section_span,
                                  register=0, cycle_beats=16.0)
    starts = [n.start for n in placed]
    # phrase A at the lead-in sam (16), B nudged to the next sam past A's end (32), C to 48
    assert starts == [16.0, 18.0, 32.0, 34.0, 48.0]
    assert placed[0].start == 16.0                                # no note in the lead-in bar


def test_intro_alap_locks_to_the_clean_arpeggio_cycle():
    # with the clean arpeggio present: bar 0 is arpeggio ALONE (no lead), and every alap phrase
    # begins on a sam (a multiple of the 16-beat cycle), then the final Sa rings to the edge
    arr = _intro_arr(clean=True, bars=4)
    layers = lead_layers_from({0: _good_intro()}, arr)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    assert notes[0].start == 16.0                                 # lead-in: nothing sounds in bar 0
    on_sam = {n.start for n in notes if n.start % 16.0 == 0.0}
    assert {16.0, 32.0, 48.0} <= on_sam                           # a phrase begins on each sam
    assert notes[-1].swara == "S" and notes[-1].fade is True      # resolves, rings out
    assert notes[-1].start + notes[-1].dur == 64.0                # to the section edge


def test_intro_without_the_clean_arpeggio_stays_flush_left():
    # no arpeggio to lock to -> the old behavior: the alap starts at the section head (beat 0)
    arr = _intro_arr(clean=False, bars=4)
    layers = lead_layers_from({0: _good_intro()}, arr)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    assert notes[0].start == 0.0                                  # flush-left, no lead-in


def test_intro_gen_span_reserves_a_lead_in_only_with_the_clean_arpeggio():
    span_clean = list(section_spans(_intro_arr(clean=True, bars=4)))[0]
    span_plain = list(section_spans(_intro_arr(clean=False, bars=4)))[0]
    assert _intro_gen_span(span_clean, 16.0).start == 16.0        # one avartan of lead-in
    assert _intro_gen_span(span_plain, 16.0).start == 0.0         # none without the arpeggio


# --- the mukhada taan FILLS: distinct cells, spliced into the middle statements --

def test_fills_are_distinct_and_spliced_into_the_middle_bars():
    # 4 bars of mukhada: bars 0 and 3 state the whole head; bars 1 and 2 are CUT the way the
    # tradition cuts them — the taan takes the FRONT of the avartan (launching from the sam)
    # and the head's APPROACH (its final ~5 matras) re-enters to land the next sam. Each cut
    # gets a DIFFERENT taan — ONE fill is generated by the LLM, the second is a DETERMINISTIC
    # in-raga variant (retrograde), no extra call; the variants rotate across the cuts.
    arr = _gat_arr((SectionKind.ALAAP, 4, "mukhada"))
    fn, calls = _fake([_good_head(), _good_fill()])
    layers, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2                                   # the head + ONE generated fill (not three)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    cut1 = [n for n in notes if 16.0 <= n.start < 27.0]      # bar 1's FRONT (16 + the 11-beat cut)
    cut2 = [n for n in notes if 32.0 <= n.start < 43.0]      # bar 2's FRONT (32 + 11)
    assert len(cut1) == 44 and all(n.dur <= 0.25 for n in cut1)
    assert len(cut2) == 44 and all(n.dur <= 0.25 for n in cut2)
    assert [n.swara for n in cut1] != [n.swara for n in cut2]   # base vs deterministic variant
    approach1 = [n.swara for n in notes if 27.0 <= n.start < 32.0]
    assert approach1 == _HEAD_SWARAS[4:]                     # the head's approach re-enters at beat 11
    head_restated = [n.swara for n in notes if 48.0 <= n.start < 64.0]
    assert head_restated == _HEAD_SWARAS                     # bar 3: the head, whole
    fill_events = [e for e in events if e.data.get("fill")]
    assert len(fill_events) == 1 and fill_events[0].data["count"] == 2


def test_short_mukhada_sections_get_no_fill():
    # 2 bars is too short to spare a statement — every bar states the whole head
    arr = _gat_arr((SectionKind.ALAAP, 2, "mukhada"))
    fn, calls = _fake([_good_head()])
    layers, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 1                                   # no fill was requested
    assert not [e for e in events if e.data.get("fill")]


# --- the manjha: verified against the cached head (cross-cell awareness) ---------

def test_manjha_is_verified_and_rerolled_with_the_seam_feedback():
    # a manjha that dies early is bounced; the re-roll is told to reach the closing sam
    bad = _phrase("d", "n", dur=2.0)                         # 4 of 16 beats — nowhere near the sam
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "manjha"))
    fn, calls = _fake([_good_head(), bad, _good_manjha()])
    _, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 3                                   # head + manjha + one re-roll
    assert fn.seen_feedback[2] and any("sam" in v for v in fn.seen_feedback[2])
    rr = next(e for e in events if e.data.get("gat_verify"))
    assert rr.data["cell"] == "manjha"


# --- the WHOLE gat: mukhada + manjha + antara composed as ONE object, per-part repair ----------

def _fake_gat(gat: Gat):
    """A fake gat_fn: returns a canned Gat and records the needs-flags it was asked for."""
    calls: list[dict] = []

    def fn(arr, *, needs_manjha, needs_antara, needs_amad):
        calls.append({"needs_manjha": needs_manjha, "needs_antara": needs_antara,
                      "needs_amad": needs_amad})
        return gat

    return fn, calls


def test_whole_gat_composes_the_parts_together_and_uses_them():
    # a joint gat with clean parts: the mukhada + manjha come from ONE gat_fn call, and the
    # per-section gen_fn is not called at all (the whole gat was composed together)
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "manjha"),
                   (SectionKind.ALAAP, 2, "mukhada"))
    gat = Gat(anchor="d n S", mukhada=_good_head(), manjha=_good_manjha())
    gfn, gcalls = _fake_gat(gat)
    fn, calls = _fake([])                                    # gen_fn must NOT be called
    layers, events = generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert gcalls == [{"needs_manjha": True, "needs_antara": False,
                       "needs_amad": False}]                # ONE joint call, right parts
    assert calls == []                                      # no per-section lead generation
    assert any(e.data.get("gat") for e in events)           # the "composed as one object" beat
    assert layers and layers[0].notes                       # the parts were placed


def test_whole_gat_repairs_a_failing_part_in_isolation():
    # the joint gat's manjha never dips to the mandra -> it is regenerated IN ISOLATION via gen_fn,
    # while the good mukhada is kept (nobody rewrites a whole gat for one weak part)
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"), (SectionKind.ALAAP, 1, "manjha"))
    bad_manjha = LeadPhrase(phrase_plan=_plan("m"),         # all madhya -> fails "dip into the mandra"
                            notes=[LeadNote(swara="m", dur=2.0), LeadNote(swara="g", dur=2.0),
                                   LeadNote(swara="m", dur=2.0), LeadNote(swara="g", dur=1.5),
                                   LeadNote(swara="m", dur=2.0), LeadNote(swara="S", dur=2.0)])
    gfn, _ = _fake_gat(Gat(mukhada=_good_head(), manjha=bad_manjha))
    fn, calls = _fake([_good_manjha()])                     # gen_fn regenerates ONLY the manjha
    layers, events = generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert len(calls) == 1                                  # exactly one per-part regen (mukhada kept)
    assert any("gat" in (e.data.get("cell") or "") for e in events)   # a per-part repair event


def test_whole_gat_is_skipped_without_a_mukhada():
    # no mukhada -> nothing to compose jointly; gat_fn is never called, the intro falls back per-section
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    gfn, gcalls = _fake_gat(Gat(mukhada=_good_head()))
    fn, _ = _fake([_good_intro()])
    generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert gcalls == []                                     # no mukhada -> gat_fn not called


def test_intro_sees_the_head_it_must_tease():
    # WHOLE-GAT path: the head is composed FIRST, so the intro is generated KNOWING it — the
    # head memo rides the intro's memory (feeding the {mukhada_head} tease block) and the
    # verifier accepts a motif drawn from the head's swaras (n S appears in d n S m ...).
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"), (SectionKind.ALAAP, 1, "mukhada"))
    head = LeadPhrase(phrase_plan=_plan("d"),                # contains "n S" — _good_intro's motif —
                      notes=[LeadNote(swara="S", dur=4.0, bol="da"),      # and passes head + frame
                             LeadNote(swara="d", dur=2.0, bol="da"),
                             LeadNote(swara="n", dur=2.0, bol="ra"),
                             LeadNote(swara="S", dur=2.0, bol="da"),
                             LeadNote(swara="d", dur=1.0, bol="ra"),
                             LeadNote(swara="n", dur=0.5, bol="da"),
                             LeadNote(swara="d", dur=0.5, bol="ra"),
                             LeadNote(swara="m", dur=1.0, bol="da"),
                             LeadNote(swara="g", dur=0.5, bol="da"),
                             LeadNote(swara="m", dur=0.5, bol="ra"),
                             LeadNote(swara="S", dur=2.0, bol="da")])
    gfn, _ = _fake_gat(Gat(mukhada=head))
    fn, calls = _fake([_good_intro()])
    generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert len(calls) == 1                                  # the teasing intro passed first try
    assert any(m.form_role == "mukhada" for m in fn.seen_memory[0])   # the intro SAW the head


def test_intro_motif_is_rerolled_when_not_drawn_from_the_head():
    # the head never sounds "n S" as a phrase (its n sits four notes from its closing S), so
    # _good_intro's motif (n S) teases the WRONG tune — bounced, and the re-roll (told exactly
    # why) derives its motif from the head instead
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"), (SectionKind.ALAAP, 1, "mukhada"))
    gfn, _ = _fake_gat(Gat(mukhada=_good_head()))
    teasing = LeadPhrase(
        phrase_plan=_plan("g", "S"),
        notes=[LeadNote(swara="S", dur=1.0), LeadNote(swara="g", dur=1.0), LeadNote(swara="S", dur=1.5),
               LeadNote(swara="S", dur=1.5, rest=True),
               LeadNote(swara="d", dur=1.0, oct=-1), LeadNote(swara="n", dur=1.0, oct=-1),
               LeadNote(swara="g", dur=1.0), LeadNote(swara="S", dur=1.5),
               LeadNote(swara="m", dur=1.5, rest=True),
               LeadNote(swara="g", dur=1.0), LeadNote(swara="m", dur=1.0),
               LeadNote(swara="g", dur=0.5), LeadNote(swara="S", dur=2.5)])
    fn, calls = _fake([_good_intro(), teasing])
    generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert len(calls) == 2
    assert fn.seen_feedback[1] and any("not drawn from the mukhada head" in v
                                       for v in fn.seen_feedback[1])


# --- the antara: verified arc (quote -> climb -> late peak -> descend to Sa) -----

def _good_antara() -> LeadPhrase:
    # quotes the head (S m g S), climbs to a late taar peak, descends to madhya Sa —
    # and fills its 16-beat window exactly (end-anchored cells must not overrun)
    return LeadPhrase(phrase_plan=_plan("S"),
                      notes=[LeadNote(swara="S", dur=1.5), LeadNote(swara="m", dur=1.0),
                             LeadNote(swara="g", dur=1.0), LeadNote(swara="S", dur=1.5),
                             LeadNote(swara="d", dur=1.0), LeadNote(swara="n", dur=1.0),
                             LeadNote(swara="S", dur=1.0, oct=1), LeadNote(swara="g", dur=1.5, oct=1),
                             LeadNote(swara="m", dur=1.0, oct=1), LeadNote(swara="g", dur=1.0, oct=1),
                             LeadNote(swara="S", dur=0.5, oct=1), LeadNote(swara="n", dur=1.0),
                             LeadNote(swara="d", dur=1.0), LeadNote(swara="S", dur=2.0)])


def test_antara_is_verified_and_rerolled_with_the_arc_feedback():
    # a "new tune in the taar" antara is bounced; the re-roll is told to quote the head
    bad = LeadPhrase(phrase_plan=_plan("d"),
                     notes=[LeadNote(swara="d", dur=2.0), LeadNote(swara="n", dur=1.5),
                            LeadNote(swara="g", dur=2.0, oct=1), LeadNote(swara="n", dur=2.0),
                            LeadNote(swara="d", dur=1.0), LeadNote(swara="S", dur=3.0)])
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "antara"))
    fn, calls = _fake([_good_head(), bad, _good_antara()])
    _, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 3                                   # head + antara + one re-roll
    assert fn.seen_feedback[2] and any("quote" in v for v in fn.seen_feedback[2])
    rr = next(e for e in events if e.data.get("gat_verify"))
    assert rr.data["cell"] == "antara"


# --- the developed taan (taan_long): verified peak ------------------------------

def test_taan_long_is_verified_and_rerolled_with_feedback():
    # an even wall of quarter notes is NOT a taan — bounced with the exact reasons;
    # the arrangement motif for _gat_arr is d n S m, so the good taan must quote it
    bad = _phrase("d", "n", "S", "m", dur=1.0)
    good = LeadPhrase(phrase_plan=_plan("d"),
                      notes=[LeadNote(swara="d", dur=0.5), LeadNote(swara="n", dur=0.5),
                             LeadNote(swara="S", dur=0.5), LeadNote(swara="m", dur=0.5),
                             LeadNote(swara="m", dur=2.0),
                             LeadNote(swara="g", dur=0.25), LeadNote(swara="m", dur=0.25),
                             LeadNote(swara="d", dur=0.25), LeadNote(swara="n", dur=0.25),
                             LeadNote(swara="g", dur=0.25), LeadNote(swara="m", dur=0.25),
                             LeadNote(swara="d", dur=0.25), LeadNote(swara="n", dur=0.25),
                             LeadNote(swara="d", dur=0.25), LeadNote(swara="n", dur=0.25),
                             LeadNote(swara="S", dur=0.25, oct=1), LeadNote(swara="g", dur=0.25, oct=1),
                             LeadNote(swara="m", dur=1.0, oct=1),
                             LeadNote(swara="g", dur=0.5, oct=1), LeadNote(swara="S", dur=0.5, oct=1),
                             LeadNote(swara="n", dur=0.5), LeadNote(swara="d", dur=0.5),
                             LeadNote(swara="m", dur=1.0), LeadNote(swara="g", dur=0.5),
                             LeadNote(swara="S", dur=3.0)])
    arr = _gat_arr((SectionKind.TAAN, 1, "taan_long"))
    fn, calls = _fake([bad, good])
    _, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2
    assert fn.seen_feedback[1] and any("burst" in v for v in fn.seen_feedback[1])
    rr = next(e for e in events if e.data.get("gat_verify"))
    assert rr.data["cell"] == "taan_long"


def test_mukhada_cell_rides_the_event_stream():
    # cross-voice seeding seam: the cached head is fished back from the events the lead
    # already returns, so the riff can reduce it with no signature change
    from crew.lead import mukhada_cell_from_events
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, _ = _fake([_good_head()])
    _, events = generate_lead(arr, gen_fn=fn)
    cell = mukhada_cell_from_events(events)
    assert cell is not None
    assert [n.swara for n in cell.notes] == _HEAD_SWARAS
    assert mukhada_cell_from_events([]) is None


def test_mukhada_voices_unison_whatever_its_kind():
    # the head doubles sitar+guitar even on a kind that voices solo sitar — the verbatim
    # return must carry the same presence as the first statement (Sujit, 2026-07-16)
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, _ = _fake([_good_head()])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 2                                      # sitar + lead guitar
    sitar, guitar = layers
    assert [(n.swara, n.start) for n in sitar.notes] == \
           [(n.swara, n.start) for n in guitar.notes]            # a true unison double


def test_manjha_memory_labels_the_head():
    # the manjha's memory names the mukhada, so the prompt can render THE GAT HEAD block
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "manjha"))
    fn, _ = _fake([_good_head(), _good_manjha()])
    generate_lead(arr, gen_fn=fn)
    memos = fn.seen_memory[1]                                # what the manjha call saw
    assert any(m.form_role == "mukhada" for m in memos)


# --- approach_cut: where the head's protected tail begins (the mukhda anacrusis) --

def test_approach_cut_snaps_to_the_boundary_nearest_the_mukhda_line():
    assert approach_cut(_good_head().notes, 16.0) == 11.0    # a boundary sits ON the line
    # boundaries at 10 and 12 straddle the line (11) equally -> the tie goes LATER
    notes = [LeadNote(swara="S", dur=10.0), LeadNote(swara="m", dur=2.0),
             LeadNote(swara="S", dur=4.0)]
    assert approach_cut(notes, 16.0) == 12.0


def test_approach_cut_degenerates_to_the_full_cycle():
    # a single-note head has no boundary to cut at -> no approach, callers skip the fill
    assert approach_cut([LeadNote(swara="S", dur=16.0)], 16.0) == 16.0


# --- the tihai: the closing phrase x3, landing exactly on the sam ----------------

def test_make_tihai_states_the_closing_phrase_three_times_to_the_window():
    notes = [LeadNote(swara="n", dur=2.0), LeadNote(swara="g", dur=0.25),
             LeadNote(swara="m", dur=0.25), LeadNote(swara="d", dur=0.25),
             LeadNote(swara="S", dur=1.0)]
    tihai = make_tihai(notes, 6.0)
    assert tihai is not None
    assert abs(sum(n.dur for n in tihai) - 6.0) < 1e-9      # 3 statements + 2 gaps == the window
    landings = [n for n in tihai if not n.rest and n.swara == "S"]
    assert len(landings) == 3                                # the phrase lands three times
    assert sum(1 for n in tihai if n.rest) == 2              # the two equal gaps


def test_make_tihai_rejects_thin_or_stranded_material():
    assert make_tihai([LeadNote(swara="S", dur=4.0)], 6.0) is None          # one note: a pulse
    assert make_tihai([LeadNote(swara="m", dur=0.25),                       # gaps would dwarf
                       LeadNote(swara="S", dur=0.25)], 6.0) is None         # ...the phrase


def test_splice_tihai_replaces_the_final_avartan_only():
    sixteenths = [LeadNote(swara=s, dur=0.25) for s in (["g", "m", "d", "n"] * 11)]
    notes = ([LeadNote(swara="m", dur=3.0)] + sixteenths + [LeadNote(swara="S", dur=2.0)])
    total = sum(n.dur for n in notes)                        # 16 beats = 2 8-beat cycles
    spliced, ok = splice_tihai(notes, 8.0)
    assert ok
    assert abs(sum(n.dur for n in spliced) - total) < 1e-9   # the taan's length is untouched
    assert spliced[0] == notes[0]                            # the front is kept verbatim
    landings = [n for n in spliced if not n.rest and n.swara == "S"]
    assert len(landings) == 3                                # the close now lands three times


def test_splice_tihai_leaves_a_short_taan_alone():
    notes = [LeadNote(swara="g", dur=0.25)] * 8 + [LeadNote(swara="S", dur=2.0)]
    spliced, ok = splice_tihai(notes, 8.0)                   # 4 beats < 2 cycles
    assert not ok and spliced == notes


def test_taan_long_gets_a_code_built_tihai():
    # the verified taan's own close is restated x3 across its final avartan, and the
    # timeline shows it (the gharana cadence — code owns the counting)
    arr = _gat_arr((SectionKind.TAAN, 2, "taan_long"))
    cell = LeadPhrase(phrase_plan=_plan("d"), notes=[
        LeadNote(swara="d", dur=0.5), LeadNote(swara="n", dur=0.5),          # the motif (d n S m)
        LeadNote(swara="S", dur=0.5), LeadNote(swara="m", dur=0.5),
        LeadNote(swara="m", dur=4.0),                                        # held space
        LeadNote(swara="g", dur=0.25), LeadNote(swara="m", dur=0.25),        # burst
        LeadNote(swara="d", dur=0.25), LeadNote(swara="n", dur=0.25),
        LeadNote(swara="d", dur=0.25), LeadNote(swara="n", dur=0.25),
        LeadNote(swara="S", dur=0.25, oct=1), LeadNote(swara="g", dur=0.25, oct=1),
        LeadNote(swara="n", dur=2.0), LeadNote(swara="d", dur=2.0),
        LeadNote(swara="g", dur=0.25), LeadNote(swara="m", dur=0.25),
        LeadNote(swara="d", dur=0.25), LeadNote(swara="n", dur=0.25),
        LeadNote(swara="S", dur=0.25, oct=1), LeadNote(swara="g", dur=0.25, oct=1),
        LeadNote(swara="m", dur=0.25, oct=1), LeadNote(swara="g", dur=0.25, oct=1),  # the peak
        LeadNote(swara="S", dur=2.0, oct=1),
        LeadNote(swara="n", dur=2.0), LeadNote(swara="d", dur=2.0),
        LeadNote(swara="m", dur=2.0), LeadNote(swara="g", dur=2.0),
        LeadNote(swara="m", dur=0.25), LeadNote(swara="g", dur=0.25),        # the cadential run
        LeadNote(swara="m", dur=0.25), LeadNote(swara="d", dur=0.25),
        LeadNote(swara="n", dur=0.25), LeadNote(swara="d", dur=0.25),
        LeadNote(swara="m", dur=0.25), LeadNote(swara="g", dur=0.25),
        LeadNote(swara="m", dur=0.25), LeadNote(swara="g", dur=0.25),
        LeadNote(swara="S", dur=0.25), LeadNote(swara="g", dur=0.25),
        LeadNote(swara="m", dur=0.25), LeadNote(swara="g", dur=0.25),
        LeadNote(swara="m", dur=0.25), LeadNote(swara="g", dur=0.25),
        LeadNote(swara="S", dur=4.0)])                                       # lands on Sa
    fn, _ = _fake([cell])
    layers, events = generate_lead(arr, gen_fn=fn)
    assert any(e.data.get("tihai") for e in events)          # the cadence beat is on the timeline
    sitar = next(x for x in layers if x.instrument == VOICES["sitar"].instrument)
    final_bar_landings = [n for n in sitar.notes
                          if n.start >= 16.0 and n.swara == "S" and n.dur >= 3.0]
    assert len(final_bar_landings) == 3                      # the close lands THREE times


# --- the amad: Parikh's fourth line, riding the antara's final avartan -----------

def test_whole_gat_composes_and_places_the_amad():
    # an antara section with a spare avartan asks the joint gat for an AMAD; the antara
    # proper fills the front bars and the amad — the composed descent — takes the final
    # avartan, ending as a lead-in to the head
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"), (SectionKind.ALAAP, 2, "antara"))
    antara = LeadPhrase(phrase_plan=_plan("S"), notes=[     # quotes the head, peaks late, 16 beats
        LeadNote(swara="S", dur=2.0), LeadNote(swara="m", dur=1.5),
        LeadNote(swara="g", dur=1.0), LeadNote(swara="d", dur=1.5),
        LeadNote(swara="n", dur=1.0), LeadNote(swara="S", dur=1.0, oct=1),
        LeadNote(swara="g", dur=1.0, oct=1), LeadNote(swara="m", dur=2.0, oct=1),
        LeadNote(swara="g", dur=1.0, oct=1), LeadNote(swara="S", dur=1.0, oct=1),
        LeadNote(swara="n", dur=1.5), LeadNote(swara="d", dur=1.5)])         # ends AWAY from home
    amad = LeadPhrase(phrase_plan=_plan("d"), notes=[       # opens on the antara's landing, descends
        LeadNote(swara="d", dur=2.0), LeadNote(swara="m", dur=2.0),
        LeadNote(swara="g", dur=1.5), LeadNote(swara="m", dur=1.0),
        LeadNote(swara="g", dur=1.5), LeadNote(swara="S", dur=2.0),
        LeadNote(swara="d", dur=1.5, oct=-1), LeadNote(swara="n", dur=1.5, oct=-1),
        LeadNote(swara="S", dur=3.0)])
    gfn, gcalls = _fake_gat(Gat(mukhada=_good_head(), antara=antara, amad=amad))
    fn, calls = _fake([])                                    # every part is clean — no repair
    layers, _ = generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert gcalls[0]["needs_amad"] is True
    assert calls == []
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    final_avartan = [n.swara for n in notes if n.start >= 32.0]      # the antara section's last bar
    assert final_avartan == [n.swara for n in amad.notes]            # the amad rides it
    assert final_avartan[-1] == "S"                                  # ...ending at home, into the head


def test_whole_gat_skips_the_amad_when_the_antara_has_no_room():
    # a 1-bar antara keeps the old shape: no amad requested, homecoming stays the antara's job
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"), (SectionKind.ALAAP, 1, "antara"))
    gfn, gcalls = _fake_gat(Gat(mukhada=_good_head(), antara=_good_antara()))
    fn, _ = _fake([])
    generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert gcalls[0]["needs_amad"] is False


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
