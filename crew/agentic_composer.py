"""
THE AGENTIC COMPOSER — the Composer as a real agent for its sitar calls (Sujit, 2026-10-19: "will
making these agents real agents give more flexibility and autonomy? try it").

Today the Composer answers once, code checks the answer, and a failing answer goes back with the
exact fault (self-correction from code). Here the model gets the SAME checks as a tool and decides
for itself when to use them, what to fix, and when it is done — a model directing its own process
and tool use, which is what makes it an agent rather than a step in a workflow. Code still bounds it
(`CHECK_MAX_USES` per call) and still runs the same hard checks on whatever it submits, so the loop
can only make a draft cleaner before code sees it, never let a broken one through.

Process stays in code (the order of sections, the gat before the sections): the experiment gives the
model autonomy over its own drafting loop, which our evidence says is the autonomy most likely to pay
(the listening tool lost because its tool reported something that did not decide quality; this tool
reports exactly what code will judge). Behind `RMA_AGENTIC_COMPOSER` (default OFF).

The checks reach the tool through context variables set around each model call
(`checking`, `checking_gat`), so no generation signature changes.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from crew.contracts import Gat, LeadPhrase
from crew.gat_verifier import CellChecks

CHECK_MAX_USES: Final = 4           # checks per call — the cap lives in code, not in the prompt
CellCheck = Callable[[LeadPhrase], CellChecks]
GatCheck = Callable[[Gat], dict[str, CellChecks]]
_CELL: ContextVar[CellCheck | None] = ContextVar("agentic_cell_check", default=None)
_GAT: ContextVar[GatCheck | None] = ContextVar("agentic_gat_check", default=None)


@contextmanager
def checking(check: CellCheck) -> Iterator[None]:
    """The section being composed is judged by `check` — offer it to the model as a tool."""
    token = _CELL.set(check)
    try:
        yield
    finally:
        _CELL.reset(token)


@contextmanager
def checking_gat(check: GatCheck) -> Iterator[None]:
    token = _GAT.set(check)
    try:
        yield
    finally:
        _GAT.reset(token)


def render_checks(checks: CellChecks) -> str:
    """What code will say about this draft, in words."""
    if not checks.hard and not checks.craft:
        return "Clean: code finds nothing wrong. Submit it when the music is right."
    out = []
    if checks.hard:
        out.append("MUST FIX (code will reject the draft):\n" + "\n".join(f"  - {h}" for h in checks.hard))
    if checks.craft:
        out.append("CRAFT NOTES (taste — your call):\n" + "\n".join(f"  - {c}" for c in checks.craft))
    return "\n".join(out)


def render_gat_checks(by_part: dict[str, CellChecks]) -> str:
    return "\n\n".join(f"{part.upper()}:\n{render_checks(c)}" for part, c in by_part.items())


def _never_cache(_args: Any = None, _result: Any = None) -> bool:
    return False


class _PhraseArgs(BaseModel):
    phrase: LeadPhrase = Field(description="Your draft exactly as you would answer it: phrase_plan and notes.")


class CheckDraftTool(BaseTool):
    name: str = "check_draft"
    description: str = ("Check a draft before answering: returns exactly what code will judge — the faults "
                        "it would reject (raga grammar, length, the section's own rules) and its craft notes. "
                        "You decide when to check, what to change, and when you are done.")
    args_schema: type[BaseModel] = _PhraseArgs
    _check: CellCheck = PrivateAttr()

    def __init__(self, check: CellCheck) -> None:
        super().__init__(cache_function=_never_cache, max_usage_count=CHECK_MAX_USES)
        self._check = check

    def _run(self, phrase: Any) -> str:
        return render_checks(self._check(LeadPhrase.model_validate(phrase)))


class _GatArgs(BaseModel):
    gat: Gat = Field(description="Your draft gat exactly as you would answer it.")


class CheckGatTool(BaseTool):
    name: str = "check_gat"
    description: str = ("Check a draft gat before answering: for each part (mukhada, manjha, antara, amad) "
                        "returns what code will reject and its craft notes. You decide when you are done.")
    args_schema: type[BaseModel] = _GatArgs
    _check: GatCheck = PrivateAttr()

    def __init__(self, check: GatCheck) -> None:
        super().__init__(cache_function=_never_cache, max_usage_count=CHECK_MAX_USES)
        self._check = check

    def _run(self, gat: Any) -> str:
        return render_gat_checks(self._check(Gat.model_validate(gat)))


def check_tools(default: CellCheck) -> list[BaseTool]:
    """The section call's tool, when the agentic Composer is on: the section's own checks if the
    caller set them (`checking`), else `default`."""
    from crew.config import agentic_composer_enabled
    if not agentic_composer_enabled():
        return []
    return [CheckDraftTool(_CELL.get() or default)]


def gat_check_tools() -> list[BaseTool]:
    from crew.config import agentic_composer_enabled
    check = _GAT.get()
    return [CheckGatTool(check)] if agentic_composer_enabled() and check is not None else []


def agentic_brief(tools: list[BaseTool]) -> str:
    """The prompt paragraph that hands the model its loop (empty when it has no tool)."""
    if not tools:
        return ""
    name = tools[0].name
    return (f"YOU ARE WORKING, NOT ANSWERING ONCE. You have a tool, `{name}`, that tells you exactly what "
            f"code will judge about a draft: the faults it would reject and its craft notes. Draft, check, "
            f"revise as many times as the music needs (up to {CHECK_MAX_USES} checks), and answer only when "
            f"you are satisfied. Faults must be fixed; craft notes are taste and yours to weigh. The music "
            f"comes first: a clean check is the floor, not the goal.")
