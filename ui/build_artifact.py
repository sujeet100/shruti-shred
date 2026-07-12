"""
Build the SELF-CONTAINED artifact version of the UI (for publishing to claude.ai).

The local server injects the pixel fonts and serves the WAVs at runtime, so ui/app.html
stays small. The artifact has no server, so this bakes both in:
  * the two pixel fonts as @font-face data URIs (into the /*__PIXEL_FONTS__*/ slot), and
  * a short, mono, real FluidSynth WAV clip as a data URI (into the __EMBED_AUDIO__ token),
    so the standalone page still plays the true rendered sound.

Usage:  uv run python ui/build_artifact.py [out.html]   (default: <cwd>/app_artifact.html)
"""

from __future__ import annotations

import array
import base64
import io
import sys
import wave
from pathlib import Path

_UI = Path(__file__).resolve().parent
_OUT = _UI.parent / "out"
_PIXEL_FONTS = (("PressStart2P", "PressStart2P.ttf"), ("VT323", "VT323.ttf"))


def _font_faces() -> str:
    faces = []
    for family, fname in _PIXEL_FONTS:
        b64 = base64.b64encode((_UI / "fonts" / fname).read_bytes()).decode("ascii")
        faces.append(
            f"@font-face{{font-family:'{family}';"
            f"src:url(data:font/ttf;base64,{b64}) format('truetype');font-display:block;}}"
        )
    return "\n".join(faces)


def _clip_data_uri(src: str = "flow_demo.wav", seconds: float = 12.0) -> str:
    """A short, mono clip of a real render, as a base64 data URI (keeps the artifact small)."""
    with wave.open(str(_OUT / src), "rb") as w:
        nch, sw, fr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(min(w.getnframes(), int(fr * seconds)))
    if nch == 2 and sw == 2:  # fold stereo to mono to halve the payload
        a = array.array("h")
        a.frombytes(raw)
        mono = array.array("h", [(a[i] + a[i + 1]) // 2 for i in range(0, len(a) - 1, 2)])
        raw, nch = mono.tobytes(), 1
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(nch)
        out.setsampwidth(sw)
        out.setframerate(fr)
        out.writeframes(raw)
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build(dest: Path) -> Path:
    html = (_UI / "app.html").read_text(encoding="utf-8")
    html = html.replace("/*__PIXEL_FONTS__*/", _font_faces())
    html = html.replace("__EMBED_AUDIO__", _clip_data_uri())
    dest.write_text(html, encoding="utf-8")
    return dest


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "app_artifact.html"
    out = build(target)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
