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
from typing import Any, Callable, Final, Literal, Optional, get_args

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from fretboard import LOWEST_OPEN
from gats import STROKE_HOLD
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
# A stated piece length, in seconds — outside this range it is junk, not a request (same rule
# as an implausible bpm: a 2-second or a 3-hour "piece" means the extractor misread).
_DURATION_MIN_S: Final = 10
_DURATION_MAX_S: Final = 1200

# Laya = the tempo CLASS a user may name (a Hindustani vocabulary word, not a bpm number). Kept as
# a separate field so "vilambit" isn't lost by the bpm validator; the composer reads it as guidance
# and picks an actual tempo within the subgenre's range.
_LAYAS: Final[dict[str, str]] = {
    "vilambit": "slow — pick a tempo at the SLOW end of the subgenre's range",
    "madhya": "medium — a tempo in the MIDDLE of the subgenre's range",
    "drut": "fast — a tempo at the FAST end of the subgenre's range",
}


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
    tala: Optional[str] = None          # a rhythmic cycle the user named (e.g. "teentaal")
    laya: Optional[str] = None          # a tempo class the user named (vilambit / madhya / drut)
    instruments: Optional[list[str]] = None
    duration_s: Optional[int] = None    # a piece length the user stated, in seconds
    playable_rhythm: Optional[bool] = None  # the user asked for a rhythm part a human can play

    @field_validator("raga", "key", "subgenre", "mood", "tala", "laya", mode="before")
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

    @field_validator("duration_s", mode="before")
    @classmethod
    def _bad_duration_to_none(cls, v):
        try:
            seconds = None if v is None else int(v)
        except (TypeError, ValueError):
            return None
        return seconds if seconds is not None and _DURATION_MIN_S <= seconds <= _DURATION_MAX_S else None

    @field_validator("playable_rhythm", mode="before")
    @classmethod
    def _only_true_counts(cls, v):
        # Only an explicit yes turns the constraint on; "false", junk and "not stated" all mean
        # "no constraint was asked for", which is the same thing as None.
        return True if v is True or (isinstance(v, str) and v.strip().lower() == "true") else None

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
    tala: Optional[str] = None         # kept only if the user named a SUPPORTED tala (else composers choose)
    laya: Optional[str] = None         # vilambit / madhya / drut, if the user stated a tempo class
    instruments: Optional[list[str]] = None  # only if the user named some
    mood: Optional[str] = None         # emotional vibe (e.g. angry, romantic) — a hint for the composers
    notes: list[str] = Field(default_factory=list)
    duration_s: Optional[int] = None   # a stated length in seconds — code turns it into an
                                       # avartan budget (crew/form_budget.py); None = open
    playable_rhythm: bool = False      # the rhythm guitar must be playable by a human on a six-
                                       # string in E standard (crew/riff_playability.py)
    request: str = ""                  # the user's words VERBATIM — copied by code, never by the
                                       # LLM, so what no field captures (form, ending, playability)
                                       # still reaches every agent that makes a musical decision

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

    @field_validator("tala")
    @classmethod
    def _known_tala(cls, v):
        if v is not None and v not in TALAS:
            raise ValueError(f"unknown tala '{v}' (expected one of {sorted(TALAS)})")
        return v

    @field_validator("laya")
    @classmethod
    def _known_laya(cls, v):
        if v is not None and v not in _LAYAS:
            raise ValueError(f"unknown laya '{v}' (expected one of {sorted(_LAYAS)})")
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


# Common English/roman-spelling variants for the tala names, so "teental"/"tintal" or a laya-prefixed
# phrase ("vilambit teentaal") still resolves to the supported key.
_TALA_ALIASES: Final[dict[str, str]] = {
    "teental": "teentaal", "tintal": "teentaal", "trital": "teentaal", "tritaal": "teentaal",
    "jhaptal": "jhaptaal", "japtal": "jhaptaal", "ektal": "ektaal",
    "rupaktaal": "rupak", "roopak": "rupak", "kaharwa": "keherwa", "kaherva": "keherwa",
}


def _match_tala(text: Optional[str]) -> Optional[str]:
    """Map a free-text tala name to a TALAS key, or None. Handles the key, the display name, common
    spellings, and a laya-prefixed phrase ("vilambit teentaal" -> teentaal)."""
    if not text:
        return None
    t = text.strip().lower()
    if t in TALAS:
        return t
    for key in TALAS:
        if key in t or TALAS[key]["display"].lower() in t:
            return key
    for alias, key in _TALA_ALIASES.items():
        if alias in t:
            return key
    return None


def _match_laya(text: Optional[str]) -> Optional[str]:
    """Map a free-text tempo word to a laya (vilambit / madhya / drut), or None. Accepts the
    Hindustani term or its English gloss (slow / medium / fast)."""
    if not text:
        return None
    t = text.strip().lower()
    aliases = {"vilambit": "vilambit", "vilambhit": "vilambit", "slow": "vilambit",
               "madhya": "madhya", "madhyalaya": "madhya", "medium": "madhya", "moderate": "madhya",
               "drut": "drut", "fast": "drut"}
    for alias, laya in aliases.items():
        if alias in t:
            return laya
    return None


