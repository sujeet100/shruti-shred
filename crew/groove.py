"""
The Groove / Drums generator (step 4) — the metal kit, DETERMINISTIC (no LLM).

The drum groove is derivable, so it is CODE, not an agent (DESIGN.md, "the derivable
voices"): the tala's accent grid is the rhythmic skeleton, the subgenre profile gives
the kit vocabulary and technique, the section KIND sets the feel, and — like the bass
— the kit READS the riff so the kick locks to it instead of to a canned pattern. A
rule drops a tom fill into each section transition, and each section opens on a crash.

The split, applied to the drums: the tala grid + subgenre profile + riff are all facts
the code has, so no LLM decides the groove. The one place an agent might later earn its
keep is a creative fill that interprets the composers' `transition` text — added only
if the rule-based fill proves too plain (see DESIGN.md).

Pure: `groove_layer(arr, rhythm)` is data-in, data-out — fully unit-tested with no key.

Entry point (full rhythm section + drums; the riff is the only LLM call):
  uv run python -m crew.groove
"""

from __future__ import annotations

import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import Final, Optional

from crew.contracts import Arrangement, DrumHit, Layer, SectionKind
from crew.generators import (
    SectionSpan,
    assemble_composition,
    bass_layer,
    drone_layer,
    render_composition,
    section_spans,
)
from raga import validate_composition
from subgenres import SUBGENRES
from talas import TALAS

_DRUMS_ROLE: Final = "drums"
_DRUMS_CHANNEL: Final = 9                 # GM percussion channel

# Velocities per voice — the kit's dynamic shape.
_V_KICK: Final = 118
_V_SNARE: Final = 108
_V_HAT: Final = 72
_V_CRASH: Final = 112
_V_TOM: Final = 104
_SAM_ACCENT: Final = 1.08                 # the sam kick hits a touch harder

_FILL_BEATS: Final[float] = 2.0           # a transition fill takes the last 2 beats of a section
_FILL_STEP: Final[float] = 0.5            # the fill runs in 8ths


class GrooveFeel(Enum):
    """The rhythmic feel of a section's groove — set by the section kind."""
    STRAIGHT = "straight"        # driving backbeat (snare on 2 & 4)
    HALF_TIME = "half_time"      # heavy and spacious — snare once per 4 beats
    DOUBLE_TIME = "double_time"  # busy — 8th hats, kick on every beat


# The feel per section kind: an alaap has NO kit (tabla territory), a taan drives
# double-time, a breakdown/outro sits back in half-time, the rest keep a straight beat.
_FEEL_BY_KIND: Final[dict[SectionKind, Optional[GrooveFeel]]] = {
    SectionKind.ALAAP: None,
    SectionKind.MELODY: GrooveFeel.STRAIGHT,
    SectionKind.RIFF: GrooveFeel.STRAIGHT,
    SectionKind.SOLO: GrooveFeel.STRAIGHT,
    SectionKind.TAAN: GrooveFeel.DOUBLE_TIME,
    SectionKind.BREAKDOWN: GrooveFeel.HALF_TIME,
    SectionKind.OUTRO: GrooveFeel.HALF_TIME,
}


def _feel_for(kind: SectionKind) -> Optional[GrooveFeel]:
    return _FEEL_BY_KIND.get(kind, GrooveFeel.STRAIGHT)


# --------------------------------------------------------------------------- #
# Kit vocabulary + the per-cycle pattern positions. Pure.                      #
# --------------------------------------------------------------------------- #

def _voices(arr: Arrangement) -> set[str]:
    return set(SUBGENRES[arr.subgenre]["drums"]["voices"])


def _double_kick(arr: Arrangement) -> bool:
    return bool(SUBGENRES[arr.subgenre]["drums"]["double_kick"])


def _dense(arr: Arrangement) -> bool:
    return SUBGENRES[arr.subgenre]["drums"]["density"] in ("dense", "very dense")


def _accent_cymbal(voices: set[str]) -> str:
    """The best available cymbal for a section-opening accent."""
    for cymbal in ("crash", "china", "ride", "hhat"):
        if cymbal in voices:
            return cymbal
    return "hhat"


def _arange(start: float, end: float, step: float) -> list[float]:
    """Evenly spaced beats in [start, end), rounded — the on-grid positions."""
    positions: list[float] = []
    t = start
    while t < end - 1e-9:
        positions.append(round(t, 4))
        t += step
    return positions


def _hat_positions(cycle: int, feel: GrooveFeel, dense: bool) -> list[float]:
    step = 0.5 if (feel is GrooveFeel.DOUBLE_TIME or dense) else 1.0
    return _arange(0.0, float(cycle), step)


def _snare_positions(cycle: int, feel: GrooveFeel) -> list[float]:
    if feel is GrooveFeel.HALF_TIME:
        return [float(b) for b in range(cycle) if b % 4 == 2]   # heavy half-time backbeat
    return [float(b) for b in range(cycle) if b % 2 == 1]       # 2 & 4


