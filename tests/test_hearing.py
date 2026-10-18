"""
Tests for the Composer's listening tool (crew/hearing.py + crew/hearing_tool.py) — all pure.

The tool is worth its round trip only if it tells the truth about the render, so the central
test holds `heard_statement` to the line `generate_lead` actually places; the rest pin what the
report says about the cases the 2026-10-18 songs got wrong (a Darbari Ga too short to sway), the
raga rules it must respect (Bhairav's r sways only in descent), and the wiring (flag, roles, cap,
no cache, the prompt paragraph only when the tool is attached).

Runs as a script (`uv run python tests/test_hearing.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    LeadNote,
    LeadPhrase,
    Note,
    PhrasePlan,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import section_spans  # noqa: E402
from crew.hearing import (  # noqa: E402
    HEAR_MAX_USES,
    HEARING_BRIEF,
    audit_words,
    hear,
    hearing_brief,
    wants_hearing,
)


def _arr(role: str | None = "antara", *, kind: SectionKind = SectionKind.MELODY,
         raga: str = "darbari", bars: int = 1, sections: int = 1):
    secs = [Section(kind=kind, bars=bars, layers=["lead", "drone"], foreground="lead",
                    form_role=role) for _ in range(sections)]
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=72,
                             motif=["S"], sections=secs)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _notes(*spec: tuple[str, float]) -> list[LeadNote]:
    return [LeadNote(swara=s, dur=d) for s, d in spec]


def _line_for(report: str, beat: float) -> str:
    return next(line for line in report.splitlines() if line.startswith(f"beat {beat:6.2f}"))


def test_a_short_komal_ga_is_reported_too_short_to_sway():
    """Darbari C held 0 of 47 ga/dha long enough to sway; the tool must say so, note by note."""
    arr = _arr()
    report = hear(_notes(("S", 1), ("R", 0.5), ("g", 0.5), ("R", 1), ("S", 2)),
                  section_spans(arr)[0], arr)
    assert "too short to sway" in _line_for(report, 1.5)
    assert "0 sway" in report


def test_a_held_komal_dha_after_ni_takes_its_kan_and_sways():
    arr = _arr()
    report = hear(_notes(("S", 1), ("n", 1), ("d", 2), ("P", 2)), section_spans(arr)[0], arr)
    assert _line_for(report, 2.0).endswith("kan from n, then sways toward P")
    assert "1 sway" in report


def test_in_the_gat_a_held_ga_takes_gurujis_measured_loop_instead_of_a_sway():
    arr = _arr()
    report = hear(_notes(("S", 1), ("g", 2), ("R", 1), ("S", 2)), section_spans(arr)[0], arr)
    assert "loops up to m and back" in _line_for(report, 1.0)
    assert "1 take a measured gesture" in report


def test_bhairav_re_sways_coming_down_and_plays_plain_rising_through():
    """Bhairav's andolan belongs to the descent (Parrikar, Ragajunglism, van der Meer & Rao)."""
    arr = _arr("intro", kind=SectionKind.ALAAP, raga="bhairav", bars=2)
    span = section_spans(arr)[0]
    falling = hear(_notes(("G", 1), ("r", 3), ("S", 2)), span, arr)
    rising = hear(_notes(("S", 1), ("r", 3), ("G", 2)), span, arr)
    assert "sways" in falling.splitlines()[2]
    assert "moves straight on" in rising.splitlines()[2]


def test_rests_are_heard_as_silences():
    arr = _arr()
    notes = _notes(("S", 1), ("R", 1)) + [LeadNote(swara="S", dur=2, rest=True)] + _notes(("S", 2))
    report = hear(notes, section_spans(arr)[0], arr)
    assert "silence" in _line_for(report, 2.0)
    assert "the longest 2 beats" in report


def test_a_draft_longer_than_its_window_is_told_what_gets_cut():
    arr = _arr()                                         # one teentaal avartan: 16 beats
    report = hear(_notes(("S", 8), ("R", 6), ("S", 5)), section_spans(arr)[0], arr)
    assert "runs 19 beats" in report and "last 3 beats are cut" in report


def test_a_looping_head_is_heard_as_its_one_avartan():
    arr = _arr("mukhada", bars=4)
    report = hear(_notes(("S", 4), ("R", 4), ("g", 4), ("S", 4)), section_spans(arr)[0], arr)
    beats = [line for line in report.splitlines() if line.startswith("beat")]
    assert len(beats) == 4, report


def test_the_heard_statement_is_the_line_the_band_plays():
    """No parallel imitation: one statement heard == the sitar line generate_lead places."""
    from crew.lead import generate_lead, heard_statement
    arr = _arr(None, sections=2)
    notes = _notes(("S", 1), ("n", 1), ("d", 2), ("P", 1), ("g", 0.5), ("m", 0.5), ("R", 2),
                   ("S", 8))
    plan = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"],
                      climax_and_sam="lands on Sa")

    def gen(span, arr, memory, *, feedback=None):
        return LeadPhrase(phrase_plan=plan, notes=notes)

    layers, _ = generate_lead(arr, gen_fn=gen)
    span = section_spans(arr)[0]
    sitar = next(la for la in layers if la.instrument == "sitar")
    placed = [n for n in sitar.notes if span.start <= n.start < span.end]
    assert len(placed) >= len(notes) - 1, placed
    assert heard_statement(notes, span, arr) == placed


