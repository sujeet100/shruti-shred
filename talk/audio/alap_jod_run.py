"""
The alap, before and after ALAP-THEN-JOD (2026-10-19 evening; ALAP_RESEARCH.md).

One live intro call: the composer writes a new alap for fusion_20261019_184632_pipeline_darbari
against that song's own head (the chart's seed hook — no gat call). Both alaps are rendered sitar +
tanpura only, so the ear compares the line and nothing else, and both are measured by the
Producer's alap report:

    A = the alap the song shipped with (the whole-alap jod pulse: 31% held)
    B = the new alap (unmetred, holds in seconds, then a short jod into the head)

    uv run python talk/audio/alap_jod_run.py   ->  out/alap_jod_<stamp>/{A.wav, B.wav, notes.md}
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SONG = ROOT / "out" / "fusion_20261019_184632_pipeline_darbari"


def _phrases(notes, end: float, bpm: float, jod: float | None) -> list[str]:
    """Each phrase as 'time: swaras[seconds] -> rests on X', split at a silence of a beat or more."""
    s = 60.0 / bpm
    notes = sorted((n for n in notes if n.start < end), key=lambda n: n.start)
    out, cur = [], []
    for i, n in enumerate(notes):
        cur.append(n)
        nxt = notes[i + 1].start if i + 1 < len(notes) else end
        if nxt - (n.start + n.dur) >= 1.0 or i == len(notes) - 1:
            tag = "JOD" if jod is not None and cur[0].start >= jod - 1e-6 else "alap"
            line = " ".join(f"{m.swara}{'' if not m.oct else m.oct}[{m.dur * s:.1f}s]" for m in cur)
            out.append(f"- {cur[0].start * s:5.1f} s ({tag}): {line} -> rests on **{cur[-1].swara}**")
            cur = []
    return out


def main() -> Path:
    from crew.alap_report import render_alap
    from crew.config import load_env
    from crew.contracts import Arrangement, Composition
    from crew.flow import _SOUNDFONT
    from crew.generators import render_composition, section_spans
    from crew.lead import compose_seeded_lead, intro_jod_window
    from crew.tracing import traced
    load_env()
    out = ROOT / "out" / f"alap_jod_{time.strftime('%Y%m%d_%H%M%S')}"
    arr = Arrangement.model_validate_json(SONG.with_name(SONG.name + ".arrangement.json").read_text())
    comp = Composition.model_validate_json(SONG.with_suffix(".json").read_text())
    chart = arr.model_copy(update={"sections": arr.sections[:2]})          # the alap, then the head
    span = section_spans(chart)[0]
    with traced("alap then jod"):
        layers, events = compose_seeded_lead(chart)
    new_lead = next(layer for layer in layers if layer.role == "lead")
    old_lead = next(layer for layer in comp.layers if layer.role == "lead")
    drone = next(layer for layer in comp.layers if layer.role == "drone")
    _, jod = intro_jod_window(arr, span)

    def clip(layer):
        return layer.model_copy(update={"notes": [n.model_copy(update={"dur": min(n.dur, span.end + 8 - n.start)})
                                                  for n in layer.notes if n.start < span.end]})
    for name, lead in (("A", old_lead), ("B", new_lead)):
        render_composition(comp.model_copy(update={"layers": [clip(drone), clip(lead)]}), out_dir=out, name=name,
                           soundfont=_SOUNDFONT)
    head = [ly for ly in comp.layers if ly.role != "lead"]
    report_b = render_alap(comp.model_copy(update={"layers": head + [new_lead]}), arr)
    craft = [c for e in events for c in (e.data or {}).get("craft_notes", [])]
    lines = ["# Alap then jod — A/B", "",
             f"jod enters at {jod * 60 / arr.bpm:.1f} s" if jod is not None else "no jod",
             "", "## A — shipped (whole-alap pulse)", render_alap(comp, arr), *_phrases(old_lead.notes, span.end, arr.bpm, None),
             "", "## B — alap, then jod", report_b, *_phrases(new_lead.notes, span.end, arr.bpm, jod),
             "", "## B's craft notes", *[f"- {c}" for c in craft],
             "", "## events", *[f"- {e.type}: {e.text[:200]}" for e in events]]
    (out / "notes.md").write_text("\n".join(lines) + "\n")
    return out


if __name__ == "__main__":
    print(main())
