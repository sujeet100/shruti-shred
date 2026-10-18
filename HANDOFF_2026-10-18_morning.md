# Handoff — the deck is rebuilt, the experiments are in, next: ReAct tools + a challenger (2026-10-18)

Read this first, then CLAUDE.md (Status, last bullets) and TALK.md ("2026-10-18 — what measuring
taught us"). The previous handoff is `HANDOFF_2026-10-11.md` (history only).

## 1. State of the tree

- **Nothing is committed.** ~30 changed paths (`git status`); `talk/` and `out/` are untracked.
  Earlier sessions' uncommitted work is mixed in (rhythm_section*, contracts, tasks.yaml,
  riff_notation) — leave what you did not change alone.
- **Suite: 1263 pure tests green across 62 files.** Run every file (no pytest in the env) and check
  EACH file's x/y, not just that "passed" appears (that mistake hid 3 failures once):
  `for f in tests/test_*.py; do uv run python $f | tail -1; done`.
  Run with a dummy key (`GEMINI_API_KEY=invalid`) so a test that reaches a model fails instead of billing.

## 2. What changed this session

**Product (crew/, src/)**
- **The five-agent path is the DEFAULT** (`RMA_COMPOSER`, `RMA_RHYTHM_SECTION` default ON; `=0` = legacy).
  Five agents: Interpreter, Composer, Rhythm section, Rasik, Producer (+ Orchestra on symphonic
  charts; advisory listening judge off). Legacy Pandit/Riffsmith/Lead/Riff still exist in code.
