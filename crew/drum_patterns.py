"""
The metal drum-pattern VOCABULARY — pure, research-grounded builders the groove
engine composes from. No LLM, no I/O, no Arrangement knowledge.

Each pattern builder fills ONE WINDOW (a vibhag, in beats) at 16th-note resolution
(0.25 beats), positions relative to the window start. The groove engine tiles the
windows across the tala cycle, so a 3-beat Rupak vibhag truncates the cell and the
pattern lurches with the tala — that lurch IS the fusion, not a bug.

The grids come from a research pass over drum-education sources (see DESIGN.md,
"Drum machine v2"): the skank/D-beat (thrash), the traditional/hammer/bomb blasts
(death/black), the gallop cell (heavy/melodeath), the half-time crush (doom /
breakdowns / antara), and the prog "quadruple-meter backbeat" (steady hands, a
dotted-8th kick grouping that re-aligns at the window edge). Velocities follow the
four-level scheme that makes GM soundfonts read as played, not programmed: accent /
normal / unaccented / ghost, plus a deterministic jitter (GM fonts have no round
robins — a flat velocity line is the "machine gun" tell).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final
from zlib import crc32

# The velocity levels that matter (Toontrack / Nail The Mix converge on these):
# backbeats at rimshot weight, ghosts at ~30% of them, four audible tiers overall.
VEL_SNARE: Final = 116        # the backbeat — always near-max in metal
VEL_SNARE_BLAST: Final = 106  # blast snares sit a touch under a backbeat rimshot
VEL_GHOST: Final = 34         # ghost notes: 20-45; the contrast makes the backbeat real
VEL_KICK: Final = 110         # primary (downbeat) kick
VEL_KICK_SOFT: Final = 92     # secondary / syncopated kick
VEL_CYM_ACCENT: Final = 104   # cymbal on the quarter pulse (leading hand)
VEL_CYM: Final = 86           # cymbal between the accents
VEL_BELL: Final = 112         # ride bell punch
VEL_CRASH: Final = 118        # section / sam crashes
VEL_TOM: Final = 104
VEL_ENTRANCE: Final = 127     # the band-entrance downbeat: everything at max

# Double-kick 16ths use an alternate-feet velocity ladder (dominant foot harder) —
# audibly human even on a soundfont with one kick sample.
KICK_LADDER: Final[tuple[int, ...]] = (112, 106, 110, 104)

# The A-A-A-B turnaround: ONE 16th kick pair pulled into the sam (offsets from the
# cycle end). Research economy rule: vary one element, keep the hands identical.
TURNAROUND_KICKS: Final[tuple[float, ...]] = (-0.5, -0.25)


@dataclass(frozen=True)
class PatternHit:
    """One kit stroke, relative to its window start. Internal, already-valid."""
    drum: str
    pos: float   # beats from the window start (16th grid: multiples of 0.25)
    vel: int


PatternFn = Callable[[float, str], list[PatternHit]]


def _grid(end: float, step: float, start: float = 0.0) -> list[float]:
    """Evenly spaced positions in [start, end), rounded to the 16th grid."""
    out: list[float] = []
    t = start
    while t < end - 1e-9:
        out.append(round(t, 4))
        t += step
    return out


def _cym_vel(pos: float) -> int:
    return VEL_CYM_ACCENT if float(pos).is_integer() else VEL_CYM


def _cymbal_8ths(beats: float, cymbal: str) -> list[PatternHit]:
    """Straight 8th cymbal, leading hand accented on the quarter pulse."""
    return [PatternHit(cymbal, p, _cym_vel(p)) for p in _grid(beats, 0.5)]


def _cymbal_quarters(beats: float, cymbal: str) -> list[PatternHit]:
    return [PatternHit(cymbal, float(b), VEL_CYM_ACCENT) for b in range(int(beats))]


def _backbeats(beats: float) -> list[float]:
    """Snare on 2 & 4 of the window (every odd beat)."""
    return [float(b) for b in range(1, int(beats), 2)]


def _kick_ladder(positions: list[float]) -> list[PatternHit]:
    return [PatternHit("kick", p, KICK_LADDER[i % len(KICK_LADDER)])
            for i, p in enumerate(positions)]


def _midpoint(beats: float) -> float:
    """The half-time snare slot: beat 3 of a 4-beat window, the middle otherwise."""
    return float(max(1, int(beats) // 2))


# --------------------------------------------------------------------------- #
# The pattern vocabulary. Each: (window beats, timekeeping cymbal) -> hits.    #
# --------------------------------------------------------------------------- #

def backbeat(beats: float, cymbal: str) -> list[PatternHit]:
    """The heavy-metal backbeat — the pop beat's loud, kick-doubled cousin: snare
    2 & 4 at rimshot weight, 8th-PAIR kicks (1-&, 3-&) tracking a palm-mute riff,
    straight hard 8th cymbal."""
    hits = _cymbal_8ths(beats, cymbal)
    hits += [PatternHit("snare", b, VEL_SNARE) for b in _backbeats(beats)]
    for b in range(0, int(beats), 2):
        hits.append(PatternHit("kick", float(b), VEL_KICK))
        if b + 0.5 < beats:
            hits.append(PatternHit("kick", b + 0.5, VEL_KICK_SOFT))
    return hits


def dbeat(beats: float, cymbal: str) -> list[PatternHit]:
    """The Discharge D-beat: the K-S-KK-S lurch (kick on 1, "&" of 2, "&" of 3;
    snare 2 & 4) — thrash's rolling gallop, roomier than the skank."""
    hits = _cymbal_8ths(beats, cymbal)
    for cell in _grid(beats, 4.0):                       # a 4-beat cell, truncated to fit
        for k, vel in ((0.0, VEL_KICK), (1.5, VEL_KICK_SOFT), (2.5, VEL_KICK_SOFT)):
            if cell + k < beats:
                hits.append(PatternHit("kick", round(cell + k, 4), vel))
        for s in (1.0, 3.0):
            if cell + s < beats:
                hits.append(PatternHit("snare", round(cell + s, 4), VEL_SNARE))
    return hits


