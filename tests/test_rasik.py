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
    RasikVerdict,
)
from crew.rasik import (  # noqa: E402
    _lead_swaras,
    _render_pakad_hint,
    assess,
    pakad_presence,
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
