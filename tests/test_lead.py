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
from crew.generators import VOICES, section_spans, total_beats  # noqa: E402
from crew.gat_verifier import CellChecks  # noqa: E402
from crew.lead import (  # noqa: E402
    _ALAP_RING_MAX,
    _PLUCK_SUSTAIN_MAX,
    LeadMemo,
    Voicing,
    _intro_gen_span,
    _LeadContext,
    _lead_guardrail,
    _doubled_hook,
    _generate_verified_cell,
    _restated_to_window,
    _role_briefs,
    _render_canvas_for_lead,
    _render_previous,
    _voice_line,
    apply_ornaments,
    apply_strokes,
    approach_cut,
    generate_lead,
    is_mukhada,
    is_underfilled,
    lead_layers_from,
    make_tihai,
    place_phrase,
    pluck_limited,
    splice_tihai,
    studio_lead_fn,
    take_severity,
)



def _with_lead_guitar(test):
    """Run a test of the lead-guitar VOICINGS (unison/octave/third, the taan trade) with the
    guitar switched on — it is OFF by default since 2026-10-12 (config.lead_guitar_enabled)."""
    import functools

    @functools.wraps(test)
    def run():
        old = os.environ.get("RMA_LEAD_GUITAR")
        os.environ["RMA_LEAD_GUITAR"] = "1"
        try:
            return test()
        finally:
            if old is None:
                os.environ.pop("RMA_LEAD_GUITAR", None)
            else:
                os.environ["RMA_LEAD_GUITAR"] = old
    return run

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
    assert "alaap: S:" in text
    assert "g(+1):1" in text and "m~P:1" in text       # local octave, meend TARGET, and the beats


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


@_with_lead_guitar
def test_solo_is_voiced_on_lead_guitar_only():
    arr = _arr(("lead", "drone"), kind=SectionKind.SOLO)   # SOLO -> GUITAR
    fn, _ = _fake([_phrase("S", "m")])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 1
    assert layers[0].instrument == VOICES["lead_guitar"].instrument


@_with_lead_guitar
def test_melody_is_voiced_in_unison_on_two_layers():
    arr = _arr(("lead", "drone"), kind=SectionKind.MELODY)  # MELODY -> UNISON
    fn, _ = _fake([_phrase("S", "m")])
    layers, _ = generate_lead(arr, gen_fn=fn)
    assert len(layers) == 2
    assert [[n.swara for n in x.notes] for x in layers] == [["S", "m"], ["S", "m"]]


@_with_lead_guitar
def test_a_one_bar_taan_is_played_by_both_voices_in_unison():
    arr = _arr(("lead", "drone"), kind=SectionKind.TAAN, raga="darbari")
    fn, _ = _fake([_phrase("S", "R", "g")])        # legal in darbari
    layers, _ = generate_lead(arr, gen_fn=fn)
    sitar = next(x for x in layers if x.instrument == VOICES["sitar"].instrument)
    guitar = next(x for x in layers if x.instrument == VOICES["lead_guitar"].instrument)
    assert [n.swara for n in sitar.notes] == ["S", "R", "g"]
    assert [n.swara for n in guitar.notes] == ["S", "R", "g"]   # unison: weight, not a 2nd melody


@_with_lead_guitar
def test_the_sitar_plays_the_WHOLE_taan_and_the_guitar_joins_at_the_end():
    """The voices used to TRADE the taan — sitar calls, guitar answers. That stopped the arc
    dead at the climax: the sitar builds, reaches intensity, and the piece pauses to give the
    other instrument a turn (Sujit, 2026-09-14). It also cost the raga exactly where the raga
    matters most, since the sitar's taan is the most faithful playing in the piece. The climb
    now belongs to ONE voice so it can actually climb, and the guitar arriving for the last
    avartan is what makes the peak land."""
    arr = _gat_arr((SectionKind.TAAN, 3, "taan_long"), raga="darbari")
    cell = LeadPhrase(phrase_plan=_plan("g"),
                      notes=[LeadNote(swara="g", dur=8.0), LeadNote(swara="m", dur=8.0),
                             LeadNote(swara="d", dur=2.0), LeadNote(swara="R", dur=2.0),
                             LeadNote(swara="m", dur=6.0), LeadNote(swara="n", dur=6.0),
                             LeadNote(swara="S", dur=8.0, oct=1),
                             LeadNote(swara="m", dur=8.0, oct=1)])
    layers = lead_layers_from({0: cell}, arr)
    sitar = next(x for x in layers if x.instrument == VOICES["sitar"].instrument)
    guitar = next(x for x in layers if x.instrument == VOICES["lead_guitar"].instrument)
    assert min(n.start for n in sitar.notes) == 0.0                  # the sitar opens...
    assert max(n.start for n in sitar.notes) >= 32.0                 # ...and never sits out
    assert all(n.start >= 32.0 for n in guitar.notes)                # guitar only in the last bar
    # the jhala's chikari strokes are the sitar's drone strings, which a guitar does not have
    join_s = [n for n in sitar.notes if n.start >= 32.0 and not n.chikari]
    join_g = list(guitar.notes)
    assert [n.swara for n in join_g] == [n.swara for n in join_s]    # in UNISON, not a third


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

