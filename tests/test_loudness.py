"""
Tests for crew/loudness.py — per-section loudness of the RENDER, measured by code (no LLM).

The pure parts are proven on captured ffmpeg output; the shell edge runs real ffmpeg on a tiny
synthetic WAV laid out to match a two-section chart (a quiet section, then a loud climax).

Runs as a script (`uv run python tests/test_loudness.py`) or under pytest.
"""

from __future__ import annotations

import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.loudness import (  # noqa: E402
    SectionLevel,
    SegmentLevel,
    climax_index,
    ffmpeg_level_command,
    measure_sections,
    measure_segment,
    parse_levels,
    render_arc,
    section_windows,
    summarize,
)

# Captured from `ffmpeg ... -af ebur128=peak=true,volumedetect -f null -` on a sine wave.
_REPORT = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:          -5.6 LUFS
    Threshold: -15.6 LUFS

  Loudness range:
    LRA:         0.0 LU

  True peak:
    Peak:       -1.9 dBFS
[Parsed_volumedetect_1 @ 0x2] n_samples: 44100
[Parsed_volumedetect_1 @ 0x2] mean_volume: -4.9 dB
[Parsed_volumedetect_1 @ 0x2] max_volume: -1.9 dB
"""


def _arr(bpm: int = 240):
    """Two one-cycle sections at 240 bpm teentaal = 4 s each: a mukhada, then the climax."""
    sections = [Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "rhythm", "drone"],
                        foreground="lead", form_role="mukhada"),
                Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "rhythm", "drone"],
                        foreground="lead", form_role="taan_long")]
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala="teentaal", bpm=bpm,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _wav(path: Path, amplitudes: list[float], seconds_each: float, rate: int = 22050) -> Path:
    """A mono 440 Hz sine, one segment per amplitude."""
    frames = bytearray()
    for amp in amplitudes:
        for i in range(int(rate * seconds_each)):
            frames += struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * 440 * i / rate)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return path


def _level(lufs: float, peak: float = -3.0) -> SegmentLevel:
    return SegmentLevel(integrated_lufs=lufs, true_peak_db=peak, max_volume_db=peak,
                        mean_volume_db=lufs)


def test_the_ffmpeg_report_parses():
    level = parse_levels(_REPORT)
    assert (level.integrated_lufs, level.true_peak_db) == (-5.6, -1.9)
    assert (level.max_volume_db, level.mean_volume_db) == (-1.9, -4.9)


def test_a_silent_or_missing_reading_is_minus_infinity():
    level = parse_levels("Integrated loudness:\n    I:         -inf LUFS\n")
    assert math.isinf(level.integrated_lufs) and math.isinf(level.true_peak_db)


def test_section_windows_follow_the_arrangement_clock():
    assert section_windows(_arr()) == [(0, 0.0, 4.0, "mukhada"), (1, 4.0, 8.0, "taan_long")]
    assert climax_index(_arr()) == 1


def test_the_command_measures_one_window():
    argv = ffmpeg_level_command(Path("x.wav"), 4.0, 2.5)
    assert argv[argv.index("-ss") + 1] == "4.000" and argv[argv.index("-t") + 1] == "2.500"
    assert "ebur128=peak=true,volumedetect" in argv


def test_the_arc_names_the_loudest_section_and_checks_the_climax():
    sections = [SectionLevel(0, 0, 4, "mukhada", _level(-14.0)),
                SectionLevel(1, 4, 8, "taan_long", _level(-20.0)),
                SectionLevel(2, 8, 12, "outro", _level(-14.5))]
    arc = summarize(sections, climax=1)
    assert arc.loudest_index == 0
    assert arc.climax_is_peak is False                  # the climax deflates
    assert arc.final_is_peak is True                    # within 1 LU of the loudest
    assert arc.clipping is False
    assert "climax is the peak: no" in render_arc(arc)


def test_a_peak_at_full_scale_is_clipping():
    arc = summarize([SectionLevel(0, 0, 4, "riff", _level(-10.0, peak=0.0))], climax=None)
    assert arc.clipping is True and arc.climax_is_peak is None


def test_a_real_render_is_measured_section_by_section():
    with tempfile.TemporaryDirectory() as tmp:
        wav = _wav(Path(tmp) / "piece.wav", [0.05, 0.6], seconds_each=4.0)
        quiet = measure_segment(wav, 0.0, 4.0)
        arc = measure_sections(wav, _arr())
    assert quiet.integrated_lufs < arc.sections[1].level.integrated_lufs
    assert arc.loudest_index == 1 and arc.climax_is_peak is True and arc.final_is_peak is True


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