def skank(beats: float, cymbal: str) -> list[PatternHit]:
    """The thrash skank: kick every quarter, snare every off-8th — "a faster,
    harder-hitting 2/4 polka"; the perceived tempo doubles."""
    hits = _cymbal_8ths(beats, cymbal)
    hits += [PatternHit("kick", float(b), VEL_KICK) for b in range(int(beats))]
    hits += [PatternHit("snare", b + 0.5, VEL_SNARE) for b in range(int(beats))]
    return hits


def gallop(beats: float, cymbal: str) -> list[PatternHit]:
    """The Maiden gallop skeleton: an 8th + two-16th kick cell under EVERY beat
    (locked to the riff's gallop), snare 2 & 4, quarter-note cymbal."""
    hits = _cymbal_quarters(beats, cymbal)
    hits += [PatternHit("snare", b, VEL_SNARE) for b in _backbeats(beats)]
    for b in range(int(beats)):
        hits.append(PatternHit("kick", float(b), VEL_KICK))
        for off in (0.5, 0.75):
            if b + off < beats:
                hits.append(PatternHit("kick", b + off, VEL_KICK_SOFT))
    return hits


def double16(beats: float, cymbal: str) -> list[PatternHit]:
    """The double-kick carpet: 16th kicks on the alternate-feet ladder under a
    hard 2 & 4 backbeat — the driving death/power-metal groove."""
    hits = _cymbal_8ths(beats, cymbal)
    hits += [PatternHit("snare", b, VEL_SNARE) for b in _backbeats(beats)]
    hits += _kick_ladder(_grid(beats, 0.25))
    return hits


def blast(beats: float, cymbal: str) -> list[PatternHit]:
    """The traditional blast: an alternating single-stroke roll split kick/snare at
    16th rate, cymbal in UNISON with the kick (that unison is what makes it a blast
    and not a skank)."""
    hits: list[PatternHit] = []
    for i, p in enumerate(_grid(beats, 0.5)):
        hits.append(PatternHit("kick", p, KICK_LADDER[i % len(KICK_LADDER)]))
        hits.append(PatternHit(cymbal, p, _cym_vel(p)))
    hits += [PatternHit("snare", p, VEL_SNARE_BLAST) for p in _grid(beats, 0.5, start=0.25)]
    return hits


def hammer(beats: float, cymbal: str) -> list[PatternHit]:
    """The hammer blast: kick + snare + cymbal in unison 8ths, no flam between
    limbs — the coldest, most mechanical wall."""
    hits: list[PatternHit] = []
    for i, p in enumerate(_grid(beats, 0.5)):
        hits.append(PatternHit("kick", p, KICK_LADDER[i % len(KICK_LADDER)]))
        hits.append(PatternHit("snare", p, VEL_SNARE_BLAST))
        hits.append(PatternHit(cymbal, p, _cym_vel(p)))
    return hits