@_with_lead_guitar
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


def _durs(bol: str, dur: float) -> list[float]:
    return [n.dur for n in apply_strokes([LeadNote(swara="m", dur=dur, vel=90, bol=bol)])]


def test_the_gat_head_prompt_teaches_how_the_melody_rides_the_strokes():
    from crew.lead import _render_bol_frame
    drut, vilambit = _render_bol_frame("razakhani"), _render_bol_frame("masitkhani")
    for block in (drut, vilambit):
        assert "dadir — da:di:r = 2:1:1" in block and "Many bols can share one matra" in block
        assert "write the note with dur" not in block                 # no length is prescribed
        assert "arrival swara is often restated" in block and "breathe before the mukhda" in block
        assert "m m m" not in block and "n-S dir" not in block        # principles, not figures to copy
        assert "NOTE VALUES are yours" in block and "matra by matra" not in block   # density is free
    assert "MOVING and SETTLING" in vilambit and "MOVING and SETTLING" not in drut  # a masitkhani rule
    assert "a dir is the SAME swara struck twice" in drut                         # verified (Sujit + notation)


def test_the_stroke_research_reaches_the_prompt():
    from crew.lead import _render_bol_frame
    drut, vilambit = _render_bol_frame("razakhani"), _render_bol_frame("masitkhani")
    for block in (drut, vilambit):
        assert "dara usually MOVES" in block and "dir doubles the ARRIVAL" in block
        assert "A compound on ONE note repeats that swara" in block
    assert "da dir dara" in drut and "da dir dara" not in vilambit       # drut figures, drut frame


def test_the_seed_sees_both_frames_but_the_vocabulary_once():
    from crew.lead import render_seed_strokes
    block = render_seed_strokes(None)
    assert "Masitkhani" in block and "Razakhani" in block
    assert block.count("bol words") == 1 and block.count("how a gat head moves") == 1


def test_the_head_plans_its_right_hand_before_its_notes():
    from crew.lead import _render_bol_frame, phrase_schema
    schema = phrase_schema()
    assert '"stroke_line"' in schema and "one token per matra" in schema
    # the 2026-10-12 contradiction: the schema told the head bols were optional decoration
    assert "add grace / meend / bol / ornament only where a rule asks" not in schema
    assert "every sounding note carries the bol its" in schema
    assert '"rda"' in schema
    drut, vilambit = _render_bol_frame("razakhani"), _render_bol_frame("masitkhani")
    assert "at least TWO dir matras" not in drut                     # a floor read as the target
    assert "compose your OWN stroke_line" in drut
    assert "this grid IS your stroke_line" in vilambit and "LEFT hand" in vilambit
    for block in (drut, vilambit):
        assert "Plan the stroke_line FIRST" in block


def test_the_plan_offers_raga_devices_before_sequences_and_no_inversion():
    from crew.lead import phrase_schema
    schema = phrase_schema()
    assert "invert" not in schema
    assert "sequence_up / sequence_down only where the raga's" in schema


def test_the_lead_prompt_drops_the_copied_example_and_the_rest_quota():
    import yaml
    from pathlib import Path
    config = Path(__file__).resolve().parent.parent / "crew" / "config"
    lead = yaml.safe_load((config / "tasks.yaml").read_text())["generate_lead"]["description"]
    assert "Worked example of developing ONE seed" not in lead
    assert "Use 1-2 true RESTS per avartan" not in lead
    assert "(the vadi, Sa, or a m->S resolution)" not in lead
    mukhada = yaml.safe_load((config / "lead_roles.yaml").read_text())["roles"]["mukhada"]
    assert "a couple of matras of anacrusis" not in mukhada        # the frame owns the approach
    assert "PLAN THE RIGHT HAND FIRST" in mukhada


