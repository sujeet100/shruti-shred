"""The experiment slide's ladder, from REAL model output (one cached call each).

    A — one prompt, no knowledge: "a 30-second melody in raga Bhairav".
    B — the SAME prompt + Bhairav's grammar, generated from src/raga.py (the data the agents read).
    (C — the full agentic system — is an excerpt of the opening song's lead; see ladder_c.)

Both replies are cached in build/, so each call happens once; re-running only re-renders. The
notes are rendered raw (no andolan or shaping of ours: adding it would slip our knowledge into
A), over the same drone, and a 16-beat window from the middle is cut, because a long request
is where a knowledge-free melody loses its thread.

    uv run python talk/audio/ladder.py                                  # A and B
    uv run python talk/audio/ladder.py C out/fusion_20261011_194039.json 16   # C: the opening song's first gat cycle
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_clips as mc  # noqa: E402  (shared voices, render, loudness and visuals)

LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SWARA_OF = {0: "S", 1: "r", 2: "R", 3: "g", 4: "G", 5: "m", 6: "M", 7: "P", 8: "d", 9: "D", 10: "n", 11: "N"}
PITCH_OF = {v: k for k, v in SWARA_OF.items()}
NAMES = ["E", "F", "F#", "G", "G#", "A", "A#", "B", "C", "C#", "D", "D#"]   # semitones above Sa = E
WINDOW_BEATS = 16.0
WINDOWS = mc.BUILD / "ladder_windows.json"   # what each clip's piano roll should show (read by the deck)


def record_window(clip_id: str, src: str, start: float, length: float, sam: bool) -> None:
    """Note the clip's window in its source json's own beat positions, for the slide's roll."""
    w = json.loads(WINDOWS.read_text()) if WINDOWS.exists() else {}
    w[clip_id] = {"src": src, "start": start, "len": length, "sam": sam}
    WINDOWS.write_text(json.dumps(w, indent=1))

BASE = ("Compose a lead melody for a metal song in raga Bhairav, played on sitar, at 128 BPM, in the key "
        "of E (Sa = E4). Make it about 30 seconds long (about 64 beats). Return ONLY a JSON list of notes, "
        'each {"note": "<scientific pitch like E4 or F#4, or rest>", "beats": <duration in beats>}.')


def grammar(raga: str = "bhairav") -> str:
    """A raga's grammar as prompt text, straight from the encoded data."""
    b = mc.RAGAS[raga]

    def seq(sws: list[str]) -> str:
        return " ".join(f"{sw}({NAMES[PITCH_OF[sw]]})" for sw in sws)

    lines = ["", f"Raga {raga.title()}'s grammar (follow it):",
             f"- Allowed notes, sargam(pitch): {seq(b['allowed'])}. No other notes.",
             f"- Aroha, the ascent: {' '.join(b['aroha'])}",
             f"- Avaroha, the descent: {' '.join(b['avaroha'])}",
             f"- Vadi (most important note): {b['vadi']}; samvadi (its partner): {b['samvadi']}",
             "- Pakad (signature phrases): " + " | ".join(" ".join(p) for p in b["pakad"]),
             "- Chalan (characteristic movements): " + " | ".join(" ".join(c) for c in b["chalan"]),
             *([f"- Andolan (slow oscillation) on: {', '.join(b['andolan'])}"] if b.get("andolan") else []),
             "Sargam: S Sa, r komal Re, R Re, g komal Ga, G Ga, m Ma, M tivra Ma, P Pa, d komal Dha, D Dha, n komal Ni, N Ni."]
    return "\n".join(lines)


PROMPTS = {"A": BASE, "B": BASE + "\n" + grammar()}


def ask_once(key: str) -> str:
    cache = mc.BUILD / f"ladder{key}_llm.txt"
    if cache.exists():
        return cache.read_text()
    from crew.config import generator_llm, load_env
    load_env()
    reply = generator_llm().call(PROMPTS[key])
    mc.BUILD.mkdir(parents=True, exist_ok=True)
    (mc.BUILD / f"ladder{key}_prompt.txt").write_text(PROMPTS[key])
    cache.write_text(reply)
    return reply


def midi(note: str) -> int:
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", note.strip())
    if not m:
        raise ValueError(f"unparseable pitch {note!r}")
    return 12 * (int(m.group(3)) + 1) + LETTER[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]


