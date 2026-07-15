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
from typing import Any, Callable, Final, Literal, Optional

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


# The playable tempo range — anything an LLM emits outside this is junk, not a choice
# (slower than 40 isn't a groove, faster than 300 isn't playable): the extractor nulls it
# (unstated), the composer draft REJECTS it (schema retry).
_BPM_MIN: Final = 40
_BPM_MAX: Final = 300


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
        # Junk includes IMPLAUSIBLE tempi, not just non-numbers: a live run saw the extractor
        # emit bpm=2 for a query that stated no tempo (its own reasoning said "not stated"),
        # and 2 bpm rendered a 53-minute WAV. Outside the playable range means "unstated".
        try:
            bpm = None if v is None else int(v)
        except (TypeError, ValueError):
            return None
        return bpm if bpm is not None and _BPM_MIN <= bpm <= _BPM_MAX else None

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


# The gat/song FORMAL role of a section — what it DOES in the composition's form, kept
# ORTHOGONAL to `kind` (kind = how to RENDER a block; form_role = its place in the gat).
# A gat-led piece STATES a `mukhada` (the recurring melodic+rhythmic head that resolves to
# the sam), develops it through `manjha` and a higher-register `antara`, brings the mukhada
# BACK (the SAME role recurring IS the return — no separate symbol), and reserves ONE
# `taan_long` for the peak; `taan_short` is a cadential filler, `tihai` a thrice-repeated
# cadence landing on the sam. A closed set (Literal), friendly to Gemini controlled generation.
FormRole = Literal[
    "intro", "mukhada", "manjha", "antara",
    "taan_short", "taan_long", "breakdown", "tihai", "outro",
]

# Which idea SEEDS the composition — the shared anchor both creative voices derive from, so
# one idea (not two colliding ones) runs through the piece. `gat_first`: the sitar mukhada is
# the source and the riff is its rhythmic reduction; `riff_first`: the riff is the source and
# the mukhada quotes its accented notes. A first-class DECISION the composers make (agents map
# to decisions, not instruments), not something code invents.
CompositionAnchor = Literal["gat_first", "riff_first"]


