"""
GESTURES — measured left-hand figures a raga's characteristic swara is played with.

A raga swara is not a pitch with a wobble added: it is approached, it moves, and it leaves in a
way the raga owns. The `andolan` model (one sway direction per swara, a symmetric curve) could
not say that, and two GPT reviews of the 2026-10-12 Darbari render heard the result as a generic
U-shaped bend. This table holds whole gestures instead: a pitch PATH in milliseconds after the
note sounds, toward a named neighbour, selected by where the line arrives FROM.

Darbari's komal Ga, measured (pYIN) on Sujit's guruji's recorded Darbari gat (oral tradition,
2026-10-12; Sa = D, 120 bpm). Six clear gestures, two families:
  * arriving from Sa, from Pa, or after a rest (3.3 s, 8.8 s, 27.1 s, 52.0 s): Ga is struck,
    pulled UP to Ma (rise ~40 ms), held there 100-245 ms, and released back to Ga (~100 ms) —
    one stroke, no new pluck. Parrikar writes the same upper touch as "(M)g" (his M = our m).
  * arriving from Ma itself (44.5 s, 48.4 s): Ga dips to Re for 35-70 ms and returns, then the
    line resolves toward Sa — the Re-ga oscillation AUTRIM/NCPA and Deepak Raja describe.
    Arriving from Ma already carries the upper touch, so the dip moves the line on.
The times are the measured medians; the tracker's confidence on a mixed recording is low, so
the shapes are trustworthy and the milliseconds are approximate (tune by ear). Dha's gestures
are NOT encoded: its evidence (4 loops down to Pa, 1 up to Ni) was too thin.

Bageshree's komal Ga, arriving from Ma (Sujit's guruji, oral tradition, 2026-10-11 — "a slow Ma->Ga
reverse bend"; Parrikar "(m)g", Ga taking its colour from Ma above): the string is plucked already
pulled to Ma's pitch, rests there a moment, and is RELEASED slowly onto Ga, which then holds still.
It replaced a sway that turned on shuddha Ga (fusion_20261013_081705_bageshree, 6.5/10/20.5 s:
+98 cents held ~250 ms, three times) — a gesture may PASS a pitch the raga does not own, but it
never RESTS on one (`check_gestures`). The release's milliseconds are inference, for the ear.

Two motions, kept distinct because they mean different things:
  * LOOP — leaves the swara and comes home (a kan-like touch, a dip): starts and ends on it;
  * RELEASE — a meend that ARRIVES at the swara from its neighbour: starts on the neighbour, ends
    on the swara and stays. (Andolan, the sway that turns inside a swara's own periphery, lives
    in `crew/expression.py`; gamak, the re-struck swing between two swaras, is below.)

Pure — no I/O, no LLM. The renderer never imports this; code resolves a gesture to a concrete
path on the note (`Note.pitch_path`) and the renderer draws whatever path it is given.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Final

from raga import KHADA_RAGAS, RAGAS, SWARAS, directional_varjya, scale_step_up

SETTLE_MS: Final = 60      # the note must still sound this long after the gesture ends


LOOP: Final = "loop"
RELEASE: Final = "release"


@dataclass(frozen=True)
class Gesture:
    """A pitch path between a swara and its neighbour `toward`: knots of (ms after the note
    sounds, share of the way to `toward`). A LOOP starts and ends on the swara (share 0); a
    RELEASE starts on the neighbour (share 1) and ends on the swara. Either way it rests only on
    the two swaras themselves — every held stretch is at share 0 or 1."""
    name: str
    toward: str
    knots: tuple[tuple[float, float], ...]
    source: str
    hold_range_ms: tuple[float, float] | None = None   # the measured spread of the hold at the neighbour
    motion: str = LOOP
    move_range_ms: tuple[float, float] | None = None   # the spread of the final move onto the swara

    @property
    def length_ms(self) -> float:
        """The longest the gesture can take — its hold and its final move at the top of their
        ranges."""
        longest = self.knots[-1][0]
        if self.hold_range_ms is not None:
            longest += self.hold_range_ms[1] - _hold_ms(self.knots)
        if self.move_range_ms is not None:
            longest += self.move_range_ms[1] - _last_move_ms(self.knots)
        return longest


@dataclass(frozen=True)
class GestureRule:
    """`swara` is played with `gesture` when the line arrives from `from_swara` (the swara just
    before it, as the adjacent neighbour) — or from anywhere else when `from_swara` is None.
    `in_alap`: the gesture also belongs in the slow alap/outro (guruji's Darbari figures were
    measured in a fast gat, so they stay out of it; Bageshree's release is an alap gesture)."""
    swara: str
    gesture: Gesture
    from_swara: str | None = None
    in_alap: bool = False


_GURUJI: Final = "Sujit's guruji, recorded Darbari gat (oral tradition, measured 2026-10-12)"


def _hold_ms(knots: tuple[tuple[float, float], ...]) -> float:
    """How long the path rests at the neighbour (the knots at full share)."""
    top = [ms for ms, share in knots if share == 1.0]
    return top[-1] - top[0] if len(top) >= 2 else 0.0


def _last_move_ms(knots: tuple[tuple[float, float], ...]) -> float:
    """How long the final move onto the swara takes."""
    return knots[-1][0] - knots[-2][0]


def _mixed(seed: float, k: int) -> float:
    """A deterministic fraction in [0, 1) keyed on (seed, k) through CRC32 — well mixed where
    `vary`'s low bits are not (starts 20 and 41 land 4% apart there). Kept separate so the
    gestures already tuned by ear on `vary` sound exactly as they did."""
    return (zlib.crc32(f"{seed:.4f}:{k}".encode()) % 4096) / 4096.0


def vary(seed: float, k: int) -> float:
    """A deterministic fraction in [0, 1) keyed on a note's start and an index — the drum
    machine's no-RNG humanising: the same note always plays the same way, and two notes rarely
    do (a repeated gesture with one fixed trajectory reads as a machine)."""
    key = (int(round(seed * 8)) * 2654435761 + k * 40503 + 12289) & 0xFFFFFFFF
    return (key % 1024) / 1024.0

GA_MA_LOOP: Final = Gesture(
    name="ga_ma_loop", toward="m",
    knots=((0, 0.0), (60, 0.0), (100, 1.0), (270, 1.0), (370, 0.0)),
    source=f"{_GURUJI}; Parrikar 'The avarohi gandhar: (M)g, (M)g M (S)R, S' (his M = shuddha)",
    hold_range_ms=(100.0, 245.0))

GA_RE_DIP: Final = Gesture(
    name="ga_re_dip", toward="R",
    knots=((0, 0.0), (40, 0.0), (60, 1.0), (110, 1.0), (135, 0.0)),
    source=f"{_GURUJI}; AUTRIM/NCPA ga moves 'between Re and Ga'; Deepak Raja 'Re-ga'",
    hold_range_ms=(35.0, 70.0))

GA_MA_RELEASE: Final = Gesture(
    name="ga_ma_release", toward="m",
    knots=((0, 1.0), (140, 1.0), (560, 0.0)),
    source="Sujit's guruji (oral tradition, 2026-10-11): 'a slow Ma->Ga reverse bend'; "
           "Parrikar Bageshree '(m)g'",
    hold_range_ms=(90.0, 200.0), motion=RELEASE, move_range_ms=(340.0, 520.0))

GESTURES: dict[str, tuple[GestureRule, ...]] = {
    "darbari": (
        GestureRule(swara="g", gesture=GA_RE_DIP, from_swara="m"),
        GestureRule(swara="g", gesture=GA_MA_LOOP),
    ),
    "bageshree": (
        GestureRule(swara="g", gesture=GA_MA_RELEASE, from_swara="m", in_alap=True),
    ),
}


def gesture_for(raga: str, swara: str, from_swara: str | None, *,
                alap: bool = False) -> Gesture | None:
    """The gesture this swara takes arriving from `from_swara` (None = no adjacent approach):
    a rule naming that approach first, else the swara's default, else None. In the alap only
    the rules marked `in_alap` apply."""
    rules = [r for r in GESTURES.get(raga, ()) if r.swara == swara and (r.in_alap or not alap)]
    specific = [r for r in rules if r.from_swara is not None and r.from_swara == from_swara]
    default = [r for r in rules if r.from_swara is None]
    chosen = (specific or default or [None])[0]
    return chosen.gesture if chosen is not None else None


def gesture_named(name: str) -> Gesture | None:
    """The gesture with this name, from any raga's rules (names are unique)."""
    return next((r.gesture for rules in GESTURES.values() for r in rules
                 if r.gesture.name == name), None)


def gesture_path(gesture: Gesture, swara: str, seed: float | None = None) -> list[list[float]]:
    """The gesture as concrete (ms, semitones) knots from `swara` — the neighbour's interval
    taken the short way round the octave (g -> m is +2, g -> R is -1). With a `seed` (the note's
    start) the hold at the neighbour takes a length inside its measured range, so each
    occurrence differs as a player's does; without one, the median. A RELEASE begins at the
    neighbour's interval and ends at 0."""
    gap = (SWARAS[gesture.toward] - SWARAS[swara]) % 12
    interval = gap - 12 if gap > 6 else gap
    knots = gesture.knots
    if seed is not None and gesture.hold_range_ms is not None:
        lo, hi = gesture.hold_range_ms
        shift = lo + (hi - lo) * vary(seed, 0) - _hold_ms(knots)
        top_end = max(ms for ms, share in knots if share == 1.0)
        knots = tuple((ms + shift if ms >= top_end else ms, share) for ms, share in knots)
    if seed is not None and gesture.move_range_ms is not None:
        lo, hi = gesture.move_range_ms
        last = knots[-2][0] + lo + (hi - lo) * _mixed(seed, 1)
        knots = knots[:-1] + ((last, knots[-1][1]),)
    return [[round(ms, 1), round(share * interval, 3)] for ms, share in knots]


def check_gestures() -> list[str]:
    """Data hygiene: every rule's swara and neighbour belong to its raga, every path ends on the
    swara (a loop also starts there, a release starts on the neighbour) with time moving forward,
    every hold rests on one of the two swaras, and every gesture names its source."""
    problems: list[str] = []
    for raga, rules in GESTURES.items():
        allowed = RAGAS[raga]["allowed"]
        for r in rules:
            g = r.gesture
            if r.swara not in allowed or g.toward not in allowed:
                problems.append(f"{raga}.{g.name}: swara/neighbour outside the raga")
            if r.from_swara is not None and r.from_swara not in allowed:
                problems.append(f"{raga}.{g.name}: approach swara outside the raga")
            times = [ms for ms, _ in g.knots]
            first = 1.0 if g.motion == RELEASE else 0.0
            if g.knots[0][1] != first or g.knots[-1][1] != 0 or times != sorted(set(times)):
                problems.append(f"{raga}.{g.name}: a {g.motion} must start on "
                                f"{'its neighbour' if first else 'the swara'}, end on the swara, "
                                "time forward")
            if any(a == b and a not in (0.0, 1.0) for (_, a), (_, b) in zip(g.knots, g.knots[1:])):
                problems.append(f"{raga}.{g.name}: rests between two swaras — on no swara at all")
            if not g.source:
                problems.append(f"{raga}.{g.name}: no source")
        if sum(1 for r in rules if r.from_swara is None) > len({r.swara for r in rules}):
            problems.append(f"{raga}: more than one default gesture for a swara")
    return problems


# ---------------------------------------------------------------------------
# GAMAK — fast forceful swings between two ADJACENT swaras, re-struck as they go.
#
# Measured on the same recording (run-length pitch labels between stroke onsets): guruji's
# gamak phrases swing between neighbouring swaras — the gat OPENS with S | m g (one stroke,
# Ma swung onto Ga); at 29-31 s "P93 m93 P46 | P186 m35 | m209 P23" (Pa<->Ma across three
# strokes); then d<->n; in the mandra "P93 d35 P23 d35 | d209" (Pa<->Dha). Each visit lasts
# 35-210 ms (typical ~85), the move between ~25 ms, and strokes fall about every 250 ms (two
# a beat at his 120 bpm) — the right hand keeps the pulse, the left hand does the swinging.
# A gamak is common across ragas (Sujit, 2026-10-12: "common in Yaman too and many other
# raagas"); the composer chooses WHERE and WITH WHICH NEIGHBOUR, code plays it. A khada raga
# (Marwa — Parrikar: "shorn of delicacies and meends") never takes one.
# ---------------------------------------------------------------------------

GAMAK_VISIT_MS: Final = 85        # time held on each swara of the swing
GAMAK_MOVE_MS: Final = 25         # the pull from one to the other
GAMAK_STROKE_MS: Final = 250      # a new stroke about this often
GAMAK_SUBDIVISIONS: Final = (1.0, 0.5, 0.25)   # stroke grid choices, in beats

# The pairs a master's gat actually swings — told to the composer as idiom, not enforced.
GAMAK_PAIRS: dict[str, tuple[str, ...]] = {
    "darbari": ("g<>m", "m<>P", "d<>n", "P<>d in the mandra"),
}


def gamak_interval(raga: str, swara: str, partner: str) -> int | None:
    """The signed semitones from `swara` to `partner` when the partner is its adjacent raga
    neighbour and the swing is legal both ways (the direction rule: a descent-only swara is
    never entered from below, an ascent-only one never from above); None otherwise."""
    allowed = RAGAS[raga]["allowed"]
    if swara not in allowed or partner not in allowed:
        return None
    rules = directional_varjya(raga)
    up, _ = scale_step_up(swara, raga, 1)
    down, _ = scale_step_up(swara, raga, -1)
    if partner == up and rules.get(partner) != "avaroha" and rules.get(swara) != "aroha":
        return (SWARAS[partner] - SWARAS[swara]) % 12 or 12
    if partner == down and rules.get(partner) != "aroha" and rules.get(swara) != "avaroha":
        return -((SWARAS[swara] - SWARAS[partner]) % 12 or 12)
    return None


def gamak_stroke_beats(bpm: int) -> float:
    """The stroke grid nearest the measured ~250 ms: an eighth at 120 bpm, a sixteenth at 64."""
    return min(GAMAK_SUBDIVISIONS, key=lambda b: abs(b * 60000.0 / bpm - GAMAK_STROKE_MS))


GAMAK_VISIT_SPREAD: Final = 0.25   # each stroke's visits vary +/-25% (measured 35-210 ms)
GAMAK_SETTLE_SHARE: Final = 0.9    # the swing is home by this share of the stroke — a varied,
                                   # longer swing otherwise ended ON the next stroke, 9 cents short


def gamak_stroke_path(stroke_ms: float, interval: int,
                      seed: float | None = None) -> list[list[float]]:
    """One stroke of a gamak: out to the partner and back, as many round trips as fit
    (at least one, compressed when the stroke is short), ending home. (ms, semitones). With a
    `seed` (the stroke's start) its visits are a little longer or shorter than the median."""
    base = GAMAK_VISIT_MS
    if seed is not None:
        base *= 1.0 + GAMAK_VISIT_SPREAD * (2 * vary(seed, 1) - 1)
    trip = 2 * (base + GAMAK_MOVE_MS)
    trips = max(1, int(stroke_ms * GAMAK_SETTLE_SHARE // trip))
    scale = min(1.0, stroke_ms * GAMAK_SETTLE_SHARE / (trips * trip))
    visit, move = base * scale, GAMAK_MOVE_MS * scale
    path: list[list[float]] = [[0.0, 0.0]]
    t = 0.0
    for _ in range(trips):
        for a, b in ((0.0, interval), (interval, 0.0)):
            path.append([round(t + visit, 1), float(a)])
            t += visit + move
            path.append([round(t, 1), float(b)])
    return path


def render_gamak(raga: str) -> str:
    """The gamak line of the raga facts (the lead's and the composer's): none in a khada raga;
    otherwise how to write one, and the pairs a master's gat was heard to swing, where measured."""
    if raga in KHADA_RAGAS:
        return "NONE: this raga is sung khada (direct, unwavering) — never write gamak_with"
    pairs = GAMAK_PAIRS.get(raga)
    heard = f"; a master's gat in this raga swings {', '.join(pairs)}" if pairs else ""
    return f"write a gamak cell with \"gamak_with\" (an adjacent swara){heard}"
