"""The system as a graph that fills in step by step (Act 1), ported from the retired pixel deck
(`build.py`, `band_graph`) to the light Sahaj style, at Sujit's request (2026-10-18): without a
picture of the wiring it is hard to imagine how the agentic system is built, or where a pattern sits.

Seats are fixed by the FINAL eleven-agent roster, so the picture never moves between slides: the
audience watches one graph fill in. Agents sit in pipeline columns, joined left to right; the
revise loop returns from the referee to the composers. CODE is drawn as its own row under the
agents (the model/code split on every step). The new pieces of a step are mustard and pop in on the
first click; seats still to come are dashed ghosts. Nothing is smaller than 32px (the deck's floor).

Pure: returns pinned HTML/SVG children for a 1920 x 1080 slide.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import visuals as V

HERE = Path(__file__).resolve().parent
SPRITES: Final = json.loads((HERE.parent / "sprites" / "assets.json").read_text())
INDIGO, CARD, LINE, MUTED = V.INDIGO, V.CARD, V.LINE, V.MUTED
TERRA, MUSTARD, SKY, PURPLE = V.TERRA, V.MUSTARD, V.SKY, V.PURPLE
NEW_FILL, GHOST, EDGE, PAGE = "#FFF4DF", "#B9B3AA", "#9A948C", "#F3F0EA"
SKY_TEXT: Final = "#2E7A93"

NAMES: Final = {"interpreter": "Interpreter", "pandit": "Pandit", "riffsmith": "Riffsmith", "lead": "Lead",
                "riff": "Riff", "orchestra": "Orchestra", "arranger": "Arranger", "ustad": "Ustad",
                "rasik": "Rasik", "producer": "Producer", "conductor": "Conductor"}
ROLE: Final = {"interpreter": SKY, "pandit": PURPLE, "riffsmith": TERRA, "lead": SKY, "riff": TERRA,
               "orchestra": MUSTARD, "arranger": PURPLE, "ustad": INDIGO, "rasik": TERRA, "producer": PURPLE,
               "conductor": INDIGO}
COLS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("interpret", ("interpreter",)), ("shape", ("pandit", "riffsmith")), ("compose", ("lead", "riff", "orchestra")),
    ("repair", ("arranger",)), ("judge", ("ustad", "rasik", "producer")), ("decide", ("conductor",)))
AGENT_STEP: Final = {"interpreter": 4, "pandit": 5, "riffsmith": 5, "lead": 6, "riff": 6, "ustad": 7, "rasik": 7,
                     "conductor": 8, "producer": 9, "orchestra": 11, "arranger": 11}
# The code row, in the order it grew: (label, the step that added it).
CODE: Final = (("raga facts", 3), ("resolver", 4), ("bass · drums", 6), ("round cap", 8), ("metrics", 9),
               ("canvas", 10), ("verifiers", 11))
LOOP_STEP: Final = 8
CANVAS_STEP: Final = 10

LEFT, WIDTH = 128, 1664
PITCH: Final = WIDTH / len(COLS)
NODE_W, NODE_H, ROW = 246, 104, 116
TOP: Final = 310                                      # room above for the group labels (2026-10-20)
MID: Final = TOP + ROW + NODE_H // 2                  # every column is centred on the middle row
LANE: Final = TOP + 2 * ROW + NODE_H + 16             # the revise loop runs under the agents
CODE_Y: Final = LANE + 18


def _cx(col: int) -> float:
    return LEFT + PITCH * (col + 0.5)


def _top(col: int, k: int) -> float:
    return TOP + (k + (3 - len(COLS[col][1])) / 2) * ROW


def _build(new: bool) -> str:
    return ' data-build-in="pop 1"' if new else ""


def _fresh(s: int, since: int, step: int) -> bool:
    """Did this piece arrive in the slide's span of steps (`since`..`step`)?"""
    return since <= s <= step