class Section(BaseModel):
    """One block of the form: what kind, how long, who plays, who leads.

    `intent` is the composer's free-text creative direction for this block ("brood
    on the vadi", "half-time crush", "double-time taan to the climax"). `transition`
    describes the SEAM out of this block into the next ("tabla fades as feedback
    swells", "a tihai landing on sam") — fusion fails at the handoffs, so the
    composers design them explicitly. Both are optional shaping hints the step-4
    generators read; the section's `kind` alone is enough to render it.

    `riff_slot` names WHICH riff the rhythm plays here — a small library ("main", "chorus",
    "breakdown"). Sections that share a slot REPLAY the same riff, so the main riff RECURS
    as a hook (a real song form, and a mukhda/refrain on the raga side); distinct slots get
    distinct riffs. Identity lives in the slot ("code owns the recurrence"), not in the LLM
    remembering to reprise; `None` falls back to the `kind`, so same-kind sections reuse one
    riff by default.

    `form_role` names the section's place in the GAT FORM (mukhada/manjha/antara/...), kept
    orthogonal to `kind`. It is `Optional` in the schema (so fixtures/demos need not set it),
    but the composer guardrail REQUIRES it and enforces the gat invariant (a mukhada that
    returns) — the same optional-in-schema / required-in-guardrail split as `riff_slot`.
    """
    kind: SectionKind
    bars: int = Field(ge=1)          # length in tala cycles
    layers: list[str]                # active roles this section (subset of ROLES)
    foreground: str                  # the role in the spotlight (must be active here)
    intent: str = ""                 # optional creative hint the composer writes
    transition: str = ""             # optional: how this section hands off to the next
    riff_slot: Optional[str] = None  # which named riff plays here ("main"/"chorus"/"breakdown");
                                     # sections sharing a slot REPLAY the same riff (recurrence).
                                     # None -> falls back to the section kind.
    form_role: Optional[FormRole] = None  # its place in the gat form (mukhada/manjha/antara/...);
                                          # required by the composer guardrail, not the schema.

    @field_validator("riff_slot", mode="before")
    @classmethod
    def _norm_slot(cls, v):
        # normalise to a lowercase label; blank/nullish -> None (fall back to the kind)
        if v is None:
            return None
        s = str(v).strip().lower()
        return s or None

    @field_validator("form_role", mode="before")
    @classmethod
    def _norm_form_role(cls, v):
        # absorb the nullish sentinels an LLM emits for "unset" so a blank doesn't trip the
        # Literal; a genuinely-unknown role still fails the Literal (fed back as a retry).
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
            return None
        return str(v).strip().lower()

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
    the section form, the `anchor` (which idea seeds the piece), and the `motif` (the
    piece's melodic seed) — plus optional `registers` when it wants to voice the parts itself. Code never invents the
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
    bpm: int = Field(ge=_BPM_MIN, le=_BPM_MAX)   # playable range — an absurd tempo is a schema retry
    anchor: CompositionAnchor = "gat_first"  # which idea seeds the piece (gat_first | riff_first)
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
    anchor: CompositionAnchor = "gat_first"         # which idea seeds the piece (carried from the draft)
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
# Lowest ABSOLUTE octave any rhythm-guitar note may sound at (~D2 at the default Sa); below
# this a distortion patch is a muddy sub-bass rumble that reads as (and collides with) the
# bass. PUBLIC because riff placement clamps each note here too: the register default alone
# proved insufficient — the riff LLM writes local `oct: -1` notes, which pushed roots to ~D1
# (heard as mud in the first live gat render; 62% of riff onsets were below D2).
RHYTHM_FLOOR: int = -2


def voice_registers(subgenre: str) -> dict[str, int]:
    """The DEFAULT base octave per voice when the composer doesn't voice the parts.

    Derived from the subgenre so voices can't clash: the riff sits at the
    subgenre's low (downtuned) octave, the lead sings a couple of octaves above,
    and the drone anchors the low end with the riff — lead >= rhythm >= drone. The
    composer may override this in its draft; this is the sane fallback.
    """
    riff_floor, _ = SUBGENRES[subgenre]["register"]
    lead = max(0, riff_floor + _LEAD_OCTAVES_ABOVE_RIFF)
    # Keep the rhythm GUITAR out of sub-bass: at oct -3 (~D1, 37 Hz) a distortion patch
    # is a muddy rumble that reads as bass, not a guitar. Floor it at -2 (~D2) so the
    # bass (an octave below it) owns the sub and the guitar keeps its crunch.
    rhythm = max(riff_floor, RHYTHM_FLOOR)
    return {"lead": lead, "rhythm": rhythm, "drone": riff_floor}


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
        anchor=draft.anchor,
        beats_per_bar=float(matras),
        sections=draft.sections,
        accent_grid=accent_grid(draft.tala),
        motif=draft.motif,
        registers=draft.registers or voice_registers(subgenre),
    )


# --------------------------------------------------------------------------- #
# Contract 1: Composition                                                     #
# --------------------------------------------------------------------------- #

def _clean_meend_swara(v):
    """Normalize an LLM `meend_swara` (the glide TARGET) to a legal swara or None.

    The meend target was once a `str | {swara, oct}` union — but Gemini's native
    controlled generation (`response_json_schema`) handles `anyOf`/union schemas poorly,
    so we flattened it to two flat scalar fields (`meend_swara` + `meend_oct`). This still
    absorbs the nullish sentinels an LLM emits for "no glide" (JSON null, '', 'null',
    'none'); a genuinely unknown target swara still raises."""
    if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
        return None
    if v not in SWARAS:
        raise ValueError(f"unknown meend target '{v}' (expected one of {' '.join(SWARAS)})")
    return v


# A rhythm-guitar playing technique the renderer maps to a MIDI gesture — the chug of
# a palm-mute, a slide/bend on the pitch wheel, or a softer legato attack. A closed set,
# so it validates at the boundary; shared by the riff contract and the render-time Note.
RiffTechnique = Literal["palm_mute", "slide", "long_slide", "pick_scrape", "bend",
                        "hammer_on", "pull_off"]


