"""
HEARING — what the sitar will actually do with a draft, told back to the Composer mid-composition.

The Composer writes swaras and durations; code decides the rest after it has answered. Whether a
komal Ga sways depends on how long it is held and how the line leaves it; whether it takes a kan,
a measured loop to Ma or a slow release depends on where the line arrives from; a long hold turns
into jhala at the pluck limit. None of that is visible from the JSON the model writes. Across the
2026-10-18 Darbari songs the system held 0 of 47 ga/dha long enough to sway, and never knew.

So the Composer can LISTEN: `hear(notes, span, arr)` runs one statement of the draft through the
real realisation path (`lead.heard_statement` — placement, pluck limit, voicing, the code-set
gestures), asks the renderer's own gate whether each andolit note sways (`render.sways`), renders
the statement to MIDI and runs the ornament audit on it, and returns a short report in words.

The report says what the draft WILL SOUND LIKE, never what it should be: no target, no score, no
reference to measure against. A judge optimises whatever number it is shown (the seed debate's
lesson); a composer told "2 of 5 sway" may hold every Ga to raise it. What to do about it is the
Composer's call. Pure, apart from a temporary MIDI file the audit reads.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Final

from crew.contracts import Arrangement, Composition, LeadNote, Note, Section, SectionKind
from crew.expression import GAMAK_GESTURE
from crew.generators import SectionSpan
from crew.lead_notation import swara_with_oct
from gestures import RELEASE, gesture_named
from ornament_audit import audit_midi
from raga import ANDOLAN_TOWARD, RAGAS, SWARAS
from render import ANDOLAN_MIN_MS, KAN_STEP_MS, MEEND_RANGE, build_midi, sways

# Sections where a held note decides how the raga sounds. The taan is a continuous chaugun run by
# rule (no holds to hear), a tihai is code-built, and a guitar-voiced section has no sitar line.
_UNHEARD_ROLES: Final = frozenset({"taan_long", "tihai", "takeover"})
_UNHEARD_KINDS: Final = frozenset({SectionKind.TAAN, SectionKind.SOLO, SectionKind.BREAKDOWN})
HEAR_MAX_USES: Final = 2          # listens per lead call (the tool's cap, enforced by CrewAI)
_SILENCE_BEATS: Final = 0.5       # a gap this long is reported as a silence
_STRUCK_GROUP: Final = 3          # this many identical plain strokes in a row read as one line

HEARING_BRIEF: Final = """\
You can LISTEN before you answer: call the `hear_phrase` tool with your draft's notes and it tells
you what the sitar will actually play — which notes sway, which take a kan or a measured gesture,
which long holds turn into jhala, where the silences fall, and whether any bend sounds out of tune.
Code decides those ornaments after you answer, from how long each note is held and how the line
arrives at it and leaves it, so the draft alone does not show them. Listen once, change what you
want to change, and answer; you may listen at most twice."""


def wants_hearing(section: Section) -> bool:
    """Whether a lead call for this section is given the listening tool."""
    return section.form_role not in _UNHEARD_ROLES and section.kind not in _UNHEARD_KINDS


def hearing_brief(section: Section, enabled: bool) -> str:
    """The prompt's listening paragraph — empty when the call has no tool."""
    return HEARING_BRIEF if enabled and wants_hearing(section) else ""


# --------------------------------------------------------------------------- #
# One note, in words.                                                         #
# --------------------------------------------------------------------------- #

def _seconds(beats: float, bpm: int) -> float:
    return beats * 60.0 / bpm


def _sway_toward(raga: str, swara: str) -> str:
    allowed = RAGAS[raga]["allowed"]
    i = allowed.index(swara)
    above = ANDOLAN_TOWARD.get(raga, {}).get(swara, "below") == "above"
    return allowed[(i + 1) % len(allowed)] if above else allowed[i - 1]


def _resting(n: Note) -> str:
    return n.meend_swara if n.meend_swara is not None else n.swara


def _on_swaying_swara(n: Note, raga: str) -> bool:
    return (_resting(n) in RAGAS[raga].get("andolan", []) and n.gesture is None
            and not n.chikari)