def _node(col: int, k: int, agent: str, step: int, since: int) -> str:
    x, y = _cx(col) - NODE_W / 2, _top(col, k)
    if AGENT_STEP[agent] > step:
        return (f'<div style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{NODE_W}px;height:{NODE_H}px;'
                f'border:3px dashed {GHOST};border-radius:16px;background:{PAGE};display:flex;align-items:center;'
                f'justify-content:center"><p style="font-size:32px;color:{GHOST}">{COLS[col][0]}</p></div>')
    new = _fresh(AGENT_STEP[agent], since, step)
    border, fill = (MUSTARD, NEW_FILL) if new else (ROLE[agent], CARD)
    return (f'<div{_build(new)} style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{NODE_W}px;height:{NODE_H}px;'
            f'background:{fill};border:{6 if new else 4}px solid {border};border-radius:16px;display:flex;'
            f'align-items:center;justify-content:center;gap:8px">'
            f'<img src="{SPRITES[agent]}" alt="{NAMES[agent]}" style="width:38px;height:52px;object-fit:contain">'
            f'<p style="font-size:32px;font-weight:800;color:{INDIGO}">{NAMES[agent]}</p></div>')


def _live(col: int, step: int) -> list[int]:
    return [k for k, a in enumerate(COLS[col][1]) if AGENT_STEP[a] <= step]


def _pairs(step: int) -> list[tuple[int, int]]:
    cols = [c for c in range(len(COLS)) if _live(c, step)]
    return list(zip(cols, cols[1:]))


def _segments(step: int, since: int) -> list[tuple[str, bool]]:
    """Every wire of the graph after `step` as (SVG path, added this step): a trunk on the middle
    row between consecutive live columns, a bus into each multi-seat column, a stub per agent."""
    before = set(_pairs(since - 1))
    out: list[tuple[str, bool]] = []
    for a, b in _pairs(step):
        pair_new = (a, b) not in before
        ends = {}
        for col, x_edge, x_bus in ((a, _cx(a) + NODE_W / 2, _cx(a) + NODE_W / 2 + 14),
                                   (b, _cx(b) - NODE_W / 2, _cx(b) - NODE_W / 2 - 14)):
            mids = [_top(col, k) + NODE_H / 2 for k in _live(col, step)]
            ends[col] = x_edge if mids == [MID] else x_bus
            if mids == [MID]:
                continue
            for k in _live(col, step):
                agent_new = _fresh(AGENT_STEP[COLS[col][1][k]], since, step)
                out.append((f"M{x_edge:.0f} {_top(col, k) + NODE_H / 2:.0f} H{x_bus:.0f}", pair_new or agent_new))
            out.append((f"M{x_bus:.0f} {min(mids + [MID]):.0f} V{max(mids + [MID]):.0f}", pair_new))
        x2 = ends[b] - 4
        out.append((f"M{ends[a]:.0f} {MID} H{x2:.0f}", pair_new))
        out.append((f"M{x2 - 14:.0f} {MID - 12} L{x2:.0f} {MID} L{x2 - 14:.0f} {MID + 12}", pair_new))
    return out


def _wires(step: int, since: int, new: bool) -> str:
    """The wires this step kept (`new` False, grey) or added (`new` True, mustard, popped in)."""
    paths = [d for d, added in _segments(step, since) if added == new]
    if not paths:
        return ""
    color = MUSTARD if new else EDGE
    body = "".join(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="5" stroke-linecap="round" '
                   f'stroke-linejoin="round"/>' for d in paths)
    return (f'<svg aria-label=""{_build(new)} style="position:absolute;left:0px;top:0px;width:1920px;height:1080px" '
            f'viewBox="0 0 1920 1080">{body}</svg>')


def _loop(step: int, since: int) -> str:
    """The Flow's revise loop: from the referee back to the composers, under the agents."""
    if step < LOOP_STEP:
        return ""
    new = _fresh(LOOP_STEP, since, step)
    color = MUSTARD if new else SKY
    xd, xc = _cx(5), _cx(2) + 40
    d = (f"M{xd:.0f} {_top(5, 0) + NODE_H:.0f} V{LANE} H{xc:.0f} V{_top(2, 2) + NODE_H + 4:.0f}")
    head = f"M{xc - 12:.0f} {_top(2, 2) + NODE_H + 18:.0f} L{xc:.0f} {_top(2, 2) + NODE_H + 4:.0f} L{xc + 12:.0f} {_top(2, 2) + NODE_H + 18:.0f}"
    body = "".join(f'<path d="{p}" fill="none" stroke="{color}" stroke-width="5" stroke-dasharray="3 12" '
                   f'stroke-linecap="round" stroke-linejoin="round"/>' for p in (d, head))
    return (f'<svg aria-label="the revise loop"{_build(new)} style="position:absolute;left:0px;top:0px;width:1920px;height:1080px" '
            f'viewBox="0 0 1920 1080">{body}</svg>')


