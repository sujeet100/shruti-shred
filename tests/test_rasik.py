"""
Tests for Rasik, the TASTE critic — the CODE side, with no LLM (free, no key).

Rasik's verdict is the model's (taste is not checkable), so what's testable without
an LLM is the plumbing: the deterministic pakad-presence grounding, the renderers
that feed the judge, the `assess` control flow over an injected fake judge, and that
the CRITIQUE event carries the rubric as scores. The real graded judgment is
exercised live via `uv run python -m crew.rasik`, not here.

Runs as a script (`uv run python tests/test_rasik.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    Composition,
    EventType,
    Layer,
    Note,
    RasikScores,
    RasikSuggestion,
    RasikVerdict,
)
from crew.rasik import (  # noqa: E402
    _lead_swaras,
    _note_token,
    _render_pakad_hint,
    assess,
    judge_inputs,
    pakad_presence,
    register_profile,
)
from raga import RAGAS  # noqa: E402

_RAGA = "darbari"
_PAKAD = RAGAS[_RAGA]["pakad"][0]                 # a signature phrase, e.g. S R g R g m P
_SA = RAGAS[_RAGA]["allowed"][0]


def _comp(lead_swaras: list[str]) -> Composition:
    return Composition(
        raga=_RAGA, sa=62, bpm=90, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[
            Layer(role="drone", notes=[Note(swara=_SA, oct=-2, start=0.0, dur=16.0)]),
            Layer(role="lead", notes=[
                Note(swara=sw, oct=0, start=float(i), dur=1.0) for i, sw in enumerate(lead_swaras)])])


def _fake_judge(scores: RasikScores, notes: str = "", reasoning: str = ""):
    """A stand-in Rasik: returns a canned verdict and records how it was called."""
    calls: list[Composition] = []

    def fn(comp):
        calls.append(comp)
        return RasikVerdict(scores=scores, notes=notes, reasoning=reasoning)

    return fn, calls


def test_pakad_presence_detects_a_literal_quote():
    # a lead that quotes the pakad verbatim (plus a trailing note) -> literal
    found = {tuple(p): v for p, v in pakad_presence(list(_PAKAD) + [_SA], _RAGA)}
    assert found[tuple(_PAKAD)] == "literal"


def test_pakad_presence_is_absent_when_missing():
    hits = pakad_presence([_SA, _SA, _SA], _RAGA)
    assert all(match == "absent" for _, match in hits)


def test_pakad_presence_tolerates_a_wedged_grace_note():
    # every pakad swara is present in order, one grace note wedged mid-phrase: no longer
    # a literal run, but the fuzzy tier evokes it (the brittleness this fixes)
    ornamented = [*_PAKAD[:2], _SA, *_PAKAD[2:]]
    found = {tuple(p): v for p, v in pakad_presence(ornamented, _RAGA)}
    assert found[tuple(_PAKAD)] == "fuzzy"


def test_pakad_presence_absent_when_scattered_beyond_the_gap():
    # pakad swaras present but strung far apart (gaps > the fuzzy window) -> absent,
    # so a coincidental scatter across the whole line does not count as present
    filler = [_SA, _SA, _SA, _SA]
    scattered = [_PAKAD[0], *filler, _PAKAD[1], *filler, *_PAKAD[2:]]
    found = {tuple(p): v for p, v in pakad_presence(scattered, _RAGA)}
    assert found[tuple(_PAKAD)] == "absent"


def test_lead_swaras_reads_the_lead_in_time_order():
    comp = Composition(
        raga=_RAGA, sa=62, bpm=90, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="lead", notes=[
            Note(swara="P", oct=0, start=2.0, dur=1.0),
            Note(swara="S", oct=0, start=0.0, dur=1.0),
            Note(swara="R", oct=0, start=1.0, dur=1.0)])])
    assert _lead_swaras(comp) == ["S", "R", "P"]           # sorted by start, not input order


def test_pakad_hint_marks_literal_fuzzy_and_absent():
    literal = _render_pakad_hint(_comp(list(_PAKAD)))
    assert "appears verbatim" in literal
    fuzzy = _render_pakad_hint(_comp([*_PAKAD[:2], _SA, *_PAKAD[2:]]))
    assert "ornamented" in fuzzy
    absent = _render_pakad_hint(_comp([_SA, _SA]))
    assert "not found in the lead" in absent


def test_assess_streams_the_rubric_as_event_scores():
    scores = RasikScores(pakad=5, idiom=4, rasa=4)
    verdict, events = assess(_comp(list(_PAKAD)), judge_fn=_fake_judge(scores, notes="has soul")[0])
    critique = [e for e in events if e.type == EventType.CRITIQUE]
    assert len(critique) == 1
    assert critique[0].agent == "Rasik"
    assert critique[0].text == "has soul"
    assert critique[0].scores == {"pakad": 5.0, "idiom": 4.0, "rasa": 4.0}


def test_assess_passes_the_composition_to_the_judge():
    fn, calls = _fake_judge(RasikScores(pakad=3, idiom=3, rasa=3))
    assess(_comp(list(_PAKAD)), judge_fn=fn)
    assert len(calls) == 1 and calls[0].raga == _RAGA


def test_scores_are_bounded_1_to_5():
    # the rubric contract itself enforces the fixed scale (a bias countermeasure)
    try:
        RasikScores(pakad=6, idiom=3, rasa=3)
        assert False, "expected a validation error for a score above 5"
    except Exception:
        pass



def test_suggestions_ride_the_event_and_are_capped_at_three():
    # the consultant's edits reach the Producer (and the UI) on the CRITIQUE event; a long
    # wish-list is trimmed to the three that matter most
    many = [RasikSuggestion(section=i, change=f"edit {i}", why="pakad") for i in range(5)]

    def judge(comp):
        return RasikVerdict(scores=RasikScores(pakad=2, idiom=3, rasa=3), suggestions=many)

    verdict, events = assess(_comp(list(_PAKAD)), judge_fn=judge)
    assert [x.section for x in verdict.suggestions] == [0, 1, 2]
    assert len(events[0].data["suggestions"]) == 3


def test_with_the_chart_the_lead_is_shown_by_section():
    # a suggestion must name a section, so the lead line is grouped by the chart's sections
    from crew.contracts import ArrangementDraft, CompositionBrief, Section, SectionKind, build_arrangement
    draft = ArrangementDraft(raga=_RAGA, subgenre="doom", tala="teentaal", bpm=90, motif=["S", "R"],
                             sections=[Section(kind=SectionKind.ALAAP, bars=1, layers=["lead"],
                                               foreground="lead", form_role="intro")])
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    line = judge_inputs(_comp(list(_PAKAD)), arr=arr)["lead_line"]
    assert line.startswith("  section 0 (intro):")

def test_the_lead_line_shows_holds_and_ornaments():
    # a bare swara list hid whether Darbari's komal Ga was held and swayed or merely passed
    from crew.contracts import Note
    held = Note(swara="g", start=0, dur=1.5, grace=["m"], andolan=True)
    passing = Note(swara="g", start=0, dur=0.5)
    glide = Note(swara="R", oct=-1, start=0, dur=1, meend_swara="S")
    assert _note_token(held) == "(m)g~[1.5]"
    assert _note_token(passing) == "g"
    assert _note_token(glide) == "R(-1)>S[1]"


def test_register_profile_weighs_time_not_note_count():
    from crew.contracts import Note
    notes = [Note(swara="d", oct=-1, start=0, dur=3), Note(swara="S", start=3, dur=0.5),
             Note(swara="P", start=3.5, dur=0.5)]
    p = register_profile(notes, home=0)
    assert p["mandra"] == 0.75 and p["madhya"] == 0.25 and p["taar"] == 0.0
    assert p["poorvanga"] == 0.125                       # only the half-beat Sa is S..m


def test_rasik_sees_the_register_fact_and_where_the_line_sits():
    from crew.contracts import Composition, Layer, Note
    lead = Layer(role="lead", instrument="sitar", program=104, channel=2,
                 notes=[Note(swara="g", start=0, dur=2), Note(swara="R", start=2, dur=2)])
    comp = Composition(raga="darbari", sa=62, bpm=64, layers=[lead],
                       tala={"name": "keherwa", "beats_per_bar": 8.0})
    inputs = judge_inputs(comp)
    assert "MANDRA" in inputs["raga_facts"] and "kan (how a swara" in inputs["raga_facts"]
    assert "0% in the mandra" in inputs["motion"]


def test_every_placeholder_in_rasiks_template_is_an_input_it_receives():
    # 2026-10-12: a legend written as "{X}" was read by CrewAI as a template variable and
    # killed a live run at Rasik — prompt text may contain no braces it is not given
    import re

    import yaml
    from crew.contracts import Composition, Layer, Note
    task = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "crew", "config", "tasks.yaml")))["assess_taste"]
    wanted = set(re.findall(r"\{([^{}]*)\}", task["description"] + task["expected_output"]))
    lead = Layer(role="lead", instrument="sitar", program=104, channel=2,
                 notes=[Note(swara="S", start=0, dur=1)])
    comp = Composition(raga="darbari", sa=62, bpm=64, layers=[lead],
                       tala={"name": "keherwa", "beats_per_bar": 8.0})
    assert wanted <= set(judge_inputs(comp)), wanted - set(judge_inputs(comp))


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
