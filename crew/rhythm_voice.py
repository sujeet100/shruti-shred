"""
The RHYTHM SECTION in the pipeline — the sitar first, then ONE call for guitar + bass around it,
with today's riff path as the fallback (`RMA_RHYTHM_SECTION`, Sujit's decision 2026-10-12).

  * `creative_voices_with_rhythm_section` — the lead is composed as before, WITHOUT the
    per-section riff calls (except in a riff_first piece on the parallel path, where the head
    quotes the riff and so needs it first). Then the rhythm-section call reads the placed sitar.
    The Composer path and the parallel path differ only in which lead composer runs and which
    legacy riff is the fallback.
  * `compose_rhythm_voice` — the call, made safe: a call that raises, or returns a part code
    cannot play, falls back to the legacy riff, and says so on the event stream. A success
    publishes the composed part (`RHYTHM_SECTION_KEY`), which the Flow stores on the chart
    (`rhythm_section.with_rhythm_section`) so assembly realises its bass and skips the code passes.
  * `revise_rhythm_voice` — a riff revise re-asks for the plan's sections only, with the plan's
    instruction and preserve list, and splices those parts into the stored ones; the rest of the
    rhythm section stands. An unplayable answer leaves the part unchanged.

Pure control flow: every LLM step is injected, so this is tested with no LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, Optional, Sequence

from crew.contracts import Arrangement, DebateEvent, EventType, Layer, RevisionPlan, RhythmSection
from crew.revision import target_sections
from crew.rhythm_section import RHYTHM_SECTION_KEY, part_errors, realise, splice_parts

_AGENT: Final = "Rhythm"
_ROLE: Final = "generator"

RhythmCall = Callable[..., RhythmSection]           # (arr, lead_layers, *, feedback=None)
VoicesFn = Callable[..., tuple[list[Layer], Optional[Layer], list[DebateEvent]]]
Legacy = Callable[[], tuple[Optional[Layer], list[DebateEvent]]]
Announce = Callable[[str, str], None]
Emit = Callable[[list[DebateEvent]], None]


def _quiet(agent: str, text: str) -> None:
    return None


def _keep(events: list[DebateEvent]) -> None:
    return None


def no_riff(arr: Arrangement, *args: object, **kwargs: object) -> tuple[None, list[DebateEvent]]:
    """A riff step that writes nothing — the rhythm section writes the guitar instead."""
    return None, []


def rhythm_section_event(rs: RhythmSection, text: str) -> DebateEvent:
    """The composed part on the event stream — the record the chart is updated from."""
    return DebateEvent(type=EventType.PROPOSE, agent=_AGENT, role=_ROLE, text=text,
                       data={RHYTHM_SECTION_KEY: rs.model_dump(exclude_none=True),
                             "reasoning": rs.reasoning})


def _fallback_event(reason: str) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent=_AGENT, role=_ROLE,
                       text=f"the rhythm section could not be used ({reason}) — the riff path plays")


def _summary(rs: RhythmSection) -> str:
    return "; ".join(f"section {p.section}: " + (f"same as {p.same_as}" if p.same_as is not None
                                                 else p.role or "—")
                     for p in rs.parts)


def compose_rhythm_voice(arr: Arrangement, lead_layers: Sequence[Layer], *, call: RhythmCall,
                         legacy: Legacy, announce: Announce = _quiet,
                         emit: Emit = _keep) -> tuple[Optional[Layer], list[DebateEvent]]:
    """(guitar, events) from the rhythm-section call, or from `legacy` when it cannot be used."""
    announce(_AGENT, "arranging guitar and bass around the sitar…")
    try:
        rs = call(arr, lead_layers)
        errors = part_errors(rs, arr)
    except Exception as exc:  # noqa: BLE001 — any failure of the call is a fallback, never a crash
        rs, errors = None, [f"{type(exc).__name__}: {exc}"]
    if rs is None or errors:
        rhythm, events = legacy()
        events = [_fallback_event(errors[0]), *events]
        emit(events)
        return rhythm, events
    guitar, _ = realise(rs, arr)
    events = [rhythm_section_event(rs, f"rhythm section — {_summary(rs)}")]
    emit(events)
    return guitar, events


def creative_voices_with_rhythm_section(
        arr: Arrangement, *, voices: VoicesFn, composer: bool, call: RhythmCall,
        legacy_riff: Callable[[Arrangement, list[DebateEvent]], tuple[Optional[Layer], list[DebateEvent]]],
        announce: Announce = _quiet, emit: Emit = _keep,
) -> tuple[list[Layer], Optional[Layer], list[DebateEvent]]:
    """Lead (and only the riff a riff_first head needs), then the rhythm section. `voices` is the
    path's own lead+riff composer called with a `riff_fn`; `legacy_riff(arr, lead_events)` is the
    path's riff for the fallback. Returns (lead_layers, rhythm, events)."""
    needs_riff = not composer and arr.anchor == "riff_first"
    riff_fn = None if needs_riff else no_riff
    lead_layers, quoted, events = voices(arr, riff_fn=riff_fn, announce=announce, emit=emit)

    def legacy() -> tuple[Optional[Layer], list[DebateEvent]]:
        return (quoted, []) if quoted is not None else legacy_riff(arr, events)

    from crew.anchor import with_realized_seeds    # the riff the head quoted is given material
    rhythm, rs_events = compose_rhythm_voice(with_realized_seeds(arr, events), lead_layers,
                                             call=call, legacy=legacy, announce=announce, emit=emit)
    return lead_layers, rhythm, [*events, *rs_events]


def _revision_feedback(plan: RevisionPlan, sections: Sequence[int]) -> list[str]:
    keep = f" Keep: {'; '.join(plan.preserve)}." if plan.preserve else ""
    return [f"A REVISION, not a first take: rewrite the parts of section(s) "
            f"{', '.join(map(str, sections))} only — {plan.instruction}.{keep} Return the full set "
            f"of parts; the other sections' parts will be kept as they were."]


def revise_rhythm_voice(arr: Arrangement, revised: Arrangement, plan: RevisionPlan,
                        lead_layers: Sequence[Layer], *, call: RhythmCall,
                        announce: Announce = _quiet) -> tuple[Optional[Layer], list[DebateEvent]]:
    """The riff revise on a composed rhythm section: re-ask for the plan's sections, splice them
    into the stored part, realise. An unusable answer keeps the stored part. `arr` must carry a
    rhythm section."""
    assert arr.rhythm_section is not None
    old = arr.rhythm_section
    sections = target_sections(arr, plan)
    announce(_AGENT, f"reworking the rhythm section in section(s) {sections}…")
    try:
        spliced = splice_parts(old, call(revised, lead_layers,
                                         feedback=_revision_feedback(plan, sections)), sections)
        errors = part_errors(spliced, arr)
    except Exception as exc:  # noqa: BLE001
        spliced, errors = old, [f"{type(exc).__name__}: {exc}"]
    if errors:
        spliced = old
    guitar, _ = realise(spliced, arr)
    text = (f"rhythm section reworked in section(s) {sections}" if not errors else
            f"the rhythm section revise could not be used ({errors[0]}) — the part stands")
    return guitar, [rhythm_section_event(spliced, text)]
