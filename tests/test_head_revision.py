"""Pure tests for the gat head's measured self-revision (`crew/head_report.py`,
`crew/head_revision.py`). The reviser is stubbed; no API."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crew.contracts import (ArrangementDraft, CompositionBrief, HeadTurn, LeadNote, LeadPhrase,  # noqa: E402
                            PhrasePlan, Section, SectionKind, build_arrangement)
from crew.gat_verifier import CellChecks  # noqa: E402
from crew.head_report import head_findings, revision_kept, unmet  # noqa: E402
from crew.head_revision import revise_head_once  # noqa: E402


def _head(*tokens: str) -> LeadPhrase:
    """'g:2' = madhya g for 2 beats; 'd-1' = mandra d for 1 beat."""
    notes = []
    for t in tokens:
        name, _, dur = t.partition(":")
        swara, _, octave = name.partition("-")
        notes.append(LeadNote(swara=swara, oct=-int(octave) if octave else 0, dur=float(dur or 1)))
    plan = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"], climax_and_sam="Sa")
    return LeadPhrase(phrase_plan=plan, notes=notes)


# The control run's real heads (out/head_control_20261019_000558), swaras/octaves/durations kept.
DRAFT_A = _head("S", "R", "g", "R", "g:3", "m", "P", "n", "P", "m", "P", "g", "m", "R")       # all madhya
REVISED_A = _head("S", "R", "g", "R", "g:2", "m", "R", "S", "d-1", "n-1", "P-1", "m-1", "P-1", "d-1", "n-1")
DRAFT_B = _head("S", "m", "g", "m", "P", "P", "g:2", "m", "R", "S", "P", "m", "g", "m", "R")
OVERSHOT_B = _head("S", "d-1", "n-1", "P-1", "m-1", "P-1", "g-1:2", "m-1", "R-1", "S-1", "P-1", "m-1", "g-1",
                   "m-1", "R-1")                                                          # 94% mandra
MET = _head("S", "d-1", "n-1", "P-1", "d-1:2", "n-1", "P-1", "S", "R", "g", "m", "P", "g", "m", "R")


def _arr():
    section = Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "drone"], foreground="lead",
                      form_role="mukhada")
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=60, motif=["S"],
                             sections=[section])
    return build_arrangement(draft, CompositionBrief(request="a slow doom gat in Darbari"))


def _sound(_: LeadPhrase) -> CellChecks:
    return CellChecks()


def _reviser(head: LeadPhrase, changed: bool = True, calls: list | None = None):
    def revise(arr, own, report, verify):
        if calls is not None:
            calls.append(report)
        return HeadTurn(argument="moved low", changed=changed, head=head)
    return revise


def test_the_drafts_miss_the_register_the_prompt_states():
    assert [f.name for f in unmet(head_findings(DRAFT_A, "darbari", 60))] == ["register"]
    assert unmet(head_findings(MET, "darbari", 60)) == []


def test_a_head_that_meets_every_fact_never_reaches_the_model():
    calls, events = [], []
    assert revise_head_once(_arr(), MET, verify=_sound, reviser=_reviser(DRAFT_A, calls=calls),
                            events=events) is MET
    assert calls == [] and events == []


def test_a_revision_that_fixes_the_register_is_kept_and_reported():
    calls, events = [], []
    out = revise_head_once(_arr(), DRAFT_A, verify=_sound, reviser=_reviser(REVISED_A, calls=calls), events=events)
    assert out is REVISED_A and events[0].data["kept"] and events[0].data["missed"] == ["register"]
    assert "MISSED  register" in calls[0] and "mandra 0%" in calls[0]


def test_a_traded_fault_keeps_the_draft():
    """The control's B: chasing '0% below Sa' to 94% lost the madhya the raga also lives in."""
    assert not revision_kept(head_findings(DRAFT_B, "darbari", 60), head_findings(OVERSHOT_B, "darbari", 60))
    events = []
    assert revise_head_once(_arr(), DRAFT_B, verify=_sound, reviser=_reviser(OVERSHOT_B), events=events) is DRAFT_B
    assert not events[0].data["kept"] and "traded" in events[0].data["why"]


def test_a_revision_must_keep_the_first_note_and_pass_the_checks():
    moved = _head("R", "R", "g", "R", "g:2", "m", "R", "S", "d-1", "n-1", "P-1", "m-1", "P-1", "d-1", "n-1")
    events = []
    assert revise_head_once(_arr(), DRAFT_A, verify=_sound, reviser=_reviser(moved), events=events) is DRAFT_A
    assert "first note" in events[0].data["why"]
    broken = revise_head_once(_arr(), DRAFT_A, verify=lambda c: CellChecks(hard=("rest inside the head",)),
                              reviser=_reviser(REVISED_A), events=events)
    assert broken is DRAFT_A and "checks" in events[-1].data["why"]


def test_the_revision_guardrail_holds_the_keep_rules_lines():
    """The live guardrail checks what the keep rule checks: the full verification and the first note,
    so a fixable fault goes back for the retry instead of discarding the revision."""
    from crew.head_revision import head_turn_guardrail

    class _Out:
        def __init__(self, turn):
            self.pydantic, self.raw = turn, turn.model_dump_json()
    ends_badly = lambda c: CellChecks(hard=("the mukhada ends on n, not a resting swara",))  # noqa: E731
    ok, why = head_turn_guardrail(_arr(), ends_badly, ("S", 0))(_Out(HeadTurn(changed=True, head=REVISED_A)))
    assert not ok and "ends on n" in why
    moved = _head(*["R"] * 16)
    ok, why = head_turn_guardrail(_arr(), _sound, ("S", 0))(_Out(HeadTurn(changed=True, head=moved)))
    assert not ok and "first note" in why


def test_a_dead_or_declined_call_keeps_the_draft():
    def dead(arr, own, report, verify):
        raise ConnectionError("503")
    events = []
    assert revise_head_once(_arr(), DRAFT_A, verify=_sound, reviser=dead, events=events) is DRAFT_A
    assert revise_head_once(_arr(), DRAFT_A, verify=_sound, reviser=_reviser(REVISED_A, changed=False),
                            events=events) is DRAFT_A
    assert [e.data["kept"] for e in events] == [False, False]


def test_a_raga_with_no_register_entry_is_measured_on_what_it_has():
    assert "register" not in {f.name for f in head_findings(DRAFT_A, "yaman", 120)}
    assert "andolan" not in {f.name for f in head_findings(DRAFT_A, "darbari", 120)}   # not vilambit


def test_the_pass_is_on_by_default():
    from crew.config import head_revision_enabled
    saved = os.environ.pop("RMA_HEAD_REVISE", None)
    try:
        assert head_revision_enabled()
        os.environ["RMA_HEAD_REVISE"] = "0"
        assert not head_revision_enabled()
    finally:
        os.environ.pop("RMA_HEAD_REVISE", None)
        if saved is not None:
            os.environ["RMA_HEAD_REVISE"] = saved


def test_the_live_task_fills_every_placeholder():
    import re

    from crew.head_revision import _config, render_your_head, revise_inputs
    from crew.head_report import render_head_report
    task = _config("tasks.yaml")["revise_head"]["description"]
    inputs = revise_inputs(_arr(), "the gat head you wrote",
                           render_your_head(DRAFT_A, render_head_report(head_findings(DRAFT_A, "darbari", 60))))
    needed = set(re.findall(r"\{(\w+)\}", task))
    assert needed <= set(inputs), needed - set(inputs)


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
