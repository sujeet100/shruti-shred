# talk/audio — the talk's audio clips and the data behind them

This folder holds every short audio clip the talk deck plays, together with the scripts that made them and, under `build/`, the exact composition each clip was rendered from. A clip ID such as `FA` names a family of files: `FA.wav` is the loudness-matched audio, `FA.mp4` the waveform-and-playhead video the deck embeds, `FA.png` its first-frame still, and `build/FA_src.{json,mid,wav}` the composition, its MIDI and the raw render. The `.wav`/`.mp4`/`.png` media are kept out of git, so treat `build/` and the scripts as the record and regenerate the media from them. Almost everything here is free to rebuild, because the scripts render through the repo's deterministic core (FluidSynth plus the soundfonts that `setup.sh` fetches) and every model reply they depend on is cached in `build/`: re-running a script re-renders from the cached reply instead of calling the model again. The main entry points, all run from the repo root with `uv run python talk/audio/<script>`, are `make_clips.py` (A02–A10, N1–N3), `raga_clip.py` (N4, then K4), `keyboard_video.py` (K1–K4, after the N audio exists), `pure_songs.py` (the bare-prompt songs), `ladder.py` (LA/LB/LC), `band_ladder.py` (SA/SB/SC), `oneshot.py` (A06a), `revoice.py` (RV_*), `knows_clip.py` (KN) and `restyle_clips.py` (BG, plus a light-theme redraw of FA/FB/FC/A04). Several clips cut from full-song renders in `out/`, so those need the named `out/fusion_*` render re-rendered to WAV first (its JSON and MIDI are committed; see `out/README.md`); TR and MK were cut by hand and have no script, and S10 comes from the separate studio project in `talk/studio/`.

`assets.json` maps 31 clip IDs to the artifact blob ids (`video`, `still`) that the Claude Slides deck references once a clip is uploaded. "Current deck" below means `talk/deck/story.py`, the live deck since 2026-10-18 (slide ids are its `section(...)` names); "retired deck" means `talk/deck/build.py`, the earlier pixel-style deck it replaced.

### The music primer: twelve notes, then one raga

The talk teaches just enough music to follow the rest, and these clips draw a keyboard inside the video itself so the keys light in sync with the sound (the deck can only start a clip with its slide, so a separately animated keyboard would drift). The N clips are the audio, rendered at Sa = C so the sound matches the drawn keys; the K clips are the videos that play them.

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| N1 | `N1_src.{json,mid,wav}` | The seven shuddha (natural) notes, Sa up to upper Sa and back down, over a soft drone. Audio for K1. | `make_clips.py N` | via K1 |
| N2 | `N2_src.*` | Each natural note followed by its komal (flat) version: Re/re, Ga/ga, Dha/dha, Ni/ni. Audio for K2. | `make_clips.py N` | via K2 |
| N3 | `N3_src.*` | Shuddha Ma then tivra (sharp) Ma resolving to Pa, then the two achal (fixed) notes Sa and Pa and upper Sa. Audio for K3. | `make_clips.py N` | via K3 |
| N4 | `N4_src.*` | Raga Bhairav from the encoded data in `src/raga.py`: its aroha (way up), avaroha (way down) and two chalan phrases with the slow andolan sway on komal re and dha. Audio for K4. | `raga_clip.py` | via K4 |
| K1 | `keyboard_sahaj/K1.txt` + frames (light theme); `keyboard/K1.txt` (older dark theme) | N1 with the keyboard drawn in: each natural key appears as its note sounds. | `keyboard_video.py` | current `notes1`; retired deck notes slides |
| K2 | `keyboard_sahaj/K2.txt`, `keyboard/K2.txt` | N2 drawn: each natural key lights, then its flat key appears beside it. | `keyboard_video.py` | current `notes2` |
| K3 | `keyboard_sahaj/K3.txt`, `keyboard/K3.txt` | N3 drawn: tivra Ma appears and resolves to Pa; Sa and Pa are ringed as achal. | `keyboard_video.py` | current `notes3` |
| K4 | `keyboard_sahaj/K4.txt` + frames | N4 drawn: Bhairav's seven of twelve keys lit (the other five faded as illegal), with a phase label for aroha / avaroha / chalan. | `raga_clip.py` → `keyboard_video.py` | current `raga` ("A raga is a rulebook for a melody") |

