"""
A no-LLM SOUND CHECK for the chikari (crew/chikari.py): a short hand-written Bageshree gat —
alap, the head stated twice, the manjha, the head's return, the climax — placed by the REAL
lead pipeline (`lead_layers_from`) and rendered twice over the tanpura:

  A — the old chikari: the head's written chikari is ONE taar Sa on the melodic sitar channel,
      and nothing else strikes the drone strings;
  B — the new chikari: written and planned strokes strummed across guruji's S S D m strings
      on their own unbent channel, ringing until the next stroke.

Sketches, not a composition: the swaras are idiomatic Bageshree, the rhythm is illustrative.

Run: `uv run python -m crew.chikari_demo` -> out/chikari_<timestamp>_{A_old,B_new}.wav
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Final

from crew.chikari import chikari_layer, without_chikari
from crew.contracts import (
    Arrangement,
    ArrangementDraft,
    Composition,
    CompositionBrief,
    Layer,
    LeadNote,
    LeadPhrase,
    PhrasePlan,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import drone_layer, section_spans

_RAGA: Final = "bageshree"
_BPM: Final = 72
_PLAN: Final = PhrasePlan(seed=["m", "D"], contour="arch", transformations=["repeat"],
                          climax_and_sam="lands on Sa at the sam")

Cell = list[tuple[str, int, float, str | None]]   # (swara or "-" for a rest, oct, beats, bol)

# The head: its stroke line leaves matras 3-4, 8 and 13 to ring — the chikari's matras.
_HEAD_STROKES: Final = ["da", "ra", "da", "-", "-", "da", "ra", "da", "-", "da", "ra", "da",
                        "da", "-", "da", "chikari"]
_HEAD: Final[Cell] = [("S", 0, 1, "da"), ("g", 0, 1, "ra"), ("m", 0, 3, "da"),
                      ("D", 0, 1, "da"), ("n", 0, 1, "ra"), ("D", 0, 2, "da"),
                      ("m", 0, 1, "da"), ("g", 0, 1, "ra"), ("R", 0, 1, "da"),
                      ("S", 0, 2, "da"), ("S", 0, 1, "da"), ("S", 0, 1, "chikari")]
_ALAP: Final[Cell] = [("S", 0, 2, None), ("n", -1, 1, None), ("D", -1, 2, None),
                      ("-", 0, 4, None), ("m", -1, 1, None), ("D", -1, 1, None),
                      ("n", -1, 1, None), ("S", 0, 2, None), ("-", 0, 3, None),
                      ("g", 0, 2, None), ("m", 0, 2, None), ("D", 0, 1, None),
                      ("g", 0, 2, None), ("R", 0, 1, None), ("S", 0, 3, None)]
_MANJHA: Final[Cell] = [("D", -1, 2, None), ("n", -1, 2, None), ("D", -1, 1, None),
                        ("m", -1, 1, None), ("D", -1, 2, None), ("S", 0, 3, None)]
_TAAN: Final[Cell] = ([(sw, 0, 0.5, None) for sw in "SgmDnS"] + [("S", 1, 2, None)]
                      + [(sw, 1, 0.5, None) for sw in "SnD"] + [("m", 0, 0.5, None)]
                      + [("D", 0, 2, None), ("-", 0, 1, None)]
                      + [(sw, 0, 0.5, None) for sw in "mgRS"] + [("S", 0, 4, None)])


def _phrase(cell: Cell, stroke_line: list[str] | None = None) -> LeadPhrase:
    plan = _PLAN.model_copy(update={"stroke_line": stroke_line})
    return LeadPhrase(phrase_plan=plan, notes=[
        LeadNote(swara="S", dur=d, rest=True) if sw == "-" else
        LeadNote(swara=sw, oct=o, dur=d, bol=bol, vel=90) for sw, o, d, bol in cell])


def _arrangement() -> Arrangement:
    def section(kind: SectionKind, bars: int, role: str) -> Section:
        return Section(kind=kind, bars=bars, layers=["lead", "drone"], foreground="lead",
                       form_role=role)
    draft = ArrangementDraft(raga=_RAGA, subgenre="doom", tala="teentaal", bpm=_BPM, motif=["m"],
                             sections=[section(SectionKind.ALAAP, 2, "intro"),
                                       section(SectionKind.MELODY, 2, "mukhada"),
                                       section(SectionKind.MELODY, 1, "manjha"),
                                       section(SectionKind.MELODY, 1, "mukhada"),
                                       section(SectionKind.TAAN, 1, "taan_long")])
    return build_arrangement(draft, CompositionBrief())


def _lead(arr: Arrangement) -> list[Layer]:
    from crew.lead import lead_layers_from   # lazy: crew.lead pulls in crewai
    head = _phrase(_HEAD, _HEAD_STROKES)
    return lead_layers_from({0: _phrase(_ALAP), 1: head, 2: _phrase(_MANJHA), 3: head,
                             4: _phrase(_TAAN)}, arr)


def _compositions(arr: Arrangement) -> dict[str, Composition]:
    """A (the old single-note chikari on the melody channel) and B (the chikari layer)."""
    lead = _lead(arr)
    bed = [drone_layer(arr)]
    chikari = chikari_layer(arr, lead)
    new = [*without_chikari(lead), *([chikari] if chikari is not None else [])]

    def comp(layers: list[Layer]) -> Composition:
        return Composition(raga=arr.raga, sa=arr.sa, bpm=arr.bpm,
                           tala={"name": arr.tala, "beats_per_bar": arr.beats_per_bar},
                           layers=[*bed, *layers])
    return {"A_old": comp(lead), "B_new": comp(new)}


def main() -> int:
    from crew.generators import render_composition

    root = Path(__file__).resolve().parents[1]
    soundfont = root / "soundfonts" / "GeneralUser-GS.sf2"
    if not (shutil.which("fluidsynth") and soundfont.exists()):
        print("-> render skipped (fluidsynth or soundfont not found)")
        return 1
    arr = _arrangement()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for label, comp in _compositions(arr).items():
        wav = render_composition(comp, out_dir=root / "out", name=f"chikari_{stamp}_{label}",
                                 soundfont=soundfont)
        print(f"-> {wav.relative_to(root)}")
    for span in section_spans(arr):
        seconds = span.start * 60.0 / arr.bpm
        print(f"   {int(seconds // 60)}:{seconds % 60:04.1f}  {span.section.form_role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
