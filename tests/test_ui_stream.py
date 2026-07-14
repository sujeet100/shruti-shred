"""
Test the UI streaming generator (ui.server._compose_events) — pure, no LLM.

`compose_flow` is faked to publish a couple of events through the live sink and return a
stub state, so we verify the worker-thread + queue plumbing SURFACES events live and ends
with a {done, composition, audio} payload — no network, no crew, no spend.

Runs as a script (`uv run python tests/test_ui_stream.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

import crew.flow as flow_mod  # noqa: E402
import ui.server as srv  # noqa: E402
from crew.contracts import DebateEvent, EventType  # noqa: E402
from crew.live import publish  # noqa: E402


class _StubComp:
    def model_dump(self, mode=None):
        return {"raga": "darbari"}


class _StubState:
    composition = _StubComp()
    wav_path = "/repo/out/fusion.wav"


def _fake_compose_flow(query, **_kw):
    # runs inside the worker thread, within the installed live_sink -> publish reaches it
    publish(DebateEvent(type=EventType.INFO, agent="Interpreter", role="system", text=f"heard: {query}"))
    publish(DebateEvent(type=EventType.PROPOSE, agent="Riff", role="generator", text="the main riff"))
    return _StubState()


def test_compose_events_streams_events_then_a_done_payload():
    os.environ.setdefault("GEMINI_API_KEY", "test-key")   # make it "live capable"
    os.environ["RMA_TRACE"] = "0"                          # no trace file in the test
    original = flow_mod.compose_flow
    flow_mod.compose_flow = _fake_compose_flow
    try:
        items = list(srv._compose_events("doom in darbari"))
    finally:
        flow_mod.compose_flow = original
        os.environ.pop("RMA_TRACE", None)

    # the two published events surfaced live, in order, before the terminal payload
    streamed = [it for it in items if "agent" in it]
    assert [it["agent"] for it in streamed] == ["Interpreter", "Riff"]
    done = items[-1]
    assert done.get("done") is True
    assert done["composition"] == {"raga": "darbari"}
    assert done["audio"] == "/audio/fusion.wav"           # derived from wav_path's basename


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
