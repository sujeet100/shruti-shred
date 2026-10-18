"""
Crew configuration — model tiers, thinking levels, and the round clock.

One place for every knob so the agents stay model-agnostic (CLAUDE.md: "model =
one config value"). Model IDs are overridable via env so they can be swapped
without touching code.

No import-time side effects (CLAUDE.md): this module does NOT call `load_dotenv`,
touch the network, or construct an LLM at import. An entry point calls `load_env()`
once, then reads config via the getters; the LLM factories build clients lazily.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# --- Pure constants (no env, safe at import) ------------------------------------
# NO TEMPERATURE (Sujit, 2026-10-11). Every agent runs at the model's DEFAULT sampling. Google
# "strongly recommend[s] keeping the temperature parameter at its default value of 1.0" for the
# Gemini 3 family and warns that lower values can cause looping or degraded reasoning (PROMPTING.md
# §3). The old ladder (generators 0.9, composers 0.7, critics 0.2, extractor 0.0) was the pre-3
# canon; the best riff we have measured came from a call with no config at all, and rubric bias is
# flat across temperatures, so judge consistency comes from the rubric, not the sampler. The one
# knob we keep is the THINKING LEVEL (see build_llm) — verified in traces to be load-bearing.

# The revise cap — the Flow's clock. Research puts the useful range at 2-3 rounds (gains
# plateau fast); small is also live-safe. The router returns "done" once it is reached, so
# the propose->critique->revise loop always terminates (crew/flow.py).
MAX_ROUNDS: int = 2
# Rounds the PRODUCER's own plans may spend (2026-10-18). Across every recorded run it revised the
# first draft 14/14 times and its scores rose after an edit as often as they fell; one round, kept
# only if it wins a both-orders comparison (crew/compare.py). Code-forced fixes keep MAX_ROUNDS.
MAX_JUDGE_ROUNDS: int = 1

# The composer dialogue's clock: how many turn-by-turn exchanges Pandit and
# Riffsmith get before we stop (they may stop earlier by agreeing). The bounded
# loop — not organic consensus — is what guarantees termination on stage.
COMPOSER_TURNS: int = 3

# The studio session's clock — bounded COOPERATIVE collaboration (the talk's
# SECOND named pattern, beside the critique loop). How many turns the two creative
# voices (Lead + Riff) take on a section's shared canvas before CODE stops them:
# the leader PROPOSES, the follower RESPONDS, then bounded REFINE turns. Small by
# design (gains plateau, and live cost is ~2 agents x passes per section) and
# always terminating — the bandleader's clock, never organic consensus. A fast /
# live-safe run passes a smaller value (see crew/studio.collaboration_schedule).
CANVAS_PASSES: int = 3

# One bounded retry per turn (CLAUDE.md: "one bounded retry, not a loop"). If a
# composer's draft is illegal, the guardrail hands back the precise error and the
# turn is re-run this many times before we give up. Billing is live — keep it low.
COMPOSER_RETRIES: int = 1
# The single Composer's SEED bundles three artifacts (chart, main riff, hook), each with its own
# hard checks, so it gets one more bounded retry than a single composer turn.
SEED_RETRIES: int = 2

# Generators (Lead/Riff/Groove) emit ONE structured phrase per section. Same
# discipline as the composers: one bounded retry when the legality guardrail
# bounces an out-of-raga note, and a modest within-call iteration cap for live
# safety. The generators have no across-call loop of their own (they fan out over
# a fixed section list), so these are the only clocks they need.
GENERATOR_RETRIES: int = 1
GENERATOR_MAX_ITER: int = 3

# Per-turn circuit-breaker on an agent's internal reasoning/tool loop (CLAUDE.md:
# "modest max_iter for live safety"). Our own turn cap (COMPOSER_TURNS) bounds the
# ACROSS-turn debate; this bounds the WITHIN-turn work. A composer turn is a single
# structured emission with no tools, so it needs very few iterations — this is a
# backstop against a runaway ReAct loop, not a working budget.
COMPOSER_MAX_ITER: int = 3

# The critics' within-call cap. Unlike a composer turn, Ustad makes ONE tool
# round-trip (call validate_composition -> read the violations -> answer), so it
# needs a couple more iterations than a pure emission — still a live-safety
# backstop against a runaway ReAct loop, not a working budget.
CRITIC_MAX_ITER: int = 4

# CrewAI's OWN task-level retry on error — set to 0 on EVERY agent (Sujit's call,
# 2026-07-16): the default (2) silently re-dials a failed call up to twice, so a dead
# connection pins one progress beat for 3 x the 120s timeout (~6 min) before the flow
# hears about it. We fail FAST and LOUDLY instead: the UI falls back to Demo on a live
# failure, and every retry that matters is OURS — the verifier re-rolls and guardrail
# retries carry targeted feedback, which a blind re-dial never does.
AGENT_RETRY_LIMIT: int = 0

# Defaults; override via the env vars named below.
# PINNED to an exact version (2026-10-11): `gemini-3.5-flash` had dropped off Google's model page
# and was being answered by 3.6 Flash (the response's model_version said so) — silent drift.
# 3.8 Flash is Google's recommended Flash for new projects, same price as 3.6. Never use the
# `gemini-flash-latest` alias: Google hot-swaps it on every release.
_DEFAULT_FLASH: str = "gemini/gemini-3.8-flash"
_DEFAULT_LISTEN_MODEL: str = "gemini-3.1-pro-preview"   # google-genai id (no provider prefix)
_DEFAULT_REASONING: str = "low"

# Thinking by TIER (2026-10-12). On 3.8 Flash `low` is NO thinking: probed on a composition
# prompt it returned no thought count at all (with or without a JSON schema), while `medium` spent
# 731 thought tokens; the 2026-10-11 run's 41 calls all reported zero. So the calls where the piece
# is CONCEIVED (the chart / the Composer's seed / the joint gat) and JUDGED (Rasik, the Producer)
# think at `medium` — a handful per run, Google's level for creative reasoning — while the many
# per-section generator calls stay at `low`: they reason in the open through the schema
# (`phrase_plan`, `reasoning`), and `medium` on 26 lead calls would cost minutes on stage.
_DEFAULT_CONCEPTION_THINKING: str = "medium"
_DEFAULT_JUDGE_THINKING: str = "medium"
# The rhythm section thinks at LOW (Sujit, 2026-10-13): at medium it spent 39.7k of its 49.2k
# output tokens thinking — 305 s for one call on fusion_20261013_074703, the run's slowest and
# costliest step. Low (no thinking on 3.8 Flash) is the trial; `RMA_RHYTHM_THINKING` restores it.
_DEFAULT_RHYTHM_THINKING: str = "low"

# The Interpreter's thinking level. Faithful extraction is driven by the PROMPT's
# rules + examples, not by deliberation (prompt-before-effort), so it runs at the
# model's FLOOR. Uncapped, the extractor was observed burning ~650 thinking tokens on a
# job that needs none. The floor is MODEL-SPECIFIC: 3.5 Flash took `minimal`; 3.8 Flash
# REJECTS it (400 INVALID_ARGUMENT, first live run 2026-10-11) and accepts low/medium/high
# — probed directly: `low` thought ~53 tokens on a one-word reply, and none at all on a
# composition prompt (2026-10-12). Re-probe on a model change.
EXTRACTOR_THINKING: str = "low"

# Per-request timeout. A live run hung for 19 minutes on ONE dropped LLM call (2026-07-16 —
# no default timeout anywhere in the native google-genai stack), freezing the whole flow
# mid-demo. Raised 120 -> 180 the same evening: the stricter verifier constraints made the
# hard lead cells think longer (healthy calls observed up to ~111s / 31k tokens), and 120s
# started clipping LEGITIMATE work (a 504 killed a 12-minute run). 180s fits the observed
# tail with margin while a true hang still dies visibly in three minutes. On expiry the
# call raises; the flow surfaces the failure (the UI falls back to Demo on a failed run).
_DEFAULT_TIMEOUT_S: int = 180


def load_env() -> None:
    """Load `.env` into the process environment. Call once at an entry point.

    Kept out of import time so importing `crew.config` has no side effects.
    Idempotent — `python-dotenv` will not clobber vars already set.
    """
    from dotenv import load_dotenv
    load_dotenv()


def flash_model() -> str:
    """Flash-tier model id (fast/cheap); env `RMA_FLASH_MODEL` overrides."""
    return os.getenv("RMA_FLASH_MODEL", _DEFAULT_FLASH)


def pro_model() -> str:
    """Pro-tier model id for critics/Conductor; `RMA_PRO_MODEL` overrides.

    Starts equal to the Flash model — begin the whole crew on Flash, promote the
    critics later by setting `RMA_PRO_MODEL`.
    """
    return os.getenv("RMA_PRO_MODEL", flash_model())


def reasoning_effort() -> str:
    """The default thinking level (Gemini `thinking_level`: low/medium/high on 3.8 Flash —
    `minimal` is rejected there);
    `RMA_REASONING_EFFORT` overrides (default low)."""
    return os.getenv("RMA_REASONING_EFFORT", _DEFAULT_REASONING)


def conception_thinking() -> str:
    """Thinking for the calls that CONCEIVE the piece (chart, seed, joint gat);
    `RMA_CONCEPTION_THINKING` overrides (default medium)."""
    return os.getenv("RMA_CONCEPTION_THINKING", _DEFAULT_CONCEPTION_THINKING)


def judge_thinking() -> str:
    """Thinking for the critics (Rasik, the Producer); `RMA_JUDGE_THINKING` overrides
    (default medium)."""
    return os.getenv("RMA_JUDGE_THINKING", _DEFAULT_JUDGE_THINKING)


def rhythm_thinking() -> str:
    """Thinking for the rhythm-section call (guitar + bass for the whole piece);
    `RMA_RHYTHM_THINKING` overrides (default low)."""
    return os.getenv("RMA_RHYTHM_THINKING", _DEFAULT_RHYTHM_THINKING)


def llm_timeout_s() -> int:
    """Per-request LLM timeout in seconds; `RMA_LLM_TIMEOUT_S` overrides (default 180).
    A non-integer value falls back to the default rather than crashing a run."""
    raw = os.getenv("RMA_LLM_TIMEOUT_S")
    if raw is None:
        return _DEFAULT_TIMEOUT_S
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_TIMEOUT_S


def has_api_key() -> bool:
    """True iff GEMINI_API_KEY is set — gate LLM calls on this."""
    return bool(os.getenv("GEMINI_API_KEY"))


def _env_flag(name: str) -> bool:
    """True iff env var `name` is set to a truthy value (1/true/yes/on)."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_flag_on(name: str) -> bool:
    """A default-ON flag: True unless env var `name` is set to a falsy value (0/false/no/off)."""
    return os.getenv(name, "").strip().lower() not in {"0", "false", "no", "off"}


