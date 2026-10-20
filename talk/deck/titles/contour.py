"""Measure the Bageshree Ga contours (original vs corrected) from the solo-sitar renders, for the
Lesson 4 chart. Free: YIN over saved WAVs. Writes titles/bageshree_contour.json.

    uv run python talk/deck/titles/contour.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from pitch_track import SAMPLE_RATE, track  # noqa: E402

SA = 62                      # D
WINDOW = (9.9, 11.6)         # the Ma -> Ga release / the old sway turning on shuddha Ga
GA = 3                       # komal Ga, semitones above Sa


def samples(wav: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-t", "13", "-ac", "1", "-ar", str(SAMPLE_RATE),
                          "-f", "s16le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def contour(tag: str) -> list[tuple[float, float]]:
    wav = ROOT / "out" / f"fusion_20261013_081705_bageshree_alap_{tag}_sitar.wav"
    t, f0 = track(samples(wav), fmin=200.0, fmax=1000.0)
    out = []
    for lo in np.arange(WINDOW[0], WINDOW[1], 0.02):
        m = (t >= lo) & (t < lo + 0.02) & ~np.isnan(f0)
        if m.sum() >= 1:
            semis = 69 + 12 * np.log2(float(np.median(f0[m])) / 440.0) - SA
            out.append((round(float(lo - WINDOW[0]), 3), round(float((semis % 12 - GA) * 100), 1)))
    return out


if __name__ == "__main__":
    data = {"window": WINDOW, "original": contour("C_original"), "corrected": contour("B_corrected")}
    (Path(__file__).parent / "bageshree_contour.json").write_text(json.dumps(data))
    for k in ("original", "corrected"):
        v = [c for _, c in data[k]]
        print(k, len(v), "min", min(v), "max", max(v))
