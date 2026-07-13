"""
End-to-end proof of the data-driven pipeline (still no LLM):

  compose (swaras) -> validate against raga grammar -> render to WAV

Reproduces the clip you approved, but now expressed as the exact composition
data an agent will emit. Also builds the "naive" version with an illegal note
so you can see the Guru-critic's deterministic core catch it — that contrast
is the demo's thesis in miniature.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from raga import validate_composition  # noqa: E402
from render import render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SF = os.path.join(ROOT, "soundfonts", "GeneralUser-GS.sf2")

BEATS_PER_BAR = 3.5          # 7/8
EIGHTH = 0.5
INTRO_BARS, DROP_BARS = 2, 6
INTRO_LEN = INTRO_BARS * BEATS_PER_BAR


def build_fusion(illegal: bool = False) -> dict:
    total = INTRO_LEN + DROP_BARS * BEATS_PER_BAR

    # Tanpura-style drone: Sa + Pa held underneath everything (oct -1 = C3)
    drone = {"role": "drone", "instrument": "strings", "program": 48, "channel": 1, "notes": [
        {"swara": "S", "oct": -1, "start": 0, "dur": total, "vel": 55},
        {"swara": "P", "oct": -1, "start": 0, "dur": total, "vel": 45},
    ]}

    # Sitar alaap intro: S r G m P d N S' (unhurried, states the raga)
    lead_notes = []
    alaap = ["S", "r", "G", "m", "P", "d", "N", ("S", 1)]
    t = 0.0
    for i, sw in enumerate(alaap):
        oct = 0
        if isinstance(sw, tuple):
            sw, oct = sw
        dur = 0.9 if i < len(alaap) - 1 else 1.4
        lead_notes.append({"swara": sw, "oct": oct, "start": round(t, 3), "dur": dur, "vel": 90})
        t += dur * 0.9

    # 7/8 djent riff that still spells Bhairav (S r G m over low C)
    riff = ["S", "S", "r", "S", "G", "S", "m"]
    if illegal:
        riff[2] = "R"   # shuddha Re — the classic Bhairav violation

    guitar_notes = []
    for bar in range(DROP_BARS):
        bs = INTRO_LEN + bar * BEATS_PER_BAR
        for i, sw in enumerate(riff):
            guitar_notes.append({"swara": sw, "oct": -2, "start": round(bs + i * EIGHTH, 3), "dur": 0.42, "vel": 118})
            if i == 0:  # octave-down reinforcement on the downbeat
                guitar_notes.append({"swara": sw, "oct": -3, "start": round(bs, 3), "dur": 0.42, "vel": 110})
        if bar % 2 == 1:  # sitar answers every other bar
            for i, sw in enumerate(["P", "d", "P", "m", "G", "r", "S"]):
                lead_notes.append({"swara": sw, "oct": 0, "start": round(bs + i * EIGHTH, 3), "dur": 0.4, "vel": 85})

    guitar = {"role": "rhythm", "instrument": "dist_guitar", "program": 29, "channel": 0, "notes": guitar_notes}
    lead = {"role": "lead", "instrument": "sitar", "program": 104, "channel": 2, "notes": lead_notes}

    # 7/8 drum groove
    hits = []
    for bar in range(DROP_BARS):
        bs = INTRO_LEN + bar * BEATS_PER_BAR
        hits += [{"drum": "hhat", "start": round(bs + i * EIGHTH, 3), "vel": 70} for i in range(7)]
        hits += [{"drum": "kick", "start": round(bs + k * EIGHTH, 3), "vel": 120} for k in (0, 3, 5)]
        hits += [{"drum": "snare", "start": round(bs + s * EIGHTH, 3), "vel": 110} for s in (2, 6)]
    drums = {"role": "drums", "channel": 9, "hits": hits}

    return {
        "raga": "bhairav", "sa": 60, "bpm": 140,
        "tala": {"name": "rupak", "beats_per_bar": BEATS_PER_BAR},
        "layers": [drone, lead, guitar, drums],
    }


if __name__ == "__main__":
    good = build_fusion(illegal=False)
    print(f"[crew fusion ]  grammar violations: {len(validate_composition(good))}")
    render(good, os.path.join(ROOT, "out", "fusion_legal.mid"),
           os.path.join(ROOT, "out", "fusion_legal.wav"), SF)
    print("               -> rendered out/fusion_legal.wav")

    bad = build_fusion(illegal=True)
    viols = validate_composition(bad)
    print(f"[naive fusion]  grammar violations: {len(viols)}")
    for x in viols[:3]:
        print(f"               -> {x['layer']} @ beat {x['start_beat']}: {x['reason']}")
