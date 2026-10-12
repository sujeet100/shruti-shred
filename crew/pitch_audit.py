"""
PITCH AUDIT — what the sitar actually SOUNDED against what its MIDI asked for.

A MIDI file can be correct and still sound wrong (the synthesizer may ignore a bend range, a
sample may be detuned, a gesture may run into silence). This renders the composition's sitar
ALONE through the real renderer and soundfont, tracks its pitch (`src/pitch_track.py`), rebuilds
the intended pitch from the MIDI's notes and pitch-wheel events, and reports per note how far the
two differ — octave-blind (the Indian Ensemble sitar is transposed to correct its octave-low
samples) and skipping each pluck's first 50 ms (a string starts sharp; that is the instrument).

    uv run python -m crew.pitch_audit out/<render>.json [seconds]

The shell edge: it renders and reads files. The arithmetic is `deviations`, which is pure.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

import mido
import numpy as np

_ROOT: Final = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from pitch_track import SAMPLE_RATE, track  # noqa: E402
from render import MEEND_RANGE  # noqa: E402

ATTACK_SKIP_S: Final = 0.05       # a plucked string starts sharp — not an intonation fault
OFF_CENTS: Final = 25             # a frame further than this from the intended pitch is "off"


def intended(mid_path: str, channel: int) -> list[tuple[float, float, int, list[tuple[float, int]]]]:
    """(on, off, MIDI pitch, wheel events inside) for each note on `channel`, in seconds."""
    notes, wheel, open_on = [], [], {}
    t = 0.0
    for msg in mido.MidiFile(mid_path):
        t += msg.time
        if getattr(msg, "channel", None) != channel:
            continue
        if msg.type == "pitchwheel":
            wheel.append((t, msg.pitch))
        elif msg.type == "note_on" and msg.velocity > 0:
            open_on[msg.note] = t
        elif msg.type in ("note_on", "note_off") and msg.note in open_on:
            notes.append((open_on.pop(msg.note), t, msg.note))
    return [(on, off, p, [(w, v) for w, v in wheel if on - 0.01 <= w < off]) for on, off, p in sorted(notes)]


def _wheel_at(events: list[tuple[float, int]], t: float) -> int:
    value = 0
    for when, v in events:
        if when > t:
            break
        value = v
    return value


def deviations(notes, times: np.ndarray, f0: np.ndarray) -> list[dict]:
    """Per note: frames tracked, median and worst |cents| from the intended pitch, share off. Pure."""
    report = []
    for on, off, pitch, events in notes:
        mask = (times >= on + ATTACK_SKIP_S) & (times < off) & ~np.isnan(f0)
        if mask.sum() < 4:
            continue
        cents = []
        for t, f in zip(times[mask], f0[mask]):
            want = pitch + _wheel_at(events, t) / 8191 * MEEND_RANGE
            got = 69 + 12 * np.log2(f / 440.0)
            cents.append((got - want) * 100)
        dev = np.abs((np.array(cents) + 600) % 1200 - 600)   # octave-blind
        report.append({"on": round(on, 2), "pitch": pitch, "frames": int(mask.sum()),
                       "median": float(np.median(dev)), "worst": float(dev.max()),
                       "off_share": float(np.mean(dev > OFF_CENTS))})
    return report


def _render_solo(comp_path: str, out_dir: Path) -> tuple[Path, Path, int]:
    sys.path.insert(0, str(_ROOT))
    from crew.contracts import Composition
    from crew.generators import render_composition
    comp = Composition.model_validate(json.loads(Path(comp_path).read_text()))
    lead = [layer for layer in comp.layers if layer.role == "lead"]
    wav = render_composition(comp.model_copy(update={"layers": lead}), out_dir=out_dir, name="solo",
                             soundfont=_ROOT / "soundfonts" / "GeneralUser-GS.sf2")
    return Path(wav), out_dir / "solo.mid", lead[0].channel


def _samples(wav: Path, seconds: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-t", str(seconds), "-ac", "1",
                          "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"], check=True,
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def main(argv: list[str]) -> int:
    comp_path, seconds = argv[0], float(argv[1]) if len(argv) > 1 else 60.0
    with tempfile.TemporaryDirectory() as tmp:
        wav, mid, channel = _render_solo(comp_path, Path(tmp))
        times, f0 = track(_samples(wav, seconds))
        report = deviations([n for n in intended(str(mid), channel) if n[0] < seconds], times, f0)
    off = [r for r in report if r["off_share"] > 0.2]
    print(f"{len(report)} sitar notes tracked in the first {seconds:g} s; "
          f"median deviation {np.median([r['median'] for r in report]):.1f} cents; "
          f"{len(off)} note(s) more than a fifth of the time over {OFF_CENTS} cents off:")
    for r in off:
        print(f"  {r['on']:7.2f} s  pitch {r['pitch']}  median {r['median']:.0f}  worst "
              f"{r['worst']:.0f}  off {r['off_share']:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