def tabla_enabled() -> bool:
    """Whether the TABLA plays; env `RMA_TABLA` (default OFF as of 2026-09-14).

    Sujit's call, after the teentaal render: the tabla holds one onset per matra everywhere in
    the piece, so against a sixteenth-note taan and a double-kick groove it reads as dropping
    into half-time even though the tala never changes — and most matras strike both tabla
    pitches together, which is a two-sample pulse rather than an articulated theka. It hurts
    more than it helps until it becomes section-aware (theka under the gat, denser bols into
    the taan, a pickup into the sam).

    A FLAG, not a deletion: `crew/groove.tabla_layer` and its Indian-Ensemble routing (bank,
    Sa-tuning) are good code that will be wanted back — set RMA_TABLA=1 to hear it.
    """
    return _env_flag("RMA_TABLA")


def lead_guitar_enabled() -> bool:
    """Whether the distorted LEAD GUITAR doubles, harmonises or trades the sitar's line; env
    `RMA_LEAD_GUITAR` (default OFF as of 2026-10-12).

    Sujit's call on the 2026-10-12 Darbari render: the unison guitar played the line plain (by
    design, so it never sways out of tune with the sitar) and so BURIED the sitar's gamaks and
    Ga gestures — measured, the first melody section carried 10 gamak strokes nobody heard until
    the taan exposed the sitar — and the sitar sounded "feeble compared to guitar". A FLAG, not a
    deletion: the voicings (unison/octave/third, the taan trade) are good code — RMA_LEAD_GUITAR=1
    brings them back.
    """
    return _env_flag("RMA_LEAD_GUITAR")


