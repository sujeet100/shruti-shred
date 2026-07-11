"""
Local tracing — SEE what the agents actually do, no cloud login.

Modeled on Langfuse's trace → observations shape: ONE run of the agent/graph is a
TRACE with a unique id, holding many SPANS (crew kickoff, agent execution, each LLM
call with its full prompt/response/tokens, each guardrail pass or retry). Each run
is written to `traces/<id>.json`; browse and open them by id in the local portal
(`crew/trace_portal.py`). A readable tree also streams to the console live.

Tracing is ON by default for LLM test/eval runs — set `RMA_TRACE=0` to opt out.
Wrap any crew run:

    from crew.tracing import traced
    with traced("doom fusion in Darbari"):
        compose(brief)

NOTE: the crewai.events import paths are verified for CrewAI 1.15.2; they move
between releases (see CLAUDE.md) — re-check on upgrade.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from crewai.events import BaseEventListener
from crewai.events.event_types import (
    AgentExecutionStartedEvent,
    CrewKickoffCompletedEvent,
    CrewKickoffFailedEvent,
    CrewKickoffStartedEvent,
    LLMCallCompletedEvent,
    LLMCallFailedEvent,
    LLMCallStartedEvent,
    LLMGuardrailCompletedEvent,
    LLMGuardrailStartedEvent,
    TaskCompletedEvent,
)

# glyph + nesting depth per span kind — shapes the readable console tree.
_STYLE: dict[str, tuple[str, int]] = {
    "crew.start": ("▶", 0), "crew.done": ("■", 0), "crew.fail": ("✗", 0),
    "agent.start": ("▷", 1), "task.done": ("▪", 1),
    "llm.start": ("→", 2), "llm.done": ("←", 2), "llm.fail": ("✗", 2),
    "guardrail.start": ("?", 2), "guardrail.pass": ("✓", 2), "guardrail.retry": ("↻", 2),
}

_TRACE_OFF = {"0", "false", "off", "no"}


def tracing_enabled() -> bool:
    """True unless RMA_TRACE is explicitly disabled. Default: trace every LLM run."""
    return os.getenv("RMA_TRACE", "").strip().lower() not in _TRACE_OFF


def new_run_id() -> str:
    """A short, unique id for one run/trace (like Langfuse's trace id)."""
    return uuid.uuid4().hex[:12]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "run"


def _short_agent(role: str | None) -> str:
    """A tidy label from a verbose agent role ('Pandit — the tradition-keeper…' → 'Pandit')."""
    low = (role or "").lower()
    if "pandit" in low:
        return "Pandit"
    if "riffsmith" in low:
        return "Riffsmith"
    if "interpret" in low or "intake" in low:
        return "Interpreter"
    return (role or "").split("—")[0].split(",")[0].strip()[:14] or "system"


def _usage_dict(usage: Any) -> dict[str, int]:
    """Normalize CrewAI's usage (dict or object) to a plain token dict."""
    if usage is None:
        return {}
    if isinstance(usage, dict):
        keys, get = usage, usage.get
    else:
        keys = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_prompt_tokens")
        def get(k):  # noqa: E306
            return getattr(usage, k, None)
    return {k: get(k) for k in keys if isinstance(get(k), int)}


def _clean_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list):
        return [{"role": "prompt", "content": str(messages)}]
    return [{"role": str(m.get("role", "?")), "content": str(m.get("content", ""))}
            for m in messages if isinstance(m, dict)]


