"""
Tests for the CHIKARI — the sitar's drone-string strokes (crew/chikari.py): where the planner
places them per section role, the head's pattern returning with the head, the strum across the
raga's strings, the ring, the unbent channel of their own, and the composer's own chikari bols.
No LLM.

Runs as a script (`uv run python tests/test_chikari.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.band import band_layers  # noqa: E402
from crew.chikari import (  # noqa: E402
    MIN_SPACING_BEATS,
    STRUM_MS,
    ChikariStroke,
    chikari_layer,
    chikari_strokes,
    head_right_hand,
    right_hand_rhythm,
    split_sitar_line,
    strum_notes,
    without_chikari,
)
from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    Layer,
    LeadNote,
    LeadPhrase,
    Note,
    PhrasePlan,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.dynamics import _role_gain  # noqa: E402
from crew.generators import VOICES, section_spans  # noqa: E402
from crew.lead import Voicing, _voice_line, lead_layers_from  # noqa: E402
from raga import CHIKARI_STRING_WEIGHTS, SWARAS, chikari_swaras  # noqa: E402
from render import build_midi  # noqa: E402
from soundfont import route_indian  # noqa: E402

_RAGA = "bageshree"
_CYCLE = 16.0
_PLAN = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"], climax_and_sam="sam")
_EPS = 1e-6

# The gat head as a stroke line: one token per matra, "-" where the right hand rests on the
# melody string — those are the matras its chikari may fill.
_HEAD_STROKES = ["da", "ra", "da", "-", "-", "da", "ra", "da", "-", "da", "ra", "da", "da", "-",
                 "da", "chikari"]
_HEAD = [("S", 1, "da"), ("g", 1, "ra"), ("m", 3, "da"), ("D", 1, "da"), ("n", 1, "ra"),
         ("D", 2, "da"), ("m", 1, "da"), ("g", 1, "ra"), ("R", 1, "da"), ("S", 2, "da"),
         ("S", 1, "da"), ("S", 1, "chikari")]
_DASH_MATRAS = {i for i, tok in enumerate(_HEAD_STROKES) if tok == "-"}


def _sec(kind: SectionKind, bars: int, role: str | None,
         layers: tuple[str, ...] = ("lead", "drone", "rhythm")) -> Section:
    return Section(kind=kind, bars=bars, layers=list(layers), foreground="lead", form_role=role)


def _arr(*sections: Section, raga: str = _RAGA) -> Arrangement:
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=72, motif=["S"],
                             sections=list(sections))
    return build_arrangement(draft, CompositionBrief())


def _phrase(*notes: tuple[str, float, str | None], stroke_line: list[str] | None = None) -> LeadPhrase:
    """A phrase from (swara, beats, bol) — swara "-" is a rest."""
    plan = _PLAN.model_copy(update={"stroke_line": stroke_line})
    return LeadPhrase(phrase_plan=plan, notes=[
        LeadNote(swara="S", dur=d, rest=True) if s == "-" else LeadNote(swara=s, dur=d, bol=b)
        for s, d, b in notes])


def _head() -> LeadPhrase:
    return _phrase(*_HEAD, stroke_line=_HEAD_STROKES)


def _gat() -> tuple[Arrangement, list[Layer]]:
    """intro, head x2, manjha, head x2, antara, climax — the sitar's whole form."""
    arr = _arr(_sec(SectionKind.ALAAP, 2, "intro"), _sec(SectionKind.MELODY, 2, "mukhada"),
               _sec(SectionKind.MELODY, 1, "manjha"), _sec(SectionKind.MELODY, 2, "mukhada"),
               _sec(SectionKind.MELODY, 2, "antara"), _sec(SectionKind.TAAN, 2, "taan_long"),
               _sec(SectionKind.OUTRO, 1, "outro"))
    phrases = {
        0: _phrase(("S", 2, None), ("n", 1, None), ("D", 2, None), ("-", 4, None),
                   ("m", 2, None), ("g", 2, None), ("-", 3, None), ("m", 1, None),
                   ("D", 2, None), ("S", 3, None)),
        1: _head(), 3: _head(),
        2: _phrase(("D", 2, None), ("n", 2, None), ("S", 4, None)),
        4: _phrase(*[("m", 1, None), ("D", 1, None), ("S", 2, None), ("-", 2, None)] * 5),
        5: _phrase(*[("S", 0.5, None), ("R", 0.5, None), ("g", 0.5, None), ("m", 0.5, None)] * 6,
                   ("D", 2, None), ("-", 2, None),
                   *[("m", 0.5, None), ("D", 0.5, None), ("n", 0.5, None), ("D", 0.5, None)] * 3,
                   ("S", 3, None), ("-", 1, None), ("m", 2, None), ("-", 2, None)),
        6: _phrase(("D", 2, None), ("m", 2, None), ("g", 2, None), ("S", 8, None)),
    }
    return arr, lead_layers_from(phrases, arr)


