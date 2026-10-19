"""
The REHEARSAL — a band argues over one shared song and settles it by playing (Sujit, 2026-10-19).

Our debates failed because the debaters were one mind twice, read the music as text, competed
with rival versions, and never tried an idea. A rehearsal fixes each of those:

  * every member HEARS the song — the mix and their own part solo, as in a monitor — so they
    get information that differs, not just a different name;
  * they share ONE song and each proposes at most one change from the rehearsal vocabulary
    (`rehearsal_edits`: sit out, louder, softer, sparser, chug, cut, repeat), played free by code;
  * each member hears the others' changes before/after and argues for or against them;
  * the BANDLEADER — fluent in Hindustani and Western theory, proposing nothing of their own —
    hears every before/after, reads the arguments, and decides; kept changes are merged and the
    next round starts from the new song. Bounded: `MAX_ROUNDS`, and it stops early when nobody
    proposes or nothing is kept;
  * at the end the bandleader hears the whole song before and after, BLIND and in BOTH orders, and
    the rehearsed version is kept only if it wins both — stacked changes that were each fine can
    still drift from what was good, and a split or a "same" keeps the original (the Producer's
    champion rule, applied to the band).

The band is two members since 2026-10-19 — the sitarist and the guitarist, the two parts an agent
actually writes; the drummer had no part to defend (the drums are code).

Pure orchestration: the model (`Ears`) and the renderer (`Studio`) are injected, so the loop is
tested with fakes; `talk/audio/rehearsal_run.py` wires Gemini audio and FluidSynth. Every answer
is validated at the edge with ONE bounded repair that names the fault (an impossible change is
named and sent back, like any guardrail).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from string import Template
from typing import Final, Literal, Optional, Protocol, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from crew.contracts import Arrangement, Composition
from crew.generators import section_spans
from crew.loudness import seconds_per_beat
from crew.rehearsal_edits import (KINDS, STRUCTURAL, Change, apply_change, change_errors, playing, stem,
                                  voices, window)
from raga import RAGAS
from subgenres import SUBGENRES
from talas import TALAS

MAX_ROUNDS: Final = 3       # round 2 of the first run was still finding things Sujit liked
GAP_S: Final = 1.5            # silence between BEFORE and AFTER (and between mix and monitor)
PAUSE_S: Final = 3.0          # silence between one proposal's pair and the next
CONTEXT_S: Final = 4.0        # the bars either side of a change, so it is heard in place
MAX_CLIP_S: Final = 50.0      # a long change is heard from its start, up to this much
_TRIES: Final = 2             # one answer + ONE repair
_PATH: Final = Path(__file__).parent / "config" / "rehearsal.yaml"
T = TypeVar("T")


# --------------------------------------------------------------------------- #
# Boundary contracts — validated once, at the edge.                           #
# --------------------------------------------------------------------------- #

class Proposal(BaseModel):
    heard: str
    change: Optional[Change] = None
    why: str = ""


class Reaction(BaseModel):
    proposal: int
    support: bool
    argument: str


class Reactions(BaseModel):
    reactions: list[Reaction]


class Decision(BaseModel):
    proposal: int
    keep: bool
    reason: str


class Ruling(BaseModel):
    reasoning: str
    decisions: list[Decision]


class FinalChoice(BaseModel):
    reasoning: str
    better: Literal["first", "second", "same"]


# --------------------------------------------------------------------------- #
# The seams.                                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Clip:
    """A stretch of one rendered version, in seconds (`end` None = to the end)."""
    version: str
    start: float = 0.0
    end: Optional[float] = None


class Ears(Protocol):
    """Hears the clips, joined with the given silences, and answers the prompt."""

    def __call__(self, clips: list[Clip], gaps: list[float], prompt: str) -> str: ...


class Studio(Protocol):
    """Renders a song version; returns its name, which a Clip can then refer to."""

    def __call__(self, comp: Composition, arr: Arrangement, name: str) -> str: ...


@dataclass(frozen=True)
class Member:
    key: str
    name: str
    monitor: tuple[str, ...]
    persona: str


@dataclass
class Tried:
    """One proposal the band played: who, what, and the version it made."""
    number: int
    member: Member
    proposal: Proposal
    version: str
    before: Clip
    after: Clip


@dataclass
class Round:
    number: int
    song: str
    proposals: dict[str, Proposal | None] = field(default_factory=dict)
    tried: list[Tried] = field(default_factory=list)
    reactions: dict[str, Reactions | None] = field(default_factory=dict)
    ruling: Ruling | None = None
    kept: list[int] = field(default_factory=list)
    result: str = ""
    note: str = ""


@dataclass(frozen=True)
class FinalCheck:
    """The bandleader's blind before/after verdict on the whole song, asked in both orders."""
    before_first: FinalChoice | None
    after_first: FinalChoice | None

    @property
    def rehearsed_wins(self) -> bool:
        return (self.before_first is not None and self.before_first.better == "second"
                and self.after_first is not None and self.after_first.better == "first")


