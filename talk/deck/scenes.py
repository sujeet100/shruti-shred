"""Animated pattern scenes (2026-10-18, Sujit): our band acting each pattern out — the characters in
the pattern's shape, messages flying between them as envelopes, speech bubbles popping up as they
speak, a ring when one works or decides. One SVG timeline per scene (SMIL, no script), looping.

Words in the bubbles are VERBATIM from traces (or a status line the Flow's code publishes), trimmed only
with "…"; an action ("re-composes section 4") is set in italics without quote marks. Sources per
scene below. SVG text cannot load the deck's web fonts, so bubbles use a system sans serif — the price
of keeping the words in time with the moving envelopes.

Pure: actors (placed by the slide builder, which owns the sprites) and the SVG overlay.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import visuals as V

INDIGO, CARD, MUTED, LINE = V.INDIGO, V.CARD, V.MUTED, V.LINE
TERRA, MUSTARD, SKY, PURPLE = V.TERRA, V.MUSTARD, V.SKY, V.PURPLE
W, H = 1664, 430
PERIOD_S: Final = 10.0
FONT: Final = "Mulish, 'Helvetica Neue', Arial, sans-serif"
TEXT_PX: Final = 32
WRAP: Final = 26          # characters per bubble line
HALF_H: Final = 76        # half a character's height (sprites at scale 2.3)


@dataclass(frozen=True)
class Actor:
    key: str
    kind: str             # a band sprite key, or code / tool / person / judge / canvas / out
    x: float
    y: float
    label: str


@dataclass(frozen=True)
class Send:
    a: str
    b: str
    t0: float             # seconds into the loop
    t1: float
    color: str = MUSTARD
    dashed: bool = False
    bend: float = 0.0     # curve the path sideways (two messages between one pair)


@dataclass(frozen=True)
class Say:
    a: str
    text: str
    t0: float
    t1: float
    quote: bool = True
    side: str = "above"   # above | below | right | left — where the bubble sits beside its speaker


@dataclass(frozen=True)
class Pulse:
    a: str
    t: float
    color: str = SKY


@dataclass(frozen=True)
class Scene:
    actors: tuple[Actor, ...]
    events: tuple[Send | Say | Pulse, ...]
    source: str


# --------------------------------------------------------------------------- #
# The scenes.                                                                 #
# --------------------------------------------------------------------------- #

SCENES: Final[dict[str, Scene]] = {
    "orchestrator": Scene(
        (Actor("pandit", "pandit", 170, 90, "Pandit"), Actor("riffsmith", "riffsmith", 400, 300, "Riffsmith"),
         Actor("lead", "lead", 1000, 90, "Lead"), Actor("riff", "riff", 1000, 300, "Riff"),
         Actor("song", "out", 1520, 195, "the song")),
        (Send("pandit", "riffsmith", 0.3, 1.2, bend=-30), Say("pandit", "…an opening Alaap…", 0.3, 2.4, side="right"),
         Send("riffsmith", "pandit", 2.5, 3.4, PURPLE, bend=-30),
         Say("riffsmith", "I shortened the intro… added a high-tension Taan…", 2.5, 4.8, side="right"),
         Say("pandit", "I accept this structure…", 4.9, 6.2, side="right"),
         Send("pandit", "lead", 6.3, 7.2), Send("pandit", "riff", 6.3, 7.2),
         Pulse("lead", 7.3), Pulse("riff", 7.3),
         Send("lead", "song", 7.8, 8.7, SKY), Send("riff", "song", 7.8, 8.7, SKY), Pulse("song", 8.8)),
        "trace 6cb40c236412 (2026-07-11): Pandit/Riffsmith notes"),
    # The first band's plan, alone (Sujit, 2026-10-20: slide 17 explains only the two composers' collaboration).
    "composers": Scene(
        (Actor("pandit", "pandit", 300, 110, "Pandit"), Actor("riffsmith", "riffsmith", 1320, 110, "Riffsmith"),
         Actor("plan", "canvas", 810, 300, "the shared plan")),
        (Send("pandit", "plan", 0.3, 1.2, bend=-20), Say("pandit", "…an opening Alaap…", 0.3, 2.4, side="right"),
         Pulse("plan", 1.3), Send("plan", "riffsmith", 1.6, 2.5, bend=-20),
         Send("riffsmith", "plan", 2.7, 3.6, PURPLE, bend=20),
         Say("riffsmith", "I shortened the intro… added a high-tension Taan…", 2.7, 5.0, side="left"),
         Pulse("plan", 3.7, PURPLE), Send("plan", "pandit", 4.0, 4.9, bend=20),
         Say("pandit", "I accept this structure…", 5.1, 6.6, side="right"), Pulse("plan", 6.7, MUSTARD)),
        "trace 6cb40c236412 (2026-07-11): Pandit/Riffsmith notes"),
    "react": Scene(
        (Actor("composer", "composer", 360, 300, "Pandit"), Actor("tool", "tool", 1300, 300, "hear_phrase (code)")),
        (Send("composer", "tool", 0.3, 1.2, bend=-40), Say("composer", "calls hear_phrase on its draft", 0.3, 1.6, quote=False),
         Pulse("tool", 1.3), Say("tool", "g, 1 beat: … 0.47 s is too short to sway", 1.4, 3.4),
         Send("tool", "composer", 3.5, 4.4, SKY, dashed=True, bend=40),
         Pulse("composer", 4.5, MUSTARD), Say("composer", "holds g for two beats", 4.5, 5.8, quote=False),
         Send("composer", "tool", 5.9, 6.8, bend=-40), Pulse("tool", 6.9),
         Say("tool", "g, 2 beats: … sways toward R", 7.0, 9.4), Send("tool", "composer", 8.6, 9.5, SKY, dashed=True, bend=40)),
        "trace 8ceb769ebf63 (2026-10-18): hear_phrase reports"),
    "selfcorrect": Scene(
        (Actor("composer", "composer", 360, 300, "Pandit"), Actor("check", "code", 1300, 300, "validator (code)")),
        (Send("composer", "check", 0.3, 1.2, bend=-40), Say("composer", "writes a Bageshree phrase", 0.3, 1.6, quote=False),
         Pulse("check", 1.3, TERRA),
         Say("check", "… 'P' is DESCENT-only (the aroha skips it): touch it only on the way down …", 1.4, 4.4),
         Send("check", "composer", 4.5, 5.3, TERRA, dashed=True, bend=40),
         Pulse("composer", 5.4, MUSTARD), Say("composer", "moves Pa to the descent", 5.4, 6.6, quote=False),
         Send("composer", "check", 6.7, 7.5, bend=-40), Pulse("check", 7.6),
         Say("check", "passed", 7.7, 9.6)),
        "trace 8805efb8eceb (2026-10-13, Bageshree): guardrail retry, then pass"),
    "workflow": Scene(
        (Actor("interpreter", "interpreter", 170, 300, "Interpreter"), Actor("composer", "composer", 520, 300, "Pandit"),
         Actor("rhythm", "rhythm", 870, 300, "Rhythm section"), Actor("producer", "producer", 1220, 300, "Producer"),
         Actor("song", "out", 1530, 300, "render"), Actor("flow", "code", 300, 60, "the Flow (code)")),
        (Send("interpreter", "composer", 0.2, 0.9), Send("composer", "rhythm", 1.0, 1.7), Send("rhythm", "producer", 1.8, 2.5),
         Send("producer", "composer", 2.6, 3.5, TERRA, dashed=True, bend=70),
         Say("flow", "Revise round 1: reworking the lead — …", 2.6, 5.2, side="right"),
         Send("composer", "rhythm", 3.6, 4.3), Send("rhythm", "producer", 4.4, 5.1),
         Send("producer", "composer", 5.3, 6.2, TERRA, dashed=True, bend=70),
         Send("composer", "rhythm", 6.3, 7.0), Send("rhythm", "producer", 7.1, 7.8),
         Say("flow", "Revise cap (2) reached — stopping here; the final check decides what ships.", 7.9, 9.8, side="right"),
         Send("producer", "song", 8.0, 8.8, SKY), Pulse("song", 8.9)),
        "crew/flow.py status lines"),
    "agent": Scene(
        (Actor("manager", "model", 830, 70, "the manager"),
         Actor("interpreter", "interpreter", 170, 310, "Interpreter"), Actor("composer", "composer", 520, 310, "Pandit"),
         Actor("rhythm", "rhythm", 1140, 310, "Rhythm section"), Actor("producer", "producer", 1490, 310, "Producer")),
        (Say("manager", "who plays next?", 0.2, 1.4, quote=False, side="right"),
         Send("manager", "composer", 0.5, 1.3), Pulse("composer", 1.4, MUSTARD),
         Send("composer", "manager", 1.7, 2.5, SKY, dashed=True, bend=40),
         Say("manager", "now the Producer", 2.6, 3.8, quote=False, side="right"),
         Send("manager", "producer", 2.8, 3.6), Pulse("producer", 3.7, MUSTARD),
         Send("producer", "manager", 4.0, 4.8, SKY, dashed=True, bend=-40),
         Say("manager", "back to Pandit", 4.9, 6.1, quote=False, side="right"),
         Send("manager", "composer", 5.0, 5.8), Pulse("composer", 5.9, MUSTARD),
         Send("composer", "manager", 6.2, 7.0, SKY, dashed=True, bend=40),
         Say("manager", "done… or one more change?", 7.1, 9.6, quote=False, side="right"),
         Pulse("manager", 7.2, TERRA)),
        "an illustration, not a trace: the manager's lines are actions (italic), never quotes"),
    "evaluator": Scene(
        (Actor("composer", "composer", 360, 300, "Pandit"), Actor("producer", "producer", 1300, 300, "Producer")),
        (Send("composer", "producer", 0.3, 1.2, bend=-40),
         Say("producer", "Change the final cadential phrase… dip into the mandra…", 1.3, 3.9),
         Send("producer", "composer", 4.0, 4.9, TERRA, dashed=True, bend=40),
         Pulse("composer", 5.0, MUSTARD), Say("composer", "re-composes section 4", 5.0, 6.3, quote=False),
         Send("composer", "producer", 6.4, 7.3, bend=-40),
         Say("producer", "Replace the mechanical triple repetition…", 7.4, 9.8)),
        "trace 57af304fd1ad (2026-10-18): the Producer's plans"),
    "debate": Scene(
        (Actor("a", "composer", 260, 110, "Pandit A"), Actor("b", "composer", 1400, 110, "Pandit B"),
         Actor("judge", "judge", 830, 290, "the judge")),
        (Send("a", "b", 0.3, 1.2, SKY, bend=-40), Say("a", "…an impeccable 100% swara match…", 0.3, 3.0, side="right"),
         Send("b", "a", 3.1, 4.0, PURPLE, bend=-40), Say("b", "…scoring 0% on shared accent swaras…", 3.1, 5.8, side="left"),
         Pulse("a", 5.9, MUSTARD), Pulse("b", 5.9, MUSTARD),
         Send("a", "judge", 6.5, 7.4, SKY), Send("b", "judge", 6.5, 7.4, PURPLE), Pulse("judge", 7.5, TERRA),
         Say("judge", "picks one", 7.6, 9.6, quote=False)),
        "trace b0545e590880 (2026-10-12): debate turns"),
    # The same debate in plain actions (Sujit, 2026-10-20: slide text must read on its own; the verbatim lines
    # quote internal measures the room cannot parse).
    "composer-debate": Scene(
        (Actor("a", "composer", 260, 110, "Composer A"), Actor("b", "composer", 1400, 110, "Composer B"),
         Actor("judge", "judge", 830, 290, "the judge")),
        (Send("a", "b", 0.3, 1.2, SKY, bend=-40), Say("a", "argues for its own plan", 0.3, 3.0, quote=False, side="right"),
         Send("b", "a", 3.1, 4.0, PURPLE, bend=-40), Say("b", "argues for its own plan", 3.1, 5.8, quote=False, side="left"),
         Send("a", "judge", 6.5, 7.4, SKY), Send("b", "judge", 6.5, 7.4, PURPLE), Pulse("judge", 7.5, TERRA),
         Say("judge", "picks one", 7.6, 9.6, quote=False)),
        "illustration of the seed and head debates (2026-10-18/19); actions, not quotes"),
    # The notes debate (2026-10-19, traces 8975dcdabcef + 4b6e80296582), in plain actions, not quotes.
    "notes-win": Scene(
        (Actor("sitar", "lead", 300, 110, "Lead, sitar (Gemini)"), Actor("guitar", "rhythm", 1320, 110, "Guitar agent (GPT)"),
         Actor("check", "code", 810, 300, "the check")),
        (Send("sitar", "guitar", 0.3, 1.2, SKY, bend=-30), Say("sitar", "rewrites the end of its hook", 0.3, 2.2, quote=False, side="right"),
         Say("guitar", "your reason is wrong: the old ending wasn't on the home note", 2.3, 4.6, quote=False, side="left"),
         Send("guitar", "sitar", 4.7, 5.6, PURPLE, bend=-30), Say("guitar", "rewrites a riff: lower, palm-muted", 4.7, 6.4, quote=False, side="left"),
         Say("sitar", "then end it under my note", 6.5, 7.9, quote=False, side="right"),
         Send("sitar", "check", 8.0, 8.9, SKY), Send("guitar", "check", 8.0, 8.9, PURPLE), Pulse("check", 9.0, MUSTARD)),
        "notes debate, 2026-10-19: paraphrased actions from traces 8975dcdabcef and 4b6e80296582"),
    "collaboration": Scene(
        # The FULL pattern (Sujit, 2026-10-20): a studio room where anyone messages anyone and the players
        # decide the turns themselves. An illustration, so every line is an action (italic), never a quote.
        (Actor("sitar", "lead", 250, 90, "Sitarist"), Actor("guitar", "riff", 1410, 90, "Guitarist"),
         Actor("bass", "rhythm", 560, 320, "Bassist"), Actor("drums", "drums", 1100, 320, "Drummer")),
        (Say("bass", "I'll lay down a bass line", 0.2, 1.5, quote=False, side="right"), Send("bass", "guitar", 0.5, 1.4),
         Say("guitar", "I'll go next: a riff on top", 1.5, 2.8, quote=False, side="left"), Send("guitar", "drums", 1.8, 2.7, PURPLE),
         Say("drums", "I'll lock the kick to that riff", 2.8, 4.1, quote=False, side="left"), Send("drums", "sitar", 3.1, 4.0, SKY),
         Say("sitar", "I'll come in on beat one", 4.1, 5.4, quote=False, side="right"), Send("sitar", "bass", 4.4, 5.3, TERRA),
         Say("bass", "leave me room in bar 4?", 5.4, 6.7, quote=False, side="right"), Send("bass", "guitar", 5.7, 6.6),
         Say("guitar", "dropping the chug there", 6.7, 8.0, quote=False, side="left"), Send("guitar", "sitar", 7.0, 7.9, PURPLE, bend=30),
         Say("drums", "one more pass?", 8.0, 9.8, quote=False, side="left"), Pulse("drums", 8.1, TERRA)),
        "an illustration of the full pattern, not a trace: every line is an action (italic), never a quote"),
    "blackboard": Scene(
        (Actor("lead", "lead", 300, 300, "Lead"), Actor("canvas", "canvas", 830, 300, "the blackboard"),
         Actor("riff", "riff", 1360, 300, "Riff"), Actor("flow", "code", 830, 60, "controller (code)")),
        (Say("flow", "Lead first, 3 passes", 0.1, 1.6, quote=False, side="right"),
         Send("lead", "canvas", 0.3, 1.2), Say("lead", "writes the head", 0.3, 1.7, quote=False), Pulse("canvas", 1.3, MUTED),
         Send("canvas", "riff", 1.8, 2.7, SKY), Say("riff", "…leaves explicit rest space for the sitar mukhada", 2.8, 5.4),
         Send("riff", "canvas", 5.5, 6.4, PURPLE), Pulse("canvas", 6.5, MUTED),
         Send("canvas", "lead", 6.8, 7.7, PURPLE), Say("lead", "plays into that space", 7.8, 9.6, quote=False)),
        "trace 480f18b59298 (2026-10-11): the Riff's reasoning in the studio session; code's order is an action"),
    "chaining": Scene(
        # One owner's calls (Sujit, 2026-10-20): a chain (seed, then gat), then three sections AT ONCE, each
        # seeing the gat but not the others. An illustration of the order, so every line is an action.
        (Actor("seed", "composer", 170, 300, "Pandit · seed"), Actor("gat", "composer", 560, 300, "Pandit · gat"),
         Actor("alap", "composer", 960, 300, "Pandit · alap"), Actor("taan", "composer", 1250, 300, "Pandit · taan"),
         Actor("outro", "composer", 1540, 300, "Pandit · outro")),
        (Pulse("seed", 0.2, MUSTARD), Say("seed", "writes the plan, the riff and the hook", 0.2, 2.0, quote=False),
         Pulse("seed", 1.8), Send("seed", "gat", 2.0, 2.7),
         Pulse("gat", 2.7, MUSTARD), Say("gat", "writes the head from the seed", 2.7, 4.6, quote=False),
         Pulse("gat", 4.4), Send("gat", "alap", 4.7, 5.6, bend=-60), Send("gat", "taan", 4.7, 5.6, bend=-90),
         Send("gat", "outro", 4.7, 5.6, bend=-120),
         Pulse("alap", 5.7, MUSTARD), Pulse("taan", 5.7, MUSTARD), Pulse("outro", 5.7, MUSTARD),
         Say("taan", "three sections at once, none hearing the others", 5.8, 8.6, quote=False),
         Pulse("alap", 8.4), Pulse("taan", 8.4), Pulse("outro", 8.4)),
        "an illustration of the calls' order, not a trace: every line is an action (italic), never a quote"),
    "hitl": Scene(
        (Actor("composer", "composer", 300, 300, "the system"), Actor("person", "person", 860, 300, "Sujit, blind"),
         Actor("stage", "out", 1440, 300, "what ships")),
        (Send("composer", "person", 0.3, 1.3, MUSTARD, bend=-40), Send("composer", "person", 0.3, 1.3, PURPLE, bend=40),
         Say("composer", "two takes, X and Y", 0.3, 1.6, quote=False),
         Say("person", "Y is clearly better. X had issues in rhythm…", 1.6, 4.4), Pulse("person", 4.5, MUSTARD),
         Send("person", "stage", 4.8, 5.8, SKY), Pulse("stage", 5.9),
         Say("stage", "Y was the first draft; the judge had shipped X", 6.0, 9.6, quote=False)),
        "out/blind_producer_20261018_165129 + Sujit's verdict (2026-10-18)"),
}


# --------------------------------------------------------------------------- #
# Drawing.                                                                    #
# --------------------------------------------------------------------------- #

def _actor(scene: Scene, key: str) -> Actor:
    return next(a for a in scene.actors if a.key == key)


def _path(a: Actor, b: Actor, bend: float, gap: float = 88) -> str:
    dx, dy = b.x - a.x, b.y - a.y
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    x1, y1, x2, y2 = a.x + ux * gap, a.y + uy * gap, b.x - ux * gap, b.y - uy * gap
    if not bend:
        return f"M{x1:.0f} {y1:.0f} L{x2:.0f} {y2:.0f}"
    mx, my = (x1 + x2) / 2 - uy * bend, (y1 + y2) / 2 + ux * bend
    return f"M{x1:.0f} {y1:.0f} Q{mx:.0f} {my:.0f} {x2:.0f} {y2:.0f}"


def _loop() -> str:
    return f'dur="{PERIOD_S:g}s" repeatCount="indefinite"'


def _k(t: float) -> str:
    return f"{min(max(t / PERIOD_S, 0.0), 1.0):.4f}"


def _envelope(d: str, color: str, t0: float, t1: float) -> str:
    body = (f'<rect x="-22" y="-15" width="44" height="30" rx="5" fill="{color}"/>'
            f'<path d="M-20 -12 L0 4 L20 -12" fill="none" stroke="{CARD}" stroke-width="3.5" stroke-linejoin="round"/>')
    return (f'<g opacity="0"><animate attributeName="opacity" values="0;1;0" keyTimes="0;{_k(t0)};{_k(t1)}" '
            f'calcMode="discrete" {_loop()}/><animateMotion path="{d}" keyPoints="0;0;1;1" '
            f'keyTimes="0;{_k(t0)};{_k(t1)};1" calcMode="linear" {_loop()}/>{body}</g>')


def _wrap(text: str) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > WRAP:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur] if cur else lines


def _bubble(actor: Actor, say: Say) -> str:
    text = f"“{say.text}”" if say.quote else say.text
    lines = _wrap(text)
    w = max(len(line) for line in lines) * TEXT_PX * 0.53 + 44
    h = len(lines) * TEXT_PX * 1.25 + 30
    if say.side == "right":
        x, y = actor.x + 90, actor.y - h / 2
        tail = f"M{x:.0f} {actor.y - 12:.0f} L{x - 20:.0f} {actor.y:.0f} L{x:.0f} {actor.y + 12:.0f} Z"
    elif say.side == "left":
        x, y = actor.x - 90 - w, actor.y - h / 2
        tail = f"M{x + w:.0f} {actor.y - 12:.0f} L{x + w + 20:.0f} {actor.y:.0f} L{x + w:.0f} {actor.y + 12:.0f} Z"
    elif say.side == "below":
        x, y = actor.x - w / 2, actor.y + HALF_H + 44
        tail = f"M{actor.x - 14:.0f} {y:.0f} L{actor.x:.0f} {y - 18:.0f} L{actor.x + 14:.0f} {y:.0f} Z"
    else:
        x, y = actor.x - w / 2, actor.y - HALF_H - 24 - h
        tail = f"M{actor.x - 14:.0f} {y + h:.0f} L{actor.x:.0f} {y + h + 18:.0f} L{actor.x + 14:.0f} {y + h:.0f} Z"
    x, y = min(max(x, 0), W - w), min(max(y, 0), H - h)
    edge = SKY if say.quote else LINE
    style = 'font-style="italic" ' if not say.quote else ""
    ink = INDIGO if say.quote else MUTED
    texts = "".join(f'<text x="{x + 22:.0f}" y="{y + 20 + TEXT_PX + i * TEXT_PX * 1.25:.0f}" font-family="{FONT}" '
                    f'font-size="{TEXT_PX}" {style}fill="{ink}">{line}</text>' for i, line in enumerate(lines))
    dash = "" if say.quote else ' stroke-dasharray="8 6"'
    box = (f'<path d="{tail}" fill="{CARD}" stroke="{edge}" stroke-width="3"/>'
           f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="16" fill="{CARD}" stroke="{edge}" stroke-width="3"{dash}/>')
    show = (f'<animate attributeName="opacity" values="0;1;0" keyTimes="0;{_k(say.t0)};{_k(say.t1)}" '
            f'calcMode="discrete" {_loop()}/>')
    return f'<g opacity="0">{show}{box}{texts}</g>'


def _pulse(actor: Actor, pulse: Pulse) -> str:
    k = f'keyTimes="0;{_k(pulse.t - 0.05)};{_k(pulse.t)};{_k(pulse.t + 0.8)};1"'
    return (f'<circle cx="{actor.x}" cy="{actor.y}" r="70" fill="none" stroke="{pulse.color}" stroke-width="7" opacity="0">'
            f'<animate attributeName="r" values="70;70;70;110;110" {k} {_loop()}/>'
            f'<animate attributeName="opacity" values="0;0;0.9;0;0" {k} {_loop()}/></circle>')


def overlay(key: str) -> str:
    """The scene's animated layer: faint routes, envelopes, rings, then bubbles on top."""
    scene = SCENES[key]
    routes, moving, rings, bubbles = {}, [], [], []
    for e in scene.events:
        if isinstance(e, Send):
            d = _path(_actor(scene, e.a), _actor(scene, e.b), e.bend)
            routes[d] = e.dashed
            moving.append(_envelope(d, e.color, e.t0, e.t1))
        elif isinstance(e, Pulse):
            rings.append(_pulse(_actor(scene, e.a), e))
        else:
            bubbles.append(_bubble(_actor(scene, e.a), e))
    lines = "".join(f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="4" stroke-linecap="round"'
                    f'{" stroke-dasharray=\"4 12\"" if dashed else ""}/>' for d, dashed in routes.items())
    return lines + "".join(rings) + "".join(moving) + "".join(bubbles)