def events_of(reply: str) -> tuple[list[tuple], list[str]]:
    """(swara, oct, beats) events relative to Sa = E4, and the notes outside Bhairav."""
    notes = json.loads(reply[reply.index("["): reply.rindex("]") + 1])
    events, illegal = [], []
    for n in notes:
        beats = float(n["beats"])
        if str(n["note"]).lower() == "rest":
            events.append(("-", None, beats))
            continue
        rel = midi(n["note"]) - mc.SA
        sw = SWARA_OF[rel % 12]
        events.append((sw, rel // 12, beats))
        if sw not in mc.BH["allowed"]:
            illegal.append(n["note"])
    return events, illegal


def window(events: list[tuple]) -> tuple[float, float]:
    """A WINDOW_BEATS stretch from the middle, starting on a note onset."""
    total = sum(d for *_, d in events)
    t, start = 0.0, 0.0
    for sw, _, d in events:
        if t >= max(0.0, total / 2 - WINDOW_BEATS / 2) and sw != "-":
            start = t
            break
        t += d
    return start, min(WINDOW_BEATS, total - start)


def clip(key: str) -> dict:
    events, illegal = events_of(ask_once(key))
    total = sum(d for *_, d in events)
    wav = mc.render_comp(mc.comp([mc.drone(total + 4), mc.sitar_line(events, shaped=False, start=1.0)]), f"L{key}_src", check_raga=False)
    start, length = window(events)
    spb = mc.SEC_PER_BEAT
    _, stats = mc.assemble(f"L{key}", [(wav, (1.0 + start) * spb - 0.15, length * spb + 0.5)], 0, fade_out=0.5)
    mc.visuals(f"L{key}")
    record_window(f"L{key}", f"L{key}_src.json", 1.0 + start, length, sam=False)
    durs = sorted({d for sw, _, d in events if sw != "-"})
    return {"clip": f"L{key}", "notes": sum(1 for e in events if e[0] != "-"), "rests": sum(1 for e in events if e[0] == "-"),
            "beats": total, "illegal": illegal, "distinct_durations": durs, "window_beats": (start, start + length), "stats": stats}


def _sitar_window(lead: dict, bpb: float) -> float:
    """The cycle-aligned WINDOW_BEATS stretch where the sitar sounds the most."""
    end = max(n["start"] + n["dur"] for n in lead["notes"])
    best, best_cover = 0.0, -1.0
    start = 0.0
    while start + WINDOW_BEATS <= end:
        cover = sum(max(0.0, min(n["start"] + n["dur"], start + WINDOW_BEATS) - max(n["start"], start)) for n in lead["notes"])
        if cover > best_cover:
            best, best_cover = start, cover
        start += bpb
    return best


def clip_c(composition: Path, clip_id: str = "LC", start: float | None = None) -> dict:
    """C — the full agentic system: the real sitar line and drone from a saved composition,
    the same WINDOW_BEATS length as A and B, starting on a cycle boundary."""
    d = json.loads(composition.read_text())
    lead = next(l for l in d["layers"] if l["role"] == "lead" and l.get("instrument") == "sitar")
    drone = next(l for l in d["layers"] if l["role"] == "drone")
    c = mc.Composition.model_validate({**{k: v for k, v in d.items() if k != "layers"}, "layers": [drone, lead]})
    wav = mc.render_comp(c, f"{clip_id}_src", check_raga=False)
    spb = 60.0 / d["bpm"]
    start = _sitar_window(lead, d["tala"]["beats_per_bar"]) if start is None else start
    _, stats = mc.assemble(clip_id, [(wav, start * spb, WINDOW_BEATS * spb + 0.5)], 0, fade_out=0.5)
    mc.visuals(clip_id)
    record_window(clip_id, f"{clip_id}_src.json", start, WINDOW_BEATS, sam=True)
    return {"clip": clip_id, "from": composition.name, "raga": d["raga"], "window_beats": (start, start + WINDOW_BEATS), "stats": stats}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "C":
        print(json.dumps(clip_c(Path(args[1]), "LC", float(args[2]) if len(args) > 2 else None)))
    else:
        for k in args or ["A", "B"]:
            print(json.dumps(clip(k)))
