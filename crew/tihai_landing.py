"""
TIHAI LANDING — a tihai's last note strikes the sam, and code puts it there.

A tihai is one phrase stated three times whose FINAL note falls on the sam that follows. The
LLM (a `tihai` section) or `make_tihai` (a long taan's cadence) writes the three statements;
where the landing falls is arithmetic, so code owns it. Both writers used to fit the three
statements INSIDE the section's window, so the landing note sounded before the sam. Measured
on `fusion_20261012_112714` (Darbari): the tihai section's `g m R S` x3 put its Sa on matra 7,
1.5 beats early, and the outro's opening Ma took the sam the cadence was built for.

The rule, on the placed line of one lead layer:
  * find the tripled statement closing a tihai/taan_long section (three identical pitch runs);
  * the first statement stays where it was written and the two gaps widen EQUALLY until the
    third statement's final note STRIKES the next sam (shifting the whole tihai instead left
    dead air between a taan and its cadence; widening only ever grows a gap, so the
    statements can never overlap);
  * the landing owns that beat for up to `LANDING_MAX_BEATS`, and the next section's lead
    yields (its notes starting inside the landing start after it) — EXCEPT a returning
    mukhada, whose head is the hook: there the head's sam note IS the landing and the
    tihai's own final note is dropped;
  * a tihai closing the piece lands past the last section (`hard_stop` clips it and strikes
    its own stroke on that sam; `ring_out` lets it ring).
A line with no tripled statement is left exactly as written. Pure.
"""

from __future__ import annotations

from typing import Final

from crew.contracts import Arrangement, Note
from crew.generators import SectionSpan, section_spans

LANDING_MAX_BEATS: Final = 1.0     # the landing is a strike, not a new phrase
_MIN_STATEMENT_NOTES: Final = 2    # one note thrice is a pulse, not a tihai
_MIN_YIELD_BEATS: Final = 0.1      # a next-section note pushed shorter than this is dropped
_EPS: Final = 1e-6


def land_tihais(notes: list[Note], arr: Arrangement) -> list[Note]:
    """Re-time every tihai in one lead layer's placed line so it lands on its sam."""
    spans = section_spans(arr)
    out = sorted(notes, key=lambda n: n.start)
    for k, span in enumerate(spans):
        following_role = spans[k + 1].section.form_role if k + 1 < len(spans) else None
        if span.section.form_role == "tihai" or (span.section.form_role == "taan_long"
                                                  and span.section.tihai
                                                  and following_role != "mukhada"):
            following = spans[k + 1] if k + 1 < len(spans) else None
            out = _land_one(out, span, following)
    return out


def _land_one(notes: list[Note], span: SectionSpan, following: SectionSpan | None) -> list[Note]:
    inside = [n for n in notes if span.start - _EPS <= n.start < span.end - _EPS]
    size = _statement_size(inside)
    if size is None:
        return notes
    statements = [inside[len(inside) - 3 * size + j * size:][:size] for j in range(3)]
    placed = _placed_statements(statements, span.end)
    if placed is None:
        return notes
    prefix = inside[:len(inside) - 3 * size]
    head_wins = following is not None and following.section.form_role == "mukhada" and any(
        abs(n.start - span.end) < _EPS for n in notes)
    landing = placed[-1]
    if head_wins:
        placed = placed[:-1]
    before = [n for n in notes if n.start < span.start - _EPS]
    after = [n for n in notes if n.start >= span.end - _EPS]
    if not head_wins:
        after = _yield_to(landing, after)
    return before + prefix + placed + after


def _statement_size(inside: list[Note]) -> int | None:
    """The longest statement whose three copies close the section's line, or None."""
    keys = [(n.swara, n.oct) for n in inside]
    for size in range(len(keys) // 3, _MIN_STATEMENT_NOTES - 1, -1):
        tail = keys[len(keys) - 3 * size:]
        if tail[:size] == tail[size:2 * size] == tail[2 * size:]:
            return size
    return None


def _placed_statements(statements: list[list[Note]], sam: float) -> list[Note] | None:
    """The three statements from where the first was written, on the even period that puts
    the third's final note on `sam`, with the first statement's internal rhythm for all
    three. None when the line already lands at or past the sam."""
    first = statements[0]
    t0 = first[0].start
    offsets = [n.start - t0 for n in first]
    period = (sam - t0 - offsets[-1]) / 2
    if period < (statements[2][0].start - t0) / 2 - _EPS:
        return None
    placed = [n.model_copy(update={"start": round(t0 + j * period + offsets[i], 4)})
              for j, statement in enumerate(statements) for i, n in enumerate(statement)]
    timed = [n.model_copy(update={"dur": round(min(first[i % len(first)].dur,
                                                   placed[i + 1].start - n.start), 4)})
             for i, n in enumerate(placed[:-1])]
    landing = placed[-1].model_copy(update={"dur": min(placed[-1].dur, LANDING_MAX_BEATS)})
    return timed + [landing]


def _yield_to(landing: Note, after: list[Note]) -> list[Note]:
    """The next section's notes that would start inside the landing start after it."""
    clear = landing.start + landing.dur
    out: list[Note] = []
    for n in after:
        if n.start >= clear - _EPS:
            out.append(n)
            continue
        left = n.start + n.dur - clear
        if left >= _MIN_YIELD_BEATS:
            out.append(n.model_copy(update={"start": round(clear, 4), "dur": round(left, 4)}))
    return out
