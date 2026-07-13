# Soundfonts

The renderer needs `GeneralUser-GS.sf2` here (GeneralUser GS 2.0.3 — a GM/GS soundfont;
Distortion Guitar = GM program 30, Sitar = program 104 0-indexed / GM #105).
It's a ~31MB binary, kept out of git.

**Just run `./setup.sh` from the repo root** — it installs FluidSynth and downloads
this soundfont (idempotently, pinned to a commit for a reproducible build). To fetch only
the soundfont by hand:

```
SHA=684543d5e5efaef08d02be50dcda8d552478fa60
curl -L -o soundfonts/GeneralUser-GS.sf2 \
  https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$SHA/GeneralUser-GS.sf2
```

Source: [GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS) by S. Christian
Collins (maintained fork by mrbumpy409). **License v2.0** — unrestricted use for private or
commercial music, and redistribution is permitted (the bank embeds this license). FluidSynth
itself is a **system** binary — install via `brew install fluidsynth`, not pip.

> Replaced `MuseScore_General.sf3` (MIT) on 2026-07-13 — GeneralUser GS is an all-round
> upgrade for guitars, bass, and drums and has a proper GM sitar. Our exact GM program
> numbers map transparently (Overdrive 29, Distortion 30, Finger Bass 33, Strings 48,
> Sitar 104), so it's a drop-in with no code change beyond the filename.

## Stacked (split) soundfonts

The renderer can **stack** specialized banks over the GM base (FluidSynth `-b` bank-offset +
a MIDI Bank Select per channel) so a voice pulls from a dedicated soundfont while everything
else stays on GeneralUser GS. Routing lives in `src/soundfont.py`; a missing extra file
degrades cleanly to the base. Current + planned extras:

- **`Dethmetal.sf2`** — a dedicated distorted electric guitar. `setup.sh` fetches it (skip
  with `RMA_SKIP_DETHMETAL=1`). The rhythm/lead guitars route to its single-note "Distorted"
  patch (internal bank 126, program 0). Source: zanderjaz.com. **License UNVERIFIED** — the
  source disclaims usage rights, so this is for the demo, not commercial redistribution.
- **`Indian-Ensemble.sf2`** — the classical side: a multi-sampled **sitar** and a real **tabla**
  (wired via a bank offset of 50; its presets sit at internal bank 0). This soundfont is pitched
  an **octave low**, so the sitar (preset 2) is transposed **up one octave** to sit in the band's
  register. The tabla routes to real strokes (preset 0, keys 53–96, on its own melodic channel
  instead of GM congas) **tuned to the piece's Sa** via MIDI RPN coarse-tuning (the dayan is a
  tuned drum; the strokes are fixed near C). The **drone stays on the GM string pad** — it sounds
  better than this soundfont's tamboura. Source: E-mu "Indian Ensemble" via
  [polyphone](https://www.polyphone.io/en/soundfonts/instrument-sets/358-indian-ensemble),
  **attribution license**.

  **Cannot be auto-downloaded** — polyphone gates it behind a free sign-in, so `setup.sh`
  can't fetch it. Get it once, by hand:
  1. sign in and download the `.sf2` (~4 MB) from the link above;
  2. save it as `soundfonts/Indian-Ensemble.sf2`.

  Without the file the render degrades cleanly (string-pad drone, GM-conga tabla, GM sitar).
