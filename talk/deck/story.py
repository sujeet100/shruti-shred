"""Build "Lessons from an Agentic AI Raga-Metal Band" (Sahaj DevDay, 2026-10-18 rewrite).

One cohesive story for an audience that knows neither music nor Hindustani music: the band is the
testbed, the agentic lessons are the subject. Act 1 grows the system to eleven agents, Act 2 is the
day one bare prompt beat it, Act 3 is seven lessons, each a claim with one piece of real evidence.
Music is explained in one plain line at the moment a lesson needs it; everything deeper is annex.

The look is Sahaj's (sahaj.ai's own stylesheets): Zilla Slab headings, Mulish text, indigo #33357D
with terracotta, mustard and sky accents; light content slides, indigo titles and act dividers
(DevDay's own field, and kinder to an LED wall). No characters, no decorative animation: a picture
appears only where the argument depends on it, and audio is evidence.

    python3 talk/deck/story.py && python3 talk/deck/preview.py && python3 talk/deck/clickcheck.py

Writes project/slides/<id>.html and project/deck.json (order, sections, faces).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Final

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SLIDES = HERE / "project" / "slides"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from raga import RAGAS  # noqa: E402  (the encoded, source-verified raga facts)
from title_slides import title_slides  # noqa: E402
from titles.bot import bot  # noqa: E402
from keyboard import ALL, KB_REGION, SHUDDHA, keyboard  # noqa: E402
import visuals as V  # noqa: E402
from patterns import AGENTIC, DO_DONT, INTRO_ORDER, PATTERNS, VERDICT_ORDER, diagram  # noqa: E402
from workflow import build, code_seats, graph, groups, shrink  # noqa: E402

AUDIO: dict[str, dict[str, str]] = json.loads((HERE.parent / "audio" / "assets.json").read_text())

# ---- tokens ---------------------------------------------------------------------------------
PAGE, CARD, LINE, SUNK = "#F3F0EA", "#FEFCFA", "#DDD8CF", "#E7E3DB"
INDIGO, DEEP, INK, MUTED = "#33357D", "#27235A", "#434343", "#6E6A66"
TERRA, MUSTARD, SKY, PURPLE, DANGER = "#D26F5D", "#E0AA55", "#79B8CC", "#715397", "#C0392B"
TERRA_TEXT, SKY_TEXT, MUSTARD_TEXT = "#B4513F", "#2E7A93", "#9A6B12"          # the accents darkened to read as text on PAGE
LIGHT, SOFT = "#FEFCFA", "#C9CAE6"                    # text on indigo
SERIF: Final = "'Zilla Slab', Georgia, serif"
SANS: Final = "'Mulish', Arial, sans-serif"
MONO: Final = "'JetBrains Mono', 'Courier New', monospace"
DEVA: Final = "'Noto Sans Devanagari', sans-serif"
H2, BIG, BODY, LABEL = 72, 52, 40, 32                 # nothing on a slide goes below LABEL
FACES: Final = {
    "zilla-slab": {"family": "Zilla Slab", "href": "https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@400;600;700&display=swap"},
    "mulish": {"family": "Mulish", "href": "https://fonts.googleapis.com/css2?family=Mulish:wght@400..800&display=swap"},
    "jetbrains-mono": {"family": "JetBrains Mono", "href": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap"},
    "noto-sans-devanagari": {"family": "Noto Sans Devanagari", "href": "https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@500;600&display=swap"},
}


SPRITES: dict[str, str] = json.loads((HERE.parent / "sprites" / "assets.json").read_text())
# Today's composer IS Pandit (Sujit, 2026-10-19: keep the names the evolution introduced, so the audience
# follows one character from beat 2 to the band today), so the composer role wears Pandit's sprite.
SPRITES["composer"] = SPRITES["fusion"]   # today's Pandit: tradition and metal in one composer (2026-10-20)
SHOTS: dict[str, str] = json.loads((HERE / "shots" / "assets.json").read_text())   # UI screenshots
NAMES: Final = {"interpreter": "Interpreter", "pandit": "Pandit", "riffsmith": "Riffsmith", "lead": "Lead", "riff": "Riff",
                "orchestra": "Orchestra", "arranger": "Arranger", "ustad": "Ustad", "rasik": "Rasik",
                "producer": "Producer", "conductor": "Conductor", "composer": "Pandit",
                "rhythm": "Rhythm section", "drums": "Drum kit", "system": "Code"}


# ---- primitives -----------------------------------------------------------------------------
def persona(name: str, scale: float = 3, extra: str = "") -> str:
    """One of the band: a pixel character (48 x 64 grid), drawn at `scale`."""
    return (f'<img src="{SPRITES[name]}" alt="{NAMES[name]}" style="width:{round(48 * scale)}px;height:{round(64 * scale)}px;'
            f'object-fit:contain{extra}">')


def member(name: str, role: str, *, scale: float = 2.5, dim: bool = False, tag: str = "", tag_color: str = TERRA_TEXT,
           build: str = "") -> str:
    """A band member standing on the stage line: the character, its name, one line of what it does."""
    fade = ";opacity:0.22" if dim else ""
    b = f' data-build-in="{build}"' if build else ""
    tag_html = p(tag, LABEL, tag_color, ";font-weight:800") if tag else ""
    return (f'<div{b} style="flex:1;display:flex;flex-direction:column;align-items:center;gap:6px">'
            f'<div style="display:flex;align-items:end;justify-content:center;height:{round(64 * scale)}px;border-bottom:4px solid {LINE};width:100%">'
            f'{persona(name, scale, fade)}</div>'
            f'<p style="font-size:36px;font-weight:800;color:{MUTED if dim else INDIGO};text-align:center">{NAMES[name]}</p>'
            f'<p style="font-size:{LABEL}px;line-height:1.2;color:{MUTED};text-align:center">{role}</p>{tag_html}</div>')


def bubble(text: str, who: str) -> str:
    """A speech bubble: an agent's real words, quoted from its trace."""
    return (f'<div style="background:{CARD};border:3px solid {INDIGO};border-radius:24px;padding:24px 30px;display:flex;flex-direction:column;gap:10px">'
            f'<p style="font-family:{SERIF};font-size:52px;font-weight:600;line-height:1.15;color:{INDIGO}">{text}</p>'
            f'<p style="font-size:{LABEL}px;color:{MUTED}">{who}</p></div>')


# ---- primitives (layout) --------------------------------------------------------------------
def section(sid: str, inner: list[str], notes: str, *, dark: bool = False, justify: str = "start",
            gap: int = 32, pad: str = "96px 128px") -> str:
    """A slide. Flowing children stack in a column; pinned ones (clips) are emitted last so
    nothing transparent lies above a player."""
    bg, fg = (INDIGO, LIGHT) if dark else (PAGE, INK)
    items = [x for x in inner if x and x.strip()]
    items = [x for x in items if "data-video" not in x] + [x for x in items if "data-video" in x]
    return (f'<section id="{sid}" data-transition="fade" style="background:{bg};color:{fg};font-family:{SANS};'
            f'padding:{pad};display:flex;flex-direction:column;justify-content:{justify};gap:{gap}px">\n'
            + "\n".join(items) + f"\n<aside>{notes}</aside>\n</section>\n")


def eyebrow(text: str, color: str = TERRA_TEXT) -> str:
    return (f'<p style="font-size:{LABEL}px;font-weight:800;letter-spacing:4px;text-transform:uppercase;'
            f'color:{color}">{text}</p>')


def h2(text: str, color: str = INDIGO, size: int = H2) -> str:
    return f'<h2 style="font-family:{SERIF};font-size:{size}px;font-weight:600;line-height:1.1;color:{color}">{text}</h2>'


def p(text: str, size: int = BODY, color: str = INK, extra: str = "") -> str:
    return f'<p style="font-size:{size}px;line-height:1.3;color:{color}{extra}">{text}</p>'


def b(text: str, color: str = INDIGO) -> str:
    return f'<b style="color:{color}">{text}</b>'


def card(inner: str, accent: str = LINE, *, flex: str = "flex:1", pad: str = "28px 32px", gap: int = 14,
         bg: str = CARD) -> str:
    return (f'<div style="{flex};background:{bg};border:2px solid {LINE};border-top:10px solid {accent};'
            f'border-radius:16px;padding:{pad};display:flex;flex-direction:column;gap:{gap}px">{inner}</div>')


def row(*items: str, gap: int = 32, align: str = "stretch", extra: str = "") -> str:
    return f'<div style="display:flex;gap:{gap}px;align-items:{align}{extra}">{"".join(items)}</div>'


def chip(text: str, fill: str, ink: str = LIGHT) -> str:
    return (f'<p style="font-size:{LABEL}px;font-weight:800;color:{ink};background:{fill};border-radius:12px;'
            f'padding:8px 18px">{text}</p>')


def code(lines: list[str], size: int = 34) -> str:
    body = "".join(f'<p style="font-family:{MONO};font-size:{size}px;line-height:1.35;color:{INDIGO}">{ln}</p>' for ln in lines)
    return (f'<div style="background:{CARD};border:2px solid {LINE};border-left:10px solid {SKY};border-radius:12px;'
            f'padding:24px 28px;display:flex;flex-direction:column">{body}</div>')


