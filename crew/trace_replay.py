"""
Replay a traced run's model answers, in order, then go live.

A long live experiment that dies late has already paid for every answer before the crash, and the
trace holds each one verbatim (`llm.done`). Inside `replaying(trace_id)`, `config.build_llm` hands
out a `ReplayLLM` while recorded answers remain: each call returns the next answer instead of
reaching the API. Everything between the calls is deterministic code, so the same run takes the
same path, guardrail rejections included, and reaches the crash point with identical results.
Once the recording is spent, `build_llm` builds real models again.

Out of step is loud: each call's prompt size is checked against the recording, so a code change
that alters a prompt stops the replay instead of feeding an answer to the wrong question.

A call that FAILED mid-run (a timeout the code caught and survived) fails again on replay, so the
run takes the same path; only a trace's trailing failures (the ones that ended it) are dropped —
those are the calls a resume makes live. Several traces chain: a run resumed once is replayed from
its first trace and then its resume's.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from crewai.llms.base_llm import BaseLLM

_TRACES: Final = Path(__file__).resolve().parents[1] / "traces"
# A prompt may differ by a few characters (message framing) between the event the tracer saw
# and what the executor hands a custom model; a different question differs by far more.
_SIZE_TOLERANCE: Final = 0.02


@dataclass
class Recording:
    """Recorded model calls in order: (prompt size in characters, the answer — None if it failed)."""
    calls: list[tuple[int, str | None]]
    used: int = 0
    tolerance: float = _SIZE_TOLERANCE      # how far a prompt's size may drift before it is a different call

    def remaining(self) -> int:
        return len(self.calls) - self.used

    def next_answer(self, prompt_chars: int) -> str:
        expected, answer = self.calls[self.used]
        if abs(prompt_chars - expected) > self.tolerance * expected:
            raise RuntimeError(f"replay out of step at call {self.used + 1}: prompt is "
                               f"{prompt_chars:,} chars, the recording's was {expected:,}")
        self.used += 1
        if answer is None:
            raise ConnectionError(f"replayed failure at call {self.used} (it failed in the recording)")
        return answer


def load_recording(*trace_ids: str) -> Recording:
    """Every call in the traces, in order, each paired with its prompt's size."""
    return Recording([call for trace_id in trace_ids for call in _calls(trace_id)])


def _calls(trace_id: str) -> list[tuple[int, str | None]]:
    """One trace's calls: each `llm.start` closed by its `llm.done` (the answer) or `llm.fail`
    (None), with the trailing failures — the ones that ended the run — dropped."""
    calls: list[tuple[int, str | None]] = []
    open_ = False
    for span in json.loads((_TRACES / f"{trace_id}.json").read_text())["spans"]:
        if span["kind"] == "llm.start":
            calls.append((_chars(span["data"]["messages"]), None))
            open_ = True
        elif span["kind"] == "llm.done" and open_:
            calls[-1] = (calls[-1][0], _as_json(span["data"]["response"]))
            open_ = False
        elif span["kind"] == "llm.fail":
            open_ = False
    while calls and calls[-1][1] is None:
        calls.pop()
    return calls


def _as_json(answer: str) -> str:
    """A recorded answer as the text the model sent. Traces written before the tracer recorded
    structured answers as JSON hold a Python repr for OpenAI's parsed output — and one level
    down, each nested value was stringified too (a section's kind stored as "'alaap'", its
    layers as "['drone', 'lead']"). Decode both back into JSON; anything else passes through."""
    try:
        json.loads(answer)
        return answer
    except ValueError:
        pass
    value = _decoded(answer)
    return _compact(value) if isinstance(value, (dict, list)) else answer


def _compact(value: Any) -> str:
    """JSON as the providers send it (no spaces after separators) — a retry prompt quotes the
    previous answer back, so the replayed text must match it character for character."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decoded(value: Any) -> Any:
    """`value` with every string that is a Python literal (quoted text, list, dict) evaluated,
    recursively; prose stays prose."""
    if isinstance(value, dict):
        return {k: _decoded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decoded(v) for v in value]
    if isinstance(value, str) and value[:1] in ("'", '"', "[", "{"):
        try:
            return _decoded(ast.literal_eval(value))
        except (ValueError, SyntaxError):
            return value
    return value


def _chars(messages: Any) -> int:
    from crew.tracing import _clean_messages
    return sum(len(m["content"]) for m in _clean_messages(messages))


class ReplayLLM(BaseLLM):
    """A model that answers from a `Recording`."""
    recording: Any = None

    def call(self, messages: Any, tools: Any = None, callbacks: Any = None,
             available_functions: Any = None, from_task: Any = None, from_agent: Any = None,
             response_model: Any = None) -> str:
        return self.recording.next_answer(_chars(messages))

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False


_ACTIVE: ContextVar[Recording | None] = ContextVar("trace_replay", default=None)


@contextmanager
def replaying(*trace_ids: str, tolerance: float = _SIZE_TOLERANCE) -> Iterator[Recording]:
    """Answer the block's model calls from the traces, in order, until the recording runs out.
    `tolerance` widens the size check when a prompt was edited since the recording (a reworded brief
    still asks the same question); the ORDER is what the replay relies on."""
    recording = load_recording(*trace_ids)
    recording.tolerance = tolerance
    token = _ACTIVE.set(recording)
    try:
        yield recording
    finally:
        _ACTIVE.reset(token)


def replay_llm() -> ReplayLLM | None:
    """The replaying model while a recording has answers left, else None (build a real one)."""
    recording = _ACTIVE.get()
    if recording is None or recording.remaining() == 0:
        return None
    return ReplayLLM(model="replay", recording=recording)
