"""
Tests for the single COMPOSER (crew/composer.py) — all pure, fakes for every LLM.

One musician owns the music: a SEED call co-writes the chart, the main riff and the hook; the
existing generators DEVELOP around it (the main riff slot IS the seed riff, the mukhada / the
song's recurring hook IS the seed hook); the seeds ride the Arrangement so a revise keeps them.
Proven here: the seed guardrail's hard lines, the seeded riff and gat, the song-form hook that
recurs and loops, seeds surviving a revise on both paths, and the flag routing in the Flow.

Runs as a script (`uv run python tests/test_composer.py`) or under pytest.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

import yaml  # noqa: E402

from crew import composer as composer_mod  # noqa: E402
from crew.anchor import (  # noqa: E402
    HOOK_EVENT_KEY,
    RIFF_EVENT_KEY,
    hook_seed_for_riff,
    is_song_hook,
    main_riff_slot,
    render_song_seed,
    riff_seed_for_lead,
    with_realized_seeds,
)
from crew.composer import compose_seed, compose_seeded_voices, seed_arrangement, seed_errors  # noqa: E402
from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    DebateEvent,
    EventType,
    Gat,
    HeadIdea,
    LeadNote,
    LeadPhrase,
    RevisionPlan,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    SongSeed,
    build_arrangement,
)
from crew.lead import _GatContext, _LeadContext, _SeededGat, generate_lead  # noqa: E402
from crew.revision import revise_arrangement  # noqa: E402
from crew.riff import _RiffContext, compose_seeded_riff  # noqa: E402
from crew.generators import section_spans  # noqa: E402
from tests.test_lead import _good_head  # noqa: E402

_BRIEF = CompositionBrief(mood="dark")
_CYCLE = 16.0


def _song_chart(anchor: str = "gat_first") -> ArrangementDraft:
    """A Malkauns SONG: the main riff (with the sitar's hook) returns around a breakdown."""
    main = dict(kind=SectionKind.RIFF, bars=2, layers=["lead", "rhythm", "drums", "drone"],
                foreground="rhythm", riff_slot="main")
    return ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, form="song", anchor=anchor,
        motif=["d", "n", "S", "m"],
        sections=[Section(**main),
                  Section(kind=SectionKind.BREAKDOWN, bars=1, layers=["rhythm", "drums", "drone"],
                          foreground="rhythm", riff_slot="breakdown", form_role="breakdown"),
                  Section(**main)])


def _riff(*cells: tuple[str, float]) -> RiffPattern:
    return RiffPattern(notes=[RiffNote(swara=s, dur=d) for s, d in cells])


def _main_riff() -> RiffPattern:
    """One legal 16-beat cycle: a home Sa with a g-m answer, four times."""
    cell = [("S", 1.0), ("S", 0.5), ("S", 0.5), ("g", 0.5), ("m", 0.5), ("S", 1.0)]
    return _riff(*(cell * 4))


def _seed(**update) -> SongSeed:
    base = SongSeed(reasoning="one idea", energy_arc="build; crush; return heavier",
                    chart=_song_chart(), main_riff=_main_riff(), hook=_good_head())
    return base.model_copy(update=update)


# --- the seed guardrail: the hard lines only ---------------------------------------------

def test_a_good_seed_has_no_hard_faults():
    assert seed_errors(_seed(), _BRIEF) == []


def test_an_illegal_riff_is_rejected_with_its_part_named():
    bad = _main_riff().model_copy(update={"notes": [RiffNote(swara="r", dur=16.0)]})
    errors = seed_errors(_seed(main_riff=bad), _BRIEF)
    assert errors and all("main riff" in e for e in errors) and "illegal" in errors[0]


def test_a_hook_that_fails_a_mukhada_hard_check_is_rejected():
    stub = LeadPhrase(phrase_plan=_good_head().phrase_plan,
                      notes=[LeadNote(swara="S", dur=1.0), LeadNote(swara="m", dur=1.0)])
    errors = seed_errors(_seed(hook=stub), _BRIEF)
    assert errors and all("hook" in e for e in errors)


def test_a_riff_first_hook_must_quote_the_riff():
    # the riff sits on S at every accent; the good head sounds S, m, m -> 1 of 3 quoted
    errors = seed_errors(_seed(chart=_song_chart(anchor="riff_first")), _BRIEF)
    assert any("riff_first" in e for e in errors)


def test_a_fixed_raga_cannot_be_overridden_by_the_chart():
    errors = seed_errors(_seed(), CompositionBrief(mood="dark", raga="bhairav"))
    assert len(errors) == 1 and "FIXED" in errors[0]


