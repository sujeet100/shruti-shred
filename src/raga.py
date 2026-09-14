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
#   ornaments     light decorative ornaments the raga idiomatically uses (murki/khatka) —
#                 an expressive CHOICE the composer places, gated per-raga (source-verified;
#                 of our five only Bhairavi uses them; the grave/meend ragas use andolan)
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
        "ornaments": [],    # a grave raga — andolan, not light murki/khatka
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
        # Source-verified (Tanarang, chandrakantha, raag-hindustani, ITC-SRA): of our five
        # ragas ONLY Bhairavi idiomatically uses murki/khatka, concentrated on the komal
        # g / komal r descent (m g r S). They differ by WEIGHT (murki light, khatka sharper),
        # not by note pattern — see DESIGN.md "Murki/khatka".
        "ornaments": ["murki", "khatka"],
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
        "ornaments": [],    # a romantic raga on meend + kan-swar, not signature murki/khatka
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
        "ornaments": [],    # the grave Kanada — heavy andolan, not light murki/khatka
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
        "ornaments": [],  # sources exclude light murki/khatka here — meend/gamak/andolan instead
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

    # --- Menu expansion (2026-07-14, source-verified ≥2 Hindustani sources each). ------------
    # Kirwani + Charukeshi are CARNATIC in origin (melakarta ragas) adopted into Hindustani —
    # verified in their HINDUSTANI treatment, Carnatic sources excluded. Yaman was previously
    # dropped as "too bright for metal" (Lydian) and is re-added deliberately (prog/power-leaning).

    "kirwani": {
        "display": "Kirwani",
        "thaat": "none (harmonic minor — outside Bhatkhande's ten thaats)",
        "western_mode": "harmonic minor",
        # Carnatic origin (21st melakarta Keeravani), adopted into Hindustani; treated as a
        # scalar, instrument-friendly raga. Shuddha ma (m5), NOT tivra. = Western harmonic minor;
        # the augmented 2nd komal-Dha -> shuddha-Ni (d -> N) is its signature colour. The most
        # metal-friendly of the roster (harmonic minor = the neoclassical/shred scale).
        "allowed": ["S", "R", "g", "m", "P", "d", "N"],
        "aroha":   ["S", "R", "g", "m", "P", "d", "N", "S"],
        "avaroha": ["S", "N", "d", "P", "m", "g", "R", "S"],
        "vadi": "P",      # Pancham (majority; softly fixed — sources also offer m, or none)
        "samvadi": "S",   # Shadj
        "jati": "sampurna-sampurna",
        "andolan": [],
        "ornaments": [],  # meend-driven (esp. the d->N slide); murki/khatka only inferred, not encoded
        "pakad": [
            ["R", "g", "m", "P", "d", "P", "m", "g", "R"],
            ["N", "d", "P", "g", "R"],
        ],
        "chalan": [
            ["N", "S", "R", "g", "R", "S"],
            ["m", "P", "d", "N", "S"],
            ["S", "N", "d", "P", "m", "g", "R", "S"],
        ],
        "samay": "second prahar of the night (~9 PM–12 AM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-keervani/"},
            {"name": "Ragajunglism", "url": "https://ragajunglism.org/ragas/kirwani/"},
            {"name": "Wikipedia — Kirwani", "url": "https://en.wikipedia.org/wiki/Kirwani"},
        ],
    },

    "charukeshi": {
        "display": "Charukeshi",
        "thaat": "none (mishra — no clean Bhatkhande thaat)",
        "western_mode": "Mixolydian b6",
        # Carnatic origin (26th melakarta), a recent Hindustani adoptee "in a formative phase".
        # A bright, all-shuddha lower tetrachord (S R G m) clashing with a komal upper (P d n) —
        # Mixolydian b6 / Aeolian dominant ("Hindu scale"). vadi/samvadi are GENUINELY unsettled
        # (Tanarang: ma/Sa; others reverse or none) — encoded ma/Sa, not a hard fact.
        "allowed": ["S", "R", "G", "m", "P", "d", "n"],
        "aroha":   ["S", "R", "G", "m", "P", "d", "n", "S"],
        "avaroha": ["S", "n", "d", "P", "m", "G", "R", "S"],
        "vadi": "m",      # Madhyam (Tanarang; contested — see note)
        "samvadi": "S",   # Shadj
        "jati": "sampurna-sampurna",
        "andolan": [],
        "ornaments": [],
        "pakad": [
            ["d", "n", "S", "R", "G"],
            ["G", "m", "R", "S"],
            ["R", "G", "m", "d", "P"],
        ],
        "chalan": [
            ["d", "n", "S", "R", "G", "m", "G", "R"],
            ["R", "G", "m", "d", "P"],
            ["G", "m", "d", "d", "P"],           # the "Bhairav cluster" touch (Parrikar)
        ],
        "samay": "second prahar of the morning (~9 AM–12 PM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-charukeshi/"},
            {"name": "Rajan Parrikar", "url": "https://www.parrikar.org/hindustani/charukeshi/"},
            {"name": "Ragajunglism", "url": "https://ragajunglism.org/ragas/charukeshi/"},
        ],
    },

    "bageshree": {
        "display": "Bageshree",
        "thaat": "Kafi",
        "western_mode": "Dorian",
        # Kafi/Dorian — the SAME mode as Bhimpalasi; its distinct identity is NOT the scale but
        # the weak/omitted Pancham (audhav ascent, no R/P), the vakra Pa in the descent
        # (m P D m g), Ma as vadi, and Dha as the strong nyas. Longing (vipralambha) rasa.
        "allowed": ["S", "R", "g", "m", "P", "D", "n"],
        "aroha":   ["S", "g", "m", "D", "n", "S"],          # audhav: R and P dropped ascending
        "avaroha": ["S", "n", "D", "P", "m", "g", "R", "S"],
        "vadi": "m",      # Madhyam
        "samvadi": "S",   # Shadj (Tanarang/Courtney/Wikipedia; ragajunglism's Pa is a weaker outlier)
        "jati": "audhav-sampurna",   # 5 up, 7 down (R/P dropped ascending)
        "andolan": [],
        "ornaments": [],  # lyrical/romantic — light murki possible but not an identity ornament
        "pakad": [
            ["m", "D", "n", "D", "m", "g", "R", "S"],
            ["m", "P", "D", "m", "g"],          # the vakra Pa signature (avaroha-only)
        ],
        "chalan": [
            ["S", "n", "D", "n", "S"],
            ["S", "g", "m", "D", "n", "D"],
            ["m", "P", "D", "m", "g", "R", "S"],
        ],
        "samay": "second prahar of the night (~9 PM–12 AM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-bageshree/"},
            {"name": "Rajan Parrikar", "url": "https://www.parrikar.org/hindustani/bageshree/"},
            {"name": "Ragajunglism", "url": "https://ragajunglism.org/ragas/bageshri/"},
        ],
    },

    "puriya_dhanashree": {
        "display": "Puriya Dhanashree",
        "thaat": "Poorvi",
        "western_mode": "double harmonic #4",
        # Poorvi thaat, sandhi-prakash (dusk). Bhairav's double-harmonic colour but with tivra Ma
        # (M6) replacing shuddha ma — so a TRITONE above Sa. komal r + tivra M + komal d = dark,
        # exotic, two augmented-2nd leaps (r->G, d->N). Pancham-centric (a rock-solid power-chord
        # root). vakra descent (M G M r G r S). samvadi contested (r primary; Tanarang says S).
        "allowed": ["S", "r", "G", "M", "P", "d", "N"],
        "aroha":   ["S", "r", "G", "M", "P", "d", "N", "S"],
        "avaroha": ["S", "N", "d", "P", "M", "G", "M", "r", "G", "r", "S"],   # vakra lower tetrachord
        "vadi": "P",      # Pancham — "the breath of Puriya Dhanashree's life" (Parrikar)
        "samvadi": "r",   # komal Rishabh (majority; Tanarang/Sangeetapriya say Shadj — a documented variant)
        "jati": "sampurna-sampurna",
        "andolan": [],
        "ornaments": [],
        "pakad": [
            ["P", "M", "G", "M", "r", "G", "P"],
            ["N", "r", "G", "M", "P"],
        ],
        "chalan": [
            ["N", "r", "G", "M", "P"],
            ["P", "M", "G", "M", "r", "G"],
            ["M", "d", "N", "S"],
        ],
        "samay": "sandhi-prakash — dusk / sunset (afternoon–evening junction)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-puriya-dhanashree/"},
            {"name": "Rajan Parrikar", "url": "https://www.parrikar.org/hindustani/poorvi/"},
            {"name": "Wikipedia — Puriya Dhanashree",
             "url": "https://en.wikipedia.org/wiki/Puriya_Dhanashree"},
        ],
    },

    "yaman": {
        "display": "Yaman",
        "thaat": "Kalyan",
        "western_mode": "Lydian",
        # The defining Kalyan raga: all shuddha PLUS tivra Ma (M6) = Lydian (raised 4th). The
        # BRIGHTEST of the roster — previously dropped from the menu as "too bright for metal";
        # re-added deliberately (a luminous/heroic Lydian colour that fits prog/power far better
        # than doom/black). No andolan, no murki/khatka; meend + kan are its ornaments. Dha is
        # avoided as a nyas.
        "allowed": ["S", "R", "G", "M", "P", "D", "N"],
        "aroha":   ["S", "R", "G", "M", "P", "D", "N", "S"],
        "avaroha": ["S", "N", "D", "P", "M", "G", "R", "S"],
        "vadi": "G",      # Gandhar
        "samvadi": "N",   # Nishad (Ga–Ni samvad)
        "jati": "sampurna-sampurna",
        "andolan": [],
        "ornaments": [],
        "pakad": [
            ["N", "R", "G", "M", "G", "R", "S"],
            ["P", "M", "G", "R", "S"],
        ],
        "chalan": [
            ["N", "D", "N", "R", "G", "R", "S"],
            ["G", "M", "P", "M", "G", "R", "S"],
            ["S", "N", "D", "N", "D", "P"],
        ],
        "samay": "first prahar of the night (~6–9 PM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-yaman/"},
            {"name": "Rajan Parrikar", "url": "https://www.parrikar.org/hindustani/kalyan/"},
            {"name": "Ragajunglism", "url": "https://ragajunglism.org/ragas/yaman/"},
        ],
    },

    # --- Menu expansion (2026-07-15, source-verified ≥2 Hindustani sources each). ------------
    # Chandrakauns, Jog, Marwa, Todi. Two are thaat-inexact (Chandrakauns modern, Jog uses both
    # gandhars); Marwa and Todi are eponymous thaat ragas. Discrepancies FLAGGED in each comment.

    "chandrakauns": {
        "display": "Chandrakauns",
        "thaat": "none (thaat-inexact — a modern Malkauns derivative)",
        "western_mode": "dark pentatonic (natural 7)",
        # Malkauns's dark pentatonic (S g m d) but with SHUDDHA Ni (N) instead of komal ni — the
        # single changed note IS the raga: N is a leading tone pulling hard to Sa, so the brooding
        # Malkauns frame gains tension/urgency, and komal-d -> shuddha-N -> S gives an augmented-2nd
        # then a semitone (a neoclassical/"evil" colour). Re and Pa absent (audhav). FLAG: the modern
        # shuddha-Ni form is the standard one encoded here; an older komal-ni variant also exists.
        "allowed": ["S", "g", "m", "d", "N"],
        "aroha":   ["S", "g", "m", "d", "N", "S"],
        "avaroha": ["S", "N", "d", "m", "g", "S"],
        "vadi": "m",      # Madhyam (Tanarang)
        "samvadi": "S",   # Shadj
        "jati": "audhav-audhav",   # 5 up, 5 down
        "andolan": [],
        "ornaments": [],  # meend-driven like its parent Malkauns; no signature murki/khatka in sources
        "pakad": [
            ["g", "m", "d", "N", "S"],
            ["N", "d", "m", "g", "S"],
        ],
        "chalan": [
            ["m", "g", "S"],
            ["d", "N", "S"],                          # the shuddha-Ni pull to Sa — the identity
            ["S", "N", "d", "m", "g", "m", "g", "S"], # Tanarang's "N d m g m g S" sway
        ],
        "samay": "second prahar of the night (~9 PM–12 AM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-chandrakauns/"},
            {"name": "Ragajunglism", "url": "https://ragajunglism.org/ragas/chandrakauns/"},
        ],
    },

    "jog": {
        "display": "Jog",
        "thaat": "Kafi (thaat-inexact — uses both gandhars)",
        "western_mode": "both-Ga pentatonic (no Re/Dha, komal Ni)",
        # A pentatonic on S–Ga–m–P–Ni that uses BOTH gandhars: SHUDDHA Ga ascending, then the
        # signature komal-ga "Gmg" zigzag near Sa in descent (m G g S). That major/minor-third
        # ambiguity (like a blues third) over a heavy P is the whole raga. Komal Ni; Re and Dha
        # absent. FLAG (contested vadi): Tanarang gives Madhyam–Shadj; ragajunglism makes shuddha
        # Ga the vadi (with Pa/Sa). Encoded m/S (Tanarang) — a judgement call, not a hard fact.
        "allowed": ["S", "g", "G", "m", "P", "n"],   # ascending-semitone order (both Ga adjacent)
        "aroha":   ["S", "G", "m", "P", "n", "S"],   # shuddha Ga ascending
        "avaroha": ["S", "n", "P", "m", "G", "g", "S"],  # komal ga enters near Sa (the Gmg zigzag)
        "vadi": "m",      # Madhyam (Tanarang; see FLAG)
        "samvadi": "S",   # Shadj
        "jati": "audhav-audhav",   # 5 swara-positions up/down (Ga counted once)
        "andolan": [],
        "ornaments": [],  # the Gmg is a vakra gamak/kan gesture, not a light murki/khatka
        "pakad": [
            ["G", "m", "P", "m", "G"],
            ["m", "G", "g", "S"],         # the Gmg zigzag resolving to Sa — the fingerprint
        ],
        "chalan": [
            ["S", "G", "m", "P", "n", "S"],
            ["P", "m", "G", "m", "G", "g", "S"],
            ["n", "S", "g", "S"],         # ragajunglism's "nSgS" komal-ga touch
        ],
        "samay": "second prahar of the night (~9 PM–12 AM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-jog/"},
            {"name": "Ragajunglism", "url": "https://ragajunglism.org/ragas/jog/"},
        ],
    },

    "marwa": {
        "display": "Marwa",
        "thaat": "Marwa",
        "western_mode": "Marwa (flat-2, sharp-4, no Pa)",
        # Marwa-thaat, sandhi-prakash (sunset). Komal Re + tivra Ma + NO Pancham — six notes — and
        # the tonic itself is WEAK/avoided for long stretches (the raga hovers on komal re and Dha
        # and resolves reluctantly to Sa). No Pa = no dominant pull (it floats, like Malkauns) plus
        # a tritone (S–M) over a ♭2: unresolved, tense, exotic (a doom/black colour). vadi komal Re,
        # samvadi Dha — an exceptional r–Dha axis with no consonance between them (Parrikar). FLAG:
        # ragajunglism's page garbled Re's quality ("natural second"); Tanarang + Parrikar's lowercase
        # "re" both confirm KOMAL Re (textbook Marwa).
        "allowed": ["S", "r", "G", "M", "D", "N"],
        "aroha":   ["S", "r", "G", "M", "D", "N", "S"],
        "avaroha": ["S", "N", "D", "M", "G", "r", "S"],
        "vadi": "r",      # komal Rishabh
        "samvadi": "D",   # shuddha Dhaivat
        "jati": "shadav-shadav",   # 6 up, 6 down (Pa omitted)
        "andolan": [],
        "ornaments": [],  # a meend-and-sustain raga; the weak Sa is structural, not an ornament
        "pakad": [
            ["D", "N", "r", "S"],         # the reluctant descent to the weak Sa
            ["N", "r", "G", "M", "D"],
            ["M", "G", "r", "S"],
        ],
        "chalan": [
            ["r", "G", "M", "D"],
            ["G", "M", "D", "N", "D"],    # dwelling on the samvadi Dha
            ["N", "D", "N", "r", "S"],    # the mandra Ni–Dha approach to the weak Sa
        ],
        "samay": "sandhi-prakash — fourth prahar of the day / sunset (~3–6 PM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-marwa/"},
            {"name": "Ragajunglism (incl. Rajan Parrikar)",
             "url": "https://ragajunglism.org/ragas/marwa/"},
        ],
    },

    "todi": {
        "display": "Todi (Miyan ki Todi)",
        "thaat": "Todi",
        "western_mode": "Todi thaat (flat-2 flat-3 sharp-4 flat-6 natural-7)",
        # The eponymous Todi-thaat raga (Miyan ki Todi). Komal Re + komal Ga + TIVRA Ma + komal Dha
        # + shuddha Ni; Pancham present but SPARSE (alp — omit it entirely and it becomes Gurjari/
        # Gujari Todi). vadi komal Dha, samvadi komal Ga. FLAG: the komal re/ga are sung "ati-komal"
        # (a lower shruti than plain komal) — a microtone we cannot notate, so they are encoded as
        # r/g and coloured by meend. The most chromatic raga of the roster (♭2 ♭3 ♯4 ♭6 ♮7 =
        # harmonic-minor-with-a-tritone): a neoclassical/death "evil-scale" colour. Triple-sourced.
        "allowed": ["S", "r", "g", "M", "P", "d", "N"],
        "aroha":   ["S", "r", "g", "M", "d", "N", "S"],   # Pa generally skipped ascending
        "avaroha": ["S", "N", "d", "P", "M", "g", "r", "S"],
        "vadi": "d",      # komal Dhaivat
        "samvadi": "g",   # komal Gandhar
        "jati": "sampurna-sampurna",   # all 7 present (Pa sparse, not absent)
        "andolan": [],
        "ornaments": [],  # plaintive meend + the ati-komal shruti carry it, not light murki/khatka
        "pakad": [
            ["d", "N", "S", "r", "g", "r", "S"],
            ["M", "d", "N", "d", "P"],
        ],
        "chalan": [
            ["S", "r", "g", "r", "S"],
            ["g", "M", "d", "N", "S"],
            ["S", "N", "d", "P", "M", "g", "r", "S"],
        ],
        "samay": "second prahar of the day / late morning (~9 AM–12 PM)",
        "sources": [
            {"name": "Tanarang", "url": "https://tanarang.com/raag-todi/"},
            {"name": "Wikipedia — Todi (raga)", "url": "https://en.wikipedia.org/wiki/Todi_(raga)"},
            {"name": "Ragajunglism", "url": "https://ragajunglism.org/ragas/todi/"},
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


# Tanpura tuning, in preference order: the companion string is Pa; for a raga
# WITHOUT Pa it is Ma (madhyam) — e.g. Malkauns, tuned Sa-ma; failing both, the
# nishad. This is a performance-practice CONVENTION, not a per-raga fact from the
# raga sources — kept here as data so the (deterministic) drone stays legal in the
# grammar by construction. FLAG: confirm the convention before the talk.
_DRONE_COMPANIONS: tuple[str, ...] = ("P", "m", "M", "N", "n")


# The SITAR's own drone strings — the chikari, struck to fill an empty matra — are tuned per
# raga, and that tuning is part of the raga's sound: the ringing strings colour every stroke.
# The convention is the same substitution the tanpura makes (Rāga Junglism's sitar page: for
# ragas with an absent Pa or a strong ma, the top-layer Pa strings are set to ma instead;
# Malkauns retunes that string to ma or dha; Marwa's drone strings sound Dha and Sa), so the
# DEFAULT is derived here rather than listed per raga.
#
# `_CHIKARI_TUNINGS` holds only the ragas whose tuning does NOT follow from that rule.
# Bageshree is the case in point: it HAS a Pa, so the "absent Pa" convention does not reach
# it, yet it is tuned Sa Sa Dha Ma — because its Pa is vakra and avaroha-only while Ma is its
# vadi and Dha its strong nyas (both already encoded above). SOURCE: Sujit's guruji (oral
# tradition, via Sujit 2026-09-14) — a practitioner source, recorded as such rather than
# dressed up as a citation. Add a raga here only on the same footing.
_CHIKARI_TUNINGS: dict[str, list[str]] = {
    "bageshree": ["S", "S", "D", "m"],
}

# Strings 1 and 2 carry the stroke; 3 and 4 add colour under it, not equal weight.
CHIKARI_STRING_WEIGHTS: tuple[float, ...] = (1.0, 0.9, 0.5, 0.35)


def chikari_swaras(raga: str) -> list[str]:
    """The sitar's chikari strings for a raga, string 1 first.

    Strings 1-2 are Sa (the stroke's body); strings 3-4 carry the raga's own colour — the
    drone companion the tanpura would take, and the raga's vadi. A raga whose tuning does not
    follow that convention is listed explicitly in `_CHIKARI_TUNINGS`. Every returned swara is
    legal in the raga, so a chikari stroke can never sound outside the grammar. Pure.
    """
    if raga in _CHIKARI_TUNINGS:
        return list(_CHIKARI_TUNINGS[raga])
    allowed = set(RAGAS[raga]["allowed"])
    companion = drone_swaras(raga)[-1]
    vadi = RAGAS[raga]["vadi"]
    colour = [sw for sw in (companion, vadi) if sw in allowed and sw != "S"]
    return ["S", "S", *dict.fromkeys(colour)]


def drone_swaras(raga: str) -> list[str]:
    """The tanpura's drone tones for a raga — Sa plus one companion.

    The companion is chosen from `_DRONE_COMPANIONS` (Pa, else Ma, else Ni), but
    ONLY if it is in this raga's allowed set, so the drone can never sound a swara
    the raga forbids — the drone is legal by construction and the validator never
    flags it. Returns just ["S"] if no companion is legal. Pure: reads only the
    encoded raga facts, invents nothing.
    """
    allowed = set(RAGAS[raga]["allowed"])
    for companion in _DRONE_COMPANIONS:
        if companion in allowed:
            return ["S", companion]
    return ["S"]


def resting_swaras(raga: str) -> set[str]:
    """The raga's resting / cadence notes — where a phrase can SETTLE: Sa (the home, always a
    nyas), plus the vadi and samvadi (the raga's two most prominent swaras, and so its natural
    resting points).

    Used to snap a trading solo's handoff to a CLEAN LANDING — a taan phrase ends on a resting
    note and the next voice starts fresh (Sujit's steer: 'the previous solo ends on a beat /
    resting note / Sa'). Pure: reads only the encoded, source-verified raga facts, invents
    nothing. A dedicated per-raga `nyas` set could refine this later; Sa + vadi + samvadi is a
    faithful, grounded approximation.
    """
    r = RAGAS[raga]
    return {"S", r["vadi"], r["samvadi"]}


def scale_step_up(swara: str, raga: str, steps: int = 1) -> tuple[str, int]:
    """The swara `steps` scale-degrees above `swara` in the raga's ascending ladder,
    with the octave delta (0, +1, ...) when it wraps past Sa.

    Used to harmonize a melodic line INSIDE the raga (a 'third' is steps=2): the
    result is drawn from the raga's own allowed swaras (which are stored in ascending
    semitone order), so a harmony built on it is legal and idiomatic BY CONSTRUCTION.
    The interval is the raga's own scale-third, so it varies — minor or major in a
    seven-note raga, wider in a pentatonic like Malkauns — which is correct diatonic
    behaviour, not a bug. `swara` must be a legal swara of the raga.
    """
    allowed = RAGAS[raga]["allowed"]
    idx = allowed.index(swara) + steps
    return allowed[idx % len(allowed)], idx // len(allowed)


def directional_varjya(raga: str) -> dict[str, str]:
    """Swaras this raga admits in only ONE melodic direction, DERIVED from the verified
    aroha/avaroha (no new facts): a swara absent from the aroha is DESCENT-only (value
    "avaroha" — e.g. Bageshree's P and R, touched only on the way down), one absent from
    the avaroha is ASCENT-only (value "aroha"). Empty for a raga whose swaras all move
    freely. Pure: reads only the encoded, source-verified ladders.
    """
    r = RAGAS[raga]
    aroha, avaroha = set(r["aroha"]), set(r["avaroha"])
    out: dict[str, str] = {}
    for sw in r["allowed"]:
        if sw not in aroha:
            out[sw] = "avaroha"
        elif sw not in avaroha:
            out[sw] = "aroha"
    return out


def direction_violations(seq: list[tuple[str, int]], raga: str) -> list[str]:
    """Directional-varjya violations over ONE melodic line — human-readable, for the
    generator guardrails (the early bounded retry). `seq` is the line's sounding
    (swara, octave) pairs in playing order; give a meend its own step (note, then target)
    so a glide INTO a one-directional swara faces the rule too.

    Scope (deliberate): this guards the lines an LLM WRITES (lead phrase, gat parts, riff
    cycle). It is NOT part of `validate_composition` — code-derived voices (the
    raga-diatonic third harmony, the bass's root-following) mirror a legal line in ways a
    naive entered-from check can mis-flag, and a hard validator rule would turn those
    into forced-revise loops with no agent at fault. Re-striking the same pitch is free;
    only a strictly lower->higher entry into a descent-only swara (or the mirror) flags.
    """
    rules = directional_varjya(raga)
    if not rules:
        return []
    out: list[str] = []
    prev: int | None = None
    for sw, oct_ in seq:
        pitch = semitone(sw) + 12 * oct_ if sw in SWARAS else None
        if pitch is None:                     # an illegal swara — the set check owns that
            prev = None
            continue
        rule = rules.get(sw)
        if rule == "avaroha" and prev is not None and prev < pitch:
            out.append(f"'{sw}' is approached from below — in this raga '{sw}' is "
                       f"DESCENT-only (the aroha skips it): touch it only on the way "
                       f"down, reached from above")
        elif rule == "aroha" and prev is not None and prev > pitch:
            out.append(f"'{sw}' is approached from above — in this raga '{sw}' is "
                       f"ASCENT-only (the avaroha skips it): touch it only on the way "
                       f"up, reached from below")
        prev = pitch
    return out


def ascent_step(swara: str, raga: str) -> tuple[str, int]:
    """The nearest swara ABOVE `swara` this raga lets you ENTER from below — one scale
    step up (`scale_step_up`), skipping any descent-only swara exactly as the aroha
    skips it. Returns (swara, octave_delta). The seat for any code gesture that RISES
    INTO a pitch (a riff bend's apex): legal by set AND by direction. Pure."""
    rules = directional_varjya(raga)
    steps = 1
    sw, oct_d = scale_step_up(swara, raga, steps)
    while rules.get(sw) == "avaroha":
        steps += 1
        sw, oct_d = scale_step_up(swara, raga, steps)
    return sw, oct_d


def validate_composition(comp: dict) -> list[dict]:
    """Return a list of grammar violations (empty == clean).

    Each violation is what the Guru-critic quotes back to the offending agent.
    Drums carry no pitch, so they're skipped.
    """
    raga = RAGAS[comp["raga"]]
    allowed = set(raga["allowed"])
    violations = []
    for layer in comp["layers"]:
        if layer.get("role") in ("drums", "tabla"):   # percussion carries no pitch
            continue
        for n in layer.get("notes", []):
            # Every pitch that actually sounds faces the grammar — the main
            # swara, each kan (grace note), each riff CHORD tone (sounded with the
            # root), and a meend's TARGET swara (the note you land on). The guardrail
            # can't have a blind spot for ornaments or chords. The microtones a meend
            # sweeps through are not notes, so not checked.
            checks = [(n["swara"], "note")]
            checks += [(g, "grace") for g in n.get("grace", [])]
            checks += [(c, "chord") for c in n.get("chord", [])]
            tsw = n.get("meend_swara")
            if tsw is not None:
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