def test_the_lead_prompt_states_objectives_not_recipes():
    import yaml
    from pathlib import Path
    tasks = yaml.safe_load((Path(__file__).resolve().parent.parent / "crew" / "config"
                            / "tasks.yaml").read_text())
    lead, gat, seed = (tasks[k]["description"] for k in ("generate_lead", "generate_gat", "compose_seed"))
    assert "OPEN with a RECOGNISABLE pakad/chalan fragment" not in lead
    assert "an eighth-note pickup, then a burst of sixteenths" not in lead
    assert "rests count toward the window exactly as notes" in lead     # fill vs silence reconciled
    assert "spanning 2.5-3 octaves)" not in gat and "lives low" in gat
    assert "riff_first means" in seed                                   # the one fixed relationship


def test_a_head_check_measures_its_stroke_line():
    from crew.lead import _head_strokes, _render_plan
    head = LeadPhrase(phrase_plan=PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"],
                                             climax_and_sam="x"),
                      notes=[LeadNote(swara="S", dur=16.0, bol="da")])
    assert any("no stroke_line planned" in v
               for v in _head_strokes(head, cycle_beats=16.0, frame="razakhani").craft)
    planned = head.phrase_plan.model_copy(update={"stroke_line": ["da"] + ["-"] * 15})
    assert "strokes: da - -" in _render_plan(planned)


def test_dir_is_two_half_matra_strokes():
    out = apply_strokes([LeadNote(swara="m", dur=1.0, vel=90, bol="dir")])
    assert [n.dur for n in out] == [0.5, 0.5]
    assert out[0].vel > out[1].vel                       # di (inward) stronger than the r
    assert all(n.swara == "m" for n in out)


def test_each_bol_word_keeps_its_own_rhythm():
    # Parikh / Swarmatra: a bol keeps its value inside a compound — never squeezed to fit
    assert _durs("dar", 1.5) == [1.0, 0.5]               # da(1) + r(1/2)
    assert _durs("dadir", 2.0) == [1.0, 0.5, 0.5]        # da(1) + di(1/2) + r(1/2)
    assert _durs("dara", 1.0) == [0.5, 0.5]              # two strokes, not a triplet
    assert _durs("daradara", 1.0) == [0.25] * 4
    assert round(sum(_durs("darada", 1.0)), 4) == 1.0 and len(_durs("darada", 1.0)) == 3


def test_a_figure_scales_to_whatever_length_its_note_has():
    # Sujit, 2026-10-12: a drut gat puts many bols inside one matra — the ratios hold at any size
    assert _durs("dadir", 1.0) == [0.5, 0.25, 0.25]      # dadir INSIDE one matra
    assert _durs("dir", 0.5) == [0.25, 0.25]             # a dir in half a matra: two quarters
    assert _durs("dar", 3.0) == [2.0, 1.0]               # dar stretched: still 2:1


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
    notes = [LeadNote(swara="S", dur=1.0, bol="dir"), LeadNote(swara="g", dur=2.0, bol="dadir")]
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
    # graces degrade to plain notes; the old note-level "diri" reads as "dir", and "dara" is
    # its own two-stroke word (it used to be mis-mapped to the three-stroke "darada")
    assert LeadNote(swara="S", dur=1.0, bol="diri").bol == "dir"
    assert LeadNote(swara="S", dur=1.0, bol="Da-Dir").bol == "dadir"
    assert LeadNote(swara="S", dur=1.0, bol="dara").bol == "dara"
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
_HEAD_SWARAS = ["S", "m", "g", "d", "n", "d", "m", "g", "S", "m"]


def _good_head() -> LeadPhrase:
    # a mukhada that PASSES the gat verifier AND the stroke frame (bpm 72 -> masitkhani):
    # fills the 16-beat teentaal avartan, OPENS on S (the swara every sam restates, struck
    # "da"), cadences to the vadi m (NOT back to S — a head ending where it began merges with
    # itself across the loop and hides the sam), and carries the frame's dir doublings — double
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
                             LeadNote(swara="S", dur=0.5, bol="ra"),
                             LeadNote(swara="m", dur=2.0, bol="da")])   # cadences AWAY from
                             # the opening S, so the sam re-enters audibly when the head loops


def _flat_head() -> LeadPhrase:
    # fills the cycle at a steady pulse (fine since 2026-09-14 — a gat MOVES at one value),
    # but it opens and closes on the same S, so the two merge across the loop and the sam
    # disappears -> one violation
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
    assert fn.seen_feedback[1] and any("SAM DISAPPEARS" in v for v in fn.seen_feedback[1])


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
    assert "S:1 -:1" in _render_previous(memory)        # a rest keeps its length


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