def _kick_positions(cycle: int, feel: GrooveFeel, double_kick: bool) -> list[float]:
    if feel is GrooveFeel.HALF_TIME:
        return [float(b) for b in range(cycle) if b % 4 == 0]   # sparse, on the "1"
    if feel is GrooveFeel.DOUBLE_TIME and double_kick:
        return _arange(0.0, float(cycle), 0.5)                  # double-bass 8ths
    if double_kick or feel is GrooveFeel.DOUBLE_TIME:
        return [float(b) for b in range(cycle)]                 # kick every beat
    return [float(b) for b in range(cycle) if b % 2 == 0]       # 1 & 3


# --------------------------------------------------------------------------- #
# Riff lock + fills + one section's hits. Pure.                                #
# --------------------------------------------------------------------------- #

def _riff_onbeats(rhythm: Layer | None, span: SectionSpan) -> set[float]:
    """The whole-beat onsets the riff hits in this section — the kick locks to these
    (the same on-beat rule the bass uses), so kick, bass and riff all land together."""
    if rhythm is None or not rhythm.notes:
        return set()
    return {n.start for n in rhythm.notes
            if span.start <= n.start < span.end and float(n.start).is_integer()}


def _tom_fill(start: float, end: float, voices: set[str]) -> list[DrumHit]:
    """A descending tom run (with a kick under each hit) over [start, end) — the
    transition fill that leads into the next section's opening crash."""
    toms = [t for t in ("tom_hi", "tom_mid", "tom_lo") if t in voices]
    if not toms:
        toms = ["tom_lo"] if "tom_lo" in voices else ["snare"]
    positions = _arange(start, end, _FILL_STEP)
    hits: list[DrumHit] = []
    for i, t in enumerate(positions):
        drum = toms[min(i * len(toms) // max(1, len(positions)), len(toms) - 1)]
        hits.append(DrumHit(drum=drum, start=t, vel=_V_TOM))
        hits.append(DrumHit(drum="kick", start=t, vel=_V_KICK))
    return hits


def _section_hits(arr: Arrangement, span: SectionSpan, rhythm: Layer | None,
                  feel: GrooveFeel, *, fill_into_next: bool) -> list[DrumHit]:
    """One section's groove: the per-cycle pattern repeated across its bars, the kick
    locked to the riff, a tom fill carved into the last bar, and an opening crash."""
    cycle = int(arr.beats_per_bar)
    voices = _voices(arr)
    hats = _hat_positions(cycle, feel, _dense(arr))
    snares = _snare_positions(cycle, feel)
    kicks = _kick_positions(cycle, feel, _double_kick(arr))
    riff_beats = _riff_onbeats(rhythm, span)

    hits: list[DrumHit] = []
    for bar in range(span.section.bars):
        base = span.start + bar * cycle
        hits += [DrumHit(drum="hhat", start=round(base + h, 4), vel=_V_HAT) for h in hats]
        hits += [DrumHit(drum="snare", start=round(base + s, 4), vel=_V_SNARE) for s in snares]
        # kick: the pattern PLUS the riff's on-beat onsets in this bar (deduped)
        kick_beats = {round(base + k, 4) for k in kicks}
        kick_beats |= {round(b, 4) for b in riff_beats if base <= b < base + cycle}
        for k in sorted(kick_beats):
            vel = min(127, round(_V_KICK * _SAM_ACCENT)) if k == round(base, 4) else _V_KICK
            hits.append(DrumHit(drum="kick", start=k, vel=vel))

    if fill_into_next:
        fill_start = span.end - _FILL_BEATS
        hits = [h for h in hits if h.start < fill_start]   # clear the fill zone
        hits += _tom_fill(fill_start, span.end, voices)

    hits.append(DrumHit(drum=_accent_cymbal(voices), start=round(span.start, 4), vel=_V_CRASH))
    return hits


def groove_layer(arr: Arrangement, rhythm: Layer | None) -> Layer | None:
    """The metal-kit drums layer for the whole piece. Deterministic, no LLM.

    Fills the drums for each section that lists `drums`, choosing the feel from the
    section kind (an alaap gets no kit). The kick locks to `rhythm` (the riff) where
    present; a tom fill leads each section into the next. Returns None when no section
    uses the kit.
    """
    spans = section_spans(arr)
    hits: list[DrumHit] = []
    for i, span in enumerate(spans):
        if _DRUMS_ROLE not in span.section.layers:
            continue
        feel = _feel_for(span.section.kind)
        if feel is None:                       # alaap: no kit
            continue
        hits += _section_hits(arr, span, rhythm, feel, fill_into_next=(i + 1 < len(spans)))

    if not hits:
        return None
    return Layer(role=_DRUMS_ROLE, channel=_DRUMS_CHANNEL, hits=hits)


# --------------------------------------------------------------------------- #
# Tabla — the Hindustani theka, DETERMINISTIC. The tala's theka IS the tabla    #
# part (it lives in talas.py), so this is pure data -> hits: one bol per matra, #
# repeated across the section's bars, accented on the sam/tali. Tabla may play  #
# ALONGSIDE the metal kit (tabla under the groove is a core fusion sound) — both #
# are GM-channel-9 percussion and mix.                                          #
# --------------------------------------------------------------------------- #

_TABLA_ROLE: Final = "tabla"
_V_TABLA_SAM: Final = 92
_V_TABLA_TALI: Final = 82
_V_TABLA_KHALI: Final = 58
_V_TABLA_BEAT: Final = 66

# Which conga voice(s) a theka bol maps to: resonant two-hand bols ring both, the
# closed bass bols are bayan-only, the rest are treble (dayan). Covers every bol in
# the six encoded thekas (talas.py).
_BOL_BOTH: Final = frozenset({"Dha", "Dhin", "Dhi", "Dhage"})
_BOL_LOW: Final = frozenset({"Ge", "Ka", "Kat"})


def _bol_voices(bol: str) -> tuple[str, ...]:
    if bol in _BOL_BOTH:
        return ("tabla_lo", "tabla_hi")
    if bol in _BOL_LOW:
        return ("tabla_lo",)
    return ("tabla_hi",)


def _tabla_vel(kind: str) -> int:
    return {"sam": _V_TABLA_SAM, "tali": _V_TABLA_TALI,
            "khali": _V_TABLA_KHALI}.get(kind, _V_TABLA_BEAT)


def tabla_layer(arr: Arrangement) -> Layer | None:
    """The tabla theka for the whole piece — the tala's encoded bols, one per matra.

    Deterministic, no LLM: the theka is a FACT in talas.py. Lays it across every
    tabla-active section, mapping each bol to the conga stand-ins and accenting the
    sam and tali from the accent grid. Returns None when no section uses the tabla.
    """
    theka = TALAS[arr.tala]["theka"]
    kinds = [a.kind for a in arr.accent_grid]          # one per matra, aligned to theka
    cycle = int(arr.beats_per_bar)
    hits: list[DrumHit] = []
    for span in section_spans(arr):
        if _TABLA_ROLE not in span.section.layers:
            continue
        for bar in range(span.section.bars):
            base = span.start + bar * cycle
            for matra, bol in enumerate(theka):
                vel = _tabla_vel(kinds[matra])
                for voice in _bol_voices(bol):
                    hits.append(DrumHit(drum=voice, start=round(base + matra, 4), vel=vel))
    if not hits:
        return None
    return Layer(role=_TABLA_ROLE, channel=_DRUMS_CHANNEL, hits=hits)


# --------------------------------------------------------------------------- #
# The imperative edge — the full rhythm section + drums (riff = the LLM call).  #
# --------------------------------------------------------------------------- #

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "MuseScore_General.sf3"
_OUT_DIR: Final[Path] = _ROOT / "out"


def _groove_demo_arrangement() -> Arrangement:
    """A two-section chart (RIFF -> BREAKDOWN) so the confirmation hears the groove
    CHANGE (straight -> half-time) and the tom FILL at the seam. Doom/Darbari, slow
    enough to hear it. Built through the real composer contract (no LLM here)."""
    from crew.contracts import ArrangementDraft, CompositionBrief, Section, SectionKind, build_arrangement
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=80,
        motif=["S", "R", "g", "R", "g", "m", "P"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drums", "drone"],
                    foreground="rhythm", intent="the main crushing riff",
                    transition="a tom fill rolls into the breakdown"),
            Section(kind=SectionKind.BREAKDOWN, bars=2, layers=["rhythm", "drums", "drone"],
                    foreground="rhythm", intent="half-time, even heavier"),
        ],
    )
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _run() -> None:
    from crew.contracts import EventStream
    from crew.riff import compose_riff

    arr = _groove_demo_arrangement()
    stream = EventStream()
    rhythm, events = compose_riff(arr)          # the only LLM work (one call per riff section)
    for event in events:
        stream.emit(event)

    groove = groove_layer(arr, rhythm)
    bass = bass_layer(arr, rhythm)
    layers = [drone_layer(arr)] + [x for x in (rhythm, bass, groove) if x is not None]
    comp = assemble_composition(arr, layers)
    payload = comp.model_dump(exclude_none=True)
    violations = validate_composition(payload)
    n_hits = len(groove.hits) if groove else 0
    print(f"full rhythm section ({len(layers)} layers, {n_hits} drum hits): "
          f"{len(violations)} grammar violation(s)")

    if shutil.which("fluidsynth") and _SOUNDFONT.exists():
        wav = render_composition(comp, out_dir=_OUT_DIR, name="rhythm_section", soundfont=_SOUNDFONT)
        print(f"-> rendered {wav.relative_to(_ROOT)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")


def main(argv: list[str]) -> int:
    from crew.config import load_env
    load_env()
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("groove-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
