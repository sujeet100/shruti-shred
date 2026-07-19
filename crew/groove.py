"""
The Groove / Drums generator (step 4) — the metal kit, DETERMINISTIC (no LLM).

The drum groove is derivable, so it is CODE, not an agent (DESIGN.md, "the derivable
voices") — but v2 makes the code a real metal drummer instead of a pop machine. The
architecture borrows Logic Pro's Drummer (see DESIGN.md, "Drum machine v2"): a
section's ENERGY picks a research-grounded pattern from the subgenre's vocabulary
(skank, D-beat, blasts, gallop, half-time, the prog kick-drift), the kit voice is a
per-section choice (tight hat verses, ride-led antara, crash-wash climax), fills are
a property of BOUNDARIES (phrase turnarounds, mid-section mini-fills, seam fills,
the band-entrance pickup roll), and velocities carry the humanity (four levels,
ghost notes, deterministic jitter).

The tala × subgenre intersection is finally structural: patterns tile per VIBHAG
(odd talas reshape them), each sam lands a crash + kick, the tali lean in (bell),
and the khali vibhag sits back — the tala's accent skeleton drives the kit, not
just the tabla. The kick still locks to the riff's on-beats; progressive shadows
EVERY riff onset (the Meshuggah "quadruple-meter backbeat": steady hands, the kick
plays the riff).

Pure: `groove_layer(arr, rhythm)` is data-in, data-out — fully unit-tested with no key.

Entry point (full rhythm section + drums; the riff is the only LLM call):
  uv run python -m crew.groove
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Optional

from crew.contracts import Arrangement, DrumHit, Layer, Section, SectionKind
from crew.drum_patterns import (
    PATTERNS,
    TURNAROUND_KICKS,
    VEL_BELL,
    VEL_CRASH,
    VEL_CYM_ACCENT,
    VEL_ENTRANCE,
    VEL_KICK,
    VEL_KICK_SOFT,
    VEL_SNARE,
    ghost_snares,
    humanized,
    pickup_roll,
    tom_run,
)
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

_TALI_BUMP: Final = 8                     # the tali cymbal leans in
_KHALI_DIP: Final = 10                    # the khali vibhag sits back (the "empty" wave)
_TURNAROUND_BUMP: Final = 6               # the phrase's last backbeat runs hotter
_MINI_FILL_BEATS: Final[float] = 1.0      # the mid-section nudge (the "bar 8" fill)
_SEAM_FILL_BEATS: Final[float] = 2.0      # the section-transition fill
_BIG_FILL_BEATS: Final[float] = 4.0       # ...upgraded when the CLIMAX is next
_PICKUP_BEATS: Final[float] = 1.0         # the entrance snare roll
_DOOM_DRAG: Final[float] = 0.02           # doom backbeats land ~15ms late — the drag IS doom
_RIFF_ACCENT_MIN_RING: Final[float] = 1.0  # a riff note this long (and open) counts as an accent


class GrooveEnergy(Enum):
    """A section's drum energy (Logic-Drummer style) — picks pattern + kit voice."""
    VERSE = "verse"      # tight and contained — the lead has the spotlight
    DRIVE = "drive"      # the subgenre's signature engine at full push
    CLIMAX = "climax"    # everything up: the busiest pattern under a crash wash
    HALF = "half"        # half the perceived rate — heavy, spacious


# Energy per section kind: an alaap has NO kit (tabla territory), a taan is the
# climax, a breakdown/outro sits back in half-time.
_ENERGY_BY_KIND: Final[dict[SectionKind, Optional[GrooveEnergy]]] = {
    SectionKind.ALAAP: None,
    SectionKind.MELODY: GrooveEnergy.VERSE,
    SectionKind.RIFF: GrooveEnergy.DRIVE,
    SectionKind.SOLO: GrooveEnergy.DRIVE,
    SectionKind.TAAN: GrooveEnergy.CLIMAX,
    SectionKind.BREAKDOWN: GrooveEnergy.HALF,
    SectionKind.OUTRO: GrooveEnergy.HALF,
}