The `K*.txt` files are ffmpeg concat lists (frame PNG + duration); `frame.html` is the page screenshotted to make each frame from the deck's own `keyboard()` drawing.

### How Hindustani music is built (retired deck's primer)

Before the 2026-10-18 rewrite, the primer used deterministic Bhairav clips at Sa = E and 128 BPM to show the three kinds of time a raga-metal band must coordinate and what separates a raga from a scale. They are all hand-specified from the raga and tala data in `make_clips.py`; no model is involved.

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| A02 | `A02_full.{json,mid,wav}` | A stem build: drone alone for ~4 s, the sitar enters with Bhairav's two pakad (signature) phrases, then the tabla's teentaal theka lands on the sam (~8 s). | `make_clips.py A02` | retired `hindustani` |
| A03 | `A03_a.*`, `A03_b.*` | A plain aroha scale run in even quarter notes, then the two pakad phrases with varied durations and andolan on r/d, landing on Sa: a scale versus the raga's own movement. | `make_clips.py A03` | retired `bhairav` |
| A04 | `A04_a.*`, `A04_b.*` | One held komal Re, first plain and then with the renderer's andolan; otherwise identical. | `make_clips.py A04` (light-theme redraw: `restyle_clips.py`) | retired `raga`; kept for the Sahaj deck per `restyle_clips.py` but not on any current slide |
| A05 | `A05_full.*` | Exactly one teentaal cycle (16 matras, 7.5 s at 128 BPM) of the theka over a soft drone, sam accented. | `make_clips.py A05` | retired `tala` |

### The first experiment, at melody level (later dropped)

The experiment slide began as a ladder of melodies: what one prompt writes, what the raga's grammar adds, what the system writes. `talk/HANDOVER.md` records why this version was dropped: by October the model wrote legal, fluent Bhairav melodies unaided, so the three rungs sounded alike. A06b and A06c are hand-written illustrations rather than model output, which is worth knowing given the later finding (TALK.md "We skipped the baseline") that early "naive" examples were never measured.

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| A06a | `A06a_src.*`, `A06a_llm.txt` (the cached reply) | "Prompt only": one call asking for a short Bhairav sitar melody as a JSON note list, rendered at Sa = E over the drone. The reply's 16 notes are all legal in Bhairav. Called through the project's `generator_llm` (CrewAI wrapper). | `oneshot.py` | uploaded (`assets.json`); no placement found in either deck source |
| A06b | `A06b_src.*` | Hand-written "legal but aimless" line: 16 Bhairav-legal notes, all 0.75 beats, leaps with no phrase, no andolan, ending on Ni. | `make_clips.py A06` | uploaded; no placement found |
| A06c | `A06c_src.*` | Hand-written shaped line: pakad 1 plus a descending chalan, varied rhythm, andolan on d/r, rests, Sa landing on the sam. | `make_clips.py A06` | uploaded; no placement found |
| A06bc | (A06b + A06c) | A06b, one second of silence, then A06c in one file, level-matched, because the deck plays one clip per slide. | `make_clips.py A06` | uploaded; no placement found |
| LA | `LA_src.*`, `ladderA_prompt.txt`, `ladderA_llm.txt`, `ladder_windows.json` | Model output for "a lead melody for a metal song in raga Bhairav ... about 30 seconds", rendered raw (no added ornament) over the drone; a 16-beat window from the middle. | `ladder.py` | uploaded; superseded by SA–SC then FA–FC |
| LB | `LB_src.*`, `ladderB_prompt.txt`, `ladderB_llm.txt` | The same prompt plus Bhairav's grammar generated from `src/raga.py`, same treatment. | `ladder.py` | uploaded; superseded |
| LC | `LC_src.*` | The system's sitar line and drone from the opening song (`out/fusion_20261011_194039`), its first gat cycle (beats 16–32). | `ladder.py C out/fusion_20261011_194039.json 16` | uploaded; superseded |

