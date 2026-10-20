"""
THE NOTES DEBATE — two players argue about the MUSIC, not the mix (Sujit, 2026-10-19).

The rehearsal could only turn knobs (sit out, softer, sparser…), so every argument became "turn the
guitar down" and the song went hollow. Here each player argues about notes, phrases and the riff:

  * the SITARIST owns the sitar line and proposes a rewrite of ONE part of it — the head (which
    returns at every mukhada), the manjha, the antara or the outro — as the actual new notes;
  * the GUITARIST owns the composed guitar part and proposes a rewrite of ONE section's riff, as
    the actual new cycles in the compact riff notation (`crew/riff_notation.py`);
  * each CRITIQUES the other's rewrite against the notes, and each then REVISES, DEFENDS or
    WITHDRAWS its own in the light of that critique — a real exchange, about the music;
  * code CHECKS every rewrite before anyone builds it (raga grammar, the same length as the part it
    replaces, a head keeps its first note and passes the head's hard lines, the riff stays
    playable and in the raga); a failing rewrite goes back once with the exact fault;
  * the song is REBUILT exactly as the pipeline builds it (the phrases → the sitar line; the
    guitar part → guitar, derived bass and the drums that lock to it) and rendered: the original,
    each first proposal, each final, and both finals together. The judge is Sujit's ear — the
    audio judges could not hear (TALK.md "The rehearsal's ears were not listening").

In the PIPELINE (`debate_stage`, wired into the Flow's `finish` behind `RMA_NOTES_DEBATE`): the
debate runs on the accepted song only when a reviewer named a concern it can fix
(`crew/debate_trigger.py`, 2026-10-20), that concern is the players' brief, and each final rewrite is kept only if it beats that song in the
blind both-orders comparison (`crew/compare.py`) — the Producer's champion rule. Its record against
Sujit's ear before it went in: 2 better, 1 sidegrade, 1 neutral, 0 worse (TALK.md 2026-10-19).

Pure: the model calls arrive as injected functions, the renderer as `build`. The intro and the
taan are not on the table — each has its own verified pipeline.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Literal, Optional

from pydantic import BaseModel, Field

from crew.contracts import (Arrangement, Composition, DebateEvent, EventType, Layer, LeadNote, LeadPhrase,
                            RhythmSection, RiffNote)
from crew.riff_notation import NotationError, parse_cycle, render_cycle

SitarPart = Literal["head", "manjha", "antara", "outro"]
SITAR_PARTS: Final[dict[str, str]] = {"head": "mukhada", "manjha": "manjha", "antara": "antara", "outro": "outro"}


# --------------------------------------------------------------------------- #
# Boundary contracts — what the players write.                               #
# --------------------------------------------------------------------------- #

class SitarRewrite(BaseModel):
    why: str = Field(description="what is wrong with the part now and what the rewrite does, in musical terms")
    part: SitarPart
    phrase: LeadPhrase


class RiffRewrite(BaseModel):
    why: str = Field(description="what is wrong with the riff now and what the rewrite does, in musical terms")
    section: int
    cycles: list[str] = Field(description="one compact-notation string per avartan, as many as the part has now")


class Critique(BaseModel):
    argument: str = Field(description="2-4 sentences about the notes: what the rewrite gains or loses")
    verdict: Literal["support", "oppose"]
    suggestion: str = Field(default="", description="one concrete change to the rewrite's notes, if any")


class SitarRevision(BaseModel):
    response: str = Field(description="answer the critique: what you take from it and what you keep")
    decision: Literal["keep", "revise", "withdraw"]
    phrase: Optional[LeadPhrase] = None


class RiffRevision(BaseModel):
    response: str = Field(description="answer the critique: what you take from it and what you keep")
    decision: Literal["keep", "revise", "withdraw"]
    cycles: Optional[list[str]] = None


# --------------------------------------------------------------------------- #
# The song the debate edits.                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Song:
    """Everything the pipeline builds a composition from (`flow._assemble` + `lead_layers_from`)."""
    arr: Arrangement
    phrases: dict[int, LeadPhrase]
    fills: list[LeadPhrase] = field(default_factory=list)
    rhythm: Optional[Layer] = None
    orchestra: list[Layer] = field(default_factory=list)


def part_sections(arr: Arrangement, part: str) -> list[int]:
    """The section indices a sitar part plays in (the head: every mukhada)."""
    role = SITAR_PARTS[part]
    return [i for i, s in enumerate(arr.sections) if s.form_role == role]


def apply_sitar(song: Song, part: str, phrase: LeadPhrase) -> Song:
    phrases = dict(song.phrases)
    for i in part_sections(song.arr, part):
        phrases[i] = phrase
    return Song(song.arr, phrases, song.fills, song.rhythm, song.orchestra)


def apply_riff(song: Song, section: int, cycles: list[list[RiffNote]]) -> Song:
    """The guitar part with one section's cycles replaced; its bass is left for code to derive
    from the new riff (a written bass would no longer match it)."""
    rs = song.arr.rhythm_section
    parts = [p.model_copy(update={"guitar": cycles, "bass": []}) if p.section == section else p for p in rs.parts]
    arr = song.arr.model_copy(update={"rhythm_section": rs.model_copy(update={"parts": parts})})
    return Song(arr, song.phrases, song.fills, song.rhythm, song.orchestra)


def riff_sections(rs: RhythmSection) -> list[int]:
    """The sections whose riff is written out — the pipeline's own rule (`rhythm_section._resolved`):
    a part with cycles plays them; only an EMPTY part replays the one its `same_as` names."""
    return [p.section for p in rs.parts if p.guitar]


def _part(rs: RhythmSection, section: int):
    return next((p for p in rs.parts if p.section == section), None)


# --------------------------------------------------------------------------- #
# Checks — every rewrite, before anyone builds it.                            #
# --------------------------------------------------------------------------- #

def sitar_errors(song: Song, part: str, phrase: LeadPhrase) -> list[str]:
    from crew.gat_verifier import check_mukhada, nyas_violations
    from crew.lead import _head_checks, phrase_grammar_error
    from gats import frame_for_bpm
    where = part_sections(song.arr, part)
    if not where:
        return [f"this song has no {part}"]
    old = song.phrases[where[0]]
    beats, new_beats = sum(n.dur for n in old.notes), sum(n.dur for n in phrase.notes)
    errors = [f"the rewrite fills {new_beats:g} beats; the {part} it replaces fills {beats:g} — match it exactly"] \
        if abs(beats - new_beats) > 1e-6 else []
    grammar = phrase_grammar_error(phrase, song.arr.raga)
    errors += [grammar] if grammar else []
    if part == "head":
        first, new_first = _first(old.notes), _first(phrase.notes)
        if first != new_first:
            errors.append(f"keep the head's first note ({first[0]}, octave {first[1]}): it sounds on every sam and "
                          f"the other parts land on it")
        cycle, frame = song.arr.beats_per_bar, frame_for_bpm(song.arr.bpm)
        errors += list(check_mukhada(phrase, cycle_beats=cycle, raga=song.arr.raga).hard)
        errors += list(_head_checks(phrase, cycle_beats=cycle, frame=frame, raga=song.arr.raga).hard)
    else:
        errors += nyas_violations(phrase.notes, song.arr.raga)
    return errors


def riff_errors(song: Song, section: int, texts: list[str]) -> tuple[list[list[RiffNote]], list[str]]:
    """The parsed cycles and the faults (empty when the rewrite can be played)."""
    from crew.rhythm_section import part_errors
    rs = song.arr.rhythm_section
    if rs is None or section not in riff_sections(rs):
        return [], [f"section {section} has no riff of its own to rewrite (choose from {riff_sections(rs) if rs else []})"]
    old = _part(rs, section)
    if len(texts) != len(old.guitar):
        return [], [f"section {section}'s riff has {len(old.guitar)} cycle(s); write exactly that many"]
    cycles, errors = [], []
    for i, text in enumerate(texts, start=1):
        try:
            cycles.append(parse_cycle(text))
        except NotationError as exc:
            errors.append(f"cycle {i}: {exc}")
    if errors:
        return [], errors
    return cycles, part_errors(apply_riff(song, section, cycles).arr.rhythm_section, song.arr)


def _first(notes: list[LeadNote]) -> tuple[str, int] | None:
    return next(((n.swara, n.oct) for n in notes if not n.rest), None)


# --------------------------------------------------------------------------- #
# What the players read — the song as notes.                                 #
# --------------------------------------------------------------------------- #

def sitar_tokens(notes: list[LeadNote]) -> str:
    """swara(octave):bol[beats] with ornaments: (kan)X, X~ andolan, X>Y meend, X<>Y gamak."""
    def token(n: LeadNote) -> str:
        if n.rest:
            return f"-[{n.dur:g}]"
        pitch = f"{n.swara}({n.oct:+d})" if n.oct else n.swara
        kan = f"({''.join(n.grace)})" if n.grace else ""
        marks = (f">{n.meend_swara}" if n.meend_swara else "") + (f"<>{n.gamak_with}" if n.gamak_with else "")
        return f"{kan}{pitch}{marks}{':' + n.bol if n.bol else ''}[{n.dur:g}]"
    return " ".join(token(n) for n in notes)


def render_piece(song: Song) -> str:
    """Every section: its role, length, the sitar's notes and the guitar's cycles."""
    from crew.generators import section_spans
    from crew.loudness import seconds_per_beat
    spb, rs = seconds_per_beat(song.arr), song.arr.rhythm_section
    shown: dict[str, int] = {}
    lines = []
    for span in section_spans(song.arr):
        i, s = span.index, span.section
        clock = f"{int(span.start * spb) // 60}:{int(span.start * spb) % 60:02d}"
        lines.append(f"SECTION {i} — {s.form_role or s.kind.value}, {s.bars} avartan(s), from {clock}")
        phrase = song.phrases.get(i)
        if phrase is not None:
            key = phrase.model_dump_json()
            if key in shown:
                lines.append(f"  sitar: the same phrase as section {shown[key]}")
            else:
                shown[key] = i
                lines.append(f"  sitar: {sitar_tokens(phrase.notes)}")
        part = _part(rs, i) if rs else None
        if part is not None and part.guitar:
            for k, cycle in enumerate(part.guitar, start=1):
                lines.append(f"  guitar cycle {k}: {render_cycle(cycle)}")
        elif part is not None and part.same_as is not None:
            lines.append(f"  guitar: the same riff as section {part.same_as}")
        elif "rhythm" not in s.layers:
            lines.append("  guitar: (does not play)")
    return "\n".join(lines)


def describe_sitar(song: Song, rewrite: SitarRewrite) -> str:
    old = song.phrases[part_sections(song.arr, rewrite.part)[0]]
    return (f"The sitarist rewrites the {rewrite.part.upper()} (sections {part_sections(song.arr, rewrite.part)}).\n"
            f"  now:      {sitar_tokens(old.notes)}\n  proposed: {sitar_tokens(rewrite.phrase.notes)}\n"
            f"  why: {rewrite.why}")


def describe_riff(song: Song, rewrite: RiffRewrite) -> str:
    old = _part(song.arr.rhythm_section, rewrite.section)
    now = " | ".join(render_cycle(c) for c in old.guitar)
    return (f"The guitarist rewrites the riff of SECTION {rewrite.section}.\n  now:      {now}\n"
            f"  proposed: {' | '.join(rewrite.cycles)}\n  why: {rewrite.why}")


# --------------------------------------------------------------------------- #
# The debate.                                                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Players:
    """The model calls, injected (live: `crew/notes_debate_crew.py`)."""
    propose_sitar: Callable[[str], SitarRewrite]
    propose_riff: Callable[[str], RiffRewrite]
    critique: Callable[[str, str, str], Critique]               # (critic, piece, the other's rewrite)
    revise_sitar: Callable[[str, str, str], SitarRevision]      # (piece, own rewrite, the critique)
    revise_riff: Callable[[str, str, str], RiffRevision]


@dataclass
class Debate:
    sitar: SitarRewrite | None = None
    riff: RiffRewrite | None = None
    critique_of_sitar: Critique | None = None
    critique_of_riff: Critique | None = None
    sitar_revision: SitarRevision | None = None
    riff_revision: RiffRevision | None = None
    final_sitar: LeadPhrase | None = None
    final_riff: list[str] | None = None
    versions: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def notes_debate(song: Song, players: Players, build: Callable[[Song, str], object]) -> Debate:
    """Propose, critique each other, revise — then build every version for the ear."""
    d = Debate(versions={"original": build(song, "original")})
    piece = render_piece(song)
    d.sitar = _safe(players.propose_sitar, piece, d, "the sitarist's proposal")
    d.riff = _safe(players.propose_riff, piece, d, "the guitarist's proposal")
    if d.sitar:
        d.versions["sitar_proposed"] = build(apply_sitar(song, d.sitar.part, d.sitar.phrase), "sitar_proposed")
        d.critique_of_sitar = _safe(lambda p: players.critique("guitarist", p, describe_sitar(song, d.sitar)),
                                    piece, d, "the guitarist's critique")
    if d.riff:
        d.versions["riff_proposed"] = build(_with_riff(song, d.riff.section, d.riff.cycles), "riff_proposed")
        d.critique_of_riff = _safe(lambda p: players.critique("sitarist", p, describe_riff(song, d.riff)),
                                   piece, d, "the sitarist's critique")
    if d.sitar and d.critique_of_sitar:
        d.sitar_revision = _safe(lambda p: players.revise_sitar(p, describe_sitar(song, d.sitar),
                                                                _critique_text(d.critique_of_sitar)),
                                 piece, d, "the sitarist's revision")
    if d.riff and d.critique_of_riff:
        d.riff_revision = _safe(lambda p: players.revise_riff(p, describe_riff(song, d.riff),
                                                              _critique_text(d.critique_of_riff)),
                                piece, d, "the guitarist's revision")
    d.final_sitar = _final(d.sitar and d.sitar.phrase, d.sitar_revision, "phrase")
    d.final_riff = _final(d.riff and d.riff.cycles, d.riff_revision, "cycles")
    final = song
    if d.final_sitar is not None:
        final = apply_sitar(final, d.sitar.part, d.final_sitar)
        d.versions["sitar_final"] = build(apply_sitar(song, d.sitar.part, d.final_sitar), "sitar_final")
    if d.final_riff is not None:
        final = _with_riff(final, d.riff.section, d.final_riff)
        d.versions["riff_final"] = build(_with_riff(song, d.riff.section, d.final_riff), "riff_final")
    if d.final_sitar is not None and d.final_riff is not None:
        d.versions["both_final"] = build(final, "both_final")
    return d


def _with_riff(song: Song, section: int, texts: list[str]) -> Song:
    return apply_riff(song, section, [parse_cycle(t) for t in texts])


def _final(proposed, revision, attr: str):
    """The rewrite that stands after the exchange: the revision's, the proposal kept, or nothing."""
    if proposed is None or revision is None:
        return proposed
    if revision.decision == "withdraw":
        return None
    if revision.decision == "revise" and getattr(revision, attr) is not None:
        return getattr(revision, attr)
    return proposed


