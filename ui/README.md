# Shruti Shred — the demo UI

A pixel-art, point-and-click-adventure-style front end for the raga × metal agent band.
It speaks ONLY the two `UI_CONTRACT.md` seams — the **`DebateEvent`** stream (the timeline)
and the **`Composition`** (the audio/score). It never reaches into agent internals.

## Run it

```bash
# offline replay — zero LLM cost (the default; safe to run freely)
uv run python -m ui.server          # -> http://127.0.0.1:8500

# LIVE — actually calls the crew (Gemini billing is on; opt in explicitly)
RMA_UI_LIVE=1 uv run python -m ui.server
```

Open a browser at the printed URL and press **Compose**. In replay mode the button plays
an embedded, contract-accurate event stream + a matching Composition, so the whole show
runs with no key and no cost. In LIVE mode the button POSTs the text box to
`crew.flow.compose_flow` and renders the real `state.events` / `state.composition` through
the **same** code path. If a live call fails on stage, the UI falls back to the replay, so
a dead key never blanks the screen.

## Files

- `app.html` — the entire UI (one content-only file: `<style>` + markup + `<script>`, no
  `<html>`/`<head>`/`<body>`). It carries two placeholders (`/*__PIXEL_FONTS__*/` and
  `__EMBED_AUDIO__`) that get filled at serve/publish time, so the source stays small.
- `server.py` — a dependency-free stdlib server (like `crew/trace_portal.py`): serves the
  page (inlining the fonts), serves the rendered WAVs at `/audio/<name>` with HTTP Range,
  and exposes `POST /api/compose` for the live path.
- `fonts/` — the two pixel webfonts (Press Start 2P + VT323, OFL), inlined as @font-face
  data URIs (the artifact CSP blocks font CDNs). The Devanagari logo has no pixel face, so
  it is rendered as a pixel-canvas (real glyphs rasterised small + upscaled nearest-neighbour).
- `build_artifact.py` — produces the SELF-CONTAINED artifact file (fonts + a short real WAV
  clip baked in) for publishing to claude.ai.

## Audio

The player plays the **FluidSynth-rendered WAV** (the real distortion-guitar/sitar sound
from `src/render.py` + `MuseScore_General.sf3`) through an `<audio>` element — not an
in-browser synth. Live mode plays `state.wav_path`; replay plays a real `out/*.wav`. The
piano-roll visualiser reads the `Composition` and follows the WAV's clock. The finished
song auto-plays when the run ends. (The published Artifact embeds a short mono clip so it
still has the true sound with no server.)

## What's real vs. still a mock

- **Real:** the pixel-art stage + 10 mascots, pixel type throughout, the event-driven
  choreography (spotlight, speech bubbles, cooperate/debate money-moment banners), the
  session log, and the WAV player + synced piano-roll visualiser.
- **Mock:** the embedded `DEMO_EVENTS` / `DEMO_COMPOSITION` in `app.html` and the demo WAV.
  The events are hand-authored to match `UI_CONTRACT.md` §4 exactly (Rasik `pakad/idiom/rasa`,
  Producer's 9 criteria, both money moments, a revise round). Capturing ONE real trace — or
  flipping on LIVE — replaces them with the real thing through the same code path.

## Dev knob

`window.SHRUTI_SPEED` (default 1) scales the event pacing at runtime — set it low to slow
the walkthrough for a talk, or high to fast-forward. Set it in the console or an init script.