`ladder_windows.json` records which beat window each L clip shows (read by the deck to draw a matching piano roll). `LC_dry_src.*` / `LC_dry_part0.wav` are not named by any script; they look like an earlier variant of LC and are unexplained.

### The first experiment, at song level: one prompt vs grammar vs the system (2026-10-11)

Moving the ladder up to whole songs is what made the comparison audible. A asks for a one-minute heavy metal song in a raga with sitar, guitar, bass and drums; B adds the raga's grammar; C is the full agentic system. A and B went straight to Gemini through Google's SDK with the prompt as the only content (no system prompt, default settings), and are rendered exactly as written. HANDOVER.md records Sujit's verdict on the Bhairav set: A sounded best and its riffs beat B and C, though its guitar played E-minor metal with 92 notes Bhairav forbids, which became the talk's "best metal, worst Bhairav" turn.

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| SA | `SA_src.*`, `bandA_prompt.txt`, `bandA_llm.txt` | A ~30-second Bhairav band song from one prompt (via `generator_llm`); the last 24 beats, where endings show coordination. | `band_ladder.py` | uploaded; superseded by FA |
| SB | `SB_src.*`, `bandB_prompt.txt`, `bandB_llm.txt` | The same plus Bhairav's grammar; last 24 beats. | `band_ladder.py` | uploaded; superseded by FB |
| SC | (cut from `out/fusion_20261011_194039.wav`) | The last 24 beats of the opening song: the taan landing, then the band to the hard stop. | `band_ladder.py` | uploaded; superseded by FC |
| FA | `FA_src.*`, `pureA_request.json`, `pureA_reply.txt`, `pureA_usage.json` | Bhairav, one bare call (gemini-3.5-flash), whole one-minute song. 92 forbidden notes (all guitar), all four parts playing every bar. | `pure_songs.py` (with `RMA_PURE_MODEL=gemini-3.5-flash`) | retired `naive` ("92 wrong notes · no motif"); its climax is half of TR; source for `grind_ab.py` / `harmony_ab.py` |
| FB | `FB_src.*`, `pureB_*` | The same prompt plus Bhairav's grammar: every note legal, phrases repeat in four-bar blocks, still every part every bar ("never breathes"). | `pure_songs.py` | retired `naive` ("in the raga · never breathes") |
| FC | (cut from `out/fusion_20261011_194039.wav`) | The opening song, made by the system (trace 480f18b59298, log `A01_run.log`; accepted in round 0): sitar alone, band enters, sitar drops for the breakdown, hook returns varied, taan. | `pure_songs.py` (C) | retired `naive` ("hook returns · has a shape") |
| GA | `GA_src.*`, `pure_bageshree_A_*` | Bageshree, one bare call (3.5): legal, power chords on Pa. Its opening is the raga's pakad almost word for word. | `pure_songs.py bageshree` | first half of KN |
| GB | `GB_src.*`, `pure_bageshree_B_*` | Bageshree with grammar: legal, never rests. | `pure_songs.py bageshree` | none found |
| GF | `GF_src.*`, `pure_bageshree_F_*` | Bageshree A plus one sentence naming the song form ("an intro, alap, gat (mukhada + manjha), antara and taans"). HANDOVER: only a density ramp, drums from bar 1, the mukhada never returns, 32 forbidden notes (shuddha Ga): "naming a section isn't knowing what it does". | `pure_songs.py bageshree ... F` | none found |

There is no GC: both full Bageshree system runs crashed on a LeadNote validation error (`C_bageshree_run.log`: a note with `dur: 0.0`; `C_bageshree_run2.log`: a note with `swara: "rest"`), as HANDOVER.md §4 describes.

### The same experiment re-run on gemini-3.8-flash, three ragas (2026-10-18)

