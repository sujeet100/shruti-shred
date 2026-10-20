"""One-minute songs for the experiment: A and B from a BARE model call, C = the full system.

    A — "a one-minute heavy metal song in raga <X>" (sitar, guitar, bass, drums), no knowledge.
    B — the same prompt + the raga's grammar (ladder.grammar(raga), from src/raga.py).
    C — a one-minute song the full agentic system composed for the same request.

A and B go to Gemini through the Google SDK DIRECTLY, never through our CrewAI wrapper: the
request carries the prompt text as its only content — no system instruction, no generation
config (the model's own defaults), no tools. The exact request and the raw reply are saved in
build/ (pure{A,B}_request.json / pure{A,B}_reply.txt) and each call happens once.

The songs are rendered exactly as written (band_ladder.layers_of) and measured for what a
knowledge-free song tends to lack: motifs that return, structure, and consistent note values.

    uv run python talk/audio/pure_songs.py                       # Bhairav: FA FB FC (C = the opening song)
    uv run python talk/audio/pure_songs.py bageshree out/fusion_<stamp>   # Bageshree: GA GB GC
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import band_ladder as bl  # noqa: E402  (the song prompt, rendering exactly as written)
import ladder  # noqa: E402  (the grammar block)
import make_clips as mc  # noqa: E402

MODEL = os.environ.get("RMA_PURE_MODEL", "gemini-3.8-flash")   # the model our agents run on (3.5 for the 2026-10-11 runs)
# Unset = the model's own default thinking (every run before 2026-10-18); e.g. "low" to hear a low-effort call.
THINKING = os.environ.get("RMA_PURE_THINKING")
ONE_MINUTE = bl.BASE.replace("about 30 seconds long (about 64 beats)", "about 1 minute long (about 128 beats)")
assert ONE_MINUTE != bl.BASE
PREFIX = {"bhairav": "F", "bageshree": "G",     # clip ids: FA FB FC (Bhairav), GA GB GC (Bageshree)
          "todi": "T", "yaman": "Y", "malkauns": "M",   # the grind-treatment A/B (2026-10-11)
          "darbari": "D"}


def prompts(raga: str) -> dict[str, str]:
    a = ONE_MINUTE.replace("raga Bhairav", f"raga {raga.title()}")
    form = "The song should include an intro, alap, gat (mukhada + manjha), antara and taans."
    return {"A": a, "F": a + "\n" + form, "B": a + "\n" + ladder.grammar(raga)}   # F = A + the song form, named only


def _tag(raga: str, key: str) -> str:
    """Bhairav keeps its original file names; a run on a model other than the 2026-10-11 one (3.5)
    is cached separately, so a newer model is never answered from an old reply."""
    base = key if raga == "bhairav" else f"_{raga}_{key}"
    tag = base if MODEL == "gemini-3.5-flash" else f"{base}_{MODEL.split('-')[1].replace('.', '')}"
    return tag + (f"_{THINKING}" if THINKING else "")


def ask_once(key: str, raga: str = "bhairav") -> dict:
    """One bare call: the prompt is the only thing sent."""
    tag = _tag(raga, key)
    reply_path = mc.BUILD / f"pure{tag}_reply.txt"
    if not reply_path.exists():
        from dotenv import load_dotenv
        from google import genai
        load_dotenv()
        config = {"thinking_config": {"thinking_level": THINKING}} if THINKING else None
        request = {"model": MODEL, "contents": prompts(raga)[key], "config": config}
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        resp = client.models.generate_content(model=request["model"], contents=request["contents"], config=config)
        (mc.BUILD / f"pure{tag}_request.json").write_text(json.dumps(request, indent=1, ensure_ascii=False))
        usage = resp.usage_metadata.model_dump(exclude_none=True) if resp.usage_metadata else {}
        usage["model_version"] = getattr(resp, "model_version", None)   # which model ANSWERED
        (mc.BUILD / f"pure{tag}_usage.json").write_text(json.dumps(usage, indent=1))
        reply_path.write_text(resp.text)
    reply = reply_path.read_text()
    return json.loads(reply[reply.index("{"): reply.rindex("}") + 1])


# --------------------------------------------------------------------------- #
# What a knowledge-free song tends to lack, measured on the notes.            #
# --------------------------------------------------------------------------- #

def _repeat_share(seq: list, n: int = 4) -> float:
    """Share of n-note windows that recur somewhere else in the line (motifs that come back)."""
    grams = [tuple(seq[i:i + n]) for i in range(len(seq) - n + 1)]
    counts = Counter(grams)
    return round(sum(1 for g in grams if counts[g] > 1) / len(grams), 2) if grams else 0.0


def _bars(notes: list[dict], bar: float = 4.0) -> list[tuple]:
    """The guitar part as a list of bars (each a tuple of (offset, pitch-class set, length))."""
    out: dict[int, list] = {}
    for n in notes:
        k = int(n["start"] // bar)
        out.setdefault(k, []).append((round(n["start"] - k * bar, 3), n["swara"], n["oct"], round(n["dur"], 3)))
    return [tuple(sorted(out.get(k, []))) for k in range(max(out) + 1)] if out else []


def measure(comp: dict, raga: str = "bhairav") -> dict:
    lay = {(l["role"], l.get("instrument")): l for l in comp["layers"]}
    sitar = next(l for (r, i), l in lay.items() if r == "lead" and i == "sitar")["notes"]
    guitar = next(l for (r, _), l in lay.items() if r == "rhythm")["notes"]
    durs = Counter(round(n["dur"], 3) for n in sitar)
    bars = _bars(guitar)
    allowed = set(mc.RAGAS[raga]["allowed"])
    illegal = sum(1 for l in comp["layers"] for n in (l.get("notes") or [])
                  if n["swara"] not in allowed or any(c not in allowed for c in n.get("chord") or []))
    return {"sitar_notes": len(sitar),
            "sitar_motif_repeat": _repeat_share([(n["swara"], n["oct"]) for n in sitar]),
            "sitar_distinct_durations": len(durs),
            "sitar_most_common_duration_share": round(durs.most_common(1)[0][1] / len(sitar), 2),
            "sitar_rests_over_1_beat": sum(1 for a, b in zip(sitar, sitar[1:]) if b["start"] - (a["start"] + a["dur"]) >= 1.0),
            "guitar_bars": len(bars), "guitar_distinct_bars": len(set(bars)),
            "illegal_notes": illegal}


def clip_prefix(raga: str) -> str:
    """The clip-id prefix. Bhairav's 2026-10-11 clips (FA FB FC) are on the deck, so a re-run on a
    newer model writes HA HB HC instead of overwriting them."""
    return "H" if raga == "bhairav" and MODEL != "gemini-3.5-flash" else PREFIX[raga]


def model_suffix() -> str:
    """The clip-id suffix for a model other than the two the deck's clips came from (3.5, 3.8),
    so e.g. a 2.5 run writes YA25 instead of overwriting YA."""
    model = "" if MODEL in ("gemini-3.5-flash", "gemini-3.8-flash") else MODEL.split("-")[1].replace(".", "")
    return model + (THINKING[0].upper() if THINKING else "")


def song(key: str, raga: str = "bhairav") -> dict:
    cid = clip_prefix(raga) + key + model_suffix()
    layers, facts = bl.layers_of(ask_once(key, raga), set(mc.RAGAS[raga]["allowed"]))
    comp = mc.comp(layers).model_copy(update={"raga": raga})
    wav = mc.render_comp(comp, f"{cid}_src", check_raga=False)
    end = max(facts["beats"].values())
    mc.assemble(cid, [(wav, 0.0, end * mc.SEC_PER_BEAT + 2.0)], 0, fade_out=1.0)
    mc.visuals(cid)
    return {"song": cid, "part_beats": facts["beats"], **measure(comp.model_dump(exclude_none=True), raga)}


def song_c(raga: str = "bhairav", stem: Path = bl.OPENING) -> dict:
    cid = PREFIX[raga] + "C"
    comp = json.loads(stem.with_suffix(".json").read_text())
    mc.assemble(cid, [(stem.with_suffix(".wav"), 0.0, 10_000.0)], 0, fade_out=1.0)
    mc.visuals(cid)
    return {"song": cid, "from": stem.name, **measure(comp, raga)}


if __name__ == "__main__":
    args = sys.argv[1:]
    raga = args.pop(0) if args and args[0] in PREFIX else "bhairav"
    stem = Path(args.pop(0)) if args and "/" in args[0] else bl.OPENING
    for k in args or ["A", "B", "C"]:
        print(json.dumps(song_c(raga, stem) if k == "C" else song(k, raga)))