# The gat form_role overrides the kind: the ANTARA sits back on the ride in
# half-time (the higher-register development wants air under it, not a crash),
# and the reserved long taan IS the climax.
_ENERGY_BY_ROLE: Final[dict[str, GrooveEnergy]] = {
    "antara": GrooveEnergy.HALF,
    "taan_long": GrooveEnergy.CLIMAX,
    "breakdown": GrooveEnergy.HALF,
}


def _energy_for(section: Section) -> Optional[GrooveEnergy]:
    if section.kind is SectionKind.ALAAP:
        return None
    if section.form_role in _ENERGY_BY_ROLE:
        return _ENERGY_BY_ROLE[section.form_role]
    return _ENERGY_BY_KIND.get(section.kind, GrooveEnergy.DRIVE)


# --------------------------------------------------------------------------- #
# The groove plan: subgenre style tables + cymbal orchestration. Pure.         #
# --------------------------------------------------------------------------- #

# The subgenre's pattern per energy (HALF is always the half-time crush). Blasts
# appear only where the profile declares them idiomatic.
# Driving metal grooves per subgenre — the plain `backbeat` (the pop beat's cousin) is pulled from
# the mid-tempo VERSE/DEFAULT slots where it read pop (Sujit, 2026-07-16: "remove simple pop-like
# grooves, keep hard rock/metal grooves"). Grounded in the metal-drumming taxonomy (Wikipedia;
# Drumeo/Modern Drummer): heavy = the Maiden gallop, thrash = skank/D-beat, death = double-bass +
# blast, black = blast/skank, prog = syncopation over the odd vibhag groupings. DOOM keeps the
# backbeat — dragged late and hit heavy (the `_DOOM_DRAG` + rimshot weight), it is the doom groove,
# NOT a pop beat — so removing it there would lose doom's identity.
_STYLE: Final[dict[str, dict[GrooveEnergy, str]]] = {
    "heavy": {GrooveEnergy.VERSE: "dbeat", GrooveEnergy.DRIVE: "gallop",
              GrooveEnergy.CLIMAX: "double16"},
    "thrash": {GrooveEnergy.VERSE: "dbeat", GrooveEnergy.DRIVE: "skank",
               GrooveEnergy.CLIMAX: "double16"},
    "doom": {GrooveEnergy.VERSE: "halftime", GrooveEnergy.DRIVE: "backbeat",
             GrooveEnergy.CLIMAX: "backbeat"},   # the dragged, heavy doom backbeat IS doom (not pop)
    "death": {GrooveEnergy.VERSE: "double16", GrooveEnergy.DRIVE: "blast",
              GrooveEnergy.CLIMAX: "bomb"},
    "black": {GrooveEnergy.VERSE: "skank", GrooveEnergy.DRIVE: "blast",
              GrooveEnergy.CLIMAX: "hammer"},
    "melodic_death": {GrooveEnergy.VERSE: "gallop", GrooveEnergy.DRIVE: "gallop",
                      GrooveEnergy.CLIMAX: "blast"},
    "progressive": {GrooveEnergy.VERSE: "dbeat", GrooveEnergy.DRIVE: "prog",
                    GrooveEnergy.CLIMAX: "double16"},
}
_DEFAULT_STYLE: Final[dict[GrooveEnergy, str]] = {
    GrooveEnergy.VERSE: "dbeat", GrooveEnergy.DRIVE: "gallop",
    GrooveEnergy.CLIMAX: "double16",
}

# The DRIVE timekeeper per subgenre (verses stay on the tight closed hat, the
# climax washes the crash): death rides a tight ride, melodeath/prog punch the
# bell, doom rides the crash.
_DRIVE_CYMBAL: Final[dict[str, str]] = {
    "heavy": "hhat", "thrash": "hhat", "doom": "crash", "death": "ride",
    "black": "hhat", "melodic_death": "bell", "progressive": "bell",
}

_CYMBAL_FALLBACK: Final[dict[str, tuple[str, ...]]] = {
    "bell": ("ride", "hhat"), "ride": ("hhat",), "china": ("crash", "ride", "hhat"),
    "crash": ("ride", "hhat"), "hhat": (),
}


