"""Song C of the single-prompt experiment for any raga: the FULL system (today's default path)
composes the same one-minute request the bare call got, traced and rendered under a unique name.

    uv run python talk/audio/system_song.py yaman      # -> out/fusion_<stamp>_yaman.{wav,json}

LIVE: one full Flow run (about 20-25 model calls). Ask Sujit first (CLAUDE.md).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def request(raga: str) -> str:
    """The bare call's ask in plain words (band_ladder.BASE): Sa = E, 128 BPM, one minute."""
    return f"a one-minute heavy metal song in raga {raga.title()}, key of E, 128 bpm"


def main(raga: str) -> Path:
    from crew.config import load_env
    from crew.flow import compose_flow, production_stages
    from crew.tracing import traced
    load_env()
    name = f"fusion_{time.strftime('%Y%m%d_%H%M%S')}_{raga}"
    with traced(f"single-prompt-C-{raga}"):
        state = compose_flow(request(raga), stages=production_stages(name=name))
    print(f"{raga}: decision {state.decision} after {state.round} round(s); {state.wav_path}")
    return ROOT / "out" / name


if __name__ == "__main__":
    main(sys.argv[1])
