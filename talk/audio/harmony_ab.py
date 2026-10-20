"""Free A/B (no LLM): STRICT RAGA vs FUSION HARMONY on the same single-call riff.

In every single-call song the ONLY out-of-raga notes are rhythm-guitar chord tones — the
conventional fifth over a root whose fifth the raga forbids (Bhairav: G over komal dha, F# over
Pa; Todi: F# over Pa, D over komal ga). Sitar, bass and every guitar root are legal. So the
harmony policy can be heard in isolation:

  fusion — the song as written: conventional fifths, a few of them outside the raga.
  strict — the same riff with each out-of-raga chord tone replaced by the strict voicing
           (`riff_voicing.power_voicing`: the fourth, else the octave alone).

The right take is derived from the treated riff with `double_track`, as the product does.

    uv run python talk/audio/harmony_ab.py [STEM ...]     # default: FA_src TA_src
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from crew.contracts import Composition, Layer, Note  # noqa: E402
from crew.generators import double_track, render_composition  # noqa: E402
from crew.riff_voicing import power_voicing  # noqa: E402
from raga import RAGAS, SWARAS  # noqa: E402

_BY_SEMI = {v: k for k, v in SWARAS.items()}


def _pitch(n: Note) -> int:
    return SWARAS[n.swara] + 12 * n.oct


def _groups(notes: list[Note]) -> list[list[Note]]:
    out: list[list[Note]] = []
    for n in sorted(notes, key=lambda n: n.start):
        if out and abs(n.start - out[-1][0].start) <= 0.06:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def _at(root: Note, semis: int) -> Note:
    p = _pitch(root) + semis
    sw = _BY_SEMI[p % 12]
    return root.model_copy(update={"swara": sw, "oct": (p - SWARAS[sw]) // 12})


def strict(layer: Layer, raga: str, log: dict) -> Layer:
    """Each stroke with an out-of-raga chord tone: drop those tones, add the strict dyad."""
    allowed = set(RAGAS[raga]["allowed"])
    out: list[Note] = []
    for grp in _groups(layer.notes):
        bad = [n for n in grp if n.swara not in allowed]
        if not bad:
            out += grp
            continue
        root = min(grp, key=_pitch)
        keep = [n for n in grp if n.swara in allowed]
        chord = power_voicing(root.swara, root.dur, raga)
        if len(chord) == 2:
            semis = (SWARAS[chord[0]] - SWARAS[root.swara]) % 12
            keep.append(_at(root, semis))
            log["fourth"] = log.get("fourth", 0) + 1
        else:
            log["octave"] = log.get("octave", 0) + 1
        out += keep
    return layer.model_copy(update={"notes": sorted(out, key=lambda n: n.start)})


def main() -> None:
    stems = sys.argv[1:] or ["FA_src", "TA_src"]
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    for stem in stems:
        src = Composition.model_validate_json((ROOT / f"talk/audio/build/{stem}.json").read_text())
        takes = [i for i, l in enumerate(src.layers) if l.role == "rhythm"]
        report: dict = {"song": stem, "raga": src.raga}
        for mode in ("fusion", "strict"):
            log: dict = {}
            layers = list(src.layers)
            if mode == "strict":
                layers[takes[0]] = strict(src.layers[takes[0]], src.raga, log)
                for i in takes[1:]:
                    layers[i] = double_track(layers[takes[0]]).model_copy(update={
                        k: getattr(src.layers[i], k) for k in ("program", "channel", "pan",
                                                              "detune_cents")
                        if getattr(src.layers[i], k, None) is not None})
            comp = src.model_copy(update={"layers": layers})
            wav = render_composition(comp, out_dir=ROOT / "out", name=f"harmony_{mode}_{stem}_{stamp}",
                                     soundfont=ROOT / "soundfonts/GeneralUser-GS.sf2")
            report[mode] = {"strokes_revoiced": log, "wav": wav.name}
        print(json.dumps(report))


if __name__ == "__main__":
    main()
