"""
Live event streaming — an OPTIONAL, context-scoped sink the pipeline publishes each
DebateEvent to AS IT IS PRODUCED, so a shell (the UI's streaming endpoint) can show
progress while the crew works instead of only at the very end.

Same shape as tracing (crew/tracing.py): ambient and context-scoped, so there are NO
function-signature changes and NO behaviour change when no sink is installed —
`publish()` is a no-op then, so the CLI, the tests, and the synchronous POST path are
untouched. Thread-safe via `contextvars`, which was verified to propagate through
CrewAI's asyncio Flow execution (the Flow methods run on an event-loop thread that
inherits the installing thread's context), so an event published deep inside the studio
loop still reaches a sink installed by the request thread that kicked the flow off.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from crew.contracts import DebateEvent, EventType

_SINK: contextvars.ContextVar[Callable[[DebateEvent], None] | None] = contextvars.ContextVar(
    "live_sink", default=None)


@contextmanager
def live_sink(sink: Callable[[DebateEvent], None]) -> Iterator[None]:
    """Install `sink` as the live event sink for the duration of the block, then restore
    the previous one. Nesting is fine (the token restores the prior sink)."""
    token = _SINK.set(sink)
    try:
        yield
    finally:
        _SINK.reset(token)


def publish(event: DebateEvent) -> None:
    """Publish ONE event to the active live sink, if any. A no-op when none is installed —
    so the pipeline's default behaviour (no streaming) is unchanged and cost-free."""
    sink = _SINK.get()
    if sink is not None:
        sink(event)


def publish_all(events: list[DebateEvent]) -> None:
    """Publish a batch in order (a convenience for the stage boundaries that hand back a
    list of events at once)."""
    for event in events:
        publish(event)


def beat(agent: str, text: str, role: str = "generator", data: dict | None = None) -> None:
    """Publish a TRANSIENT 'working on X now' beat from INSIDE a slow stage — the per-call
    progress the flow's per-stage RUNNING beats can't give (the whole lead phase is ONE flow
    node holding 15+ LLM calls, so without these the UI freezes on 'composing the gat…' and
    then floods; Sujit's live note, 2026-07-16). Same shape as the flow's `_running` beats:
    type RUNNING, published only, never part of a returned event list — so the persisted
    stream / replay contract is unchanged and a run with no sink pays nothing. `data` may
    carry the full verifier violations behind a re-roll for a UI that wants to expand them."""
    publish(DebateEvent(type=EventType.RUNNING, agent=agent, role=role, text=text,
                        data=data or {}))


def flags(violations: list[str], limit: int = 160) -> str:
    """Verifier violations condensed for a TICKER line: each violation's FACT (the clause
    before its ' — how to fix' tail), joined and capped — 'the alap dwells on Sa for 4
    continuous beats; 16 of 21 notes carry a meend', not three paragraphs of guidance.
    The full list rides the beat's `data` for a UI that wants to show everything."""
    facts = "; ".join(v.split(" — ")[0].strip() for v in violations)
    return facts if len(facts) <= limit else facts[:limit - 1].rstrip() + "…"
