"""
Tests for Ustad, the LEGALITY critic — the CODE side, with no LLM (free, no key).

The one property worth pinning: code — not the model — owns the verdict. `assess`
takes an injected `judge_fn`, so we hand it a fake narration and check that the
verdict/violations still come straight from the deterministic validator: a planted
illegal swara reads "illegal" even when the fake Ustad claims the piece is fine, and
a clean piece reads "legal". We also exercise the tool adapter directly (it surfaces
the same violations) and confirm the CRITIQUE event carries the verdict. The real LLM
narration is exercised live via `uv run python -m crew.ustad`, not here.

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
    UstadNarration,
)
from crew.ustad import (  # noqa: E402
    ValidateCompositionTool,
    _an_illegal_swara,
    _never_cache,
    _validator_tool,
    assess,
)
from raga import RAGAS  # noqa: E402

_RAGA = "bhairav"
_SA = RAGAS[_RAGA]["allowed"][0]                 # Sa — always legal
_FOREIGN = _an_illegal_swara(_RAGA)              # a swara Bhairav forbids


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


def _fake_judge(explanation: str = "", reasoning: str = ""):
    """A stand-in Ustad: returns a canned narration and records how it was called."""
    calls: list[dict] = []

    def fn(comp, payload):
        calls.append({"comp": comp, "payload": payload})
        return UstadNarration(reasoning=reasoning, explanation=explanation)

    return fn, calls


def test_clean_piece_reads_legal():
    verdict, _ = assess(_comp(_SA, _SA), judge_fn=_fake_judge()[0])
    assert verdict.verdict == "legal"
    assert verdict.violations == []


def test_planted_illegal_swara_reads_illegal():
    verdict, _ = assess(_comp(_SA, _FOREIGN), judge_fn=_fake_judge()[0])
    assert verdict.verdict == "illegal"
    assert [v.swara for v in verdict.violations] == [_FOREIGN]
    assert verdict.violations[0].layer == "lead"


def test_code_owns_the_verdict_not_the_llm():
    # The fake Ustad LIES ("all clean"); the deterministic check must still rule illegal.
    lying_judge, _ = _fake_judge(explanation="Looks perfectly legal to me.")
    verdict, _ = assess(_comp(_SA, _FOREIGN), judge_fn=lying_judge)
    assert verdict.verdict == "illegal"                      # code overrides the model
    assert verdict.explanation == "Looks perfectly legal to me."   # but the narration is preserved


def test_judge_is_handed_the_render_payload():
    # the judge (the LLM) runs ONLY when there's a violation to explain — hand it an ILLEGAL piece
    fn, calls = _fake_judge()
    assess(_comp(_SA, _FOREIGN), judge_fn=fn)
    assert len(calls) == 1
    assert calls[0]["payload"]["raga"] == _RAGA                # the dict the tool binds to
    assert any(layer["role"] == "lead" for layer in calls[0]["payload"]["layers"])


def test_clean_piece_skips_the_llm_judge():
    # a LEGAL piece needs no narration — code owns the "legal" verdict, so the LLM/ReAct call is
    # skipped entirely (Sujit, 2026-07-16: "do things programmatically instead of the ReAct loop").
    fn, calls = _fake_judge(explanation="should never be used")
    verdict, _ = assess(_comp(_SA, _SA), judge_fn=fn)
    assert verdict.verdict == "legal" and calls == []          # the judge was NOT called
    assert "legal" in verdict.explanation.lower()              # a deterministic confirmation instead


def test_critique_event_carries_the_verdict():
    _, events = assess(_comp(_SA, _FOREIGN), judge_fn=_fake_judge(explanation="foreign note")[0])
    critique = [e for e in events if e.type == EventType.CRITIQUE]
    assert len(critique) == 1
    assert critique[0].agent == "Ustad" and critique[0].verdict == "illegal"
    assert critique[0].text == "foreign note"
    assert len(critique[0].data["violations"]) == 1


def test_tool_adapter_surfaces_the_same_violations():
    tool = _validator_tool(_comp(_SA, _FOREIGN).model_dump(exclude_none=True))
    result = tool._run()
    assert [v["swara"] for v in result["violations"]] == [_FOREIGN]


def test_tool_is_not_cached():
    # A zero-arg tool with default caching would hand back a PRIOR piece's result;
    # our factory disables caching so each composition is checked fresh.
    tool = _validator_tool(_comp(_SA).model_dump(exclude_none=True))
    assert tool.cache_function() is False


def test_tool_binds_the_composition():
    tool = ValidateCompositionTool(
        composition=_comp(_SA).model_dump(exclude_none=True),
        cache_function=_never_cache)
    assert tool.name == "validate_composition"
    assert tool._run()["violations"] == []                    # a clean piece: no violations


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
