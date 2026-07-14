"""
The Shruti Shred demo UI — a dependency-free stdlib server (like crew/trace_portal).

It does two things and nothing else:

  * GET /            — serves ui/app.html wrapped in a minimal HTML skeleton (the same
                       content that publishes as an Artifact, so there is ONE source file).
  * POST /api/compose — runs the REAL pipeline (crew.flow.compose_flow) and returns the
                       DebateEvent stream + Composition as JSON, exactly the shape the UI
                       already consumes from its embedded replay (UI_CONTRACT.md §2/§7).

LIVE is opt-in per run from the UI itself (a Source toggle: Live ⇄ Demo). The server
advertises two facts to the page via the skeleton and /api/health:
  * SHRUTI_LIVE_CAPABLE — a GEMINI_API_KEY is present, so live CAN run (the toggle unlocks).
  * SHRUTI_LIVE         — the toggle's DEFAULT position (Live only if RMA_UI_LIVE=1 AND a
                          key exists; otherwise Demo, the zero-cost embedded replay).
So the default is always the cost-safe Demo unless you explicitly opt in with
`RMA_UI_LIVE=1`, but a presenter with a key can still flip Live on from the page. /api/compose
runs the REAL pipeline; with no key it returns 503 and the UI falls back to the replay, so a
dead key on stage never blanks the screen.

Run:  uv run python -m ui.server   ->  http://127.0.0.1:8500
"""

from __future__ import annotations

import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_APP_HTML = Path(__file__).with_name("app.html")
_FONTS_DIR = Path(__file__).with_name("fonts")
_PIXEL_FONTS = (("PressStart2P", "PressStart2P.ttf"), ("VT323", "VT323.ttf"))
_OUT_DIR = Path(__file__).resolve().parent.parent / "out"   # the FluidSynth-rendered WAVs live here

_SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Shruti Shred — श्रुति श्रेड</title>
<style>*{{margin:0;padding:0}}html,body{{background:#08070d}}</style>
<script>window.SHRUTI_LIVE = {live}; window.SHRUTI_LIVE_CAPABLE = {capable}; window.SHRUTI_AUDIO = "{audio}";</script>
</head>
<body>
{content}
</body>
</html>
"""


def _live_capable() -> bool:
    """A GEMINI_API_KEY is present, so a live run is possible at all (the toggle unlocks)."""
    return bool(os.getenv("GEMINI_API_KEY"))


def _live_default() -> bool:
    """The Source toggle's DEFAULT position: Live only when explicitly opted in AND a key
    exists — never live by accident. Otherwise the cost-safe embedded Demo."""
    return os.getenv("RMA_UI_LIVE") == "1" and _live_capable()


def font_face_css() -> str:
    """Inline the pixel fonts as @font-face data URIs (the artifact CSP blocks font CDNs)."""
    faces = []
    for family, fname in _PIXEL_FONTS:
        path = _FONTS_DIR / fname
        if not path.exists():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            f"@font-face{{font-family:'{family}';"
            f"src:url(data:font/ttf;base64,{b64}) format('truetype');font-display:block;}}"
        )
    return "\n".join(faces)


def _demo_audio_url() -> str:
    """A real rendered WAV to play in replay mode — the full-band flow output if present."""
    for name in ("flow_demo.wav", "full_band.wav", "rhythm_section.wav"):
        if (_OUT_DIR / name).exists():
            return f"/audio/{name}"
    wavs = sorted(_OUT_DIR.glob("*.wav"))
    return f"/audio/{wavs[0].name}" if wavs else ""


def _page() -> bytes:
    content = _APP_HTML.read_text(encoding="utf-8").replace("/*__PIXEL_FONTS__*/", font_face_css())
    html = _SKELETON.format(
        live="true" if _live_default() else "false",
        capable="true" if _live_capable() else "false",
        audio=_demo_audio_url(),
        content=content,
    )
    return html.encode("utf-8")


def _live_ctx():
    """The tracing context for a live run — writes a traces/ file so the portal can show it
    (RMA_TRACE=0 opts out). Lazily imported so the light path never pulls in tracing."""
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    return traced("ui-live") if tracing_enabled() else nullcontext()


def _run_live(query: str) -> dict:
    """Run the whole crew and return the UI payload. Imported lazily so the light
    path (serving the page / offline replay) never pulls in crewai or a network client."""
    from crew.config import load_env
    from crew.flow import compose_flow

    load_env()
    if not _live_capable():
        raise RuntimeError("no GEMINI_API_KEY — set it in .env to run live")
    with _live_ctx():
        state = compose_flow(query)
    return {
        "events": [e.model_dump(mode="json") for e in state.events],
        "composition": state.composition.model_dump(mode="json") if state.composition else None,
        "wav_path": state.wav_path,
        "audio": f"/audio/{Path(state.wav_path).name}" if state.wav_path else None,
    }


_STREAM_END = object()   # sentinel: the worker thread finished


def _compose_events(query: str):
    """Yield each DebateEvent (as a JSON dict) AS the crew produces it, then a final
    {'done': True, composition, audio}. The flow runs in a worker thread that publishes to a
    live sink -> a Queue; this generator (on the request thread) drains the queue, so events
    surface live instead of only at the end. On failure it yields {'error': ...}."""
    import queue
    import threading

    from crew.config import load_env
    from crew.flow import compose_flow
    from crew.live import live_sink

    load_env()
    if not _live_capable():
        yield {"error": "no GEMINI_API_KEY — set it in .env to run live"}
        return

    q: queue.Queue = queue.Queue()
    box: dict = {}

    def worker() -> None:
        try:
            with _live_ctx(), live_sink(lambda e: q.put(e.model_dump(mode="json"))):
                box["state"] = compose_flow(query)
        except Exception as exc:  # noqa: BLE001 — surface any live failure to the client
            box["error"] = str(exc)
        finally:
            q.put(_STREAM_END)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = q.get()
        if item is _STREAM_END:
            break
        yield item

    if "error" in box:
        yield {"error": box["error"]}
        return
    state = box.get("state")
    yield {
        "done": True,
        "composition": state.composition.model_dump(mode="json") if state and state.composition else None,
        "audio": f"/audio/{Path(state.wav_path).name}" if state and state.wav_path else None,
    }


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path in ("/", "/index.html"):
            self._send(200, _page(), "text/html; charset=utf-8")
        elif self.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif self.path == "/api/health":
            health = {"live_capable": _live_capable(), "live_default": _live_default()}
            self._send(200, json.dumps(health).encode(), "application/json")
        elif self.path.startswith("/audio/"):
            self._serve_audio(self.path[len("/audio/"):])
        else:
            self._send(404, b"not found", "text/plain")

    def _serve_audio(self, name: str) -> None:
        """Serve a rendered WAV from out/ with HTTP Range support (so <audio> can seek)."""
        name = os.path.basename(name)
        path = _OUT_DIR / name
        if not name.endswith((".wav", ".mid")) or not path.exists():
            self._send(404, b"not found", "text/plain")
            return
        data = path.read_bytes()
        ctype = "audio/wav" if name.endswith(".wav") else "audio/midi"
        rng = self.headers.get("Range", "")
        start, end = 0, len(data) - 1
        partial = False
        if rng.startswith("bytes="):
            try:
                s, _, e = rng[6:].partition("-")
                start = int(s) if s else 0
                end = int(e) if e else len(data) - 1
                end = min(end, len(data) - 1)
                partial = True
            except ValueError:
                partial = False
        chunk = data[start:end + 1]
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        try:
            self.wfile.write(chunk)
        except BrokenPipeError:
            pass

    def _read_query(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}").get("query", "")
        except (ValueError, AttributeError):
            return ""

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/compose":
            query = self._read_query()
            try:
                payload = _run_live(query)
                self._send(200, json.dumps(payload).encode(), "application/json")
            except Exception as exc:  # a live failure -> 503; the UI falls back to replay
                self._send(503, json.dumps({"error": str(exc)}).encode(), "application/json")
        elif self.path == "/api/compose/stream":
            self._compose_stream(self._read_query())
        else:
            self._send(404, b"not found", "text/plain")

    def _compose_stream(self, query: str) -> None:
        """Stream the run as newline-delimited JSON — one event per line as it happens, then a
        final {'done': ...}. Flushed per line so the browser renders progress live; the
        request thread stays open for the whole run (ThreadingHTTPServer serves others)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for item in _compose_events(query):
                self.wfile.write((json.dumps(item) + "\n").encode())
                self.wfile.flush()
        except BrokenPipeError:
            pass   # the client navigated away mid-stream

    def log_message(self, *_args) -> None:  # keep the console quiet
        pass


def serve(host: str = "127.0.0.1", port: int = 8500) -> None:
    # Load .env at the entry point (not import time) so capability detection sees the key
    # even when it lives only in .env. Light path: crew.config has no crewai import.
    from crew.config import load_env
    load_env()
    server = ThreadingHTTPServer((host, port), _Handler)
    if _live_default():
        mode = "LIVE by default (calls the crew)"
    elif _live_capable():
        mode = "Demo by default — Live toggle UNLOCKED (a key is present)"
    else:
        mode = "Demo only — no GEMINI_API_KEY, so Live is locked"
    print(f"Shruti Shred UI — {mode}")
    print(f"  http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    serve()