def test_apply_ornaments_realises_a_murki_as_unstruck_kan_on_one_stroke():
    # a murki on komal g in Bhairavi: one pluck on the upper neighbour (m), pull-off to the lower
    # (r), hammer onto g — the cluster rides the note as kan, so it is ONE note, ONE attack
    out = apply_ornaments([LeadNote(swara="g", dur=2.0, ornament="murki")], "bhairavi")
    assert len(out) == 1 and out[0].swara == "g" and out[0].dur == 2.0
    assert out[0].grace == ["m", "r"] and out[0].ornament is None


def test_khatka_is_the_same_cluster_struck_harder():
    murki = apply_ornaments([LeadNote(swara="g", dur=2.0, vel=90, ornament="murki")], "bhairavi")
    khatka = apply_ornaments([LeadNote(swara="g", dur=2.0, vel=90, ornament="khatka")], "bhairavi")
    assert murki[0].grace == khatka[0].grace                 # same notes — force tells them apart
    assert murki[0].vel == 90 < khatka[0].vel


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
    [note] = layers[0].notes
    assert note.swara == "g" and note.grace == ["m", "r"]   # one placed note carrying the cluster


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
    # the trailing pause is CODE's: the alap is asked for LESS than its section window — about
    # 2.5 s of breath (it was up to a third of the intro: 11.2 of 32 beats, GPT 2026-10-12)
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    fn, calls = _fake([_good_intro()])
    generate_lead(arr, gen_fn=fn)
    assert calls[0].length == 32 - round(2.5 * arr.bpm / 60 * 4) / 4


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


def _overlong_intro() -> LeadPhrase:
    """A HARD-faulty alap: 48 beats of notes in a 2-avartan (32-beat) intro — it would spill into
    the silence code reserves before the gat. (Taste faults no longer re-roll; this one does.)"""
    return _phrase(*(["g", "m", "d", "n"] * 6), dur=2.0)


def test_live_beats_stream_from_inside_the_lead_stage():
    # per-call progress (Sujit's live note): a sink installed around generate_lead hears a
    # RUNNING beat for the cell AND for its re-roll — the UI shows work as it happens, not
    # one flood when the flow node completes. Without a sink, beats are free no-ops.
    from crew.contracts import EventType
    from crew.live import live_sink
    bad = _overlong_intro()
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    seen: list = []
    fn, _ = _fake([bad, _good_intro()])
    with live_sink(seen.append):
        generate_lead(arr, gen_fn=fn)
    running = [e for e in seen if e.type == EventType.RUNNING]
    assert any("composing the intro" in e.text for e in running)
    reroll = next(e for e in running if "re-rolling the intro" in e.text)
    assert "flagged:" in reroll.text and "window" in reroll.text  # the ticker SAYS WHY
    assert reroll.data["violations"]                              # ...and carries the full list


def test_intro_is_verified_and_rerolled_with_feedback():
    # an alap that overruns its window is bounced (a HARD fault); the re-roll sees WHY
    bad = _overlong_intro()
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    fn, calls = _fake([bad, _good_intro()])
    _, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 2
    assert fn.seen_feedback[1] and any("window" in v for v in fn.seen_feedback[1])
    rr = next(e for e in events if e.data.get("gat_verify"))
    assert rr.data["cell"] == "intro"


def test_a_taste_only_weak_alap_is_reported_not_rerolled():
    # never resolves to Sa (ends on a legal Malkauns rest), no rests, no mandra dip — all CRAFT
    # now: one take, no paid re-roll, and the notes ride the intro's event for the judges
    wandering = _phrase("g", "m", "d", "m", dur=2.0)
    arr = _gat_arr((SectionKind.ALAAP, 2, "intro"))
    fn, calls = _fake([wandering])
    _, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 1 and fn.seen_feedback == [None]
    intro = next(e for e in events if e.data.get("craft_notes"))
    assert any("mandra" in v for v in intro.data["craft_notes"])


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


def test_a_short_taan_restates_itself_rather_than_leaving_the_peak_empty():
    """The repair loop is bounded and keeps the best-of-N, so a taan that fails its own fill
    check twice still plays. Measured on the 2026-09-14 render, the taan covered 20 of its 40
    beats and the other TWENTY were silent — the composition's peak, half empty, with the band
    vamping under nothing."""
    cell = [LeadNote(swara=s, dur=1.0) for s in "Sgmp".replace("p", "P")]
    out = _restated_to_window(cell, 16.0)
    assert sum(n.dur for n in out) >= 16.0
    assert {n.swara for n in out} == {n.swara for n in cell}, "restating invented a pitch"


def test_a_taan_that_already_fills_its_window_is_untouched():
    cell = [LeadNote(swara="S", dur=4.0), LeadNote(swara="g", dur=4.0)]
    assert _restated_to_window(cell, 8.0) == cell