def _available(want: str, voices: set[str]) -> str:
    """The wanted cymbal, degraded along its fallback chain to what the kit has."""
    for cymbal in (want, *_CYMBAL_FALLBACK.get(want, ())):
        if cymbal in voices:
            return cymbal
    return "hhat"


@dataclass(frozen=True)
class GroovePlan:
    """How one section grooves — pattern, timekeeper, sam accent, realism knobs."""
    pattern: str
    cymbal: str          # the timekeeping voice
    sam_cymbal: str      # the accent landing on each phrase-opening sam
    ghosts: bool         # ghost snares in the pockets (roomy grooves only)
    follow_riff: bool    # prog: the kick shadows EVERY riff onset (16th-quantized)
    spread: int          # velocity-jitter width (black metal stays icy-flat)
    drag: float          # lay the backbeat back by this many beats (doom)


def _plan_for(section: Section, subgenre: str, energy: GrooveEnergy,
              voices: set[str]) -> GroovePlan:
    profile = SUBGENRES[subgenre]["drums"]
    pattern = ("halftime" if energy is GrooveEnergy.HALF
               else _STYLE.get(subgenre, _DEFAULT_STYLE)[energy])
    if energy is GrooveEnergy.CLIMAX:
        want = "crash"                     # wash the crash under the climax
    elif energy is GrooveEnergy.HALF:
        want = "china" if section.kind is SectionKind.BREAKDOWN else "ride"
    elif energy is GrooveEnergy.DRIVE:
        want = _DRIVE_CYMBAL.get(subgenre, "hhat")
    else:
        want = "hhat"
    cymbal = _available(want, voices)
    # ride-led sections punch the BELL on the sam instead of crashing over the line
    sam = ("bell" if cymbal in ("ride", "bell")
           else "china" if cymbal == "china" else "crash")
    # ghosts on every roomy groove except the CLIMAX blast walls (they have no gaps) —
    # widened from VERSE/HALF-only (2026-07-19) so DRIVE grooves breathe too.
    ghosts = (energy is not GrooveEnergy.CLIMAX
              and profile["density"] in ("sparse", "medium"))
    spread = 1 if subgenre == "black" else 3 if profile["density"] == "very dense" else 4
    return GroovePlan(
        pattern=pattern, cymbal=cymbal, sam_cymbal=_available(sam, voices),
        ghosts=ghosts,
        follow_riff=(subgenre == "progressive" and energy is not GrooveEnergy.VERSE),
        spread=spread, drag=_DOOM_DRAG if subgenre == "doom" else 0.0)


# --------------------------------------------------------------------------- #
# The tala skeleton: vibhag windows + the phrase (A-A-A-B) unit. Pure.         #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _Vibhag:
    """One vibhag window within the cycle. Internal, already-valid."""
    start: float   # beat offset within the cycle
    length: float
    kind: str      # "sam" | "tali" | "khali"


def _vibhags(arr: Arrangement) -> list[_Vibhag]:
    """The tala's vibhag windows — every vibhag start is a sam/tali/khali mark."""
    marks = [(a.beat, a.kind) for a in arr.accent_grid if a.kind != "beat"]
    ends = [beat for beat, _ in marks[1:]] + [float(arr.beats_per_bar)]
    return [_Vibhag(start=beat, length=end - beat, kind=kind)
            for (beat, kind), end in zip(marks, ends)]


def _phrase_cycles(cycle: int) -> int:
    """Tala cycles per phrase — the A-A-A-B unit (≈ four bars of 4/4): a 16-beat
    Teentaal cycle IS a phrase; short cycles (Keherwa 8, Rupak 7) group up."""
    n = 1
    while n * cycle < 12:
        n += 1
    return n


# --------------------------------------------------------------------------- #
# One section's hits: tiled pattern, tala accents, variation, fills. Pure.     #
# --------------------------------------------------------------------------- #

