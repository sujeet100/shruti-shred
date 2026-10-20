"""
The studio session's spoken lines -> one WAV per line + a manifest (`voices/voices.json`) the
scene reads for each line's real duration.

`--engine say` uses the Mac's local voices: free scratch audio for judging timing and wording.
`--engine gemini` is the real cast (Sujit approved the script 2026-10-18): one Gemini TTS call
per line (paid), a fixed prebuilt voice per character; the line alone is sent. Delivery comes from
the voice and the line's own punctuation — gemini-3.8-flash-tts reads a "Say warmly: ..." prefix
ALOUD and rejects a system instruction (both tried 2026-10-18). The manifest records model and
voice, so a take can be traced and redone.

    uv run python talk/studio/voices.py [--engine say|gemini] [--only <line index>] | --retrim
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))                  # the repo root, for crew.config
SCRIPT: Final = HERE / "script.json"
OUT: Final = HERE / "voices"
RATE: Final = 48000
# One local voice per character, distinct enough to follow who is talking (scratch only).
SAY_VOICES: Final = {"sitar": "Rishi", "guitar": "Daniel", "bass": "Ralph", "drums": "Fred",
                     "producer": "Karen"}


TTS_MODEL: Final = os.getenv("RMA_TTS_MODEL", "gemini-3.8-flash-tts")
TTS_RATE: Final = 24000                      # Gemini TTS returns 16-bit mono PCM at 24 kHz
# The cast: one prebuilt voice per character, chosen for the role's temperament.
GEMINI_VOICES: Final = {"sitar": "Sulafat", "guitar": "Puck", "bass": "Algenib", "drums": "Fenrir",
                        "producer": "Kore"}


def _gemini(text: str, who: str, wav: Path) -> dict:
    """One line through Gemini TTS -> a 48 kHz mono WAV; returns what the take used."""
    from google import genai
    from google.genai import types

    from crew.config import load_env
    load_env()
    client = genai.Client()                      # held: an inline client is closed before it sends
    response = client.models.generate_content(
        model=TTS_MODEL, contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICES[who])))))
    audio = response.candidates[0].content.parts[0].inline_data
    raw = wav.with_suffix(".24k.wav")
    if audio.data[:4] == b"RIFF":
        # gemini-3.8-flash-tts returns a whole WAV file (header + speech + a trailing metadata
        # chunk), not bare PCM: wrapped as PCM, that chunk played as a 127 ms scratch at the end
        # of every line (2026-10-18). Write it as the file it is.
        raw.write_bytes(audio.data)
    else:                                       # bare 16-bit PCM (the documented L16 response)
        with wave.open(str(raw), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(TTS_RATE)
            out.writeframes(audio.data)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-ar", str(RATE), str(wav)], check=True)
    raw.unlink()
    return {"model": TTS_MODEL, "model_version": getattr(response, "model_version", None),
            "voice": GEMINI_VOICES[who]}


# Leading silence and trailing breath off every take, so a line's duration is its speech.
TRIM: Final = ("silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.02,areverse,"
               "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.08,areverse")


def _trim(wav: Path) -> None:
    tmp = wav.with_suffix(".trim.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", TRIM, str(tmp)], check=True)
    tmp.replace(wav)


def _duration(path: Path) -> float:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(path)], capture_output=True, text=True, check=True)
    return float(probe.stdout.strip())


def _say(text: str, who: str, wav: Path) -> None:
    aiff = wav.with_suffix(".aiff")
    subprocess.run(["say", "-v", SAY_VOICES[who], "-o", str(aiff), text], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", str(RATE), "-ac", "1",
                    str(wav)], check=True)
    aiff.unlink()


def main(engine: str, only: int | None = None) -> Path:
    if engine not in ("say", "gemini"):
        raise SystemExit(f"engine {engine!r}: say | gemini")
    OUT.mkdir(exist_ok=True)
    lines = json.loads(SCRIPT.read_text())["lines"]
    manifest = []
    previous = json.loads((OUT / "voices.json").read_text()) if (OUT / "voices.json").exists() else []
    for k, line in enumerate(lines):
        wav = OUT / f"{k:02d}_{line['who']}.wav"
        if only is not None and k != only:              # keep the other takes as they are
            manifest.append(previous[k])
            continue
        take = {}
        if engine == "say":
            _say(line["text"], line["who"], wav)
        else:
            take = _gemini(line["text"], line["who"], wav)
        _trim(wav)
        manifest.append({**line, "file": wav.name, "dur": round(_duration(wav), 3), "engine": engine, **take})
    path = OUT / "voices.json"
    path.write_text(json.dumps(manifest, indent=1))
    return path


def retrim() -> Path:
    """Trim the existing takes and re-measure them — no new speech, no API call."""
    path = OUT / "voices.json"
    manifest = json.loads(path.read_text())
    for line in manifest:
        _trim(OUT / line["file"])
        line["dur"] = round(_duration(OUT / line["file"]), 3)
    path.write_text(json.dumps(manifest, indent=1))
    return path


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--retrim" in args:
        print(retrim())
        sys.exit(0)
    only = int(args[args.index("--only") + 1]) if "--only" in args else None
    print(main(args[args.index("--engine") + 1] if "--engine" in args else "say", only))
