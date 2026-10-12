"""
Tests for the ANCHOR seam — which creative voice seeds the piece, all pure (no key, no cost).

`Arrangement.anchor` used to be decorative: the lead was always composed first and every
mukhada riff was told it reduces the head. Now the order follows the anchor
(`compose_creative_voices`), a `riff_first` riff is told it is the source, its mukhada riff
rides the event stream to the gat, and the gat's head is VERIFIED to quote the riff's
accented roots (`verify_riff_quote`). Proven here with fakes in place of the LLM.

Runs as a script (`uv run python tests/test_anchor.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.anchor import RiffAccent, render_gat_source, riff_accents  # noqa: E402
from crew.band import compose_creative_voices  # noqa: E402
from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    DebateEvent,
    EventType,
    Gat,
    LeadNote,
    LeadPhrase,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.gat_verifier import verify_riff_quote  # noqa: E402
from crew.generators import section_spans  # noqa: E402
from crew.lead import _GatContext, generate_lead  # noqa: E402
from crew.riff import _RiffContext, generate_riff, mukhada_riff_from_events  # noqa: E402
from tests.test_lead import _good_head  # noqa: E402


def _arr(anchor: str = "riff_first", *, roles: tuple[str | None, ...] = ("mukhada",),
         layers: tuple[str, ...] = ("lead", "rhythm", "drone"),
         slots: tuple[str | None, ...] | None = None) -> Arrangement:
    """A Malkauns teentaal chart (16-beat cycle; sam 0, talis 4 and 12, khali 8)."""
    sections = [Section(kind=SectionKind.ALAAP, bars=1, layers=list(layers), foreground="lead",
                        form_role=role, riff_slot=(slots[i] if slots else None))
                for i, role in enumerate(roles)]
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections, anchor=anchor)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _riff(*notes: tuple[str, float], rest_at: int | None = None) -> RiffPattern:
    return RiffPattern(notes=[RiffNote(swara=s, dur=d, rest=(i == rest_at))
                              for i, (s, d) in enumerate(notes)])


# The good head sounds S on beat 0, m on beat 4, m on beat 12 — a riff with those roots is quoted.
_QUOTED_RIFF = _riff(("S", 4.0), ("m", 4.0), ("g", 4.0), ("m", 4.0))
_UNQUOTED_RIFF = _riff(("g", 4.0), ("d", 4.0), ("S", 4.0), ("n", 4.0))


# --- reading the riff's accented roots ---------------------------------------------------

def test_riff_accents_read_the_sam_and_talis_never_the_khali():
    accents = riff_accents(_QUOTED_RIFF, _arr())
    assert [(a.kind, a.beat, a.swara) for a in accents] == [
        ("sam", 0.0, "S"), ("tali", 4.0, "m"), ("tali", 12.0, "m")]


def test_a_rest_on_an_accent_states_nothing_to_quote():
    riff = _riff(("S", 4.0), ("m", 4.0), ("g", 4.0), ("m", 4.0), rest_at=1)
    assert [a.beat for a in riff_accents(riff, _arr())] == [0.0, 12.0]


def test_a_short_riff_extends_its_last_note_to_the_cycle_edge():
    # mirrors _sequence_cycle: a pattern that falls short rings its last note to the edge
    riff = _riff(("S", 2.0), ("m", 4.0))
    assert [a.swara for a in riff_accents(riff, _arr())] == ["S", "m", "m"]


# --- the quote check ---------------------------------------------------------------------

def test_a_head_on_the_riffs_roots_quotes_it():
    accents = riff_accents(_QUOTED_RIFF, _arr())
    assert verify_riff_quote(_good_head(), accents) == []


def test_a_head_missing_the_riffs_roots_is_flagged_with_the_beats():
    accents = riff_accents(_UNQUOTED_RIFF, _arr())
    viol = verify_riff_quote(_good_head(), accents)
    assert len(viol) == 1 and "riff_first" in viol[0]
    assert "sam beat 0 g" in viol[0] and "at least 2" in viol[0]


def test_half_the_accents_is_enough_the_head_sings_between_them():
    accents = [RiffAccent(0.0, "sam", "S"), RiffAccent(4.0, "tali", "g"),
               RiffAccent(12.0, "tali", "m")]                  # head: S, m, m -> 2 of 3
    assert verify_riff_quote(_good_head(), accents) == []


def test_a_meend_is_judged_at_its_target_and_a_rest_is_a_miss():
    head = LeadPhrase(phrase_plan=_good_head().phrase_plan,
                      notes=[LeadNote(swara="g", dur=4.0, meend_swara="S"),   # sounds S
                             LeadNote(swara="m", dur=12.0, rest=True)])
    accents = [RiffAccent(0.0, "sam", "S"), RiffAccent(4.0, "tali", "m")]
    assert verify_riff_quote(head, accents) == []                # 1 of 2 = half
    assert verify_riff_quote(head, accents + [RiffAccent(12.0, "tali", "m")])  # 1 of 3


def test_no_accents_means_nothing_to_quote():
    assert verify_riff_quote(_good_head(), []) == []


# --- what each voice is told -------------------------------------------------------------

def test_the_gat_is_shown_the_riff_only_when_the_riff_is_the_source():
    shown = render_gat_source(_arr("riff_first"), _QUOTED_RIFF)
    assert "riff_first" in shown and "QUOTES" in shown and "sam beat 0 S" in shown
    for line in (render_gat_source(_arr("gat_first"), _QUOTED_RIFF),
                 render_gat_source(_arr("riff_first"), None)):    # nothing to quote -> head leads
        assert "gat_first" in line and "QUOTES" not in line


def test_the_gat_prompt_carries_the_source_block():
    inputs = _GatContext(_arr("riff_first"), _QUOTED_RIFF).inputs_for(
        needs_manjha=False, needs_antara=False, needs_amad=False)
    assert "QUOTES" in inputs["riff_source"]


def test_a_riff_first_riff_is_told_it_is_the_source_not_a_reduction():
    arr = _arr("riff_first")
    line = _RiffContext(arr).inputs_for(section_spans(arr)[0], [])["mukhada_line"]
    assert "YOU are the source" in line and "REDUCTION" not in line
    assert "beat 0 (sam)" in line                                # the beats the head will quote


def test_a_gat_first_riff_still_reduces_the_head():
    arr = _arr("gat_first")
    line = _RiffContext(arr, _good_head()).inputs_for(section_spans(arr)[0], [])["mukhada_line"]
    assert "RHYTHMIC REDUCTION" in line


# --- the seam: the mukhada riff rides the events -----------------------------------------

def test_the_mukhada_riff_rides_the_event_stream():
    arr = _arr()
    _, events = generate_riff(arr, gen_fn=lambda span, a, memory: _QUOTED_RIFF)
    seed = mukhada_riff_from_events(events)
    assert seed is not None and [n.swara for n in seed.notes] == ["S", "m", "g", "m"]
    assert mukhada_riff_from_events([]) is None


def test_a_reprised_main_riff_is_still_published_for_the_head():
    # the main riff is written in an earlier section; the mukhada REPLAYS it (a reprise event)
    arr = _arr(roles=(None, "mukhada"), slots=("main", "main"))
    _, events = generate_riff(arr, gen_fn=lambda span, a, memory: _QUOTED_RIFF)
    assert mukhada_riff_from_events(events) is not None
    assert sum("mukhada_riff" in e.data for e in events) == 1     # published exactly once


# --- the gat quotes the riff ---------------------------------------------------------------

def _recording_gen(phrase: LeadPhrase):
    feedbacks: list[list[str] | None] = []

    def fn(span, arr, memory, feedback=None):
        feedbacks.append(feedback)
        return phrase

    return fn, feedbacks


def _gat_fn(arr, *, needs_manjha, needs_antara, needs_amad):
    return Gat(anchor="the riff", mukhada=_good_head())


def test_a_riff_first_head_that_misses_the_riff_is_repaired_with_the_quote_named():
    fn, feedbacks = _recording_gen(_good_head())
    generate_lead(_arr(layers=("lead", "drone")), gen_fn=fn, gat_fn=_gat_fn,
                  riff_source=_UNQUOTED_RIFF)
    assert feedbacks and any(fb and any("riff_first" in v for v in fb) for fb in feedbacks)


def test_a_riff_first_head_that_quotes_the_riff_is_kept():
    fn, feedbacks = _recording_gen(_good_head())
    generate_lead(_arr(layers=("lead", "drone")), gen_fn=fn, gat_fn=_gat_fn,
                  riff_source=_QUOTED_RIFF)
    assert feedbacks == []                                      # no repair call at all


def test_a_gat_first_piece_never_checks_a_quote():
    fn, feedbacks = _recording_gen(_good_head())
    generate_lead(_arr("gat_first", layers=("lead", "drone")), gen_fn=fn, gat_fn=_gat_fn,
                  riff_source=_UNQUOTED_RIFF)
    assert feedbacks == []


# --- the order follows the anchor -------------------------------------------------------------

def _event(**data) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent="x", role="generator", text="x", data=data)


def _voices(order: list[tuple[str, object]]):
    def lead(arr, riff):
        order.append(("lead", riff))
        return [], [_event(mukhada_cell=_good_head().model_dump(exclude_none=True))]

    def riff(arr, mukhada):
        order.append(("riff", mukhada))
        return None, [_event(mukhada_riff=_QUOTED_RIFF.model_dump(exclude_none=True))]

    return lead, riff


def test_riff_first_composes_the_riff_and_hands_it_to_the_gat():
    order: list[tuple[str, object]] = []
    lead, riff = _voices(order)
    _, _, events = compose_creative_voices(_arr("riff_first"), lead_fn=lead, riff_fn=riff)
    assert [who for who, _ in order] == ["riff", "lead"]
    assert order[0][1] is None and isinstance(order[1][1], RiffPattern)
    assert "mukhada_riff" in events[0].data                      # events in composition order


def test_gat_first_composes_the_gat_and_hands_the_head_to_the_riff():
    order: list[tuple[str, object]] = []
    lead, riff = _voices(order)
    announced: list[str] = []
    compose_creative_voices(_arr("gat_first"), lead_fn=lead, riff_fn=riff,
                            announce=lambda agent, text: announced.append(agent))
    assert [who for who, _ in order] == ["lead", "riff"]
    assert order[0][1] is None and isinstance(order[1][1], LeadPhrase)
    assert announced == ["Lead", "Riff"]                         # the live beats lead each call


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
