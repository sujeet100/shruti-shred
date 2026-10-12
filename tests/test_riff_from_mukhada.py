"""
Tests for the riff that GROWS OUT OF the gat head — all pure (no key, no cost).

The guitar inherits the mukhada's identity (`crew/head_anatomy.py` decides what that is): its
strokes and pauses, its accents and the sam, its structural notes as power-chord roots. Ornaments
keep their stroke but not their pitch, a held note becomes a strike and a chug run, and the roots
stay legal in the raga — set AND direction — and seated above the rhythm floor. Then the head riff
develops by statement (`crew/riff_statements.py`) and its kinship with the head is measured for the
Producer (`crew/riff_kinship.py`), never enforced.

Runs as a script (`uv run python tests/test_riff_from_mukhada.py`) or under pytest.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

import yaml  # noqa: E402

from crew.anchor import RIFF_EVENT_KEY, riff_accents  # noqa: E402
from crew.contracts import (  # noqa: E402
    RHYTHM_FLOOR,
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    LeadNote,
    LeadPhrase,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import assemble_composition, drone_layer, section_spans  # noqa: E402
from crew.head_anatomy import head_anatomy, head_onsets, structural_notes  # noqa: E402
from crew.riff import _RiffContext, compose_seeded_riff, generate_riff, riff_grammar_error  # noqa: E402
from crew.riff_from_mukhada import (  # noqa: E402
    derive_riff_from_mukhada,
    derived_slots,
    head_riff,
    render_head_riff,
)
from crew.riff_kinship import kinship_report, render_kinship  # noqa: E402
from crew.riff_statements import apply_statement, develop_statements, statement_variant  # noqa: E402
from crew.riff_texture import verify_riff  # noqa: E402
from raga import RAGAS, direction_violations, validate_composition  # noqa: E402
from tests.test_lead import _good_head, _plan  # noqa: E402

# teentaal: a 16-beat avartan, sam 0, talis 4 and 12 (khali 8 is never an accent)
_ACCENTS = frozenset({0.0, 4.0, 12.0})
_LEAD, _RHYTHM = ["lead", "rhythm", "drone"], ["rhythm", "drums", "drone"]


def _mukhada(bars: int = 1, slot: str = "main") -> Section:
    return Section(kind=SectionKind.MELODY, bars=bars, layers=_LEAD, foreground="lead",
                   form_role="mukhada", riff_slot=slot)


def _takeover(bars: int = 3, slot: str = "takeover") -> Section:
    return Section(kind=SectionKind.RIFF, bars=bars, layers=_RHYTHM, foreground="rhythm",
                   riff_slot=slot)


def _breakdown() -> Section:
    return Section(kind=SectionKind.BREAKDOWN, bars=1, layers=["rhythm", "drums"],
                   foreground="rhythm", form_role="breakdown", riff_slot="crush")


def _chart(*sections: Section, raga: str = "malkauns", anchor: str = "gat_first",
           head: LeadPhrase | None = None) -> Arrangement:
    secs = list(sections) or [_mukhada(), _takeover(), _breakdown(), _mukhada()]
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=72, motif=["S"],
                             sections=secs, anchor=anchor)
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    return arr.model_copy(update={"seed_hook": head}) if head is not None else arr


def _head(*notes: LeadNote) -> LeadPhrase:
    return LeadPhrase(phrase_plan=_plan("S"), notes=list(notes))


def _n(swara: str, dur: float, bol: str | None = "da", **kw) -> LeadNote:
    return LeadNote(swara=swara, dur=dur, bol=bol, **kw)


def _raga_head(raga: str) -> LeadPhrase:
    """A 16-beat head walked from the raga's own ladders: up the aroha, down the avaroha."""
    up, down = RAGAS[raga]["aroha"], RAGAS[raga]["avaroha"]
    return _head(_n("S", 4.0), _n(up[2], 2.0), _n(up[3], 1.0, "dir"), _n(up[4], 1.0),
                 _n(down[1], 0.5, "ra"), _n(down[2], 0.5), _n(down[3], 1.0, meend_swara=down[4]),
                 _n(down[4], 2.0), _n(down[-3], 2.0), _n(down[-2], 2.0, "ra"))


def _derive(head: LeadPhrase, raga: str = "malkauns", register: int = -2, **kw) -> RiffPattern:
    return derive_riff_from_mukhada(head, raga=raga, cycle_beats=16.0, accents=_ACCENTS,
                                    register=register, **kw)


