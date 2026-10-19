"""Pure tests for the head debate (`crew/head_debate.py`) and its live turn's wiring
(`seed_debate_crew.llm_head_turn`, with the model call stubbed). No API."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crew.contracts import (ArrangementDraft, CompositionBrief, HeadTurn, LeadNote, LeadPhrase,  # noqa: E402
                            PhrasePlan, Section, SectionKind, build_arrangement)
from crew.head_debate import head_debate, head_measures  # noqa: E402


def _head(*swaras: str, dur: float = 1.0) -> LeadPhrase:
    plan = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"], climax_and_sam="Sa")
    return LeadPhrase(phrase_plan=plan, notes=[LeadNote(swara=s, dur=dur) for s in swaras])


A0, B0 = _head("S", "R", "g", "m"), _head("S", "m", "P", "n")


def test_both_composers_answer_the_same_pair_and_agreement_ends_the_debate():
    seen = []

    def turn(composer, own, other, r):
        seen.append((composer, r, own, other))
        changed = composer == "A" and r == 1
        return HeadTurn(argument=f"{composer}{r}", changed=changed, head=_head("S", "g", "m", "R") if changed else own)
    versions = head_debate({"A": A0, "B": B0}, turn)
    assert [(v.composer, v.round) for v in versions] == [("A", 0), ("B", 0), ("A", 1), ("B", 1), ("A", 2), ("B", 2)]
    assert seen[0][3] == B0 and seen[1][3] == A0          # round 1: both read the proposals
    assert seen[3][3] == versions[2].head                 # round 2: B reads A's revision


def test_kept_means_kept_and_a_dead_turn_keeps_its_head():
    def turn(composer, own, other, r):
        if composer == "B":
            raise ConnectionError("503")
        return HeadTurn(argument="I keep mine", changed=False, head=_head("S", "S", "S", "S"))
    versions = head_debate({"A": A0, "B": B0}, turn, rounds=3)
    assert versions[2].head == A0 and versions[3].head == B0 and len(versions) == 4


def test_cells_are_counted_across_the_loop_back_to_the_sam():
    head = _head("S", "R", "d", "n", "P", "m", "P", "g", "m", "R")       # ends m R; S comes on the sam
    m = head_measures(head)
    assert m["g m R S"] == 1 and m["d n P"] == 1


def _arr():
    section = Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "drone"], foreground="lead",
                      form_role="mukhada")
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=60, motif=["S"],
                             sections=[section])
    return build_arrangement(draft, CompositionBrief(request="a slow doom gat in Darbari"))


def test_the_guardrail_rejects_a_head_of_the_wrong_length_or_an_illegal_swara():
    from crew.seed_debate_crew import head_turn_guardrail
    guard = head_turn_guardrail(_arr())

    class _Out:
        def __init__(self, turn):
            self.pydantic, self.raw = turn, turn.model_dump_json()
    short = guard(_Out(HeadTurn(head=_head("S", "R", "g", "m"))))
    assert not short[0] and "fills 4 beats" in short[1]
    illegal = guard(_Out(HeadTurn(head=_head(*["G"] * 16))))      # shuddha Ga: not Darbari's
    assert not illegal[0]


def test_the_live_turn_fills_every_placeholder_of_its_prompt():
    import crew.seed_debate_crew as live
    captured = {}

    def fake_run(agent_key, llm, task, model, guardrail, retries, inputs):
        captured.update(task=task, inputs=inputs)
        return HeadTurn(head=A0)
    live._run, real = fake_run, live._run
    try:
        live.llm_head_turn(_arr(), {"A": "weight", "B": "rhythm"}, rounds=4)("A", A0, B0, 1)
    finally:
        live._run = real
    needed = set(re.findall(r"\{(\w+)\}", captured["task"]["description"]))
    assert needed <= set(captured["inputs"]), needed - set(captured["inputs"])
    assert captured["inputs"]["approach"] == "weight" and "THE OTHER COMPOSER'S HEAD" in captured["inputs"]["debate"]


def test_the_solo_control_shows_only_its_own_head():
    import crew.seed_debate_crew as live
    captured = {}

    def fake_run(agent_key, llm, task, model, guardrail, retries, inputs):
        captured.update(task=task, inputs=inputs)
        return HeadTurn(head=A0)
    live._run, real = fake_run, live._run
    try:
        live.llm_head_turn(_arr(), {"A": "weight", "B": "rhythm"}, rounds=2, solo=True)("A", A0, B0, 1)
    finally:
        live._run = real
    needed = set(re.findall(r"\{(\w+)\}", captured["task"]["description"]))
    assert needed <= set(captured["inputs"]), needed - set(captured["inputs"])
    assert "OTHER" not in captured["inputs"]["your_head"] and "other composer" not in captured["task"]["description"]


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
