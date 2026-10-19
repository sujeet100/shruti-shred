"""The LISTENING PASS — an audio model reports what it HEARS in the render. ADVISORY.

Every critic so far judges the symbolic score, so nothing in the loop has ever heard the mix,
the guitar tone, the groove or whether the climax lands. This module lets a Gemini model listen
to the rendered WAV, with the discipline the audio-judging research (2026-10-11) calls for:

  * AUDIO-FIRST and BLIND to the score — the prompt carries the raga, the subgenre and the length,
    never the section map, so the judge cannot parrot a structure it was told
    (crew/config/listening.yaml);
  * TIMESTAMPED observations on fixed aspects (climax, lead audibility, riff heaviness, groove,
    artifacts, mood), each rated 1-5 with one sentence — a reporter, not a trusted scorer;
  * CODE CROSS-CHECKS it (`cross_check`): timestamps must fall inside the piece, and where it
    places the climax is compared with the measured loudness (crew/loudness.py) and with the
    arrangement's own climax — a judge answering from priors contradicts the measurements;
  * the audio is sent as 16 kHz mono FLAC — what the model hears anyway — so the request is small;
  * Pro by default (`RMA_LISTEN_MODEL`): Flash is far weaker at music perception.

It stays ADVISORY until calibrated against Sujit's blind ranking (≥70% pairwise agreement and
≥80% order consistency — `compare` is the building block). Nothing here is wired into the Flow.

Boundary contracts (`ListeningObservation`, `ListeningReport`) live here: this module validates
the model's JSON once at its edge. The judge is an injected `AudioJudge`, so everything is tested
with a fake; `GeminiAudioJudge` is the real adapter (google-genai directly — CrewAI may not pass
audio parts through).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import wave
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template
from typing import Callable, Final, Literal, Optional, Protocol, TypeVar

import yaml
from pydantic import BaseModel, Field, field_validator

from crew.config import listen_model, listening_enabled  # noqa: F401  (re-exported)
from crew.contracts import Arrangement
from crew.loudness import LoudnessArc, SectionLevel, section_windows
from raga import RAGAS
from subgenres import SUBGENRES

_PROMPTS_PATH: Final = Path(__file__).parent / "config" / "listening.yaml"
_MIME: Final = "audio/flac"
_SAMPLE_RATE: Final = 16000
_PAIR_GAP_S: Final = 1.5            # silence between the two clips of a pairwise comparison
_TRIES: Final = 2                   # one answer + ONE bounded repair
_TAIL_S: Final = 5.0                # a ring-out may run past the last section's end
_PEAK_TOLERANCE_LU: Final = 1.0     # "as loud as the loudest" for the climax check
_TIMESTAMP: Final = re.compile(r"^\s*(\d+):([0-5]\d)(?:\.\d+)?\s*$")

Aspect = Literal["climax", "lead_audibility", "riff_heaviness", "groove", "artifacts", "mood"]
T = TypeVar("T")


@cache
def _prompts() -> dict[str, str]:
    return yaml.safe_load(_PROMPTS_PATH.read_text())


# --------------------------------------------------------------------------- #
# The boundary contracts — validated once, here.                               #
# --------------------------------------------------------------------------- #

def timestamp_seconds(stamp: str) -> float:
    """'MM:SS' (or 'M:SS', optional fraction) -> seconds. Raises ValueError otherwise. Pure."""
    match = _TIMESTAMP.match(stamp)
    if not match:
        raise ValueError(f"timestamp {stamp!r} is not MM:SS")
    return int(match.group(1)) * 60 + int(match.group(2))


class ListeningObservation(BaseModel):
    """One thing the judge heard: when (MM:SS), which aspect, a 1-5 rating, one sentence."""
    at: str
    aspect: Aspect
    rating: int = Field(ge=1, le=5)
    note: str

    @field_validator("at")
    @classmethod
    def _is_timestamp(cls, v: str) -> str:
        timestamp_seconds(v)
        return v.strip()

    @property
    def at_s(self) -> float:
        return timestamp_seconds(self.at)


class ListeningReport(BaseModel):
    """The judge's report. Empty observations = it heard nothing usable (or never answered)."""
    observations: list[ListeningObservation] = Field(default_factory=list)
    overall_note: str = ""


