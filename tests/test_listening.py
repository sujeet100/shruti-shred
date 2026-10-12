"""
Tests for crew/listening.py — the ADVISORY listening pass. Pure + real ffmpeg, NO paid calls:
the audio judge is always a fake.

Proven here: the prompt is audio-first and blind to the score; a malformed answer gets ONE
bounded repair and a second failure degrades to an empty report (never an exception); code
cross-checks the judge (an out-of-range timestamp, a climax claim that contradicts the measured
loudness and the arrangement); the Producer's block is grouped by section and labelled ADVISORY;
and a pairwise comparison asked in both orders counts an order-dependent answer as a tie.

Runs as a script (`uv run python tests/test_listening.py`) or under pytest.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.listening import (  # noqa: E402
    ListeningReport,
    compare,
    cross_check,
    judge_audio,
    listen,
    listen_model,
    listening_enabled,
    render_listening,
    resolve_pair,
    timestamp_seconds,
    transcode_command,
)
from crew.loudness import LoudnessArc, SectionLevel, SegmentLevel  # noqa: E402
from tests.test_loudness import _arr, _wav  # noqa: E402


class _Judge:
    """A fake AudioJudge: replays canned answers and records what it was asked."""

    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []
        self.audio: list[bytes] = []

    def judge(self, audio: bytes, mime_type: str, prompt: str) -> str:
        self.prompts.append(prompt)
        self.audio.append(audio)
        return self._answers.pop(0)


def _answer(*observations: tuple[str, str, int]) -> str:
    return json.dumps({"observations": [{"at": at, "aspect": aspect, "rating": rating,
                                         "note": f"{aspect} heard"}
                                        for at, aspect, rating in observations],
                       "overall_note": "a dark, heavy piece"})


def _arc(loudest: int = 1) -> LoudnessArc:
    def level(lufs: float) -> SegmentLevel:
        return SegmentLevel(lufs, -3.0, -3.0, lufs)
    sections = (SectionLevel(0, 0.0, 4.0, "mukhada", level(-20.0 if loudest == 1 else -12.0)),
                SectionLevel(1, 4.0, 8.0, "taan_long", level(-12.0 if loudest == 1 else -20.0)))
    return LoudnessArc(sections, loudest, 1, loudest == 1, loudest == 1, False)


# --- the boundary -------------------------------------------------------------------------

def test_timestamps_parse_as_minutes_and_seconds():
    assert timestamp_seconds("0:07") == 7 and timestamp_seconds("01:05") == 65
    for bad in ("7", "1:75", "soon"):
        try:
            timestamp_seconds(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should not parse")


def test_flags_and_model_come_from_the_environment():
    os.environ.pop("RMA_LISTEN", None)
    os.environ.pop("RMA_LISTEN_MODEL", None)
    assert listening_enabled() is False and listen_model() == "gemini-3.1-pro-preview"
    os.environ["RMA_LISTEN"] = "1"
    try:
        assert listening_enabled() is True
    finally:
        os.environ.pop("RMA_LISTEN")


def test_the_audio_is_sent_as_16khz_mono_flac():
    argv = transcode_command(Path("x.wav"))
    assert argv[argv.index("-ac") + 1] == "1" and argv[argv.index("-ar") + 1] == "16000"
    assert argv[argv.index("-f") + 1] == "flac"


# --- listening ------------------------------------------------------------------------------

def test_the_prompt_is_blind_to_the_score():
    judge = _Judge(_answer(("0:06", "climax", 4)))
    judge_audio(b"audio", _arr(), 8.0, client=judge)
    prompt = judge.prompts[0]
    assert "Malkauns" in prompt and "0:08 (8 seconds)" in prompt
    assert "mukhada" not in prompt and "taan_long" not in prompt   # never the section map


def test_a_valid_answer_needs_one_call():
    judge = _Judge(_answer(("0:06", "climax", 4), ("0:02", "riff_heaviness", 2)))
    report = judge_audio(b"audio", _arr(), 8.0, client=judge)
    assert len(judge.prompts) == 1 and len(report.observations) == 2


def test_a_malformed_answer_gets_one_repair_that_names_the_fault():
    judge = _Judge("I loved it!", _answer(("0:06", "climax", 5)))
    report = judge_audio(b"audio", _arr(), 8.0, client=judge)
    assert len(judge.prompts) == 2 and "could not be used" in judge.prompts[1]
    assert report.observations[0].rating == 5


def test_two_unusable_answers_degrade_to_an_empty_report():
    judge = _Judge("nope", json.dumps({"observations": [{"at": "soon", "aspect": "climax",
                                                          "rating": 9, "note": "x"}]}))
    report = judge_audio(b"audio", _arr(), 8.0, client=judge)
    assert len(judge.prompts) == 2 and report.observations == []
    assert "no usable report" in report.overall_note


def test_listen_transcodes_the_real_wav_before_sending():
    with tempfile.TemporaryDirectory() as tmp:
        wav = _wav(Path(tmp) / "piece.wav", [0.05, 0.6], seconds_each=4.0)
        judge = _Judge(_answer(("0:06", "climax", 4)))
        report = listen(wav, _arr(), client=judge)
    assert judge.audio[0][:4] == b"fLaC" and len(report.observations) == 1
    assert "0:08" in judge.prompts[0]                       # the WAV's own duration


# --- the cross-check --------------------------------------------------------------------------

def test_a_climax_where_the_music_peaks_is_consistent():
    report = ListeningReport.model_validate_json(_answer(("0:06", "climax", 4),
                                                         ("0:01", "groove", 3)))
    check = cross_check(report, _arr(), _arc(loudest=1))
    assert check.contradictions == () and check.consistency == 1.0
    assert [p.section for p in check.placements] == [1, 0]


def test_the_cross_check_catches_a_judge_that_is_not_listening():
    # it hears the climax at 0:02 (the quiet section) and reports something at 5:00 in an
    # eight-second piece — both contradicted by code
    report = ListeningReport.model_validate_json(_answer(("0:02", "climax", 5),
                                                         ("5:00", "mood", 4)))
    check = cross_check(report, _arr(), _arc(loudest=1))
    text = " ".join(check.contradictions)
    assert "outside the piece" in text
    assert "measured loudness peaks in section 1" in text
    assert "arrangement's climax is section 1" in text
    assert check.consistency < 0.5


def test_an_empty_report_has_no_consistency():
    check = cross_check(ListeningReport(), _arr(), _arc())
    assert check.consistency == 0.0 and check.placements == ()


# --- the Producer's block ------------------------------------------------------------------------

def test_the_block_is_grouped_by_section_and_labelled_advisory():
    report = ListeningReport.model_validate_json(_answer(("0:06", "climax", 4),
                                                         ("0:01", "riff_heaviness", 2),
                                                         ("5:00", "mood", 3)))
    block = render_listening(report, cross_check(report, _arr(), _arc()))
    assert "ADVISORY" in block and "NOT calibrated" in block
    assert block.index("section 0 (mukhada") < block.index("section 1 (taan_long")
    assert "outside the piece (ignore)" in block and "CONTRADICTION" in block
    assert "riff_heaviness 2/5" in block


def test_an_empty_report_renders_honestly():
    block = render_listening(ListeningReport(overall_note="silence"),
                             cross_check(ListeningReport(), _arr(), _arc()))
    assert "no usable observations" in block and "silence" in block


# --- calibration: pairwise, both orders -----------------------------------------------------------

def test_the_same_clip_named_in_both_orders_is_a_preference():
    assert resolve_pair("first", "second").preference == "a"
    assert resolve_pair("second", "first").preference == "b"


def test_an_answer_that_follows_the_position_is_a_tie():
    flipped = resolve_pair("first", "first")             # always the first clip played
    assert flipped.preference == "tie" and flipped.order_consistent is False
    assert resolve_pair(None, "second").preference == "tie"


def test_compare_plays_both_orders_through_real_ffmpeg():
    with tempfile.TemporaryDirectory() as tmp:
        a = _wav(Path(tmp) / "a.wav", [0.3], seconds_each=1.0)
        b = _wav(Path(tmp) / "b.wav", [0.6], seconds_each=1.0)
        judge = _Judge('{"preferred": "first", "reason": "x"}',
                       '{"preferred": "second", "reason": "x"}')
        result = compare(a, b, judge, subgenre="Doom")
    assert result.preference == "a" and result.order_consistent is True
    assert len(judge.audio) == 2 and all(blob[:4] == b"fLaC" for blob in judge.audio)
    assert "Doom" in judge.prompts[0]


def test_the_mood_is_judged_against_the_request_not_a_fixed_dark_heavy():
    from crew.listening import listen_prompt
    arr = _arr()
    plain = listen_prompt(arr, 60.0)
    assert "dark/heavy" not in plain and "$mood_target" not in plain
    assert "true to that raga's own character" in plain             # no request: raga + subgenre
    asked = listen_prompt(arr.model_copy(update={"request": "a  joyful\nfast piece"}), 60.0)
    assert 'the request "a joyful fast piece"' in asked


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
