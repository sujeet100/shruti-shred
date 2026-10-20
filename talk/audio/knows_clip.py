"""KN: what the plain prompt knew, and what it didn't (free: ffmpeg over the saved bare-prompt renders,
no LLM, no live render).

    Bageshree's opening: the raga's signature phrase, resting on Ma, almost word for word.
    Malkauns' middle: the same five notes run evenly up and down, resting on dha, with no glide;
    it stops sounding like Malkauns.

    uv run python talk/audio/knows_clip.py   ->  talk/audio/KN.{wav,png,mp4}
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_clips  # noqa: E402

SEC_PER_BEAT = 60.0 / 128
PARTS = ((HERE / "GA.wav", 0.0, 16 * SEC_PER_BEAT + 0.6),           # Bageshree, the four-bar pakad opening
         (HERE / "MA.wav", 48 * SEC_PER_BEAT, 16 * SEC_PER_BEAT))    # Malkauns, the even pentatonic run


def main() -> None:
    make_clips.FG, make_clips.BG = "0x33357D", "0xFBF9F5"            # the deck's light theme
    _, stats = make_clips.assemble("KN", list(PARTS), gap_s=0.8)
    make_clips.visuals("KN")
    print("KN", stats)


if __name__ == "__main__":
    main()
