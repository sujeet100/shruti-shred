"""Free A/B: is the system's riff thin because of its VOICING? (no model call)

Takes the opening song's composition and changes ONE thing — the rhythm guitar's voicing.
Every riff stroke becomes root + dyad + octave: a power-chord fifth on roots whose fifth is in
the raga, a fourth on roots whose fifth is not (both perfect consonances, both distortion-clean),
an octave alone if neither is legal. Rhythm, durations, techniques, velocities and every other
part stay exactly as the system wrote them. Both versions render through the same path with the
raga validator ON, so the re-voiced riff is proven legal.

    uv run python talk/audio/revoice.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_clips as mc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "out" / "fusion_20261011_194039.json"
AB_WINDOW = (64.0, 96.0)     # the hook's return "with full heavy drive": two cycles of the full band
SWARA_AT = {v: k for k, v in mc.SWARAS.items()}


def dyad_for(root: str, allowed: set[str]) -> list[str]:
    """The heaviest legal voicing above `root`: fifth, else fourth, else octave alone."""
    for interval in (7, 5):
        tone = SWARA_AT[(mc.SWARAS[root] + interval) % 12]
        if tone in allowed:
            return [tone, root]
    return [root]


def revoice(comp: dict) -> tuple[dict, dict]:
    allowed = set(mc.RAGAS[comp["raga"]]["allowed"])
    out = json.loads(json.dumps(comp))
    used: Counter = Counter()
    for layer in out["layers"]:
        if layer["role"] != "rhythm":
            continue
        for n in layer["notes"]:
            n["chord"] = dyad_for(n["swara"], allowed)
            used[(n["swara"], "fifth" if len(n["chord"]) == 2 and (mc.SWARAS[n["chord"][0]] - mc.SWARAS[n["swara"]]) % 12 == 7 else
                  "fourth" if len(n["chord"]) == 2 else "octave")] += 1
    return out, dict(used)


def chord_share(comp: dict) -> float:
    notes = [n for l in comp["layers"] if l["role"] == "rhythm" for n in l["notes"]]
    return round(sum(1 for n in notes if n.get("chord")) / len(notes), 2)


def main() -> None:
    orig = json.loads(SOURCE.read_text())
    new, used = revoice(orig)
    wavs = {}
    for tag, comp in (("orig", orig), ("revoiced", new)):
        wavs[tag] = mc.render_comp(mc.Composition.model_validate(comp), f"RV_{tag}", check_raga=True)
        mc.assemble(f"RV_{tag}_full", [(wavs[tag], 0.0, 10_000.0)], 0, fade_out=1.0)
    spb = 60.0 / orig["bpm"]
    a, b = AB_WINDOW
    _, stats = mc.assemble("RV_ab", [(wavs["orig"], a * spb, (b - a) * spb), (wavs["revoiced"], a * spb, (b - a) * spb)], 1.0, fade_out=0.4)
    mc.visuals("RV_ab")
    print(json.dumps({"chord_share": {"orig": chord_share(orig), "revoiced": chord_share(new)},
                      "voicings": {f"{r}:{k}": v for (r, k), v in sorted(used.items())},
                      "ab_window_beats": AB_WINDOW, "stats": stats}))


if __name__ == "__main__":
    main()
