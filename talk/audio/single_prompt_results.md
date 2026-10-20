# Single-prompt experiment — results (2026-10-18, gemini-3.8-flash)

A = one bare call ("a one-minute heavy metal song in raga X", Sa = E, 128 BPM, four parts, JSON in
the prompt, no schema, no system prompt). B = A + the raga's grammar (`ladder.grammar`). C = the full
system (five-agent default: Interpreter, Composer, Rhythm section, Rasik, Producer).
All rendered through the same instruments. Measured by `compare_songs.py` and `idiom.py`; mood by Rasik.

| Song | Audio |
|---|---|
| Yaman A / B / C | `talk/audio/YA.wav`, `YB.wav`, `out/fusion_20261018_131644_yaman.wav` |
| Darbari A / B / C | `talk/audio/DA.wav`, `DB.wav`, `out/fusion_20261018_132646_darbari.wav` |
| Bhairav A / B / C | `talk/audio/HA.wav`, `HB.wav`, `out/fusion_20261018_142210_bhairav.wav` |

## The whole song

| | All parts playing | Sitar silent | Power-chord strokes | Palm-muted | Hook returns | Parts end together (beats apart) | Illegal notes |
|---|---|---|---|---|---|---|---|
| Yaman A | 100% of bars | 3% | 21% | 0 (format can't) | 0 | 0.9 | 0 |
| Yaman B | 100% | 5% | 33% | 0 | 0 | 1.9 | 0 |
| Yaman C | 75% | 25% | 81% | 40% | 3 | 0 | 0 |
| Darbari A | 72% | 24% | 27% | 0 | 2 | **31** | **4 (guitar)** |
| Darbari B | 100% | 1% | 33% | 0 | 1 | 2.0 | 0 |
| Darbari C | 75% | 25% | 81% | 35% | 3 | 0 | 0 |
| Bhairav A | 100% | 1% | 33% | 0 | 1 | 0.9 | 0 |
| Bhairav B | 100% | 2% | 32% | 0 | 0 | 2.0 | 0 |
| Bhairav C | **100%** | **0%** | 100% | 44% | 3 | 0 | 0 |

## The raga (sitar line)

| | Pakad (2 phrases) | In raga movements | Longest straight run | Turns | Andolit notes held / swayed | Rasik pakad · idiom · mood |
|---|---|---|---|---|---|---|
| Yaman A | 1 exact, 1 loose | 65% | 13 | 26% | (no andolan) | 4 · 3 · 3 |
| Yaman B | 2 exact | 85% | 10 | 26% | – | 5 · 3 · 3 |
| Yaman C | 1 exact, 1 loose | 84% | 7 | 34% | – | 4 · 3 · 4 |
| Darbari A | 1 of 2 | 63% | 9 | 38% | 5 of 28 / 0 | 3 · 2 · 2 |
| Darbari B | 2 exact | 83% | 8 | 53% | 11 of 39 / 0 | 4 · 2 · 2 |
| Darbari C | 1 of 2 | 87% | 5 | 55% | **0 of 47 / 0** | 4 · 4 · 4 |
| Bhairav A | 0 exact, 1 loose | 17% | 10 | 35% | 6 of 77 / 0 | 3 · 2 · 2 |
| Bhairav B | 2 exact | 50% | 7 | 54% | 31 of 65 / 0 | 5 · 3 · 3 |
| Bhairav C | 2 exact | 52% | 7 | 40% | 23 of 82 / **18** | 5 · 4 · 4 |

## Confounds (read before trusting a column)

* The bare prompt says "with every part playing for the whole length" (meant: the parts' beats add
  up to the same length). It may push A and B toward never breathing.
* The bare format has no ornament or articulation field: A and B cannot write an andolan or a palm
  mute. C's andolan and chugs are partly the format.
* No tala and no sections in the bare format; C chooses a form.
* Bhairav's 2026-10-11 songs (FA, FB, on the deck) ran on 3.5; on 3.8 the bare guitar no longer
  plays forbidden notes (0, was 92).
