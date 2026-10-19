"""
Gat-form library — the stroke-pattern (bol) frames of the sitar gat.

Same discipline as the raga/tala libraries: gat-form facts live here as DATA, verified
against >=2 reliable Hindustani sources, consumed by both the deterministic verifier
(`crew/gat_verifier.verify_bol_frame`) and the LLM prompts. The stroke pattern is the
gat's rhythmic IDENTITY — Pandit Arvind Parikh: "I don't call gats that don't follow
Masitkhani bol patterns as Masitkhani gats. They are just vilambit gats."

The two canonical frames (both teentaal — the gat's home tala):
  * MASITKHANI (vilambit): the full matra-by-matra grid IS verified — the 8-bol unit
    "dir da dir da ra da da ra" stated twice per avartan, phase-locked so the MUKHDA
    (the head) is a five-matra ANACRUSIS on matras 12-16 ("dir da dir da ra") whose
    arrival stroke lands ON the next sam. It begins inside the khali vibhag (9-12), so
    the gat's densest strokes cut across the tala's quietest zone and resolve on its
    loudest beat — the catchiness engine of the form.
  * RAZAKHANI (drut): Parikh gives the bol set "da ra dir dir dar dar da, da dir dara
    da da ra" but fixed only "with a slight flexibility", and the mukhda may start from
    the sam, the khali (matra 9) or matra 7 — no default is named (Parikh FAQ q56).
    FLAG: no source gives a trustworthy matra-by-matra map (the one paper that prints a
    "Razakhani grid" repeats the Masitkhani pattern verbatim — a mislabel), so this
    entry encodes the VOCABULARY and the start options, never an invented grid.

Bols here are the mizrab strokes: "da" (inward, strong), "ra" (outward, softer),
"dir" (the da-ra pair inside ONE matra — a double attack). A gat melody note may carry
several strokes; the grid is rhythm, not melody.

Fields per frame:
  display               human-readable name
  matras                the avartan the frame is stated over (16 — teentaal)
  bols                  matra->bol grid, 1-indexed from the sam; None = no verified grid
  double_stroke_matras  the matras carrying a dir double attack (the surge positions)
  mukhda_start          (masitkhani) the matra the mukhda anacrusis begins on
  mukhda_starts         (razakhani) the sanctioned start options
  bol_phrase            (razakhani) Parikh's canonical bol set, flexibility permitted
  character             one line on what the frame feels like
  sources               the Hindustani references this encoding was cross-checked on

Sources (researched 2026-07-20; all Hindustani):
  * Pandit Arvind Parikh, "Bandish on the Instruments" — panditarvindparikh.org and the
    Nad Sadhna copy (two independent publications of the text).
  * Pandit Arvind Parikh, FAQ — panditarvindparikh.org/faq/ ("Masitkhani gats start from
    12th matra"; the Razakhani bol set and its sam/khali/7th-matra start options).
  * Vishwamohini — "Masitkhani Gat in Teentaal, Raag Bhimpalasi": a published notation
    whose matra map confirms the grid exactly (dir-da-dir-da-ra on 12-16, da-da-ra on 1-3).
  * Lokogandhar — "The Evolution and Structure of the Masidkhani Gat and Baaj" (the same
    skeleton written from matra 1; the khali placement of the mukhda).
"""