def _one_vibhag(origin: float, vib: _Vibhag, plan: GroovePlan,
                voices: set[str], bar: int = 0) -> list[DrumHit]:
    """One vibhag of the plan's pattern, with the tala written into the dynamics:
    the tali cymbal leans in (bell when riding), the khali vibhag sits back. `bar` rotates
    the ghost pockets so consecutive bars are not identical."""
    local = PATTERNS[plan.pattern](vib.length, plan.cymbal)
    if plan.ghosts and vib.kind != "khali":
        backs = {h.pos for h in local if h.drum == "snare" and h.vel >= 100}
        local += [g for g in ghost_snares(vib.length, bar)     # never crowd a backbeat
                  if g.pos not in backs and round(g.pos + 0.25, 4) not in backs]
    out: list[DrumHit] = []
    for hit in local:
        drum, vel = hit.drum, hit.vel
        if vib.kind == "khali":
            vel -= _KHALI_DIP
        elif vib.kind == "tali" and hit.pos == 0.0 and drum == plan.cymbal:
            if drum in ("ride", "bell") and "bell" in voices:
                drum, vel = "bell", VEL_BELL
            else:
                vel += _TALI_BUMP
        drag = plan.drag if (drum == "snare" and vel >= 100) else 0.0
        out.append(DrumHit(drum=drum, start=round(origin + hit.pos + drag, 4),
                           vel=max(1, min(127, vel))))
    return out


def _sam_accent(hits: list[DrumHit], at: float, plan: GroovePlan,
                vel: int) -> list[DrumHit]:
    """Land the sam: swap the pattern's cymbal at the downbeat for the accent
    cymbal, with a kick under it (a fill always resolves INTO a crash + kick)."""
    kept = [h for h in hits if not (h.start == at and h.drum == plan.cymbal)]
    kept.append(DrumHit(drum=plan.sam_cymbal, start=at, vel=vel))
    kept.append(DrumHit(drum="kick", start=at, vel=VEL_KICK))
    return kept


def _push_last_backbeat(hits: list[DrumHit], end: float) -> None:
    """The drummer leans on the phrase's last backbeat to signal the loop point."""
    last = max((h for h in hits if h.drum == "snare" and h.vel >= 100 and h.start < end),
               key=lambda h: h.start, default=None)
    if last is not None:
        last.vel = min(127, last.vel + _TURNAROUND_BUMP)


_FILL_HANDS: Final = ("snare", "hhat", "ohat", "ride", "bell", "china", "crash",
                      "tom_hi", "tom_mid", "tom_lo")


def _carve_fill(hits: list[DrumHit], zone_start: float, zone_end: float,
                toms: list[str], *, vel_hi: int = 124) -> list[DrumHit]:
    """Carve a fill zone: the HANDS leave the pattern for the crescendo snare→tom
    run; the kick carpet underneath stays (the double-kick fill is the metal one)."""
    kept = [h for h in hits
            if not (zone_start <= h.start < zone_end and h.drum in _FILL_HANDS)]
    kept += [DrumHit(drum=f.drum, start=round(zone_start + f.pos, 4), vel=f.vel)
             for f in tom_run(zone_end - zone_start, toms, vel_hi=vel_hi)]
    return kept


def _wind_up(hits: list[DrumHit], zone_start: float, plan: GroovePlan,
             voices: set[str]) -> list[DrumHit]:
    """Thin the cymbal in the half-beat before a fill (open the hat when there is
    one) — a fill out of an unbroken cymbal line is a programming tell."""
    kept = [h for h in hits
            if not (zone_start - 0.5 <= h.start < zone_start and h.drum == plan.cymbal)]
    if "ohat" in voices:
        kept.append(DrumHit(drum="ohat", start=round(zone_start - 0.5, 4),
                            vel=VEL_CYM_ACCENT))
    return kept


def _riff_onbeats(rhythm: Layer | None, span: SectionSpan) -> set[float]:
    """The whole-beat onsets the riff hits in this section — the kick locks to these
    (the same on-beat rule the bass uses), so kick, bass and riff all land together."""
    if rhythm is None or not rhythm.notes:
        return set()
    return {n.start for n in rhythm.notes
            if span.start <= n.start < span.end and float(n.start).is_integer()}


def _riff_onsets(rhythm: Layer | None, span: SectionSpan) -> set[float]:
    """EVERY riff onset in the section, quantized to the 16th grid (prog follow)."""
    if rhythm is None or not rhythm.notes:
        return set()
    return {round(round(n.start * 4) / 4, 4) for n in rhythm.notes
            if span.start <= n.start < span.end}