def test_the_ornament_check_reports_a_bend_held_away_from_its_swara():
    arr = _arr()
    held = Note(swara="g", oct=0, start=0.0, dur=2.0, gesture="ga_ma_loop",
                pitch_path=[[0, 0.0], [40, 2.0], [900, 2.0], [960, 0.0]])
    assert "held away" in audit_words([held], arr, 0.0)
    assert "in tune" in audit_words([held.model_copy(update={"gesture": None, "pitch_path": None})],
                                    arr, 0.0)


def test_only_sections_with_a_held_line_are_heard():
    assert wants_hearing(_arr("antara").sections[0])
    assert wants_hearing(_arr("intro", kind=SectionKind.ALAAP).sections[0])
    assert not wants_hearing(_arr("taan_long", kind=SectionKind.TAAN).sections[0])
    assert not wants_hearing(_arr(None, kind=SectionKind.SOLO).sections[0])


def test_the_prompt_paragraph_rides_only_with_the_tool():
    section = _arr("antara").sections[0]
    assert hearing_brief(section, True) == HEARING_BRIEF
    assert hearing_brief(section, False) == ""
    assert hearing_brief(_arr("taan_long", kind=SectionKind.TAAN).sections[0], True) == ""


def test_the_tool_is_attached_only_when_switched_on():
    from crew.lead import _hearing_tools
    arr = _arr()
    span = section_spans(arr)[0]
    os.environ.pop("RMA_HEAR", None)
    assert _hearing_tools(span, arr) == []
    os.environ["RMA_HEAR"] = "1"
    try:
        tools = _hearing_tools(span, arr)
        taan = _arr("taan_long", kind=SectionKind.TAAN)
        assert _hearing_tools(section_spans(taan)[0], taan) == []
    finally:
        os.environ.pop("RMA_HEAR", None)
    assert [t.name for t in tools] == ["hear_phrase"]
    assert tools[0].max_usage_count == HEAR_MAX_USES
    assert tools[0].cache_function(None, None) is False


def test_the_tool_answers_with_the_report_and_stops_at_its_cap():
    from crew.hearing_tool import HearPhraseTool
    arr = _arr()
    span = section_spans(arr)[0]
    tool = HearPhraseTool(span, arr)
    draft = [{"swara": "S", "dur": 2}, {"swara": "g", "dur": 0.5}, {"swara": "S", "dur": 2}]
    expected = hear([LeadNote.model_validate(n) for n in draft], span, arr)
    answers = [tool.run(notes=draft) for _ in range(HEAR_MAX_USES + 1)]
    assert answers[:HEAR_MAX_USES] == [expected] * HEAR_MAX_USES
    assert "usage limit" in answers[-1]


# --------------------------------------------------------------------------- #
# The ReAct loop itself, through CrewAI, with a scripted model (no key).      #
# --------------------------------------------------------------------------- #

def _scripted_llm(*answers):
    """A CrewAI LLM that replays `answers` in turn and records every call it receives."""
    from typing import Any

    from crewai.llms.base_llm import BaseLLM

    class Scripted(BaseLLM):
        seen: list[Any] = []

        def call(self, messages, tools=None, callbacks=None, available_functions=None,
                 from_task=None, from_agent=None, response_model=None):
            self.seen.append({"messages": messages, "tools": tools, "response_model": response_model})
            return answers[len(self.seen) - 1]

        def supports_function_calling(self) -> bool:
            return True

        def supports_stop_words(self) -> bool:
            return False

    return Scripted(model="scripted")


def _final_phrase() -> LeadPhrase:
    plan = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"],
                      climax_and_sam="lands on Sa")
    return LeadPhrase(phrase_plan=plan, notes=_notes(("S", 2), ("n", 1), ("d", 3), ("P", 2),
                                                     ("g", 3), ("R", 1), ("S", 4)))


def _antara_call(hearing: bool):
    from crew.lead import _hearing_tools, _LeadContext
    arr = _arr()
    span = section_spans(arr)[0]
    inputs = _LeadContext(arr).inputs_for(span, [])
    if not hearing:
        return inputs, []
    os.environ["RMA_HEAR"] = "1"
    try:
        tools = _hearing_tools(span, arr)
    finally:
        os.environ.pop("RMA_HEAR", None)
    inputs["hearing"] = hearing_brief(span.section, bool(tools))
    return inputs, tools


def test_the_composer_listens_mid_call_and_answers_with_what_it_heard():
    """ReAct through CrewAI's native tool loop: the model asks to hear a draft, the report
    comes back into its next turn, and its final answer still passes the lead guardrail."""
    import json

    from crew.lead import _LeadCrew
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    draft = {"notes": [{"swara": "S", "dur": 2}, {"swara": "g", "dur": 0.5}]}
    listen = [{"id": "c1", "function": {"name": "hear_phrase", "arguments": json.dumps(draft)}}]
    final = _final_phrase()
    llm = _scripted_llm(listen, final.model_dump_json())
    inputs, tools = _antara_call(hearing=True)
    assert _LeadCrew("composer").run("darbari", inputs, tools, llm=llm) == final
    first, second = llm.seen
    assert "call the `hear_phrase` tool" in str(first["messages"])
    assert "too short to sway" in str(second["messages"])        # it heard its short Ga
    # with a tool attached CrewAI sends no native schema — the guardrail parses the text answer
    assert first["response_model"] is None and second["response_model"] is None


def test_without_the_tool_the_call_is_unchanged():
    from crew.lead import _LeadCrew
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    final = _final_phrase()
    llm = _scripted_llm(final)
    inputs, tools = _antara_call(hearing=False)
    assert _LeadCrew("composer").run("darbari", inputs, tools, llm=llm) == final
    (only,) = llm.seen
    assert not only["tools"] and only["response_model"] is LeadPhrase
    assert "hear_phrase" not in str(only["messages"])


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