def trace_stats(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll a trace's spans up to headline numbers (spans, LLM calls, tokens, ...)."""
    tokens = sum((s["data"].get("usage") or {}).get("total_tokens", 0) or 0
                 for s in spans if s["kind"] == "llm.done")
    return {
        "spans": len(spans),
        "llm_calls": sum(1 for s in spans if s["kind"] == "llm.start"),
        "tokens": tokens,
        "retries": sum(1 for s in spans if s["kind"] == "guardrail.retry"),
        "wall": round(spans[-1]["ms"] / 1000, 1) if spans else 0.0,
    }


class LocalTracer(BaseEventListener):
    """Collects ONE run's CrewAI events into a trace: a unique id + a list of spans.

    Constructing it registers handlers on the global event bus (that's how
    BaseEventListener works), so create it via `traced(...)` around one run.
    """

    def __init__(self, *, run_id: str, name: str, query: str, console: bool = True) -> None:
        self.run_id = run_id
        self.name = name
        self.query = query
        self.console = console
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.epoch = time.time()
        self.spans: list[dict[str, Any]] = []
        self._t0: float | None = None
        super().__init__()  # registers setup_listeners on the bus

    def _record(self, kind: str, agent: str | None, summary: str,
                data: dict[str, Any] | None = None) -> None:
        now = time.perf_counter()
        if self._t0 is None:
            self._t0 = now
        span = {"seq": len(self.spans), "ms": round((now - self._t0) * 1000),
                "kind": kind, "agent": _short_agent(agent), "summary": summary, "data": data or {}}
        self.spans.append(span)
        if self.console:
            glyph, depth = _STYLE.get(kind, ("·", 0))
            print(f"  [{span['ms'] / 1000:6.1f}s] {'  ' * depth}{glyph} "
                  f"{kind:15} {span['agent']:11} {summary}")

    def setup_listeners(self, bus) -> None:  # noqa: ANN001 — bus type is CrewAI-internal
        @bus.on(CrewKickoffStartedEvent)
        def on_crew_start(_src, e):
            keys = list((e.inputs or {}).keys()) if getattr(e, "inputs", None) else []
            self._record("crew.start", e.agent_role, f"{e.crew_name or 'crew'} · inputs {keys}")

        @bus.on(AgentExecutionStartedEvent)
        def on_agent_start(_src, e):
            self._record("agent.start", e.agent_role, "thinking…")

        @bus.on(LLMCallStartedEvent)
        def on_llm_start(_src, e):
            messages = _clean_messages(e.messages)
            chars = sum(len(m["content"]) for m in messages)
            self._record("llm.start", e.agent_role,
                         f"{e.model} temp={e.temperature} · prompt {chars:,} chars",
                         {"model": e.model, "temperature": e.temperature, "messages": messages})

        @bus.on(LLMCallCompletedEvent)
        def on_llm_done(_src, e):
            usage = _usage_dict(getattr(e, "usage", None))
            total = usage.get("total_tokens")
            self._record("llm.done", e.agent_role,
                         f"{f'{total:,} tok' if total else '? tok'} · finish={getattr(e, 'finish_reason', None)}",
                         {"response": str(getattr(e, "response", "")), "usage": usage})

        @bus.on(LLMGuardrailStartedEvent)
        def on_guard_start(_src, e):
            self._record("guardrail.start", e.agent_role,
                         f"{e.guardrail_name or 'guardrail'} · retry {e.retry_count}")

        @bus.on(LLMGuardrailCompletedEvent)
        def on_guard_done(_src, e):
            passed = bool(e.success)
            detail = "passed" if passed else f"REJECT → retry: {str(e.error)[:140]}"
            self._record("guardrail.pass" if passed else "guardrail.retry", e.agent_role,
                         f"retry {e.retry_count} · {detail}",
                         {"success": passed, "error": str(e.error) if e.error else None,
                          "retry": e.retry_count})

        @bus.on(TaskCompletedEvent)
        def on_task_done(_src, e):
            self._record("task.done", e.agent_role, e.task_name or "task")

        @bus.on(CrewKickoffCompletedEvent)
        def on_crew_done(_src, e):
            self._record("crew.done", e.agent_role,
                         f"total_tokens={getattr(e, 'total_tokens', None)}")

        @bus.on(CrewKickoffFailedEvent)
        def on_crew_fail(_src, e):
            self._record("crew.fail", getattr(e, "agent_role", ""),
                         str(getattr(e, "error", ""))[:160])

        @bus.on(LLMCallFailedEvent)
        def on_llm_fail(_src, e):
            self._record("llm.fail", getattr(e, "agent_role", ""),
                         str(getattr(e, "error", ""))[:160])

    def to_trace(self) -> dict[str, Any]:
        return {"id": self.run_id, "name": self.name, "query": self.query,
                "started_at": self.started_at, "epoch": self.epoch, "spans": self.spans}

    def write(self, out_dir: str) -> Path:
        """Write traces/<id>.json and return its path."""
        directory = Path(out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.run_id}.json"
        path.write_text(json.dumps(self.to_trace()), encoding="utf-8")
        return path


@contextmanager
def traced(query: str, *, out_dir: str = "traces", console: bool = True) -> Iterator[LocalTracer]:
    """Trace every crew run inside the block as ONE trace with a unique id."""
    run_id = new_run_id()
    if console:
        print(f"\n─── trace {run_id} · {query} " + "─" * 24)
    tracer = LocalTracer(run_id=run_id, name=_slug(query), query=query, console=console)
    try:
        yield tracer
    finally:
        tracer.write(out_dir)
        print(f"─── trace {run_id} · {len(tracer.spans)} spans · "
              f"portal: uv run python -m crew.trace_portal ".ljust(40, "─"))


# --------------------------------------------------------------------------- #
# The trace detail view (the span timeline). Reused by the portal.             #
# --------------------------------------------------------------------------- #

def _agent_class(agent: str) -> str:
    low = agent.lower()
    if "pandit" in low or "interpreter" in low or "intake" in low:
        return "a-pandit" if "pandit" in low else "a-neutral"
    if "riffsmith" in low:
        return "a-riffsmith"
    return "a-neutral"


def _row_html(span: dict[str, Any]) -> str:
    kind = span["kind"]
    glyph, depth = _STYLE.get(kind, ("·", 0))
    esc = html.escape
    agent = esc(span["agent"]) or "system"
    detail = ""
    data = span["data"]
    if kind == "llm.start" and data.get("messages"):
        blocks = "".join(
            f'<div class="msg"><span class="role">{esc(m["role"])}</span>'
            f'<pre>{esc(m["content"])}</pre></div>' for m in data["messages"])
        detail = f'<details><summary>prompt ({len(data["messages"])} messages)</summary>{blocks}</details>'
    elif kind == "llm.done" and data.get("response"):
        usage = " · ".join(f"{k}={v}" for k, v in (data.get("usage") or {}).items())
        detail = (f'<details><summary>response{" · " + esc(usage) if usage else ""}</summary>'
                  f'<pre>{esc(data["response"])}</pre></details>')
    elif kind == "guardrail.retry" and data.get("error"):
        detail = f'<div class="err">{esc(str(data["error"]))}</div>'
    return (
        f'<div class="row k-{kind.replace(".", "-")} {_agent_class(span["agent"])}">'
        f'<span class="t">{span["ms"] / 1000:.1f}s</span>'
        f'<span class="g d{depth}">{glyph}</span>'
        f'<span class="k">{esc(kind)}</span>'
        f'<span class="ag">{agent}</span>'
        f'<span class="sm">{esc(span["summary"])}{detail}</span>'
        f'</div>')


def render_trace(trace: dict[str, Any], *, home_link: str | None = None) -> str:
    """Render one trace (id + spans) as a self-contained HTML timeline."""
    esc = html.escape
    spans = trace.get("spans", [])
    s = trace_stats(spans)
    rows = "\n".join(_row_html(sp) for sp in spans)
    back = f'<a class="back" href="{esc(home_link)}">&larr; all traces</a>' if home_link else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>trace · {esc(trace.get("id", ""))}</title>
<style>
:root {{
  --bg:#17151a; --panel:#201d24; --ink:#ece5d8; --soft:#a49b8c; --hair:#35313b;
  --pandit:#e0a44a; --riffsmith:#7ba7cf; --code:#74b493; --danger:#e07b70;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}}
@media (prefers-color-scheme:light) {{
  :root {{ --bg:#f4f1ea; --panel:#fbf9f4; --ink:#221d16; --soft:#6b6153; --hair:#e2dacb; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans); }}
.wrap {{ max-width:60rem; margin:0 auto; padding:2rem 1.2rem 4rem; }}
h1 {{ font-size:1.15rem; margin:.4rem 0 .1rem; font-weight:600; }}
h1 .id {{ font-family:var(--mono); color:var(--pandit); }}
.q {{ color:var(--soft); font-size:.9rem; margin:0 0 .1rem; }}
.q b {{ color:var(--ink); font-weight:500; }}
.stats {{ display:flex; flex-wrap:wrap; gap:.4rem .6rem; margin:.9rem 0 1.6rem; }}
.stat {{ font-family:var(--mono); font-size:.8rem; color:var(--soft); background:var(--panel);
  border:1px solid var(--hair); border-radius:7px; padding:.3rem .6rem; }}
.stat b {{ color:var(--ink); }}
.row {{ display:grid; grid-template-columns:3.2rem 1.4rem 8.5rem 7rem 1fr; gap:.5rem;
  align-items:baseline; padding:.28rem .5rem; border-radius:7px; font-size:.86rem; }}
.row:hover {{ background:var(--panel); }}
.t {{ font-family:var(--mono); color:var(--soft); text-align:right; font-size:.78rem;
  font-variant-numeric:tabular-nums; }}
.g {{ text-align:center; color:var(--soft); }}
.g.d0 {{ color:var(--ink); }} .g.d2 {{ opacity:.85; }}
.k {{ font-family:var(--mono); font-size:.78rem; color:var(--soft); }}
.ag {{ font-family:var(--mono); font-size:.78rem; font-weight:600; }}
.a-pandit .ag {{ color:var(--pandit); }}
.a-riffsmith .ag {{ color:var(--riffsmith); }}
.a-neutral .ag {{ color:var(--soft); }}
.k-crew-start, .k-crew-done {{ border-top:1px solid var(--hair); margin-top:.4rem; padding-top:.5rem; }}
.k-guardrail-pass .k {{ color:var(--code); }}
.k-guardrail-retry .k, .k-crew-fail .k, .k-llm-fail .k {{ color:var(--danger); }}
.sm {{ color:var(--ink); }}
details {{ margin-top:.35rem; }}
summary {{ cursor:pointer; color:var(--riffsmith); font-family:var(--mono); font-size:.76rem; }}
.msg {{ margin:.4rem 0; }}
.role {{ font-family:var(--mono); font-size:.68rem; text-transform:uppercase; letter-spacing:.08em;
  color:var(--soft); }}
pre {{ margin:.2rem 0 0; padding:.6rem .75rem; background:var(--panel); border:1px solid var(--hair);
  border-radius:7px; overflow-x:auto; font-family:var(--mono); font-size:.76rem; line-height:1.55;
  white-space:pre-wrap; word-break:break-word; }}
.err {{ margin-top:.3rem; color:var(--danger); font-family:var(--mono); font-size:.78rem; }}
.back {{ font-family:var(--mono); font-size:.8rem; color:var(--riffsmith); text-decoration:none; }}
.back:hover {{ text-decoration:underline; }}
</style></head><body><div class="wrap">
{back}
<h1>trace <span class="id">{esc(trace.get("id", ""))}</span></h1>
<p class="q">query: <b>{esc(trace.get("query", ""))}</b> · {esc(trace.get("started_at", ""))}</p>
<div class="stats">
  <span class="stat"><b>{s['spans']}</b> spans</span>
  <span class="stat"><b>{s['llm_calls']}</b> LLM calls</span>
  <span class="stat"><b>{s['tokens']:,}</b> tokens</span>
  <span class="stat"><b>{s['retries']}</b> guardrail retries</span>
  <span class="stat"><b>{s['wall']:.1f}s</b> wall</span>
</div>
{rows}
</div></body></html>"""