def _critique_text(c: Critique) -> str:
    return f"{c.verdict.upper()}: {c.argument}" + (f"\n  suggestion: {c.suggestion}" if c.suggestion else "")


def _safe(call: Callable[[str], object], piece: str, d: Debate, what: str):
    """LIVE SAFETY: a dead call is recorded and the debate goes on without it."""
    try:
        return call(piece)
    except Exception as exc:  # noqa: BLE001
        d.notes.append(f"{what} failed: {type(exc).__name__}: {exc}")
        return None


# --------------------------------------------------------------------------- #
# In the pipeline: keep only the rewrites that beat the accepted song.        #
# --------------------------------------------------------------------------- #

Compare = Callable[[Composition, Composition, Arrangement], tuple[bool, list[DebateEvent]]]


@dataclass(frozen=True)
class Settled:
    song: Song
    composition: Composition
    kept: dict[str, bool]
    events: list[DebateEvent]


def settle(song: Song, d: Debate, original: Composition, assemble: Callable[[Song], Composition],
           compare: Compare) -> Settled:
    """The final rewrites are accepted ONE AT A TIME against the current champion — the sitar's
    first, then the guitar's — each blind and in both orders (`compare`). A rewrite that wins
    becomes the champion the next must beat, so the song that ships is always one the comparison
    actually heard (two rewrites that each beat the original were never heard together before).
    A failed comparison keeps the champion."""
    steps: list[tuple[str, Callable[[Song], Song]]] = []
    if d.final_sitar is not None:
        steps.append(("sitar", lambda s: apply_sitar(s, d.sitar.part, d.final_sitar)))
    if d.final_riff is not None:
        steps.append(("riff", lambda s: _with_riff(s, d.riff.section, d.final_riff)))
    champion, heard = song, original
    kept: dict[str, bool] = {}
    events: list[DebateEvent] = []
    for name, rewrite in steps:
        candidate = rewrite(champion)
        try:
            candidate_heard = assemble(candidate)
            kept[name], said = compare(heard, candidate_heard, song.arr)
        except Exception as exc:  # noqa: BLE001 — LIVE SAFETY: the champion stands
            kept[name], said = False, [_event(EventType.INFO, "Band", f"the {name} comparison failed ({exc})")]
        events += said
        if kept[name]:
            champion, heard = candidate, candidate_heard
    verdict = ", ".join(f"the {k} rewrite {'kept' if v else 'not kept'}" for k, v in kept.items()) or "nothing to judge"
    events.append(_event(EventType.VERDICT, "Band", f"notes debate settled: {verdict}", {"notes_debate": kept}))
    return Settled(champion, heard, kept, events)