Because the models had moved on, the experiment was repeated on the model the agents now run on, across Yaman, Darbari and Bhairav, with C songs freshly composed by the five-agent system (`system_song.py`; those renders live in `out/`). `single_prompt_results.md` holds the measured tables and the confounds; the current deck's `ladder` slide summarises it as "Correct, then the raga's words, then music", with the clips themselves not embedded.

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| YA | `YA_src.*`, `pure_yaman_A_38_*` | Yaman, bare call on 3.8: 0 illegal notes, all parts every bar, the hook never returns. | `pure_songs.py yaman A` | figures on current `ladder` |
| YB | `YB_src.*`, `pure_yaman_B_38_*` | Yaman with grammar: both pakad phrases exact, still no returning hook. | `pure_songs.py yaman B` | figures on `ladder` |
| DA | `DA_src.*`, `pure_darbari_A_38_*` | Darbari, bare call: 4 illegal guitar notes, parts end 31 beats apart. | `pure_songs.py darbari A` | figures on `ladder` |
| DB | `DB_src.*`, `pure_darbari_B_38_*` | Darbari with grammar: legal, both pakad exact, every part almost every bar. | `pure_songs.py darbari B` | figures on `ladder` |
| HA | `HA_src.*`, `pureA_38_*` | Bhairav bare call on 3.8 (the FA prompt): now 0 forbidden notes (FA had 92 on 3.5). | `pure_songs.py A` | figures on `ladder` |
| HB | `HB_src.*`, `pureB_38_*` | Bhairav with grammar on 3.8. | `pure_songs.py B` | figures on `ladder` |
| HA3L | `HA3L_src.*`, `pureA_3_low_*` | The Bhairav A prompt on `gemini-3-flash-preview` at `thinking_level: low` (4,155 tokens). Measured from the data: 0 illegal notes, but only 36 beats long though one minute (~128 beats) was asked. | `pure_songs.py A` with `RMA_PURE_MODEL=gemini-3-flash-preview RMA_PURE_THINKING=low` | none found; **purpose unexplained** |
| FAL | `FAL_src.*`, `pureA_low_*` | The Bhairav A prompt requested on gemini-3.5-flash at `thinking_level: low` (answered by gemini-3.6-flash). From the data: 0 illegal notes (FA had 92), a full 130 beats. | `pure_songs.py A` with `RMA_PURE_MODEL=gemini-3.5-flash RMA_PURE_THINKING=low` | none found; **purpose unexplained** |

A caution for regenerating: the Yaman bare call was also made on 3.5 on 2026-10-11 (`pure_yaman_A_*` without `_38`), and its clip was later overwritten when the 3.8 run wrote `YA`; running `pure_songs.py yaman` with `RMA_PURE_MODEL=gemini-3.5-flash` would overwrite the current YA again.

### What the plain prompt knew, and what it couldn't do

These clips back the claim that the model already knows the raga's vocabulary but not what to do with it. MA and TA come from bare 3.5 calls made on 2026-10-11 for the grind and harmony comparisons (`pure_songs.py`'s prefix table notes them as "the grind-treatment A/B").

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| MA | `MA_src.*`, `pure_malkauns_A_*` | Malkauns, one bare call: 0 illegal notes, but the same five notes run evenly up and down and rest on dha. | `pure_songs.py malkauns A` | second half of KN |
| TA | `TA_src.*`, `pure_todi_A_*` | Todi, one bare call: the out-of-raga notes are all guitar power-chord fifths (94 by `pure_songs.measure`); the deck notes say its power chords add notes Todi does not have. | `pure_songs.py todi A` | source for `harmony_ab.py`; no slide |
| KN | (cut from `GA.wav` and `MA.wav`) | Bageshree's bare opening (its pakad, resting on Ma, nearly word for word), a 0.8 s gap, then Malkauns' even pentatonic run resting on dha, which stops sounding like Malkauns. | `knows_clip.py` | was on `knew` ("It knew the raga. It didn't know what to do with it.", deck V113); the current `knew` slide no longer embeds it |

### The riff: one plain prompt beat ours, and what the riff work found

