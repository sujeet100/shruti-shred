"""
Subgenre profiles — the third orthogonal axis.

Three independent axes make a composition:
  raga     = which notes are legal        (raga.py — Hindustani knowledge)
  tala     = the rhythmic cycle           (talas.py — Hindustani knowledge)
  subgenre = tempo, rhythm, register      (this file — metal knowledge)

Keeping them orthogonal is a deliberate design choice: any raga can pair with
any tala with any subgenre. The subgenre says nothing about *which notes* (that
is the raga) and nothing about *the cycle* (that is the tala) — it only sets the
metal character: how fast, how low, how the riff subdivides, and the drum
vocabulary a groove is built from.

Unlike ragas/talas these are genre conventions, not facts needing >=2 Hindustani
sources — but they should still be idiomatic (a doom track is not 200 bpm).

DRUM GROOVES ARE NOT STORED HERE. Per the project's decided architecture, a
groove is GENERATED at the tala x subgenre intersection: the tala gives the
accent skeleton (sam/tali/khali + bol stress) and the subgenre gives the
`drums` VOCABULARY below; a drum-generator agent maps one onto the other. There
is deliberately no hand-authored per-combo groove table.

Fields per subgenre:
  display      human-readable name
  bpm          [min, max] tempo range
  feel         one-line rhythmic character of the riff
  subdivision  how the riff divides the beat (drives note density/timing)
  register     [low, high] octave offsets from Sa for the rhythm guitar
               (negative = lower/downtuned; Sa=60=C4, so -3 ~ C1)
  techniques   guitar techniques the MetalRiff generator may use
  drums        the drum VOCABULARY (see below) — inputs to groove generation
  raga_affinity  SOFT hints only: ragas whose mode suits this subgenre, used to
                 pick demo hero-combos. NOT a constraint — any raga is allowed.
  character    one-line summary incl. which talas tend to fit

The `drums` vocabulary:
  voices       kit voices this subgenre uses (subset of render.DRUMS keys)
  feel         how the kit behaves
  double_kick  whether sustained double-bass is idiomatic
  blast_beats  whether blast beats are idiomatic
  density      "sparse" | "medium" | "dense" | "very dense"
  backbeat     where the snare characteristically lands
"""

from raga import RAGAS

DENSITIES = {"sparse", "medium", "dense", "very dense"}

SUBGENRES = {
    "progressive": {
        "display": "Progressive",
        "bpm": [100, 180],
        "feel": "shifting and syncopated; metric modulation, odd meters welcome",
        "subdivision": "mixed 8ths/16ths and triplets, syncopated accents",
        "register": [-2, 0],   # widest range of the four — uses the mid octave too
        "techniques": ["palm_mute", "power_chords", "clean_arpeggio", "tapping", "syncopation"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "ohat", "ride", "crash",
                       "tom_hi", "tom_mid", "tom_lo"],
            "feel": "dynamic and ghost-note driven, frequent tom fills, ride-led sections",
            "double_kick": True,     # used in bursts, not wall-to-wall
            "blast_beats": False,
            "density": "medium",
            "backbeat": "not fixed — follows the odd-meter vibhags rather than a rigid 2 & 4",
        },
        "raga_affinity": ["bhimpalasi", "darbari"],   # Dorian / Aeolian
        "character": "Technical and metric-shifting; the odd talas (Rupak 7, Jhaptaal 10, "
                     "Ektaal 12) are its home turf.",
    },

    "thrash": {
        "display": "Thrash",
        "bpm": [160, 210],
        "feel": "relentless downpicked gallop, aggressive and forward-driving",
        "subdivision": "galloping 8th/16th figures, tight downpicking",
        "register": [-2, -1],
        "techniques": ["palm_mute", "downpicking", "gallop", "power_chords"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "crash", "ride", "tom_lo"],
            "feel": "fast skank beat (snare on the offbeats), driving and precise",
            "double_kick": True,
            "blast_beats": False,    # the odd fill, but not the identity
            "density": "dense",
            "backbeat": "hard 2 & 4 at speed, the skank pushing between",
        },
        "raga_affinity": ["bhairavi", "bhairav"],      # Phrygian / double-harmonic
        "character": "Fast and sharp; a brisk Keherwa/Teentaal keeps the gallop straight, "
                     "Rupak makes it lurch.",
    },

    "doom": {
        "display": "Doom",
        "bpm": [60, 90],
        "feel": "slow, crushing, half-time; long sustained power chords",
        "subdivision": "whole/half notes, sparse and heavy",
        "register": [-3, -2],   # very low, downtuned
        "techniques": ["power_chords", "sustain", "bends", "sparse_palm_mute"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "crash", "ride", "china", "tom_lo"],
            "feel": "spacious half-time, huge slow backbeat, cymbal swells",
            "double_kick": False,
            "blast_beats": False,
            "density": "sparse",
            "backbeat": "half-time — snare lands once per two vibhags, landing heavy",
        },
        "raga_affinity": ["darbari", "malkauns"],      # Aeolian / dark pentatonic
        "character": "Funereal and vast; Dadra's slow 6 or a broad Teentaal give it room "
                     "to sway.",
    },

    "death": {
        "display": "Death",
        "bpm": [140, 240],
        "feel": "brutal and blasting; tremolo-picked, chromatic, low",
        "subdivision": "tremolo 16ths and chromatic runs",
        "register": [-3, -2],   # very low, downtuned
        "techniques": ["tremolo", "palm_mute", "power_chords", "chromatic", "pinch_harmonic"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "crash", "china", "tom_lo", "tom_mid"],
            "feel": "blast beats over constant double-kick, dense and violent",
            "double_kick": True,
            "blast_beats": True,     # the defining feature
            "density": "very dense",
            "backbeat": "blast — snare/kick alternating at high subdivision over the whole cycle",
        },
        "raga_affinity": ["bhairavi", "bhairav"],      # Phrygian / double-harmonic (exotic, dark)
        "character": "Blasting and chromatic; komal-heavy ragas fit its darkness, and a fast "
                     "Ektaal or Teentaal carries the blast.",
    },
}


def check_subgenre_consistency(name: str) -> list[str]:
    """Assert a subgenre profile is well-formed and cross-references resolve.

    Testable data, same as ragas/talas: the tempo/register ranges must be sane,
    every drum voice must be a real kit voice the renderer can produce, and every
    raga_affinity must name a raga that actually exists in the library.
    """
    from render import DRUMS   # local import: keeps this module free of midiutil

    s = SUBGENRES[name]
    problems: list[str] = []

    lo, hi = s["bpm"]
    if not (0 < lo <= hi):
        problems.append(f"bpm range {s['bpm']} is not a sane [min, max]")
    rlo, rhi = s["register"]
    if rlo > rhi:
        problems.append(f"register {s['register']} has low > high")

    d = s["drums"]
    unknown = [v for v in d["voices"] if v not in DRUMS]
    if unknown:
        problems.append(f"drum voices {unknown} are not in the kit {sorted(DRUMS)}")
    if d["density"] not in DENSITIES:
        problems.append(f"density '{d['density']}' not one of {sorted(DENSITIES)}")
    for flag in ("double_kick", "blast_beats"):
        if not isinstance(d[flag], bool):
            problems.append(f"drums.{flag} must be a bool")

    missing = [r for r in s["raga_affinity"] if r not in RAGAS]
    if missing:
        problems.append(f"raga_affinity names unknown ragas: {missing}")

    return problems
