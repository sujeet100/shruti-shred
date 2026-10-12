"""LOUDNESS — what the rendered audio measurably does, section by section. No LLM.

The listening pass (crew/listening.py) asks a model what it HEARS; this module measures what
code can measure for free, so the two can be checked against each other: per-section integrated
loudness (EBU R128, LUFS), true peak and sample peak, and the ARC they form — which section is
loudest, whether the climax and the final section are the peak, whether anything clips. A judge
that claims "the energy peaks at 0:12" while the loudest section is the last one is not
listening; code catches that (`listening.cross_check`).

Layering: the ffmpeg call is the only side effect (`measure_segment`); parsing its report
(`parse_levels`), deriving the section windows from an Arrangement (`section_windows`) and
summarising the arc (`summarize`) are pure and unit-tested on captured strings.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional

from crew.contracts import Arrangement
from crew.generators import section_spans

# The climax role — the section the arrangement means as its peak.
_CLIMAX_ROLE: Final = "taan_long"
# Two sections within this many LU are "equally loud": the ear does not rank a 0.3 LU gap.
_PEAK_TOLERANCE_LU: Final = 1.0
# A sample at or above this level is treated as clipping (the render normalises to -2 dBFS).
_CLIP_DB: Final = -0.1
_NUMBER: Final = r"(-?inf|-?\d+(?:\.\d+)?)"
_INTEGRATED: Final = re.compile(r"Integrated loudness:\s*\n\s*I:\s*" + _NUMBER)
_TRUE_PEAK: Final = re.compile(r"True peak:\s*\n\s*Peak:\s*" + _NUMBER)
_MAX_VOLUME: Final = re.compile(r"max_volume:\s*" + _NUMBER + r" dB")
_MEAN_VOLUME: Final = re.compile(r"mean_volume:\s*" + _NUMBER + r" dB")


@dataclass(frozen=True)
class SegmentLevel:
    """One stretch of audio's levels: EBU R128 integrated loudness, true peak, sample peak and
    mean level. `-inf` for silence."""
    integrated_lufs: float
    true_peak_db: float
    max_volume_db: float
    mean_volume_db: float


@dataclass(frozen=True)
class SectionLevel:
    """A section's window in SECONDS, its form role/kind (for labels), and its levels."""
    index: int
    start_s: float
    end_s: float
    label: str
    level: SegmentLevel


@dataclass(frozen=True)
class LoudnessArc:
    """The whole piece's loudness shape. `loudest_index` is the section with the highest
    integrated loudness; `climax_index` the arrangement's climax section (None without one);
    `climax_is_peak` / `final_is_peak` say whether those sections are within `_PEAK_TOLERANCE_LU`
    of the loudest; `clipping` is true when any section's peak reaches `_CLIP_DB`."""
    sections: tuple[SectionLevel, ...]
    loudest_index: Optional[int]
    climax_index: Optional[int]
    climax_is_peak: Optional[bool]
    final_is_peak: bool
    clipping: bool


def _number(pattern: re.Pattern[str], text: str) -> float:
    match = pattern.search(text)
    return float(match.group(1)) if match else float("-inf")


def parse_levels(ffmpeg_report: str) -> SegmentLevel:
    """Read ffmpeg's `ebur128=peak=true,volumedetect` stderr into a SegmentLevel. Pure; a
    missing field (e.g. an all-silent window) reads as -inf."""
    return SegmentLevel(integrated_lufs=_number(_INTEGRATED, ffmpeg_report),
                        true_peak_db=_number(_TRUE_PEAK, ffmpeg_report),
                        max_volume_db=_number(_MAX_VOLUME, ffmpeg_report),
                        mean_volume_db=_number(_MEAN_VOLUME, ffmpeg_report))


def seconds_per_beat(arr: Arrangement) -> float:
    return 60.0 / arr.bpm


def _label(section) -> str:
    return f"{section.form_role or section.kind.value}"


def section_windows(arr: Arrangement) -> list[tuple[int, float, float, str]]:
    """Each section's (index, start_s, end_s, label) on the render's clock. Pure."""
    spb = seconds_per_beat(arr)
    return [(span.index, span.start * spb, span.end * spb, _label(span.section))
            for span in section_spans(arr)]


def climax_index(arr: Arrangement) -> Optional[int]:
    """The arrangement's climax section — its first long taan — or None. Pure."""
    return next((span.index for span in section_spans(arr)
                 if span.section.form_role == _CLIMAX_ROLE), None)


def _is_peak(level: SegmentLevel, loudest: float) -> bool:
    return level.integrated_lufs >= loudest - _PEAK_TOLERANCE_LU


def summarize(sections: list[SectionLevel], climax: Optional[int]) -> LoudnessArc:
    """The arc from already-measured sections. Pure."""
    if not sections:
        return LoudnessArc((), None, climax, None, False, False)
    loudest = max(sections, key=lambda s: s.level.integrated_lufs)
    top = loudest.level.integrated_lufs
    by_index = {s.index: s for s in sections}
    climax_peak = (_is_peak(by_index[climax].level, top) if climax in by_index else None)
    clipping = any(max(s.level.true_peak_db, s.level.max_volume_db) >= _CLIP_DB for s in sections)
    return LoudnessArc(tuple(sections), loudest.index, climax, climax_peak,
                       _is_peak(sections[-1].level, top), clipping)


def ffmpeg_level_command(wav: Path, start_s: float, duration_s: float) -> list[str]:
    """The ffmpeg invocation that measures one window. Pure (just builds argv)."""
    return ["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start_s:.3f}", "-t",
            f"{duration_s:.3f}", "-i", str(wav), "-af", "ebur128=peak=true,volumedetect",
            "-f", "null", "-"]


def measure_segment(wav: Path, start_s: float, duration_s: float) -> SegmentLevel:
    """Measure one window of a WAV with ffmpeg. The shell edge — ffmpeg writes its report to
    stderr."""
    result = subprocess.run(ffmpeg_level_command(wav, start_s, duration_s),
                            capture_output=True, text=True, check=False)
    return parse_levels(result.stderr)


def measure_sections(wav: Path, arr: Arrangement) -> LoudnessArc:
    """Measure every section of a rendered piece and summarise the arc."""
    sections = [SectionLevel(i, start, end, label, measure_segment(wav, start, end - start))
                for i, start, end, label in section_windows(arr)]
    return summarize(sections, climax_index(arr))


def render_arc(arc: LoudnessArc) -> str:
    """The arc as a short prompt/report block: per-section LUFS, the loudest, the climax check,
    clipping. Pure."""
    def lufs(v: float) -> str:
        return "silent" if math.isinf(v) else f"{v:.1f} LUFS"
    lines = [f"  {s.index}: {s.label} {s.start_s:.0f}-{s.end_s:.0f}s  {lufs(s.level.integrated_lufs)}"
             for s in arc.sections]
    if arc.loudest_index is not None:
        lines.append(f"  loudest: section {arc.loudest_index}; final section is the peak: "
                     f"{'yes' if arc.final_is_peak else 'no'}"
                     + ("" if arc.climax_is_peak is None
                        else f"; climax is the peak: {'yes' if arc.climax_is_peak else 'no'}")
                     + ("; CLIPPING" if arc.clipping else ""))
    return "\n".join(lines)
