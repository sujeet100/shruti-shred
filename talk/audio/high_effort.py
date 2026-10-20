"""High-effort system song + does the Producer's critique loop help? (2026-10-18, Sujit's ask)

One full live run of today's system on song C's request (Darbari, one minute, Sa = E, 128 BPM)
with the Composer and the judges (Rasik, the Producer) thinking at HIGH instead of medium. Every
version of the piece the critics see is saved, so one run gives two comparisons:

  * effort    — this song against song C (`out/fusion_20261018_132646_darbari`, medium effort);
  * the loop  — round 0 (the Composer's first draft, before any critique) against the final round
                (what the Producer's edit plans produced), rendered side by side for a blind listen.

The Flow itself is unchanged: the critique stage is wrapped to record what it was given and what
the Producer said. LIVE: one full run (~20-25 model calls, high thinking). Rendering rounds is free.

    uv run python talk/audio/high_effort.py darbari
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("RMA_CONCEPTION_THINKING", "high")   # the Composer's seed, gat and head calls
os.environ.setdefault("RMA_JUDGE_THINKING", "high")        # Rasik and the Producer
os.environ.setdefault("RMA_LLM_TIMEOUT_S", "420")          # high thinking runs long; a timeout re-pays the call


def _recording(critique, rounds: list[dict]):
    """The critique stage, recording each composition it judges and the Producer's verdict."""
    def stage(comp, arr):
        ustad, rasik, producer, events = critique(comp, arr)
        rounds.append({"composition": comp.model_dump(exclude_none=True),
                       "producer": producer.model_dump(exclude_none=True),
                       "rasik": rasik.model_dump(exclude_none=True)})
        return ustad, rasik, producer, events
    return stage


def main(raga: str) -> Path:
    from crew.config import load_env
    from crew.contracts import Composition
    from crew.flow import _OUT_DIR, _SOUNDFONT, _render, compose_flow, production_stages
    from crew.tracing import traced
    from system_song import request
    load_env()
    name = f"fusion_{time.strftime('%Y%m%d_%H%M%S')}_{raga}_high"
    rounds: list[dict] = []
    base = production_stages(name=name)
    stages = dataclasses.replace(base, critique=_recording(base.critique, rounds))
    with traced(f"high-effort-{raga}") as tracer:
        state = compose_flow(request(raga), stages=stages)
    out = _OUT_DIR / f"{name}_rounds"
    out.mkdir(parents=True, exist_ok=True)
    for k, rec in enumerate(rounds):
        (out / f"round{k}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        _render(Composition.model_validate(rec["composition"]), soundfont=_SOUNDFONT, out_dir=out, name=f"round{k}")
    summary = [{"round": k, "decision": "accept" if r["producer"].get("plan") is None else "revise",
                "scores": r["producer"].get("scores"), "plan": (r["producer"].get("plan") or {}).get("instruction")}
               for k, r in enumerate(rounds)]
    (out / "summary.json").write_text(json.dumps({"trace": tracer.run_id, "final": state.decision,
                                                   "revise_rounds": state.round, "rounds": summary}, indent=1))
    print(f"{raga}: {state.decision} after {state.round} revise round(s); {len(rounds)} version(s) judged; "
          f"final {state.wav_path}; rounds in {out}; trace {tracer.run_id}")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "darbari")
