"""
THE RHYTHM SECTION, COMPOSED FROM THE LEAD LINE — what the call sees, what it may return, and
how its answer becomes guitar and bass.

Sujit, 2026-10-12: "ask the LLM to build the entire rhythm section based on the lead line." The
riff used to be written per section, before or beside the sitar, from a summary of the head; it
could not know where the sitar holds an andolan or lands a phrase, so it harmonised the melody
note by note and struck through every ornament (measured on `fusion_20261012_152048`). This call
comes AFTER the sitar is placed and sees it whole, so it can ring under a held note, answer a
rest, give the head one recurring chord pattern and move the manjha and antara — the way Sujit's
own Yaman recording is arranged. Guitar and bass are written together (one harmonic decision);
the drums stay code and lock to the guitar's attacks.

Three pure pieces live here; the LLM adapter is `crew/rhythm_section_call.py`:
  * `render_timed_lead` — the sitar line section by section, avartan by avartan, each note at
    its beat with its ornaments written in (`lead_notation.note_token`), a repeated avartan
    named once ("same as section 1, avartan 1");
  * `part_errors` — the HARD checks, as retry feedback: every rhythm section has a part, every
    cycle fills its avartan and is physical (`riff_texture.verify_riff`), every pitch is legal and
    entered from its side (`riff.riff_grammar_error`), the bass plays single notes;
  * `realise` — the answer as layers: each guitar cycle voiced (`riff_voicing.voice_riff`, bare
    strokes get their power chord) and placed on the tala (`riff.place_cycles`), the bass laid
    an octave under the guitar, and any section that wrote no bass given the bass code derives.

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from typing import Final, Sequence

from crew.contracts import (
    Arrangement,
    DebateEvent,
    Layer,
    Note,
    RhythmSection,
    RhythmSectionDraft,
    RiffNote,
    RiffPattern,
    SectionPart,
)
from crew.generators import BASS_FLOOR, VOICES, bass_layer, section_spans
from crew.head_anatomy import accent_beats
from crew.lead_notation import note_token
from crew.riff import place_cycles, riff_grammar_error
from crew.riff_notation import NotationError, parse_cycle
from crew.riff_texture import verify_riff
from crew.riff_voicing import voice_riff

_EPS: Final = 1e-6
_RHYTHM: Final = "rhythm"
_BASS: Final = "bass"
_LEAD: Final = "lead"


# --------------------------------------------------------------------------- #
# What the call sees                                                          #
# --------------------------------------------------------------------------- #

def _sitar_notes(lead_layers: Sequence[Layer]) -> list[Note]:
    """The sitar's melody notes in time order (the lead guitar, when on, only doubles it)."""
    leads = [ly for ly in lead_layers if ly.role == _LEAD and ly.notes]
    sitar = next((ly for ly in leads if ly.instrument == "sitar"), leads[0] if leads else None)
    return sorted((n for n in (sitar.notes if sitar else []) if not n.chikari),
                  key=lambda n: n.start)


def _avartan_line(notes: list[Note], start: float, cycle: float) -> str:
    """One avartan of the sitar: each note at its beat, and the silences between them."""
    tokens: list[str] = []
    edge = start
    for n in notes:
        if n.start > edge + _EPS:
            tokens.append(f"rest {edge - start:g}-{n.start - start:g}")
        tokens.append(f"{n.start - start:g} {note_token(n)}")
        edge = max(edge, n.start + n.dur)
    if edge < start + cycle - _EPS:
        tokens.append(f"rest {edge - start:g}-{cycle:g}")
    return " · ".join(tokens) if notes else "(the sitar is silent)"


def render_timed_lead(lead_layers: Sequence[Layer], arr: Arrangement) -> str:
    """The sitar line as the rhythm section reads it — see the module docstring. Pure."""
    sitar = _sitar_notes(lead_layers)
    cycle = arr.beats_per_bar
    seen: dict[str, str] = {}
    lines: list[str] = []
    for span in section_spans(arr):
        sec = span.section
        guitar = "the guitar plays" if _RHYTHM in sec.layers else "no guitar"
        lines.append(f"section {span.index} ({sec.form_role or sec.kind.value}, "
                     f"{sec.bars} avartan{'s' if sec.bars != 1 else ''}, {guitar}):")
        for bar in range(sec.bars):
            a = span.start + bar * cycle
            line = _avartan_line([n for n in sitar if a - _EPS <= n.start < a + cycle - _EPS],
                                 a, cycle)
            where = f"section {span.index}, avartan {bar + 1}"
            lines.append(f"  avartan {bar + 1}: "
                         + (f"same as {seen[line]}" if line in seen else line))
            seen.setdefault(line, where)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# What it may return                                                          #