@dataclass
class Rehearsal:
    """Every round, the song as it came in, and the song the band ends with."""
    rounds: list[Round]
    start: str
    song: str
    check: FinalCheck | None = None


@cache
def _prompts() -> dict:
    return yaml.safe_load(_PATH.read_text())


def members() -> list[Member]:
    return [Member(key, m["name"], tuple(m["monitor"]), m["persona"].strip())
            for key, m in _prompts()["members"].items()]


def bandleader() -> Member:
    b = _prompts()["bandleader"]
    return Member("bandleader", b["name"], (), b["persona"].strip())


# --------------------------------------------------------------------------- #
# The loop.                                                                   #
# --------------------------------------------------------------------------- #

def rehearse(comp: Composition, arr: Arrangement, *, ears: Ears, studio: Studio,
             band: list[Member] | None = None, leader: Member | None = None,
             rounds: int = MAX_ROUNDS) -> Rehearsal:
    """The rehearsal, from the song as it came in to the song the band ends with: the last
    rehearsed version when it wins the final check, else the song as it came in."""
    band, leader = band or members(), leader or bandleader()
    start_arr = arr
    start = song = studio(comp, arr, "r0_song")
    history: list[str] = []
    log: list[Round] = []
    for r in range(1, rounds + 1):
        rnd = Round(r, song)
        log.append(rnd)
        for m in band:
            monitor = studio(stem(comp, m.monitor), arr, f"r{r}_{m.key}_monitor")
            rnd.proposals[m.key] = _ask(ears, [Clip(song), Clip(monitor)], [GAP_S],
                                        lambda fix, m=m: propose_prompt(m, comp, arr, history, fix),
                                        _proposal_parser(comp, arr))
        rnd.tried = _try_all(rnd, band, comp, arr, studio)
        if not rnd.tried:
            rnd.result, rnd.note = song, "nobody proposed a change"
            break
        for m in band:
            others = [t for t in rnd.tried if t.member.key != m.key]
            if others:
                rnd.reactions[m.key] = _ask(ears, *_pairs(others), lambda fix, m=m, o=others: react_prompt(
                    m, comp, arr, o, fix), _parser(Reactions, [t.number for t in others]))
        rnd.ruling = _ask(ears, *_pairs(rnd.tried), lambda fix: rule_prompt(leader, comp, arr, rnd, fix),
                          _parser(Ruling, [t.number for t in rnd.tried]))
        rnd.kept = [d.proposal for d in (rnd.ruling.decisions if rnd.ruling else []) if d.keep]
        if not rnd.kept:
            rnd.result, rnd.note = song, "the bandleader kept nothing"
            break
        changes = [t.proposal.change for t in rnd.tried if t.number in rnd.kept]
        comp, arr, dropped = merge(changes, comp, arr)
        if dropped:
            rnd.note = f"{len(dropped)} kept change(s) overlapped another structural change and were not played"
        song = rnd.result = studio(comp, arr, f"r{r}_result")
        history += [describe(c) for c in changes if c not in dropped]
    if song == start:
        return Rehearsal(log, start, start)
    check = final_check(ears, leader, start, start_arr, song, arr)
    return Rehearsal(log, start, song if check.rehearsed_wins else start, check)