GAT_FRAMES = {
    "masitkhani": {
        "display": "Masitkhani (vilambit)",
        "matras": 16,
        # The verified grid, 1-indexed from the sam: the 8-bol unit "dir da dir da ra
        # da da ra" twice, phase-locked with "dir" landing on matras 4/6/12/14 and the
        # mukhda's "dir da dir da ra" occupying matras 12-16 into the next sam.
        "bols": ["da", "da", "ra", "dir", "da", "dir", "da", "ra",
                 "da", "da", "ra", "dir", "da", "dir", "da", "ra"],
        "double_stroke_matras": [4, 6, 12, 14],
        "mukhda_start": 12,
        "character": "Grave and unhurried — dhrupad-rooted; the five-matra mukhda "
                     "gathers through the khali and lands its arrival stroke on the sam.",
        "sources": [
            {"name": "Arvind Parikh — Bandish on the Instruments",
             "url": "https://panditarvindparikh.org/articles/music-related/bandish-on-the-instruments/"},
            {"name": "Vishwamohini — Masitkhani Gat in Teentaal (Bhimpalasi), notation",
             "url": "https://vishwamohini.com/music/music.php?id=1152"},
            {"name": "Lokogandhar — Evolution and Structure of the Masidkhani Gat",
             "url": "https://lokogandhar.com/the-evolution-and-structure-of-the-masidkhani-gat-and-baaj/"},
        ],
    },

    "razakhani": {
        "display": "Razakhani (drut)",
        "matras": 16,
        "bols": None,   # no verified matra grid — flexibility is the sourced fact (see docstring)
        "bol_phrase": "da ra dir dir dar dar da, da dir dara da da ra",
        # sourced drut stroke phrases — VOCABULARY to draw on, never a template to copy
        "drut_figures": ["da dir dara", "dir dir dara", "dara dara da dara"],
        "double_stroke_matras": [],   # positions are free; the DENSITY of dir doublings is the identity
        "mukhda_starts": [1, 7, 9],   # sam, matra 7, khali — alternatives, none the default (Parikh FAQ q56)
        "character": "Fast and playful — thumri/tarana-rooted; dir doublings drive the "
                     "momentum, and the mukhda may launch from the sam, matra 7, or the khali.",
        "sources": [
            {"name": "Arvind Parikh — FAQ (Razakhani bols and start options)",
             "url": "https://panditarvindparikh.org/faq/"},
            {"name": "Arvind Parikh — Bandish on the Instruments (Nad Sadhna copy)",
             "url": "https://nadsadhna.com/bandish-on-instruments-with-particular-reference-to-sitar-by-pandit-arvind-parikh/"},
            {"name": "Ustad Shahid Parvez — 'da dir dara', 'dir dir dara' (Free Press Journal interview)",
             "url": "https://www.freepressjournal.in/amp/lifestyle/ustad-shahid-parvez-enchants-with-sitar-mastery-at-a-recently-held-musical-extravaganza-in-mumbais-jai-hind-college"},
            {"name": "Lalmani Misra — drut bol tables, 'DaRa DaRa DaDaRa'",
             "url": "https://www.omenad.net/articles/bsv_sitar3.htm"},
        ],
    },
}

# The laya boundary between the two frames, as an ENGINEERING mapping (not a sourced tempo
# rule): a true vilambit teentaal sits far below any metal tempo, so the split is chosen to
# give the slow end (doom, 60-90 bpm) the Masitkhani gravity and every faster subgenre the
# Razakhani drive. Strictly-below-90 because the next subgenre up (symphonic) STARTS at 90:
# laya, not genre, is the criterion, so a doom piece at its very top edge takes the drut frame.
_VILAMBIT_MAX_BPM = 90.0

_BOL_VOCAB = {"da", "ra", "dir"}

