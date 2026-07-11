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
# Gemini has no "reasoning effort" knob in the Claude-Code sense — we steer with
# temperature. Generators explore; critics/Conductor stay steady. Composers sit
# in between: creative enough to vary, disciplined enough to emit valid structure.
GENERATOR_TEMPERATURE: float = 0.9
COMPOSER_TEMPERATURE: float = 0.7
CRITIC_TEMPERATURE: float = 0.2
# Faithful extraction wants reproducibility, not variety — run it stone cold.
EXTRACTOR_TEMPERATURE: float = 0.0

# The debate/revise cap — the Conductor's "clock". Research puts the useful range
# at 2-3 rounds (gains plateau fast); small is also live-safe.
MAX_ROUNDS: int = 2

# The composer dialogue's clock: how many turn-by-turn exchanges Pandit and
# Riffsmith get before we stop (they may stop earlier by agreeing). The bounded
# loop — not organic consensus — is what guarantees termination on stage.
COMPOSER_TURNS: int = 3

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

# Defaults; override via the env vars named below.
_DEFAULT_FLASH: str = "gemini/gemini-3.5-flash"
_DEFAULT_REASONING: str = "low"


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
    """Gemini reasoning effort; `RMA_REASONING_EFFORT` overrides (default low)."""
    return os.getenv("RMA_REASONING_EFFORT", _DEFAULT_REASONING)


def has_api_key() -> bool:
    """True iff GEMINI_API_KEY is set — gate LLM calls on this."""
    return bool(os.getenv("GEMINI_API_KEY"))


def build_llm(model: str, temperature: float, effort: str | None = None):
    """Construct a CrewAI LLM (lazy import: no crewai cost until called).

    `effort` overrides the global reasoning effort for this one agent — used where
    a task needs more budget than the default (e.g. faithful extraction).
    """
    from crewai import LLM
    return LLM(model=model, temperature=temperature, reasoning_effort=effort or reasoning_effort())


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


def extractor_llm():
    """Low-temperature Flash for extraction (Interpreter).

    Runs stone cold (temperature 0 — extraction needs reproducibility, not variety)
    at the default (low) effort. Faithful extraction is driven by the PROMPT's rules
    + examples, not by burning reasoning effort — prompt first, effort only if a
    solid prompt still fails (see DESIGN.md). The `effort` param on build_llm exists
    for that escalation, deliberately unused here.
    """
    return build_llm(flash_model(), EXTRACTOR_TEMPERATURE)
