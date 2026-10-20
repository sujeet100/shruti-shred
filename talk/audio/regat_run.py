"""
Today's band around an OLD gat (Sujit, 2026-10-20): keep fusion_20261012_213455's chart and its
realised gat head exactly, and let the current system write everything else — the alap, manjha,
antara, taan and outro, the rhythm section's guitar and bass, then Rasik and the Producer, the
draft-or-revision comparison, a notes debate only on a concern, and the final code check.

The head rides the chart as `seed_hook`, which the Composer path treats as a finished hook (it is
never revised). The Interpreter and the seed call are skipped: the chart is the old one, so the
comparison with the old render is the band, not the plan.

Records like fresh_run.py: <name>_rounds/roundK.wav, notes.md, the trace id.

    uv run python talk/audio/regat_run.py --dry     # load + check the chart and head, no LLM
    uv run python talk/audio/regat_run.py           # LIVE: one full run (ask Sujit first)
"""
from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SOURCE = ROOT / "out" / "fusion_20261012_213455.arrangement.json"
TAG = "regat213455"


def old_chart():
    """The 213455 chart with its realised head and main riff, as the Composer path takes them. Pure."""
    from crew.contracts import Arrangement
    arr = Arrangement.model_validate(json.loads(SOURCE.read_text()))
    return arr.model_copy(update={"seed_head": None, "rhythm_section": None})


def dry() -> None:
    from crew.gat_verifier import check_head_shape
    arr = old_chart()
    head = arr.seed_hook
    roles = [s.form_role or s.kind.value for s in arr.sections]
    print(f"{arr.raga} · {arr.subgenre} · {arr.tala} @ {arr.bpm} · form={arr.form} anchor={arr.anchor}")
    print("sections:", " → ".join(roles))
    print("head:", " ".join(n.swara for n in head.notes), f"({sum(n.dur for n in head.notes)} beats)")
    checks = check_head_shape(head, raga=arr.raga)
    print("today's head-shape checks:", checks)
    print("seed riff notes:", len(arr.seed_riff.notes) if arr.seed_riff else None)


def main() -> str:
    import fresh_run as fr
    from crew.config import load_env
    from crew.contracts import Composition
    from crew.flow import _OUT_DIR, _SOUNDFONT, _render, compose_flow, production_stages
    from crew.tracing import traced
    load_env()
    fr.REQUEST = old_chart().request or "a dark doom fusion in Darbari, key of D, teental, 120 bpm"
    name = f"fusion_{time.strftime('%Y%m%d_%H%M%S')}_{TAG}"
    rounds: list[dict] = []
    verdicts: list[dict] = []
    before: list = []
    times: dict = {}
    base = production_stages(name=name)
    arr = old_chart()
    stages = dataclasses.replace(
        base,
        interpret=lambda query: (None, []),
        compose=lambda brief: (arr, []),
        critique=fr._timed(fr._recording_critique(base.critique, rounds), "critique", times),
        compare=fr._timed(fr._recording_compare(base.compare, verdicts), "compare", times) if base.compare else None,
        debate=fr._timed(fr._recording_debate(base.debate, before), "notes debate", times) if base.debate else None,
        generate=fr._timed(base.generate, "generate (lead + rhythm section)", times),
        regenerate=fr._timed(base.regenerate, "revise", times),
        render=fr._timed(base.render, "render", times))
    t_start = time.monotonic()
    with traced("regat-run") as tracer:
        state = compose_flow(fr.REQUEST, stages=stages)
    out = _OUT_DIR / f"{name}_rounds"
    out.mkdir(parents=True, exist_ok=True)
    for k, rec in enumerate(rounds):
        (out / f"round{k}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        _render(Composition.model_validate(rec["composition"]), soundfont=_SOUNDFONT, out_dir=out, name=f"round{k}")
    total = round(time.monotonic() - t_start, 1)
    if before:
        _render(before[0][0], soundfont=_SOUNDFONT, out_dir=out, name="pre_debate")
    timing = ["", "## Stage times (seconds)", *[f"- {k}: {v}" for k, v in times.items()], f"- whole run: {total}"]
    concern = [f"\n## The concern that called the notes debate\n{before[0][1]}"] if before else []
    header = f"Kept from fusion_20261012_213455: the chart and the gat head (seed_hook).\n\n"
    (out / "notes.md").write_text(header + fr._notes(name, rounds, verdicts, state) + "\n".join(concern + timing)
                                  + f"\n\nTrace: {tracer.run_id}\n")
    print(f"NAME={name}")
    print(f"TRACE={tracer.run_id}")
    return name


if __name__ == "__main__":
    dry() if "--dry" in sys.argv else main()
