"""
Tests for the riff VOICING pass — every bare stroke becomes a power chord, inside the raga.
All pure (no key, no cost).

The evidence (talk/HANDOVER.md §2-3): the best riff of the A/B/C experiment chorded every
stroke, ours chorded 15%; and the conventional power chord on Bhairav's Pa or komal dha needs a
fifth the raga forbids, so a fourth (the inverted power chord) stands in. Proven here: the
table for Bhairav, legality for every raga, the direction and andolan skips, the model's own
colour chords kept, gestures and rests untouched, and the shared generation boundary voicing
the take BEFORE it is verified.

Runs as a script (`uv run python tests/test_riff_voicing.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.riff import voiced_and_verified  # noqa: E402
from crew.riff_voicing import (  # noqa: E402
    StrokeRole,
    home_root,
    power_voicing,
    render_power_roots,
    strip_meaningless_legato,
    voice_note,
    voice_riff,
)
from raga import RAGAS, SWARAS, directional_varjya  # noqa: E402


def _n(swara: str, dur: float = 0.5, **kw) -> RiffNote:
    return RiffNote(swara=swara, dur=dur, **kw)


def test_bhairav_takes_the_fifth_where_legal_and_the_fourth_where_not():
    # Sa=E: E5, F5, and the two roots whose fifth Bhairav forbids (F#, G) take the fourth
    assert power_voicing("S", 0.5, "bhairav") == ["P", "S"]      # E + B + E
    assert power_voicing("r", 0.5, "bhairav") == ["d", "r"]      # F + C + F
    assert power_voicing("P", 0.5, "bhairav") == ["S", "P"]      # B + E (fourth) + B
    assert power_voicing("d", 0.5, "bhairav") == ["r", "d"]      # C + F (fourth) + C


def test_every_voicing_is_legal_in_every_raga_and_role():
    for raga, facts in RAGAS.items():
        allowed = set(facts["allowed"])
        one_way = directional_varjya(raga)
        for root in allowed:
            for dur in (0.5, 2.0):
                for role in StrokeRole:
                    chord = power_voicing(root, dur, raga, role)
                    assert set(chord) <= allowed, (raga, root, role, chord)
                    dyad = [t for t in chord if t != root]
                    if role not in (StrokeRole.ACCENT, StrokeRole.SUSTAINED):
                        assert not set(dyad) & set(one_way), (raga, root, role, chord)
                    for tone in dyad:                            # only a fifth or a fourth
                        assert (SWARAS[tone] - SWARAS[root]) % 12 in (5, 7), (raga, root, tone)
                    if role is StrokeRole.CHUG and dyad:         # a chug never takes the fourth
                        assert (SWARAS[dyad[0]] - SWARAS[root]) % 12 == 7, (raga, root, chord)


def test_bageshree_sa_takes_ma_never_the_descent_only_pa():
    assert power_voicing("S", 0.5, "bageshree") == ["m", "S"]


def test_an_andolan_swara_is_never_held_under_the_sitar():
    # Bhairav's komal re over a SHORT stroke takes komal dha; on a held stroke dha is the
    # andolan swara, and re has no other legal dyad, so it plays root + octave alone
    assert power_voicing("r", 0.5, "bhairav") == ["d", "r"]
    assert power_voicing("r", 2.0, "bhairav") == ["r"]


def test_a_bare_stroke_and_a_bare_octave_are_voiced():
    assert voice_note(_n("S"), "bhairav").chord == ["P", "S"]
    assert voice_note(_n("S", chord=["S"]), "bhairav").chord == ["P", "S"]


def test_the_models_colour_chord_is_kept():
    colour = _n("S", chord=["G", "N"])
    assert voice_note(colour, "bhairav") is colour


def test_gestures_and_rests_stay_single():
    for note in (_n("S", technique="slide"), _n("S", technique="bend"),
                 _n("S", technique="hammer_on"), _n("S", 1.0, rest=True)):
        assert voice_note(note, "bhairav") is note


def test_palm_muted_chugs_become_muted_power_chords():
    chug = voice_note(_n("S", technique="palm_mute"), "bhairav")
    assert chug.chord == ["P", "S"] and chug.technique == "palm_mute"


def test_todis_pa_completes_sa_only_on_accents_and_sustained_chords():
    # the GPT review's "allow Sa–Pa selectively": Todi's Pa is one-direction, so a chug or a
    # passing stroke keeps the octave and Pa joins only where the chord must carry weight
    assert power_voicing("S", 0.5, "todi", StrokeRole.CHUG) == ["S"]
    assert power_voicing("S", 0.5, "todi", StrokeRole.MOVE) == ["S"]
    assert power_voicing("S", 0.5, "todi", StrokeRole.ACCENT) == ["P", "S"]
    assert power_voicing("S", 2.0, "todi", StrokeRole.SUSTAINED) == ["P", "S"]


def test_a_chug_without_a_legal_fifth_takes_the_octave():
    # Bageshree's Sa has no free fifth: its chugs ring the octave; Sa–Ma (its idiomatic dyad)
    # is kept for accents and sustained chords — the descent-only Pa is never reached
    assert power_voicing("S", 0.5, "bageshree", StrokeRole.CHUG) == ["S"]
    assert power_voicing("S", 0.5, "bageshree", StrokeRole.ACCENT) == ["m", "S"]


def test_a_stroke_on_the_sam_or_a_tali_is_an_accent():
    # Todi, 8-beat cycle: the sam (beat 0) and a tali (beat 4) voice as accents (Sa takes Pa),
    # the chugs between them keep the octave
    chug = RiffNote(swara="S", dur=0.5, technique="palm_mute")
    pattern = RiffPattern(notes=[chug] * 16)
    voiced = voice_riff(pattern, "todi", frozenset({0.0, 4.0}))
    chords = [n.chord for n in voiced.notes]
    assert chords[0] == ["P", "S"] and chords[8] == ["P", "S"]
    assert all(c == ["S"] for i, c in enumerate(chords) if i not in (0, 8))


def test_the_home_root_is_sa_unless_the_ragas_sa_is_weak():
    # Sa is a CORE resting note in every raga on the menu except Marwa, whose core rests are
    # komal re and Dha — and Dha carries a full fifth, so Marwa's riff homes on Dha
    assert {r: home_root(r) for r in RAGAS if home_root(r) != "S"} == {"marwa": "D"}


def test_the_power_root_map_tells_the_composer_which_roots_hit_hardest():
    marwa = render_power_roots("marwa")
    assert "root + fifth): G M D N" in marwa and "octave only: S" in marwa


def test_voicing_is_idempotent():
    pattern = RiffPattern(notes=[_n("S"), _n("r"), _n("P", 1.0), _n("S", 1.0, rest=True)])
    once = voice_riff(pattern, "bhairav")
    assert voice_riff(once, "bhairav") is once


def test_the_generation_boundary_verifies_the_VOICED_take():
    """Both composition roots share `voiced_and_verified`: the take is voiced before the hard
    checks and the playability budget see it, so they judge the chords that will sound."""
    section = Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                      foreground="rhythm", form_role="mukhada")
    draft = ArrangementDraft(raga="bhairav", subgenre="heavy", tala="teentaal", bpm=128,
                             motif=["S", "r", "G", "m"], sections=[section])
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    bare = RiffPattern(notes=[_n("S", 1.0), _n("r", 1.0)] * 8)
    out = voiced_and_verified(lambda feedback: bare, arr.sections[0], arr)
    assert all(n.chord for n in out.notes if not n.rest)
    assert out.notes[0].chord == ["P", "S"] and out.notes[1].chord == ["d", "r"]


# --- meaningless legato is stripped BEFORE voicing (2026-10-12) -------------------

def test_legato_that_could_never_sound_becomes_a_plain_stroke():
    """The 2026-10-11 breakdown riff slurred nearly every stroke, and a legato note stays
    single, so the riff kept no power chords. A slur needs a ringing single note at ANOTHER
    pitch before it: the cycle's first stroke, a stroke after a rest, a repeated pitch and a
    chorded note cannot be one."""
    pattern = RiffPattern(notes=[
        _n("S", technique="hammer_on"),                    # opens the cycle (the sam)
        _n("S", technique="pull_off"),                     # same pitch as the ringing note
        _n("S", 0.5, rest=True),
        _n("r", technique="hammer_on"),                    # after a rest — nothing rings
        _n("G", technique="hammer_on", chord=["N"]),       # a chord cannot be slurred
    ])
    out = strip_meaningless_legato(pattern)
    assert [n.technique for n in out.notes] == [None, None, None, None, None]


def test_a_real_slur_is_kept():
    # a new pitch, from a ringing single note, unchorded: a hammer-on the hand can play
    pattern = RiffPattern(notes=[_n("S"), _n("r", technique="hammer_on"),
                                 _n("S", technique="pull_off"),
                                 _n("S", oct=1, technique="hammer_on")])   # octave = new pitch
    assert strip_meaningless_legato(pattern) is pattern


def test_a_stripped_legato_gets_its_power_chord():
    # the point of the strip: the breakdown's slurred strokes now carry weight
    slurred = RiffPattern(notes=[_n("S", 1.0, technique="hammer_on"),
                                 _n("S", 1.0, technique="hammer_on"),
                                 _n("r", technique="hammer_on")])           # a real slur: kept
    out = voice_riff(slurred, "bhairav")
    assert out.notes[0].chord == ["P", "S"] and out.notes[1].chord == ["P", "S"]
    assert out.notes[2].technique == "hammer_on" and not out.notes[2].chord
    assert voice_riff(out, "bhairav") is out                                # still idempotent


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
