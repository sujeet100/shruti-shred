"""
Crew configuration — model tiers, temperatures, and the debate clock.

One place for every knob so the agents stay model-agnostic (CLAUDE.md: "model =
one config value"). Model IDs are overridable via env so they can be swapped
without touching code — important because the exact Gemini IDs must be
re-verified the moment the key lands (see CLAUDE.md; `-latest` aliases are the
safe default for a live stage endpoint).

Importing this module does NOT hit the network or construct an LLM — the LLM
factories are lazy and only run when an agent is actually built.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # load .env if present; a no-op when it's absent

# --- Model tiers (see CLAUDE.md "CrewAI & agentic implementation rules") --------
# Flash = fast/cheap for generators; Pro = stronger reasoning for critics/Conductor.
# Prefer the `-latest` aliases for a stable live endpoint; override via env to pin.
FLASH_MODEL = os.getenv("RMA_FLASH_MODEL", "gemini/gemini-flash-latest")
PRO_MODEL = os.getenv("RMA_PRO_MODEL", "gemini/gemini-pro-latest")

# Gemini has no "reasoning effort" knob — steer with temperature.
GENERATOR_TEMPERATURE = 0.9  # variety: we want the generators to explore
CRITIC_TEMPERATURE = 0.2     # consistency: critics/Conductor should be steady

# The debate/revise cap — the Conductor's "clock". Research puts the useful range
# at 2-3 rounds (gains plateau fast); small is also live-safe.
MAX_ROUNDS = 2


def has_api_key() -> bool:
    """True iff GEMINI_API_KEY is set — gate LLM calls on this."""
    return bool(os.getenv("GEMINI_API_KEY"))


def generator_llm():
    """Flash-tier LLM for the generators (lazy import: no crewai cost until used)."""
    from crewai import LLM
    return LLM(model=FLASH_MODEL, temperature=GENERATOR_TEMPERATURE)


def critic_llm():
    """Pro-tier LLM for the critics and the Conductor."""
    from crewai import LLM
    return LLM(model=PRO_MODEL, temperature=CRITIC_TEMPERATURE)