def bomb(beats: float, cymbal: str) -> list[PatternHit]:
    """The bomb blast: snare 8ths RIDING a 16th double-kick carpet — the snare
    leads (unlike the kick-led traditional); the climax blast."""
    hits = _kick_ladder(_grid(beats, 0.25))
    for p in _grid(beats, 0.5):
        hits.append(PatternHit("snare", p, VEL_SNARE_BLAST))
        hits.append(PatternHit(cymbal, p, _cym_vel(p)))
    return hits


def halftime(beats: float, cymbal: str) -> list[PatternHit]:
    """Half-time: cymbal quarters, ONE snare at the window's midpoint, kick on 1
    plus one late syncopation when there's room — same tempo, half the perceived
    rate, "very slow and heavy"."""
    hits = _cymbal_quarters(beats, cymbal)
    mid = _midpoint(beats)
    hits.append(PatternHit("snare", mid, VEL_SNARE))
    hits.append(PatternHit("kick", 0.0, VEL_KICK))
    if beats >= 4:
        hits.append(PatternHit("kick", mid + 0.5, VEL_KICK_SOFT))
    return hits


def prog(beats: float, cymbal: str) -> list[PatternHit]:
    """The prog "quadruple-meter backbeat" (Haake): cymbal and snare keep plain
    time while the kick walks a dotted-8th (3-sixteenth) grouping that drifts
    against them and re-aligns at the window edge."""
    hits = _cymbal_quarters(beats, cymbal)
    hits.append(PatternHit("snare", _midpoint(beats), VEL_SNARE))
    hits += _kick_ladder(_grid(beats, 0.75))
    return hits


PATTERNS: Final[dict[str, PatternFn]] = {
    "backbeat": backbeat, "dbeat": dbeat, "skank": skank, "gallop": gallop,
    "double16": double16, "blast": blast, "hammer": hammer, "bomb": bomb,
    "halftime": halftime, "prog": prog,
}


# --------------------------------------------------------------------------- #
# Ghost notes, fills, and the deterministic humanizer.                         #
# --------------------------------------------------------------------------- #

# Idiomatic ghost pockets in a 4-beat window: the "e" after a backbeat and the
# "a" of 2 — never directly before a backbeat, singles/doubles only (Toontrack's
# physical-playability rules). Ghosts belong to roomy grooves; blasts have no gaps.
_GHOST_POCKETS: Final[tuple[float, ...]] = (1.25, 1.75, 3.25)


def ghost_snares(beats: float) -> list[PatternHit]:
    """Ghost 16ths for one window — the single biggest realism lever."""
    return [PatternHit("snare", p, VEL_GHOST) for p in _GHOST_POCKETS if p < beats - 0.2]


def tom_run(beats: float, toms: list[str], *,
            vel_lo: int = 88, vel_hi: int = 124) -> list[PatternHit]:
    """A crescendo 16th fill: snare for the first half, then a descent down the
    available toms — positions relative to the FILL window start. The caller lands
    the crash + kick on the next downbeat (the near-absolute rule: a fill resolves
    INTO the next bar, never inside its own)."""
    steps = _grid(beats, 0.25)
    n_snare = len(steps) - len(steps) // 2          # snare leads, toms take the back half
    n_toms = len(steps) - n_snare
    lanes = ["snare"] * n_snare
    lanes += [toms[min(i * len(toms) // max(1, n_toms), len(toms) - 1)] if toms else "snare"
              for i in range(n_toms)]
    span = max(1, len(steps) - 1)
    return [PatternHit(lane, p, round(vel_lo + (vel_hi - vel_lo) * i / span))
            for i, (p, lane) in enumerate(zip(steps, lanes))]


def pickup_roll(beats: float = 1.0) -> list[PatternHit]:
    """The band-entrance snare roll: 16ths swelling hard into the downbeat."""
    steps = _grid(beats, 0.25)
    span = max(1, len(steps) - 1)
    return [PatternHit("snare", p, round(70 + (127 - 70) * i / span))
            for i, p in enumerate(steps)]


def humanized(vel: int, start: float, drum: str, spread: int) -> int:
    """Deterministic velocity jitter (±spread) keyed on (grid position, drum).

    Same input, same output — no RNG, so grooves stay test-stable and re-renders
    are reproducible. Research bound: beyond ~±5 reads as sloppy, 0 reads as a
    machine gun on a round-robin-less GM soundfont.
    """
    if spread <= 0:
        return max(1, min(127, vel))
    key = (int(round(start * 8)) * 2654435761 + crc32(drum.encode())) & 0xFFFFFFFF
    return max(1, min(127, vel + key % (2 * spread + 1) - spread))