def _onsets(notes: list[RiffNote]) -> dict[float, RiffNote]:
    """Within-cycle onset -> the sounding stroke there."""
    t, out = 0.0, {}
    for n in notes:
        if not n.rest:
            out[round(t, 4)] = n
        t += n.dur
    return out


def _fail(span, arr, memory):
    raise AssertionError(f"the model was called for section {span.index}")


def _recorder(pattern: RiffPattern):
    calls: list[int] = []

    def fn(span, arr, memory):
        calls.append(span.index)
        return pattern
    return fn, calls


_OTHER = RiffPattern(notes=[RiffNote(swara="g", dur=2.0), RiffNote(swara="d", dur=2.0, rest=True),
                            RiffNote(swara="S", dur=12.0)])


# --- the anatomy: what is identity -------------------------------------------------------------

def test_passing_and_neighbour_notes_are_ornaments_and_accents_never_are():
    roles = {(n.onset, n.swara): n.role for n in head_anatomy(_good_head(), cycle_beats=16.0,
                                                              accents=_ACCENTS)}
    assert roles[(11.0, "n")] == "ornamental"       # d -> n -> d: a neighbour
    assert roles[(11.5, "d")] == "ornamental"       # n -> d -> m: passing, downward
    assert roles[(13.0, "g")] == "ornamental"       # m -> g -> S: passing
    assert roles[(13.5, "S")] == "structural"       # g -> S -> m: a turn of direction
    assert roles[(0.0, "S")] == roles[(4.0, "m")] == roles[(12.0, "m")] == "structural"


def test_a_meend_counts_at_its_arrival_and_a_chikari_is_rhythm_only():
    head = _head(_n("S", 4.0), _n("g", 4.0, meend_swara="m"), _n("S", 1.0, "chikari"),
                 _n("m", 7.0))
    anatomy = head_anatomy(head, cycle_beats=16.0, accents=_ACCENTS)
    assert (anatomy[1].swara, anatomy[1].meend) == ("m", True)
    assert anatomy[2].chikari and anatomy[2].role == "ornamental"


def test_a_compound_bol_is_several_plucks():
    head = _head(_n("S", 2.0, "dadir"), _n("m", 14.0))
    plucks = head_onsets(head_anatomy(head, cycle_beats=16.0, accents=_ACCENTS))
    assert plucks == (0.0, 1.0, 1.5, 2.0)            # da 1/2, di 1/4, r 1/4 of the two beats


# --- the derivation: the head's identity on guitar ---------------------------------------------

def test_the_riff_strikes_every_pluck_of_the_head_and_fills_the_cycle():
    riff = _derive(_good_head())
    head = head_onsets(head_anatomy(_good_head(), cycle_beats=16.0, accents=_ACCENTS))
    assert set(head) <= set(_onsets(riff.notes))
    assert abs(sum(n.dur for n in riff.notes) - 16.0) < 1e-6
    assert verify_riff(riff, cycle_beats=16.0) == []


def test_the_accent_structure_and_the_sam_survive():
    arr = _chart()
    accents = [(a.beat, a.swara) for a in riff_accents(_derive(_good_head()), arr)]
    assert accents == [(0.0, "S"), (4.0, "m"), (12.0, "m")]      # the head's sam and tali swaras
    first = _derive(_good_head()).notes[0]
    assert first.technique is None and first.vel >= 120       # the sam rings, hit hardest


def test_structural_notes_become_roots_at_their_onsets():
    anatomy = head_anatomy(_good_head(), cycle_beats=16.0, accents=_ACCENTS)
    strokes = _onsets(_derive(_good_head()).notes)
    for note in structural_notes(anatomy):
        assert strokes[note.onset].swara == note.swara, note


def test_an_ornament_keeps_its_stroke_but_not_its_pitch():
    strokes = _onsets(_derive(_good_head()).notes)
    assert strokes[11.0].swara == strokes[11.5].swara == "d"    # the root already sounding
    assert strokes[11.0].technique == "palm_mute" and strokes[13.0].swara == "m"


def test_a_held_note_becomes_a_strike_and_a_chug_run():
    notes = _derive(_good_head()).notes
    run = [n for n, t in _beats(notes) if 4.0 <= t < 8.0]       # the 4-beat m on the tali
    assert run[0].technique is None and run[0].dur == 1.0
    assert all(n.swara == "m" and n.technique == "palm_mute" and n.dur <= 1.0 for n in run[1:])
    assert len({n.vel for n in run[1:]}) > 1                    # an accented chug run, not flat


