"""
Tests for crew/repairs.py + crew/arranger.py — the ARRANGER pass. All pure (no LLM).

The agent here chooses from a menu CODE builds, so what must be proven is that the menu can
only contain legal, surgical repairs, that the right-of-way rule decides who gives way, and
that the pass ALWAYS terminates with the piece no worse than the old deterministic guard
left it. The taste — which legal repair sounds best — is the only thing the model owns, and
a fake `decide_fn` stands in for it throughout.

Runs as a script (`uv run python tests/test_arranger.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.arranger import (  # noqa: E402
    Finding,
    _picks_from_decision,
    arrange,
    deterministic_decider,
)
from crew.coexistence import coexistence_of  # noqa: E402
from crew.contracts import (  # noqa: E402
    ArrangerChoice,
    ArrangerDecision,
    ArrangementDraft,
    CompositionBrief,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.repairs import (  # noqa: E402
    Repair,
    RepairKind,
    Yielder,
    apply_repairs,
    grind_repairs,
    right_of_way,
)
from raga import RAGAS, directional_varjya  # noqa: E402

_MOTIF = ["S", "g", "m", "P"]


def _arr(anchor: str = "gat_first", form_role: str | None = None, *, bars: int = 1):
    draft = ArrangementDraft(
        raga="bhairavi", subgenre="doom", tala="teentaal", bpm=72, motif=_MOTIF,
        anchor=anchor,
        sections=[Section(kind=SectionKind.SOLO, bars=bars, layers=["lead", "rhythm"],
                          foreground="lead", form_role=form_role)])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _riff(notes: list[Note]) -> Layer:
    return Layer(role="rhythm", notes=notes)


def _leads(notes: list[Note]) -> list[Layer]:
    return [Layer(role="lead", notes=notes)]


def _clashing():
    """A riff on komal re under a held Sa — a semitone, the plainest grind there is."""
    return (_riff([Note(swara="r", oct=-2, start=0.0, dur=1.0, chord=["M"])]),
            _leads([Note(swara="S", oct=0, start=0.0, dur=2.0)]))


# --- right of way: code decides who moves, never a negotiation -----------------

def test_the_anchor_decides_who_gives_way():
    section = _arr().sections[0]
    assert right_of_way(section, "gat_first") is Yielder.RIFF
    assert right_of_way(section, "riff_first") is Yielder.LEAD


def test_a_section_the_melody_owns_overrides_the_anchor():
    """Nothing re-pitches a taan — the melody IS the section there, however the piece is
    anchored."""
    taan = _arr(anchor="riff_first", form_role="taan_long").sections[0]
    assert right_of_way(taan, "riff_first") is Yielder.RIFF


def test_a_section_the_riff_owns_overrides_it_the_other_way():
    breakdown = _arr(anchor="gat_first", form_role="breakdown").sections[0]
    assert right_of_way(breakdown, "gat_first") is Yielder.LEAD


# --- the menu: every option legal, and only local edits ------------------------

def test_every_offered_reseat_is_raga_legal_and_direction_safe():
    """The agent cannot choose an illegal pitch because one is never offered. Reseats also
    refuse direction-sensitive swaras, which a local repair has no way to reason about."""
    riff, leads = _clashing()
    arr = _arr()
    (section,) = coexistence_of(riff, leads, arr).sections
    allowed, varjya = set(RAGAS["bhairavi"]["allowed"]), directional_varjya("bhairavi")
    offered = [r for g in section.grinds
               for r in grind_repairs(g, yielder=Yielder.RIFF, raga="bhairavi",
                                      riff_notes=riff.notes, lead_notes=leads[0].notes)]
    reseats = [r for r in offered if r.kind is RepairKind.RESEAT_RIFF]
    assert reseats, "a grinding root must have somewhere consonant to go"
    for repair in reseats:
        assert repair.swara in allowed and repair.swara not in varjya


def test_keep_is_always_on_the_menu():
    """An arranger who judges a clash expressive must be able to say so — a pass that can
    only 'fix' sands the music smooth."""
    riff, leads = _clashing()
    (section,) = coexistence_of(riff, leads, _arr()).sections
    for grind in section.grinds:
        repairs = grind_repairs(grind, yielder=Yielder.RIFF, raga="bhairavi",
                                riff_notes=riff.notes, lead_notes=leads[0].notes)
        assert repairs[-1].kind is RepairKind.KEEP


def test_a_chord_tone_grind_is_offered_the_surgical_fix_first():
    riff, leads = _clashing()
    (section,) = coexistence_of(riff, leads, _arr()).sections
    (tone_grind,) = [g for g in section.grinds if g.from_chord]
    first = grind_repairs(tone_grind, yielder=Yielder.RIFF, raga="bhairavi",
                          riff_notes=riff.notes, lead_notes=leads[0].notes)[0]
    assert first.kind is RepairKind.DROP_TONE and first.swara == "M"


# --- applying: surgical, and never a rhythm change -----------------------------

def test_a_repair_never_moves_an_attack_or_changes_the_cell():
    """The riff's identity is what a listener remembers, so it is protected by construction
    rather than by asking the agent to be careful."""
    riff, leads = _clashing()
    riff = _riff(riff.notes + [Note(swara="S", oct=-2, start=1.0, dur=1.0)])
    repaired, _ = apply_repairs(riff, leads, [(0, Repair(RepairKind.DAMP))])
    assert [n.start for n in repaired.notes] == [n.start for n in riff.notes]
    assert len(repaired.notes) == len(riff.notes)
    assert repaired.notes[1] == riff.notes[1]           # an untouched note is untouched


def test_damping_strips_the_stack_and_clips_to_a_chug():
    riff, leads = _clashing()
    repaired, _ = apply_repairs(riff, leads, [(0, Repair(RepairKind.DAMP))])
    note = repaired.notes[0]
    assert note.chord is None and note.dur <= 0.5 and note.technique == "palm_mute"


def test_reseating_a_gliding_melody_note_moves_where_it_LANDS():
    """A meend sounds at its target, so moving the written swara would leave the clash and
    silently redirect the glide."""
    leads = _leads([Note(swara="S", oct=0, start=0.0, dur=2.0, meend_swara="r", meend_oct=0)])
    riff = _riff([Note(swara="S", oct=-2, start=0.0, dur=1.0)])
    _, moved = apply_repairs(riff, leads, [(0, Repair(RepairKind.RESEAT_LEAD, "m"))],
                             lead_targets={0: 0})
    note = moved[0].notes[0]
    assert note.meend_swara == "m" and note.swara == "S"


# --- the pass: bounded, and it always terminates -------------------------------

def test_a_clean_piece_is_returned_untouched_and_makes_no_call():
    """Cost follows the evidence: no findings, no decider, no tokens."""
    riff = _riff([Note(swara="S", oct=-2, start=0.0, dur=1.0)])
    leads = _leads([Note(swara="P", oct=0, start=0.0, dur=2.0)])

    def _never(*_args):
        raise AssertionError("a clean section must not reach the decider")

    out_riff, out_leads, events = arrange(riff, leads, _arr(), decide_fn=_never)
    assert out_riff is riff and out_leads is leads and events == []


def test_the_pass_repairs_what_it_finds_and_reports_it():
    riff, leads = _clashing()
    repaired, _, events = arrange(riff, leads, _arr(), decide_fn=deterministic_decider)
    assert coexistence_of(repaired, leads, _arr()).clean
    assert len(events) == 1 and events[0].agent == "Arranger"


def test_keeping_every_clash_still_terminates_with_the_deterministic_sweep():
    """The terminator: an agent that repairs NOTHING must not leave the piece grinding —
    code damps whatever survives, so the pass is never worse than the old guard."""
    riff, leads = _clashing()

    def _keep_everything(_section, findings):
        return [Repair(RepairKind.KEEP) for _ in findings]

    repaired, _, _ = arrange(riff, leads, _arr(), decide_fn=_keep_everything)
    assert repaired.notes[0].dur <= 0.5 and repaired.notes[0].chord is None


def test_a_decider_that_explodes_falls_back_instead_of_failing_the_run():
    riff, leads = _clashing()

    def _broken(_section, _findings):
        raise RuntimeError("the model timed out")

    repaired, _, _ = arrange(riff, leads, _arr(), decide_fn=_broken)
    assert coexistence_of(repaired, leads, _arr()).clean


# --- mapping the agent's answer back onto the menu -----------------------------

def _menu() -> list[Finding]:
    return [Finding(label="a clash", riff_index=0, lead_index=None,
                    repairs=(Repair(RepairKind.DROP_TONE, "M"), Repair(RepairKind.DAMP),
                             Repair(RepairKind.KEEP)))]


def test_an_offered_repair_is_honoured():
    decision = ArrangerDecision(choices=[ArrangerChoice(finding=0, repair="damp")])
    assert _picks_from_decision(decision, _menu())[0].kind is RepairKind.DAMP


def test_a_repair_that_was_never_offered_falls_back_to_the_safest():
    """The menu is the authority, not the reply — an invented repair cannot reach the music."""
    decision = ArrangerDecision(choices=[ArrangerChoice(finding=0, repair="reseat_riff:N")])
    assert _picks_from_decision(decision, _menu())[0].kind is RepairKind.DROP_TONE


def test_a_finding_the_agent_skipped_still_gets_repaired():
    assert _picks_from_decision(ArrangerDecision(), _menu())[0].kind is RepairKind.DROP_TONE


def test_a_finding_number_out_of_range_is_ignored():
    decision = ArrangerDecision(choices=[ArrangerChoice(finding=7, repair="damp")])
    assert _picks_from_decision(decision, _menu())[0].kind is RepairKind.DROP_TONE


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
