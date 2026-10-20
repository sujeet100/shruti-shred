"""Redraw the clips the Sahaj deck keeps (waveform still + playhead video) in the light theme, and
cut the Bageshree before/after clip (free: ffmpeg over saved renders, no LLM, no live render).

    uv run python talk/audio/restyle_clips.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_clips  # noqa: E402

KEEP = ("FA", "FB", "FC", "A04")
OUTDIR = HERE.parents[1] / "out"
BAGESHREE = "fusion_20261013_081705_bageshree_alap_{}_mix.wav"
WINDOW = (6.0, 5.8)          # the first Ga (6.5 s) and the Ma->Ga release (10 s), seconds


def bageshree_ab() -> None:
    """BG: the original alap's Ga (it swings up and turns on the wrong note), a breath, then the
    corrected one, loudness-matched, as one clip."""
    parts = [(OUTDIR / BAGESHREE.format(tag), *WINDOW) for tag in ("C_original", "B_corrected")]
    make_clips.assemble("BG", parts, gap_s=0.8)


def main() -> None:
    make_clips.FG, make_clips.BG = "0x33357D", "0xFBF9F5"
    bageshree_ab()
    for clip in (*KEEP, "BG"):
        make_clips.visuals(clip)
        print("redrawn", clip)


if __name__ == "__main__":
    main()
