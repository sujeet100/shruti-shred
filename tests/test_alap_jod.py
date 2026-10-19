"""Pure tests for THE ALAP, THEN A JOD (2026-10-19, Sujit's "ours is more of an intro than an alap" +
ALAP_RESEARCH.md): code names the beat where the jod enters, the prompt, the checker and the
Producer's report all read it, the pulse rules hold only from there, the unmetred alap is measured
in seconds, and the head is prepared rather than quoted. No API."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_lead as T  # noqa: E402
from crew.alap_report import alap_facts, render_alap  # noqa: E402
from crew.contracts import Composition, Gat, LeadNote, LeadPhrase, SectionKind  # noqa: E402
from crew.gat_verifier import check_intro  # noqa: E402
from crew.generators import SectionSpan, section_spans  # noqa: E402
from crew.lead import _intro_job, _render_room, generate_lead, intro_jod_at, intro_phrase_grid  # noqa: E402


def _arr():
    return T._gat_arr((SectionKind.ALAAP, 2, "intro"), (SectionKind.ALAAP, 1, "mukhada"))


def _verify(cell: LeadPhrase, head: LeadPhrase | None = None):
    arr = _arr()
    _, _, verify = _intro_job(section_spans(arr)[0], arr, [], None, head or T._good_head())
    return verify(cell)


def _window(arr, length: float) -> SectionSpan:
    return SectionSpan(index=0, section=arr.sections[0], start=0.0, end=length)


def _with_jod(*jod: LeadNote) -> LeadPhrase:
    """The fixture's four alap phrases (to beat 20) followed by this jod."""
    return LeadPhrase(phrase_plan=T._good_intro().phrase_plan, notes=T._good_intro().notes[:15] + list(jod))


def test_the_jod_enters_on_a_vibhag_about_three_quarters_through():
    arr = _arr()
    assert intro_jod_at(arr, _window(arr, 29.0)) == 20.0         # a 2-avartan intro at 72 bpm
    assert intro_jod_at(arr, _window(arr, 59.0)) == 44.0         # ~15 beats of jod, under an avartan
    assert intro_jod_at(arr, _window(arr, 120.0)) == 104.0       # never longer than one avartan
    assert intro_jod_at(arr, _window(arr, 6.0)) is None          # too short for both: all alap


def test_the_fixture_alap_then_jod_is_clean():
    checks = _verify(T._good_intro())
    assert checks.hard == ()
    assert not any("held" in c or "frontier" in c or "head's" in c for c in checks.craft)


def test_a_jod_that_misses_its_beat_is_rejected():
    late = _with_jod(LeadNote(swara="S", dur=0.5, rest=True), LeadNote(swara="n", dur=1.0),
                     LeadNote(swara="d", dur=1.0), LeadNote(swara="m", dur=1.0),
                     LeadNote(swara="g", dur=1.0), LeadNote(swara="S", dur=2.0))
    assert any("no note starts on beat 20" in h for h in _verify(late).hard)


def test_the_pulse_holds_only_in_the_jod():
    arr, cell = _arr(), T._good_intro()
    grid = intro_phrase_grid(arr, 0.0, 31.0)
    jod = check_intro(cell, window_beats=31.0, raga="malkauns", phrase_grid=grid, jod_at=20.0, bpm=72)
    whole = check_intro(cell, window_beats=31.0, raga="malkauns", phrase_grid=grid, bpm=72)
    assert jod.hard == ()                                        # the alap's m at 11.5 is free
    assert any("start between beats" in h for h in whole.hard)    # as a jod, it would be off the beat


def test_a_busy_alap_is_noted_in_seconds_not_beats():
    busy = LeadPhrase(phrase_plan=T._good_intro().phrase_plan, notes=[
        LeadNote(swara=sw, dur=1.0) for sw in ("S", "n", "S", "g", "m", "g")] + [LeadNote(swara="S", dur=2.0)])
    fast = check_intro(busy, window_beats=16.0, raga="malkauns", bpm=120).craft   # a beat = 0.5 s
    slow = check_intro(busy, window_beats=16.0, raga="malkauns", bpm=30).craft    # a beat = 2 s
    assert any("held 1 s" in c for c in fast)
    assert not any("held 1 s" in c for c in slow)


def test_an_alap_that_opens_the_range_all_at_once_is_noted():
    cell = LeadPhrase(phrase_plan=T._good_intro().phrase_plan, notes=[
        LeadNote(swara="S", dur=3.0), LeadNote(swara="S", dur=1.5, rest=True),
        LeadNote(swara="g", dur=0.5), LeadNote(swara="m", dur=0.5), LeadNote(swara="d", dur=3.0),
        LeadNote(swara="S", dur=1.5, rest=True), LeadNote(swara="S", dur=3.0)])
    craft = check_intro(cell, window_beats=16.0, raga="malkauns", bpm=60).craft
    assert any("opens 3 new swaras at once" in c for c in craft)


def test_the_alap_must_rest_on_the_heads_first_swara_near_the_close():
    head = LeadPhrase(phrase_plan=T._plan("g"), notes=[LeadNote(swara="g", dur=4.0, bol="da")]
                      + T._good_head().notes[1:])
    assert any("never rest on g" in c for c in _verify(T._good_intro(), head=head).craft)


def test_the_length_line_names_the_jod_beat_and_the_holds_in_seconds():
    arr = _arr()
    gen = _intro_job(section_spans(arr)[0], arr, [], None, None)[0]
    line = _render_room(gen, arr)
    assert "THE JOD enters exactly ON beat 20" in line
    assert "2-4 s is 2.5-5 beats" in line                        # at 72 bpm a beat is 0.83 s


def test_the_producer_reads_the_alap_and_its_jod():
    arr = _arr()
    fn, _ = T._fake([T._good_intro()])
    gfn, _ = T._fake_gat(Gat(mukhada=T._good_head()))
    layers, _ = generate_lead(arr, gen_fn=fn, gat_fn=gfn)
    comp = Composition(raga=arr.raga, sa=arr.sa, bpm=arr.bpm,
                       tala={"name": arr.tala, "beats_per_bar": arr.beats_per_bar}, layers=layers)
    facts = alap_facts(comp, arr)
    assert facts is not None and facts.phrases == 4 and facts.held_share > 0.5
    assert facts.jod_s is not None and facts.rests_on_head and not facts.quotes_head
    assert "THE ALAP" in render_alap(comp, arr)


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
