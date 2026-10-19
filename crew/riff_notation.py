"""
THE COMPACT RIFF NOTATION — one avartan cycle of guitar or bass as one short string.

Why (2026-10-13, Sujit: "do compact format too"): the rhythm-section call wrote every note as a
JSON object with all eight fields spelled out, nulls included — 264 notes at ~110 characters each
on `fusion_20261013_074703`. Output tokens are what a call waits on and pays for, so the model now
writes each cycle in the notation it already READS the sitar in (`crew/lead_notation.py`: an
octave as `(+1)`, a length as `[beats]`), and code parses it back into the `RiffNote`s the rest of
the pipeline plays. Nothing downstream changes.

A cycle is tokens separated by spaces:

    <swara>[(<octave>)][+<chord swara>...][<beats>][<flags>]      a note
    -[<beats>]                                                      a silence

    d[2]  d[.5]pm!  P[.5]pm@100  -[1]  S(+1)+P[1]  R(-1)[1]sl

Flags, in any order: a technique code (`TECHNIQUE_CODES` — pm palm_mute, sl slide, ls long_slide,
ps pick_scrape, bd bend, ho hammer_on, po pull_off; the full name works too), `!` a deliberate
single note (never voiced into a power chord), `@<1-127>` the velocity. Pure.
"""

from __future__ import annotations

import re
from typing import Final, get_args

from crew.contracts import RiffNote, RiffTechnique
from raga import SWARAS

TECHNIQUE_CODES: Final[dict[str, str]] = {
    "pm": "palm_mute", "sl": "slide", "ls": "long_slide", "ps": "pick_scrape",
    "bd": "bend", "ho": "hammer_on", "po": "pull_off",
}
_CODE_OF: Final[dict[str, str]] = {name: code for code, name in TECHNIQUE_CODES.items()}
_TECHNIQUES: Final[frozenset[str]] = frozenset(get_args(RiffTechnique))
_REST: Final = "-"

_SWARA = "|".join(sorted(SWARAS, key=len, reverse=True))
_TOKEN: Final = re.compile(
    rf"^(?P<swara>{_SWARA}|-)"
    r"(?:\((?P<oct>[+-]?\d)\))?"
    rf"(?P<chord>(?:\+(?:{_SWARA}))*)"
    r"\[(?P<dur>\d*\.?\d+)\]"
    r"(?P<flags>.*)$")
_FLAG: Final = re.compile(r"!|@\d+|[a-z_]+")


class NotationError(ValueError):
    """A token the notation cannot read — its message names the token and what is wrong."""


def parse_cycle(text: str) -> list[RiffNote]:
    """One cycle's string -> its notes. Raises `NotationError` on the first unreadable token."""
    tokens = text.split()
    if not tokens:
        raise NotationError("an empty cycle — write at least one note or silence")
    return [_parse_token(tok) for tok in tokens]


def _parse_token(token: str) -> RiffNote:
    match = _TOKEN.match(token)
    if match is None:
        raise NotationError(f"'{token}' is not a note — write swara(octave)+chord[beats]flags, "
                            f"e.g. d[.5]pm or S(+1)+P[1] (the octave mark goes on the root only; "
                            f"chord tones are bare swaras), or -[beats] for a silence")
    dur = float(match["dur"])
    if dur <= 0:
        raise NotationError(f"'{token}' has no length — [beats] must be more than 0")
    if match["swara"] == _REST:
        return RiffNote(swara="S", dur=dur, rest=True)
    chord = [c for c in match["chord"].split("+") if c] or None
    note = {"swara": match["swara"], "oct": int(match["oct"] or 0), "dur": dur, "chord": chord}
    return RiffNote(**note, **_flags(token, match["flags"]))


def _flags(token: str, text: str) -> dict:
    """The technique / single / velocity flags after the length."""
    out: dict = {}
    rest = _FLAG.sub("", text)
    if rest:
        raise NotationError(f"'{token}' ends in '{rest}', which is not a flag (a technique code, "
                            f"! or @velocity)")
    for flag in _FLAG.findall(text):
        if flag == "!":
            out["single"] = True
        elif flag.startswith("@"):
            vel = int(flag[1:])
            if not 1 <= vel <= 127:
                raise NotationError(f"'{token}' has velocity {vel} — use 1-127")
            out["vel"] = vel
        else:
            technique = TECHNIQUE_CODES.get(flag, flag)
            if technique not in _TECHNIQUES:
                raise NotationError(f"'{token}' uses '{flag}', not a technique "
                                    f"({' '.join(TECHNIQUE_CODES)})")
            out["technique"] = technique
    return out


def render_cycle(notes: list[RiffNote]) -> str:
    """Notes -> one cycle's string, the inverse of `parse_cycle` (default velocity left out)."""
    return " ".join(_render_note(n) for n in notes)


def _beats(dur: float) -> str:
    """A length the way the examples write it: 2, 1.5, .5, .25."""
    text = f"{dur:g}"
    return text[1:] if text.startswith("0.") else text


def _render_note(n: RiffNote) -> str:
    length = f"[{_beats(n.dur)}]"
    if n.rest:
        return _REST + length
    token = n.swara + (f"({n.oct:+d})" if n.oct else "")
    token += "".join(f"+{c}" for c in n.chord or [])
    token += length
    token += _CODE_OF.get(n.technique, "") if n.technique else ""
    token += "!" if n.single else ""
    token += f"@{n.vel}" if n.vel != RiffNote.model_fields["vel"].default else ""
    return token
