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
    the sam, the khali (matra 9) or matra 7 (matra 7 = the common teaching default).
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
        "double_stroke_matras": [],   # positions are free; the DENSITY of dir doublings is the identity
        "mukhda_starts": [1, 7, 9],   # sam, matra 7 (the teaching default), khali — Parikh FAQ
        "character": "Fast and playful — thumri/tarana-rooted; dir doublings drive the "
                     "momentum, and the mukhda may launch from the sam, matra 7, or the khali.",
        "sources": [
            {"name": "Arvind Parikh — FAQ (Razakhani bols and start options)",
             "url": "https://panditarvindparikh.org/faq/"},
            {"name": "Arvind Parikh — Bandish on the Instruments (Nad Sadhna copy)",
             "url": "https://nadsadhna.com/bandish-on-instruments-with-particular-reference-to-sitar-by-pandit-arvind-parikh/"},
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


def frame_for_bpm(bpm: float) -> str:
    """Which gat frame a piece at this tempo composes under — masitkhani below the laya
    boundary (doom), razakhani above it (everything else)."""
    return "masitkhani" if bpm < _VILAMBIT_MAX_BPM else "razakhani"


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
    return problems
