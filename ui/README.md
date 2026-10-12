# Shruti Shred — the demo UI

A pixel-art, point-and-click-adventure-style front end for the raga × metal agent band.
It speaks ONLY the two `UI_CONTRACT.md` seams — the **`DebateEvent`** stream (the timeline)
and the **`Composition`** (the audio/score). It never reaches into agent internals.

## Run it

```bash
uv run python -m ui.server          # -> http://127.0.0.1:8500
```

Open the printed URL and press **Compose**. Two independent switches drive the show, and
you can flip either at any time (including mid-run):

- **Source — `Demo | Live`** (in the input bar). *Demo* plays the embedded,
  contract-accurate event stream + a matching Composition, so the whole show runs with no
  key and no cost. *Live* POSTs the text box to `crew.flow.compose_flow` and renders the
  real `state.events` / `state.composition` through the **same** code path. The Live
  segment is only selectable when the server sees a `GEMINI_API_KEY` (it turns hot-magenta
  when armed — Gemini billing is on). The default is always the cost-safe **Demo**; pass
  `RMA_UI_LIVE=1 uv run python -m ui.server` to make Live the default toggle position. If a
  live call fails on stage, the UI falls back to Demo, so a dead key never blanks the screen.
- **Walkthrough — `Auto | Step`** (under the sentence line). *Auto* plays the event stream
  on a paced timer (the classic show, auto-plays the finished WAV at the end). *Step* freezes
  on each event and advances only when you press **NEXT ▸** (**◂ BACK** rewinds) — or the
  keyboard: **→ / Space** = next, **←** = back. A live run first collects the whole stream,
  then you walk the audience through it one beat at a time. The finished song reveals at the
  last step with **Play** enabled but paused, so you time the reveal yourself.

A run is one `DebateEvent` stream (Demo or Live) played back in whichever mode is selected —
so **Demo + Step** lets you rehearse the audience walkthrough for free, then flip to
**Live + Step** on stage. This matches `UI_CONTRACT.md` §9 option 1 (collect the stream,
then pace it in the UI); no backend streaming is needed.

## The roster on stage (the redesign, 2026-10-11)

The stage mirrors the crew as it is now built (CLAUDE.md "Architecture", DESIGN.md "THE
REDESIGN"), with one room per kind of ownership:

- **Intake** — the **Interpreter** (LLM) turns the query into the brief.
- **Writers' room** — whoever writes the chart. With `RMA_COMPOSER` on it is the single
  **Composer** (one SEED call co-writes the chart, the main riff and the hook, then DEVELOP calls
  write each section around it). With the flag off it is the legacy **Pandit ⇄ Riffsmith** pair.
  The server's flag only sets the IDLE roster. Once a run streams, the events decide: a
  `Composer` event switches the room to the one owner, a `Pandit`/`Riffsmith` event to the legacy
  pair.
- **Live room** — the two creative voices, **Lead** (sitar) and **Riff** (guitar), plus the
  **Orchestra**, which appears only when a symphonic chart actually summons it (one LLM call for
  the intent, which code expands into strings, brass, choir and timpani). A `CODE` rack lists the
  deterministic voices (drone, jod, bass, drums, tabla, clean guitar); each lights up once the
  finished composition carries it.
- **Control room** — **Ustad** is a terminal, not a character, because it is CODE
  (`validate_composition`, no LLM): its readout is the validator's result. **Rasik** is the raga
  consultant (pakad/idiom/rasa scores and at most three lead-only suggestions, with no authority).
  The **Producer** is the one judge whose call stands.
- **Listening booth** (where the Conductor's riser used to be) — the advisory **Listener**. It is
  dimmed unless `RMA_LISTEN` is on or a `Listener` event arrives.

The **flow strip** under the sentence line lights the pipeline step by step: interpret → seed
(or chart) → develop (or generate) → code voices → Ustad → Rasik → Producer → triage → revise
(↺, bounded by `MAX_ROUNDS`) → render → listen. Steps that are pure code have a dashed border.

The **judging desk** (full width, under the log and player) shows the latest of each verdict:
Ustad's LEGAL/ILLEGAL and its first violations; Rasik's three scores and suggestions (sections
numbered from §1, as the piece's structure numbers them); the Producer's ten-criterion rubric and
decision; the **final call** with its `RevisionPlan` (voice, where, what to do, and what to KEEP),
plus who made the call; and the listening report (observations plus code's consistency). The
final call is triage, which is code: an illegal piece is a forced revise (VERDICT from `Ustad`), a
lead the audience can't hear is a forced revise (recognised by its text, since it is emitted as
`Producer`), and otherwise the Producer's own call stands.

The Conductor, the critic debate and the Arranger are gone. Old streams still replay: a
`Conductor` ruling (`data.layer`) shows as a retired final call on the Producer, and a retired
`DEBATE` event from a critic is logged dimmed with a `[retired debate]` tag and no banner.

The server advertises the crew's shape as `window.SHRUTI_FLOW = {composer, listen, max_rounds}`
(also in `/api/health`), read from the import-light `crew.config`.

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
piano-roll visualiser reads the `Composition` and follows the WAV's clock. In **Auto** the
finished song auto-plays when the run ends; in **Step** it reveals paused at the last event
so you press Play on cue. (The published Artifact embeds a short mono clip so it still has
the true sound with no server.)

## What's real vs. still a mock

- **Real:** the pixel-art stage and its roster, pixel type throughout, the event-driven
  choreography (spotlight, speech bubbles, the core-idea and final-call banners), the flow
  strip, the judging desk, the session log, and the WAV player + synced piano-roll visualiser
  (which now also draws the clean guitar, the jod and the orchestra lanes).
- **Mock:** the embedded `DEMO_EVENTS` / `DEMO_COMPOSITION` in `app.html` and the demo WAV.
  The events are hand-authored in the shapes `crew/` emits today, in composer mode: the
  Composer's seed, the developed riff and lead, Ustad's code verdict, Rasik's scores plus
  suggestions, the Producer's ten criteria with a `RevisionPlan`, the VERDICT
  (`data = {decision, plan}`), one revise round, an accept, and an advisory listening report.
  Capturing ONE real trace, or flipping on LIVE, replaces them with the real thing through the
  same code path.

## Dev knob

`window.SHRUTI_SPEED` (default 1) scales the **Auto** pacing at runtime — set it low to slow
the walkthrough for a talk, or high to fast-forward. Set it in the console or an init script.
(In **Step** mode pacing is entirely manual, so this knob has no effect there.)