def resolve_brief(intent: RawIntent, request: str = "") -> CompositionBrief:
    """Extract & validate ONLY what the user stated; invent nothing. Always succeeds.

    `request` is the user's original text, carried onto the brief untouched: the fields
    below are what the system can ENFORCE, the request is everything the user said.

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

    tala: Optional[str] = None
    if intent.tala:
        matched = _match_tala(intent.tala)
        if matched:
            tala = matched
        else:
            notes.append(f"tala {intent.tala!r} not supported {sorted(TALAS)} "
                         f"— left open for the composers")

    laya: Optional[str] = None
    if intent.laya:
        matched = _match_laya(intent.laya)
        if matched:
            laya = matched
        else:
            notes.append(f"laya {intent.laya!r} not recognized (vilambit/madhya/drut) — left open")

    return CompositionBrief(raga=raga, key=key, sa=sa, subgenre=subgenre,
                            bpm=intent.bpm, tala=tala, laya=laya,
                            instruments=intent.instruments, mood=intent.mood, notes=notes,
                            duration_s=intent.duration_s,
                            playable_rhythm=bool(intent.playable_rhythm),
                            request=request.strip())


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
ROLES: frozenset[str] = frozenset({"drone", "lead", "rhythm", "drums", "tabla", "clean",
                                   "orchestra"})


# How a section MOVES harmonically — the composers' per-section harmony decision
# (DESIGN.md "song-quality campaign" #1). Hindustani music is MELODIC — Sa's gravity is
# the music — so the modes are ordered by how much motion they dare: `drone` = none (the
# tanpura dyad is the harmony; alaap/taan-climax territory); `modal_pedal` = a Sa pedal
# under CHANGING legal colour tones (the raga-metal default — motion without leaving
# home); `progression` = a short root cycle for chorus-like sections ONLY, always
# resolving back to Sa. A Western V-I is never available by construction: roots are raga
# swaras, voicings are built up the raga's own ladder.
HarmonyMode = Literal["drone", "modal_pedal", "progression"]


# How a section's harmony BEHAVES (2026-10-12 harmony brief — Sujit: "a changing emotional
# landscape underneath the sitar, not the same two power chords; not a Western progression"):
# pedal = one tonal centre, colour only above it; slow = long chords with occasional movement;
# phrase = changes follow the sitar's arrivals; tension = suspended / fourth colours that resolve to
# home on the sam; breakdown = restrained harmony, heavier articulation. The composer chooses.
HarmonicBehaviour = Literal["pedal", "slow", "phrase", "tension", "breakdown"]
# The rhythm guitar's chord SHAPES (`crew/voicings.py` builds each inside the raga, falling back
# when a tone is illegal): power = root+5th+8ve; octave; fifth = open fifth; sus2; sus4;
# fourths = root+4th+8ve; triad = the raga's own third and fifth.
VoicingName = Literal["power", "octave", "fifth", "sus2", "sus4", "fourths", "triad"]


class ChordEvent(BaseModel):
    """One chord of a section's harmonic timeline: a raga swara as its root, a shape, and how many
    MATRAS it lasts (the tala's count — 8 + 4 + 2 + 2 in teentaal is "root, root, chord 2, chord 3
    -> chord 4"). Legality in the raga is the composer guardrail's; unknown symbols fail here."""
    root: str
    matras: float = Field(gt=0)
    voicing: VoicingName = "power"

    @field_validator("root")
    @classmethod
    def _known_root(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown swara '{v}' as a chord root")
        return v

    @field_validator("voicing", mode="before")
    @classmethod
    def _norm_voicing(cls, v):
        return str(v).strip().lower() if v is not None else "power"


class HarmonyPlan(BaseModel):
    """One section's harmony decision: the mode, plus its root/colour material.

    `roots` means: for `progression`, the per-avartan chord roots (2-4 raga swaras,
    the LAST one Sa — the cycle comes home); for `modal_pedal`, the colour tones
    rotated above the Sa pedal (empty = code defaults to the raga's vadi/samvadi);
    for `drone`, unused. Swara legality IN THE RAGA is the composer guardrail's job
    (the raga isn't known here); this schema only rejects unknown symbols."""
    mode: HarmonyMode = "modal_pedal"
    roots: list[str] = Field(default_factory=list)
    # The rhythm guitar's harmony (optional — absent, the chord floor's default shape plays):
    # how it behaves, and ONE avartan's chord timeline, repeated for each avartan of the section.
    behaviour: Optional[HarmonicBehaviour] = None
    chords: list[ChordEvent] = Field(default_factory=list)

    @field_validator("roots")
    @classmethod
    def _known_roots(cls, v: list[str]) -> list[str]:
        bad = [r for r in v if r not in SWARAS]
        if bad:
            raise ValueError(f"unknown swara(s) {bad} in harmony roots")
        return v


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
    "takeover",   # the GUITAR plays the gat's mukhada (code translates the realised head:
                  # crew/riff_from_mukhada.py `interpret_mukhada`) — not an independent riff
]

# How a peak (`taan_long`) section is REALISED under the metal band — orthogonal to its
# form_role (which says WHERE it sits). `driven` (the DEFAULT): the band DRIVES the climax —
# sustained ringing rhythm chords + climax drums hold the floor while the sitar/guitar taan
# TRADES over them (the metal-solo climax). `exposed`: the alap-style reveal — the band drops
# out of the taan's FINAL avartan so the sitar + tabla + drone carry the peak alone. Only
# consulted for the long taan (see crew/dynamics.py::apply_taan_exposure); ignored elsewhere.
ClimaxStyle = Literal["driven", "exposed"]

# Which idea SEEDS the composition — the shared anchor both creative voices derive from, so
# one idea (not two colliding ones) runs through the piece. `gat_first`: the sitar mukhada is
# the source and the riff is its rhythmic reduction; `riff_first`: the riff is the source and
# the mukhada quotes its accented notes. A first-class DECISION the composers make (agents map
# to decisions, not instruments), not something code invents.
CompositionAnchor = Literal["gat_first", "riff_first"]

# How the piece STOPS — a composer decision, realised by code (crew/ending.py). `ring_out`:
# the last section's sound simply decays (the old behaviour, the default). `hard_stop`: the
# whole band lands ONE stroke on the sam after the last section — the lead on taar Sa, guitar,
# bass and kit on low Sa — then silence. A tihai closing the final taan lands on that sam.
Ending = Literal["ring_out", "hard_stop"]

# The piece's overall FORM — a composer decision (Sujit, 2026-10-11: the gat is OPTIONAL). `gat`:
# the Hindustani instrumental form (intro/alap, a mukhada stated and RETURNED, manjha, antara,
# the long taan) — the guardrail enforces its structure. `song`: a metal song built on ONE main
# riff (intro -> main riff -> development -> contrast -> the riff RETURNS -> climax -> ending);
# its sections ride `kind` + `riff_slot` recurrence, `form_role` optional and never a gat-only
# role. The default keeps every existing chart a gat.
SongForm = Literal["gat", "song"]


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
    harmony: Optional[HarmonyPlan] = None  # how this section moves harmonically (drone /
                                           # modal_pedal / progression) — read by the CLEAN
                                           # guitar (crew/harmony.py); None = modal_pedal
                                           # defaults when a clean layer plays.
    climax_style: ClimaxStyle = "driven"  # how a taan_long peak is realised: `driven` (the band
                                          # DRIVES the climax — the default, metal-solo side) or
                                          # `exposed` (the alap-style band-drop reveal). Ignored
                                          # off a taan_long. See dynamics.py::apply_taan_exposure.
    tihai: bool = False                   # close this taan_long with a code-built TIHAI. OPT-IN
                                          # (Sujit, 2026-10-12): forced on every long taan, it
                                          # replaced the final avartan, so the climb peaked early,
                                          # ended on a repeated low cell and left a gap before the
                                          # sam. By default the taan flows straight into the sam.

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

    @field_validator("climax_style", mode="before")
    @classmethod
    def _norm_climax_style(cls, v):
        # a blank / nullish value from an LLM defaults to the metal-solo `driven`; a genuinely
        # unknown value still fails the Literal (fed back as a retry).
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
            return "driven"
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
    ending: Ending = "ring_out"              # how the piece stops (ring_out | hard_stop)
    form: SongForm = "gat"                   # the overall form (gat | song)
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

    @field_validator("form", mode="before")
    @classmethod
    def _norm_form(cls, v):
        # nullish -> the default gat; an unknown value still fails the Literal (a retry)
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
            return "gat"
        return str(v).strip().lower()

    @field_validator("ending", mode="before")
    @classmethod
    def _norm_ending(cls, v):
        # nullish -> the default ring-out; an unknown value still fails the Literal (a retry)
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH):
            return "ring_out"
        return str(v).strip().lower()

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
    ending: Ending = "ring_out"                     # how the piece stops (carried from the draft)
    form: SongForm = "gat"                          # the overall form (carried from the draft)
    playable_rhythm: bool = False                   # the riff must be playable by a human (from the brief)
    beats_per_bar: float                            # one tala cycle, in quarter-note beats
    sections: list[Section] = Field(min_length=1)
    accent_grid: list[Accent] = Field(min_length=1)
    motif: list[str] = Field(min_length=1)          # swaras drawn from the raga's pakad
    registers: dict[str, int]                       # base octave per voice
    notes: list[str] = Field(default_factory=list)
    request: str = ""                               # the user's words verbatim (from the brief) —
                                                    # every downstream agent reads it off the chart
    # THE SONG'S SEED — the core idea, carried on the chart so every later call (develop AND
    # revise) is handed it instead of nothing. Set at seed time by the single Composer
    # (crew/composer.py); on the legacy path the Flow stores the REALIZED head + main riff here
    # after the first generation (`anchor.with_realized_seeds`). None = no seed yet.
    seed_riff: Optional[RiffPattern] = None         # ONE cycle of the main riff (the slot that recurs)
    seed_hook: Optional[LeadPhrase] = None          # ONE avartan: the mukhada (gat) / the sitar's hook (song)
    seed_head: Optional[HeadIdea] = None            # GAT form: the head's IDEA the gat call composes from
    energy_arc: str = ""                            # the Composer's plan for how intensity moves
    # The COMPOSED rhythm section (guitar + bass, written from the placed sitar — crew/rhythm_voice.py),
    # carried on the chart like the seeds so assembly realises its bass and a riff revise edits it
    # section by section. None = the per-section riff path (the bass derived by code).
    rhythm_section: Optional[RhythmSection] = None

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
    # The clean guitar arpeggiates the harmony BETWEEN the wall and the raga line — an
    # octave under the lead (never below the riff), so its broken chords shimmer in the
    # mid-range without crowding either voice.
    # The orchestra's strings sing at the lead's height (clear of the rhythm wall); the
    # expander seats the low strings an octave under this base and the high strings/counter
    # at or above it, so the section reads as a full string spread without crowding a voice.
    return {"lead": lead, "rhythm": rhythm, "drone": riff_floor,
            "clean": max(lead - 1, rhythm), "orchestra": lead}


