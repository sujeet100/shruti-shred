"""Pure tests for the rehearsal (`crew/rehearsal_edits.py`, `crew/rehearsal.py`): the edits play
what they say, and the loop runs with fake ears and a fake studio. No API, no audio."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crew.contracts import (ArrangementDraft, CompositionBrief, Composition, DrumHit, Layer, Note,  # noqa: E402
                            Section, SectionKind, build_arrangement)
from crew.rehearsal import (MAX_ROUNDS, Clip, Member, _prompts, excerpts, members, merge,  # noqa: E402
                            propose_prompt, react_prompt, rehearse, rule_prompt)
from crew.rehearsal_edits import Change, apply_change, change_errors, playing  # noqa: E402


def _arr(n: int = 3):
    sections = [Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "rhythm", "drone", "drums"],
                        foreground="lead", form_role=role) for role in ("mukhada", "antara", "mukhada")[:n]]
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=120, motif=["S"],
                             sections=sections)
    return build_arrangement(draft, CompositionBrief(request="slow doom Darbari"))


def _comp() -> Composition:
    """Three 16-beat sections: sitar quarters, guitar eighths, a drone held through, a kick per beat."""
    sitar = [Note(swara="S", start=float(b), dur=1.0, vel=80) for b in range(48)]
    guitar = [Note(swara="S", start=b / 2, dur=0.5, vel=100, technique="palm_mute") for b in range(96)]
    drone = [Note(swara="S", oct=-1, start=0.0, dur=48.0, vel=50)]
    kick = [DrumHit(drum="kick", start=float(b)) for b in range(48)]
    return Composition(raga="darbari", bpm=120, tala={"name": "teentaal", "beats_per_bar": 16}, layers=[
        Layer(role="lead", instrument="sitar", notes=sitar), Layer(role="rhythm", notes=guitar),
        Layer(role="drone", notes=drone), Layer(role="drums", hits=kick)])


def _layer(comp: Composition, role: str):
    return next(layer for layer in comp.layers if layer.role == role)


def test_sit_out_silences_only_that_voice_and_the_drone_resumes():
    comp, arr = apply_change(Change(kind="sit_out", voice="sitar", sections=[2]), _comp(), _arr())
    starts = [n.start for n in _layer(comp, "lead").notes]
    assert not any(16 <= s < 32 for s in starts) and len(starts) == 32
    held, _ = apply_change(Change(kind="sit_out", voice="drone", sections=[2]), _comp(), _arr())
    assert [(n.start, n.dur) for n in _layer(held, "drone").notes] == [(0.0, 16.0), (32.0, 16.0)]
    assert playing(comp, arr)[1] == ["guitars", "drums", "drone"]


def test_sparser_hits_each_vibhag_and_lets_it_ring():
    comp, _ = apply_change(Change(kind="sparser", voice="guitars", sections=[1]), _comp(), _arr())
    first = [n for n in _layer(comp, "rhythm").notes if n.start < 16]
    assert [(n.start, n.dur, n.technique) for n in first] == [(0.0, 4.0, None), (4.0, 4.0, None),
                                                              (8.0, 4.0, None), (12.0, 4.0, None)]


def test_chug_keeps_the_rhythm_on_a_low_sa_pedal():
    comp = _comp()
    rhythm = _layer(comp, "rhythm").model_copy(update={"notes": [
        Note(swara=sw, oct=o, start=b / 2, dur=0.5, chord=["P"]) for b, (sw, o) in
        enumerate([("P", 0), ("m", -1), ("g", 0)] * 32)]})
    comp = comp.model_copy(update={"layers": [rhythm if layer.role == "rhythm" else layer for layer in comp.layers]})
    out, _ = apply_change(Change(kind="chug", voice="guitars", sections=[2]), comp, _arr())
    inside = [n for n in _layer(out, "rhythm").notes if 16 <= n.start < 32]
    assert {(n.swara, n.oct, n.technique, n.chord) for n in inside} == {("S", -1, "palm_mute", None)}
    assert [n.start for n in inside] == [16 + b / 2 for b in range(32)]
    assert _layer(out, "rhythm").notes[0].swara == "P"                       # outside: untouched


def test_cut_and_repeat_move_the_song_and_its_map():
    comp, arr = apply_change(Change(kind="cut", voice="", sections=[2]), _comp(), _arr())
    assert len(arr.sections) == 2 and max(n.start for n in _layer(comp, "lead").notes) == 31.0
    assert _layer(comp, "drone").notes[0].dur == 32.0
    comp, arr = apply_change(Change(kind="repeat", voice="", sections=[1]), _comp(), _arr())
    assert len(arr.sections) == 4 and len(_layer(comp, "lead").notes) == 64
    drone = [(n.start, n.start + n.dur) for n in _layer(comp, "drone").notes]
    assert drone == [(0.0, 16.0), (16.0, 64.0)]                       # the repeat re-strikes the drone


def test_impossible_changes_are_named():
    assert change_errors(Change(kind="louder", voice="orchestra", sections=[9]), _comp(), _arr())[0].startswith("section 9")
    assert any("not a voice" in e for e in change_errors(Change(kind="louder", voice="orchestra", sections=[1]), _comp(), _arr()))
    assert change_errors(Change(kind="cut", voice="", sections=[1, 3]), _comp(), _arr())


def test_merge_plays_voice_changes_first_then_structure_from_the_back():
    changes = [Change(kind="repeat", voice="", sections=[1]), Change(kind="softer", voice="sitar", sections=[3]),
               Change(kind="cut", voice="", sections=[3])]
    comp, arr, dropped = merge(changes, _comp(), _arr())
    assert dropped == [] and len(arr.sections) == 3                        # +1 repeat, -1 cut
    clash = [Change(kind="cut", voice="", sections=[2]), Change(kind="repeat", voice="", sections=[2])]
    assert len(merge(clash, _comp(), _arr())[2]) == 1


def test_excerpts_hear_a_cut_shorter_and_a_repeat_longer():
    arr = _arr()                                                          # 8 s per section at 120 bpm
    b, a = excerpts(Change(kind="cut", voice="", sections=[2]), arr, "old", "new")
    assert (b.start, b.end, a.end) == (4.0, 20.0, 12.0)
    b, a = excerpts(Change(kind="repeat", voice="", sections=[2]), arr, "old", "new")
    assert a.end == 28.0


def test_every_prompt_fills_its_placeholders():
    arr, comp = _arr(), _comp()
    m = Member("sitarist", "the sitarist", ("sitar",), "persona")
    texts = [propose_prompt(m, comp, arr, ["guitars softer in section 2"])]
    from crew.rehearsal import Proposal, Round, Tried
    p = Proposal(heard="x", change=Change(kind="softer", voice="guitars", sections=[2]), why="y")
    t = Tried(1, m, p, "v", Clip("a"), Clip("b"))
    from crew.rehearsal import final_prompt
    texts += [react_prompt(m, comp, arr, [t]), rule_prompt(m, comp, arr, Round(1, "song", tried=[t])),
              final_prompt(m, arr, 160.0)]
    for text in texts:
        assert not re.findall(r"\$[a-z_]+", text), re.findall(r"\$[a-z_]+", text)


def test_every_member_hears_the_house_rules():
    m = Member("drummer", "the drummer", ("drums",), "persona")
    assert "drum BUILDUP under the intro is welcome" in propose_prompt(m, _comp(), _arr(), [])


def test_the_bandleader_knows_both_traditions():
    persona = _prompts()["bandleader"]["persona"]
    assert "Hindustani" in persona and "Western" in persona


class _Studio:
    def __init__(self):
        self.rendered = []

    def __call__(self, comp, arr, name):
        self.rendered.append((name, len(arr.sections)))
        return name


def _fake_ears(final: tuple[str, str], asked: list):
    """Round 1: the guitarist asks the guitars to sit out in section 2 (a bad first answer gets one
    repair), the sitarist proposes nothing; the bandleader keeps it. Round 2: nobody proposes.
    The final check answers `final` (before-first order, then after-first)."""
    finals = list(final)

    def ears(clips, gaps, prompt):
        asked.append(prompt)
        assert len(gaps) == len(clips) - 1
        if '"better"' in prompt:
            return json.dumps({"reasoning": "heard both", "better": finals.pop(0)})
        if '"heard"' in prompt:
            if "GUITARIST" in prompt and "ALREADY CHANGED" not in prompt:
                if "could not be used" not in prompt:
                    return json.dumps({"heard": "x", "change": {"kind": "sit_out", "voice": "guitars", "sections": [7]}})
                return json.dumps({"heard": "x", "change": {"kind": "sit_out", "voice": "guitars", "sections": [2]},
                                   "why": "space"})
            return json.dumps({"heard": "fine", "change": None})
        if '"reactions"' in prompt:
            return json.dumps({"reactions": [{"proposal": 1, "support": True, "argument": "yes"}]})
        return json.dumps({"reasoning": "better", "decisions": [{"proposal": 1, "keep": True, "reason": "clearer"}]})
    return ears


def test_a_full_rehearsal_with_fake_ears():
    asked = []
    studio = _Studio()
    result = rehearse(_comp(), _arr(), ears=_fake_ears(("second", "first"), asked), studio=studio)
    assert [len(r.tried) for r in result.rounds] == [1, 0] and result.rounds[0].kept == [1]
    assert result.rounds[1].note == "nobody proposed a change"
    assert any("section 7 does not exist" in p for p in asked)              # the repair named the fault
    assert ("r1_p1_guitarist", 3) in studio.rendered
    assert result.check.rehearsed_wins and result.song == "r1_result"
    assert "drummer" not in {m.key for m in members()} and MAX_ROUNDS == 3


def test_a_split_final_check_keeps_the_song_as_it_came_in():
    result = rehearse(_comp(), _arr(), ears=_fake_ears(("second", "second"), []), studio=_Studio())
    assert not result.check.rehearsed_wins and result.song == "r0_song" == result.start


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