# The mizrab bol WORDS a gat note may carry — each a STROKE PATTERN given as RATIOS, every stroke a
# separate pluck on the note's swara; the note's own length sets the figure's size and the strokes
# divide it in proportion. A drut gat puts many bols inside one matra, in figures of every size —
# dara, dadir, dir dir, darada at 1/4, 1/2, 1, 2/3 of a matra, triplets, quadruplets (Sujit,
# 2026-10-12). Fixed ABSOLUTE lengths (dir = 1 matra, dadir = 2) made every figure a whole-matra
# slot and the heads one note per matra; ratios keep the relations Sujit set in Swarmatra (Aug
# 2026: inside dadir, di and r are each half the da) at whatever size the composer writes, which is
# also how the published notation fits "DaDir" inside one vilambit matra (1/2 + 1/4 + 1/4). Inward
# strokes (da, di) are the strong ones; the outward return (ra, r) is softer. A single-stroke word
# (da, ra) is one pluck lasting the whole note. Sources: Pandit Arvind Parikh, "Bandish on the
# Instruments" and his FAQ (da, ra, dir, dadir, dar, dara; the Razakhani set "da ra dir dir dar
# dar da, da dir dara da da ra"); Vishwamohini's notated gat (dara and dadir inside one matra,
# 1:1 and 2:1:1). rda is the fourth of the sitar's four basic strokes in Parikh's "Origin of the
# Sitar" ("Rda: the outward and inward in quick succession", the mirror of dir; it sits in his
# Razakhani stroke format), read 2026-10-12 — the GPT guide gives the same definition. darada and
# daradara are Sujit's own encoding (Swarmatra `src/domain/bols.ts`) — Parikh's list has "darda",
# whose strokes no source defines. Left out on purpose: dra (mainly a SAROD stroke — Parikh FAQ).
BOL_WORDS: dict[str, tuple[tuple[str, int | None], ...]] = {
    "da": (("da", None),),
    "ra": (("ra", None),),
    "dir": (("di", 1), ("r", 1)),
    "rda": (("r", 1), ("da", 1)),
    "dara": (("da", 1), ("ra", 1)),
    "dar": (("da", 2), ("r", 1)),
    "dadir": (("da", 2), ("di", 1), ("r", 1)),
    "darada": (("da", 1), ("ra", 1), ("da", 1)),
    "daradara": (("da", 1), ("ra", 1), ("da", 1), ("ra", 1)),
}
INWARD_STROKES: frozenset[str] = frozenset({"da", "di"})   # strong; ra / r are the softer returns

# HOW A GAT HEAD MOVES — the craft of the melody riding the strokes (researched 2026-10-12 for
# Sujit's "the mukhada does not sound like a sitar gat"). Each rule carries its sources and a
# confidence: VERIFIED = >=2 Hindustani sources agree; COMMON = one published notation shows it
# (Vishwamohini's Masitkhani gat in Bhimpalasi, the only trustworthy matra-by-matra gat notation
# found from an allowed source) and nothing contradicts it — prompted as a tendency, never a
# rule. `frames` limits a rule to the frames it was observed in. RESOLVED by Sujit (2026-10-12):
# bol words have no absolute length — many bols share a matra in drut (BOL_WORDS is ratios now).
# STILL FLAGGED, NOT ENCODED: how "dir dir" / "dar dar" pairs sit melodically is unsourced; the
# notation has no chikari in the head (absence, not a rule).
_PARIKH = "Parikh, Bandish on the Instruments (panditarvindparikh.org; Nad Sadhna copy)"
_PARIKH_FAQ = "Parikh, FAQ and Etawah-Imdadkhani gharana essay (panditarvindparikh.org)"
_NOTATION = "Vishwamohini, Masitkhani gat in Bhimpalasi (vishwamohini.com/music/music.php?id=1152)"
_LOKOGANDHAR = "Lokogandhar, Evolution and Structure of the Masidkhani Gat and Baaj"
_PARVEZ = "Ustad Shahid Parvez (Etawah), Free Press Journal interview"
_MISRA = "Lalmani Misra's drut bol tables (omenad.net)"
_NAD_SADHNA = "Nad Sadhna, Vilayatkhani-Itawa gharana page"
_SUJIT = "Sujit (sitar practice, guruji's teaching), 2026-10-12: \"dir is generally used on the same note\""
GAT_CRAFT: tuple[dict, ...] = (
    {"rule": "the LEFT hand moves the melody, the RIGHT hand makes the rhythm: one swara often "
             "takes several strokes in a row (2-3, even 6 in a drut gat — dir dir on a held swara "
             "while the left hand waits) — after the sam arrival, the arrival swara is often "
             "restated before the line moves on",
     "confidence": "VERIFIED", "sources": [_PARIKH_FAQ, _NOTATION, _NAD_SADHNA]},
    {"rule": "dara usually MOVES — its da and its ra carry two swaras, so write it as two notes "
             "(da on one, ra on the next)",
     "confidence": "COMMON", "sources": [_NOTATION]},
    {"rule": "in a dadir the da APPROACHES and the dir doubles the ARRIVAL — write the da and "
             "the dir as two notes",
     "confidence": "COMMON", "sources": [_NOTATION]},
    {"rule": "da ra da ra on ONE swara is a practice drill; in a taan run each stroke takes a new "
             "swara (one note, one bol)",
     "confidence": "VERIFIED", "sources": [_PARIKH_FAQ, _NAD_SADHNA]},
    {"rule": "phrases come in MOVING and SETTLING groups: five-matra groups driven by dir "
             "(dir da dir da ra) carry the melody forward, three-matra groups (da da ra) settle it",
     "confidence": "VERIFIED", "sources": [_PARIKH, _NOTATION], "frames": ("masitkhani",)},
    {"rule": "a dir is the SAME swara struck twice (now and then a single step up into the next "
             "target — never a leap)",
     "confidence": "VERIFIED", "sources": [_NOTATION, _SUJIT]},
    {"rule": "move stepwise on the raga's OWN ladder (its skips count as steps); inside a phrase "
             "the widest leap is about a third, and vakra turns live in the moving groups — the "
             "one bigger leap is the arrival onto the sam",
     "confidence": "COMMON", "sources": [_NOTATION]},
    {"rule": "breathe before the mukhda: the line settles on a resting swara (Sa, on the soft "
             "'ra') just before the mukhda restarts — the nyas that resets the phrase",
     "confidence": "VERIFIED", "sources": [_LOKOGANDHAR, _NOTATION]},
    {"rule": "the mukhda's approach into the sam is IDENTICAL every time the head comes round — "
             "it is the hook — and it arrives on the sam swara from below",
     "confidence": "COMMON", "sources": [_NOTATION, _PARIKH]},
    {"rule": "the head's sam swara is its home — a resting swara of the raga, often Sa or the vadi "
             "but not always (real gats land it on Pa, Ma, even Re); the manjha lands low, the "
             "antara on taar Sa: each line's sam note follows its job",
     "confidence": "VERIFIED", "sources": [_PARIKH, _NOTATION]},
)