def test_compose_seed_carries_the_core_idea_on_the_chart():
    arr, events = compose_seed(_BRIEF, seed_fn=lambda brief: _seed())
    assert arr.seed_riff == _main_riff() and arr.seed_hook == _good_head()
    assert arr.energy_arc and arr.form == "song" and main_riff_slot(arr) == "main"
    assert events[0].agent == "Composer" and events[0].type is EventType.PROPOSE


# --- develop: the seed IS the main riff and the hook ------------------------------------------

def _seeded_song():
    return seed_arrangement(_seed(), _BRIEF)


def test_the_main_slot_plays_the_seed_riff_and_only_other_slots_are_composed():
    arr = _seeded_song()
    calls: list[str] = []

    def others(span, a, memory):
        calls.append(span.section.riff_slot)
        return _riff(("S", 4.0), ("m", 4.0), ("S", 4.0), ("g", 4.0))

    layer, events = compose_seeded_riff(arr, others=others)
    assert calls == ["breakdown"]                        # the main slot made no call
    assert layer is not None and layer.notes
    proposals = [e for e in events if e.type is EventType.PROPOSE]
    assert proposals[0].data["slot"] == "main"


def test_a_section_with_its_own_role_is_never_the_song_hook():
    # the 2026-10-12 song: intro, taan_long and outro on the 'main' slot all replayed the hook
    arr = _seeded_song()
    lead_spans = [s for s in section_spans(arr) if "lead" in s.section.layers]
    for role in ("intro", "taan_long", "tihai", "outro"):
        roled = lead_spans[0].section.model_copy(update={"form_role": role})
        assert not is_song_hook(roled, arr), role


def test_the_song_hook_recurs_and_loops_over_the_main_riff():
    arr = _seeded_song()

    def boom(*args, **kwargs):
        raise AssertionError("no lead section here needs a fresh phrase")

    layers, events = generate_lead(arr, gen_fn=boom)
    assert all(is_song_hook(s.section, arr) for s in section_spans(arr) if "lead" in s.section.layers)
    assert events[0].data[HOOK_EVENT_KEY]                 # the first statement is published
    notes = [n for layer in layers for n in layer.notes]
    first = [n.swara for n in notes if 0 <= n.start < 32]
    last = [n.swara for n in notes if 48 <= n.start < 80]
    assert first and first == last                        # the same hook returns
    bar1 = [n.swara for n in notes if 0 <= n.start < 16]
    bar2 = [n.swara for n in notes if 16 <= n.start < 32]
    assert bar1 == bar2                                   # looped across the section's bars


def test_the_seeded_gat_keeps_the_hook_as_its_mukhada():
    arr = _seeded_song()
    gat_fn = _SeededGat(arr, "composer")
    assert gat_fn(arr, needs_manjha=False, needs_antara=False, needs_amad=False).mukhada == _good_head()
    other = LeadPhrase(phrase_plan=_good_head().phrase_plan, notes=[LeadNote(swara="g", dur=16.0)])
    gat_fn._parts = lambda a, **kw: Gat(mukhada=other, manjha=other)   # the model rewrote the head
    gat = gat_fn(arr, needs_manjha=True, needs_antara=False, needs_amad=False)
    assert gat.mukhada == _good_head() and gat.manjha == other        # the seed wins


def test_compose_seeded_voices_develops_both_voices():
    order: list[str] = []
    lead, rhythm, events = compose_seeded_voices(
        _seeded_song(),
        lead_fn=lambda a: (order.append("lead") or [], []),
        riff_fn=lambda a: (order.append("riff") or None, []))
    assert sorted(order) == ["lead", "riff"]


# --- the seeds survive a revise, on both paths --------------------------------------------------

def _event(**data) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent="x", role="generator", text="x", data=data)


def test_the_realized_seeds_are_stored_once_and_never_overwritten():
    legacy = build_arrangement(_song_chart(), _BRIEF)
    events = [_event(**{HOOK_EVENT_KEY: _good_head().model_dump(exclude_none=True)}),
              _event(**{RIFF_EVENT_KEY: _main_riff().model_dump(exclude_none=True)}),
              DebateEvent(type=EventType.INFO, agent="y", role="generator", text="no data")]
    stored = with_realized_seeds(legacy, events)
    assert stored.seed_hook == _good_head() and stored.seed_riff == _main_riff()
    seeded = _seeded_song()
    assert with_realized_seeds(seeded, [_event(**{HOOK_EVENT_KEY: {"notes": []}})]) is seeded


