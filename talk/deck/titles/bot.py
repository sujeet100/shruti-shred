"""The DevDay bot (2026-10-18): one small geometric character, the conference motif, varied per talk.

Sujit chose the bot over the line motifs, then asked for it smaller, as a character rather than a
backdrop. It is flat geometry, deliberately not cute: a lavender rounded head with a dark face
screen, two square cyan eyes and no mouth, a cyan ear on one side and an amber dial (its one
asymmetric detail), a body and two short legs. Every talk keeps that figure and changes what it
holds or how it moves; `bot()` draws it anywhere at any size, with an instrument or none.

This talk's bot is a musician: it plays a sitar, nods its head in time (a restrained headbang: this
is a metal band) and strums on the beat; its eyes blink now and then. Motion is SMIL, no script.
Pure geometry; SVG children in the slide's 1920 x 1080 space.
"""
from __future__ import annotations

from typing import Final

LAVENDER, LIMB, DEEP = "#B9A3E0", "#9C84CC", "#27235A"
CYAN, AMBER, TERRA = "#79B8CC", "#E0AA55", "#D26F5D"

BEAT_S: Final = 0.9          # one head nod (about 67 nods a minute: a slow, heavy groove)
BLINK_S: Final = 4.6
NOD_DEG: Final = 5
STRUM_DEG: Final = 7


def _blink(y: float, h: float) -> str:
    keys = 'keyTimes="0;0.92;0.95;1" dur="{0:g}s" repeatCount="indefinite"'.format(BLINK_S)
    return (f'<animate attributeName="height" values="{h};{h};6;{h}" {keys}/>'
            f'<animate attributeName="y" values="{y};{y};{y + h / 2 - 3};{y}" {keys}/>')


def _swing(deg: float, cx: float, cy: float, period: float) -> str:
    return (f'<animateTransform attributeName="transform" type="rotate" values="0 {cx} {cy};{deg} {cx} {cy};0 {cx} {cy}" '
            f'dur="{period:g}s" repeatCount="indefinite" calcMode="spline" keyTimes="0;0.5;1" '
            f'keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>')


def _head(animated: bool) -> str:
    """The head, nodding about the neck. Local coordinates: the figure is ~460 x 560."""
    eyes = "".join(f'<rect x="{x}" y="95" width="46" height="46" rx="8" fill="{CYAN}">{_blink(95, 46) if animated else ""}</rect>'
                   for x in (128, 228))
    parts = (f'<rect x="50" y="0" width="300" height="230" rx="62" fill="{LAVENDER}"/>'
             f'<rect x="24" y="82" width="34" height="74" rx="12" fill="{CYAN}"/>'
             f'<circle cx="98" cy="40" r="17" fill="{AMBER}"/><circle cx="98" cy="40" r="6" fill="{LAVENDER}"/>'
             f'<rect x="88" y="62" width="228" height="118" rx="40" fill="{DEEP}"/>{eyes}')
    nod = _swing(NOD_DEG, 200, 240, BEAT_S) if animated else ""
    return f'<g>{nod}{parts}</g>'


def _body() -> str:
    return (f'<rect x="168" y="226" width="64" height="30" fill="{DEEP}"/>'
            f'<rect x="70" y="250" width="260" height="212" rx="52" fill="{LAVENDER}"/>'
            f'<rect x="116" y="452" width="58" height="96" rx="22" fill="{LAVENDER}"/>'
            f'<rect x="226" y="452" width="58" height="96" rx="22" fill="{LAVENDER}"/>')


def _sitar() -> str:
    """A sitar held across the body: the big gourd low on the left, the long neck rising right."""
    frets = "".join(f'<rect x="{x}" y="-15" width="5" height="30" fill="{DEEP}" opacity="0.55"/>' for x in range(150, 420, 34))
    neck = (f'<g transform="translate(72 452) rotate(-38)">'
            f'<rect x="0" y="-16" width="452" height="32" rx="10" fill="{AMBER}"/>{frets}'
            f'<rect x="20" y="-2" width="420" height="4" fill="#FEFCFA" opacity="0.8"/></g>')
    return (neck + f'<circle cx="62" cy="468" r="80" fill="{TERRA}"/><circle cx="62" cy="468" r="34" fill="{DEEP}" opacity="0.35"/>'
            f'<circle cx="430" cy="174" r="26" fill="{TERRA}"/>')


def _arms(animated: bool) -> str:
    """The fretting arm reaches up to the high neck; the plucking arm swings on the beat just above
    the gourd. Neither crosses the chest."""
    style = f'stroke="{LIMB}" stroke-width="34" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    fret = (f'<path d="M318 296 L384 316 L356 240" {style}/><circle cx="356" cy="240" r="21" fill="{LIMB}"/>')
    pluck = (f'<path d="M82 296 L52 372 L116 402" {style}/><circle cx="116" cy="402" r="21" fill="{LIMB}"/>')
    swing = _swing(-STRUM_DEG, 82, 296, BEAT_S / 2) if animated else ""
    return fret + f'<g>{swing}{pluck}</g>'


INSTRUMENTS: Final = {"sitar": _sitar, None: lambda: ""}


def bot(x: float, y: float, scale: float = 1.0, *, instrument: str | None = "sitar", animated: bool = True) -> str:
    """The bot with its top-left at (x, y) on the slide, `scale` x its ~460 x 560 size."""
    held = INSTRUMENTS[instrument]()
    arms = _arms(animated) if instrument else ""
    return (f'<g transform="translate({x} {y}) scale({scale})">{_body()}{held}{_head(animated)}{arms}</g>')
