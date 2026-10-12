"""
Tests for the RHYTHM SECTION's pure half — the timed sitar line the call reads, the hard checks on
what it returns, and how its answer becomes guitar and bass layers. No LLM.

Runs as a script (`uv run python tests/test_rhythm_section.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    Layer,
    Note,
    RhythmSection,
    RiffNote,
    Section,
    SectionKind,
    SectionPart,
    build_arrangement,
)
from crew.generators import BASS_FLOOR, VOICES  # noqa: E402
from crew.rhythm_section import part_errors, realise, render_timed_lead  # noqa: E402

_BAND = ["lead", "rhythm", "drums", "drone"]


def _arr() -> Arrangement:
    """intro (no guitar) | mukhada x2 | manjha | mukhada — teentaal, 16 beats an avartan."""
    def sec(role: str, bars: int, layers: list[str], kind=SectionKind.MELODY) -> Section:
        return Section(kind=kind, bars=bars, layers=layers, foreground="lead",
                       riff_slot="main", form_role=role)
    draft = ArrangementDraft(
        raga="darbari", subgenre="progressive", tala="teentaal", bpm=120, motif=["g", "m", "R", "S"],
        sections=[sec("intro", 1, ["lead", "drone"], SectionKind.ALAAP), sec("mukhada", 2, _BAND),
                  sec("manjha", 1, _BAND), sec("mukhada", 1, _BAND)])
    return build_arrangement(draft, CompositionBrief(sa=62))


def _sitar(*notes: Note) -> list[Layer]:
    v = VOICES["sitar"]
    return [Layer(role="lead", instrument=v.instrument, program=v.program, channel=v.channel,
                  notes=list(notes))]


def _head(start: float) -> list[Note]:
    return [Note(swara="S", oct=0, start=start, dur=1.0),
            Note(swara="g", oct=0, start=start + 2, dur=4.0, andolan=True, grace=["m"]),
            Note(swara="R", oct=0, start=start + 8, dur=8.0)]


def _cycle(*items: tuple[str, float]) -> list[RiffNote]:
    return [RiffNote(swara=sw, dur=d) for sw, d in items]


_HOME = _cycle(("S", 8.0), ("S", 4.0), ("P", 4.0))          # home held, a move into the sam
_MOVE = _cycle(("S", 4.0), ("d", 4.0), ("n", 8.0))


def _good() -> RhythmSection:
    return RhythmSection(reasoning="home held; the head's one move; the manjha moves", parts=[
        SectionPart(section=1, role="rings under the held Ga", guitar=[_HOME],
                    bass=[_cycle(("S", 12.0), ("P", 4.0))]),
        SectionPart(section=2, role="moves under the low bridge", guitar=[_MOVE]),
        SectionPart(section=3, role="the head again", same_as=1)])


# --- what the call sees -------------------------------------------------------------------------

def test_the_sitar_line_shows_each_note_at_its_beat_with_its_ornaments():
    text = render_timed_lead(_sitar(*_head(16.0)), _arr())
    assert "section 0 (intro, 1 avartan, no guitar):" in text
    assert "section 1 (mukhada, 2 avartans, the guitar plays):" in text
    assert "0 S[1] · rest 1-2 · 2 (m)g~[4] · rest 6-8 · 8 R[8]" in text


def test_a_repeated_avartan_is_named_once():
    text = render_timed_lead(_sitar(*_head(16.0), *_head(32.0), *_head(64.0)), _arr())
    assert text.count("same as section 1, avartan 1") == 2
    assert "(the sitar is silent)" in text                      # the manjha here has no sitar


# --- what it may return -------------------------------------------------------------------------

def test_a_well_formed_rhythm_section_has_no_errors():
    assert part_errors(_good(), _arr()) == []


def test_every_section_the_guitar_plays_needs_a_part():
    rs = _good().model_copy(update={"parts": _good().parts[:2]})
    assert any("section 3 has the guitar playing but no part" in e for e in part_errors(rs, _arr()))


def test_same_as_must_name_a_section_with_its_own_cycles():
    parts = _good().parts
    rs = _good().model_copy(update={"parts": [parts[0], parts[1].model_copy(
        update={"guitar": [], "same_as": 3}), parts[2]]})
    assert any("section 2" in e and "same_as" in e for e in part_errors(rs, _arr()))


def test_cycles_must_fill_the_avartan_be_legal_and_the_bass_single_notes():
    rs = RhythmSection(parts=[
        SectionPart(section=1, guitar=[_cycle(("S", 8.0))],                     # half a cycle
                    bass=[[RiffNote(swara="S", dur=16.0, chord=["P"])]]),        # a bass chord
        SectionPart(section=2, guitar=[_cycle(("S", 8.0), ("D", 8.0))]),         # D: not Darbari
        SectionPart(section=3, same_as=1), SectionPart(section=9, guitar=[_HOME])])
    errors = " | ".join(part_errors(rs, _arr()))
    assert "section 1 guitar cycle 1" in errors
    assert "single notes" in errors
    assert "illegal in raga darbari" in errors
    assert "there is no section 9" in errors


# --- how it becomes layers ----------------------------------------------------------------------

def test_cycles_play_bar_by_bar_and_the_last_repeats():
    rs = _good().model_copy(update={"parts": [
        SectionPart(section=1, guitar=[_HOME, _MOVE]), SectionPart(section=2, guitar=[_MOVE]),
        SectionPart(section=3, guitar=[_HOME])]})
    guitar, _ = realise(rs, _arr())
    def roots(a: float, b: float) -> list[str]:
        return [n.swara for n in guitar.notes if a <= n.start < b]
    assert roots(16, 32) == ["S", "S", "P"] and roots(32, 48) == ["S", "d", "n"]


def test_the_head_recurs_identically_through_same_as():
    guitar, _ = realise(_good(), _arr())
    first = [(n.start - 16, n.swara, n.dur, tuple(n.chord or [])) for n in guitar.notes
             if 16 <= n.start < 32]
    again = [(n.start - 64, n.swara, n.dur, tuple(n.chord or [])) for n in guitar.notes
             if 64 <= n.start < 80]
    assert first == again


def test_bare_strokes_take_their_power_chord():
    guitar, _ = realise(_good(), _arr())
    sa = next(n for n in guitar.notes if n.swara == "S")
    assert sa.chord and "P" in sa.chord


def test_the_bass_sits_under_the_guitar_and_a_section_without_one_is_derived():
    arr = _arr()
    guitar, bass = realise(_good(), arr)
    written = [n for n in bass.notes if 16 <= n.start < 48]
    assert [n.swara for n in written[:2]] == ["S", "P"]
    assert all(n.oct == max(arr.registers["rhythm"] - 1, BASS_FLOOR) for n in written)
    derived = [n for n in bass.notes if 48 <= n.start < 64]       # the manjha wrote no bass
    on_attacks = {(n.start, n.swara) for n in derived if n.start in (48.0, 52.0, 56.0)}
    assert on_attacks == {(48.0, "S"), (52.0, "d"), (56.0, "n")}   # (with its walk-ins between)
    assert not [n for n in bass.notes if n.start < 16]            # no guitar, no bass


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
