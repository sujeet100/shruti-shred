"""The agentic patterns the talk teaches (Sujit, 2026-10-18): what each one is, when to use it, when
not to, and what happened when we tried it.

Each pattern is introduced in Act 1 at the moment we adopted it (an INTRO card: the pattern in
general, a small abstract diagram), and judged in Act 3 (a VERDICT card: our version, its evidence,
and the precondition we lacked). One record per pattern feeds both cards, so a definition can never
drift between them. Only the well-known agentic patterns get cards; plain engineering (handoffs,
plans, guardrails) stays in the story and the lessons.

Diagrams are wordless (fonts never load inside a slide's SVG): plain nodes and straight arrows,
no cycle arrows and no tool icons (both rejected for the deck). Pure: data and SVG strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import visuals as V

INDIGO, CARD, MUTED = V.INDIGO, V.CARD, V.MUTED
TERRA, MUSTARD, SKY, PURPLE = V.TERRA, V.MUSTARD, V.SKY, V.PURPLE
W, H = 600, 360                              # every diagram's own drawing size


@dataclass(frozen=True)
class Pattern:
    key: str
    name: str
    what: str                                # one short line, the pattern in general
    use_when: str | tuple[str, ...]          # the precondition (bullets when it lists conditions)
    avoid_when: str | tuple[str, ...]        # what breaks it (bullets when it lists conditions)
    why_us: str                              # why we reached for it (Act 1)
    verdict: str                             # the chip (Act 3)
    verdict_color: str
    headline: str                            # the verdict card's claim
    evidence: tuple[str, ...]                # what happened, measured
    takeaway: str                            # the precondition we lacked, or the rule
    cast: tuple[str, ...]                    # our agents who played it (band sprites)
    intro_notes: str
    verdict_notes: str
    also: str = ""                           # a second pattern composed into this one (a chip on its card)


# --------------------------------------------------------------------------- #
# The diagrams.                                                               #
# --------------------------------------------------------------------------- #

def _node(x: float, y: float, r: float = 30, color: str = INDIGO, fill: str = CARD) -> str:
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{color}" stroke-width="7"/>'


def _diamond(x: float, y: float, r: float = 38, color: str = TERRA) -> str:
    return (f'<polygon points="{x},{y - r} {x + r},{y} {x},{y + r} {x - r},{y}" fill="{CARD}" stroke="{color}" '
            f'stroke-width="7" stroke-linejoin="round"/>')


def _square(x: float, y: float, r: float = 30, color: str = SKY) -> str:
    return (f'<rect x="{x - r}" y="{y - r}" width="{2 * r}" height="{2 * r}" rx="8" fill="{CARD}" stroke="{color}" '
            f'stroke-width="7"/>')


def _arrow(x1: float, y1: float, x2: float, y2: float, color: str = MUTED, *, gap: float = 40,
           dashed: bool = False) -> str:
    """A straight arrow from one node to another, stopping `gap` short of each centre."""
    dx, dy = x2 - x1, y2 - y1
    n = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / n, dy / n
    ax, ay, bx, by = x1 + ux * gap, y1 + uy * gap, x2 - ux * gap, y2 - uy * gap
    hx, hy = bx - ux * 18, by - uy * 18
    dash = ' stroke-dasharray="3 14"' if dashed else ""
    return (f'<path d="M{ax:.1f} {ay:.1f} L{bx:.1f} {by:.1f}" stroke="{color}" stroke-width="6" '
            f'stroke-linecap="round"{dash}/>'
            f'<path d="M{hx - uy * 13:.1f} {hy + ux * 13:.1f} L{bx:.1f} {by:.1f} L{hx + uy * 13:.1f} {hy - ux * 13:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>')


def _person(x: float, y: float, color: str = MUSTARD) -> str:
    return (f'<circle cx="{x}" cy="{y - 26}" r="18" fill="{color}"/>'
            f'<path d="M{x - 30} {y + 30} C{x - 30} {y - 4}, {x + 30} {y - 4}, {x + 30} {y + 30} Z" fill="{color}"/>')


def _orchestrator() -> str:
    lead, out = (300, 50), (300, 310)
    workers = [(110, 180), (300, 180), (490, 180)]
    body = [_arrow(*lead, *w) for w in workers] + [_arrow(*w, *out) for w in workers]
    return "".join(body + [_node(*lead, 36, MUSTARD)] + [_node(*w, 26) for w in workers] + [_node(*out, 26, SKY)])


def _react() -> str:
    model, tool, answer = (170, 150), (450, 150), (170, 310)
    return (_arrow(170, 125, 450, 125, gap=44) + _arrow(450, 178, 170, 178, SKY, gap=44, dashed=True)
            + _arrow(*model, *answer, gap=44) + _node(*model, 38, MUSTARD) + _square(*tool, 34) + _node(*answer, 24, SKY))


def _evaluator() -> str:
    writer, critic, out = (160, 150), (450, 150), (160, 310)
    return (_arrow(160, 126, 450, 126, gap=44) + _arrow(450, 176, 160, 176, TERRA, gap=44, dashed=True)
            + _arrow(*writer, *out, gap=44) + _node(*writer, 38, MUSTARD) + _diamond(*critic, 40) + _node(*out, 24, SKY))


def _selfcorrect() -> str:
    """The model writes; a code check (a square: it measures, it doesn't judge) sends the exact
    fault back once; what passes flows on."""
    writer, check, out = (150, 150), (450, 150), (450, 310)
    box = (f'<rect x="{check[0] - 40}" y="{check[1] - 40}" width="80" height="80" rx="10" fill="{CARD}" '
           f'stroke="{SKY}" stroke-width="8"/>')
    return (_arrow(150, 126, 450, 126, gap=44) + _arrow(450, 176, 150, 176, TERRA, gap=44, dashed=True)
            + _arrow(*check, *out, SKY, gap=46) + _node(*writer, 38, MUSTARD) + box + _node(*out, 24, SKY))


def _debate() -> str:
    a, b, judge = (120, 110), (480, 110), (300, 300)
    return (_arrow(120, 80, 480, 80, gap=44) + _arrow(480, 125, 120, 125, gap=44) + _arrow(120, 170, 480, 170, gap=44)
            + _arrow(*a, *judge, gap=46) + _arrow(*b, *judge, gap=46)
            + _node(*a, 36, SKY) + _node(*b, 36, PURPLE) + _diamond(*judge, 42))


def _collaboration() -> str:
    """Two equals either side of one shared canvas, each writing to it and reading the other's work."""
    a, b = (80, 180), (520, 180)
    canvas = (f'<rect x="210" y="105" width="180" height="150" rx="14" fill="{CARD}" stroke="{MUTED}" '
              f'stroke-width="6" stroke-dasharray="4 12"/>')
    return (canvas + _arrow(a[0], 155, 300, 155, SKY, gap=44) + _arrow(300, 205, a[0], 205, PURPLE, gap=44, dashed=True)
            + _arrow(b[0], 205, 300, 205, PURPLE, gap=44) + _arrow(300, 155, b[0], 155, SKY, gap=44, dashed=True)
            + _node(*a, 36, SKY) + _node(*b, 36, PURPLE))


def _hitl() -> str:
    xs = (60, 190, 330, 480)
    body = [_arrow(xs[0], 200, xs[1], 200, gap=34), _arrow(xs[1], 200, xs[2], 200, gap=40),
            _arrow(xs[2], 200, xs[3], 200, gap=44)]
    return "".join(body + [_node(xs[0], 200, 24), _node(xs[1], 200, 24), _diamond(xs[2], 200, 42, MUSTARD),
                           _person(xs[2], 90), _node(xs[3], 200, 26, SKY)])


def _workflow() -> str:
    """Fixed steps left to right, one bounded loop back, three ticks for the round limit."""
    xs = (60, 190, 320, 450, 560)
    body = [_arrow(xs[i], 200, xs[i + 1], 200, gap=34) for i in range(4)]
    loop = (f'<path d="M450 166 C450 96, 320 96, 320 160" fill="none" stroke="{TERRA}" stroke-width="6" '
            f'stroke-dasharray="3 14" stroke-linecap="round"/>'
            f'<path d="M308 146 L320 166 L332 146" fill="none" stroke="{TERRA}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>')
    ticks = "".join(f'<rect x="{350 + k * 26}" y="270" width="16" height="34" rx="4" fill="none" stroke="{MUTED}" stroke-width="5"/>'
                    for k in range(3))
    nodes = [_node(xs[0], 200, 24), _node(xs[1], 200, 26), _node(xs[2], 200, 26), _node(xs[3], 200, 26, TERRA), _node(xs[4], 200, 24, SKY)]
    return "".join(body) + loop + ticks + "".join(nodes)


def _chaining() -> str:
    """One owner's calls in a fixed row, each feeding the next, a code check (a square) between them."""
    calls, checks = (60, 230, 400, 570), (145, 315, 485)
    body = [_arrow(calls[i], 180, calls[i + 1], 180, gap=30) for i in range(3)]
    gates = "".join(f'<rect x="{x - 14}" y="166" width="28" height="28" rx="5" fill="{CARD}" stroke="{SKY}" stroke-width="6"/>'
                    for x in checks)
    return "".join(body) + gates + "".join(_node(x, 180, 26, MUSTARD) for x in calls)


DIAGRAMS: Final = {"chaining": _chaining, "orchestrator": _orchestrator, "react": _react, "evaluator": _evaluator, "debate": _debate,
                   "selfcorrect": _selfcorrect,
                   "collaboration": _collaboration, "hitl": _hitl, "workflow": _workflow}


# --------------------------------------------------------------------------- #
# The animations: tokens act each pattern out on a loop (SMIL, no script).    #
# Times are shares of PERIOD_S; a token is visible only while it moves.        #
# --------------------------------------------------------------------------- #

PERIOD_S: Final = 6.0


def _seg(x1: float, y1: float, x2: float, y2: float, gap: float = 40) -> str:
    dx, dy = x2 - x1, y2 - y1
    n = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / n, dy / n
    return f"M{x1 + ux * gap:.1f} {y1 + uy * gap:.1f} L{x2 - ux * gap:.1f} {y2 - uy * gap:.1f}"


def _move(d: str, color: str, t0: float, t1: float, r: float = 11) -> str:
    """A token travelling `d` between t0 and t1 (shares of the loop), hidden otherwise."""
    loop = f'dur="{PERIOD_S:g}s" repeatCount="indefinite"'
    return (f'<circle r="{r}" fill="{color}" opacity="0">'
            f'<animate attributeName="opacity" values="0;1;0" keyTimes="0;{t0:.3f};{t1:.3f}" calcMode="discrete" {loop}/>'
            f'<animateMotion path="{d}" keyPoints="0;0;1;1" keyTimes="0;{t0:.3f};{t1:.3f};1" calcMode="linear" {loop}/></circle>')


def _pulse(x: float, y: float, color: str, t: float, r0: float = 30, r1: float = 52) -> str:
    """A ring that swells once around a node at t: it is working, or deciding."""
    loop = f'dur="{PERIOD_S:g}s" repeatCount="indefinite"'
    k = f'keyTimes="0;{t - 0.005:.3f};{t:.3f};{t + 0.08:.3f};1"'          # held at rest until its moment
    return (f'<circle cx="{x}" cy="{y}" r="{r0}" fill="none" stroke="{color}" stroke-width="6" opacity="0">'
            f'<animate attributeName="r" values="{r0};{r0};{r0};{r1};{r1}" {k} {loop}/>'
            f'<animate attributeName="opacity" values="0;0;0.9;0;0" {k} {loop}/></circle>')


def _a_orchestrator() -> str:
    lead, out, ws = (300, 50), (300, 310), ((110, 180), (300, 180), (490, 180))
    return ("".join(_move(_seg(*lead, *w), MUSTARD, 0.05, 0.28) for w in ws)
            + "".join(_pulse(*w, SKY, 0.30, 26, 46) for w in ws)
            + "".join(_move(_seg(*w, *out), SKY, 0.45, 0.68) for w in ws) + _pulse(*out, SKY, 0.70, 26, 50))


def _a_react() -> str:
    up, down, answer = "M214 125 L406 125", "M406 178 L214 178", _seg(170, 150, 170, 310, 44)
    return (_move(up, MUSTARD, 0.04, 0.18) + _pulse(450, 150, SKY, 0.19, 34, 54) + _move(down, SKY, 0.27, 0.41)
            + _move(up, MUSTARD, 0.45, 0.59) + _pulse(450, 150, SKY, 0.60, 34, 54) + _move(down, SKY, 0.68, 0.80)
            + _move(answer, MUSTARD, 0.84, 0.97))


def _a_evaluator() -> str:
    up, down, out = "M204 126 L406 126", "M406 176 L204 176", _seg(160, 150, 160, 310, 44)
    return (_move(up, MUSTARD, 0.04, 0.18) + _pulse(450, 150, TERRA, 0.19, 40, 60) + _move(down, TERRA, 0.27, 0.41)
            + _move(up, MUSTARD, 0.46, 0.60) + _pulse(450, 150, SKY, 0.61, 40, 60) + _move(out, MUSTARD, 0.72, 0.88))


def _a_debate() -> str:
    a, b, judge = (120, 110), (480, 110), (300, 300)
    return (_move("M164 80 L436 80", SKY, 0.04, 0.17) + _move("M436 125 L164 125", PURPLE, 0.20, 0.33)
            + _move("M164 170 L436 170", SKY, 0.36, 0.49) + _move(_seg(*a, *judge, 46), SKY, 0.55, 0.72)
            + _move(_seg(*b, *judge, 46), PURPLE, 0.55, 0.72) + _pulse(*judge, TERRA, 0.74, 42, 64))


def _a_collaboration() -> str:
    return (_move("M124 155 L256 155", SKY, 0.04, 0.16) + _pulse(300, 180, MUTED, 0.17, 60, 84)
            + _move("M344 155 L476 155", SKY, 0.24, 0.36) + _move("M476 205 L344 205", PURPLE, 0.48, 0.60)
            + _pulse(300, 180, MUTED, 0.61, 60, 84) + _move("M256 205 L124 205", PURPLE, 0.68, 0.80))


def _a_hitl() -> str:
    return (_move(_seg(60, 200, 190, 200, 34), INDIGO, 0.04, 0.16) + _move(_seg(190, 200, 330, 200, 40), INDIGO, 0.18, 0.30)
            + _pulse(330, 90, MUSTARD, 0.36, 40, 66) + _pulse(330, 200, MUSTARD, 0.46, 42, 64)
            + _move(_seg(330, 200, 480, 200, 44), MUSTARD, 0.56, 0.70) + _pulse(480, 200, SKY, 0.72, 26, 48))


def _a_workflow() -> str:
    xs = (60, 190, 320, 450, 560)
    steps = [_move(_seg(xs[i], 200, xs[i + 1], 200, 34), INDIGO, 0.03 + i * 0.09, 0.11 + i * 0.09) for i in range(3)]
    loop = "M450 166 C450 96, 320 96, 320 160"
    rounds = []
    for k, t in enumerate((0.31, 0.53)):
        rounds.append(_move(loop, TERRA, t, t + 0.09))
        rounds.append(f'<rect x="{350 + k * 26}" y="270" width="16" height="34" rx="4" fill="{TERRA}" opacity="0">'
                      f'<animate attributeName="opacity" values="0;1;0" keyTimes="0;{t + 0.09:.3f};0.97" calcMode="discrete" '
                      f'dur="{PERIOD_S:g}s" repeatCount="indefinite"/></rect>')
        rounds.append(_move(_seg(320, 200, 450, 200, 34), INDIGO, t + 0.11, t + 0.19))
    exit_ = _move(_seg(450, 200, 560, 200, 34), SKY, 0.78, 0.88) + _pulse(560, 200, SKY, 0.89, 24, 46)
    return "".join(steps) + "".join(rounds) + exit_


ANIMATIONS: Final = {"orchestrator": _a_orchestrator, "react": _a_react, "evaluator": _a_evaluator,
                     "debate": _a_debate, "collaboration": _a_collaboration, "hitl": _a_hitl,
                     "workflow": _a_workflow}


def diagram(key: str, w: int = 540, h: int = 324, label: str = "", *, animated: bool = False) -> str:
    """The pattern's wordless diagram; `animated` adds the tokens that act it out (intro cards)."""
    return V.svg(w, h, DIAGRAMS[key]() + (ANIMATIONS[key]() if animated else ""), label, (W, H))


# --------------------------------------------------------------------------- #
# The patterns, in the order they appear in Act 1.                            #
# --------------------------------------------------------------------------- #

PATTERNS: Final[dict[str, Pattern]] = {p.key: p for p in (
    Pattern(
        key="hitl", name="Human in the loop",
        what="A person makes the one decision that matters; code checks the rest.",
        use_when=("The real judge is a person", "One decision needs a human"),
        avoid_when=("Code can check it", "Too much to review well"),
        why_us="Tonight, that will be you: before questions, you pick how the piece ends, and it composes while we talk.",
        verdict="The strongest here", verdict_color=MUSTARD,
        headline="The comparisons that mattered were decided by a person listening",
        evidence=("Every model judge we built (the seed judge, the Producer, the debate) was a prediction of one listener's ear.",
                  "Where a model judge and my ear disagreed, my blind listening settled it.",
                  "The audio judge gets no vote until it agrees with my rankings; it hasn't yet."),
        takeaway="Spend people's attention on the one decision that matters, and calibrate every model judge against them.",
        cast=(),
        intro_notes="Just before its verdict. We never put a human in the pipeline, yet a blind ear overruled our own judge: Y was the first draft, the judge had shipped X. Name the pattern, then promise the room its part: just before questions they make the one decision that matters, the ending.",
        verdict_notes="We never built a human into the pipeline; the talk is the only place it runs. Yet the key comparisons were settled by Sujit listening, blind where the record says so, and every model judge was a guess at that ear. The 70% agreement bar for the audio judge is our proposed gate, not one it has met. The most advanced agent in this system is the person in the room; the architecture's job is to spend that attention where it counts."),
    Pattern(
        key="orchestrator", name="Sectioning", also="Blackboard",
        what="Code splits the work into fixed parts; separate calls do each; code combines them.",
        use_when=("The parts are truly independent", "You know the split in advance"),
        avoid_when="The parts are one idea, conceived together.",
        why_us="One prompt per instrument never listened. So two composers wrote a shared chart, and a worker per instrument filled it in.",
        verdict="Reshaped", verdict_color=PURPLE,
        headline="The parts were one idea, so one owner took them back",
        evidence=("Sectioning: the sitar and the riff were written apart, and one idea came back as a collage.",
                  "Blackboard: equals traded concessions, on the plan and then on the parts. Nobody owned the whole idea, though it played tonight's opener.",
                  "Now Pandit owns the idea, and the Rhythm section writes the guitar after hearing every sitar note. Blind, its guitar fit the hook better than Pandit's own riff."),
        takeaway="One idea needs one owner. Split by information, not by job title.",
        cast=("pandit", "riffsmith", "lead", "riff"),
        intro_notes="Two patterns composed. First a blackboard for the plan: one shared chart, two equals writing on it in turns, each bringing their own expertise. Pandit (tradition) and Riffsmith (metal) each read the other's last draft, kept one thing, pushed back on one, and wrote the next version of the whole chart; code fixed the order (Pandit first, then alternate) and capped the turns, and nobody was the judge. Two authors who must both accept tend to meet in the middle, so it ended in a compromise. The same blackboard appeared one level down in the studio session, where the sitar and the riff wrote in turn on a shared canvas; that is how the opening song was made (its definition card is in the annex). This was never a debate: there was no judge and no competing answers, just two authors revising one shared chart until both accepted. Then sectioning, Anthropic's name for the fixed split: for every section, code called the Lead for the sitar and the Riff for the guitar, separately, and merged them. Say it plainly: no model chose the workers; the split was ours, in code. Sectioning is the predetermined cousin of orchestrator-workers, where a lead model decides the split at run time; use it when you know the parts in advance, and only when they are truly independent. Ours were not. Each pattern brought its own failure, which the verdict shows: the co-written plan was a compromise, the split was a collage.",
        verdict_notes="One verdict for both patterns. Sectioning: the split followed job titles, not information; every worker saw the same chart and knew the same raga, and nothing about the work was separable, so the sitar and the riff came back as a collage. Blackboard: the composers co-wrote the plan and the studio session shared a canvas for the parts; both traded concessions, and nobody owned the whole idea. The studio session did compose the piece that opened tonight, so it worked well enough to perform, but in our measured songs one owner did better. What survived is a handoff: Pandit owns the plan, the hook and the sitar line, and the Rhythm section writes guitar and bass after it can see the finished sitar line. Two honest caveats. The riff that lost was also written under a rule that forced most of it into chugs, and the redesign removed that rule in the same step as the merge, so the two causes were never separated. And a later blind test asked who should write the guitar under the hook: five songs, the first mukhada with Pandit's seed riff or with the Rhythm section's guitar, all else identical. The Rhythm section won three of five; Pandit's riff lost by being too busy or clashing, because it is written before the sitar exists. The rule: split agents where the information or the judgment differs, never where the job titles do."),
    Pattern(
        key="react", name="Tool use (ReAct)",
        what="The model reasons, calls a tool, reads the result, decides the next step.",
        use_when=("The model needs information while it works", "Only the tool can supply it"),
        avoid_when=("A check could run after the answer", "It reports a number to chase"),
        why_us="Our legality critic called the validator in the middle of its reasoning, to explain a wrong note rather than just flag it.",
        verdict="Mixed", verdict_color=MUSTARD,
        headline="Checks as tools made the agent slow",
        evidence=("Given our rule checks as tools, the composer fixed its own faults, but took about three times as long.",
                  "The same checks run by code after it answers, with one retry, did that job in a third of the time.",
                  "A tool earns its place when the model needs information it cannot have before it starts."),
        takeaway="Check the answer in code and retry. Give tools only for what the model must look up.",
        cast=("ustad", "composer"),
        intro_notes="ReAct: reason, act, observe. Ustad was our first tool user: it called validate_composition mid-reasoning, visible in the trace.",
        verdict_notes=("The lesson in one line: a deterministic check works best AFTER the answer, as a guardrail with one "
                       "retry; as a tool the agent calls mid-task it makes every step slower. Tools are for information the "
                       "model needs at run time and cannot be given up front. Three tries. Ustad's tool restated code's verdict, so the agent added cost and no information. The "
                       "hear_phrase tool reported which held notes would sway; Pandit lengthened exactly those notes and "
                       "lost the cadence that makes Darbari Darbari, and blind, the version without the tool won. The third, on 19 "
                       "October: Pandit as a real agent, its tools the very checks code applies (raga grammar, the head's "
                       "rules, the alap's call and answer), deciding when to check and when it was done. Same Bhairav request "
                       "as the morning's workflow song: it caught and fixed six faults itself, so code had to send back none "
                       "(the workflow's drafts were sent back three times), but composing took 11.8 minutes instead of "
                       "4.1, 20 calls instead of 9, plus one format retry tool mode costs. Sujit's ear preferred it. One caveat, said out "
                       "loud: its chart drew a different form, so the win is not yet isolated. It stays off by default; it "
                       "would never fit a live slot.")),
    Pattern(
        key="workflow", name="Predefined workflow",
        what="Code fixes the steps and their order; models think inside each step.",
        use_when=("You know the steps", "\u201cpredictability and consistency\u201d (Anthropic)"),
        avoid_when=("Nobody knows the path ahead", "Errors would compound"),
        why_us="Composing has known stages, and on stage it must always finish. CrewAI's advice: \u201cFor any production-ready application, start with a Flow.\u201d",
        verdict="Kept", verdict_color=SKY,
        headline="The fixed workflow is the one structure we never regretted",
        evidence=("Every run ends: the judge gets one round, capped in code, never ended by agents agreeing.",
                  "Every step is visible: about twenty model calls a song, each one in the trace.",
                  "Twice a model that chose its own steps chased what it was shown; the third time it won, at 3× the minutes."),
        takeaway="Start with a predefined workflow. Let a model choose the path only where nobody can.",
        cast=("interpreter", "composer", "rhythm", "producer"),
        intro_notes="Sources, verbatim: Anthropic, workflows give \u201cpredictability and consistency for well-defined tasks\u201d; agents bring \u201chigher costs, and the potential for compounding errors\u201d. Step 8 made the whole pipeline one CrewAI Flow. Name the pattern: a predefined workflow, where code fixes the order of the steps and models think inside them, as opposed to an autonomous agent that decides what to do next. Anthropic draws the same line (workflows vs agents) and says start simple; CrewAI's docs say: for any production-ready application, start with a Flow. Why not a dynamic workflow or a ReAct agent driving the whole thing? Our steps are known, and a live show must always end.",
        verdict_notes="The one pattern we kept unchanged from day one. The round limit lives in code, so termination never depends on agents converging; every step is traced; and when we handed a model control of its own next step it either optimised what the tool reported rather than the music (twice), or won by ear at three times the time (once, on 19 October). And stopping is not accepting: a round limit only bounds the effort, so a final code check stands between 'we stopped' and 'this ships', falling back to the last take that passed."),
    Pattern(
        key="evaluator", name="Evaluator–optimiser",
        what="One agent writes, another critiques, the writer revises, until accepted or capped.",
        use_when=("The criteria are clear", "The judge agrees with real listeners"),
        avoid_when=("It misses what matters", "Rounds don't measurably help"),
        why_us="Correct notes weren't good music. So two critics scored the raga and the song, and the composer revised.",
        verdict="Reworked", verdict_color=TERRA,
        headline="The judge asked for a revision every time",
        evidence=("Its edits made its own scores go up about as often as down. Most of them copied the raga critic.",
                  "Listening blind, I preferred the first draft to the revision we shipped.",
                  "Now it decides before it reads the raga critic, accepts by default, and keeps a revision only if it wins in both orders."),
        takeaway="Accept by default. A revision has to beat the draft, in both orders.",
        cast=("rasik", "producer"),
        intro_notes="The loop every agent framework demos. Ours: Rasik advises on the raga, the Producer judges the song, Pandit revises; the round limit is in code. The test that tells it from debate: one draft, revised until a critic accepts it, with fixed roles, one side writing and the other judging.",
        verdict_notes="Measured across every recorded run with an explicit accept-or-revise decision (14 runs): it requested a revision in all 14, often right after praising it; 87% of its scores were 4 or 5, and after an edit they rose as often as they fell; 30 of 36 plans copied Rasik near-verbatim. In the one blind test the first draft won, and the loop had shipped the revision its own judge scored lower. The fix is structural: accept by default, describe problems not notes, one round, and keep a revision only if it wins a side-by-side comparison in both orders. Since the rework it accepted the first draft in both live runs of 19 October; on 20 October it asked for one revision, rightly: the taan's peak landed early, a fault its two tries had not fixed, and the revision won the comparison in both orders. The last fix is independence: it used to read Rasik's notes before judging and copied them, so the two critics now judge in parallel, blind to each other, and the Producer reads Rasik only when Rasik flags the raga, in a second look."),
    Pattern(
        key="debate", name="Multi-agent debate",
        what="Each agent defends its own answer; a judge picks between them.",
        use_when=("Each side owns its work", "A comparison decides what stays"),
        avoid_when=("Same model, same facts", "Arguing knobs, not notes"),
        why_us="Our raga critic and our song critic disagreed. A Conductor refereed a bounded debate between them.",
        verdict="Reworked", verdict_color=TERRA,
        headline="The debate that argued about notes helped, a little",
        evidence=("Two composers, same facts: the rival added nothing the measurements didn't, at twice the cost.",
                  "A band that could only turn knobs kept turning the guitar down, and the song went hollow.",
                  "Two players rewriting their own notes: a few edits I preferred, none I liked less, across two songs."),
        takeaway="Debate the notes, give each side a part it owns, and keep only what wins.",
        cast=("lead", "riff"),
        intro_notes="The test, say it out loud: one draft revised until a critic accepts it is evaluator-optimiser; several positions, and a judge picks between them, is debate. Du et al.'s multi-agent debate: agents answer, read each other, update over a few rounds, and gains come in rounds one and two; Irving et al.'s adversarial form has two sides and a judge. Ours, by that test: the critics' debate (Rasik against the Producer, the Conductor ruling) and the head debate (two composers' heads, a judge choosing) are debates; the notes debate is closer to debate, since each player owns a candidate rewrite and a comparison picks; the composers' chart in the ownership chapter was neither: no judge and no fixed critic, just two equals co-writing one draft, which is a blackboard: two equals co-writing one shared chart.",
        verdict_notes=("Five designs. The critics' debate rewrote half the music each turn. The seed debate, Gemini against "
                       "OpenAI's Sol, wrote one piece seven times: same facts, same answer. The head debate's control showed "
                       "the rival added nothing the measurements didn't. The rehearsal, a band with only volume knobs, "
                       "subtracted guitar until the song was hollow, and its audio judges described music that wasn't "
                       "playing. The fifth, the notes debate: a Gemini sitarist and a gpt-6-luna guitarist each rewrite "
                       "notes of their own part, critique each other, and revise; code checks every rewrite; an "
                       "order-swapped comparison keeps only winners. The second model caught a false premise and a 17-beat "
                       "bar. Two songs, four rewrites, judged by ear: two better, one sidegrade, one neutral, none worse. Different models, ownership, scope and prompts all changed at once, so the gain is not proof that model diversity did it. Now in the pipeline, and it runs only when a reviewer names a concern the players can fix; that concern is their brief.")),
    Pattern(
        key="collaboration", name="Peer collaboration",
        what=("Agents work as equals, with no boss", "Any agent can message any other", "They decide among themselves who goes next"),
        use_when=("Each agent owns a different part", "The work gets better in turns"),
        avoid_when=("It must finish in a fixed number of turns", "You need to know who speaks next"),
        why_us="The sitar and the guitar kept clashing. So they composed together in a studio session: a shared canvas, a few bounded passes, the lead rotating by section.",
        verdict="Dropped", verdict_color=TERRA,
        headline="Two equal owners wrote a compromise; one owner wrote a song",
        evidence=("The studio session composed the piece that opened tonight, so it worked well enough to perform.",
                  "But in our measured songs one owner did better: the riff and the hook are one idea, and passing it back and forth diluted it.",
                  "What survived is a handoff, not a negotiation: the guitar is written after the sitar, seeing every note."),
        takeaway="What we lacked: two parts that are really separate.",
        cast=("lead", "riff", "rhythm"),
        intro_notes="The textbook pattern, the way most people picture multi-agent: a studio room. The bassist says I'll lay down a bass line, the guitarist says I'll go next, the drummer locks to the riff, the sitarist comes in on the sam; then they refine each other's parts. Frameworks ship this as a group chat: any agent can address any other, and the agents themselves pick the next speaker. The scene is an illustration, not a trace. Its two challenges are why we didn't build it: it can take many more turns, because nobody decides when it's done, and who goes next is decided by the agents, so you can't predict or debug the order. NEXT: the two side by side, and why we chose the blackboard.",
        verdict_notes="Collaboration needs separable ownership. Here the hook and the riff are one idea; the working version is a sequential handoff, where the rhythm section writes after it can see the finished sitar line."),
)}

PATTERNS["selfcorrect"] = Pattern(
    key="selfcorrect", name="Self-correction from code",
    what="The model writes; code checks; the exact fault goes back; one retry.",
    use_when=("The rule is checkable in code", "The fault can be named"),
    avoid_when=("The model checks itself", "It keeps needing retries"),
    why_us="Illegal notes slipped through unseen. So code checks every answer, and a rejected answer goes back with the exact fault.",
    verdict="Kept", verdict_color=SKY,
    headline="It ignored the rule until we measured its draft",
    evidence=("Told to dwell in the low register, the drafts didn't. Shown how little time they spent there, they moved.",
              "One overshot and lost the middle. Code keeps a revision only if it fixes a measured miss without breaking another check.",
              "Legality works the same way: the exact fault goes back, and one retry fixes it."),
    takeaway="Tell the model the rule, then measure its draft and show it the result.",
    cast=("composer",),
    intro_notes=("Anthropic's evaluator-optimizer, with code as the evaluator. The research line is CRITIC (Gou et al., "
                 "2023): models correct themselves well with feedback from a tool, and poorly without it (Huang et al., "
                 "2023, \u201cLarge Language Models Cannot Self-Correct Reasoning Yet\u201d). Ours: every agent's answer "
                 "passes a guardrail in code, and a rejected answer goes back with the exact fault, once. If a step "
                 "routinely needs two retries, fix the prompt, not the retry count. The scene is verbatim from the "
                 "Bageshree run: the validator's message, then the pass."),
    verdict_notes=("Every agent kept it for legality. The new result is craft: the gat head's prompt says, in plain "
                   "words, dwell below Sa. Ten drafts ignored it. Measure the draft, show the composer its own number, "
                   "and it moves on the first pass. The failure inside it: one composer chased the number to 94% and "
                   "lost the middle register, so code keeps a revision only if it fixes a missed fact without breaking "
                   "one the draft met. And replaying the real heads caught our own keep-rule judging backwards before it "
                   "shipped. CRITIC was right: feedback from a tool works; a model judging itself doesn't."),
)

# Every pattern two ways (Sujit, 2026-10-19: "how could each be built the agentic way, and what does it cost?"):
# (the agentic version — the model decides what happens next, what it costs and what we saw). Feeds the
# synthesis slide at the end of Act 2 and each verdict card's speaker notes.
AGENTIC: Final[dict[str, tuple[str, str, str]]] = {
    "workflow": ("a model picks each next step", "every judge we measured over-edited",
                 "We never handed the whole flow to a model. An orchestrating LLM would decide when the song is done, "
                 "and the Producer, the head debate and the rehearsal all showed models either revise too much or "
                 "chase what they are shown; a live demo also needs a run that always ends."),
    "selfcorrect": ("it checks itself, stops when done", "better by ear once, 3× the time",
                    "Built and run on 19 October: Pandit with the checks as tools. Sujit preferred the song; it took 11.8 "
                    "minutes of composing instead of 4.1; it fixed six faults itself, so code sent nothing back (the "
                    "workflow's drafts were sent back three times). Not yet the default, and never on stage."),
    "react": ("it picks its tools and when to stop", "chased the tool's report; lost by ear",
              "Both tool loops before that one lost: the legality tool only narrated code, and the listening tool pulled "
              "Pandit onto sway lengths and away from the cadence."),
    "evaluator": ("the judge picks how many rounds", "revised 14 of 14; a coin-flip gain",
                  "Left to loop, the judge always found something to change, and often made it worse by its own score, "
                  "so the round count moved into code and a revision must now beat the draft in both orders."),
    "debate": ("the debaters decide when to stop", "both that stopped themselves: parked",
               "In the head debate and the rehearsal the models effectively chose when to stop, by keeping or proposing "
               "nothing; both were parked. The notes debate that won has a fixed script and free content."),
    "collaboration": ("equals choose when to write", "compromise, even on a fixed rota",
                      "Our studio session was already scripted: code chose the leader, the order and the passes. A true "
                      "blackboard, where each decides when to write, would only loosen what already produced compromise."),
    "orchestrator": ("a lead model splits the work", "one idea, split into a collage",
                     "Our version was a planner, with code dispatching the workers; a run-time orchestrator would have "
                     "split the same single idea, just less predictably."),
    "hitl": ("it asks a human only when unsure", "never built; the ear settled all",
             "The agentic version would let a model decide when a human is needed. We never built it: every "
             "comparison that mattered was settled by Sujit listening, the one judge we trust."),
}

# What to do and not to do, per pattern — each line carries this project's own evidence (Act 3).
# (rule, evidence) pairs; the slide follows the pattern's verdict card.
DO_DONT: Final[dict[str, dict]] = {
    "debate": {
        # Rebuilt 2026-10-20 (Sujit: the old slide leaned on experiments the audience never sees): only what the
        # "Two agents or one?" chapter showed — the two composers, the composer debates, the sitar-guitar debate.
        "title": "Before you add a second agent",
        # Generic rules (Sujit, 2026-10-20: this slide speaks to any system, not ours); the band's evidence is in notes.
        "do": (("Give each agent a different part", "Owners of different work catch each other's mistakes."),
               ("Show each agent the whole work", "Each can judge its own part against everything else."),
               ("Keep a change only if it beats the current version", "Compare every change with what you already have.")),
        "dont": (("A prompt that already decides the answer", "If the prompt dictates the result, every agent writes the same thing."),
                 ("Opposing personas, same facts", "A new persona is the same model with the same information."),
                 ("A debate where feedback is enough", "If one agent fixes it once shown the problem, stop there.")),
        "notes": ("Generic rules on the slide; each comes from a slide the room has just seen, and the band's evidence is here. DO: give each agent a different part "
                  "(the sitar and guitar agents, who caught a rewrite made for a wrong reason and an outro one beat "
                  "too long); let both see the whole work (both were shown every section of the song); keep a change "
                  "only if it beats the current song (rewrites were accepted one at a time against the current take). "
                  "DON'T: a prompt that already decides the answer (the seed debates: every composer, Gemini or "
                  "OpenAI, chose the same piece, because the prompt handed down the motif, the rhythm grid and 43 lines of "
                  "direction; before adding a debater, step back and read the prompt — loosened, the melodies finally differed); a debate where feedback is enough (the head debate's control: one composer shown the same measurement "
                  "made the same fix, at about half the tokens); opposing personas, same facts (Pandit for tradition, Riffsmith for "
                  "metal: 28 of 31 runs one script, Pandit's melody never changed; a persona is a prompt, not a second view). NEXT: the balance."),
    },
    "evaluator": {
        "title": "The judge: what to do, what not to do",
        "do": (("Accept by default", "Before, it asked for a revision every time."),
               ("Keep the best take, not the last", "A revision must beat the draft in both orders."),
               ("Decide before reading the other critic", "It copied the raga critic's plans almost word for word."),
               ("One round, then stop", "More rounds didn't make its scores better.")),
        "dont": (("Trust its scores to steer", "Nearly every score was a 4 or a 5."),
                 ("Let it grade its own edit", "It shipped a take its own scores rated lower."),
                 ("Skip the human check", "Listening blind, I preferred the first draft.")),
        "notes": ("The Producer's lessons as rules. The fix was structural, not a better prompt: accept by default, one "
                  "round, a revision kept only if it wins an order-swapped comparison, and each critic judging before it "
                  "sees the other's view. Its instructions also name the problem a listener hears, never the notes."),
    },
}

# The alternative to a predefined workflow (Sujit, 2026-10-19: "explain the alternative options clearly so that
# people can learn the pattern"): an intro card only — slide 15 compares the two and says why we kept the workflow.
PATTERNS["agent"] = Pattern(
    key="agent", name="Autonomous agent",
    what="The model chooses the next step: which agent works next, what to do with the result, and when it is done.",
    use_when=("Nobody can list the steps ahead", "Each request needs a different path"),
    avoid_when=("You already know the steps", "It has to finish, on time, every time"),
    why_us="The obvious alternative to our fixed Flow: let a model run the band.",
    verdict="Not used", verdict_color=MUTED,
    headline="", evidence=(), takeaway="",
    cast=("composer", "producer"),
    intro_notes=("Anthropic calls this an agent: systems where \u201cLLMs dynamically direct their own processes and tool "
                 "usage\u201d. CrewAI ships it as the hierarchical process, a manager agent that delegates. Not the same as the first chapter's sectioning, where code fixes the split; here the model decides the ORDER of the "
                 "work and when to stop. The scene is an illustration, not a trace: we never let a manager run the whole band; "
                 "we tried the idea one level down, Pandit choosing its own checks."),
    verdict_notes="")

# What we used instead of open collaboration (Sujit, 2026-10-20): Lead and Riff write in turn on one shared
# board, code choosing who writes next, for a fixed number of passes. An intro card only; the ownership
# chapter's before/after slide is its verdict.
PATTERNS["blackboard"] = Pattern(
    key="blackboard", name="Blackboard",
    what="Agents write to one shared board; a controller decides who writes next, for a fixed number of turns.",
    use_when=("Many contributors, one shared state", "You want the order and the stop in code"),
    avoid_when="One idea needs one owner; turns still trade concessions.",
    why_us="Open collaboration had no stopping rule and no fixed order, so we gave the board a controller: code.",
    verdict="Used", verdict_color=SKY, headline="", evidence=(), takeaway="",
    cast=("lead", "riff"),
    intro_notes=("The blackboard is one of the oldest multi-agent designs, from the Hearsay-II speech recogniser in "
                 "the 1970s: specialists write to a shared board, and a controller decides who writes next. Ours, the "
                 "studio session: Lead and Riff on a shared section canvas, code choosing the leader by section kind "
                 "(the riff leads a groove, the sitar leads an alap), three passes, then stop. The scene is real: the "
                 "Riff's line is verbatim from the trace. It ran, and it composed the piece that opened tonight; the "
                 "next slide is what we found anyway."),
    verdict_notes="")

# How one owner writes a whole song (Sujit, 2026-10-20): Pandit's calls are a fixed chain, the seed, the gat,
# then one call per section with its own brief, every call carrying the seed and what came before. An intro card
# only, in the ownership chapter after the before/after slide: the sections are steps of one agent, not agents.
PATTERNS["chaining"] = Pattern(
    key="chaining", name="Prompt chaining", also="Parallelisation",
    what="One task as a fixed sequence of calls: each builds on the last, and code checks in between.",
    use_when=("The task splits into known steps", "Each step needs its own instructions"),
    avoid_when=("Steps need different knowledge or judgment", "One quick answer is enough"),
    why_us=("One owner still can't write a whole song in one answer. So Pandit writes it as a chain: the seed, "
            "the gat, then each section with its own brief, every call seeing the seed and everything before it."),
    verdict="Used", verdict_color=SKY, headline="", evidence=(), takeaway="",
    cast=("composer",),
    intro_notes=("Anthropic's first workflow in Building Effective Agents: \u201cPrompt chaining decomposes a task into "
                 "a sequence of steps, where each LLM call processes the output of the previous one,\u201d with "
                 "programmatic checks on the steps in between; it is for tasks that split cleanly into fixed subtasks, "
                 "trading latency for accuracy by making each call an easier task. Ours: Pandit's seed call writes the "
                 "plan, the main riff and the hook; the gat call writes the head, the manjha and the antara; then one "
                 "call for each remaining section, the alap, the taan, the outro, each with its own brief — "
                 "and those three run AT ONCE: Anthropic's second workflow, parallelisation (sectioning), independent "
                 "subtasks side by side. They see the seed and the gat, not each other: about a minute saved a song, for "
                 "an alap that cannot hear the taan. Code checks each answer before it is kept (the sky ring). The scene is an illustration of the order, every line an action, not a quote. Say the "
                 "point plainly: these are steps of one agent, not an Alap agent and a Taan agent. They differ in "
                 "instructions, not in what they know or how they judge, so naming them as agents would be splitting by "
                 "job title again. The seed travelling through every call is what keeps the riff, the hook and the form "
                 "one idea."),
    verdict_notes="")

INTRO_ORDER: Final = ("hitl", "selfcorrect", "orchestrator", "react", "workflow", "agent", "evaluator", "debate", "collaboration", "blackboard", "chaining")
VERDICT_ORDER: Final = ("orchestrator", "collaboration", "debate", "selfcorrect", "evaluator", "react", "workflow", "hitl")