def test_restating_never_loops_forever_on_an_empty_cell():
    assert _restated_to_window([], 16.0) == []


def test_the_unison_guitar_doubles_the_theme_and_lays_out_through_a_run():
    """Measured on the 2026-09-14 render: the lead guitar shared onset AND swara with the
    sitar on 86% of its notes, so the sitar stopped being the distinctive voice and the fast
    passages turned thick. A guitarist doubling a soloist plays the theme with them and lays
    out through the flurries."""
    theme = [Note(swara=s, oct=0, start=float(i), dur=1.0) for i, s in enumerate("Sgm")]
    run = [Note(swara="P", oct=0, start=3.0 + i * 0.25, dur=0.25) for i in range(8)]
    doubled = _doubled_hook(theme + run)
    assert [n.swara for n in doubled] == ["S", "g", "m"], "the guitar followed the run"


def test_an_isolated_long_note_inside_a_run_is_not_doubled():
    """One hit in the middle of a flurry reads as a mistake, not a part."""
    run = [Note(swara="P", oct=0, start=i * 0.25, dur=0.25) for i in range(4)]
    lone = [Note(swara="m", oct=0, start=1.0, dur=1.0)]
    more = [Note(swara="g", oct=0, start=2.0 + i * 0.25, dur=0.25) for i in range(4)]
    assert _doubled_hook(run + lone + more) == []


def test_intro_alap_is_placed_in_time_as_written_after_the_lead_in():
    # the vibhag snap is gone (Sujit, 2026-10-12): bar 0 is still arpeggio ALONE, then the alap
    # plays its own durations and rests back to back — a jod-like pulse, not phrase-snapping
    arr = _intro_arr(clean=True, bars=4)
    layers = lead_layers_from({0: _good_intro()}, arr)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    assert notes[0].start == 16.0                                 # lead-in: nothing sounds in bar 0
    cursor, expected = 16.0, []
    for n in _good_intro().notes:
        if not n.rest:
            expected.append(cursor)
        cursor += n.dur
    assert [n.start for n in notes] == expected[:len(notes)]       # exactly as written, in time
    assert notes[-1].swara == "S" and notes[-1].fade is True      # resolves, rings out
    assert notes[-1].start + notes[-1].dur == 64.0                # to the section edge


def test_the_pause_before_the_gat_is_a_breath_not_a_section():
    from crew.lead import _INTRO_MIN_GAP_BEATS, _intro_place_end
    span = list(section_spans(_intro_arr(clean=False, bars=2)))[0]
    window = _intro_gen_span(span, 16.0, 4.0, bpm=64)
    assert span.end - window.end == 2.75                          # ~2.5 s at 64 bpm, not 5.6 beats
    assert _intro_place_end(span) == span.end - _INTRO_MIN_GAP_BEATS   # the alap may eat code's
                                                                  # pause, never the last breath


def test_intro_without_the_clean_arpeggio_stays_flush_left():
    # no arpeggio to lock to -> the old behavior: the alap starts at the section head (beat 0)
    arr = _intro_arr(clean=False, bars=4)
    layers = lead_layers_from({0: _good_intro()}, arr)
    notes = sorted(layers[0].notes, key=lambda n: n.start)
    assert notes[0].start == 0.0                                  # flush-left, no lead-in


def test_intro_gen_span_reserves_a_lead_in_only_with_the_clean_arpeggio():
    span_clean = list(section_spans(_intro_arr(clean=True, bars=4)))[0]
    span_plain = list(section_spans(_intro_arr(clean=False, bars=4)))[0]
    assert _intro_gen_span(span_clean, 16.0, 4.0).start == 16.0   # one avartan of lead-in
    assert _intro_gen_span(span_plain, 16.0, 4.0).start == 0.0    # none without the arpeggio


def test_a_two_avartan_intro_keeps_most_of_its_window_for_the_alap():
    # the 2026-10-11 short-form render: a whole avartan of lead-in left the alap 10.4 of 32
    # beats and it crammed a taan into the space. One vibhag of lead-in sets the pulse instead.
    span = list(section_spans(_intro_arr(clean=True, bars=2)))[0]
    window = _intro_gen_span(span, 16.0, 4.0)
    assert window.start == 4.0
    assert window.length > 17.0


