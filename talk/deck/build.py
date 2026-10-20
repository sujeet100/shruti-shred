"""LEGACY (pixel deck, retired 2026-10-18 — the live deck is story.py). Built the Shruti Shred deck: one HTML file per slide under project/slides/.

The slides are a Claude Slides artifact (1920x1080, inline-style subset). This file is the
source of truth for their content; it keeps one type scale so text stays readable on a LED
wall, and reads the uploaded-asset maps for sprites and audio clips.

    python3 talk/deck/build.py && python3 talk/deck/preview.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLIDES = HERE / "project" / "slides"
EMBEDS = HERE / "embeds"
SPRITE_URLS: dict[str, str] = json.loads((HERE.parent / "sprites" / "assets.json").read_text())
sys.path.insert(0, str(HERE.parents[1] / "src"))
from raga import RAGAS  # noqa: E402  (the encoded, source-verified raga facts)
from title_slides import title_slides  # noqa: E402  (the Sahaj-themed title slides)

AUDIO_MAP = HERE.parent / "audio" / "assets.json"
AUDIO: dict[str, dict[str, str]] = json.loads(AUDIO_MAP.read_text()) if AUDIO_MAP.exists() else {}

# ---- design tokens ---------------------------------------------------------
HEAD = "'Press Start 2P', 'Courier New', monospace"
BODY = "'JetBrains Mono', 'Courier New', monospace"
CODE = "'JetBrains Mono', 'Courier New', monospace"  # VT323 retired 2026-10-18: its face slot went to Mulish
DEVA = "'Noto Sans Devanagari', sans-serif"
BG, PANEL, LINE = "#08070d", "#191426", "#2a2138"
GOLD, GOLDHI, SAFFRON, MAGENTA, CYAN = "#f2b53c", "#ffd97a", "#d9702a", "#ff2e88", "#38e0cf"
INK, TEXT, DIM, FAINT, VIOLET, SYS = "#ece5d3", "#d8d0c0", "#8c8399", "#574f68", "#4a3f6b", "#7d7690"
GLOW = "radial-gradient(ellipse at 50% 0%, #1b1530 0%, #08070d 60%)"
SCAN = "repeating-linear-gradient(0deg, #0c0a14 0px, #0c0a14 2px, #08070d 2px, #08070d 4px)"
# type scale (px) — nothing on a slide goes below SMALL
H1, H2, EYE, BIG, BODYPX, LABEL, SMALL = 64, 48, 36, 44, 40, 36, 32

LINEUP = ["interpreter", "pandit", "riffsmith", "lead", "riff", "orchestra",
          "arranger", "ustad", "rasik", "producer", "conductor"]
NAMES = {"interpreter": "Interpreter", "pandit": "Pandit", "riffsmith": "Riffsmith", "lead": "Lead",
         "riff": "Riff", "orchestra": "Orchestra", "arranger": "Arranger", "ustad": "Ustad",
         "rasik": "Rasik", "producer": "Producer", "conductor": "Conductor"}
ROLE = {"interpreter": SYS, "pandit": GOLD, "riffsmith": GOLD, "lead": SAFFRON, "riff": SAFFRON,
        "orchestra": SAFFRON, "arranger": GOLDHI, "ustad": MAGENTA, "rasik": MAGENTA,
        "producer": MAGENTA, "conductor": CYAN}


# ---- primitives ------------------------------------------------------------
EYE_RE = re.compile(r'<p style="font-family:[^"]*;font-size:36px;font-weight:600;letter-spacing:4px;text-transform:uppercase;color:(#[0-9a-f]+)">(.*?)</p>')
H2_RE = re.compile(r'<h2 style="font-family:[^"]*;font-size:(\d+)px;font-weight:400;line-height:1.35;color:(#[0-9a-f]+)">(.*?)</h2>')


def _is_pinned(item: str) -> bool:
    head = item.lstrip()
    return head.startswith("<x-embed") or "position:absolute" in head.split(">", 1)[0]


def section(sid: str, inner: str | list[str], notes: str, *, bg: str = GLOW, pad: str = "96px 128px",
            gap: int = 32, justify: str = "start", transition: str = "fade", color: str = INK,
            flow_top: int | None = None, flow_bottom: int = 984) -> str:
    """A slide. Standard slides pin their eyebrow + headline at fixed coordinates and place all
    flowing content in ONE explicitly positioned container below them, so nothing depends on
    an empty spacer div (the viewer drops those) or on how tall the header renders."""
    items = [x for x in (inner if isinstance(inner, list) else [inner]) if x and x.strip()]
    if pad == "96px 128px":
        eye = next((x for x in items if EYE_RE.fullmatch(x.strip())), None)
        h2 = next((x for x in items if H2_RE.fullmatch(x.strip())), None)
        header, top = [], 264
        if eye and h2:
            e, h = EYE_RE.fullmatch(eye.strip()), H2_RE.fullmatch(h2.strip())
            size, text = int(h.group(1)), h.group(3)
            lines = max(1, math.ceil(len(re.sub(r"<[^>]+>|&[a-z]+;", "x", text)) * size / 1640))
            header = [f'<p style="position:absolute;left:128px;top:96px;width:1664px;font-size:{EYE}px;font-weight:600;letter-spacing:4px;'
                      f'text-transform:uppercase;color:{e.group(1)}">{e.group(2)}</p>',
                      f'<h2 style="position:absolute;left:128px;top:150px;width:1664px;font-family:{HEAD};font-size:{size}px;font-weight:400;'
                      f'line-height:1.35;color:{h.group(2)}">{text}</h2>']
            top = 150 + lines * round(size * 1.35) + 50
            items = [x for x in items if x not in (eye, h2)]
        top = flow_top or top
        pinned = [x for x in items if _is_pinned(x)]
        flow = [x for x in items if not _is_pinned(x)]
        box = (f'<div style="position:absolute;left:128px;top:{top}px;width:1664px;height:{flow_bottom - top}px;display:flex;'
               f'flex-direction:column;gap:{gap}px;justify-content:{justify}">{"".join(flow)}</div>') if flow else ""
        items = header + ([box] if box else []) + pinned
    # A clip must be the topmost thing on its slide or something transparent above it swallows
    # the click (the flow container did exactly that), so every player is emitted last.
    items = [x for x in items if "data-video" not in x] + [x for x in items if "data-video" in x]
    body = "\n".join(items)
    return (f'<section id="{sid}" data-transition="{transition}" style="background:{bg};color:{color};'
            f"font-family:{BODY};padding:{pad};display:flex;flex-direction:column;"
            f'justify-content:{justify};gap:{gap}px">\n{body}\n<aside>{notes}</aside>\n</section>\n')


def eyebrow(text: str, color: str = GOLD) -> str:
    return (f'<p style="font-family:{BODY};font-size:{EYE}px;font-weight:600;letter-spacing:4px;'
            f'text-transform:uppercase;color:{color}">{text}</p>')


def headline(text: str, size: int = H2, color: str = INK, width: int | None = None, tag: str = "h2") -> str:
    w = f";width:{width}px" if width else ""
    return (f'<{tag} style="font-family:{HEAD};font-size:{size}px;font-weight:400;line-height:1.35;'
            f'color:{color}{w}">{text}</{tag}>')


def p(text: str, size: int = BODYPX, color: str = TEXT, extra: str = "") -> str:
    return f'<p style="font-size:{size}px;line-height:1.2;color:{color}{extra}">{text}</p>'


def label(text: str, color: str, size: int = LABEL) -> str:
    return f'<p style="font-size:{size}px;font-weight:600;letter-spacing:2px;color:{color}">{text}</p>'


def panel(inner: str, border: str = LINE, *, pad: str = "28px", gap: int = 14, extra: str = "",
          bg: str = PANEL, width: str = "flex:1") -> str:
    return (f'<div style="{width};background:{bg};border:4px solid {border};box-shadow:8px 8px 0px #000000;'
            f'padding:{pad};display:flex;flex-direction:column;gap:{gap}px{extra}">{inner}</div>')


def row(*items: str, gap: int = 32, align: str = "stretch", extra: str = "") -> str:
    return f'<div style="display:flex;gap:{gap}px;align-items:{align}{extra}">{"".join(items)}</div>'


def sprite(name: str, x: int, y: int, scale: int = 3, build: str | None = None, opacity: float | None = None) -> str:
    """A persona sprite (48x64 grid) pinned at integer scale, optionally with a build-in."""
    b = f' data-build-in="{build}"' if build else ""
    o = f";opacity:{opacity}" if opacity is not None else ""
    return (f'<img{b} src="{SPRITE_URLS[name]}" alt="{NAMES.get(name, name)}" style="position:absolute;'
            f'left:{x}px;top:{y}px;width:{48 * scale}px;height:{64 * scale}px;object-fit:contain{o}">')


def img(name: str, w: int, h: int, alt: str) -> str:
    return f'<img src="{SPRITE_URLS[name]}" alt="{alt}" style="width:{w}px;height:{h}px;object-fit:contain">'


def embed(name: str, x: int, y: int, w: int, h: int, replace: dict[str, str] | None = None, bg: str = "#120f1d") -> str:
    """A live animation with an explicitly painted backdrop (the viewer paints unpainted
    embeds white), plus a matching painted div behind it so the edge never shows."""
    body = (EMBEDS / f"{name}.html").read_text().replace("background:transparent", f"background:{bg}")
    for a, b2 in (replace or {}).items():
        body = body.replace(a, b2)
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;background:{bg}"></div>'
            f'<x-embed style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px">{body}</x-embed>')


def audio(clip: str, x: int, y: int, w: int = 480, h: int = 100, caption: str = "") -> str:
    """A click-to-play clip: the video frame is a TOP-LEVEL pinned <img data-video> (the only
    form the deck treats as a playable clip); its caption is a separate pinned label above it."""
    cap = (f'<p style="position:absolute;left:{x}px;top:{y - 46}px;width:{w}px;text-align:right;font-size:{SMALL}px;'
           f'white-space:nowrap;color:{CYAN}">▶ {caption}</p>') if caption else ""
    if clip in AUDIO:
        a = AUDIO[clip]
        media = (f'<img src="{a["still"]}" data-video="{a["video"]}" data-video-sound="on" data-video-start="click" '
                 f'alt="Audio clip {clip}: {caption}" style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
                 f'object-fit:cover;border:4px solid {CYAN}">')
    else:
        media = (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;background:#120f1d;border:4px dashed {CYAN};'
                 f'display:flex;align-items:center;justify-content:center"><p style="font-size:{SMALL}px;color:{CYAN}">AUDIO {clip} · pending</p></div>')
    return cap + media


def do_dont(dos: list[str], donts: list[str], width: str = "flex:1") -> str:
    items = "".join(p("✓ " + d, BODYPX, INK) for d in dos) + "".join(p("✗ " + d, BODYPX, DIM) for d in donts)
    return panel(items, GOLD, gap=18, width=width)


def bit_us(text: str) -> str:
    return panel(p(f'<span style="color:{MAGENTA}">WHAT BIT US</span> · {text}', BODYPX, TEXT), MAGENTA,
                 pad="22px 26px", width="")


def stage_bar(n: int, total: int = 3) -> str:
    cells = "".join(f'<div style="width:140px;height:28px;background:{GOLD if i < n else "#120f1d"};'
                    f'border:3px solid {GOLDHI if i < n else LINE}"></div>' for i in range(total))
    return f'<div style="display:flex;gap:16px">{cells}</div>'


def case(symptom: str, evidence: str, decision: str, rule: str) -> str:
    cards = row(panel(label("SYMPTOM", MAGENTA) + symptom, MAGENTA, width="flex:3"),
                panel(label("EVIDENCE", CYAN) + evidence, CYAN, width="flex:6"),
                panel(label("DECISION", GOLD) + decision, GOLD, width="flex:3"), gap=28, extra=";flex:1")
    return cards + p(rule, BIG, GOLD)


# ---- slides ----------------------------------------------------------------
def s_cover() -> str:
    inner = [f'<div style="position:absolute;left:0px;top:948px;width:1920px;height:132px;background:#120f1d;border-top:4px solid {LINE}"></div>',
             eyebrow("Raga × metal × agents"),
             f'<h1 style="font-family:{HEAD};font-size:104px;font-weight:400;line-height:1.1;color:{INK};text-shadow:8px 8px 0px {MAGENTA}">SHRUTI SHRED</h1>',
             p("What domain knowledge does to an agentic system", 56, INK),
             p("Sujit Kamthe · [event · date]", BODYPX, DIM)]
    inner.insert(0, f'<div style="position:absolute;left:0px;top:740px;width:1920px;height:208px;background:#120f1d"></div>')
    inner.append(embed("band", 127, 756, 1665, 192))
    return section("cover", inner, "On screen while the room fills. The band takes turns at 128 BPM: each character gets four beats under a spotlight (the Conductor swings, the Riff and Riffsmith headbang, the Lead plucks, the Producer rides the faders), then hands over to the next. Guitar plugged in, in-ears on, backing track cued in Logic Pro. Advance to the performance slide and play.",
                   bg="radial-gradient(ellipse at 50% 22%, #241b3d 0%, #08070d 68%)", pad="96px 128px 96px 128px", gap=28)


def s_perform() -> str:
    seg = lambda n, flex, c: f'<div style="flex:{flex};border:4px solid {c};padding:14px 16px"><p style="font-family:{HEAD};font-size:22px;color:{c}">{n}</p></div>'
    inner = [p("Raga Bhairav · heavy metal · teentaal · 128 BPM · Sa = E", BIG, DIM),
             f'<div style="height:6px;background:{GOLD}"></div>',
             row(seg("ALAP", 1, CYAN), seg("GAT", 2, GOLD), seg("CALL · ANSWER", 2, SAFFRON), seg("TAAN", 2, MAGENTA), seg("TIHAI", 1, GOLDHI), gap=10),
             f'<div style="display:flex;justify-content:space-between">{p("0:00", LABEL, FAINT)}{p("0:30", LABEL, FAINT)}{p("1:00", LABEL, FAINT)}</div>']
    return section("perform", inner, "0:00–1:00. A01, presenter click. Play; say nothing first; no agent trace on screen. One 16-beat cycle = 7.5 s at 128 BPM. 0:00 alap over the drone, stand ready. 0:07.5 gat for two cycles, enter on the first sam with the written riff. 0:22.5 call and response, leave space for the sitar's answer (gaps cut in Logic Pro). 0:37.5 taan climax. 0:52.5 tihai lands on the final sam: hit it together, stop, hold black about a second. The drone is the entry cue. Fallback A12: the recorded performance, framed identically.",
                   bg=BG, pad="128px", gap=40, justify="center")


def s_reveal() -> str:
    inner = [headline("ELEVEN AGENTS COMPOSED WHAT YOU JUST HEARD.", H2)]
    for i, n in enumerate(LINEUP):
        rw, k = divmod(i, 6)
        per = 6 if rw == 0 else len(LINEUP) - 6
        x = 960 - per * 140 + k * 280 + 68
        y = 250 + rw * 300
        inner.append(sprite(n, x, y, 3, build=f"pop {i + 1} auto"))
        inner.append(f'<p data-build-in="pop {i + 1} auto" style="position:absolute;left:{x + 72 - 140}px;top:{y + 200}px;width:280px;'
                     f'text-align:center;font-size:{LABEL}px;font-weight:600;color:{ROLE[n]}">{NAMES[n]}</p>')
    inner.append(f'<p data-build-in="rise 12" style="position:absolute;left:128px;top:860px;width:1664px;font-size:64px;line-height:1.1;color:{GOLD}">I played the riff they wrote.</p>')
    return section("reveal", inner, "1:00–1:45. Let the silence land after the tihai. The band pops on one by one by itself, each with its name. Click for the last line. \"I didn't write that riff. Eleven agents did, and I learned it off their output. I'm the session guitarist tonight.\" Fifteen seconds on who you are, then: \"This talk is about how we got that to work, and the parts that didn't.\"",
                   bg="radial-gradient(ellipse at 50% 55%, #1d1733 0%, #08070d 70%)", pad="110px 128px")


def s_hindustani() -> str:
    def layer(n: int, x: int, c: str, art: str, title: str, text: str) -> str:
        return (f'<div data-build-in="rise {n}" style="position:absolute;left:{x}px;top:264px;width:528px;height:520px;background:{PANEL};'
                f'border:4px solid {c};box-shadow:8px 8px 0px #000000;padding:28px;display:flex;flex-direction:column;gap:14px">'
                f'<div style="height:230px;display:flex;align-items:center;justify-content:center">{art}</div>'
                f'{label(title, c)}{p(text, BODYPX, TEXT)}</div>')
    inner = [eyebrow("Hindustani music"), headline("WHAT YOU HEARD UNDER MY GUITAR"),
             layer(1, 128, CYAN, img("tanpura", 62, 230, "Tanpura"), "DRONE · tanpura", "Holds Sa, the home note, the whole time."),
             layer(2, 696, SAFFRON, img("sitar", 460, 138, "Sitar"), "MELODY · sitar", "Improvises inside the raga's grammar."),
             layer(3, 1264, MAGENTA, img("tabla", 320, 192, "Tabla"), "CYCLE · tabla", "Keeps the tala, a repeating beat cycle."),
             audio("A02", 1312, 850, 480, 90, "drone, sitar, tabla")]
    return section("hindustani", inner, "Under 40 seconds. Click the clip (A02: drone 4 s, sitar joins, tabla joins) and click each panel in as you hear its layer. Line to land: \"The system has to coordinate three different kinds of time.\" Hindustani is the North Indian tradition; Carnatic, from the South, shares raga names but differs in ragas and rhythm, and we treat a Carnatic source as a red flag.")


DEV = {"S": "सा", "r": "रे", "R": "रे", "g": "ग", "G": "ग", "m": "म", "M": "म॑", "P": "प", "d": "ध", "D": "ध", "n": "नि", "N": "नि"}
LAT = {"S": "Sa", "r": "re", "R": "Re", "g": "ga", "G": "Ga", "m": "ma", "M": "Ma", "P": "Pa", "d": "dha", "D": "Dha", "n": "ni", "N": "Ni"}
KOMAL = set("rgdn")


def dev(sw: str, upper: bool = False) -> str:
    """One swara in Bhatkhande-style Devanagari: komal underlined, upper Sa as सां."""
    if upper and sw == "S":
        return "सां"
    return f"<u>{DEV[sw]}</u>" if sw in KOMAL else DEV[sw]


def phrase(sws: list[str]) -> str:
    return " ".join(dev(x) for x in sws)


def audio_built(clip: str, x: int, y: int, w: int, h: int, caption: str, build: str) -> str:
    """A clip that appears on a click, with its caption, instead of sitting on the slide from the start."""
    return audio(clip, x, y, w, h, caption).replace('<p style=', f'<p data-build-in="{build}" style=', 1).replace('<img ', f'<img data-build-in="{build}" ', 1)


def term_box(x: int, w: int, deva: str, latin: str, text: str, c: str, build: str, top: int = 700, h: int = 160, stacked: bool = False) -> str:
    """A Hindustani term: the Devanagari word first, its romanisation, then what it means.
    `stacked` puts the romanisation under the Devanagari, for terms too long to share a line."""
    head = (f'<p style="font-family:{DEVA};font-size:44px;line-height:1.2;color:{c}">{deva}</p>'
            f'<p style="font-family:{HEAD};font-size:20px;color:{c}">{latin}</p>')
    if not stacked:
        head = f'<div style="display:flex;gap:16px;align-items:baseline">{head}</div>'
    return (f'<div{_built(build)} style="position:absolute;left:{x}px;top:{top}px;width:{w}px;height:{h}px;background:{PANEL};border:4px solid {c};'
            f'box-shadow:8px 8px 0px #000000;padding:12px 20px;display:flex;flex-direction:column;gap:{8 if stacked else 4}px">'
            f'{head}{p(text, 32, TEXT)}</div>')


# ---- The twelve notes: a keyboard drawn by the clip itself, in sync with its sound -------
# One drawing serves both the slide and the frames of the clips (talk/audio/keyboard_video.py):
# each key appears or lights at the moment its note sounds, so the clip starts with its slide
# and there is no player to click.
KB_X0, KB_W, KB_H, KB_BW, KB_BH, KB_Y = 236, 206, 340, 124, 210, 290
KB_REGION = (228, 282, 1460, 356)            # x, y, w, h of the keyboard on the slide = the clip's crop
KB_WHITES = [("S", "सा", "Sa"), ("R", "रे", "Re"), ("G", "ग", "Ga"), ("m", "म", "Ma"), ("P", "प", "Pa"), ("D", "ध", "Dha"), ("N", "नि", "Ni")]
KB_BLACKS = [("r", 0, "<u>रे</u>", "re", MAGENTA), ("g", 1, "<u>ग</u>", "ga", MAGENTA), ("M", 3, "म॑", "Ma", CYAN),
             ("d", 4, "<u>ध</u>", "dha", MAGENTA), ("n", 5, "<u>नि</u>", "ni", MAGENTA)]
KB_SHUDDHA = {k for k, *_ in KB_WHITES}
KB_KOMAL = {"r", "g", "d", "n"}


def keyboard(visible: set[str], lit: str | None = None, achal: bool = False) -> list[str]:
    """The twelve keys as pinned divs: `visible` keys drawn, `lit` one glowing, `achal` rings
    Sa and Pa in gold. White keys first, so the black keys sit on top of them."""
    out: list[str] = []
    for i, (k, d, l) in enumerate(KB_WHITES):
        if k not in visible:
            continue
        on, ring = k == lit, achal and k in ("S", "P")
        bg, fg, sub = (GOLD, BG, BG) if on else (INK, BG, "#8a5a10" if ring else VIOLET)
        out.append(f'<div style="position:absolute;left:{KB_X0 + i * KB_W}px;top:{KB_Y}px;width:{KB_W - 8}px;height:{KB_H}px;background:{bg};'
                   f'border:{8 if ring else 4}px solid {GOLD if ring else "#8c8399"};display:flex;flex-direction:column;justify-content:end;align-items:center;'
                   f'padding:0px 0px {12 if ring else 16}px 0px"><p style="font-family:{DEVA};font-size:52px;line-height:1.2;color:{fg}">{d}</p>'
                   f'<p style="font-size:30px;color:{sub}">{l}</p></div>')
    for k, after, d, l, c in KB_BLACKS:
        if k not in visible:
            continue
        on = k == lit
        x = KB_X0 + (after + 1) * KB_W - KB_BW // 2 - 4
        out.append(f'<div style="position:absolute;left:{x}px;top:{KB_Y}px;width:{KB_BW}px;height:{KB_BH}px;background:{c if on else PANEL};'
                   f'border:4px solid {c};display:flex;flex-direction:column;justify-content:end;align-items:center;padding:0px 0px 12px 0px">'
                   f'<p style="font-family:{DEVA};font-size:44px;line-height:1.2;color:{BG if on else c}">{d}</p>'
                   f'<p style="font-size:30px;color:{BG if on else c}">{l}</p></div>')
    return out


def autoclip(clip: str, alt: str) -> str:
    """A clip that starts by itself as its slide opens (after the transition), sound on,
    pinned exactly over the keyboard it draws."""
    x, y, w, h = KB_REGION
    if clip not in AUDIO:
        return f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;border:4px dashed {CYAN}"><p style="font-size:32px;color:{CYAN}">CLIP {clip} · pending</p></div>'
    a = AUDIO[clip]
    return (f'<img src="{a["still"]}" data-video="{a["video"]}" data-video-sound="on" data-video-delay="0.8" alt="{alt}" '
            f'style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;object-fit:cover">')


KB_TERMS = [("शुद्ध", "SHUDDHA", "natural · the white keys", INK), ("कोमल", "KOMAL", "flat · a line below", MAGENTA),
            ("तीव्र", "TIVRA", "sharp · only Ma", CYAN), ("अचल", "ACHAL", "Sa and Pa never move", GOLD)]


def _twelve_head(pop: bool) -> list[str]:
    return [eyebrow("Hindustani music · twelve notes"), headline("HOW MANY NOTES IN AN OCTAVE?"),
            f'<p{" data-build-in=\"pop 1\"" if pop else ""} style="position:absolute;left:1560px;top:120px;width:232px;font-family:{HEAD};font-size:112px;color:{GOLD};text-shadow:6px 6px 0px {SAFFRON}">12</p>']


def s_twelve() -> str:
    return section("twelve", _twelve_head(pop=True), "Hindustani is the North Indian classical tradition; Carnatic, from the South, shares raga names but differs in ragas and rhythm, and we treat a Carnatic source as a red flag. Ask the room: how many notes are there in an octave? Take a few answers (people often say 7 or 8), then CLICK: 12. Then advance: the next three slides play by themselves, each key appearing as its note sounds.")


def s_notes(n: int) -> str:
    """Stage n of the twelve: 1 = the shuddha notes up and down, 2 = each shuddha note then its
    komal, 3 = shuddha Ma then tivra Ma, then Sa and Pa ringed as achal."""
    clip, alt, notes = [
        ("K1", "The seven shuddha keys appear one by one as Sa to upper Sa plays, then light again on the way down",
         "Plays by itself (about 8 s): the seven shuddha (natural) notes, Sa up to upper Sa and back down, each key appearing as it sounds. These are the white keys."),
        ("K2", "Each shuddha key lights, then its komal key appears beside it as the flat note plays",
         "Plays by itself (about 9 s): each natural note, then its komal (flat) version appears and sounds: Re re, Ga ga, Dha dha, Ni ni. Komal is written with a line below."),
        ("K3", "Ma lights, tivra Ma appears and sounds, resolving to Pa; then Sa and Pa are ringed in gold as they play",
         "Plays by itself (about 10 s): Ma, then tivra (sharp) Ma, the only note that goes up, resolving to Pa. Then Sa and Pa sound and are ringed in gold: they're achal, immovable. With Sa on C every komal and tivra note is a black key. A raga is a choice from these twelve; the next slide shows that choice.")][n - 1]
    inner = _twelve_head(pop=False) + [autoclip(clip, alt)]
    for i, (d, l, t, c) in enumerate(KB_TERMS[: n + (1 if n == 3 else 0)]):
        new = i >= n - 1
        inner.append(term_box(128 + i * 420, 404, d, l, t, c, "fade 1 auto" if new else None, top=740))
    return section(f"notes{n}", inner, notes)


def s_raga() -> str:
    b = RAGAS["bhairav"]
    chroma = ["S", "r", "R", "g", "G", "m", "M", "P", "d", "D", "n", "N"]
    tw, tg, ty = 127, 12, 256
    inner = [eyebrow("Raga"), headline("A RAGA CHOOSES ITS NOTES")]
    for i, sw in enumerate(chroma):
        x = 128 + i * (tw + tg)
        glyph = "म॑" if sw == "M" else dev(sw)
        inner.append(f'<div style="position:absolute;left:{x}px;top:{ty}px;width:{tw}px;height:124px;background:#120f1d;border:3px solid {LINE};'
                     f'display:flex;flex-direction:column;align-items:center;justify-content:center">'
                     f'<p style="font-family:{DEVA};font-size:46px;line-height:1.2;color:{FAINT}">{glyph}</p>{p(LAT[sw], 28, FAINT)}</div>')
        if sw in b["allowed"]:
            inner.append(f'<div data-build-in="{"pop 1" if sw == "S" else "pop 0 auto"}" style="position:absolute;left:{x}px;top:{ty}px;width:{tw}px;height:124px;background:{GOLD};border:4px solid {INK};'
                         f'box-shadow:6px 6px 0px #000000;display:flex;flex-direction:column;align-items:center;justify-content:center">'
                         f'<p style="font-family:{DEVA};font-size:46px;line-height:1.2;color:{BG}">{glyph}</p>{p(LAT[sw], 28, BG)}</div>')
    inner = [x.replace('data-build-in="pop 0 auto"', 'data-build-in="pop 2 auto"') for x in inner]
    inner.append(f'<p data-build-in="fade 3 auto" style="position:absolute;left:128px;top:400px;width:1664px;font-size:{LABEL}px;color:{GOLD}">Bhairav keeps {len(b["allowed"])} of the 12. The rest are illegal in it.</p>')
    cards = [("स्वर", "SWARA", "Which notes it allows.", GOLD),
             ("आरोह · अवरोह", "AROHA · AVAROHA", "The way up and down.", CYAN),
             ("वादी · संवादी", "VADI · SAMVADI", "Its two strongest notes.", MAGENTA),
             ("पकड़ · चलन", "PAKAD · CHALAN", "Catchphrase, movement.", SAFFRON),
             ("आंदोलन · मींड", "ANDOLAN · MEEND", "A slow sway, a glide.", GOLDHI),
             ("रस", "RASA", "Its mood.", SYS)]
    for i, (d, l, t, c) in enumerate(cards):
        inner.append(term_box(128 + (i % 3) * 568, 528, d, l, t, c, f"rise {4 + i}", top=476 + (i // 3) * 200, h=180, stacked=True))
    inner += [p(f'<span style="color:{GOLD}">KEY</span> · where Sa sits. Tonight, Sa = E.', BODYPX, TEXT).replace('<p style="', '<p data-build-in="fade 10" style="position:absolute;left:128px;top:912px;width:1100px;', 1),
              audio("A04", 1312, 924, 480, 70, "plain Re, then andolan")]
    return section("raga", inner, "About 60 seconds. CLICK: of the twelve notes from the last slide, Bhairav keeps seven (they light up, from the raga data): komal re and komal dha, with shuddha Ga, Ma and Ni. The other five are illegal in Bhairav; that is the part a validator can check. Then the point of the slide: a raga is far more than a scale. Two ragas can share the same notes and still be different ragas (Bhimpalasi and Bageshree are both Dorian). CLICK each card in as you name it: the notes, the way up and down, the important notes, the catchphrase and movement, the ornaments (play A04: a plain komal Re, then the same note with andolan), and the mood. The next slide fills every one in for Bhairav. CLICK: the key, where Sa sits.", gap=26)


def s_bhairav() -> str:
    b = RAGAS["bhairav"]

    def lane(sws: list[str], y: int, first_build: int, title: str, c: str) -> list[str]:
        out = [f'<p style="position:absolute;left:128px;top:{y + 30}px;width:230px;font-size:{LABEL}px;font-weight:600;color:{c}">{title}</p>']
        for i, sw in enumerate(sws):
            x = 370 + i * 178
            upper = sw == "S" and ((title.startswith("AROHA") and i == len(sws) - 1) or (title.startswith("AVAROHA") and i == 0))
            glyph, lat = dev(sw, upper), ("Sa'" if upper else LAT[sw])
            kom = sw in KOMAL
            base = (f'<div style="position:absolute;left:{x}px;top:{y}px;width:160px;height:118px;background:{PANEL};border:4px solid {MAGENTA if kom else LINE};'
                    f'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0px">'
                    f'<p style="font-family:{DEVA};font-size:52px;line-height:1.15;color:{MAGENTA if kom else INK}">{glyph}</p>{p(lat, 30, MAGENTA if kom else DIM)}</div>')
            lit = (f'<div data-build-in="pop {first_build + i} auto" style="position:absolute;left:{x}px;top:{y}px;width:160px;height:118px;background:{c};border:4px solid {INK};'
                   f'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0px">'
                   f'<p style="font-family:{DEVA};font-size:52px;line-height:1.15;color:{BG}">{glyph}</p>{p(lat, 30, BG)}</div>')
            out += [base, lit]
        return out

    vadi = panel(label("VADI · SAMVADI", MAGENTA)
                 + row(f'<p style="font-family:{DEVA};font-size:56px;color:{INK}">{dev(b["vadi"])}</p>' + p(LAT[b["vadi"]] + " · king", LABEL, TEXT),
                       gap=16, align="center")
                 + row(f'<p style="font-family:{DEVA};font-size:56px;color:{INK}">{dev(b["samvadi"])}</p>' + p(LAT[b["samvadi"]] + " · minister", LABEL, TEXT),
                       gap=16, align="center"), MAGENTA, pad="18px 22px", gap=4)
    pakad = panel(label("PAKAD · CHALAN", SAFFRON)
                  + f'<p style="font-family:{DEVA};font-size:44px;line-height:1.3;color:{INK}">{phrase(b["pakad"][0])} , {phrase(b["pakad"][1])}</p>'
                  + f'<p style="font-family:{DEVA};font-size:44px;line-height:1.3;color:{TEXT}">{phrase(b["chalan"][2])}</p>'
                  + p("re and dha sway: andolan", LABEL, MAGENTA), SAFFRON, pad="18px 22px", gap=6, width="flex:2")
    samay = panel(label("SAMAY · TIME", SYS) + p("Dawn", BIG, INK) + p("6 to 9 am", LABEL, TEXT)
                  + p(f"Thaat {b['thaat']}", LABEL, DIM), SYS, pad="18px 22px", gap=6)
    inner = [eyebrow("Raga Bhairav"), headline("BHAIRAV, THE DAWN RAGA")]
    inner += lane(b["aroha"], 270, 1, "AROHA ↑", CYAN)
    inner += lane(b["avaroha"], 404, 9, "AVAROHA ↓", GOLD)
    inner += [row(vadi, pakad, samay, gap=24),
              audio("A03", 1312, 880, 480, 70, "scale run, then Bhairav")]
    return section("bhairav", inner, flow_top=548, notes= "About 75 seconds. Every note on this slide comes from src/raga.py, the same data the agents and the validator use. The aroha lights up note by note, then the avaroha. Underlined notes are komal (flat): Bhairav flattens Re and Dha, and those are exactly the notes that sway (andolan). Vadi dha is the most emphasised note, samvadi re its partner. The pakad is the catchphrase that tells a listener it's Bhairav; the chalan is how it moves. Bhairav belongs to dawn, the first prahar, which is why it often opens a morning concert. Play A03: a plain scale run, then Bhairav's own movement. (The andolan clip, A04, is on the previous slide.) Sources recorded in the data: Tanarang, Wikipedia.", gap=26)


def s_tala() -> str:
    right = (p(f'<span style="color:{INK}">Teentaal</span> · 16 beats, four groups. To a metal ear, four bars of 4/4.', BODYPX, TEXT)
             + p(f'<span style="color:{GOLD}">SAM</span> · beat 1, where everything lands', BODYPX, TEXT, f";border-top:3px solid {LINE};padding:14px 0px 0px 0px")
             + p(f'<span style="color:{INK}">CLAPS</span> on 5 and 13 · <span style="color:{DIM}">KHALI</span>, the open wave, on 9', BODYPX, TEXT, f";border-top:3px solid {LINE};padding:14px 0px 0px 0px")
             + p(f'<span style="color:{CYAN}">BPM</span> · tempo. At 128, one cycle is 7.5 s.', BODYPX, TEXT, f";border-top:3px solid {LINE};padding:14px 0px 0px 0px"))
    inner = [embed("tala", 128, 280, 680, 680, {"width:600px;height:600px": "width:680px;height:680px"}),
             eyebrow("Tala"), headline("EVERYTHING LANDS ON BEAT ONE"),
             f'<div style="position:absolute;left:880px;top:320px;width:912px;display:flex;flex-direction:column;gap:20px">{right}</div>',
             audio("A05", 1312, 860, 480, 80, "one teentaal cycle")]
    return section("tala", inner, "About 45 seconds. Play A05, one teentaal cycle at 128 BPM. The circle flashes SAM on beat one. Clap along if the room is game: clap on 1, 5 and 13, wave on 9. Line: \"The ending is correct only if it lands in the right place.\"")


def s_metal() -> str:
    vocab = (p(f'<span style="color:{GOLD}">RIFF</span> · a short repeated guitar figure', BODYPX, TEXT)
             + p(f'<span style="color:{GOLD}">POWER CHORD</span> · root plus fifth. It rings.', BODYPX, TEXT)
             + p(f'<span style="color:{MAGENTA}">CHUG</span> · a palm-muted note. It stops short.', BODYPX, TEXT))
    inner = [eyebrow("Metal", MAGENTA), headline("WHAT MAKES A RIFF HEAVY"),
             row(f'<div style="display:flex;gap:24px;align-items:end">{img("guitar", 360, 135, "Flying-V guitar")}{img("amp", 150, 169, "Amp stack")}{img("drums", 252, 162, "Drum kit")}</div>',
                 f'<div style="flex:1;display:flex;flex-direction:column;gap:12px">{vocab}</div>', gap=48, align="center"),
             f'<div style="position:absolute;left:128px;top:748px;width:1664px;display:flex;justify-content:space-around">{label("POWER CHORD · rings out", GOLD)}{label("CHUG · stops short", MAGENTA)}</div>',
             embed("scopes", 128, 495, 1664, 240, {"width:1664px;height:260px": "width:1664px;height:240px"})]
    return section("metal", inner, "About 45 seconds. The two traces are the vocabulary of a riff: a power chord rings and decays; a palm-muted chug is a short burst on every eighth note. Remember \"chug\"; it comes back in the war stories when our renderer chopped every chug to 80 ms.",
                   bg="radial-gradient(ellipse at 50% 0%, #2a1224 0%, #08070d 60%)")


def s_song() -> str:
    secs = [("ALAP", 1, CYAN), ("GAT", 2, GOLD), ("CALL · ANSWER", 2, SAFFRON), ("TAAN", 2, MAGENTA), ("TIHAI", 1, GOLDHI)]
    groups = [("LEAD", GOLD, [("MELODY", "sitar · lead guitar", "sitar", [1, 1, 1, 1, 1], GOLD)]),
              ("RHYTHM", SAFFRON, [("RIFF", "power chords · chugs", "guitar", [0, 1, 1, 1, 1], SAFFRON),
                                   ("BASS", "follows the riff", "amp", [0, 1, 1, 1, 1], SAFFRON),
                                   ("DRUMS · TABLA", "the beat and the cycle", "drums", [0, 1, 1, 1, 1], MAGENTA)]),
              ("COLOUR", CYAN, [("DRONE", "tanpura or strings", "tanpura", [1, 1, 1, 1, 1], CYAN),
                                ("EXTRAS", "clean guitar, orchestra", "orchestra", [0, 0, 1, 1, 0], GOLDHI)])]
    GW, GAP, X0, LW, Y0, RH, GG = 176, 16, 128, 478, 316, 92, 16    # group column, row label, rows, gap between groups
    XR = X0 + GW + GAP
    unit = (1792 - XR - LW) / 8
    inner = [eyebrow("Layers"), headline("WHAT MAKES A SONG")]
    x = XR + LW
    for name, span, c in secs:
        inner.append(f'<p style="position:absolute;left:{int(x)}px;top:276px;width:{int(unit * span) - 8}px;font-family:{HEAD};font-size:16px;color:{c}">{name}</p>')
        x += unit * span
    y = Y0
    for g, (gname, gc, rows) in enumerate(groups):
        build = f"rise {g + 1}"
        inner.append(f'<div data-build-in="{build}" style="position:absolute;left:{X0}px;top:{y}px;width:{GW}px;height:{len(rows) * RH - 10}px;background:{PANEL};'
                     f'border:4px solid {gc};display:flex;align-items:center;justify-content:center">'
                     f'<p style="font-family:{HEAD};font-size:22px;color:{gc}">{gname}</p></div>')
        for role, instr, icon, on, c in rows:
            art = img(icon, 64, 64, role) if icon != "tanpura" else img(icon, 22, 64, role)
            inner.append(f'<div data-build-in="{build}" style="position:absolute;left:{XR}px;top:{y}px;width:{1792 - XR}px;height:{RH - 10}px;display:flex;align-items:center;gap:0px">'
                         f'<div style="width:{LW}px;display:flex;align-items:center;gap:14px"><div style="width:70px;display:flex;justify-content:center">{art}</div>'
                         f'<div style="display:flex;flex-direction:column">{label(role, c, 28)}{p(instr, 26, DIM)}</div></div>'
                         + "".join(f'<div style="width:{int(unit * span) - 8}px;height:{RH - 34}px;background:{c if lit else "#120f1d"};border:3px solid {c if lit else LINE};opacity:{1 if lit else 0.7}"></div><div style="width:8px;height:2px;background:{BG}"></div>'
                                   for lit, (_, span, _) in zip(on, secs))
                         + "</div>")
            y += RH
        y += GG
    inner.append(f'<p data-build-in="fade 4" style="position:absolute;left:128px;top:{y + 6}px;width:1664px;font-size:{BIG}px;color:{GOLD}">Roles stay. Instruments change.</p>')
    return section("song", inner, "About 60 seconds, three clicks, one per group. A song is layers in three groups. LEAD: the melody, the line you'd hum, on sitar or lead guitar or both in unison. RHYTHM: the riff, the bass and the drums with the tabla, the engine; in metal the bass and the kick follow the riff, which comes back in Part 1. COLOUR: the drone under everything and the extras, clean guitar or an orchestra. The grid is roughly the opening piece, section by section; lit cells are the layers playing. The roles are stable but the instruments that fill them change: the alap drops the whole rhythm group, a symphonic piece adds an orchestra. Two words to keep for later: the riff is the repeated guitar figure; a chug is a palm-muted note that stops short. The column names are the song's form: alap, the slow intro with no beat; gat, the composed hook that keeps returning; taan, a fast run; tihai, a phrase played three times that lands on beat one.", gap=24)


def s_subgenres() -> str:
    rows = [("Doom", 0, 183, VIOLET), ("Symphonic", 183, 428, VIOLET), ("Progressive", 244, 489, VIOLET),
            ("Heavy", 306, 428, GOLD), ("Death", 489, 611, MAGENTA), ("Melodic death", 550, 428, MAGENTA),
            ("Black", 550, 428, MAGENTA), ("Thrash", 611, 306, MAGENTA)]
    axis = row(p("BPM", LABEL, DIM, ";width:300px"),
               f'<div style="width:1100px;display:flex;justify-content:space-between">{"".join(p(v, LABEL, DIM) for v in ["60", "120", "180", "240"])}</div>', gap=24, align="center")
    bars = "".join(row(p(n, LABEL, GOLD if c == GOLD else TEXT, ";width:300px"),
                       f'<div style="width:1100px;height:40px;display:flex;background:#120f1d"><div style="width:{off}px;background:#120f1d"></div><div style="width:{w}px;background:{c}"></div></div>',
                       gap=24, align="center") for n, off, w, c in rows)
    inner = [f'<div style="position:absolute;left:866px;top:290px;width:5px;height:470px;background:{CYAN}"></div>',
             f'<p style="position:absolute;left:800px;top:772px;width:300px;font-size:{LABEL}px;font-weight:600;color:{CYAN}">TONIGHT · 128</p>',
             eyebrow("Subgenres", MAGENTA), headline("THE SUBGENRE SETS THE TEMPO"),
             f'<div style="display:flex;flex-direction:column;gap:12px">{axis}{bars}</div>']
    return section("subgenres", inner, "About 30 seconds. Each bar is a tempo range from the system's own data. Feel, for questions: doom slow and crushing; symphonic band plus orchestra; progressive shifting, odd meters; heavy anthemic and galloping; death brutal and low; melodic death twin leads over drive; black cold tremolo walls; thrash fast and aggressive. The cyan line is tonight's 128 BPM. The raga still decides which notes are legal; the subgenre decides tempo, register and feel.",
                   bg="radial-gradient(ellipse at 50% 0%, #2a1224 0%, #08070d 60%)")


def s_form() -> str:
    def card(dev: str, name: str, text: str, cousin: str, c: str) -> str:
        return panel(f'<p style="font-family:{DEVA};font-size:56px;line-height:1.2;color:{c}">{dev}</p>'
                     + f'<p style="font-family:{HEAD};font-size:22px;color:{INK}">{name}</p>'
                     + p(text, LABEL, TEXT) + p("≈ " + cousin, LABEL, DIM, f";border-top:3px solid {LINE};padding:8px 0px 0px 0px"),
                     c, pad="22px", gap=10)
    inner = [eyebrow("Song form"), headline("ALAP TO TIHAI, INTRO TO BREAKDOWN"),
             row(card("आलाप", "ALAP", "Slow, no beat", "intro", CYAN), card("गत", "GAT", "The hook, on beat one", "main riff", GOLD),
                 card("अंतरा", "ANTARA", "Second theme, up high", "bridge", SAFFRON), card("तान", "TAAN", "Fast runs", "shred solo", MAGENTA),
                 card("तिहाई", "TIHAI", "A phrase × 3, lands on beat one", "final hit", GOLDHI), gap=20),
             label("THE OPENING, CYCLE BY CYCLE", DIM),
             embed("formstrip", 128, 760, 1664, 144)]
    return section("form", inner, "About 45 seconds. The panels give the room handles; the metal mapping is approximate and that's fine. The strip is the opening performance cycle by cycle: alap, gat, call and answer, taan, and the tihai marked three times before the final hit. The tihai is the one to remember.")


SEMI = {"S": 0, "r": 1, "R": 2, "g": 3, "G": 4, "m": 5, "M": 6, "P": 7, "d": 8, "D": 9, "n": 10, "N": 11}


def roll_svg(clip_json: str, label: str, color: str, sam_beat: float | None = None,
             start: float = 0.0, span: float = 12.8) -> str:
    """A pixel piano roll drawn from a rendered clip's own note data: the sitar's notes from
    `start` for `span` beats (the window the clip actually plays), with an optional sam line."""
    data = json.loads((HERE.parent / "audio" / "build" / clip_json).read_text())
    notes = [n for layer in data["layers"] if layer["role"] == "lead" and layer.get("instrument", "sitar") == "sitar" for n in layer["notes"]]
    notes = [{**n, "start": n["start"] - start} for n in notes if n["start"] + n["dur"] > start and n["start"] < start + span]
    x = lambda beat: 2 + max(beat, 0.0) * 116 / span
    y = lambda n: 44 - (SEMI[n["swara"]] + 12 * n["oct"] + 12) * 40 / 36
    r = ['<rect width="120" height="48" fill="#0a0f18"/>'] + [f'<rect x="0" y="{yy}" width="120" height="1" fill="#1f1830"/>' for yy in (8, 21, 34)]
    if sam_beat is not None:
        r.append(f'<rect x="{x(sam_beat):.1f}" y="0" width="1" height="48" fill="#ffd97a"/>')
    for n in notes:
        x0 = x(n["start"])
        w = (min(n["start"] + n["dur"], span) - max(n["start"], 0.0)) * 116 / span - 0.8
        yy = y(n)
        r.append(f'<rect x="{x0:.1f}" y="{yy:.1f}" width="{max(w, 0.6):.1f}" height="2" fill="{color}"/>')
        if n.get("andolan"):
            for k in range(int(w // 2)):
                r.append(f'<rect x="{x0 + 2 * k + 0.5:.1f}" y="{yy - 2 - (k % 2):.1f}" width="1" height="1" fill="#ff2e88"/>')
    return (f'<svg aria-label="{label}" width="480" height="192" viewBox="0 0 120 48" shape-rendering="crispEdges">'
            + "".join(r) + "</svg>")


def band_lanes_svg(comp_json: Path, label: str, end: float | None = None, span: float = 24.0) -> str:
    """The last `span` beats of a band as four pixel lanes (sitar, guitar, bass, drums, top to
    bottom), drawn from the composition's own notes: each lane stops where that part stops,
    and every note Bhairav forbids is magenta."""
    data = json.loads(comp_json.read_text())
    allowed = set(RAGAS["bhairav"]["allowed"])
    def pick(role: str, instrument: str | None = None) -> dict | None:
        return next((l for l in data["layers"] if l["role"] == role and (instrument is None or l.get("instrument") == instrument)), None)
    lanes = [(pick("lead", "sitar"), GOLD), (pick("rhythm"), SAFFRON), (pick("bass"), CYAN), (pick("drums"), INK)]
    stop = lambda l: max([n["start"] + n["dur"] for n in l.get("notes") or []] + [h["start"] + h.get("dur", 0.2) for h in l.get("hits") or []] + [0.0])
    end = end if end is not None else max(stop(l) for l, _ in lanes if l)
    t0 = end - span
    x = lambda beat: 2 + (beat - t0) * 116 / span
    r = ['<rect width="120" height="48" fill="#0a0f18"/>'] + [f'<rect x="{x(t0 + k * 4):.1f}" y="0" width="0.4" height="48" fill="#2a2138"/>' for k in range(1, int(span // 4))]
    for i, (layer, c) in enumerate(lanes):
        y0 = 2 + i * 11.5
        if not layer:
            continue
        for h in layer.get("hits") or []:
            if t0 <= h["start"] < end:
                r.append(f'<rect x="{x(h["start"]):.1f}" y="{y0 + (0 if h["drum"] in ("crash", "china", "ride") else 3 if h["drum"] in ("hhat", "ohat") else 6):.1f}" width="0.8" height="2" fill="{c}"/>')
        for n in layer.get("notes") or []:
            a_, b_ = max(n["start"], t0), min(n["start"] + n["dur"], end)
            if b_ <= a_:
                continue
            bad = n["swara"] not in allowed or any(cs not in allowed for cs in n.get("chord") or [])
            r.append(f'<rect x="{x(a_):.1f}" y="{y0 + 2:.1f}" width="{max((b_ - a_) * 116 / span - 0.6, 0.6):.1f}" height="{6 if bad else 4}" fill="{MAGENTA if bad else c}"/>')
    return (f'<svg aria-label="{label}" width="480" height="192" viewBox="0 0 120 48" shape-rendering="crispEdges">'
            + "".join(r) + "</svg>")


def song_map_svg(comp_json: Path, label: str, bars: int = 32, bar: float = 4.0) -> str:
    """A one-minute song as a map: four rows (sitar, guitar, bass, drums) by `bars` bars, drawn
    from the notes. A lit cell = that part plays in that bar; magenta = the bar holds a note
    Bhairav forbids; a gold tick above the sitar = that sitar bar brings back earlier material."""
    data = json.loads(comp_json.read_text())
    allowed = set(RAGAS["bhairav"]["allowed"])
    def pick(role: str, instrument: str | None = None) -> dict:
        return next(l for l in data["layers"] if l["role"] == role and (instrument is None or l.get("instrument") == instrument))
    rows = [(pick("lead", "sitar"), GOLD), (pick("rhythm"), SAFFRON), (pick("bass"), CYAN), (pick("drums"), "#9a90b0")]
    cw = 116 / bars
    r = ['<rect width="120" height="48" fill="#0a0f18"/>']
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
            fill = MAGENTA if k in bad else (c if k in on else "#1a1528")
            r.append(f'<rect x="{2 + k * cw:.2f}" y="{y0:.1f}" width="{cw - 0.5:.2f}" height="7.5" fill="{fill}"/>')
        if i == 0:
            seen: set = set()
            for k in range(bars):
                content = tuple(sorted((round(e["start"] - k * bar, 3), e["swara"], e["oct"], e["dur"]) for e in events if k * bar <= e["start"] < (k + 1) * bar))
                if content and content in seen:
                    r.append(f'<rect x="{2 + k * cw:.2f}" y="3" width="{cw - 0.5:.2f}" height="3" fill="{GOLDHI}"/>')
                if content:
                    seen.add(content)
    return (f'<svg aria-label="{label}" width="480" height="192" viewBox="0 0 120 48" shape-rendering="crispEdges">'
            + "".join(r) + "</svg>")


def s_naive() -> str:
    """The ladder as three whole one-minute songs, all real output: A = one bare prompt (no
    system prompt, default settings) for a Bhairav metal song, B = the same plus Bhairav's
    grammar from the data, C = the full system (the opening song)."""
    audio_build = HERE.parent / "audio" / "build"
    maps = {"A": song_map_svg(audio_build / "FA_src.json", "Song A: all four parts play every bar; the guitar's bars are full of forbidden notes; the sitar never repeats a bar"),
            "B": song_map_svg(audio_build / "FB_src.json", "Song B: every note legal and phrases repeat, but all four parts still play every bar"),
            "C": song_map_svg(HERE.parent.parent / "out" / "fusion_20261011_194039.json", "Song C: the sitar opens alone, the band enters, the sitar drops out for the breakdown and the hook returns")}

    def col(n: int, x: int, k: str, cap: str) -> str:
        return (f'<div data-build-in="rise {n}" style="position:absolute;left:{x}px;top:330px;width:520px;height:520px;background:{PANEL};'
                f'border:4px solid {VIOLET};box-shadow:8px 8px 0px #000000;padding:20px;display:flex;flex-direction:column;gap:14px">'
                f'<p style="font-family:{HEAD};font-size:44px;color:{INK}">{k}</p>{maps[k]}{p(cap, BODYPX, TEXT)}</div>')
    chip = lambda n, x, txt, c: (f'<p data-build-in="pop {n}{" auto" if n > 4 else ""}" style="position:absolute;left:{x}px;top:342px;width:340px;'
                                 f'font-family:{HEAD};font-size:20px;line-height:1.6;color:{BG};background:{c};border:3px solid {BG};padding:8px 12px">{txt}</p>')
    inner = [eyebrow("The experiment", CYAN), headline("LISTEN BEFORE I SAY WHICH IS WHICH"),
             p("&gt; a one-minute heavy metal song in raga Bhairav", BODYPX, GOLD),
             col(1, 128, "A", "One prompt, no knowledge"), col(2, 700, "B", "The same prompt, plus the raga's grammar"),
             col(3, 1272, "C", "The full system"),
             chip(4, 290, "92 WRONG NOTES · NO MOTIF", MAGENTA), chip(5, 862, "IN THE RAGA · NEVER BREATHES", CYAN), chip(6, 1434, "HOOK RETURNS · HAS A SHAPE", GOLD),
             audio("FA", 148, 880, 480, 70, "A · 1 min"), audio("FB", 720, 880, 480, 70, "B · 1 min"), audio("FC", 1292, 880, 480, 70, "C · 1 min")]
    return section("naive", inner, "6:00–10:00. Three whole one-minute songs; play each in turn (clicking a playing clip pauses it, so you can cut one short). Keep the captions neutral until all three have played, then click for the verdicts. All three are real output. A and B went straight to Gemini 3.5 Flash through Google's SDK: the prompt was the only thing sent, with no system prompt and default settings. The maps are drawn from the notes: four rows (sitar, guitar, bass, drums) by 32 bars; lit = that part plays, magenta = a note Bhairav forbids, gold ticks = a sitar bar that brings back earlier material. A: one prompt, no knowledge. The guitar plays E minor metal, 92 notes Bhairav forbids; the sitar writes 32 bars and repeats one, a generic line with no motif; and all four parts play every bar for the whole minute. B: the same prompt plus Bhairav's grammar from our data. Every note is now legal and the sitar repeats its phrases in four-bar blocks, so knowledge alone buys a lot. But it never breathes: all four parts still play every bar. C: the song I played over. The sitar opens alone, the band enters, the sitar drops out for the breakdown, the hook comes back with a different continuation, then the taan. Knowledge gets you the raga; the system gets you a song.", gap=24)


def s_rules() -> str:
    inner = [f'<h1 style="font-family:{HEAD};font-size:56px;font-weight:400;line-height:1.5;color:{INK}">FOLLOWING THE RULES GETS YOU <span style="color:{CYAN}">CORRECT</span>.<br>IT DOESN\'T GET YOU <span style="color:{GOLD}">MUSIC</span>.</h1>',
             p("The same is true of clinical coding, contract drafting, and your domain.", 52, TEXT, ";width:1500px")]
    return section("rules", inner, "Pause here. Rules get you compliant; they don't get you good. A contract can satisfy every clause template and still fail the client; a clinical code can be valid and wrong for the patient. The rest of the talk is about the gap between correct and good.",
                   bg=SCAN, pad="128px", gap=56, justify="center")


def s_vote() -> str:
    def card(k: str, name: str, text: str, c: str) -> str:
        return panel(f'<p style="font-family:{HEAD};font-size:56px;color:{c}">{k}</p><p style="font-family:{HEAD};font-size:30px;line-height:1.4;color:{INK}">{name}</p>' + p(text, BODYPX, TEXT), c, pad="36px", gap=18)
    inner = [eyebrow("Your turn", CYAN), headline("YOU PICK HOW IT ENDS"),
             row(card("A", "DOOM", "Slow, low and crushing", VIOLET), card("B", "SYMPHONIC", "The band plus an orchestra", GOLD),
                 card("C", "THRASH", "Fast and aggressive", MAGENTA), gap=40),
             p("All three were composed before the talk. Your vote picks which real run, and which real trace, we open at the end.", BIG, CYAN)]
    return section("vote", inner, "About minute 9. Show of hands; no web poll. Pre-generate all three branches (same raga, your choice) and keep each branch's trace, WAV and an MP4 replay. The audience still controls the outcome, and the talk no longer depends on a model API or venue network.",
                   bg="radial-gradient(ellipse at 50% 30%, #241b3d 0%, #08070d 70%)", gap=40)


def s_steer() -> str:
    def card(art: str, title: str, text: str, c: str) -> str:
        return panel(f'<div style="height:200px;display:flex;align-items:end;gap:8px">{art}</div>' + label(title, c, 40) + p(text, BODYPX, TEXT), c, pad="30px")
    inner = [eyebrow("The agenda"), headline("WHAT GOT US FROM CORRECT TO MUSIC"),
             row(card(img("pandit", 144, 192, "Pandit"), "DOMAIN KNOWLEDGE", "The tradition's craft, written down as tested data", GOLD),
                 card(img("conductor", 144, 192, "Conductor"), "STEERING", "Verifiers, critics with rubrics, small repairs", CYAN),
                 card(img("lead", 96, 128, "Lead") + img("riff", 96, 128, "Riff") + img("rasik", 96, 128, "Rasik"), "DECOMPOSITION", "One agent per decision, each prompt doing one job", MAGENTA),
                 gap=40, extra=";flex:1")]
    return section("steer", inner, "This doubles as the agenda. Part 1: where knowledge lives and how the work is split. Part 2: the patterns that steer. Part 3: what building it taught us. Then the live demo.")


def s_stage(sid: str, n: int, title: str, sub: str, art: str, notes: str) -> str:
    inner = [art, p(f"STAGE {n} / 3", BIG, CYAN, ";letter-spacing:6px;font-weight:600"),
             headline(title, H1, width=1250, tag="h1"), p(sub, 48, DIM, ";width:1150px"), stage_bar(n)]
    return section(sid, inner, notes, bg=SCAN, pad="128px", gap=40, justify="center", transition="push")


def s_thesis() -> str:
    def q(spr: str, title: str, text: str, c: str) -> str:
        return panel(row(img(spr, 144, 192, NAMES[spr]), f'<div style="flex:1;display:flex;flex-direction:column;gap:14px">'
                         f'<p style="font-family:{HEAD};font-size:28px;line-height:1.5;color:{c}">{title}</p>{p(text, BIG, TEXT)}</div>', gap=28, align="center"), c)
    hyb = lambda spr, text: row(img(spr, 72, 96, NAMES[spr]), p(text, BODYPX, TEXT, ";flex:1"), gap=16, align="center", extra=f";flex:1;border-top:4px solid {GOLD};padding:14px 0px 0px 0px")
    inner = [eyebrow("The thesis"), headline("IS IT ALLOWED? IS IT ANY GOOD?"),
             row(q("ustad", "ALLOWED?", f'Has a proof, so <span style="color:{CYAN}">code decides</span>.', CYAN),
                 q("rasik", "ANY GOOD?", f'Is an argument, so <span style="color:{MAGENTA}">a model judges</span>.', MAGENTA), gap=40),
             label("MOST OF THE SYSTEM LIVES IN BETWEEN", DIM),
             row(hyb("ustad", "Code proves it; an agent explains"), hyb("producer", "Code measures; an agent evaluates"),
                 hyb("arranger", "Code offers legal edits; an agent picks"), gap=40)]
    return section("thesis", inner, "6:30–8:30. \"Is this note legal?\" has a proof, so it never goes to a model, for the same reason you don't ask a model what a million times twelve is. \"Does this sound like Bhairav?\" has no proof, only an argument, so a model judges it. Domain knowledge decides where uncertainty may live. The three hybrids are Ustad, the Producer and the Arranger; each comes back later.", gap=30)


def s_knowledge() -> str:
    code = ["<span style=\"color:#f2b53c\">\"bhairav\"</span>: {",
            "&#160;&#160;\"allowed\": [\"S\",\"r\",\"G\",\"m\",\"P\",\"d\",\"N\"],",
            "&#160;&#160;\"vadi\": \"d\", \"samvadi\": \"r\",",
            "&#160;&#160;<span style=\"color:#ff2e88\">\"andolan\": [\"r\", \"d\"],</span>",
            "&#160;&#160;\"pakad\": [[\"G\",\"m\",\"d\",\"d\",\"P\"], …],",
            "&#160;&#160;\"sources\": [Tanarang, …],", "}"]
    codebox = panel("".join(f'<p style="font-family:{CODE};font-size:36px;line-height:1.2;color:{INK}">{c}</p>' for c in code)
                    + f'<p style="font-family:{CODE};font-size:32px;color:{FAINT}">src/raga.py · trimmed</p>', CYAN, bg="#0a0f18", gap=2, width="flex:8")
    right = (p("One source feeds the validator, the verifiers and every agent prompt.", BODYPX, INK)
             + p("Each entry cites its sources. Disagreements are flagged in the data.", BODYPX, TEXT)
             + p("Tests check the facts themselves.", BODYPX, TEXT))
    inner = [eyebrow("Knowledge is data"), headline("THE RULEBOOK LIVES IN CODE"),
             row(codebox, f'<div style="flex:4;display:flex;flex-direction:column;gap:22px">{right}</div>', gap=48, extra=";flex:1"),
             p("✓ Put facts in code, with sources and tests   ✗ Let the model supply facts from memory", BODYPX, GOLD)]
    return section("knowledge", inner, "8:30–10:00. \"The agents reason over the rulebook; they never write it.\" If your domain facts live in a doc, they rot; in code with assertions, they can't. Point at andolan (magenta): the sway you just saw animated is Bhairav, and Rasik checks for it later. Callback to the opener: an illegal shuddha Re in Bhairav is exactly what the validator catches.")


# ---- Part 1 as a build story: one slide per step, the system growing ----------
N_STEPS = 11

# ---- The band as a graph that fills in step by step ------------------------------------
# Seats are fixed by the FINAL roster, so the picture never shifts between slides: the
# audience watches the same graph fill in. Agents sit in pipeline columns; code (cyan)
# sits on the wiring: the rulebook under everything, checks and measures on the edges.
G_COLS: list[tuple[str, list[str]]] = [("INTERPRET", ["interpreter"]), ("SHAPE", ["pandit", "riffsmith"]),
                                       ("COMPOSE", ["lead", "riff", "orchestra"]), ("REPAIR", ["arranger"]),
                                       ("JUDGE", ["ustad", "rasik", "producer"]), ("DECIDE", ["conductor"])]
AGENT_STEP = {"interpreter": 4, "pandit": 5, "riffsmith": 5, "lead": 6, "riff": 6, "conductor": 8, "ustad": 7,
              "rasik": 7, "producer": 9, "orchestra": 11, "arranger": 11}
CODE_STEP = {"rulebook": 3, "resolver": 4, "voices": 6, "loop": 8, "metrics": 9, "canvas": 10, "verifiers": 11}
G_TOP, G_NW, G_NH, G_ROW, G_PITCH = 236, 158, 104, 112, 1664 / 6
G_MID = G_TOP + G_ROW + G_NH // 2                     # the centre row: every column is centred on it
EDGE = "#6b6080"


def _cx(col: int) -> int:
    return round(128 + G_PITCH * (col + 0.5))


def _node_top(col: int, k: int) -> int:
    n = len(G_COLS[col][1])
    return round(G_TOP + (k + (3 - n) / 2) * G_ROW)


def _built(build: str | None) -> str:
    return f' data-build-in="{build}"' if build else ""


def _bar(x1: int, y1: int, x2: int, y2: int, c: str, build: str | None) -> str:
    """A 4px pixel wire, horizontal or vertical."""
    x, y = min(x1, x2) - (2 if x1 == x2 else 0), min(y1, y2) - (2 if y1 == y2 else 0)
    w, h = (4, abs(y2 - y1)) if x1 == x2 else (abs(x2 - x1), 4)
    return f'<div{_built(build)} style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;background:{c}"></div>'


def _arrow(x: int, y: int, c: str, build: str | None, up: bool = False) -> str:
    """A stepped pixel arrowhead whose tip is at (x, y), pointing right (or up)."""
    out = []
    for i, size in enumerate((16, 10, 4)):
        if up:
            out.append(f'<div{_built(build)} style="position:absolute;left:{x - size // 2}px;top:{y + i * 4}px;width:{size}px;height:4px;background:{c}"></div>')
        else:
            out.append(f'<div{_built(build)} style="position:absolute;left:{x - 12 + i * 4}px;top:{y - size // 2}px;width:4px;height:{size}px;background:{c}"></div>')
    return "".join(out)


def _chip(text: str, x: int, y: int, w: int, new: bool, build: str | None) -> str:
    """A cyan code chip sitting on the wiring."""
    c = GOLD if new else CYAN
    return (f'<div{_built(build)} style="position:absolute;left:{x}px;top:{y}px;width:{w}px;background:{GOLD if new else "#0b1a1c"};'
            f'border:3px solid {c};padding:2px 0px;display:flex;justify-content:center">'
            f'<p style="font-size:18px;line-height:1.15;text-align:center;color:{BG if new else CYAN}">{text}</p></div>')


def _live(col: int, step: int) -> list[int]:
    return [k for k, a in enumerate(G_COLS[col][1]) if AGENT_STEP[a] <= step]


def _edges(step: int) -> list[tuple[int, int]]:
    cols = [c for c in range(len(G_COLS)) if _live(c, step)]
    return list(zip(cols, cols[1:]))


def band_graph(step: int, recap: bool = False) -> list[str]:
    """The system as it stood after `step`. New pieces are gold and build in on the first click
    (on the recap, everything builds in automatically, grouped by the step that added it)."""
    out: list[str] = []

    def build_for(s: int) -> str | None:
        if recap:
            return f"{'pop' if s else 'fade'} {s - 2} auto" if s >= 3 else None
        return "pop 1" if s == step else None

    def colour(s: int, base: str) -> str:
        return GOLD if (s == step and not recap) else base

    # ghost seats for agents still to come
    for col, (stage, agents) in enumerate(G_COLS):
        for k, a in enumerate(agents):
            if AGENT_STEP[a] > step:
                out.append(f'<div style="position:absolute;left:{_cx(col) - G_NW // 2}px;top:{_node_top(col, k)}px;width:{G_NW}px;height:{G_NH}px;'
                           f'background:#0c0a14;border:3px dashed {LINE};display:flex;align-items:center;justify-content:center">'
                           f'<p style="font-family:{HEAD};font-size:14px;color:{FAINT}">{stage}</p></div>')
    # the rulebook: the foundation every agent and check reads
    if step >= CODE_STEP["rulebook"]:
        s = CODE_STEP["rulebook"]
        out.append(f'<div{_built(build_for(s))} style="position:absolute;left:128px;top:600px;width:1664px;height:40px;background:{"#2a2410" if colour(s, CYAN) == GOLD else "#0b1a1c"};'
                   f'border:3px solid {colour(s, CYAN)};display:flex;align-items:center;justify-content:center">'
                   f'<p style="font-size:22px;color:{colour(s, CYAN)}">RULEBOOK · the raga and tala facts every agent and every check reads</p></div>')
    # the shared canvas frames Lead and Riff
    if step >= CODE_STEP["canvas"]:
        s = CODE_STEP["canvas"]
        x, y = _cx(2) - G_NW // 2 - 10, _node_top(2, 0) - 8
        out.append(f'<div{_built(build_for(s))} style="position:absolute;left:{x}px;top:{y}px;width:{G_NW + 20}px;height:{G_ROW + G_NH + 16}px;border:4px dashed {colour(s, CYAN)}"></div>')
    # wiring between consecutive live columns: a bus on each multi-seat side, one trunk on the centre row
    prev = set(_edges(step - 1)) if not recap else set()
    for a, b in _edges(step):
        s = max(min(AGENT_STEP[G_COLS[a][1][k]] for k in _live(a, step)), min(AGENT_STEP[G_COLS[b][1][k]] for k in _live(b, step)))
        is_new = (a, b) not in prev and not recap
        c, bld = (GOLD if is_new else EDGE), (("pop 1" if is_new else None) if not recap else build_for(s))
        xa, xb = _cx(a) + G_NW // 2, _cx(b) - G_NW // 2
        for col, x_edge, x_bus in ((a, xa, xa + 16), (b, xb, xb - 16)):
            mids = [_node_top(col, k) + G_NH // 2 for k in _live(col, step)]
            if mids != [G_MID]:
                for k in _live(col, step):
                    m = _node_top(col, k) + G_NH // 2
                    ks = AGENT_STEP[G_COLS[col][1][k]]
                    cc = GOLD if (ks == step and not recap) else c
                    out.append(_bar(x_edge, m, x_bus, m, cc, build_for(ks) if recap else ("pop 1" if ks == step else bld)))
                lo, hi = min(mids + [G_MID]), max(mids + [G_MID])
                out.append(_bar(x_bus, lo, x_bus, hi, c, bld))
        x1 = xa + 16 if [_node_top(a, k) + G_NH // 2 for k in _live(a, step)] != [G_MID] else xa
        x2 = xb - 16 if [_node_top(b, k) + G_NH // 2 for k in _live(b, step)] != [G_MID] else xb
        out.append(_bar(x1, G_MID, x2 - 8, G_MID, c, bld))
        out.append(_arrow(x2 - 2, G_MID, c, bld))
    # the Flow's revise loop: Conductor back to the composers, capped in code
    if step >= CODE_STEP["loop"]:
        s = CODE_STEP["loop"]
        c, bld, lane = colour(s, CYAN), build_for(s), 584
        xc, xg = _cx(5), _cx(2) + 30
        out += [_bar(xc, _node_top(5, 0) + G_NH, xc, lane, c, bld), _bar(xg, lane, xc, lane, c, bld),
                _bar(xg, _node_top(2, 2) + G_NH + 12, xg, lane, c, bld), _arrow(xg, _node_top(2, 2) + G_NH, c, bld, up=True),
                _chip("revise · ≤ 3 rounds", _cx(4) - 130, lane - 15, 260, colour(s, CYAN) == GOLD, bld)]
    # code chips on the wiring
    chips = [("resolver", "resolver", _cx(0) + G_NW // 2 + 4, G_MID + 18, 104),
             ("verifiers", "verifiers", _cx(2) + G_NW // 2 + 22, _node_top(2, 0) + 20, 118),
             ("voices", "bass·drums<br>drone", _cx(2) + G_NW // 2 + 22, _node_top(2, 2) + 8, 118),
             ("metrics", "metrics", _cx(3) + G_NW // 2 + 6, _node_top(4, 2) + 30, 112),
             ("canvas", "canvas", _cx(1) + G_NW // 2 + 6, _node_top(2, 0) + 4, 92)]
    for key, text, x, y, w in chips:
        if step >= CODE_STEP[key]:
            out.append(_chip(text, x, y, w, colour(CODE_STEP[key], CYAN) == GOLD, build_for(CODE_STEP[key])))
    # the agents themselves, on top of their wiring
    for col, (_, agents) in enumerate(G_COLS):
        for k, a in enumerate(agents):
            s = AGENT_STEP[a]
            if s > step:
                continue
            new = s == step and not recap
            c = GOLD if new else ROLE[a]
            glow = f";box-shadow:0px 0px 0px 4px {BG},0px 0px 0px 8px {GOLD}" if new else ";box-shadow:6px 6px 0px #000000"
            out.append(f'<div{_built(build_for(s))} style="position:absolute;left:{_cx(col) - G_NW // 2}px;top:{_node_top(col, k)}px;width:{G_NW}px;height:{G_NH}px;'
                       f'background:{PANEL};border:4px solid {c}{glow};display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px">'
                       f'{img(a, 54, 72, NAMES[a])}<p style="font-size:19px;font-weight:600;line-height:1;color:{c}">{NAMES[a]}</p></div>')
    return out


def prompt_strip(step: int) -> list[str]:
    """Steps 1 and 2 predate the agents: one prompt, then one prompt per instrument."""
    out: list[str] = []
    boxes = [("system", "ONE PROMPT")] if step == 1 else [("sitar", "SITAR"), ("guitar", "GUITAR"), ("amp", "BASS"), ("drums", "DRUMS")]
    w, gap = 280, 40
    x0 = 128 + (1664 - (len(boxes) * w + (len(boxes) - 1) * gap) - 360) // 2
    for i, (icon, name) in enumerate(boxes):
        x = x0 + i * (w + gap)
        art = img(icon, 72, 96, name) if icon == "system" else img(icon, 150, 80, name)
        out.append(f'<div data-build-in="pop 1" style="position:absolute;left:{x}px;top:300px;width:{w}px;height:220px;background:{PANEL};border:4px solid {GOLD};'
                   f'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px">{art}'
                   f'<p style="font-family:{HEAD};font-size:18px;color:{GOLD}">{name}{"" if step == 1 else " PROMPT"}</p></div>')
    xs = x0 + len(boxes) * (w + gap)
    out.append(f'<p style="position:absolute;left:{xs - 30}px;top:380px;width:60px;font-family:{HEAD};font-size:40px;color:{FAINT}">&gt;</p>')
    out.append(f'<div style="position:absolute;left:{xs + 40}px;top:300px;width:280px;height:220px;background:#120f1d;border:4px dashed {VIOLET};'
               f'display:flex;align-items:center;justify-content:center"><p style="font-family:{HEAD};font-size:24px;color:{DIM}">A SONG?</p></div>')
    return out


def split_bar(model: str, code: str, build: str | None = None) -> str:
    """Who does what at this step: the model's job beside code's, so the deterministic/LLM
    boundary is visible on every step instead of on one summary table."""
    half = lambda tag, text, c, x: (f'<div{_built(build)} style="position:absolute;left:{x}px;top:876px;width:816px;height:84px;background:#120f1d;border:4px solid {c};'
                                     f'padding:0px 22px;display:flex;align-items:center;gap:20px"><p style="width:110px;flex-shrink:0;font-family:{HEAD};font-size:20px;color:{c}">{tag}</p>'
                                     f'{p(text, 30, INK, ";line-height:1.15")}</div>')
    return half("MODEL", model, SAFFRON, 128) + half("CODE", code, CYAN, 976)


def s_step(n: int, pattern: str, title: str, pain: str, decision: str, tradeoff: str, model: str, code: str, notes: str) -> str:
    """Pain shows first; click 1 brings the new agent into the graph with the decision; click 2
    brings the trade-off and who does what."""
    cols = [("PAIN", pain, MAGENTA, None), ("DECISION", decision, GOLD, "fade 1"), ("TRADE-OFF", tradeoff, CYAN, "fade 2")]
    inner = [eyebrow(f"Step {n} of {N_STEPS} · {pattern}", GOLD), headline(title)]
    inner += prompt_strip(n) if n <= 2 else band_graph(n)
    for i, (h, t, c, bld) in enumerate(cols):
        inner.append(f'<div{_built(bld)} style="position:absolute;left:{128 + i * 568}px;top:660px;width:528px;height:196px;background:{PANEL};border:4px solid {c};'
                     f'box-shadow:8px 8px 0px #000000;padding:18px 24px;display:flex;flex-direction:column;gap:10px">'
                     f'<p style="font-family:{HEAD};font-size:22px;color:{c}">{h}</p>{p(t, 34, INK, ";line-height:1.2")}</div>')
    inner.append(split_bar(model, code, "fade 2"))
    return section(f"step{n}", inner, notes + " CLICK 1: the new piece joins the graph, with the decision. CLICK 2: the trade-off and who does what.")


def s_band() -> str:
    """The recap: the whole graph assembles itself in the order it was built."""
    inner = [eyebrow("Recap · how the band grew"), headline("THE WHOLE BAND")] + band_graph(N_STEPS, recap=True)
    tiles = [("11 AGENTS", "One per decision, not per instrument.", GOLD),
             ("CODE, IN CYAN", "Facts, checks, measures, the clock.", CYAN),
             ("ONE FLOW", "Bounded. It always ends.", SAFFRON)]
    for i, (h, t, c) in enumerate(tiles):
        inner.append(f'<div data-build-in="rise {10 + i}" style="position:absolute;left:{128 + i * 568}px;top:690px;width:528px;height:200px;background:{PANEL};'
                     f'border:4px solid {c};box-shadow:8px 8px 0px #000000;padding:22px 26px;display:flex;flex-direction:column;gap:12px">'
                     f'<p style="font-family:{HEAD};font-size:26px;color:{c}">{h}</p>{p(t, 36, INK, ";line-height:1.2")}</div>')
    return section("band", inner, "About 60 seconds. The graph assembles itself in build order, the same picture the room has watched fill in step by step: the rulebook first, then the Interpreter and resolver, the composers, Lead and Riff with the code voices, the two critics, the Conductor and the Flow's revise loop, the Producer with its metrics, the shared canvas, and finally the verifiers, the Orchestra and the Arranger. Let it finish, then click the three tiles: eleven agents, one per decision; everything cyan is code; one Flow that always ends. If time is short, skip straight to Part 2.")


STEPS = [
    (1, "Single prompt", "IT STARTED WITH ONE PROMPT", "None yet. It sounded plausible.", "Try the simplest thing: one call.", "Cheap and fast. Nothing could check it.",
     "Everything: notes, form, rules.", "Nothing yet.",
     "One call, no rules, no data. This is clip A from the experiment: it even got the scale right. The problem is that nothing in the system could say whether it was right, or steer it."),
    (2, "Split by instrument", "THEN A PROMPT PER INSTRUMENT", "One prompt couldn't hold every part.", "Give every instrument its own prompt.", "Parts ignored each other. Heading for ~15 agents.",
     "Every part, each on its own.", "Glue: stack the tracks.",
     "The natural next move: one prompt per track. Each part got attention, but they never listened to each other, nobody owned the form, and the design was heading for about fifteen agents: sitar, drums, tabla, solo, harmoniser. Hold that number; step 6 comes back to it."),
    (3, "Knowledge as data · guardrail", "RULES MOVED INTO CODE", "Illegal notes slipped through unseen.", "Raga facts as data. A validator in code.", "Hand-verified data, two sources per raga.",
     "Still writes every note.", "Owns the raga facts. Checks legality.",
     "The first real decision, and it came before any agent: the rules leave the prompt and become data plus a deterministic validator, the same data every later agent reads. Online raga data is often wrong, so each raga is checked against two Hindustani sources. The next two slides are this decision in detail."),
    (4, "Prompt chaining · structured output", "AN INTERPRETER AT THE DOOR", "\"Make it angry\" became a whole invented brief.", "An extractor that invents nothing.", "One more call. No silent creative choices.",
     "Reads what you said.", "Checks it against the menu.",
     "Free text needs a front door. The first cut chose the subgenre and tempo when you didn't say, which is a creative decision hiding at intake. Now the model extracts only what was said, a pure resolver keeps only supported values, and everything unsaid stays OPEN for the composers. \"The model is allowed to be wrong about what you said; it is never allowed to decide what's legal.\""),
    (5, "Role-based agents · bounded dialogue", "TWO COMPOSERS WHO DISAGREE", "Nobody owned the song's form.", "Two opposed composers argue one chart.", "More turns, capped by code. Real tension.",
     "Form, motif, tempo, tala.", "Tala accents, legal motif, turn cap.",
     "Pandit leans tradition, Riffsmith leans metal. Two neutral agents collapse into agreement theatre; opposed tastes explore the real trade-off. The first cut had code copy the raga's pakad as the motif, so every piece opened the same way: the model got the pen back, code kept the rulebook. We own the loop, so it ends on a turn boundary with a complete chart."),
    (6, "Agents for decisions, not instruments", "NO BASS AGENT. NO DRUM AGENT.", "~15 instrument agents: 15× calls, 15× failures.", "Sitar line and riff are agents. The rest is code.", "Rule drums risk sounding canned, so they read the riff.",
     "The sitar line and the riff.", "Bass, drums, drone, tabla, timing.",
     "The pivot, and the answer to \"why not an agent for drums and bass?\": in metal the bass and the kick follow the riff. That is derivable, not a decision, and every agent is an LLM call, so the wrong axis costs latency, money and failure surface. Deterministic doesn't mean dumb: the kick locks to the riff's onsets and the feel changes per section. The model supplies durations; code supplies the clock. Next slide: the whole band, agents vs code."),
    (7, "Tool use · LLM-as-judge", "TWO CRITICS: LEGAL AND BEAUTIFUL", "Legal, but lifeless. Nobody said why.", "Ustad checks legality. Rasik judges taste.", "Two more calls. Taste stays an opinion.",
     "Ustad explains. Rasik judges.", "Decides legal. Ustad can't overrule it.",
     "Legality is a fact, so code owns it: Ustad calls the validator as a tool and its output type has no verdict field, so even a lying Ustad can't pass an illegal piece. Taste isn't checkable, so Rasik genuinely judges, against a fixed 1–5 rubric grounded in the raga's pakad and chalan. The next slide is Ustad in detail."),
    (8, "Arbiter · deterministic flow", "A REFEREE AND A CLOCK", "Critics disagreed. Nobody decided.", "A Conductor rules. One Flow, capped rounds.", "No autonomous orchestrator. Always ends.",
     "Debates, then rules.", "Triage, routing, the round cap.",
     "Code triages first: illegal means a forced revise with no debate; both critics happy means accept. Only a real aesthetic conflict reaches the Conductor, who always rules at the cap. The pipeline becomes one CrewAI Flow whose router returns done at the round limit. Next: why a flow and not an orchestrator agent, then the referee."),
    (9, "Separate judges · code measures", "A THIRD CRITIC: THE PRODUCER", "Rasik judged raga and song at once.", "A Producer for the song. Rasik keeps the raga.", "One more judge. A debate with real stakes.",
     "Judges the song.", "Measures dynamics, motif, overlap.",
     "Rasik was doing two jobs, and the old debate was hollow: by the time a piece is debated it's legal, so Ustad had no aesthetic stake. Both external reviews flagged it. The Producer judges the song from metrics code computes; the debate becomes Rasik against the Producer, and Ustad exits."),
    (10, "Shared blackboard", "THE BAND STARTS LISTENING", "Lead and Riff composed deaf to each other.", "A shared canvas. Code picks who leads.", "More passes. Never a free group chat.",
     "Each voice answers the other.", "Who leads, how many passes.",
     "Each part was legal and well judged, and still didn't sound like a band. On the shared canvas the leader proposes and the follower answers what it actually hears. The sharpest lesson: the first revise regenerated a voice in isolation, so the critique loop quietly undid the collaboration. The canvas became durable Flow state."),
    (11, "Verifiers · constrained choice · local repair", "FEELINGS BECOME BUDGETS", "\"Too light\" had nowhere to go.", "Verifiers, an Arranger, an Orchestra.", "Domain work to set budgets. Fixes, not rewrites.",
     "Composes; picks one repair.", "Budgets, repair menu, right of way.",
     "Listening notes became numbers a generator must meet, with one bounded re-roll. When riff and melody clash, the Arranger picks one legal edit from a menu code builds, and code decides who yields. The Orchestra adds symphonic colour. Then: the patterns we refused."),
]


def s_evolution() -> str:
    code_badge = f'<p style="font-family:{HEAD};font-size:18px;color:{CYAN};border:3px solid {CYAN};padding:6px 8px">{{ }}</p>'
    steps = [("ONE PROMPT", ["system"], "Plausible. Nothing could check it.", DIM),
             ("A PROMPT PER INSTRUMENT", ["sitar", "guitar", "drums"], "Parts ignored each other. No owner.", DIM),
             ("RULES MOVE INTO CODE", [], "The model never supplies a fact again.", CYAN),
             ("THE INTERPRETER", ["interpreter"], "Free text becomes a checked brief.", SYS),
             ("PANDIT + RIFFSMITH", ["pandit", "riffsmith"], "Someone owns the song's form.", GOLD),
             ("LEAD + RIFF", ["lead", "riff"], "Bass, drums and drone become code.", SAFFRON),
             ("USTAD + RASIK", ["ustad", "rasik"], "Legal is a fact; taste is a judgement.", MAGENTA),
             ("CONDUCTOR + FLOW", ["conductor"], "Disputes need a referee and a clock.", CYAN),
             ("THE PRODUCER", ["producer"], "Rasik was judging raga and song at once.", MAGENTA),
             ("A SHARED CANVAS", ["lead", "riff"], "Lead and riff had composed deaf.", SAFFRON),
             ("VERIFIERS + ARRANGER", ["orchestra", "arranger"], "Feelings become budgets. Fix the note.", GOLDHI)]
    inner = [eyebrow("Recap · how the band grew"), headline("ELEVEN STEPS, ELEVEN AGENTS")]
    for i, (what, sprites, why, c) in enumerate(steps):
        y = 248 + i * 66
        art = code_badge if not sprites else "".join(img(sp, 42, 56, NAMES.get(sp, sp)) if sp in NAMES or sp == "system" else img(sp, 60, 40, sp) for sp in sprites)
        inner.append(f'<div data-build-in="rise {i + 1}" style="position:absolute;left:128px;top:{y}px;width:1664px;height:58px;background:{PANEL};border:3px solid {c};'
                     f'display:flex;align-items:center;gap:20px;padding:0px 18px">'
                     f'<p style="width:44px;font-family:{HEAD};font-size:20px;color:{c}">{i + 1}</p>'
                     f'<div style="width:190px;display:flex;gap:4px;align-items:center">{art}</div>'
                     f'<p style="width:520px;font-family:{HEAD};font-size:18px;line-height:1.4;color:{INK}">{what}</p>'
                     f'<p style="flex:1;font-size:32px;color:{TEXT}">{why}</p></div>')
    return section("evolution", inner, "Recap, about 45 seconds; click through quickly, the room has seen every step. About 3 minutes if used instead of the step slides; one click per step, and each step is the failure that forced it. 1: one prompt, plausible and uncheckable. 2: a prompt per instrument; the parts never listened to each other and nobody owned the song (this is the wrong axis the next slide is about). 3: raga and tala facts moved into code with a validator, so the model never supplies a fact. 4: the Interpreter turns free text into a validated brief and invents nothing. 5: Pandit and Riffsmith, opposed composers, own the song's form. 6: the Lead and the Riff compose; bass, drums and drone are derived by code. 7: critics, Ustad for legality (code decides) and Rasik for taste. 8: the Conductor because they disagreed; the Flow puts the loop on a clock. 9: the Producer, because Rasik was judging raga authenticity and songwriting at once. 10: the shared canvas, because the lead and riff were composed deaf to each other. 11: verifiers turned listening notes into budgets, the Orchestra added symphonic colour, and the Arranger repairs one clashing note instead of regenerating. Steps 1 and 2 predate the repo; the rest follow the commit history.", gap=24)


def s_decisions() -> str:
    def tile(art: str, name: str, agent: bool) -> str:
        c = GOLD if agent else LINE
        return (f'<div style="flex:1;background:{PANEL if agent else "#120f1d"};border:4px solid {c};padding:12px;display:flex;flex-direction:column;align-items:center;gap:6px{"" if agent else ";opacity:0.8"}">'
                f'<div style="height:120px;display:flex;align-items:center">{art}</div>{label(name, INK if agent else TEXT, 32)}{label("AGENT" if agent else "CODE", GOLD if agent else DIM, 32)}</div>')
    inner = [eyebrow("Decomposition"), headline("WE STARTED WITH AN AGENT PER INSTRUMENT"),
             row(f'<div style="display:flex;flex-direction:column;gap:6px"><p style="font-family:{HEAD};font-size:104px;color:{FAINT}">~15</p>{p("first design", LABEL, DIM)}</div>',
                 f'<p style="font-family:{HEAD};font-size:56px;color:{GOLD}">&gt;</p>',
                 f'<div style="display:flex;flex-direction:column;gap:6px"><p style="font-family:{HEAD};font-size:104px;color:{GOLD};text-shadow:6px 6px 0px {SAFFRON}">11</p>{p("one per decision", LABEL, GOLD)}</div>', gap=56, align="center"),
             row(tile(img("sitar", 150, 45, "Sitar"), "LEAD", True), tile(img("guitar", 150, 56, "Guitar"), "RIFF", True), tile(img("orchestra", 90, 120, "Orchestra"), "ORCHESTRA", True),
                 tile(img("tanpura", 32, 120, "Tanpura"), "DRONE", False), tile(img("amp", 100, 113, "Bass amp"), "BASS", False), tile(img("drums", 150, 96, "Drums"), "DRUMS", False),
                 tile(img("tabla", 150, 90, "Tabla"), "TABLA", False), tile(img("guitar", 150, 56, "Clean guitar"), "CLEAN", False), gap=14),
             p("Eight parts, three agents. The rest follow the riff and the chart, so they're code.", BIG, TEXT)]
    return section("decisions", inner, "10:00–11:30. \"An agent earns a place when it owns a decision you can state in one sentence.\" If you're drawing one agent per noun in the output, you're writing a utils.py. Every agent is an LLM call: the wrong axis costs latency, money and failure surface. The three gold tiles are composed by agents (the lead line, the riff, the orchestra's intent); the five dim ones are derived, because in metal the bass and the kick follow the riff.", gap=28)


def s_roster() -> str:
    def card(n: str, sprites: list[str], stage: str, names: str, text: str, c: str) -> str:
        art = "".join(img(s, 96, 128, NAMES[s]) for s in sprites)
        return panel(f'<div style="display:flex;gap:8px;height:128px;align-items:end">{art}</div>' + label(f"{n} · {stage}", c) + p(f'<span style="color:{INK}">{names}</span> {text}', LABEL, TEXT), c, pad="20px", gap=8)
    inner = [eyebrow("The roster"), headline("MEET THE BAND"),
             f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:28px">'
             + card("1", ["interpreter"], "INTERPRET", "Interpreter", "reads your request", SYS)
             + card("2", ["pandit", "riffsmith"], "SHAPE", "Pandit, Riffsmith", "argue the song's form", GOLD)
             + card("3", ["lead", "riff", "orchestra"], "COMPOSE", "Lead, Riff, Orchestra", "write the music", SAFFRON)
             + card("4", ["arranger"], "REPAIR", "Arranger", "fixes clashing notes", GOLDHI)
             + card("5", ["ustad", "rasik", "producer"], "JUDGE", "Ustad, Rasik, Producer", "legal? raga? song?", MAGENTA)
             + card("6", ["conductor"], "DECIDE", "Conductor", "settles disputes, on a clock", CYAN) + "</div>"]
    return section("roster", inner, "11:30–13:00. Under a minute; the agents return when their decisions matter. The colours are the demo UI's role code and stay consistent: gold composers, saffron generators, magenta critics, cyan Conductor. Point out the missing instrument agents.", gap=28)


def pattern(sid: str, eye: str, eye_c: str, title: str, inner: list[str], notes: str, bg: str = GLOW, flow_top: int | None = None) -> str:
    return section(sid, [eyebrow(eye, eye_c), headline(title)] + inner, notes, bg=bg, flow_top=flow_top)


def s_front() -> str:
    brief = (f'<div data-build-in="pop 1" style="position:absolute;left:300px;top:420px;width:760px;background:#0a0f18;border:4px solid {CYAN};box-shadow:8px 8px 0px #000000;'
             f'padding:18px 24px;display:grid;grid-template-columns:230px 1fr;gap:6px">'
             + "".join(p(k, BODYPX, DIM) + p(v, BODYPX, c) for k, v, c in [("raga", "darbari ✓", CYAN), ("subgenre", "doom ✓", CYAN), ("key", "D, so Sa = D ✓", CYAN), ("tala", "OPEN", FAINT), ("tempo", "OPEN", FAINT)])
             + "</div>")
    inner = [sprite("interpreter", 128, 270, 3),
             f'<div style="position:absolute;left:300px;top:280px;width:760px;background:{INK};border:4px solid {BG};box-shadow:6px 6px 0px #000000;padding:16px 22px">{p("&quot;doom fusion in Darbari, key of D&quot;", BIG, BG)}</div>',
             brief,
             f'<div style="position:absolute;left:1120px;top:280px;width:672px">{do_dont(["Make the model reason in the schema first", "Fix the prompt before buying effort"], ["Let the intake pick creative choices"], "")}</div>',
             f'<div style="position:absolute;left:128px;top:740px;width:932px">{bit_us("A mood-only request hallucinated a whole brief. A reasoning field placed first fixed it.")}</div>']
    return pattern("front", "Structured output", SYS, "THE FRONT DOOR INVENTS NOTHING", inner,
                   "13:30–15:30. Click once: the request locks into a validated brief. Everything the user said is checked against the libraries; anything they didn't say stays OPEN for the composers. \"The model is allowed to be wrong about what you said; it is never allowed to decide what's legal.\" An LLM extracts a loose intent; a pure resolver validates it; junk degrades to OPEN, never a crash. More reasoning effort didn't fix the hallucinated brief; a reasoning field first in the schema did.")


def s_guardrail() -> str:
    code = ["class UstadNarration(BaseModel):", "&#160;&#160;&#160;&#160;reasoning: str", "&#160;&#160;&#160;&#160;explanation: str",
            "<span style=\"color:#ff2e88\">&#160;&#160;&#160;&#160;# no verdict field</span>"]
    codebox = panel("".join(f'<p style="font-family:{CODE};font-size:44px;line-height:1.1;color:{INK}">{c}</p>' for c in code), CYAN, bg="#0a0f18", gap=2, width="")
    inner = [row(f'<div style="flex:7;display:flex;flex-direction:column;gap:24px">{codebox}</div>',
                 f'<div style="flex:5;display:flex;flex-direction:column;gap:24px">{do_dont(["Encode authority in the type"], ["Ask the model not to decide"])}{bit_us("Caching a zero-argument tool would have returned the first verdict forever.")}</div>', gap=40),
             sprite("ustad", 128, 590, 4),
             f'<div data-build-in="rise 1" style="position:absolute;left:340px;top:590px;width:500px;background:{INK};border:4px solid {BG};box-shadow:6px 6px 0px #000000;padding:16px 22px">'
             f'<p style="font-family:{HEAD};font-size:24px;line-height:1.5;color:{BG}">"PERFECTLY LEGAL!"</p>{p("a fake Ustad that lies", LABEL, VIOLET)}</div>',
             f'<div data-build-in="pop 2" style="position:absolute;left:400px;top:770px;width:500px;background:{MAGENTA};border:4px solid {BG};box-shadow:6px 6px 0px #000000;padding:16px 22px;transform:rotate(-4deg)">'
             f'<p style="font-family:{HEAD};font-size:28px;line-height:1.5;color:{BG}">VERDICT: ILLEGAL</p>{p("assembled by code", LABEL, BG)}</div>']
    return pattern("guardrail", "ReAct tool use · guardrail", MAGENTA, "USTAD CAN'T DECLARE A PIECE LEGAL", inner,
                   "15:30–17:30. Click 1: a fake Ustad that lies says \"perfectly legal\". Click 2: the verdict is still ILLEGAL, because code assembles it and Ustad's output type has no verdict field. \"We didn't tell the model not to decide legality; we built a type where it can't.\" One validator, two jobs: the hard gate on every generator's output, and a tool Ustad calls (a visible ReAct step in the trace) to explain the violation. When notes gained grace notes and glides, the validator was extended in the same commit.",
                   bg="radial-gradient(ellipse at 50% 0%, #2a1224 0%, #08070d 60%)")


def s_verifier() -> str:
    rows_l = ["chugs ≥ 55% of notes", "pitch changes capped", "real silence in it", "lands on a held Sa"]
    c1 = [("✗ too few chugs", MAGENTA), ("✗ too melodic", MAGENTA), ("✓ breathes", TEXT), ("✓ lands", TEXT)]
    c2 = [("✓ ground holds", CYAN), ("✓ a riff", CYAN), ("✓ breathes", CYAN), ("✓ lands", CYAN)]
    col = lambda head, items, c: "".join([f'<p style="height:56px;font-size:{LABEL}px;font-weight:600;color:{c}">{head}</p>'] + [f'<p style="height:64px;font-size:{BODYPX}px;color:{ic}">{t}</p>' for t, ic in items])
    box = lambda x, n, head, items, c: (f'<div data-build-in="rise {n}" style="position:absolute;left:{x}px;top:330px;width:470px;height:368px;background:{PANEL};border:4px solid {c};'
                                        f'box-shadow:8px 8px 0px #000000;padding:16px 22px;display:flex;flex-direction:column">{col(head, items, c)}</div>')
    inner = [p('"THE RIFF SOUNDS TOO LIGHT."', 30, GOLD, f";font-family:{HEAD};line-height:1.5"),
             f'<div style="position:absolute;left:128px;top:330px;width:620px;height:368px;background:#120f1d;border:4px solid {LINE};padding:16px 22px;display:flex;flex-direction:column">{col("WHAT CODE CHECKS", [(r, TEXT) for r in rows_l], DIM)}</div>',
             box(800, 1, "CANDIDATE 1", c1, MAGENTA), box(1300, 2, "CANDIDATE 2", c2, CYAN),
             f'<p style="position:absolute;left:128px;top:730px;width:1664px;font-size:{BIG}px;line-height:1.2;color:{INK}">Meters cover what is testable. A critic judges the rest.</p>',
             audio("A10", 1312, 830, 480, 100, "melody-riff, then chug-riff")]
    return pattern("verifier", "Verifier · bounded retry", CYAN, "WHAT 'TOO LIGHT' MEANS IN NUMBERS", inner,
                   "17:30–19:30. Keep the complaint up. Click 1: candidate one fails two meters. Click 2: the re-roll, with those violations quoted back, passes all four. Play A10: the same riff as a melody-riff, then as a grounded chug-riff. Say the boundary out loud: the meters don't define heaviness; they define the part we can test cheaply and consistently. The 55% floor is calibrated on our renders: the light one sat at 47%, the good one at 73%. \"You can't prompt for silence; you have to own the clock.\" If a step routinely needs two retries, fix the prompt or schema.")


def s_blackboard() -> str:
    inner = [sprite("lead", 128, 270, 4), sprite("riff", 1600, 270, 4), embed("canvas", 352, 272, 1216, 260),
             row(panel(label("WHEN TO USE IT", CYAN) + p("One part must answer another", BODYPX, TEXT), CYAN, pad="22px"),
                 panel(label("WHAT BIT US", MAGENTA) + p("A lone revise erased the duet", BODYPX, TEXT), MAGENTA, pad="22px"),
                 panel(label("MEMORY", GOLD) + p("Each section hears the last", BODYPX, TEXT), GOLD, pad="22px"), gap=28),
             audio("A07", 1312, 860, 480, 80, "phrase, answer, both")]
    return pattern("blackboard", "Shared blackboard", SAFFRON, "SITAR AND RIFF WRITE ON ONE PAGE", inner,
                   "19:30–21:30. The canvas is the shared state. Pass 1: the Lead proposes. Pass 2: the Riff answers what it hears. Pass 3: both refine. Then code stops it. Play A07: 3 s Lead phrase, 3 s Riff response, 4 s combined. Who leads is a code rule keyed to the section: the riff opens a groove, the sitar opens an alap. Point back to the opening: the call and answer between my guitar and the sitar is this pattern with a human as the follower. The canvas had to become durable flow state, or a revise silently erased the collaboration.",
                   bg="radial-gradient(ellipse at 50% 0%, #2a1a10 0%, #08070d 60%)", flow_top=568)


def s_judge() -> str:
    def bar(name: str, n: int) -> str:
        return row(p(name, LABEL, TEXT, ";width:190px"), f'<div style="width:240px;height:26px;background:#120f1d;display:flex"><div style="width:{n * 48}px;background:{MAGENTA}"></div></div>', p(str(n), LABEL, INK), gap=14, align="center")
    def card(spr: str, title: str, crit: list[tuple[str, int]]) -> str:
        return panel(row(img(spr, 144, 192, NAMES[spr]), f'<div style="flex:1;display:flex;flex-direction:column;gap:10px">{label(title, MAGENTA)}{"".join(bar(n, v) for n, v in crit)}</div>', gap=22, align="center"), MAGENTA, pad="22px")
    chips = "".join(f'<div style="background:{PANEL};border:3px solid {c};padding:10px 16px">{p(t, LABEL, c)}</div>' for t, c in
                    [("the piece", CYAN), ("facts code measured", CYAN), ("a 1–5 rubric", CYAN), ("→ reasons, then scores", MAGENTA)])
    inner = [f'<div style="display:flex;gap:14px;align-items:center">{chips}</div>',
             row(card("rasik", "RASIK · the raga?", [("pakad", 4), ("idiom", 2), ("rasa", 3)]),
                 card("producer", "PRODUCER · the song?", [("structure", 4), ("hook", 3), ("dynamics", 4)]), gap=32),
             bit_us("Rasik was right (\"a scale run, not a taan\") and nothing improved, until the generator had to plan its phrase first.")]
    return pattern("judge", "LLM-as-judge", MAGENTA, "CRITICS SCORE WHAT CODE MEASURED", inner,
                   "21:30–23:30. Mostly static by design. Scorecards illustrate the rubric's shape, not a specific run. Three orthogonal critics: is it legal (Ustad, code owns it), does it sound like the raga (Rasik), does it work as a song (the Producer, ten criteria in the real rubric). Bias fixes we used: fixed scale over named criteria, anchors for 1, 3 and 5, facts computed by code, reasoning before each number. A critic is only as good as the generator's ability to act on it.",
                   bg="radial-gradient(ellipse at 50% 0%, #2a1224 0%, #08070d 60%)")


def s_debate() -> str:
    chip = lambda t, c, b: f'<div style="flex:1;background:{PANEL if b else "#120f1d"};border:{4 if b else 3}px solid {c};padding:12px 18px">{p(t, LABEL, c)}</div>'
    inner = [row(chip("ILLEGAL › revise, no debate", DIM, False), chip("ALL HAPPY › accept", DIM, False), chip("CONTESTED › debate", GOLD, True), gap=20),
             f'<div style="position:absolute;left:840px;top:612px;width:240px;height:28px;background:#123a3f;border:3px solid {CYAN}"></div>',
             sprite("conductor", 864, 420, 4), sprite("rasik", 128, 600, 4), sprite("producer", 1600, 600, 4),
             f'<div data-build-in="rise 1" style="position:absolute;left:330px;top:440px;width:490px;background:{INK};border:4px solid {MAGENTA};box-shadow:6px 6px 0px #000000;padding:16px 20px">'
             f'<p style="font-family:{HEAD};font-size:22px;line-height:1.6;color:{BG}">NO ANDOLAN ON KOMAL GA, DHA.</p>{p("RASIK", LABEL, "#5a1f36")}</div>',
             f'<div data-build-in="rise 2" style="position:absolute;left:1100px;top:440px;width:490px;background:{PANEL};border:4px dashed {MAGENTA};box-shadow:6px 6px 0px #000000;padding:16px 20px">'
             f'<p style="font-family:{HEAD};font-size:22px;line-height:1.6;color:{DIM}">[FROM A FRESH TRACE]</p>{p("PRODUCER", LABEL, MAGENTA)}</div>',
             f'<p data-build-in="pop 3" style="position:absolute;left:870px;top:356px;width:180px;font-family:{HEAD};font-size:20px;color:{CYAN};background:{BG};border:3px solid {CYAN};padding:8px 12px">ROUND 2/2</p>',
             f'<div data-build-in="pop 4" style="position:absolute;left:540px;top:700px;width:840px;background:{CYAN};border:4px solid {BG};box-shadow:8px 8px 0px #000000;padding:16px 22px">'
             f'<p style="font-family:{HEAD};font-size:22px;line-height:1.6;color:{BG}">RULING: REVISE THE LEAD. DWELL ON GA, DHA.</p>{p("CONDUCTOR · one layer, one reason", LABEL, "#123a3f")}</div>',
             f'<div data-build-in="fade 5" style="position:absolute;left:128px;top:880px;width:1664px;display:flex;gap:12px;align-items:center">{p("LEAD", LABEL, DIM, ";width:110px")}'
             + "".join(f'<div style="width:170px;height:34px;background:{GOLD if i in (2, 3) else LINE}"></div>' for i in range(6))
             + p("only this part is redone", LABEL, GOLD, ";flex:1") + "</div>"]
    return pattern("debate", "Debate · arbiter", MAGENTA, "WHEN THE CRITICS DISAGREE", inner,
                   "23:30–25:30. One click per beat. 1: Rasik's objection (paraphrased from a real Darbari trace). 2: the Producer's counter; replace the placeholder with eight words or fewer from a fresh Rasik vs Producer trace. 3: the round counter hits its bound. 4: the Conductor rules (paraphrase of the real ruling). 5: only the lead's region regenerates. Play A08 here: the failing region, a second of silence, the repaired region. Triage is code: an illegal piece is never debated, a satisfied one is accepted, and only a contested one earns the debate. Ustad exits; a legal piece gives legality no aesthetic stake.",
                   bg="radial-gradient(ellipse at 50% 30%, #1d1733 0%, #08070d 70%)")


def s_referee() -> str:
    inner = [embed("clock", 1240, 150, 480, 480, bg=SAFFRON), sprite("conductor", 1384, 664, 4),
             headline("DEBATE NEEDS A REFEREE AND A CLOCK.", H1, BG, 1040, "h1"),
             p("Critics built to disagree never agree. The round cap is one line of code, and the Conductor always rules when it's reached.", 52, BG, ";width:1040px")]
    return section("referee", inner, "25:30–26:00. The clock runs three rounds once and stops on RULING. Say the headline once and pause. \"The framework will happily loop forever. The terminator is one line of your code, not a hope that the agents settle.\" Debate gains plateau fast: most of the benefit is in rounds one and two.",
                   bg=SAFFRON, pad="128px", gap=48, justify="center", color=BG)


def s_repair() -> str:
    tile = lambda t, txt, c: panel(f'<p style="font-family:{HEAD};font-size:24px;color:{c}">{t}</p>' + p(txt, BODYPX, TEXT), c, pad="20px 24px", gap=8, width="")
    inner = [sprite("arranger", 128, 290, 4), embed("counter", 370, 320, 480, 240),
             f'<p style="position:absolute;left:128px;top:620px;width:760px;font-size:{BODYPX}px;line-height:1.2;color:{INK}">The Arranger picks one legal edit from a menu code built. It never moves a beat.</p>',
             f'<div style="position:absolute;left:1000px;top:280px;width:792px;display:flex;flex-direction:column;gap:20px">{tile("A PHRASE", "A verifier flags it; it re-rolls", CYAN)}{tile("A VOICE", "The Conductor names it; it regenerates", GOLD)}{tile("A NOTE", "The Arranger fixes one clash", GOLDHI)}</div>']
    return pattern("repair", "Local repair", GOLDHI, "FIX THE NOTE, KEEP THE SONG", inner,
                   "26:00–28:00. One principle at three scales. The counter runs once: 107 grinds between riff and melody down to zero in a dry run on a real piece, with no attack moved. Who yields is code: in a melody-led section the riff yields. Code builds the menu, the agent chooses, an unoffered choice falls back to the safest, so the pass always terminates. The dry run used no LLM; the Arranger has not made a live call yet. Give the model choices, not a blank page, when correctness matters.")


def s_refused() -> str:
    card = lambda k, t, txt: panel(label(k, DIM) + f'<p style="font-family:{HEAD};font-size:24px;line-height:1.5;color:{INK}">{t}</p>' + p(txt, BODYPX, TEXT), VIOLET, bg="#120f1d", pad="26px")
    inner = [row(card("DECOMPOSITION", "AN AGENT PER INSTRUMENT", "Overlapping jobs, many more calls"),
                 card("AUTHORITY", "MODELS FOR FACTS", "Cost and variance where code is certain"),
                 card("CONTROL", "UNBOUNDED AUTONOMY", "Self-directed delegation, endless reflection"), gap=32),
             panel(f'<p style="font-family:{CODE};font-size:48px;color:{INK}">if state.round &gt;= MAX_ROUNDS: return <span style="color:{GOLD}">"done"</span></p>'
                   + p("CrewAI Flows have no built-in loop cap. Ours is this line.", BODYPX, DIM), CYAN, bg="#0a0f18", width=""),
             p("These are defaults for a live system, not universal bans.", BODYPX, DIM)]
    return pattern("refused", "Refused patterns", DIM, "WHAT WE CHOSE NOT TO BUILD", inner,
                   "28:00–29:00. Explain the trade-off rather than painting autonomy as a villain: these patterns give up inspectable state, bounded cost and clear authority, which a live system needs. CrewAI's headline collaboration feature, agents delegating to each other, was the wrong tool for a debate the audience should read. Our reflection loop is bounded. Optional gotcha: a Flow loop-back must be a router label, because a plain or_() listener fires once and the loop silently dies after one pass.")


def story(sid: str, eye: str, title: str, body: str, notes: str, extra: str = "") -> str:
    return section(sid, [eyebrow(eye, DIM), headline(title), body, extra], notes, bg=BG, gap=28, flow_bottom=830 if extra else 984)


def evid(rows: list[tuple[str, str]]) -> str:
    return "".join(row(p(k, LABEL, GOLD, ";width:220px;font-weight:600"), p(v, BODYPX, TEXT, ";flex:1"), gap=20, extra=f";border-top:3px solid {LINE};padding:12px 0px 0px 0px") for k, v in rows)


def s_stories() -> list[str]:
    big = lambda n, c, txt: row(f'<p style="font-family:{HEAD};font-size:96px;color:{c};text-shadow:6px 6px 0px #123a3f">{n}</p>', p(txt, BIG, INK, ";flex:1"), gap=28, align="center")
    return [
        story("layers", "War story · measure first", "&quot;THE RIFFS SOUND HAPPY&quot;",
              case(p("Light, happy, not metal.", BIG, INK), evid([("MENU", "Yaman, our brightest raga"), ("VOICING", "Bright add9 chords"), ("WRITING", "Pitch changed on 79% of notes"), ("RENDER", "Mutes in the data, inaudible")]),
                   p("Four fixes. Only one was the prompt.", BIG, INK), "Prompt editing is not diagnosis."),
              "29:30–30:30. A GPT review said \"rewrite the prompt\". The saved composition JSON apportioned the blame across four layers. Play A09: the same notes rendered without and with the articulations. Companion line: the drum data declared blast beats that the drum code never read.",
              audio("A09", 1312, 884, 480, 80, "before and after")),
        story("midi", "War story · evidence beats agreement", "THE MIDI OUTVOTED TWO REVIEWERS",
              case(p("Muddy riffs. Two reviewers blamed tritone chords.", BIG, INK), big("0", CYAN, "tritones in 118 chord stacks") + p("Real causes: roots an octave low, clipping, dry samples.", BODYPX, TEXT),
                   p("Fix those. Save the score beside every render.", BIG, INK), "When opinion and data disagree, read the data."),
              "30:30–31:30. A critique loop that can't see the artefact converges on plausibility, not truth. 110 octaves and 8 fifths, zero tritones. Every render now saves its composition JSON, so the next diagnosis is free and needs no LLM call."),
        story("promptbug", "War story · never explain a bug to the model", "THE PROMPT THAT DOCUMENTED A BUG",
              case(p("Choppy riffs. Every check passed.", BIG, INK),
                   f'<p style="font-family:{CODE};font-size:48px;color:{GOLD}">PALM_MUTE_MS = 80</p>' + p('"a palm-muted note gates to a short chunk whatever its written duration"', BODYPX, DIM, ";text-decoration:line-through") + p("We wrote the bug into the prompt as a rule.", BODYPX, TEXT),
                   p("Fix the renderer. Delete the line.", BIG, INK), "A prompt that documents a bug teaches the model to repeat it."),
              "31:30–32:30. A chug written for two beats played for 0.16. Three of the four things I heard lived downstream of the last verifier: the clamp, a branch computed and never read (every chug fired twice), and channel-wide pitch bends on 58% of the power chords. Found by measuring the saved JSON; fixed and A/B'd by re-rendering it. Zero LLM calls."),
        story("backwards", "War story · let a practitioner correct you", "THE RULE THAT WAS BACKWARDS",
              case(p("The gat (the hook) didn't sound good.", BIG, INK),
                   row(f'<div style="flex:1">{big("2", CYAN, "")}{p("note values in a real gat", BODYPX, TEXT)}</div>', f'<div style="flex:1">{big("5", FAINT, "")}{p("in ours", BODYPX, TEXT)}</div>', gap=28)
                   + p('"at least THREE distinct durations"', BODYPX, DIM, ";text-decoration:line-through"),
                   p("Flip the rule. Keep the counter-example as a test.", BIG, INK) + p('"Convincingly Bageshree."', BODYPX, CYAN),
                   "Domain rules need a practitioner, not just tests."),
              "32:30–33:30. A practitioner sang two gats he was learning. In his, one note value covered 95% of notes; in ours the commonest covered 31%. A gat moves at one pulse; our rule was right for a taan and wrong for the head. The next render: \"intro and gat sound convincingly Bageshree.\" Every one of those rules came from reasoning about what the tradition should do, and a real piece corrected each one."),
        story("knobs", "War story · verify every setting", "THE FRAMEWORK IGNORED OUR SETTINGS",
              case(p("Lead calls stalled for up to 137 seconds.", BIG, INK),
                   evid([("SET", 'reasoning_effort = "low"'), ("SENT", "nothing; the provider dropped it"), ("USED", "up to 18.5k thinking tokens")]),
                   p("Use the provider's own setting. Check it in the trace.", BIG, INK), "Configured is not the same as applied."),
              "33:30–34:00. Found by reading token counts in the trace. Every run writes a trace: real prompts, responses, tokens, timing and retries. Same framework, second example: a Flow listener on or_() fires once, so the revise loop silently died after one pass. \"It ran once\" is not \"it loops\"."),
        story("hygiene", "War story · test for free", "WE TEST THE BAND WITHOUT PAYING IT",
              case(p("Billing is live. Every change risks a paid run.", BIG, INK), big("760+", CYAN, "tests, no LLM calls") + p("Fakes drive the real orchestration: routing, the round cap, the collaboration.", BODYPX, TEXT),
                   p("Pay only to test model behaviour.", BIG, INK), "Most workflow logic can be tested deterministically."),
              "34:00–34:30. Every stage is injected, so the multi-agent flow runs on fakes. Evals run one case at a time; the debate sits behind free code triage. Update the test count before the talk."),
    ]


def s_demo() -> str:
    step = lambda n, t: row(f'<p style="width:60px;font-family:{HEAD};font-size:26px;color:{GOLD}">{n}</p>', p(t, BIG, TEXT, ";flex:1"), gap=20, extra=f";border-top:3px solid {LINE};padding:10px 0px 0px 0px")
    inner = [sprite(n, 1150 + i * 128, 640, 2) for i, n in enumerate(["interpreter", "lead", "riff", "rasik", "conductor"])]
    inner += [p("STAGE 3 / 3 · LIVE", BIG, CYAN, ";letter-spacing:6px;font-weight:600"), headline("BACK TO THE BAND YOU PICKED", 56, tag="h1"),
              f'<div style="display:flex;flex-direction:column;gap:12px;width:980px">{step("1", "Your vote and its brief")}{step("2", "The trace, room by room")}{step("3", "A failure, a dispute, a ruling")}{step("4", "The piece")}{step("5", "What code decided, and what models did")}</div>',
              stage_bar(3)]
    return section("demo", inner, "34:00–39:00. A11. One question: can the audience connect the result to the decisions behind it? 0:00–0:30 the vote and its brief. 0:30–1:45 an accelerated trace replay in the studio UI. 1:45–2:45 pause on one verifier failure, one critic disagreement and the Conductor's repair order. 2:45–3:45 play the piece. 3:45–5:00 what code decided, what models decided, what was repaired. Primary path: the pre-generated branch replayed in the UI. Fallbacks: the cached composition, a screen recording of the trace, an MP4 of both.",
                   bg=SCAN, gap=26, transition="push")


def compare_col(title: str, sub: str, body: str, pros: list[str], cons: list[str], c: str, chosen: bool) -> str:
    items = "".join(p("✓ " + x, LABEL, INK) for x in pros) + "".join(p("✗ " + x, LABEL, DIM) for x in cons)
    tag = f'<p style="font-family:{HEAD};font-size:18px;color:{BG};background:{c};padding:6px 10px">OUR CHOICE</p>' if chosen else ""
    return panel(row(label(title, c, 34), tag, gap=16, align="center", extra=";justify-content:space-between")
                 + p(sub, LABEL, DIM) + p(body, BODYPX, TEXT) + items,
                 c if chosen else VIOLET, bg=PANEL if chosen else "#120f1d", pad="26px", gap=12)


def s_collabwhy() -> str:
    inner = [eyebrow("Shared blackboard · why not a group chat", SAFFRON), headline("A SHARED PAGE, NOT A GROUP CHAT"),
             row(compare_col("PARALLEL", "Isolation", "Each agent writes alone from the same plan.", [], ["Deaf to each other"], VIOLET, False),
                 compare_col("FREE COLLABORATION", "A group chat", "Agents message each other, pick who speaks next, decide when they're done.", [],
                             ["Turn order is a model decision", "Stopping is a hope", "Cost grows with the transcript", "Never replays the same way"], MAGENTA, False),
                 compare_col("BLACKBOARD", "A shared score", "Both read and write one score. Code picks the leader and the passes.",
                             ["Every turn sees the real work", "Always stops", "Tested with zero LLM calls"], [], GOLD, True), gap=28),
             p("Collaborate through the artefact, not the conversation.", BIG, GOLD)]
    return section("collabwhy", inner, "21:30–22:30. The selection rule, stated as a choice. Parallel generation against one plan was legal and deaf: the lead and the riff never responded to each other. A full collaboration pattern (agents chatting, choosing who speaks, deciding when they're done) would have handed turn order, termination and cost to the models, and no two runs would match, which a live demo can't afford. The blackboard keeps the useful part of collaboration, each agent responding to the other's actual work, while code owns the turns and the clock. What gets shared is the score, not a transcript.", gap=30)


def s_flowwhy() -> str:
    stage = lambda t, c: f'<div style="background:#120f1d;border:3px solid {c};padding:8px 12px">{p(t, 30, c)}</div>'
    arrow = p("›", 34, FAINT)
    chain = (f'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
             + arrow.join(stage(t, c) for t, c in [("interpret", SYS), ("compose", GOLD), ("generate", SAFFRON), ("critique", MAGENTA), ("decide", CYAN), ("repair", GOLDHI), ("render", TEXT)]) + "</div>")
    orch = compare_col("ORCHESTRATOR AGENT", "An LLM manager", "Plans the work, hands out tasks, decides what runs next and when it's finished.", [],
                       ["Routing is a model guess", "Retries and stopping are too", "A different path every run"], MAGENTA, False)
    flow = panel(row(label("DETERMINISTIC FLOW", GOLD, 34), f'<p style="font-family:{HEAD};font-size:18px;color:{BG};background:{GOLD};padding:6px 10px">OUR CHOICE</p>', gap=16, align="center", extra=";justify-content:space-between")
                 + p("A CrewAI Flow", LABEL, DIM) + chain + p("Code routes. Agents make only the decisions inside each step. The round cap is one line.", BODYPX, TEXT)
                 + p("✓ Same path every run", LABEL, INK) + p("✓ 760+ tests on fakes", LABEL, INK) + p("✓ Cost known up front", LABEL, INK), GOLD, pad="26px", gap=12, width="flex:3")
    inner = [eyebrow("Orchestration", CYAN), headline("A FLOW, NOT AN ORCHESTRATOR AGENT"),
             row(orch.replace("flex:1", "flex:2", 1), flow, gap=28),
             p("Use an orchestrator when you can't know the steps in advance. A song's steps are known.", BIG, GOLD)]
    return section("flowwhy", inner, "13:00–14:00. The skeleton before the patterns. Orchestrator-workers lets an LLM plan, delegate and decide when it's done; that is the right tool when the decomposition is unknown in advance, like open-ended research. Our pipeline's steps are known: interpret, compose, generate, critique, decide, repair, render. So the flow is code (a CrewAI Flow with @router labels and a round cap), and the agents only make the decisions inside each step. That's why the whole flow runs on fakes in tests, takes the same path every run, and has a cost we can predict. Every pattern that follows lives inside one of these boxes.", gap=30)


def s_domains() -> str:
    card = lambda t, code, model, c: panel(label(t, c, 34) + p(f'<span style="color:{CYAN}">CODE</span> · {code}', BODYPX, TEXT)
                                         + p(f'<span style="color:{MAGENTA}">MODEL</span> · {model}', BODYPX, TEXT), c, pad="28px", gap=16)
    inner = [eyebrow("Beyond music", CYAN), headline("THE SAME BOUNDARY, OTHER DOMAINS"),
             row(card("CONTRACTS", "required clauses and dates are present", "interprets ambiguity, proposes language", GOLD),
                 card("CLINICAL CODING", "code sets and exclusions are valid", "reads the unstructured notes within them", SAFFRON),
                 card("SOFTWARE DESIGN", "dependencies and policy violations, measured", "weighs the trade-offs, picks a bounded change", MAGENTA), gap=28),
             p("Illustrative. Your domain's owner decides which rules are authoritative.", BODYPX, DIM)]
    return section("domains", inner, "39:00–40:00. Transfer the allocation without claiming the music architecture copies across. In each domain there are rules a machine can prove and judgements it can only argue, and the same split applies: code owns the provable, the model owns the contextual, and a hybrid offers the model only legal options. The examples are illustrative; the domain owner still decides what is authoritative.", gap=30)


def s_matrix() -> str:
    steps = [("CAN CODE PROVE THE ANSWER?", "Write code", "ustad", CYAN),
             ("CAN CODE LIST THE VALID ACTIONS?", "Hybrid: menu + pick", "arranger", GOLDHI),
             ("MUST SPECIALISTS SEE EACH OTHER'S WORK?", "Shared blackboard", "lead", SAFFRON),
             ("DO THE JUDGES WANT DIFFERENT THINGS?", "Separate judges", "rasik", MAGENTA),
             ("CAN DISAGREEMENT BLOCK PROGRESS?", "Debate + arbiter", "conductor", CYAN)]
    inner = [eyebrow("Take this home"), headline("THE PATTERN FOLLOWS THE DECISION")]
    for i, (q, a, spr, c) in enumerate(steps):
        y = 262 + i * 136
        inner.append(f'<div data-build-in="rise {i + 1}" style="position:absolute;left:128px;top:{y}px;width:1664px;height:120px;background:{PANEL};border:4px solid {c};'
                     f'box-shadow:8px 8px 0px #000000;padding:0px 24px;display:flex;align-items:center;gap:24px">'
                     f'<p style="font-family:{HEAD};font-size:32px;color:{c};width:60px">{i + 1}</p>'
                     f'<p style="flex:1;font-family:{HEAD};font-size:22px;line-height:1.5;color:{INK}">{q}</p>'
                     f'<p style="width:600px;font-size:40px;color:{c}">› {a}</p>'
                     f'<img src="{SPRITE_URLS[spr]}" alt="{NAMES[spr]}" style="width:72px;height:96px;object-fit:contain"></div>')
    return section("matrix", inner, "40:00–41:30. Walk down the questions in order; each click reveals the next. Can code prove the answer? Write code (Ustad's legality). Can code list the valid actions? A hybrid: code offers, a model picks (the Arranger). Must specialists see each other's evolving work? A shared blackboard (the Lead and the Riff). Do the judges want different things? Keep them separate (Rasik and the Producer). Can disagreement block progress? A bounded debate with an arbiter (the Conductor). Most of the time you stop at the first question, which is why the answer is usually fewer agents than you expected.", bg=BG, gap=28)


def s_checklist() -> str:
    pairs = [("Facts in code, with tests", "Facts from the model"), ("One agent per decision", "One agent per noun"),
             ("Unsafe choices unrepresentable", "Asking nicely"), ("Feelings → measurable budgets", "Prompt adjectives"),
             ("Code measures, model judges", "\"Rate this 1–10\""), ("Repair just the broken part", "Regenerate everything"),
             ("A referee and a clock", "Waiting for consensus"), ("Read the data first", "Fix the plausible cause"),
             ("Trace every run", "Trusting defaults"), ("A practitioner's review", "Reasoning alone")]
    tr = "".join(f'<tr><td style="color:{INK}">{a}</td><td>{b}</td></tr>' for a, b in pairs)
    inner = [eyebrow("The checklist"), headline("WHAT TO DO ON MONDAY"),
             f'<table style="font-family:{BODY};font-size:36px;color:{DIM}"><tr style="background:{PANEL}"><th style="width:55%;text-align:left;color:{GOLD}">✓ DO</th><th style="width:45%;text-align:left;color:{DIM}">✗ DON\'T</th></tr>{tr}</table>']
    return section("checklist", inner, "41:00–42:00. Don't read it out; it's the leave-behind. Land the three takeaways over it: name the pattern your problem needs; decide which parts should not be agents; encode your domain's rules into the parts that are.", bg=BG, gap=24)


def s_close() -> str:
    inner = [f'<div style="position:absolute;left:0px;top:948px;width:1920px;height:132px;background:#120f1d;border-top:4px solid {LINE}"></div>']
    inner += [sprite(n, 128 + i * 104, 820, 2, opacity=0.45) for i, n in enumerate(LINEUP[:-1])]
    inner += [f'<div style="position:absolute;left:1520px;top:916px;width:272px;height:32px;background:#123a3f;border:3px solid {CYAN}"></div>',
              sprite("conductor", 1560, 660, 4), eyebrow("Shruti Shred"),
              f'<p style="font-family:{HEAD};font-size:24px;line-height:1.6;color:{TEXT}"><span style="color:{CYAN}">ENCODE FACTS.</span>&#160; <span style="color:{MAGENTA}">ASSIGN JUDGEMENT.</span>&#160; <span style="color:{GOLD}">BOUND INTERACTION.</span></p>',
              f'<h1 style="font-family:{HEAD};font-size:48px;font-weight:400;line-height:1.6;color:{INK};width:1340px">THE MODEL SUPPLIES RANGE.<br>THE DOMAIN SUPPLIES SHAPE.<br><span style="color:{CYAN}">THE ARCHITECTURE DECIDES WHICH ONE HAS AUTHORITY.</span></h1>',
              p("Sujit Kamthe · [repo link] · [contact]", BODYPX, DIM)]
    return section("close", inner, "42:00–43:00, then questions. Static. The whole band on stage, only the Conductor's riser lit. No song under the final lines; silence lets the room keep the framework.",
                   bg="radial-gradient(ellipse at 88% 70%, #123a3f 0%, #08070d 45%)", pad="120px 128px", gap=40)


def main() -> None:
    slides = {
        "cover": s_cover(), "perform": s_perform(), "reveal": s_reveal(), "hindustani": s_hindustani(), "twelve": s_twelve(), "raga": s_raga(), "bhairav": s_bhairav(),
        "song": s_song(), "form": s_form(), "naive": s_naive(),
        "rules": s_rules(), "vote": s_vote(), "steer": s_steer(),
        "sec1": s_stage("sec1", 1, "BUILDING THE BAND, ONE STEP AT A TIME", "Eleven steps. At each: what hurt, what we changed, what it cost.",
                        sprite("ustad", 1408, 600, 4) + sprite("rasik", 1600, 600, 4), "Thirty seconds. Part 1 is the system as we actually built it, one decision at a time, so the eleven agents arrive one or two at a time instead of all at once."),
        "thesis": s_thesis(), "knowledge": s_knowledge(), "evolution": s_evolution(), "decisions": s_decisions(),
        "sec2": s_stage("sec2", 2, "HOW WE STEER THE BAND", "Each pattern: what we built, what bit us, what we'd do again.",
                        sprite("lead", 1408, 600, 4) + sprite("riff", 1600, 600, 4), "13:00. Sixteen minutes, about two per pattern."),
        "flowwhy": s_flowwhy(), "front": s_front(), "guardrail": s_guardrail(), "verifier": s_verifier(), "blackboard": s_blackboard(), "collabwhy": s_collabwhy(), "judge": s_judge(),
        "debate": s_debate(), "referee": s_referee(), "repair": s_repair(), "refused": s_refused(),
        "sec3": s_stage("sec3", 2, "WHAT BUILDING IT TAUGHT US", "Each story: the symptom, the evidence, the decision.",
                        f'<img src="{SPRITE_URLS["amp"]}" alt="Amp stack" style="position:absolute;left:1440px;top:560px;width:256px;height:288px;object-fit:contain">',
                        "29:00. Quieter now: calm case cards after the animation-heavy section. If running long, keep the first, third and fourth."),
    }
    for args in STEPS:
        slides[f"step{args[0]}"] = s_step(*args)
    for html in s_stories():
        sid = html.split('id="', 1)[1].split('"', 1)[0]
        slides[sid] = html
    slides.update({"notes1": s_notes(1), "notes2": s_notes(2), "notes3": s_notes(3), "band": s_band(), "demo": s_demo(), "domains": s_domains(), "matrix": s_matrix(), "checklist": s_checklist(), "close": s_close()})
    slides.update(title_slides())
    for sid, html in slides.items():
        for m in re.finditer(r'<div style="([^"]*)"></div>', html):
            if not any(k in m.group(1) for k in ("background", "border", "box-shadow")):
                raise SystemExit(f"{sid}: empty spacer div ({m.group(1)}); the viewer drops these")
        for m in re.finditer(r"padding:([^;\"]+)", html):
            for v in re.findall(r"(\d+)px", m.group(1)):
                if int(v) > 256:
                    raise SystemExit(f"{sid}: padding {v}px exceeds the format's 256px cap")
        for m in re.finditer(r"<img [^>]*data-video=", html):
            before = html[:m.start()]
            if before.count("<div") != before.count("</div>"):
                raise SystemExit(f"{sid}: a clip is nested inside a div; only a top-level clip is clickable")
        if "data-video" in html:
            tail = html[html.index(">", html.rindex("data-video")) + 1:html.index("<aside>")]
            if re.search(r"<(div|p|img|x-embed|h\d|svg)\b", tail):
                raise SystemExit(f"{sid}: something is painted above the last clip and will swallow its click")
        (SLIDES / f"{sid}.html").write_text(html)
    print(f"wrote {len(slides)} slides")


if __name__ == "__main__":
    main()