def _json_object(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the answer")
    return text[start:end + 1]


def parse_report(text: str) -> ListeningReport:
    """The judge's answer as a ListeningReport; ValueError (incl. ValidationError) if unusable."""
    return ListeningReport.model_validate_json(_json_object(text))


def parse_preference(text: str) -> Literal["first", "second"]:
    """A pairwise answer's choice; ValueError if it names neither clip."""
    data = json.loads(_json_object(text))
    choice = str(data.get("preferred", "") if isinstance(data, dict) else "").strip().lower()
    if choice not in ("first", "second"):
        raise ValueError(f"'preferred' must be \"first\" or \"second\", got {choice!r}")
    return choice  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# The judge — a Protocol, so tests inject a fake.                              #
# --------------------------------------------------------------------------- #

class AudioJudge(Protocol):
    """Anything that can hear audio and answer a prompt about it."""

    def judge(self, audio: bytes, mime_type: str, prompt: str) -> str: ...


class GeminiAudioJudge:
    """The real judge: google-genai directly, audio as an inline part, JSON response, the model's
    DEFAULT sampling (no temperature) and default thinking. The client is built lazily."""

    def __init__(self, model: Optional[str] = None, timeout_s: Optional[float] = None) -> None:
        self._model = model or listen_model()
        self._timeout_s = timeout_s      # None = the SDK's own (none): a stuck call then hangs forever
        self._client = None

    def judge(self, audio: bytes, mime_type: str, prompt: str) -> str:
        from google.genai import types
        response = self._get_client().models.generate_content(
            model=self._model,
            contents=[types.Part.from_bytes(data=audio, mime_type=mime_type), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"))
        return response.text or ""

    def _get_client(self):
        if self._client is None:
            from google import genai

            from crew.config import load_env
            load_env()
            from google.genai import types
            http = types.HttpOptions(timeout=int(self._timeout_s * 1000)) if self._timeout_s else None
            self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=http)
        return self._client


def _ask(client: AudioJudge, audio: bytes, build_prompt: Callable[[str], str],
         parse: Callable[[str], T]) -> Optional[T]:
    """One answer plus ONE bounded repair that names exactly what was wrong; None if both fail
    (a listening pass never kills a run)."""
    repair = ""
    for _ in range(_TRIES):
        text = client.judge(audio, _MIME, build_prompt(repair))
        try:
            return parse(text)
        except ValueError as error:
            repair = Template(_prompts()["repair"]).safe_substitute(error=str(error)[:300])
    return None


# --------------------------------------------------------------------------- #
# Audio preparation — the ffmpeg shell edge, argv built purely.                #
# --------------------------------------------------------------------------- #

def wav_duration_s(wav: Path) -> float:
    with wave.open(str(wav), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def transcode_command(wav: Path) -> list[str]:
    """argv: the WAV as 16 kHz mono FLAC on stdout. Pure."""
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(wav), "-ac", "1",
            "-ar", str(_SAMPLE_RATE), "-f", "flac", "pipe:1"]


def pair_command(first: Path, second: Path) -> list[str]:
    """argv: two clips as ONE 16 kHz mono FLAC, a short silence between them. Pure."""
    fmt = f"aformat=sample_rates={_SAMPLE_RATE}:channel_layouts=mono"
    graph = (f"[0:a]{fmt},apad=pad_dur={_PAIR_GAP_S}[a0];[1:a]{fmt}[a1];"
             f"[a0][a1]concat=n=2:v=0:a=1[out]")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(first), "-i", str(second),
            "-filter_complex", graph, "-map", "[out]", "-f", "flac", "pipe:1"]


def _run(argv: list[str]) -> bytes:
    return subprocess.run(argv, capture_output=True, check=True).stdout


def transcode(wav: Path) -> bytes:
    return _run(transcode_command(wav))


def pair_audio(first: Path, second: Path) -> bytes:
    return _run(pair_command(first, second))


# --------------------------------------------------------------------------- #
# Listen.                                                                      #
# --------------------------------------------------------------------------- #

def _clock(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


_REQUEST_MAX: Final = 240    # characters of the user's words the mood aspect quotes


def _mood_target(arr: Arrangement) -> str:
    """What the mood aspect judges against: the user's own request when there is one — the mood
    is theirs, not a fixed "dark/heavy" every piece was once held to — else the raga and the
    subgenre. Never the section map (the pass stays blind to the score). Pure."""
    request = " ".join(arr.request.split())
    if request:
        clipped = request if len(request) <= _REQUEST_MAX else request[:_REQUEST_MAX].rstrip() + "…"
        return f'the request "{clipped}"'
    return (f"a {SUBGENRES[arr.subgenre]['display']} piece in raga {RAGAS[arr.raga]['display']}, "
            f"true to that raga's own character")


def listen_prompt(arr: Arrangement, duration_s: float, repair: str = "") -> str:
    """The audio-first, score-blind prompt: raga, subgenre, length and the requested mood. Pure."""
    return Template(_prompts()["listen"]).safe_substitute(
        raga=RAGAS[arr.raga]["display"], subgenre=SUBGENRES[arr.subgenre]["display"],
        duration=f"{_clock(duration_s)} ({duration_s:.0f} seconds)",
        mood_target=_mood_target(arr), repair=repair)


def judge_audio(audio: bytes, arr: Arrangement, duration_s: float, *,
                client: AudioJudge) -> ListeningReport:
    """Ask the judge about already-prepared audio. An unusable answer (twice) yields an empty
    report with a note, never an exception."""
    report = _ask(client, audio, lambda repair: listen_prompt(arr, duration_s, repair),
                  parse_report)
    return report or ListeningReport(overall_note="(the listener returned no usable report)")


def listen(wav: Path, arr: Arrangement, *, client: AudioJudge) -> ListeningReport:
    """Let the judge hear the rendered piece and report, timestamped. ADVISORY."""
    return judge_audio(transcode(wav), arr, wav_duration_s(wav), client=client)


# --------------------------------------------------------------------------- #
# Cross-check — did the judge actually listen?                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Placement:
    """An observation mapped onto the arrangement: its section index (None = outside the piece)."""
    observation: ListeningObservation
    section: Optional[int]


@dataclass(frozen=True)
class CrossCheck:
    """What code could verify about the report. `consistency` is the share of checks passed
    (0.0 for an empty report); `contradictions` say what failed, in words."""
    placements: tuple[Placement, ...]
    labels: dict[int, str]
    windows: dict[int, tuple[float, float]]
    contradictions: tuple[str, ...]
    consistency: float


def _section_at(at_s: float, windows: list[tuple[int, float, float, str]]) -> Optional[int]:
    for index, start, end, _ in windows:
        if start <= at_s < end:
            return index
    last = windows[-1] if windows else None
    if last and last[2] <= at_s <= last[2] + _TAIL_S:
        return last[0]                      # the ring-out belongs to the last section
    return None


def _claimed_climax(placements: list[Placement]) -> Optional[Placement]:
    """Where the judge says the energy peaks: its highest-rated placed climax observation."""
    claims = [p for p in placements if p.observation.aspect == "climax" and p.section is not None]
    return max(claims, key=lambda p: p.observation.rating) if claims else None


def _loudness_check(claim: Placement, arc: LoudnessArc) -> Optional[tuple[bool, str]]:
    levels: dict[int, SectionLevel] = {s.index: s for s in arc.sections}
    if claim.section not in levels or arc.loudest_index is None:
        return None
    top = levels[arc.loudest_index].level.integrated_lufs
    ok = levels[claim.section].level.integrated_lufs >= top - _PEAK_TOLERANCE_LU
    return ok, (f"the judge places the climax at {claim.observation.at} (section {claim.section}), "
                f"but the measured loudness peaks in section {arc.loudest_index}")


def _arrangement_check(claim: Placement, arc: LoudnessArc) -> Optional[tuple[bool, str]]:
    if arc.climax_index is None:
        return None
    ok = claim.section == arc.climax_index
    return ok, (f"the judge places the climax at {claim.observation.at} (section {claim.section}), "
                f"but the arrangement's climax is section {arc.climax_index}")


def cross_check(report: ListeningReport, arr: Arrangement, arc: LoudnessArc) -> CrossCheck:
    """Verify what code can: every timestamp lies inside the piece, and the claimed climax agrees
    with the measured loudness peak and with the arrangement's climax. Pure."""
    windows = section_windows(arr)
    placements = [Placement(o, _section_at(o.at_s, windows)) for o in report.observations]
    checks: list[tuple[bool, str]] = [
        (p.section is not None, f"observation at {p.observation.at} lies outside the piece")
        for p in placements]
    claim = _claimed_climax(placements)
    if claim is not None:
        checks += [c for c in (_loudness_check(claim, arc), _arrangement_check(claim, arc)) if c]
    passed = sum(ok for ok, _ in checks)
    return CrossCheck(placements=tuple(placements),
                      labels={i: label for i, _, _, label in windows},
                      windows={i: (start, end) for i, start, end, _ in windows},
                      contradictions=tuple(msg for ok, msg in checks if not ok),
                      consistency=passed / len(checks) if checks else 0.0)


# --------------------------------------------------------------------------- #
# The Producer's block.                                                        #
# --------------------------------------------------------------------------- #

def _observation_line(o: ListeningObservation) -> str:
    return f"      {o.at}  {o.aspect} {o.rating}/5 — {o.note}"


def _section_block(index: int, check: CrossCheck) -> list[str]:
    start, end = check.windows[index]
    heard = [p.observation for p in check.placements if p.section == index]
    if not heard:
        return []
    header = f"    section {index} ({check.labels[index]}, {_clock(start)}-{_clock(end)}):"
    return [header, *(_observation_line(o) for o in sorted(heard, key=lambda o: o.at_s))]


def render_listening(report: ListeningReport, check: CrossCheck) -> str:
    """The listening pass as a prompt block for the Producer — grouped by section, its
    contradictions marked, and labelled ADVISORY. Pure."""
    lines = ["  LISTENING PASS — ADVISORY: an audio model's timestamped impressions of the RENDER, "
             "checked by code but NOT calibrated against Sujit's ear. Weigh it as a hint, never "
             f"as a verdict. Code consistency: {check.consistency:.0%}."]
    if not report.observations:
        lines.append(f"    (no usable observations) {report.overall_note}".rstrip())
        return "\n".join(lines)
    for index in sorted(check.windows):
        lines += _section_block(index, check)
    unplaced = [p.observation for p in check.placements if p.section is None]
    if unplaced:
        lines.append("    outside the piece (ignore):")
        lines += [_observation_line(o) for o in unplaced]
    lines += [f"    CONTRADICTION: {msg}" for msg in check.contradictions]
    if report.overall_note:
        lines.append(f"    overall: {report.overall_note}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Calibration building block — a pairwise preference, asked in BOTH orders.    #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PairwiseResult:
    """Which clip the judge prefers ("a" / "b"), or "tie" when its answer flips with the order
    (position bias) or it never answered; `order_consistent` says whether both orders agreed."""
    preference: Literal["a", "b", "tie"]
    order_consistent: bool


def _ask_pair(first: Path, second: Path, subgenre: str, client: AudioJudge) -> Optional[str]:
    prompt = Template(_prompts()["compare"]).safe_substitute(subgenre=subgenre)
    return _ask(client, pair_audio(first, second), lambda repair: prompt + repair,
                parse_preference)


def resolve_pair(ab: Optional[str], ba: Optional[str]) -> PairwiseResult:
    """Combine the two orders' answers. Played (a, b) then (b, a): a consistent judge names the
    same CLIP both times. Pure."""
    pick_ab = {"first": "a", "second": "b"}.get(ab or "")
    pick_ba = {"first": "b", "second": "a"}.get(ba or "")
    if pick_ab is not None and pick_ab == pick_ba:
        return PairwiseResult(pick_ab, True)        # type: ignore[arg-type]
    return PairwiseResult("tie", False)


def compare(wav_a: Path, wav_b: Path, client: AudioJudge, *,
            subgenre: str = "metal") -> PairwiseResult:
    """Ask the judge which of two renders is better, in BOTH orders; an order-dependent answer
    counts as a tie. The building block for calibrating against Sujit's blind ranking."""
    return resolve_pair(_ask_pair(wav_a, wav_b, subgenre, client),
                        _ask_pair(wav_b, wav_a, subgenre, client))
