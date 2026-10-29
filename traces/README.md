# traces/ — every traced agent run

Each file is one run of the agents, recorded by `crew/tracing.py` from CrewAI's event bus: the
crew, agent, LLM and guardrail steps with the full prompt, the response, token usage, timing and
retries. Read one before changing an agent's prompt (the project's rule: never guess what an agent
did). Browse them with `uv run python -m crew.trace_portal` → http://127.0.0.1:8420.

The file is `<id>.json` with `id`, `name`, `query`, `started_at` and `spans`. Early traces (July)
carry per-agent smoke-test names (`lead-demo`, `conductor-demo`); `ui-live` is a run started from
the demo UI; experiment scripts in `talk/audio/` name theirs (`seed debate experiment`, `notes
debate`, `fresh-run`, …). A trace pairs with a render in `out/` when `started_at` equals the
render's timestamp; `out/README.md` explains what each of those runs was for and what it showed.
Traces with a handful of spans are runs that aborted (an invalid key, a crash, exhausted credits);
they are kept because the failure is part of the history.

Direct google-genai audio calls (the rehearsal's ears, the listening judge) bypass the CrewAI
tracer; those experiments log their calls in their own `out/<experiment>/calls.jsonl`.

| Trace | Started | Name | Spans | Run / what it was |
|---|---|---|---|---|
| `6cb40c236412` | 2026-07-11 19:08:28 | a-doom-fusion-in-bhairavi | 30 | Interpreter + Pandit⇄Riffsmith only; no render (agent #2 smoke run) |
| `4cba8b608015` | 2026-07-11 20:05:20 | lead-demo | 8 | `lead_alaap` (Malkauns Lead smoke run) |
| `f9501050b61f` | 2026-07-11 20:35:17 | riff-demo | 8 | `riff_bass` (Malkauns Riff smoke run) |
| `c59e9423d93d` | 2026-07-11 21:30:53 | lead-demo | 11 | `lead_taan` (Darbari taan; one validation failure, then success) |
| `b6414d567b59` | 2026-07-11 21:43:13 | groove-demo | 16 | `rhythm_section` (Darbari riff + bass + drums) |
| `b6d16449c36d` | 2026-07-11 21:53:15 | band-demo | 35 | `full_band` (first full-band render) |
| `8c947c8930d1` | 2026-07-11 23:03:09 | ustad-demo | 8 | Ustad tool-call smoke run on a Bhairav piece; no render |
| `26269a101c05` | 2026-07-11 23:13:37 | rasik-demo | 6 | Rasik smoke run on a Darbari drone+lead; no render |
| `bf28522b3be5` | 2026-07-11 23:26:37 | conductor-demo | 2 | aborted/empty: failed at once on a missing `lead_line` template variable |
| `ad6b32188140` | 2026-07-11 23:27:17 | conductor-demo | 18 | Rasik → Ustad → Conductor debate on a Darbari lead; ruled revise |
| `829ac9915888` | 2026-07-11 23:28:01 | conductor-demo | 18 | Same debate, rerun; ruled revise |
| `c77e54e864fa` | 2026-07-11 23:28:42 | conductor-demo | 18 | Same debate, rerun; ruled revise |
| `32abddc84225` | 2026-07-11 23:50:14 | flow-demo | 11 | First Flow run; crashed on three Lead validation failures (malformed meend) |
| `ca1e2de2e139` | 2026-07-11 23:53:30 | flow-demo | 90 | Flow run, 21 min: Rasik idiom 2, Conductor revise, idiom 4 after; output overwritten (`flow_demo`) |
| `a7823c3eed52` | 2026-07-11 23:58:19 | flow-demo | 38 | Flow run, six LLM calls, accepted; output overwritten (`flow_demo`) |
| `49d6cff3e73a` | 2026-07-12 12:43:15 | flow-demo | 44 | Fixed-chart Flow with the Producer; ear check of steps 6/7/9/10; likely source of `diag_lead_full` |
| `a1f851a1decb` | 2026-07-12 13:39:24 | flow-demo | 44 | Same, rerun; likely source of `diag_lead_sitar` and the meend tests |
| `45fbba64235b` | 2026-07-13 23:14:47 | flow-demo | 218 | `flow_demo` (studio session, three critique rounds) |
| `f20b9d65ddcb` | 2026-07-14 19:30:29 | ui-live | 133 | First full live UI render (Bhairavi); `fusion.wav`, since overwritten |
| `fd42579d559b` | 2026-07-14 23:06:10 | ui-live | 122 | Yaman progressive Suno-style prompt; `fusion.wav`, since overwritten |
| `86f8df34e1d8` | 2026-07-15 08:30:13 | gat-development-live | 73 | aborted: "Yaman heavy metal fusion", stopped mid Lead call (no completion recorded) |
| `c70161fc1b1c` | 2026-07-15 08:50:11 | gat-development-live | 154 | Same request, completed; output overwritten (`fusion`) |
| `d5a6e178d33c` | 2026-07-15 09:08:01 | gat-development-live-final | 122 | Same request, completed (Interpreter returned bpm 2); output overwritten (`fusion`) |
| `17388136e44a` | 2026-07-15 09:22:05 | gat-development-final | 154 | `fusion` (the surviving Yaman 132 bpm render) |
| `db86de3eb881` | 2026-07-15 20:47:29 | ui-live | 178 | `fusion_20260715_204729` (Kirwani) |
| `ed5feca8f9c4` | 2026-07-16 07:23:57 | ui-live | 162 | `fusion_20260716_072357` (Malkauns; tala bug) |
| `a5cd57c59c1e` | 2026-07-16 09:46:36 | ui-live | 162 | `fusion_20260716_094636` (Malkauns, after the tala fix) |
| `c06d25022f73` | 2026-07-16 19:01:08 | ui-live | 105 | Charukeshi; died on Gemini 504 after ~15 min; no render |
| `c4d99a220733` | 2026-07-16 19:38:31 | ui-live | 107 | Charukeshi; died on Gemini 504 after ~13 min; no render |
| `36cf7ee56139` | 2026-07-16 21:37:07 | ui-live | 162 | `fusion_20260716_213707` (Charukeshi; listen-back fixes) |
| `5dd804e9e2f8` | 2026-07-16 23:33:08 | ui-live | 159 | `fusion_20260716_233308` (Darbari death; andolan finding) |
| `0fd85bdf420b` | 2026-07-17 14:16:00 | ui-live | 154 | `fusion_20260717_141600` (Darbari death again) |
| `3a80c436b5c2` | 2026-07-17 14:20:50 | ui-live | 67 | Marwa black metal; died on Gemini 503; no render |
| `ba68ecc0928a` | 2026-07-19 17:54:19 | ui-live | 154 | `fusion_20260719_175419` (Marwa black) |
| `5da349c337b8` | 2026-07-19 21:59:24 | ui-live | 178 | `fusion_20260719_215924` (Charukeshi symphonic; first Orchestra run) |
| `d99b1e19a418` | 2026-07-19 22:26:34 | ui-live | 5 | aborted/empty: Gemini 429, credits depleted |
| `3a0f1a49b689` | 2026-07-19 22:31:18 | ui-live | 186 | `fusion_20260719_223118` (Darbari symphonic) |
| `001b2e83e034` | 2026-07-20 08:39:50 | ui-live | 162 | `fusion_20260720_083950` (Darbari symphonic) |
| `2ff7403df1e5` | 2026-07-20 08:48:13 | ui-live | 186 | `fusion_20260720_084813` (Charukeshi symphonic) |
| `13a3e29171d3` | 2026-07-20 08:56:23 | ui-live | 75 | Kirwani gothic symphonic; crashed on `meend_swara: ":"`; no render |
| `aa16264e989d` | 2026-07-20 18:34:03 | ui-live | 186 | `fusion_20260720_183403` (Todi thrash, "Slayer style") |
| `b6cd6430c1f6` | 2026-09-14 20:48:15 | live-bageshree | 260 | `fusion_20260914_204815` (Bageshree, first Arranger run) |
| `c5fcc5b3323c` | 2026-09-14 22:29:48 | live-bageshree-teentaal | 221 | `fusion_20260914_222948` (Bageshree teentaal, "convincingly Bageshree") |
| 480f18b59298 | 2026-10-11 19:40:39 | a01-opening-bhairav | 156 | fusion_20261011_194039, the A01 opener (old band: Pandit, Riffsmith, Lead, Riff, Arranger, Rasik, Producer; 21 calls, ~3 min) |
| 97262ddfe346 | 2026-10-11 19:41:46 | ui-live | 184 | fusion_20261011_194146 (90 s Bhairav brief, old band) |
| 8fbcdb773585 | 2026-10-11 19:50:34 | ui-live | 181 | fusion_20261011_195034 (first short-form render; alap crammed) |
| 6c5614a961e8 | 2026-10-11 21:04:08 | pure-c-bageshree | 98 | Bageshree "C" song for the talk's experiment slide; crashed on a LeadPhrase note with `dur: 0.0`, no render |
| bdb8cd72a365 | 2026-10-11 21:11:18 | pure-c-bageshree-2 | 43 | Second Bageshree C attempt; crashed on `swara: "rest"`, no render |
| 58c31e844a7c | 2026-10-11 23:41:14 | ui-live | 5 | Aborted: the Interpreter's call rejected (400, thinking level MINIMAL unsupported on 3.8) |
| 15fbd6571f72 | 2026-10-11 23:42:42 | ui-live | 314 | fusion_20261011_234242, the redesign's first live run (41 calls; silent lead) |
| c61c7d31fa6f | 2026-10-12 00:22:43 | taan-a-b-low-vs-medium-lean-schema | 32 | Taan-only probe, 4 calls alternating low/medium thinking; no render |
| 659feccb16d1 | 2026-10-12 00:25:38 | taan-a-b-low-vs-medium-lean-schema | 8 | One more low-thinking taan call; no render |
| 67d2a86cc01f | 2026-10-12 00:30:32 | ui-live | 98 | fusion_20261012_003032 (Composer path + listening) |
| b0545e590880 | 2026-10-12 07:09:25 | seed-debate-experiment | 347 | out/seed_ab_20261012_070925, round 1 (one seed-judge call timed out) |
| 0553414fc3fa | 2026-10-12 08:16:45 | seed-debate-experiment | 335 | out/seed_ab_20261012_081645, round 2 |
| 83aff247a1cb | 2026-10-12 11:27:14 | ui-live | 154 | fusion_20261012_112714 (doom Darbari, keherwa 64; GPT-reviewed) |
| f4e6ae154cae | 2026-10-12 13:53:07 | ui-live | 56 | Crashed at Rasik: braces in its legend read as a template variable (fixed in a1a0826); no render |
| 04fb97a11a1b | 2026-10-12 13:57:24 | ui-live | 90 | fusion_20261012_135724 (song-form Darbari; led to sitar forward) |
| e8efbdfbfe7d | 2026-10-12 15:20:48 | ui-live | 130 | fusion_20261012_152048 (Darbari prog; the 152048 review) |
| 5cc384efae31 | 2026-10-12 20:50:06 | rhythm-section-darbari | 11 | Aborted: connection reset in the Composer's first call; no render |
| 01bf552e0ce0 | 2026-10-12 21:28:45 | rhythm-section-darbari | 59 | Crashed on a LeadPhrase validation error before the rhythm-section call; no render |
| d1d56a353154 | 2026-10-12 21:34:55 | ui-live | 119 | fusion_20261012_213455 (rhythm-section call hit a 504; the ornament-audit song) |
| fe4020ed4e40 | 2026-10-12 23:34:35 | darbari-takeover-taan | 106 | fusion_20261012_233435 (rhythm-section answer rejected by the guardrail; source of _revised) |
| 6f9b8e3c14ab | 2026-10-13 00:12:03 | darbari-233435-flowing-taan | 16 | Taan-only live call, 2 Composer calls → fusion_20261012_233435_livetaan_20261013_001252 and the flowing excerpt |
| b09cace9fb30 | 2026-10-13 07:36:38 | darbari-full-song-213455-head-20261013 | 27 | Aborted: Composer read timeout; no render |
| ff7d69298643 | 2026-10-13 07:47:03 | darbari-full-song-213455-head-20261013 | 114 | fusion_20261013_074703 |
| 11601e1a8c1d | 2026-10-13 08:17:05 | yaman-full-song | 106 | fusion_20261013_081705_yaman |
| 8805efb8eceb | 2026-10-13 08:17:05 | bageshree-full-song | 151 | fusion_20261013_081705_bageshree (includes the direction-guardrail failure on 'R') |
| 520747d3e2e9 | 2026-10-18 12:42:23 | seed-debate-experiment | 115 | Seed debate round 3, P1 Bhairav → `seed_ab_20261018_124223/p1_*`; aborted at prompt 2 (Interpreter read timeout) |
| 53195ea5f5dc | 2026-10-18 13:03:55 | seed-debate-experiment | 199 | Seed debate round 3, P2 Darbari → `seed_ab_20261018_124223/p2_seed_sketches_not_the_gat_test/` (inferred from timing) |
| 17e1f12c3251 | 2026-10-18 13:16:44 | single-prompt-c-yaman | 98 | Single-prompt arm C → `fusion_20261018_131644_yaman` |
| f0f79ac55fde | 2026-10-18 13:26:46 | single-prompt-c-darbari | 78 | Single-prompt arm C → `fusion_20261018_132646_darbari` ("song C") |
| e3f7212a9204 | 2026-10-18 14:22:10 | single-prompt-c-bhairav | 94 | Single-prompt arm C → `fusion_20261018_142210_bhairav` |
| 58f3ac9c73d6 | 2026-10-18 15:11:24 | hear-ab-a-darbari-mukhada | 8 | ReAct A/B #1, arm A (no tool) → `hear_ab_20261018_151123/mukhada_A` |
| 8ceb769ebf63 | 2026-10-18 15:11:24 | hear-ab-b-darbari-mukhada | 12 | ReAct A/B #1, arm B (hear_phrase, 3 calls) → `mukhada_B` |
| 043492920b13 | 2026-10-18 15:23:53 | hear-ab-a-darbari-mukhada | 8 | ReAct A/B fresh, arm A → `hear_ab_20261018_152351_fresh/mukhada_A` (Sujit's pick) |
| 56c3138779a9 | 2026-10-18 15:23:53 | hear-ab-b-darbari-mukhada | 12 | ReAct A/B fresh, arm B → `mukhada_B` |
| 653e65a6e96c | 2026-10-18 16:47:04 | high-effort-darbari | 5 | Aborted: 402 credits depleted at the Interpreter |
| 57af304fd1ad | 2026-10-18 16:51:29 | high-effort-darbari | 102 | High-effort run → `fusion_20261018_165129_darbari_high` + `blind_producer_20261018_165129` |
| 22b0b82f86d0 | 2026-10-18 17:41:35 | seed-debate-experiment | 151 | Cross-model seed debate; died after 51 min on an OpenAI timeout → empty `seed_ab_20261018_174135` |
| c6e4ea9e50a4 | 2026-10-18 21:17:45 | seed-debate-experiment | 109 | Replay dry run with dummy keys (401, 0 model calls) |
| 074dfa250b82 | 2026-10-18 21:17:59 | seed-debate-experiment | 127 | Cross resume #1; died on a Sol hang then Gemini 503 (`seed_cross_resume_20261018.log`) |
| 6ca08d21aad9 | 2026-10-18 21:50:58 | seed-debate-experiment | 112 | Replay attempt; aborted "replay out of step at call 23" |
| 2d87ffeb8e70 | 2026-10-18 21:52:11 | seed-debate-experiment | 112 | Replay attempt; aborted, out of step |
| 00993fd38c46 | 2026-10-18 21:53:01 | seed-debate-experiment | 112 | Replay attempt; aborted, out of step |
| 6495f963e1a8 | 2026-10-18 21:53:50 | seed-debate-experiment | 112 | Replay attempt; aborted, out of step |
| 1204753d827b | 2026-10-18 21:55:17 | seed-debate-experiment | 112 | Replay attempt; aborted, out of step |
| b87ab2cec402 | 2026-10-18 21:56:03 | seed-debate-experiment | 134 | Replay dry run (invalid Gemini key, 0 model calls) |
| 0bcbb0f57d97 | 2026-10-18 21:57:55 | seed-debate-experiment | 124 | Replay dry run (invalid OpenAI key, 0 model calls) |
| 45c1d05b013a | 2026-10-18 21:59:20 | seed-debate-experiment | 231 | Cross resume #2, completed → `seed_ab_20261018_215920` |
| 000b61d8a7ab | 2026-10-18 23:01:19 | motif-experiment | 112 | Motif guided-vs-free → `motif_ab_20261018_230119` |
| f32e2a7b5d5f | 2026-10-18 23:15:51 | eval-ad-hoc-query | 6 | One Interpreter eval call (dark Darbari doom in D); purpose undocumented |
| 29f5e64199d0 | 2026-10-18 23:40:58 | head-debate | 10 | Aborted: invalid API key, 0 model calls |
| 924cad7451fd | 2026-10-18 23:41:35 | head-debate | 96 | Head debate → `head_debate_20261018_234135` |
| c0e7320909c6 | 2026-10-19 00:05:58 | head-control-solo-revision | 37 | Head-debate control → `head_control_20261019_000558` |
| e6ac29f35d4d | 2026-10-19 08:32:59 | fresh-run | 90 | → `fusion_20261019_083259_fresh` (first Producer accept); later replayed for notes debate #1 |
| 8ced2b321c55 | 2026-10-19 09:12:59 | alap-call-and-answer | 16 | → `alap_ab_20261019_091259` |
| 6c7fcad7558c | 2026-10-19 09:23:12 | alap-call-and-answer | 8 | → `alap_ab_20261019_092312` |
| 8975dcdabcef | 2026-10-19 09:49:43 | notes-debate | 58 | Notes debate #1 (Darbari) → `notes_debate_20261019_094935` |
| fb08fb641163 | 2026-10-19 10:07:27 | fresh-run | 98 | → `fusion_20261019_100727_bhairav` (workflow Composer) |
| 4b6e80296582 | 2026-10-19 10:12:45 | notes-debate | 53 | Notes debate #2 (Bhairav) → `notes_debate_20261019_101238` |
| 25f862b73ad8 | 2026-10-19 16:41:27 | fresh-run | 176 | → `fusion_20261019_164127_agentic_bhairav` (agentic Composer + in-pipeline notes debate) |
| 78ed74760e8a | 2026-10-19 18:46:32 | fresh-run | 192 | → `fusion_20261019_184632_pipeline_darbari` (deck's "One real run"; the guitarist's debate call failed its guardrail) |
| a8b711f667eb | 2026-10-19 19:50:00 | alap-then-jod | 16 | → `alap_jod_20261019_195000` |
| fce06eb8e70b | 2026-10-20 14:42:18 | fresh-run | 128 | → `fusion_20261020_144218_darbari_symph` |
| d3f20960b49c | 2026-10-20 23:09:36 | regat-run | 60 | → `fusion_20261020_230936_regat213455` |
| (e2642043aa73) | file dated 2026-10-21 18:43 | — | 0 | Empty 0-byte trace file (unreadable, no started_at); by inference an aborted start just before the promo batch |
| fbf97aab1906 | 2026-10-21 18:48:31 | devday-promo-bhairavi | 94 | → `fusion_20261021_184831` |
| 2be3b52cc6be | 2026-10-21 18:48:34 | devday-promo-bhairav | 78 | → `fusion_20261021_184834` |
| 786a65281a24 | 2026-10-21 18:58:52 | devday-promo-charukeshi-symphonic | 90 | → `fusion_20261021_185852` |
| e02131f4e486 | 2026-10-21 18:58:52 | devday-promo-kirwani-symphonic | 78 | Failed: read timeout, no output |
| e576f3567c2c | 2026-10-21 19:07:48 | devday-promo-kirwani-symphonic | 78 | Failed: 402 credits depleted, no output |
| 60e6d49dd518 | 2026-10-21 19:10:11 | devday-promo-darbari-doom-symphonic | 55 | Failed: 402 credits depleted, no output |
| `e2642043aa73` | 2026-10-21 18:43 (file mtime) | — | 0 | Empty file: the run died before the tracer wrote anything. Its time falls among the DevDay promo runs. |
