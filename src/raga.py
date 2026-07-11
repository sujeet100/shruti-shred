"""
Raga grammar + validator.

This is the deterministic core of the Guru-critic agent. The LLM agents will
emit compositions as swaras; this module decides — note by note — whether they
obey the raga. That check is the whole thesis: "constraints make agents creative."

Sargam notation (offset in semitones from Sa):
  S=0  r=1(komal Re)  R=2  g=3(komal Ga)  G=4  m=5  M=6(tivra Ma)
  P=7  d=8(komal Dha)  D=9  n=10(komal Ni)  N=11
Lowercase = komal (flat), uppercase = shuddha (natural), M = tivra Ma (sharp).
A trailing "'" means the next octave up (S' = Sa an octave above); handled by
the note's `oct` field at render time, so validation ignores octave.
"""

SWARAS = {
    "S": 0, "r": 1, "R": 2, "g": 3, "G": 4, "m": 5,
    "M": 6, "P": 7, "d": 8, "D": 9, "n": 10, "N": 11,
}

# ---------------------------------------------------------------------------
# Raga library — knowledge as DATA (the single source of truth).
#
# This is the project's core discipline: raga facts live here in code, verified
# against >=2 reliable Hindustani sources (NOT Carnatic), and are consumed by
# BOTH the deterministic validator and the LLM agents. The agents reason and
# map; they never supply these facts. Each entry records its `sources` so the
# encoding is auditable.
#
# Fields per raga:
#   display       human-readable name
#   thaat         parent thaat (the 10-thaat Hindustani classification)
#   western_mode  closest Western mode — for the talk's "orthogonal axes" point
#   allowed       set of legal swaras (the hard grammar the validator enforces)
#   aroha         canonical ascent   (swaras, octave-agnostic)
#   avaroha       canonical descent
#   vadi/samvadi  most / second-most prominent swara
#   jati          how many swaras in ascent/descent (e.g. sampurna = all 7)
#   andolan       swaras that oscillate — idiomatic gesture, not just in-scale
#   pakad         signature phrase(s): the raga's fingerprint. Each phrase is a
#                 list of swaras. Used as a generation seed AND as a Rasik
#                 critique criterion ("is the pakad actually present?").
#   chalan        characteristic movement phrases beyond the pakad — how the
#                 raga *moves*. Seeds idiomatic (not merely legal) generation.
#   samay         traditional time of performance
#   sources       the Hindustani references this encoding was cross-checked on
#
# Swaras use the project notation: S r R g G m M P d D n N (see top of file).
# Pakad/chalan are octave-agnostic; octave placement happens at render time.
# ---------------------------------------------------------------------------