def _canvas(step: int, since: int) -> str:
    """The shared canvas framing Lead and Riff (step 10 on)."""
    if step < CANVAS_STEP:
        return ""
    new = _fresh(CANVAS_STEP, since, step)
    x, y = _cx(2) - NODE_W / 2 - 10, _top(2, 0) - 8
    return (f'<div{_build(new)} style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{NODE_W + 20}px;'
            f'height:{ROW + NODE_H + 16}px;border:4px dashed {MUSTARD if new else SKY};border-radius:20px"></div>')


def _code_row(step: int, since: int) -> str:
    chips = []
    for label, s in CODE:
        if s > step:
            continue
        new = _fresh(s, since, step)
        chips.append(f'<p{_build(new)} style="font-size:32px;font-weight:700;color:{INDIGO if new else SKY_TEXT};'
                     f'background:{NEW_FILL if new else CARD};border:3px solid {MUSTARD if new else SKY};'
                     f'border-radius:12px;padding:4px 16px">{label}</p>')
    tag = f'<p style="font-size:32px;font-weight:800;letter-spacing:3px;color:{SKY_TEXT}">CODE</p>'
    return (f'<div style="position:absolute;left:{LEFT}px;top:{CODE_Y}px;width:{WIDTH}px;display:flex;gap:14px;'
            f'align-items:center;border-top:3px solid {LINE};padding-top:12px">{tag}{"".join(chips)}</div>')


def graph(step: int, since: int | None = None) -> list[str]:
    """The system as it stood after `step` (3..11), as pinned slide children: old wiring, the
    canvas and loop, ghosts and agents, the new wiring, then the code row. The pieces added from
    `since` (default: this step alone) to `step` are the new ones — one growth beat may span steps."""
    since = step if since is None else since
    out = [_wires(step, since, new=False), _canvas(step, since), _loop(step, since)]
    out += [_node(col, k, a, step, since) for col, (_, agents) in enumerate(COLS) for k, a in enumerate(agents)]
    out += [_wires(step, since, new=True), _code_row(step, since)]
    return [x for x in out if x]


# The compact build (2026-10-19, the "build, challenge, investigate, rebuild" arc): the whole growth on ONE
# slide. Each piece pops in on the click of the beat that added it; ghosts are there from the start.
BEATS: Final = ((3, 4), (5, 6), (7, 9), (10, 11))   # (first step, last step) per click — four clicks (2026-10-20)


def _beat_of(step: int) -> int:
    return next(i for i, (a, b) in enumerate(BEATS, start=1) if a <= step <= b)


def _pop(k: int) -> str:
    return f' data-build-in="pop {k}"'


def _ghost(col: int, k: int) -> str:
    x, y = _cx(col) - NODE_W / 2, _top(col, k)
    return (f'<div style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{NODE_W}px;height:{NODE_H}px;'
            f'border:3px dashed {GHOST};border-radius:16px;background:{PAGE};display:flex;align-items:center;'
            f'justify-content:center"><p style="font-size:32px;color:{GHOST}">{COLS[col][0]}</p></div>')


def _agent(col: int, k: int, agent: str) -> str:
    x, y = _cx(col) - NODE_W / 2, _top(col, k)
    return (f'<div{_pop(_beat_of(AGENT_STEP[agent]))} style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;'
            f'width:{NODE_W}px;height:{NODE_H}px;background:{CARD};border:4px solid {ROLE[agent]};border-radius:16px;'
            f'display:flex;align-items:center;justify-content:center;gap:8px">'
            f'<img src="{SPRITES[agent]}" alt="{NAMES[agent]}" style="width:38px;height:52px;object-fit:contain">'
            f'<p style="font-size:32px;font-weight:800;color:{INDIGO}">{NAMES[agent]}</p></div>')


