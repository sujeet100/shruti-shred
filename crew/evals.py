"""
A tiny LLM eval harness — ALWAYS surfaces query + reasoning + output.

LLM behaviour is non-deterministic and opaque, so a bare pass/fail hides WHY a
model decided what it did. Every eval here prints the query, the model's own
`reasoning`, and its structured output, then grades it against an expectation.
Use it to diagnose and to A/B models or prompts — never as a silent green check.

This grades the RAW extraction (the model's own output, before any deterministic
grounding), so it measures the MODEL's faithfulness directly.

Run:  uv run python -m crew.evals
      RMA_FLASH_MODEL=gemini/gemini-3.5-flash-lite uv run python -m crew.evals
      RMA_REASONING_EFFORT=medium uv run python -m crew.evals
"""

from __future__ import annotations

import sys
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

from crew.config import flash_model, load_env, reasoning_effort
from crew.contracts import RawIntent
from crew.interpreter import _extract_intent
from crew.tracing import traced, tracing_enabled

_VALUE_FIELDS = ("raga", "key", "subgenre", "mood", "bpm", "instruments")


@dataclass(frozen=True)
class Case:
    """One eval: a query and the fields we expect. A field absent from `expect`
    is expected to be null. `mood` is graded on PRESENCE only (it's fuzzy)."""
    query: str
    expect: dict[str, Any] = field(default_factory=dict)
    note: str = ""


def _norm(value: Any) -> Any:
    """Normalize for comparison: strings lower/stripped (blank -> None), lists sorted."""
    if isinstance(value, str):
        return value.strip().lower() or None
    if isinstance(value, list):
        return sorted(v.strip().lower() for v in value) or None
    return value


def _grade(intent: RawIntent, expect: dict[str, Any]) -> list[str]:
    """Return a list of field mismatches (empty == pass)."""
    got = intent.model_dump(exclude={"reasoning"})
    problems: list[str] = []
    for f in _VALUE_FIELDS:
        want, have = expect.get(f), got.get(f)
        if f == "mood":  # fuzzy: grade presence, not exact wording
            if bool(_norm(have)) != bool(_norm(want)):
                problems.append(f"mood: got {have!r}, want {'a mood' if want else 'null'}")
        elif _norm(have) != _norm(want):
            problems.append(f"{f}: got {have!r}, want {want!r}")
    return problems


def run_eval(cases: list[Case], *, label: str) -> tuple[int, int]:
    """Run every case, PRINTING query + reasoning + output + verdict. Returns (passed, total)."""
    print(f"\n{'=' * 70}\nEVAL: {label}\n{'=' * 70}")
    passed = 0
    for case in cases:
        try:
            intent = _extract_intent(case.query)
        except Exception as e:  # noqa: BLE001 — surface the failure, keep going
            print(f"\nQ: {case.query!r}\n  ERROR: {type(e).__name__}: {str(e)[:160]}")
            continue
        output = intent.model_dump(exclude={"reasoning"}, exclude_none=True)
        if case.expect:
            problems = _grade(intent, case.expect)
            verdict = "PASS" if not problems else "FAIL: " + "; ".join(problems)
            passed += not problems
        else:  # ad-hoc query — nothing to grade, just surface it
            verdict = "(shown — no expectation)"
            passed += 1
        print(f"\nQ: {case.query!r}"
              f"\n  reasoning: {intent.reasoning or '(none returned)'}"
              f"\n  output:    {output}"
              f"\n  {verdict}")
    print(f"\n{'-' * 70}\n{label}: {passed}/{len(cases)} passed\n")
    return passed, len(cases)


# The interpreter golden set: mood-only, full-spec, echo-prone, instruments, mixes.
INTERPRETER_CASES: list[Case] = [
    Case("a crushing, dark metal fusion", {"mood": "crushing, dark"},
         "mood only — must NOT invent a raga/subgenre/tempo/instruments"),
    Case("something epic and heavy", {"mood": "epic, heavy"},
         "mood only — a word or two, not the whole phrase"),
    Case("thrash in Bhairav, key of E, 190 bpm",
         {"raga": "bhairav", "key": "E", "subgenre": "thrash", "bpm": 190},
         "full spec — mood + instruments must stay null (no echo)"),
    Case("a doom track in Malkauns with tabla and drums",
         {"raga": "malkauns", "subgenre": "doom", "instruments": ["tabla", "drums"]},
         "doom is a subgenre not a mood; no invented bpm"),
    Case("a romantic fusion in Bhimpalasi", {"raga": "bhimpalasi", "mood": "romantic"},
         "raga + mood; nothing else"),
    Case("fast death metal in Bhairavi at 220 bpm",
         {"raga": "bhairavi", "subgenre": "death", "bpm": 220},
         "'fast' is not a tempo number; mood null"),
]


def _select(argv: list[str]) -> tuple[list[Case], str]:
    """Pick cases from argv: an index → one golden case; text → one ad-hoc query;
    nothing → the FULL suite (a deliberate regression pass — see CLAUDE.md)."""
    if argv and argv[0].isdigit():
        i = int(argv[0])
        if not 0 <= i < len(INTERPRETER_CASES):
            raise SystemExit(f"case index out of range (0..{len(INTERPRETER_CASES) - 1})")
        return [INTERPRETER_CASES[i]], f"case {i}"
    if argv:
        return [Case(" ".join(argv))], "ad-hoc query"
    return INTERPRETER_CASES, "FULL SUITE"


def main(argv: list[str]) -> int:
    load_env()
    cases, scope = _select(argv)
    label = f"interpreter | {scope} | model={flash_model()} effort={reasoning_effort()}"
    # Trace the eval by default so every run is inspectable in the portal (RMA_TRACE=0 opts out).
    ctx = traced(f"eval · {scope}") if tracing_enabled() else nullcontext()
    with ctx:
        passed, total = run_eval(cases, label=label)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