RAGAS = {
    "bhairav": {
        "display": "Bhairav",
        "thaat": "Bhairav",
        "western_mode": "double harmonic (Byzantine)",
        # Bhairav's signature: komal Re (r) and komal Dha (d); shuddha Ga/Ma/Ni.
        "allowed": ["S", "r", "G", "m", "P", "d", "N"],
        "aroha":   ["S", "r", "G", "m", "P", "d", "N", "S"],   # ascent
        "avaroha": ["S", "N", "d", "P", "m", "G", "r", "S"],   # descent
        "vadi": "d",      # komal Dhaivat — most prominent
        "samvadi": "r",   # komal Rishabh — second-most prominent
        "jati": "sampurna-sampurna",   # all 7 swaras up and down
        # The oscillated komal Re and komal Dha ARE Bhairav — a straight,
        # un-oscillated r/d sounds like a different raga. Rasik checks for this.
        "andolan": ["r", "d"],
        "pakad": [
            ["G", "m", "d", "d", "P"],
            ["G", "m", "r", "r", "S"],
        ],
        "chalan": [
            ["S", "r", "r", "S"],             # andolit komal Re resolving to Sa
            ["G", "m", "P", "d", "P"],        # the upper tetrachord around vadi d
            ["d", "d", "P", "G", "m", "r", "r", "S"],  # full descent with andolan
        ],
        "samay": "first prahar (early morning, ~6–9 AM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-bhairav/"},
            {"name": "Wikipedia — Bhairav (raga)",
             "url": "https://en.wikipedia.org/wiki/Bhairav_(raga)"},
        ],
    },

    "bhairavi": {
        "display": "Bhairavi",
        "thaat": "Bhairavi",
        "western_mode": "Phrygian",
        # NOTE: full-performance ("mishra") Bhairavi borrows all 12 notes freely.
        # We deliberately encode the STRICT thaat form (Phrygian) as the hard
        # grammar — komal Re, Ga, Dha, Ni; shuddha Ma, Pa. A permissive mishra
        # grammar would let the validator pass almost anything and defeat the
        # guardrail. The metal menu wants the dark Phrygian colour anyway.
        "allowed": ["S", "r", "g", "m", "P", "d", "n"],
        "aroha":   ["S", "r", "g", "m", "P", "d", "n", "S"],
        "avaroha": ["S", "n", "d", "P", "m", "g", "r", "S"],
        "vadi": "m",      # Madhyam
        "samvadi": "S",   # Shadj
        "jati": "sampurna-sampurna",
        "andolan": [],    # Bhairavi leans on murki/khatka ornament, not andolan
        "pakad": [
            ["g", "S", "r", "S"],
            ["g", "m", "P", "d", "m", "g", "m", "r", "S"],
        ],
        "chalan": [
            ["d", "n", "S"],                          # cadence into upper Sa
            ["m", "P", "d", "n", "S"],                # upper-tetrachord ascent
            ["S", "d", "P", "g", "m", "r", "S"],      # signature komal descent
        ],
        "samay": "first prahar; also the traditional concert-closing raga (sarva-kalik)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-bhairavi/"},
            {"name": "Wikipedia — Bhairavi (Hindustani)",
             "url": "https://en.wikipedia.org/wiki/Bhairavi_(Hindustani)"},
        ],
    },

    "bhimpalasi": {
        "display": "Bhimpalasi",
        "thaat": "Kafi",
        "western_mode": "Dorian",
        # Kafi-thaat: komal Ga and komal Ni; shuddha Re, Ma, Pa, Dha.
        # Full note-set is Dorian (S R g m P D n).
        "allowed": ["S", "R", "g", "m", "P", "D", "n"],
        # Audhav ascent: Re and Dha are DROPPED going up, restored coming down —
        # this asymmetry is the raga's identity, not a scale we can flatten.
        "aroha":   ["S", "g", "m", "P", "n", "S"],
        "avaroha": ["S", "n", "D", "P", "m", "g", "R", "S"],
        "vadi": "m",      # Madhyam
        "samvadi": "S",   # Shadj
        "jati": "audhav-sampurna",   # 5 up, 7 down
        "andolan": [],
        "pakad": [
            ["n", "S", "g", "m", "P"],
            ["m", "g", "R", "S"],
        ],
        "chalan": [
            ["P", "n", "D", "P"],                     # the D appears only descending
            ["g", "m", "P", "n", "S"],                # audhav ascent, no R/D
            ["S", "n", "D", "P", "m", "g", "R", "S"], # full sampurna descent
        ],
        "samay": "third prahar (early afternoon, ~12–3 PM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-bheempalasi/"},
            {"name": "Wikipedia — Bhimpalasi",
             "url": "https://en.wikipedia.org/wiki/Bhimpalasi"},
        ],
    },

    "darbari": {
        "display": "Darbari Kanada",
        "thaat": "Asavari",
        "western_mode": "Aeolian",
        # Asavari-thaat: komal Ga, Dha, Ni; shuddha Re, Ma, Pa. Full set = Aeolian.
        "allowed": ["S", "R", "g", "m", "P", "d", "n"],
        "aroha":   ["S", "R", "g", "m", "P", "d", "n", "S"],
        # Avaroha is VAKRA (zig-zag): the P–m–P and g–m–R turns are the raga.
        "avaroha": ["S", "d", "n", "P", "m", "P", "g", "m", "R", "S"],
        "vadi": "R",      # Rishabh
        "samvadi": "P",   # Pancham
        "jati": "sampurna-sampurna (vakra)",
        # The heavy, slow andolan on komal Ga and komal Dha IS Darbari — a
        # straight g/d turns it into plain Asavari/Adana. Rasik must hear this.
        "andolan": ["g", "d"],
        # Source-verified kan (grace-note) conventions: komal Ga is approached
        # with a Re-kan ascending, a Ma-kan descending; komal Dha with a Pa-kan
        # ascending, a Ni-kan descending. Generators attach these as `grace`.
        "kan": {
            "g": {"aroha": "R", "avaroha": "m"},
            "d": {"aroha": "P", "avaroha": "n"},
        },
        "pakad": [
            ["S", "R", "g", "R", "g", "m", "P"],
            ["d", "n", "P", "m", "P", "g", "m", "R", "S"],
        ],
        "chalan": [
            ["g", "m", "R", "S"],                      # the komal-Ga turn to Sa
            ["m", "P", "d", "n", "P"],                 # dwelling on komal Dha
            ["n", "P", "m", "P", "g", "m", "R", "S"],  # vakra descent
        ],
        "samay": "third prahar of the night (late night, ~12–3 AM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-darbari-kanada/"},
            {"name": "Wikipedia — Darbari",
             "url": "https://en.wikipedia.org/wiki/Darbari"},
        ],
    },

    "malkauns": {
        "display": "Malkauns",
        "thaat": "Bhairavi",
        "western_mode": "dark/minor pentatonic (no Re, no Pa)",
        # Audhav pentatonic: komal Ga, Dha, Ni; shuddha Ma. Re and Pa ABSENT.
        # The missing Pa is why Malkauns floats — no dominant to pull home.
        "allowed": ["S", "g", "m", "d", "n"],
        "aroha":   ["S", "g", "m", "d", "n", "S"],
        "avaroha": ["S", "n", "d", "m", "g", "S"],
        "vadi": "m",      # Madhyam
        "samvadi": "S",   # Shadj
        "jati": "audhav-audhav",   # 5 up, 5 down
        "andolan": [],    # Malkauns lives on meend (glides), not oscillation
        "pakad": [
            ["d", "n", "S", "m"],
            ["g", "m", "g", "S"],
        ],
        "chalan": [
            ["g", "m", "d", "n", "S"],       # pentatonic ascent
            ["n", "d", "m", "g", "S"],       # pentatonic descent
            ["m", "d", "n", "d", "m", "g"],  # the brooding middle-octave sway
        ],
        "samay": "third prahar of the night (late night, ~12–3 AM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-malkauns/"},
            {"name": "Wikipedia — Malkauns",
             "url": "https://en.wikipedia.org/wiki/Malkauns"},
        ],
    },
}