def final_check(ears: Ears, leader: Member, start: str, start_arr: Arrangement, song: str,
                arr: Arrangement) -> FinalCheck:
    """Before vs after, whole songs, blind, in both orders (one call each)."""
    def ask(first: str, first_arr: Arrangement, second: str) -> FinalChoice | None:
        return _ask(ears, [Clip(first), Clip(second)], [GAP_S],
                    lambda fix: final_prompt(leader, start_arr, _duration(first_arr), fix), _parser(FinalChoice, []))
    return FinalCheck(ask(start, start_arr, song), ask(song, arr, start))


def _try_all(rnd: Round, band: list[Member], comp: Composition, arr: Arrangement, studio: Studio) -> list[Tried]:
    tried: list[Tried] = []
    for m in band:
        proposal = rnd.proposals.get(m.key)
        if proposal is None or proposal.change is None:
            continue
        number = len(tried) + 1
        new_comp, new_arr = apply_change(proposal.change, comp, arr)
        version = studio(new_comp, new_arr, f"r{rnd.number}_p{number}_{m.key}")
        before, after = excerpts(proposal.change, arr, rnd.song, version)
        tried.append(Tried(number, m, proposal, version, before, after))
    return tried


def merge(changes: list[Change], comp: Composition,
          arr: Arrangement) -> tuple[Composition, Arrangement, list[Change]]:
    """Play every kept change on one song. Voice changes first (they keep the section numbers the
    band used), then cuts/repeats from the last section back so earlier numbers stay true. A
    cut/repeat overlapping one already applied is dropped (returned) rather than guessed at."""
    plain = [c for c in changes if c.kind not in STRUCTURAL]
    structural = sorted((c for c in changes if c.kind in STRUCTURAL), key=lambda c: -min(c.sections))
    for c in plain:
        comp, arr = apply_change(c, comp, arr)
    taken: set[int] = set()
    dropped: list[Change] = []
    for c in structural:
        if taken & set(c.sections):
            dropped.append(c)
            continue
        comp, arr = apply_change(c, comp, arr)
        taken |= set(c.sections)
    return comp, arr, dropped


def excerpts(change: Change, arr: Arrangement, before: str, after: str) -> tuple[Clip, Clip]:
    """The passage around a change, as heard BEFORE and AFTER it (seconds)."""
    spb = seconds_per_beat(arr)
    start, end = (b * spb for b in window(change, arr))
    lo = max(0.0, start - CONTEXT_S)
    length = {"cut": 0.0, "repeat": 2 * (end - start)}.get(change.kind, end - start)
    hi_before = end + CONTEXT_S
    hi_after = start + length + CONTEXT_S
    cap = lo + MAX_CLIP_S
    return Clip(before, lo, min(hi_before, cap)), Clip(after, lo, min(hi_after, cap))


def _pairs(tried: list[Tried]) -> tuple[list[Clip], list[float]]:
    clips: list[Clip] = []
    gaps: list[float] = []
    for i, t in enumerate(tried):
        clips += [t.before, t.after]
        gaps += [GAP_S] + ([PAUSE_S] if i < len(tried) - 1 else [])
    return clips, gaps


# --------------------------------------------------------------------------- #
# Answers, validated at the edge (one repair that names the fault).           #
# --------------------------------------------------------------------------- #

def _ask(ears: Ears, clips: list[Clip], gaps: list[float], build: Callable[[str], str],
         parse: Callable[[str], T]) -> Optional[T]:
    fix = ""
    for _ in range(_TRIES):
        text = ears(clips, gaps, build(fix))
        try:
            return parse(text)
        except ValueError as error:
            fix = Template(_prompts()["repair"]).safe_substitute(error=str(error)[:400])
    return None


def _json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("no JSON object in the answer")
    return match.group(0)


def _proposal_parser(comp: Composition, arr: Arrangement) -> Callable[[str], Proposal]:
    def parse(text: str) -> Proposal:
        try:
            proposal = Proposal.model_validate_json(_json(text))
        except ValidationError as error:
            raise ValueError(str(error)) from error
        if proposal.change is not None:
            errors = change_errors(proposal.change, comp, arr)
            if errors:
                raise ValueError("the change cannot be played: " + "; ".join(errors))
        return proposal
    return parse