def test_a_revise_keeps_the_seeds_and_hands_each_voice_its_partner():
    arr = _seeded_song()
    revised = revise_arrangement(arr, RevisionPlan(voice="riff", sections=[0],
                                                   instruction="push harder",
                                                   preserve=["the hook"]))
    assert revised.seed_riff == arr.seed_riff and revised.seed_hook == arr.seed_hook
    assert hook_seed_for_riff(revised) == _good_head()           # gat_first: the riff reduces it
    assert riff_seed_for_lead(revised) is None
    riff_first = revised.model_copy(update={"anchor": "riff_first"})
    assert riff_seed_for_lead(riff_first) == _main_riff() and hook_seed_for_riff(riff_first) is None


# --- every develop prompt carries the seed ------------------------------------------------------

def _placeholders(task: str) -> set[str]:
    tasks = yaml.safe_load(open(os.path.join(os.path.dirname(composer_mod.__file__),
                                             "config", "tasks.yaml")))
    return set(re.findall(r"\{([a-zA-Z_]+)\}", tasks[task]["description"]))


def test_every_develop_prompt_is_shown_the_seed():
    arr = _seeded_song()
    span = section_spans(arr)[0]
    lead_inputs = _LeadContext(arr).inputs_for(span, [])
    gat_inputs = _GatContext(arr).inputs_for(needs_manjha=False, needs_antara=False,
                                             needs_amad=False)
    riff_inputs = _RiffContext(arr).inputs_for(span, [])
    for task, inputs in (("generate_lead", lead_inputs), ("generate_gat", gat_inputs),
                         ("generate_riff", riff_inputs)):
        assert "song_seed" in _placeholders(task) and _placeholders(task) <= set(inputs), task
        assert "DEVELOP it" in inputs["song_seed"]
    assert "no song seed" in render_song_seed(build_arrangement(_song_chart(), _BRIEF))


# --- the flag routes the Flow ------------------------------------------------------------------

def test_the_flag_routes_compose_and_generate_to_the_composer():
    from crew import flow
    original = (composer_mod.compose_seed, composer_mod.compose_seeded_voices,
                os.environ.get("RMA_COMPOSER"), os.environ.get("RMA_RHYTHM_SECTION"))
    seen: list[str] = []
    composer_mod.compose_seed = lambda brief: (seen.append("seed") or _seeded_song(), [])
    composer_mod.compose_seeded_voices = (
        lambda arr, **kw: (seen.append("develop") or [], None, []))
    try:
        os.environ["RMA_COMPOSER"] = "1"
        os.environ["RMA_RHYTHM_SECTION"] = "0"      # the develop path on its own, no rhythm-section call
        arr, _ = flow._compose(_BRIEF)
        flow._creative_voices(arr)
        assert seen == ["seed", "develop"]
    finally:
        composer_mod.compose_seed, composer_mod.compose_seeded_voices = original[:2]
        for key, value in (("RMA_COMPOSER", original[2]), ("RMA_RHYTHM_SECTION", original[3])):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_the_five_agent_path_is_the_default_and_zero_turns_it_off():
    # Sujit, 2026-10-18: the redesigned path (one Composer + the rhythm-section call) is the system
    from crew.config import composer_enabled, rhythm_section_enabled
    saved = {k: os.environ.pop(k, None) for k in ("RMA_COMPOSER", "RMA_RHYTHM_SECTION")}
    try:
        assert composer_enabled() is True and rhythm_section_enabled() is True
        os.environ["RMA_COMPOSER"], os.environ["RMA_RHYTHM_SECTION"] = "0", "off"
        assert composer_enabled() is False and rhythm_section_enabled() is False
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --- Option A: a gat seed writes the head's IDEA; the gat call composes the head ----------------

_GRID = "da da ra dir da dir da ra da da ra dir da dir da ra"      # the Masitkhani line (72 bpm)


def _gat_chart(anchor: str = "gat_first") -> ArrangementDraft:
    """A minimal valid GAT: the mukhada stated, a manjha, the mukhada back (as test_composers)."""
    mukhada = dict(kind=SectionKind.RIFF, bars=4, layers=["lead", "rhythm", "drums", "drone"],
                   foreground="rhythm", riff_slot="main", form_role="mukhada")
    return ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, form="gat", anchor=anchor,
        motif=["d", "n", "S", "m"],
        sections=[Section(**mukhada),
                  Section(kind=SectionKind.MELODY, bars=2, layers=["lead", "drone"],
                          foreground="lead", form_role="manjha"),
                  Section(**mukhada)])