def _in_section(strokes: list[ChikariStroke], arr: Arrangement, index: int) -> list[ChikariStroke]:
    span = section_spans(arr)[index]
    return [s for s in strokes if span.start - _EPS <= s.start < span.end - _EPS]


def _per_bar(strokes: list[ChikariStroke], arr: Arrangement, index: int) -> list[list[float]]:
    span = section_spans(arr)[index]
    return [[round(s.start - span.start - bar * _CYCLE, 4) for s in strokes
             if span.start + bar * _CYCLE - _EPS <= s.start < span.start + (bar + 1) * _CYCLE - _EPS]
            for bar in range(span.section.bars)]


# --- the composer's own chikari ------------------------------------------------------------

def test_a_written_chikari_is_marked_and_lifted_off_the_melody():
    arr, lead = _gat()
    melody, written = split_sitar_line(lead)
    head_sam = section_spans(arr)[1].start
    assert any(abs(n.start - (head_sam + 15)) < _EPS for n in written)   # the head's own chikari
    assert all(n.swara == "S" for n in written)
    lifted = without_chikari(lead)
    assert not any(n.chikari for ly in lifted for n in ly.notes or [])
    assert sum(len(ly.notes or []) for ly in lifted) == sum(len(ly.notes or []) for ly in lead) \
        - len(written)
    strokes = chikari_strokes(arr, lead)
    assert {round(n.start, 4) for n in written} <= {round(s.start, 4) for s in strokes if s.written}


def test_the_lead_guitar_never_plays_a_chikari():
    line = [Note(swara="m", start=0, dur=1), Note(swara="g", start=1, dur=1),
            Note(swara="S", oct=1, start=2, dur=0.5, chikari=True), Note(swara="D", start=2.5, dur=1)]
    for voicing in Voicing:
        sitar, guitar = _voice_line(line, voicing, _RAGA)
        assert not any(abs(n.start - 2.0) < _EPS for n in guitar), voicing
    sitar, _ = _voice_line(line, Voicing.SITAR, _RAGA)
    assert any(n.chikari for n in sitar)                     # the sitar keeps it, to lift later


# --- how a stroke sounds ---------------------------------------------------------------------

def test_each_stroke_is_a_fast_strum_across_the_raga_strings():
    arr, _ = _gat()
    notes = strum_notes([ChikariStroke(8.0, 80, 1600.0, written=True)], arr)
    assert [n.swara for n in notes] == chikari_swaras(_RAGA)          # guruji's S S D m
    pitches = [SWARAS[n.swara] + 12 * n.oct for n in notes]
    assert len(set(pitches)) == len(pitches)                          # no unison pair on one channel
    assert max(pitches) == pitches[0]                                 # string 1: the high Sa
    sweep = (notes[-1].start - notes[0].start) * 60000.0 / arr.bpm
    assert abs(sweep - STRUM_MS * (len(notes) - 1)) < 1.0 and sweep < 30.0   # one stroke, not an arpeggio
    assert notes[0].start == 8.0 and all(a.start < b.start for a, b in zip(notes, notes[1:]))
    assert [n.vel for n in notes] == [round(80 * w) for w in CHIKARI_STRING_WEIGHTS]
    assert notes[0].vel > notes[1].vel > notes[-1].vel                # string 1 a touch strongest


def test_a_planned_stroke_is_the_sa_pair_not_a_wash():
    # GPT, 2026-10-12: four strings on every stroke read as "a resonance wash"
    from crew.chikari import PLANNED_STRINGS
    arr, _ = _gat()
    notes = strum_notes([ChikariStroke(8.0, 80, 1600.0, written=False)], arr)
    assert len(notes) == PLANNED_STRINGS == 2
    assert [n.swara for n in notes] == ["S", "S"] and notes[0].oct == notes[1].oct + 1


def test_a_string_rings_until_the_next_stroke_or_its_cap():
    arr, _ = _gat()
    notes = strum_notes([ChikariStroke(0.0, 80, 1600.0, written=False),
                         ChikariStroke(1.0, 80, 1600.0, written=False)], arr)
    half = len(notes) // 2
    first, last = notes[:half], notes[half:]
    assert all(abs(n.dur - 1.0) < 1e-3 for n in first)               # re-struck: rings to the stroke
    cap = 1600.0 * arr.bpm / 60000.0
    assert all(abs(n.dur - cap) < 1e-3 for n in last)                 # left alone: rings to its cap
    for a, b in zip(first, last):                                     # same string never overlaps itself
        assert a.start + a.dur <= b.start + _EPS


