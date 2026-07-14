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

from crew.contracts import DebateEvent

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
