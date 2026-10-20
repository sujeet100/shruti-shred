"""
One HEAD debate, every version kept (Sujit, 2026-10-18: "let 2 composers debate for 3-4 rounds and
decide the gat ... capture every version starting from the proposal to the final").

The debate gets a fair chance this time: the two composers start from DIFFERENT approaches (weight vs
rhythm), both with the free motif (no inherited cell or stroke line, `crew/head_brief.py`), and they
argue over their actual heads, not seed ideas (`crew/head_debate.py`). Same chart for both: the
single-call seed Sujit ranked first (Z, out/seed_ab_20261018_215920).

Out: every version auditioned (A0, B0, A1, B1, ...), the judge's pick between the finals (both
orders), round-by-round convergence (how alike A and B are) and drift (how far each moved from its
proposal), and a 3-clip BLIND set — proposal A, proposal B, the chosen final — with its key apart.
LIVE: 2 heads + up to 8 turns + 2 judge calls, Gemini at the Composer's tier (plus any repair).

    uv run python talk/audio/head_debate_run.py      ->  out/head_debate_<stamp>/
"""
from __future__ import annotations

import json
import random
import shutil
import sys
import time
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SOURCE: Final = ROOT / "out" / "seed_ab_20261018_215920" / "record.json"
APPROACHES: Final = {
    "A": ("Start from WEIGHT: open low (the mandra or the lower madhya), give komal Ga and komal Dha long "
          "holds where they rest so they sway, and let the head move slowly and gravely, like an alap set "
          "in time; the metal weight comes from the band underneath."),
    "B": ("Start from RHYTHM: make the head a figure the right hand drives — strokes and short notes that "
          "lock to the metal groove, a riff the sitar sings — with one held note as its breather; the "
          "raga's phrases ride the rhythm."),
}


def _inputs():
    from crew.contracts import CompositionBrief, SongSeed
    record = json.loads(SOURCE.read_text())[0]
    return SongSeed.model_validate(record["arms"]["single"]["chosen"]), CompositionBrief.model_validate(record["brief"])


def _propose(seed, brief, composer: str):
    """The composer's proposal: the free head brief, its approach as the head's idea."""
    from crew.head_brief import head_brief
    from crew.seed_debate_crew import llm_head, with_retry
    idea = f"Masitkhani vilambit gat in Darbari Kanada. {APPROACHES[composer]}"
    own = seed.model_copy(update={"head": seed.head.model_copy(update={"idea": idea})})
    with head_brief("free"):
        return with_retry(llm_head)(own, brief)


def _similarity(a, b) -> dict[str, float]:
    from crew.seed_measures import _similarity as sim
    sw = lambda h: [n.swara for n in h.notes if not n.rest]  # noqa: E731
    rh = lambda h: [n.dur for n in h.notes]  # noqa: E731
    return {"swaras": round(sim(sw(a), sw(b)), 2), "rhythm": round(sim(rh(a), rh(b)), 2)}


def main() -> Path:
    from crew.anchor import lead_tokens
    from crew.audition import head_arrangement, render_audition
    from crew.config import load_env
    from crew.flow import _SOUNDFONT
    from crew.head_debate import MAX_ROUNDS, head_debate, head_measures
    from crew.seed_debate import select
    from crew.seed_debate_crew import llm_head_turn, llm_select, with_retry
    from crew.tracing import traced
    load_env()
    seed, brief = _inputs()
    out = ROOT / "out" / f"head_debate_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True)
    arr = head_arrangement(seed, brief)
    with traced("head debate"):
        proposals = {c: _propose(seed, brief, c) for c in APPROACHES}
        versions = head_debate(proposals, llm_head_turn(arr, dict(APPROACHES), MAX_ROUNDS))
        finals = {v.composer: v for v in versions}                       # the last version of each
        candidates = [seed.model_copy(update={"hook": finals[c].head}) for c in APPROACHES]
        chosen, judge_events = select(brief, candidates, select_fn=with_retry(llm_select))
    winner = list(APPROACHES)[chosen]

    for v in versions:                                                 # every version, auditioned (free)
        render_audition(seed.model_copy(update={"hook": v.head}), brief, out_dir=out,
                        name=f"{v.composer}{v.round}", soundfont=_SOUNDFONT)
    by_round: dict[int, dict[str, object]] = {}
    for v in versions:
        by_round.setdefault(v.round, {})[v.composer] = v.head
    record = {
        "approaches": APPROACHES,
        "versions": [{"composer": v.composer, "round": v.round, "changed": v.changed, "argument": v.argument,
                      "motif": v.head.phrase_plan.seed, "stroke_line": v.head.phrase_plan.stroke_line,
                      "notes": lead_tokens(v.head.notes), "measures": head_measures(v.head)} for v in versions],
        "convergence": {r: _similarity(h["A"], h["B"]) for r, h in by_round.items() if len(h) == 2},
        "drift_from_proposal": {c: {v.round: _similarity(proposals[c], v.head) for v in versions if v.composer == c}
                                for c in APPROACHES},
        "judge": {"winner": winner, "final_round": finals[winner].round,
                  "events": [e.model_dump(mode="json") for e in judge_events]},
    }
    (out / "record.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))

    blind = {"A0": "proposal A (weight)", "B0": "proposal B (rhythm)",
             f"{winner}{finals[winner].round}": f"the judge's final ({winner}, round {finals[winner].round})"}
    labels = random.SystemRandom().sample("XYZ", len(blind))
    key = {}
    for label, (name, what) in zip(labels, blind.items()):
        shutil.copy(out / f"{name}.wav", out / f"blind_{label}.wav")
        key[f"blind_{label}"] = what
    (out / "blind_key.json").write_text(json.dumps(dict(sorted(key.items())), indent=1))
    return out


if __name__ == "__main__":
    print(main())
