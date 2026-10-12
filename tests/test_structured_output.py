"""
Tests for `crew.config.structured_output` — pure, no LLM (the Agent is never run).

CrewAI 1.15.2 sends a Task's Pydantic model to Gemini as native structured output AND, unless
`response_model` is set, pastes the same JSON schema into the prompt as text — ~2.9k duplicated
tokens at the END of every lead call (trace 15fbd6571f72). This pins the fix, so an upgrade that
changes the rule shows up here, not on the bill.

Runs as a script (`uv run python tests/test_structured_output.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("OPENAI_API_KEY", "unused")   # Agent() validates an LLM; nothing is called

from crewai import Agent, Task  # noqa: E402
from crewai.agent.utils import build_task_prompt_with_schema  # noqa: E402

from crew.config import structured_output  # noqa: E402
from crew.contracts import LeadPhrase  # noqa: E402


def _prompt(**kwargs) -> str:
    agent = Agent(role="r", goal="g", backstory="b", llm="gpt-4o-mini")
    task = Task(description="compose", expected_output="a phrase", agent=agent, **kwargs)
    return build_task_prompt_with_schema(task, task.prompt())


def test_the_schema_is_not_pasted_into_the_prompt():
    assert "OpenAPI schema" in _prompt(output_pydantic=LeadPhrase)     # the duplicate, without the fix
    assert "OpenAPI schema" not in _prompt(**structured_output(LeadPhrase))


def test_the_task_still_parses_into_the_model():
    kwargs = structured_output(LeadPhrase)
    assert kwargs["output_pydantic"] is LeadPhrase and kwargs["response_model"] is LeadPhrase


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