def check_raga_consistency(name: str) -> list[str]:
    """Assert a raga's encoding is internally consistent; return any problems.

    This makes the *data* testable (a project convention): every swara that
    appears in the aroha, avaroha, pakad, chalan, vadi, samvadi, or andolan
    must be a legal swara of the raga, and every swara must be a known sargam
    symbol. Catches typos before they ever reach a generator or the renderer.
    """
    raga = RAGAS[name]
    allowed = set(raga["allowed"])
    problems: list[str] = []

    for sw in raga["allowed"]:
        if sw not in SWARAS:
            problems.append(f"allowed swara '{sw}' is not a known sargam symbol")

    def check_phrase(swaras, where):
        for sw in swaras:
            if sw not in SWARAS:
                problems.append(f"{where}: '{sw}' is not a known sargam symbol")
            elif sw not in allowed:
                problems.append(f"{where}: '{sw}' is not in {name}'s allowed set")

    check_phrase(raga["aroha"], "aroha")
    check_phrase(raga["avaroha"], "avaroha")
    check_phrase([raga["vadi"], raga["samvadi"]], "vadi/samvadi")
    check_phrase(raga.get("andolan", []), "andolan")
    for i, phrase in enumerate(raga.get("pakad", [])):
        check_phrase(phrase, f"pakad[{i}]")
    for i, phrase in enumerate(raga.get("chalan", [])):
        check_phrase(phrase, f"chalan[{i}]")

    return problems


def semitone(swara: str) -> int:
    """Semitone offset of a swara above Sa."""
    return SWARAS[swara]


def validate_composition(comp: dict) -> list[dict]:
    """Return a list of grammar violations (empty == clean).

    Each violation is what the Guru-critic quotes back to the offending agent.
    Drums carry no pitch, so they're skipped.
    """
    raga = RAGAS[comp["raga"]]
    allowed = set(raga["allowed"])
    violations = []
    for layer in comp["layers"]:
        if layer.get("role") == "drums":
            continue
        for n in layer.get("notes", []):
            # Every pitch that actually sounds faces the grammar — the main
            # swara, each kan (grace note), and a meend's TARGET swara (the note
            # you land on). The guardrail can't have a blind spot for ornaments.
            # The microtones a meend sweeps through are not notes, so not checked.
            checks = [(n["swara"], "note")]
            checks += [(g, "grace") for g in n.get("grace", [])]
            m = n.get("meend")
            if m is not None:
                tsw = m["swara"] if isinstance(m, dict) else m
                checks.append((tsw, "meend-target"))
            for sw, kind in checks:
                if sw not in allowed:
                    label = "" if kind == "note" else f"{kind.replace('-', ' ')} "
                    violations.append({
                        "layer": layer["role"],
                        "swara": sw,
                        "start_beat": n["start"],
                        "kind": kind,
                        "reason": (
                            f"{label}'{sw}' is illegal in raga {raga['display']} "
                            f"(allowed: {' '.join(raga['allowed'])})"
                        ),
                    })
    return violations
