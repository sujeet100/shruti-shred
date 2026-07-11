"""
Local trace portal — list every run by its trace id and open any one.

A dependency-free web app (stdlib http.server) over the traces/ directory, shaped
like Langfuse: the index lists each run (one TRACE = one unique id) with its
headline numbers, and clicking an id renders that run's full span timeline
(prompts, responses, tokens, guardrail retries). No cloud, no framework.

Run:   uv run python -m crew.trace_portal            # serves http://127.0.0.1:8420
       uv run python -m crew.trace_portal 9000 out   # custom port + traces dir

Generate traces first with:  uv run python -m crew.composers "..."   (traced by default)
"""

from __future__ import annotations

import html
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from crew.tracing import render_trace, trace_stats

_DEFAULT_PORT = 8420
_DEFAULT_DIR = "traces"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _list_traces(directory: Path) -> list[dict[str, Any]]:
    """Every trace in the directory, newest first, with its id, query and stats."""
    traces: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            trace = _load(path)
        except (ValueError, OSError):
            continue
        traces.append({
            "id": trace.get("id", path.stem),
            "query": trace.get("query", trace.get("name", path.stem)),
            "started_at": trace.get("started_at", ""),
            "epoch": trace.get("epoch", path.stat().st_mtime),
            **trace_stats(trace.get("spans", [])),
        })
    traces.sort(key=lambda t: t["epoch"], reverse=True)
    return traces


def render_index(directory: Path) -> str:
    esc = html.escape
    traces = _list_traces(directory)
    if traces:
        rows = "\n".join(
            f'<a class="trace" href="/t/{esc(t["id"])}">'
            f'<span class="id">{esc(t["id"])}</span>'
            f'<span class="q">{esc(t["query"])}</span>'
            f'<span class="when">{esc(t["started_at"])}</span>'
            f'<span class="m">{t["llm_calls"]} calls</span>'
            f'<span class="m">{t["tokens"]:,} tok</span>'
            f'<span class="m retries{" hot" if t["retries"] else ""}">{t["retries"]} retry</span>'
            f'<span class="m">{t["wall"]:.1f}s</span>'
            f'</a>' for t in traces)
    else:
        rows = ('<p class="empty">No traces yet. Generate one with '
                '<code>uv run python -m crew.composers "doom fusion in Darbari"</code></p>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>trace portal</title>
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
.wrap {{ max-width:56rem; margin:0 auto; padding:2.4rem 1.2rem 4rem; }}
h1 {{ font-size:1.3rem; margin:0 0 .2rem; font-weight:600; }}
.sub {{ color:var(--soft); font-size:.9rem; margin:0 0 1.6rem; }}
.sub code {{ font-family:var(--mono); font-size:.85em; }}
.trace {{ display:grid; grid-template-columns:6.5rem 1fr auto auto auto auto auto;
  gap:.35rem .9rem; align-items:baseline; padding:.7rem .85rem; border:1px solid var(--hair);
  border-radius:9px; background:var(--panel); margin-bottom:.5rem; text-decoration:none; color:var(--ink); }}
.trace:hover {{ border-color:var(--pandit); }}
.id {{ font-family:var(--mono); font-weight:600; font-size:.82rem; color:var(--pandit); }}
.q {{ font-size:.9rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.when {{ font-family:var(--mono); font-size:.74rem; color:var(--soft); }}
.m {{ font-family:var(--mono); font-size:.76rem; color:var(--soft); font-variant-numeric:tabular-nums; }}
.retries.hot {{ color:var(--danger); }}
.empty {{ color:var(--soft); }}
.empty code {{ font-family:var(--mono); background:var(--panel); padding:.15em .4em; border-radius:5px;
  border:1px solid var(--hair); font-size:.82em; }}
@media (max-width:680px) {{
  .trace {{ grid-template-columns:6.5rem 1fr; }}
  .when, .m {{ grid-column:span 1; }}
  .q {{ white-space:normal; }}
}}
</style></head><body><div class="wrap">
<h1>Trace portal</h1>
<p class="sub">{len(traces)} run{"s" if len(traces) != 1 else ""} in
  <code>{esc(str(directory))}/</code> · newest first · one id = one run</p>
{rows}
</div></body></html>"""


def _make_handler(directory: Path) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def _send(self, body: str, status: int = 200) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 — http.server's required name
            path = self.path.split("?", 1)[0]
            if path in ("/", ""):
                self._send(render_index(directory))
            elif path.startswith("/t/"):
                trace_id = unquote(path[len("/t/"):])
                jsonf = directory / f"{trace_id}.json"
                if jsonf.is_file() and jsonf.parent == directory:
                    self._send(render_trace(_load(jsonf), home_link="/"))
                else:
                    self._send("<p>trace not found — <a href='/'>back</a></p>", status=404)
            else:
                self._send("<p>not found — <a href='/'>back</a></p>", status=404)

        def log_message(self, *_args: Any) -> None:  # keep the console quiet
            pass

    return _Handler


def serve(port: int = _DEFAULT_PORT, traces_dir: str = _DEFAULT_DIR) -> int:
    directory = Path(traces_dir)
    directory.mkdir(parents=True, exist_ok=True)
    server = HTTPServer(("127.0.0.1", port), _make_handler(directory))
    print(f"trace portal → http://127.0.0.1:{port}   (traces in {directory}/)")
    print("  Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str]) -> int:
    port = int(argv[0]) if argv else _DEFAULT_PORT
    traces_dir = argv[1] if len(argv) > 1 else _DEFAULT_DIR
    return serve(port, traces_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
