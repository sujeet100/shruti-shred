"""
The two contracts that hold the system together (both framework-agnostic, so
they double as teaching artifacts):

  1. COMPOSITION  — the swara-JSON generators emit and the renderer consumes.
                    Defined here as Pydantic v2 so an agent's `output_pydantic`
                    can target it and malformed output fails at the BOUNDARY,
                    not deep in the renderer. `.model_dump()` yields exactly the
                    dict `render.build_midi` / `raga.validate_composition` expect.

  2. DEBATE EVENT STREAM — the `{type, agent, role, text, verdict?, scores?}`
                    events the UI renders. The UI can't tell whether an event
                    came from the live crew or a replay script — same shape.

Two levels of checking, kept deliberately separate (a talk point):
  * STRUCTURAL  — "is this well-formed, with known symbols?"  -> Pydantic here.
  * GRAMMATICAL — "is this legal in the raga?"                -> validate_composition.
A composition can be structurally perfect and still illegal; the guardrail is
the second gate, never the first.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Optional, Union

from pydantic import BaseModel, Field, ValidationError, field_validator

from raga import RAGAS, SWARAS  # single source of truth for ragas + legal sargam symbols
from subgenres import SUBGENRES


# --------------------------------------------------------------------------- #
# Contract 0: Intake (free-text query -> validated brief)                     #
#                                                                             #
# Split on purpose: the LLM does FUZZY extraction (RawIntent — what the user  #
# said), and deterministic CODE does AUTHORITATIVE validation (resolve_brief).#
# It invents NOTHING. The one hard check is that the raga is supported (we    #
# only have five) — that's boundary validation, not a creative choice. Every  #
# UNSTATED dimension (subgenre, tempo, instruments, key/register) is left     #
# OPEN for the composers to decide; the Interpreter must not preempt them.    #
# resolve_brief is pure and unit-tested without any LLM.                      #
# --------------------------------------------------------------------------- #

# Note name -> MIDI pitch (octave 4; C4 = 60). Used to transcribe "in the key of D".
KEY_TO_MIDI: dict[str, int] = {
    "C": 60, "C#": 61, "DB": 61, "D": 62, "D#": 63, "EB": 63, "E": 64, "F": 65,
    "F#": 66, "GB": 66, "G": 67, "G#": 68, "AB": 68, "A": 69, "A#": 70, "BB": 70, "B": 71,
}
DEFAULT_SA: int = KEY_TO_MIDI["D"]  # render-time fallback ONLY if key is never set; NOT an intake default


_NULLISH = {"", "null", "none", "n/a", "na", "unspecified", "unknown", "any"}


class RawIntent(BaseModel):
    """What the Interpreter LLM extracts — loose, only what the user actually said.

    Every field is optional: a null means "user didn't specify", NOT "guess".
    Grounded defaults are the deterministic resolver's job, never the model's.

    LLMs are unreliable at "leave it null" — they emit the string "null", or a
    sentinel like bpm -1, or an empty list. These validators normalize that junk
    back to real None at the boundary, so the resolver sees clean data. (They
    can't undo a *plausible* hallucination like an invented bpm of 120 — that's
    dampened prompt-side; see tasks.yaml.)
    """
    raga: Optional[str] = None
    key: Optional[str] = None
    subgenre: Optional[str] = None
    mood: Optional[str] = None
    bpm: Optional[int] = None
    instruments: Optional[list[str]] = None

    @field_validator("raga", "key", "subgenre", "mood", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return None if isinstance(v, str) and v.strip().lower() in _NULLISH else v

    @field_validator("bpm", mode="before")
    @classmethod
    def _bad_bpm_to_none(cls, v):
        try:
            return None if v is None or int(v) <= 0 else int(v)
        except (TypeError, ValueError):
            return None

    @field_validator("instruments", mode="before")
    @classmethod
    def _clean_instruments(cls, v):
        if not v:
            return None
        cleaned = [i for i in v if isinstance(i, str) and i.strip().lower() not in _NULLISH]
        return cleaned or None


class CompositionBrief(BaseModel):
    """What the user asked for — extracted and validated, nothing invented.

    EVERYTHING is optional. The user might name a raga and key, or say nothing but a
    mood ("a romantic metal fusion"). Each field is what the user EXPLICITLY stated,
    or None = "open — the composers decide." The Interpreter makes no creative
    choices; the composers pick whatever was left open — including the RAGA itself,
    guided by the mood. `notes` records extraction observations (e.g. an unsupported
    raga/subgenre was requested and left open).
    """
    raga: Optional[str] = None         # kept only if the user named a SUPPORTED raga
    key: Optional[str] = None          # transcribed if stated (e.g. "D")
    sa: Optional[int] = None           # MIDI root, from key if stated; else open
    subgenre: Optional[str] = None     # kept only if the user named a SUPPORTED one
    bpm: Optional[int] = None          # only if the user gave a number
    instruments: Optional[list[str]] = None  # only if the user named some
    mood: Optional[str] = None         # emotional vibe (e.g. angry, romantic) — a hint for the composers
    notes: list[str] = Field(default_factory=list)

    @field_validator("raga")
    @classmethod
    def _known_raga(cls, v):
        if v is not None and v not in RAGAS:
            raise ValueError(f"unknown raga '{v}' (expected one of {sorted(RAGAS)})")
        return v

    @field_validator("subgenre")
    @classmethod
    def _known_subgenre(cls, v):
        if v is not None and v not in SUBGENRES:
            raise ValueError(f"unknown subgenre '{v}' (expected one of {sorted(SUBGENRES)})")
        return v


def _match_raga(text: Optional[str]) -> Optional[str]:
    """Map a free-text raga name to a RAGAS key, or None. Handles display names."""
    if not text:
        return None
    t = text.strip().lower()
    if t in RAGAS:
        return t
    for key, raga in RAGAS.items():
        display = raga["display"].lower()
        if key in t or display in t or t in display:
            return key
    return None


def resolve_brief(intent: RawIntent) -> CompositionBrief:
    """Extract & validate ONLY what the user stated; invent nothing. Always succeeds.

    Pure and deterministic — no LLM, no network. NOTHING is required: the user may
    give only a mood. A stated raga or subgenre is kept only if we support it (else
    noted and left open); a stated key is transcribed to Sa; bpm/instruments/mood
    pass through as stated. Every unstated dimension stays None = "open for the
    composers" — who will pick the raga (from the mood), subgenre, tempo, and rest.
    """
    notes: list[str] = []

    raga: Optional[str] = None
    if intent.raga:
        matched = _match_raga(intent.raga)
        if matched:
            raga = matched
        else:
            notes.append(f"raga {intent.raga!r} not supported {sorted(RAGAS)} "
                         f"— left open for the composers")

    key: Optional[str] = None
    sa: Optional[int] = None
    if intent.key:
        candidate = intent.key.strip().upper()
        if candidate in KEY_TO_MIDI:
            key, sa = candidate, KEY_TO_MIDI[candidate]
        else:
            notes.append(f"key {intent.key!r} not recognized — left open")

    subgenre: Optional[str] = None
    if intent.subgenre:
        candidate = intent.subgenre.strip().lower()
        if candidate in SUBGENRES:
            subgenre = candidate
        else:
            notes.append(f"subgenre {intent.subgenre!r} not supported "
                         f"{sorted(SUBGENRES)} — left open for the composers")

    return CompositionBrief(raga=raga, key=key, sa=sa, subgenre=subgenre,
                            bpm=intent.bpm, instruments=intent.instruments,
                            mood=intent.mood, notes=notes)


# --------------------------------------------------------------------------- #
# Contract 1: Composition                                                     #
# --------------------------------------------------------------------------- #

class Note(BaseModel):
    swara: str
    oct: int = 0
    start: float
    dur: float
    vel: int = 100
    grace: Optional[list[str]] = None            # kan (grace notes)
    meend: Optional[Union[str, dict]] = None     # glide target: swara or {swara, oct}

    @field_validator("swara")
    @classmethod
    def _known_swara(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown swara '{v}' (expected one of {' '.join(SWARAS)})")
        return v

    @field_validator("grace")
    @classmethod
    def _known_grace(cls, v):
        bad = [g for g in (v or []) if g not in SWARAS]
        if bad:
            raise ValueError(f"unknown grace swara(s) {bad}")
        return v

    @field_validator("meend")
    @classmethod
    def _known_meend(cls, v):
        sw = v["swara"] if isinstance(v, dict) else v
        if sw is not None and sw not in SWARAS:
            raise ValueError(f"unknown meend target '{sw}'")
        return v


class DrumHit(BaseModel):
    drum: str
    start: float
    dur: float = 0.2
    vel: int = 100

    @field_validator("drum")
    @classmethod
    def _known_drum(cls, v: str) -> str:
        from render import DRUMS  # lazy: keeps render (midiutil) off the light path
        if v not in DRUMS:
            raise ValueError(f"unknown drum '{v}' (expected one of {' '.join(DRUMS)})")
        return v


class Layer(BaseModel):
    role: str  # "drone" | "lead" | "rhythm" | "drums"
    instrument: Optional[str] = None
    program: Optional[int] = None
    channel: Optional[int] = None
    notes: Optional[list[Note]] = None
    hits: Optional[list[DrumHit]] = None


class Composition(BaseModel):
    raga: str
    sa: int = 60
    bpm: int
    tala: dict            # {"name": str, "beats_per_bar": float}
    layers: list[Layer]


def parse_composition(comp: dict) -> tuple[Optional[Composition], list[str]]:
    """Structural gate: parse a raw dict into a Composition (shape + known symbols).

    Returns (composition, []) on success or (None, [human-readable errors]).
    This is NOT raga-legality — that's `raga.validate_composition`, the guardrail.
    """
    try:
        return Composition.model_validate(comp), []
    except ValidationError as e:
        return None, [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]


# --------------------------------------------------------------------------- #
# Contract 2: Debate event stream                                             #
# --------------------------------------------------------------------------- #

class EventType(str, Enum):
    INFO = "info"          # setup / narration
    PROPOSE = "propose"    # a generator emits a candidate
    VALIDATE = "validate"  # the deterministic guardrail runs
    CRITIQUE = "critique"  # a critic scores / comments
    DEBATE = "debate"      # a turn in the Ustad<->Rasik argument
    VERDICT = "verdict"    # the Conductor rules (accept / revise)
    REVISE = "revise"      # a generator reworks
    RENDER = "render"      # audio produced


class DebateEvent(BaseModel):
    """One event the UI renders. Same shape whether live crew or replay."""
    type: EventType
    agent: str                                   # "Ustad", "Rasik", "Conductor", "RagaGrammar"...
    role: str                                    # "generator" | "critic" | "conductor" | "system"
    text: str = ""
    verdict: Optional[str] = None                # e.g. "legal"/"illegal", "accept"/"revise"
    scores: Optional[dict[str, float]] = None    # Rasik's rubric, etc.
    round: Optional[int] = None                  # which debate/revise round
    data: Optional[dict[str, Any]] = None        # violations, composition ref, ...


Sink = Callable[[DebateEvent], None]


def pretty_sink(e: DebateEvent) -> None:
    """Default sink: a readable one-liner for headless runs."""
    rnd = f"[r{e.round}] " if e.round is not None else ""
    tail = ""
    if e.verdict is not None:
        tail += f"  -> {e.verdict}"
    if e.scores:
        tail += "  " + " ".join(f"{k}={v}" for k, v in e.scores.items())
    print(f"{rnd}{e.type.value:9} {e.agent:12} {e.text}{tail}")


class EventStream:
    """Collects debate events and pushes each to a sink as it happens.

    The crew, the headless runner, and (Phase 3) the SSE endpoint all emit
    through this one object — swap the sink, keep the contract. `to_list()`
    serializes the whole run, which is exactly what the replay harness reads.
    """

    def __init__(self, sink: Optional[Sink] = None) -> None:
        self.events: list[DebateEvent] = []
        self._sink: Sink = sink or pretty_sink

    def emit(self, event: DebateEvent) -> DebateEvent:
        self.events.append(event)
        self._sink(event)
        return event

    def to_list(self) -> list[dict]:
        return [e.model_dump(mode="json") for e in self.events]