def _riff_accents(rhythm: Layer | None, span: SectionSpan) -> set[float]:
    """16th-quantized onsets where the riff hits WEIGHT — a power chord or an open ring
    (>= `_RIFF_ACCENT_MIN_RING` beats, not palm-muted) — the riff's own accents, NOT the
    chug ground. The kick locks to these (every subgenre, not just prog) so the kit punches
    WITH the riff's power chords, not only on the tala's sam (Sujit: grooves should feel
    derived from the riff)."""
    if rhythm is None or not rhythm.notes:
        return set()
    accents: set[float] = set()
    for n in rhythm.notes:
        if not (span.start <= n.start < span.end):
            continue
        rings = n.dur >= _RIFF_ACCENT_MIN_RING and n.technique != "palm_mute"
        if n.chord or rings:
            accents.add(round(round(n.start * 4) / 4, 4))
    return accents


def _stop_hit_entrance(hits: list[DrumHit], rhythm: Layer | None, span: SectionSpan,
                       window: float, voices: set[str]) -> list[DrumHit]:
    """A riff that opens the entrance with 2-3 spaced accents gets matched STOP
    HITS — unison crash + kick (+ snare off the downbeat) on each riff onset, the
    groove proper starting from the next vibhag."""
    if rhythm is None or not rhythm.notes:
        return hits
    end = span.start + window
    onsets = sorted({round(n.start, 4) for n in rhythm.notes
                     if span.start <= n.start < end})
    if not 2 <= len(onsets) <= 3:
        return hits
    kept = [h for h in hits if not (span.start <= h.start < end)]
    crash = _available("crash", voices)
    for t in onsets:
        kept.append(DrumHit(drum=crash, start=t, vel=VEL_ENTRANCE))
        kept.append(DrumHit(drum="kick", start=t, vel=VEL_ENTRANCE))
        if t != span.start:
            kept.append(DrumHit(drum="snare", start=t, vel=VEL_SNARE))
    return kept


def _dedup(hits: list[DrumHit]) -> list[DrumHit]:
    """Collapse same-drum same-instant collisions, keeping the loudest stroke."""
    best: dict[tuple[str, float], DrumHit] = {}
    for h in hits:
        key = (h.drum, h.start)
        if key not in best or h.vel > best[key].vel:
            best[key] = h
    return sorted(best.values(), key=lambda h: (h.start, h.drum))


