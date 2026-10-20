"""
The CONTROL for the head debate (out/head_debate_20261018_234135): did the rival's arguments move
the heads, or did code's measurements? Same chart, same proposals A0 and B0, same approaches, same
measurements, same rounds — but each composer revises ALONE (`llm_head_turn(..., solo=True)`, the
`revise_head` task): it never sees the other head.

If the solo composers make the debate's move (into the mandra, the d n P cell), the measurements
did the work and the debate added cost, not direction. LIVE: up to 4 turns, Gemini at the
Composer's tier.

    uv run python talk/audio/head_control_run.py   ->  out/head_control_<stamp>/
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "talk" / "audio"))

DEBATE: Final = ROOT / "out" / "head_debate_20261018_234135"
ROUNDS: Final = 2                              # the debate settled after 2 rounds


def _proposal(name: str):
    from crew.contracts import LeadPhrase
    return LeadPhrase.model_validate(json.loads((DEBATE / f"{name}.arrangement.json").read_text())["seed_hook"])


def main() -> Path:
    from crew.anchor import lead_tokens
    from crew.audition import head_arrangement, render_audition
    from crew.config import load_env
    from crew.flow import _SOUNDFONT
    from crew.head_debate import head_debate, head_measures
    from crew.seed_debate_crew import llm_head_turn
    from crew.tracing import traced
    from head_debate_run import APPROACHES, _inputs, _similarity
    load_env()
    seed, brief = _inputs()
    out = ROOT / "out" / f"head_control_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True)
    proposals = {c: _proposal(f"{c}0") for c in APPROACHES}
    with traced("head control (solo revision)"):
        versions = head_debate(proposals, llm_head_turn(head_arrangement(seed, brief), dict(APPROACHES),
                                                        ROUNDS, solo=True), rounds=ROUNDS)
    for v in versions:
        if v.round:
            render_audition(seed.model_copy(update={"hook": v.head}), brief, out_dir=out,
                            name=f"{v.composer}{v.round}", soundfont=_SOUNDFONT)
    by_round: dict[int, dict[str, object]] = {}
    for v in versions:
        by_round.setdefault(v.round, {})[v.composer] = v.head
    record = {
        "versions": [{"composer": v.composer, "round": v.round, "changed": v.changed, "argument": v.argument,
                      "motif": v.head.phrase_plan.seed, "notes": lead_tokens(v.head.notes),
                      "measures": head_measures(v.head)} for v in versions],
        "convergence": {r: _similarity(h["A"], h["B"]) for r, h in by_round.items() if len(h) == 2},
        "drift_from_proposal": {c: {v.round: _similarity(proposals[c], v.head) for v in versions if v.composer == c}
                                for c in APPROACHES},
    }
    (out / "record.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    print(main())
