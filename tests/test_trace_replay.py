"""Pure tests for resuming a dead live run: the trace replay (`crew/trace_replay.py`) and the
one-retry wrapper on the experiment's live calls (`seed_debate_crew.with_retry`). No API."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import crew.trace_replay as replay  # noqa: E402


def _start(prompt: str) -> dict:
    return {
        "kind": "llm.start",
        "data": {"messages": [{"role": "user", "content": prompt}]},
    }


def _done(answer: str) -> dict:
    return {"kind": "llm.done", "data": {"response": answer}}


FAIL = {"kind": "llm.fail", "data": {}}


def _with_traces(traces: dict[str, list[dict]]):
    """Write the traces to a temp dir and point the module at it."""
    tmp = Path(tempfile.mkdtemp())
    for name, spans in traces.items():
        (tmp / f"{name}.json").write_text(json.dumps({"spans": spans}))
    replay._TRACES = tmp


def test_a_failure_mid_run_replays_as_a_failure_and_trailing_ones_are_dropped():
    # the caught failure stays (the run took that path); the crash at the end is the resume point
    _with_traces(
        {
            "t": [
                _start("a" * 100),
                _done("A"),
                _start("b" * 200),
                FAIL,
                FAIL,
                _start("c" * 300),
                _done("C"),
                _start("d" * 400),
                FAIL,
            ]
        }
    )
    assert replay.load_recording("t").calls == [(100, "A"), (200, None), (300, "C")]


def test_traces_chain_in_order():
    _with_traces(
        {
            "one": [_start("x" * 50), _done("X"), _start("y" * 60), FAIL],
            "two": [_start("y" * 60), _done("Y")],
        }
    )
    assert replay.load_recording("one", "two").calls == [(50, "X"), (60, "Y")]


def test_a_recorded_failure_fails_again_and_a_changed_prompt_stops_the_replay():
    rec = replay.Recording([(100, "A"), (200, None), (300, "C")])
    assert rec.next_answer(100) == "A"
    try:
        rec.next_answer(200)
        raise AssertionError("a recorded failure must fail again")
    except ConnectionError:
        pass
    try:
        rec.next_answer(900)
        raise AssertionError("an out-of-step prompt must stop the replay")
    except RuntimeError:
        pass
    assert rec.remaining() == 1


def test_a_python_repr_answer_replays_as_json_and_the_tracer_now_writes_json():
    # OpenAI's Responses path hands back a parsed dict; old traces stored its repr
    old = str(
        {
            "reasoning": "Sa's 'toll'",
            "n": [1, 2],
            "sections": [{"kind": repr("alaap"), "layers": repr(["drone", "lead"])}],
        }
    )
    assert json.loads(replay._as_json(old)) == {
        "reasoning": "Sa's 'toll'",
        "n": [1, 2],
        "sections": [{"kind": "alaap", "layers": ["drone", "lead"]}],
    }
    assert (
        replay._as_json('{"a": 1}') == '{"a": 1}'
        and replay._as_json("plain") == "plain"
    )
    from crew.tracing import _response_text

    assert json.loads(_response_text({"a": "ā"})) == {"a": "ā"}


def test_with_retry_tries_once_more_then_lets_the_failure_through():
    import crew.seed_debate_crew as live

    live.RETRY_WAIT_S = 0.0
    calls: list[int] = []

    def flaky(x: int) -> int:
        calls.append(x)
        if len(calls) == 1:
            raise ConnectionError("503")
        return x * 2

    assert live.with_retry(flaky)(4) == 8 and len(calls) == 2

    def dead(x: int) -> int:
        calls.append(x)
        raise ConnectionError("503")

    calls.clear()
    try:
        live.with_retry(dead)(1)
        raise AssertionError("the second failure must propagate")
    except ConnectionError:
        pass
    assert len(calls) == 2


if __name__ == "__main__":
    tests = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
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
