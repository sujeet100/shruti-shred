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
# temperature. Generators explore; critics/Conductor stay steady.
GENERATOR_TEMPERATURE: float = 0.9
CRITIC_TEMPERATURE: float = 0.2

# The debate/revise cap — the Conductor's "clock". Research puts the useful range
# at 2-3 rounds (gains plateau fast); small is also live-safe.
MAX_ROUNDS: int = 2

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


def generator_llm():
    """Flash-tier LLM for the generators (lazy import: no crewai cost until used)."""
    from crewai import LLM
    return LLM(model=flash_model(), temperature=GENERATOR_TEMPERATURE,
               reasoning_effort=reasoning_effort())


def critic_llm():
    """Critic/Conductor LLM (Flash for now; promote via RMA_PRO_MODEL later)."""
    from crewai import LLM
    return LLM(model=pro_model(), temperature=CRITIC_TEMPERATURE,
               reasoning_effort=reasoning_effort())
