"""
Tests for the TARGETED revise (crew/realized.py + the `keep` path of the lead and riff
generators) — pure, no LLM.

A pass publishes what each voice realized; a revise hands the kept part back, and the model is
called ONLY for the sections the plan names (the 2026-10-11 run paid nine lead calls per round to
keep one or two). A plan that names the head widens to every hook section — the head returns
verbatim, so it changes everywhere or nowhere.

Runs as a script (`uv run python tests/test_realized.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    LeadNote,
    LeadPhrase,
    PhrasePlan,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.lead import generate_lead, lead_revise_targets  # noqa: E402
from crew.realized import kept_lead, kept_riffs, realized_lead, realized_riffs  # noqa: E402
from crew.riff import generate_riff  # noqa: E402


def _chart(kinds_roles: list[tuple[SectionKind, str | None]], layers: list[str]):
    sections = [Section(kind=k, bars=1, layers=list(layers), foreground=layers[0], form_role=r)
                for k, r in kinds_roles]
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _phrase(*swaras: str) -> LeadPhrase:
    plan = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"], climax_and_sam="Sa")
    return LeadPhrase(phrase_plan=plan, notes=[LeadNote(swara=s, dur=2.0) for s in swaras])


def _lead_fake(phrases: list[LeadPhrase]):
    calls: list[int] = []
    memories: list = []
    it = iter(phrases)

    def fn(span, arr, memory, *, feedback=None):
        calls.append(span.index)
        memories.append([m.phrase for m in memory])
        return next(it)

    return fn, calls, memories


def test_a_lead_revise_calls_the_model_only_for_the_named_section():
    arr = _chart([(SectionKind.ALAAP, None)] * 3, ["lead", "drone"])
    first = [_phrase("S", "m"), _phrase("g", "m"), _phrase("d", "n")]
    fn, calls, _ = _lead_fake(first)
    _, events = generate_lead(arr, gen_fn=fn)
    kept = realized_lead(events)
    assert kept is not None and kept.phrases == dict(enumerate(first))

    fresh = _phrase("m", "d")
    fn, calls, memories = _lead_fake([fresh])
    _, events = generate_lead(arr, gen_fn=fn, keep=kept_lead(kept, [1]))
    assert calls == [1]                                  # one call, for the named section only
    assert memories[0] == [first[0]]                     # it still hears the section before it
    assert realized_lead(events).phrases == {0: first[0], 1: fresh, 2: first[2]}


def test_naming_the_head_widens_the_revise_to_every_return():
    arr = _chart([(SectionKind.ALAAP, "intro"), (SectionKind.MELODY, "mukhada"),
                  (SectionKind.MELODY, "manjha"), (SectionKind.MELODY, "mukhada")],
                 ["lead", "drone"])
    assert lead_revise_targets(arr, [1]) == [1, 3]       # the head changes everywhere or nowhere
    assert lead_revise_targets(arr, [2]) == [2]          # a manjha edit stays a manjha edit


def _riff(*swaras: str) -> RiffPattern:
    return RiffPattern(notes=[RiffNote(swara=s, dur=4.0) for s in swaras])


def test_a_riff_revise_recomposes_only_the_named_sections_slot():
    sections = [Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drums"],
                        foreground="rhythm", riff_slot=slot) for slot in ("main", "bridge", "main")]
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    main, bridge, new_bridge = _riff("S", "S", "g", "S"), _riff("m", "m", "d", "m"), _riff("n", "S", "n", "S")
    calls: list[int] = []
    queue = iter([main, bridge, new_bridge])

    def fn(span, arr, memory):
        calls.append(span.index)
        return next(queue)

    _, events = generate_riff(arr, gen_fn=fn)
    library = realized_riffs(events)
    assert library == {"main": main, "bridge": bridge} and calls == [0, 1]
    calls.clear()
    _, events = generate_riff(arr, gen_fn=fn, keep=kept_riffs(library, {"bridge"}))
    assert calls == [1]                                  # the main riff replays, no call
    assert realized_riffs(events) == {"main": main, "bridge": new_bridge}


def test_no_realized_pass_means_nothing_to_keep():
    assert realized_lead([]) is None and realized_riffs([]) is None


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