def _beat_wires() -> list[str]:
    """The wires each beat adds, one SVG per beat, so they pop in with that beat's agents."""
    drawn: set[str] = set()
    out = []
    for k, (a, b) in enumerate(BEATS, start=1):
        paths = [d for d, _ in _segments(b, a) if d not in drawn]
        drawn.update(paths)
        body = "".join(f'<path d="{d}" fill="none" stroke="{EDGE}" stroke-width="5" stroke-linecap="round" '
                       f'stroke-linejoin="round"/>' for d in paths)
        if body:
            out.append(f'<svg aria-label=""{_pop(k)} style="position:absolute;left:0px;top:0px;width:1920px;height:1080px" '
                       f'viewBox="0 0 1920 1080">{body}</svg>')
    return out


def _beat_code_row() -> str:
    chips = "".join(f'<p{_pop(_beat_of(s))} style="font-size:32px;font-weight:700;color:{SKY_TEXT};background:{CARD};'
                    f'border:3px solid {SKY};border-radius:12px;padding:4px 16px">{label}</p>' for label, s in CODE)
    tag = f'<p style="font-size:32px;font-weight:800;letter-spacing:3px;color:{SKY_TEXT}">CODE</p>'
    return (f'<div style="position:absolute;left:{LEFT}px;top:{CODE_Y}px;width:{WIDTH}px;display:flex;gap:14px;'
            f'align-items:center;border-top:3px solid {LINE};padding-top:12px">{tag}{chips}</div>')


def build() -> list[str]:
    """The system growing from nothing to eleven agents, one click per beat, as pinned slide children."""
    out = [_ghost(col, k) for col, (_, agents) in enumerate(COLS) for k in range(len(agents))]
    out += _beat_wires()
    out.append(_loop(LOOP_STEP, LOOP_STEP).replace(_build(True), _pop(_beat_of(LOOP_STEP))))
    out.append(_canvas(CANVAS_STEP, CANVAS_STEP).replace(_build(True), _pop(_beat_of(CANVAS_STEP))))
    out += [_agent(col, k, a) for col, (_, agents) in enumerate(COLS) for k, a in enumerate(agents)]
    out.append(_beat_code_row())
    return out


# The rebuild, one stage per chapter (Sujit, 2026-10-20: "show a slide like this after every change"): each stage
# slide shows the band as it stood after the earlier chapters, then one click retires that chapter's agents (a dashed
# note in the seat says where the job went). Stage 5 is the static recap. Same seats as `build()`.
SHRINK: Final = {"riffsmith": (1, "→ Pandit"), "riff": (2, None), "ustad": (3, "→ code"),
                 "arranger": (2, "→ Rhythm"), "conductor": (4, "→ round cap")}
RHYTHM_STAGE: Final = 2
BASS_NOTE: Final = "→ Rhythm"


def _out(k: int) -> str:
    return f' data-build-out="fade {k}"'


def _box(col: int, k: int, inner: str, style: str, attr: str = "", top: float | None = None) -> str:  # noqa: PLR0913
    x, y = _cx(col) - NODE_W / 2, (_top(col, k) if top is None else top)
    return (f'<div{attr} style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{NODE_W}px;height:{NODE_H}px;'
            f'{style};border-radius:16px;display:flex;align-items:center;justify-content:center;gap:8px">{inner}</div>')


def _face(sprite: str, name: str) -> str:
    return (f'<img src="{SPRITES[sprite]}" alt="{name}" style="width:38px;height:52px;object-fit:contain">'
            f'<p style="font-size:32px;font-weight:800;color:{INDIGO}">{name}</p>')


def _note(text: str) -> str:
    return f'<p style="font-size:32px;font-weight:800;color:{MUTED}">{text}</p>'


NOTE_STYLE: Final = f"border:3px dashed {GHOST};background:{PAGE}"
CODE_STYLE: Final = f"background:{CARD};border:4px dashed {SKY}"
BECOMES_CODE: Final = {"ustad": "Rule check", "conductor": "Round cap"}   # Sujit, 2026-10-20: Ustad becomes a code box like bass and drums


def _code_label(label: str) -> str:
    return f'{V.braces_check(42, 34)}<p style="font-size:32px;font-weight:800;color:{SKY_TEXT}">{label}</p>'


NEW_STYLE: Final = f"background:{NEW_FILL};border:6px solid {MUSTARD}"


RING_IN: Final = ' data-build-in="pop 1" data-build-out="fade 2 auto"'
LEAVE: Final = ' data-build-out="fade 2 auto"'
NOTE_IN: Final = ' data-build-in="fade 3 auto"'
ARRIVE: Final = ' data-build-in="pop 4 auto"'