- **Bhairav andolan corrected** (research: Parrikar, Ragajunglism, van der Meer & Rao measured
  Gundecha's dha): approached FROM ABOVE in descent (kan G→r, N→d), a small sway UP inside the swara
  (`ANDOLAN_DEPTH_ST` 0.2), plain when the line rises THROUGH r/d. `src/raga.py` (ANDOLAN_TOWARD,
  ANDOLAN_DEPTH_ST, ANDOLAN_ONLY_IN, Bhairav kan) + `crew/expression.py` (`_off_direction`). Darbari
  untouched. FLAG kept: ITC "re within the periphery of S" (read as pitch, not a swing).
- **Seed-debate harness fixed**: a gat seed's head is always composed by the gat call
  (`seed_debate.needs_head` — the composer's sketched hook is ignored, as the system ignores it);
  key/record saved per prompt; one retry on the brief; `--into/--first` to continue a run.
  `lead.compose_head`, `audition.head_arrangement`, `seed_debate_crew.llm_head`.

**Talk tooling (talk/)**
- Deck rebuilt: `talk/deck/story.py` (35 slides) is the source; `build.py` is the retired pixel deck.
  Pieces: `title_slides.py` (title), `titles/score_graph.py` (the motif), `visuals.py` (icons/charts),
  `keyboard.py` (music-101 keyboard), `titles/devday-logo.png` (OFFICIAL logo — never redraw).
- Audio: `talk/audio/raga_clip.py` + `keyboard_video.py K4` (Bhairav aroha/avaroha/chalan clip, now
  with the corrected andolan), `restyle_clips.py` (light-theme clips + the Bageshree before/after BG).
- Experiments: `pure_songs.py` (bare A/B; model 3.8 default; Bhairav re-run writes HA/HB),
  `system_song.py <raga>` (song C via the full system), `idiom.py` (raga checks + `--rasik`),
  `compare_songs.py` (whole-song measures). Results: `talk/audio/single_prompt_results.md`.

## 3. The deck

- Live: https://claude.ai/artifact/9fb9xNiGt1rF8UWXMQ82ja (**Version 48**). Publish procedure:
  `python3 talk/deck/story.py` → `python3 talk/deck/preview.py <ids>` (LOOK at the PNGs) →
  `python3 talk/deck/clickcheck.py | grep -c BLOCKED` (0) → publish changed `project/slides/*.html`
  (+ `project/deck.json` only when order/faces change), root `talk/deck`. New images/clips: upload
  as assets, record the blob in the matching `assets.json`.
- Sujit's direction (memory `talk-story-direction`): title "Lessons from an Agentic AI Raga-Metal
  Band"; DevDay indigo title + act dividers; light content slides; Zilla Slab + Mulish; visuals over
  text (characters = the agents, real data as charts); not corporate, no gimmicks; audience knows no
  music (one plain line per idea + the music-101 keyboard slides). Rejected motifs: cycle arrows,
  robot arm, copied pipe-routes, corner ornament, pixel grid/sound wave, kites. Current motif: a
  staff becoming an agent graph (title), tangle / straight line / clean five (acts).
- **Open on the deck:**
  1. The experiment slide (`naive`) still shows the 2026-10-11 songs on gemini-3.5 ("92 wrong
     notes"). On 3.8 the bare call plays 0 forbidden notes — re-tell it with the 3.8 Bhairav songs
     (HA/HB vs the system's `out/fusion_20261018_142210_bhairav`) and the new finding: right notes,
     wrong raga (Rasik mood 2-3 vs 4). Its "never breathes" claim is partly our prompt's wording.
  2. Add the "every pattern has a precondition" slide + a human-in-the-loop slide (TALK.md).
  3. The trace/plan slides use the Bageshree run as a placeholder for the voted branch (vote
     branches need rendering — live, ask). `[repo link] [contact]` on the close.
  4. A lesson for "a judge optimises what you show it" (debate transcripts) — L4 or a new L8.

## 4. Experiment results (details in TALK.md and the results file)

- **Single prompt, 3 ragas × A/B/C on 3.8**: the system is musically strongest on every measure
  that is a fair comparison (power chords 81-100% vs 21-33%, hook returns 3 vs 0-2, parts end
  together, Rasik mood 4 vs 2-3). Its faults: Bhairav C never breathes (every part every bar, flat
  dynamics); Darbari C never holds ga/dha (0 of 47) so never sways. Confounds: the bare prompt's
  "every part playing for the whole length"; no ornament field in the bare format.
- **Seed debate, round 3**: P1 Bhairav song — Sujit: debate > best-of > single. P2 Darbari gat —
  single > debate > best-of ("X more weight, real character"); P2 heads were the composer's
  SKETCHES (harness bug, set aside in `out/seed_ab_20261018_124223/p2_seed_sketches_not_the_gat_test/`).
  Every debate turn rewrote ~half the notes and most rhythm, citing our measurements. GPT's review
  (pasted in the session): keep debate out; remove measurement tie-breakers; critics notes-first.
  **Decision: debate stays parked.**

## 5. Next session (Sujit, 2026-10-18)

1. **ReAct with real tools** — give the Composer tools that return what it cannot see, called
   mid-composition, e.g.: `audit_ornaments(phrase)` (render the phrase, run `src/ornament_audit`
   / `crew/pitch_audit` — does any bend linger on a foreign pitch?), `dwell_report(phrase)` (how many
   andolit swaras are held long enough to sway — Darbari C held 0 of 47), maybe `texture(section)`
   (who is playing). Design first: which tools, CrewAI tool wiring (`crewai.tools.BaseTool`, no
   cache), cost per call, and a pure test with a fake LLM. Then ONE live run (ask).
2. **Challenger** — one bounded counter-variation that never replaces the original: it may ACCEPT
   or CHALLENGE one concrete, audible weakness; the Composer patches one phrase (a bounded patch may
   touch the coordinated guitar); both versions render; the original wins ties; selection by
   Sujit's ear in the experiment. Compare against the unchanged original (and optionally a
   self-revision). No measurement block in its prompt (notes first).
3. **Human in the loop: TALK ONLY** (don't build) — why it is the strongest pattern here.
4. Cheap, still queued: save every Producer round's render and blind-A/B round 0 vs final (does
   the loop earn its 40% of calls?); the seed-sketch head vs gat-call head A/B (could delete the gat
   call); delete the legacy paths behind the tests; texture plan / dwell notes / dynamics from the
   energy arc (see TALK.md "what the nine songs say to change").

Rules unchanged: ask Sujit before ANY live render or LLM run; batch; trace everything; never
overwrite a render name; commit only when asked.
