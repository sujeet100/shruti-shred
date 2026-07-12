# UI Contract — Shruti Shred (Raga × Metal agentic composer)

**Audience:** the separate Claude (Fable) session that builds the demo UI.
**Purpose:** everything the UI needs to render a composition run, without reading the
agent internals. Build against the two contracts below; treat everything in `crew/*.py`
that isn't named here as private.

The demo shows a multi-agent system compose Hindustani-classical × metal fusion live:
the band **cooperates** to build the music, the critics **debate** it, a Conductor
**rules**, and the result **renders to audio**. The UI's job is to make that visible —
primarily as a **live event timeline** plus an audio player.

---

## 1. The one integration seam: the `DebateEvent` stream

The whole pipeline speaks ONE UI-facing contract: an ordered list of **`DebateEvent`s**
(`crew/contracts.py`). Every stage emits events of this shape, and — this is the point —
the events are **identical whether they come from a live run or a canned replay**. So the
UI renders `DebateEvent`s and never touches the crew internals or the LLM output.

There is a second contract, the **`Composition`** (the rendered score / the WAV), for
when the UI wants to play or visualize the finished music. See §7.

Do **not**: reach into `Arrangement`/`Layer`/agent classes, parse any LLM JSON, or depend
on module-private helpers. The event stream + the `Composition` are the only stable APIs.

---

## 2. Entry points — how to run a composition

All live entry points are in `crew/flow.py`. A run needs `GEMINI_API_KEY` in `.env`
(billing is LIVE — see §6 for the free offline path).

```python
from crew.config import load_env
from crew.flow import compose_flow

load_env()                                    # loads .env once (idempotent)
state = compose_flow("a dark doom fusion in Darbari, key of D")
```

`compose_flow(query: str, *, max_rounds=2) -> ComposeState` runs the **whole pipeline**
(interpret → compose → generate → 3 critics → Conductor → bounded revise* → render) and
returns the final state. The fields the UI cares about:

| field | type | meaning |
|---|---|---|
| `state.events` | `list[DebateEvent]` | **the event stream** — the ordered timeline to render |
| `state.composition` | `Composition \| None` | the finished score (§7) |
| `state.wav_path` | `str \| None` | path to the rendered WAV (None if fluidsynth absent) |
| `state.round` | `int` | how many revise rounds happened |
| `state.ruling` | `ConductorRuling \| None` | the final accept/revise decision |

Serialize the stream to plain JSON (exactly what the UI should consume) with:

```python
payload = [e.model_dump(mode="json") for e in state.events]
```

There is also `crew/band.py::compose_from_query(query) -> (Composition, list[DebateEvent])`
if you want just the music + events without the critique/Conductor loop.

---

## 3. `DebateEvent` schema

```jsonc
{
  "type":    "info | propose | critique | debate | verdict | validate | revise | render",
  "agent":   "Interpreter | System | Pandit | Riffsmith | Lead | Riff | Ustad | Rasik | Producer | Conductor | Flow",
  "role":    "system | composer | generator | critic | conductor",
  "text":    "human-readable line to show",
  "verdict": "legal | illegal | accept | revise | null",   // present on some events
  "scores":  { "criterion": 0.0 } ,                         // present on critic events; null otherwise
  "round":   1,                                             // debate/revise round; null when N/A
  "data":    { ... }                                        // per-event extras (reasoning, violations, ...)
}
```

- `type`, `agent`, `role`, `text` are always present.
- `verdict`, `scores`, `round`, `data` are optional — render defensively (any may be
  `null`/absent).
- **`role` is your styling key** (color/lane by role: system, composer, generator, critic,
  conductor). **`agent`** is the display name of the speaker. **`type`** is what happened.

---

## 4. Event catalog — what actually fires, per stage

This is the authoritative list of events a live `compose_flow` run emits, in order. Use it
to design the timeline. (Payload keys are under `data` unless noted.)