def hearing_enabled() -> bool:
    """Whether the lead calls may LISTEN to a draft before answering (crew/hearing.py — the
    `hear_phrase` tool, the Composer's first ReAct step); env `RMA_HEAR`. Default OFF until one
    live run has shown what the model does with it and Sujit has heard the result: each listen
    is another round trip on that section's call."""
    return _env_flag("RMA_HEAR")


def studio_enabled() -> bool:
    """True iff the COOPERATIVE studio session is the generation path; env `RMA_STUDIO`.

    Opt-in — default OFF, so the Flow keeps the parallel generate-in-isolation path until
    the studio output has been heard on stage. Flip it on (or make it the default here)
    once confirmed; nothing else in the pipeline changes, both paths return the same shape.
    """
    return _env_flag("RMA_STUDIO")


def listening_enabled() -> bool:
    """Whether the ADVISORY listening pass runs after a render (crew/listening.py); env
    `RMA_LISTEN`. Default OFF — it is uncalibrated against Sujit's ear, and each listen is a paid
    Pro call. It reports; it never gates a decision until calibrated."""
    return _env_flag("RMA_LISTEN")


def listen_model() -> str:
    """The audio judge's model; env `RMA_LISTEN_MODEL`. Pro, not Flash: Flash scored far lower on
    music perception (MUSE benchmark) — see DESIGN.md "THE REDESIGN"."""
    return os.getenv("RMA_LISTEN_MODEL", _DEFAULT_LISTEN_MODEL)


