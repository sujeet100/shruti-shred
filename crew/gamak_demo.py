"""
A no-LLM SOUND CHECK for gamak cells (2026-10-12): sketches of the gamak passages in Sujit's
guruji's recorded Darbari gat, written the way the composer would write them (a note with
`gamak_with`) and run through the REAL expression passes (gamak cells, measured gestures, kan),
at his tempo (120 bpm) and Sa (D). Sketches, not transcriptions: the swaras and pairs are from
the pitch track, the rhythm is approximate. One cue A/Bs the old per-note climax shake.

Run: `uv run python -m crew.gamak_demo` -> out/gamak_darbari_<timestamp>.wav (+ a cue sheet)
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

from crew.contracts import Composition, Layer, Note
from crew.expression import with_gamak_cells, with_gestures, with_kan
from crew.generators import VOICES

_RAGA: Final = "darbari"
_BPM: Final = 120           # guruji's pulse
_SA: Final = 62             # D, his Sa
_GAP: Final = 2.0           # silence between cues, in beats

Phrase = list[tuple[str, int, float, dict]]


@dataclass
class _Cues:
    """Lays phrases end to end with a gap, remembering where each cue starts."""
    notes: list[Note] = field(default_factory=list)
    sheet: list[tuple[float, str]] = field(default_factory=list)
    t: float = 0.0

    def add(self, label: str, phrase: Phrase) -> None:
        self.sheet.append((self.t * 60 / _BPM, label))
        for swara, octave, dur, extra in phrase:
            self.notes.append(Note(swara=swara, oct=octave, start=self.t, dur=dur, vel=100,
                                   **extra))
            self.t += dur
        self.t += _GAP


def _cues() -> _Cues:
    c = _Cues()
    c.add("the gat's opening: Sa, then Ma swung onto Ga, Sa strokes, Ga swung up to Ma",
          [("S", 0, 0.5, {}), ("m", 0, 1.0, {"gamak_with": "g"}), ("S", 0, 0.5, {}),
           ("S", 0, 0.5, {}), ("S", 0, 0.5, {}), ("g", 0, 1.0, {"gamak_with": "m"}),
           ("R", 0, 0.5, {}), ("S", 0, 1.5, {})])
    c.add("29-34 s: Pa<->Ma, then Dha<->Ni, resolving down the Kanada way (n P m P)",
          [("P", 0, 1.5, {"gamak_with": "m"}), ("d", 0, 1.5, {"gamak_with": "n"}),
           ("n", 0, 0.5, {}), ("P", 0, 0.5, {}), ("m", 0, 0.5, {}), ("P", 0, 2.0, {})])
    c.add("34-38 s: the mandra Pa<->Dha swing",
          [("P", -1, 2.0, {"gamak_with": "d"}), ("d", -1, 1.0, {}), ("P", -1, 2.0, {})])
    line: Phrase = [("R", 0, 0.5, {}), ("g", 0, 1.0, {}), ("m", 0, 1.0, {}), ("P", 0, 1.0, {}),
                    ("m", 0, 0.5, {}), ("g", 0, 1.0, {}), ("R", 0, 0.5, {}), ("S", 0, 1.5, {})]
    c.add("A — the OLD climax shake: each note bent up to its next swara", [
        (sw, o, d, {"gamak_st": 2 if sw in "RmP" else 1}) for sw, o, d, _ in line])
    c.add("B — the same line as gamak CELLS where a composer would place them", [
        (sw, o, d, {"gamak_with": "m"} if (sw, d) == ("g", 1.0) and i == 1 else
         {"gamak_with": "P"} if sw == "m" and d == 1.0 else {}) for i, (sw, o, d, _) in
        enumerate(line)])
    return c


def _expressed(notes: list[Note]) -> list[Note]:
    """The live expression passes (andolan depth and the climax fallback aside)."""
    return with_kan(with_gestures(with_gamak_cells(notes, _RAGA, _BPM), _RAGA, _BPM),
                    _RAGA, _BPM)


def _composition(cues: _Cues) -> Composition:
    sitar, drone = VOICES["sitar"], VOICES["drone"]
    lead = Layer(role="lead", instrument=sitar.instrument, program=sitar.program,
                 channel=sitar.channel, pan=sitar.pan, notes=_expressed(cues.notes))
    tanpura = Layer(role="drone", instrument=drone.instrument, program=drone.program,
                    channel=drone.channel, pan=drone.pan,
                    notes=[Note(swara="S", oct=-1, start=0.0, dur=cues.t, vel=50),
                           Note(swara="P", oct=-2, start=0.0, dur=cues.t, vel=42)])
    return Composition(raga=_RAGA, sa=_SA, bpm=_BPM,
                       tala={"name": "teentaal", "beats_per_bar": 16.0}, layers=[tanpura, lead])


def main() -> int:
    from crew.generators import render_composition

    root = Path(__file__).resolve().parents[1]
    soundfont = root / "soundfonts" / "GeneralUser-GS.sf2"
    if not (shutil.which("fluidsynth") and soundfont.exists()):
        print("-> render skipped (fluidsynth or soundfont not found)")
        return 1
    cues = _cues()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    wav = render_composition(_composition(cues), out_dir=root / "out",
                             name=f"gamak_{_RAGA}_{stamp}", soundfont=soundfont)
    print(f"\n-> {wav.relative_to(root)}")
    for seconds, label in cues.sheet:
        print(f"   {int(seconds // 60)}:{seconds % 60:04.1f}  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
