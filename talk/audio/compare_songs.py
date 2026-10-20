"""Whole-song comparison for the single-prompt experiment: A (bare call), B (bare + grammar) and
C (the full system), measured on what a listener notices across ALL parts — form and energy arc,
breathing, the riff, dynamics, the return of the opening idea, the ending, and illegal notes in any
part — beside the sitar's raga idiom (talk/audio/idiom.py). Free: reads saved compositions.

    uv run python talk/audio/compare_songs.py            # every song it can find -> stdout JSON
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import idiom  # noqa: E402
from raga import RAGAS, SWARAS  # noqa: E402

BAR = 4.0
BUILD = ROOT / "talk" / "audio" / "build"
SONGS = {
    "yaman": {"A": BUILD / "YA_src.json", "B": BUILD / "YB_src.json", "C": ROOT / "out" / "fusion_20261018_131644_yaman.json"},
    "darbari": {"A": BUILD / "DA_src.json", "B": BUILD / "DB_src.json", "C": ROOT / "out" / "fusion_20261018_132646_darbari.json"},
    "bhairav": {"A": BUILD / "HA_src.json", "B": BUILD / "HB_src.json", "C": None},
}


def _part(comp: dict, role: str, instrument: str | None = None) -> list[dict]:
    out = []
    for l in comp["layers"]:
        if l["role"] == role and (instrument is None or l.get("instrument") == instrument):
            out += [e for e in (l.get("notes") or l.get("hits") or []) if not e.get("rest")]
    return sorted(out, key=lambda e: e["start"])


def _bars_on(events: list[dict], bars: int) -> list[bool]:
    on = [False] * bars
    for e in events:
        for k in range(int(e["start"] // BAR), min(bars, int((e["start"] + e.get("dur", 0.25) - 1e-6) // BAR) + 1)):
            on[k] = True
    return on


def _per_bar(events: list[dict], bars: int) -> list[int]:
    c = [0] * bars
    for e in events:
        k = int(e["start"] // BAR)
        if k < bars:
            c[k] += 1
    return c


def measure(comp: dict, raga: str) -> dict:
    sitar, guitar = _part(comp, "lead", "sitar"), _part(comp, "rhythm")
    bass, drums = _part(comp, "bass"), _part(comp, "drums")
    end = max(e["start"] + e.get("dur", 0.25) for e in sitar + guitar + bass + drums)
    bars = max(1, round(end / BAR))
    on = {k: _bars_on(v, bars) for k, v in (("sitar", sitar), ("guitar", guitar), ("bass", bass), ("drums", drums))}
    all_on = sum(all(on[k][b] for k in on) for b in range(bars)) / bars
    energy = [sum(x) for x in zip(*(_per_bar(v, bars) for v in (sitar, guitar, bass, drums)))]
    third = max(1, bars // 3)
    arc = [round(st.mean(energy[i:i + third]), 1) for i in range(0, third * 3, third)]
    # a STROKE is every guitar note starting together (the bare format writes a chord as several
    # notes on one beat; the system writes one note with a `chord`)
    strokes: dict[float, list[dict]] = {}
    for g in guitar:
        strokes.setdefault(round(g["start"], 3), []).append(g)
    stroke_list = list(strokes.values())
    gchords = [s_ for s_ in stroke_list if len(s_) >= 2 or any(g.get("chord") for g in s_)]
    glong = [s_ for s_ in stroke_list if max(g["dur"] for g in s_) >= 1.0]
    gpm = [s_ for s_ in stroke_list if any(g.get("technique") == "palm_mute" for g in s_)]
    cyc = Counter(tuple((round(e["start"] % BAR, 2), e["swara"]) for e in guitar if b * BAR <= e["start"] < (b + 1) * BAR)
                  for b in range(bars))
    vels = [st.mean([e.get("vel", 90) for e in v if b * BAR <= e["start"] < (b + 1) * BAR] or [0]) for b in range(bars)
            for v in (guitar + sitar,)]
    first = [(n["swara"], n.get("oct", 0)) for n in sitar if n["start"] < BAR * 2]
    seq = [(n["swara"], n.get("oct", 0)) for n in sitar]
    returns = sum(1 for i in range(len(first), len(seq) - len(first) + 1) if first and seq[i:i + len(first)] == first)
    allowed = set(RAGAS[raga]["allowed"])
    illegal = {k: sum(1 for e in v if "swara" in e and (e["swara"] not in allowed or any(c not in allowed for c in e.get("chord") or [])))
               for k, v in (("sitar", sitar), ("guitar", guitar), ("bass", bass))}
    last = {k: max((e["start"] + e.get("dur", 0.25) for e in v), default=0) for k, v in
            (("sitar", sitar), ("guitar", guitar), ("bass", bass), ("drums", drums))}
    pitches = [SWARAS[n["swara"]] + 12 * n.get("oct", 0) for n in sitar]
    sitar_time = sum(n["dur"] for n in sitar)
    return {
        "length_bars": bars,
        "breathing": {"bars_with_every_part_playing": round(all_on, 2),
                      "sitar_silent_share": round(1 - min(1.0, sitar_time / end), 2),
                      "bars_each_part_plays": {k: round(sum(v) / bars, 2) for k, v in on.items()}},
        "energy_arc_thirds": arc,
        "energy_range": [min(energy), max(energy)],
        "riff": {"strokes": len(stroke_list), "chord_share": round(len(gchords) / max(1, len(stroke_list)), 2),
                 "sustained_share": round(len(glong) / max(1, len(stroke_list)), 2),
                 "palm_mute_share": round(len(gpm) / max(1, len(stroke_list)), 2),
                 "distinct_bars": len(cyc), "most_repeated_bar_count": cyc.most_common(1)[0][1] if cyc else 0},
        "dynamics": {"bar_velocity_spread": round(max(vels) - min(vels), 1) if vels else 0},
        "sitar": {"notes": len(sitar), "range_semitones": (max(pitches) - min(pitches)) if pitches else 0,
                  "opening_returns": returns, "distinct_durations": len({round(n["dur"], 2) for n in sitar})},
        "illegal_notes": illegal,
        "ending_spread_beats": round(max(last.values()) - min(v for v in last.values() if v), 2),
        "idiom": {k: v for k, v in idiom.measure(comp, raga).items() if k in ("pakad", "chalan", "nyas", "andolan", "vadi_samvadi_time_share")},
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        SONGS["bhairav"]["C"] = Path(sys.argv[1])
    out = {}
    for raga, songs in SONGS.items():
        for k, path in songs.items():
            if path and path.exists():
                m = measure(json.loads(path.read_text()), raga)
                m["idiom"]["nyas"].pop("rests", None)
                out[f"{raga} {k}"] = m
    print(json.dumps(out, indent=1, ensure_ascii=False))
