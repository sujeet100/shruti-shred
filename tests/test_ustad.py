"""
Tests for Ustad, the LEGALITY critic — pure code since the redesign (no LLM, free).

Legality is a grammar fact, so the deterministic validator owns the verdict AND, now, its
explanation: a planted illegal swara reads "illegal" with the voice, swara and beat named;
a clean piece reads "legal"; the CRITIQUE event carries the verdict and the violations.

Runs as a script (`uv run python tests/test_ustad.py`) or under pytest.
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
)
from crew.ustad import assess, critique_legality  # noqa: E402
from raga import RAGAS, SWARAS  # noqa: E402

_RAGA = "bhairav"
_SA = RAGAS[_RAGA]["allowed"][0]                 # Sa — always legal
_FOREIGN = next(sw for sw in SWARAS if sw not in RAGAS[_RAGA]["allowed"])  # a swara Bhairav forbids


def _comp(*lead_swaras: str) -> Composition:
    """A tiny drone + lead piece whose lead plays the given swaras (oct 0)."""
    return Composition(
        raga=_RAGA, sa=62, bpm=90, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[
            Layer(role="drone", notes=[Note(swara=_SA, oct=-2, start=0.0, dur=16.0)]),
            Layer(role="lead", notes=[
                Note(swara=sw, oct=0, start=float(i), dur=1.0)
                for i, sw in enumerate(lead_swaras)]),
        ])


def test_clean_piece_reads_legal():
    verdict, _ = assess(_comp(_SA, _SA))
    assert verdict.verdict == "legal" and verdict.violations == []
    assert "legal" in verdict.explanation.lower()


def test_planted_illegal_swara_reads_illegal():
    verdict, _ = assess(_comp(_SA, _FOREIGN))
    assert verdict.verdict == "illegal"
    assert [v.swara for v in verdict.violations] == [_FOREIGN]
    assert verdict.violations[0].layer == "lead"


def test_the_explanation_names_the_voice_the_swara_and_the_beat():
    verdict, _ = assess(_comp(_SA, _FOREIGN))
    assert f"lead plays {_FOREIGN} at beat 1" in verdict.explanation
    assert " ".join(RAGAS[_RAGA]["allowed"]) in verdict.explanation


def test_a_long_list_is_summarised_not_dumped():
    verdict, _ = assess(_comp(*([_FOREIGN] * 6)))
    assert "and 3 more" in verdict.explanation


def test_critique_event_carries_the_verdict():
    _, events = critique_legality(_comp(_SA, _FOREIGN))
    critique = [e for e in events if e.type == EventType.CRITIQUE]
    assert len(critique) == 1
    assert critique[0].agent == "Ustad" and critique[0].verdict == "illegal"
    assert len(critique[0].data["violations"]) == 1


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