### Intake — the Interpreter (`role: system`, `agent: Interpreter`)
- `info` — `"heard: {...}"` (what the user's words extracted to)
- `info` — `"note: ..."` (one per extraction observation, e.g. an unsupported raga left open)
- `info` — `"brief: ..."` (the resolved brief)

### Composer dialogue — Pandit ⇄ Riffsmith (`role: composer`)
- `info` `agent: System` — `"Composer dialogue: ..."` setup line, has `round`
- `propose` — the **opening** turn (round 1). `agent: Pandit|Riffsmith`, `text` = the
  in-character argument, `data: { draft: "<summary>", reasoning: "<monologue>" }`, `round`
- `debate` — each **subsequent** turn (rounds 2+), same shape as `propose`
- `info` — `"agrees — the chart serves both sides."` when a composer concedes early

### Generation — Lead & Riff (`role: generator`)
- `propose` `agent: Lead` — one per lead-active section. `text` = e.g.
  `"taan: 12 notes over 16 beats [third]"`, `data: { reasoning: "<phrase plan>", voicing:
  "sitar|guitar|unison|octave|third", swaras: [...] }`
- `propose` `agent: Riff` — one per rhythm-active section. `text` = e.g.
  `"riff: 2-bar riff, 8 notes/cycle"`, `data: { reasoning: "...", swaras: [...] }`
- `info` — `"no lead/rhythm-active sections ..."` when a voice sits out

> The collaboration feature (in progress) will add **canvas** events here — the band
> building a section together (leader proposes → follower responds → refine). Design the
> generator lane to accept more event kinds gracefully (see §8).

### Critique — three orthogonal critics (`role: critic`, `type: critique`)
All three fire once per round, in this order:

- `agent: Ustad` — **legality**. `verdict: "legal" | "illegal"`, `text` = explanation,
  `data: { violations: [ {layer, swara, start_beat, kind, reason} ], reasoning }`.
  **No `scores`** (legality is binary, code-decided).
- `agent: Rasik` — **raga authenticity**. `scores: { pakad, idiom, rasa }` — each an
  integer **1–5** (as float). `text` = the critique, `data: { reasoning }`.
- `agent: Producer` — **composition quality**. `scores: { structure, dynamics, climax,
  motif, hook, balance, independence, mood_fit, repetition }` — each **1–5**. `text` +
  `data: { reasoning }`.

### Debate + ruling — the Conductor (the money moment)
Only fires when the Conductor's triage finds an **aesthetic conflict** (a legal-but-flagged
piece); a clean piece is accepted with no debate, an illegal one is force-revised with no
debate.
- `info` `agent: System role: system` — debate setup line, has `round`
- `debate` `agent: Rasik|Producer role: critic` — each debate turn. `verdict` = that
  critic's `stance` (`accept|revise`), `data: { reasoning, target_layer }`, `round`
- `verdict` `agent: Conductor role: conductor` — the **ruling**. `verdict` = `accept |
  revise`, `text` = the surgical directive, `data: { reasoning, layer }`

### Revise loop + finish — the Flow (`role: system`, `agent: Flow`)
- `info` — `"Revise round N: regenerating '<layer>' per the Conductor."` (then the
  regenerated voice re-emits its `propose`, and the critics re-fire → a new round)
- `info` — `"Revise cap (N) reached — accepting the last version."` at the clock limit

### ⚠️ Reserved-but-not-emitted event types
`validate`, `revise`, and `render` exist in the `EventType` enum but the **live flow does
not emit them today** — validation surfaces inside Ustad's `critique`, a revise shows as a
Flow `info` + a fresh `propose`, and the render result is `state.wav_path` (no event). Do
**not** build the UI to wait on these. (If the UI wants an explicit "rendered" beat, ask
the backend session to add a `render` event — it's a one-liner.)

---

## 5. The timeline the UI tells

The natural demo arc (and the two "money moments" to spotlight):

```
Interpret  →  Composers COOPERATE (dialogue)  →  Generate voices
           →  3 Critics score  →  Rasik ↔ Producer DEBATE  →  Conductor rules
           →  [revise → re-critique]*  (bounded)            →  Render → audio
                    ↑ money moment: cooperate            ↑ money moment: debate
```

Everything is **bounded and always terminates** — that's the project's thesis. `round`
increments across revise loops; the Conductor's `verdict` on the final `verdict` event is
the outcome.

---

## 5.5 Personas (for mascots / avatars)

Every event's `agent` field names the speaker, and the set is **stable** — assign one
mascot/sprite per persona and the demo tells itself as the mascots take turns. Key the
sprite off `agent`, and the lane/color off `role`.

| agent | role | who it is | mascot idea |
|---|---|---|---|
| Interpreter | system | turns the user's words into a brief | a listener / ear |
| Pandit | composer | the tradition-keeper (raga soul) | a classical guru |
| Riffsmith | composer | the metal side (groove, weight) | a headbanger |
| Lead | generator | the melodic voice (sitar / lead guitar) | sitar-player |
| Riff | generator | the rhythm guitar | a chugging guitarist |
| Ustad | critic | legality judge (*is it in the raga?*) | a stern examiner |
| Rasik | critic | raga-authenticity judge (*does it sound like the raga?*) | a discerning connoisseur |
| Producer | critic | composition-quality judge (*does it work as a song?*) | a studio producer at a desk |
| Conductor | conductor | the arbiter who rules accept/revise | a baton-wielding maestro |
| System / Flow | system | narration / plumbing | neutral badge, not a character |

The two **money moments** to spotlight visually: the creative voices **cooperate**
(the coming canvas events — Lead ⇄ Riff building a section together), then Rasik and
Producer **debate** while the Conductor rules. Cooperate → argue → verdict.

## 6. Offline development (recommended — zero LLM cost)

You do **not** need an API key, fluidsynth, or a live run to build the UI. Two options:

**a) The replay harness.** `crew/replay.py` re-emits a recorded list of event dicts through
the same contract:

