"""
Connectivity check — one trivial Gemini call to prove the key + model work.

This is the pre-flight before any agent is built: does GEMINI_API_KEY resolve,
and does the configured Flash model answer? It fails LOUD and early if not,
instead of surfacing as a confusing failure deep in the Flow on stage.

Run:  uv run python -m crew.connectivity
"""

import sys

from crew.config import FLASH_MODEL, generator_llm, has_api_key


def main() -> int:
    if not has_api_key():
        print("✗ GEMINI_API_KEY not set.")
        print("  Copy .env.example to .env and add your key, then re-run:")
        print("    uv run python -m crew.connectivity")
        return 1

    print(f"→ Calling {FLASH_MODEL} ...")
    try:
        reply = generator_llm().call("Reply with exactly the word: pong")
    except Exception as e:  # noqa: BLE001 — we want the raw failure surfaced here
        print(f"✗ Call failed: {type(e).__name__}: {e}")
        print("  Check the model ID (see CLAUDE.md — verify current Gemini IDs) and the key.")
        return 1

    print(f"✓ Reply: {reply!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
