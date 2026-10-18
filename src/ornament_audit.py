"""
ORNAMENT AUDIT — checks on the rendered MIDI that a pitch gesture does what it means.

A MIDI file can be perfectly valid and still sound wrong. The 2026-10-12 Darbari render
(`fusion_20261012_213455`) passed every legality check, yet its 0:07 Ga ended 40 cents flat in a
decaying tail with an unbent copy of the swara ringing against it. These are the checkable halves
of what made it sound out of tune, read straight off the file the synthesizer plays:

  * UNSETTLED — a bent note whose wheel is not back at 0 when it ends (or the next note starts):
    the gesture never comes home to its swara;
  * HELD AWAY — the wheel held away from 0 for longer than `HELD_AWAY_MAX_S`: an excursion that
    stops being an ornament and becomes a wrong note (the loop to Ma holds at most ~0.25 s, a
    meend sounds at its target with the wheel at 0, so neither trips it);
  * DETUNED UNISON — a note sounding unbent on one channel while the SAME pitch is bent on
    another: the sympathetic copy beating against the moving string;
  * CLIPPED — the wheel pinned at its limit: a bend asked for more than the armed range;
  * MECHANICAL — one bend trajectory repeated many times: a fixed effect, not a hand;
  * FOREIGN DWELL — a bend that lingers on a pitch the raga does not own (given the raga and Sa):
    a glide may PASS one, but a turn or hold there is heard as that swara. The Bageshree alap of
    `fusion_20261013_081705` swung komal Ga up to shuddha Ga and turned there ~250 ms, three
    times; it passed every other check (its hold, at 0.25 s, was under HELD_AWAY_MAX_S).

Pure analysis (it reads a file and returns findings; it prints nothing). The audio half — what the
synthesizer actually sounded — is `crew/pitch_audit.py`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Final

import mido

HELD_AWAY_MAX_S: Final = 0.30      # longer than the longest measured hold at a neighbour (245 ms)
# Within this of a swara, a pitch is heard AS that swara (half way to the next is ambiguous)...
FOREIGN_NEAR_CENTS: Final = 30
# ...and staying there longer than this is a dwell: a release from Ma to Ga crosses shuddha Ga's
# 60-cent window in ~50 ms; the faulty sway sat in it ~250 ms.
FOREIGN_DWELL_MAX_S: Final = 0.08
_SAMPLE_S: Final = 0.005
MECHANICAL_MIN_REPEATS: Final = 4  # one exact trajectory this often is a fixed effect
_MOVING_VALUES: Final = 3          # a trajectory through this many pitches MOVES — a kan's step onto
                                   # a fret (and a note held at its shruti) is meant to repeat
_WHEEL_LIMIT: Final = 8191
_EPS: Final = 1e-6


@dataclass(frozen=True)
class Finding:
    kind: str          # unsettled | held_away | detuned_unison | clipped | mechanical | foreign_dwell
    time_s: float
    channel: int
    detail: str


@dataclass
class _Note:
    channel: int
    pitch: int
    on: float
    off: float


def _timeline(path: str) -> tuple[list[_Note], dict[int, list[tuple[float, int]]]]:
    """Notes and per-channel wheel events, in seconds."""
    mid = mido.MidiFile(path)
    notes: list[_Note] = []
    wheel: dict[int, list[tuple[float, int]]] = defaultdict(list)
    open_notes: dict[tuple[int, int], float] = {}
    t = 0.0
    for msg in mid:                                  # iterating a MidiFile yields seconds
        t += msg.time
        if msg.type == "pitchwheel":
            wheel[msg.channel].append((t, msg.pitch))
        elif msg.type == "note_on" and msg.velocity > 0:
            open_notes[(msg.channel, msg.note)] = t
        elif msg.type in ("note_off", "note_on"):
            on = open_notes.pop((msg.channel, msg.note), None)
            if on is not None:
                notes.append(_Note(msg.channel, msg.note, on, t))
    return sorted(notes, key=lambda n: n.on), wheel


def _wheel_at(events: list[tuple[float, int]], t: float) -> int:
    value = 0
    for when, v in events:
        if when > t + _EPS:
            break
        value = v
    return value


def _segments(events: list[tuple[float, int]], end: float) -> list[tuple[float, float, int]]:
    """(start, end, value) runs of a constant wheel value."""
    runs = []
    for (t0, v), (t1, _) in zip(events, events[1:] + [(end, 0)]):
        if t1 > t0:
            runs.append((t0, t1, v))
    return runs


def _bent_channels(wheel: dict[int, list[tuple[float, int]]]) -> set[int]:
    return {ch for ch, ev in wheel.items() if any(v != 0 for _, v in ev)}


def _unsettled(notes: list[_Note], wheel: dict[int, list[tuple[float, int]]]) -> list[Finding]:
    out = []
    for ch in _bent_channels(wheel):
        mine = [n for n in notes if n.channel == ch]
        for a, b in zip(mine, mine[1:] + [None]):
            end = min(a.off, b.on) if b is not None else a.off
            left = _wheel_at(wheel[ch], end - 0.002)
            if left != 0:
                out.append(Finding("unsettled", round(end, 3), ch,
                                   f"pitch {a.pitch} ends {left * 12 / _WHEEL_LIMIT * 100:+.0f} "
                                   f"cents off its swara"))
    return out


_FLAT_CENTS: Final = 5             # a run of wheel values within this of each other is a HOLD
INTONATION_MAX_CENTS: Final = 35   # a hold this close to the swara is INTONATION (an ati-komal
                                   # Ga sung low on purpose), not an excursion; the old andolan's
                                   # fault held at -44


def _held_away(notes: list[_Note], wheel: dict[int, list[tuple[float, int]]],
               bend_range: int) -> list[Finding]:
    """Flat holds away from the swara: the wheel resting at one non-zero value (within
    `_FLAT_CENTS`) for longer than `HELD_AWAY_MAX_S` while a note sounds. A continuous swing is
    not a hold; the old andolan's 300 ms plateau at the far edge was."""
    tol = _FLAT_CENTS / 100 / bend_range * _WHEEL_LIMIT
    out = []
    for ch in _bent_channels(wheel):
        end = max((n.off for n in notes if n.channel == ch), default=0.0)
        run: tuple[float, int] | None = None
        for t0, _t1, v in _segments(sorted(wheel[ch]), end) + [(end, end, 0)]:
            if run is not None and (v == 0 or abs(v - run[1]) > tol):
                held = t0 - run[0]
                sounding = any(n.channel == ch and n.on <= run[0] < n.off for n in notes)
                cents = abs(run[1]) * bend_range / _WHEEL_LIMIT * 100
                if sounding and held > HELD_AWAY_MAX_S and cents > INTONATION_MAX_CENTS:
                    cents = run[1] * bend_range / _WHEEL_LIMIT * 100
                    out.append(Finding("held_away", round(run[0], 3), ch,
                                       f"held {held:.2f} s at {cents:+.0f} cents from the swara"))
                run = None
            if run is None and v != 0:
                run = (t0, v)
    return out