def _beats(notes: list[RiffNote]) -> list[tuple[RiffNote, float]]:
    t, out = 0.0, []
    for n in notes:
        out.append((n, t))
        t += n.dur
    return out


def test_the_first_unaccented_meend_becomes_a_slide_and_the_rest_land_plain():
    head = _head(_n("S", 4.0), _n("g", 2.0), _n("d", 2.0, meend_swara="n"),
                 _n("m", 4.0), _n("g", 2.0, meend_swara="m"), _n("S", 2.0))
    strokes = _onsets(_derive(head).notes)
    assert strokes[6.0].swara == "n" and strokes[6.0].technique == "slide" and not strokes[6.0].chord
    assert strokes[12.0].technique is None                      # an accent never slides
    assert [n.technique for n in _derive(head).notes].count("slide") == 1


def test_a_compound_bol_plays_the_heads_own_strokes():
    head = _head(_n("S", 4.0), _n("m", 4.0), _n("g", 2.0, "dir"), _n("m", 6.0))
    strokes = _onsets(_derive(head).notes)
    assert strokes[8.0].swara == strokes[9.0].swara == "g"
    assert strokes[8.0].technique is None and strokes[9.0].technique == "palm_mute"   # di open, r chug


def test_a_head_that_rests_on_the_sam_still_has_the_sam_struck():
    head = _head(LeadNote(swara="S", dur=1.0, rest=True), _n("S", 3.0), _n("m", 12.0))
    first = _derive(head).notes[0]
    assert not first.rest and first.swara == "S"


def test_the_heads_pauses_stay_pauses():
    head = _head(_n("S", 4.0), _n("m", 3.0), LeadNote(swara="S", dur=1.0, rest=True), _n("g", 8.0))
    beats = [(n.rest, t) for n, t in _beats(_derive(head).notes)]
    assert (True, 7.0) in beats


# --- legality and register ---------------------------------------------------------------------

def test_every_root_and_chord_tone_is_legal_across_ragas():
    for raga in ("malkauns", "darbari", "bageshree", "marwa", "todi"):
        head = _raga_head(raga)
        arr = _chart(_mukhada(), _takeover(), raga=raga)
        riff = head_riff(arr, head)
        assert riff is not None and riff.playable, (raga, riff and riff.violations)
        assert riff_grammar_error(riff.pattern, raga) is None, raga
        layer, _ = generate_riff(arr, gen_fn=_fail, head=head)
        comp = assemble_composition(arr, [drone_layer(arr), layer])
        assert validate_composition(comp.model_dump(exclude_none=True)) == [], raga


def test_darbari_never_voices_a_shuddha_ni_or_dha():
    riff = head_riff(_chart(_mukhada(), _takeover(), raga="darbari"), _raga_head("darbari"))
    tones = {c for n in riff.pattern.notes for c in (n.chord or [])}
    assert not tones & {"N", "D"}


def test_the_riff_is_seated_low_and_never_under_the_floor():
    head = _head(_n("S", 4.0), _n("n", 4.0, oct=-1), _n("S", 4.0, oct=1), _n("m", 4.0))
    riff = _derive(head, register=-2)
    assert all(0 <= n.oct <= 1 for n in riff.notes if not n.rest)
    arr = _chart(_mukhada(), _takeover())
    layer, _ = generate_riff(arr, gen_fn=_fail, head=head)
    assert min(n.oct for n in layer.notes) >= RHYTHM_FLOOR


def test_a_root_entered_against_the_direction_rule_holds_the_previous_root():
    # Bageshree's Pa is descent-only. The head sings S -> mandra P (from above — legal), but the
    # guitar cannot go below its floor, so P is seated up beside S and would be entered from
    # below: it holds S instead.
    head = _head(_n("S", 4.0), _n("m", 4.0), _n("S", 2.0), _n("P", 2.0, oct=-1), _n("m", 4.0))
    riff = _derive(head, raga="bageshree", register=-2)
    roots = [(n.swara, n.oct) for n in riff.notes if not n.rest]
    assert not direction_violations(roots, "bageshree")
    assert "P" not in {n.swara for n in riff.notes}


# --- which slots inherit the head --------------------------------------------------------------