def _parser(model: type[T], numbers: list[int]) -> Callable[[str], T]:
    def parse(text: str) -> T:
        try:
            answer = model.model_validate_json(_json(text))
        except ValidationError as error:
            raise ValueError(str(error)) from error
        items = getattr(answer, "reactions", None) or getattr(answer, "decisions", [])
        if numbers and sorted(i.proposal for i in items) != sorted(numbers):
            raise ValueError(f"answer each proposal exactly once: proposals {numbers}")
        return answer
    return parse


# --------------------------------------------------------------------------- #
# Prompts — pure renderers over crew/config/rehearsal.yaml.                   #
# --------------------------------------------------------------------------- #

def _clock(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def section_map(comp: Composition, arr: Arrangement) -> str:
    spb = seconds_per_beat(arr)
    who = playing(comp, arr)
    return "\n".join(f"  {s.index + 1}. {s.section.form_role or s.section.kind.value:<11} "
                     f"{_clock(s.start * spb)}-{_clock(s.end * spb)}  {', '.join(who[s.index]) or 'silence'}"
                     for s in section_spans(arr))


def _duration(arr: Arrangement) -> float:
    return section_spans(arr)[-1].end * seconds_per_beat(arr)


def _piece(comp: Composition, arr: Arrangement) -> str:
    request = f'The request it answers: "{arr.request.strip()}"' if arr.request.strip() else ""
    return Template(_prompts()["piece"]).safe_substitute(
        raga=RAGAS[arr.raga]["display"], subgenre=SUBGENRES[arr.subgenre]["display"],
        tala=TALAS[arr.tala]["display"], bpm=arr.bpm, duration=_clock(_duration(arr)),
        request=request, section_map=section_map(comp, arr),
        house_rules="\n".join(f"  - {rule}" for rule in _prompts().get("house_rules", [])) or "  (none)")


def _vocabulary(comp: Composition) -> str:
    return Template(_prompts()["vocabulary"]).safe_substitute(
        kinds="\n".join(f"  - {k}: {v}" for k, v in KINDS.items()), voices=", ".join(voices(comp)))


def describe(change: Change) -> str:
    where = ", ".join(str(s) for s in change.sections)
    who = "" if change.kind in STRUCTURAL else f"{change.voice} "
    return f"{who}{change.kind.replace('_', ' ')} in section{'s' if len(change.sections) > 1 else ''} {where}"


def propose_prompt(m: Member, comp: Composition, arr: Arrangement, history: list[str], fix: str = "") -> str:
    done = ("ALREADY CHANGED in earlier rounds (the map above shows the song as it is now): "
            + "; ".join(history) + "\n") if history else ""
    return Template(_prompts()["propose"]).safe_substitute(
        persona=m.persona, piece=_piece(comp, arr), vocabulary=_vocabulary(comp), history=done,
        mix_end=_clock(_duration(arr)), gap=f"{GAP_S:g}", monitor=", ".join(m.monitor), repair=fix)


def _clip_lines(tried: list[Tried]) -> str:
    return "\n".join(f"  proposal {t.number} ({t.member.name}): {describe(t.proposal.change)} — "
                     f"heard from {_clock(t.before.start)} of the song" for t in tried)


def react_prompt(m: Member, comp: Composition, arr: Arrangement, others: list[Tried], fix: str = "") -> str:
    clips = "\n".join(f"{line}\n    why: {t.proposal.why}" for line, t in zip(_clip_lines(others).split("\n"), others))
    return Template(_prompts()["react"]).safe_substitute(
        persona=m.persona, piece=_piece(comp, arr), clips=clips, gap=f"{GAP_S:g}", pause=f"{PAUSE_S:g}",
        repair=fix)


def rule_prompt(leader: Member, comp: Composition, arr: Arrangement, rnd: Round, fix: str = "") -> str:
    names = {t.member.key: t.member.name for t in rnd.tried} | {m.key: m.name for m in members()}
    lines = []
    for t in rnd.tried:
        lines.append(f"  PROPOSAL {t.number} — {t.member.name}: {describe(t.proposal.change)}\n"
                     f"    what they heard: {t.proposal.heard}\n    why: {t.proposal.why}")
        for key, answer in rnd.reactions.items():
            for r in (answer.reactions if answer else []):
                if r.proposal == t.number:
                    lines.append(f"    {names.get(key, key)} {'SUPPORTS' if r.support else 'OPPOSES'}: {r.argument}")
    return Template(_prompts()["rule"]).safe_substitute(
        persona=leader.persona, piece=_piece(comp, arr), debate="\n".join(lines),
        clips=_clip_lines(rnd.tried), gap=f"{GAP_S:g}", pause=f"{PAUSE_S:g}", repair=fix)


def final_prompt(leader: Member, arr: Arrangement, first_s: float, fix: str = "") -> str:
    return Template(_prompts()["final"]).safe_substitute(
        persona=leader.persona, raga=RAGAS[arr.raga]["display"], subgenre=SUBGENRES[arr.subgenre]["display"],
        tala=TALAS[arr.tala]["display"], bpm=arr.bpm, first_end=_clock(first_s), gap=f"{GAP_S:g}", repair=fix)


def transcript(rehearsal: Rehearsal) -> str:
    """The rehearsal as a readable script, round by round, then the final check."""
    out: list[str] = []
    for rnd in rehearsal.rounds:
        out.append(f"## Round {rnd.number} (playing {rnd.song})")
        for key, p in rnd.proposals.items():
            if p is None:
                out.append(f"- **{key}**: (no usable answer)")
                continue
            change = describe(p.change) if p.change else "no change"
            out.append(f"- **{key}** heard: {p.heard}\n  proposes: **{change}** — {p.why}")
        for key, answer in rnd.reactions.items():
            for r in (answer.reactions if answer else []):
                out.append(f"  - {key} on proposal {r.proposal}: {'for' if r.support else 'against'} — {r.argument}")
        if rnd.ruling:
            out.append(f"- **bandleader**: {rnd.ruling.reasoning}")
            for d in rnd.ruling.decisions:
                out.append(f"  - proposal {d.proposal}: {'KEEP' if d.keep else 'drop'} — {d.reason}")
        out.append(f"- result: {rnd.result or '(none)'}" + (f" — {rnd.note}" if rnd.note else ""))
    check = rehearsal.check
    if check is not None:
        out.append("## Final check (bandleader, blind, both orders)")
        for label, choice in (("before first", check.before_first), ("after first", check.after_first)):
            out.append(f"- {label}: {choice.better if choice else '(no usable answer)'}"
                       + (f" — {choice.reasoning}" if choice else ""))
    out.append(f"- **the band ends with {rehearsal.song}**"
               + ("" if rehearsal.song != rehearsal.start or check is None else " (the rehearsed version did not win both)"))
    return "\n".join(out)


def as_record(rehearsal: Rehearsal) -> str:
    def tried(t: Tried) -> dict:
        return {"number": t.number, "member": t.member.key, "change": t.proposal.change.model_dump(),
                "version": t.version, "before": vars(t.before), "after": vars(t.after)}
    rounds = [{"round": r.number, "song": r.song, "result": r.result, "note": r.note, "kept": r.kept,
                        "proposals": {k: p.model_dump() if p else None for k, p in r.proposals.items()},
                        "tried": [tried(t) for t in r.tried],
                        "reactions": {k: a.model_dump() if a else None for k, a in r.reactions.items()},
                        "ruling": r.ruling.model_dump() if r.ruling else None} for r in rehearsal.rounds]
    check = rehearsal.check
    return json.dumps({"start": rehearsal.start, "song": rehearsal.song, "rounds": rounds,
                       "final_check": None if check is None else {
                           "before_first": check.before_first.model_dump() if check.before_first else None,
                           "after_first": check.after_first.model_dump() if check.after_first else None,
                           "rehearsed_wins": check.rehearsed_wins}}, indent=1)