_AUDIBLE_OVERLAP_S: Final = 0.02  # a clash shorter than this is not heard (a kan's 1 ms pre-bend)
UNISON_TOLERANCE_CENTS: Final = 10  # a shruti-tuned note against its tempered taraf: a shimmer


def _tolerance(bend_range: int) -> float:
    return UNISON_TOLERANCE_CENTS / 100 / bend_range * _WHEEL_LIMIT


def _time_away(events: list[tuple[float, int]], lo: float, hi: float,
               tol: float = 0.0) -> tuple[float, float]:
    """(seconds the wheel is more than `tol` away from 0 inside [lo, hi), when it first is)."""
    if hi <= lo:
        return 0.0, lo
    points = [(lo, _wheel_at(events, lo))] + [(t, v) for t, v in events if lo < t < hi]
    away, first = 0.0, hi
    for (t0, v), (t1, _) in zip(points, points[1:] + [(hi, 0)]):
        if abs(v) > tol:
            away += t1 - t0
            first = min(first, t0)
    return away, first


def _detuned_unison(notes: list[_Note], wheel: dict[int, list[tuple[float, int]]],
                    bend_range: int = 12) -> list[Finding]:
    out = []
    bent = _bent_channels(wheel)
    for a in (n for n in notes if n.channel in bent):
        for b in notes:
            if b.channel == a.channel or b.channel in bent or b.pitch != a.pitch:
                continue
            lo, hi = max(a.on, b.on), min(a.off, b.off)
            away, first = _time_away(wheel[a.channel], lo, hi, _tolerance(bend_range))
            if away >= _AUDIBLE_OVERLAP_S:
                out.append(Finding("detuned_unison", round(first, 3), b.channel,
                                   f"pitch {b.pitch} rings unbent while channel {a.channel} "
                                   f"bends the same note"))
                break
    return out


