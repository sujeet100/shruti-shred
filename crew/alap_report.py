"""
THE ALAP, MEASURED — does the intro breathe like an alap, and does it walk the band in?

Sujit, 2026-10-19: "ours is more of an intro than an alap". Measured on
`fusion_20261019_184632_pipeline_darbari`, its alap played 30 notes in ~26 s, mostly half-second
notes, with only 39% of its sound on notes held a second or longer — a melody in tempo. The
research (ALAP_RESEARCH.md; Clarke, *Rags Around the Clock* ch. 3) describes an alap as unmetred
and mostly held, revealing the raga one frontier at a time and peaking late (Clarke's 14 short
alaps: the top arrives at 77% on average). Those are facts the score shows, so code measures them
and the Producer judges with them — reported, never a rejection (the same contract as
`crew/taan_report.py`; the hard limits live in `gat_verifier.check_intro`):

  * HELD — the share of the alap's sound on notes held a second or longer;
  * PHRASES — how many, how long, and how many stand on a held note;
  * FRONTIER — how many new swaras each phrase opens beyond the ground so far;
  * REACH — where the widest reach arrives (down for a raga that lives low, up otherwise);
  * JOD — how long the pulsed lead-in is, and how busy;
  * HEAD — whether the alap rests on the head's first swara near the close, and whether it quotes
    the head's opening figure.

Pure: the placed composition in, text out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from crew.contracts import Arrangement, Composition, Note
from crew.gat_verifier import lives_low
from crew.generators import section_spans
from crew.lead import intro_jod_window
from raga import SWARAS

_LEAD: Final = "lead"
_EPS: Final = 1e-6
_HELD_S: Final = 1.0          # a note this many seconds long is HELD
_BREATH_BEATS: Final = 1.0    # a silence this long ends a phrase
_HEAD_FIGURE: Final = 4       # the head's opening this many swaras, heard in the alap, is a quote


@dataclass(frozen=True)
class AlapFacts:
    seconds: float                  # the alap part, first note to the jod (or to its end)
    held_share: float               # share of its sound on notes held >= _HELD_S
    phrases: int
    mean_phrase_s: float
    held_phrases: int               # phrases with at least one held note
    new_per_phrase: tuple[int, ...]  # new swaras each phrase opens beyond the ground so far
    reach: str                      # the widest-reach note, e.g. "R." (mandra)
    reach_at: float                 # share of the alap elapsed when it sounds
    jod_s: float | None             # the jod's length, None when the intro has none
    jod_notes_per_beat: float | None
    rests_on_head: bool | None      # does a late phrase rest on the head's first swara?
    quotes_head: bool | None        # is the head's opening figure heard in the alap?


def _sitar(comp: Composition) -> list[Note]:
    lead = next((ly for ly in comp.layers if ly.role == _LEAD and ly.instrument == "sitar"), None)
    return sorted((n for n in (lead.notes if lead else []) if not n.chikari), key=lambda n: n.start)


def _pitch(n: Note) -> int:
    return SWARAS[n.swara] + 12 * n.oct


def _mark(n: Note) -> str:
    return n.swara + ("'" if n.oct > 0 else ("." if n.oct < 0 else ""))


def _phrases(notes: list[Note]) -> list[list[Note]]:
    out: list[list[Note]] = []
    for n in notes:
        if out and n.start - (out[-1][-1].start + out[-1][-1].dur) < _BREATH_BEATS - _EPS:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def _new_per_phrase(phrases: list[list[Note]]) -> tuple[int, ...]:
    seen: set[int] = set()
    counts: list[int] = []
    for ph in phrases:
        heights = {_pitch(n) for n in ph}
        counts.append(len(heights) if not seen else
                      len({h for h in heights if h < min(seen) or h > max(seen)}))
        seen |= heights
    return tuple(counts)


def _head_relation(alap: list[list[Note]], head: list[Note]) -> tuple[bool | None, bool | None]:
    if not head:
        return None, None
    first = head[0].swara
    rests = any(ph[-1].swara == first for ph in alap[-2:])
    figure = [n.swara for n in head[:_HEAD_FIGURE]]
    line = [n.swara for ph in alap for n in ph]
    quotes = len(figure) == _HEAD_FIGURE and any(
        line[i:i + _HEAD_FIGURE] == figure for i in range(len(line) - _HEAD_FIGURE + 1))
    return rests, quotes


def alap_facts(comp: Composition, arr: Arrangement) -> AlapFacts | None:
    """The facts of the piece's intro alap, or None when it has none. Pure."""
    spans = section_spans(arr)
    k = next((i for i, sp in enumerate(spans) if sp.section.form_role == "intro"), None)
    if k is None:
        return None
    span, sitar = spans[k], _sitar(comp)
    start, jod = intro_jod_window(arr, span)
    split = span.end if jod is None else jod
    alap = [n for n in sitar if start - _EPS <= n.start < split - _EPS]
    if not alap:
        return None
    beat_s = 60.0 / arr.bpm
    phrases = _phrases(alap)
    sound = sum(n.dur for n in alap)
    held = sum(n.dur for n in alap if n.dur * beat_s >= _HELD_S - _EPS)
    widest = min(alap, key=_pitch) if lives_low(arr.raga) else max(alap, key=_pitch)
    end = alap[-1].start + alap[-1].dur
    jod_notes = [n for n in sitar if jod is not None and jod - _EPS <= n.start < span.end - _EPS]
    following = next((sp for sp in spans[k + 1:] if sp.section.form_role == "mukhada"), None)
    head = [n for n in sitar if following is not None
            and following.start - _EPS <= n.start < following.start + arr.beats_per_bar - _EPS]
    late = phrases + ([jod_notes] if jod_notes else [])
    rests, quotes = _head_relation(late, head)
    return AlapFacts(
        seconds=(end - alap[0].start) * beat_s, held_share=held / sound if sound else 0.0,
        phrases=len(phrases), mean_phrase_s=sum((ph[-1].start + ph[-1].dur - ph[0].start) * beat_s
                                                for ph in phrases) / len(phrases),
        held_phrases=sum(any(n.dur * beat_s >= _HELD_S - _EPS for n in ph) for ph in phrases),
        new_per_phrase=_new_per_phrase(phrases), reach=_mark(widest),
        reach_at=(widest.start - alap[0].start) / max(end - alap[0].start, _EPS),
        jod_s=None if jod is None else (span.end - jod) * beat_s,
        jod_notes_per_beat=(len(jod_notes) / (span.end - jod)) if jod is not None and span.end > jod else None,
        rests_on_head=rests, quotes_head=quotes)


