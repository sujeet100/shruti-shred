"""Pure tests for the notes debate (`crew/notes_debate.py`, the live wiring's prompts). No API."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crew.contracts import (ArrangementDraft, CompositionBrief, LeadNote, LeadPhrase, PhrasePlan,  # noqa: E402
                            RhythmSection, RiffNote, Section, SectionKind, SectionPart, build_arrangement)
from crew.notes_debate import (Critique, Players, RiffRevision, RiffRewrite, SitarRevision, SitarRewrite,  # noqa: E402
                               Song, apply_sitar, notes_debate, part_sections, render_piece, riff_errors,
                               sitar_errors)


def _phrase(*tokens: str) -> LeadPhrase:
    notes = []
    for t in tokens:
        swara, _, dur = t.partition(":")
        notes.append(LeadNote(swara=swara, dur=float(dur or 1), bol="da"))
    plan = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"], climax_and_sam="Sa")
    return LeadPhrase(phrase_plan=plan, notes=notes)


HEAD = _phrase("S:2", "R", "g:2", "m", "R:2", "S", "n", "P:2", "m", "g:2", "R")
MANJHA = _phrase("m", "g:2", "R", "S:2", "n", "S:9")


def _song() -> Song:
    roles = ("mukhada", "manjha", "mukhada")
    sections = [Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "rhythm", "drums", "drone"],
                        foreground="lead", form_role=r) for r in roles]
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=120, motif=["S"], sections=sections)
    arr = build_arrangement(draft, CompositionBrief(request="slow doom Darbari"))
    chug = [RiffNote(swara="S", dur=1.0, technique="palm_mute") for _ in range(16)]
    rs = RhythmSection(parts=[SectionPart(section=0, guitar=[chug]), SectionPart(section=1, guitar=[chug]),
                              SectionPart(section=2, same_as=0)])
    return Song(arr.model_copy(update={"rhythm_section": rs}), {0: HEAD, 1: MANJHA, 2: HEAD})


def test_a_head_rewrite_plays_at_every_mukhada():
    song = _song()
    new = _phrase("S:2", "R", "g:2", "m", "R:2", "S", "n", "d:2", "n", "S:2", "R")
    after = apply_sitar(song, "head", new)
    assert part_sections(song.arr, "head") == [0, 2] and after.phrases[0] is new and after.phrases[2] is new
    assert after.phrases[1] is MANJHA


def test_a_sitar_rewrite_must_match_the_length_and_keep_the_heads_first_note():
    song = _song()
    short = sitar_errors(song, "manjha", _phrase("m", "g", "R", "S:2"))
    assert any("fills 5 beats" in e for e in short)
    moved = sitar_errors(song, "head", _phrase("R:2", "R", "g:2", "m", "R:2", "S", "n", "P:2", "m", "g:2", "R"))
    assert any("keep the head's first note" in e for e in moved)
    assert sitar_errors(song, "antara", MANJHA) == ["this song has no antara"]


def test_a_riff_rewrite_is_parsed_and_checked():
    song = _song()
    _, errors = riff_errors(song, 2, ["S[16]"])
    assert errors and "no riff of its own" in errors[0]                     # 2 replays section 0
    assert riff_errors(song, 0, ["S[8]", "S[8]"])[1][0].startswith("section 0's riff has 1 cycle")
    assert "cycle 1" in riff_errors(song, 0, ["X[16]"])[1][0]
    cycles, errors = riff_errors(song, 0, ["S[2] S[1]pm S[1]pm " * 4])
    assert len(cycles) == 1 and len(cycles[0]) == 12, errors


def test_the_piece_shows_repeats_as_references():
    text = render_piece(_song())
    assert "SECTION 2 — mukhada" in text and "the same phrase as section 0" in text
    assert "the same riff as section 0" in text and "guitar cycle 1: S[1]pm" in text


def _players(sitar_decision: str, riff_decision: str, seen: list) -> Players:
    new_head = _phrase("S:2", "R", "g:2", "m", "R:2", "S", "n", "d:2", "n", "S:2", "R")
    revised = _phrase("S:2", "R", "g:2", "m", "g:2", "m", "R", "S:2", "n", "S")

    def critique(critic, piece, rewrite):
        seen.append((critic, rewrite))
        return Critique(argument="the landing is weak", verdict="oppose", suggestion="end on Re")
    return Players(
        propose_sitar=lambda piece: SitarRewrite(why="the head ends limp", part="head", phrase=new_head),
        propose_riff=lambda piece: RiffRewrite(why="more drive", section=1, cycles=["S[2] S[1]pm S[1]pm " * 4]),
        critique=critique,
        revise_sitar=lambda piece, rewrite, said: SitarRevision(response="fair", decision=sitar_decision,
                                                                phrase=revised if sitar_decision == "revise" else None),
        revise_riff=lambda piece, rewrite, said: RiffRevision(response="no", decision=riff_decision))


def test_the_debate_builds_every_version_and_honours_each_decision():
    seen, built = [], []
    d = notes_debate(_song(), _players("revise", "withdraw", seen), lambda s, name: built.append(name) or name)
    assert [c for c, _ in seen] == ["guitarist", "sitarist"]               # each critiques the OTHER's part
    assert "now:" in seen[0][1] and "proposed:" in seen[0][1]
    assert d.final_sitar is not None and d.final_sitar.notes[4].swara == "g"    # the revision stands
    assert d.final_riff is None                                                 # withdrawn
    assert built == ["original", "sitar_proposed", "riff_proposed", "sitar_final"]


def test_a_dead_call_is_noted_and_the_debate_goes_on():
    def dead(piece):
        raise ConnectionError("503")
    p = _players("keep", "keep", [])
    p = Players(dead, p.propose_riff, p.critique, p.revise_sitar, p.revise_riff)
    d = notes_debate(_song(), p, lambda s, name: name)
    assert d.sitar is None and d.final_riff is not None and "both_final" not in d.versions
    assert any("sitarist's proposal failed" in n for n in d.notes)


def test_settle_keeps_only_the_rewrites_that_win_the_blind_comparison():
    from crew.contracts import Composition
    from crew.notes_debate import settle
    song = _song()
    d = notes_debate(song, _players("revise", "keep", []), lambda s, name: name)
    original = Composition(raga="original", bpm=120, tala={"name": "teentaal", "beats_per_bar": 16}, layers=[])
    built = []

    def assemble(s):
        built.append(s)
        return original.model_copy(update={"raga": f"v{len(built)}"})

    def compare(draft, revision, arr):                     # the riff rewrite wins, the head does not
        return revision.raga == "v2", []
    settled = settle(song, d, original, assemble, compare)
    assert settled.kept == {"sitar": False, "riff": True}
    assert settled.song.phrases[0] is HEAD                                   # head untouched
    assert settled.song.arr.rhythm_section.parts[1].guitar != song.arr.rhythm_section.parts[1].guitar
    assert "the riff rewrite kept" in settled.events[-1].text

    def broken(draft, revision, arr):
        raise TimeoutError("judge down")
    assert settle(song, d, original, assemble, broken).composition is original   # the accepted song stands


def test_every_prompt_is_filled():
    import yaml
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / "crew/config/notes_debate.yaml").read_text())
    from crew.notes_debate_crew import _inputs
    provided = set(_inputs(_song(), "piece")) | {"critic", "rewrite", "critique"}
    for key, task in config["tasks"].items():
        text = task["description"].replace("{common}", config["common"])
        missing = set(re.findall(r"\{(\w+)\}", text)) - provided
        assert not missing, (key, missing)


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