def does_sway(n: Note, raga: str, bpm: int) -> bool:
    """Whether the renderer draws a sway on this note — flagged by code, and long enough in real
    time once a kan has taken its share."""
    lead_ms = KAN_STEP_MS * len(n.grace or [])
    return _on_swaying_swara(n, raga) and bool(n.andolan) and sways(n.dur, bpm, lead_ms=lead_ms)


def _andolan_words(n: Note, raga: str, bpm: int) -> str | None:
    """What happens to a note resting on one of the raga's swaying swaras, or None."""
    if not _on_swaying_swara(n, raga):
        return None
    if does_sway(n, raga, bpm):
        return f"sways toward {_sway_toward(raga, _resting(n))}"
    if n.dur < 1.0:
        return f"plain: held {n.dur:g} beat, too short to sway (a sway needs at least 1 beat)"
    if n.andolan:
        return (f"plain: {_seconds(n.dur, bpm):.2f} s is too short to sway at this tempo "
                f"(a sway needs at least {ANDOLAN_MIN_MS / 1000:.1f} s)")
    return "plain: the line moves straight on from it, so it does not sway"


def _gesture_words(n: Note) -> str | None:
    gesture = gesture_named(n.gesture) if n.gesture else None
    if gesture is None:
        return None
    if gesture.motion == RELEASE:
        return f"plucked pulled up to {gesture.toward}, released slowly onto {n.swara}"
    way = "dips to" if SWARAS[gesture.toward] < SWARAS[n.swara] else "loops up to"
    return f"{way} {gesture.toward} and back, then holds"


def note_words(n: Note, raga: str, bpm: int) -> str:
    """What the sitar does with one placed, expressed note."""
    if n.chikari:
        return "chikari stroke (the drone strings)"
    parts = [f"kan from {''.join(n.grace)}"] if n.grace else []
    parts += [w for w in (_gesture_words(n),) if w]
    if n.meend_swara is not None:
        parts.append(f"glides into {n.meend_swara}")
    parts += [w for w in (_andolan_words(n, raga, bpm),) if w]
    return ", then ".join(parts) or "plain"


# --------------------------------------------------------------------------- #
# The line, in words.                                                         #
# --------------------------------------------------------------------------- #

def _token(n: Note, register: int) -> str:
    return swara_with_oct(n.swara, n.oct - register)


def _is_gamak(n: Note) -> bool:
    return n.gesture == GAMAK_GESTURE


def _same_stroke(a: Note, b: Note) -> bool:
    """Two notes that read as one repeated stroke: a gamak cell's strokes, or identical plain
    short strokes (a jhala)."""
    if (a.swara, a.oct) != (b.swara, b.oct) or abs(a.start + a.dur - b.start) > 1e-3:
        return False
    if _is_gamak(a) or _is_gamak(b):
        return _is_gamak(a) and _is_gamak(b) and a.gamak_with == b.gamak_with
    plain = not (a.grace or a.gesture or a.meend_swara or a.andolan or a.chikari)
    return plain and a.dur == b.dur and a.dur < 1.0 and not (b.grace or b.gesture or b.andolan)


def _groups(line: list[Note]) -> list[list[Note]]:
    groups: list[list[Note]] = []
    for n in line:
        if groups and _same_stroke(groups[-1][-1], n):
            groups[-1].append(n)
        else:
            groups.append([n])
    return [g for big in groups for g in ([big] if _groupable(big) else [[n] for n in big])]


def _groupable(group: list[Note]) -> bool:
    return _is_gamak(group[0]) or len(group) >= _STRUCK_GROUP


def _group_line(group: list[Note], at: float, register: int, raga: str, bpm: int) -> str:
    first = group[0]
    total = round(sum(n.dur for n in group), 4)
    head = f"beat {first.start - at:6.2f}  {_token(first, register):<7} {total:5g}"
    if len(group) == 1:
        return f"{head}  {note_words(first, raga, bpm)}"
    if _is_gamak(first):
        return f"{head}  gamak with {first.gamak_with}: {len(group)} strokes"
    return f"{head}  struck {len(group)} times (jhala)"


