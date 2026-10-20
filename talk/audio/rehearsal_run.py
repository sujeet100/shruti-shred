"""
The REHEARSAL, live (Sujit, 2026-10-19): a sitarist and a guitarist hear a finished song, each
proposes one change, the band plays every change and argues, and a bandleader fluent in Hindustani
and Western theory decides. Up to three rounds, then the bandleader's blind before/after check on
the whole song (`crew/rehearsal.py`).

The song: fusion_20261013_074703 — the latest full live Darbari render (160 s, doom, teentaal at
120 bpm, every part of the form). Every version is rendered (FluidSynth, free); every listening
call goes to Gemini's audio model (`RMA_LISTEN_MODEL`, Pro by default) and is logged in calls.jsonl
(google-genai directly, so the CrewAI tracer does not see it).

    uv run python talk/audio/rehearsal_run.py [fusion_<stamp> [out/rehearsal_<stamp> to resume]]   ->  out/rehearsal_<stamp>/{transcript.md, record.json, *.wav}
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SONG: Final = ROOT / "out" / (sys.argv[1] if len(sys.argv) > 1 else "fusion_20261013_074703")
# RESUME: a previous rehearsal's calls.jsonl — any call whose prompt and clips match one it holds is
# answered from it (renders are deterministic, so the same song gives the same prompts and clips).
RESUME: Final = Path(sys.argv[2]) if len(sys.argv) > 2 else None
TIMEOUT_S: Final = 240.0         # one audio call; a stuck call (2026-10-19: 35 min) fails and is retried once
RATE: Final = 16000


def clips_command(clips: list[tuple[Path, float, float | None]], gaps: list[float]) -> list[str]:
    """argv: the clips joined, with the given silences between them, as one 16 kHz mono FLAC."""
    argv = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for path, start, end in clips:
        argv += ["-ss", f"{start:.2f}"] + (["-to", f"{end:.2f}"] if end is not None else []) + ["-i", str(path)]
    fmt = f"aformat=sample_rates={RATE}:channel_layouts=mono"
    parts, labels = [], []
    for i in range(len(clips)):
        parts.append(f"[{i}:a]{fmt}[c{i}]")
        labels.append(f"[c{i}]")
        if i < len(gaps):
            parts.append(f"anullsrc=r={RATE}:cl=mono,atrim=duration={gaps[i]:.2f}[g{i}]")
            labels.append(f"[g{i}]")
    graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]"
    return argv + ["-filter_complex", graph, "-map", "[out]", "-f", "flac", "pipe:1"]


def main() -> Path:
    from crew.config import listen_model, load_env
    from crew.contracts import Arrangement, Composition
    from crew.flow import _SOUNDFONT
    from crew.generators import render_composition
    from crew.listening import GeminiAudioJudge
    from crew.rehearsal import as_record, rehearse, transcript
    load_env()
    out = ROOT / "out" / f"rehearsal_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True)
    comp = Composition.model_validate_json((SONG.with_suffix(".json")).read_text())
    arr = Arrangement.model_validate_json(SONG.with_name(SONG.name + ".arrangement.json").read_text())
    wavs: dict[str, Path] = {}
    judge = GeminiAudioJudge(listen_model(), timeout_s=TIMEOUT_S)
    calls = out / "calls.jsonl"
    saved: dict[str, str] = {}
    if RESUME is not None:
        for line in (RESUME / "calls.jsonl").read_text().splitlines():
            c = json.loads(line)
            saved[json.dumps([c["clips"], c["gaps"], c["prompt"]])] = c["answer"]

    def studio(c, a, name):
        if name == "r0_song":                                     # the song as it came in: no re-render
            shutil.copy(SONG.with_suffix(".wav"), out / "r0_song.wav")
            wavs[name] = out / "r0_song.wav"
        else:
            wavs[name] = render_composition(c, out_dir=out, name=name, soundfont=_SOUNDFONT, arrangement=a)
        return name

    def ears(clips, gaps, prompt):
        key = json.dumps([[vars(c) for c in clips], gaps, prompt])
        if key in saved:
            print("  replayed a saved call", flush=True)
            answer = saved[key]
            with calls.open("a") as log:
                log.write(json.dumps({"seconds": 0, "model": "replay", "clips": [vars(c) for c in clips],
                                      "gaps": gaps, "prompt": prompt, "answer": answer}) + "\n")
            return answer
        audio = subprocess.run(clips_command([(wavs[c.version], c.start, c.end) for c in clips], gaps),
                               capture_output=True, check=True).stdout
        started = time.time()
        try:
            answer = judge.judge(audio, "audio/flac", prompt)
        except Exception as exc:  # noqa: BLE001 — one retry on a timeout or a provider blip
            print(f"  call failed ({type(exc).__name__}); retrying once", flush=True)
            answer = judge.judge(audio, "audio/flac", prompt)
        with calls.open("a") as log:
            log.write(json.dumps({"seconds": round(time.time() - started, 1), "model": listen_model(),
                                  "clips": [vars(c) for c in clips], "gaps": gaps, "prompt": prompt,
                                  "answer": answer}) + "\n")
        print(f"  heard {len(clips)} clip(s) in {time.time() - started:.0f}s", flush=True)
        return answer

    result = rehearse(comp, arr, ears=ears, studio=studio)
    (out / "transcript.md").write_text(f"# Rehearsal of {SONG.name}\n\n" + transcript(result) + "\n")
    (out / "record.json").write_text(as_record(result))
    return out


if __name__ == "__main__":
    print(main())