# --------------------------------------------------------------------------- #

def _playing(arr: Arrangement) -> list[int]:
    """The sections the guitar plays in that this call writes — a TAKEOVER plays the arranged
    head instead (`crew/takeover.py`), so it needs no part."""
    return [s.index for s in section_spans(arr)
            if _RHYTHM in s.section.layers and s.section.form_role != "takeover"]


def _resolved(part: SectionPart, parts: dict[int, SectionPart]) -> SectionPart | None:
    """The part whose cycles this section plays: its OWN when it wrote any, else the one `same_as`
    names (when that one has its own). Own cycles win: Gemini's structured output fills every
    field, so the 2026-10-12 live answer wrote real cycles AND `"same_as": 0` (the intro) on the
    same part, and following `same_as` first rejected a playable arrangement."""
    if part.guitar:
        return part
    target = parts.get(part.same_as) if part.same_as is not None else None
    return target if target is not None and target.guitar else None


def _cycle_errors(cycles: list[list[RiffNote]], where: str, arr: Arrangement, *,
                  bass: bool) -> list[str]:
    errors: list[str] = []
    for k, notes in enumerate(cycles):
        label = f"{where} {'bass' if bass else 'guitar'} cycle {k + 1}"
        if not notes:
            errors.append(f"{label} is empty")
            continue
        pattern = RiffPattern(notes=notes)
        errors += [f"{label}: {e}" for e in verify_riff(pattern, cycle_beats=arr.beats_per_bar)]
        grammar = riff_grammar_error(pattern, arr.raga)
        if grammar:
            errors.append(f"{label}: {grammar}")
        if bass and any(n.chord for n in notes if not n.rest):
            errors.append(f"{label}: the bass plays single notes — no chord")
    return errors


def from_draft(draft: RhythmSectionDraft) -> tuple[RhythmSection | None, list[str]]:
    """The model's compact answer read back into the `RhythmSection` the pipeline plays: every
    cycle string parsed (`crew/riff_notation.py`). Returns the section, or None with one fault per
    unreadable cycle (fed back as the retry's repair list). Pure."""
    faults: list[str] = []
    parts: list[SectionPart] = []
    for draft_part in draft.parts:
        voices = {}
        for voice in ("guitar", "bass"):
            cycles = []
            for i, text in enumerate(getattr(draft_part, voice), start=1):
                try:
                    cycles.append(parse_cycle(text))
                except NotationError as exc:
                    faults.append(f"section {draft_part.section} {voice} cycle {i}: {exc}")
            voices[voice] = cycles
        parts.append(SectionPart(section=draft_part.section, role=draft_part.role,
                                 same_as=draft_part.same_as, **voices))
    if faults:
        return None, faults
    return RhythmSection(reasoning=draft.reasoning, parts=parts), []


def part_errors(rs: RhythmSection, arr: Arrangement) -> list[str]:
    """The HARD faults of a rhythm section, as retry feedback (empty == it can be played). Pure."""
    count = len(arr.sections)
    parts = {p.section: p for p in rs.parts}
    errors = [f"there is no section {p.section} (the chart has sections 0-{count - 1})"
              for p in rs.parts if not 0 <= p.section < count]
    for index in _playing(arr):
        part = parts.get(index)
        if part is None:
            errors.append(f"section {index} has the guitar playing but no part")
        elif _resolved(part, parts) is None:
            errors.append(f"section {index}: write its guitar cycles, or `same_as` a section "
                          f"that has its own")
    for part in rs.parts:
        where = f"section {part.section}"
        errors += _cycle_errors(part.guitar, where, arr, bass=False)
        errors += _cycle_errors(part.bass, where, arr, bass=True)
    return errors


# --------------------------------------------------------------------------- #
# How the answer becomes layers                                               #
# --------------------------------------------------------------------------- #

def _per_bar(cycles: list[list[RiffNote]], bars: int) -> list[list[RiffNote]]:
    """Cycle i plays bar i; a section longer than its cycles repeats the last."""
    return [cycles[min(bar, len(cycles) - 1)] for bar in range(bars)]