def rhythm_section_enabled() -> bool:
    """True iff ONE call writes guitar + bass for the whole piece from the placed sitar line
    (crew/rhythm_voice.py, Sujit's decision 2026-10-12); env `RMA_RHYTHM_SECTION`.

    Default ON since 2026-10-18 (Sujit: the redesigned five-agent path is the system); set it to 0
    for the per-section riff + the code passes (chord floor, articulation) + the derived bass, which
    are also the fallback when the call fails. The studio path ignores it."""
    return _env_flag_on("RMA_RHYTHM_SECTION")


def composer_enabled() -> bool:
    """True iff the single COMPOSER owns the music (crew/composer.py: one seed call co-writes the
    chart, main riff and hook; the generators develop around it); env `RMA_COMPOSER`.

    Default ON since 2026-10-18 (Sujit: the redesigned five-agent path is the system); set it to 0
    for the legacy Pandit/Riffsmith composers and per-voice generators. Takes precedence over the
    studio (whose two-agent canvas is what the single owner replaces)."""
    return _env_flag_on("RMA_COMPOSER")


def canvas_passes() -> int:
    """Turns per section in the studio session; env `RMA_CANVAS_PASSES` overrides
    CANVAS_PASSES. Clamped to >= 1 (a fast / live-safe run passes a smaller value; 1 is
    leader-only). A non-integer value falls back to the default rather than crashing a run.
    """
    raw = os.getenv("RMA_CANVAS_PASSES")
    if raw is None:
        return CANVAS_PASSES
    try:
        return max(1, int(raw))
    except ValueError:
        return CANVAS_PASSES


def build_llm(model: str, effort: str | None = None, *, timeout_s: int | None = None):
    """Construct a CrewAI LLM at the model's default sampling (no temperature — see the
    note at the top of this module). Lazy import: no crewai cost until called.

    `effort` overrides the global thinking level for this one agent — e.g. the
    extractor could run a lower level than the rest of the crew.

    The thinking cap rides the provider's `thinking_config` passthrough, NOT
    `reasoning_effort`: CrewAI 1.15.2's native Gemini provider silently DROPS
    `reasoning_effort` (only the OpenAI/Azure providers forward it), so thinking ran
    at the model default — `medium`, uncapped. Traces of 2026-07-16 showed lead calls
    burning 4k-18.5k thinking tokens each (40-137s latencies, 504 DEADLINE_EXCEEDED
    stalls); `thinking_level` is the knob the API actually honors. Re-verify the
    passthrough (and the reasoning_tokens in a trace) on any CrewAI upgrade.

    The per-request timeout rides `client_params` into the native google-genai client
    (`http_options.timeout`, milliseconds) — both knobs are specific to the
    Gemini-native provider; the non-`gemini/` fallback path gets `reasoning_effort`,
    which those providers do forward.
    """
    from crewai import LLM

    from crew.trace_replay import replay_llm
    if (replayed := replay_llm()) is not None:                # inside `trace_replay.replaying`
        return replayed
    level = effort or reasoning_effort()
    timeout_ms = (timeout_s or llm_timeout_s()) * 1000
    common: dict = {"client_params": {"http_options": {"timeout": timeout_ms}}}
    if model.startswith("gemini/"):
        from google.genai import types

        from crew.lean_gemini import LeanGemini      # asks only for informative fields (see module)
        return LeanGemini(model=model.removeprefix("gemini/"), provider="gemini",
                          thinking_config=types.ThinkingConfig(thinking_level=level,
                                                               include_thoughts=True),
                          **common)
    valid = {"none", "low", "medium", "high"}                 # CrewAI's reasoning_effort Literal
    # `http_options` is the google-genai client's; other providers take a plain timeout (seconds)
    # — passing the Gemini dict broke every non-Gemini model (found 2026-10-18, gpt-6.1-sol).
    # OpenAI: the RESPONSES API. On Chat Completions CrewAI 1.15.2 sends `reasoning_effort` only to
    # "o1" model names, so gpt-6.1-sol silently ran at its default (medium); the Responses path sends
    # `reasoning: {effort}` and carries structured output as `text.format` (verified 2026-10-18).
    # `max_retries=0`: the OpenAI client silently retries a timed-out call twice, so one slow
    # gpt-6.1-sol call at a 420 s limit hung for 21 minutes (2026-10-18). Fail once, loudly.
    extra = {"api": "responses", "max_retries": 0} if model.startswith("openai/") else {}
    return LLM(model=model, reasoning_effort=level if level in valid else "low",
               timeout=timeout_ms / 1000, **extra)


