"""Blind A/B, free (no LLM): who should write the guitar under the mukhada? (Sujit, 2026-10-20.)

For each recent song that carries both Pandit's seed riff and a composed rhythm section, the band is
rebuilt TWICE from the saved chart and sitar line, identical except for the guitar in the mukhada
sections:

    seed   — Pandit's main riff (the seed), played under every mukhada
    rhythm — the Rhythm section's own mukhada guitar, as it shipped

Both versions take the code-derived bass in the mukhada (so only the guitar differs), go through the
same assembly (double-track, drums locked to the guitar, dynamics), and are cut to the FIRST mukhada
section and loudness-matched. Files are labelled X / Y at random; the key is in key.json.

    uv run python talk/audio/mukhada_ab.py   ->  out/mukhada_ab_<stamp>/{NN_raga_X.wav, NN_raga_Y.wav, key.json}
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(Path(__file__).resolve().parent)]

SONGS = ("fusion_20261019_184632_pipeline_darbari", "fusion_20261019_100727_bhairav", "fusion_20261019_083259_fresh",
         "fusion_20261018_142210_bhairav", "fusion_20261018_132646_darbari")
SPLICED = ("rhythm", "bass", "drums")        # the roles each version rebuilds; every other layer stays as shipped
TARGET_LUFS = -18.0


def _role(section) -> str:
    r = section.form_role
    return str(getattr(r, "value", r) or "")


def _variant(arr, use_seed: bool):
    """The chart with every mukhada part made explicit: the seed riff or the part's own resolved
    guitar, and no written bass (code derives it), so the two versions differ only in the guitar."""
    from crew.contracts import RhythmSection, SectionPart
    from crew.generators import section_spans
    from crew.rhythm_section import _resolved
    rs = arr.rhythm_section
    parts = {p.section: p for p in rs.parts}
    heads = [s.index for s in section_spans(arr) if _role(s.section) == "mukhada"]
    out = []
    for i in sorted(set(parts) | set(heads)):
        if i not in heads:
            out.append(parts[i])
            continue
        own = _resolved(parts[i], parts) if i in parts else _resolved(parts[heads[0]], parts)
        guitar = [list(arr.seed_riff.notes)] if use_seed else list(own.guitar)
        out.append(SectionPart(section=i, role="seed riff" if use_seed else own.role, guitar=guitar, bass=[]))
    return arr.model_copy(update={"rhythm_section": RhythmSection(reasoning=rs.reasoning, parts=out)}), heads


def _build(arr, comp, use_seed: bool):
    from crew.band import band_layers
    from crew.rhythm_section import part_errors, realise
    v, heads = _variant(arr, use_seed)
    errors = part_errors(v.rhythm_section, v)
    guitar, _ = realise(v.rhythm_section, v)
    leads = [ly for ly in comp.layers if ly.role == "lead"]
    orch = [ly for ly in comp.layers if ly.role.startswith("orch_")]
    built = band_layers(v, leads, guitar, orch)
    layers = [ly for ly in comp.layers if ly.role not in SPLICED] + [ly for ly in built if ly.role in SPLICED]
    return comp.model_copy(update={"layers": layers}), heads, errors


def _cut(src: Path, dst: Path, start_s: float, dur_s: float) -> None:
    import make_clips as mc
    tmp = dst.with_suffix(".raw.wav")
    mc.cut(src, tmp, start_s, dur_s, fade_out=0.6)
    gain = TARGET_LUFS - mc.lufs(tmp)
    mc.ff("-i", str(tmp), "-af", f"volume={gain:.2f}dB", "-c:a", "pcm_s16le", str(dst))
    tmp.unlink()


def main() -> Path:
    from crew.contracts import Arrangement, Composition
    from crew.flow import _SOUNDFONT
    from crew.generators import render_composition, section_spans
    out = ROOT / "out" / f"mukhada_ab_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True)
    key, report = {}, []
    for n, stem in enumerate(SONGS, start=1):
        base = ROOT / "out" / stem
        arr = Arrangement.model_validate_json(base.with_name(stem + ".arrangement.json").read_text())
        comp = Composition.model_validate_json(base.with_suffix(".json").read_text())
        labels = ["X", "Y"]
        random.Random(f"{stem}-mukhada").shuffle(labels)                 # deterministic, but not by song order
        tag = f"{n:02d}_{arr.raga}"
        for use_seed, label in zip((True, False), labels):
            version, heads, errors = _build(arr, comp, use_seed)
            full = render_composition(version, out_dir=out / "full", name=f"{tag}_{label}", soundfont=_SOUNDFONT)
            span = next(s for s in section_spans(arr) if s.index == heads[0])
            spb = 60.0 / arr.bpm
            _cut(full, out / f"{tag}_{label}.wav", span.start * spb, (span.end - span.start) * spb)
            key[f"{tag}_{label}"] = "seed (Pandit's riff)" if use_seed else "rhythm (the Rhythm section's guitar)"
            report.append(f"{tag}_{label}: {stem}, mukhada sections {heads}, first at {span.start * spb:.1f} s"
                          + (f"; checks: {errors}" if errors else ""))
    (out / "key.json").write_text(json.dumps(key, indent=2) + "\n")
    (out / "notes.md").write_text("# Mukhada guitar, blind\n\n" + "\n".join(f"- {r}" for r in report) + "\n")
    return out


if __name__ == "__main__":
    print(main())