def test_the_tala_note_describes_the_window_it_is_given():
    from crew.lead import _render_tala_position
    span = list(section_spans(_intro_arr(clean=True, bars=2)))[0]
    note = _render_tala_position(_intro_gen_span(span, 16.0, 4.0), 16.0)
    assert "beat(s) 12 within" in note             # the next sam, measured from the window start
    assert "before the next sam" in note           # a shortened window does not end on one
    whole = _render_tala_position(span, 16.0)
    assert "beat(s) 0, 16 within" in whole and "ENDS on the closing sam" in whole


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
    # the joint gat's manjha stops far short of the sam (a HARD fault: the head would re-enter
    # after a dead gap) -> it is regenerated IN ISOLATION via gen_fn, while the good mukhada is
    # kept (nobody rewrites a whole gat for one weak part)
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"), (SectionKind.ALAAP, 1, "manjha"))
    bad_manjha = LeadPhrase(phrase_plan=_plan("m"),         # 3 beats of a ~12-beat window
                            notes=[LeadNote(swara="m", dur=1.5), LeadNote(swara="S", dur=1.5)])
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
                             LeadNote(swara="S", dur=0.5, bol="ra"),
                             LeadNote(swara="m", dur=2.0, bol="da")])   # cadences AWAY from
                             # the opening S, so the sam re-enters audibly when the head loops
    gfn, _ = _fake_gat(Gat(mukhada=head))
    fn, calls = _fake([_good_intro()])
    generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert len(calls) == 1                                  # the teasing intro passed first try
    assert any(m.form_role == "mukhada" for m in fn.seen_memory[0])   # the intro SAW the head


def test_intro_motif_not_drawn_from_the_head_is_reported_not_rerolled():
    # the head never sounds "n S" as a phrase (its n sits four notes from its closing S), so
    # _good_intro's motif (n S) teases the WRONG tune — motif discipline is CRAFT now: one take,
    # and the note rides the intro's event for the judges
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
    _, events = generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    assert len(calls) == 1
    notes = [v for e in events for v in e.data.get("craft_notes", [])]
    assert any("not drawn from the mukhada head" in v for v in notes)


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
    # an antara that overruns its window (it would be TRUNCATED, cutting off its own landing)
    # is bounced; the re-roll is told exactly that. Not quoting the head is now CRAFT.
    bad = LeadPhrase(phrase_plan=_plan("d"),
                     notes=[LeadNote(swara="d", dur=4.0), LeadNote(swara="n", dur=4.0),
                            LeadNote(swara="g", dur=4.0, oct=1), LeadNote(swara="n", dur=4.0),
                            LeadNote(swara="d", dur=4.0), LeadNote(swara="S", dur=4.0)])
    arr = _gat_arr((SectionKind.ALAAP, 1, "mukhada"),
                   (SectionKind.ALAAP, 1, "antara"))
    fn, calls = _fake([_good_head(), bad, _good_antara()])
    _, events = generate_lead(arr, gen_fn=fn)
    assert len(calls) == 3                                   # head + antara + one re-roll
    assert fn.seen_feedback[2] and any("TRUNCATED" in v for v in fn.seen_feedback[2])
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
    assert fn.seen_feedback[1] and any("fills only" in v for v in fn.seen_feedback[1])
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


def test_the_mukhada_is_the_sitar_alone_whatever_its_kind():
    # a distorted guitar doubling the head turned the gat into a guitar line (Sujit,
    # 2026-10-12) — the head is the sitar's, on a melody-kind section as on any other
    for kind in (SectionKind.MELODY, SectionKind.ALAAP):
        arr = _gat_arr((kind, 1, "mukhada"))
        fn, _ = _fake([_good_head()])
        layers, _ = generate_lead(arr, gen_fn=fn)
        assert [layer.instrument for layer in layers] == ["sitar"]


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
    final_bar_sas = [n for n in sitar.notes if n.start >= 16.0 and n.swara == "S"
                     and (n.dur >= 3.0 or n.start == total_beats(arr))]
    assert len(final_bar_sas) == 3                           # the close lands THREE times
    assert final_bar_sas[-1].start == total_beats(arr)       # ... the third ON the sam


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



# --- the PLUCK LIMIT: a padded climax hold becomes jhala (2026-10-11 opener's sag) -------------

def test_a_hold_past_the_pluck_limit_becomes_jhala_on_its_own_swara():
    from crew.lead import animate_long_holds
    notes = [LeadNote(swara="m", dur=1.0), LeadNote(swara="S", dur=16.0)]
    out = animate_long_holds(notes)
    assert abs(sum(n.dur for n in out) - 17.0) < 1e-9             # total length kept exactly
    assert out[0] == notes[0] and out[1].swara == "S" and out[1].dur == 2.0   # the landing rings
    jhala = out[2:]
    assert all(n.dur <= 0.5 + 1e-9 for n in jhala)                # re-struck, never held
    assert {n.bol for n in jhala} == {"da", "chikari"}
    assert all(n.swara == "S" for n in jhala)                      # the held swara + taar-Sa chikari
    short = [LeadNote(swara="S", dur=4.0), LeadNote(swara="S", dur=2.0, rest=True)]
    assert animate_long_holds(short) == short                       # within the limit: untouched