def _bass_notes(cycles: list[list[RiffNote]], start: float, cycle: float,
                register: int) -> list[Note]:
    notes: list[Note] = []
    for bar, cyc in enumerate(cycles):
        t = start + bar * cycle
        for n in cyc:
            if not n.rest:
                notes.append(Note(swara=n.swara, oct=max(register + n.oct, BASS_FLOOR),
                                  start=round(t, 4), dur=n.dur, vel=n.vel))
            t += n.dur
    return notes


def _layer(role: str, voice_key: str, notes: list[Note]) -> Layer | None:
    if not notes:
        return None
    voice = VOICES[voice_key]
    return Layer(role=role, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


def _section_guitar(part: SectionPart, start: float, bars: int, arr: Arrangement) -> list[Note]:
    """A section's guitar: each bar's cycle voiced (bare strokes take their power chord) and
    placed on the tala from `start`."""
    accents = accent_beats(arr)
    voiced = [list(voice_riff(RiffPattern(notes=c), arr.raga, accents).notes)
              for c in _per_bar(part.guitar, bars)]
    return place_cycles(voiced, start=start, cycle_beats=arr.beats_per_bar,
                        register=arr.registers[_RHYTHM], accent_beats=set(accents), raga=arr.raga)


def _derived_bass(arr: Arrangement, guitar: Layer | None,
                  spans: list[tuple[float, float]]) -> list[Note]:
    """The code-derived bass, kept only inside the sections that wrote none of their own."""
    derived = bass_layer(arr, guitar) if spans else None
    return [n for n in (derived.notes if derived else [])
            if any(a - _EPS <= n.start < b - _EPS for a, b in spans)]


def realise(rs: RhythmSection, arr: Arrangement) -> tuple[Layer | None, Layer | None]:
    """(guitar, bass) layers from a rhythm section that passed `part_errors`. Pure."""
    parts = {p.section: p for p in rs.parts}
    bass_register = max(arr.registers[_RHYTHM] - 1, BASS_FLOOR)
    guitar: list[Note] = []
    bass: list[Note] = []
    unwritten: list[tuple[float, float]] = []          # sections whose bass code derives
    for span in (s for s in section_spans(arr) if s.index in parts):
        part = _resolved(parts[span.index], parts)
        if part is None or _RHYTHM not in span.section.layers:
            continue
        guitar += _section_guitar(part, span.start, span.section.bars, arr)
        if part.bass:
            bass += _bass_notes(_per_bar(part.bass, span.section.bars), span.start,
                                arr.beats_per_bar, bass_register)
        else:
            unwritten.append((span.start, span.end))
    guitar_layer = _layer(_RHYTHM, _RHYTHM, guitar)
    bass += _derived_bass(arr, guitar_layer, unwritten)
    return guitar_layer, _layer(_BASS, _BASS, sorted(bass, key=lambda n: n.start))


# --------------------------------------------------------------------------- #
# On the chart: the composed part rides the event stream, then the Arrangement #
# --------------------------------------------------------------------------- #

RHYTHM_SECTION_KEY: Final = "rhythm_section"


def rhythm_section_from_events(events: Sequence[DebateEvent]) -> RhythmSection | None:
    """The last composed rhythm section the events carry, or None. Pure."""
    for event in reversed(list(events)):
        data = event.data or {}
        if RHYTHM_SECTION_KEY in data:
            return RhythmSection.model_validate(data[RHYTHM_SECTION_KEY])
    return None


def with_rhythm_section(arr: Arrangement, events: Sequence[DebateEvent]) -> Arrangement:
    """The chart carrying the rhythm section the events composed (replacing any it had — a revise
    rewrites it), or the chart unchanged when they composed none. Pure."""
    rs = rhythm_section_from_events(events)
    return arr if rs is None else arr.model_copy(update={"rhythm_section": rs})


def splice_parts(old: RhythmSection, new: RhythmSection, sections: Sequence[int]) -> RhythmSection:
    """`old` with the parts of `sections` taken from `new` (a revise re-asks for those only; a
    section `new` left out keeps its old part). Pure."""
    fresh = {p.section: p for p in new.parts if p.section in sections}
    parts = [fresh.pop(p.section, p) for p in old.parts] + list(fresh.values())
    return old.model_copy(update={"parts": sorted(parts, key=lambda p: p.section)})
