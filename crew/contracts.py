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

from pydantic import BaseModel, ValidationError, field_validator

from raga import SWARAS  # single source of truth for legal sargam symbols


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