def test_the_chikari_has_its_own_channel_and_is_never_bent():
    import mido
    arr, _ = _gat()
    sitar = VOICES["sitar"]
    chikari = Layer(role="chikari", instrument="sitar", program=104,
                    channel=VOICES["chikari"].channel, pan=44,
                    notes=strum_notes([ChikariStroke(0.5, 80, 1600.0, False),
                                       ChikariStroke(4.0, 80, 1600.0, True)], arr))
    lead = {"role": "lead", "instrument": "sitar", "program": 104, "channel": sitar.channel,
            "notes": [{"swara": "m", "oct": 0, "start": 0.0, "dur": 2.0, "vel": 100,
                       "meend_swara": "g"},
                      {"swara": "g", "oct": 0, "start": 2.0, "dur": 6.0, "vel": 100,
                       "andolan": True, "andolan_st": 1.0}]}
    comp = {"raga": _RAGA, "sa": 62, "bpm": 60, "tala": {"name": "teentaal", "beats_per_bar": 16},
            "layers": [lead, chikari.model_dump(exclude_none=True)]}
    path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "rma_test_chikari.mid")
    build_midi(comp, path)
    msgs = [m for t in mido.MidiFile(path).tracks for m in t]
    os.remove(path)
    ch = VOICES["chikari"].channel
    assert ch != sitar.channel
    assert any(m.type == "pitchwheel" and m.channel == sitar.channel for m in msgs)  # the sitar bends
    assert not any(m.type == "pitchwheel" and m.channel == ch for m in msgs)         # its strings never
    on = [m for m in msgs if m.type == "note_on" and m.velocity > 0]
    # a planned stroke strums the Sa pair, a written one all four, plus the taraf's g, sharing
    assert sum(m.channel == ch for m in on) == 2 + 4 + 1
    assert {m.channel for m in on} == {sitar.channel, ch}                            # no third channel


def test_the_chikari_takes_the_sitars_own_timbre():
    layer = chikari_layer(*_gat()).model_dump(exclude_none=True)
    octaves = [n["oct"] for n in layer["notes"]]
    route_indian([layer], sa=62, indian_present=True)                 # the Indian Ensemble sitar
    assert layer["bank"] is not None and layer["program"] == 2
    assert [n["oct"] for n in layer["notes"]] == [o + 1 for o in octaves]   # its octave fix too


# --- where the planner puts them ------------------------------------------------------------

def test_a_planned_stroke_never_lands_on_a_melody_stroke():
    arr, lead = _gat()
    melody, _ = split_sitar_line(lead)
    onsets = [n.start for n in melody]
    for s in chikari_strokes(arr, lead):
        if s.written:
            continue
        # an EMPTY matra: the melody string is not struck anywhere in it
        assert not any(s.start - _EPS <= t < s.start + 1 - _EPS for t in onsets), s
    spaced = sorted(s.start for s in chikari_strokes(arr, lead) if not s.written)
    assert all(b - a >= MIN_SPACING_BEATS - _EPS for a, b in zip(spaced, spaced[1:]))


def test_the_alap_punctuates_phrase_endings_sparsely():
    arr, lead = _gat()
    melody, _ = split_sitar_line(lead)
    strokes = _in_section(chikari_strokes(arr, lead), arr, 0)
    assert strokes and all(len(bar) <= 1 for bar in _per_bar(strokes, arr, 0))
    ends = [n.start + n.dur for n in melody]
    for s in strokes:
        assert not any(n.start <= s.start < n.start + n.dur for n in melody)   # in a silence...
        assert any(0 < s.start - e <= 2.0 + _EPS for e in ends)                # ...a breath after a phrase
    # the first avartan breathes twice (after "S n D" and after "m g") but is punctuated once
    silences = [b.start - (a.start + a.dur) for a, b in zip(melody, melody[1:])
                if a.start + a.dur < _CYCLE]
    assert sum(gap >= 2.0 for gap in silences) == 2
    assert len(_per_bar(strokes, arr, 0)[0]) == 1                              # not every rest


def test_the_head_brings_the_same_chikari_back_every_time():
    arr, lead = _gat()
    strokes = chikari_strokes(arr, lead)
    bars = _per_bar(strokes, arr, 1) + _per_bar(strokes, arr, 3)
    assert len(bars) == 4 and bars[0]                      # four statements, each with chikari
    assert all(bar == bars[0] for bar in bars)             # ...and the SAME chikari every time


