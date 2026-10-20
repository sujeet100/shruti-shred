"""A/B for ReAct step 1: does LISTENING change what the Composer writes?

The same lead call — the Composer persona composing the mukhada of the 2026-10-18 Darbari song C
(`out/fusion_20261018_132646_darbari`, the song that held 0 of 47 ga/dha long enough to sway) —
run twice on IDENTICAL inputs: A without the `hear_phrase` tool, B with it (RMA_HEAR=1). Each run is
its own process and its own trace; B also records every draft it listened to and what it heard.

    uv run python talk/audio/hear_ab.py run A out/hear_ab_<stamp>    # LIVE: one lead call
    uv run python talk/audio/hear_ab.py run B out/hear_ab_<stamp>    # LIVE: one call + its listens
    uv run python talk/audio/hear_ab.py compare out/hear_ab_<stamp>  # free: reports + two WAVs
    (add `fresh` to every command to strip song C's seeds: a NEW melody, not a development)

The comparison renders each answer's mukhada (both avartans) over the tanpura, and prints the
listening report of each FINAL answer, so A is described exactly as B was told.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SONG = ROOT / "out" / "fusion_20261018_132646_darbari.arrangement.json"
SECTION = 0                                   # the mukhada


def _chart(fresh: bool = False):
    """Song C's chart; `fresh` strips its seeds (hook, head idea, riff) so the mukhada is a NEW
    melody, not a development of the one song C's seed call already wrote."""
    from crew.contracts import Arrangement
    from crew.generators import section_spans
    arr = Arrangement.model_validate_json(SONG.read_text())
    if fresh:
        arr = arr.model_copy(update={"seed_hook": None, "seed_head": None, "seed_riff": None})
    return arr, section_spans(arr)[SECTION]


def _record_listens(log: list[dict]) -> None:
    """Wrap the tool so every draft B listens to, and what it heard, is kept."""
    from crew.contracts import LeadNote
    from crew.hearing_tool import HearPhraseTool
    original = HearPhraseTool._run

    def recording(self, notes):
        report = original(self, notes)
        log.append({"draft": [LeadNote.model_validate(n).model_dump(exclude_none=True)
                              for n in notes], "report": report})
        return report
    HearPhraseTool._run = recording


def run(variant: str, out: Path, fresh: bool = False) -> None:
    from crew.config import load_env
    from crew.lead import _LLMLead
    from crew.tracing import traced
    load_env()
    if variant == "B":
        os.environ["RMA_HEAR"] = "1"
    else:
        os.environ.pop("RMA_HEAR", None)
    listens: list[dict] = []
    _record_listens(listens)
    arr, span = _chart(fresh)
    with traced(f"hear-ab-{variant}-darbari-mukhada") as tracer:
        phrase = _LLMLead(arr, "composer")(span, arr, [])
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{variant}.json").write_text(json.dumps({
        "variant": variant, "fresh": fresh, "trace": tracer.run_id, "phrase": phrase.model_dump(exclude_none=True),
        "listens": listens}, indent=1))
    print(f"{variant}: {len(phrase.notes)} notes, listened {len(listens)} time(s), trace {tracer.run_id}")


def compare(out: Path, fresh: bool = False) -> None:
    from crew.contracts import LeadPhrase
    from crew.flow import _SOUNDFONT
    from crew.generators import assemble_composition, drone_layer, render_composition
    from crew.hearing import hear
    from crew.lead import lead_layers_from
    arr, span = _chart(fresh)
    solo = arr.model_copy(update={"sections": arr.sections[:SECTION + 1]})
    for variant in ("A", "B"):
        data = json.loads((out / f"{variant}.json").read_text())
        phrase = LeadPhrase.model_validate(data["phrase"])
        print(f"\n===== {variant} — listened {len(data['listens'])} time(s), trace {data['trace']}")
        for i, listen in enumerate(data["listens"], 1):
            print(f"--- what B heard on listen {i}:\n{listen['report']}")
        print(f"--- the FINAL answer, as the tool would describe it:\n{hear(phrase.notes, span, arr)}")
        comp = assemble_composition(solo, [*lead_layers_from({SECTION: phrase}, solo), drone_layer(solo)])
        wav = render_composition(comp, out_dir=out, name=f"mukhada_{variant}", soundfont=_SOUNDFONT)
        print(f"--- {wav}")


if __name__ == "__main__":
    command, *rest = sys.argv[1:]
    fresh = "fresh" in rest
    if command == "run":
        run(rest[0], ROOT / rest[1], fresh)
    else:
        compare(ROOT / rest[0], fresh)