def is_compound(word: str) -> bool:
    """A bol word of several strokes (dir, dar, dadir ...), as opposed to a single da / ra."""
    return len(BOL_WORDS[word]) > 1


def bol_onsets(word: str, dur: float) -> list[tuple[float, float, str]]:
    """Where each stroke of `word` falls inside a note of `dur` matras: (offset, length, stroke).
    The strokes divide the note in the word's ratios — dadir over one matra is 1/2 + 1/4 + 1/4,
    over two it is 1 + 1/2 + 1/2; a single stroke is the whole note. Pure."""
    strokes = BOL_WORDS[word]
    total = sum(weight or 1 for _, weight in strokes)
    out: list[tuple[float, float, str]] = []
    t = 0.0
    for stroke, weight in strokes:
        length = dur * (weight or 1) / total
        out.append((t, length, stroke))
        t += length
    return out


# THE STROKE LINE — the right hand written out, one token per matra, the way the sources notate a
# gat's bols (Parikh's grids, Vishwamohini's notation): a bol word, "chikari", or STROKE_HOLD for a
# matra with no new stroke (a held note ringing on, or a silence). The head PLANS it before its notes
# (`PhrasePlan.stroke_line`), so the rhythm is composed as a pattern instead of sprinkled note by note.
STROKE_HOLD: str = "-"


def stroke_line_attacks(token: str) -> int | None:
    """How many plucks one matra of a stroke line asks for — none for STROKE_HOLD, one for a chikari,
    a bol word's stroke count otherwise; None when the token is no stroke at all. Pure."""
    if token == STROKE_HOLD:
        return 0
    if token == "chikari":
        return 1
    return len(BOL_WORDS[token]) if token in BOL_WORDS else None


def is_vilambit(bpm: float) -> bool:
    """Whether a piece at this tempo is slow (vilambit) — below the laya boundary."""
    return bpm < _VILAMBIT_MAX_BPM


def frame_for_bpm(bpm: float) -> str:
    """Which gat frame a piece at this tempo composes under — masitkhani below the laya
    boundary (doom), razakhani above it (everything else)."""
    return "masitkhani" if is_vilambit(bpm) else "razakhani"


