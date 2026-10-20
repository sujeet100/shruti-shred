"""
Lay the session's sound under the captured video: the band and drum stems (session_music.py)
summed with the drums lifted, the music ducked a few dB under each spoken line, and the voices
(voices.py) placed at their script times.

    uv run python talk/studio/mix.py [video] -> out/studio_session_mixed.mp4
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).resolve().parent
OUT: Final = HERE.parents[1] / "out"
BAND: Final = OUT / "studio_session_band.wav"
DRUMS: Final = OUT / "studio_session_drums.wav"
# Each stem is peak-normalised by the renderer; at 0 dB the kit sits ~10 dB under the band. This
# brings it to a metal mix's place, clearly heard on every kick and snare.
DRUM_GAIN_DB: Final = 3.0
MIN_WORD_S: Final = 0.2                       # shorter than any spoken word: a breath or a click
VOICES: Final = HERE / "voices" / "voices.json"
SCRIPT: Final = HERE / "script.json"
VOICE_GAIN_DB: Final = 4.0
# The music dips under a line (sidechain on the voices) and comes back as it ends — the words stay
# clear without the band disappearing.
# The limiter's ceiling sits at -2.5 dBFS because AAC overshoots sharp drum transients by ~1.5 dB
# (measured 2026-10-18: -1.5 dB before encoding read 0.0 after), keeping the delivered file under -1.
DUCK: Final = "sidechaincompress=threshold=0.02:ratio=5:attack=25:release=350:makeup=1"


def _words(take: Path) -> list[tuple[float, float]]:
    """The spoken words of a take: the spans between its silences."""
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(take), "-af", "silencedetect=noise=-40dB:d=0.12",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    length = float(re.search(r"Duration: (\d+):(\d+):([\d.]+)", log).group(3))
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [0.0] + [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    spans = [(a, min(b, length)) for a, b in zip(ends, [*starts, length])]
    return [(a, b) for a, b in spans if b - a >= MIN_WORD_S]           # a breath is not a word


def _placed(k: int, line: dict) -> str:
    """Line k's voice on the timeline: the whole take at its time, or — for a count-in with
    `on_beats` — each word cut out and dropped on its hi-hat click."""
    gain = f"volume={VOICE_GAIN_DB}dB"
    beats = line.get("on_beats")
    words = _words(VOICES.parent / line["file"]) if beats else []
    if not beats or len(words) != len(beats):
        return f"[{k + 3}:a]adelay={round(line['at'] * 1000)}:all=1,{gain}[v{k}]"
    cuts = "".join(f"[w{k}_{j}]" for j in range(len(words)))
    parts = [f"[{k + 3}:a]asplit={len(words)}{cuts}"]
    parts += [f"[w{k}_{j}]atrim={a:.3f}:{min(b, a + 0.48):.3f},asetpts=PTS-STARTPTS,"
              f"adelay={round(t * 1000)}:all=1[x{k}_{j}]" for j, ((a, b), t) in enumerate(zip(words, beats))]
    joined = "".join(f"[x{k}_{j}]" for j in range(len(words)))
    parts.append(f"{joined}amix=inputs={len(words)}:normalize=0,{gain}[v{k}]")
    return ";".join(parts)


def mix(video: Path, out: Path) -> Path:
    lines = json.loads(VOICES.read_text())
    script = json.loads(SCRIPT.read_text())["lines"]               # same order as the takes
    lines = [{**line, **script[k]} for k, line in enumerate(lines)]  # timing from the script
    inputs = ["-i", str(video), "-i", str(BAND), "-i", str(DRUMS)]
    for line in lines:
        inputs += ["-i", str(VOICES.parent / line["file"])]
    placed = [_placed(k, line) for k, line in enumerate(lines)]
    voices = "".join(f"[v{k}]" for k in range(len(lines)))
    graph = ";".join([f"[2:a]volume={DRUM_GAIN_DB}dB[kit]",
                      "[1:a][kit]amix=inputs=2:normalize=0:duration=longest[music]",
                      *placed,
                      # padded with silence: the compressor stops when its key ends, which
                      # would cut the music at the last line
                      f"{voices}amix=inputs={len(lines)}:normalize=0,apad,asplit=2[vox][key]",
                      f"[music][key]{DUCK}[ducked]",
                      "[ducked][vox]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.75:attack=1:release=60:level=disabled[a]"])
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph,
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                    "-shortest", str(out)], check=True)
    return out


if __name__ == "__main__":
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "studio_session.mp4"
    print(mix(video, OUT / "studio_session_mixed.mp4"))
