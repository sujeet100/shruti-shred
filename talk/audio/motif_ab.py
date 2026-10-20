"""
Does a composer that DEFINES ITS OWN MOTIF write a different gat head? (Sujit, 2026-10-18)

The cross-model debate's seven seeds all chose the same head: each seed picked its cell from the
raga's facts (Darbari's pakad, avaroha and chalan close on g m R S) and the head call was told to
derive the mukhada from it and play the seed's stroke line. This test holds the chart fixed — the
single-call seed Sujit ranked first (Z, out/seed_ab_20261018_215920) — and composes the gat head
eight times, interleaved:

  * GUIDED x4 — the seed's cell, stroke line and riff, as today, plus "define your motif first";
  * FREE   x4 — no motif, no cell, no stroke line, no riff notes (`crew/head_brief.py`); the sam
                swara stays and the idea keeps only its mood. Each head defines its own motif and
                its own stroke pattern; the Masitkhani grid stays as the form's knowledge.

Each head is auditioned through the real band (free) under a shuffled letter; the key and every
head's motif, strokes and notes go to separate files. Diversity WITHIN each arm is measured
octave-free (seed_measures). LIVE: 8 head calls (+ any repair), Gemini at the Composer's tier.

    uv run python talk/audio/motif_ab.py            ->  out/motif_ab_<stamp>/{A..H}.wav, key.json, record.json
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SOURCE: Final = ROOT / "out" / "seed_ab_20261018_215920" / "record.json"
PER_ARM: Final = 4
ARMS: Final = ("guided", "free")
# Seed Z's idea, as the FREE arm reads it: its mood, without the phrase it named ("and majestic
# d n P descent") — a named phrase is a motif handed down.
FREE_IDEA: Final = "Masitkhani vilambit gat anchored on Sa, with andolan on komal ga"


def _seeds():
    from crew.contracts import CompositionBrief, SongSeed
    record = json.loads(SOURCE.read_text())[0]
    seed = SongSeed.model_validate(record["arms"]["single"]["chosen"])
    brief = CompositionBrief.model_validate(record["brief"])
    free = seed.model_copy(update={"head": seed.head.model_copy(update={"idea": FREE_IDEA})})
    return brief, {"guided": seed, "free": free}


def _head(seed, brief, arm: str):
    """One gat head composed under `arm`'s brief (one retry on a provider blip)."""
    from crew.head_brief import head_brief
    from crew.seed_debate_crew import llm_head, with_retry
    with head_brief(arm):
        return with_retry(llm_head)(seed, brief)


def _diversity(heads) -> dict:
    from crew.seed_measures import _hook_bols, _hook_line, _hook_rhythm, _similarity

    class _Seed:                                   # the measures read only .hook / .head
        head = None

        def __init__(self, hook):
            self.hook = hook
    seeds = [_Seed(h) for h in heads]
    pairs = [(a, b) for i, a in enumerate(seeds) for b in seeds[i + 1:]]
    mean = lambda part: round(sum(_similarity(part(a), part(b)) for a, b in pairs) / len(pairs), 2)  # noqa: E731
    return {"swaras": mean(_hook_line), "rhythm": mean(_hook_rhythm), "bols": mean(_hook_bols),
            "note": "mean pairwise similarity, 1.0 = identical (swaras octave-free)"}


def main() -> Path:
    from crew.audition import render_audition
    from crew.config import load_env
    from crew.flow import _SOUNDFONT
    from crew.tracing import traced
    load_env()
    brief, seeds = _seeds()
    out = ROOT / "out" / f"motif_ab_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True)
    order = [arm for _ in range(PER_ARM) for arm in ARMS]          # interleaved: g f g f ...
    labels = random.SystemRandom().sample("ABCDEFGH", len(order))
    key, record, heads = {}, [], {arm: [] for arm in ARMS}
    with traced("motif experiment"):
        for label, arm in zip(labels, order):
            head = _head(seeds[arm], brief, arm)
            heads[arm].append(head)
            render_audition(seeds[arm].model_copy(update={"hook": head}), brief, out_dir=out, name=label,
                            soundfont=_SOUNDFONT)
            key[label] = arm
            plan = head.phrase_plan
            record.append({"label": label, "arm": arm, "motif": plan.seed, "stroke_line": plan.stroke_line,
                           "contour": plan.contour, "notes": [n.model_dump(exclude_none=True) for n in head.notes]})
            (out / "key.json").write_text(json.dumps(dict(sorted(key.items())), indent=1))
            (out / "record.json").write_text(json.dumps(record, indent=1))
    (out / "diversity.json").write_text(json.dumps({arm: _diversity(h) for arm, h in heads.items()}, indent=1))
    return out


if __name__ == "__main__":
    print(main())
