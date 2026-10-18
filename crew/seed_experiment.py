"""
Run the SEED DEBATE experiment (`crew/seed_debate.py`) and write blind auditions for Sujit's ear.

For each prompt: interpret it once, run the three arms (single / best-of-4 / debate) on the same
brief, and render each arm's winning seed as an audition (`crew/audition.py`). Files are labelled
by a shuffled letter per prompt; the key, every seed and the debate's events go to separate JSON
files, so the listening is blind and the run is replayable. Traced like every live run.

    uv run python -m crew.seed_experiment "prompt one" "prompt two" ...
    uv run python -m crew.seed_experiment --into out/seed_ab_X --first 2 "prompt two" ...   # continue a run
    uv run python -m crew.seed_experiment --cross openai/<id>:high gemini/gemini-3.8-flash:high "prompt"
        # single (B) / B debating itself / A debating B — every Composer call on its side's model
    uv run python -m crew.seed_experiment --replay <trace>[,<trace>...] ...   # resume a run that
        # died: the traces' answers replay in order (free), the calls after the crash go live

The key and the record are written after EVERY prompt (a crash keeps what finished), and a transient
API error on the brief gets one retry.

LIVE: per prompt, 1 interpret + single 2 + best-of 10 + debate 8-10 (each gat seed adds one head
call, plus any repair) ≈ 21-23 calls. Ask Sujit before running (CLAUDE.md cost rules).
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


# The cross-model run (`--cross A B`): each debater is "<model>:<effort>", e.g.
# "openai/<id>:high" and "gemini/gemini-3.8-flash:high". Set by `main`, read by `_arms`.
_CROSS: list[tuple[str, str]] = []


def _arms(brief: CompositionBrief) -> list[ArmResult]:
    from crew.seed_debate_crew import llm_head, llm_seed, llm_select, llm_turn, with_retry
    if _CROSS:
        return _cross_arms(brief, *_CROSS)
    seed, head, select = with_retry(llm_seed), with_retry(llm_head), with_retry(llm_select)
    return [single_seed(brief, seed_fn=seed, head_fn=head),
            best_of(brief, seed_fn=seed, select_fn=select, head_fn=head),
            debate(brief, seed_fn=seed, turn_fn=with_retry(llm_turn), select_fn=select, head_fn=head)]


def _cross_arms(brief: CompositionBrief, a: tuple[str, str], b: tuple[str, str]) -> list[ArmResult]:
    """Three arms that separate mixing models from effort: one seed from B alone; B debating
    itself; A debating B. Every Composer call in each arm runs on its side's model."""
    from crew.seed_debate_crew import llm_select, llm_side, with_retry
    side_a, side_b = llm_side(*a), llm_side(*b)
    llm_select = with_retry(llm_select)
    return [single_seed(brief, seed_fn=side_b.seed_fn, head_fn=side_b.head_fn),
            debate(brief, seed_fn=side_b.seed_fn, turn_fn=side_b.turn_fn, select_fn=llm_select,
                   sides=(side_b, side_b), arm="debate-same"),
            debate(brief, seed_fn=side_a.seed_fn, turn_fn=side_a.turn_fn, select_fn=llm_select,
                   sides=(side_a, side_b), arm="debate-cross")]


def _brief(query: str, attempts: int = 2) -> CompositionBrief:
    """The brief, with one retry on a transient API failure (a read timeout killed the 2026-10-18 run)."""
    from crew.interpreter import interpret
    for attempt in range(attempts):
        try:
            return interpret(query)[0]
        except Exception:  # noqa: BLE001 — LIVE SAFETY: one retry, then let it fail loudly
            if attempt == attempts - 1:
                raise
            time.sleep(5)
    raise AssertionError("unreachable")


def _run_prompt(index: int, query: str, out_dir: Path, rng: random.Random) -> dict:
    """One prompt: brief, three arms, three blind auditions. Returns its key + record."""
    from crew.audition import render_audition
    from crew.flow import _SOUNDFONT
    brief = _brief(query)
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


def _save(out_dir: Path, records: list[dict]) -> None:
    """Merge every finished prompt into key.json and record.json (keeping what an earlier, partial
    run of this directory saved)."""
    key_path, rec_path = out_dir / "key.json", out_dir / "record.json"
    key = json.loads(key_path.read_text()) if key_path.exists() else {}
    key.update({k: v for r in records for k, v in r["key"].items()})
    key_path.write_text(json.dumps(key, indent=1))
    rec_path.write_text(json.dumps(records, indent=1))


def run(queries: list[str], *, into: Path | None = None, first: int = 1) -> Path:
    """Run every prompt; return the experiment directory (auditions + key.json + record.json).
    `into` continues an earlier directory, numbering its prompts from `first`."""
    from crew.config import load_env
    from crew.tracing import traced
    load_env()
    out_dir = into or _OUT / f"seed_ab_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=into is not None)     # a new run never overwrites an old one
    rng = random.SystemRandom()
    records: list[dict] = []
    with traced("seed debate experiment"):
        for i, query in enumerate(queries, start=first):
            records.append(_run_prompt(i, query, out_dir, rng))
            _save(out_dir, records)
    return out_dir


def main(argv: list[str]) -> int:
    into, first, replay = None, 1, None
    while argv and argv[0] in ("--into", "--first", "--cross", "--replay"):
        if argv[0] == "--cross":                      # --cross <modelA:effort> <modelB:effort>
            _CROSS[:] = [tuple(spec.rsplit(":", 1)) for spec in argv[1:3]]
            argv = argv[3:]
            continue
        flag, value, argv = argv[0], argv[1], argv[2:]
        if flag == "--into":
            into = Path(value)
        elif flag == "--replay":
            replay = value
        else:
            first = int(value)
    if not argv:
        print(__doc__)
        return 2
    if replay is None:
        out_dir = run(argv, into=into, first=first)
    else:
        from crew.trace_replay import replaying
        with replaying(*replay.split(",")):
            out_dir = run(argv, into=into, first=first)
    print(f"auditions in {out_dir} — listen blind; the key is in key.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