The riff is where the talk admits doubt. One bare prompt's Bhairav riff (FA) beat the system's in Sujit's ear, which prompted the voicing experiment, the riff checker examples and, later, the blind test of who should write the guitar.

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| TR | `TR_part0.wav` (ours), `TR_part1.wav` (plain prompt); stroke data in `talk/deck/data/turn_strokes.json` | About 4.5 s of the opening song's climax, then the same moment of FA, loudness-matched. The stroke lanes beside it show the plain prompt building into a wall of guitar strokes at the climax (636 strokes vs ours 157 over the song) while ours thins. | cut by hand (no script) | current annex `turn-evidence` ("ours, then the plain prompt") |
| RV_orig_full | `RV_orig.{json,mid,wav}` | The opening song as the system wrote it, re-rendered with the raga validator on. Its riff is 15% chords. | `revoice.py` | none (listening reference) |
| RV_revoiced_full | `RV_revoiced.*` | The same song with only the rhythm guitar's voicing changed: every stroke gets a power-chord fifth where the raga allows it, a fourth where it doesn't, else the octave. Chord share 15% → 100%, all legal. | `revoice.py` | none (listening reference) |
| RV_ab | (cut from RV_orig / RV_revoiced) | The hook's full-band return (beats 64–96), original then re-voiced. Evidence for the voicing pass later built into `crew/riff_voicing.py`. | `revoice.py` | none found |
| A10 | `A10_a.*`, `A10_b.*` | Hand-written: a melody-riff that changes pitch on every eighth note, then a grounded chug riff on low Sa with palm mutes, power-chord accents and two silences, over identical bass and drums. | `make_clips.py A10` | retired `verifier` ("melody-riff, then chug-riff") |
| A09 | (cut from `out/fusion_20260720_183403.wav` and `out/gatefix_183403.wav`) | The same 4 s riff-only window before and after the palm-mute gate fix (a fixed 80 ms gate had clipped every chug). | `make_clips.py A09` | retired war story `layers` ("The riffs sound happy") |
| MK | `MK_part0.wav` (seed), `MK_part1.wav` (Rhythm section) | Song 04 of the blind mukhada test (`fusion_20261018_142210_bhairav`): the first mukhada with Pandit's seed riff, written before the sitar existed, then with the Rhythm section's guitar written against the finished sitar. Blind, the Rhythm section won 3–2 overall; this song's seed riff "clashes". | cut by hand from the `mukhada_ab.py` pair | current `own-test` ("Pandit's riff, then Rhythm's") |

### The critic loved it; the audio was wrong

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| BG | (cut from `out/fusion_20261013_081705_bageshree_alap_{C_original,B_corrected}_mix.wav`) | The Bageshree alap's komal Ga: first as originally rendered, where the andolan swung up to shuddha Ga and turned on the wrong note, then the corrected sway that stays inside the swara. Rasik had praised the same run's andolans from the notes. | `restyle_clips.py` | current `l4` ("The critic loved it. The audio was wrong.") |

### How a song gets made

| Clip | Source data (build/) | What it plays, and what it shows | Made by | Used on slide |
|---|---|---|---|---|
| S10 | none here (video only; built in `talk/studio/`) | A ~68 s three.js voxel studio scene: the sitarist offers a real Darbari head, guitar, bass and drums join one by one, the producer stops the take to fix the riff under the sitar's Ga (the system's own articulation fix), and the band plays it again; Gemini TTS voices. | `talk/studio/` (`session_music.py`, `capture.mjs`, `mix.py`) | current `process` ("Songs are built in layers") |

