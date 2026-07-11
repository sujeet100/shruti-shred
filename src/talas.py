"""
Tala library — the rhythmic half of the knowledge-as-data core.

Same discipline as the raga library (`raga.py`): tala facts live here as DATA,
verified against >=2 reliable Hindustani sources, and are consumed by both the
deterministic layer and the LLM agents. The Tala *agent* reasons about which
tala fits a chosen subgenre's meter; it never invents these facts.

IMPORTANT: Hindustani talas, NOT Carnatic. The two systems share some names but
differ fundamentally — Carnatic uses angas (laghu/drutam/anudrutam) with a jaati
count; Hindustani uses vibhags marked by sam / tali (claps) / khali (wave). Any
Carnatic source is a red flag here.

Fields per tala (exactly the structure a composition needs to place a groove):
  display   human-readable name
  matras    number of beats in one cycle (avartan)
  vibhags   the beat-groups the cycle divides into; sum(vibhags) == matras
  sam       the matra of the sam — cycle beat 1, the resolving downbeat (always 1)
  tali      matras that carry a clap (audible stress) — vibhag starts
  khali     matras that carry a khali/wave (the "empty", unstressed vibhag start)
  theka     the canonical bol per matra (len(theka) == matras) — the groove itself
  character one line on what the tala feels like / where it's used
  sources   the Hindustani references this encoding was cross-checked on

sam / tali / khali are the beats where a vibhag BEGINS: every vibhag start is
either a tali (clap) or a khali (wave), and together they account for all of them.
Matra numbers are 1-indexed (matra 1 == sam), matching how the cycle is counted.

Bols are transliterated syllables; a compound like "Dhage"/"Tirakita" is multiple
tabla strokes falling within a single matra.
"""

