# Handover — talk deck + the A/B/C experiment + the riff proposal (2026-10-11, ~21:50)

Written by the deck session (raga-metal-agents-63) at ~55% context. Everything below is either
built and published, or a proposal waiting on Sujit's go. Nothing here is committed to git; the
`talk/` tree is untracked.

## 0. Concurrency warning — read first

Another session (`raga-metal-agents-88`) has large UNCOMMITTED edits in product code:
`src/raga.py`, `src/render.py`, `crew/{contracts,lead,riff,riff_texture,flow,band,composers,
gat_verifier,interpreter,producer,orchestra,rasik,evals}.py`, `crew/config/{tasks,lead_roles}.yaml`,
tests, `CLAUDE.md`, `DESIGN.md`, `TALK.md`. It is adding riff PLAYABILITY checks (`crew/riff_playability.py`,
`verified_riff(extra_check=...)`) and a stated song length (`duration_s`). The deck session did NOT
touch product code. Do the riff/crash work below in THAT session, or after it commits.

## 1. The deck (Claude Slides artifact)

- URL: https://claude.ai/artifact/9fb9xNiGt1rF8UWXMQ82ja — **Version 33** is live.
- Source of truth: `talk/deck/build.py` → `talk/deck/project/slides/*.html` + `project/deck.json`.
- Every change: `python3 talk/deck/build.py` → `python3 talk/deck/preview.py [ids]` (look at the PNGs) →
  `python3 talk/deck/clickcheck.py | grep -c BLOCKED` (must be 0) → publish `project/deck.json` with the
  changed slides in `files` (root `talk/deck`).
- Viewer facts learned the hard way: empty unpainted divs are dropped; padding caps at 256px; a clip must be
  top-level and painted LAST (section() does it; build guards fail otherwise); a clip starts only WITH ITS
  SLIDE (or a click on it) and loops — to sync sound with something appearing, draw the visual INTO the clip.
- Structure (53 main slides + annex): cover, perform, reveal (two rows) → twelve (question) + notes1–3
  (self-playing keyboard clips K1–K3, drawn by `talk/audio/keyboard_video.py`) → raga (Bhairav's 7 of 12 +
  Devanagari term cards) → bhairav → song (LEAD / RHYTHM / COLOUR groups) → naive (THE EXPERIMENT, §2) →
  rules → vote → steer → Part 1 = 11-step BUILD STORY (`STEPS`, `s_step`, `band_graph(step)`: agents at fixed
  seats fill in, new = gold, code = cyan chips on the wiring, rulebook bar; pattern slides follow the step that
  created them) → `band` recap (whole graph assembles itself) → war stories → demo → close → ANNEX
  (hindustani, form).