def render_alap(comp: Composition, arr: Arrangement) -> str:
    """The Producer's prompt block, or "" when the piece has no intro alap. Pure."""
    f = alap_facts(comp, arr)
    if f is None:
        return ""
    jod = ("no jod" if f.jod_s is None else
           f"then a {f.jod_s:.1f} s jod at {f.jod_notes_per_beat:.1f} notes/beat")
    head = ("" if f.rests_on_head is None else
            f"; its last phrases {'rest' if f.rests_on_head else 'do NOT rest'} on the head's first "
            f"swara, and it {'QUOTES' if f.quotes_head else 'does not quote'} the head's opening figure")
    return "\n".join([
        "  - THE ALAP (the intro) — does it breathe like an alap, and walk the band in?",
        f"    {f.seconds:.0f} s of alap; {f.held_share:.0%} of its sound on notes held 1 s or longer; "
        f"{f.phrases} phrases, {f.mean_phrase_s:.1f} s each on average, {f.held_phrases} standing on "
        f"a held note; new swaras per phrase: {' '.join(map(str, f.new_per_phrase))}; widest reach "
        f"{f.reach} at {f.reach_at:.0%}; {jod}{head}",
        "    how to read it: an alap is unmetred and mostly HELD (well over half its sound), each "
        "phrase standing on one held swara for seconds; it opens the raga one or two new swaras a "
        "phrase, reaches widest about three quarters through, then a short pulsed jod leads the "
        "band in, preparing the head without quoting it. Short busy phrases, a range opened all at "
        "once, or a quoted head read as an INTRO in tempo, not an alap."])