def debate_events(song: Song, d: Debate) -> list[DebateEvent]:
    """The exchange as the UI and the trace show it — about notes, in the players' own words."""
    out: list[DebateEvent] = []
    if d.sitar:
        out.append(_event(EventType.PROPOSE, "Sitarist", describe_sitar(song, d.sitar)))
    if d.riff:
        out.append(_event(EventType.PROPOSE, "Guitarist", describe_riff(song, d.riff)))
    if d.critique_of_sitar:
        out.append(_event(EventType.CRITIQUE, "Guitarist", _critique_text(d.critique_of_sitar)))
    if d.critique_of_riff:
        out.append(_event(EventType.CRITIQUE, "Sitarist", _critique_text(d.critique_of_riff)))
    if d.sitar_revision:
        out.append(_event(EventType.REVISE, "Sitarist", f"{d.sitar_revision.decision}: {d.sitar_revision.response}"))
    if d.riff_revision:
        out.append(_event(EventType.REVISE, "Guitarist", f"{d.riff_revision.decision}: {d.riff_revision.response}"))
    out += [_event(EventType.INFO, "Band", note) for note in d.notes]
    return out


def debate_stage(arr: Arrangement, phrases: dict[int, LeadPhrase], fills: list[LeadPhrase],
                 rhythm: Optional[Layer], orchestra: list[Layer], composition: Composition, *,
                 players: Callable[[Song, str], Players], assemble: Callable[[Song], Composition],
                 compare: Compare, concern: str = "") -> tuple[Composition, Arrangement, list[DebateEvent], Debate, Settled]:
    """The Flow's notes-debate step: debate the accepted song ABOUT `concern` (the reviewers' words
    that called it), keep only the rewrites that beat it."""
    song = Song(arr, phrases, fills, rhythm, orchestra)
    d = notes_debate(song, players(song, concern), lambda s, name: None)   # no renders inside the pipeline
    settled = settle(song, d, composition, assemble, compare)
    return settled.composition, settled.song.arr, debate_events(song, d) + settled.events, d, settled