def structured_output(model: type) -> dict[str, type]:
    """The Task kwargs for a structured answer, sent ONCE. With `output_pydantic` alone, CrewAI
    1.15.2 sends the model to Gemini as native structured output (`response_json_schema`) AND
    pastes the same JSON schema into the prompt as text ("Format your final answer according to
    the following OpenAPI schema...") — ~10k characters, ~2.9k tokens, at the END of every lead
    prompt (trace 15fbd6571f72: 45% of each lead call's input). Setting `response_model` to the
    same model skips the text copy (`build_task_prompt_with_schema`) and changes nothing else:
    the executor already used this model natively, and `output_pydantic` still drives parsing
    and the guardrail. Re-check on a CrewAI upgrade. Pure."""
    return {"output_pydantic": model, "response_model": model}


def generator_llm():
    """Flash-tier — the generators."""
    return build_llm(flash_model())


# The cross-model debate's seam: inside `composer_override(model, effort)` every Composer call
# (the seed, the gat head, a debate turn) runs on that model; outside it nothing changes.
_COMPOSER_OVERRIDE: ContextVar[tuple[str, str] | None] = ContextVar("composer_override", default=None)


@contextmanager
def composer_override(model: str, effort: str) -> Iterator[None]:
    """Run the Composer's calls on `model` (e.g. "openai/<id>" or "gemini/gemini-3.8-flash") at
    `effort` for the duration of the block."""
    token = _COMPOSER_OVERRIDE.set((model, effort))
    try:
        yield
    finally:
        _COMPOSER_OVERRIDE.reset(token)


def composer_llm(*, timeout_s: int | None = None):
    """The calls that CONCEIVE the piece — the chart (Pandit/Riffsmith), the Composer's seed, the
    joint gat — Flash at `conception_thinking()` (promote to Pro later via RMA_PRO_MODEL), or the
    model and effort a `composer_override` block names. `timeout_s` lengthens the per-request
    limit for a call with a long answer."""
    override = _COMPOSER_OVERRIDE.get()
    if override is not None:
        return build_llm(override[0], effort=override[1], timeout_s=timeout_s)
    return build_llm(flash_model(), effort=conception_thinking(), timeout_s=timeout_s)


def rhythm_section_llm():
    """The rhythm-section call — Flash at `rhythm_thinking()`, with its own longer limit."""
    return build_llm(flash_model(), effort=rhythm_thinking(), timeout_s=rhythm_section_timeout_s())


# The rhythm section writes guitar AND bass for the whole piece in one answer: on 2026-10-12 it ran
# into the 180 s per-request limit (504 DEADLINE_EXCEEDED) and fell back to the riff path. Its own
# limit is longer; every other call keeps `llm_timeout_s()`. `RMA_RHYTHM_TIMEOUT_S` overrides.
def rhythm_section_timeout_s() -> int:
    return int(os.getenv("RMA_RHYTHM_TIMEOUT_S", "360"))


def critic_llm():
    """The critics — Pro tier (Flash for now, via RMA_PRO_MODEL) at `judge_thinking()`."""
    return build_llm(pro_model(), effort=judge_thinking())


def extractor_llm():
    """Flash for extraction (Interpreter), at MINIMAL thinking. Faithful extraction is
    driven by the PROMPT's rules + examples, not by deliberation or a cold sampler —
    prompt first, effort only if a solid prompt still fails (see DESIGN.md).
    """
    return build_llm(flash_model(), effort=EXTRACTOR_THINKING)
