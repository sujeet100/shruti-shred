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
  groove_brief an OPERATIONAL directive — concrete rhythm to PLAY, not a mood. This is the
               fix for "a vague brief collapses into sparse whole notes": it tells the
               generators what actually happens rhythmically (chugs, turnarounds, fills),
               so even a slow subgenre stays alive rather than empty.
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
        "groove_brief": "Shift the feel across sections: mix 8ths, 16ths and triplets, displace "
                        "accents off the beat, and let the odd-meter vibhags reshape the groove. "
                        "Contrast the heavy riffing with a clean arpeggiated passage, then a "
                        "16th turnaround back into the sam.",
        "register": [-2, 0],   # widest range of the four — uses the mid octave too
        "techniques": ["palm_mute", "power_chords", "clean_arpeggio", "tapping", "syncopation"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "ohat", "ride", "bell", "crash",
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
        "groove_brief": "Relentless downpicked 8th/16th gallop locked to the kick — keep the right "
                        "hand driving. Punctuate with a tight 16th fill or a rest-stab into the "
                        "sam. Aggressive and forward, never laid-back.",
        "register": [-2, -1],
        "techniques": ["palm_mute", "downpicking", "gallop", "power_chords"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "crash", "ride", "bell", "tom_lo"],
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
        "feel": "slow and crushing, half-time — sustained power chords ANCHORED by palm-muted "
                "chugs (heavy, not empty)",
        "subdivision": "long sustained chords punctuated by 8th-note chugs, with a 16th-note "
                       "turnaround into each sam",
        "groove_brief": "Slow and crushing, but NOT empty. Anchor the long sustained power chords "
                        "with palm-muted 8th-note chugs in the gaps, and drive one 16th-note "
                        "turnaround into each sam. The kit can play a busier (near double-time) "
                        "feel under the half-time riff for momentum. Weight comes from the low "
                        "sustain PLUS the chug — never from silence.",
        "register": [-3, -2],   # very low, downtuned
        "techniques": ["power_chords", "sustain", "bends", "sparse_palm_mute"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "crash", "ride", "bell", "china", "tom_lo"],
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
        "groove_brief": "Brutal tremolo-picked 16ths and chromatic runs over constant "
                        "double-kick/blast — dense and violent. Break the wall only with a sudden "
                        "half-time breakdown stab, then slam back into the blast.",
        "register": [-3, -2],   # very low, downtuned
        "techniques": ["tremolo", "palm_mute", "power_chords", "chromatic", "pinch_harmonic"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "ride", "bell", "crash", "china",
                       "tom_lo", "tom_mid"],
            "feel": "blast beats over constant double-kick, dense and violent — the blast "
                    "rides a tight ride",
            "double_kick": True,
            "blast_beats": True,     # the defining feature
            "density": "very dense",
            "backbeat": "blast — snare/kick alternating at high subdivision over the whole cycle",
        },
        "raga_affinity": ["bhairavi", "bhairav"],      # Phrygian / double-harmonic (exotic, dark)
        "character": "Blasting and chromatic; komal-heavy ragas fit its darkness, and a fast "
                     "Ektaal or Teentaal carries the blast.",
    },

    "heavy": {
        "display": "Heavy Metal",
        "bpm": [110, 180],
        "feel": "driving mid-tempo power chords and galloping riffs; anthemic, NWOBHM",
        "subdivision": "steady 8ths and galloping 8th/16th figures, palm-muted",
        "groove_brief": "Classic heavy-metal drive: palm-muted power-chord riffs and gallops at a "
                        "steady mid-tempo, with twin-guitar HARMONIZED leads (thirds). Anthemic and "
                        "headbangable — a strong, memorable riff and a solid backbeat, not extremity. "
                        "Punctuate with a tom fill into the chorus.",
        "register": [-2, -1],
        "techniques": ["palm_mute", "power_chords", "gallop", "harmonized_leads", "bends"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "ohat", "ride", "bell", "crash",
                       "tom_hi", "tom_mid", "tom_lo"],
            "feel": "driving backbeat with a galloping kick, tom fills into sections",
            "double_kick": True,     # a gallop, used — not wall-to-wall
            "blast_beats": False,
            "density": "medium",
            "backbeat": "hard 2 & 4 with a galloping kick underneath",
        },
        "raga_affinity": ["kirwani", "yaman"],   # neoclassical harmonic-minor + heroic Lydian
        "character": "Anthemic and driving; twin-guitar harmonies over a galloping backbeat. A "
                     "mid-tempo Teentaal/Keherwa; the heroic Yaman and neoclassical Kirwani fit.",
    },

    "melodic_death": {
        "display": "Melodic Death",
        "bpm": [150, 220],
        "feel": "melodic tremolo riffs with harmonized twin-guitar leads over a death-metal drive",
        "subdivision": "tremolo 16ths and galloping 8ths, with harmonized melodic runs",
        "groove_brief": "Gothenburg drive: melodic tremolo-picked riffs and galloping 8ths over "
                        "double-kick, with HARMONIZED twin-guitar leads (thirds/sixths) carrying the "
                        "melody. Heavy but tuneful — a memorable melodic hook, not just a chug. Drop "
                        "to a half-time melodic chorus, then back to the gallop.",
        "register": [-2, -1],
        "techniques": ["tremolo", "palm_mute", "power_chords", "gallop", "melodic_lead"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "crash", "ride", "bell", "china",
                       "tom_lo", "tom_mid"],
            "feel": "driving double-kick with blast bursts, dynamic between gallop and half-time",
            "double_kick": True,
            "blast_beats": True,     # in bursts, not the identity
            "density": "dense",
            "backbeat": "hard 2 & 4 with double-kick under; drops to half-time for melodic choruses",
        },
        "raga_affinity": ["kirwani", "charukeshi"],   # harmonic minor / Aeolian dominant
        "character": "Melodic and driving; harmonized leads over blast/gallop. Harmonic-minor "
                     "Kirwani and Charukeshi give it its melancholy; a brisk Teentaal carries it.",
    },

    "black": {
        "display": "Black",
        "bpm": [150, 220],
        "feel": "cold, fast tremolo-picked walls of sound; trebly, raw, atmospheric",
        "subdivision": "constant tremolo 16ths sustained through the chord changes",
        "groove_brief": "Cold, relentless tremolo-picked 16ths forming a WALL of sound — let the "
                        "harmony change UNDER the tremolo rather than stopping it. Blast beats and "
                        "fast double-kick drive it; stay trebly and higher (leave the sub-low chug to "
                        "death). Break the wall only for a slow, dissonant, ringing passage.",
        "register": [-2, 0],   # higher / trebly — distinct from death's sub-low tuning
        "techniques": ["tremolo", "power_chords", "palm_mute", "dissonance"],
        "drums": {
            "voices": ["kick", "snare", "hhat", "crash", "china", "ride", "bell", "tom_lo"],
            "feel": "relentless blast beats over fast double-kick, cold and cymbal-heavy",
            "double_kick": True,
            "blast_beats": True,
            "density": "very dense",
            "backbeat": "blast — snare/kick alternating at high subdivision, snare near every beat",
        },
        "raga_affinity": ["bhairav", "puriya_dhanashree"],   # exotic, komal-heavy, tritone-dark
        "character": "Cold and relentless; tremolo walls over blast beats. A driving Teentaal/Ektaal "
                     "or a raw free feel; the exotic komal-heavy ragas suit its darkness.",
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

    if not str(s.get("groove_brief", "")).strip():
        problems.append("groove_brief is missing or empty — every subgenre needs an operational brief")

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
