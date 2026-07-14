"""
Tests for the live event sink (crew/live.py) — pure, no LLM.

The sink is how the UI streams progress: `publish()` pushes an event to the installed
sink and is a NO-OP when none is installed, so the CLI, the tests, and the synchronous
POST path are unchanged. Context-scoped and nestable.

Runs as a script (`uv run python tests/test_live.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import DebateEvent, EventType  # noqa: E402
from crew.live import live_sink, publish, publish_all  # noqa: E402


def _ev(name: str) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent=name, role="system", text=name)


def test_publish_is_a_noop_without_a_sink():
    publish(_ev("x"))                              # must not raise, nowhere to go


def test_installed_sink_receives_published_events_in_order():
    got: list = []
    with live_sink(got.append):
        publish(_ev("a"))
        publish(_ev("b"))
    assert [e.agent for e in got] == ["a", "b"]


def test_sink_is_removed_after_the_context():
    got: list = []
    with live_sink(got.append):
        publish(_ev("a"))
    publish(_ev("b"))                              # outside the context -> dropped
    assert [e.agent for e in got] == ["a"]


def test_publish_all_batches_in_order():
    got: list = []
    with live_sink(got.append):
        publish_all([_ev("a"), _ev("b"), _ev("c")])
    assert [e.agent for e in got] == ["a", "b", "c"]


def test_nested_sinks_restore_the_outer_one():
    outer, inner = [], []
    with live_sink(outer.append):
        publish(_ev("o1"))
        with live_sink(inner.append):
            publish(_ev("i1"))
        publish(_ev("o2"))
    assert [e.agent for e in outer] == ["o1", "o2"]
    assert [e.agent for e in inner] == ["i1"]


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
