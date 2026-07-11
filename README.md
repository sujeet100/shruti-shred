# Raga × Metal — Agentic Composer

A conference-talk demo: a multi-agent system that composes **Hindustani-classical ×
metal** fusion, used to **teach agentic-AI patterns**. The audience picks a raga +
metal subgenre; the agents compose, critique, and revise live; the result renders to
audio.

See `PLAN.md` (roadmap), `CLAUDE.md` (working rules), and `TALK.md` (talk prep).

## Setup

Python deps come from **uv**. Two things are *not* Python packages — FluidSynth (a
system binary) and the ~38MB MuseScore soundfont (no reliable PyPI package, so `uv`
can't fetch it). A one-time script installs both:

```bash
./setup.sh                     # installs fluidsynth + downloads the soundfont (idempotent)
uv run python src/demo.py      # sound check → writes out/*.wav
uv run python tests/test_knowledge.py   # knowledge-core test suite
```

## Layout

- `src/raga.py` — raga grammar + `validate_composition` (the deterministic guardrail),
  plus kan/meend ornament support.
- `src/talas.py` — 6 Hindustani talas (matras, vibhags, sam/tali/khali, theka).
- `src/subgenres.py` — 4 metal subgenres (tempo/register + drum vocabulary).
- `src/render.py` — composition JSON → MIDI → WAV (FluidSynth).
- `src/demo.py` — end-to-end proof: compose → validate → render.
- `tests/test_knowledge.py` — proves the *data* is correct (consistency + mode match).

Status: Phase 1 (knowledge core) done. Phase 2 (CrewAI Flow + agents) is next and
needs `GEMINI_API_KEY` in `.env` (copy `.env.example`).