def test_a_taan_fill_only_silences_the_heads_chikari_it_covers():
    arr = _arr(_sec(SectionKind.MELODY, 4, "mukhada"))
    fill = _phrase(*[(sw, 0.25, None) for sw in "SRgmDnDmgRSn" * 4])   # sixteenths from the sam
    lead = lead_layers_from({0: _head()}, arr, fills=[fill])
    bars = _per_bar(chikari_strokes(arr, lead), arr, 0)
    pattern = bars[0]
    assert pattern and bars[-1] == pattern                 # the plain statements carry it whole
    cut = [bar for bar in bars[1:-1] if bar != pattern]
    assert cut                                             # the fill took the front of a statement...
    assert all(set(bar) < set(pattern) for bar in cut)     # ...and only REMOVED strokes it covered


def test_the_heads_chikari_fills_the_empty_strokes_of_its_stroke_line():
    arr, lead = _gat()
    strokes = [s for s in _in_section(chikari_strokes(arr, lead), arr, 1) if not s.written]
    sam = section_spans(arr)[1].start
    offsets = {round((s.start - sam) % _CYCLE) for s in strokes}
    assert offsets and offsets <= _DASH_MATRAS             # only where the right hand rests


def test_a_light_section_stays_light_and_the_climax_is_busier_but_selective():
    arr, lead = _gat()
    strokes = chikari_strokes(arr, lead)
    for index in (2, 4, 6):                                # manjha, antara, outro
        assert all(len(bar) <= 1 for bar in _per_bar(strokes, arr, index)), index
    climax = _per_bar(strokes, arr, 5)
    assert max(len(bar) for bar in climax) == 2           # a little more active...
    assert sum(len(bar) for bar in climax) < 2 * _CYCLE / 4   # ...nowhere near a stroke a beat


def test_a_written_chikari_counts_toward_the_cap():
    arr = _arr(_sec(SectionKind.MELODY, 1, "antara"))
    plain = _phrase(("m", 2, None), ("-", 2, None), ("D", 2, None), ("-", 2, None),
                    ("S", 4, None), ("-", 4, None))
    with_bol = _phrase(("m", 2, None), ("-", 2, None), ("D", 2, None), ("-", 2, None),
                       ("S", 4, None), ("S", 0.5, "chikari"), ("-", 3.5, None))
    planned = chikari_strokes(arr, lead_layers_from({0: plain}, arr))
    written = chikari_strokes(arr, lead_layers_from({0: with_bol}, arr))
    assert len(planned) == 1 and not planned[0].written
    assert len(written) == 1 and written[0].written       # the composer's stroke IS the one


def test_no_sitar_no_chikari():
    os.environ["RMA_LEAD_GUITAR"] = "1"                     # a guitar solo needs the lead guitar
    try:
        _no_sitar_no_chikari()
    finally:
        os.environ.pop("RMA_LEAD_GUITAR", None)


def _no_sitar_no_chikari():
    arr = _arr(_sec(SectionKind.SOLO, 1, None))            # a guitar solo: the sitar lays out
    lead = lead_layers_from({0: _phrase(("m", 2, None), ("-", 2, None), ("S", 1, "chikari"),
                                        ("D", 4, None))}, arr)
    assert chikari_layer(arr, lead) is None
    assert not any(n.chikari for ly in lead for n in ly.notes or [])


# --- wiring + the combined right hand --------------------------------------------------------

def test_the_band_carries_the_chikari_beside_the_sitar():
    arr, lead = _gat()
    layers = band_layers(arr, lead, None)
    roles = [ly.role for ly in layers]
    assert roles.count("chikari") == 1 and roles.index("chikari") > roles.index("lead")
    layer = layers[roles.index("chikari")]
    assert layer.channel == VOICES["chikari"].channel and layer.instrument == "sitar"
    assert not any(n.chikari for ly in layers if ly.role == "lead" for n in ly.notes or [])


def test_the_chikari_rises_and_falls_with_the_sitar():
    for role in ("mukhada", "antara", "taan_long"):
        section = _sec(SectionKind.MELODY, 1, role)
        assert _role_gain("chikari", section) == _role_gain("lead", section)


def test_the_right_hand_merges_melody_and_chikari_strokes():
    arr, lead = _gat()
    hand = right_hand_rhythm(arr, lead, 1)
    assert [s.beat for s in hand] == sorted(s.beat for s in hand)
    assert {s.kind for s in hand} == {"melody", "chikari"}
    chikari_beats = {s.beat for s in hand if s.kind == "chikari"}
    sam = section_spans(arr)[1].start
    assert chikari_beats == {round(s.start - sam, 4)
                             for s in _in_section(chikari_strokes(arr, lead), arr, 1)}
    head = head_right_hand(arr, lead)
    assert head and all(0 <= s.beat < _CYCLE for s in head)
    assert [(s.beat, s.kind) for s in head] == [(s.beat, s.kind) for s in hand
                                                if s.beat < _CYCLE]   # one avartan of the head


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