def _playable(registers: dict[str, int], sa: int, playable: bool) -> dict[str, int]:
    """When a human will play the rhythm part, seat its home octave where its Sa is a real
    guitar note: the lowest octave whose Sa sits at or above the open low string (E2). In E
    that is exactly the open low E; in a lower key it lifts the riff an octave rather than
    asking for a note below the instrument."""
    if not playable:
        return registers
    lowest = -((sa - LOWEST_OPEN) // 12)          # smallest oct with sa + 12*oct >= LOWEST_OPEN
    return {**registers, "rhythm": max(registers.get("rhythm", RHYTHM_FLOOR), lowest)}


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
        ending=draft.ending,
        form=draft.form,
        playable_rhythm=brief.playable_rhythm,
        beats_per_bar=float(matras),
        sections=draft.sections,
        accent_grid=accent_grid(draft.tala),
        motif=draft.motif,
        registers=_playable(draft.registers or voice_registers(subgenre), sa,
                            brief.playable_rhythm),
        request=brief.request,
    )


# --------------------------------------------------------------------------- #
# Contract 1: Composition                                                     #
# --------------------------------------------------------------------------- #

_REST_SPELLINGS: Final = frozenset({"rest", "silence", "-"})


def _rest_as_swara(data: Any) -> Any:
    """A silence the model spelled as `"swara": "rest"` instead of `"rest": true`, read as the rest
    it means. The 2026-10-12 live run died on it: three such notes in one lead phrase failed the
    swara check, the parse raised, and the whole Flow stopped — for a spelling, not a fault."""
    if isinstance(data, dict) and str(data.get("swara", "")).strip().lower() in _REST_SPELLINGS:
        return {**data, "swara": "S", "rest": True}
    return data


