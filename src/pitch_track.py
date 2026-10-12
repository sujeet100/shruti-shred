"""
PITCH TRACKING — a YIN fundamental-frequency tracker (de Cheveigne & Kawahara, 2002), numpy only.

Used to compare what a rendered voice actually SOUNDED against what its MIDI asked for
(`crew/pitch_audit.py`). Monophonic and simple on purpose: it is run on a voice rendered ALONE,
so the tracker never has to pick a sitar out of a band. Pure: arrays in, arrays out.
"""

from __future__ import annotations

from typing import Final

import numpy as np

SAMPLE_RATE: Final = 22050
_SILENT_RMS: Final = 0.003        # quieter than this, a frame has no pitch worth reporting


def track(x: np.ndarray, *, sr: int = SAMPLE_RATE, hop_s: float = 0.005, win_s: float = 0.04,
          fmin: float = 110.0, fmax: float = 900.0,
          threshold: float = 0.15) -> tuple[np.ndarray, np.ndarray]:
    """(frame centre times in s, f0 in Hz with NaN where unvoiced or silent)."""
    win, hop = int(win_s * sr), int(hop_s * sr)
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    times, f0 = [], []
    for start in range(0, len(x) - win - tmax, hop):
        frame = x[start:start + win + tmax]
        times.append((start + win / 2) / sr)
        f0.append(_frame_f0(frame, win, tmin, tmax, sr, threshold))
    return np.array(times), np.array(f0)


def _frame_f0(frame: np.ndarray, win: int, tmin: int, tmax: int, sr: int,
              threshold: float) -> float:
    if np.sqrt(np.mean(frame[:win] ** 2)) < _SILENT_RMS:
        return np.nan
    diff = np.array([np.sum((frame[:win] - frame[lag:lag + win]) ** 2) for lag in range(tmax + 1)])
    cmnd = np.r_[1.0, diff[1:] * np.arange(1, tmax + 1) / (np.cumsum(diff[1:]) + 1e-12)]
    below = np.where(cmnd[tmin:] < threshold)[0]
    if len(below) == 0:
        return np.nan
    lag = int(below[0] + tmin)
    while lag + 1 < len(cmnd) and cmnd[lag + 1] < cmnd[lag]:
        lag += 1
    if 1 <= lag < len(cmnd) - 1:                         # parabolic refinement
        a, b, c = cmnd[lag - 1], cmnd[lag], cmnd[lag + 1]
        return sr / (lag + 0.5 * (a - c) / (a - 2 * b + c + 1e-12))
    return sr / lag