class Note(BaseModel):
    swara: str
    oct: int = 0
    start: float
    dur: float
    vel: int = 100
    grace: Optional[list[str]] = None            # kan (grace notes)
    meend_swara: Optional[str] = None            # glide TARGET swara (None = no glide)
    meend_oct: Optional[int] = None              # target's ABSOLUTE octave (None = the note's own octave)
    chord: Optional[list[str]] = None            # extra raga swaras sounded WITH the root (stacked up)
    technique: Optional[RiffTechnique] = None    # a rhythm-guitar articulation the renderer maps
    andolan: Optional[bool] = None               # a slow, shallow pitch OSCILLATION on this held note
                                                 # (Darbari komal g/d, Bhairav komal r/d) — code sets it
                                                 # deterministically on the raga's andolan swaras
    fade: Optional[bool] = None                  # a RING-OUT: expression decays across the note like a
                                                 # struck string dying away — code sets it on the intro's
                                                 # final Sa so the resolution rings into the reserved
                                                 # silence before the gat

    @field_validator("swara")
    @classmethod
    def _known_swara(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown swara '{v}' (expected one of {' '.join(SWARAS)})")
        return v

    @field_validator("grace", "chord")
    @classmethod
    def _known_extra_swaras(cls, v):
        bad = [g for g in (v or []) if g not in SWARAS]
        if bad:
            raise ValueError(f"unknown swara(s) {bad}")
        return v

    @field_validator("meend_swara", mode="before")
    @classmethod
    def _known_meend(cls, v):
        return _clean_meend_swara(v)


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
    pan: Optional[int] = None                     # MIDI CC10 stereo position, 0=L .. 64=C .. 127=R
    detune_cents: Optional[int] = None            # channel fine-tune (RPN 0,1) — decorrelates a double-track
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

# The sitar's right-hand mizrab (plectrum) STROKE — a closed set (Hindustani only; sources +
# verification tier recorded in DESIGN.md, step 5): `da` the strong stroke (inward/upward), `ra`
# the softer return, `diri` a fast da+ra DOUBLE-stroke (a PAIR), `darada` a da+ra+da TRIPLE-stroke
# (a TRIPLET), `chikari` a bright high-Sa drone-string accent (punctuation, not a melody pitch). A
# bol is a STROKE, not a subdivision — it carries no duration; rhythm comes from where it is placed,
# and a compound simply names 2 (diri) or 3 (darada) strokes. Code realises a bol as sitar
# ARTICULATION (crew/lead.py `apply_strokes`), never as pitch — orthogonal to `dur`, no renderer change.
Bol = Literal["da", "ra", "diri", "darada", "chikari"]

# A light DECORATIVE ornament the sitar flicks on a note — a small crushed neighbour-cluster
# wrapping the main note. `murki` is delicate and fast; `khatka` the same shape but sharper and
# heavier (source-verified: the distinction is WEIGHT, not the notes). Unlike andolan (a raga
# FACT code applies), these are an expressive CHOICE the LLM places; code realises the cluster
# from the raga's own scale neighbours (legal by construction) and gates it to ragas that use
# them (only Bhairavi, of our five). Sources + verification in DESIGN.md "Murki/khatka".
Ornament = Literal["murki", "khatka"]


class LeadNote(BaseModel):
    """One note in a Lead phrase — a swara with a duration, no absolute start.

    Same ornament vocabulary as `Note` (kan via `grace`, portamento via `meend_swara`),
    validated identically so an out-of-symbol ornament fails at the boundary; but the
    timing is a `dur` the code sequences, and every octave here is LOCAL to the lead's
    register (`generators.place_phrase` adds the register base). The glide is two flat
    fields (not a union — Gemini controlled generation dislikes `anyOf`): `meend_swara`
    is the target, and `meend_oct` its LOCAL octave (same frame as the note's `oct`,
    register-shifted at placement) — leave `meend_oct` None to glide WITHIN the note's
    octave, or set it to glide ACROSS octaves (mandra<->taar), core raga idiom.

    `rest` marks a SILENT beat (nyas / breathing space): it occupies its `dur` but sounds
    nothing (the code skips placing it), so a gat can rest on the sam or leave a gap for the
    tabla instead of the lead lengthening notes to fake a pause. When `rest` is true,
    `swara`/`grace`/`meend`/`bol` are ignored; set `swara` to any legal symbol (e.g. "S").
    The same field the Riff already carries (`RiffNote.rest`), added to the lead so a gat
    mukhada can breathe.
    """
    swara: str
    oct: int = 0
    dur: float = Field(gt=0)
    vel: int = Field(default=90, ge=1, le=127)
    grace: Optional[list[str]] = None
    meend_swara: Optional[str] = None
    meend_oct: Optional[int] = None
    bol: Optional[Bol] = None            # the mizrab stroke (da/ra/diri/chikari) — sitar articulation
    rest: bool = False                   # a SILENT beat (nyas/space) — occupies dur, sounds nothing
    ornament: Optional[Ornament] = None  # a murki/khatka flick — code realises the neighbour-cluster

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

    @field_validator("meend_swara", mode="before")
    @classmethod
    def _known_meend(cls, v):
        return _clean_meend_swara(v)

    @field_validator("bol", mode="before")
    @classmethod
    def _norm_bol(cls, v):
        # absorb nullish sentinels so a blank doesn't trip the Literal; an unknown bol still fails.
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
            return None
        return str(v).strip().lower()

    @field_validator("ornament", mode="before")
    @classmethod
    def _norm_ornament(cls, v):
        # same nullish absorption as bol; an unknown ornament still fails the Literal (retryable).
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
            return None
        return str(v).strip().lower()


# A phrase's overall shape, and the transformations that develop its seed — closed sets
# (Literal, friendly to Gemini's controlled generation) so the model picks from a fixed
# compositional vocabulary rather than inventing one.
LeadContour = Literal["ascending", "descending", "arch", "wave", "landing", "explosion"]
PhraseMove = Literal[
    "repeat", "sequence_up", "sequence_down", "invert", "fragment",
    "accelerate", "answer", "resolve", "octave_shift", "rhythmic_compression",
]


class PhrasePlan(BaseModel):
    """The compositional plan the Lead commits to BEFORE any notes — so a taan DEVELOPS one
    idea (the way a real improviser does) instead of running the scale (the "drunken
    staircase" a directionless model produces). This is reasoning-first made STRUCTURAL: the
    schema puts the plan ahead of the notes, so the model cannot emit a note without first
    declaring the seed it grows, the shape, and the transformations. The renderer ignores the
    plan — it steers the notes and shows the intent in the trace, while Rasik/Producer judge
    whether the notes actually honour it.
    """
    seed: list[str]                     # the core idea — 2-5 swaras, drawn from pakad/chalan
    contour: LeadContour                # the phrase's overall shape
    transformations: list[PhraseMove]   # how the seed evolves, in order
    climax_and_sam: str                 # one line: where energy peaks and how it resolves/lands
    # Taan architecture (a taan/solo section fills these too — optional so every other section,
    # and every existing fixture, is untouched). Kept as free strings, not Literals: the prompt
    # supplies the verified vocabulary, and a lenient field never burns a schema retry on a
    # stray-but-harmless value (the plan steers the model; code never executes it).
    taan_style: Optional[str] = None    # ONE dominant style for the whole taan (prompt lists the verified set)
    register_plan: Optional[str] = None  # the arc: where it starts, where the single peak lands, the descent
    rhythm_plan: Optional[str] = None    # the burst/space shape (e.g. "pickup, burst, held, burst, tihai")

    @field_validator("seed")
    @classmethod
    def _known_seed(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in SWARAS]
        if bad:
            raise ValueError(f"unknown seed swara(s) {bad} (expected from {' '.join(SWARAS)})")
        return v


class LeadPhrase(BaseModel):
    """The Lead generator's structured output for ONE section.

    `phrase_plan` is filled FIRST and is REQUIRED: the model commits to a seed, a contour,
    and the transformations that develop it BEFORE it may write a single note (reasoning-first
    made structural — see `PhrasePlan`). Legality (every swara in the raga, seed included) is
    NOT enforced here; it is the generator's guardrail (a bounded retry) so `output_pydantic`
    can always parse a well-formed phrase.
    """
    phrase_plan: PhrasePlan
    notes: list[LeadNote] = Field(min_length=1)


class RiffNote(BaseModel):
    """One note of a metal riff — a swara with a duration. A riff doesn't kan/meend,
    but it DOES voice chords and articulate the chug.

    `chord` stacks extra raga SWARAS above the root, each seated at the lowest octave over
    it and each legal in the raga (STRICT_RAGA — the distorted-guitar voicing stays inside
    the grammar; the guardrail enforces it). A chord tone is a raga swara stacked above the
    root, NOT a fixed interval: add the note's OWN swara for a true octave (root+octave —
    the power-chord weight), and `["P"]` is Pa (a genuine perfect FIFTH only above the tonic
    Sa; above another root it is whatever raga interval Pa sits at). `["g","n"]` is a stacked
    raga-colour voicing. `technique` names an articulation the renderer maps (palm_mute,
    slide, bend, hammer_on, pull_off).

    `rest` marks a SILENT beat: it occupies its `dur` but sounds nothing (the code skips
    placing it), so a riff can leave SPACE — rests, not wall-to-wall notes — for the tabla and
    the gat to speak. When `rest` is true, `swara`/`chord`/`technique` are ignored; set `swara`
    to any legal symbol (e.g. "S"). `oct` is LOCAL to the rhythm register; `vel` defaults loud;
    timing is a `dur` the code lays on the tala grid. Chord legality is the generator's
    guardrail, not enforced here, so `output_pydantic` can always parse a well-formed note."""
    swara: str
    oct: int = 0
    dur: float = Field(gt=0)
    vel: int = Field(default=110, ge=1, le=127)
    chord: Optional[list[str]] = None
    technique: Optional[RiffTechnique] = None
    rest: bool = False

    @field_validator("swara")
    @classmethod
    def _known_swara(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown swara '{v}' (expected one of {' '.join(SWARAS)})")
        return v

    @field_validator("chord")
    @classmethod
    def _known_chord(cls, v):
        bad = [c for c in (v or []) if c not in SWARAS]
        if bad:
            raise ValueError(f"unknown chord swara(s) {bad}")
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
# Contract 1.6: The collaboration canvas — the shared BLACKBOARD               #
#                                                                             #
# The talk's SECOND named multi-agent pattern (beside the critique loop):      #
# bounded COOPERATIVE collaboration. Today each voice is generated in          #
# ISOLATION (which is why the Producer even scores independence/balance); here #
# the two creative voices (Lead + Riff) build a section on ONE shared surface  #
# — a leader SEEDS it, the follower ANSWERS what it hears, and a bounded number #
# of REFINE turns follow. This model is the "blackboard": the working state     #
# every pass reads and writes back. WHO leads and WHEN to stop are decided in   #
# CODE (crew/studio.py — the "bandleader + clock"), never by the agents, so the #
# collaboration stays visible and terminating (not autonomous L4). The          #
# Drone/Bass/Drums/Tabla stay deterministic and arrange themselves AROUND the   #
# finished canvas, so only these two voices are ever LLM.                       #
# --------------------------------------------------------------------------- #

# The two LLM voices that collaborate, named by their LAYER role — the same
# strings Section.layers / VOICES / ConductorRuling.layer already use — so the
# canvas speaks the system's existing vocabulary rather than inventing its own.
CreativeRole = Literal["lead", "rhythm"]


class CanvasMove(str, Enum):
    """What a voice DOES on its turn at the canvas — a closed set so the schedule
    (crew/studio.py) and the event stream share one vocabulary.
    """
    PROPOSE = "propose"   # the leader seeds the section on the empty canvas
    RESPOND = "respond"   # the follower answers the leader's line
    REFINE = "refine"     # a voice reworks its own line given the full ensemble


# The section's higher-level musical intent, as closed VOCABULARIES (Literal — friendly
# to Gemini controlled generation, and a fixed set the follower and the deterministic
# voices can both read). These are the SEMANTIC layer of the blackboard: notes say HOW,
# these say WHAT the section is trying to do.
PhraseShape = Literal["question", "answer", "statement", "development", "climax", "resolution"]
Tension = Literal["rising", "falling", "steady", "suspended"]
Groove = Literal["straight", "syncopated", "gallop", "halftime", "free"]


class SectionIntent(BaseModel):
    """The section's shared musical INTENT — what the section is TRYING to do, above
    the level of notes. This is the "semantic ownership" layer of the blackboard.

    Authored by the LEADER when it proposes, and read by (a) the FOLLOWER — which
    answers the declared intent instead of reverse-engineering it from a note list —
    and (b) the DETERMINISTIC voices, so `energy`/`groove`/`tension` finally shape the
    drums, bass and dynamics (the piece's arc spine, previously only implicit in the
    notes). The note lines (`SectionCanvas.lead`/`.riff`) REALISE this intent.

    Ownership rule (enforced by the loop, crew/studio.py, not the schema): the leader
    AUTHORS this; a follower may PROPOSE an amendment on a refine turn, never silently
    overwrite it — which is what keeps a shared mutable surface coherent.

    Only known-SYMBOL checks live here (so parsing stays robust); RAGA-LEGALITY of
    `motif`/`target_resolution` is enforced by the authoring guardrail, exactly as the
    composer's motif and the generators' notes are (see `motif_illegal_in_raga`).
    """
    motif: list[str] = Field(default_factory=list)   # the motif CELL this section foregrounds — a quote/variation of the piece motif; EMPTY = inherit the shared arr.motif (so the two can't drift)
    phrase_shape: PhraseShape                         # the dialogic/structural role (question/answer/...)
    energy: int = Field(ge=1, le=10)                  # target intensity — the arc's explicit spine
    tension: Tension                                  # where the section's tension is heading
    target_resolution: str                            # the swara (nyas) the section leans toward
    groove: Groove                                    # the rhythmic feel the riff + drums lock to
    rhythm_pattern: list[float] = Field(default_factory=list)  # optional shared rhythmic cell (durations in beats) both voices accent

    @field_validator("motif")
    @classmethod
    def _known_motif_symbols(cls, v: list[str]) -> list[str]:
        _check_motif_symbols(v)
        return v

    @field_validator("target_resolution")
    @classmethod
    def _known_resolution(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown target_resolution swara '{v}' (expected one of {' '.join(SWARAS)})")
        return v

    @field_validator("rhythm_pattern")
    @classmethod
    def _positive_beats(cls, v: list[float]) -> list[float]:
        bad = [b for b in v if b <= 0]
        if bad:
            raise ValueError(f"rhythm_pattern durations must be positive beats, got {bad}")
        return v


class SectionCanvas(BaseModel):
    """The shared blackboard for ONE section — its shared INTENT plus each creative
    voice's CURRENT line, and who leads.

    The studio loop (crew/studio.py) seeds this, lets the follower respond, then
    (bounded) refines; the finished canvas is what the deterministic voices arrange
    around. `intent` is the semantic layer the leader authors (None until it does);
    `lead`/`riff` are the note lines that realise it — each starts empty and fills in
    as its voice plays, so a `None` line means "hasn't played yet", itself meaningful
    (an alaap's riff may stay silent). `log` is a human trace of the session for the
    event stream and the talk. Mutated IN PLACE during a session (Pydantic models are
    mutable by default) — transient working state, not a frozen value object.
    """
    index: int                                     # the section's position in the form
    kind: SectionKind
    start: float                                   # the section's window on the beat grid
    end: float
    leader: CreativeRole
    follower: CreativeRole
    intent: Optional[SectionIntent] = None         # the shared semantic layer (None until the leader authors it)
    lead: Optional[LeadPhrase] = None              # the lead's current line (None until it plays)
    riff: Optional[RiffPattern] = None             # the riff's current line (None until it plays)
    log: list[str] = Field(default_factory=list)   # who contributed what, in order

    @property
    def window(self) -> float:
        """The section's length in beats — what a voice aims to fill."""
        return self.end - self.start

    def line_for(self, role: CreativeRole) -> LeadPhrase | RiffPattern | None:
        """The voice's current line on the canvas, or None if it hasn't played yet.
        Lets the loop read 'the leader's line' / 'the follower's line' generically."""
        return self.lead if role == "lead" else self.riff


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
    """Rasik's rubric — the RAGA-AUTHENTICITY criteria on a FIXED 1-5 scale.

    Rasik owns exactly ONE dimension: does it sound like the raga? (Songwriting quality
    is the Producer's job; legality is Ustad's.) So the rubric is the uniquely Hindustani
    questions only. The fixed, named, bounded scale is the countermeasure to LLM-as-judge
    bias (verbosity, a gestalt "vibe" number): the model commits a separate integer per
    named criterion, each justified against the encoded raga facts — criteria, not vibes.
    """
    pakad: int = Field(ge=1, le=5)      # is the raga's signature phrase present (literally or evoked)?
    idiom: int = Field(ge=1, le=5)      # does the line MOVE like the raga (chalan, ornaments, vadi, expressive not scalar)?
    rasa: int = Field(ge=1, le=5)       # does the music serve the raga's emotional essence / samay?


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


class ProducerScores(BaseModel):
    """The Producer's rubric — COMPOSITION QUALITY on a FIXED 1-5 scale, raga-agnostic.

    The third critic dimension (Ustad=legality, Rasik=raga authenticity, Producer=does it
    WORK as a song). These are the songwriting/arrangement questions no one checked while
    Rasik was overloaded — each an integer the model must justify from the piece's actual
    structure, motif, riff and ensemble, grounded in code-computed metrics (`crew/metrics.py`).
    """
    structure: int = Field(ge=1, le=5)      # do the sections lead naturally into each other?
    dynamics: int = Field(ge=1, le=5)       # does the energy actually build (not flat all through)?
    climax: int = Field(ge=1, le=5)         # is there an earned peak and a resolution (an arc)?
    motif: int = Field(ge=1, le=5)          # is the motif developed — introduced, repeated, varied, resolved?
    hook: int = Field(ge=1, le=5)           # is the riff memorable, loopable, with a strong downbeat?
    balance: int = Field(ge=1, le=5)        # arrangement space — not every voice at full throughout?
    independence: int = Field(ge=1, le=5)   # does each voice contribute (lead != riff, bass != riff, drums != tabla)?
    mood_fit: int = Field(ge=1, le=5)       # does the whole piece hold the requested SUBGENRE mood?
    repetition: int = Field(ge=1, le=5)     # enough return (hook/motif reinforced) without becoming monotonous?


class ProducerVerdict(BaseModel):
    """The composition-quality critic's verdict — LLM-OWNED, like Rasik's (songwriting
    craft is judgment, not a checkable fact). `reasoning` (filled FIRST) justifies each
    score from the piece's structure/motif/riff/ensemble before it is committed; `scores`
    is the rubric; `notes` is the short actionable critique.
    """
    reasoning: str = ""
    scores: ProducerScores
    notes: str = ""


# --------------------------------------------------------------------------- #
# Contract 1.9: The arbitration (Conductor)                                   #
#                                                                             #
# When the critics disagree over whether a finished piece should ship, the    #
# Conductor is the referee WITH A CLOCK. Legality is non-negotiable (code      #
# forces a revise on an illegal piece, no debate); the genuine judgment is the #
# AESTHETIC one — SOUL (Rasik) vs WORKS-AS-MUSIC (Producer): is either worth a  #
# revise, or is the piece good enough? A bounded Rasik<->Producer debate feeds  #
# the Conductor's final ruling. The ruling drives the Flow's surgical revise    #
# (step 6b), which is why it names ONE layer.                                  #
# --------------------------------------------------------------------------- #

class DebateTurn(BaseModel):
    """One critic's turn in the bounded Rasik<->Producer arbitration debate.

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
    RUNNING = "running"    # a component STARTED working (streamed before its slow LLM work,
                           # so the UI can spotlight it + show a "composing…" placeholder;
                           # its real PROPOSE/CRITIQUE/etc. follows when it finishes)
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