def check_gat_frame_consistency() -> list[str]:
    """Assertable facts about the frames — the same testable-knowledge discipline as the
    raga/tala libraries. Returns a list of problems (empty == consistent)."""
    problems: list[str] = []
    for name, f in GAT_FRAMES.items():
        bols = f["bols"]
        if bols is not None:
            if len(bols) != f["matras"]:
                problems.append(f"{name}: grid has {len(bols)} bols for {f['matras']} matras")
            if bad := [b for b in bols if b not in _BOL_VOCAB]:
                problems.append(f"{name}: unknown bols {bad}")
            if bols[: f["matras"] // 2] != bols[f["matras"] // 2:]:
                problems.append(f"{name}: the grid is not the 8-bol unit stated twice")
            dirs = [i + 1 for i, b in enumerate(bols) if b == "dir"]
            if dirs != list(f["double_stroke_matras"]):
                problems.append(f"{name}: dir matras {dirs} != declared {f['double_stroke_matras']}")
        start = f.get("mukhda_start")
        if start is not None and not 1 <= start <= f["matras"]:
            problems.append(f"{name}: mukhda_start {start} outside 1..{f['matras']}")
        for s in f.get("mukhda_starts", []):
            if not 1 <= s <= f["matras"]:
                problems.append(f"{name}: mukhda start option {s} outside 1..{f['matras']}")
        if len(f["sources"]) < 2:
            problems.append(f"{name}: fewer than 2 sources recorded")
    for word, strokes in BOL_WORDS.items():
        if bad := [s for s, _ in strokes if s not in INWARD_STROKES | {"ra", "r"}]:
            problems.append(f"bol {word}: unknown strokes {bad}")
        if len(strokes) > 1 and any(w is None or w <= 0 for _, w in strokes):
            problems.append(f"bol {word}: a compound needs a positive ratio on every stroke")
    for craft in GAT_CRAFT:
        if craft["confidence"] == "VERIFIED" and len(craft["sources"]) < 2:
            problems.append(f"gat craft marked VERIFIED on one source: {craft['rule'][:50]}")
        if bad := [f for f in craft.get("frames", ()) if f not in GAT_FRAMES]:
            problems.append(f"gat craft names unknown frame(s) {bad}")
    for figure in (fig for f in GAT_FRAMES.values() for fig in f.get("drut_figures", [])):
        if bad := [w for w in figure.split() if w not in BOL_WORDS]:
            problems.append(f"drut figure '{figure}' uses unknown bol word(s) {bad}")
    for bol in {b for f in GAT_FRAMES.values() for b in (f["bols"] or [])}:
        if bol not in BOL_WORDS:
            problems.append(f"frame bol {bol} is not a known bol word")
    return problems


def gat_craft_for(frame: str) -> list[dict]:
    """The craft rules that apply under `frame` (a rule without `frames` applies to every frame)."""
    return [c for c in GAT_CRAFT if frame in c.get("frames", (frame,))]


_MOTIF_MIN_WORDS = 2
_MOTIF_MAX_WORDS = 4


def stroke_motif(bols: list[str | None]) -> tuple[str, ...] | None:
    """The hook's STROKE MOTIF: its recurring bol figure — in a sitar gat the stroke pattern often
    IS the motif (Sujit, 2026-10-12), as recognisable as any swara figure. The longest contiguous
    run of 2-4 bol words that occurs at least twice (more occurrences break a tie), with at least
    one compound word in it so a bare da-ra alternation does not count. None when nothing recurs.
    `bols` is the hook's sounding notes' bols in order (None = a note with no bol). Pure."""
    best: tuple[int, int, tuple[str, ...]] | None = None
    for size in range(_MOTIF_MIN_WORDS, _MOTIF_MAX_WORDS + 1):
        counts: dict[tuple[str, ...], int] = {}
        for i in range(len(bols) - size + 1):
            figure = bols[i:i + size]
            if None in figure or not any(is_compound(b) for b in figure if b in BOL_WORDS):
                continue
            key = tuple(b for b in figure if b is not None)
            counts[key] = counts.get(key, 0) + 1
        for figure, count in counts.items():
            if count >= 2 and (best is None or (size, count) > best[:2]):
                best = (size, count, figure)
    return best[2] if best else None