def _clean_meend_swara(v):
    """Normalize a `meend_swara` (the glide TARGET) to a legal swara or None.

    The meend target was once a `str | {swara, oct}` union — but Gemini's native
    controlled generation (`response_json_schema`) handles `anyOf`/union schemas poorly,
    so we flattened it to two flat scalar fields (`meend_swara` + `meend_oct`). It absorbs
    the nullish sentinels an LLM emits for "no glide" (JSON null, '', 'null', 'none') AND
    any junk that isn't a swara at all — the note then plays plain, without the glide.

    ABSORB, DON'T RAISE (2026-07-20 live failure): a raising validator here fires inside
    the provider's structured-output validation — BEFORE any guardrail/verify feedback
    loop can see it — so one junk value (a live run emitted ':' as a target) killed the
    entire compose. A meend is an OPTIONAL ornament: junk degrades to no-ornament; only
    the core fields (the note's own swara) may be strict. In-vocabulary-but-illegal
    targets are still caught by the raga guardrail, which DOES feed back."""
    if not isinstance(v, str) or v.strip().lower() in _NULLISH or v not in SWARAS:
        return None
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
    bend_st: Optional[int] = None                # a bend's rise in semitones — code stamps the
                                                 # RAGA-AWARE depth (the next swara enterable from
                                                 # below, raga.ascent_step) so the apex never holds
                                                 # an out-of-raga pitch; None = renderer default
    andolan: Optional[bool] = None               # a slow, shallow pitch OSCILLATION on this held note
                                                 # (Darbari komal g/d, Bhairav komal r/d) — code sets it
                                                 # deterministically on the raga's andolan swaras
    andolan_st: Optional[float] = None           # the sway's signed depth in semitones — negative swings
                                                 # BELOW, positive ABOVE (code stamps it from the raga's
                                                 # ANDOLAN_TOWARD); None = the renderer's default dip
    andolan_swings: Optional[tuple[int, int]] = None  # the (fewest, most) swings the raga's andolan
                                                 # takes (raga.ANDOLAN_SWINGS, Darbari 2-3; code-set);
                                                 # None = the renderer's default one or two
    meend_style: Optional[Literal["quick", "slow"]] = None  # how the glide moves: a quick gat pull
                                                 # (None/quick) or a slow alap meend that holds the source
                                                 # and pauses on the raga swaras it passes (code-set)
    gamak_st: Optional[int] = None               # a GAMAK: forceful repeated swings up to the raga
                                                 # swara this many semitones above, with audible stops
                                                 # on each (code-set in the climax taan)
    fade: Optional[bool] = None                  # a RING-OUT: expression decays across the note like a
                                                 # struck string dying away — code sets it on the intro's
                                                 # final Sa so the resolution rings into the reserved
                                                 # silence before the gat
    gamak_with: Optional[str] = None             # a GAMAK cell: swing with this adjacent swara (code
                                                 # splits the note into strokes, each a measured swing)
    gesture: Optional[str] = None                # a measured raga GESTURE this note is played with
                                                 # (src/gestures.py, e.g. "ga_ma_loop") — code-set
    pitch_path: Optional[list[list[float]]] = None  # that gesture resolved: [[ms after the note sounds,
                                                 # semitones from the swara], ...] — the renderer draws it
    fade_tail: Optional[float] = None            # a RING-OUT over only the note's LAST this-many beats —
                                                 # the piece's `ring_out` ending: a drone held for the
                                                 # whole piece decays at the end, not from its attack
    cents: Optional[float] = None                # the swara's own INTONATION off equal temperament
                                                 # (an ati-komal Ga) — code-set from raga data, drawn
                                                 # under every gesture the note carries
    chikari: Optional[bool] = None               # a CHIKARI stroke the composer wrote (bol "chikari",
                                                 # or the jhala's), marked at placement so the band
                                                 # lifts it off the melody onto the chikari layer
                                                 # (crew/chikari.py) — never a melody pitch

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

