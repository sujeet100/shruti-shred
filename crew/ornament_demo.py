"""
A no-LLM SOUND CHECK for the ornament campaign (2026-10-11): hand-written sitar lines over the
drone, rendered through the same soundfonts and routing as a live piece, so the ear can judge
the gestures before any live run. Two files, each with a printed cue sheet:

  Bhairav   — andolan depth A/B on komal re and komal dha (30 / 50 / 70 cents, all below),
              unstruck kan in the pakad, and a gamak run;
  Bageshree — Sujit's Ma->Ga: a slow reverse bend vs the quick gat pull, ga swaying UP toward
              ma after a Ma kan, and a slow meend D->m that rests on Pa on the way down.

Run: `uv run python -m crew.ornament_demo` -> out/ornaments_<raga>_<timestamp>.wav
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

from crew.contracts import Composition, Layer, Note
from crew.generators import VOICES

_BPM: Final = 60            # slow enough that every hold clears the 1-second andolan gate
_SA: Final = 64             # E, the opener's key
_GAP: Final = 2.0           # silence between cues, in beats


@dataclass
class _Cues:
    """Lays phrases end to end with a gap, remembering where each cue starts."""
    notes: list[Note] = field(default_factory=list)
    sheet: list[tuple[float, str]] = field(default_factory=list)
    t: float = 0.0

    def add(self, label: str, phrase: list[tuple[str, int, float, dict]]) -> None:
        self.sheet.append((self.t * 60 / _BPM, label))
        for swara, octave, dur, extra in phrase:
            self.notes.append(Note(swara=swara, oct=octave, start=self.t, dur=dur, vel=96, **extra))
            self.t += dur
        self.t += _GAP


def _bhairav() -> _Cues:
    c = _Cues()
    for cents in (30, 50, 70):
        c.add(f"komal re andolan, {cents} cents below (toward Sa)",
              [("G", 0, 1, {}), ("r", 0, 4, {"andolan": True, "andolan_st": -cents / 100}),
               ("S", 0, 2, {})])
    for cents in (30, 50, 70):
        c.add(f"komal dha andolan, {cents} cents below (toward Pa)",
              [("N", 0, 1, {}), ("d", 0, 4, {"andolan": True, "andolan_st": -cents / 100}),
               ("P", 0, 2, {})])
    c.add("pakad with UNSTRUCK kan — (N)d and (G)r, one pluck each",
          [("G", 0, 1, {}), ("m", 0, 1, {}), ("d", 0, 2, {"grace": ["N"]}), ("d", 0, 1, {}),
           ("P", 0, 2, {}), ("G", 0, 1, {}), ("m", 0, 1, {}), ("r", 0, 2, {"grace": ["G"]}),
           ("S", 0, 2, {})])
    c.add("gamak run — each eighth swings to the next raga swara and back",
          [(sw, 0, 0.5, {"gamak_st": st}) for sw, st in
           (("S", 1), ("r", 3), ("G", 1), ("m", 2), ("P", 1), ("d", 3))] + [("N", 0, 2, {})])
    return c


def _bageshree() -> _Cues:
    c = _Cues()
    c.add("Ma -> Ga, the SLOW reverse bend (alap meend)",
          [("m", 0, 4, {"meend_swara": "g", "meend_style": "slow"}), ("R", 0, 1, {}),
           ("S", 0, 2, {})])
    c.add("Ma -> Ga, the QUICK gat pull, for comparison",
          [("m", 0, 4, {"meend_swara": "g"}), ("R", 0, 1, {}), ("S", 0, 2, {})])
    c.add("(m)g — a Ma kan, then ga swaying UP toward ma (50% of the way)",
          [("D", 0, 1, {}), ("m", 0, 1, {}), ("g", 0, 5, {"grace": ["m"], "andolan": True,
                                                          "andolan_st": 1.0}), ("R", 0, 1, {}),
           ("S", 0, 2, {})])
    c.add("Dha -> Ma, a slow meend resting on Pa on the way down",
          [("n", 0, 1, {}), ("D", 0, 5, {"meend_swara": "m", "meend_style": "slow"}),
           ("g", 0, 2, {})])
    return c


def _composition(raga: str, cues: _Cues) -> Composition:
    sitar, drone = VOICES["sitar"], VOICES["drone"]
    end = cues.t
    lead = Layer(role="lead", instrument=sitar.instrument, program=sitar.program,
                 channel=sitar.channel, pan=sitar.pan, notes=cues.notes)
    tanpura = Layer(role="drone", instrument=drone.instrument, program=drone.program,
                    channel=drone.channel, pan=drone.pan,
                    notes=[Note(swara="S", oct=-1, start=0.0, dur=end, vel=50),
                           Note(swara="P" if raga == "bhairav" else "m", oct=-2, start=0.0,
                                dur=end, vel=42)])
    return Composition(raga=raga, sa=_SA, bpm=_BPM,
                       tala={"name": "teentaal", "beats_per_bar": 16.0}, layers=[tanpura, lead])


def main() -> int:
    from crew.generators import render_composition

    root = Path(__file__).resolve().parents[1]
    soundfont = root / "soundfonts" / "GeneralUser-GS.sf2"
    if not (shutil.which("fluidsynth") and soundfont.exists()):
        print("-> render skipped (fluidsynth or soundfont not found)")
        return 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for raga, cues in (("bhairav", _bhairav()), ("bageshree", _bageshree())):
        comp = _composition(raga, cues)
        wav = render_composition(comp, out_dir=root / "out", name=f"ornaments_{raga}_{stamp}",
                                 soundfont=soundfont)
        print(f"\n-> {wav.relative_to(root)}")
        for seconds, label in cues.sheet:
            print(f"   {int(seconds // 60)}:{seconds % 60:04.1f}  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