def icon(kind: str) -> str:
    """A non-sprite actor's mark (the sprites are placed by the slide builder)."""
    marks = {
        "code": V.braces_check(110, 90),
        "tool": V.svg(96, 96, f'<rect x="10" y="10" width="76" height="76" rx="12" fill="{CARD}" stroke="{SKY}" stroke-width="8"/>'
                              f'<path d="M30 48 H66 M48 30 V66" stroke="{SKY}" stroke-width="8" stroke-linecap="round"/>', "a tool", (96, 96)),
        "person": V.svg(96, 112, f'<circle cx="48" cy="30" r="24" fill="{MUSTARD}"/><path d="M6 112 C6 60 90 60 90 112 Z" fill="{MUSTARD}"/>',
                        "a person", (96, 112)),
        "model": V.svg(110, 96, f'<circle cx="55" cy="44" r="40" fill="{MUSTARD}"/><path d="M34 76 L22 94 L52 82 Z" fill="{MUSTARD}"/>'
                               f'<circle cx="37" cy="44" r="7" fill="{CARD}"/><circle cx="55" cy="44" r="7" fill="{CARD}"/>'
                               f'<circle cx="73" cy="44" r="7" fill="{CARD}"/>', "a model", (110, 96)),
        "judge": V.svg(100, 100, f'<polygon points="50,6 94,50 50,94 6,50" fill="{CARD}" stroke="{TERRA}" stroke-width="8" stroke-linejoin="round"/>',
                       "a judge", (100, 100)),
        "canvas": V.svg(170, 120, f'<rect x="6" y="6" width="158" height="108" rx="14" fill="{CARD}" stroke="{MUTED}" stroke-width="6" stroke-dasharray="6 12"/>',
                        "a shared canvas", (170, 120)),
        "out": V.svg(96, 96, f'<circle cx="48" cy="48" r="38" fill="{CARD}" stroke="{SKY}" stroke-width="8"/>'
                             f'<path d="M40 30 V64 M40 30 L64 24 V56" fill="none" stroke="{SKY}" stroke-width="6" stroke-linecap="round"/>'
                             f'<circle cx="34" cy="66" r="8" fill="{SKY}"/><circle cx="58" cy="58" r="8" fill="{SKY}"/>', "the song", (96, 96)),
    }
    return marks[kind]
