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

from typing import Final

from shruti import offset_cents

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
        # Kan (2026-10-18): the andolit r and d are approached FROM ABOVE in descent — Parrikar
        # "G M P G M (G)r, S" and "G M (N)d, d, P"; Ragajunglism "GmG\\r~S", "NSN\\d~P"; van der
        # Meer & Rao measured Gundecha's dha "attacked from above". No aroha kan: r is alpa there.
        "kan": {
            "r": {"avaroha": "G"},
            "d": {"avaroha": "N"},
        },
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
        # Kan (2026-10-12): Ni takes a Sa touch (Parrikar "P (S')n, n S'" — the antara launch,
        # ascending; Tanarang "adjacent Shadj is used as a Kan-Swar"); Ga takes a Ma touch
        # (Parrikar descending "(M)g" — his M = our m; Tanarang "Gandhar is rendered with
        # madhyam as a Kan-Swar"). Only the direction a source SHOWS is encoded.
        "kan": {
            "n": {"aroha": "S"},
            "g": {"avaroha": "m"},
        },
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
        "andolan": ["g"],   # ga sways UP toward ma (Parrikar "(m)g"; Sujit's guruji, oral tradition — see ANDOLAN_TOWARD)
        "ornaments": [],  # lyrical/romantic — light murki possible but not an identity ornament
        # Kan (2026-10-13): Ga takes its colour from Ma ABOVE, whichever way the line arrives —
        # Parrikar "(m)g", Ragajunglism "(m)g (m)gm" (rising into Ma), Sujit's guruji (oral
        # tradition: "Ga approached from above"). Arriving FROM Ma it is a slow release instead
        # (`gestures.GA_MA_RELEASE`), which claims the note before the kan pass sees it.
        "kan": {
            "g": {"aroha": "m", "avaroha": "m"},
        },
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
        # Kan (2026-10-12): descending, komal ga takes a Sa touch — Tanarang "m (S)g S";
        # Parrikar "M (S)g->S" (his M = our m).
        "kan": {
            "g": {"avaroha": "S"},
        },
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
        "andolan": ["r"],   # komal re sways UP toward komal ga (ITC; Parrikar "S, r<->g")
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


# ---------------------------------------------------------------------------
# NYAS — where a phrase may come to REST (researched 2026-10-11).
#
# A nyas is a swara the performer pauses on to "build and subsequently sustain the format of
# a rag"; it delimits phrases (A.K. Dey, *Nyasa in raga*, via Gulati et al. 2014). Two facts
# shape this table:
#   * a long HOLD is not automatically a rest — Parrikar separates deergha bahutva (elongation)
#     from nyasa bahutva (resting): Darbari's andolit g and d are long holds, not endings;
#   * resting can depend on DIRECTION — Bhairav's komal re and Bageshree's ga rest only in
#     the avaroha (Tanarang lists rests per direction; Parrikar names them).
#
# Fields per raga:
#   core          the rests the sources AGREE on — the ones the prompt leads with
#   permitted     every rest at least one strong source gives (a superset of core). The phrase-
#                 ending check enforces THIS, not core: three rules last month were tighter than
#                 the tradition and each was refuted by a real gat, so the check stays loose
#   descent_only  rests only when reached from above (the avaroha)
#   ascent_only   rests only when reached from below (the aroha)
#   avoid         swaras a source names as damaging/weak as a rest — rejected outright
#   note          discrepancies and coverage, so the encoding stays auditable
#   sources       T = Tanarang "Vishranti Sthan" field, P = Parrikar, DR = Deepak Raja,
#                 RJ = Ragajunglism (weaker; often quotes Parrikar)
# ---------------------------------------------------------------------------