def _event(kind: EventType, agent: str, text: str, data: dict | None = None) -> DebateEvent:
    return DebateEvent(type=kind, agent=agent, role="composer", text=text, data=data or {})


def transcript(song: Song, d: Debate) -> str:
    out = ["# The notes debate", ""]
    if d.sitar:
        out += ["## The sitarist proposes", "```", describe_sitar(song, d.sitar), "```"]
    if d.critique_of_sitar:
        out += [f"**The guitarist ({d.critique_of_sitar.verdict}):** {d.critique_of_sitar.argument}"]
        out += [f"> suggestion: {d.critique_of_sitar.suggestion}"] if d.critique_of_sitar.suggestion else []
    if d.sitar_revision:
        r = d.sitar_revision
        out += [f"**The sitarist ({r.decision}):** {r.response}"]
        out += ["```", f"final: {sitar_tokens(r.phrase.notes)}", "```"] if r.decision == "revise" and r.phrase else []
    out.append("")
    if d.riff:
        out += ["## The guitarist proposes", "```", describe_riff(song, d.riff), "```"]
    if d.critique_of_riff:
        out += [f"**The sitarist ({d.critique_of_riff.verdict}):** {d.critique_of_riff.argument}"]
        out += [f"> suggestion: {d.critique_of_riff.suggestion}"] if d.critique_of_riff.suggestion else []
    if d.riff_revision:
        r = d.riff_revision
        out += [f"**The guitarist ({r.decision}):** {r.response}"]
        out += ["```", f"final: {' | '.join(r.cycles)}", "```"] if r.decision == "revise" and r.cycles else []
    out += ["", "## Listen", *[f"- {k}: {v}" for k, v in d.versions.items()]]
    out += ["", "## Notes", *[f"- {n}" for n in d.notes]] if d.notes else []
    return "\n".join(out) + "\n"
