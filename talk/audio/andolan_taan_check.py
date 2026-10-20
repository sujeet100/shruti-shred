"""Two free listening checks on fusion_20261020_144218_darbari_symph (no LLM; Sujit, 2026-10-20).

1. THE ALAP'S SWAYS — "the bends in the alap still seem out of tune". The pitch audit shows the render
   follows the MIDI (median 7 cents), so the question is the instruction. The alap, sitar + tanpura only:
     A_shipped    — the 50-cent sway below each held ga/dha, with its kan flick first (as shipped)
     B_sway25     — a 25-cent sway (the one measured Darbari dha span), kan kept
     C_sway25_nokan — a 25-cent sway, no kan on the swaying notes

2. THE TAAN'S SPEED — "chaugun at 64 bpm sounds like dugun". The shipped taan's own notes, sitar +
   tanpura only, at the pulse it played and at twice that pulse (does the sitar sample still speak?):
     D_taan_4_per_beat — as shipped: 4 per beat = ~4.3 notes/s
     E_taan_8_per_beat — the same notes, 8 per beat = ~8.5 notes/s

    uv run python talk/audio/andolan_taan_check.py   ->  out/andolan_taan_<stamp>/{A..E}.wav
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

SONG = ROOT / "out" / "fusion_20261020_144218_darbari_symph"
SHALLOW = -0.25                       # semitones: the 25-cent sway


def _window(layer, start: float, end: float, shift: float = 0.0, scale: float = 1.0):
    """The layer's notes in [start, end), moved to begin at 0 and (for the taan) time-scaled."""
    notes = [n.model_copy(update={"start": round((n.start - start) * scale + shift, 4),
                                  "dur": round(min(n.dur, end - n.start) * scale, 4)})
             for n in layer.notes if start <= n.start < end]
    return layer.model_copy(update={"notes": notes})


def _sways(lead, *, depth: float | None, kan: bool):
    def edit(n):
        if not n.andolan:
            return n
        update = {"andolan_st": depth} if depth is not None else {}
        if not kan:
            update["grace"] = None
        return n.model_copy(update=update)
    return lead.model_copy(update={"notes": [edit(n) for n in lead.notes]})


def main() -> Path:
    from crew.contracts import Arrangement, Composition
    from crew.flow import _SOUNDFONT
    from crew.generators import render_composition, section_spans
    arr = Arrangement.model_validate_json(SONG.with_name(SONG.name + ".arrangement.json").read_text())
    comp = Composition.model_validate_json(SONG.with_suffix(".json").read_text())
    out = ROOT / "out" / f"andolan_taan_{time.strftime('%Y%m%d_%H%M%S')}"
    lead = next(ly for ly in comp.layers if ly.role == "lead")
    drone = next(ly for ly in comp.layers if ly.role == "drone")
    spans = section_spans(arr)
    alap = spans[0]
    tail = 6.0                                                   # let the closing Sa ring
    for name, version in (("A_shipped", lead), ("B_sway25", _sways(lead, depth=SHALLOW, kan=True)),
                          ("C_sway25_nokan", _sways(lead, depth=SHALLOW, kan=False))):
        layers = [_window(drone, 0, alap.end + tail), _window(version, alap.start, alap.end)]
        render_composition(comp.model_copy(update={"layers": layers}), out_dir=out, name=name, soundfont=_SOUNDFONT)
    taan = next(s for s in spans if s.section.form_role == "taan_long")
    for name, scale in (("D_taan_4_per_beat", 1.0), ("E_taan_8_per_beat", 0.5)):
        length = (taan.end - taan.start) * scale
        layers = [_window(drone, 0, length + 6, 0), _window(lead, taan.start, taan.end, shift=1.0, scale=scale)]
        render_composition(comp.model_copy(update={"layers": layers}), out_dir=out, name=name, soundfont=_SOUNDFONT)
    return out


if __name__ == "__main__":
    print(main())
