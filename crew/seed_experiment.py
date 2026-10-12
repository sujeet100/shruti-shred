"""
Run the SEED DEBATE experiment (`crew/seed_debate.py`) and write blind auditions for Sujit's ear.

For each prompt: interpret it once, run the three arms (single / best-of-4 / debate) on the same
brief, and render each arm's winning seed as an audition (`crew/audition.py`). Files are labelled
by a shuffled letter per prompt; the key, every seed and the debate's events go to separate JSON
files, so the listening is blind and the run is replayable. Traced like every live run.

    uv run python -m crew.seed_experiment "prompt one" "prompt two" ...

LIVE: about 1 + 1 + 6 + 6 = 14 calls per prompt. Ask Sujit before running (CLAUDE.md cost rules).
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from typing import Final

from crew.contracts import CompositionBrief
from crew.seed_debate import ArmResult, best_of, debate, single_seed
from crew.seed_measures import diversity

_ROOT: Final = Path(__file__).resolve().parents[1]
_OUT: Final = _ROOT / "out"
_LABELS: Final = "XYZ"


def _arms(brief: CompositionBrief) -> list[ArmResult]:
    from crew.seed_debate_crew import llm_seed, llm_select, llm_turn
    return [single_seed(brief, seed_fn=llm_seed),
            best_of(brief, seed_fn=llm_seed, select_fn=llm_select),
            debate(brief, seed_fn=llm_seed, turn_fn=llm_turn, select_fn=llm_select)]


def _run_prompt(index: int, query: str, out_dir: Path, rng: random.Random) -> dict:
    """One prompt: brief, three arms, three blind auditions. Returns its key + record."""
    from crew.audition import render_audition
    from crew.flow import _SOUNDFONT
    from crew.interpreter import interpret
    brief, _ = interpret(query)
    results = _arms(brief)
    labels = rng.sample(_LABELS, len(results))
    record: dict = {"query": query, "brief": brief.model_dump(), "key": {}, "arms": {}}
    for label, result in zip(labels, results):
        name = f"p{index}_{label}"
        render_audition(result.seed, brief, out_dir=out_dir, name=name, soundfont=_SOUNDFONT)
        record["key"][name] = result.arm
        record["arms"][result.arm] = {
            "calls": result.calls, "chosen": result.seed.model_dump(),
            "draft_diversity": diversity(result.drafts),
            "drafts": [s.model_dump() for s in result.drafts],
            "candidates": [s.model_dump() for s in result.candidates],
            "events": [e.model_dump(mode="json") for e in result.events]}
    return record


def run(queries: list[str]) -> Path:
    """Run every prompt; return the experiment directory (auditions + key.json + record.json)."""
    from crew.config import load_env
    from crew.tracing import traced
    load_env()
    out_dir = _OUT / f"seed_ab_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=False)     # never overwrite an earlier experiment
    rng = random.SystemRandom()
    records = []
    with traced("seed debate experiment"):
        for i, query in enumerate(queries, start=1):
            records.append(_run_prompt(i, query, out_dir, rng))
    (out_dir / "key.json").write_text(json.dumps({k: v for r in records for k, v in r["key"].items()},
                                                 indent=1))
    (out_dir / "record.json").write_text(json.dumps(records, indent=1))
    return out_dir


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    out_dir = run(argv)
    print(f"auditions in {out_dir} — listen blind; the key is in key.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