def test_the_climax_taan_never_ends_in_a_silent_hold():
    # the opener's shape: a verified taan_long that pads its window with one long closing Sa —
    # placed, the climax now drives to its end instead of decaying into a band-only avartan
    run = [LeadNote(swara=sw, dur=0.25) for sw in ("d", "n", "S", "g", "m", "g", "S", "n") * 3]
    cell = LeadPhrase(phrase_plan=_plan("d"),
                      notes=[*run, LeadNote(swara="m", dur=1.0), LeadNote(swara="g", dur=1.0),
                             LeadNote(swara="S", dur=24.0)])
    arr = _gat_arr((SectionKind.TAAN, 2, "taan_long"))
    fn, _ = _fake([cell])
    layers, _ = generate_lead(arr, gen_fn=fn)
    notes = [n for layer in layers for n in layer.notes]
    assert notes and max(n.dur for n in notes) <= 4.0 + 1e-9
    assert max(n.start + n.dur for n in notes) > 28.0              # the line reaches the end


# --- the pluck limit on EVERY placed lead note (2026-10-12, the silent-sitar run) -------

def _sitar_notes_in(layers, start: float, end: float) -> list[Note]:
    sitar = next(layer for layer in layers if layer.instrument == VOICES["sitar"].instrument)
    return sorted((n for n in sitar.notes if start <= n.start < end), key=lambda n: n.start)


def test_a_one_beat_cell_in_a_long_mislabelled_intro_never_outlives_the_pluck():
    # the first live run: a 3-bar section labelled `intro` that was NOT the last got a 1-note
    # 1-beat cell, and the ring-out stretched it into ONE 48-beat note — 30 s of silence
    arr = _gat_arr((SectionKind.RIFF, 3, "intro"), (SectionKind.RIFF, 1, None))
    cell = LeadPhrase(phrase_plan=_plan(), notes=[LeadNote(swara="g", dur=1.0)])
    layers = lead_layers_from({0: cell, 1: _phrase("S", "m", "g", "S", dur=4.0)}, arr)
    intro = _sitar_notes_in(layers, 0.0, 48.0)
    assert intro and max(n.dur for n in intro) <= _PLUCK_SUSTAIN_MAX + 1e-9
    assert intro[-1].fade is True and intro[-1].dur == _ALAP_RING_MAX   # a bounded ring, fading


def test_a_padded_metered_hold_rings_then_jhalas_to_its_written_end():
    # a 45-beat hold inside a metered section that is not the last: no note past the limit,
    # yet the line still reaches the section edge — it keeps sounding instead of decaying
    arr = _gat_arr((SectionKind.RIFF, 3, None), (SectionKind.RIFF, 1, None))
    cell = LeadPhrase(phrase_plan=_plan(), notes=[LeadNote(swara="S", dur=1.0),
                                                  LeadNote(swara="g", dur=2.0),
                                                  LeadNote(swara="m", dur=45.0)])
    layers = lead_layers_from({0: cell, 1: _phrase("S", "m", "g", "S", dur=4.0)}, arr)
    first = _sitar_notes_in(layers, 0.0, 48.0)
    assert max(n.dur for n in first) <= _PLUCK_SUSTAIN_MAX + 1e-9
    assert max(n.start + n.dur for n in first) == 48.0


def test_the_lead_lines_final_note_may_ring():
    # the one exemption: the very last note of the whole lead line dies away on its own
    arr = _gat_arr((SectionKind.RIFF, 2, None))
    cell = LeadPhrase(phrase_plan=_plan(), notes=[LeadNote(swara="g", dur=2.0),
                                                  LeadNote(swara="S", dur=30.0)])
    notes = _sitar_notes_in(lead_layers_from({0: cell}, arr), 0.0, 32.0)
    assert notes[-1].swara == "S" and notes[-1].dur == 30.0