def _idea(**update) -> HeadIdea:
    base = HeadIdea(idea="the vadi falls onto Sa", sam_swara="S", cell=["d", "n", "d"],
                    stroke_line=_GRID)
    return base.model_copy(update=update)


def _gat_seed(**update) -> SongSeed:
    return _seed(chart=_gat_chart(), hook=None, head=_idea()).model_copy(update=update)


def test_a_chikari_in_the_heads_stroke_line_becomes_a_held_matra():
    # fusion_20261012_152048's idea: `da ra dir chikari` x4 — four holes in the head
    idea = HeadIdea(idea="x", sam_swara="S", cell=["S"],
                    stroke_line="da ra dir chikari da ra dir chikari")
    assert idea.stroke_line == ["da", "ra", "dir", "-", "da", "ra", "dir", "-"]


def test_a_gat_seed_writes_the_heads_idea_and_the_chart_carries_it():
    assert seed_errors(_gat_seed(), _BRIEF) == []
    arr = seed_arrangement(_gat_seed(), _BRIEF)
    assert arr.seed_head == _idea() and arr.seed_hook is None    # no head to copy: the gat call writes it


def test_a_gat_seed_without_an_idea_is_asked_for_one():
    errors = seed_errors(_gat_seed(head=None, hook=_good_head()), _BRIEF)
    assert len(errors) == 1 and "write `head`" in errors[0]


def test_a_gat_head_idea_stays_in_the_raga():
    errors = seed_errors(_gat_seed(head=_idea(sam_swara="r", cell=["d", "P"])), _BRIEF)
    assert len(errors) == 1 and "P r not in malkauns" in errors[0]


def test_a_song_seed_still_writes_its_hook():
    errors = seed_errors(_seed(hook=None), _BRIEF)
    assert len(errors) == 1 and "write `hook`" in errors[0]


def test_an_idea_seed_composes_the_lead_first_and_hands_the_riff_the_realized_head():
    arr = seed_arrangement(_gat_seed(), _BRIEF)
    order: list[str] = []
    seen: list = []
    head_event = _event(**{HOOK_EVENT_KEY: _good_head().model_dump(exclude_none=True)})
    compose_seeded_voices(
        arr,
        lead_fn=lambda a: (order.append("lead") or [], [head_event]),
        riff_fn=lambda a: (order.append("riff") or seen.append(hook_seed_for_riff(a)) or None, []))
    assert order == ["lead", "riff"]                # the head exists before the riff reduces it
    assert seen == [_good_head()]                   # gat_first: the riff gets the composed head


def test_the_develop_prompts_read_the_heads_idea():
    block = render_song_seed(seed_arrangement(_gat_seed(), _BRIEF))
    assert "HEAD'S IDEA" in block and "sam swara: S" in block and "core cell: d n d" in block
    assert "da da ra dir" in block


def test_the_composed_head_is_measured_against_the_idea_never_rejected():
    arr = seed_arrangement(_gat_seed(head=_idea(sam_swara="g")), _BRIEF)
    events = generate_lead(arr, gen_fn=lambda *a, **k: _good_head(),
                           gat_fn=lambda a, **kw: Gat(mukhada=_good_head(), manjha=_good_head()))[1]
    notes = [n for e in events for n in (e.data or {}).get("craft_notes", [])]
    assert any("your idea put g on the sam" in n for n in notes)       # the head opens on S
    assert any("stroke_line differs" in n for n in notes)              # _good_head plans none


def test_a_head_that_keeps_its_idea_is_clean():
    from crew.gat_verifier import check_head_idea
    head = _good_head()
    head = head.model_copy(update={"phrase_plan": head.phrase_plan.model_copy(
        update={"stroke_line": _idea().stroke_line})})
    assert check_head_idea(head, _idea()).craft == ()          # opens on S, sounds d n d, same line
    assert check_head_idea(head, None).craft == ()             # no idea, nothing to compare


def test_the_parked_seed_tools_read_an_idea_only_seed():
    from crew.audition import audition_arrangement
    from crew.seed_measures import diversity, measure_seed, render_seed
    m = measure_seed(_gat_seed(), _BRIEF)
    assert m.sam_note == "S" and m.compound_figures == 4 and m.stroke_motif is not None
    assert "head idea: sam S; cell d n d" in render_seed("1", _gat_seed(), _BRIEF)
    assert diversity([_gat_seed(), _gat_seed()])["hook_bols"] == 1.0
    try:
        audition_arrangement(_gat_seed(), _BRIEF)
        raise AssertionError("an idea-only seed has no notes to audition")
    except ValueError as e:
        assert "compose the head" in str(e)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