```python
from crew.replay import replay, SAMPLE
stream = replay(SAMPLE)            # or replay(your_captured_json)
events = stream.to_list()          # list[dict], the shape the UI consumes
```

> ⚠️ `replay.SAMPLE` is an **old hand-written sketch** — its critic `scores` keys
> (`pakad_present`, `energy`) are **stale** (pre-Producer split). Use it only to exercise
> the event *shape*. The **authoritative** score keys are in §4 (Rasik: `pakad/idiom/rasa`;
> Producer: the 9 listed). Best practice: capture a **real** trace once (below) and develop
> against that.

**b) Capture one real trace, then iterate offline.** Run `compose_flow` once (costs a few
LLM calls), dump `[e.model_dump(mode="json") for e in state.events]` to a JSON file, and
build the entire UI against that file via `replay(json.load(...))`. Only the final demo
runs live.

---

## 7. The `Composition` contract (for score display / audio)

If the UI wants to visualize the score or play audio, `state.composition` is a
`Composition` (`crew/contracts.py`):

```jsonc
{
  "raga": "darbari", "sa": 62, "bpm": 120,
  "tala": { "name": "teentaal", "beats_per_bar": 16.0 },
  "layers": [
    { "role": "drone|lead|rhythm|bass|drums|tabla",
      "instrument": "sitar", "program": 104, "channel": 2, "pan": 44,
      "notes": [ { "swara": "g", "oct": 0, "start": 0.0, "dur": 1.5, "vel": 90,
                   "grace": ["S"], "meend_swara": "m", "chord": ["S"], "technique": "palm_mute" } ],
      "hits":  [ { "drum": "kick", "start": 0.0, "dur": 0.2, "vel": 110 } ] }
  ]
}
```

- **Sargam** (semitones from Sa): `S0 r1 R2 g3 G4 m5 M6 P7 d8 D9 n10 N11` — lowercase =
  komal (flat), `M` = tivra Ma (sharp). MIDI pitch = `sa + semitone(swara) + 12*oct`.
- `start`/`dur` are in quarter-note beats. `pan` is MIDI CC10 (0=L, 64=C, 127=R).
- `role` distinguishes voices; `hits` (not `notes`) is for the drum kit / tabla.
- Audio: `state.wav_path` points at a rendered `.wav` (requires fluidsynth + the soundfont
  on the backend; `None` otherwise). For the UI, prefer serving that file to an `<audio>`
  element over re-synthesizing.

---

## 8. Forward-compatibility (important)

The backend is actively growing. The **cooperative-collaboration** feature will add new
generator-lane events (a shared "canvas": leader proposes → follower responds → bounded
refine), and full-song form will add more sections (so more `propose`/`critique` events).
Build the UI to **degrade gracefully on unknown `type`/`agent` values** — render an unknown
event with its `text` in the lane keyed by `role` rather than dropping it or crashing. The
`role` set (system/composer/generator/critic/conductor) is stable; the `type` and `agent`
sets may gain members.

---

## 9. Live streaming (a seam that does NOT exist yet)

Today events are **collected** into `state.events` and available only when
`compose_flow` **returns** — there is no incremental push during the run. For a live
"watch it happen" UI you have two choices:

1. **Simplest, works now:** run to completion, then play the `state.events` list back in
   the UI with your own pacing/animation (identical to replay). Great for a controlled demo.
2. **True live streaming (Phase 3, needs a small backend addition):** an SSE/WebSocket
   endpoint that runs the flow and emits each `DebateEvent` as it's produced. This requires
   the **backend** session to thread an event sink through the flow stages — it is **not**
   the UI session's job. Coordinate with the backend session if you want this; until then,
   use option 1.

---

## 10. Quick reference

| you want… | use |
|---|---|
| the event timeline | `compose_flow(query).events` → `[e.model_dump(mode="json") …]` |
| to build with no cost | `crew/replay.py` + a captured trace JSON |
| the finished score | `state.composition` (§7) |
| the audio | `state.wav_path` |
| the outcome | `state.ruling.directive` / the final `verdict` event |
| event shape | §3 · what fires when | §4 · the demo arc | §5 |

**Golden rule:** the UI consumes `DebateEvent`s and the `Composition`. It never imports an
agent, parses LLM output, or depends on anything not in this document.