def _section_hits(arr: Arrangement, span: SectionSpan, rhythm: Layer | None,
                  energy: GrooveEnergy, *, entrance: bool, announce: bool = False,
                  fill_into: Optional[GrooveEnergy]) -> list[DrumHit]:
    """One section's groove: the plan's pattern tiled per vibhag with the tala's
    accents, A-A-A-B phrase turnarounds, a mid-section mini-fill, the kick locked
    to the riff (its on-beats AND its power-chord accents), and a crescendo seam fill when
    another kit section follows. `announce` marks a NEW riff/energy arriving after another
    kit section — its opening sam gets the full-force entrance crash."""
    voices = set(SUBGENRES[arr.subgenre]["drums"]["voices"])
    plan = _plan_for(span.section, arr.subgenre, energy, voices)
    cycle = int(arr.beats_per_bar)
    phrase = _phrase_cycles(cycle)
    vibs = _vibhags(arr)
    toms = [t for t in ("tom_hi", "tom_mid", "tom_lo") if t in voices] or ["snare"]

    hits: list[DrumHit] = []
    for bar in range(span.section.bars):
        base = span.start + bar * cycle
        bar_hits: list[DrumHit] = []
        for vib in vibs:
            bar_hits += _one_vibhag(base + vib.start, vib, plan, voices, bar)
        if bar % phrase == 0:              # a crash opens every phrase's sam...
            vel = VEL_ENTRANCE if ((entrance or announce) and bar == 0) else VEL_CRASH
            bar_hits = _sam_accent(bar_hits, round(base, 4), plan, vel)
        else:                              # ...the other sams just get the kick under
            bar_hits.append(DrumHit(drum="kick", start=round(base, 4), vel=VEL_KICK))
        if (bar + 1) % phrase == 0:        # the A-A-A-B turnaround: ONE kick pair in
            bar_hits += [DrumHit(drum="kick", start=round(base + cycle + off, 4),
                                 vel=VEL_KICK_SOFT) for off in TURNAROUND_KICKS]
            _push_last_backbeat(bar_hits, base + cycle)
        hits += bar_hits
        if (bar + 1) % (2 * phrase) == 0 and bar + 1 < span.section.bars:
            hits = _carve_fill(hits, round(base + cycle - _MINI_FILL_BEATS, 4),
                               round(base + cycle, 4), toms, vel_hi=112)

    # the kick locks to the riff: on-beats for everyone, the riff's power-chord ACCENTS
    # wherever they land (so the kit punches with the riff, not only the sam), every onset for prog
    riff_kicks = {(t, VEL_KICK) for t in _riff_onbeats(rhythm, span)}
    riff_kicks |= {(t, VEL_KICK) for t in _riff_accents(rhythm, span)}
    if plan.follow_riff:
        riff_kicks |= {(t, VEL_KICK_SOFT) for t in _riff_onsets(rhythm, span)}
    hits += [DrumHit(drum="kick", start=round(t, 4), vel=v) for t, v in riff_kicks]

    if fill_into is not None:              # the seam fill — bigger into a climax
        beats = _BIG_FILL_BEATS if fill_into is GrooveEnergy.CLIMAX else _SEAM_FILL_BEATS
        beats = min(beats, vibs[-1].length)
        zone = round(span.end - beats, 4)
        hits = _wind_up(hits, zone, plan, voices)
        hits = _carve_fill(hits, zone, span.end, toms)
    if entrance:
        hits = _stop_hit_entrance(hits, rhythm, span, vibs[0].length, voices)

    return [DrumHit(drum=h.drum, start=h.start,
                    vel=humanized(h.vel, h.start, h.drum, plan.spread))
            for h in _dedup(hits)]


def groove_layer(arr: Arrangement, rhythm: Layer | None) -> Layer | None:
    """The metal-kit drums layer for the whole piece. Deterministic, no LLM.

    Fills the drums for each section that lists `drums`, choosing the groove from
    the section's energy (kind + gat form_role: an alaap gets no kit, the antara
    rides half-time). The kick locks to `rhythm` (the riff) where present; fills
    mark the phrase and section boundaries; when the kit ENTERS after a kit-less
    section it plays a pickup snare roll into an everything-at-127 downbeat (or
    matched stop hits when the riff opens with spaced accents). Returns None when
    no section uses the kit.
    """
    spans = section_spans(arr)
    energies = [_energy_for(s.section) if _DRUMS_ROLE in s.section.layers else None
                for s in spans]
    hits: list[DrumHit] = []
    prev_kit: Optional[int] = None            # index of the previous kit section (skips alaap gaps)
    for i, span in enumerate(spans):
        if energies[i] is None:
            continue
        entrance = i > 0 and energies[i - 1] is None
        # a NEW riff/energy arriving right after another kit section — announce it with a crash
        announce = (not entrance and prev_kit is not None
                    and (energies[i] != energies[prev_kit]
                         or span.section.riff_slot != spans[prev_kit].section.riff_slot))
        fill_into = energies[i + 1] if i + 1 < len(spans) else None
        hits += _section_hits(arr, span, rhythm, energies[i],
                              entrance=entrance, announce=announce, fill_into=fill_into)
        prev_kit = i
        if entrance:                       # the pickup roll swells out of the silence
            hits += [DrumHit(drum=p.drum,
                             start=round(span.start - _PICKUP_BEATS + p.pos, 4),
                             vel=p.vel) for p in pickup_roll(_PICKUP_BEATS)]

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
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"


def _groove_demo_arrangement() -> Arrangement:
    """A two-section chart (RIFF -> BREAKDOWN) so the confirmation hears the groove
    CHANGE (drive -> half-time) and the tom FILL at the seam. Doom/Darbari, slow
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