def _ring(col: int, k: int, top: float | None = None) -> str:
    """The 'this one is leaving' mark: a terracotta ring around the seat, shown first, gone with the seat."""
    x, y = _cx(col) - NODE_W / 2 - 10, (_top(col, k) if top is None else top) - 10
    return (f'<div{RING_IN} style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:{NODE_W + 20}px;'
            f'height:{NODE_H + 20}px;border:6px solid {TERRA};border-radius:22px"></div>')


def _calls(col: int, k: int, n: int, attr: str) -> str:
    """A model-call count in a small square inside a seat's right edge (Sujit, 2026-10-20: show both counts fall)."""
    x, y = _cx(col) + NODE_W / 2 - 54, _top(col, k) + (NODE_H - 46) / 2
    return (f'<p{attr} style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;width:46px;font-size:32px;font-weight:800;'
            f'line-height:1.3;color:{INDIGO};background:{MUSTARD};border-radius:8px;text-align:center">{n}</p>')


CALLS_LEGEND: Final = "model calls"


def _when(gone: int, stage: int, now_attr: str) -> str | None:
    """How a piece retired at `gone` appears on the `stage` slide: None = still there, "" = already gone (static),
    else the build attribute that animates it on this slide's click."""
    return None if gone > stage else ("" if gone < stage else now_attr)


def shrink(stage: int) -> list[str]:
    """The band after `stage` changes (1 composers merge, 2 guitar + bass become the rhythm section, 3 the legality
    critic becomes code, 4 the referee and the fixer become rules; 5 = everything applied, static)."""
    out = [_wires(11, 12, new=False), _loop(11, 12)]
    canvas = _when(RHYTHM_STAGE, stage, LEAVE)
    if canvas is None or canvas:
        out.append(_canvas(11, 12).replace("<div", f"<div{canvas or ''}", 1))
    for col, (_, agents) in enumerate(COLS):
        for k, agent in enumerate(agents):
            gone = SHRINK.get(agent)
            pad = ";padding-right:52px" if stage == RHYTHM_STAGE and agent in ("lead", "riff") else ""   # room for the call square
            seat = _box(col, k, _face(agent, NAMES[agent]), f"background:{CARD};border:4px solid {ROLE[agent]}{pad}")
            if gone is None:
                if agent == "pandit":
                    fused = _box(col, k, _face("fusion", "Pandit"), NEW_STYLE if stage == 1 else
                                 f"background:{CARD};border:4px solid {ROLE[agent]}", ARRIVE if stage == 1 else "")
                    out += [seat, fused] if stage == 1 else [fused]
                else:
                    out.append(seat)
                continue
            when = _when(gone[0], stage, LEAVE)
            if when is None or when:
                out.append(seat.replace("<div", f"<div{when or ''}", 1))
            if when:
                out.append(_ring(col, k))
            if when is not None and agent in BECOMES_CODE:   # the job is now code: the blue code seat takes the chair
                out.append(_box(col, k, _code_label(BECOMES_CODE[agent]), CODE_STYLE, ARRIVE if when else ""))
            elif when is not None and gone[1]:
                out.append(_box(col, k, _note(gone[1]), NOTE_STYLE, NOTE_IN if when else ""))
            if agent == "riff" and when is not None:
                out.append(_box(col, k, _face("rhythm", "Rhythm"), (NEW_STYLE + pad) if when else
                                f"background:{CARD};border:4px solid {TERRA}", ARRIVE if when else ""))
            if agent == "riff" and stage == RHYTHM_STAGE:   # calls on the opening song's five sections, before and after
                lead_k = COLS[col][1].index("lead")
                out += [_calls(col, k, 6, LEAVE), _calls(col, k, 1, ARRIVE),
                        _calls(col, lead_k, 7, ' data-build-out="fade 2 auto"'), _calls(col, lead_k, 3, ARRIVE),
                        f'<p style="position:absolute;left:{_cx(col) - NODE_W / 2:.0f}px;top:{LANE + 40:.0f}px;'
                        f'font-size:32px;font-weight:700;color:{MUTED};white-space:nowrap">'
                        f'<span style="color:{INDIGO}">■</span> {CALLS_LEGEND}</p>']
    # code seats: bass joins the rhythm section at stage 2; drums stay code
    bass_when = _when(RHYTHM_STAGE, stage, LEAVE)
    for label, col, row in CODE_SEATS:
        box = _code_seat(label, col, row, pop=False)
        if label == "Bass" and bass_when is not None:
            if bass_when:
                out.append(box.replace("<div", f"<div{bass_when}", 1))
                out.append(_ring(col, 0, top=TOP + row * ROW))
            out.append(_box(col, 0, _note(BASS_NOTE), NOTE_STYLE, NOTE_IN if bass_when else "", top=TOP + row * ROW))
        else:
            out.append(box)
    out.append(_stage_code_row(stage))
    return [x for x in out if x]


