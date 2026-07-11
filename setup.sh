#!/usr/bin/env bash
# One-time setup for the render pipeline's SYSTEM dependencies.
#
# Python deps are handled by uv (`uv run ...`). But two things are NOT Python
# packages and can't come from uv: FluidSynth (a system binary) and the
# MuseScore_General soundfont (a ~38MB asset with no reliable PyPI package).
# This script installs both. It is idempotent — safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SF="$ROOT/soundfonts/MuseScore_General.sf3"
SF_URL="https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3"

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
  echo "→ downloading MuseScore_General.sf3 (~38MB)..."
  mkdir -p "$ROOT/soundfonts"
  curl -fL --progress-bar -o "$SF" "$SF_URL"
  echo "✓ soundfont installed: $SF"
fi

echo "Setup complete. Sound check:  uv run python src/demo.py"
