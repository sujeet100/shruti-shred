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
from crew.lead import (  # noqa: E402
    LeadMemo,
    Voicing,
    _LeadContext,
    _lead_guardrail,
    _render_canvas_for_lead,
    _render_previous,
    _voice_line,
    apply_ornaments,
    apply_strokes,
    generate_lead,
    is_mukhada,
    lead_layers_from,
    place_phrase,
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


def test_leadnote_rejects_an_unknown_meend_swara():
    try:
        LeadNote(swara="S", dur=1.0, meend_swara="Z", meend_oct=1)
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


def test_leadnote_coerces_nullish_meend_swara_to_none():
    # LLMs express "no glide" as null or the STRING 'null'/'none'/''; all -> None, so a
    # stray nullish meend can't hard-fail a generation (see _clean_meend_swara).
    for junk in (None, "null", "none", ""):
        assert LeadNote(swara="S", dur=1.0, meend_swara=junk).meend_swara is None
    # a real target still parses, and a genuinely unknown one still raises
    assert LeadNote(swara="S", dur=1.0, meend_swara="P").meend_swara == "P"
    try:
        LeadNote(swara="S", dur=1.0, meend_swara="Z")
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "unknown meend target" in str(e).lower()


# --- the gat HEAD (mukhada): a cached, looping ~1-avartan cell -----------------

def _gat_arr(*specs: tuple[SectionKind, int, str], raga: str = "malkauns") -> Arrangement:
    """A chart whose sections carry a gat `form_role`. specs = (kind, bars, form_role); every
    section plays lead+drone. Kind ALAAP voices as solo sitar -> one clean lead layer to assert on."""
    sections = [Section(kind=k, bars=b, layers=["lead", "drone"], foreground="lead", form_role=fr)
                for (k, b, fr) in specs]
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _good_head() -> LeadPhrase:
    # a mukhada that PASSES the gat verifier: fills the 16-beat teentaal avartan, lands on Sa,
    # varied durations. Used wherever a test needs a clean head so the verify+repair is a no-op.
    return LeadPhrase(phrase_plan=_plan("S"),
                      notes=[LeadNote(swara="S", dur=6.0), LeadNote(swara="m", dur=4.0),
                             LeadNote(swara="g", dur=3.0), LeadNote(swara="S", dur=3.0)])


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


def test_is_mukhada_reads_the_form_role():
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"), (SectionKind.ALAAP, 1, "manjha"))
    assert is_mukhada(arr.sections[0]) is True
    assert is_mukhada(arr.sections[1]) is False


def test_generate_lead_writes_the_mukhada_as_ONE_avartan():
    # the LLM is asked for exactly one cycle (bars coerced to 1), not the whole multi-bar window
    arr = _gat_arr((SectionKind.ALAAP, 3, "mukhada"))
    fn, calls = _fake([_good_head()])
    generate_lead(arr, gen_fn=fn)
    assert calls[0].section.bars == 1                       # a one-avartan gen window
    assert calls[0].length == arr.beats_per_bar             # ...spanning a single cycle


def test_generate_lead_loops_the_mukhada_cell_across_its_bars():
    # code repeats the one-cycle cell across every bar so each avartan re-lands on the sam
    arr = _gat_arr((SectionKind.ALAAP, 2, "mukhada"))       # teentaal -> 16-beat cycles
    fn, _ = _fake([_good_head()])                           # a clean 16-beat head
    layers, _ = generate_lead(arr, gen_fn=fn)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    assert len(notes) == 8                                  # the 4-note cell placed in both bars
    bar0 = [n.swara for n in notes if n.start < 16.0]
    bar1 = [n.swara for n in notes if n.start >= 16.0]
    assert bar0 == bar1 == ["S", "m", "g", "S"]             # looped verbatim, each avartan on the sam
    assert min(n.start for n in notes if n.start >= 16.0) == 16.0


def test_generate_lead_reuses_the_cached_mukhada_on_return():
    # mukhada -> manjha -> mukhada: the RETURN reuses the cached head, so gen_fn fires only twice
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "manjha"),
                   (SectionKind.ALAAP, 1, "mukhada"))
    fn, calls = _fake([_good_head(), _phrase("d", "n")])     # only TWO phrases: proves the 3rd reused
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
    assert head == ret == ["S", "m", "g", "S"]


def test_non_mukhada_roles_are_not_looped():
    # a manjha is composed once across its whole window (not a looped cell)
    arr = _gat_arr((SectionKind.ALAAP, 2, "manjha"))
    fn, calls = _fake([_phrase("d", "n", dur=2.0)])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert calls[0].section.bars == 2                        # full multi-bar window, not coerced
    assert len(layers[0].notes) == 2                         # placed once, not looped per bar


# --- gat verifier repair: a weak mukhada is RE-ROLLED before it's cached (fix #4) -

def test_generate_lead_rerolls_a_weak_mukhada_and_keeps_the_clean_one():
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, calls = _fake([_flat_head(), _good_head()])         # first weak, the re-roll lands clean
    layers, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2                                   # the hook was re-rolled once
    swaras = [n.swara for n in sorted(layers[0].notes, key=lambda n: n.start)]
    assert swaras == ["S", "m", "g", "S"]                   # the CLEAN head is what got placed
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
    assert fn.seen_feedback[1] and any("flat" in v for v in fn.seen_feedback[1])  # re-roll sees the flaw


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


def test_place_phrase_andolan_and_meend_are_mutually_exclusive():
    # a note that glides (meend) must not also andolan — both drive the one pitch wheel
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