def clip(cid: str, x: int, y: int, caption: str, w: int = 480, h: int = 96, show_caption: bool = True) -> str:
    """A click-to-play clip: a top-level pinned <img data-video> (the only form the viewer plays),
    its caption pinned above it."""
    a = AUDIO[cid]
    cap = (f'<p style="position:absolute;left:{x}px;top:{y - 48}px;width:{w}px;text-align:right;font-size:{LABEL}px;'
           f'font-weight:700;color:{SKY_TEXT}">▶ {caption}</p>') if show_caption else ""
    return (cap +
            f'<img src="{a["still"]}" data-video="{a["video"]}" data-video-sound="on" data-video-start="click" '
            f'alt="Audio clip: {caption}" style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'object-fit:cover;border:3px solid {SKY};border-radius:12px">')


# The talk's parts, as the dividers' progress strip shows them; an act's index is its position here.
PARTS: Final = ("Opening", "Act 1", "Act 2", "Close")   # Act 3 folded into the close (Sujit, 2026-10-20)
STRIP_Y, STRIP_H = 880, 12


def _strip(n: int) -> list[str]:
    """Where we are in the talk: past parts soft, this act mustard, parts to come dim, and the
    DevDay bot standing on this act's segment."""
    here = PARTS.index(f"Act {n}")
    gap = 16
    w = (1664 - (len(PARTS) - 1) * gap) / len(PARTS)
    out = []
    for i, name in enumerate(PARTS):
        x = 128 + i * (w + gap)
        bar, ink = (MUSTARD, MUSTARD) if i == here else ((SOFT, SOFT) if i < here else ("#4A4C92", "#7F81B8"))
        out.append(f'<div style="position:absolute;left:{x:.0f}px;top:{STRIP_Y}px;width:{w:.0f}px;height:{STRIP_H}px;'
                   f'background:{bar};border-radius:6px"></div>')
        out.append(f'<p style="position:absolute;left:{x:.0f}px;top:{STRIP_Y + 26}px;width:{w:.0f}px;font-size:{LABEL}px;'
                   f'font-weight:{800 if i == here else 600};color:{ink}">{name}</p>')
    scale = 0.3
    bx = 128 + here * (w + gap) + w / 2 - 230 * scale
    out.append(f'<svg aria-label="" style="position:absolute;left:0px;top:0px;width:1920px;height:1080px" viewBox="0 0 1920 1080">'
               f'{bot(bx, STRIP_Y - 4 - 548 * scale, scale)}</svg>')
    return out


def divider(sid: str, n: int, title: str, sub: str, notes: str) -> str:
    """An act divider, built to read as a section break rather than a title: a huge outlined act
    numeral, the act's title and one line beside it, and the talk's progress strip with the DevDay
    bot standing on this act."""
    numeral = (f'<p style="position:absolute;left:112px;top:150px;width:420px;font-family:{SERIF};font-size:400px;'
               f'font-weight:700;line-height:1;color:transparent;-webkit-text-stroke:6px {MUSTARD}">{n}</p>')
    text = (f'<div style="position:absolute;left:560px;top:250px;width:1230px;display:flex;flex-direction:column;gap:22px">'
            f'<p style="font-size:{LABEL}px;font-weight:800;letter-spacing:4px;text-transform:uppercase;color:{MUSTARD}">Act {n}</p>'
            f'<h2 style="font-family:{SERIF};font-size:96px;font-weight:700;line-height:1.1;color:{LIGHT}">{title}</h2>'
            f'<p style="font-size:{BIG}px;line-height:1.3;color:{SOFT}">{sub}</p></div>')
    inner = [numeral, text, *_strip(n)]
    return section(sid, inner, notes, dark=True, pad="128px")


QUOTE_BG: Final = f"radial-gradient(circle at 88% 92%, {PURPLE} 0%, {INDIGO} 62%)"


def quote(sid: str, inner: list[str], notes: str) -> str:
    """A quote slide: the one slide type with a gradient (a purple glow from the lower right into
    flat indigo) and one solid mustard opening quotation mark above the words, so it reads as a
    thought to keep before anyone reads it."""
    mark = V.svg(150, 120, f'<g fill="{MUSTARD}"><circle cx="34" cy="74" r="30"/><path d="M8 70 C8 34 26 10 60 2 L64 14 C42 22 32 40 34 60 Z"/>'
                           f'<circle cx="112" cy="74" r="30"/><path d="M86 70 C86 34 104 10 138 2 L142 14 C120 22 110 40 112 60 Z"/></g>',
                 "", (150, 110))
    return (f'<section id="{sid}" data-transition="fade" style="background:{QUOTE_BG};color:{LIGHT};font-family:{SANS};'
            f'padding:128px 160px;display:flex;flex-direction:column;justify-content:center;gap:48px">\n'
            + "\n".join([mark, *inner]) + f"\n<aside>{notes}</aside>\n</section>\n")


def statement(sid: str, lines: str, sub: str, notes: str) -> str:
    return quote(sid, [f'<h1 style="font-family:{SERIF};font-size:88px;font-weight:600;line-height:1.15;color:{LIGHT}">{lines}</h1>',
                       p(sub, BIG, SOFT, ";width:1500px")], notes)


def lesson(sid: str, n: int, claim: str, evidence: list[str], rule: str, notes: str, extra: list[str] | None = None) -> str:
    """One lesson: the claim, the evidence that taught it, the rule to take home."""
    return section(sid, [eyebrow(f"Lesson {n} of 7"), h2(claim), *evidence,
                         p(rule, BIG, TERRA_TEXT, (";width:1150px" if extra else "") + ";font-weight:700;font-family:" + SERIF), *(extra or [])], notes, gap=30)


# ---- the system, drawn once ------------------------------------------------------------------
def node(name: str, role: str, kind: str) -> str:
    """kind: model (sky), code (indigo outline), person (mustard)."""
    fill, border, ink = {"model": ("#E3F0F4", SKY, INDIGO), "code": (CARD, INDIGO, INDIGO),
                         "person": ("#F7EBD5", MUSTARD, INDIGO)}[kind]
    return (f'<div style="flex:1;background:{fill};border:3px solid {border};border-radius:16px;padding:18px 20px;'
            f'display:flex;flex-direction:column;gap:6px"><p style="font-size:36px;font-weight:800;color:{ink}">{name}</p>'
            f'<p style="font-size:{LABEL}px;line-height:1.25;color:{MUTED}">{role}</p></div>')


ARROW = f'<p style="font-size:44px;font-weight:800;color:{MUTED};align-self:center">→</p>'


def system_today() -> str:
    flow = row(node("You", "say what you want", "person"), ARROW,
               node("Interpreter", "turns it into a brief", "model"), ARROW,
               node("Pandit", "writes the whole piece", "model"), ARROW,
               node("Code", "rules, chords, bass, drums, audio", "code"), gap=14, align="stretch")
    judges = row(node("Rasik", "advises on the raga", "model"), node("Producer", "accepts, or sends one edit plan back", "model"),
                 node("The round limit", "at most 3 rounds, in code", "code"), gap=14)
    legend = p(f'<span style="color:{SKY_TEXT}">■</span> a model call &#160;&#160; '
               f'<span style="color:{INDIGO}">□</span> code &#160;&#160; <span style="color:#B98A2E">■</span> a person', LABEL, MUTED)
    return flow + judges + legend


# ---- slides: open ---------------------------------------------------------------------------
def s_perform() -> str:
    parts = [("Slow intro", 1, SKY), ("The hook", 2, MUSTARD), ("Call and answer", 2, TERRA), ("Fast run", 2, PURPLE), ("Landing", 1, SOFT)]
    strip = row(*(f'<div style="flex:{f};background:{c};border-radius:10px;padding:14px 16px"><p style="font-size:{LABEL}px;'
                  f'font-weight:800;color:{INDIGO}">{n}</p></div>' for n, f, c in parts), gap=10)
    inner = [p("Raga Bhairav · heavy metal · 128 beats a minute", BIG, SOFT), strip,
             row(p("0:00", LABEL, SOFT), p("0:30", LABEL, SOFT), p("1:00", LABEL, SOFT), extra=";justify-content:space-between")]
    return section("perform", inner, "0:00–1:00. Play first, say nothing. The drone is the entry cue; enter on the first beat of the hook with the written riff; leave space in the call and answer; the fast run is the climax; land the final hit together and hold a second of silence. Fallback: the recorded performance.",
                   dark=True, justify="center", gap=36, pad="128px")


def _icon(name: str, w: int, h: int) -> str:
    return f'<img src="{SPRITES[name]}" alt="{name}" style="width:{w}px;height:{h}px;object-fit:contain">'


def s_origin() -> str:
    """How it started (Sujit, 2026-10-20): a metalhead who also studies Hindustani classical sitar; why not a
    band of agents that writes raga x metal. Each world fades in, then the idea."""
    def world(pics: str, title: str, line: str, accent: str, build: int) -> str:
        return (f'<div data-build-in="fade {build}" style="flex:1;display:flex;flex-direction:column;align-items:center;'
                f'gap:18px;background:{CARD};border:2px solid {LINE};border-top:10px solid {accent};border-radius:20px;'
                f'padding:26px 30px"><div style="height:220px;display:flex;align-items:end;justify-content:center;gap:16px">'
                f'{pics}</div>{p(title, 48, INDIGO, f";font-family:{SERIF};font-weight:700")}'
                f'{p(line, 36, INK, ";text-align:center;line-height:1.3")}</div>')
    metal = world(persona("riff", 2.6) + persona("drums", 2.6), "I'm a metalhead",
                  "Riffs with weight, a groove you feel in your chest.", TERRA, 1)
    raga = world(persona("lead", 2.6) + _icon("tanpura", 70, 190), "I study Hindustani classical sitar",
                 "Ragas, ornaments, a melody that breathes over a drone.", MUSTARD, 2)
    idea = (f'<div data-build-in="fade 3" style="display:flex;align-items:center;justify-content:center;gap:24px">'
            f'{p("So I asked: why not a band of AI agents that writes raga × metal?", 48, TERRA_TEXT, f";font-family:{SERIF};font-weight:700;text-align:center")}'
            f'</div>')
    inner = [eyebrow("How it started"), h2("Two kinds of music I love"), row(metal, raga, gap=40), idea]
    return section("origin", inner, (
        "Right after the performance, in the first person. CLICK 1: I'm a metalhead: riffs, weight, the groove. "
        "CLICK 2: and I study Hindustani classical sitar: ragas, ornaments, a melody that breathes over the tanpura's "
        "drone. CLICK 3: the two have more in common than they look, so the question was obvious to me: why not build "
        "a band of AI agents that composes raga × metal? That is how this started. The music is the testbed; the "
        "talk is about what building that band taught us about agents."), gap=28)


# The two traditions do the same jobs (Sujit, 2026-10-20): the words the talk uses, introduced by the job they
# share, one row a click. Pairings are by function, not equivalence.
WORLDS: Final = (
    ("The opening", "Alap", "slow and unmetred: the raga unfolds, note by note", "Intro", "the band waits, the mood is set"),
    ("The idea that comes back", "Gat and mukhada", "a fixed composition; its head returns on the first beat", "Riff",
     "the guitar figure the song is built on"),
    ("The pulse", "Tala and sam", "a cycle of beats; everything lands on the first", "Groove and downbeat",
     "drums and riff locked together"),
    ("The climax", "Taan", "a fast, continuous run, the peak of the piece", "Shred solo", "speed and height"),
    ("The expression", "Andolan and meend", "a slow sway, a glide into a note", "Bends and palm-mutes",
     "a note pulled, a stroke damped to a chug"),
)


def s_worlds() -> str:
    """The vocabulary the talk uses, as the jobs the two traditions share: one row a click."""
    head = (f'<div style="display:grid;grid-template-columns:330px 1fr 1fr;gap:0px 28px;padding:0px 6px 8px">'
            + p("", 30) + p("Hindustani classical", 36, MUSTARD_TEXT, ";font-weight:800")
            + p("Metal", 36, TERRA_TEXT, ";font-weight:800") + "</div>")
    def cell(term: str, gloss: str, ink: str) -> str:
        return (f'<div>{p(term, 40, ink, f";font-family:{SERIF};font-weight:700;line-height:1.1")}'
                f'{p(gloss, 32, INK, ";line-height:1.2")}</div>')
    rows_ = "".join(
        f'<div data-build-in="fade {k}" style="display:grid;grid-template-columns:330px 1fr 1fr;gap:0px 28px;'
        f'align-items:center;border-top:2px solid {LINE};padding:10px 6px">'
        f'{p(job, 34, INDIGO, ";font-weight:800")}{cell(h, hg, MUSTARD_TEXT)}{cell(m, mg, TERRA_TEXT)}</div>'
        for k, (job, h, hg, m, mg) in enumerate(WORLDS, start=1))
    inner = [eyebrow("Annex · the words we use, side by side"), h2("Two traditions, the same jobs"),
             f'<div style="display:flex;flex-direction:column">{head}{rows_}</div>']
    return section("worlds", inner, (
        "Five clicks, a row each: the words the rest of the talk uses, introduced by the job the two traditions share. "
        "The alap is the slow, unmetred opening where the raga unfolds; a metal intro sets the mood. The gat is a "
        "fixed composition and its head, the mukhada, comes back on the first beat of every cycle; that is our hook, "
        "the way a riff is a metal song's. The tala is the rhythmic cycle and the sam its first beat; the metal "
        "equivalent is the groove locked to the downbeat. The taan is the fast, continuous run at the climax, our "
        "shred solo. And the ornaments: the andolan is a slow sway on a note, the meend a glide into one; metal pulls "
        "notes with bends and damps strokes into chugs with a palm mute. These pairs are by job, not equivalence: a "
        "raga is more than a scale, which the next slides show."), gap=22)


OPENER: Final = [("interpreter", "read the request"), ("pandit", "argued for tradition"), ("riffsmith", "argued for metal"),
                  ("lead", "wrote the sitar"), ("riff", "wrote the guitar"), ("arranger", "fixed clashing notes"),
                  ("rasik", "judged the raga"), ("producer", "judged the song")]


def s_reveal() -> str:
    """The eleven, faces and names only (Sujit, 2026-10-20): slide 13 explains who does what, so this slide only has to
    land the count in about ten seconds."""
    def face(name: str) -> str:
        return (f'<div style="width:277px;display:flex;flex-direction:column;align-items:center;gap:6px">{persona(name, 2.9)}'
                f'{p(NAMES[name], 36, INDIGO, ";font-weight:800")}</div>')
    cast = [n for n, _ in OPENER] + ["orchestra", "ustad", "conductor"]
    order = ["interpreter", "pandit", "riffsmith", "lead", "riff", "orchestra", "arranger", "ustad", "rasik",
             "producer", "conductor"]
    assert sorted(cast) == sorted(order), "the reveal shows exactly the eleven"
    grid = (f'<div style="display:flex;flex-wrap:wrap;justify-content:center;row-gap:28px">'
            + "".join(face(n) for n in order) + "</div>")
    flow = grid + p("Today the band is six.", 44, TERRA_TEXT, f";font-family:{SERIF};font-weight:600;text-align:right")
    inner = [eyebrow("What you just heard"), h2("I didn't write that riff. These eleven agents did."), flow]
    return section("reveal", inner, "The band had eleven agents (Sujit, 2026-10-20: show all eleven). Strictly, eight made model calls for this song (trace 480f18b59298); the other three were in the band but had nothing to do this time: the Orchestra joins only symphonic pieces, the Conductor rules only when the critics disagree, and Ustad's legality check ran as code. If asked, say so. Plant the twist now and pay it off at the turn: this exact song is the one whose riff lost to a single prompt, once, in one comparison. 1:00–2:30. \"I learned it off their output; I'm the session guitarist tonight.\" These are the eight agents that actually ran for tonight's piece (trace 480f18b59298, 2026-10-11): two composers argued the form, Lead and Riff wrote the parts, the Arranger fixed clashing notes, Rasik and the Producer judged it, and code checked every rule. That was before the redesign; the talk is how the band grew to eleven and then shrank to six. Ten seconds here: faces and names only; slide 13 explains who does what.", gap=24)


def s_testbed() -> str:
    def q(pic: str, title: str, sub: str) -> str:
        return (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:14px">'
                f'<div style="height:340px;display:flex;flex-direction:column;align-items:center;justify-content:end;gap:10px">{pic}</div>'
                f'{p(title, 52, INDIGO, f";font-family:{SERIF};font-weight:600")}{p(sub, BODY, MUTED, ";text-align:center")}</div>')
    inner = [eyebrow("Act 1 · how to split the work"), h2("Every agentic system has three kinds of question"),
             row(q(V.braces_check(320, 262), "Is it allowed?", "A wrong note is a fact."),
                 q(persona("rasik", 3.2) + V.stars(4, 380, 88), "Is it any good?", "Correct can still be dull."),
                 q(V.crowd(480, 255), "Who decides?", "The ear in the room."), gap=40),
             p("Swap the raga for clinical codes, a contract, or your own domain.", BIG, TERRA_TEXT, f";font-family:{SERIF};font-weight:600;text-align:center")]
    return section("testbed", inner, "Right after one agent per instrument fails: if not by instrument, by what? By the questions every agentic system has to answer: rules you can check (a raga forbids some notes), taste you cannot (correct can still be boring), and one ground truth (a listener). Most failures come from answering one with the tool meant for another. NEXT: split the band by those jobs.", gap=40)


# ---- music 101: how a song gets made ------------------------------------------------------------
# The studio session clip (talk/studio: three.js voxel personas, real Darbari head, Gemini voices):
# 16:9 in the left column under the heading, the takeaway beside it.
STUDIO_REGION: Final = (128, 264, 1184, 666)


def s_process() -> str:
    """How a song really gets made (Sujit, 2026-10-18): one idea; each part written hearing the
    parts before it; a producer's single correction; the band again. Played out by the band's
    personas in a studio, on a real Darbari head — and the correction is our system's own fix."""
    x, y, w, _ = STUDIO_REGION
    side = (f'<div style="position:absolute;left:{x + w + 48}px;top:{y + 8}px;width:{1792 - x - w - 48}px;'
            f'display:flex;flex-direction:column;gap:40px">'
            + p("Every part is written hearing the parts before it.", 44, INDIGO, f";font-family:{SERIF};font-weight:700;line-height:1.2")
            + p("Then someone listens to the whole, and the band fixes what they hear.", BODY, TERRA_TEXT, ";line-height:1.3")
            + "</div>")
    alt = ("A band of pixel-style 3D characters in a studio: the sitar player offers a Darbari phrase, the guitarist, "
           "bassist and drummer join one by one, the producer stops the take to fix the riff under the sitar's Ga, "
           "and the band plays it again")
    inner = [eyebrow("Music 101 · how a song gets made"), h2("Songs are built in layers"), side,
             autoclip("S10", alt, STUDIO_REGION)]
    return section("process", inner, "About 70 seconds; the clip plays by itself (and holds on its last frame). "
                   "The clip names the words the talk uses as each part enters (Sujit, 2026-10-20): the sitar's phrase "
                   "is the MUKHADA, the head of a gat, the hook that returns on the first beat of every cycle (the sam); "
                   "the guitarist's answer is the RIFF; the bass locks to the riff's roots; the drums make the GROOVE, "
                   "on the tala's cycle; the producer hears the whole. The other words (alap, taan, andolan) are named "
                   "where the talk first uses them; the two-traditions table is in the annex. "
                   "This is how a song really gets made. Someone brings one idea: here the sitar, a phrase in raga Darbari. "
                   "The guitarist hears it and answers with a riff under it. The bass locks onto the riff's roots, the drummer "
                   "locks to both. Every part is written hearing the parts before it. Then the producer stops the take: "
                   "the riff hits Re right under the sitar's held Ga, a semitone grind. One precise note, the guitar holds "
                   "its chord and lets it ring, and the band goes again. Two things to notice. The music is real: this is the "
                   "head of a piece our system composed, and the 'after' riff is our pipeline's own articulation pass doing "
                   "exactly what the producer asks. And the shape is the one our system ended up with: one composer for the "
                   "idea, the rhythm section written from the sitar's line, the drums locked to it, and someone listening "
                   "to the whole who sends the band back to fix what they hear. Hold that shape; our first design did not have it.", gap=28)


# ---- the starting point: the demo UI (ui/, Demo mode) ------------------------------------------
UI_W: Final = 1060                                     # both screenshots share this width on the slide


def _step(n: str, line: str, sub: str) -> str:
    return (f'<div style="display:flex;gap:22px;align-items:start">'
            f'<p style="width:52px;font-family:{SERIF};font-size:72px;font-weight:700;line-height:1;color:{MUSTARD}">{n}</p>'
            f'<div style="display:flex;flex-direction:column;gap:8px">{p(line, BODY, INDIGO, ";font-weight:800;line-height:1.2")}'
            f'{p(sub, LABEL, MUTED, ";line-height:1.3")}</div></div>')


def s_ui() -> str:
    """Where every piece starts (Sujit, 2026-10-18): the demo UI's request box, then the stage and
    the flow strip it sets in motion — just before the slide that introduces the agent reading it."""
    x, top = 128, 262
    in_h, stage_h = round(UI_W * 290 / 2352), round(UI_W * 1168 / 2352)
    frame = "border-radius:14px;box-shadow:0 10px 24px rgba(39,35,90,0.28)"
    shots = [f'<img src="{SHOTS["ui_input"]}" alt="The request box: a dark doom fusion in Darbari, key of D; '
             f'Compose; Demo or Live; raga and metal quick picks" style="position:absolute;left:{x}px;top:{top}px;'
             f'width:{UI_W}px;height:{in_h}px;object-fit:contain;{frame}">',
             f'<img src="{SHOTS["ui_stage"]}" alt="The stage: intake, Pandit, the live room, the control '
             f'room, and the flow strip from interpret to render" style="position:absolute;left:{x}px;'
             f'top:{top + in_h + 20}px;width:{UI_W}px;height:{stage_h}px;object-fit:contain;{frame}">']
    col = x + UI_W + 56
    steps = (f'<div style="position:absolute;left:{col}px;top:{top}px;width:{1792 - col}px;display:flex;'
             f'flex-direction:column;gap:56px">'
             + _step("1", "Type what you want, in plain words.", "A raga, a style, a mood, a length.")
             + _step("2", "Press Compose.", "Demo replays a recorded run. Live runs the agents.")
             + _step("3", "Watch the band work.", "Each step lights up, from the brief to the finished song.")
             + "</div>")
    inner = [eyebrow("Act 1 · where a piece starts"), h2("It starts with one sentence"), *shots, steps]
    return section("ui", inner, "About 40 seconds. This is where every piece in this talk starts: the demo UI. You "
                   "type what you want in plain words, here a dark doom fusion in Darbari, key of D; the chips only "
                   "seed those words. Demo replays a recorded run for free; Live calls the agents. Press Compose "
                   "and the strip along the bottom lights each step as it runs: interpret, seed, develop, the "
                   "voices, the checks, the judge, render. We meet those steps as the band grew them, "
                   "starting with the first: something has to read this sentence.", gap=28)


# ---- step 4, shown: the interpreter's real answer (trace f32e2a7b5d5f, 2026-10-18) ---------------
# Verbatim from the trace for slide 15's sentence; the reasoning string is trimmed with "…" only.
# One JSON line per row; a value of None prints as null. Verbatim from the trace, the reasoning
# trimmed with "…" to its "not stated" part (the rest repeats the fields below it).
_BRIEF_ROWS: Final = [
    [("reasoning", "… bpm: not stated; …")],
    [("raga", "Darbari"), ("key", "D")],
    [("subgenre", "doom"), ("mood", "dark")],
    [("bpm", None), ("tala", None), ("laya", None)],
    [("instruments", None), ("duration_s", None)],
    [("playable_rhythm", None)],
]
_JSON_KEY, _JSON_STR, _JSON_PUNCT = SKY, "#F2BFB3", SOFT


def _json_row(pairs: list[tuple[str, str | None]], last: bool) -> str:
    """One syntax-highlighted line of valid JSON: keys sky, strings terracotta, null mustard."""
    def value(v: str | None) -> str:
        return (f'<span style="color:{MUSTARD}">null</span>' if v is None
                else f'<span style="color:{_JSON_STR}">"{v}"</span>')
    punct = lambda t: f'<span style="color:{_JSON_PUNCT}">{t}</span>'  # noqa: E731
    body = punct(", ").join(f'<span style="color:{_JSON_KEY}">"{k}"</span>{punct(": ")}{value(v)}' for k, v in pairs)
    return body + ("" if last else punct(","))


_RESOLVED: Final = [("raga", "Darbari → darbari (supported)"),
                    ("key", "D → Sa = MIDI 62"),
                    ("tempo · tala · laya · length", "OPEN — the composers decide"),
                    ("request", "copied word for word")]


def s_brief() -> str:
    """Step 4 made visible: one sentence in, the model's extraction (verbatim), code's brief out —
    every unsaid field stays OPEN instead of being guessed."""
    code_p = f";font-family:{MONO};line-height:1.35"
    rows = "".join(p(_json_row(pairs, i == len(_BRIEF_ROWS) - 1), LABEL, LIGHT, code_p + ";padding-left:32px")
                   for i, pairs in enumerate(_BRIEF_ROWS))
    model = (f'<div style="flex:11;display:flex;flex-direction:column;gap:14px">'
             + p("The model extracts", 40, INDIGO, ";font-weight:800")
             + f'<div style="background:{DEEP};border-radius:16px;padding:18px 26px;display:flex;flex-direction:column;gap:0px">'
             + p("{", LABEL, _JSON_PUNCT, code_p) + rows + p("}", LABEL, _JSON_PUNCT, code_p) + "</div></div>")
    resolved = "".join(f'<div style="display:flex;flex-direction:column;gap:2px;border-left:8px solid '
                       f'{MUSTARD if v.startswith("OPEN") else LINE};padding-left:18px">'
                       + p(k, LABEL, MUTED, ";font-weight:700")
                       + p(v, 36, MUSTARD_TEXT if v.startswith("OPEN") else INDIGO, ";font-weight:800;line-height:1.2")
                       + "</div>" for k, v in _RESOLVED)
    code = (f'<div style="flex:9;display:flex;flex-direction:column;gap:14px">'
            + p("Code resolves it", 40, INDIGO, ";font-weight:800")
            + f'<div style="display:flex;flex-direction:column;gap:18px">{resolved}</div></div>')
    sentence = p("“a dark doom fusion in Darbari, key of D”", 44, INK, f";font-family:{SERIF};font-weight:600")
    inner = [eyebrow("Act 1 · step 4, shown"), h2("One sentence in, a brief out"), sentence, row(model, code, gap=48)]
    return section("brief", inner, "About 40 seconds. The real answer, from a traced run of the sentence on the "
                   "last slide. The model's job is only to extract: it writes its reasoning first, then the four "
                   "things the sentence says, and null for everything it doesn't. Then code takes over: it keeps "
                   "only values it supports (Darbari becomes darbari), turns the key into a home note, copies the "
                   "request word for word, and leaves tempo, tala and length OPEN. Nothing unsaid gets decided at "
                   "the door; that is the composers' job.", gap=24)


# ---- music 101: the twelve notes, in under two minutes ---------------------------------------
TERMS: Final = [("शुद्ध", "Shuddha", "natural: the white keys", INDIGO), ("कोमल", "Komal", "flat: a line below", TERRA_TEXT),
                ("तीव्र", "Tivra", "sharp: only Ma", SKY_TEXT), ("अचल", "Achal", "Sa and Pa never move", "#9A6B12")]


def _twelve_head(pop: bool) -> list[str]:
    b_ = ' data-build-in="pop 1"' if pop else ""
    return [eyebrow("Just enough music"), h2("How many notes in an octave?"),
            f'<p{b_} style="position:absolute;left:1560px;top:70px;width:232px;text-align:right;font-family:{SERIF};'
            f'font-size:180px;font-weight:700;line-height:1.0;color:{TERRA}">12</p>']


def term_card(deva: str, latin: str, text: str, c: str, x: int, build: str | None) -> str:
    b_ = f' data-build-in="{build}"' if build else ""
    return (f'<div{b_} style="position:absolute;left:{x}px;top:740px;width:404px;background:{CARD};border:2px solid {LINE};'
            f'border-top:10px solid {c};border-radius:16px;padding:16px 22px;display:flex;flex-direction:column;gap:4px">'
            f'<div style="display:flex;gap:16px;align-items:baseline"><p style="font-family:{DEVA};font-size:48px;line-height:1.2;color:{c}">{deva}</p>'
            f'<p style="font-size:36px;font-weight:800;color:{c}">{latin}</p></div>{p(text, LABEL, INK)}</div>')


def autoclip(cid: str, alt: str, region: tuple[int, int, int, int] = KB_REGION) -> str:
    """A clip that starts by itself as its slide opens, pinned exactly over the keyboard it draws."""
    x, y, w, h = region
    a = AUDIO[cid]
    return (f'<img src="{a["still"]}" data-video="{a["video"]}" data-video-sound="on" data-video-delay="0.8" alt="{alt}" '
            f'style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;object-fit:cover">')


def s_twelve() -> str:
    return section("twelve", _twelve_head(True), "Ask the room: how many notes are there in an octave? Take a few answers (people often say 7 or 8), then click: 12. Western music and Hindustani music use the same twelve. Then advance: the next three slides play by themselves, each key appearing as its note sounds.")


def s_notes(n: int) -> str:
    clip_id, alt, notes = [
        ("K1", "The seven natural keys appear one by one as Sa to upper Sa plays, then light again on the way down",
         "Plays by itself (about 8 s): the seven natural notes, shuddha, Sa up to upper Sa and back. Sa is the home note: everything comes back to it."),
        ("K2", "Each natural key lights, then its flat key appears beside it as the flat note plays",
         "Plays by itself (about 9 s): each natural note, then its komal, flat, version: Re re, Ga ga, Dha dha, Ni ni. Komal is written with a line below."),
        ("K3", "Ma lights, sharp Ma appears and sounds, resolving to Pa; then Sa and Pa are ringed as they play",
         "Plays by itself (about 10 s): Ma, then tivra, sharp, Ma, the only note that goes up, resolving to Pa. Then Sa and Pa are ringed: they're achal, immovable. That's all twelve. A raga is a choice from them, and the next slide shows one.")][n - 1]
    inner = _twelve_head(False) + [autoclip(clip_id, alt)]
    for i, (d, l, t, c) in enumerate(TERMS[: n + (1 if n == 3 else 0)]):
        inner.append(term_card(d, l, t, c, 128 + i * 420, "fade 1 auto" if i >= n - 1 else None))
    return section(f"notes{n}", inner, notes)


K4_REGION: Final = (228, 282, 1460, 440)            # the keyboard and the phase label the clip draws


def s_raga() -> str:
    inner = [eyebrow("Just enough music"), h2("A raga is a rulebook for a melody"),
             autoclip("K4", "Raga Bhairav: its seven notes light up going up (aroha), coming down (avaroha), "
                            "then in its characteristic phrases (chalan), swaying on re and dha", K4_REGION),
             p("Code checks the notes. A listener judges the movement.", BIG, TERRA_TEXT,
               f";position:absolute;left:236px;top:800px;width:1440px;text-align:center;font-family:{SERIF};font-weight:600")]
    return section("raga", inner, "About 60 seconds; the clip plays by itself. Bhairav keeps seven of the twelve, lit; the other five are faded, illegal. First the aroha, the way up: komal re, shuddha Ga, Ma, Pa, komal dha, Ni, upper Sa. Then the avaroha, the way down. Then the chalan, the raga's characteristic movement, which a scale can't give you: it circles back (Sa re Sa), and it never plays komal re or dha straight, it sways on them slowly. That sway, the andolan, is Bhairav. The notes are checkable, so code owns them; the movement is idiom, so a listener judges it. The whole talk hangs off that split. Every fact here comes from the raga data, two Hindustani sources each.")


# ---- the experiment -------------------------------------------------------------------------
def song_map_svg(comp_json: Path, label: str, bars: int = 32, bar: float = 4.0) -> str:
    """A one-minute song as a map: four rows (sitar, guitar, bass, drums) by `bars` bars, drawn
    from the notes. Lit = that part plays that bar; red = a note Bhairav forbids; a mustard tick
    above the sitar = that bar brings back earlier material."""
    data = json.loads(comp_json.read_text())
    allowed = set(RAGAS["bhairav"]["allowed"])

    def pick(role: str, instrument: str | None = None) -> dict:
        return next(l for l in data["layers"] if l["role"] == role and (instrument is None or l.get("instrument") == instrument))
    rows = [(pick("lead", "sitar"), INDIGO), (pick("rhythm"), TERRA), (pick("bass"), SKY), (pick("drums"), PURPLE)]
    cw = 116 / bars
    r = [f'<rect width="120" height="48" fill="{CARD}"/>']
    for i, (layer, c) in enumerate(rows):
        y0 = 9 + i * 9.5
        events = layer.get("notes") or layer.get("hits") or []
        on, bad = set(), set()
        for e in events:
            s0, d = e["start"], e.get("dur", 0.2)
            for k in range(int(s0 // bar), int((s0 + min(d, bar) - 1e-6) // bar) + 1):
                on.add(k)
                if "swara" in e and (e["swara"] not in allowed or any(cs not in allowed for cs in e.get("chord") or [])):
                    bad.add(k)
        for k in range(bars):
            fill = DANGER if k in bad else (c if k in on else SUNK)
            r.append(f'<rect x="{2 + k * cw:.2f}" y="{y0:.1f}" width="{cw - 0.6:.2f}" height="7.5" rx="0.6" fill="{fill}"/>')
        if i == 0:
            seen: set = set()
            for k in range(bars):
                content = tuple(sorted((round(e["start"] - k * bar, 3), e["swara"], e["oct"], e["dur"])
                                       for e in events if k * bar <= e["start"] < (k + 1) * bar))
                if content and content in seen:
                    r.append(f'<rect x="{2 + k * cw:.2f}" y="3" width="{cw - 0.6:.2f}" height="3" fill="{MUSTARD}"/>')
                if content:
                    seen.add(content)
    return (f'<svg aria-label="{label}" style="width:100%;height:170px" viewBox="0 0 120 48">' + "".join(r) + "</svg>")


def s_naive() -> str:
    """The experiment, posed: three contestants and one request. No audio and no verdict here;
    the measured answer closes Act 2 (`s_ladder`), after the redesign it depends on."""
    def contestant(k: str, name: str, how: str, pic: str) -> str:
        return card(p(k, 56, INDIGO, f";font-family:{SERIF};font-weight:700")
                    + f'<div style="height:200px;display:flex;align-items:center;justify-content:center;gap:8px">{pic}</div>'
                    + p(name, 40, INDIGO, ";font-weight:800") + p(how, BODY, MUTED), LINE, gap=12)
    plain = V.bubble(200, 160)
    grammar = V.bubble(170, 136) + V.doc(120, 150, "raga")
    system = "".join(persona(n, 1.6) for n in ("interpreter", "composer", "rhythm", "rasik", "producer"))
    inner = [eyebrow("The experiment"), h2("Can one prompt write raga metal?"),
             p("“A one-minute heavy metal song in raga Bhairav.” Three ways to answer it:", BODY, MUTED, ";font-style:italic"),
             row(contestant("A", "One plain prompt", "The model alone, no knowledge.", plain),
                 contestant("B", "The prompt plus the raga's grammar", "Our raga data pasted in.", grammar),
                 contestant("C", "The agentic system", "Six agents and code.", system), gap=28),
             p("Hold your guess. The answer comes later, after we nearly got it wrong.", BIG, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:600")]
    return section("naive", inner, "About a minute. Pose the question, don't answer it. The same request, three ways: the bare model; the bare model with the raga's grammar from our data; the system. Ask the room to guess which wins and by how much. The answer opens Act 2, after the band has grown to eleven agents; the answer on today's model is the ladder that closes Act 2.", gap=26)


def s_rules() -> str:
    return statement("rules", "Following the rules gets you correct.<br>It doesn't get you good.",
                     "Code can check correct. Only a listener can judge good.",
                     "Pause. The measured answer just landed: the bare prompt was correct and still not music. Knowledge buys correctness; it does not buy good. Code can check the first, only a listener can judge the second, and that split runs through the rest of the talk.")


def s_vote() -> str:
    bolt = V.svg(240, 272, f'<path d="M92 6 L28 96 H74 L54 164 L124 66 H78 Z" fill="{TERRA}"/>', "fast", (150, 170))
    slow = V.svg(360, 225, f'<path d="M6 75 C 60 -10, 120 160, 234 75" fill="none" stroke="{PURPLE}" stroke-width="16" stroke-linecap="round"/>', "slow", (240, 150))
    def opt(k: str, name: str, pic: str, c: str) -> str:
        return (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:14px;background:{CARD};border-top:10px solid {c};border-radius:20px;padding:26px">'
                f'<div style="height:320px;display:flex;align-items:center">{pic}</div>'
                f'{p(f"{k} · {name}", 52, INDIGO, f";font-family:{SERIF};font-weight:700")}</div>')
    inner = [eyebrow("Your turn"), h2("Choose the style for our live composition"),
             row(opt("A", "Doom", slow, PURPLE), opt("B", "Symphonic", persona("orchestra", 4.4), MUSTARD), opt("C", "Thrash", bolt, TERRA), gap=32),
             p("Composing your choice live, inside a twelve-minute budget; "
               "if it runs late, we play a recorded example in your chosen style.", BODY, SKY_TEXT, ";text-align:center")]
    return section("vote", inner, "Right after the reveal, about minute three: starting now gives the live run most of the talk. Show of hands, no web poll. Start the winning style with RMA_BUDGET_S=720: optional stages (another revision, the notes debate, listening) start only while they fit. The budget gates those stages; it does not guarantee a finish (the 20 October symphonic doom run took about ten and a half minutes unbudgeted), so start it now and keep the labelled fallback ready. Prepare one recorded fallback per style, labelled as recorded. The payoff slide plays whichever is true.", gap=36)


# ---- the patterns: introduced where we adopted them (Act 1), judged in Act 3 ----------------------
def _when(i: int, title: str, text: str | tuple[str, ...], accent: str, ink: str) -> str:
    """One of a pattern card's three boxes, pinned so it can pop in on its own click (i + 1): a
    short line, or bullets when the box really lists conditions."""
    body = (p(text, LABEL, INK, ";line-height:1.3") if isinstance(text, str) else
            f'<ul style="font-size:{LABEL}px;line-height:1.3;color:{INK};padding-left:30px">'
            + "".join(f"<li>{t}</li>" for t in text) + "</ul>")
    return (f'<div data-build-in="fade {i + 1}" style="position:absolute;left:{128 + i * 568}px;top:740px;width:528px;'
            f'background:{CARD};border:2px solid {LINE};border-top:10px solid {accent};border-radius:16px;'
            f'padding:16px 22px;display:flex;flex-direction:column;gap:6px">'
            f'{p(title, LABEL, ink, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")}{body}</div>')


def _scene(key: str) -> str:
    """Our band acting the pattern out (talk/deck/scenes.py): characters placed in the pattern's shape,
    with the animated layer — routes, flying messages, rings, speech bubbles — drawn over them."""
    import scenes
    sc = scenes.SCENES[key]
    out = []
    for actor in sc.actors:
        if actor.kind in SPRITES:
            pic, w, h = persona(actor.kind, 2.3), 110, 152
        else:
            pic, w, h = scenes.icon(actor.kind), 170, 152
        out.append(f'<div style="position:absolute;left:{actor.x - w / 2:.0f}px;top:{actor.y - h / 2:.0f}px;width:{w}px;'
                   f'height:{h}px;display:flex;align-items:center;justify-content:center">{pic}</div>')
        out.append(f'<p style="position:absolute;left:{actor.x - 150:.0f}px;top:{actor.y + h / 2 + 2:.0f}px;width:300px;'
                   f'text-align:center;font-size:{LABEL}px;font-weight:800;color:{INDIGO}">{actor.label}</p>')
    art = V.svg(scenes.W, scenes.H, scenes.overlay(key), f"{PATTERNS[key].name if key in PATTERNS else key}, acted out by our agents", (scenes.W, scenes.H))
    out.append(f'<div style="position:absolute;left:0px;top:0px;width:{scenes.W}px;height:{scenes.H}px">{art}</div>')
    return f'<div style="position:relative;width:{scenes.W}px;height:{scenes.H + 40}px">{"".join(out)}</div>'


def s_pattern(key: str, full: bool = True) -> str:
    """A pattern, taught through our own band: the scene (real messages, in order), then what the
    pattern is, when to use it and when not to."""
    pt = PATTERNS[key]
    facts = [_when(0, "What it is", pt.what, INDIGO, INDIGO), _when(1, "Use it when", pt.use_when, SKY, SKY_TEXT),
             _when(2, "Avoid it when", pt.avoid_when, TERRA, TERRA_TEXT)][:3 if full else 1]
    if not full:   # the comparison has its own slide; "what it is" spans the width
        facts = [facts[0].replace("width:528px", "width:1664px", 1)]
    where = "Act 3 · the pattern we never built in" if key == "hitl" else "Act 1 · a pattern we reached for"
    # A "Pattern" chip, pinned top right, marks every pattern card (Sujit, 2026-10-19), so no title needs the word.
    chips = chip("Pattern", MUSTARD, INDIGO) + (chip(f"+ {pt.also}", PURPLE) if pt.also else "")
    badge = (f'<div style="position:absolute;top:88px;right:128px;display:flex;gap:16px;align-items:center">'
             f'{chips}</div>')     # the same corner on every pattern card, whatever the title's length
    inner = [eyebrow(where), h2(pt.name), _scene(key), *facts, badge]
    return section(f"p-{key}", inner, f"Why we reached for it: {pt.why_us} {pt.intro_notes} "
                   + ("Let the scene play, then CLICK 1: what it is. CLICK 2: use it when. CLICK 3: avoid it when." if full
                    else "Let the scene play, then CLICK 1: what it is."), gap=22)


def s_story(sid: str, key: str, eyebrow_text: str, title: str, beats: tuple[tuple[str, str | tuple[str, ...]], ...], notes: str,
            scene: str | None = None, chips: tuple[str, ...] | None = None) -> str:
    """A pattern told as the story of our experiment (Sujit, 2026-10-20: "patterns as story"): our band acts it out
    (the scene, verbatim from traces), then three beats on click — what the pattern is, what happened, what we
    kept. Replaces the definition card + verdict pair."""
    pt = PATTERNS[key]
    colours = ((INDIGO, INDIGO), (TERRA, TERRA_TEXT), (SKY, SKY_TEXT))
    cards = [_when(i, head, text, *colours[i]) for i, (head, text) in enumerate(beats)]
    names = chips or ((pt.name, pt.also) if pt.also else (pt.name,))
    inner = [eyebrow(eyebrow_text), h2(title), _pattern_chips(*names), _scene(scene or key), *cards]
    return section(sid, inner, notes + " Let the scene play, then CLICK 1, 2, 3: the three beats.", gap=22)


def s_own_now() -> str:
    """The split chapter's Now (Sujit, 2026-10-20): the two advocates became one composer holding both priors."""
    def person(sprite: str, name: str, prior: str, scale: float = 2.0) -> str:
        return (f'<div style="display:flex;flex-direction:column;align-items:center;gap:6px">{persona(sprite, scale)}'
                f'{p(name, 36, INDIGO, ";font-weight:800")}{p(prior, 32, MUTED, ";text-align:center;line-height:1.2")}</div>')
    before = card(p("Before: two advocates", 40, TERRA_TEXT, ";font-weight:800")
                  + row(person("pandit", "Pandit", "argues for tradition"),
                        p("⇄", 64, MUTED, ";align-self:center"), person("riffsmith", "Riffsmith", "argues for metal"),
                        gap=24, align="end", extra=";justify-content:center")
                  + p("two to four calls, one script, then a plan", 34, INK, ";text-align:center"),
                  TERRA, flex="flex:1", gap=18)
    after = card(p("Now: one composer, both priors", 40, SKY_TEXT, ";font-weight:800")
                 + row(person("composer", "Pandit", "“a guitarist who grew up on metal and trained in Hindustani music”", 2.4),
                       gap=0, extra=";justify-content:center")
                 + p("one call: the plan, the main riff and the hook's idea", 34, INK, ";text-align:center"),
                 SKY, flex="flex:1", gap=18)
    after = after.replace('<div style="flex:1;', '<div data-build-in="fade 1" style="flex:1;', 1)
    inner = [eyebrow("Act 2 · two agents or one? · now"), h2("Two advocates became one composer"), row(before, after, gap=32),
             p("If one model can hold both priors, don't split them into two agents to argue.", 40, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("own-now", inner, (
        "WHERE WE ARE: two agents or one?, Now. Before: two agents with opposite priors, written into their backstories, "
        "negotiated the plan. CLICK: now one composer holds both priors; its brief, verbatim, is 'a guitarist who grew "
        "up on metal and trained in Hindustani music. You write the riff and the melody in the same sitting, because "
        "they are one idea.' One seed call writes the plan, the main riff and the hook's idea; the old negotiation took "
        "two to four calls and ended where Pandit started. Today's Pandit is not the old traditionalist; it is one "
        "musician carrying both voices. NEXT: collaboration or debate, the difference."), gap=26)


COLLAB_VS_DEBATE: Final = (
    ("Purpose", "Build one thing from different strengths", "Test competing answers"),
    ("How it runs", "Propose, build, refine", "Propose, challenge, defend"),
    ("Who decides", "The shared result meets the goal", "A judge picks one"),
    ("Main risk", "Nobody challenges anything", "Disagreement made up for its own sake"),
)


def s_collab_vs_debate() -> str:
    """The chapter's hinge (GPT's comparison, trimmed; Sujit 2026-10-20): slides before are collaboration, slides after
    are debate. Generic, so it reads for any system."""
    def cell(text: str, *, head: bool = False, ink: str = INK, bg: str = CARD) -> str:
        weight = "800" if head else "400"
        return (f'<div style="background:{bg};border-radius:14px;padding:14px 22px;display:flex;align-items:center">'
                f'{p(text, 40 if head else 36, ink, f";font-weight:{weight};line-height:1.25")}</div>')
    head = (cell("", bg=PAGE) + cell("Collaboration", head=True, ink=SKY_TEXT, bg="#E3F0F4")
            + cell("Debate", head=True, ink=TERRA_TEXT, bg="#F8E4DF"))
    body = "".join(cell(label, head=True, ink=MUTED, bg=PAGE) + cell(c) + cell(d) for label, c, d in COLLAB_VS_DEBATE)
    grid = (f'<div style="display:grid;grid-template-columns:300px 1fr 1fr;gap:12px">{head}{body}</div>')
    inner = [eyebrow("Act 2 · two agents or one?"), h2("Collaboration or debate?"), grid,
             p("Either way, ask what the second agent brings that one capable agent wouldn't.", 42, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("collab-vs-debate", inner, (
        "The hinge of the chapter: everything so far was collaboration, everything next is debate. Collaboration: "
        "agents with different strengths build one shared result, proposing, building and refining, and it ends when "
        "the result meets the goal; its risk is that nobody challenges anything. Debate: agents hold competing "
        "answers, challenge and defend them, and a judge picks; its risk is disagreement manufactured for its own "
        "sake, and extra rounds. They are not exclusive: a collaborative workflow can call a debate to settle one "
        "decision, which is exactly what the sitar and guitar debate two slides on turns out to be. Close on the "
        "question for every extra agent: what new information, independent view or decision quality does it bring "
        "that one capable agent would not? NEXT: we tried to make two composers disagree."), gap=26)


def s_comp_proof() -> str:
    return s_story("comp-proof", "debate", "Act 2 · two agents or one? · proof", "We tried to make two composers disagree", (
        ("Detailed prompt", ("Composers on Gemini and on OpenAI", "Each wrote a song plan", "All wrote the same piece")),
        ("Looser prompt", ("Each chose its own melody", "Arguing, both made the change one composer made alone")),
        ("What we learned", ("Same facts and same prompt: they agree", "Even on different models"))),
        "WHERE WE ARE: two agents or one?, the evidence. Three experiments, each a variation of the debate pattern, all on 18-19 "
        "October. CLICK 1, STEERED TIGHT, the seed debate: a single composer, the same model debating itself, and "
        "Gemini against OpenAI's Sol. All seven seeds chose the same piece before arguing: the same gat, tempo, "
        "sections and opening cell. The prompt had decided: 43 directive lines, a motif handed down, a fixed stroke "
        "grid for slow tempos. Two vendors, one answer. Blind, my ranking put the single composer first; it took 2 "
        "calls against 9 and 10. CLICK 2, LOOSENED: each composer chose its own motif. Melodies went from 82% alike to "
        "54%, all still correct Darbari; rhythm stayed 89% alike, because the grid fixes it; I could not rank them. "
        "Then two composers with different briefs debated their heads: both quoted the same code measurement and made "
        "the same move into the low register; the judge's two orders disagreed. The control, one composer with the same "
        "measurement and no rival, made the same move in 5 calls and 89k tokens against 12 and 184k. Loosening bought "
        "variety, not a second opinion. CLICK 3: agents given the same facts and the same prompt agree, even across vendors; a second agent is not a second opinion; what moved the music each time was a measurement, not a rival. NEXT: the one debate that "
        "worked.", scene="composer-debate")


def s_own_before() -> str:
    return s_story("own-before", "blackboard", "Act 2 · ownership", "How the first band planned a song", (
        ("How it worked", ("Personas: tradition vs metal", "Turns on one shared plan", "Sitar and guitar agents, too")),
        ("What hurt", ("Every run: propose, push back once, accept", "Riffsmith never once changed Pandit's melody")),
        ("So we asked", "Does a second persona of the same model bring a second opinion?")),
        "WHERE WE ARE: chapter one, two agents or one?; the badge says: the first band. How the first band planned a song, acted "
        "out from a real July trace (6cb40c236412): Pandit proposes the form, Riffsmith pushes back, Pandit accepts. Name "
        "the pattern: COLLABORATION, in its BLACKBOARD form: equals taking turns on one shared plan, code fixing the order and the turn limit, "
        "nobody judging. It was not a debate: no competing answers and no judge, just two authors revising one plan "
        "until both accepted. CLICK 1, third bullet: the same blackboard ran one level down, in the studio session: "
         "for each section the sitar (Lead) and the guitar (Riff) agents took turns on a shared canvas, which is how "
         "the opening song was made; the riff answered a draft of the sitar, which then changed after hearing it. CLICK 2, what hurt, measured across all 31 recorded runs of the two composers: 28 followed one script, Pandit "
        "proposes, Riffsmith pushes back once, Pandit accepts; none went past one round of push back. The hook's seed "
        "never changed (31 of 31). The metal voice's whole contribution: nudge the tempo (16 runs) and add a breakdown "
        "(11). Those are its backstory's priors replayed, not a new idea. CLICK 3, the question the rest "
        "of the chapter answers. NEXT: the textbook version of this pattern, and why we did not use it.",
        scene="composers", chips=("Collaboration", "Blackboard"))


HOOK_BEFORE: Final = (("G m d d P G m r r S S S r", None), ("G m d d P G m r S S S r", 8))   # trace 480f18b59298


def _hook_line(swaras: str, gap_at: int | None = None, ink: str = INK) -> str:
    """One statement of the hook as swara chips; gap_at marks the note the second statement lost."""
    cells = [f'<span style="display:inline-block;min-width:44px;text-align:center;font-family:{MONO};font-size:36px;'
             f'color:{ink}">{s}</span>' for s in swaras.split()]
    if gap_at is not None:
        cells.insert(gap_at, f'<span style="display:inline-block;width:40px;height:40px;border:3px dashed {DANGER};'
                             f'border-radius:8px;vertical-align:middle;margin:0px 2px"></span>')
    return f'<div style="display:flex;align-items:center;gap:2px">{"".join(cells)}</div>'


def s_hook_fix() -> str:
    """The split chapter's Now (GPT's framing, 2026-10-20): a shared idea is made once and reused; a dependent part
    is handed the finished material. Replaces "one owner took the parts back" (own-flow, now in the annex)."""
    def label(text: str, ink: str) -> str:
        return p(text, 32, ink, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")
    hook = card(p("The hook: make it once", 40, INDIGO, f";font-family:{SERIF};font-weight:700")
                + label("Before: rewritten in each section", TERRA_TEXT)
                + "".join(_hook_line(s, g) for s, g in HOOK_BEFORE)
                + p("the second time, a note went missing", 32, DANGER, ";font-weight:800")
                + f'<div data-build-in="fade 1" style="display:flex;flex-direction:column;gap:10px">'
                + label("Now: one hook, repeated by code", SKY_TEXT)
                + _hook_line("G m d d P G m r r S S S r", None, SKY_TEXT)
                + p("identical at every return", 32, SKY_TEXT, ";font-weight:800") + "</div>",
                INDIGO, flex="flex:1", gap=12)
    def step(pics: str, text: str) -> str:
        return (f'<div style="display:flex;align-items:center;gap:16px;background:{PAGE};border-radius:14px;'
                f'padding:8px 16px">{pics}{p(text, 34, INK, ";line-height:1.2")}</div>')
    guitar = card(p("The guitar: give it the finished part", 40, INDIGO, f";font-family:{SERIF};font-weight:700")
                  + label("Before: it answered a draft", TERRA_TEXT)
                  + step(persona("lead", 1.2) + persona("riff", 1.2), "the riff answered the sitar's draft, then the sitar changed")
                  + f'<div data-build-in="fade 2" style="display:flex;flex-direction:column;gap:10px">'
                  + label("Now: it gets the finished sitar", SKY_TEXT)
                  + step(persona("rhythm", 1.2), "one call writes the whole song's guitar and bass, seeing every sitar note")
                  + "</div>", SKY, flex="flex:1", gap=12)
    inner = [eyebrow("Act 2 · two agents or one? · now"), h2("Make it once. Hand over the finished part."), row(hook, guitar, gap=28),
             p("Create a shared idea once and reuse it. Give dependent work the finished material it needs.", 40,
               TERRA_TEXT, f";font-family:{SERIF};font-weight:700")]
    return section("hook-fix", inner, (
        "Two changes, and both are about state, not about who the writer is. THE HOOK: in "
        "the old band each mukhada section wrote the hook inside its own call. For the second one the prompt said 'no "
        "mukhada stated yet', so it was written again, and a note went missing (trace 480f18b59298). Call it what it "
        "is: a state-propagation bug. The fix is the lesson: exact recurrence should be reuse, not another generation "
        "task. Now the gat call commits the hook once and code repeats it (the line on the slide is the same old hook, drawn as it would repeat); a stronger model might copy it more "
        "reliably, but you would still be asking it to rebuild something you already have. CLICK 1. THE GUITAR: the "
        "studio riff answered a draft of the sitar, which then changed; where the guitar led, there was no sitar at "
        "all. Now the Rhythm section writes guitar and bass for the whole song in one call, after the sitar is "
        "finished. CLICK 2. The rule: create shared ideas once and reuse them explicitly; give dependent parts the "
        "committed material they need. Keeping the hook and its development in one gat call helps them grow together; "
        "the repeat by code is what guarantees the hook. NEXT: the band after this change."), gap=22)


def s_notes_win() -> str:
    """The one debate that beat the original by ear (2026-10-19): each side owned a different part."""
    return s_story("notes-win", "debate", "Act 2 · two agents or one? · proof", "The debate that worked", (
        ("Who argued", ("Lead (sitar) on Gemini", "Guitar on GPT", "Both saw the whole song", "Each rewrote only its part")),
        ("What happened", ("Each caught the other's mistakes", "A rewrite for a wrong reason", "A part one beat too long")),
        ("We kept it", ("It runs when a reviewer flags a problem", "Otherwise it is skipped"))),
        "WHERE WE ARE: two agents or one?, the one debate that worked, the morning of 19 October, two songs (a Darbari and a "
        "Bhairav). A Gemini sitarist (the lead line, where the hook lives) and a GPT guitarist (gpt-6-luna); both were "
        "shown the whole song as it stood, every section of sitar and guitar, but each could rewrite only its own part; "
        "each proposed one rewrite, critiqued the other's, then kept, revised or withdrew it; code checked every rewrite, "
        "and a change was kept only if it beat the current song. They argued notes and disagreed for the first time. "
        "The guitarist caught the sitarist rewriting the head on a false premise (it said the old head ended on Sa; it "
        "ended on Re) and named a held-note rub; the sitarist asked the guitarist's low, palm-muted antara riff to end "
        "under its note; in the Bhairav run the guitarist found the sitar's outro was 17 beats in a 16-beat section, a bug "
        "no check had caught. My ear: 2 better, 1 sidegrade, 1 neutral, 0 worse. Different models and different parts "
        "changed together, so say it honestly: each side owned something the other did not. A small sample; today it "
        "runs only when a reviewer names a concern. Say what we kept: it is in tonight's workflow, but conditional. It "
        "runs only when a reviewer flags a problem (Rasik scores the raga low, or the Producer scores the hook, balance "
        "or performance 3 or below), and that concern becomes the players' brief; otherwise it is skipped, about seven "
        "calls saved. NEXT: the rules we would hand anyone adding a second agent.",
        scene="notes-win")


def s_rhythm_now() -> str:
    """The second change (Sujit, 2026-10-20): the sitar and guitar agents' section-by-section collaboration (13 calls
    on the opening song, trace 480f18b59298) became one rhythm-section call written after the sitar is finished."""
    def chip_(text: str, bg: str, ink: str = INDIGO) -> str:
        return (f'<p style="font-size:32px;font-weight:800;color:{ink};background:{bg};border-radius:12px;'
                f'padding:4px 16px;white-space:nowrap">{text}</p>')
    def turn(n: str, who: str, sprite: str, did: str) -> str:
        return (f'<div style="display:flex;align-items:center;gap:14px;background:{PAGE};border-radius:14px;padding:6px 16px">'
                f'{p(n, 32, MUTED, ";font-weight:800")}{persona(sprite, 0.9)}{p(f"{who} {did}", 34, INK)}</div>')
    before = card(p("Before: they collaborated, section by section", 38, TERRA_TEXT, ";font-weight:800")
                  + turn("1", "Sitar", "lead", "drafts the section")
                  + turn("2", "Guitar", "riff", "answers the draft")
                  + turn("3", "Sitar", "lead", "rewrites its line")
                  + f'<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
                  + chip_("sitar: 7 calls", MUSTARD) + chip_("guitar: 6 calls", MUSTARD) + "</div>"
                  + p("The guitar answered a draft that then changed. Code derived the bass, and a fixer agent mended the clashes.", 34, INK, ";line-height:1.25"),
                  TERRA, flex="flex:1", gap=12)
    after = card(p("Now: the sitar first, then one call", 38, SKY_TEXT, ";font-weight:800")
                 + turn("1", "Lead", "lead", "writes the theme in one call")
                 + turn("2", "Lead", "lead", "writes intro and solo, a call each")
                 + turn("3", "Rhythm section", "rhythm", "writes guitar and bass")
                 + f'<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
                 + chip_("sitar: 3 calls", MUSTARD) + chip_("guitar and bass: 1 call", MUSTARD) + "</div>"
                 + p("It hears every finished sitar note before it writes.", 34, INK, ";line-height:1.25"),
                 SKY, flex="flex:1", gap=12)
    after = after.replace('<div style="flex:1;', '<div data-build-in="fade 1" style="flex:1;', 1)
    inner = [eyebrow("Act 2 · two agents or one?"), h2("From many turns to one call"), row(before, after, gap=32),
             p("Write the part that depends on another once, after that part is finished.", 40, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("rhythm-now", inner, (
        "WHERE WE ARE: the second change. BEFORE, the first band's studio session: for every section, the sitar and "
        "guitar agents collaborated on a shared canvas, the sitar drafting, the guitar answering, the sitar rewriting. "
        "On the opening song (trace 480f18b59298, five sections): the sitar agent 7 calls and the guitar agent 6, four "
        "of the guitar's rejected by the old riff rule. Now, for the same five sections: the sitar 3 (one gat call for the "
        "hook sections, one each for the alap and the taan, no redrafts). Apples to apples: both sides are the same five sections. This song had no outro; with one, now would be 4 sitar calls (the outro gets its own call, run alongside the intro and solo) and before would have been about 9 (draft plus rewrite, an estimate). Now's 3 + 1 assumes every check passes first time; a retry adds a call on either side, as the old guitar's four thrown-out answers did. and the guitar 1, which writes the bass too. The guitar always answered a draft that then changed, and in "
        "guitar-led sections there was no sitar yet at all; the bass was not written by anyone, code derived it from "
        "the riff. CLICK: NOW the sitar is finished first, and one Rhythm-section call writes guitar AND bass for the "
        "whole song, seeing every sitar note (guitar and bass both play the rhythm, so one agent owns both). It never "
        "answers a draft. A blind test leaned the same way: under the hook, a guitar "
        "written after the finished sitar fit better than the composer's own riff, 3 songs of 5 (a lean, not a law). "
        "NEXT: the band after this change."), gap=26)


def s_ev_story() -> str:
    return s_story("ev-story", "evaluator", "Act 2 · judgment · the judge", "The judge asked for a revision every time", (
        ("What we built", ("One agent writes", "A judge critiques", "The writer revises, until accepted or capped")),
        ("What happened", ("It revised every first draft", "Its scores rose as often as they fell", "Blind, I preferred the first draft")),
        ("What we kept", ("It accepts by default", "A revision must win in both orders"))),
        "Evaluator-optimiser, the loop every agent framework demos. Ours: Rasik advises on the raga, the Producer judges "
        "the song, Pandit revises, and the round limit is in code. The scene is real: the Producer's plans, verbatim "
        "(trace 57af304fd1ad). CLICK 2, the failure, measured across every recorded run with an accept-or-revise "
        "decision (14 runs): it asked for a revision in all 14, often right after praising the draft; 87% of its scores "
        "were 4 or 5, and after an edit they rose as often as they fell. In the one blind listening test the first draft "
        "won, and the loop had shipped the revision. CLICK 3, the structural fix: accept by default, describe the problem "
        "a listener hears rather than the notes, one round, and keep a revision only if it wins a comparison in both "
        "orders. Point back to the rules chapter: this is the SAME pattern as code checking legality; with code "
        "as the evaluator it works, with a model as the evaluator it over-revised. The pattern is fine; the evaluator "
        "decides. The first band also had the critics DEBATE when they disagreed, a Conductor ruling: it re-argued "
        "opinions already on the table and kept the weaker song, so it went. The next slide is one half of that fix, what each judge sees; the other half, a revision kept only if it wins in both orders, is on this slide's third card (one real run of it is in the annex).")


def s_db_story() -> str:
    return s_story("db-story", "debate", "Act 2 · judgment · the debate", "Only the debate about notes helped", (
        ("What it is", "Each agent defends its own answer; a judge picks between them."),
        ("What we compared", "The same fix without the rival: the same move, at half the cost."),
        ("What worked", "Two players rewriting notes they own: some edits better, none worse.")),
        "The test, say it out loud: one draft revised until a critic accepts it is evaluator-optimiser; several "
        "positions and a judge picking between them is debate. Our first was Rasik against the Producer, the Conductor "
        "ruling: it re-argued opinions already on the table and kept the weaker song. The seed debate, Gemini against "
        "OpenAI, wrote one piece seven times: same facts, same answer. The scene is the head debate, two composers' heads "
        "and a judge (trace b0545e590880). CLICK 2, its control: the same starting heads and the same measurements, no "
        "rival, one revision: it made the same correction (into the mandra) in 5 calls and 89k tokens against 12 calls "
        "and 184k. The rival added nothing the measurement didn't; and one solo revision overshot, which is why a "
        "repair needs a check against regressions. The rehearsal, players turning knobs on the mix, only subtracted, "
        "and the song went hollow. CLICK 3, the fifth: a Gemini sitarist and a GPT guitarist, each rewriting notes of "
        "their own part, critiquing each other, every change kept only if it wins against the current take. By my ear "
        "across two songs: some edits better, none worse. A small sample, still being evaluated; today it runs only "
        "when a reviewer names a concern. If asked why the debates converged: the annex slide on the funnel shows the "
        "prompt had decided the answer before the debate began.")


def s_verdict(key: str) -> str:
    """Our version of a pattern: who played it, the verdict, the evidence, what we lacked."""
    pt = PATTERNS[key]
    who = "".join(persona(n, 2.1) for n in pt.cast) if pt.cast else V.crowd(320, 170)
    left = (f'<div style="flex:4;display:flex;flex-direction:column;align-items:center;gap:20px;background:{CARD};'
            f'border:2px solid {LINE};border-radius:20px;padding:24px">'
            f'<div style="display:flex;align-items:end;justify-content:center;gap:4px;height:180px">{who}</div>'
            f'{V.stamp(pt.verdict, pt.verdict_color, 26 * len(pt.verdict) + 90, 110, -4)}{diagram(key, 320, 192, pt.name)}</div>')
    ev = "".join(p(e, BODY, INK, f";border-left:8px solid {LINE};padding-left:22px") for e in pt.evidence)
    right = f'<div style="flex:6;display:flex;flex-direction:column;gap:22px">{ev}</div>'
    inner = [eyebrow(f"Act 3 · the verdict · {pt.name}"), h2(pt.headline), _pattern_chips(pt.name), row(left, right, gap=36),
             p(pt.takeaway, 44, TERRA_TEXT, f";font-family:{SERIF};font-weight:700")]
    agent = AGENTIC.get(key)
    notes = pt.verdict_notes + (f" As an agent instead: {agent[0]}. {agent[2]}" if agent else "")
    return section(f"v-{key}", inner, notes, gap=24)


def _choice(sid: str, eyebrow_text: str, left: tuple, right: tuple, why_title: str, why: str | tuple[str, ...],
            notes: str) -> str:
    """Two patterns side by side, when to use each in plain words, then (on click) why we chose ours. Each side is
    (icon html, name, ink, accent, use-when lines)."""
    def bullet(text: str, color: str) -> str:
        return p(text, 36, INK, f";border-left:6px solid {color};padding-left:16px;line-height:1.22")

    def side(icon: str, name: str, ink: str, accent: str, when: tuple[str, ...]) -> str:
        head = (f'<div style="display:flex;align-items:center;gap:20px">{icon}'
                f'{p(name, 46, ink, f";font-family:{SERIF};font-weight:700;line-height:1.1")}</div>')
        return card(head + p("Use it when", 32, MUTED, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")
                    + "".join(bullet(t_, accent) for t_ in when), accent, flex="flex:1", gap=16)
    reason = (f'<div data-build-in="fade 1" style="background:{CARD};border:2px solid {LINE};border-left:12px solid {TERRA};'
              f'border-radius:16px;padding:22px 30px;display:flex;flex-direction:column;gap:10px">'
              + p(why_title, 40, TERRA_TEXT, ";font-weight:800")
              + (p(why, 38, INK, ";line-height:1.3") if isinstance(why, str) else
                 f'<ul style="font-size:38px;line-height:1.3;color:{INK};padding-left:34px">'
                 + "".join(f"<li>{w}</li>" for w in why) + "</ul>") + "</div>")
    inner = [eyebrow(eyebrow_text), h2("Which one, and when?"), row(side(*left), side(*right), gap=32), reason]
    return section(sid, inner, notes, gap=26)


def s_workflow_choice() -> str:
    """The two patterns side by side — when to use each, in plain words — then why we chose the workflow (Sujit,
    2026-10-19: introduce the alternative as a pattern first, then compare, then say why). Evidence in the notes."""
    import scenes
    return _choice(
        "v-workflow", "Act 2 · rules and control · the choice",
        (V.braces_check(96, 80), "Predefined workflow", INDIGO, SKY,
         ("You know the steps.", "You want predictable time and cost.", "You want to see and fix each step.")),
        (scenes.icon("model"), "Autonomous agent", MUSTARD_TEXT, MUSTARD,
         ("Nobody can list the steps ahead.", "Each request needs a different path.",
          "Waiting longer is fine, if it reaches further.")),
        "Why we chose the workflow",
        ("A song has known steps, so code can order them", "A model choosing its own steps took about three times as long",
         "It won by ear once; that did not pay for the extra time and cost"),
        ("Two patterns, one question: does code decide the order of the work, or does a model? Use a workflow when "
         "you can write the steps down, when it must always finish, and when you want to see and fix each step. Use "
         "an autonomous agent when nobody can list the steps in advance and each request needs its own path, and "
         "you can afford it taking longer. CLICK: why we chose the workflow. Composing a song has known stages, so code "
         "can order them; letting a model choose costs time, money and latency. Be precise about the evidence: we never ran a model choosing the whole workflow, so this "
         "is a choice, not a measured failure of the alternative. What we did measure was agency inside one step: "
         "Pandit choosing its own checks was better by ear once, but took about three times as long; a listening "
         "tool made Pandit chase one measurement and lose the raga's cadence; and our judge, deciding when a song was "
         "done, revised the first draft every time (a loop decision, not a workflow one). Anthropic's advice matches: "
         "start with the simplest thing, and add agency only where it pays."))


def s_calls_choice() -> str:
    """When to merge work into one model call and when to keep separate calls (Sujit, 2026-10-20: the learning
    behind the rhythm-section change, stated generally, right after it)."""
    import scenes
    many = "".join(scenes.icon("model") for _ in range(3))
    return _choice(
        "calls-choice", "Act 2 · two agents or one? · the choice",
        (scenes.icon("model"), "One call", MUSTARD_TEXT, MUSTARD,
         ("The parts must fit each other note by note.", "The parts are one idea, conceived together.",
          "Each extra call costs time and money.")),
        (f'<div style="display:flex;gap:6px">{many}</div>', "Separate calls", INDIGO, SKY,
         ("A part needs another part finished first.", "One call can't attend to every part.",
          "One part's rules would fight another's.")),
        "What we merged, and what we kept apart",
        ("Guitar and bass now share one call: the bass locks to the guitar",
         "The guitar call waits until the whole sitar line is finished",
         "The sitar keeps three calls: the intro holds notes, the fast solo never does"),
        ("The learning behind the last slide, stated for any system. Merge work into ONE call when the parts must "
         "fit each other closely (guitar and bass lock note by note), when they are really one idea (the riff, the "
         "hook and the form were conceived together by one composer), and when the extra calls cost you time and "
         "money for nothing. Keep SEPARATE calls when one part depends on another being finished first (the guitar "
         "needs the finished sitar line), when one call cannot give every part enough attention, when one part's "
         "rules would pull against another's (one prompt per job), and when you want to retry or revise one part without re-rolling the rest. CLICK: what we did. Guitar and bass: one "
         "call, where the bass used to be derived by code from a guitar part written section by section (guitar 6 "
         "calls before, 1 now, on the same five-section song). The sitar went the other way on purpose: it kept "
         "separate calls for the alap, the gat and the taan, each with its own prompt, which also made each prompt "
         "about half as long (alap ~5.2k to ~2.8k tokens, taan ~4.7k to ~2.1k). Merged calls have a cost too: if the "
         "one big answer fails its check, everything is re-asked, so the rhythm-section call keeps a fallback. "
         "The sitar's three calls had a cost we learned the hard way: when one shared prompt served every section, the alap was told to land on the beat it should float over, the taan was asked for rests it must never take, and each new rule landed in every section. Now each job has its own prompt, and a rejected draft rides along with its retry. Later we meet a third reason to keep calls apart: two judges must answer separately, or one copies the other."))


def s_sc_story() -> str:
    """Self-correction from code, told as our story like the other chapters' patterns (Sujit, 2026-10-20: "same
    treatment as other patterns, with animation"). The scene is the Bageshree guardrail retry (trace 8805efb8eceb)."""
    pt = PATTERNS["selfcorrect"]
    return s_story("sc-story", "selfcorrect", "Act 2 · rules · the pattern", pt.headline, (
        ("What it is", ("The model writes", "Code checks the answer", "The fault goes back, once")),
        ("What happened", ("Drafts ignored a stated rule", "Shown a number, they moved", "One fix overshot")),
        ("What we kept", ("Code checks every answer", "A fix must break nothing"))),
        "Name it honestly: this is Anthropic's evaluator-optimiser, the same pattern as the judge chapter, with CODE "
        "as the evaluator. The research name is CRITIC (Gou et al., 2023); libraries ship it as validate-and-retry "
        "(Guardrails AI's reask, Instructor's validation retries). The scene is real: Pandit writes a Bageshree phrase, the validator rejects it with the exact rule (Pa only on "
        "the way down), Pandit moves Pa, the check passes. " + pt.intro_notes + " CLICK 2, the craft result: "
        + pt.verdict_notes, chips=("Evaluator–optimiser", "code as the evaluator"))


CODE_RULES: Final = ("Every note belongs to the raga", "Notes move in the raga's allowed direction",
                     "Each part fills its exact length", "The riff loops cleanly around the cycle",
                     "The guitar part is playable, when asked", "The theme is one idea and holds a note",
                     "The fast solo runs unbroken into the theme")
CODE_MEASURES: Final = ("Is the raga's signature phrase there?", "Time spent low, middle and high",
                        "Bursts of notes, and room to breathe", "Energy, section by section",
                        "How often the theme comes back", "Where the guitar and sitar clash", "Where the fast solo peaks")


def s_code_rules() -> str:
    """What code owns (Sujit, 2026-10-20: "what all rules we had in code, what all metrics"), so the room sees that the
    deterministic half matters as much as the agents. Rules reject; measurements only report to a judge."""
    def col(head: str, sub: str, items: tuple[str, ...], accent: str, ink: str) -> str:
        return card(p(head, 44, ink, f";font-family:{SERIF};font-weight:700;line-height:1.1") + p(sub, 32, MUTED, ";font-weight:800")
                    + "".join(p(x, 34, INK, f";border-left:6px solid {accent};padding-left:16px;line-height:1.2") for x in items),
                    accent, flex="flex:1", gap=12)
    measures = col("Measurements", "code reports, a judge decides", CODE_MEASURES, SKY, SKY_TEXT)
    measures = measures.replace('<div style="flex:1;', '<div data-build-in="fade 1" style="flex:1;', 1)
    inner = [eyebrow("Act 2 · rules · what code owns"), h2("What code decides, and what it only measures"),
             row(col("Rules", "code rejects a wrong answer", CODE_RULES, TERRA, TERRA_TEXT), measures, gap=32),
             p("Agents write and judge the music; code keeps it correct.", 40, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("code-rules", inner, (
        "The deterministic half of the band, so nobody leaves thinking the agents did everything. LEFT, the rules: a "
        "wrong answer is rejected and goes back with its fault (src/raga.py validate_composition for notes; the "
        "direction rules from each raga's ascent and descent; exact window fill; the riff filling its tala cycle; "
        "fretboard reach and shapes when the request asks for a playable riff; the gat head's shape checks; the taan's "
        "continuity and its landing on the theme). Every one of them is a fact we could check, sourced from two "
        "Hindustani references where it is about the raga. CLICK: the measurements. These never reject: they are "
        "numbers in front of a judge (the signature phrase for Rasik; register, density, energy curve, motif "
        "recurrence, guitar-sitar clashes and the taan's peak for the Producer). Taste stays with the judges; the "
        "numbers keep them honest. Code also PLAYS a lot: the drums, drone and tabla, every ornament's pitch path, "
        "the 22-shruti tuning. About 1,400 tests run on all of it without a single model call."), gap=22)


def s_conductor_now() -> str:
    """Who the Conductor was before it leaves at stage 4 (Sujit, 2026-10-20: its role was never explained): the judge of
    the critics' debate, not an orchestrator — code always decided the order."""
    def beat(head: str, text: str, accent: str, ink: str, attr: str = "") -> str:
        return (f'<div{attr} style="background:{CARD};border:2px solid {LINE};border-left:12px solid {accent};border-radius:16px;'
                f'padding:18px 28px;display:flex;flex-direction:column;gap:6px">'
                f'{p(head, 32, ink, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")}{p(text, 40, INK, ";line-height:1.25")}</div>')
    who = (f'<div style="flex:3;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px">'
           f'{persona("conductor", 3.2)}{p("Conductor", 44, INDIGO, ";font-weight:800")}'
           f'{p("the referee", 34, MUTED)}</div>')
    beats = (f'<div style="flex:7;display:flex;flex-direction:column;gap:18px">'
             + beat("Its job", "When the two critics disagreed, they debated, and it ruled.", INDIGO, INDIGO)
             + beat("What happened", "They repeated opinions already given, and it kept the weaker song.", TERRA, TERRA_TEXT,
                    ' data-build-in="fade 1"')
             + beat("Now", "One judge decides, and code stops after one round.", SKY, SKY_TEXT, ' data-build-in="fade 2"')
             + "</div>")
    inner = [eyebrow("Act 2 · judgment · the referee"), h2("The referee only repeated the argument"), row(who, beats, gap=40)]
    return section("conductor-now", inner, (
        "Before it leaves on the next slide, who it was. Not an orchestrator: code always decided the order of the "
        "work. The Conductor was the judge in the first band's debate. When Rasik and the Producer disagreed, they "
        "argued for a capped number of rounds, Rasik opening, and the Conductor always ruled at the cap, naming one "
        "voice to revise and one reason. CLICK: what happened. The debate re-argued opinions already on the table, and "
        "the ruling accepted the weaker song. CLICK: now. The Producer is the one judge; Rasik advises in parallel, "
        "blind to it; one round, and a revision is kept only if it wins in both orders. The referee's only real job, "
        "stopping, is a number in code."), gap=26)


def s_collab_choice() -> str:
    """Blackboard vs the textbook peer collaboration (Sujit, 2026-10-20: compare on its own slide, then say why)."""
    import scenes
    room = persona("lead", 1.0) + persona("riff", 1.0) + persona("rhythm", 1.0)
    return _choice(
        "collab-choice", "Act 2 · two agents or one? · the choice",
        (scenes.icon("canvas"), "Blackboard", INDIGO, SKY,
         ("You already know whose turn comes next.", "You want to cap turns, time and cost.",
          "Several agents add to one shared piece of work.")),
        (f'<div style="display:flex;align-items:end;gap:4px">{room}</div>', "Peer collaboration", PURPLE, PURPLE,
         ("Each agent owns a different part.", "Nobody can say ahead who should go next.",
          "Taking longer is fine, if the work gets better.")),
        "Why we chose the blackboard",
        ("Agents choosing who goes next take many more turns", "Every turn is a model call: more time, more cost",
         "A song is planned in a known order, so code picks the next writer"),
        ("The two ways to let agents work on one thing together. A blackboard: one shared piece of work, and code "
         "decides who writes next and for how many turns (Hearsay-II, the 1970s speech recogniser, is the origin). "
         "Peer collaboration, the textbook version on the slide before: a room of equals that message each other and "
         "pick the next speaker themselves; frameworks ship it as a group chat. Use the blackboard when the order is "
         "known and the run must end; use peer collaboration when each agent owns a different part and nobody can "
         "script the order, and you can afford many more turns. CLICK: why we chose the blackboard. Letting the agents "
         "pick the next speaker means many more turns, and every turn is a model call: more time, more cost, more "
         "latency, with no sign the music gets better. A song plan has a known order, so code picks the writer and "
         "caps the turns. NEXT: what "
         "replaced even the blackboard: one composer."))


def s_dodont(key: str) -> str:
    """A pattern's rules as Do / Don't, each with the run that taught it (follows its verdict card)."""
    d, pt = DO_DONT[key], PATTERNS[key]

    def col(title: str, items: tuple, c: str, mark: str) -> str:
        body = "".join(f'<div style="display:flex;flex-direction:column;gap:2px">{p(f"{mark} {rule}", 40, INK, ";font-weight:800")}'
                       f'{p(why, 32, MUTED, ";padding-left:46px")}</div>' for rule, why in items)
        return card(p(title, 44, c, ";font-weight:800") + body, c, gap=18)
    inner = [eyebrow(f"Act 3 · what we learned · {pt.name}"), h2(d["title"]),
             row(col("Do", d["do"], SKY_TEXT, "✓"), col("Don't", d["dont"], TERRA_TEXT, "✗"), gap=32)]
    return section(f"dd-{key}", inner, d["notes"], gap=24)


# ---- act 1, step by step: the system as one graph that fills in ---------------------------------
# The build, step by step (ported from the retired pixel deck): (step, pattern, title, pain, decision, trade-off, notes)
STEPS: Final = (
    (3, 'Knowledge as data · guardrail', 'The rules moved into code',
     'Illegal notes slipped through unseen.',
     'Raga facts as data. A validator in code.',
     'Hand-verified data, two sources per raga.',
     'The first real decision, and it came before any agent: the rules leave the prompt and become data plus a deterministic validator, the same data every later agent reads. Online raga data is often wrong, so each raga is checked against two Hindustani sources.'),
    (4, 'Prompt chaining · structured output', 'An interpreter at the door',
     '"Make it angry" became a whole invented brief.',
     'An extractor that invents nothing.',
     'One more call. No silent creative choices.',
     'Free text needs a front door. The first cut chose the subgenre and tempo when you didn\'t say, which is a creative decision hiding at intake. Now the model extracts only what was said, a pure resolver keeps only supported values, and everything unsaid stays OPEN for the composers. "The model is allowed to be wrong about what you said; it is never allowed to decide what\'s legal."'),
    (5, 'Role-based agents · bounded dialogue', 'Two composers who disagree',
     "Nobody owned the song's form.",
     'Two opposed composers argue one chart.',
     'More turns, capped by code. Real tension.',
     "Pandit leans tradition, Riffsmith leans metal. Two neutral agents collapse into agreement theatre; opposed tastes explore the real trade-off. The first cut had code copy the raga's pakad as the motif, so every piece opened the same way: the model got the pen back, code kept the rulebook. We own the loop, so it ends on a turn boundary with a complete chart."),
    (6, 'Agents for decisions, not instruments', 'No bass agent. No drum agent.',
     '~15 instrument agents: 15× calls, 15× failures.',
     'Sitar line and riff are agents. The rest is code.',
     'Rule drums risk sounding canned, so they read the riff.',
     'The pivot, and the answer to "why not an agent for drums and bass?": in metal the bass and the kick follow the riff. That is derivable, not a decision, and every agent is an LLM call, so the wrong axis costs latency, money and failure surface. Deterministic doesn\'t mean dumb: the kick locks to the riff\'s onsets and the feel changes per section. The model supplies durations; code supplies the timing.'),
    (7, 'Tool use · LLM-as-judge', 'Two critics: legal and beautiful',
     'Legal, but lifeless. Nobody said why.',
     'Ustad checks legality. Rasik judges taste.',
     'Two more calls. Taste stays an opinion.',
     "Legality is a fact, so code owns it: Ustad calls the validator as a tool and its output type has no verdict field, so even a lying Ustad can't pass an illegal piece. Taste isn't checkable, so Rasik genuinely judges, against a fixed 1–5 rubric grounded in the raga's pakad and chalan."),
    (8, 'Arbiter · deterministic flow', 'A referee and a round limit',
     'Critics disagreed. Nobody decided.',
     'A Conductor rules. One Flow, capped rounds.',
     'No autonomous orchestrator. Always ends.',
     'Code triages first: illegal means a forced revise with no debate; both critics happy means accept. Only a real aesthetic conflict reaches the Conductor, who always rules at the cap. The pipeline becomes one CrewAI Flow whose router returns done at the round limit.'),
    (9, 'Separate judges · code measures', 'A third critic: the Producer',
     'Rasik judged raga and song at once.',
     'A Producer for the song. Rasik keeps the raga.',
     'One more judge. A debate with real stakes.',
     "Rasik was doing two jobs, and the old debate was hollow: by the time a piece is debated it's legal, so Ustad had no aesthetic stake. Both external reviews flagged it. The Producer judges the song from metrics code computes; the debate becomes Rasik against the Producer, and Ustad exits."),
    (10, 'Shared blackboard', 'The band starts listening',
     'Lead and Riff composed deaf to each other.',
     'A shared canvas. Code picks who leads.',
     'More passes. Never a free group chat.',
     "Each part was legal and well judged, and still didn't sound like a band. On the shared canvas the leader proposes and the follower answers what it actually hears. The sharpest lesson: the first revise regenerated a voice in isolation, so the critique loop quietly undid the collaboration. The canvas became durable Flow state."),
    (11, 'Verifiers · constrained choice · local repair', 'Feelings become budgets',
     '"Too light" had nowhere to go.',
     'Verifiers, an Arranger, an Orchestra.',
     'Domain work to set budgets. Fixes, not rewrites.',
     'Listening notes became numbers a generator must meet, with one bounded re-roll. When riff and melody clash, the Arranger picks one legal edit from a menu code builds, and code decides who yields. The Orchestra adds symphonic colour.'),
)


def s_step(n: int, pattern: str, title: str, pain: str, decision: str, tradeoff: str, notes: str) -> str:
    """One build step: the graph as it stood after it (new pieces mustard, popped in on click 1),
    over the pain, the decision (click 1) and the trade-off (click 2)."""
    cards = [("Pain", pain, TERRA, TERRA_TEXT, ""), ("Decision", decision, MUSTARD, INDIGO, ' data-build-in="fade 1"'),
             ("Trade-off", tradeoff, SKY, SKY_TEXT, ' data-build-in="fade 2"')]
    boxes = [f'<div{bld} style="position:absolute;left:{128 + i * 568}px;top:776px;width:528px;background:{CARD};'
             f'border:2px solid {LINE};border-top:10px solid {accent};border-radius:16px;padding:18px 24px;display:flex;'
             f'flex-direction:column;gap:6px">{p(head, LABEL, ink, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")}'
             f'{p(text, 36, INK, ";line-height:1.2")}</div>' for i, (head, text, accent, ink, bld) in enumerate(cards)]
    inner = [eyebrow(f"Act 1 · step {n} of 11 · {pattern}"), h2(title), *graph(n), *boxes]
    return section(f"step{n}", inner, notes + " CLICK 1: the new piece joins the graph, with the decision. CLICK 2: the trade-off.", gap=20)




# ---- act 1: how the band grew, in five beats (Sujit, 2026-10-19: tell the evolution again, compressed) ----
# Each beat is one or more of the old build steps; its new pieces light up together on the graph, and the
# pattern card(s) it reached for follow it. Plain words on the slide; the story in the notes.
# (id, first step, last step, pattern, title, pain, decision, trade-off, notes)
GROWTH: Final = (
    ("grow1", 3, 3, "self-correction from code", "The rules moved into code",
     "The model played wrong notes, and nothing caught them.",
     "The raga's rules become data. Code checks every note and sends a mistake back.",
     "Someone has to get the rules right, from real sources.",
     "The first real decision came before any agent: the rules leave the prompt and become data plus a check "
     "in code, the same data every later agent reads, each raga verified against two Hindustani sources. Note "
     "the graph: no agent yet, only code."),
    ("grow2", 4, 4, "prompt chaining", "A front door that invents nothing",
     "Ask for “something angry” and the model quietly picked the subgenre and the tempo for you.",
     "An Interpreter turns the request into a brief, and leaves everything you didn't say open.",
     "One more call. No silent creative choices.",
     "Free text needs a front door. The first cut chose the subgenre and the tempo when you didn't say, a "
     "creative decision hiding at intake. Now the model extracts only what was said, code keeps only supported "
     "values, and everything unsaid stays open for the composers."),
    ("grow3", 5, 6, "sectioning", "A plan, and a worker for each part",
     "Nobody owned the song.",
     "Two composers agree a plan; one agent writes the sitar, one the riff. Bass and drums are code.",
     "More calls, and each part is written on its own.",
     "Pandit leans tradition, Riffsmith leans metal; they argue one chart, and a worker fills in each part. "
     "Bass and drums follow the riff in metal, so they are code, not agents: split by decision, not by "
     "instrument."),
    ("grow4", 7, 7, "tool use · evaluator–optimiser", "Two critics: is it correct, is it good?",
     "Correct notes, lifeless music, and nobody said why.",
     "One critic checks the rules with a tool. One judges whether it sounds like the raga.",
     "Two more calls, and taste is still an opinion.",
     "Correct is a fact, so code owns it: Ustad calls the checker as a tool. Good is not checkable, so Rasik "
     "judges against a fixed rubric grounded in the raga's own phrases. Their notes go back to the composers."),
    ("grow5", 8, 8, "debate · predefined workflow", "A referee, and one fixed path",
     "The critics disagreed, and nobody decided.",
     "A Conductor rules between them. Code runs the order and stops at a round limit.",
     "Less freedom for the agents. Every run ends.",
     "The critics argue, a Conductor referees, and the whole pipeline becomes one CrewAI Flow: code decides who "
     "works next and when to stop, never the agents. Act 2 comes back to this choice: a fixed workflow or an "
     "autonomous agent."),
    ("grow6", 9, 9, "LLM-as-judge", "A third judge, for the song",
     "One critic judged two things: does it sound like the raga, and is it a good song?",
     "A Producer judges the song from the score and what code measures. Rasik keeps the raga.",
     "One more judge to keep honest.",
     "Three judges, three questions. Ustad: is it correct, every note legal in the raga (code can check that). "
     "Rasik: does it sound like this raga, its signature phrase, its idiom, its mood. The Producer: is it a good "
     "song, the structure, the dynamics, whether the climax lands and the hook comes back, read from the whole "
     "score and from numbers code measures (the energy curve, how often the hook returns, how much the riff and "
     "the sitar overlap). It ignores the raga entirely. Rasik had been doing both jobs, and a piece can be "
     "perfectly raga-like and still a dull song. It also gave the debate real sides: Rasik for the raga, the "
     "Producer for the song, where before Ustad had argued a fact."),
    ("grow7", 10, 11, "blackboard", "The band starts listening",
     "Every part was good alone, and it didn't sound like a band.",
     "Sitar and riff share one canvas. Checks for 'too light'. An Arranger fixes clashes.",
     "More passes, more parts to tune.",
     "On the shared canvas the leader proposes and the follower answers what it actually hears. Listening "
     "notes become checks a part must pass; when riff and melody clash, the Arranger picks one fix from a "
     "menu code builds. Count the band now: eleven agents."),
)


def s_grow(sid: str, since: int, step: int, pattern: str, title: str, pain: str, decision: str, tradeoff: str,
           notes: str) -> str:
    """One growth beat: the graph after `step`, everything added since `since` lit (popped in on
    click 1), over the pain, the decision (click 1) and the trade-off (click 2)."""
    beat = int(sid[-1])
    cards = [("Pain", pain, TERRA, TERRA_TEXT, ""), ("Decision", decision, MUSTARD, INDIGO, ' data-build-in="fade 1"'),
             ("Trade-off", tradeoff, SKY, SKY_TEXT, ' data-build-in="fade 2"')]
    boxes = [f'<div{bld} style="position:absolute;left:{128 + i * 568}px;top:776px;width:528px;background:{CARD};'
             f'border:2px solid {LINE};border-top:10px solid {accent};border-radius:16px;padding:18px 24px;display:flex;'
             f'flex-direction:column;gap:6px">{p(head, LABEL, ink, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")}'
             f'{p(text, 34, INK, ";line-height:1.2")}</div>' for i, (head, text, accent, ink, bld) in enumerate(cards)]
    inner = [eyebrow(f"Act 1 · how the band grew · {beat} of {len(GROWTH)} · {pattern}"), h2(title), *graph(step, since), *boxes]
    return section(sid, inner, notes + " CLICK 1: the new pieces join the graph, with the decision. CLICK 2: the trade-off.", gap=20)

# ---- act 1 (today): the band as it runs now, and each stage's decision ----------------------------
# The talk opens on the system that works and tours it stage by stage, each stage showing what we tried
# instead and why it lost (Sujit, 2026-10-19); the growth story moved to the annex.
# The workflow as it runs (Bhairav, trace fb08fb641163: 13 calls to the judge; the notes debate ~7 more):
# a snake across two rows, the judge's decision point with its one bounded loop back, the debate's
# blind gate, and every role's calls as chips. (x, y, w) on the 1920 x 1080 canvas.
ROW1, ROW2, ROW_H = 282, 642, 276


def _box(x: int, y: int, w: int, inner: str, accent: str = LINE) -> str:
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{ROW_H}px;background:{CARD};'
            f'border:2px solid {LINE};border-top:8px solid {accent};border-radius:16px;padding:14px 16px;'
            f'display:flex;flex-direction:column;align-items:center;justify-content:start;gap:4px">{inner}</div>')


def _role(names: tuple[str, ...], title: str, what: str, calls: str, scale: float = 1.6) -> str:
    pics = "".join(persona(n, scale) for n in names)
    return (f'<div style="display:flex;align-items:end;gap:12px;height:{round(64 * scale)}px">{pics}'
            f'{chip(calls, MUSTARD, INDIGO)}</div>'
            f'<p style="font-size:36px;font-weight:800;color:{INDIGO};text-align:center;line-height:1.1;margin-top:6px">{title}</p>'
            f'<p style="font-size:32px;color:{MUTED};text-align:center;line-height:1.15">{what}</p>')


def _arrows() -> str:
    def line(x1, y1, x2, y2, color=MUTED, dash=""):
        dx, dy = x2 - x1, y2 - y1
        n = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / n, dy / n
        head = (f'M{x2 - 18 * ux + 12 * uy:.0f} {y2 - 18 * uy - 12 * ux:.0f} L{x2} {y2} '
                f'L{x2 - 18 * ux - 12 * uy:.0f} {y2 - 18 * uy + 12 * ux:.0f}')
        return (f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="6" stroke-linecap="round" {dash}/>'
                f'<path d="{head}" fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>')
    mid1, mid2 = ROW1 + ROW_H // 2, ROW2 + ROW_H // 2
    body = (line(372, mid1, 432, mid1) + line(1032, mid1, 1092, mid1) + line(1426, mid1, 1486, mid1)
            + line(1640, ROW1 + ROW_H + 4, 1640, ROW2 - 6)
            + line(1092, mid2, 1062, mid2) + line(938, mid2, 812, mid2)
            + line(432, mid2, 372, mid2)
            + line(1000, mid2 - 58, 1000, ROW1 + ROW_H + 6, TERRA, 'stroke-dasharray="4 14"')
            + f'<polygon points="1000,{mid2 - 58} 1058,{mid2} 1000,{mid2 + 58} 942,{mid2}" fill="{CARD}" '
              f'stroke="{TERRA}" stroke-width="7" stroke-linejoin="round"/>'
            + V.text(1000, mid2 + 12, "?", 44, TERRA, 800, "middle")
            + V.text(875, mid2 - 20, "accept", 32, MUTED, 800, "middle")
            + V.text(980, ROW1 + ROW_H + 50, "one fix, ≤1 round, kept only if it wins both ways", 32, TERRA, 800, "end"))
    return (f'<svg aria-label="workflow arrows" style="position:absolute;left:0px;top:0px;width:1920px;height:1080px" '
            f'viewBox="0 0 1920 1080">{body}</svg>')


CODE_DOES: Final = ("raga facts and legality", "form and length", "bass and drums", "blind checks", "the render")


def s_today() -> str:
    chain = "seed → gat → alap, taan, outro"
    def writer(sprite: str, name: str, calls: str, what: str) -> str:
        return (f'<div style="display:flex;align-items:center;gap:14px">{persona(sprite, 1.2)}'
                f'<div style="display:flex;flex-direction:column;gap:0px"><div style="display:flex;gap:12px;align-items:center">'
                f'<p style="font-size:36px;font-weight:800;color:{INDIGO};line-height:1.1">{name}</p>{chip(calls, MUSTARD, INDIGO)}</div>'
                f'<p style="font-size:32px;color:{MUTED};line-height:1.15">{what}</p></div></div>')
    composer = (writer("composer", "Pandit", "1 call", "the seed: plan, riff, hook's idea")
                + writer("lead", "Lead", "3–4 calls", "the gat, then alap, taan, outro")
                + f'<p style="font-size:32px;color:{SKY_TEXT};font-weight:700">the last three at once; all checked</p>')
    code_box = (f'<div style="display:flex;align-items:center;gap:12px;height:102px">{V.braces_check(120, 98)}'
                f'{chip("0 calls", SKY, INDIGO)}</div>'
                f'<p style="font-size:36px;font-weight:800;color:{SKY_TEXT};text-align:center;line-height:1.1;margin-top:6px">Code</p>'
                f'<p style="font-size:32px;color:{MUTED};text-align:center;line-height:1.15">drums, checks, assembly</p>')
    render = (f'<div style="display:flex;align-items:center;height:102px">{V.wave(200, 90)}</div>'
              f'<p style="font-size:36px;font-weight:800;color:{INDIGO};text-align:center;line-height:1.1">The song</p>'
              f'<p style="font-size:32px;color:{MUTED};text-align:center;line-height:1.15">rendered</p>')
    boxes = [
        _box(128, ROW1, 244, _role(("interpreter",), "Interpreter", "reads the request", "1 call")),
        _box(432, ROW1, 600, composer, SKY),
        _box(1092, ROW1, 334, _role(("rhythm",), "Rhythm section", "guitar and bass, written to the sitar", "1 call")),
        _box(1486, ROW1, 306, code_box, SKY),
        _box(1092, ROW2, 700, _role(("rasik", "producer"), "Rasik and Producer",
                                    "judge the same take side by side; the Producer decides", "2 calls")),
        _box(432, ROW2, 380, _role(("lead", "riff"), "Sitarist ⇄ Guitarist", "on a concern: argue the notes",
                                   "~7 calls")),
        _box(128, ROW2, 244, render),
    ]
    inner = [eyebrow("Act 1 · the band today"), h2("One workflow: six agents, plus a debate when needed"), _arrows(), *boxes]
    return section("today", inner, (
        "One workflow, read it like a song being made. The Interpreter turns your sentence into a brief. Pandit "
        "writes the seed in one call: the plan, the main riff and the hook's idea. The Lead writes the sitar from it as "
        "a chain of calls, the whole gat, then the alap, taan and outro at once, and code checks every step before the "
        "next. (In code the Lead's calls run under the composer's brief with the seed in view; it is the old Lead loop.) The rhythm section writes guitar and bass after hearing that line; code "
        "derives the drums from the guitar, playing the drum feel the rhythm section chose, and assembles. Rasik and the Producer "
        "judge the same take in parallel, blind to each other; the Producer reads Rasik only if Rasik flags the raga. "
        "The Producer decides: accept, or one fix, which loops back at most once and is kept only if it wins a blind "
        "comparison in both orders. Only when a reviewer named a concern do the sitarist and the guitarist, on two "
        "different models, argue about the notes, and only rewrites that win blind survive. A final code check runs "
        "before anything ships. When nothing needs fixing that is 8 or 9 model calls (1 + 1 + 3 or 4 + 1 + 2, the fourth Lead call for an outro); a fix adds the revision and two comparison calls, a debate several more, and a failed check a retry. Strictly, by Anthropic's definition, this is a workflow, not an agent: "
        "code decides what happens next at every step. That was the point. We never handed a model the whole workflow; "
        "inside one step, the one agentic version that won cost three times the minutes."), gap=26)


# Each stage's decision: today's owner, and what we tried instead (characters, then why it lost).
DECISIONS: Final[dict[str, dict]] = {
    "composer": {
        "stage": 3, "title": "One owner writes the music",
        "today": (("composer",), "Pandit, in a chain", "seed, gat, every section in turn; code checks each step"),
        "tried": ((("pandit", "riffsmith"), "Two composers arguing the form", "a negotiated chart, nobody's idea"),
                  (("lead", "riff"), "Lead and riff written apart", "a collage, not one idea"),
                  (("lead", "riff"), "Equals on a shared canvas", "a compromise, not a song"),
                  (("composer",), "A listening tool for the composer", "it fixed what the tool showed, and got worse")),
        "notes": ("The riff, the hook and the form are one idea, so one agent owns them, writing in a chain of calls "
                  "with code checking every step. We got here by trying the alternatives: two composers negotiating the "
                  "form, separate lead and riff agents, a peer studio session, and a tool that let the composer hear "
                  "its draft. The verdicts follow."),
    },
    "rhythm": {
        "stage": 4, "title": "The guitar is written after hearing the sitar",
        "today": (("rhythm",), "One rhythm section", "guitar and bass for the whole piece, reading the finished sitar line"),
        "tried": ((("riff",), "A riff agent, in parallel", "it ground against the sitar's held notes"),
                  (("arranger",), "An Arranger fixing clashes later", "patched symptoms; deleted"),
                  (("drums",), "Agents for bass and drums", "derivable from the riff, so code"),
                  (("riff",), "A riff checker's budgets", "rejected our best riff; now a measurement")),
        "notes": ("The guitar is written after the sitar line exists, seeing it note by note, so it can ring under a held "
                  "Ga instead of fighting it. Bass and drums are derived by code from the guitar. Before this, a parallel "
                  "riff agent clashed with the sitar and an Arranger agent tried to patch the clashes afterwards."),
    },
    "judge": {
        "stage": 5, "title": "One judge, and a draft it has to beat",
        "today": (("producer", "rasik"), "One judge, one adviser", "judging apart; the Producer decides; a fix must win blind, twice"),
        "tried": ((("ustad",), "An LLM legality critic", "code already knew the answer"),
                  (("conductor",), "A referee for a critics' debate", "each turn rewrote half the music"),
                  (("producer",), "A judge revising every draft", "14 of 14, and the first draft was better"),
                  (("producer",), "A judge reading the adviser first", "it copied the adviser's plans")),
        "notes": ("Legality is a fact, so code decides it. Taste needs one judge with authority, and that judge has to be "
                  "kept honest: it accepts by default, and any fix it asks for must beat the draft in a comparison "
                  "asked in both orders. Each alternative here failed for a measured reason."),
    },
    "debate": {
        "stage": 6, "title": "Two models argue about the notes",
        "today": (("lead", "riff"), "Sitarist ⇄ guitarist", "each rewrites notes of its own part; a blind check keeps winners"),
        "tried": ((("rasik", "producer"), "Critics debating, refereed", "theatre: opinions already on the table"),
                  (("composer", "composer"), "Two vendors debating seeds", "seven seeds, one piece"),
                  (("composer",), "Two composers debating a head", "the measurements did the work alone"),
                  (("lead", "riff"), "A band with volume knobs", "every change subtracted; hollow")),
        "notes": ("Debate earned its place only on the fifth design: each player owns a part, they argue about notes, "
                  "the second player is a different model, and a blind check keeps only the rewrites that win. The four "
                  "before it failed for the reasons on the right."),
    },
}


# Why seven seeds were one piece (the motif experiment, out/motif_ab_20261018_230119): the prompt funnelled
# every composer onto the same cell before any debate began.
FUNNEL: Final = (("Darbari's facts all end on g m R S", 760), ("the seed picks that cell", 640),
                 ("“derive the head from it”", 520), ("+ the stroke line to play", 400))


def s_funnel() -> str:
    rows, y = "", 0
    for label, w in FUNNEL:
        x = (760 - w) / 2 + 4
        rows += (f'<rect x="{x:.0f}" y="{y + 3}" width="{w - 8}" height="80" rx="14" fill="{CARD}" stroke="{TERRA}" stroke-width="5"/>'
                 + V.text(380, y + 54, label, 34, INDIGO, 800, "middle"))
        y += 104
    rows += (f'<path d="M380 {y - 14} L380 {y + 30}" stroke="{TERRA}" stroke-width="7" stroke-linecap="round"/>'
             f'<path d="M364 {y + 14} L380 {y + 34} L396 {y + 14}" fill="none" stroke="{TERRA}" stroke-width="7" stroke-linecap="round"/>'
             + V.text(380, y + 92, "one head, seven times", 40, TERRA, 800, "middle"))
    funnel = V.svg(760, y + 110, rows, "a prompt funnelling every composer onto the same cell")
    bars = V.hbars([("guided", 82, TERRA), ("motif freed", 54, SKY), ("rhythm, both", 89, MUTED)], w=860, rh=110)
    right = (f'<div style="flex:1;display:flex;flex-direction:column;gap:18px">'
             + p("How alike the heads were", 40, INDIGO, ";font-weight:800") + bars
             + p("Freed to choose its own motif, each composer wrote a different melody. The rhythm didn't move: "
                 "the stroke grid still decided it.", BODY) + "</div>")
    inner = [eyebrow("Act 2 · stage 6 · why seven seeds were one piece"), h2("The prompt decided before the debate began"),
             row(f'<div style="width:760px">{funnel}</div>', right, gap=48, align="start"),
             p("Two minds can't diverge if the prompt already chose the answer.", 44, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("funnel", inner, (
        "The cross-model debate's seven seeds, from Gemini and OpenAI, all wrote one piece. Same model was only half "
        "of it; the other half was our prompt. Darbari's pakad, avaroha and chalan all close on g m R S, every seed "
        "picked that cell, and the head prompt then said: derive the mukhada from it, and play this stroke line. So "
        "we ran eight heads, half handed the cell and stroke line, half told to define their own motif. Guided heads "
        "were 82% alike; freed, 54%. The rhythm stayed 89% alike either way, because the Masitkhani stroke grid, which "
        "is the form's own knowledge, still fixed it. All eight were correct Darbari. A debate is only as diverse as "
        "the prompts it starts from."), gap=24)


TWO_WAYS: Final = ("workflow", "selfcorrect", "react", "evaluator", "debate", "collaboration", "orchestrator", "hitl")


def s_two_ways() -> str:
    """Every pattern as we built it (code decides what happens next) and as an agent (the model does)."""
    head = (f'<div style="display:grid;grid-template-columns:420px 1fr 1fr;gap:0px 28px;padding:0px 6px 10px">'
            + p("The pattern", 32, MUTED, ";font-weight:800") + p("As an agent, the model decides…", 32, MUTED, ";font-weight:800")
            + p("What it costs, and what we saw", 32, MUTED, ";font-weight:800") + "</div>")
    rows = "".join(
        f'<div style="display:grid;grid-template-columns:420px 1fr 1fr;gap:0px 28px;align-items:center;'
        f'border-top:2px solid {LINE};padding:10px 6px">'
        + p(PATTERNS[k].name, 34, INDIGO, ";font-weight:800;line-height:1.15")
        + p(AGENTIC[k][0], 32, INK, ";line-height:1.2")
        + p(AGENTIC[k][1], 32, SKY_TEXT if k == "selfcorrect" else TERRA_TEXT,
            ";line-height:1.2" + (";font-weight:800" if k == "selfcorrect" else "")) + "</div>"
        for k in TWO_WAYS)
    inner = [eyebrow("Act 2 · every pattern, two ways"), h2("Each pattern could have been an agent"),
             f'<div style="display:flex;flex-direction:column">{head}{rows}</div>',
             p("Autonomy over the process paid off once, at three times the time.", 44, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700;margin-top:18px")]
    return section("two-ways", inner, (
        "Close the tour on the question every agentic talk invites: why not make each of these a real agent, where "
        "the model decides what happens next? Every row is a version we either built or measured close enough to "
        "know. Read down the right column: the autonomy over process cost us, almost every time. The one exception "
        "is today's agentic Pandit, which sounded better and took three times as long. So the rule is not 'never "
        "agents'; it is 'give a model autonomy where it pays for itself, and measure to find out where that is.'"), gap=22)


def s_decision(key: str) -> str:
    d = DECISIONS[key]
    names, who, how = d["today"]
    today = card(p("Today", 40, SKY_TEXT, ";font-weight:800")
                 + f'<div style="display:flex;align-items:end;justify-content:center;gap:6px;height:230px">'
                   f'{"".join(persona(n, 3.4) for n in names)}</div>'
                 + p(who, 44, INDIGO, f";font-family:{SERIF};font-weight:700;text-align:center;line-height:1.15")
                 + p(how, LABEL, MUTED, ";text-align:center;line-height:1.25"),
                 SKY, flex="flex:4", gap=14)
    rows_ = "".join(
        f'<div style="display:flex;gap:20px;align-items:center;border-top:2px solid {LINE};padding:12px 0px">'
        f'<div style="width:150px;display:flex;justify-content:center;gap:2px">'
        f'{"".join(persona(n, 1.35, ";opacity:0.45") for n in ns)}</div>'
        f'<div style="flex:1;display:flex;flex-direction:column;gap:2px">{p(name, 36, INK, ";font-weight:800")}'
        f'{p("✗ " + why, 32, TERRA_TEXT)}</div></div>' for ns, name, why in d["tried"])
    tried = card(p("Tried instead", 40, TERRA_TEXT, ";font-weight:800") + rows_, TERRA, flex="flex:6", gap=4)
    inner = [eyebrow(f"Act 2 · stage {d['stage']}"), h2(d["title"]), row(today, tried, gap=32)]
    return section(f"dec-{key}", inner, d["notes"], gap=26)


# ---- act 1: growing to eleven agents ----------------------------------------------------------
def s_act1() -> str:
    return divider("act1", 1, "The first band", "It grew to eleven agents. Then a prompt we had never measured beat it.",
                   "5:00. Say the mistake early: we built eleven agents before measuring one plain prompt. Show the "
                   "growth in one build, then the comparison that challenged it, around minute eight.")


def s_first() -> str:
    def lane(icon: str, w: int, h: int, segs: list[tuple[float, float]], c: str) -> str:
        return row(f'<div style="width:170px;display:flex;justify-content:center">'
                   f'<img src="{SPRITES[icon]}" alt="{icon}" style="width:{w}px;height:{h}px;object-fit:contain"></div>',
                   V.tracks([("", segs, c)], 520, 70), gap=16, align="center")
    one = (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:22px">'
           + p("One prompt", 52, INDIGO, f";font-family:{SERIF};font-weight:600")
           + row(V.bubble(220, 180), V.arrow(), V.wave(260, 140), f'<p style="font-family:{SERIF};font-size:140px;font-weight:700;color:{MUSTARD}">?</p>', gap=12, align="center")
           + p("We assumed it couldn't work, and never measured it.", BIG, TERRA_TEXT, f";font-family:{SERIF};font-weight:600") + "</div>")
    many = (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:16px">'
            + p("A prompt per instrument", 52, INDIGO, f";font-family:{SERIF};font-weight:600")
            + lane("sitar", 160, 48, [(0.0, 0.3), (0.42, 0.25), (0.8, 0.2)], SKY)
            + lane("guitar", 128, 48, [(0.12, 0.38), (0.6, 0.35)], TERRA)
            + lane("drums", 93, 60, [(0.0, 0.18), (0.25, 0.18), (0.5, 0.5)], PURPLE)
            + p("Nobody listens to anybody.", BIG, TERRA_TEXT, f";font-family:{SERIF};font-weight:600") + "</div>")
    inner = [eyebrow("Act 1 · the obvious designs"), h2("The two moves everyone makes"), row(one, many, gap=60)]
    return section("first", inner, "The two moves everyone makes. Say the mistake out loud: we built eleven agents before we measured one plain prompt. We assumed one call would be plausible and uncheckable. One prompt per instrument: every part gets attention, but the parts never listen to each other, nobody owns the form, and the design heads for fifteen agents. We skipped straight past both: our day-one design already put two composers in front of the instruments, writing the chart they all played from. Even so, the instruments never heard each other. Remember this split; Act 2 comes back to it.", gap=36)


# ---- act 1 opens on the first design question: how to split the work (Sujit, 2026-10-20) --------
def _bullet(mark: str, text: str, color: str, size: int = 38) -> str:
    return p(f"{mark} {text}", size, INK, f";border-left:6px solid {color};padding-left:18px;line-height:1.25")


def s_split_instrument() -> str:
    def lane(icon: str, w: int, h: int, segs: list[tuple[float, float]], c: str) -> str:
        return row(f'<div style="width:150px;display:flex;justify-content:center">'
                   f'<img src="{SPRITES[icon]}" alt="{icon}" style="width:{w}px;height:{h}px;object-fit:contain"></div>',
                   V.tracks([("", segs, c)], 600, 84), gap=20, align="center")
    lanes = (f'<div style="flex:1;display:flex;flex-direction:column;gap:34px;justify-content:center;margin-top:30px">'
             + lane("sitar", 190, 57, [(0.0, 0.3), (0.42, 0.25), (0.8, 0.2)], SKY)
             + lane("guitar", 152, 57, [(0.12, 0.38), (0.6, 0.35)], TERRA)
             + lane("drums", 112, 72, [(0.0, 0.18), (0.25, 0.18), (0.5, 0.5)], PURPLE)
             + lane("tabla", 112, 72, [(0.05, 0.2), (0.4, 0.15), (0.7, 0.3)], MUSTARD)
             + p("an agent per part, each writing alone", 34, MUTED, ";text-align:center") + "</div>")
    problems = (f'<div data-build-in="fade 1" style="flex:1;display:flex;flex-direction:column;gap:34px;justify-content:center;margin-top:30px">'
                + _bullet("✗", "Nobody listens: each part is written without hearing the others.", TERRA, 42)
                + _bullet("✗", "Nobody owns the song: no one decides the form, the hook or the climax.", TERRA, 42)
                + _bullet("✗", "Every agent is another model call: more cost, more waiting, more to fail.", TERRA, 42) + "</div>")
    inner = [eyebrow("Act 1 · how to split the work"), h2("One agent per instrument?"), row(lanes, problems, gap=56)]
    return section("split-instrument", inner, (
        "The first question in any agentic system: how do you split the work? The obvious answer for a band is an "
        "agent per instrument, a sitar agent, a guitar agent, a drum agent, a tabla agent. CLICK: why it fails. Each "
        "part gets attention, but none of them hears the others; nobody owns the form, the hook or the climax; and "
        "every agent is a model call, so the design heads for fifteen of them, each one more cost, more latency and "
        "one more way to fail. We never built this; it was the design we argued ourselves out of on day one."), gap=30)


def s_split_role() -> str:
    def group(title: str, names: tuple[str, ...], what: str, accent: str) -> str:
        return card(p(title, 40, INDIGO, f";font-family:{SERIF};font-weight:700")
                    + f'<div style="display:flex;align-items:end;justify-content:center;gap:6px;height:250px">'
                      f'{"".join(persona(n, 3.2 if len(names) < 3 else 2.4) for n in names)}</div>'
                    + p(what, 38, INK, ";line-height:1.25;text-align:center"), accent, flex="flex:1", gap=18)
    groups = row(group("Compose", ("pandit", "riffsmith"), "decide the song: form, hook, mood", PURPLE),
                 group("Perform", ("lead", "riff"), "write each part to that plan", SKY),
                 group("Judge", ("ustad", "rasik", "producer"), "is it correct? is it good?", TERRA),
                 group("Decide", ("conductor",), "settle it when the judges disagree", MUSTARD), gap=24)
    inner = [eyebrow("Act 1 · how to split the work"), h2("Split by role: who decides what"), groups,
             p("A split by role. But does every role need its own agent?", 42, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("split-role", inner, (
        "So we split by role, the way a real band and a studio do: someone composes, players perform, someone "
        "judges, and someone settles the argument. Now the song has owners: the composers decide the form, the "
        "players write to one plan, the critics catch what the writers miss, and a referee breaks ties. These are "
        "the characters of our first band; keep the composers in mind, because the investigation comes back to "
        "how they split the work."), gap=30)


def s_split_code() -> str:
    def item(pic: str, text: str) -> str:
        return (f'<div style="display:flex;align-items:center;gap:22px;min-height:110px">'
                f'<div style="flex:none;width:120px;display:flex;justify-content:center">{pic}</div>'
                f'{p(text, 40, INK, ";line-height:1.25")}</div>')
    agents = card(p("An agent: a judgment to make", 40, SKY_TEXT, ";font-weight:800")
                  + item(persona("lead", 2.4), "the sitar line: which phrase, which ornament")
                  + item(persona("riff", 2.4), "the riff: its rhythm, its weight"),
                  SKY, flex="flex:1", gap=20)
    code = card(p("Code: the answer follows", 40, INDIGO, ";font-weight:800")
                + item(V.braces_check(96, 80), "the bass follows the riff's roots")
                + item(V.braces_check(96, 80), "the drum beats lock to the riff's accents")
                + item(V.braces_check(96, 80), "the tabla plays the tala; the drone holds Sa"),
                INDIGO, flex="flex:1", gap=20)
    code = code.replace('<div style="flex:1;', '<div data-build-in="fade 1" style="flex:1;', 1)
    inner = [eyebrow("Act 1 · how to split the work"), h2("Not everything needs an agent"), row(agents, code, gap=32),
             p("Use an agent where there's a judgment to make. Use code where the answer follows.", 42, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("split-code", inner, (
        "The pivot, and the answer to \"why not an agent for the bass and the drums?\": in metal the bass and the "
        "kick follow the riff. That is derivable, not a decision, and every agent is a model call, so the wrong "
        "axis costs time, money and failure surface. CLICK: what code does. Deterministic doesn't mean dumb: the "
        "drum beats lock to the riff's onsets, the feel changes per section, the tabla plays the tala's own cycle. The "
        "model makes the musical decisions; code supplies what follows from them. Next: the band we built from "
        "these choices, growing one fix at a time."), gap=30)


def s_knowledge() -> str:
    b_ = RAGAS["bhairav"]
    lines = ['"bhairav": {',
             f'&#160;&#160;"allowed": {json.dumps(b_["allowed"]).replace(" ", "")},',
             '&#160;&#160;"vadi": "d", "samvadi": "r",',
             '&#160;&#160;"andolan": ["r", "d"],  # these sway',
             '&#160;&#160;"sources": ["Tanarang", ...],',
             '}']
    right = card(p(f"{b('One source of truth.')} The validator, every check and every agent prompt read the same data.", BODY)
                 + p(f"{b('Two sources per fact.')} Online raga data is often wrong; disagreements are flagged in the data.", BODY)
                 + p(f"{b('Tests check the facts themselves.')}", BODY), INDIGO, flex="flex:5")
    inner = [eyebrow("Act 1 · the first real decision"), h2("The rules moved out of the prompt and into code"),
             row(f'<div style="flex:7;display:flex;flex-direction:column">{code(lines, 30)}</div>', right, gap=32),
             p("Prompts and checks read the same sourced data. Tests check what we encoded, not the music.", BIG, TERRA_TEXT, f";font-family:{SERIF};font-weight:600")]
    return section("knowledge", inner, "The decision that came before any agent: domain facts are data plus a deterministic validator, the same data every later agent reads. A model asked for a raga's notes from memory is sometimes wrong and always confident; a lookup is never either.")


def s_guardrail() -> str:
    lines = ["class UstadNarration(BaseModel):", "&#160;&#160;&#160;&#160;reasoning: str", "&#160;&#160;&#160;&#160;explanation: str",
             f'<span style="color:{TERRA_TEXT}">&#160;&#160;&#160;&#160;# no verdict field</span>']
    inner = [eyebrow("Act 1 · a pattern that survived"), h2("An agent can't declare a piece legal"),
             row(f'<div style="flex:6;display:flex;flex-direction:column">{code(lines, 40)}</div>',
                 card(p("Legality is a fact, so code computes the verdict. The legality agent only explained it, and its output type has no field where a verdict could go.", BODY)
                      + p(f"{b('Even a model that lies cannot pass an illegal piece.')}", BODY), INDIGO, flex="flex:5"), gap=32),
             p("Later we deleted that agent too: narrating a verdict code had already computed added cost and no information.", BODY, MUTED)]
    return section("guardrail", inner, "Encode authority in the type, don't ask the model not to decide. Ustad, our legality critic, called the validator as a tool and could only explain its result. It became redundant once we saw that: the UI now shows the validator's report directly.")


ELEVEN: Final = [("interpreter", "to read requests"), ("pandit", "to own the form"), ("riffsmith", "to argue for metal"),
                  ("lead", "to write the sitar"), ("riff", "to write the guitar"), ("orchestra", "to add colour"),
                  ("ustad", "to check it's legal"), ("rasik", "to judge the raga"), ("producer", "to judge the song"),
                  ("conductor", "to referee"), ("arranger", "to fix clashes")]


def s_eleven() -> str:
    top = row(*(member(n, w, scale=2.8, build=f"pop {i + 1}") for i, (n, w) in enumerate(ELEVEN[:6])), gap=12, align="start")
    bottom = row(*(member(n, w, scale=2.8, build=f"pop {i + 7}") for i, (n, w) in enumerate(ELEVEN[6:])), gap=12, align="start")
    inner = [eyebrow("Act 1 · an agent for every pain"), h2("Eleven agents walked into a band"), top, bottom]
    return section("eleven", inner, "Two minutes; click them on one by one. Each joined to fix a real failure: the Interpreter because free text became an invented brief; Pandit and Riffsmith because nobody owned the form, so two opposed composers argued it; Lead and Riff, one per decision, while bass and drums became code; the Orchestra for colour; Ustad because illegal notes slipped through; Rasik because legal was lifeless; the Producer because Rasik judged raga and song at once; the Conductor because the critics disagreed; the Arranger because a clash meant regenerating a whole part.", gap=22)


# ---- act 2: the turn --------------------------------------------------------------------------
def s_act2() -> str:
    return divider("act2", 2, "The investigation", "Four chapters: two agents or one?, rules, judgment, control. Each one: how the first band did it, what we do now, and how we know.",
                   "About 11:00. Say the shape once, so nobody gets lost: four chapters, and each walks the same four beats: "
                   "how the first band did it and what hurt, what we do now, and how we know. A badge at the top of every "
                   "slide says which band is on screen: the first band or tonight's band. Patterns are named where the story "
                   "needs them; their definition cards are in the annex.")


TURN: Final = json.loads((HERE / "data" / "turn_strokes.json").read_text())   # every guitar stroke, both songs


def _lanes(w: int = 1664, lane_h: int = 92) -> str:
    """Both songs' rhythm-guitar strokes on one minute: a tick per stroke, our climax shaded."""
    beats, gap, top = TURN["beats"], 92, 40
    def x(t: float) -> float:
        return t / beats * w
    c0, c1 = TURN["climax"]
    body = [f'<rect x="{x(c0):.0f}" y="{top - 8}" width="{x(c1) - x(c0):.0f}" height="{2 * lane_h + gap + 16}" '
            f'rx="10" fill="{MUSTARD}" opacity="0.16"/>',
            V.text(x(c0) + 10, top - 14, "the climax", 30, MUSTARD_TEXT, 800, "start")]
    for i, (key, color) in enumerate((("plain", TERRA), ("ours", SKY))):
        y = top + i * (lane_h + gap)
        body.append(f'<rect x="0" y="{y}" width="{w}" height="{lane_h}" rx="8" fill="{LINE}" opacity="0.35"/>')
        body += [f'<rect x="{x(t):.1f}" y="{y + 6}" width="3" height="{lane_h - 12}" fill="{color}"/>' for t in TURN[key]]
    return V.svg(w, 2 * lane_h + gap + top + 8, "".join(body), "every guitar stroke of both songs over one minute",
                 (w, 2 * lane_h + gap + top + 8))


def s_turn() -> str:
    """The doubt, not the proof (Sujit, 2026-10-20: "we don't have to prove it"): the claim scoped to one song,
    then his question. The evidence (stroke lanes, clip TR) lives on the annex slide `turn-evidence`."""
    inner = [eyebrow("Act 1 · the challenge"), h2("Once, one plain prompt beat our riff"),
             p("Was all that complexity worth it, or even needed?", 60, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700;margin-top:40px")]
    return section("turn", inner, (
        "Say, in your own words: one song, raga Bhairav, and the models had moved on since we started building. It made me question everything we'd built; it works fairly well, but was all that complexity worth it? Then: the song you applauded at the start is this one, and on the riff and the climax it lost to one plain "
        "prompt, in one comparison: raga Bhairav, October. The models had moved on since we began building in July (the comparison ran on a newer Flash than the one our rules were tuned on), and our rules had not; Act 2 shows where that bit. The plain prompt's guitar built into "
        "a wall at the climax; ours thinned out exactly there. Don't prove it here (the stroke lanes and the clip are "
        "on the annex slide if asked). Say what we had already spent: months on the riff alone, its own agent, a "
        "texture checker, a chord-voicing pass, chug and palm-mute rendering fixes, an arranger. The narrow claim, and "
        "do not go past it: not better riffs in general and not a better song. When we re-measured on gemini-3.8 "
        "across Bhairav, Yaman and Darbari, our guitar played power chords on 81-100% of its strokes against 21-33% "
        "for the bare call, and outside Bhairav the bare call's guitar mostly copied the sitar (TALK.md 'Correct is "
        "not good'). So this is a doubt, not a verdict. Do NOT let the room conclude 'so write it all in one call': "
        "the band tonight still writes the guitar with a separate agent, and in Act 2 that agent beats the "
        "composer's own riff. Act 2 answers the question on this slide."), justify="center", gap=24)


def s_turn_evidence() -> str:
    """Annex backup for Q&A: the turn's evidence (stroke lanes + clip TR), moved off the main slide."""
    head = lambda t, c: p(t, 40, c, ";font-weight:800")   # noqa: E731
    lanes = (f'<div style="display:flex;flex-direction:column;gap:6px">'
             f'{head("One plain prompt: starts light, and builds into a wall at the climax", TERRA_TEXT)}'
             f'<div style="position:relative">{_lanes()}'
             f'<p style="position:absolute;left:0px;top:150px;font-size:40px;font-weight:800;color:{SKY_TEXT}">'
             f'The song that opened tonight: steady, then thinner where it should hit</p></div></div>')
    inner = [eyebrow("Act 1 · the challenge"), h2("Once, one plain prompt beat our riff"),
             p("One song, raga Bhairav, an older model: every stroke of the guitar.", BODY, MUTED, ";font-style:italic"), lanes,
             p("It made me question everything we'd built.<br>"
               "It works fairly well. But is all that complexity worth it, or even needed?", 40, INK, ";width:1120px;line-height:1.35"),
             clip("TR", 1312, 862, "ours, then the plain prompt")]
    return section("turn-evidence", inner, (
        "Say it: the song you applauded at the start is this one, and on the riff and the climax it lost, in this one comparison. "
        "The callback: the one prompt from the start of Act 1, the one we assumed away and never measured. In October, "
        "on an older Flash model, my ear said a bare prompt's riffs beat ours, so we looked. Each tick is one stroke "
        "of the rhythm guitar across the same one-minute song. The plain prompt starts with light, spaced strokes "
        "and builds into a wall at the climax; ours is steady through the middle and thins out exactly where the "
        "climax should hit, about a tenth of the plain prompt's strokes there. CLICK THE CLIP: four and a half "
        "seconds of our climax, then the same moment of the plain prompt's song, matched for loudness. Then the "
        "honest part: it broke the raga's rules, and our own riff checker, tuned in July, would have rejected that "
        "riff twice. Say what we had already spent: months on the riff alone, its own agent, a texture checker, a chord-voicing pass, chug and palm-mute rendering fixes, an arranger. Then the scope, plainly: this was Bhairav, a raga whose scale metal already owns (it is the neoclassical Phrygian-dominant sound). Across seven plain-prompt songs since, the riff was this good mainly in Bhairav; in the other ragas the guitar mostly copied the sitar, and in Todi its power chords added notes the raga does not have. What it showed us anyway: a riff with its own rhythm, a power chord on every stroke, a climax that grows. The narrow claim, and do not go past it: a stronger riff and climax in one Bhairav song on an older model, not better riffs in general and not a better song. When we re-measured on gemini-3.8 across Bhairav, Yaman and Darbari, our system's guitar played power chords on 81-100% of its strokes against 21-33% for the bare call, and the bare call's guitar mostly copied the sitar (TALK.md 'Correct is not good'). So this slide is a doubt, not a verdict: it made me question whether all that machinery was needed. Do NOT let the room conclude 'so write it all in one call': the band tonight still writes the guitar with a separate agent, and in Act 2 that agent beats the composer's own riff. Act 2 is the answer to the question on this slide."),
        gap=24)


def s_why() -> str:
    """The three causes that changed the music (rechecked 2026-10-20 against TALK.md "Deleting agents" and the
    losing song's trace 480f18b59298). Ustad's narration (a cost, not a sound) moved to the notes."""
    def cell(pic: str, title: str, sub: str) -> str:
        return (f'<div style="display:flex;gap:28px;align-items:center;background:{CARD};border-radius:20px;padding:16px 26px">'
                f'<div style="width:330px;display:flex;justify-content:center;align-items:end;gap:6px">{pic}</div>'
                f'<div style="flex:1;display:flex;flex-direction:column;gap:4px">{p(title, 44, INDIGO, f";font-family:{SERIF};font-weight:600")}'
                f'{p(sub, LABEL, MUTED)}</div></div>')
    split = "".join(persona(n, 1.3) for n in ("pandit", "riffsmith", "lead", "riff"))
    aged = (f'<p style="font-family:{SERIF};font-size:88px;font-weight:700;color:{MUTED};text-decoration:line-through">55%</p>')
    theatre = persona("rasik", 1.7) + f'<p style="font-family:{SERIF};font-size:64px;color:{MUTED}">⇄</p>' + persona("producer", 1.7)
    inner = [eyebrow("Act 2 · measuring why"), h2("What the comparison made us look at"),
             f'<div style="display:flex;flex-direction:column;gap:18px">'
             + cell(split, "The idea had no single home",
                    "the hook was rewritten in each section; the riff answered a draft of the sitar, or none at all")
             + cell(aged, "The rules had aged",
                    "tuned to an older model's mistakes, they turned our riffs into single chugs, hardly a chord")
             + cell(theatre, "The judges kept the weaker song", "two critics re-argued opinions already on the table")
             + "</div>",
             p("Underneath all three: I wanted to try every pattern, so every problem got an agent.", 40,
               TERRA_TEXT, f";font-family:{SERIF};font-weight:700")]
    return section("why", inner, (
        "An afternoon of measurement, and every answer pointed at the design, not at a prompt. These are the three "
        "that changed the music. Say the candid part out loud, after them: I went overboard. I had read about "
        "orchestrators, critics, debates and blackboards, and I wanted to try them all, so each new problem got a new "
        "agent; that is how a band reached eleven. Every agent fixed something real; together they were more "
        "machinery than the music needed. OWNERSHIP, as the losing song's trace (480f18b59298) shows it: Pandit and "
        "Riffsmith wrote the chart in one call each; then the studio session alternated Lead and Riff on a shared "
        "board. Where the sitar led, the riff answered the sitar's draft, and the sitar then rewrote its line after "
        "hearing the riff, so the guitar never heard the line that shipped. Where the guitar led, the riff was written "
        "before any sitar existed. The hook, the riff and the form each had a different author. The fix was not to "
        "merge the riff into the composer: one owner (Pandit) now holds the idea, and a separate guitar writer works "
        "after the sitar is finished. AGED RULES: the riff checker, calibrated in July on a weaker model's busy riffs, "
        "demanded that most of a driving riff be palm-muted chugs on the home note; the riff that lost was 71% single "
        "chugs on Sa, and chords sounded on 15% of its strokes against 100% for the plain prompt. It would have "
        "rejected the plain prompt's riff twice. Say the honest part: the redesign removed that rule and merged the "
        "composers in the same step, so we never separated the two causes; a later blind test (Act 2) separated one. "
        "THE JUDGES: Rasik and the Producer debated opinions already on the table and accepted the weaker song. "
        "Also found that afternoon, smaller for the music: Ustad spent a model call narrating a verdict code had "
        "already computed (a cost, see the four questions later); and the same day, a plan field nobody read (the "
        "anchor) and the user's own words lost in the Interpreter's structured handoff. NEXT: Act 2 takes these causes one chapter at a time."), gap=24)


GONE_TO: Final = {"riffsmith": "→ Pandit", "lead": "→ Pandit", "riff": "→ Rhythm section",
                   "ustad": "→ code", "conductor": "→ a round limit", "arranger": "→ a number"}
KEPT: Final = {"interpreter": "stays", "pandit": "owns the idea", "rasik": "stays", "producer": "stays",
                "orchestra": "symphonic only"}


# The eleven-agent band as each investigation chapter leaves it (the "build, challenge, investigate,
# rebuild" arc, 2026-10-19): one picture carried through Act 2, each chapter's decision changing it.
# agent -> (the chapter that decided it, its tag); chapter 1 ownership, 2 judgment, 3 rules and control.
FATE: Final = {"pandit": (1, "owns the idea"), "riffsmith": (1, "→ Pandit"), "lead": (1, "→ Pandit"), "riff": (1, "→ Rhythm section"),
               "orchestra": (1, "symphonic only"), "arranger": (1, "→ a number"), "conductor": (2, "→ a round limit"),
               "producer": (2, "the one judge"), "rasik": (2, "advises"), "ustad": (3, "→ code"), "interpreter": (3, "stays")}
GONE: Final = {"riffsmith", "lead", "riff", "arranger", "conductor", "ustad"}
BAND_TITLES: Final = {1: "Ownership: one owner for the idea", 2: "Judgment: one judge, and a rule to stop",
                      3: "Eleven became five"}


def s_own_flow() -> str:
    """The ownership chapter's decision as the workflow it changed (Sujit, 2026-10-20): before, one idea
    split across a co-written plan and two workers; after, one owner and a handoff. "After" fades in."""
    def step(pics: str, text: str, ink: str = INK) -> str:
        return (f'<div style="display:flex;align-items:center;gap:18px;background:{PAGE};border-radius:14px;'
                f'padding:8px 18px">{pics}{p(text, 34, ink, ";line-height:1.2")}</div>')
    arrow = p("↓", 44, MUTED, ";text-align:center;line-height:1;margin:2px 0px")
    before = card(p("Before: one idea, split", 40, TERRA_TEXT, ";font-weight:800")
                  + step(persona("pandit", 1.4) + persona("riffsmith", 1.4), "two composers co-write the plan")
                  + arrow
                  + step(persona("lead", 1.4) + persona("riff", 1.4), "the sitar and the riff take turns on a shared board")
                  + arrow
                  + p("each owns half: a compromise", 36, TERRA_TEXT, ";font-weight:800;text-align:center"),
                  TERRA, flex="flex:1", gap=8)
    after = card(p("After: one owner, then a handoff", 40, SKY_TEXT, ";font-weight:800")
                 + step(persona("composer", 1.4), "Pandit owns the idea: the plan, the hook and every sitar note")
                 + arrow
                 + step(persona("rhythm", 1.4), "the Rhythm section writes guitar and bass, hearing every sitar note")
                 + arrow
                 + step(V.braces_check(56, 46), "code adds the drums and assembles")
                 + p("one owner, then a specialist", 36, SKY_TEXT, ";font-weight:800;text-align:center"),
                 SKY, flex="flex:1", gap=8)
    after = after.replace('<div style="flex:1;', '<div data-build-in="fade 1" style="flex:1;', 1)
    inner = [eyebrow("Act 2 · ownership"), h2("One owner took the parts back"),
             row(before, after, gap=32),
             p("One idea needs one owner. Split by information, not by job title.", 40, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("own-flow", inner, (
        "WHERE WE ARE: ownership, Now. The answer to the two questions, drawn as the workflow it changed: the left side recaps the slide before in one glance; the right side, on click, is what we do now. Before: the composers co-wrote the plan, trading "
        "concessions; then, in the studio session, the sitar and the riff took turns on a shared board. They could see "
        "each other's drafts, but each owned half, and nobody owned the whole idea. (On the default path the two were "
        "written apart and code merged them.) The studio session composed tonight's opening piece, so it worked well "
        "enough to perform. CLICK: after. Pandit owns the idea: the plan, the hook and every note of the sitar, with a "
        "main riff as material. The Rhythm section writes guitar and bass after it can hear the finished sitar: a "
        "handoff, not a negotiation; code adds the drums. Then the test that settled who writes the guitar: five recent "
        "songs, the first mukhada rendered twice, once with Pandit's riff under the hook and once with the Rhythm "
        "section's guitar, everything else identical, judged blind by ear. The Rhythm section won three of five; "
        "Pandit's riff lost by being too busy or clashing, because it is written before the sitar exists. So one owner "
        "for the idea, and a separate specialist where the information differs. Callback to Act 1: we split the "
        "first band by role, and a role is a job title; this is where that stops. The rule: split agents where the "
        "information or the judgment differs, never where the job titles do. NEXT: what Pandit actually does today, call by call."), gap=22)


# What Pandit writes, one call at a time (Sujit, 2026-10-20: "add a slide so the audience is clear what the composer
# does; use animations"): a gat-form song map that fills in click by click. Sections in the order of the recent runs.
SONG_MAP: Final = ("alap", "mukhada", "manjha", "mukhada", "antara", "taan", "mukhada", "outro")
CALL_STEPS: Final = (
    ("A request comes in", "Pandit plans the song. The Lead writes every note of the sitar from Pandit's seed."),
    ("1 · The seed call", "Pandit: the plan of the song, the main riff, and the idea of the hook, written together in one answer."),
    ("2 · The gat call", "The Lead: the hook's notes, grown from that idea, then the manjha and antara around it. "
                         "Code repeats the hook, note for note, every time it returns."),
    ("3 · Code checks the hook", "Against the raga's facts. If it misses one, the Lead sees its own draft measured and gets one "
                                 "chance to fix it."),
    ("4 · Three calls at once", "The alap, the taan and the outro, each with its own instructions, written side by side: "
                                "each sees the seed and the gat, but not the others. Code checks every answer."),
    ("5 · The handoff", "The sitar is finished. The Rhythm section writes guitar and bass around it; "
                        "code adds the drums."),
)


def s_composer_calls() -> str:
    """The song map: empty slots, then each click fills what that call wrote (pinned, absolutely placed so
    each layer can fade in on its own click), with one caption card per step replacing the last."""
    x0, y0, w, gap, h = 330, 344, 172, 12, 96
    def at(i: int) -> int:
        return x0 + i * (w + gap)
    def block(i: int, label: str, *, fill: str, ink: str, border: str, build: int | None) -> str:
        b = f' data-build-in="fade {build}"' if build else ""
        return (f'<div{b} style="position:absolute;left:{at(i)}px;top:{y0}px;width:{w}px;height:{h}px;background:{fill};'
                f'border:3px {border};border-radius:14px;display:flex;align-items:center;justify-content:center">'
                f'<p style="font-size:{LABEL}px;font-weight:800;color:{ink}">{label}</p></div>')
    slots = "".join(block(i, "", fill=PAGE, ink=MUTED, border=f"dashed {MUTED}", build=None) for i in range(len(SONG_MAP)))
    labels = "".join(block(i, name, fill=CARD, ink=MUTED, border=f"dashed {MUTED}", build=1) for i, name in enumerate(SONG_MAP))
    gat = "".join(block(i, n, fill=MUSTARD, ink=INDIGO, border=f"solid {MUSTARD}", build=2)
                  for i, n in enumerate(SONG_MAP) if n in ("mukhada", "manjha", "antara"))
    rest = "".join(block(i, n, fill=MUSTARD, ink=INDIGO, border=f"solid {MUSTARD}", build=4)
                   for i, n in enumerate(SONG_MAP) if n in ("alap", "taan", "outro"))
    checks = "".join(f'<div data-build-in="fade 3" style="position:absolute;left:{at(i) + w - 30}px;top:{y0 - 22}px;width:52px;'
                     f'height:52px;border-radius:26px;background:{SKY};display:flex;align-items:center;justify-content:center">'
                     f'<p style="font-size:{LABEL}px;font-weight:800;color:{LIGHT}">✓</p></div>'
                     for i, n in enumerate(SONG_MAP) if n == "mukhada")
    guitar = (f'<div data-build-in="fade 5" style="position:absolute;left:{x0}px;top:{y0 + h + 14}px;width:{at(len(SONG_MAP)) - gap - x0}px;'
              f'height:46px;background:{SKY};border-radius:12px;display:flex;align-items:center;padding:0px 20px">'
              f'<p style="font-size:{LABEL}px;font-weight:800;color:{LIGHT}">guitar and bass: the Rhythm section · drums: code</p></div>')
    sitar_tag = (f'<p data-build-in="fade 2" style="position:absolute;left:{x0}px;top:{y0 - 50}px;font-size:{LABEL}px;'
                 f'font-weight:800;color:{MUSTARD_TEXT}">the sitar: the Lead</p>')
    def who(sprite: str, name: str, top: int, build: int) -> str:
        return (f'<div data-build-in="fade {build}" style="position:absolute;left:128px;top:{top}px;width:170px;display:flex;'
                f'flex-direction:column;align-items:center;gap:2px">{persona(sprite, 1.5)}'
                f'<p style="font-size:{LABEL}px;font-weight:800;color:{INDIGO}">{name}</p></div>')
    pandit = who("lead", "Lead", y0 - 40, 2) + who("composer", "Pandit", y0 + h + 30, 1)
    seed = "".join(
        f'<div data-build-in="fade 1" style="position:absolute;left:{x0 + k * 372}px;top:{y0 + h + 82}px;width:350px;height:70px;'
        f'background:{CARD};border:3px solid {color};border-radius:14px;display:flex;align-items:center;justify-content:center">'
        f'<p style="font-size:{LABEL}px;font-weight:800;color:{ink}">{text}</p></div>'
        for k, (text, color, ink) in enumerate((("the plan", INDIGO, INDIGO), ("the main riff", TERRA, TERRA_TEXT),
                                                 ("the hook's idea", MUSTARD, MUSTARD_TEXT))))
    seed_tag = (f'<p data-build-in="fade 1" style="position:absolute;left:{x0 + 3 * 372}px;top:{y0 + h + 76}px;width:340px;'
                f'font-size:{LABEL}px;line-height:1.15;font-weight:800;color:{MUTED}">← the seed, carried into every call</p>')

    def caption(k: int, title: str, text: str) -> str:
        bi = f' data-build-in="fade {k}"' if k else ""
        bo = f' data-build-out="fade {k + 1}"' if k < len(CALL_STEPS) - 1 else ""
        return (f'<div{bi}{bo} style="position:absolute;left:128px;top:690px;width:1664px;height:230px;background:{CARD};'
                f'border:2px solid {LINE};border-top:10px solid {MUSTARD};border-radius:16px;padding:20px 30px;'
                f'display:flex;flex-direction:column;gap:10px">{p(title, 44, INDIGO, f";font-family:{SERIF};font-weight:700")}'
                f'{p(text, BODY, INK, ";line-height:1.3")}</div>')
    captions = [caption(k, t, x) for k, (t, x) in enumerate(CALL_STEPS)]
    chips = (f'<div style="position:absolute;top:88px;right:128px;display:flex;gap:16px;align-items:center">'
             f'{chip("Prompt chaining", INDIGO)}{chip("+ Parallelisation", PURPLE)}</div>')   # no "Pattern" chip: the chapter tracker needs the room
    inner = [eyebrow("Act 2 · two agents or one? · now"), h2("Pandit plans; the Lead writes in a chain"),
             chips, pandit, slots, labels, sitar_tag, gat, checks, rest, seed, seed_tag, guitar, *captions]
    return section("composer-calls", inner, (
        "WHERE WE ARE: the rebuilt band, zooming into the first box of tonight's workflow. Five clicks: who writes what today. Pandit makes ONE call, the seed; the Lead writes the sitar from it. Say plainly: the section calls are the old Lead loop, now with the seed in view (in code they run under the composer\'s brief). Two engineering fixes live here, both about state. The hook is committed once and code repeats it: in the old band each mukhada section wrote it again, and the second came back with a note missing (trace 480f18b59298). And the guitar is handed the finished sitar: blind, a guitar written that way fit the hook better than Pandit\'s own riff in 3 songs of 5 (a lean; it does not show a separate agent is needed). The map is a "
        "gat-form song in the order our recent runs used. CLICK 1, the seed call: one answer holds the plan (the form, "
        "each section's length and chords, how the energy moves), the main riff, one cycle long, and the idea of the "
        "hook: the note on every sam, the core cell, the right hand's strokes. CLICK 2, the gat call: the hook's notes, "
        "written from that idea with full attention, plus the manjha and antara that share its motif; code repeats the "
        "hook verbatim at every return. CLICK 3: code checks the hook (hard rules, then the raga's measured facts: the "
        "register it should live in, a signature phrase); a miss earns one revision, kept only if it fixes the miss "
        "without breaking anything else. CLICK 4: the remaining sections are written AT ONCE, three calls side by "
        "side (parallelisation, the second pattern on this slide): each has its own brief and sees the seed and the gat, "
        "but not the others. The alap knows the hook it prepares, the taan the note it must land on; the alap cannot "
        "hear the taan. That is the trade: about a minute saved a song, for sections that do not hear each other "
        "(RMA_PARALLEL_SECTIONS; 0 restores one after another). Code checks each one, and a rejected answer goes back "
        "once with its exact fault and the rejected draft. "
        "CLICK 5: the handoff. The Lead wrote every note of the sitar; the Rhythm section writes guitar and bass after "
        "it can see all of them, with Pandit's riff as material; code derives the drums. In the song form, the seed "
        "writes the finished hook instead of its idea, and there is no gat call. NEXT: the plain prompt, measured against this band."), gap=22)


# ---- the investigation's new evidence slides (2026-10-20 restructure: failure -> mechanism -> comparison
# -> result -> decision; plain lessons on the slide, the numbers in the notes) -----------------------------
def _side(title: str, lines: tuple[tuple[str, str], ...], ink: str, accent: str, *, build: str = "") -> str:
    """One column of a before/after: a title and lines, each with an optional picture."""
    rows_ = "".join(f'<div style="display:flex;align-items:center;gap:18px;background:{PAGE};border-radius:14px;'
                    f'padding:10px 18px">{pic}{p(text, 36, INK, ";line-height:1.22")}</div>' for pic, text in lines)
    body = card(p(title, 40, ink, ";font-weight:800") + rows_, accent, flex="flex:1", gap=10)
    return body.replace('<div style="flex:1;', f'<div data-build-in="{build}" style="flex:1;', 1) if build else body


def _contrast(sid: str, eyebrow_text: str, title: str, before: tuple, after: tuple, takeaway: str, notes: str,
              extra: tuple[str, ...] = ()) -> str:
    """The investigation's evidence slide: what failed, what we do now (fades in), the lesson."""
    left = _side(before[0], before[1], TERRA_TEXT, TERRA)
    right = _side(after[0], after[1], SKY_TEXT, SKY, build="fade 1")
    inner = [eyebrow(eyebrow_text), h2(title), row(left, right, gap=32),
             p(takeaway, 42, TERRA_TEXT, f";font-family:{SERIF};font-weight:700"), *extra]
    return section(sid, inner, notes, gap=22)


def _pattern_chips(*names: str) -> str:
    chips_ = chip("Pattern", MUSTARD, INDIGO) + "".join(chip(n, INDIGO if i == 0 else PURPLE) for i, n in enumerate(names))
    return (f'<div style="position:absolute;top:88px;right:128px;display:flex;gap:16px;align-items:center">'
            f'{chips_}</div>')


def s_own_test() -> str:
    """The split chapter's proof, as GPT's review sorted it (2026-10-20): what holds by construction, what a small
    blind test leans toward, and what three simultaneous changes leave unknown."""
    def claim(tag: str, text: str, accent: str, ink: str) -> str:
        return card(p(tag, 32, ink, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")
                    + p(text, 36, INK, ";line-height:1.25"), accent, flex="flex:1", gap=12)
    cards = row(claim("Proven, in code", "The hook comes back exactly. Code repeats it; no call writes it again.",
                      SKY, SKY_TEXT),
                claim("A small lean, by ear", "Blind, the guitar written against the finished sitar fit the hook "
                      "better in 3 songs of 5.", MUSTARD, MUSTARD_TEXT),
                claim("Not known", "Whether the new split sounds better. The split, a riff rule and the model all "
                      "changed at once.", TERRA, TERRA_TEXT), gap=24)
    inner = [eyebrow("Act 2 · two agents or one? · proof"), h2("What we can prove, and what we can't"), cards,
             p("Change one thing at a time, or you only know that something worked.", 42, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700;width:1120px"),
             clip("MK", 1312, 880, "Pandit's riff, then Rhythm's")]
    return section("own-test", inner, (
        "WHERE WE ARE: two agents or one?, the evidence. Be exact about what each piece of evidence shows. PROVEN: the hook returns "
        "note for note, because code repeats the committed hook; that is a mechanism, not a listening result. A SMALL "
        "LEAN: five recent songs, the first mukhada rendered twice from saved data, everything identical except the "
        "guitar under the hook: Pandit's seed riff, written before the sitar existed, or the Rhythm section's guitar, "
        "written against the finished sitar. Judged blind by ear: 3 to 2; the seed riff lost by being too busy or "
        "clashing. CLICK THE CLIP: song 04, the seed riff, then the Rhythm section's. Say what it does not show: that "
        "the guitar needs a separate agent; another Pandit call handed the finished sitar might do as well. NOT KNOWN: "
        "the redesign changed the split, removed the riff rule that forced most of a riff into chugs, and moved from "
        "gemini-3.5 to 3.8 Flash, all on 11 October. The old band never ran on the new model, so we cannot credit the "
        "better songs to the split. Five songs is a lean, not a law. That closes the chapter. NEXT CHAPTER: rules, the "
        "same four beats."), gap=24)


def s_rules_age() -> str:
    def rule(title: str, then: str, now: str) -> str:
        return card(p(title, 40, INDIGO, f";font-family:{SERIF};font-weight:700") + p(then, 34, INK, ";line-height:1.25")
                    + p(now, 34, TERRA_TEXT, ";font-weight:800;line-height:1.25"), TERRA, gap=14)
    cards = row(rule("The riff checker", "Most of every riff had to be chugs: a guard against an older model.",
                     "It rejected our best riff."),
                rule("The taan's speed", "Four notes a beat, written at a medium tempo.",
                     "At a slow tempo the climax crawled."),
                rule("The alap's pulse", "Notes counted in beats, to keep the alap in time.",
                     "At a brisk tempo it banned the long notes an alap is made of."), gap=24)
    inner = [eyebrow("Act 2 · rules · what we found"), h2("A rule tuned at one setting is a guess at every other"), cards,
             p("State a rule in the unit it lives in, and re-check it when the model or the setting changes.", 42,
               TERRA_TEXT, f";font-family:{SERIF};font-weight:700")]
    return section("rules-age", inner, (
        "Three rules, each right where it was written and wrong somewhere else. The riff checker's 55% chug floor "
        "was tuned to an older model's thin riffs; on today's model it rejected the best riff we had (TALK.md, 11 "
        "October), so texture rules became measurements reported to a judge. The taan rule said chaugun from the "
        "first note, four a beat, written at 120 bpm (about 8 notes a second); the symphonic doom piece ran at 64 bpm, "
        "about 4 a second, and Sujit heard it as dugun. The pulse now follows the tempo, about 8 notes a second. The "
        "alap's pulse rule counted holds in beats: at 120 bpm 'nothing held past two beats' is one second, and the "
        "alaps' held share fell from 50-70% to 31%; holds are now stated in seconds. Replaying the rule over saved "
        "renders found that regression in minutes."), gap=26)


def s_prompt_job() -> str:
    return _contrast(
        "prompt-job", "Act 2 · rules · one prompt per job", "Every section inherited every other section's rules",
        ("One shared template", (
            ("", "The alap was told to land on the beat it should float over"),
            ("", "The taan was asked for the rests it must never take"),
            ("", "Each new rule landed in every section"))),
        ("A contract per job", (
            (persona("composer", 1.1), "Same agent, same call, its own instructions"),
            ("", "Only the rules and fields that job needs"),
            ("", "The rejected draft rides every retry"))),
        "A shared prompt is a shared dependency: every rule added for one job leaks into the others.",
        ("Found by an outside review that read a real trace (a8b711f667eb): the alap's prompt said 'unmetred, beat 0 to "
         "44' a page away from 'LAND ON THE SAM: the sam falls at beats 0, 16, 32, 48', and said craft is 'never a "
         "rejection' while the alap's call-and-answer rules do reject. The taan's prompt asked for rests, held arrivals "
         "and compound strokes its own brief forbids. Nobody wrote a contradiction on purpose. CLICK: the fix — the "
         "alap and the taan got their own templates, each section sees only its own answer fields, and every retry "
         "carries the rejected draft (the prompt had said 'keep what worked' while showing none of it). Measured: the "
         "alap's prompt 6.4k to 3.5k tokens, the taan's 6.2k to about 4k. Sujit's hypothesis, that mixing concerns "
         "also costs thinking time, is not yet shown: one live run, the alap passed first try, the taan's time did "
         "not move."))


def s_echo() -> str:
    return _contrast(
        "echo", "Act 2 · judgment · what we found", "Judges that read each other become one judge",
        ("One after the other", (
            (persona("rasik", 1.1), "The raga critic wrote its notes"),
            (persona("producer", 1.1), "The judge read them, then decided"),
            ("", "Its plans copied the raga critic, almost word for word"))),
        ("Side by side, blind", (
            (persona("rasik", 1.1) + persona("producer", 1.1), "Both judge the same take, neither sees the other"),
            ("", "They meet only when the raga critic flags a problem"),
            ("", "Two opinions, not one echoed"))),
        "Control what each judge sees before it decides.",
        ("Measured across the recorded runs: 30 of the Producer's 36 revision plans copied Rasik near-verbatim, "
         "because it read Rasik before judging. CLICK: now they run in parallel on the same frozen take, blind to each "
         "other (Anthropic's parallelisation, the voting form: several views of one input). The Producer reads Rasik "
         "only when Rasik scores the raga 2 or below, in a short second look, and decides whether a listener would "
         "hear it. In the first live run Rasik scored 5/4/5, so the second look did not fire; and running them side by "
         "side is faster than one after the other. The same rule, in the other direction, made the notes debate run "
         "only when a reviewer names a concern."),
        extra=(_pattern_chips("Parallelisation"),))


def s_factors() -> str:
    """The decomposition rule, after the four investigations (Sujit, 2026-10-20): one question each for
    responsibility, latency, cost and quality, answered from our own runs. Call counts on the slide are
    deliberate (Sujit: "it's ok to mention calls, it gives an idea")."""
    def factor(name: str, question: str, ours: str, accent: str, ink: str) -> str:
        return card(p(name, 44, ink, f";font-family:{SERIF};font-weight:700")
                    + p(question, 36, INDIGO, ";font-weight:800;line-height:1.2")
                    + p(ours, 34, INK, ";line-height:1.25"), accent, gap=10)
    grid = (f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">'
            + factor("Responsibility", "Same idea, or a different judgment?",
                     "The hook is made once and reused; the guitar gets the finished sitar. Raga and song are "
                     "different judgments: two critics.", PURPLE, PURPLE)
            + factor("Latency", "What has to wait for what?",
                     "Eleven agents: 21 calls, 3 min. Six: 18 calls, 10 min. Thinking and waiting set the clock, "
                     "not the count.", SKY, SKY_TEXT)
            + factor("Cost", "A judgment to make, or does the answer follow?",
                     "Ustad spent a call repeating what code had found. Bass, drums and tabla cost no calls.", MUSTARD, "#9A6B12")
            + factor("Quality", "Does the split win a blind comparison?",
                     "The guitar that heard the sitar won 3–2. The debating rival added nothing, at twice the "
                     "cost.", TERRA, TERRA_TEXT) + "</div>")
    inner = [eyebrow("Act 2 · how we decided"), h2("Four questions before you add an agent"), grid,
             p("Split by responsibility first. Then let latency, cost and quality decide if the split pays.", 40,
               TERRA_TEXT, f";font-family:{SERIF};font-weight:700")]
    return section("factors", inner, (
        "The four investigations, folded into the rule we now use. The first band grew by a different rule: I "
        "wanted to try the patterns, so every problem got an agent. RESPONSIBILITY is the axis: split where the "
        "information or the judgment differs, never where job titles differ. The other three decide whether a split "
        "pays. LATENCY, measured from the traces: the eleven-agent opener (trace 480f18b59298, a 65-second Bhairav "
        "piece, low thinking) made 21 model calls in about 3 minutes; tonight's five-agent band (fce06eb8e70b, the "
        "symphonic Darbari) made 18 calls in about 10 minutes, because the composing calls think at medium and most "
        "of them wait on the gat. Removing agents did not buy speed; running independent work side by side did "
        "(the alap, taan and outro at once; Rasik and the Producer at once). Splitting one overloaded prompt into "
        "one prompt per job cut the prompt by half; whether it also cuts thinking time is not yet shown. COST: every "
        "agent is a model call, and Ustad's was pure narration of a code verdict. QUALITY: keep a split only if it "
        "wins a comparison: the Rhythm section beat Pandit's riff under the hook 3–2 blind by ear; the head debate's "
        "control made the same move without the rival at half the tokens. Next: what the four questions left standing."), gap=20)


def s_stop_ship() -> str:
    return _contrast(
        "stop-ship", "Act 2 · control · what we found", "Stopping is not accepting",
        ("At the round limit, it shipped", (
            ("", "Whatever it had, even with wrong notes"),
            ("", "A rejected revision could sneak back in"),
            ("", "Two winning edits shipped together, never heard together"))),
        ("A gate between stopping and shipping", (
            ("", "The best take is kept whole"),
            ("", "Every combination that ships is judged"),
            (V.braces_check(56, 46), "A final code check, or the last take that passed"))),
        "A round limit bounds the effort, not the quality.",
        ("An outside code review found three bugs no test had, each verified in the code first. A revision that lost "
         "its comparison was restored in the layers but left its material as the newest entry in the history, and the "
         "notes debate read the history. The debate kept a sitar rewrite and a guitar rewrite that each beat the "
         "original, then shipped them together unheard. And at the round cap the router logged 'accepting the last "
         "version' even when the legality check said illegal. CLICK: a saved take now carries all of itself; rewrites "
         "are accepted one at a time against the current champion; a final code check runs before anything ships, "
         "with an honest outcome: accepted, budget exhausted, or failed checks. A wall-clock budget sits beside the "
         "round limit for the live slot."))


def s_band(sid: str, stage: int, notes: str) -> str:
    """The roster after chapter `stage`: decided agents carry their fate (the gone ones faded), the rest wait."""
    def m(n: str, w: str) -> str:
        chapter, tag = FATE[n]
        if chapter > stage:
            return member(n, w, scale=2.6)
        if n in GONE:
            return member(n, w, scale=2.6, dim=True, tag=tag)
        return member(n, w, scale=2.6, tag=tag, tag_color=SKY_TEXT)
    top = row(*(m(n, w) for n, w in ELEVEN[:6]), gap=12, align="start")
    rhythm = member("rhythm", "guitar + bass, to the sitar", scale=2.6, tag="new", tag_color=SKY_TEXT)
    bottom = row(*(m(n, w) for n, w in ELEVEN[6:]), rhythm, gap=12, align="start")
    return section(sid, [eyebrow("Act 2"), h2(BAND_TITLES[stage]), top, bottom], notes, gap=22)


# The build in FOUR clicks (2026-10-20 narrative review: seven was ~3 minutes): the growth beats grouped by the
# job they did. Same shape as GROWTH (the annex keeps the seven beats one per slide).
def _merged(first: int, last: int, title: str, pattern: str, pain: str, decision: str) -> tuple:
    beats = GROWTH[first:last + 1]
    return ("", beats[0][1], beats[-1][2], pattern, title, pain, decision,
            " ".join(b[7] for b in beats), " ".join(b[8] for b in beats))


BUILD_STEPS: Final = (
    _merged(0, 1, "Rules in code, and a front door", "self-correction · prompt chaining",
            "Wrong notes slipped through, and the model chose things you never asked for.",
            "The raga's rules become data checked in code; an Interpreter reads the request and invents nothing."),
    _merged(2, 2, "A plan, and a worker for each part", "sectioning",
            "Nobody owned the song.",
            "Two composers agree a plan; one agent writes the sitar, one the riff. Bass and drums are code."),
    _merged(3, 5, "Three judges and a referee", "evaluator–optimiser · debate · workflow",
            "Correct notes, lifeless music, and when the critics disagreed, nobody decided.",
            "Critics for the rules, the raga and the song; a Conductor rules; code runs the order and stops it."),
    _merged(6, 6, "The band starts listening", "blackboard",
            "Every part was good alone, and it didn't sound like a band.",
            "Sitar and riff take turns on one shared canvas; an Arranger fixes clashes."),
)


def s_build() -> str:
    """The whole growth on one slide (Sujit, 2026-10-20: "53-57 showed how the workflow grew; do it on one slide
    with animation"): click k pops beat k's pieces onto the graph and fades in its story card (pain, decision,
    trade-off, from GROWTH); the next click fades that card out as the next one comes in. The last card stays."""
    def card_for(k: int, beat: tuple) -> str:
        _, _, _, pattern, title, pain, decision, tradeoff, _ = beat
        out = f' data-build-out="fade {k + 1}"' if k < len(BUILD_STEPS) else ""
        cols = "".join(
            f'<div style="flex:1;display:flex;flex-direction:column;gap:4px">'
            f'{p(head, 30, ink, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")}'
            f'{p(text, 32, INK, ";line-height:1.2")}</div>'
            for head, text, ink in (("Pain", pain, TERRA_TEXT), ("Decision", decision, INDIGO)))   # no trade-off yet: Act 1 only introduces the band
        return (f'<div data-build-in="fade {k}"{out} style="position:absolute;left:128px;top:756px;width:1664px;'
                f'height:212px;background:{CARD};border:2px solid {LINE};border-top:10px solid {MUSTARD};border-radius:16px;'
                f'padding:14px 26px;display:flex;flex-direction:column;gap:8px">'
                f'{p(f"{k} of {len(BUILD_STEPS)} · {title} · {pattern}", 34, INDIGO, f";font-family:{SERIF};font-weight:700")}'
                f'<div style="display:flex;gap:32px">{cols}</div></div>')
    cards = [card_for(k, g) for k, g in enumerate(BUILD_STEPS, start=1)]
    inner = [eyebrow("Act 1 · the first band"), h2("The band grew one fix at a time"), *groups(), *build(), *code_seats(), *cards]
    notes = " ".join(f"CLICK {k}: {g[4]}. {g[8]}" for k, g in enumerate(BUILD_STEPS, start=1))
    return section("build", inner, (
        "Four clicks, about two minutes: the whole growth story on one picture. Each click adds that beat's pieces "
        "to the graph and tells why: the pain, and the decision. What each decision cost comes in Act 2. " + notes + " Eleven agents, each one "
        "joined to fix a real failure. Be honest here: each fix was real, but I also reached for an agent because "
        "the pattern was the fun part to build. It felt finished."), gap=20)


# One graph update per chapter (Sujit, 2026-10-20): (stage, title, what changed, notes). Stage 5 = the static recap.
STAGES: Final = (
    (1, "Two composers became one",
     "Riffsmith's priors moved into Pandit. One composer writes the plan, the riff and the hook's idea.",
     "The first change, drawn on the band from Act 1. CLICK: Riffsmith leaves; its seat says where the job went; "
     "Pandit takes on the fused look, one composer holding both priors."),
    (2, "Guitar and bass became one rhythm section",
     "One agent now writes both, for the whole song, after the sitar is finished. Drums stay code.",
     "The second change. CLICK: the Riff agent, the shared canvas and the Arranger go, and the bass code joins them. The "
     "Arranger fixed clashes between a sitar and a guitar written apart; once the guitar is written hearing every "
     "finished sitar note, that job is gone, and the clashes that remain are deliberate (by ear I kept the grinds; "
     "historically that is why it was deleted, a day before the rhythm-section call existed). Code still counts the "
     "clashes for the judge. The Rhythm "
     "section writes guitar and bass together, because both play the rhythm, and it writes after hearing the "
     "finished sitar. The drums stay code, locked to the guitar. The squares count model calls for the same song, "
     "the opening song's five sections: the Lead 7 before (it drafted each section, then redrafted after hearing the "
     "guitar) and 3 now (one gat call for the hook sections, one each for the alap and the taan); the guitar 6 "
     "before (four rejected by the old riff rule), and the Rhythm section 1 now, for guitar and bass together. "
     "Retries can add a call or two either way."),
    (3, "The legality critic became code",
     "Ustad only repeated what the rule checker found. Now the checker alone decides.",
     "After the rules chapter. CLICK: Ustad leaves. It called the validator and put its verdict into words; the "
     "verdict was already code, so the agent added a call and no information."),
    (4, "The referee became a rule",
     "One judge decides and a round cap stops it.",
     "After the judgment chapter. CLICK: the Conductor, who refereed the critics' debates, becomes a round cap in "
     "code. (The Arranger already left with the collaboration, at stage 2.)"),
    (5, "Eleven became six",
     "Interpreter, Pandit, Lead, Rhythm section, Rasik and Producer. The Orchestra joins symphonic pieces.",
     "The recap: every change at once, no clicks. Each departure was a finding from Act 2, not a guess. Then the "
     "line: keep one plain call as your control; the day it beats your system, suspect your decomposition, and "
     "change one thing at a time to find out what is wrong."),
)


def s_stage(stage: int, sid: str) -> str:
    """Slide 13's graph after `stage` changes; one click animates this stage's departures and shows the caption."""
    _, title, what, notes = STAGES[stage - 1]
    inner = [eyebrow("Act 2 · the band so far"), h2(title), *groups(), *shrink(stage)]
    return section(sid, inner, f"{what} {notes}", gap=20)


def s_payoff() -> str:
    inner = [eyebrow("Your choice"), h2("Your live composition"),
             p("[the style you picked]", BIG, MUTED, ";font-style:italic"),
             p("If the run isn't done: a recorded example in your chosen style, labelled as one.", BODY, MUTED)]
    return section("payoff", inner, (
        "Play ten seconds of the audience's live result. If it is still running, say so and play the labelled "
        "recorded example in the chosen style; if it failed, say that it did not complete. Never pass a recording "
        "off as live."), gap=30)


def s_redesign() -> str:
    return s_band("redesign", 3, "The last state of the same picture. Six left, one joined, and every departed "
                  "agent's job went somewhere better: three composers became one, Pandit, because the plan, the hook "
                  "and the sitar line are one idea; the Riff's job went to the Rhythm section, which writes guitar and "
                  "bass after hearing the finished sitar line (a blind test put its guitar ahead of Pandit's riff); Ustad's verdict was already code; the Conductor became a round limit; the Arranger's "
                  "clash detection became a number the Producer reads; the Orchestra joins only for symphonic pieces. "
                  "Then the line: keep one unconstrained call as your control; the day it beats your system, suspect "
                  "your decomposition, and change one thing at a time to find out what is wrong.")


# The single-prompt experiment on gemini-3.8-flash, three ragas (talk/audio/single_prompt_results.md).
LADDER: Final = (
    ("A", "Correct", "One plain prompt", (("Wrong notes", "0–4"), ("Signature phrase, exact", "0–1 of 2"),
                                         ("Hook comes back", "0–2 times"), ("Raga mood (Rasik)", "2–3 of 5")), 0, TERRA, TERRA_TEXT),
    ("B", "The raga's words", "+ the raga's grammar", (("Wrong notes", "0"), ("Signature phrase, exact", "2 of 2"),
                                                       ("Hook comes back", "0–1 times"), ("Raga mood (Rasik)", "2–3 of 5")), 50, SKY, SKY_TEXT),
    ("C", "Music", "The agentic system", (("Wrong notes", "0"), ("Signature phrase, exact", "1–2 of 2"),
                                          ("Hook comes back", "3 times"), ("Raga mood (Rasik)", "4 of 5")), 100, MUSTARD, "#9A6B12"),
)


LADDER_LINES: Final = (("Mostly the right notes", "Nothing comes back", "The mood is weak"),
                       ("Quotes the raga's phrases", "Still nothing comes back", "The mood doesn't move"),
                       ("The hook comes back", "The critic hears the raga", "It's built like a song"))


def s_ladder() -> str:
    """The experiment's answer, after the redesign: three rungs in plain words (Sujit, 2026-10-20: redo it; the
    twelve figures live in the notes)."""
    def rung(i: int, k: str, name: str, how: str, lift: int, accent: str, ink: str) -> str:
        lines = "".join(p(x, 34, INK, f";border-left:6px solid {accent};padding-left:14px;line-height:1.2") for x in LADDER_LINES[i])
        body = card(p(f"{k} · {name}", 48, INDIGO, f";font-family:{SERIF};font-weight:700") + p(how, LABEL, ink, ";font-weight:800")
                    + lines, accent, flex="flex:none", pad="22px 26px", gap=12)
        step = f'<div style="height:{lift + 16}px;background:{INDIGO};border-radius:0px 0px 12px 12px"></div>'
        build = f' data-build-in="fade {i}"' if i else ""
        return f'<div{build} style="flex:1;display:flex;flex-direction:column;justify-content:end">{body}{step}</div>'
    rungs = [rung(i, k, name, how, lift, accent, ink) for i, (k, name, how, _, lift, accent, ink) in enumerate(LADDER)]
    figures = "; ".join(f"{k} ({how}): " + ", ".join(f"{label.lower()} {value}" for label, value in rows_)
                        for k, _, how, rows_, *_ in LADDER)
    inner = [eyebrow("Act 2 · the answer, on today's model"), h2("Correct, then the raga's words, then music"),
             row(*rungs, gap=28, align="end"),
             p("Right notes aren't the raga, and the raga's phrases aren't a song.", 42, TERRA_TEXT, f";font-family:{SERIF};font-weight:700")]
    return section("ladder", inner, (
        "The other option we rejected, the simplest one of all: no agents, one prompt. We ran it on today's model, "
        "gemini-3.8-flash, across Yaman, Darbari and Bhairav, all through the same instruments, one song per approach. "
        "A: the plain prompt is now correct; it plays legal notes, but nothing comes back and the raga's mood is weak. "
        "CLICK. B: with our grammar it quotes the signature phrase exactly every time, and the mood score does not move: "
        "it recites the raga's words without speaking it, and it is still not a song. CLICK. C, the system of 18 "
        "October: the hook returns three times in every song, and the raga critic scores the mood 4. The figures: "
        + figures + ". Caveats, out loud: the plain format had no field for ornaments or palm mutes, its prompt asked "
        "every part to play the whole length, and our Bhairav song never breathes either. If there is time, play ten "
        "seconds of C's hook coming back."), gap=24)


def s_knew() -> str:
    """What the plain prompt already knew, what it couldn't do alone, and what the design added: the
    thesis behind the ladder, in plain words (evidence in the notes: the seven bare-prompt songs)."""
    def col(title: str, items: tuple[str, ...], accent: str, ink: str) -> str:
        lines = "".join(f'<div style="display:flex;gap:18px;align-items:baseline">'
                        f'<p style="font-size:40px;font-weight:800;color:{accent}">●</p>{p(t, BODY, INK)}</div>' for t in items)
        return card(p(title, 44, ink, f";font-family:{SERIF};font-weight:700") + lines, accent, gap=12)
    knew = col("What the model already knew", ("The raga's signature phrases", "A real metal riff", "How to build to a climax"),
               SKY, SKY_TEXT)
    alone = col("What it couldn't do on its own", ("Where a phrase should come to rest", "Bring an idea back",
                                                   "Make room for the other instrument"), TERRA, TERRA_TEXT)
    brought = "".join(f'<p style="flex:1;font-size:36px;font-weight:700;line-height:1.25;color:{LIGHT}">{t}</p>'
                      for t in ("Our knowledge, written down as data", "A plan before the notes",
                                "One agent per decision, each with one goal"))
    band = (f'<div style="background:{INDIGO};border-radius:16px;padding:22px 32px;display:flex;flex-direction:column;gap:10px">'
            f'{p("What we brought", LABEL, MUSTARD, ";font-weight:800;letter-spacing:4px;text-transform:uppercase")}'
            f'<div style="display:flex;gap:40px">{brought}</div></div>')
    inner = [eyebrow("Act 2 · what the plain prompt taught us"), h2("It knew the raga. It didn't know what to do with it."),
             row(knew, alone, gap=32), band,
             p("The model brings the knowledge.<br>Designing the system is the skill.", 44, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700")]
    return section("knew", inner, (
        "The point of the whole experiment, said plainly. Start with the misconception: a lot of people think an "
        "agentic system is a prompt with extra steps; write the prompts and the model does the music. But the model "
        "already knows more about ragas than almost anyone in this room. The plain prompt's Bageshree opens with the "
        "raga's signature phrase almost word for word, resting on Ma the way a musician would; its Bhairav riff is "
        "real neoclassical metal; every one of its songs builds to a climax. What it can't do alone is decide what matters. A raga lives in where "
        "a phrase comes to rest and which note it lingers on: across the seven plain songs nearly every phrase ends "
        "on Sa; the Todi runs Pa up the scale, which the raga forbids; the Malkauns keeps resting on dha until the "
        "same five notes sound like a Chinese pentatonic. Only one of the seven brings its opening theme back, "
        "because it writes left to right and nothing asks it to plan a return. In several songs the guitar and bass "
        "just copy the sitar, because nobody told them the sitar owns the line. What we brought is the human part: "
        "the raga's facts as data every agent reads, a plan written before any note, and agents split where the "
        "information or the judgment differs, each with one goal. That part is not a prompt, and it is the hard part."),
        gap=26)


# ---- act 3: lessons ---------------------------------------------------------------------------
def s_l1() -> str:
    def col(pic: str, title: str, sub: str) -> str:
        return (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:14px;background:{CARD};border-radius:20px;padding:24px 18px">'
                f'<div style="height:200px;display:flex;align-items:end;justify-content:center;gap:6px">{pic}</div>'
                f'{p(title, 40, INDIGO, ";font-weight:800;text-align:center")}{p(sub, LABEL, MUTED, ";text-align:center")}</div>')
    merge = "".join(persona(n, 1.1) for n in ("pandit", "riffsmith", "lead", "riff")) + V.arrow(80, 50) + persona("composer", 2.4)
    judges = persona("rasik", 2.4) + persona("producer", 2.4)
    derive = (f'<img src="{SPRITES["guitar"]}" alt="guitar" style="width:160px;height:60px;object-fit:contain">' + V.arrow(80, 50)
              + V.braces_check(150, 124))
    ev = [row(col(merge, "Same idea → one owner", "riff, hook and form are conceived together"),
              col(judges, "Different judgment → two judges", "one hears the raga, one the song"),
              col(derive, "Derivable → code", "bass and kick follow the riff"), gap=28)]
    return lesson("l1", 1, "Split agents where the information or the judgment differs", ev,
                  "Never split where only the job titles differ.", "If you are drawing one agent per noun in your output, you are writing utils.py. Every agent is a model call: latency, cost and a failure surface. It earns its place by owning a decision the others can't make with what they see.")


def s_l2() -> str:
    before = (f'<div style="flex:1;display:flex;flex-direction:column;gap:14px">'
              + p("Before: “55% of a riff on one pitch”", 40, INDIGO, ";font-weight:800")
              + V.hbars([("the rule", 55, MUTED), ("best riff", 48, DANGER)], 820, rh=130)
              + V.stamp("REJECTED", DANGER, 400, 124) + "</div>")
    physics = [("a muted string can't ring", SKY), ("a chord can't bend", SKY), ("the loop lands on beat one", SKY)]
    now = (f'<div style="flex:1;display:flex;flex-direction:column;gap:16px">'
           + p("Now: only constraints we validated", 40, INDIGO, ";font-weight:800")
           + "".join(f'<div style="display:flex;gap:22px;align-items:center"><p style="font-size:72px;color:{c};font-weight:800">✓</p>{p(t, BIG)}</div>' for t, c in physics)
           + p("Taste → a number the Producer reads", BIG, TERRA_TEXT, ";font-weight:800") + "</div>")
    ev = [row(before, now, gap=56)]
    return lesson("l2", 2, "Code enforces what we validated. Taste gets measured.", ev,
                  "A guardrail tuned to a model's weakness becomes a ceiling.", "The July rule was calibrated on real failures, when the model wrote busy melodies and called them riffs. The model moved on and the rule didn't: the best riff we had sat at 48%. Now code rejects only the physical, and on last week's run it caught a direction-rule slip and a guitar cycle that didn't fill its bar, both fixed on one retry. Whether a riff is heavy enough is a number the Producer reads, never a reason to reject.")


def s_l3() -> str:
    def flow(label: str, *items: str, verdict: str, c: str) -> str:
        return (f'<div style="display:flex;gap:28px;align-items:center;background:{CARD};border-radius:20px;padding:22px 30px">'
                f'<p style="width:230px;font-family:{SERIF};font-size:56px;font-weight:600;color:{c}">{label}</p>'
                + "".join(items) + f'<p style="flex:1;font-size:{BIG}px;line-height:1.25;color:{INK}">{verdict}</p></div>')
    ev = [flow("Told", V.doc(160, 192), V.arrow(130, 60, MUTED, dashed=True), V.bubble(210, 170), V.cross(90),
               verdict="a sentence in a prompt; mostly ignored", c=TERRA_TEXT),
          flow("Applied", V.doc(160, 192), V.arrow(130, 60), V.braces_check(200, 164), V.arrow(130, 60), V.wave(220, 120),
               verdict="code acts on every note", c=SKY_TEXT)]
    return lesson("l3", 3, "A fact in your data is not in your output until something applies it", ev,
                  "If a fact is deterministic, telling a model is a hope, not a mechanism.", "Darbari's data said exactly how its Ga is approached, and warned that a straight Ga turns it into another raga. That fact went one place: a sentence in the lead prompt, mostly ignored. Code now applies it. The flip side is the next slide: code that applies a fact can be wrong too, so test it per case.")


def contour_chart() -> str:
    """The measured pitch of one Bageshree Ga, before and after the fix (titles/contour.py)."""
    data = json.loads((HERE / "titles" / "bageshree_contour.json").read_text())
    W, H, t1, lo, hi = 980, 420, 1.08, -40, 240
    X = lambda t: 40 + t / t1 * (W - 330)
    Y = lambda c: 20 + (hi - c) / (hi - lo) * (H - 60)
    def line(k: str, c: str, w: int) -> str:
        pts = " ".join(f"{X(t):.0f},{Y(v):.0f}" for t, v in data[k] if t <= t1)
        return f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"/>'
    ref = lambda c, label, col, dash: (f'<line x1="40" x2="{W - 290}" y1="{Y(c):.0f}" y2="{Y(c):.0f}" stroke="{col}" stroke-width="3" stroke-dasharray="{dash}"/>'
                                      f'<text x="{W - 270}" y="{Y(c) + 10:.0f}" font-family="Mulish" font-size="28" font-weight="700" fill="{col}">{label}</text>')
    return (f'<svg aria-label="Measured pitch of one note: the original swings up and turns on the wrong note; the fix glides down and settles" '
            f'style="width:{W}px;height:{H}px" viewBox="0 0 {W} {H}">'
            f'<rect width="{W}" height="{H}" rx="16" fill="{CARD}"/>'
            + ref(200, "Ma", MUTED, "2 10") + ref(100, "a wrong note", DANGER, "12 10") + ref(0, "Ga, the right one", SKY_TEXT, "2 10")
            + line("original", DANGER, 8) + line("corrected", SKY_TEXT, 8)
            + f'<text x="40" y="{H - 10}" font-family="Mulish" font-size="28" fill="{MUTED}">one note, about a second, measured from the audio</text></svg>')


def s_l4() -> str:
    left = (f'<div style="width:560px;display:flex;flex-direction:column;gap:18px">'
            + bubble("“Beautiful andolans on komal ga.”", "Rasik, scoring that very run from the notes: 4, 4, 4")
            + f'<div style="display:flex;justify-content:center">{persona("rasik", 3.2)}</div></div>')
    right = (f'<div style="flex:1;display:flex;flex-direction:column;gap:16px">{contour_chart()}'
             + p(f'<span style="color:{DANGER};font-weight:800">Before:</span> the sway turns on the wrong note. '
                 f'<span style="color:{SKY_TEXT};font-weight:800">After:</span> it glides and settles.', BODY) + "</div>")
    ev = [row(left, right, gap=40, align="start")]
    return lesson("l4", 4, "The critic loved it. The audio was wrong.", ev,
                  "Check what your users receive, not the plan that produced it.",
                  "Rasik judges the score, the notes as data, and the score said exactly the right thing. The failure lived one layer later, in how the notes became sound. No agent hears audio, so code now measures the rendered pitch, and the listening model gets no vote until it agrees with a blind human ranking 70% of the time. Play BG: before, then after.",
                  [clip("BG", 1312, 930, "before, then after", 480, 80)])


def s_l5() -> str:
    asked = (f'<div style="width:760px;background:{CARD};border:3px solid {INDIGO};border-radius:28px;padding:26px 30px">'
             f'<p style="font-family:{SERIF};font-size:40px;font-weight:600;line-height:1.3;color:{INDIGO}">“Sixty seconds, Bhairav in E, teentaal at 128, '
             f'a hit on the final beat, ending on the high note, <span style="color:{TERRA_TEXT};text-decoration:underline">and I will play rhythm guitar live</span>.”</p></div>')
    chips = "".join(chip(f"{c} ✓", SKY, INDIGO) for c in ("raga", "key", "rhythm", "tempo", "style"))
    wrong = (f'<div style="display:flex;gap:12px;align-items:center">{chip("instruments: rhythm guitar", DANGER)}'
             f'{p("the exact opposite", LABEL, DANGER, ";font-weight:800")}</div>')
    lost = p('<span style="text-decoration:line-through">sixty seconds · the final hit · the high note</span> lost', LABEL, MUTED)
    brief = (f'<div style="flex:1;display:flex;flex-direction:column;gap:14px">{p("What the agents saw", 40, INDIGO, ";font-weight:800")}'
             f'<div style="display:flex;gap:10px;flex-wrap:wrap">{chips}</div>{wrong}{lost}</div>')
    ev = [row(asked, V.arrow(), brief, gap=24, align="center"),
          p("Now my words travel verbatim beside the brief, to every agent that makes a musical decision.", BODY)]
    return lesson("l5", 5, "A structured handoff loses whatever the schema didn't expect", ev,
                  "Keep the schema for what you can check. Pass the intent for what you can't.", "The Interpreter turned my request into a structured brief, and every agent after it saw only that. Five asks survived because they matched a field. The rest had nowhere to go, and the live guitar landed in instruments to use, which the composers are told to honour. The fix is two channels: the schema for what code enforces, the user's words verbatim for everything else.")


def s_l8() -> str:
    """Sujit, 2026-10-20: re-evaluate the decomposition whenever a stronger model ships."""
    def stage(when: str, model: str, text: str, accent: str) -> str:
        return card(p(when, 44, INDIGO, f";font-family:{SERIF};font-weight:700")
                    + p(model, 30, MUTED, ";font-weight:800;letter-spacing:2px;text-transform:uppercase")
                    + p(text, 36, INK, ";line-height:1.25"), accent, flex="flex:1", gap=10)
    arrow = f'<p style="font-size:56px;font-weight:800;color:{MUTED};align-self:center">→</p>'
    ev = [row(stage("July", "a weaker model", "It wrote busy melodies and called them riffs. We added rules, and agents, "
                    "to make up for it.", SKY), arrow,
              stage("October", "a newer model", "Once, one plain call beat our riff. Our rules would have rejected it.",
                    MUSTARD), arrow,
              stage("A week later", "the next model", "The plain call that played dozens of wrong notes played none.",
                    TERRA), gap=18, align="stretch"),
          p("Some boundaries encode real dependencies. Others cover for the model of the day.", BODY, INK)]
    return lesson("l8", 8, "Your decomposition has an expiry date", ev,
                  "Re-check the split whenever a stronger model ships. Keep one plain call as the control.", (
        "Sujit's lesson, from the whole story. Every agent and most rules were added to fix a failure we saw; many of "
        "those failures were the model's, at the time. In July the model wrote busy low melodies and called them "
        "riffs, so we added a chug rule and more machinery. By October requests were served by a newer Flash: one "
        "bare call wrote the riff that beat ours, and our July rule would have rejected it twice (TALK.md 'The "
        "verifier that would have rejected the best riff'). A week later, on gemini-3.8, the bare call that had played "
        "92 forbidden notes in Bhairav (gemini-3.5, 11 October) played none in Bhairav or Yaman (4 in Darbari's "
        "guitar). What the plain call still cannot do (the raga's emphasis, a hook that returns, parts that breathe "
        "together) is what the five-agent band is for now. The practice: keep a single unconstrained call as your "
        "control, re-run it on every model release, and ask of every agent and every rule whether it is still covering "
        "for a weakness the model has outgrown. The day the control beats your system, your decomposition is the bug."))


def s_l6() -> str:
    def tag(t: str, c: str) -> str:
        return f'<p style="font-family:{MONO};font-size:48px;color:{c};background:{CARD};border:4px solid {c};border-radius:14px;padding:14px 24px">{t}</p>'
    rng = V.svg(1000, 170, f'<rect x="0" y="60" width="1000" height="60" rx="30" fill="{SUNK}"/>'
                         f'<rect x="{1000 * 4 / 20:.0f}" y="60" width="{1000 * 14.5 / 20:.0f}" height="60" rx="30" fill="{TERRA}"/>'
                         + V.text(1000 * 4 / 20, 44, "4,000", 40, TERRA, 800, "middle") + V.text(1000 * 18.5 / 20, 44, "18,500", 40, TERRA, 800, "middle")
                         + V.text(0, 162, "0", 32, MUTED) + V.text(1000, 162, "20,000 thinking tokens", 32, MUTED, 700, "end"), "thinking tokens per call")
    left = (f'<div style="flex:1;display:flex;flex-direction:column;gap:18px">{p("Configured", 40, INDIGO, ";font-weight:800")}'
            f'{tag("reasoning_effort = low", INDIGO)}{p("Ran: 40 to 137 seconds a call", 40, INDIGO, ";font-weight:800")}{rng}</div>')
    right = (f'<div style="width:560px;display:flex;flex-direction:column;gap:22px">{p("Requested", 40, INDIGO, ";font-weight:800")}'
             f'{tag("gemini-3.5-flash", INDIGO)}{p("Answered by", 40, INDIGO, ";font-weight:800")}{tag("gemini-3.6-flash", TERRA)}</div>')
    ev = [row(left, right, gap=64)]
    return lesson("l6", 6, "Verify what ran, not what you configured", ev,
                  "Read the trace: the tokens, the model version, the latency. Settings are claims.", "Both were found by reading traces, not configs. The framework silently dropped the reasoning setting for our provider, so thinking ran uncapped. And the model behind the name changed, which the response itself reports; rules tuned on one model were running on another. Every run in this repo is traced by default.")


def s_l7() -> str:
    notes = V.svg(1600, 300, f'{V.text(0, 62, "written", 48, INDIGO, 800)}<rect x="230" y="12" width="1300" height="72" rx="14" fill="{SKY}"/>'
                           f'{V.text(0, 192, "played", 48, INDIGO, 800)}<rect x="230" y="142" width="90" height="72" rx="14" fill="{TERRA}"/>'
                           f'{V.text(350, 196, "80 ms, whatever was written", 48, TERRA, 800)}'
                           f'{V.text(230, 282, "one beat of a riff", 36, MUTED)}', "a written note cut to 80 milliseconds")
    rule = (f'<div style="background:{CARD};border-left:10px solid {TERRA};border-radius:12px;padding:20px 26px;display:flex;flex-direction:column;gap:8px">'
            f'<p style="font-family:{MONO};font-size:44px;color:{INDIGO}">PALM_MUTE_MS = 80</p>'
            f'<p style="font-size:40px;color:{MUTED};text-decoration:line-through">“a palm-muted note gates to a short chunk whatever its written duration”</p>'
            f'{p("…and the prompt taught it to the model as a musical rule", 40, TERRA_TEXT, ";font-weight:800")}</div>')
    ev = [notes, rule]
    return lesson("l7", 7, "Never explain a bug to the model", ev,
                  "A prompt that documents a bug teaches the model to repeat it.", "Choppy riffs, and every check passed. 21% of muted notes were written a beat or longer and played for a sixth of a beat. Worse, the prompt described the clamp as craft, so the model wrote around it. We fixed the renderer and deleted the line.")


# ---- close --------------------------------------------------------------------------------------
def s_trace() -> str:
    # trace fce06eb8e70b, fusion_20261020_144218_darbari_symph: today's workflow end to end (2026-10-20)
    stops = [(("interpreter",), "Interpreter", "a brief", "3 s", None),
             (("composer",), "Pandit", "the seed", "2 min", "2 drafts sent back"),
             (("lead",), "Lead", "the gat", "2 min", None),
             (("lead",), "Lead", "revises the head", "3 min", "too high for Darbari"),
             (("lead",), "Lead ×3", "alap, taan, outro at once", "1 min", "taan sent back"),
             (("rhythm", "orchestra"), "Rhythm, Orchestra", "guitar, bass, strings", "26 s", None),
             (("rasik", "producer"), "Rasik, Producer", "side by side; one fix: the taan", "26 s", None),
             (("lead",), "Lead", "rewrites the taan", "1.5 min", "compared: revision kept")]

    def stop(sprites: tuple[str, ...], name: str, did: str, t: str, code: str | None) -> str:
        scale = 2.3 if len(sprites) == 1 else 1.6
        badge = (f'<div style="height:96px;display:flex;align-items:end;justify-content:center">'
                 + (f'<p style="font-size:30px;font-weight:800;color:{LIGHT};background:{DANGER};border-radius:10px;'
                    f'padding:4px 10px;text-align:center;line-height:1.15">{code}</p>' if code
                    else f'<p style="font-size:30px;color:{PAGE}">.</p>') + "</div>")
        return (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:6px">{badge}'
                f'<div style="height:150px;display:flex;align-items:end;gap:2px">{"".join(persona(n, scale) for n in sprites)}</div>'
                f'<div style="width:100%;height:10px;background:{INDIGO};border-radius:5px"></div>'
                f'<p style="font-size:32px;font-weight:800;color:{INDIGO};text-align:center;line-height:1.1">{name}</p>'
                f'{p(did, LABEL, INK, ";text-align:center;line-height:1.15")}{p(t, LABEL, MUTED, ";font-weight:800")}</div>')
    inner = [eyebrow("One real run"), h2("One real run: 18 model calls, about ten minutes"),
             p("“Doom symphonic metal in Darbari.”", BODY, MUTED, ";font-style:italic"),
             row(*(stop(*x) for x in stops), gap=8, align="start"),
             p("Every check ran. The judge's one fix won, both ways round. No debate was needed.", BODY, SKY_TEXT,
               ";font-weight:800")]
    return section("trace", inner, (
        "Trace fce06eb8e70b, 20 October, today's workflow end to end, a request typed in plain words. The Interpreter "
        "read it in 3 seconds. Pandit's seed was sent back twice by code (an alap too short to establish the raga; a "
        "chord progression under the climax taan), then passed. The gat came next, and code measured its head living in "
        "the middle register when Darbari lives low, so the head revised itself once, kept because it fixed that "
        "without breaking anything. Then the alap, the taan and the outro were written at the same time; the taan was "
        "sent back once. The rhythm section wrote guitar and bass after hearing the whole sitar line, and the "
        "Orchestra added the symphonic layer. Rasik and the Producer judged the same take side by side: Rasik scored "
        "the raga 5, 4, 5, so no second look; the Producer asked for one fix, because the taan peaked early, a fault "
        "two tries had not fixed and the best of them had shipped. The rewrite won the comparison in both orders. No "
        "reviewer of the shipped take raised a concern, so the notes debate did not run. A final code check passed. 18 "
        "model calls, about ten and a half minutes with the render: every guard earns its place, and every guard costs "
        "time. The older 19 October run (27 calls in 19 minutes, with the debate) is the one whose split comparison you saw in the judgment chapter."), gap=22)


def s_plan() -> str:
    bubble_html = (f'<div style="flex:1;background:{CARD};border:4px solid {INDIGO};border-radius:32px;padding:30px 38px;display:flex;flex-direction:column;gap:18px">'
                   f'<p style="font-family:{SERIF};font-size:52px;font-weight:600;color:{INDIGO}">Revise the manjha’s cadence.</p>'
                   f'{p("“Let the melody rise briefly through madhyam and dwell heavily on Rishabh before resolving home to the tonic.”", BODY, INK)}'
                   f'<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">{p("Preserve:", BODY, SKY_TEXT, ";font-weight:800")}'
                   + "".join(chip(t, SKY, INDIGO) for t in ("the deep mandra exploration on low Pa and Dha", "the heavy rhythmic breathing of the manjha")) + "</div></div>")
    who = (f'<div style="width:360px;display:flex;flex-direction:column;align-items:center;gap:10px">{persona("producer", 5.6)}'
           f'{p("the Producer,<br>the one judge", LABEL, MUTED, ";text-align:center")}</div>')
    verdict = (f'<div style="display:flex;gap:24px;align-items:center;background:{CARD};border:2px solid {LINE};'
               f'border-left:10px solid {TERRA};border-radius:14px;padding:18px 26px">'
               + p("Compared both ways:", BODY, INDIGO, ";font-weight:800;white-space:nowrap")
               + p("revision first → revision; swapped → draft. A split: the draft stays.", BODY, INK) + "</div>")
    inner = [eyebrow("One real run"), h2("One fix asked; the comparison kept the draft"),
             row(who, bubble_html, gap=36, align="center"), verdict]
    return section("plan", inner, (
        "A 19 October run (trace 78ed74760e8a): the second half of the judge's fix, a revision must win. The Producer's real output: decision revise; the lead in the manjha; the instruction names the "
        "problem, verbatim, \"the cadence drops abruptly from the oscillating komal gandhar straight down to Sa\", and "
        "the preserve list protects the low Pa and Dha and the manjha's breathing. The fix was written. Then the "
        "comparison in both orders: shown revision first it chose the revision, shown the draft first it chose the draft. A "
        "split keeps the champion. This is the rule from the judge's do-and-don't slide, working in a real run: a "
        "fix must beat the draft in both orders, or the draft stands."), gap=26)


# ---- take this home: steering is a balance --------------------------------------------------------
BALANCE: Final = (
    ("Too tight", TERRA, TERRA_TEXT, ("Our riff checker rejected our best riff.",
                                      "Rules for an old model capped a newer one.",
                                      "Our prompt made every composer write the same piece."),
     "Correct, safe, all alike."),
    ("Balanced", MUSTARD, "#9A6B12", ("Code enforces what we validated.",
                                      "The model is free on taste.",
                                      "A person decides what is good."),
     "Right, and alive."),
    ("Too loose", PURPLE, PURPLE, ("A plain prompt: right notes, no hook.",
                                   "Debate rewrote half the music each turn.",
                                   "An older model broke the raga's rules."),
     "Plausible, but shapeless."),
)


def _steering_scale() -> str:
    """The steering bar: tight (terracotta) to loose (purple), the balanced band in mustard, and
    the DevDay bot standing on the balance point."""
    bar = (f'<defs><linearGradient id="steer" x1="0" x2="1" y1="0" y2="0">'
           f'<stop offset="0" stop-color="{TERRA}"/><stop offset="0.38" stop-color="{SUNK}"/>'
           f'<stop offset="0.62" stop-color="{SUNK}"/><stop offset="1" stop-color="{PURPLE}"/></linearGradient></defs>'
           f'<rect x="0" y="186" width="1664" height="26" rx="13" fill="url(#steer)"/>'
           f'<rect x="652" y="178" width="360" height="42" rx="21" fill="{MUSTARD}"/>'
           f'<path d="M832 224 L818 246 H846 Z" fill="{MUSTARD}"/>')
    scale = 0.32
    art = V.svg(1664, 250, bar + bot(832 - 230 * scale, 180 - 548 * scale, scale), "the steering scale", (1664, 250))
    return f'<div style="flex:none;display:flex;justify-content:center">{art}</div>'


def s_balance() -> str:
    def zone(name: str, accent: str, ink: str, lines: tuple[str, ...], result: str) -> str:
        body = "".join(p(f"· {t}", LABEL, INK) for t in lines)
        return card(p(name, 44, ink, f";font-family:{SERIF};font-weight:700") + body
                    + p(result, LABEL, ink, ";font-weight:800"), accent, pad="20px 24px", gap=8)
    inner = [eyebrow("Take this home · how hard to steer the model"), h2("Building agentic systems is a balancing act"),
             _steering_scale(), row(*(zone(*z) for z in BALANCE), gap=24)]
    return section("balance", inner, "Steer too tight and the model can only give you what your rules already describe: correct, safe, and every song alike. Our own riff checker would have thrown out the best riff we had; rules tuned to an older model capped a newer one; and a tool that reported one number made Pandit chase it. Steer too loose and you get plausible output with no shape: the plain prompt plays the right notes but nothing comes back; the debate rewrote half the music each turn; an older model broke the raga 92 times. The balance: code holds only what is true, the model is free on taste, and a person decides what is good.", gap=22)


LESSONS: Final = (
    ("Ask what a pattern needs, and whether your problem has it", "I gave every problem an agent. Most needed fewer."),
    ("Split by information and judgment, not job titles", "Merge parts that must fit; split rules that clash."),
    ("Let code own what's true; measure the rest", "Rules for facts. Numbers for taste, shown to a judge."),
    ("Whatever you show a model steers it", "Told too much, two composers wrote one song."),
    ("The model brings knowledge; your domain decides the design", "It knew the raga. We chose what mattered."),
    ("A person is the strongest judge", "Every model judge was a guess at one listener's ear."),
    ("Re-check the split whenever a stronger model ships", "Keep one plain call as a control. Change one thing at a time."),
)


def s_matrix() -> str:
    """The take-home (rebuilt 2026-10-20 from Sujit's list, cross-checked against TALK.md's recorded lessons):
    seven lessons in agentic decomposition, then the thesis they lead to."""
    def lesson(n: int, head: str, sub: str, span: str = "") -> str:
        return (f'<div style="background:{CARD};border:2px solid {LINE};border-radius:16px;padding:12px 22px;display:flex;'
                f'gap:16px;align-items:center{span}">'
                f'<p style="flex:none;width:46px;height:46px;border-radius:23px;background:{MUSTARD};color:{INDIGO};font-size:28px;'
                f'font-weight:800;text-align:center;line-height:46px">{n}</p>'
                f'<div style="display:flex;flex-direction:column;gap:2px">{p(head, 34, INDIGO, f";font-family:{SERIF};font-weight:700;line-height:1.15")}'
                f'{p(sub, 28, MUTED, ";line-height:1.2")}</div></div>')
    cards = [lesson(i + 1, h, s, ";grid-column:1/3" if i == len(LESSONS) - 1 else "") for i, (h, s) in enumerate(LESSONS)]
    grid = f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 22px">{"".join(cards)}</div>'
    thesis = p("No pattern is right or wrong. It is right or wrong for this model, this problem, this year.", 40, TERRA_TEXT,
               f";font-family:{SERIF};font-weight:700;line-height:1.2")
    inner = [eyebrow("Take this home"), h2("Lessons in agentic decomposition"), grid, thesis]
    return section("matrix", inner, (
        "Straight from Act 2 to here. Don't read the cards; one sentence each, pointing back. ONE (why, factors): I "
        "wanted to try every pattern, so every problem got an agent; every pattern has a precondition (debate needs "
        "different information, collaboration two real owners, a tool something new to say), so ask whether your problem "
        "has it. TWO (the first chapter, calls-choice): the riff, the hook and the form were one idea split across agents; "
        "we merged guitar and bass because they must lock, and kept the sitar's intro, theme and solo apart because their "
        "rules clash. THREE (the rules chapter, code-rules): checks gave zero illegal notes, but our riff rule, taste "
        "written as a rule, rejected our best riff; check facts, measure taste. A fact you only tell a model is a hope; "
        "code applying it is a guarantee. FOUR (comp-proof, echo, tools): a prompt that dictated the answer made two "
        "composers, even two vendors, write one piece; a judge shown numbers chased them; a listening tool made Pandit "
        "chase sway length and lose the cadence; our own 'every part plays the whole length' made the plain call never "
        "breathe. FIVE (knew, ladder): on today's model the plain call knew the raga's phrases; it played the notes but "
        "not the raga. The domain decided what matters: where phrases rest, the hook coming back, what code checks. And "
        "the rules we reasoned out were corrected by a practitioner's ear. SIX (human in the loop): the seed judge, the "
        "Producer and the debate were each a prediction of one listener, and my blind ear decided every experiment; "
        "calibrate every model judge against a person. SEVEN (the turn, rules-age): rules tuned to one model rejected the "
        "next model's best riff; keep one plain call as the control, re-run it on every release, change one thing at a "
        "time. The bottom line is the thesis: the blackboard, the debate and the judge loop each won somewhere and lost "
        "somewhere, and some lost only because the model had moved on."), gap=20)


def _model_icon() -> str:
    import scenes
    return scenes.icon("model")


def s_checklist() -> str:
    do = ["Domain facts in code, sourced and tested", "Split agents by information and judgment", "Let code measure and one judge decide",
          "Pass the user's words beside the schema", "Read the trace, not the config", "Keep one bare call as a control"]
    dont = ["Ask a model for facts from memory", "One agent per noun in the output", "Rules tuned to last year's model",
            "Debates of one mind, or over knobs", "Telling the model what code could apply", "Explaining a bug in a prompt"]
    col = lambda title, items, c, mark: card(p(title, 40, c, ";font-weight:800") + "".join(p(f"{mark} {x}", 36) for x in items), c, gap=10)
    inner = [eyebrow("Take this home"), h2("What to do on Monday"), row(col("Do", do, SKY_TEXT, "✓"), col("Don't", dont, TERRA_TEXT, "✗"), gap=32)]
    return section("checklist", inner, "Don't read it out; it's the leave-behind.")


def s_close() -> str:
    return quote("close", [f'<h1 style="font-family:{SERIF};font-size:80px;font-weight:600;line-height:1.2;color:{LIGHT}">The model supplies range.<br>'
                           f'The domain supplies shape.<br><span style="color:{MUSTARD}">The architecture decides which has authority.</span></h1>',
                           p("Sujit Kamthe · Sahaj Software · [repo link] · [contact]", BODY, SOFT)],
                 "Close on the thesis. Thank the room; questions.")


# ---- annex --------------------------------------------------------------------------------------
def s_annex_form() -> str:
    parts = [("Alap", "the slow intro, no beat", "intro"), ("Gat", "the composed hook that keeps returning", "main riff"),
             ("Antara", "a second theme, higher up", "bridge"), ("Taan", "a fast run", "solo"), ("Tihai", "a phrase played three times that lands on beat one", "final hit")]
    rows_ = "".join(f'<div style="display:flex;gap:28px;align-items:baseline;border-bottom:2px solid {LINE};padding:10px 0px">'
                    f'<p style="width:240px;font-size:40px;font-weight:800;color:{INDIGO}">{a}</p><p style="flex:1;font-size:36px;color:{INK}">{x}</p>'
                    f'<p style="width:260px;font-size:36px;color:{MUTED}">≈ {m}</p></div>' for a, x, m in parts)
    return section("annex-form", [eyebrow("Annex · for questions"), h2("The parts of a piece"), f'<div style="display:flex;flex-direction:column">{rows_}</div>',
                                  p("Rhythm runs in a repeating cycle (teentaal: 16 beats, four groups of four); everything lands on its first beat.", BODY, MUTED)],
                   "Backup for questions about the musical form. The metal equivalents are approximate.")


# ---- the deck -------------------------------------------------------------------------------------
# Human in the loop was never built into the pipeline, so it has no Act 1 adoption point: its card sits
# just before its own verdict (Sujit, 2026-10-18).
_VERDICTS: Final = [s for k in VERDICT_ORDER
                    for s in ((["p-hitl"] if k == "hitl" else []) + [f"v-{k}"] + ([f"dd-{k}"] if k in DO_DONT else []))]
ORDER: Final = ["title", "perform", "origin", "reveal", "vote", "raga", "process",
                "act1", "split-instrument", "testbed", "split-role", "split-code", "build", "turn", "why",
                "act2", "own-before", "p-collaboration", "collab-choice", "own-now", "collab-vs-debate", "comp-proof", "notes-win", "dd-debate", "balance", "stage1", "rhythm-now", "calls-choice", "stage2",
                "sc-story", "knowledge", "code-rules", "rules-age", "v-react", "stage3",
                "ev-story", "echo", "l4", "dd-evaluator", "v-hitl", "conductor-now", "stage4",
                "v-workflow", "stop-ship",
                "factors", "rebuild", "today", "ladder", "knew",
                "matrix", "payoff", "close",
                "annex-form", "l5", "l8", "trace", "worlds", "twelve", "notes1", "notes2", "notes3", "eleven", "grow1", "grow2", "grow3", "grow4",
                "grow5", "grow6", "grow7", "ui", "brief",
                "p-blackboard", "p-chaining", "band1", "band2", "p-selfcorrect", "p-react",
                "v-evaluator", "v-debate", "p-agent", "l6", "l7",
                "step3", "step4", "step5", "step6", "step7", "step8", "step9", "step10", "step11",
                "dec-composer", "dec-rhythm", "dec-judge", "dec-debate", "guardrail", "naive", "turn-evidence", "first", "two-ways", "v-collaboration", "v-orchestrator", "v-selfcorrect", "composer-calls", "prompt-job", "plan",
                "funnel", "p-hitl", "rules", "l1", "l2", "l3", "checklist", "own-test", "db-story", "redesign", "hook-fix",
                "p-orchestrator", "p-evaluator", "p-debate", "p-workflow", "own-flow"]
SECTIONS: Final = {
    "s1": {"description": "Opening: the live performance, the reveal and why a band is a fair test", "start": "title"},
    "sm": {"description": "Music 101: the twelve notes, how a raga picks from them, how a song gets made", "start": "twelve"},
    "s3": {"description": "Act 1: the first band, grown to eleven agents, and the prompt that challenged it", "start": "act1"},
    "s4": {"description": "Act 2: four investigations (ownership, rules, judgment, control), then the rebuilt band", "start": "act2"},
    "s6": {"description": "Close: what to take home, the audience's live composition", "start": "matrix"},
    "sa": {"description": "Annex: the growth beats, original build steps, do/don't tables and earlier lessons", "start": "annex-form"},
}


# The eyebrows of slides that moved in the 2026-10-19 restructure: their builders still say where they
# used to be, so the running order relabels them here (one place, instead of editing every builder).
_OWN, _JUDGE, _RULES, _CONTROL = "Act 2 · ownership", "Act 2 · judgment", "Act 2 · rules", "Act 2 · control"
EYEBROWS: Final = {
    "own-before": "@two agents or one?|Before|Problem", "own-now": "@two agents or one?|Now", "composer-calls": "Annex · how the sitar gets written", "prompt-job": "Annex · one prompt per job",
    "comp-proof": "@two agents or one?|Proof", "notes-win": "@two agents or one?|Proof", "dd-debate": "@two agents or one?|Proof", "balance": "Act 2 · two agents or one? · how hard to steer",
    "own-test": "Annex · what we can prove about the redesign", "own-flow": "Annex · one owner took the parts back",
    "hook-fix": "Annex · the hook made once, the finished part handed over", "rhythm-now": "@two agents or one?|Now", "db-story": "Annex · the debate story (judgment)",
    "redesign": "Annex · the rebuilt band, as a roster",
    "first": "Annex · the two obvious designs", "turn": "Act 1 · the challenge", "why": "Act 1 · the challenge · what we looked at",
    "p-orchestrator": "Annex · sectioning + blackboard, the pattern card",
    "p-collaboration": "Act 2 · two agents or one? · the textbook version", "p-blackboard": "Annex · the blackboard we used", "p-chaining": "Annex · prompt chaining, the pattern", "v-collaboration": "Annex · peer collaboration, the verdict", "v-orchestrator": "Annex · ownership, the verdict card", "band1": "Annex · the band after ownership",
    "p-evaluator": "Annex · evaluator–optimiser, the pattern card", "v-evaluator": "Annex · the judge, the verdict card",
    "p-debate": "Annex · debate, the pattern card", "v-debate": "Annex · the debate, the verdict card",
    "v-hitl": f"{_JUDGE} · the judge above every judge", "band2": "Annex · the band after judgment",
    "knowledge": f"{_RULES} · the rulebook", "p-selfcorrect": "Annex · self-correction, the pattern",
    "v-selfcorrect": "Annex · self-correction, the verdict card", "sc-story": f"{_RULES} · the pattern", "code-rules": f"{_RULES} · what code owns",
    "p-react": "Annex · tool use, the pattern", "v-react": f"{_RULES} · checks as tools", "p-workflow": "Annex · predefined workflow, the pattern card",
    "p-agent": "Annex · the autonomous agent, the pattern", "v-workflow": f"{_CONTROL} · the choice",
    "today": "Act 2 · the rebuilt band · tonight's workflow", "ladder": "Act 2 · the rebuilt band · against one prompt",
    "l4": "Act 2 · judgment · what the judge can't see", "l5": "Annex · the schema handoff", "l8": "Annex · the decomposition expires", "trace": "Annex · one real run, call by call",
    **{f"l{n}": "Annex · an earlier lesson" for n in (6, 7)},
    **{k: "Annex · the growth beats" for k in ("eleven", "grow1", "grow2", "grow3", "grow4", "grow5", "grow6", "grow7", "ui", "brief")},
    **{k: "Annex · the original build steps" for k in ("step3", "step4", "step5", "step6", "step7", "step8", "step9",
                                                       "step10", "step11")},
    **{k: "Annex · each stage's rivals" for k in ("dec-composer", "dec-rhythm", "dec-judge", "dec-debate", "guardrail")},
    "naive": "Annex · the question we used to open with", "turn-evidence": "Annex · backup: every guitar stroke, both songs", "two-ways": "Annex · each pattern as an agent",
    "dd-evaluator": f"{_JUDGE} · what we learned",
    "funnel": "Annex · the debate's funnel", "p-hitl": "Annex · human in the loop, the pattern",
    **{f"l{n}": "Annex · an earlier lesson" for n in (1, 2, 3)},
    "plan": "Annex · one real run: the comparison kept the draft", "checklist": "Annex · the checklist",
}
# Which band is on screen (Sujit, 2026-10-20: the four-beat tracker showed every beat at once in different colours
# and confused more than it helped). One badge per slide, one era: the first band or tonight's band; evidence slides take a plain eyebrow.
ERAS: Final = {"Before": ("The first band", TERRA, LIGHT, ("pandit", "riffsmith")),
               "Problem": ("The first band", TERRA, LIGHT, ("pandit", "riffsmith")),
               "Now": ("Tonight's band", SKY, INDIGO, ("composer", "rhythm"))}


def tracker(chapter: str, *lit: str) -> str:
    """The eyebrow of an Act 2 chapter slide: one era badge (with the band's faces), then the chapter's name. A row
    container, not a <p>: the Slides format forbids an <img> inside a text block."""
    if lit[0] not in ERAS:   # evidence slides need no badge (Sujit, 2026-10-20): a plain eyebrow
        return eyebrow(f"Act 2 · {chapter}")
    label, fill, ink, faces = ERAS[lit[0]]
    pics = "".join(persona(f, 0.62) for f in faces)
    text = "font-size:32px;font-weight:800;letter-spacing:4px;text-transform:uppercase"
    badge = (f'<div style="display:flex;align-items:center;gap:8px;background:{fill};border-radius:999px;'
             f'padding:2px 22px 2px {14 if faces else 22}px;border:3px solid {INDIGO if fill == CARD else fill}">'
             f'{pics}<p style="{text};color:{ink}">{label}</p></div>')
    return (f'<div style="display:flex;align-items:center;gap:18px">{badge}'
            f'<p style="{text};color:{MUTED}">{chapter}</p></div>')


_EYEBROW_TAG: Final = re.compile(r'(<p style="font-size:32px;font-weight:800;letter-spacing:4px;text-transform:uppercase;[^"]*">)(.*?)(</p>)')


def _relabel(sid: str, html: str) -> str:
    new = EYEBROWS.get(sid)
    if new and new.startswith("@"):
        chapter, *lit = new[1:].split("|")
        return _EYEBROW_TAG.sub(lambda m: tracker(chapter.capitalize(), *lit), html, count=1)
    return _EYEBROW_TAG.sub(lambda m: m.group(1) + new + m.group(3), html, count=1) if new else html


def slides() -> dict[str, str]:
    out = dict(title_slides())
    out.update({"perform": s_perform(), "reveal": s_reveal(), "testbed": s_testbed(), "twelve": s_twelve(),
                "notes1": s_notes(1), "notes2": s_notes(2), "notes3": s_notes(3), "raga": s_raga(), "process": s_process(), "ui": s_ui(), "brief": s_brief(), "naive": s_naive(),
                "rules": s_rules(), "vote": s_vote(), "act1": s_act1(), "first": s_first(), "knowledge": s_knowledge(),
                "guardrail": s_guardrail(), "eleven": s_eleven(), "act2": s_act2(), "turn": s_turn(), "turn-evidence": s_turn_evidence(), "why": s_why(),
                "redesign": s_redesign(), "ladder": s_ladder(), "knew": s_knew(), "l1": s_l1(), "l2": s_l2(), "l3": s_l3(), "l4": s_l4(),
                "l5": s_l5(), "l6": s_l6(), "l7": s_l7(), "l8": s_l8(), "trace": s_trace(), "plan": s_plan(), "matrix": s_matrix(), "balance": s_balance(),
                "checklist": s_checklist(), "close": s_close(), "annex-form": s_annex_form()})
    out.update({f"step{st[0]}": s_step(*st) for st in STEPS})
    out.update({g[0]: s_grow(*g) for g in GROWTH})
    out.update({"build": s_build(), "payoff": s_payoff(), "own-flow": s_own_flow(), "composer-calls": s_composer_calls(), "origin": s_origin(), "worlds": s_worlds(), "own-test": s_own_test(), "rules-age": s_rules_age(), "prompt-job": s_prompt_job(), "echo": s_echo(), "stop-ship": s_stop_ship(), "factors": s_factors(),
                "split-instrument": s_split_instrument(), "split-role": s_split_role(), "split-code": s_split_code(),
                "band1": s_band("band1", 1, "Chapter one's decision on the band. The idea needed one owner: Pandit writes "
                                "the plan, the hook and every sitar note; the Riff's job went to the Rhythm section, "
                                "which joins and writes guitar and bass after hearing the finished sitar line. The Arranger's "
                                "job became a measurement; the Orchestra plays only symphonic pieces."),
                "band2": s_band("band2", 2, "Chapter two's decision. The Producer is the one judge, Rasik advises (the two judge apart), and the "
                                "Conductor's job became a round limit in code; a revision is kept only if it wins.")})
    out.update({f"p-{k}": s_pattern(k) for k in INTRO_ORDER})
    out.update({f"v-{k}": s_verdict(k) for k in VERDICT_ORDER})
    out["v-workflow"] = s_workflow_choice()   # contrast first, then the decision
    out["p-collaboration"] = s_pattern("collaboration", full=False)   # the comparison has its own slide
    out["collab-choice"] = s_collab_choice()
    out["calls-choice"] = s_calls_choice()
    out["conductor-now"] = s_conductor_now()
    out["sc-story"] = s_sc_story()
    out["code-rules"] = s_code_rules()
    out.update({f"dd-{k}": s_dodont(k) for k in DO_DONT})
    out.update({"today": s_today(), "own-before": s_own_before(), "own-now": s_own_now(), "rhythm-now": s_rhythm_now(), "comp-proof": s_comp_proof(), "collab-vs-debate": s_collab_vs_debate(), "hook-fix": s_hook_fix(),
                **{f"stage{n}": s_stage(n, f"stage{n}") for n in (1, 2, 3, 4)}, "rebuild": s_stage(5, "rebuild"), "notes-win": s_notes_win(), "ev-story": s_ev_story(), "db-story": s_db_story(), "funnel": s_funnel(), "two-ways": s_two_ways(), **{f"dec-{k}": s_decision(k) for k in DECISIONS}})
    out = {sid: _relabel(sid, html) for sid, html in out.items()}
    return out


def check(sid: str, html: str) -> None:
    """The viewer's hard limits, learned on the pixel deck: empty unpainted divs vanish, padding
    caps at 256 px, a clip must be top-level and painted last."""
    for m in re.finditer(r'<div style="([^"]*)"></div>', html):
        if not any(k in m.group(1) for k in ("background", "border")):
            raise SystemExit(f"{sid}: empty spacer div; the viewer drops these")
    for m in re.finditer(r'<p(?:\s[^>]*)?>((?:(?!</p>).)*?)</p>', html, re.S):
        if re.search(r'<(img|div|svg)\b', m.group(1)):
            raise SystemExit(f"{sid}: an image or block inside a <p>; the Slides format rejects it")
    for v in re.findall(r"padding:[^;\"]*?(\d+)px", html):
        if int(v) > 256:
            raise SystemExit(f"{sid}: padding {v}px exceeds 256")
    if "data-video" in html:
        tail = html[html.index(">", html.rindex("data-video")) + 1:html.index("<aside>")]
        if re.search(r"<(div|p|img|svg|h\d)\b", tail):
            raise SystemExit(f"{sid}: something is painted above the last clip")


def main() -> None:
    built = slides()
    assert list(built) == [s for s in ORDER if s in built] or set(built) == set(ORDER), "ORDER and slides disagree"
    for sid, html in built.items():
        check(sid, html)
        (SLIDES / f"{sid}.html").write_text(html)
    deck = json.loads((HERE / "project" / "deck.json").read_text())
    deck.update({"title": "Lessons from an Agentic AI Raga-Metal Band", "order": ORDER, "sections": SECTIONS, "faces": FACES})
    (HERE / "project" / "deck.json").write_text(json.dumps(deck, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {len(built)} slides")


if __name__ == "__main__":
    main()
