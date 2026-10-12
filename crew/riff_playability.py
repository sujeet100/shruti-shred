"""
Riff PLAYABILITY — can a person play this rhythm part live, on a six-string in E standard?

The texture verifier (`crew/riff_texture.py`) asks whether a riff sounds like metal; nothing
asked whether a human could play it. When the user will play the rhythm guitar themselves,
"legal but awkward at 128 bpm" is a failure, so the brief's `playable_rhythm` switches on a
second set of budgets that ride the SAME bounded re-roll (`verified_riff`'s `extra_check`):

  * reach     — every sounding pitch exists on the instrument (nothing under the open low E);
  * stretch   — every chord shape fits a four-fret box (src/fretboard.py);
  * jumps     — no position shift of `_JUMP_FRETS`+ frets in under `_JUMP_WINDOW` beats,
                measured on the least-movement fingering path, including the loop seam;
  * rhythm    — mostly eighths: sixteenths at most `_SIXTEENTH_SHARE_MAX` of the notes, and
                only in bursts of at most `_SIXTEENTH_RUN_MAX` (one beat);
  * anchor    — when the riff's low Sa IS the open low string, the riff's ground (its most
                frequent pitch) is that open string: the easiest note on the guitar, and the
                one the user asked to anchor on.

Pitches are computed exactly as the renderer will sound them (`_sequence_cycle`'s register
and floor, `render.chord_voicing` for chord tones), so the check fingers what will be heard.

Pure — no LLM, no I/O.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Final, Optional

from crew.contracts import RHYTHM_FLOOR, Arrangement, RiffNote, RiffPattern
from crew.riff_voicing import home_root
from fretboard import LOWEST_OPEN, Fingering, easiest_path, fingerings, placements, shift
from raga import SWARAS
from render import chord_voicing

_JUMP_FRETS: Final = 5               # a shift this large...
_JUMP_WINDOW: Final = 1.0            # ...in less than this many beats is a rapid jump
_SIXTEENTH: Final = 0.5 - 1e-6       # anything shorter than an eighth counts as a sixteenth
_SIXTEENTH_SHARE_MAX: Final = 0.30
_SIXTEENTH_RUN_MAX: Final = 4        # one beat of sixteenths is a burst; more is a run
_ANCHOR_MIN_SHARE: Final = 0.35      # the open low string carries at least this much of the riff
_MAX_REPORTED: Final = 3             # name a few offenders, not every one


@dataclass(frozen=True)
class _Event:
    """One sounding riff note as the guitarist meets it: when, how long, which pitches."""
    index: int
    start: float
    dur: float
    pitches: tuple[int, ...]


def playability_check(arr: Arrangement) -> Optional[Callable[[RiffPattern], list[str]]]:
    """The `extra_check` for `verified_riff`: None unless the brief asked for a playable
    rhythm part, else a function returning the cycle's playability violations."""
    if not arr.playable_rhythm:
        return None
    register = arr.registers.get("rhythm", RHYTHM_FLOOR)

    def check(pattern: RiffPattern) -> list[str]:
        return verify_playable(pattern, sa=arr.sa, register=register,
                               cycle_beats=arr.beats_per_bar, anchor=_sa_is_home(arr))
    return check


def _sa_is_home(arr: Arrangement) -> bool:
    """The open-string anchor serves a riff whose HOME is Sa. A raga whose Sa is deliberately
    weak (Marwa) must not be pushed back onto it for the guitarist's convenience."""
    return home_root(arr.raga) == "S"


def verify_playable(pattern: RiffPattern, *, sa: int, register: int,
                    cycle_beats: float, anchor: bool = True) -> list[str]:
    """Every way this cycle is hard for a human to play, as exact, actionable sentences.
    `anchor` asks for the open low string as the ground (only when the riff's home is Sa)."""
    events = _events(pattern.notes, sa=sa, register=register)
    if not events:
        return []
    violations = _reach_violations(events) + _rhythm_violations(pattern.notes)
    shapes = [fingerings(e.pitches) for e in events]
    stretched = [e for e, options in zip(events, shapes) if not options]
    if stretched:
        violations.append(_stretch_message(stretched))
    else:
        path = easiest_path(shapes)
        assert path is not None                     # every event has an option
        violations += _jump_violations(events, path, cycle_beats)
    return violations + (_anchor_violations(events, sa=sa, register=register) if anchor else [])


