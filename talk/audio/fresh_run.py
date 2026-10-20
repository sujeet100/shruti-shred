"""
A FRESH full run with today's system, everything recorded for Sujit's ear (2026-10-19).

Tests the three untested changes in one render (the cost rule: batch): the reworked Producer
(champion take + blind draft-vs-revision comparison, one judge round), the gat head's measured
self-revision, and the rhythm section's sparse manjha/antara. Nothing is reused — no saved head,
no seed: the request is the one behind fusion_20261013_074703 (the song the first rehearsal
played), so the two can be compared.

Writes, beside the final render:
  <name>_rounds/roundK.wav — every version the critics judged (round0 = the first draft);
  <name>_rounds/notes.md   — in plain order: the head's self-revision, Rasik's notes, the
                             Producer's verdict and plan, the comparison's verdict, what shipped.
Default effort (medium). LIVE: one full run. Rendering the rounds is free.

    uv run python talk/audio/fresh_run.py ["<request>" [tag]]      -> prints NAME=<name>, TRACE=<id>
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

REQUEST = sys.argv[1] if len(sys.argv) > 1 else "a dark doom fusion in Darbari, key of D, teental, 120 bpm"
TAG = sys.argv[2] if len(sys.argv) > 2 else "fresh"


def _recording_critique(critique, rounds: list[dict]):
    def stage(comp, arr):
        ustad, rasik, producer, events = critique(comp, arr)
        rounds.append({"composition": comp.model_dump(exclude_none=True), "violations": len(ustad.violations),
                       "rasik": rasik.model_dump(exclude_none=True), "producer": producer.model_dump(exclude_none=True)})
        return ustad, rasik, producer, events
    return stage


def _recording_compare(compare, verdicts: list[dict]):
    def stage(draft, revision, arr):
        keep, events = compare(draft, revision, arr)
        verdicts.append({"revision_kept": keep, "events": [e.text for e in events]})
        return keep, events
    return stage


def _recording_debate(debate, before: list):
    """The notes-debate stage, keeping the song it was handed (rendered as pre_debate.wav) and the
    concern that called it."""
    def stage(arr, kept, rhythm, orchestra, comp, concern):
        before.append((comp, concern))
        return debate(arr, kept, rhythm, orchestra, comp, concern)
    return stage


def _timed(fn, name: str, times: dict):
    """Wrap a stage to record its wall-clock (the live budget's reserves are calibrated from these)."""
    def stage(*args, **kwargs):
        t0 = time.monotonic()
        try:
            return fn(*args, **kwargs)
        finally:
            times.setdefault(name, []).append(round(time.monotonic() - t0, 1))
    return stage


def _notes(name: str, rounds: list[dict], verdicts: list[dict], state) -> str:
    out = [f"# {name}", "", f"Request: {REQUEST}", ""]
    heads = [e for e in state.events if (e.data or {}).get("head_revision")]
    out += ["## The gat head's self-revision", *([f"- {e.text}" + (f"\n  composer: {e.data.get('argument')}"
                                                                     if e.data.get("argument") else "")
                                                  for e in heads] or ["- not asked (the head met every measured fact)"]), ""]
    for k, r in enumerate(rounds):
        rasik, producer = r["rasik"], r["producer"]
        out += [f"## Round {k} — {'the first draft' if k == 0 else 'after the revision'} (listen: round{k}.wav)",
                f"Illegal notes found by code: {r['violations']}", "",
                f"**Rasik** scores {rasik.get('scores')}", f"> {rasik.get('notes') or rasik.get('reasoning', '')}"]
        out += [f"- suggestion: {s}" for s in rasik.get("suggestions", [])]
        plan = producer.get("plan")
        out += ["", f"**Producer: {producer.get('decision', '?').upper()}**", f"> {producer.get('reasoning', '')}"]
        if plan and producer.get("decision") == "revise":
            out += [f"- plan: revise the {plan['voice']} in sections {plan.get('sections')}: {plan['instruction']}",
                    f"- preserve: {', '.join(plan.get('preserve', [])) or '-'}"]
        out.append("")
    for v in verdicts:
        out += ["## Draft or revision? (blind comparison, both orders)",
                *[f"- {t}" for t in v["events"]],
                f"- **{'the revision was kept' if v['revision_kept'] else 'the first draft was kept'}**", ""]
    band = [e for e in state.events if e.agent in ("Sitarist", "Guitarist", "Band")]
    if band:
        out += ["## The notes debate (listen: pre_debate.wav vs the shipped song)",
                *[f"- **{e.agent}** ({e.type.value}): {e.text}" for e in band], ""]
    second = [e for e in state.events if (e.data or {}).get("second_look")]
    out += ["## The Producer's second look (only when Rasik flags the raga)",
            *([f"- {e.text}" for e in second] or ["- not needed"]), ""]
    flow_notes = [e.text for e in state.events if e.agent == "Flow"]
    out += ["## The Flow's own notes (stops, budget, debate trigger, final check)", *[f"- {t}" for t in flow_notes], ""]
    from crew.drum_feel import drum_feels
    if state.arrangement is not None:
        feels = drum_feels(state.arrangement)
        roles = [s.form_role or s.kind.value for s in state.arrangement.sections]
        out += ["## Drum feels the rhythm section chose", *([f"- section {i} ({roles[i]}): {f}" for i, f in sorted(feels.items())]
                                                           or ["- none (code's defaults)"]), ""]
    out += [f"## Shipped: {state.wav_path}", f"Decision: {state.decision}; outcome: {state.outcome}; revise rounds: {state.round}"]
    return "\n".join(out)


def main() -> str:
    from crew.config import load_env
    from crew.contracts import Composition
    from crew.flow import _OUT_DIR, _SOUNDFONT, _render, compose_flow, production_stages
    from crew.tracing import traced
    load_env()
    name = f"fusion_{time.strftime('%Y%m%d_%H%M%S')}_{TAG}"
    rounds: list[dict] = []
    verdicts: list[dict] = []
    base = production_stages(name=name)
    before: list = []
    times: dict = {}
    stages = dataclasses.replace(base, critique=_timed(_recording_critique(base.critique, rounds), "critique", times),
                                 compare=_timed(_recording_compare(base.compare, verdicts), "compare", times) if base.compare else None,
                                 debate=_timed(_recording_debate(base.debate, before), "notes debate", times) if base.debate else None,
                                 interpret=_timed(base.interpret, "interpret", times),
                                 compose=_timed(base.compose, "compose (seed)", times),
                                 generate=_timed(base.generate, "generate (lead + rhythm section)", times),
                                 regenerate=_timed(base.regenerate, "revise", times),
                                 render=_timed(base.render, "render", times))
    t_start = time.monotonic()
    with traced("fresh-run") as tracer:
        state = compose_flow(REQUEST, stages=stages)
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
    (out / "notes.md").write_text(_notes(name, rounds, verdicts, state) + "\n".join(concern + timing)
                                  + f"\n\nTrace: {tracer.run_id}\n")
    print(f"NAME={name}")
    print(f"TRACE={tracer.run_id}")
    return name


if __name__ == "__main__":
    main()
