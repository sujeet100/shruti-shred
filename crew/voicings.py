"""
CHORD VOICINGS for the rhythm guitar — named shapes, each built inside the raga.

The 2026-10-12 harmony brief: "a chord should not always have the same three-note power-chord
shape", but "do not blindly build major or minor chords from every raga note" — E5 in D Darbari
holds a B natural the raga does not have. So a shape is a recipe of intervals above a root, and a
tone the raga does not hold makes the shape unavailable on that root: the guitar falls back to
the power chord, then to the bare octave (which is always legal).

  power   root + fifth + octave           octave   root + octave
  fifth   root + fifth (open)             sus2     root + second + fifth
  sus4    root + fourth + fifth           fourths  root + fourth + octave
  triad   root + the raga's own third + fifth (a modal triad — only where both are in the raga)

The renderer seats each chord tone at a distortion-consonant interval (`render._CHORD_SEATS`: a
second as an add9, a third as a tenth), so these are heavy-guitar voicings, not piano chords.
Under a held, swaying sitar note the shape is kept CONSERVATIVE (power / octave / fifth): a third or
a second against a microtonal andolan is exactly the clash the brief warns about. Pure.
"""

from __future__ import annotations

from typing import Final

from raga import RAGAS, SWARAS

_BY_SEMITONE: Final = {semi: name for name, semi in SWARAS.items()}
_FIFTH: Final = 7
_FOURTH: Final = 5
_SECOND: Final = 2
_THIRDS: Final = (3, 4)
CONSERVATIVE: Final = frozenset({"power", "octave", "fifth"})


def _tone(root: str, semitones: int, raga: str) -> str | None:
    """The swara `semitones` above `root`, if the raga holds it."""
    name = _BY_SEMITONE[(SWARAS[root] + semitones) % 12]
    return name if name in RAGAS[raga]["allowed"] else None


def _third(root: str, raga: str) -> str | None:
    """The raga's own third above the root — the swara two steps up its ladder, when that lands a
    minor or major third away (a raga with a gap there has no triad on this root)."""
    ladder = [sw for sw in RAGAS[raga]["allowed"]]
    order = sorted(ladder, key=lambda sw: (SWARAS[sw] - SWARAS[root]) % 12)
    above = [sw for sw in order if sw != root]
    if len(above) < 2:
        return None
    third = above[1]
    return third if (SWARAS[third] - SWARAS[root]) % 12 in _THIRDS else None


def _recipe(root: str, name: str, raga: str) -> list[str | None]:
    fifth = _tone(root, _FIFTH, raga)
    return {
        "power": [fifth, root],
        "octave": [root],
        "fifth": [fifth],
        "sus2": [_tone(root, _SECOND, raga), fifth],
        "sus4": [_tone(root, _FOURTH, raga), fifth],
        "fourths": [_tone(root, _FOURTH, raga), root],
        "triad": [_third(root, raga), fifth],
    }.get(name, [None])


def available(root: str, name: str, raga: str) -> bool:
    """Can this shape be built on this root inside the raga?"""
    return root in RAGAS[raga]["allowed"] and None not in _recipe(root, name, raga)


def voice(root: str, name: str, raga: str, *, conservative: bool = False) -> tuple[str, list[str]]:
    """(the shape actually used, its chord tones) for `root` — the requested shape, else the power
    chord, else the octave. `conservative` restricts the shape to power / octave / fifth."""
    wanted = name if not conservative or name in CONSERVATIVE else "power"
    for shape in (wanted, "power", "octave"):
        if available(root, shape, raga):
            return shape, [t for t in _recipe(root, shape, raga) if t is not None]
    return "octave", [root]
