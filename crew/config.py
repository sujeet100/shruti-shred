"""
Crew configuration — model tiers, temperatures, and the debate clock.

One place for every knob so the agents stay model-agnostic (CLAUDE.md: "model =
one config value"). Model IDs are overridable via env so they can be swapped
without touching code.

No import-time side effects (CLAUDE.md): this module does NOT call `load_dotenv`,
touch the network, or construct an LLM at import. An entry point calls `load_env()`
once, then reads config via the getters; the LLM factories build clients lazily.
"""

from __future__ import annotations

import os

# --- Pure constants (no env, safe at import) ------------------------------------
# Temperature: generators explore; critics/Conductor stay steady. Composers sit
# in between: creative enough to vary, disciplined enough to emit valid structure.
# (Reasoning is steered separately, via the Gemini thinking level — see build_llm.)
GENERATOR_TEMPERATURE: float = 0.9
COMPOSER_TEMPERATURE: float = 0.7
CRITIC_TEMPERATURE: float = 0.2
# Faithful extraction wants reproducibility, not variety — run it stone cold.
EXTRACTOR_TEMPERATURE: float = 0.0

# The debate/revise cap — the Conductor's "clock". Research puts the useful range
# at 2-3 rounds (gains plateau fast); small is also live-safe. Reused as the number
# of turns in the Ustad<->Rasik arbitration debate — the guaranteed terminator.
MAX_ROUNDS: int = 2

# A Rasik rubric criterion at or below this fixed 1-5 score flags an AESTHETIC
# conflict for the Conductor (3 = "acceptable"; below it, Rasik is objecting). Only
# a conflict opens the debate — legal + all-acceptable is accepted by code with no
# LLM spend, illegal forces a revise by code (legality is non-negotiable).
RASIK_PASS_SCORE: int = 3

# HYBRID triage: the debate opens when a CRITICAL criterion (pakad/idiom — the raga's
# soul) is below the pass line, OR the OVERALL mean of the four scores falls below this
# floor. The mean prong catches broad mediocrity (several middling criteria) while the
# critical prong protects the soul, so a LONE weak mood/coherence — with everything else
# strong — does NOT burn a debate on the stage. (Reviewers, 2026-07-12: "don't let a
# lone mediocre criterion trigger it.")
RASIK_OVERALL_FLOOR: float = 3.0

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
_DEFAULT_FLASH: str = "gemini/gemini-3.5-flash"
_DEFAULT_REASONING: str = "low"

# The Interpreter's thinking level. Faithful extraction is driven by the PROMPT's
# rules + examples, not by deliberation (prompt-before-effort), so it runs at the
# floor — Gemini 3.x's `minimal` (Sujit, 2026-07-16). Uncapped, the extractor was
# observed burning ~650 thinking tokens on a job that needs none.
EXTRACTOR_THINKING: str = "minimal"

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
    """The default thinking level (Gemini `thinking_level`: minimal/low/medium/high);
    `RMA_REASONING_EFFORT` overrides (default low)."""
    return os.getenv("RMA_REASONING_EFFORT", _DEFAULT_REASONING)


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


def studio_enabled() -> bool:
    """True iff the COOPERATIVE studio session is the generation path; env `RMA_STUDIO`.

    Opt-in — default OFF, so the Flow keeps the parallel generate-in-isolation path until
    the studio output has been heard on stage. Flip it on (or make it the default here)
    once confirmed; nothing else in the pipeline changes, both paths return the same shape.
    """
    return _env_flag("RMA_STUDIO")


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


def build_llm(model: str, temperature: float, effort: str | None = None):
    """Construct a CrewAI LLM (lazy import: no crewai cost until called).

    `effort` overrides the global thinking level for this one agent — e.g. the
    extractor runs `minimal` while the rest of the crew runs the default.

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
    level = effort or reasoning_effort()
    common: dict = {"temperature": temperature,
                    "client_params": {"http_options": {"timeout": llm_timeout_s() * 1000}}}
    if model.startswith("gemini/"):
        from google.genai import types
        return LLM(model=model,
                   thinking_config=types.ThinkingConfig(thinking_level=level,
                                                        include_thoughts=True),
                   **common)
    valid = {"none", "low", "medium", "high"}                 # CrewAI's reasoning_effort Literal
    return LLM(model=model, reasoning_effort=level if level in valid else "low", **common)


def generator_llm():
    """Flash-tier, high temperature — generators explore."""
    return build_llm(flash_model(), GENERATOR_TEMPERATURE)


def composer_llm():
    """Pandit/Riffsmith — Flash, mid-high temperature: the composers CREATE.

    High cognitive load per DESIGN.md, but kept on Flash for now (promote to Pro
    later via RMA_PRO_MODEL once the loop works end-to-end). The temperature buys
    variety so the same request doesn't yield the same chart twice, without
    tipping into malformed structured output.
    """
    return build_llm(flash_model(), COMPOSER_TEMPERATURE)


def critic_llm():
    """Critic/Conductor — Pro (or Flash for now via RMA_PRO_MODEL), low temperature."""
    return build_llm(pro_model(), CRITIC_TEMPERATURE)


def conductor_llm():
    """The arbiter — same tier as the critics (Pro, low temperature). Named separately
    so the Conductor's tier can diverge later without touching call sites; identical to
    `critic_llm` today (a referee wants consistency, not variety — hence low temp)."""
    return build_llm(pro_model(), CRITIC_TEMPERATURE)


def extractor_llm():
    """Low-temperature Flash for extraction (Interpreter).

    Runs stone cold (temperature 0 — extraction needs reproducibility, not variety)
    at MINIMAL thinking. Faithful extraction is driven by the PROMPT's rules +
    examples, not by deliberation — prompt first, effort only if a solid prompt
    still fails (see DESIGN.md).
    """
    return build_llm(flash_model(), EXTRACTOR_TEMPERATURE, effort=EXTRACTOR_THINKING)
