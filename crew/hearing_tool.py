"""
The Composer's listening TOOL — a thin CrewAI adapter over `crew.hearing.hear`.

One instance is built per lead call, bound to that call's section and chart, so the model passes
only its draft notes. Caching is OFF (two drafts with the same notes would be rare, but a cache
keyed on arguments must never answer for a different section) and the tool may be used at most
`HEAR_MAX_USES` times per call — the cap lives in code, not in the prompt.
"""

from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from crew.contracts import Arrangement, LeadNote
from crew.generators import SectionSpan
from crew.hearing import HEAR_MAX_USES, hear


class HearArgs(BaseModel):
    notes: list[LeadNote] = Field(description="Your draft's notes, exactly as you would answer them.")


def _never_cache(_args: Any = None, _result: Any = None) -> bool:
    return False


class HearPhraseTool(BaseTool):
    name: str = "hear_phrase"
    description: str = ("Listen to a draft before answering: returns, note by note, what the sitar "
                        "will actually play — which notes sway, take a kan or a measured gesture, "
                        "turn into jhala; the silences; whether the draft overruns its window; and "
                        "whether every bend comes home in tune.")
    args_schema: type[BaseModel] = HearArgs
    _span: SectionSpan = PrivateAttr()
    _arr: Arrangement = PrivateAttr()

    def __init__(self, span: SectionSpan, arr: Arrangement) -> None:
        super().__init__(cache_function=_never_cache, max_usage_count=HEAR_MAX_USES)
        self._span, self._arr = span, arr

    def _run(self, notes: list[Any]) -> str:
        return hear([LeadNote.model_validate(n) for n in notes], self._span, self._arr)