The retired deck also referenced A01 (the live opening performance's backing track, i.e. the opening song), A07, A08, A11 and A12; none of those has media in this folder.

## The bare single-prompt calls (`build/pure*`)

Each `pure*` triple is one call to Gemini made by `pure_songs.py` through Google's SDK directly: `_request.json` is everything sent (model, the prompt as the only content, and `config`, which is `null` except for the two low-thinking runs), `_reply.txt` the raw reply, and `_usage.json` the token counts plus, where recorded, `model_version`, the model that actually answered. The prompt variants are A, "a one-minute heavy metal song in raga X" for sitar, distorted rhythm guitar, bass and drums at 128 BPM in E, as JSON; B, the same plus the raga's grammar from `src/raga.py` (`ladder.grammar`); and F, A plus one sentence naming the Hindustani song form. Requests for `gemini-3.5-flash` were answered by `gemini-3.6-flash` wherever the version was recorded, the silent substitution CLAUDE.md describes.

| Request files | Raga · variant | Model requested → answered | Clip | Outcome (source) |
|---|---|---|---|---|
| `pureA_*` | Bhairav · A | 3.5 → not recorded | FA | 92 forbidden guitar notes; best riff by Sujit's ear; every part every bar (HANDOVER.md) |
| `pureB_*` | Bhairav · B | 3.5 → not recorded | FB | Legal, phrases in four-bar blocks, never breathes (HANDOVER.md) |
| `pure_bageshree_A_*` | Bageshree · A | 3.5 → not recorded | GA | 0 forbidden; opens on the pakad (HANDOVER.md, deck notes) |
| `pure_bageshree_B_*` | Bageshree · B | 3.5 → not recorded | GB | Legal, never rests (HANDOVER.md) |
| `pure_bageshree_F_*` | Bageshree · F | 3.5 → not recorded | GF | 32 forbidden notes, no real alap, mukhada never returns (HANDOVER.md) |
| `pure_malkauns_A_*` | Malkauns · A | 3.5 → 3.6 | MA | Legal; even pentatonic runs resting on dha (knows_clip.py, deck notes) |
| `pure_todi_A_*` | Todi · A | 3.5 → 3.6 | TA | Power-chord fifths outside the raga (harmony_ab.py) |
| `pure_yaman_A_*` | Yaman · A | 3.5 → 3.6 | none (YA overwritten by the 3.8 run) | not documented |
| `pureA_low_*` | Bhairav · A, thinking low | 3.5 → 3.6 | FAL | not documented; data shows 0 forbidden notes |
| `pureA_3_low_*` | Bhairav · A, thinking low | gemini-3-flash-preview | HA3L | not documented; data shows a 36-beat song |
| `pure_yaman_A_38_*`, `pure_yaman_B_38_*` | Yaman · A, B | 3.8 → 3.8 | YA, YB | single_prompt_results.md: A 0 illegal, hook 0, Rasik 4·3·3; B both pakad exact, Rasik 5·3·3; system C hook returns 3 times, Rasik 4·3·4 |
| `pure_darbari_A_38_*`, `pure_darbari_B_38_*` | Darbari · A, B | 3.8 → 3.8 | DA, DB | A 4 illegal guitar notes, parts end 31 beats apart, Rasik 3·2·2; B legal, Rasik 4·2·2; C Rasik 4·4·4 |
| `pureA_38_*`, `pureB_38_*` | Bhairav · A, B | 3.8 → 3.8 | HA, HB | A 0 forbidden (was 92 on 3.5), Rasik 3·2·2; B both pakad exact, Rasik 5·3·3; C Rasik 5·4·4 |

The 3.8 results support the current deck's `ladder` slide: the bare call is now correct, the grammar makes it quote the raga's phrases, and only the system brings the hook back. `single_prompt_results.md` lists the confounds worth reading first: the bare prompt asked every part to play the whole length, its format has no field for ornaments or palm mutes, and it has no tala or sections.

The other cached prompts in `build/` are not bare SDK calls: `ladder{A,B}_*` (LA/LB), `band{A,B}_*` (SA/SB) and `A06a_llm.txt` went through the project's own `crew.config.generator_llm` wrapper.

## `producer_analysis_20261018.json`

This is a per-trace extraction of the Producer critic's behaviour across every traced run from 2026-07-11 to 2026-10-18: 43 records (24 from the single-critic era, 14 from the accept-or-revise "plan" era, 5 from the debate era), 39 of which carry Producer verdicts. Each record lists its rounds with the nine rubric scores, their mean and change after an edit, the revision plan and its instruction class, whether it adopted a Rasik suggestion, Rasik's own scores, and counts of numbers and metric citations in the Producer's reasoning. TALK.md ("The Producer, measured across every run") draws the conclusions: it revised the first draft 14 of 14 times, copied a Rasik suggestion in 30 of 36 plans, its scores rose after an edit about as often as they fell, and 6 of 14 runs shipped a version below one of its own earlier rounds. That evidence drove the 2026-10-18 rework (a kept champion take, a two-order blind comparison, one judge round). The script that produced this file is not in the repo.
