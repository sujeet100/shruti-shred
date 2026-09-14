"""
CHALAN — how a raga MOVES, measured.

`raga.py` answers "is this swara allowed here?". That is swara legality, and it is only half
of what a raga is: Bageshree shares its scale with Bhimpalasi, so a piece can use nothing but
legal Bageshree notes and stop sounding like Bageshree the moment it walks the ladder. The
identity lives in the MOVEMENT — the vakra turn, the weak Pancham touched only in descent, the
signature angs (`m D n D m`, `m g R S`), Ma as the note phrases come home to.

Measured on the first Bageshree render (2026-09-14), the piece had the raga's GRAVITY and not
its MOTION: phrase landings fell on m 34 times, S 23 and D 21 — exactly vadi, samvadi, nyas —
and both pakads were present, yet 63% of all melodic moves were single steps, the longest
unbroken stepwise run was NINE notes, and only 35% of moves changed direction. The manjha
contained no Ma at all, in a raga whose vadi is Ma.

Nothing here is new knowledge. Every measure is derived from what `RAGAS` already encodes —
the allowed ladder, the aroha/avaroha (hence directional varjya), and the pakad/chalan
phrases as the raga's own vocabulary of movement. What was missing was anything that READ
them as motion rather than as membership.

The measures are deliberately split into two kinds, because a verifier and a critic need
different things (see DESIGN.md): what is WRONG (a swara entered from the forbidden side)
belongs in a hard rule, while what is merely WEAKLY CHARACTERISTIC (not enough vakra, thin
ang coverage) belongs in a score a critic reads. Making every aesthetic property a hard rule
produces stiff, uniform music.

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from raga import RAGAS

# A run this long in one direction, one step at a time, is a scale — whatever notes it uses.
# The taan brief already allows ONE straight dash (a sapat), so the cap is a phrase-level
# ceiling rather than a ban.
SCALAR_RUN_MAX: Final[int] = 4
# The share of moves that must turn. Bageshree's identity IS the zig-zag; a line that mostly
# continues in one direction is a ladder with raga pitches on it.
VAKRA_MIN_SHARE: Final[float] = 0.30
# An ang is a recognisable limb of the raga. Three notes is the shortest run that can be one.
ANG_MIN_LEN: Final[int] = 3

Pitched = tuple[str, int]      # (swara, octave)


@dataclass(frozen=True)
class MotionReport:
    """What a line DOES, against the raga it claims to be in."""
    notes: int
    stepwise_share: float       # moves that are a single ladder step (a scale walks; a raga turns)
    longest_scalar_run: int     # longest unbroken one-step run in ONE direction
    direction_changes: float    # share of moves that reverse — the vakra character
    ang_coverage: float         # share of notes inside a recognisable pakad/chalan movement
    landings: dict[str, int]    # swara -> how many phrases come to rest on it


def ladder(raga: str) -> list[str]:
    """The raga's allowed swaras, low to high — the ladder a step is measured against."""
    order = ["S", "r", "R", "g", "G", "m", "M", "P", "d", "D", "n", "N"]
    allowed = set(RAGAS[raga]["allowed"])
    return [sw for sw in order if sw in allowed]


def _degrees(seq: Sequence[Pitched], raga: str) -> list[int]:
    """Each note's position on the raga's own ladder, octaves included. A raga's 'step' is a
    step of ITS ladder, not a semitone: in a pentatonic raga a minor third IS adjacent."""
    rungs = ladder(raga)
    index = {sw: i for i, sw in enumerate(rungs)}
    size = len(rungs) or 1
    return [index[sw] + size * octave for sw, octave in seq if sw in index]


def _moves(seq: Sequence[Pitched], raga: str) -> list[int]:
    degrees = _degrees(seq, raga)
    return [b - a for a, b in zip(degrees, degrees[1:])]


def longest_scalar_run(seq: Sequence[Pitched], raga: str) -> int:
    """The longest unbroken run of single ladder steps in ONE direction, counted in NOTES.

    This is the scale tell. A raga phrase turns, repeats, skips and comes back; a generated
    line that keeps stepping the same way for nine notes has stopped being the raga and
    started being its scale.
    """
    moves = _moves(seq, raga)
    if not moves:
        return 0
    best = current = 0
    previous: int | None = None
    for move in moves:
        if abs(move) != 1:
            current, previous = 0, None
            continue
        current = current + 1 if move == previous else 1
        previous = move
        best = max(best, current)
    return best + 1 if best else 1      # k consecutive steps span k+1 notes


def direction_change_share(seq: Sequence[Pitched], raga: str) -> float:
    """Share of consecutive moves that REVERSE direction — the vakra character, measured."""
    moves = [m for m in _moves(seq, raga) if m != 0]
    if len(moves) < 2:
        return 0.0
    turns = sum(1 for a, b in zip(moves, moves[1:]) if a * b < 0)
    return round(turns / (len(moves) - 1), 3)


def angs(raga: str) -> list[list[str]]:
    """The raga's own vocabulary of movement: its pakad and chalan phrases, plus every
    contiguous fragment of them long enough to be recognisable. These are knowledge, already
    encoded and source-verified — this only reads them as movements rather than as note sets."""
    out: list[list[str]] = []
    for phrase in list(RAGAS[raga]["pakad"]) + list(RAGAS[raga].get("chalan") or []):
        for size in range(ANG_MIN_LEN, len(phrase) + 1):
            for start in range(len(phrase) - size + 1):
                fragment = phrase[start:start + size]
                if fragment not in out:
                    out.append(fragment)
    return out


def ang_coverage(seq: Sequence[Pitched], raga: str) -> float:
    """Share of the line's notes that sit inside a recognisable raga movement.

    This is the measure that replaces "what percentage of notes came from the pakad?" — a
    question every legal line answers well, since the pakad contains nearly every swara. What
    distinguishes a raga is ORDER, so this asks how much of the line is actually moving the
    way the raga moves. Octave-agnostic; contiguous matches only (a movement interrupted is a
    different movement).
    """
    swaras = [sw for sw, _ in seq]
    if not swaras:
        return 0.0
    covered = [False] * len(swaras)
    for ang in angs(raga):
        size = len(ang)
        for start in range(len(swaras) - size + 1):
            if swaras[start:start + size] == ang:
                for i in range(start, start + size):
                    covered[i] = True
    return round(sum(covered) / len(covered), 3)


def ang_matches(seq: Sequence[Pitched], raga: str) -> list[list[str]]:
    """The raga's own movements this line actually PLAYS, longest first.

    Used where a part must be recognisably in the raga rather than merely legal in it: an
    outro that lands on Sa without ever quoting the raga could belong to any raga sharing the
    scale, and a bridge that states no ang develops the scale rather than the raga.
    """
    swaras = [sw for sw, _ in seq]
    found: list[list[str]] = []
    for ang in angs(raga):
        size = len(ang)
        if any(swaras[i:i + size] == ang for i in range(len(swaras) - size + 1)):
            found.append(ang)
    return sorted(found, key=len, reverse=True)


def motion_report(seq: Sequence[Pitched], raga: str, *,
                  landings: dict[str, int] | None = None) -> MotionReport:
    """Everything the line does, against the raga it claims to be in. Pure."""
    moves = _moves(seq, raga)
    stepwise = sum(1 for m in moves if abs(m) == 1)
    return MotionReport(
        notes=len(seq),
        stepwise_share=round(stepwise / len(moves), 3) if moves else 0.0,
        longest_scalar_run=longest_scalar_run(seq, raga),
        direction_changes=direction_change_share(seq, raga),
        ang_coverage=ang_coverage(seq, raga),
        landings=dict(landings or {}))
