#!/usr/bin/env bash
# One-time setup for the render pipeline's SYSTEM dependencies.
#
# Python deps are handled by uv (`uv run ...`). But two things are NOT Python
# packages and can't come from uv: FluidSynth (a system binary) and the
# GeneralUser GS soundfont (a ~31MB asset with no reliable PyPI package).
# This script installs both. It is idempotent — safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SF="$ROOT/soundfonts/GeneralUser-GS.sf2"
# GeneralUser GS 2.0.3 (License v2.0 — unrestricted use + redistribution). Pinned to a
# commit so the stage build is reproducible. Upgrade over MuseScore_General for guitars,
# bass, and drums, with a proper GM Sitar (program 105). See soundfonts/README.md.
SF_SHA="684543d5e5efaef08d02be50dcda8d552478fa60"
SF_URL="https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$SF_SHA/GeneralUser-GS.sf2"

# 1) FluidSynth — the synth that turns MIDI into WAV.
if command -v fluidsynth >/dev/null 2>&1; then
  echo "✓ fluidsynth found: $(command -v fluidsynth)"
elif command -v brew >/dev/null 2>&1; then
  echo "→ installing fluidsynth via Homebrew..."
  brew install fluidsynth
else
  echo "✗ fluidsynth missing and no Homebrew. Install it via your package manager" >&2
  echo "  (macOS: 'brew install fluidsynth'; Debian/Ubuntu: 'apt install fluidsynth')." >&2
  exit 1
fi

# 2) Soundfont — kept out of git (large binary); download once.
if [ -f "$SF" ]; then
  echo "✓ soundfont present: $SF"
else
  echo "→ downloading GeneralUser-GS.sf2 (~31MB)..."
  mkdir -p "$ROOT/soundfonts"
  curl -fL --progress-bar -o "$SF" "$SF_URL"
  echo "✓ soundfont installed: $SF"
fi

# 3) Dethmetal — OPTIONAL dedicated distorted-guitar bank, stacked over the base so the
#    rhythm/lead guitars get a real distorted patch (the render degrades to the base's GM
#    overdrive/distortion if this is absent). LICENSE IS UNVERIFIED (the source disclaims
#    usage rights) — fetched for the demo, NOT cleared for commercial redistribution. Skip
#    with RMA_SKIP_DETHMETAL=1.
DETH="$ROOT/soundfonts/Dethmetal.sf2"
DETH_URL="https://www.zanderjaz.com/soundfonts/guitars/Dethmetal.SF2"
if [ "${RMA_SKIP_DETHMETAL:-0}" = "1" ]; then
  echo "• skipping Dethmetal (RMA_SKIP_DETHMETAL=1) — guitars will use the GM base"
elif [ -f "$DETH" ]; then
  echo "✓ Dethmetal present: $DETH"
else
  echo "→ downloading Dethmetal.sf2 (~8MB, guitar bank; license unverified)..."
  curl -fL --progress-bar -o "$DETH" "$DETH_URL" || echo "• Dethmetal download failed — guitars will use the GM base"
fi

# 4) Indian Ensemble — OPTIONAL classical bank (real tanpura drone + tabla + a multi-sampled
#    sitar). CANNOT be downloaded automatically: the source (polyphone.io) gates it behind a
#    (free) sign-in, so there is no stable direct URL. Fetch it MANUALLY, once:
#      1. sign in at https://www.polyphone.io/en/soundfonts/instrument-sets/358-indian-ensemble
#      2. download the .sf2 (~4MB, E-mu "Indian Ensemble", attribution license)
#      3. save it as:  soundfonts/Indian-Ensemble.sf2
#    Without it the render degrades cleanly: the drone stays a string pad, the tabla stays GM
#    congas, and the sitar uses the GM sitar. With it, those three route to the real samples.
INDIAN="$ROOT/soundfonts/Indian-Ensemble.sf2"
if [ -f "$INDIAN" ]; then
  echo "✓ Indian Ensemble present: $INDIAN"
else
  echo "• Indian Ensemble NOT present (manual download — see the note in setup.sh)."
  echo "  Classical voices will use the GM base until soundfonts/Indian-Ensemble.sf2 exists."
fi

echo "Setup complete. Sound check:  uv run python src/demo.py"
