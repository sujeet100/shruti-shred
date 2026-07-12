"""
The Shruti Shred demo UI — a dependency-free stdlib server (like crew/trace_portal).

It does two things and nothing else:

  * GET /            — serves ui/app.html wrapped in a minimal HTML skeleton (the same
                       content that publishes as an Artifact, so there is ONE source file).
  * POST /api/compose — runs the REAL pipeline (crew.flow.compose_flow) and returns the
                       DebateEvent stream + Composition as JSON, exactly the shape the UI
                       already consumes from its embedded replay (UI_CONTRACT.md §2/§7).

LIVE mode is OFF by default (Gemini billing is live — see CLAUDE.md "Cost discipline"):
the page runs its embedded, zero-cost replay. Flip it on for the talk with
`RMA_UI_LIVE=1 uv run python -m ui.server`, which sets `window.SHRUTI_LIVE = true` so the
Compose button calls the crew. The UI falls back to the replay if a live call fails, so a
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
<script>window.SHRUTI_LIVE = {live}; window.SHRUTI_AUDIO = "{audio}";</script>
</head>
<body>
{content}
</body>
</html>
"""


def _live_enabled() -> bool:
    """LIVE only when explicitly opted in AND a key is present — never by accident."""
    return os.getenv("RMA_UI_LIVE") == "1" and bool(os.getenv("GEMINI_API_KEY"))


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
        live="true" if _live_enabled() else "false",
        audio=_demo_audio_url(),
        content=content,
    )
    return html.encode("utf-8")


def _run_live(query: str) -> dict:
    """Run the whole crew and return the UI payload. Imported lazily so the light
    path (serving the page / offline replay) never pulls in crewai or a network client."""
    from crew.config import load_env
    from crew.flow import compose_flow

    load_env()
    state = compose_flow(query)
    return {
        "events": [e.model_dump(mode="json") for e in state.events],
        "composition": state.composition.model_dump(mode="json") if state.composition else None,
        "wav_path": state.wav_path,
        "audio": f"/audio/{Path(state.wav_path).name}" if state.wav_path else None,
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
            self._send(200, json.dumps({"live": _live_enabled()}).encode(), "application/json")
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

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/compose":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            query = json.loads(self.rfile.read(length) or b"{}").get("query", "")
            payload = _run_live(query)
            self._send(200, json.dumps(payload).encode(), "application/json")
        except Exception as exc:  # a live failure -> 503; the UI falls back to replay
            self._send(503, json.dumps({"error": str(exc)}).encode(), "application/json")

    def log_message(self, *_args) -> None:  # keep the console quiet
        pass


def serve(host: str = "127.0.0.1", port: int = 8500) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    mode = "LIVE (calls the crew)" if _live_enabled() else "replay (offline, zero cost)"
    print(f"Shruti Shred UI — {mode}")
    print(f"  http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    serve()
