"""
The NOTES DEBATE, live (Sujit, 2026-10-19): the sitarist (Gemini) and the guitarist (OpenAI
gpt-6-luna) argue about the notes of fusion_20261019_083259_fresh — each rewrites one piece of its
own part, critiques the other's, then revises, defends or withdraws (`crew/notes_debate.py`).

The song is recovered EXACTLY by replaying its own run from its trace (free; verified identical to
the shipped composition), with the checks as they were when it was made — today's alap and
head-revision checks would reject the recorded answers and ask again. Then ~6 live calls.

    uv run python talk/audio/notes_debate_run.py [<song name> <trace id> "<request>"]
      -> out/notes_debate_<stamp>/{original,sitar_proposed,sitar_final,riff_proposed,riff_final,both_final}.wav,
         transcript.md, record.json
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

# the song, its run's trace and its request (default: the first debate's Darbari song, made before
# today's alap and head-revision checks — replayed with those checks as recorded)
SONG: Final = sys.argv[1] if len(sys.argv) > 1 else "fusion_20261019_083259_fresh"
TRACE: Final = sys.argv[2] if len(sys.argv) > 2 else "e6ac29f35d4d"
REQUEST: Final = sys.argv[3] if len(sys.argv) > 3 else "a dark doom fusion in Darbari, key of D, teental, 120 bpm"
AS_RECORDED_0819: Final = SONG == "fusion_20261019_083259_fresh"    # only that song needs the old checks


def _checks_as_recorded():
    """The alap and head-revision checks as they were when the song was made (restored by the
    caller): the generic nyas rule on the alap, no call-and-answer or pulse rule, and the head
    revision's guardrail without the keep-rule lines."""
    import crew.gat_verifier as gv
    import crew.head_revision as hr
    import crew.lead as lead_mod
    saved = (gv._intro_call_and_answer, lead_mod.check_intro, hr.head_turn_guardrail)
    gv._intro_call_and_answer = lambda phrases, raga: ([], [])
    original_check, original_guard = gv.check_intro, hr.head_turn_guardrail

    def old_check(cell, **kw):
        kw.pop("phrase_grid", None)
        r = original_check(cell, **kw)
        return gv.CellChecks(r.hard + tuple(gv.nyas_violations(cell.notes, kw["raga"])), r.craft)
    lead_mod.check_intro = old_check
    hr.head_turn_guardrail = lambda arr, verify=None, first=None: original_guard(arr)

    def restore():
        gv._intro_call_and_answer, lead_mod.check_intro, hr.head_turn_guardrail = saved
    return restore


def recovered_song(scratch: Path):
    """The shipped song's parts, by replaying its run (asserted identical to what shipped)."""
    from crew.flow import compose_flow, production_stages
    from crew.notes_debate import Song
    from crew.realized import realized_lead
    from crew.trace_replay import replaying
    restore = _checks_as_recorded() if AS_RECORDED_0819 else (lambda: None)
    try:
        with replaying(TRACE, tolerance=0.05) as rec:
            state = compose_flow(REQUEST, stages=production_stages(out_dir=scratch, name="replayed"))
    finally:
        restore()
    shipped = json.loads((ROOT / "out" / f"{SONG}.json").read_text())
    if rec.remaining() or json.loads((scratch / "replayed.json").read_text()) != shipped:
        raise RuntimeError("the replay did not reproduce the shipped song — refusing to debate a different one")
    kept = realized_lead(state.events)
    return Song(state.arrangement, kept.phrases, kept.fills, state.rhythm, state.orchestra_layers)


def main() -> Path:
    from crew.config import load_env
    from crew.flow import _SOUNDFONT, _assemble
    from crew.generators import render_composition
    from crew.lead import lead_layers_from
    from crew.notes_debate import notes_debate, transcript
    from crew.notes_debate_crew import players
    from crew.tracing import traced
    load_env()
    out = ROOT / "out" / f"notes_debate_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True)
    song = recovered_song(out / "_replay")
    print("song recovered exactly from its trace", flush=True)

    def build(s, name: str) -> str:
        comp = _assemble(s.arr, lead_layers_from(s.phrases, s.arr, s.fills), s.rhythm, s.orchestra)
        return str(render_composition(comp, out_dir=out, name=name, soundfont=_SOUNDFONT, arrangement=s.arr))

    with traced("notes debate") as tracer:
        debate = notes_debate(song, players(song), build)
    (out / "transcript.md").write_text(transcript(song, debate) + f"\nTrace: {tracer.run_id}\n")
    (out / "record.json").write_text(json.dumps({
        "sitar": debate.sitar.model_dump(exclude_none=True) if debate.sitar else None,
        "riff": debate.riff.model_dump() if debate.riff else None,
        "critique_of_sitar": debate.critique_of_sitar.model_dump() if debate.critique_of_sitar else None,
        "critique_of_riff": debate.critique_of_riff.model_dump() if debate.critique_of_riff else None,
        "sitar_revision": debate.sitar_revision.model_dump(exclude_none=True) if debate.sitar_revision else None,
        "riff_revision": debate.riff_revision.model_dump(exclude_none=True) if debate.riff_revision else None,
        "versions": debate.versions, "notes": debate.notes}, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    print(main())