def test_the_head_slot_and_the_guitar_takeover_inherit_it_but_a_contrast_does_not():
    assert derived_slots(_chart()) == {"main", "takeover"}
    before = _chart(_takeover(slot="intro_riff"), _mukhada(), _takeover())
    assert "intro_riff" not in derived_slots(before)            # the guitar answers the head
    song = _chart(_takeover(), _takeover(slot="other"))
    assert derived_slots(song) == frozenset()                   # no mukhada, nothing to inherit


def test_riff_first_never_derives_the_riff_from_the_head():
    assert head_riff(_chart(anchor="riff_first"), _good_head()) is None
    assert head_riff(_chart(), None) is None


# --- generation: no model call for an inherited slot ------------------------------------------

def test_inherited_slots_cost_no_model_call_and_a_contrast_does():
    fn, calls = _recorder(_OTHER)
    arr = _chart()
    layer, events = generate_riff(arr, gen_fn=fn, head=_good_head())
    assert calls == [2]                                          # only the breakdown
    derived = [e for e in events if (e.data or {}).get("from_head")]
    assert {e.data["slot"] for e in derived} == {"main", "takeover"}
    seed = next(e.data[RIFF_EVENT_KEY] for e in events if RIFF_EVENT_KEY in (e.data or {}))
    assert seed["notes"][0]["swara"] == "S"                     # the published mukhada riff IS it


def test_a_reworked_slot_goes_back_to_the_model():
    fn, calls = _recorder(_OTHER)
    generate_riff(_chart(), gen_fn=fn, head=_good_head(), rework=frozenset({"takeover"}))
    assert calls == [1, 2]


def test_the_composers_gat_first_head_wins_over_a_seed_riff_written_before_it():
    arr = _chart(_mukhada(), _takeover(slot="main")).model_copy(
        update={"seed_riff": _OTHER, "seed_hook": _good_head()})
    layer, events = compose_seeded_riff(arr, others=_fail)
    assert any((e.data or {}).get("from_head") for e in events)
    under_sitar = [(n.swara, n.start) for n in layer.notes if n.start < 16.0]
    assert under_sitar == [("S", 0.0), ("m", 4.0), ("m", 12.0)]      # the head's accents, not g
    takeover = next(n for n in layer.notes if n.start == 16.0)
    assert takeover.swara == "S" and takeover.dur == 1.0             # the faithful statement


def test_without_a_head_generation_is_unchanged():
    fn, calls = _recorder(_OTHER)
    generate_riff(_chart(), gen_fn=fn)
    assert calls == [0, 1, 2]


# --- development by statement ------------------------------------------------------------------

def test_the_first_guitar_statement_is_faithful_and_later_ones_grow_heavier():
    takeover = _takeover(bars=3)
    variants = [statement_variant(takeover, b, 3, is_final_rhythm=False, statement=b)
                for b in range(3)]
    assert variants == ["base", "heavy", "syncopated"]
    assert statement_variant(_mukhada(), 0, 1, is_final_rhythm=False, statement=0) == "space"


def test_the_statement_count_threads_across_sections_and_skips_the_sitars():
    base = list(_derive(_good_head()).notes)
    _, after_mukhada = develop_statements(base, _mukhada(), is_final_rhythm=False,
                                          first_statement=0, raga="malkauns", accents=_ACCENTS)
    assert after_mukhada == 0                                    # under the sitar: no statement
    cycles, after = develop_statements(base, _takeover(bars=2), is_final_rhythm=False,
                                       first_statement=after_mukhada, raga="malkauns",
                                       accents=_ACCENTS)
    assert cycles[0] == base and after == 2


def test_heavy_keeps_the_accents_and_drops_the_chugs_onto_a_pedal():
    base = list(_derive(_good_head()).notes)
    heavy = apply_statement(base, "heavy", raga="malkauns", accents=_ACCENTS)
    strokes = _onsets(heavy)
    assert [strokes[b].swara for b in (0.0, 4.0, 12.0)] == ["S", "m", "m"]
    assert strokes[5.0].swara == "S" and strokes[5.0].technique == "palm_mute"   # a pedal chug
    assert abs(sum(n.dur for n in heavy) - 16.0) < 1e-6


def test_syncopated_pushes_the_last_tali_an_eighth_early():
    base = list(_derive(_good_head()).notes)
    synced = _onsets(apply_statement(base, "syncopated", raga="malkauns", accents=_ACCENTS))
    assert 11.5 in synced and synced[11.5].swara == "m" and 12.0 not in synced