TALAS = {
    "teentaal": {
        "display": "Teentaal",
        "matras": 16,
        "vibhags": [4, 4, 4, 4],
        "sam": 1,
        "tali": [1, 5, 13],
        "khali": [9],
        "theka": ["Dha", "Dhin", "Dhin", "Dha",
                  "Dha", "Dhin", "Dhin", "Dha",
                  "Dha", "Tin", "Tin", "Ta",
                  "Ta", "Dhin", "Dhin", "Dha"],
        "character": "The default of Hindustani music — symmetric 4x4, steady and "
                     "resolute. The khali third vibhag (Dha->Ta) is the one soft spot.",
        "sources": [
            {"name": "Wikipedia — Teental",
             "url": "https://en.wikipedia.org/wiki/Teental"},
            {"name": "OnlineSangeet — Teen Taal",
             "url": "https://onlinesangeet.com/teentaal-in-english/"},
        ],
    },

    "jhaptaal": {
        "display": "Jhaptaal",
        "matras": 10,
        "vibhags": [2, 3, 2, 3],
        "sam": 1,
        "tali": [1, 3, 8],
        "khali": [6],
        "theka": ["Dhi", "Na",
                  "Dhi", "Dhi", "Na",
                  "Ti", "Na",
                  "Dhi", "Dhi", "Na"],
        "character": "A lilting 2-3-2-3 limp — the uneven vibhags give it a swing "
                     "that a 4x4 can't. The Ti-Na third vibhag is khali.",
        "sources": [
            {"name": "Wikipedia — Jhaptal",
             "url": "https://en.wikipedia.org/wiki/Jhaptal"},
            {"name": "TablaTheka — Jhaptaal (10 beats)",
             "url": "https://www.tablatheka.com/2021/12/jhaptaal-10-beats.html"},
        ],
    },

    "ektaal": {
        "display": "Ektaal",
        "matras": 12,
        "vibhags": [2, 2, 2, 2, 2, 2],
        "sam": 1,
        "tali": [1, 5, 9, 11],
        "khali": [3, 7],
        # matra 8 is "Kat Ta" in the common form; some sources give "Kat Tin".
        "theka": ["Dhin", "Dhin",
                  "Dhage", "Tirakita",
                  "Tu", "Na",
                  "Kat", "Ta",
                  "Dhage", "Tirakita",
                  "Dhin", "Na"],
        "character": "Twelve beats in six twos — spacious, the standard for vilambit "
                     "(slow) khayal. Two khali vibhags (3 and 7) give it symmetry.",
        "sources": [
            {"name": "Wikipedia — Ektal",
             "url": "https://en.wikipedia.org/wiki/Ektal"},
            {"name": "OnlineSangeet — Ek Taal",
             "url": "https://onlinesangeet.com/ek-taal-in-music-in-english/"},
        ],
    },

    "rupak": {
        "display": "Rupak",
        "matras": 7,
        "vibhags": [3, 2, 2],
        "sam": 1,
        "tali": [4, 6],
        "khali": [1],   # the sam ITSELF is khali — Rupak's signature oddity
        "theka": ["Tin", "Tin", "Na",
                  "Dhin", "Na",
                  "Dhin", "Na"],
        "character": "7 beats as 3-2-2, and uniquely the sam is a KHALI (wave), not "
                     "a clap — the cycle resolves onto an unstressed beat. Odd-meter "
                     "gold for prog/thrash.",
        "sources": [
            {"name": "Wikipedia — Rupak Tala",
             "url": "https://en.wikipedia.org/wiki/Rupak_Tala"},
            {"name": "TablaTheka — Rupak Taal (7 beats)",
             "url": "https://www.tablatheka.com/2022/01/rupak-taal-7-beats.html"},
        ],
    },

    "keherwa": {
        "display": "Keherwa",
        "matras": 8,
        "vibhags": [4, 4],
        "sam": 1,
        "tali": [1],
        "khali": [5],
        "theka": ["Dha", "Ge", "Na", "Ti",
                  "Na", "Ka", "Dhin", "Na"],
        "character": "A folk/light 8-beat, two bars of four — the backbone of bhajan "
                     "and film music. Maps cleanly onto a straight metal 4/4 or 8/8.",
        "sources": [
            {"name": "Wikipedia — Keherwa",
             "url": "https://en.wikipedia.org/wiki/Keherwa"},
            {"name": "TablaTheka — Kaharwa (8 beats)",
             "url": "https://www.tablatheka.com/2021/12/kaharwa-8-beats.html"},
        ],
    },

    "dadra": {
        "display": "Dadra",
        "matras": 6,
        "vibhags": [3, 3],
        "sam": 1,
        "tali": [1],
        "khali": [4],
        "theka": ["Dha", "Dhin", "Na",
                  "Dha", "Tin", "Na"],
        "character": "A light 6-beat in two threes — a 6/8 lilt. Waltz-like; pairs "
                     "with doom's slow triple feel.",
        "sources": [
            {"name": "Wikipedia — Dadra",
             "url": "https://en.wikipedia.org/wiki/Dadra"},
            {"name": "OnlineSangeet — Dadra Taal",
             "url": "https://onlinesangeet.com/dadra-taal-in-music-in-english/"},
        ],
    },
}


def vibhag_starts(name: str) -> list[int]:
    """The 1-indexed matra on which each vibhag begins."""
    starts, m = [], 1
    for length in TALAS[name]["vibhags"]:
        starts.append(m)
        m += length
    return starts


def check_tala_consistency(name: str) -> list[str]:
    """Assert a tala's encoding is internally consistent; return any problems.

    Makes the rhythmic data testable the same way `check_raga_consistency` does:
    the vibhags must sum to the matra count, the theka must name every matra, and
    the sam / tali / khali must line up exactly with the vibhag boundaries.
    """
    t = TALAS[name]
    problems: list[str] = []

    if sum(t["vibhags"]) != t["matras"]:
        problems.append(
            f"vibhags {t['vibhags']} sum to {sum(t['vibhags'])}, not matras={t['matras']}")
    if len(t["theka"]) != t["matras"]:
        problems.append(
            f"theka has {len(t['theka'])} bols, not matras={t['matras']}")
    if t["sam"] != 1:
        problems.append(f"sam is {t['sam']}, but the sam is always matra 1")

    starts = set(vibhag_starts(name))
    marked = set(t["tali"]) | set(t["khali"])
    if marked != starts:
        problems.append(
            f"tali+khali {sorted(marked)} do not match vibhag starts {sorted(starts)}")
    overlap = set(t["tali"]) & set(t["khali"])
    if overlap:
        problems.append(f"matras {sorted(overlap)} are marked both tali and khali")
    if t["sam"] not in marked:
        problems.append("sam is neither a tali nor a khali")

    return problems
