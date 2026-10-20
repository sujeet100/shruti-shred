"""Free A/B (no LLM): song C's climax with the guitar on the PEDAL variant instead of thinned.

Takes the main riff's first cycle from the mukhada (beats 16-32, the base variant), collapses
every stroke onto the cycle's ground pitch + chord (riff_family._pedal, same attacks), lays it
under the long taan (beats 96-128), and derives the right take with double_track. Only the
guitars change (the bass that followed the thinned riff is left as rendered).

    uv run python talk/audio/climax_ab.py
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from crew.contracts import Composition  # noqa: E402
from crew.generators import double_track, render_composition  # noqa: E402

SRC = ROOT / "out/fusion_20261011_194039.json"
CYCLE, BASE_AT, TAAN = 16.0, 16.0, (96.0, 128.0)
MOVES = {"slide", "long_slide", "pick_scrape", "bend", "hammer_on", "pull_off"}

comp = Composition.model_validate_json(SRC.read_text())
takes = [i for i, l in enumerate(comp.layers) if l.role == "rhythm"]
left = comp.layers[takes[0]]
cycle = [n for n in left.notes if BASE_AT <= n.start < BASE_AT + CYCLE]
ground = Counter((n.swara, n.oct) for n in cycle).most_common(1)[0][0]
anchor = next(n for n in cycle if (n.swara, n.oct) == ground)
pedal = [n.model_copy(update={"swara": anchor.swara, "oct": anchor.oct, "chord": anchor.chord,
                              "technique": None if n.technique in MOVES else n.technique})
         for n in cycle]
under_taan = [n.model_copy(update={"start": n.start - BASE_AT + bar})
              for bar in (TAAN[0], TAAN[0] + CYCLE) for n in pedal]
kept = [n for n in left.notes if not TAAN[0] <= n.start < TAAN[1]]
new_left = left.model_copy(update={"notes": sorted(kept + under_taan, key=lambda n: n.start)})
layers = list(comp.layers)
layers[takes[0]] = new_left
for i in takes[1:]:
    layers[i] = double_track(new_left).model_copy(update={
        k: getattr(comp.layers[i], k) for k in ("program", "channel", "pan", "detune_cents")
        if getattr(comp.layers[i], k, None) is not None})
before = sum(1 for n in left.notes if TAAN[0] <= n.start < TAAN[1])
name = f"climax_pedal_194039_{datetime.now():%Y%m%d_%H%M%S}"
wav = render_composition(comp.model_copy(update={"layers": layers}), out_dir=ROOT / "out",
                         name=name, soundfont=ROOT / "soundfonts/GeneralUser-GS.sf2")
print(f"climax guitar notes: {before} -> {len(under_taan)}  ground={ground}  {wav.name}")