STAGE_CODE_GAP: Final = 110   # the stage slides have no caption card, so the code row sits lower (2026-10-20)


def _stage_code_row(stage: int) -> str:
    """The code row as it stands after `stage`: the canvas is gone and the bass is the rhythm section's from stage 2."""
    labels = [label for label, _ in CODE]
    if stage >= RHYTHM_STAGE:
        labels = ["drums" if lab == "bass · drums" else lab for lab in labels if lab != "canvas"]
    chips = "".join(f'<p style="font-size:32px;font-weight:700;color:{SKY_TEXT};background:{CARD};border:3px solid {SKY};'
                    f'border-radius:12px;padding:4px 16px">{lab}</p>' for lab in labels)
    tag = f'<p style="font-size:32px;font-weight:800;letter-spacing:3px;color:{SKY_TEXT}">CODE</p>'
    return (f'<div style="position:absolute;left:{LEFT}px;top:{CODE_Y + STAGE_CODE_GAP}px;width:{WIDTH}px;display:flex;'
            f'gap:14px;align-items:center;border-top:3px solid {LINE};padding-top:12px">{tag}{chips}</div>')


# The pipeline's groups, outlined like the reveal slide (Sujit, 2026-10-20: "show outlines like slide 4"), so the
# room sees the shape of the band before any agent arrives: (label, first column, last column).
GROUPS: Final = (("Front door", 0, 0), ("Plan the song", 1, 1), ("Write and enrich the parts", 2, 3),
                 ("Judge the song", 4, 4), ("Settle", 5, 5))
GROUP_EDGE: Final = "#C9C2B8"


def groups() -> list[str]:
    """Dashed outlines around each stage of the pipeline, with its name above: static, drawn first."""
    out = []
    y0, y1 = TOP - 12, TOP + 2 * ROW + NODE_H + 10
    for label, a, b in GROUPS:
        x0, x1 = _cx(a) - NODE_W / 2 - 14, _cx(b) + NODE_W / 2 + 14
        out.append(f'<div style="position:absolute;left:{x0:.0f}px;top:{y0:.0f}px;width:{x1 - x0:.0f}px;'
                   f'height:{y1 - y0:.0f}px;border:3px dashed {GROUP_EDGE};border-radius:22px"></div>')
        out.append(f'<p style="position:absolute;left:{x0 + 6:.0f}px;top:{y0 - 48:.0f}px;font-size:32px;font-weight:800;'
                   f'color:{MUTED};white-space:nowrap">{label}</p>')
    return out


# Bass and drums are code, not agents (Sujit, 2026-10-20: show them in "write and enrich the parts", dashed in the
# code colour): the free seats above and below the Arranger, popping in with the beat that made them code (step 6).
CODE_SEATS: Final = (("Bass", 3, 0), ("Drums", 3, 2))
CODE_SEAT_STEP: Final = 6


def _code_seat(label: str, col: int, row: int, pop: bool) -> str:
    x, y = _cx(col) - NODE_W / 2, TOP + row * ROW
    return (f'<div{_pop(_beat_of(CODE_SEAT_STEP)) if pop else ""} style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;'
            f'width:{NODE_W}px;height:{NODE_H}px;background:{CARD};border:4px dashed {SKY};border-radius:16px;display:flex;'
            f'align-items:center;justify-content:center;gap:12px">{V.braces_check(56, 46)}'
            f'<p style="font-size:32px;font-weight:800;color:{SKY_TEXT}">{label}</p></div>')


def code_seats(pop: bool = True) -> list[str]:
    """Bass and drums as code boxes; `pop` = arrive on the build's beat, else drawn from the start."""
    return [_code_seat(label, col, row, pop) for label, col, row in CODE_SEATS]