def _silences(line: list[Note], at: float) -> list[tuple[float, float]]:
    """(beat, length) of every gap of at least `_SILENCE_BEATS` between notes."""
    gaps = []
    for a, b in zip(line, line[1:]):
        gap = round(b.start - (a.start + a.dur), 4)
        if gap >= _SILENCE_BEATS:
            gaps.append((a.start + a.dur - at, gap))
    return gaps


def _note_lines(line: list[Note], at: float, register: int, raga: str, bpm: int) -> list[str]:
    rows = [(g[0].start, _group_line(g, at, register, raga, bpm)) for g in _groups(line)]
    rows += [(at + beat, f"beat {beat:6.2f}  {'-':<7} {gap:5g}  silence")
             for beat, gap in _silences(line, at)]
    return [text for _, text in sorted(rows, key=lambda r: r[0])]


def _sway_summary(line: list[Note], raga: str, bpm: int) -> str | None:
    swaying = RAGAS[raga].get("andolan", [])
    if not swaying:
        return None
    on = [n for n in line if _resting(n) in swaying and not _is_gamak(n) and not n.chikari]
    gestured = sum(1 for n in on if n.gesture is not None)
    swung = sum(1 for n in on if does_sway(n, raga, bpm))
    return (f"{' and '.join(swaying)} (the swaras {RAGAS[raga]['display']} sways): {len(on)} "
            f"note(s) — {swung} sway, {gestured} take a measured gesture, "
            f"{len(on) - swung - gestured} plain")


def _overrun_summary(notes: list[LeadNote], line: list[Note], at: float) -> str | None:
    """The draft's length against where the sitar's line ends, when the window cut it."""
    sounding = list(notes)
    while sounding and sounding[-1].rest:
        sounding.pop()
    written = sum(n.dur for n in sounding)
    heard = max(n.start + n.dur for n in line) - at
    if written <= heard + 0.01:
        return None
    return (f"your draft runs {written:g} beats but this statement's window ends at beat "
            f"{heard:g}, so the last {written - heard:g} beats are cut")


def _silence_summary(line: list[Note], at: float) -> str:
    gaps = _silences(line, at)
    if not gaps:
        return "no silence inside the phrase"
    return f"{len(gaps)} silence(s), the longest {max(g for _, g in gaps):g} beats"


# --------------------------------------------------------------------------- #
# The ornament audit, on the statement rendered to MIDI.                      #
# --------------------------------------------------------------------------- #

def _composition(line: list[Note], arr: Arrangement) -> Composition:
    from crew.lead import sitar_layer
    return Composition(raga=arr.raga, sa=arr.sa, bpm=arr.bpm,
                       tala={"name": arr.tala, "beats_per_bar": arr.beats_per_bar},
                       layers=[sitar_layer(line)])


def audit_words(line: list[Note], arr: Arrangement, at: float) -> str:
    """The ornament audit of this statement on its own sitar channel, in words."""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "heard.mid")
        build_midi(_composition(line, arr).model_dump(), path)
        findings = audit_midi(path, bend_range=MEEND_RANGE, raga=arr.raga, sa=arr.sa)
    if not findings:
        return "ornament check: every bend comes home in tune"
    return "ornament check: " + "; ".join(
        f"beat {f.time_s * arr.bpm / 60.0 - at:.2f} {f.kind.replace('_', ' ')} ({f.detail})"
        for f in findings[:4])


def hear(notes: list[LeadNote], span: SectionSpan, arr: Arrangement) -> str:
    """The listening report for one statement of a draft in this section. Pure apart from the
    temporary MIDI file the audit reads."""
    from crew.lead import heard_statement
    if not notes:
        return "The draft has no notes."
    line = heard_statement(notes, span, arr)
    if not line:
        return "This section is voiced on the lead guitar; the sitar does not play it."
    register, at = arr.registers["lead"], span.start
    summary = [s for s in (_overrun_summary(notes, line, at), _sway_summary(line, arr.raga, arr.bpm),
                           _silence_summary(line, at),
                           audit_words(line, arr, at)) if s]
    return "\n".join([f"WHAT THE SITAR WILL PLAY ({arr.bpm} bpm; beat, swara, beats, what happens):",
                      *_note_lines(line, at, register, arr.raga, arr.bpm), "", *summary])
