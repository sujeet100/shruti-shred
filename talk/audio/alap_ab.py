"""
The alap, before and after CALL AND ANSWER ON A JOD'S PULSE (Sujit, 2026-10-19).

One live call: the composer writes a new alap for fusion_20261019_083259_fresh, against that song's
own head (the chart's seed hook — no gat call, no other section). Both alaps are rendered the same
way, sitar and tanpura only, so the ear compares the line and nothing else:

    A = the alap the song shipped with (the July brief: tension held, a deleted jod string relied on)
    B = the new alap (calls pause off Sa, answers come home, phrases on the vibhag, long notes on the beat)

    uv run python talk/audio/alap_ab.py   ->  out/alap_ab_<stamp>/{A.wav, B.wav, phrases.md}
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SONG = ROOT / "out" / "fusion_20261019_083259_fresh"


def _phrases(notes, end: float) -> list[str]:
    """Each phrase as 'beat: swaras -> rests on X', split at a silence of half a beat or more."""
    notes = sorted((n for n in notes if n.start < end), key=lambda n: n.start)
    out, cur = [], []
    for i, n in enumerate(notes):
        cur.append(n)
        nxt = notes[i + 1].start if i + 1 < len(notes) else end
        if nxt - (n.start + n.dur) >= 0.5 or i == len(notes) - 1:
            off = sum(1 for m in cur if m.dur >= 1 and m.start % 1)
            line = " ".join(f"{m.swara}{'' if not m.oct else m.oct}[{m.dur:g}]" for m in cur)
            out.append(f"- beat {cur[0].start:g} (vibhag beat {cur[0].start % 4:g}): {line} -> rests on "
                       f"**{cur[-1].swara}**" + (f" ({off} long note(s) off the beat)" if off else ""))
            cur = []
    return out


def main() -> Path:
    from crew.config import load_env
    from crew.contracts import Arrangement, Composition
    from crew.flow import _SOUNDFONT
    from crew.generators import render_composition, section_spans
    from crew.lead import compose_seeded_lead
    from crew.tracing import traced
    load_env()
    out = ROOT / "out" / f"alap_ab_{time.strftime('%Y%m%d_%H%M%S')}"
    arr = Arrangement.model_validate_json(SONG.with_name(SONG.name + ".arrangement.json").read_text())
    comp = Composition.model_validate_json(SONG.with_suffix(".json").read_text())
    chart = arr.model_copy(update={"sections": arr.sections[:2]})          # the alap, then the head
    end = section_spans(chart)[0].end
    with traced("alap call-and-answer"):
        layers, _ = compose_seeded_lead(chart)
    new_lead = next(layer for layer in layers if layer.role == "lead")
    old_lead = next(layer for layer in comp.layers if layer.role == "lead")
    drone = next(layer for layer in comp.layers if layer.role == "drone")

    def clip(layer):
        return layer.model_copy(update={"notes": [n.model_copy(update={"dur": min(n.dur, end + 8 - n.start)})
                                                  for n in layer.notes if n.start < end]})
    for name, lead in (("A", old_lead), ("B", new_lead)):
        render_composition(comp.model_copy(update={"layers": [clip(drone), clip(lead)]}), out_dir=out, name=name,
                           soundfont=_SOUNDFONT)
    (out / "phrases.md").write_text("\n".join(["# Alap A/B", "", "## A — shipped (July brief)", *_phrases(old_lead.notes, end),
                                               "", "## B — call and answer on the pulse", *_phrases(new_lead.notes, end)]) + "\n")
    return out


if __name__ == "__main__":
    print(main())
