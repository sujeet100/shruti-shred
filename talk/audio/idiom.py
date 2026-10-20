"""Does a song's sitar line follow its RAGA, beyond legal notes? Measured, for the single-prompt
experiment (songs A / B / C): the scale, the direction rules, the key phrases (pakad), the
movement (chalan), where phrases come to rest (nyas), the weight on vadi/samvadi, and the andolan.

Every measure reads only the encoded, source-verified raga data (src/raga.py, src/chalan.py,
crew/rasik.pakad_presence). Mood is not countable: Rasik scores it separately (`--rasik`, one
cheap call per song). Pure except for that optional call.

    uv run python talk/audio/idiom.py <composition.json> <raga> [--rasik]

A caveat that matters for A and B: the bare prompt's format has no ornament field, so a bare song
cannot WRITE an andolan; it can only hold an andolit swara long enough for one to be played. C's
andolan is set by code from the raga data. The measure reports both.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from chalan import motion_report  # noqa: E402
from raga import NYAS, RAGAS, SWARAS, directional_varjya, nyas_problem  # noqa: E402

from crew.rasik import pakad_presence  # noqa: E402

REST_GAP = 0.5          # a silence this long (beats) ends a phrase
HELD_FOR_ANDOLAN = 1.0  # beats: a sway needs a held note


def sitar_notes(comp: dict) -> list[dict]:
    lead = [l for l in comp["layers"] if l["role"] == "lead" and l.get("instrument", "sitar") == "sitar"]
    return sorted((n for l in lead for n in l.get("notes") or [] if not n.get("rest")), key=lambda n: n["start"])


def _pitch(n: dict) -> int:
    return SWARAS[n["swara"]] + 12 * n.get("oct", 0)


def phrase_ends(notes: list[dict]) -> list[int]:
    """Indices of notes that end a phrase: followed by a silence of REST_GAP or more, or last."""
    ends = [i for i, (a, b) in enumerate(zip(notes, notes[1:])) if b["start"] - (a["start"] + a["dur"]) >= REST_GAP]
    return ends + ([len(notes) - 1] if notes else [])


def measure(comp: dict, raga: str) -> dict:
    notes = sitar_notes(comp)
    r = RAGAS[raga]
    allowed = set(r["allowed"])
    seq = [(n["swara"], n.get("oct", 0)) for n in notes]
    # direction: a descent-only swara entered from below (or an ascent-only one from above)
    dv = directional_varjya(raga)
    wrong_way = sum(1 for a, b in zip(notes, notes[1:]) if b["swara"] in dv and _pitch(b) != _pitch(a)
                    and ((dv[b["swara"]] == "avaroha") == (_pitch(b) > _pitch(a))))
    entries = sum(1 for a, b in zip(notes, notes[1:]) if b["swara"] in dv and _pitch(b) != _pitch(a))
    # nyas: what phrases rest on
    ends = phrase_ends(notes)
    bad_rests = [i for i in ends if nyas_problem(raga, notes[i]["swara"],
                                                 (_pitch(notes[i]) > _pitch(notes[i - 1])) if i else None)]
    # weight on vadi / samvadi, by time
    total = sum(n["dur"] for n in notes) or 1.0
    weight = sum(n["dur"] for n in notes if n["swara"] in (r["vadi"], r["samvadi"])) / total
    # andolan: the andolit swaras, how often held long enough to sway, how often actually swayed
    andolit = [n for n in notes if n["swara"] in r.get("andolan", [])]
    motion = motion_report(seq, raga)
    return {
        "notes": len(notes),
        "scale": {"forbidden_notes": sum(n["swara"] not in allowed for n in notes)},
        "direction": {"rule": dv, "entries": entries, "wrong_way": wrong_way},
        "pakad": {" ".join(p): m for p, m in pakad_presence([sw for sw, _ in seq], raga)},
        "chalan": {"ang_coverage": motion.ang_coverage, "longest_scalar_run": motion.longest_scalar_run,
                   "direction_changes": motion.direction_changes, "stepwise_share": motion.stepwise_share},
        "nyas": {"phrases": len(ends), "rest_on_a_wrong_swara": len(bad_rests),
                 "core": NYAS[raga]["core"], "rests": [notes[i]["swara"] for i in ends][:40]},
        "vadi_samvadi_time_share": round(weight, 2),
        "andolan": {"swaras": r.get("andolan", []), "occurrences": len(andolit),
                    "held_long_enough": sum(n["dur"] >= HELD_FOR_ANDOLAN for n in andolit),
                    "actually_swayed": sum(bool(n.get("andolan")) for n in andolit)},
    }


def rasik_scores(comp_path: Path, raga: str, request: str) -> dict:
    """Rasik's 1-5 scores (pakad, idiom, rasa = mood) and notes for the song's melody. One call."""
    from crew.config import load_env
    from crew.contracts import Composition
    from crew.rasik import critique_taste
    load_env()
    comp = Composition.model_validate(json.loads(comp_path.read_text()))
    verdict, _ = critique_taste(comp, request)
    return {"scores": verdict.scores.model_dump(), "notes": verdict.notes}


if __name__ == "__main__":
    path, raga = Path(sys.argv[1]), sys.argv[2]
    comp = json.loads(path.read_text())
    out = measure(comp, raga)
    if "--rasik" in sys.argv:
        out["rasik"] = rasik_scores(path, raga, f"a one-minute heavy metal song in raga {raga.title()}")
    print(json.dumps(out, indent=1, ensure_ascii=False))
