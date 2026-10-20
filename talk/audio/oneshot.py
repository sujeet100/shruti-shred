"""A06a — the "prompt only" clip: ONE naive Gemini call, cached, rendered like A06b/A06c.

The prompt deliberately carries no rules, no raga data and no verifier — it is the
baseline the talk compares against. The raw reply is cached in build/A06a_llm.txt so the
call happens once; re-running only re-renders.

    uv run python talk/audio/oneshot.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_clips as mc  # noqa: E402  (shared voices, render, loudness and visuals)

PROMPT = ("Compose a short lead melody for a metal song in raga Bhairav, played on sitar, "
          "128 BPM, about 6 seconds long. Return ONLY a JSON list of notes, each "
          '{"note": "<scientific pitch like E4 or F#4>", "beats": <duration in beats>}. '
          "Use 12 to 16 notes.")
CACHE = mc.BUILD / "A06a_llm.txt"
NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SWARA_OF = {0: "S", 1: "r", 2: "R", 3: "g", 4: "G", 5: "m", 6: "M", 7: "P", 8: "d", 9: "D", 10: "n", 11: "N"}


def ask_once() -> str:
    if CACHE.exists():
        return CACHE.read_text()
    from crew.config import generator_llm, load_env
    load_env()
    reply = generator_llm().call(PROMPT)
    mc.BUILD.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(reply)
    return reply


def midi(note: str) -> int:
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", note.strip())
    if not m:
        raise ValueError(f"unparseable pitch {note!r}")
    pc = NAMES[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return 12 * (int(m.group(3)) + 1) + pc


def main() -> None:
    reply = ask_once()
    notes = json.loads(reply[reply.index("["): reply.rindex("]") + 1])
    events, illegal = [], []
    tonic = midi(notes[0]["note"])                    # the model's own Sa (it chose C; the prompt named no key)
    for n in notes:
        rel = midi(n["note"]) - tonic                 # semitones from ITS Sa; rendered at Sa = E like B and C
        sw, octv = SWARA_OF[rel % 12], rel // 12
        events.append((sw, octv, float(n["beats"])))
        if sw not in mc.BH["allowed"]:
            illegal.append(n["note"])
    wav = mc.render_comp(mc.comp([mc.drone(15), mc.sitar_line(events, shaped=False)]), "A06a_src", check_raga=False)
    _, stats = mc.assemble("A06a", [(wav, 0, 6.0)], 0)
    mc.visuals("A06a")
    print(json.dumps({"notes": len(events), "illegal": illegal, "stats": stats}))


if __name__ == "__main__":
    main()
