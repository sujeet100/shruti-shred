"""Render ANY .mid through the project's FluidSynth chain — same soundfont stack
(GM base + SGM/Dethmetal/Indian extras), gain, reverb and bank-select mode as our
composition renders, so an externally exported MIDI can be A/B'd against our output
on identical synthesis settings.

Usage:  uv run python src/play_mid.py <file.mid> [out.wav]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from render import _GAIN, _REVERB_SETTINGS
from soundfont import BASE_SOUNDFONT, present_extras


def render_mid(mid_path: Path, wav_path: Path) -> Path:
    """Shell out to fluidsynth exactly as `render.render` does (sans build_midi)."""
    cmd = ["fluidsynth", "-ni", "-g", str(_GAIN)]
    for setting in _REVERB_SETTINGS:
        cmd += ["-o", setting]
    extras = present_extras()
    if extras:
        cmd += ["-o", "synth.midi-bank-select=mma"]
    cmd += ["-F", str(wav_path), "-r", "44100", str(BASE_SOUNDFONT)]
    for extra in extras:
        cmd += ["-b", str(extra.bank_offset), str(extra.path)]
    cmd.append(str(mid_path))
    subprocess.run(cmd, check=True, capture_output=True)
    return wav_path


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    mid = Path(argv[0])
    wav = Path(argv[1]) if len(argv) > 1 else mid.with_suffix(".wav")
    print(f"-> {render_mid(mid, wav)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
