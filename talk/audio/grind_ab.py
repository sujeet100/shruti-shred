"""Free A/B/C (no LLM): a single-call song's riff under three grind treatments, all else identical.

    uv run python talk/audio/grind_ab.py [STEM]     # STEM in talk/audio/build, default FA_src

  keep    — A as written: every half-step/tritone grind against the sitar survives.
  damp    — today's pipeline: a grinding stroke loses its chord, clips to 0.5 beat, softens,
            palm-mutes (the retired crew.generators.damp_note, copied below), against any SETTLED
            (>=0.5 beat) sitar note.
  resolve — the proposal: a grind on a stroke shorter than a beat is a PASSING tension (kept);
            a held one (>=1 beat) moves its root by the smallest step (1-2 semitones) to a legal
            swara consonant with the sitar (unison/fourth/fifth), preferring the riff's NEXT root,
            re-voiced as a power chord; if nothing resolves, the stroke becomes a rest.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/sujitk/projects/personal/raga-metal-agents")
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from crew.contracts import Composition  # noqa: E402
from crew.generators import double_track, render_composition  # noqa: E402
from crew.riff_voicing import power_voicing  # noqa: E402
from raga import RAGAS, SWARAS  # noqa: E402

HARSH = {1, 6, 11}


def damp_note(note):
    """The retired pipeline treatment (crew.generators.damp_note until 2026-10-11, kept here so
    this A/B still reproduces it): strip the chord, clip to a 0.5-beat chug, soften by 10%,
    palm-mute."""
    return note.model_copy(update={"chord": None, "dur": round(min(note.dur, 0.5), 4),
                                   "vel": max(1, round(note.vel * 0.9)), "technique": "palm_mute"})
CONSONANT = {0, 5, 7}
SETTLED = 0.5
HELD = 1.0
BY_SEMI = {v: k for k, v in SWARAS.items()}


def pitch(n) -> int:
    return SWARAS[n.swara] + 12 * n.oct


def groups(notes):
    """Onset groups (a chord = stacked notes struck together), in order."""
    out, cur = [], []
    for n in sorted(notes, key=lambda n: n.start):
        if cur and abs(n.start - cur[0].start) > 0.06:
            out.append(cur)
            cur = []
        cur.append(n)
    if cur:
        out.append(cur)
    return out


def settled_over(g, lead):
    s, e = g[0].start, g[0].start + g[0].dur
    return [l for l in lead if l.dur >= SETTLED and l.start < e and s < l.start + l.dur]


def grinds(g, lead) -> bool:
    return any((pitch(n) - pitch(l)) % 12 in HARSH for n in g for l in settled_over(g, lead))


def resolve(g, nxt, lead, raga):
    root = min(g, key=pitch)
    over = settled_over(g, lead)
    allowed = set(RAGAS[raga]["allowed"])
    cands = []
    for step in (1, -1, 2, -2):
        p = pitch(root) + step
        sw = BY_SEMI[p % 12]
        if sw in allowed and all((p - pitch(l)) % 12 in CONSONANT for l in over):
            cands.append((0 if nxt is not None and sw == min(nxt, key=pitch).swara else 1,
                          abs(step), sw, (p - SWARAS[sw]) // 12))
    if not cands:
        return []                                    # nothing resolves: leave space
    _, _, sw, octv = min(cands)
    new_root = root.model_copy(update={"swara": sw, "oct": octv})
    stack = [new_root]
    for tone in power_voicing(sw, root.dur, raga):   # [dyad, root] -> dyad above, octave
        semi = (SWARAS[tone] - SWARAS[sw]) % 12 or 12
        tp = pitch(new_root) + semi
        stack.append(root.model_copy(update={"swara": BY_SEMI[tp % 12], "oct": (tp - SWARAS[BY_SEMI[tp % 12]]) // 12}))
    return stack


def treat(layer, lead, mode, raga, log):
    gs = groups(layer.notes)
    out = []
    for i, g in enumerate(gs):
        if not grinds(g, lead):
            out += g
            continue
        if mode == "keep":
            out += g
            log["kept"] += 1
        elif mode == "damp":
            out.append(damp_note(min(g, key=pitch)))
            log["damped"] += 1
        else:                                       # resolve
            if g[0].dur < HELD:
                out += g
                log["passing_kept"] += 1
            else:
                new = resolve(g, gs[i + 1] if i + 1 < len(gs) else None, lead, raga)
                out += new
                log["resolved" if new else "rested"] += 1
                log.setdefault("where_s", []).append(round(g[0].start * 60 / BPM[0], 1))
    return layer.model_copy(update={"notes": sorted(out, key=lambda n: n.start)})


BPM = [128]


def main() -> None:
    stem = sys.argv[1] if len(sys.argv) > 1 else "FA_src"
    src = Composition.model_validate_json((ROOT / f"talk/audio/build/{stem}.json").read_text())
    BPM[0] = src.bpm
    lead = [n for l in src.layers if l.role == "lead" for n in (l.notes or [])]
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    report = {}
    for mode in ("keep", "damp", "resolve"):
        log: dict = {"kept": 0, "damped": 0, "passing_kept": 0, "resolved": 0, "rested": 0}
        # As the PRODUCT does: treat the riff (the left take), then derive the right take from
        # it with `double_track`. Treating the humanised right take separately counted phantom
        # grinds where its nudged note lengths overlapped a sitar note by a sliver.
        takes = [i for i, l in enumerate(src.layers) if l.role == "rhythm"]
        layers = list(src.layers)
        layers[takes[0]] = treat(src.layers[takes[0]], lead, mode, src.raga, log)
        for i in takes[1:]:
            layers[i] = double_track(layers[takes[0]]).model_copy(
                update={k: getattr(src.layers[i], k) for k in ("program", "channel", "pan",
                                                              "detune_cents")
                        if getattr(src.layers[i], k, None) is not None})
        comp = src.model_copy(update={"layers": layers})
        name = f"grind_{mode}_{stem}_{stamp}"
        wav = render_composition(comp, out_dir=ROOT / "out", name=name,
                                 soundfont=ROOT / "soundfonts/GeneralUser-GS.sf2")
        where = sorted({round(x) for x in log.pop("where_s", [])})
        report[mode] = {**{k: v for k, v in log.items() if v}, "rest_or_move_at_s": where,
                        "wav": str(wav)}
    strokes = len(groups([l for l in src.layers if l.role == "rhythm"][0].notes))
    print(json.dumps({"song": stem, "raga": src.raga, "strokes_per_take": strokes, **report},
                     indent=1))


if __name__ == "__main__":
    main()