def test_pluck_limited_keeps_time_and_never_glides_a_restrike():
    # metered: ring + jhala on the swara the hold RESTS on; total time kept, starts contiguous
    hold = Note(swara="m", oct=0, start=4.0, dur=10.0, vel=90, meend_swara="g")
    out = pluck_limited([hold], register=0, metered=True)
    assert out[0].start == 4.0 and out[0].dur == 2.0 and out[0].meend_swara == "g"   # the ring
    assert all(n.meend_swara is None for n in out[1:])               # restrikes are struck
    assert {n.swara for n in out[1:] if n.oct == 0} == {"g"}          # ...on the resting swara
    assert abs(sum(n.dur for n in out) - 10.0) < 1e-9
    assert all(abs(a.start + a.dur - b.start) < 1e-9 for a, b in zip(out, out[1:]))
    assert max(n.dur for n in out) <= _PLUCK_SUSTAIN_MAX
    # unmetered (the alap): the hold decays — cut to the limit, nothing moved, nothing added
    alap = [Note(swara="S", start=0.0, dur=10.0), Note(swara="g", start=10.0, dur=2.0)]
    cut = pluck_limited(alap, register=0, metered=False)
    assert [(n.start, n.dur) for n in cut] == [(0.0, _PLUCK_SUSTAIN_MAX), (10.0, 2.0)]
    # the line's closing note is exempt
    assert pluck_limited(alap[:1], register=0, metered=False, closes_lead=True) == alap[:1]


# --- best-of-N by SEVERITY: a near-empty take never wins on fault count ----------------

def test_a_near_empty_cell_is_underfilled_whatever_its_hold():
    full = _phrase("S", "g", "m", "d", "n", "S", "m", "g", dur=2.0)
    assert not is_underfilled(full, 16.0)
    assert is_underfilled(_phrase("S", dur=16.0), 16.0)                   # one note, padded
    assert is_underfilled(_phrase("S", "g", "m", dur=1.0), 16.0)          # 3 beats of 16
    assert take_severity(full, 16.0, ["a", "b"]) < take_severity(_phrase("S", dur=1.0), 16.0, ["a"])


def test_best_of_n_keeps_the_fuller_take_over_an_emptier_one_with_fewer_faults():
    # neither take is clean; the near-empty one trips ONE check, the full one TWO — the full
    # one must play, whichever order they arrive in
    arr = _gat_arr((SectionKind.RIFF, 1, None))
    span = section_spans(arr)[0]
    empty = _phrase("g", dur=1.0)
    full = _phrase("S", "g", "m", "d", "n", "S", "m", "g", dur=2.0)

    def verify(cell: LeadPhrase) -> CellChecks:
        return CellChecks(hard=("a",) if cell is empty else ("a", "b"))

    for takes in ([empty, full], [full, empty]):
        fn, _ = _fake(takes)
        chosen = _generate_verified_cell(span, arr, [], gen_fn=fn, verify=verify)
        assert chosen.cell is full and chosen.violations == ["a", "b"]


def test_on_a_tie_the_take_that_answered_the_feedback_wins():
    # 2026-10-12: take 1 failed "must resolve to Sa", the re-roll fixed it but ran long — one
    # fault each, and the unresolved take shipped because the first take won ties
    arr = _gat_arr((SectionKind.RIFF, 1, None))
    span = section_spans(arr)[0]
    first = _phrase("S", "g", "m", "d", "n", "S", "m", "g", dur=2.0)
    second = _phrase("S", "g", "m", "d", "n", "S", "m", "S", dur=2.0)

    def verify(cell: LeadPhrase) -> CellChecks:
        return CellChecks(hard=("unresolved",) if cell is first else ("long",))

    fn, _ = _fake([first, second])
    assert _generate_verified_cell(span, arr, [], gen_fn=fn, verify=verify).cell is second


def test_the_identity_cells_think_before_they_write():
    # the alap and the gat head run at the conception tier (medium thinking) — Sujit, 2026-10-12
    from crew.lead import _IDENTITY_ROLES
    assert _IDENTITY_ROLES == {"intro", "mukhada"}


def test_the_lead_is_told_where_the_raga_lives():
    # the 2026-10-12 Darbari lead spent 6% of its time below home Sa: nobody had told it
    from crew.lead import _render_raga_facts
    assert "register — where the raga LIVES" in _render_raga_facts("darbari")
    assert "register" not in _render_raga_facts("yaman")      # no verified entry, no claim


def test_by_default_the_sitar_carries_every_lead_section_alone():
    # Sujit, 2026-10-12: the unison guitar buried the sitar's gamaks and made it "feeble"
    arr = _gat_arr((SectionKind.MELODY, 1, None), (SectionKind.SOLO, 1, None),
                   (SectionKind.TAAN, 1, "taan_long"))
    phrases = {i: _phrase("S", "g", "m", "d", dur=2.0) for i in range(3)}
    layers = lead_layers_from(phrases, arr)
    assert [ly.instrument for ly in layers] == [VOICES["sitar"].instrument]
    assert len(layers[0].notes) == 12                       # the whole line, every section


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
