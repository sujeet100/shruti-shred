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
from typing import Any, Callable, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from raga import RAGAS, SWARAS  # single source of truth for ragas + legal sargam symbols
from subgenres import SUBGENRES
from talas import TALAS


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


# Junk an LLM emits when it means "nothing here". Includes the reasoning phrases
# a chain-of-thought extractor can bleed into a value field ("not stated").
_NULLISH = {"", "null", "none", "n/a", "na", "unspecified", "unknown", "any",
            "not stated", "not specified", "none stated", "not applicable", "unstated"}


class RawIntent(BaseModel):
    """What the Interpreter LLM extracts — loose, only what the user actually said.

    Every field is optional: a null means "user didn't specify", NOT "guess".
    Grounded defaults are the deterministic resolver's job, never the model's.

    LLMs are unreliable at "leave it null" — they emit the string "null", or a
    sentinel like bpm -1, or an empty list. These validators normalize that junk
    back to real None at the boundary, so the resolver sees clean data.

    `reasoning` is declared FIRST on purpose: the model fills it before the value
    fields, so it must justify each field ("raga: not stated -> null") BEFORE
    committing — chain-of-thought in the structured output, which both disciplines
    the extraction and lets us SEE why it decided what it did.
    """
    reasoning: str = ""
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
    pass through as extracted. Every unstated dimension stays None = "open for the
    composers" — who pick the raga (from the mood), subgenre, tempo, and rest.

    Faithfulness — not inventing or echoing values — is the EXTRACTOR's job, carried
    by its reasoning-first prompt (the model justifies each field before committing;
    see tasks.yaml). This resolver only maps names onto the supported library and
    normalizes boundary junk (RawIntent's validators); it does not second-guess the
    model's extraction.
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
# Contract 0.5: Arrangement — the shared "chart" the composers agree on        #
#                                                                             #
# Pandit (tradition) and Riffsmith (metal) negotiate a plan; the structured    #
# output each turn is an ArrangementDraft — a SMALL set of DECISIONS (raga,     #
# subgenre, tala, tempo, section form). Deterministic code then EXPANDS a final #
# draft into the full Arrangement, DERIVING the mechanical detail the parallel  #
# generators need to interlock: the tala's accent grid, a shared motif from the #
# raga's pakad, and a register per voice. This is "code does the checkable, the #
# LLM does the rest" applied to the chart — the composers make the CREATIVE     #
# calls; code supplies the FACTS, so the plan is idiomatic AND collision-free   #
# by construction, not by hoping the LLM did the arithmetic right.             #
# --------------------------------------------------------------------------- #

# The layer roles a composition can carry (see render.py / Layer.role). `drums` is
# the metal kit; `tabla` is Hindustani percussion — the two are distinct voices and
# may play TOGETHER (tabla laying the theka under a metal groove is a core fusion
# sound). Rendering tabla is wired in step 4 (the Groove generator + render).
ROLES: frozenset[str] = frozenset({"drone", "lead", "rhythm", "drums", "tabla"})


class SectionKind(str, Enum):
    """The generators' section vocabulary — each maps to a generation MODE.

    A section's kind tells the (step-4) generators HOW to fill it: an `alaap` is a
    slow, drum-less raga exposition; a `taan` is a fast melodic climax; a
    `breakdown` is a sparse rhythmic crush. The composers choose the SEQUENCE of
    sections (the form); the kind fixes each block's character.
    """
    ALAAP = "alaap"          # slow, unmetered raga exposition (lead-led, no drums)
    RIFF = "riff"            # the main metal riff statement (rhythm-led)
    MELODY = "melody"        # the motif sung as a theme over the groove
    TAAN = "taan"            # fast, virtuosic melodic run — the climax
    SOLO = "solo"            # lead improvisation over the riff
    BREAKDOWN = "breakdown"  # heavy, sparse, rhythm + drums crush
    OUTRO = "outro"          # cadential resolution


class Section(BaseModel):
    """One block of the form: what kind, how long, who plays, who leads.

    `intent` is the composer's free-text creative direction for this block ("brood
    on the vadi", "half-time crush", "double-time taan to the climax"). `transition`
    describes the SEAM out of this block into the next ("tabla fades as feedback
    swells", "a tihai landing on sam") — fusion fails at the handoffs, so the
    composers design them explicitly. Both are optional shaping hints the step-4
    generators read; the section's `kind` alone is enough to render it.
    """
    kind: SectionKind
    bars: int = Field(ge=1)          # length in tala cycles
    layers: list[str]                # active roles this section (subset of ROLES)
    foreground: str                  # the role in the spotlight (must be active here)
    intent: str = ""                 # optional creative hint the composer writes
    transition: str = ""             # optional: how this section hands off to the next

    @field_validator("layers")
    @classmethod
    def _known_roles(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("a section must have at least one active layer")
        bad = [r for r in v if r not in ROLES]
        if bad:
            raise ValueError(f"unknown layer role(s) {bad} (expected {sorted(ROLES)})")
        return v

    @model_validator(mode="after")
    def _foreground_is_active(self) -> "Section":
        if self.foreground not in self.layers:
            raise ValueError(
                f"foreground {self.foreground!r} is not among the active layers {self.layers}")
        return self


class ArrangementDraft(BaseModel):
    """What a composer EMITS each turn — the composition, not the facts.

    The LLM is the composer: it makes the creative calls — raga/subgenre/tala/tempo,
    the section form, and the `motif` (the piece's melodic seed) — plus optional
    `registers` when it wants to voice the parts itself. Code never invents the
    music; it only DERIVES verified facts later (the tala's accent grid) and
    GUARDS the hard lines HERE at the boundary: the raga/subgenre/tala must be
    supported, and the motif must be LEGAL in the raga (its swaras in the raga's
    allowed set). A bad pick or an out-of-raga motif fails here and hands the
    guardrail a precise error to retry against. What CODE never lets the LLM
    decide is legality and the raga/tala facts — everything else is the composer's.
    """
    raga: str
    subgenre: str
    tala: str
    bpm: int = Field(gt=0)
    motif: list[str] = Field(min_length=1)   # the composer's melodic seed (legal in the raga)
    sections: list[Section] = Field(min_length=1)
    registers: Optional[dict[str, int]] = None   # optional: composer voices the parts itself

    @field_validator("raga")
    @classmethod
    def _known_raga(cls, v: str) -> str:
        if v not in RAGAS:
            raise ValueError(f"unknown raga '{v}' (expected one of {sorted(RAGAS)})")
        return v

    @field_validator("subgenre")
    @classmethod
    def _known_subgenre(cls, v: str) -> str:
        if v not in SUBGENRES:
            raise ValueError(f"unknown subgenre '{v}' (expected one of {sorted(SUBGENRES)})")
        return v

    @field_validator("tala")
    @classmethod
    def _known_tala(cls, v: str) -> str:
        if v not in TALAS:
            raise ValueError(f"unknown tala '{v}' (expected one of {sorted(TALAS)})")
        return v

    @field_validator("registers", mode="before")
    @classmethod
    def _blank_registers_to_none(cls, v):
        # The model often fills the optional field with an empty dict rather than
        # omitting it; treat that (any falsy value) as "not specified" so it doesn't
        # trip the register check during output_pydantic parsing.
        return v or None

    @model_validator(mode="after")
    def _shape_checks(self) -> "ArrangementDraft":
        # SHAPE + vocabulary only. Motif LEGALITY (in-raga) is a DOMAIN rule enforced
        # by the composer's guardrail (composers.py) and the final Arrangement — NOT
        # here — so output_pydantic can always parse a structurally-valid draft.
        _check_motif_symbols(self.motif)
        if self.registers is not None:
            _check_registers(self.registers)
        return self


class ComposerTurn(BaseModel):
    """One turn in the Pandit<->Riffsmith dialogue.

    `reasoning` is the composer's INTERNAL MONOLOGUE, filled FIRST (like the
    Interpreter's): it analyzes the counterpart's last turn — one element to respect,
    one to push back on — before drafting, which sharpens the revision and shows in
    the trace. `draft` is the evolving chart; `note` is the short public argument the
    transcript streams as a DEBATE event; `agree` lets the bounded loop exit early.
    The loop NEVER relies on `agree`: a turn cap always terminates it, and the
    Conductor arbitrates an un-agreed draft in step 6. `agree` is the shortcut; the
    cap is the guarantee.
    """
    reasoning: str = ""
    draft: ArrangementDraft
    note: str = ""
    agree: bool = False


class Accent(BaseModel):
    """One matra of the tala's accent skeleton — derived, never LLM-supplied."""
    matra: int                                      # 1-indexed beat in the cycle
    beat: float                                     # 0-indexed quarter-note beat position
    kind: Literal["sam", "tali", "khali", "beat"]   # stress role of this matra
    bol: str                                        # the theka syllable here


class Arrangement(BaseModel):
    """The full shared chart the parallel generators read.

    The composers' DECISIONS (raga/subgenre/tala/tempo/sections) plus the DERIVED
    facts that let independent generators interlock with no handoff: the tala
    `accent_grid` (so riff and kick land together), a `motif` seeded from the
    raga's pakad (shared melodic DNA), and a `register` per voice (so lead, riff
    and drone sit in different octaves and can't clash).
    """
    raga: str
    subgenre: str
    tala: str
    sa: int
    bpm: int = Field(gt=0)
    beats_per_bar: float                            # one tala cycle, in quarter-note beats
    sections: list[Section] = Field(min_length=1)
    accent_grid: list[Accent] = Field(min_length=1)
    motif: list[str] = Field(min_length=1)          # swaras drawn from the raga's pakad
    registers: dict[str, int]                       # base octave per voice
    notes: list[str] = Field(default_factory=list)

    @field_validator("raga")
    @classmethod
    def _known_raga(cls, v: str) -> str:
        if v not in RAGAS:
            raise ValueError(f"unknown raga '{v}' (expected one of {sorted(RAGAS)})")
        return v

    @field_validator("subgenre")
    @classmethod
    def _known_subgenre(cls, v: str) -> str:
        if v not in SUBGENRES:
            raise ValueError(f"unknown subgenre '{v}' (expected one of {sorted(SUBGENRES)})")
        return v

    @field_validator("tala")
    @classmethod
    def _known_tala(cls, v: str) -> str:
        if v not in TALAS:
            raise ValueError(f"unknown tala '{v}' (expected one of {sorted(TALAS)})")
        return v

    @model_validator(mode="after")
    def _cross_checks(self) -> "Arrangement":
        # the accent grid must cover exactly one full cycle of the chosen tala
        matras = TALAS[self.tala]["matras"]
        if len(self.accent_grid) != matras:
            raise ValueError(
                f"accent_grid has {len(self.accent_grid)} matras, but {self.tala} has {matras}")
        # the composer's motif MUST be legal in the raga, and the voices must not clash
        _check_motif_symbols(self.motif)
        illegal = motif_illegal_in_raga(self.motif, self.raga)
        if illegal:
            raise ValueError(f"motif swaras {illegal} are illegal in raga {self.raga} "
                             f"(allowed: {' '.join(RAGAS[self.raga]['allowed'])})")
        _check_registers(self.registers)
        return self


def _check_motif_symbols(motif: list[str]) -> None:
    """SHAPE: every motif entry is a known sargam symbol. Cheap, always-true for a
    well-formed draft — safe to run inside the Pydantic schema."""
    unknown = [sw for sw in motif if sw not in SWARAS]
    if unknown:
        raise ValueError(f"motif has unknown swara(s) {unknown}")


def motif_illegal_in_raga(motif: list[str], raga: str) -> list[str]:
    """DOMAIN: return the motif swaras that are NOT legal in the raga (empty == legal).

    Public because the composer's guardrail enforces this AFTER structured parsing.
    Legality is kept OUT of the Pydantic schema on purpose: `output_pydantic` must be
    able to parse a structurally-valid draft so the guardrail can turn an out-of-raga
    motif into a clean, retryable error instead of a parse-time crash. The final
    Arrangement re-checks it (see `Arrangement._cross_checks`).
    """
    allowed = set(RAGAS[raga]["allowed"])
    return [sw for sw in motif if sw not in allowed]


def _check_registers(reg: dict[str, int]) -> None:
    """Guardrail: every voice present, and lead >= rhythm >= drone so they don't clash."""
    missing = {"lead", "rhythm", "drone"} - set(reg)
    if missing:
        raise ValueError(f"registers missing voice(s) {sorted(missing)}")
    if not (reg["lead"] >= reg["rhythm"] >= reg["drone"]):
        raise ValueError(f"registers must keep lead >= rhythm >= drone (got {reg})")


def accent_grid(tala: str) -> list[Accent]:
    """Derive the tala's accent skeleton — one Accent per matra of one cycle.

    Pure: reads the encoded tala facts (talas.py) and marks each matra as the
    `sam` (the resolving downbeat, matra 1), a `tali` (clap), a `khali` (wave), or
    a plain `beat`. This is the grid riff and kick lock onto — knowledge as data,
    never an LLM guess.
    """
    t = TALAS[tala]
    tali, khali = set(t["tali"]), set(t["khali"])
    grid: list[Accent] = []
    for matra in range(1, t["matras"] + 1):
        if matra == t["sam"]:
            kind: Literal["sam", "tali", "khali", "beat"] = "sam"
        elif matra in tali:
            kind = "tali"
        elif matra in khali:
            kind = "khali"
        else:
            kind = "beat"
        grid.append(Accent(matra=matra, beat=float(matra - 1), kind=kind,
                            bol=t["theka"][matra - 1]))
    return grid


def motif_from_pakad(raga: str) -> list[str]:
    """A pakad SEED to hand the composer as inspiration — the raga's first pakad phrase.

    This is NOT the motif the chart uses; the composer writes that (and may quote,
    vary, or depart from this seed, as long as it stays legal). Step 3b feeds this
    into the composer's prompt so its motif is rooted in real raga idiom rather
    than invented from nothing.
    """
    return list(RAGAS[raga]["pakad"][0])


# How far above the riff's floor the lead sits, in octaves — enough that the
# melody clears the downtuned rhythm and they don't fight for the same register.
_LEAD_OCTAVES_ABOVE_RIFF: int = 2


def voice_registers(subgenre: str) -> dict[str, int]:
    """The DEFAULT base octave per voice when the composer doesn't voice the parts.

    Derived from the subgenre so voices can't clash: the riff sits at the
    subgenre's low (downtuned) octave, the lead sings a couple of octaves above,
    and the drone anchors the low end with the riff — lead >= rhythm >= drone. The
    composer may override this in its draft; this is the sane fallback.
    """
    riff_floor, _ = SUBGENRES[subgenre]["register"]
    lead = max(0, riff_floor + _LEAD_OCTAVES_ABOVE_RIFF)
    return {"lead": lead, "rhythm": riff_floor, "drone": riff_floor}


def build_arrangement(draft: ArrangementDraft, brief: CompositionBrief) -> Arrangement:
    """Expand a final composer draft into the full chart. Pure, no LLM.

    The composer's music carries through untouched — its motif, section form, and
    (if given) registers ARE the chart. Code does exactly two things: it honors
    what the USER fixed (a stated raga/subgenre/bpm overrides the draft; the key
    the Interpreter transcribed sets Sa, else the render-time default), and it
    DERIVES the one verified fact the LLM must not invent — the tala's accent
    grid. Registers fall back to a subgenre default only when the composer left
    them open. The motif's legality was already guarded on the draft and is
    re-checked on the Arrangement.
    """
    raga = brief.raga or draft.raga
    subgenre = brief.subgenre or draft.subgenre
    bpm = brief.bpm or draft.bpm
    sa = brief.sa if brief.sa is not None else DEFAULT_SA
    matras = TALAS[draft.tala]["matras"]
    return Arrangement(
        raga=raga, subgenre=subgenre, tala=draft.tala, sa=sa, bpm=bpm,
        beats_per_bar=float(matras),
        sections=draft.sections,
        accent_grid=accent_grid(draft.tala),
        motif=draft.motif,
        registers=draft.registers or voice_registers(subgenre),
    )


# --------------------------------------------------------------------------- #
# Contract 1: Composition                                                     #
# --------------------------------------------------------------------------- #

def _clean_meend(v):
    """Normalize an LLM `meend` value to a valid target (swara or {swara, oct}) or None.

    LLMs express "no glide" inconsistently — JSON null, an empty dict, or the STRING
    'null'/'none' — and CrewAI's Gemini provider hard-raises on an output_pydantic
    validation failure BEFORE any guardrail can retry, so a stray nullish meend would
    kill a whole generation. We normalize the junk at the boundary (as the intake does
    with `_NULLISH`); a genuinely unknown target swara still raises."""
    if v is None:
        return None
    sw = v.get("swara") if isinstance(v, dict) else v
    if sw is None or (isinstance(sw, str) and sw.strip().lower() in _NULLISH):
        return None
    if sw not in SWARAS:
        raise ValueError(f"unknown meend target '{sw}'")
    return v


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
        return _clean_meend(v)


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
# Contract 1.5: Generator section outputs                                     #
#                                                                             #
# What a melodic generator (Lead, and later Riff) EMITS for ONE section: a    #
# phrase of notes carrying DURATIONS, not absolute start times. The LLM is bad #
# at cross-section beat arithmetic and must not own it — so the model supplies #
# the musical content (which swaras, how long, which ornaments) and CODE lays  #
# the phrase onto the section's window (`generators.place_phrase`), adding the  #
# voice's register and truncating at the window edge. "LLM aims, code enforces."#
# `oct` is LOCAL to the voice's register (0 = home; +1 to climb for a climax). #
# --------------------------------------------------------------------------- #

class LeadNote(BaseModel):
    """One note in a Lead phrase — a swara with a duration, no absolute start.

    Same ornament vocabulary as `Note` (kan via `grace`, portamento via `meend`),
    validated identically so an out-of-symbol ornament fails at the boundary; but
    the timing is a `dur` the code sequences, and every octave here is LOCAL to the
    lead's register (`generators.place_phrase` adds the register base). `meend` is a
    bare swara (glide within the note's octave) OR `{"swara","oct"}` to glide ACROSS
    octaves — that `oct` is local, in the same frame as the note's `oct`, and is
    register-shifted at placement. Cross-octave glides (mandra<->taar) are core raga
    idiom, so the lead needs them.
    """
    swara: str
    oct: int = 0
    dur: float = Field(gt=0)
    vel: int = Field(default=90, ge=1, le=127)
    grace: Optional[list[str]] = None
    meend: Optional[Union[str, dict]] = None

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
        return _clean_meend(v)


class LeadPhrase(BaseModel):
    """The Lead generator's structured output for ONE section.

    `reasoning` is filled FIRST (chain-of-thought, like every other agent here):
    which pakad/chalan idiom the phrase builds on and how it is shaped to the
    section's role — disciplining the melody and showing in the trace. Legality
    (every swara in the raga) is NOT enforced here; it is the generator's guardrail
    (a bounded retry) so `output_pydantic` can always parse a well-formed phrase.
    """
    reasoning: str = ""
    notes: list[LeadNote] = Field(min_length=1)


class RiffNote(BaseModel):
    """One note of a metal riff — a swara with a duration, no ornaments (a riff
    chugs, it doesn't kan/meend). `oct` is LOCAL to the rhythm register; `vel`
    defaults loud. Timing is a `dur` the code lays on the tala grid."""
    swara: str
    oct: int = 0
    dur: float = Field(gt=0)
    vel: int = Field(default=110, ge=1, le=127)

    @field_validator("swara")
    @classmethod
    def _known_swara(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown swara '{v}' (expected one of {' '.join(SWARAS)})")
        return v


class RiffPattern(BaseModel):
    """The Riff generator's output for ONE section — ONE tala cycle of riff.

    The code repeats this cycle across the section's bars so every bar re-lands on
    the sam, and punches the notes that fall on accented matras so the riff locks to
    the kick. `reasoning` is filled FIRST (which swaras/motif the riff builds on, how
    it lands the accents). Legality is the generator's guardrail, not enforced here,
    so `output_pydantic` can always parse a well-formed pattern.
    """
    reasoning: str = ""
    notes: list[RiffNote] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Contract 1.75: Critic verdicts                                              #
#                                                                             #
# Ustad (legality) judges a finished Composition. The lesson lives in the type #
# split: legality is CHECKABLE, so CODE owns it — the deterministic            #
# validate_composition decides `verdict`/`violations`, and the LLM's output    #
# (UstadNarration) can only EXPLAIN, never DECLARE. The shell assembles the    #
# two into an UstadVerdict, so the headline can never be an LLM hallucination. #
# (Rasik's taste verdict, LLM-owned on a rubric, lands as the next step.)      #
# --------------------------------------------------------------------------- #

class Violation(BaseModel):
    """One illegal note the validator found — the structured shape of a
    `raga.validate_composition` entry (an out-of-raga swara in some voice)."""
    layer: str                                   # the voice the note is in
    swara: str                                   # the offending swara
    start_beat: float                            # where it sounds, in beats
    kind: str                                    # "note" | "grace" | "meend-target"
    reason: str                                  # why it is illegal (names the allowed swaras)


class UstadNarration(BaseModel):
    """Ustad's LLM output — the human EXPLANATION, and nothing that decides legality.

    There is deliberately NO verdict field here: Ustad cannot DECLARE a piece legal
    or illegal, because that is the deterministic validator's call, not the model's.
    `reasoning` (filled FIRST) notes what the validate_composition tool returned;
    `explanation` turns that into a musician's account. Code pairs this with the
    tool's authoritative result to build the UstadVerdict below.
    """
    reasoning: str = ""
    explanation: str = ""


class UstadVerdict(BaseModel):
    """The legality critic's verdict, ASSEMBLED by code (see `crew/ustad.py`).

    `verdict` and `violations` come straight from the deterministic
    `raga.validate_composition` — never from the LLM — so "code decides the
    checkable" holds even for the critic's headline. `explanation` is Ustad's
    narration. This flows to the Conductor (a legality conflict is what the debate
    arbitrates) and onto the event stream.
    """
    verdict: Literal["legal", "illegal"]
    violations: list[Violation] = Field(default_factory=list)
    explanation: str = ""
    reasoning: str = ""


class RasikScores(BaseModel):
    """Rasik's rubric — four aesthetic criteria on a FIXED 1-5 scale.

    The fixed, named, bounded scale is deliberate: it is the countermeasure to
    LLM-as-judge bias (verbosity, a gestalt "vibe" number). The model must commit a
    separate integer per named criterion, each justified against the encoded raga
    facts — criteria, not vibes.
    """
    pakad: int = Field(ge=1, le=5)      # is the raga's signature phrase present (literally or evoked)?
    idiom: int = Field(ge=1, le=5)      # does the line MOVE like the raga (chalan, ornaments, vadi)?
    mood: int = Field(ge=1, le=5)       # does the music serve the raga's rasa / samay?
    coherence: int = Field(ge=1, le=5)  # do the voices cohere as an ensemble (interlock, register, space)?


class RasikVerdict(BaseModel):
    """The taste critic's verdict — LLM-OWNED, the deliberate opposite of Ustad's
    code-owned legality verdict. Taste is not checkable, so here the model DOES judge;
    we discipline it (not replace it) with a fixed rubric and encoded-fact grounding.
    `reasoning` (filled FIRST) justifies each score from the evidence before it is
    committed; `scores` is the rubric; `notes` is the short actionable critique.
    """
    reasoning: str = ""
    scores: RasikScores
    notes: str = ""


# --------------------------------------------------------------------------- #
# Contract 1.9: The arbitration (Conductor)                                   #
#                                                                             #
# When the critics disagree over whether a finished piece should ship, the    #
# Conductor is the referee WITH A CLOCK. Legality is non-negotiable (code      #
# forces a revise on an illegal piece, no debate); the genuine judgment is the #
# AESTHETIC one — is Rasik's objection worth a revise, or is the piece good     #
# enough? A bounded Ustad<->Rasik debate feeds the Conductor's final ruling.   #
# The ruling drives the Flow's surgical revise (step 6b), which is why it names #
# ONE layer.                                                                   #
# --------------------------------------------------------------------------- #

class DebateTurn(BaseModel):
    """One critic's turn in the bounded Ustad<->Rasik arbitration debate.

    `reasoning` (filled FIRST) reads the other side; `argument` is the short in-character
    point the transcript streams as a DEBATE event; `stance` is what this critic wants;
    `target_layer` names the ONE voice to regenerate when the stance is revise.
    """
    reasoning: str = ""
    argument: str = ""
    stance: Literal["accept", "revise"]
    target_layer: Optional[str] = None


class ConductorRuling(BaseModel):
    """The Conductor's FINAL call on a critiqued composition — the referee's verdict.

    Always terminating by design (the round cap is the guarantee, not organic
    consensus). `directive` is accept or revise; on a revise, `layer` is the single
    voice to regenerate and `reason` is the SURGICAL directive a generator can act on
    (what to fix, not a vague complaint). `reasoning` weighs the two sides first.
    """
    reasoning: str = ""
    directive: Literal["accept", "revise"]
    layer: Optional[str] = None
    reason: str = ""


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
