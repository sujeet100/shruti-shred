"""
A no-LLM SOUND CHECK for the ornament campaign (2026-10-11): hand-written sitar lines over the
drone, rendered through the same soundfonts and routing as a live piece, so the ear can judge
the gestures before any live run. Two files, each with a printed cue sheet:

  Bhairav   — andolan depth A/B on komal re and komal dha (30 / 50 / 70 cents, all below),
              unstruck kan in the pakad, and a gamak run;
  Bageshree — Sujit's Ma->Ga: a slow reverse bend vs the quick gat pull, ga swaying UP toward
              ma after a Ma kan, and a slow meend D->m that rests on Pa on the way down.
  Darbari   — the ornament-audit set (2026-10-12), at fusion_20261012_213455's own Sa (D) and
              tempo (120): komal Ga andolan after a Re kan, komal Dha andolan in the mandra, a
              Ga<>Ma gamak, the Ma->Ga meend slow and quick, and a whole phrase with the measured
              Ga loops — the gestures, gamak strokes and 22-shruti intonation stamped by the
              pipeline's own expression — and a 22-SHRUTI A/B (Ga at equal temperament vs its
              shruti, Dayavanti 32/27).

Run: `uv run python -m crew.ornament_demo [raga ...]` -> out/ornaments_<raga>_<timestamp>.wav
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
_DARBARI_SA: Final = 62     # D — fusion_20261012_213455's own key...
_DARBARI_BPM: Final = 120   # ...and tempo


@dataclass
class _Cues:
    """Lays phrases end to end with a gap, remembering where each cue starts."""
    notes: list[Note] = field(default_factory=list)
    sheet: list[tuple[float, str]] = field(default_factory=list)
    t: float = 0.0
    bpm: int = _BPM
    sa: int = _SA

    def add(self, label: str, phrase: list[tuple[str, int, float, dict]]) -> None:
        self.sheet.append((self.t * 60 / self.bpm, label))
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


def _darbari() -> _Cues:
    from crew.expression import with_gamak_cells, with_gestures, with_intonation
    c = _Cues(bpm=_DARBARI_BPM, sa=_DARBARI_SA)
    andolan = {"andolan": True, "andolan_st": -0.5}       # Darbari's komal Ga/Dha sway below
    c.add("komal Ga andolan, approached by a Re kan (R (R)g~ R S)",
          [("R", 0, 1, {}), ("g", 0, 3, {"grace": ["R"], **andolan}), ("R", 0, 1, {}),
           ("S", 0, 2, {})])
    c.add("komal Dha andolan in the mandra (n (n)d~ n P)",
          [("n", -1, 1, {}), ("d", -1, 3, {"grace": ["n"], **andolan}), ("n", -1, 1, {}),
           ("P", -1, 2, {})])
    c.add("gamak: Ga swung with Ma, re-struck on the stroke grid",
          [("S", 0, 1, {}), ("g", 0, 2, {"gamak_with": "m"}), ("R", 0, 1, {}), ("S", 0, 2, {})])
    c.add("meend: Ma down to Ga, slow (alap)",
          [("m", 0, 3, {"meend_swara": "g", "meend_style": "slow"}), ("R", 0, 1, {}),
           ("S", 0, 2, {})])
    c.add("meend: Ma down to Ga, quick (gat)",
          [("m", 0, 2, {"meend_swara": "g"}), ("R", 0, 1, {}), ("S", 0, 2, {})])
    c.add("a phrase: S R g(loop to Ma) m R S, n (n)d~ n P, m P (P)d~ n S",
          [("S", 0, 1, {}), ("R", 0, 1, {}), ("g", 0, 1, {}), ("m", 0, 1, {}), ("R", 0, 1, {}),
           ("S", 0, 2, {}), ("n", -1, 1, {}), ("d", -1, 2, {"grace": ["n"], **andolan}),
           ("n", -1, 1, {}), ("P", -1, 2, {}), ("m", -1, 1, {}), ("P", -1, 1, {}),
           ("d", -1, 2, {"grace": ["P"], **andolan}), ("n", -1, 1, {}), ("S", 0, 3, {})])
    for label, cents in (("equal temperament", 0.0), ("its shruti, Dayavanti 32/27", None)):
        c.add(f"22-SHRUTI A/B: Ga held and swaying at {label} (R (R)g~ R S)",
              [("R", 0, 1, {}), ("g", 0, 4, {"grace": ["R"], "cents": cents, **andolan}),
               ("R", 0, 1, {}), ("S", 0, 2, {})])
        c.add(f"22-SHRUTI A/B: Ga held plain at {label}, against the tanpura",
              [("R", 0, 1, {}), ("g", 0, 4, {"cents": cents}), ("R", 0, 1, {}),
               ("S", 0, 2, {})])
    c.notes = with_intonation(
        with_gestures(with_gamak_cells(c.notes, "darbari", c.bpm), "darbari", c.bpm),
        "darbari", c.bpm)                                # every swara at its 22-shruti pitch
    return c


def _composition(raga: str, cues: _Cues) -> Composition:
    sitar, drone = VOICES["sitar"], VOICES["drone"]
    end = cues.t
    lead = Layer(role="lead", instrument=sitar.instrument, program=sitar.program,
                 channel=sitar.channel, pan=sitar.pan, notes=cues.notes)
    tanpura = Layer(role="drone", instrument=drone.instrument, program=drone.program,
                    channel=drone.channel, pan=drone.pan,
                    notes=[Note(swara="S", oct=-1, start=0.0, dur=end, vel=50),
                           Note(swara="m" if raga == "bageshree" else "P", oct=-2, start=0.0,
                                dur=end, vel=42)])
    return Composition(raga=raga, sa=cues.sa, bpm=cues.bpm,
                       tala={"name": "teentaal", "beats_per_bar": 16.0}, layers=[tanpura, lead])


_SETS: Final = {"bhairav": _bhairav, "bageshree": _bageshree, "darbari": _darbari}


def main(argv: list[str]) -> int:
    from crew.generators import render_composition

    root = Path(__file__).resolve().parents[1]
    soundfont = root / "soundfonts" / "GeneralUser-GS.sf2"
    if not (shutil.which("fluidsynth") and soundfont.exists()):
        print("-> render skipped (fluidsynth or soundfont not found)")
        return 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for raga in argv or list(_SETS):
        cues = _SETS[raga]()
        comp = _composition(raga, cues)
        wav = render_composition(comp, out_dir=root / "out", name=f"ornaments_{raga}_{stamp}",
                                 soundfont=soundfont)
        print(f"\n-> {wav.relative_to(root)}")
        for seconds, label in cues.sheet:
            print(f"   {int(seconds // 60)}:{seconds % 60:04.1f}  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