# The sitar's right-hand mizrab (plectrum) STROKE WORD — a closed set, the Imdadkhani inventory
# (Parikh; the data and its sources live in src/gats.py `BOL_WORDS`): `da` the strong inward
# stroke, `ra` the softer return, and the COMPOUNDS, each a stroke pattern given as RATIOS that divide
# the note's length — `dir` di:r 1:1, `dara` 1:1, `dar` da:r 2:1, `dadir` 2:1:1, `darada` 1:1:1,
# `daradara` 1:1:1:1 — every stroke plucked on the note's swara (many bols can share a matra);
# `chikari` a bright high-Sa drone-string accent (punctuation, not a melody pitch). Code realises a
# bol as sitar ARTICULATION (crew/lead.py `apply_strokes`), never as pitch. The compounds were
# `diri`/`darada` until 2026-10-12, and `diri` split whatever length its note had — the compressed
# reading Sujit had already corrected in Swarmatra; `diri` still parses, as `dir`. `rda` (r:da 1:1, the
# mirror of dir) joined 2026-10-12 from Parikh's "Origin of the Sitar" — his four basic strokes.
Bol = Literal["da", "ra", "dir", "rda", "dara", "dar", "dadir", "darada", "daradara", "chikari"]

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
    bol: Optional[Bol] = None            # the mizrab stroke word (da/ra/dir/dar/...) — sitar articulation
    rest: bool = False                   # a SILENT beat (nyas/space) — occupies dur, sounds nothing
    ornament: Optional[Ornament] = None  # a murki/khatka flick — code realises the neighbour-cluster
    gamak_with: Optional[str] = None     # a GAMAK: swing fast between this swara and that ADJACENT
                                         # raga neighbour for the note's length — code plays the swing

    @model_validator(mode="before")
    @classmethod
    def _rest_spelling(cls, data: Any) -> Any:
        return _rest_as_swara(data)

    @field_validator("swara")
    @classmethod
    def _known_swara(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown swara '{v}' (expected one of {' '.join(SWARAS)})")
        return v

    @field_validator("grace")
    @classmethod
    def _known_grace(cls, v):
        # ABSORB junk (see _clean_meend_swara): keep the legal grace swaras, drop the rest —
        # a kan is an optional ornament; junk in it must never kill the parse.
        if not v:
            return v
        kept = [g for g in v if g in SWARAS]
        return kept or None

    @field_validator("meend_swara", mode="before")
    @classmethod
    def _known_meend(cls, v):
        return _clean_meend_swara(v)

    @field_validator("bol", mode="before")
    @classmethod
    def _norm_bol(cls, v):
        # Normalize the stroke: nullish sentinels and junk both absorb to None (an unknown
        # stroke plays plain — see _clean_meend_swara for why raising here is fatal). The old
        # note-level name `diri` reads as `dir`; `dara` is its OWN word (two strokes) — it used
        # to be mapped to `darada` (three), which played a da-ra as a triplet.
        if v is None or not isinstance(v, str):
            return None
        s = v.strip().lower().replace("-", "").replace(" ", "")
        s = {"diri": "dir"}.get(s, s)
        return s if s in get_args(Bol) else None

    @field_validator("ornament", mode="before")
    @classmethod
    def _norm_ornament(cls, v):
        # same absorption as bol: nullish or unknown -> no ornament, never a dead parse.
        if v is None or not isinstance(v, str):
            return None
        s = v.strip().lower()
        return s if s in get_args(Ornament) else None

    @field_validator("gamak_with", mode="before")
    @classmethod
    def _known_gamak_partner(cls, v):
        # same absorption: junk plays plain. Raga-fit (adjacent, direction-legal) is checked
        # where the raga is known — `gestures.gamak_partner_ok`.
        return v if isinstance(v, str) and v in SWARAS else None


# A phrase's overall shape, and the transformations that develop its seed — closed sets
# (Literal, friendly to Gemini's controlled generation) so the model picks from a fixed
# compositional vocabulary rather than inventing one.
LeadContour = Literal["ascending", "descending", "arch", "wave", "landing", "explosion"]
PhraseMove = Literal[
    "repeat", "sequence_up", "sequence_down", "invert", "fragment",
    "accelerate", "answer", "resolve", "octave_shift", "rhythmic_compression",
]


def _stroke_tokens(v):
    """A stroke line as tokens — from a string ("da - dir da | ...") or a list: vibhag bars dropped,
    dashes unified, `diri` read as `dir`. Anything that is not a sequence absorbs to None, and junk
    tokens are kept as written for the checks to report (a lenient plan never dead-parses)."""
    if isinstance(v, str):
        v = v.split()
    if not isinstance(v, list):
        return None
    tokens = [str(t).strip().lower() for t in v]
    tokens = [{"diri": "dir", "–": "-", "—": "-", ".": "-", "_": "-"}.get(t, t)
              for t in tokens if t and t != "|"]
    return tokens or None


HEAD_STAGES: Final = ("figure", "breather", "response", "approach")


class HeadStage(BaseModel):
    """One stage of a gat head's SHAPE — what that stretch of the avartan is FOR (GPT's second
    review of `fusion_20261012_152048`, and Sujit's "a fast section followed by a slow part which
    is the breather"): a quick FIGURE that builds anticipation, a held BREATHER that releases it
    on one swara, an optional RESPONSE that develops the figure, the APPROACH that lands the sam.
    Planned before the notes so the head is composed as one thought with contrasting speeds, not
    as equal blocks joined end to end. Lenient like the rest of the plan: an unknown stage name or
    an odd length is kept as written and reported by `gat_verifier.check_head_plan`."""
    stage: str                                # figure / breather / response / approach
    beats: float                              # how long the stage lasts, in beats
    target: Optional[str] = None              # the swara it lands on or holds (the breather's)
    ornament: Optional[str] = None            # e.g. andolan / meend / gamak / plain

    @field_validator("stage", mode="before")
    @classmethod
    def _norm_stage(cls, v):
        return str(v).strip().lower()


TAAN_PHRASE_ROLES: Final = ("statement", "build", "climax", "cadence")
TAAN_SUBDIVISIONS: Final = (2, 3, 4, 6)   # notes per matra: dugun, tigun, chaugun, chhagun


class TaanPhrase(BaseModel):
    """One phrase of a taan's RHYTHMIC PLAN (the review of `excerpt_233435_taan_revised`: the taan
    alternated fast clusters with held notes at random, so it read as disconnected phrases). A
    taan flows at ONE pulse per phrase and changes speed deliberately, at a phrase boundary — so
    the plan names each phrase's job, its length, its pulse and how high it reaches, in order:
    a statement of the motif launched straight at chaugun, builds that widen the range, ONE climax
    in the later part, and a cadence that keeps the momentum into the sam. `gat_verifier.check_taan` holds the notes to
    it. Lenient like the rest of the plan: a stray role or pulse is kept and reported there."""
    role: str                                 # statement / build / climax / cadence
    beats: float                              # the phrase's length, in whole matras
    subdivision: int                          # its pulse, notes per matra (4 chaugun, 6 chhagun)
    reach: Optional[str] = None               # the highest swara it climbs to...
    reach_oct: Optional[int] = None           # ...and that swara's octave (0 madhya, +1 taar)

    @field_validator("role", mode="before")
    @classmethod
    def _norm_role(cls, v):
        return str(v).strip().lower()


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
    rhythm_plan: Optional[str] = None    # legacy free-text shape; a taan now plans `taan_phrases`
    taan_phrases: Optional[list[TaanPhrase]] = None  # taan only: its phrases in order (see TaanPhrase)
    # Intro/alap architecture (the aochar fills this too — same optional-free-string pattern as
    # the taan fields above). The intro develops ONE recurring motif (its `seed`, drawn from the
    # mukhada head) rather than inventing independent phrases; this names the reveal.
    badhat_plan: Optional[str] = None   # intro only: the progressive reveal — the fragment phrase 1 states, what each later phrase adds, where the widest reach lands
    # Gat head architecture: the RIGHT HAND planned before the notes — one token per matra of the
    # avartan (a bol word, "chikari", or "-" for a matra with no new stroke), so the rhythm is
    # composed as a PATTERN (the gat's identity) rather than decorated note by note. Lenient like
    # the fields above: junk is kept as written and reported by `check_stroke_line`, never a dead parse.
    stroke_line: Optional[list[str]] = None
    # ...and its SHAPE, planned with it: the stages in order (`HeadStage`), summing to the avartan.
    head_shape: Optional[list[HeadStage]] = None

    @field_validator("stroke_line", mode="before")
    @classmethod
    def _norm_stroke_line(cls, v):
        return _stroke_tokens(v)

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


class Gat(BaseModel):
    """The whole gat as ONE composition (the way a musician conceives it — Pandit Arvind Parikh's
    FOUR-line model: mukhada -> manjha -> antara -> amad). The lines are generated TOGETHER, in a
    single LLM call, so they share a motif and a PLANNED REGISTER ARC — the mukhada in the madhya
    (home), the manjha dipping into the mandra (the low bridge), the antara lifting into the taar
    (the second theme), and the amad composing the DESCENT that "brings you down to the point
    where the composition started" — instead of lines composed in isolation that only happen to
    be in the same raga. The full circuit spans the tradition's 2.5-3 octaves.

    `manjha`/`antara`/`amad` are optional: an arrangement may omit any, and only the parts it
    needs are generated (the amad rides the antara section's final avartan, so it exists only
    when an antara section has room for it). Legality is the generator's guardrail (as for
    LeadPhrase); each part is then held to its own gat verifier, and a part that fails is
    repaired IN ISOLATION (the others held fixed) — nobody rewrites a whole gat because one
    antara phrase isn't convincing.
    """
    anchor: str = ""                              # the ONE idea seeding all the parts (a short note to self)
    mukhada: LeadPhrase
    manjha: Optional[LeadPhrase] = None
    antara: Optional[LeadPhrase] = None
    amad: Optional[LeadPhrase] = None             # the composed descent re-entering the head


class HeadIdea(BaseModel):
    """The IDEA of a gat head — what the single Composer's seed writes in the GAT form instead of a
    finished avartan (Sujit's Option A, 2026-10-12). The head is the piece's most important object,
    and written as one-fifth of the seed's JSON beside the chart and the riff it got the least
    attention of anything there, then was copied verbatim forever. So the seed fixes what makes the
    head THIS head — the swara on every sam, the recurring cell, the right hand's stroke line — and
    the gat call composes the notes from it with its full attention, beside the manjha and antara
    it must share a motif with. Legality (every swara in the raga) is the seed guardrail's; whether
    the composed head kept the idea is MEASURED (`gat_verifier.check_head_idea`), never enforced."""
    idea: str = ""                                # one line: what the head is
    sam_swara: str                                # the swara that sounds ON every sam (the head's first note)
    cell: list[str] = Field(min_length=1)         # the recurring core cell — a few swaras
    stroke_line: Optional[list[str]] = None       # the right hand, one token per matra (as PhrasePlan's)

    @field_validator("stroke_line", mode="before")
    @classmethod
    def _norm_stroke_line(cls, v):
        # A chikari never sits inside a gat head (GAT_COMPOSITION.md §3.1 rule 6; HARD in
        # `gat_verifier.check_head_shape`). The idea is the seed's and is copied into the head, so
        # a chikari matra here would push the head into a paid repair; it is read as what the
        # head must do instead, a held matra the previous note rings through.
        tokens = _stroke_tokens(v)
        return [STROKE_HOLD if t == "chikari" else t for t in tokens] if tokens else tokens


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
    single: Optional[bool] = None   # a deliberate SINGLE NOTE (a melodic line on guitar) — never
                                    # voiced into a power chord (`riff_voicing.voice_note`)

    @model_validator(mode="before")
    @classmethod
    def _rest_spelling(cls, data: Any) -> Any:
        return _rest_as_swara(data)

    @field_validator("swara")
    @classmethod
    def _known_swara(cls, v: str) -> str:
        if v not in SWARAS:
            raise ValueError(f"unknown swara '{v}' (expected one of {' '.join(SWARAS)})")
        return v

    @field_validator("chord")
    @classmethod
    def _known_chord(cls, v):
        # ABSORB junk (see _clean_meend_swara): keep the legal chord tones, drop the rest —
        # a thinner voicing beats a dead parse; raga legality of the kept tones is the
        # guardrail's job (which feeds back, unlike a raising validator here).
        if not v:
            return v
        kept = [c for c in v if c in SWARAS]
        return kept or None

    @field_validator("technique", mode="before")
    @classmethod
    def _norm_technique(cls, v):
        # nullish or unknown -> no technique, never a dead parse (same rule as LeadNote.bol).
        if v is None or not isinstance(v, str):
            return None
        s = v.strip().lower()
        return s if s in get_args(RiffTechnique) else None


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


class SectionPart(BaseModel):
    """The rhythm section's part for ONE section of the chart — written by the rhythm-section call
    AFTER the sitar line exists, seeing it note by note (`crew/rhythm_section.py`).

    `role` comes first: what the guitar does here and why (supports a held note, drives, breathes,
    answers, lifts). `guitar` and `bass` are avartan CYCLES in the riff's note format (durations
    filling one cycle each; `oct` local to the voice's register): cycle i plays bar i, and a
    section longer than its cycles repeats the last one. `same_as` replays another section's part
    exactly — how the head's part recurs identically with every return of the mukhada. A section
    with no bass cycles takes the bass code derives from its guitar."""
    section: int
    role: str = ""
    same_as: Optional[int] = None
    guitar: list[list[RiffNote]] = Field(default_factory=list)
    bass: list[list[RiffNote]] = Field(default_factory=list)


class RhythmSection(BaseModel):
    """The whole rhythm section — guitar and bass — composed in ONE call from the realised sitar
    line (Sujit, 2026-10-12: "ask the LLM to build the entire rhythm section based on the lead
    line"). `reasoning` is the arrangement plan, written first: the home chord and how long it
    holds, the head's recurring chord pattern, how the manjha and antara move, where the guitar
    rings under the sitar and where it answers. Legality and cycle arithmetic are checked by code
    (`rhythm_section.part_errors`), so `output_pydantic` can always parse a well-formed answer."""
    reasoning: str = ""
    parts: list[SectionPart] = Field(min_length=1)


class SectionPartDraft(BaseModel):
    """`SectionPart` as the model WRITES it: each avartan cycle one string in the compact riff
    notation (`crew/riff_notation.py`) instead of a list of note objects — the same music in a
    fraction of the output tokens. `rhythm_section.from_draft` reads it back."""
    section: int
    role: str = ""
    same_as: Optional[int] = None
    guitar: list[str] = Field(default_factory=list)
    bass: list[str] = Field(default_factory=list)


class RhythmSectionDraft(BaseModel):
    """`RhythmSection` as the model writes it — the call's structured output."""
    reasoning: str = ""
    parts: list[SectionPartDraft] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Contract 1.55: The Orchestra — the symphonic-metal voice (see crew/orchestra.py)
#
# The Orchestra is the fusion's cinematic layer — called for symphonic metal, and more
# sparingly as colour on other subgenres. ONE LLM agent decides the per-section INTENT
# (what the strings/brass/choir DO, when they enter, the dynamic arc), and DETERMINISTIC
# code (crew/orchestra.py) expands that intent into raga-legal Layers: a wide string
# section, brass, choir, timpani. The raga is the hard constraint that keeps it Hindustani,
# not generic film score — every pitch is a raga swara, seated so an upward voicing never
# enters a descent-only tone, and the harmony stays DRONE/MODAL, never Western functional
# progressions. "The LLM decides the creative call; code owns the mechanics + the legality."
#
# The intent emits WHAT, not MIDI notes: closed vocabularies + raga swara LISTS (Gemini
# controlled-generation-friendly, and something the expander can realise legally), plus ONE
# optional melodic output — a raga-legal countermelody (LeadNote[], guardrailed like every
# other written line). Orchestration is HOLISTIC (long arcs, choir/brass reserved for the
# peak), so unlike the per-section Lead/Riff the whole chart is one call (OrchestraScore).
# --------------------------------------------------------------------------- #

# What each orchestral family DOES in a section — closed sets (Literal, friendly to Gemini
# controlled generation, and a fixed vocabulary the deterministic expander realises).
StringRole = Literal["pad", "tremolo", "counter", "ostinato", "silent"]
BrassRole = Literal["stabs", "sustain", "silent"]
ChoirRole = Literal["sustained", "swell", "silent"]
# The section's orchestral loudness — a fixed dynamic marking the expander maps to a base velocity.
OrchDynamic = Literal["pp", "p", "mp", "mf", "f", "ff"]


class SectionOrchestra(BaseModel):
    """The Orchestra's INTENT for ONE section — WHAT each family does, not MIDI notes.

    Closed vocabularies + raga swara lists so Gemini controlled generation is happy and the
    deterministic expander (crew/orchestra.py) can realise every choice legally. The optional
    `countermelody` is the one genuinely melodic output — a raga-legal ANSWER line (never a
    double of the lead), guardrailed like every written phrase. LEGALITY of the swara lists /
    countermelody is the generator's guardrail, not this schema (so `output_pydantic` always
    parses a well-formed intent); the schema only rejects unknown symbols.
    """
    section_index: int = Field(ge=0)                        # which section (0-based) this intent addresses
    strings: StringRole = "pad"                             # what the string section does here
    string_swaras: list[str] = Field(default_factory=list)  # raga swaras the strings sustain/tremolo/ostinato on (empty -> code default: Sa + a colour)
    brass: BrassRole = "silent"                             # brass role (reserve stabs/sustain for weight + peaks)
    brass_swaras: list[str] = Field(default_factory=list)   # raga swaras the brass sounds (empty -> code default: Sa + fifth)
    choir: ChoirRole = "silent"                             # choir role (reserve for climaxes)
    choir_swaras: list[str] = Field(default_factory=list)   # raga swaras the choir holds (empty -> code default)
    timpani: bool = False                                   # timpani reinforcement (a roll/accent on the sam)
    swell_into_next: bool = False                           # a crescendo lifting INTO the next section (transition prep)
    dynamic: OrchDynamic = "mf"                             # the section's orchestral loudness
    countermelody: list[LeadNote] = Field(default_factory=list)  # optional raga-legal ANSWER line (guardrailed)

    @field_validator("string_swaras", "brass_swaras", "choir_swaras")
    @classmethod
    def _known_orch_swaras(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in SWARAS]
        if bad:
            raise ValueError(f"unknown swara(s) {bad} in orchestra swaras")
        return v


class OrchestraScore(BaseModel):
    """The Orchestra generator's WHOLE-CHART output — ONE LLM call seeing the entire form.

    Orchestration is holistic (long 4-16 bar arcs; the choir/brass reserved for peaks), so
    unlike the per-section Lead/Riff this is one call for the whole piece. `reasoning` (filled
    FIRST) plans the arc — where the choir/brass peak lands, how the texture develops — before
    any section intent. `sections` carries one `SectionOrchestra` per section that uses the
    orchestra layer (others omitted). Legality is the guardrail's job, not the schema's.
    """
    reasoning: str = ""
    sections: list[SectionOrchestra] = Field(default_factory=list)


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
# strings Section.layers / VOICES / `plan_layer` already use — so the
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
# Legality is CHECKABLE, so CODE owns it entirely (crew/ustad.py — no LLM since  #
# the 2026-10-11 redesign). Raga authenticity (Rasik, a consultant) and song    #
# craft (the Producer, the one judge with authority) are LLM-owned on rubrics.  #
# --------------------------------------------------------------------------- #

class Violation(BaseModel):
    """One illegal note the validator found — the structured shape of a
    `raga.validate_composition` entry (an out-of-raga swara in some voice)."""
    layer: str                                   # the voice the note is in
    swara: str                                   # the offending swara
    start_beat: float                            # where it sounds, in beats
    kind: str                                    # "note" | "grace" | "meend-target"
    reason: str                                  # why it is illegal (names the allowed swaras)


class UstadVerdict(BaseModel):
    """The legality verdict, built ENTIRELY by code (see `crew/ustad.py`): `verdict`,
    `violations` and the `explanation` all come from the deterministic
    `raga.validate_composition`. An illegal piece is a forced revise (`crew/triage.py`)."""
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


class RasikSuggestion(BaseModel):
    """One concrete edit Rasik, the raga CONSULTANT, proposes — always to the LEAD line, never
    to the riff, the form or another voice. `section` is the section's index in the chart."""
    section: int = Field(ge=0)
    change: str                      # what to change (e.g. "end the phrase on the pakad's d")
    why: str = ""                    # the raga reason (e.g. "Bhairav rests on komal dha")


class RasikVerdict(BaseModel):
    """The raga consultant's verdict — LLM-OWNED (taste is not checkable), disciplined by a
    fixed rubric and encoded-fact grounding. `reasoning` (filled FIRST) justifies each score;
    `scores` is the rubric; `notes` the short critique; `suggestions` the few phrase-level
    edits to the lead that would most raise its raga authenticity — the Producer, who has the
    final say, may adopt one as its revision plan.
    """
    reasoning: str = ""
    scores: RasikScores
    notes: str = ""
    suggestions: list[RasikSuggestion] = Field(default_factory=list)


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
    performance: int = Field(ge=1, le=5)    # does the score behave like PLAYED music — sustain where it
                                            # should ring, chugs that breathe, an accompaniment that
                                            # supports rather than clashes? (A piece can be written well
                                            # and still arrive as clicks in dead air; nobody here hears
                                            # audio, so this is judged from the computed performance
                                            # numbers, not from listening.)
    handoff: Optional[int] = Field(default=None, ge=1, le=5)   # ONLY when the piece has a guitar
                                            # TAKEOVER: is it unmistakably the gat (its rhythm, its
                                            # structural swaras, its contour), idiomatic on guitar,
                                            # developing across its avartans, and does the sitar
                                            # return seamlessly? None when there is no takeover.


# What a revision may regenerate: the creative voices. (Bass, drums, drone and the clean guitar
# are derived by code and follow the riff/lead they depend on.)
RevisionVoice = Literal["lead", "riff", "orchestra"]

# The Section.layers name each revisable voice plays under.
_VOICE_LAYER: dict[str, str] = {"lead": "lead", "riff": "rhythm", "orchestra": "orchestra"}


class RevisionPlan(BaseModel):
    """ONE surgical, EDIT-BASED revision — what the Producer (or code, for an illegal piece)
    asks for. `voice` is the one creative voice to rework; `sections` are the chart indices it
    is reworked in (empty = everywhere it plays); `instruction` says what to change and
    `preserve` what must survive (e.g. "the main riff's rhythm", "the mukhada"). Both ride the
    targeted sections' intent, and only those sections' notes are replaced (`crew/revision.py`)."""
    voice: RevisionVoice
    sections: list[int] = Field(default_factory=list)
    instruction: str
    preserve: list[str] = Field(default_factory=list)


def plan_layer(plan: RevisionPlan) -> str:
    """The Section.layers name the plan's voice plays under. Pure."""
    return _VOICE_LAYER[plan.voice]


class ProducerVerdict(BaseModel):
    """The Producer's verdict — the ONE judge with authority (the redesign, 2026-10-11).
    `reasoning` (filled FIRST) justifies each score; `scores` is the rubric; `notes` the short
    critique; `decision` accepts the piece or asks for a revision, and on a revise `plan` is the
    ONE edit to make (it may adopt one of Rasik's lead suggestions). A revise without a plan is
    read as an accept (`crew/triage.py`) — nothing actionable, nothing regenerated."""
    reasoning: str = ""
    scores: ProducerScores
    notes: str = ""
    decision: Literal["accept", "revise"] = "accept"
    plan: Optional[RevisionPlan] = None


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
    DEBATE = "debate"      # (retired 2026-10-11 — no critic debate; kept for replay/UI compatibility)
    VERDICT = "verdict"    # the final call: the Producer's accept/revise (or code's forced legality revise)
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


# --------------------------------------------------------------------------- #
# The single Composer's SEED (crew/composer.py) — the core idea, co-conceived.  #
# --------------------------------------------------------------------------- #

class SongSeed(BaseModel):
    """What the ONE Composer emits first: the chart AND the core musical material, conceived
    together in one context (the riff, the hook and the form are one idea — the single bare call
    that beat the multi-agent pipeline wrote them in one breath). `reasoning` is filled FIRST. The
    sitar's part is a finished `hook` in the SONG form and only the head's IDEA (`head`) in the GAT
    form, where the gat call composes the head's notes with its full attention (Option A).
    Legality, the form rules and the hard cell checks are the guardrail's job, not the schema's,
    so `output_pydantic` can always parse a well-formed seed."""
    reasoning: str = ""
    energy_arc: str = ""                            # one line per section: how intensity moves
    chart: ArrangementDraft
    main_riff: RiffPattern                          # ONE cycle of the riff that recurs
    hook: Optional[LeadPhrase] = None               # SONG form: ONE avartan of the sitar's recurring hook
    head: Optional[HeadIdea] = None                 # GAT form: the head's IDEA (the gat call writes its notes)


class HeadTurn(BaseModel):
    """One composer's turn in the HEAD debate (`crew/head_debate.py`): having heard the other
    composer's gat head — written from a different approach — it argues (`argument`, filled FIRST:
    where each head is stronger, as music) and returns its OWN head, revised where it was persuaded
    (`changed`: true) or unchanged where it was not. It keeps its own approach: a turn is not a merge.
    The head answers to the same hard lines as any gat head (the turn guardrail)."""
    argument: str = ""
    changed: bool = False
    head: LeadPhrase


class DebateTurn(BaseModel):
    """One composer's turn in the SEED DEBATE (`crew/seed_debate.py`): having heard a rival
    composer's seed for the same request, it argues (`argument`, filled FIRST — what the rival does
    better and worse, judged on the notes and code's measurements) and returns its OWN seed, revised
    where it was persuaded and unchanged where it was not (`changed` says which). It keeps its own
    idea: a debate turn is not a merge. The seed guardrail holds `seed` to the usual hard lines."""
    argument: str = ""
    changed: bool = False
    seed: SongSeed


class SeedChoice(BaseModel):
    """The seed SELECTOR's verdict over labelled candidate seeds: `reasoning` first (each
    candidate weighed on the rubric), then `choice`, the 1-based label of the strongest. Run twice
    with the order reversed; code reads a disagreement as a tie (position bias, not a preference)."""
    reasoning: str = ""
    choice: int = Field(ge=1)


class VersionChoice(BaseModel):
    """The judge's answer to "draft or revision?": `reasoning` first (what a listener hears in
    each), then `better` — "A", "B", or "same" when no real difference is audible. Asked twice with
    the order swapped; code keeps a revision only if it wins both times (crew/compare.py)."""
    reasoning: str = ""
    better: Literal["A", "B", "same"]


# The chart refers to the riff/phrase contracts defined further down this module.
Arrangement.model_rebuild()