NYAS: dict[str, dict] = {
    "bhairav": {
        "core": ["S", "d", "P"], "permitted": ["S", "d", "P", "r", "m"],
        "descent_only": ["r"], "ascent_only": [], "avoid": [],
        "note": "r rests in the avaroha only (T: 'S;m;P;d; - S';d;P;r;'; P: 'andolita komal "
                "rishab in the avarohi'). P: Parrikar descent-only, Tanarang both ways — "
                "permitted both. m: Tanarang only. No source flags G as avoided.",
        "sources": ["https://tanarang.com/raag-bhairav/",
                    "https://www.parrikar.org/hindustani/bhairav/", "Ragajunglism"],
    },
    "bhairavi": {
        "core": ["S", "P"], "permitted": ["S", "P", "g", "m"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "P: 'The nyasa swaras are S, g and P; in addition, M and d are often sought for "
                "elongation' (d is elongated, not a rest). T: 'S;m;P; - S';P;m;'. g (P) vs m (T).",
        "sources": ["https://www.parrikar.org/hindustani/bhairavi/",
                    "https://tanarang.com/raag-bhairavi/"],
    },
    "bhimpalasi": {
        "core": ["m", "S"], "permitted": ["m", "S", "P"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "P: 'preponderance of the madhyam (nyasa bahutva)'; R and D are deergha bahutva "
                "(elongated) in the avaroha, not rests. T: 'S;m;P; - S';P;m;'.",
        "sources": ["https://www.parrikar.org/hindustani/bhimpalasi/",
                    "https://tanarang.com/raag-bhimpalasi/", "Ragajunglism"],
    },
    "darbari": {
        "core": ["R", "P", "S"], "permitted": ["R", "P", "S"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "P: 'rishab serves as the vadi, an important nyasa sthana, while the pancham "
                "provides repose'. T: 'S;R;P; - S';P;R;'. FLAG: g and d are excluded only because "
                "no source lists them — they are long andolit holds that resolve onward "
                "(g -> m R S, d -> n P), an inference from absence.",
        "sources": ["https://www.parrikar.org/hindustani/kanada/",
                    "https://tanarang.com/raag-darbari-kanada/"],
    },
    "malkauns": {
        "core": ["m", "S", "g"], "permitted": ["m", "S", "g", "d", "n"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "P: 'each one of its swaras is considered apposite for nyasa… madhyam… primus "
                "inter pares'; RJ: all five rest both ways. FLAG: T lists only S g m.",
        "sources": ["https://www.parrikar.org/hindustani/malkauns/",
                    "https://tanarang.com/raag-malkauns/", "Ragajunglism"],
    },
    "kirwani": {
        "core": ["P", "R", "S"], "permitted": ["P", "R", "S"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "T: 'S R P - S' P R'; indianclassicalmusic.com 'Nyaas Swars: s, r, p'; RJ: shuddha "
                "Re a popular resting tone. FLAG: one strong source only (no Parrikar/Raja page).",
        "sources": ["https://tanarang.com/raag-kirwani/", "indianclassicalmusic.com",
                    "Ragajunglism"],
    },
    "charukeshi": {
        "core": ["d", "S"], "permitted": ["d", "S", "R", "G", "m", "P"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "P: 'strength and importance of the dhaivat (nyasa sthana)'; T: 'R;G;m;P;d;' (Sa "
                "implicit per Tanarang's glossary). FLAG: R G m P rest on Tanarang alone.",
        "sources": ["https://www.parrikar.org/hindustani/charukeshi/",
                    "https://tanarang.com/raag-charukeshi/"],
    },
    "bageshree": {
        "core": ["m", "D", "S"], "permitted": ["m", "D", "S", "g"],
        "descent_only": ["g"], "ascent_only": [], "avoid": ["P"],
        "note": "P: 'a modest pause on g is prescribed' in the avaroha, 'nyasa bahutva role of D', "
                "madhyam the 'melodic centre of gravity'; T: 'S;m;D; - S';D;m;g;' (g in the "
                "descent list only). P is varjit in the aroha and only touched in descent.",
        "sources": ["https://www.parrikar.org/hindustani/bageshree/",
                    "https://tanarang.com/raag-bageshree/", "Ragajunglism"],
    },
    "puriya_dhanashree": {
        "core": ["P", "G", "S"], "permitted": ["P", "G", "S", "N", "r"],
        "descent_only": ["r"], "ascent_only": ["N"], "avoid": [],
        "note": "P: 'the breath of Pooriya Dhanashree's life is pancham'; T: 'S;G;P;N; - "
                "S';P;G;r;'. FLAG: N (ascent) and r (descent) are Tanarang only; RJ calls N a "
                "launchpoint. Sa is passed through mid-phrase and closes via M G r S.",
        "sources": ["https://www.parrikar.org/hindustani/poorvi/",
                    "https://tanarang.com/raag-puriya-dhanashree/", "Ragajunglism"],
    },
    "yaman": {
        "core": ["S", "G", "N", "P"], "permitted": ["S", "G", "N", "P", "R"],
        "descent_only": [], "ascent_only": [], "avoid": ["D"],
        "note": "P: 'nyasa sthanas – S, R, G, P, N… [dhaivat] a nyasa there is damaging to the "
                "raga dharma'; T: 'S;G;N; - S';N;P;G;'. m is elongated, not a rest. R is "
                "Parrikar only.",
        "sources": ["https://www.parrikar.org/hindustani/kalyan/",
                    "https://tanarang.com/raag-yaman/", "Ragajunglism"],
    },
    "chandrakauns": {
        "core": ["S", "m", "N"], "permitted": ["S", "m", "N"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "T: 'S;m;N; - S';N;m;'; P (in the Malkauns article): 'the nyasa on mandra nishad "
                "via M g S N'. g and d only implied by 'lakshanas stay true to Malkauns' — not added.",
        "sources": ["https://tanarang.com/raag-chandrakauns/",
                    "https://www.parrikar.org/hindustani/malkauns/"],
    },
    "jog": {
        "core": ["S", "G", "P", "m"], "permitted": ["S", "g", "G", "m", "P", "n"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "MODERN recension (Sujit's choice, 2026-10-11). DR: traditionally 'phrases are "
                "permitted to terminate only on S, [shuddha] G, and P… contemporary Jog… treating "
                "all the swaras as permissible terminal points'; P: 'Pancham is a nyasa swara', "
                "'empowering M and displacing P'. T: 'G;m;P; - P;m;G;'.",
        "sources": ["Deepak Raja (swaratala.blogspot.com), Jog",
                    "https://www.parrikar.org/hindustani/jog/", "https://tanarang.com/raag-jog/"],
    },
    "marwa": {
        "core": ["r", "D"], "permitted": ["r", "D"],
        "descent_only": [], "ascent_only": [], "avoid": ["S"],
        "note": "P: 'Both the swaras [r, D] are full-blown nyasa locations… langhan of shadaj in "
                "both arohi and avarohi'; T: 'r;D; - D;r;', 'skipping of Shadj'; DR: base Sa 'only "
                "as an isolated swara'. Sa is held back for the closing motion only (RJ). The "
                "contemporary D-nyas sits in the mandra (DR).",
        "sources": ["https://www.parrikar.org/hindustani/marwa/",
                    "https://tanarang.com/raag-marwa/", "Deepak Raja (swaratala.blogspot.com), Marwa"],
    },
    "todi": {
        "core": ["g", "d", "S"], "permitted": ["g", "d", "S", "P"],
        "descent_only": [], "ascent_only": [], "avoid": [],
        "note": "P: 'r→g, with a nyasa on the gandhar, is vital', 'dominance of the dhaivat "
                "(nyasa bahutva)', pancham a nyasa for some, 'others reserve it for repose in "
                "avarohi'; T: 'S;g;d; - d;g;S;'. r lingers before dissolving on S — not terminal.",
        "sources": ["https://www.parrikar.org/hindustani/todi/",
                    "https://tanarang.com/raag-todi/", "Deepak Raja (swaratala.blogspot.com), Todi"],
    },
}


def nyas_problem(raga: str, swara: str, from_below: bool | None) -> str | None:
    """Why `swara` cannot END a phrase in `raga` — or None when it may. `from_below` is how the
    line arrived (True = rising into it, False = falling, None = unknown/repeated), which
    decides the direction-only rests. Pure."""
    n = NYAS[raga]
    if swara in n["avoid"]:
        return f"'{swara}' is a weak swara in this raga — it must never be a resting point"
    if swara not in n["permitted"]:
        rests = " ".join(n["permitted"])
        return f"'{swara}' is not a nyas of this raga — phrases rest on {rests}"
    if swara in n["descent_only"] and from_below:
        return f"'{swara}' rests only in the AVAROHA — arrive on it from above, not rising into it"
    if swara in n["ascent_only"] and from_below is False:
        return f"'{swara}' rests only in the AROHA — arrive on it from below"
    return None


def render_nyas(raga: str) -> str:
    """The raga's resting swaras as one prompt line — core first, then the conditions."""
    n = NYAS[raga]
    extra = [s for s in n["permitted"] if s not in n["core"]]
    parts = [f"rest on {' '.join(n['core'])}"]
    if extra:
        parts.append(f"also {' '.join(extra)}")
    if n["descent_only"]:
        parts.append(f"{' '.join(n['descent_only'])} only coming DOWN")
    if n["ascent_only"]:
        parts.append(f"{' '.join(n['ascent_only'])} only going UP")
    if n["avoid"]:
        parts.append(f"never rest on {' '.join(n['avoid'])}")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# REGISTER — where a raga LIVES (researched 2026-10-12).
#
# A raga is not only its notes but where it spends its time: Darbari is developed in the mandra
# and madhya and gets its gravity from the lower tetrachord; Adana, on the same notes, is
# uttaranga-pradhan. A GPT review of the 2026-10-12 Darbari render found the lead never went
# below mandra Ni — the composer had never been told, and Rasik could not see the register.
#
# Fields per raga (an entry exists ONLY where >=2 approved sources agree — no entry, no claim):
#   saptak   the octaves the raga is mainly developed in: mandra / madhya / taar
#   anga     which tetrachord carries its weight: poorvanga (S..m) / uttaranga (P..S') / balanced
#   note     the verbatim evidence and any discrepancy, so the encoding stays auditable
#   sources  P = Parrikar, T = Tanarang ("expanded in ... Saptaks"), ITC = ITC-SRA
# ---------------------------------------------------------------------------

SAPTAKS: Final = ("mandra", "madhya", "taar")
ANGAS: Final = ("poorvanga", "uttaranga", "balanced")

REGISTER: dict[str, dict] = {
    "darbari": {
        "saptak": ["mandra", "madhya"], "anga": "poorvanga",
        "note": "P: 'Darbari is a poorvanga-pradhana raga, with most melodic activity "
                "concentrated in the lower registers.' T: 'is generally expanded in Mandra and "
                "Madhya Saptaks'. ITC (Falguni Mitra, archived): 'concentrates on the lower and "
                "middle registers'; 'the development in the mandra saptak ... is very absorbing'.",
        "sources": ["https://www.parrikar.org/hindustani/kanada/",
                    "https://tanarang.com/raag-darbari-kanada/",
                    "http://itcsra.org/sra_raga/jaunpuri_darbari_kanhada_adana.html (Wayback)"],
    },
}

# ---------------------------------------------------------------------------
# CHARACTER — how a raga TREATS its swaras, beyond its notes (researched 2026-10-12).
#
# Movement rules a composer needs and the other tables do not carry: a swara skipped on the way
# up, a characteristic leap, a centre of gravity, a phrase that keeps returning. Only rules that
# >=2 approved sources state (Parrikar, Tanarang, ITC-SRA) are here; each is written in OUR
# notation (Parrikar writes M for shuddha Ma — the reverse of ours — so his "(M)g" is our "(m)g").
# These are told to the LLMs, never enforced: they describe idiom, and the legality rules live
# in the aroha/avaroha and the direction rule. Deliberately LEFT OUT, both sourced: Bhairavi's
# "all twelve swaras" (our validator forbids the vivadi notes it would invite) and Bageshree's
# Re in a vakra rise "R g m" and Pa inside the cluster "m P D (m)g" (our direction rule makes R
# and P descent-only, so the guardrails would reject both). DECIDED: keep the direction rule
# STRICT (Sujit, 2026-10-12) — these two sourced phrases stay out by choice, not oversight.
# Kirwani has one approved source only (Tanarang), so it has no entry.
# ---------------------------------------------------------------------------

_P: Final = "https://www.parrikar.org/hindustani/"
_T: Final = "https://tanarang.com/raag-"

CHARACTER: dict[str, list[dict]] = {
    "darbari": [
        {"text": "komal dha is skipped in a straight descent: no plain n d P — touch d vakra "
                 "(S' d n P)", "sources": [f"{_P}kanada/", f"{_T}darbari-kanada/"]},
        {"text": "a gamak- and meend-pradhan raga: gamaks and meends are used widely, with care",
         "sources": [f"{_T}darbari-kanada/", "ITC-SRA (Falguni Mitra, archived)"]},
        {"text": "the g m R S and d n P cells come back again and again",
         "sources": ["ITC-SRA (Falguni Mitra, archived)", f"{_T}darbari-kanada/"]},
    ],
    "puriya_dhanashree": [
        {"text": "Pa is the centre of all development", "sources": [f"{_P}poorvi/",
                                                                   f"{_T}puriya-dhanashree/"]},
        {"text": "ascent launches from mandra N, skipping Sa: N r G M P",
         "sources": [f"{_P}poorvi/", f"{_T}puriya-dhanashree/"]},
        {"text": "the reiterated G M r G, returning to Pa (P M G M r G P), is essential",
         "sources": [f"{_P}poorvi/", f"{_T}puriya-dhanashree/"]},
        {"text": "the taar sentence S' N S' r' N d P", "sources": [f"{_P}poorvi/",
                                                                  f"{_T}puriya-dhanashree/"]},
    ],
    "yaman": [
        {"text": "ascent skips Sa from mandra N (N R G) and Pa (M D N)",
         "sources": [f"{_P}kalyan/", f"{_T}yaman/"]},
    ],
    "chandrakauns": [
        {"text": "shuddha N is prominent (tension); phrases rest on mandra N via m g S N",
         "sources": [f"{_P}malkauns/", f"{_T}chandrakauns/"]},
    ],
    "jog": [
        {"text": "shuddha G rising, komal g falling; the two meet in P m G m G g S",
         "sources": [f"{_P}jog/", f"{_T}jog/"]},
        {"text": "the meend g -> S is its signpost", "sources": [f"{_P}jog/", f"{_T}jog/"]},
    ],
    "marwa": [
        {"text": "Sa is skipped in both ascent and descent", "sources": [f"{_P}marwa/",
                                                                       f"{_T}marwa/"]},
        {"text": "N is weak (alpa), often skipped on the way to taar Sa: M D S'",
         "sources": [f"{_P}marwa/", f"{_T}marwa/"]},
    ],
    "todi": [
        {"text": "r and g are joined by meend: r -> g resting on g; g -> r lingers on r "
                 "before Sa", "sources": [f"{_P}todi/", f"{_T}todi/"]},
        {"text": "Pa is sparse: skip it rising (M d N S'), use it coming down",
         "sources": [f"{_P}todi/", f"{_T}todi/", "ITC-SRA samay-raga"]},
    ],
    "bhairav": [
        {"text": "Pa is skipped rising but prominent descending; r is light rising",
         "sources": [f"{_P}bhairav/", f"{_T}bhairav/"]},
    ],
    "bhimpalasi": [
        {"text": "R and D are skipped rising and dwelt on descending",
         "sources": [f"{_P}bhimpalasi/", f"{_T}bheempalasi/"]},
        {"text": "Ma is the centre: phrases keep returning to it (m g m g R S)",
         "sources": [f"{_P}bhimpalasi/", f"{_T}bheempalasi/"]},
    ],
    "malkauns": [
        {"text": "Ma is the centre of gravity", "sources": [f"{_P}malkauns/", f"{_T}malkauns/"]},
        {"text": "the leap Sa -> Ma (mandra d n S m) is characteristic",
         "sources": [f"{_P}malkauns/", f"{_T}malkauns/"]},
    ],
    "charukeshi": [
        {"text": "d is strong, a resting note", "sources": [f"{_P}charukeshi/",
                                                           f"{_T}charukeshi/"]},
        {"text": "Pa is skipped now and then (d m in descent)",
         "sources": [f"{_P}charukeshi/", f"{_T}charukeshi/"]},
        {"text": "borrowed colours: the Bhairav cluster G m d P, the Nat poorvanga S R G m and "
                 "R G m R S", "sources": [f"{_P}charukeshi/", f"{_T}charukeshi/"]},
    ],
    "bageshree": [
        {"text": "Ma is the centre of gravity; D rests and the D-m pairing is characteristic "
                 "(m D n D m)", "sources": ["https://www.parrikar.org/?p=702", f"{_T}bageshree/"]},
        {"text": "a modest pause on g when descending",
         "sources": ["https://www.parrikar.org/?p=702", f"{_T}bageshree/"]},
        {"text": "Pa is never used rising; it lives only inside descending movement",
         "sources": ["https://www.parrikar.org/?p=702", f"{_T}bageshree/"]},
    ],
}


def render_kan(raga: str) -> str | None:
    """How the raga's kan-bearing swaras are approached, as one prompt line, or None:
    `g takes (R) rising, (m) falling` — only the directions the sources show."""
    words = {"aroha": "rising", "avaroha": "falling"}
    parts = [f"{sw} takes " + ", ".join(f"({t}) {words[d]}" for d, t in touch.items())
             for sw, touch in RAGAS[raga].get("kan", {}).items()]
    return "; ".join(parts) or None


def render_character(raga: str) -> str | None:
    """The raga's sourced treatment rules as one prompt line, or None."""
    rules = CHARACTER.get(raga)
    return "; ".join(r["text"] for r in rules) if rules else None


_ANGA_TEXT: Final = {
    "poorvanga": "the LOWER tetrachord ({tetra}) carries its weight",
    "uttaranga": "the UPPER tetrachord ({tetra}) carries its weight",
    "balanced": "both tetrachords carry it",
}


def render_register(raga: str) -> str | None:
    """Where the raga lives, as one prompt line — None when no verified entry exists (the
    prompt then says nothing rather than guessing). Phrased as composing guidance: a saptak
    the raga is developed in is somewhere to DWELL, one it is not is somewhere to visit."""
    entry = REGISTER.get(raga)
    if entry is None:
        return None
    lives = " and ".join(s.upper() for s in entry["saptak"])
    parts = [f"developed mainly in the {lives} saptak{'s' if len(entry['saptak']) > 1 else ''}"]
    if "mandra" in entry["saptak"]:
        parts.append("DWELL below home Sa (octave -1), do not just touch it")
    if "taar" not in entry["saptak"]:
        parts.append("the taar is a peak to visit, not a home")
    tetra = _tetrachord(raga, entry["anga"])
    parts.append(_ANGA_TEXT[entry["anga"]].format(tetra=" ".join(tetra)))
    return "; ".join(parts)


def _tetrachord(raga: str, anga: str) -> list[str]:
    allowed = RAGAS[raga]["allowed"]
    if anga == "poorvanga":
        return [s for s in allowed if SWARAS[s] < SWARAS["P"]]
    return [s for s in allowed if SWARAS[s] >= SWARAS["P"]] + ["S'"]


# ---------------------------------------------------------------------------
# ANDOLAN DIRECTION — which neighbour an andolit swara swings toward (researched 2026-10-11).
#
# ITC: andolan is "a gentle swing or oscillation that starts from a fixed note and touches the
# periphery of an adjacent note", and "andolit swars are raga specific" — the neighbour can be
# ABOVE or BELOW. The renderer used to dip below every andolit note; Bageshree's ga and Todi's re
# swing UP. Depth is a share of the gap to that neighbour (no source measures it in cents).
#   below  toward the next raga swara beneath it      above  toward the next one above it
# ---------------------------------------------------------------------------

ANDOLAN_TOWARD: dict[str, dict[str, str]] = {
    # Bhairav (corrected 2026-10-18): the sway lives INSIDE the swara, leaning UP from where it
    # lands — van der Meer & Rao (Microtonality in Indian Music) measured Gundecha's dha within
    # 796-828 cents (a ~32 c span): attacked from above, a bounce up, a slow landing, a hump up
    # before Pa; Parrikar and Ragajunglism write r/d approached from G/N above. No source swings it
    # down to Sa/Pa (the old "below" turned 50 c down, on pitch Bhairav does not own). FLAG: ITC
    # says the re is sung "within the periphery of S" — a statement of its low intonation, read here
    # as pitch, not as a swing toward Sa.
    "bhairav": {"r": "above", "d": "above"},
    # AUTRIM/NCPA: ga's movements "occur between Re and Ga"; Deepak Raja: oscillating "between
    # Re–ga and Pa–dha" — both swing down toward their lower neighbour.
    "darbari": {"g": "below", "d": "below"},
    # Parrikar: "(m)g" — ga takes its kan from ma above, with "a modest pause on g"; Sujit's
    # guruji (oral tradition, 2026-10-11): a slow Ma->Ga reverse bend or andolan on Ga is common.
    "bageshree": {"g": "above"},
    # ITC: Todi's re sits "in the periphery of komal gandhar", at a higher shruti; Parrikar writes
    # the raganga as "S, r<->g". (Tanarang calls the same r<->g movement meend.)
    "todi": {"r": "above"},
}


# How far an andolit swara's sway turns, in semitones, where a source measured it (otherwise the
# expression pass derives it from the neighbour: half way to a semitone, 0.3 toward a whole tone).
# Bhairav: van der Meer & Rao's measured dha spans ~32 cents, so the turn is ~20 c above the landing.
ANDOLAN_DEPTH_ST: dict[str, float] = {"bhairav": 0.2}

# Where in the melodic direction a raga's andolan belongs. Bhairav: on held r/d in DESCENT
# (Parrikar "(G)r S", "(N)d P"; r is "alpa and often omitted in arohi phrases"); a re or dha the
# line rises THROUGH (S r G) is played plain. No source forbids it in a turn (S r S) — FLAG.
ANDOLAN_ONLY_IN: dict[str, str] = {"bhairav": "avaroha"}

# How many swings an andolan carries, where a source counts them (the renderer otherwise fits one or
# two slow waves). Darbari: van der Meer & Rao ("Microtonality in Indian Music") measured its komal
# dha undulating "usually two or three times" (one vocalist, two renditions); Sujit (sitar,
# 2026-10-18): Darbari's andolan generally takes 2-3 swings, a longer sway than one. FLAG: no source
# counts the ga's swings, nor any of Bhairav's (left at the default).
ANDOLAN_SWINGS: dict[str, tuple[int, int]] = {"darbari": (2, 3)}


def andolan_neighbour_st(raga: str, swara: str) -> int:
    """The signed interval, in semitones, from an andolit swara to the neighbour it swings
    toward — negative below, positive above (the next raga swara in that direction). Pure."""
    toward = ANDOLAN_TOWARD.get(raga, {}).get(swara, "below")
    allowed = RAGAS[raga]["allowed"]
    i = allowed.index(swara)
    if toward == "above":
        nxt = allowed[(i + 1) % len(allowed)]
        return (SWARAS[nxt] - SWARAS[swara]) % 12 or 12
    prev = allowed[i - 1]
    return -((SWARAS[swara] - SWARAS[prev]) % 12 or 12)


# KHADA swaras — a raga sung "direct and unwavering, shorn of delicacies and meends" (Parrikar on
# Marwa). Code adds no oscillating ornament (gamak) there. Single source — an EXCLUSION, which
# errs on the plain side.
KHADA_RAGAS: frozenset[str] = frozenset({"marwa"})


# INTONATION — each swara's pitch off equal temperament, in cents (negative = lower), applied by
# code to every sitar note (`crew/expression.py`): a sitar's frets sit at the raga's shrutis.
#
# Sujit, 2026-10-12: notes are calculated by the HINDUSTANI 22-shruti system (`src/shruti.py`),
# all of Darbari's swaras, its Ga at Dayavanti 32/27. Darbari's komal Ga is the textbook ATI-KOMAL
# swara (English Wikipedia "Shruti (music)": "the most well-known example"; ragajunglism.org;
# Parrikar: "much is made of its ati-komal nature") — the LOWER of komal Ga's two shrutis,
# Dayavanti 32/27 (294 c), not Ranjani 6/5 (316 c); its komal Dha likewise Kshiti 128/81 (792 c),
# not Rakta 8/5. The deeper "low Ga" the ear hears comes from the andolan sinking below it.
# Other ragas stay equal-tempered until their shrutis are sourced.
SHRUTI_OF: dict[str, dict[str, int]] = {
    "darbari": {"S": 1, "R": 5, "g": 6, "m": 10, "P": 14, "d": 15, "n": 19},
}
INTONATION: dict[str, dict[str, float]] = {
    raga: {sw: offset_cents(SWARAS[sw], n) for sw, n in table.items() if offset_cents(SWARAS[sw], n)}
    for raga, table in SHRUTI_OF.items()
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

    toward = ANDOLAN_TOWARD.get(name, {})
    if set(toward) != set(raga.get("andolan", [])):
        problems.append("ANDOLAN_TOWARD must name a direction for exactly the andolit swaras")
    if any(v not in ("above", "below") for v in toward.values()):
        problems.append("an andolan direction is 'above' or 'below'")

    nyas = NYAS.get(name)
    if nyas is None:
        problems.append("no NYAS entry")
    else:
        for key in ("core", "permitted", "descent_only", "ascent_only", "avoid"):
            check_phrase(nyas[key], f"nyas.{key}")
        if not set(nyas["core"]) <= set(nyas["permitted"]):
            problems.append("nyas.core must be a subset of nyas.permitted")
        if set(nyas["avoid"]) & set(nyas["permitted"]):
            problems.append("a swara cannot be both a permitted rest and avoided")
        directional = set(nyas["descent_only"]) | set(nyas["ascent_only"])
        if not directional <= set(nyas["permitted"]):
            problems.append("a direction-only rest must also be permitted")
        if len(nyas["sources"]) < 2:
            problems.append("nyas needs at least two sources")

    register = REGISTER.get(name)
    if register is not None:
        if not register["saptak"] or not set(register["saptak"]) <= set(SAPTAKS):
            problems.append(f"register.saptak must be a non-empty subset of {SAPTAKS}")
        if register["anga"] not in ANGAS:
            problems.append(f"register.anga must be one of {ANGAS}")
        if len(register["sources"]) < 2:
            problems.append("register needs at least two sources")

    for sw, touch in raga.get("kan", {}).items():
        if not touch or set(touch) - {"aroha", "avaroha"}:
            problems.append(f"kan.{sw} names an aroha and/or avaroha touch, nothing else")
        check_phrase([sw, *touch.values()], f"kan.{sw}")

    for i, rule in enumerate(CHARACTER.get(name, [])):
        if len(rule["sources"]) < 2:
            problems.append(f"character[{i}] needs at least two sources")

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
    # A swara the raga drops on the way UP is not a resting tone, whatever the convention
    # says. Bageshree is the case that exposed this: its Pancham is present but vakra and
    # avaroha-only (dropped from the aroha, encoded above), with Ma as vadi and Dha the
    # strong nyas — yet a Pa-first preference list droned Pa continuously. Measured on the
    # 2026-09-14 live render: the tanpura sounded Sa+Pa for the whole piece while the clean
    # guitar, which reads the same function, spent 34 of its 72 notes on Pa. The raga's most
    # deliberately weakened swara was its most-sounded accompaniment tone.
    descent_only = {sw for sw, direction in directional_varjya(raga).items()
                    if direction == "avaroha"}
    for companion in _DRONE_COMPANIONS:
        if companion in allowed and companion not in descent_only:
            return ["S", companion]
    for companion in _DRONE_COMPANIONS:          # every candidate is descent-only: take one
        if companion in allowed:
            return ["S", companion]
    return ["S"]


def resting_swaras(raga: str) -> set[str]:
    """The raga's resting / cadence notes — where a phrase can SETTLE: every NYAS a strong
    source permits, plus Sa unless the raga deliberately weakens it (Marwa). Direction is NOT
    applied here; `nyas_problem` owns the direction-only rests.

    This replaced the old Sa + vadi + samvadi approximation (2026-10-11), which was tighter than
    the tradition — it rejected a Yaman head cadencing on Pa, a nyas in every source. Used for a
    cell's final cadence (mukhada, taan) and a trading solo's clean handoff. Pure."""
    n = NYAS[raga]
    return set(n["permitted"]) | ({"S"} - set(n["avoid"]))


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


def half_step_pairs(raga: str) -> list[tuple[str, str]]:
    """The raga's HALF-STEP NEIGHBOURS — pairs of allowed swaras exactly one semitone apart,
    as (lower, upper), in ascending order, including Ni-to-upper-Sa across the octave. DERIVED
    from the verified allowed swaras (arithmetic, no new facts). For a riff these are the
    one-fret power-chord moves metal grinds on: Bhairav's S-r and P-d are its signature komal
    resolutions (r falls to S, d falls to P). Empty for a raga with no semitone steps
    (Malkauns). Pure."""
    allowed = RAGAS[raga]["allowed"]
    semis = {SWARAS[sw]: sw for sw in allowed}
    return [(sw, semis[(SWARAS[sw] + 1) % 12]) for sw in allowed
            if (SWARAS[sw] + 1) % 12 in semis]


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