- Placeholders still open: [event · date], [repo link], [contact], the Producer quote on `debate`
  ("[FROM A FRESH TRACE]"), A07 (blackboard clip), A11 (demo branches — needs Sujit's go), test count "760+".

## 2. The experiment slide (naive) — what is real and what we learned

All three are REAL output, one-minute songs, with a "song map" (4 rows × 32 bars from the notes; lit = plays,
magenta = forbidden note, gold tick = a sitar bar that returns):
- **A** = ONE bare Gemini call (Google SDK directly: prompt only, no system prompt, `config: None`; request saved
  in `talk/audio/build/pureA_request.json`). **B** = same prompt + the raga grammar from `src/raga.py`.
  **C** = the opening song (`out/fusion_20261011_194039.{wav,json,arrangement.json}` — Bhairav, heavy, teentaal,
  128, Sa=E, 65 s, studio on, accepted round 0; this is also the A01 backing track).
- Scripts: `talk/audio/pure_songs.py [raga] [stem] [A|F|B|C]` (clips FA/FB/FC Bhairav, GA/GB/GF Bageshree),
  rendering exactly as written via `band_ladder.layers_of`. Earlier attempts kept for the record:
  `ladder.py` (melody-only — dropped: today's Gemini writes LEGAL fluent Bhairav melodies unaided, so A/B/C
  sounded alike) and `band_ladder.py` (16/24-beat endings).
- Measured (Bhairav): A = 92 forbidden notes (guitar plays E-minor metal), sitar repeats 1 of 32 bars, every part
  plays every bar. B = legal, phrases repeat in 4-bar blocks, still every part every bar ("never breathes").
  C = legal, shaped (sitar alone → band enters → sitar drops for the breakdown → hook returns varied → taan).
- **Sujit's verdict: A sounds best — its RIFFS are better than B and C.** Measured why: A's guitar = power chords
  on EVERY stroke, half-step B5–C5 shuffle, sixteenth gallops, ~50% off-beat. In Bhairav those roots (Pa, komal
  dha) need fifths the raga forbids (F#, G) — A is the best metal and the worst Bhairav. C's riff = 71% single
  palm-muted chugs on Sa, only 15% chords (thin). B = block chords on the beat (plods).
- Bageshree run (Dorian; 6 of 7 roots keep a legal fifth): A legal (0 forbidden), power chords on Pa; B legal,
  never rests; **A+form** ("The song should include an intro, alap, gat (mukhada + manjha), antara and taans.")
  = only a density ramp (sparse → sixteenth taans); drums from bar 1 (no real alap), mukhada never returns, 32
  forbidden notes (shuddha Ga), parts disagree on length → "naming a section isn't knowing what it does".
  **Bageshree C does not exist yet** (both full runs crashed — §4).
- Slide verdict chips now: "92 WRONG NOTES · NO MOTIF" / "IN THE RAGA · NEVER BREATHES" / "HOOK RETURNS · HAS A
  SHAPE". Proposed (not built): reframe as a vote — the room likely picks A; reveal "best metal, worst Bhairav".

## 3. Proposal: make the riff heavy inside the raga (Sujit said "go ahead make changes" — NOT built, see §0)

Evidence: `talk/audio/revoice.py` (free, no LLM) re-voiced the opening song's riff — every stroke root + dyad +
octave — and rendered it with the raga validator ON: chord share 15% → 100%, all legal
(Sa→E5 222, komal re→F5 44, Ga→G#5 32, Ma→A5 2, Pa→fourth B+E 10, komal dha→fourth C+F 4).
Listen: `talk/audio/RV_ab.wav` (original, then re-voiced, the hook's full-band return), `RV_orig_full.wav`,
`RV_revoiced_full.wav`. Research behind it: `talk/research/rhythm-guitar-harmony.md` (sources + reliability).

Spec (one step, pure, tested):
1. A deterministic VOICING PASS in `crew/riff.py::rhythm_layer_from` (pure, raga-aware, shared by the parallel
   AND studio paths), BEFORE the Arranger/coexistence so they see the real chord tones. For each sounding stroke
   whose `chord` is empty or only its own octave: chord = [fifth, root] if the fifth is legal, else
   [fourth, root], else [root]. The renderer seats a fifth +7, a fourth +5, the own swara +12 (`_CHORD_SEATS`).
   Keep a model-chosen colour chord as written.
2. Skip DIRECTION-RESTRICTED chord tones (`raga.directional_varjya`: Bageshree P and R are descent-only) — so
   Bageshree's Sa takes the fourth (Sa–Ma, its Ma-tuned tanpura / Ma-vadi home dyad) rather than the weak Pa.
3. Never add an ANDOLAN swara (`RAGAS[r]["andolan"]`: Bhairav r,d; Bageshree g) as a chord tone on a stroke
   longer than 1 beat — a held tempered tone fights the sitar's sway (research principle 2). Short stabs are fine.
4. Riff prompt (`tasks.yaml`): code voices bare strokes as power chords, so write roots + rhythm; write `chord`
   only for deliberate colour; invite the half-step shuffle between legal-fifth roots (Bhairav Sa–komal re =
   E5–F5) and gallops.
5. COORDINATE with `riff_playability`: chords added AFTER the playability check could make a playable riff
   unplayable at speed — either voice before the check or teach the check about dyads.
6. Decide later (Sujit, purist call): an out-of-raga power-chord fifth as "timbre". Research found no source;
   recommendation is stay strict (fourths cover the illegal-fifth roots).
Pure tests: legal by construction for every raga; fifth vs fourth choice; Bageshree directional skip; andolan
long-note rule; explicit colour chords kept; rests untouched; then the existing riff/band/arranger suites.

## 4. Crash fix (proposed, not built)

Two Bageshree full runs died on a strict LeadPhrase validation raised INSIDE CrewAI's native Gemini provider
(no bounded retry): (1) a note with `dur: 0.0` (`Field(gt=0)`), (2) a note with `swara: "rest"` (the format's
rest is `"rest": true` + any swara). Present in COMMITTED code too (not caused by the other session), and a
live-demo risk. Fix per the project's own rule ("schema validates shape, junk is normalized at the boundary";
`_known_chord` already absorbs junk): a before-validator on LeadNote/RiffNote/LeadPhrase notes turning swara
"rest"/"-" into a real rest, and dropping dur ≤ 0 notes at the boundary. Free test feeding both slips.
Then re-run the Bageshree C render (ASK first; and only once the other session's working copy is settled —
the two crashed runs ran on a half-edited tree).

## 5. Other open items

- The opening song's ending: the sitar's taan ends at beat 110.5, then a single Sa held 16 beats (inaudible on a
  plucked sitar) → the last cycle is band-only. Candidate: cap the lead's hold at a taan end (verifier), or fix
  in Logic.
- Slide 11 for Bageshree (GA / GF / GB + GC once rendered) — not built.
- "Rules" slide headline: kept ("Following the rules gets you correct. It doesn't get you music.") — B fits it.
- Memory: `talk-deck.md` in the session memory dir records the deck + these lessons.
