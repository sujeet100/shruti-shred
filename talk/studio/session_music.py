"""
The slide-10 studio session's MUSIC, built from a real Darbari piece — no LLM, free to re-run.

`script.json` lays the session out in avartans: the sitar's head alone, then the guitar, the
bass and the drums joining one cycle at a time, the producer's stop, and the band again. Every
part is the piece's own first-mukhada avartan, moved to its slot:

  * sitar, bass-side drums and drone come from the saved composition;
  * the guitar is the Composer's `seed_riff` voiced and placed exactly as the pipeline does
    (`voice_riff` -> `place_cycles`, double-tracked), either as WRITTEN (it strikes Re under
    the sitar's held komal Ga) or ARTICULATED (`crew.articulation.articulate`: it rings through
    the sitar's held and ornamented notes) — the correction the producer asks for is the
    system's own;
  * the bass is derived from whichever riff is playing (`bass_layer`).

It renders two STEMS — the band without its kit, and the kit alone — so the mixer can set the
drums' level (`mix.py`, DRUM_GAIN_DB): at the renderer's default channel level the head's kit sat
14 dB under the band (measured by subtraction, 2026-10-18), inaudible under two distorted guitars.

    uv run python talk/studio/session_music.py   ->  out/studio_session_{band,drums}.{wav,mid,json}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from crew.articulation import articulate  # noqa: E402
from crew.contracts import Arrangement, Composition, DrumHit, Layer  # noqa: E402
from crew.generators import VOICES, bass_layer, double_track, render_composition  # noqa: E402
from crew.riff import _accent_beats, place_cycles  # noqa: E402
from crew.riff_voicing import voice_riff  # noqa: E402

SCRIPT: Final = Path(__file__).with_name("script.json")
SOUNDFONT: Final = ROOT / "soundfonts" / "GeneralUser-GS.sf2"
STEMS: Final = ("band", "drums")             # out/studio_session_<stem>.wav
COUNT_IN_VEL: Final = 70
# The clip's drum mix. In the full piece the kit sits BACK under the sitar's head (snare ~55, kick
# ~82), which is right for the song but vanishes under two hard-panned distorted guitars — and on
# this slide the drums' entry is a story beat that has to be heard. A producer's fader, not a
# change to the piece: kick and snare lifted to a solid backbeat, the hats a little.
DRUM_LIFT: Final = {"kick": 1.35, "snare": 1.8, "hhat": 1.15}


def guitar_takes(comp: Composition, arr: Arrangement, head: float) -> dict[str, list[Layer]]:
    """The rhythm guitar for the head avartan, as WRITTEN and ARTICULATED — each a double-tracked
    pair placed at the piece's own time, so the articulation pass sees the real section."""
    accents = _accent_beats(arr)
    voiced = voice_riff(arr.seed_riff, arr.raga, frozenset(accents))
    voice = VOICES["rhythm"]
    written = Layer(role="rhythm", instrument=voice.instrument, program=voice.program,
                    channel=voice.channel, pan=voice.pan,
                    notes=place_cycles([voiced.notes], start=head, cycle_beats=arr.beats_per_bar,
                                       register=arr.registers["rhythm"], accent_beats=accents,
                                       raga=arr.raga))
    sitar = [layer for layer in comp.layers if layer.role == "lead"]
    articulated = articulate(written, sitar, arr) or written
    return {name: [take, double_track(take)] for name, take in
            (("written", written), ("articulated", articulated))}


def _window(items: list[Any], head: float, span: float, to: float, stop: float | None) -> list[Any]:
    """The items starting inside [head, head + span), moved to start at `to`; with `stop` (beats
    into the slot) everything from there on is cut and anything still sounding is clipped."""
    out = []
    for item in items:
        offset = item.start - head
        if not 0 <= offset < span or (stop is not None and offset >= stop):
            continue
        dur = item.dur if stop is None else min(item.dur, stop - offset)
        out.append(item.model_copy(update={"start": round(to + offset, 4), "dur": round(dur, 4)}))
    return out


def _lifted(hits: list[DrumHit]) -> list[DrumHit]:
    """The clip's drum mix (DRUM_LIFT): each hit's velocity scaled by its drum, capped at 127."""
    return [h.model_copy(update={"vel": min(127, round(h.vel * DRUM_LIFT.get(h.drum, 1.0)))}) for h in hits]


def _count_in(at: float, beats: float) -> list[DrumHit]:
    """Four closed hi-hat clicks on the last four beats before `at` — the drummer's count."""
    return [DrumHit(drum="hhat", start=at - beats + k, dur=0.1, vel=COUNT_IN_VEL) for k in range(4)]


def session(comp: Composition, arr: Arrangement, script: dict) -> Composition:
    """The session's composition: each avartan of the script filled with its parts."""
    span, head, lead_in = script["avartan_beats"], script["source"]["head_from_beat"], script["lead_in_beats"]
    takes = guitar_takes(comp, arr, head)
    bass = {name: bass_layer(arr, pair[0]) for name, pair in takes.items()}
    source = {layer.role: layer for layer in comp.layers}
    layers: dict[tuple[str, int | None], Layer] = {}

    def add(template: Layer, items: list[Any], field: str) -> None:
        key = (template.role, template.channel)
        held = layers.setdefault(key, template.model_copy(update={"notes": None, "hits": None}))
        setattr(held, field, (getattr(held, field) or []) + items)

    for k, slot in enumerate(script["avartans"]):
        to, stop, parts = lead_in + k * span, slot.get("stop_at_beat"), set(slot["parts"])
        riff = slot.get("riff", "written")
        if "sitar" in parts:
            for role in ("lead", "chikari"):
                add(source[role], _window(source[role].notes, head, span, to, stop), "notes")
        if "guitar" in parts:
            for take in takes[riff]:
                add(take, _window(take.notes, head, span, to, stop), "notes")
        if "bass" in parts and bass[riff] is not None:
            add(bass[riff], _window(bass[riff].notes, head, span, to, stop), "notes")
        if "drums" in parts:
            add(source["drums"], _lifted(_window(source["drums"].hits, head, span, to, stop)), "hits")
        if slot.get("count_in"):
            add(source["drums"], _count_in(to + span, 4), "hits")
    end = lead_in + len(script["avartans"]) * span
    drone = source["drone"].model_copy(update={"notes": [n.model_copy(update={"start": 0.0, "dur": float(end)})
                                                         for n in source["drone"].notes]})
    return Composition(raga=comp.raga, sa=comp.sa, bpm=comp.bpm, tala=comp.tala,
                       layers=[drone, *layers.values()])


def stems(comp: Composition) -> dict[str, Composition]:
    """The session split into the band (everything but the kit) and the kit alone."""
    drums = [layer for layer in comp.layers if layer.role == "drums"]
    band = [layer for layer in comp.layers if layer.role != "drums"]
    return {"band": comp.model_copy(update={"layers": band}), "drums": comp.model_copy(update={"layers": drums})}


def main() -> list[Path]:
    script = json.loads(SCRIPT.read_text())
    comp = Composition.model_validate(json.loads((ROOT / script["source"]["composition"]).read_text()))
    arr = Arrangement.model_validate(json.loads((ROOT / script["source"]["arrangement"]).read_text()))
    split = stems(session(comp, arr, script))
    return [render_composition(split[name], out_dir=ROOT / "out", name=f"studio_session_{name}", soundfont=SOUNDFONT)
            for name in STEMS]


if __name__ == "__main__":
    print(main())
