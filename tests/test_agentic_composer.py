"""Pure tests for the agentic Composer (`crew/agentic_composer.py` + its wiring in `crew/lead.py`):
the tool reports exactly what code will judge, it is attached only when switched on, it sees the
section's own checks, and CrewAI's native tool loop lets the model check, read, and answer. No API."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crew.agentic_composer import (CHECK_MAX_USES, agentic_brief, check_tools, checking,  # noqa: E402
                                   gat_check_tools, render_checks)
from crew.gat_verifier import CellChecks  # noqa: E402
from test_hearing import _antara_call, _final_phrase, _scripted_llm  # noqa: E402

_FLAG = "RMA_AGENTIC_COMPOSER"


class _On:
    def __enter__(self):
        os.environ[_FLAG] = "1"

    def __exit__(self, *exc):
        os.environ.pop(_FLAG, None)


def _faulty(_cell) -> CellChecks:
    return CellChecks(hard=("the phrase runs 20 beats; its section has 16",), craft=("the climax comes early",))


def test_the_report_says_what_code_will_reject_and_what_is_taste():
    text = render_checks(_faulty(None))
    assert "MUST FIX" in text and "20 beats" in text and "CRAFT NOTES" in text
    assert render_checks(CellChecks()).startswith("Clean")


def test_the_tool_is_attached_only_when_switched_on():
    os.environ.pop(_FLAG, None)
    assert check_tools(_faulty) == [] and gat_check_tools() == []
    with _On():
        (tool,) = check_tools(_faulty)
    assert tool.name == "check_draft" and tool.max_usage_count == CHECK_MAX_USES
    assert tool.cache_function(None, None) is False
    assert "check_draft" in agentic_brief([tool]) and agentic_brief([]) == ""


def test_the_tool_uses_the_sections_own_checks_when_the_loop_sets_them():
    phrase = _final_phrase().model_dump()
    with _On():
        with checking(lambda c: CellChecks(hard=("ends on n, not a resting swara",))):
            (inside,) = check_tools(_faulty)
        (outside,) = check_tools(_faulty)
    assert "ends on n" in inside.run(phrase=phrase)
    assert "20 beats" in outside.run(phrase=phrase)


def test_the_composer_checks_its_draft_mid_call_and_answers_after_reading_the_verdict():
    """A real agent loop through CrewAI: the model calls check_draft on a draft, the verdict comes
    back into its next turn, and it decides to answer."""
    from crew.lead import _LeadCrew
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    final = _final_phrase()
    draft = {"phrase": final.model_dump()}
    call = [{"id": "c1", "function": {"name": "check_draft", "arguments": json.dumps(draft)}}]
    llm = _scripted_llm(call, final.model_dump_json())
    inputs, _ = _antara_call(hearing=False)
    with _On():
        with checking(_faulty):
            tools = check_tools(_faulty)
    inputs["hearing"] = agentic_brief(tools)
    assert _LeadCrew("composer").run("darbari", inputs, tools, llm=llm) == final
    first, second = llm.seen
    assert "check_draft" in str(first["messages"]) and "MUST FIX" in str(second["messages"])


def test_the_gat_call_gets_a_tool_that_checks_every_part_of_its_draft():
    import test_lead as T
    from crew.contracts import Gat, SectionKind
    from crew.lead import generate_lead
    seen = []

    def gat_fn(arr, *, needs_manjha, needs_antara, needs_amad):
        tools = gat_check_tools()
        seen.append(tools[0].run(gat=Gat(mukhada=T._good_head()).model_dump()) if tools else None)
        return Gat(mukhada=T._good_head())
    arr = T._gat_arr((SectionKind.ALAAP, 1, "mukhada"))
    fn, _ = T._fake([])
    with _On():
        generate_lead(arr, gen_fn=fn, gat_fn=gat_fn)
    assert seen and seen[0] is not None and seen[0].startswith("MUKHADA")
    seen.clear()
    generate_lead(arr, gen_fn=fn, gat_fn=gat_fn)                       # switched off: no tool
    assert seen == [None]


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