def _clipped(wheel: dict[int, list[tuple[float, int]]]) -> list[Finding]:
    return [Finding("clipped", round(t, 3), ch, "the wheel is pinned at its limit")
            for ch, ev in wheel.items() for t, v in ev if abs(v) >= _WHEEL_LIMIT]


def _mechanical(notes: list[_Note], wheel: dict[int, list[tuple[float, int]]]) -> list[Finding]:
    shapes: Counter[tuple] = Counter()
    first: dict[tuple, tuple[float, int]] = {}
    for n in notes:
        ev = [(round(t - n.on, 2), v) for t, v in wheel.get(n.channel, []) if n.on <= t < n.off]
        if len({v for _, v in ev if v != 0}) >= _MOVING_VALUES:     # a swing or glide, not a step
            shape = tuple(ev)
            shapes[shape] += 1
            first.setdefault(shape, (n.on, n.channel))
    return [Finding("mechanical", round(first[s][0], 3), first[s][1],
                    f"the same bend trajectory {count} times")
            for s, count in shapes.items() if count >= MECHANICAL_MIN_REPEATS]


def _foreign_dwell(notes: list[_Note], wheel: dict[int, list[tuple[float, int]]],
                   bend_range: int, sa: int, owned: frozenset[int]) -> list[Finding]:
    """Bent notes that stay within `FOREIGN_NEAR_CENTS` of a pitch class outside `owned` (semitones
    from Sa) for longer than `FOREIGN_DWELL_MAX_S`. Octave-blind: the sitar sounds transposed."""
    out = []
    bent = _bent_channels(wheel)
    for n in (n for n in notes if n.channel in bent):
        run, t = 0.0, n.on
        while t < n.off:
            semis = n.pitch - sa + _wheel_at(wheel[n.channel], t) * bend_range / _WHEEL_LIMIT
            near = round(semis)
            foreign = abs(semis - near) * 100 <= FOREIGN_NEAR_CENTS and near % 12 not in owned
            run = run + _SAMPLE_S if foreign else 0.0
            if run > FOREIGN_DWELL_MAX_S:
                out.append(Finding("foreign_dwell", round(t - run, 3), n.channel,
                                   f"pitch {n.pitch} lingers on semitone {near % 12} from Sa, "
                                   f"which the raga does not own"))
                break
            t += _SAMPLE_S
    return out


def owned_pitch_classes(raga: str) -> frozenset[int]:
    """The semitones from Sa a raga's swaras occupy."""
    from raga import RAGAS, SWARAS
    return frozenset(SWARAS[sw] % 12 for sw in RAGAS[raga]["allowed"])


def audit_midi(path: str, *, bend_range: int = 12, raga: str | None = None,
               sa: int | None = None) -> list[Finding]:
    """Every finding in a rendered MIDI file, in time order. `bend_range` is the semitones the
    channels are armed with (the renderer's MEEND_RANGE). Given the `raga` and its `sa` (MIDI
    pitch), bends are also checked for dwelling on pitches the raga does not own."""
    notes, wheel = _timeline(path)
    findings = (_unsettled(notes, wheel) + _held_away(notes, wheel, bend_range)
                + _detuned_unison(notes, wheel, bend_range) + _clipped(wheel)
                + _mechanical(notes, wheel))
    if raga is not None and sa is not None:
        findings += _foreign_dwell(notes, wheel, bend_range, sa, owned_pitch_classes(raga))
    return sorted(findings, key=lambda f: f.time_s)