def render_playability(arr: Arrangement) -> str:
    """The riff-prompt block: the budgets in words, so the ask and the check agree."""
    if not arr.playable_rhythm:
        return "  (no playability constraint — write for the band's guitarist)"
    lines = [
        "  A PERSON plays this part LIVE on a six-string guitar in E standard (low to high: "
        "E A D G B E). The checks below are enforced; a miss comes back to you to fix:",
        f"  - mostly EIGHTH notes; sixteenths only in short bursts (at most "
        f"{_SIXTEENTH_RUN_MAX} in a row) and under {_SIXTEENTH_SHARE_MAX:.0%} of the notes",
        "  - every chord shape fits a four-fret box (power chords, octaves, an open low string "
        "under a fretted note); no stretches",
        f"  - no position jump of {_JUMP_FRETS}+ frets in under {_JUMP_WINDOW:g} beat — stay "
        "around one hand position and let open strings carry the moves",
        "  - one core figure with small variations, not a new idea every bar",
    ]
    if (_sa_is_home(arr)
            and _low_sa_pitch(arr.sa, arr.registers.get("rhythm", RHYTHM_FLOOR)) == LOWEST_OPEN):
        lines.append(f"  - ANCHOR on the open low string: Sa at oct 0 sounds as the open low E; "
                     f"make it the riff's ground (at least {_ANCHOR_MIN_SHARE:.0%} of the notes)")
    return "\n".join(lines)


def _events(notes: list[RiffNote], *, sa: int, register: int) -> list[_Event]:
    events: list[_Event] = []
    t = 0.0
    for i, n in enumerate(notes):
        if not n.rest:
            octave = max(register + n.oct, RHYTHM_FLOOR)
            root = sa + SWARAS[n.swara] + 12 * octave
            tones = chord_voicing(root, [sa + SWARAS[c] + 12 * octave for c in n.chord or []])
            events.append(_Event(i, t, n.dur, (root, *tones)))
        t += n.dur
    return events


def _low_sa_pitch(sa: int, register: int) -> int:
    return sa + 12 * max(register, RHYTHM_FLOOR)


def _name(e: _Event) -> str:
    return f"note #{e.index + 1}"


def _reach_violations(events: list[_Event]) -> list[str]:
    low = [e for e in events if any(not placements(p) for p in e.pitches)]
    if not low:
        return []
    names = ", ".join(_name(e) for e in low[:_MAX_REPORTED])
    return [f"{names} sound(s) outside the guitar's range (lowest note is the open low E) — "
            f"raise the octave"]


def _rhythm_violations(notes: list[RiffNote]) -> list[str]:
    sounding = [n for n in notes if not n.rest]
    if not sounding:
        return []
    out: list[str] = []
    share = sum(n.dur < _SIXTEENTH for n in sounding) / len(sounding)
    if share > _SIXTEENTH_SHARE_MAX:
        out.append(f"{share:.0%} of the notes are faster than eighths — keep sixteenths under "
                   f"{_SIXTEENTH_SHARE_MAX:.0%}; a live player needs an eighth-note pulse")
    run = longest = 0
    for n in notes:
        run = run + 1 if (not n.rest and n.dur < _SIXTEENTH) else 0
        longest = max(longest, run)
    if longest > _SIXTEENTH_RUN_MAX:
        out.append(f"a run of {longest} sixteenths — keep bursts to {_SIXTEENTH_RUN_MAX} "
                   f"(one beat), then land on a longer note")
    return out


def _stretch_message(stretched: list[_Event]) -> str:
    names = ", ".join(_name(e) for e in stretched[:_MAX_REPORTED])
    return (f"{names}: the chord shape needs a stretch wider than four frets — voice it as a "
            f"power chord or an octave")


def _jump_violations(events: list[_Event], path: list[Fingering], cycle_beats: float) -> list[str]:
    jumps: list[str] = []
    # the loop seam counts: the last note of the cycle runs straight into the first
    pairs = list(zip(range(len(events)), range(1, len(events)))) + [(len(events) - 1, 0)]
    for a, b in pairs:
        gap = (events[b].start - events[a].start) % cycle_beats or cycle_beats
        frets = shift(path[a], path[b])
        if frets >= _JUMP_FRETS and gap < _JUMP_WINDOW:
            jumps.append(f"{_name(events[a])} -> {_name(events[b])} ({frets} frets in {gap:g} beat)")
    if not jumps:
        return []
    return [f"rapid position jump(s): {'; '.join(jumps[:_MAX_REPORTED])} — keep the hand near "
            f"one position, or give the move a longer note before it"]


def _anchor_violations(events: list[_Event], *, sa: int, register: int) -> list[str]:
    low_sa = _low_sa_pitch(sa, register)
    if low_sa != LOWEST_OPEN:
        return []                       # the open low string is not this riff's Sa
    roots = Counter(e.pitches[0] for e in events)
    share = roots[LOWEST_OPEN] / len(events)
    if roots.most_common(1)[0][0] == LOWEST_OPEN and share >= _ANCHOR_MIN_SHARE:
        return []
    return [f"the open low E (Sa, oct 0) carries only {share:.0%} of the notes — make it the "
            f"riff's ground (at least {_ANCHOR_MIN_SHARE:.0%}, more than any other pitch)"]