def test_under_the_sitar_only_the_accents_remain_ringing():
    base = list(_derive(_good_head()).notes)
    space = apply_statement(base, "space", raga="malkauns", accents=_ACCENTS)
    assert sorted(_onsets(space)) == [0.0, 4.0, 12.0]
    assert all(n.technique is None for n in space if not n.rest)
    assert abs(sum(n.dur for n in space) - 16.0) < 1e-6


def test_a_statement_that_would_break_the_direction_rule_falls_back():
    # Bageshree: D then a re-struck D (-> the pedal S) then P would enter P from below.
    base = [RiffNote(swara="S", dur=4.0), RiffNote(swara="D", dur=1.0),
            RiffNote(swara="D", dur=1.0), RiffNote(swara="P", dur=2.0), RiffNote(swara="S", dur=8.0)]
    heavy = apply_statement(base, "heavy", raga="bageshree", accents=_ACCENTS)
    roots = [(n.swara, n.oct) for n in heavy if not n.rest]
    assert not direction_violations(roots, "bageshree")
    assert [r[0] for r in roots] == ["S", "D", "D", "P", "S"]     # the pitch-safe prime


# --- kinship, measured for the Producer --------------------------------------------------------

def _composed(arr: Arrangement, gen_fn) -> tuple:
    layer, _ = generate_riff(arr, gen_fn=gen_fn, head=arr.seed_hook)
    return assemble_composition(arr, [drone_layer(arr), layer])


def test_kinship_is_full_for_the_faithful_statement_and_low_for_a_stranger():
    arr = _chart(head=_good_head())
    rows = {r.index: r for r in kinship_report(_composed(arr, lambda s, a, m: _OTHER), arr)}
    takeover = rows[1]          # faithful, heavy, syncopated: the push moves one tali in three
    assert abs(takeover.accents - (1 + 1 + 2 / 3) / 3) < 0.01 and takeover.rhythm > 0.9
    assert rows[2].structure < 0.3                               # the breakdown went its own way
    assert rows[0].under_sitar and rows[0].accents == 1.0 and rows[0].rhythm < 0.5


def test_kinship_is_silent_without_a_head_and_reaches_the_producer():
    from crew.producer import judge_inputs
    plain = _chart()
    comp = _composed(plain, lambda s, a, m: _OTHER)
    assert kinship_report(comp, plain) == [] and render_kinship(comp, plain) == ""
    arr = _chart(head=_good_head())
    comp = _composed(arr, lambda s, a, m: _OTHER)
    block = render_kinship(comp, arr)
    assert "KINSHIP" in block and "section 1 (riff, guitar-led)" in block
    assert block in judge_inputs(comp, arr)["metrics"]


# --- the chikari seam --------------------------------------------------------------------------

def test_extra_right_hand_strokes_add_chugs_and_join_the_rhythm():
    riff = _derive(_good_head(), extra_onsets=[0.5])
    strokes = _onsets(riff.notes)
    assert strokes[0.0].dur == 0.5 and strokes[0.5].technique == "palm_mute"
    anatomy = head_anatomy(_good_head(), cycle_beats=16.0, accents=_ACCENTS)
    assert 0.5 in head_onsets(anatomy, [0.5]) and 0.5 not in head_onsets(anatomy)


# --- the prompt: the head riff as starting material --------------------------------------------

def test_every_riff_placeholder_is_filled_and_the_head_riff_is_shown():
    tasks = yaml.safe_load((Path(__file__).parents[1] / "crew" / "config" / "tasks.yaml").read_text())
    text = tasks["generate_riff"]["description"] + tasks["generate_riff"]["expected_output"]
    placeholders = set(re.findall(r"\{([a-z_]+)\}", text))
    arr = _chart()
    spans = section_spans(arr)
    with_head = _RiffContext(arr, _good_head())
    breakdown = with_head.inputs_for(spans[2], [])
    assert placeholders <= set(breakdown), placeholders - set(breakdown)
    assert "mukhada_riff" in placeholders
    assert "S(1) S:pm(0.5)" in breakdown["mukhada_riff"] and "DEVELOP from it" in breakdown["mukhada_riff"]
    assert "reworking it" in with_head.inputs_for(spans[1], [])["mukhada_riff"]
    assert "no head riff" in _RiffContext(arr).inputs_for(spans[0], [])["mukhada_riff"]


def test_the_prompt_block_names_the_heads_accent_roots():
    arr = _chart()
    block = render_head_riff(head_riff(arr, _good_head()), arr, "crush")
    assert "sam beat 0 S, tali beat 4 m, tali beat 12 m" in block


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
