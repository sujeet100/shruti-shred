"""
Composition metrics — the FACTS the Producer reasons over. Pure (no LLM, no I/O).

The pattern: CODE MEASURES, the LLM EVALUATES. The Producer judges whether a piece works
as a song, but many of those judgments have a measurable backbone — you do not need a
language model to count how many voices play in each section, or to notice that the energy
never rises, or that the lead merely reuses the riff's notes. So code computes the numbers
and hands them to the Producer as grounding (exactly as `pakad_presence` grounds Rasik);
the Producer spends its judgment on what the numbers MEAN, not on deriving them.

Each metric maps to Producer rubric criteria:
  * the per-section ENERGY curve      -> dynamics, climax, balance
  * peak / resolution / flatness      -> climax, dynamics
  * motif_share                       -> motif (developed vs abandoned vs never-varied)
  * lead_riff_overlap                 -> independence (a lead that just doubles the riff)
  * register_overlaps                 -> balance (voices colliding in one octave)
  * always_on_fraction                -> balance (no arrangement space — everyone always on)

These are DELIBERATELY facts, not verdicts: a high motif_share is not "bad", it is a
number the Producer interprets (too high = no development, too low = motif dropped).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from crew.contracts import Arrangement, Composition, Layer
from crew.generators import section_spans

# Voices whose octave ranges we check for collisions — the melodic/rhythmic parts. The
# drone is a fixed pedal and the percussion carries no pitch, so neither is a "collision".
_PITCHED_MELODIC: Final = ("lead", "rhythm", "bass")

# Energy barely moves across the piece if the peak is within this fraction of the trough —
# a "flat" arc, the Producer's cue that nothing builds.
_FLAT_RATIO: Final[float] = 0.15


@dataclass(frozen=True)
class SectionEnergy:
    """One section's measured intensity — the row of the dynamics curve."""
    kind: str
    active_voices: int          # distinct roles sounding in this section (perc included)
    notes_per_beat: float       # pitched-note density over the section window
    mean_vel: float             # average velocity of the pitched notes (0 if none)
    energy: float               # composite index = active_voices * mean_vel / 127


@dataclass(frozen=True)
class ProducerMetrics:
    """The computed facts handed to the Producer. Internal, already-valid — a dataclass,
    not a boundary contract."""
    energy: list[SectionEnergy]
    peak_index: int             # section index of maximum energy (-1 if the piece is empty)
    resolves: bool              # energy falls after the peak (a resolution, not a hard stop)
    is_flat: bool               # energy barely varies across sections (no arc)
    motif_share: float          # fraction of lead notes whose swara is in the motif set
    lead_riff_overlap: float    # fraction of the lead's swaras that also appear in the riff
    register_overlaps: list[tuple[str, str]]  # melodic voice pairs sharing an octave band
    always_on_fraction: float   # fraction of sections where EVERY present voice plays


# --------------------------------------------------------------------------- #
# Small pure helpers over the Composition.                                     #
# --------------------------------------------------------------------------- #

def _layer_active(layer: Layer, start: float, end: float) -> bool:
    """Does any of a layer's events (notes OR hits) SOUND during [start, end)? Uses interval
    overlap, not just onset — a drone note that begins at beat 0 and sustains is still active
    in every later section it covers."""
    for e in (layer.notes or []) + (layer.hits or []):
        if e.start < end and e.start + e.dur > start:
            return True
    return False


def _active_roles(comp: Composition, start: float, end: float) -> set[str]:
    """The distinct voice ROLES sounding in [start, end) — deduped, so a double-tracked
    rhythm guitar (two layers, one role) counts once."""
    return {ly.role for ly in comp.layers if _layer_active(ly, start, end)}


def _roles_present(comp: Composition) -> set[str]:
    """Every voice role that carries at least one event somewhere in the piece."""
    return {ly.role for ly in comp.layers if ly.notes or ly.hits}


def _pitched_notes_in(comp: Composition, start: float, end: float) -> list:
    """Every pitched note (any melodic voice) whose onset lands in [start, end)."""
    return [n for ly in comp.layers for n in (ly.notes or []) if start <= n.start < end]


def _role_swaras(comp: Composition, role: str) -> list[str]:
    """All swaras of a role's notes in time order (across layers — e.g. both rhythm tracks)."""
    notes = [n for ly in comp.layers if ly.role == role for n in (ly.notes or [])]
    return [n.swara for n in sorted(notes, key=lambda x: x.start)]


def _role_oct_range(comp: Composition, role: str) -> tuple[int, int] | None:
    """The (min, max) octave a role occupies, or None if it has no notes."""
    octs = [n.oct for ly in comp.layers if ly.role == role for n in (ly.notes or [])]
    return (min(octs), max(octs)) if octs else None


# --------------------------------------------------------------------------- #
# The metric computations.                                                     #
# --------------------------------------------------------------------------- #

def _section_energy(comp: Composition, arr: Arrangement) -> list[SectionEnergy]:
    """The dynamics curve — one row per section, measured from the realized voices."""
    rows: list[SectionEnergy] = []
    for span in section_spans(arr):
        active = len(_active_roles(comp, span.start, span.end))
        pitched = _pitched_notes_in(comp, span.start, span.end)
        length = span.length or 1.0
        density = round(len(pitched) / length, 3)
        mean_vel = round(sum(n.vel for n in pitched) / len(pitched), 1) if pitched else 0.0
        energy = round(active * mean_vel / 127, 3)
        rows.append(SectionEnergy(kind=span.section.kind.value, active_voices=active,
                                  notes_per_beat=density, mean_vel=mean_vel, energy=energy))
    return rows


def _peak_and_resolution(energy: list[SectionEnergy]) -> tuple[int, bool, bool]:
    """(peak index, whether it resolves after, whether the whole arc is flat)."""
    if not energy:
        return -1, False, False
    values = [row.energy for row in energy]
    peak = max(range(len(values)), key=lambda i: values[i])
    resolves = peak < len(values) - 1 and values[-1] < values[peak]
    hi, lo = max(values), min(values)
    is_flat = hi <= 0 or (hi - lo) <= _FLAT_RATIO * hi
    return peak, resolves, is_flat


def _motif_share(comp: Composition, arr: Arrangement) -> float:
    """Fraction of the LEAD's notes whose swara is one of the motif's swaras. High means
    the lead never leaves the motif (no development); low means it was abandoned."""
    lead = _role_swaras(comp, "lead")
    if not lead:
        return 0.0
    motif = set(arr.motif)
    return round(sum(1 for sw in lead if sw in motif) / len(lead), 3)


def _lead_riff_overlap(comp: Composition) -> float:
    """Fraction of the lead's DISTINCT swaras that also appear in the riff — a proxy for
    the lead merely doubling the riff (low independence). 0 when either voice is absent."""
    lead = set(_role_swaras(comp, "lead"))
    riff = set(_role_swaras(comp, "rhythm"))
    if not lead or not riff:
        return 0.0
    return round(len(lead & riff) / len(lead), 3)


def _register_overlaps(comp: Composition) -> list[tuple[str, str]]:
    """Melodic voice pairs whose octave ranges intersect — a register collision (e.g. the
    lead sitting in the rhythm's octave). A bass/rhythm overlap at the low end is normal
    metal craft; the caller (the prompt) says so, so we still report it plainly."""
    ranges = {role: r for role in _PITCHED_MELODIC if (r := _role_oct_range(comp, role))}
    roles = sorted(ranges)
    overlaps: list[tuple[str, str]] = []
    for i, a in enumerate(roles):
        for b in roles[i + 1:]:
            (a_lo, a_hi), (b_lo, b_hi) = ranges[a], ranges[b]
            if a_lo <= b_hi and b_lo <= a_hi:      # the ranges intersect
                overlaps.append((a, b))
    return overlaps


def _always_on_fraction(energy: list[SectionEnergy], comp: Composition) -> float:
    """Fraction of sections in which EVERY voice present in the piece is playing — a high
    value means no arrangement space (everyone on, all the time)."""
    if not energy:
        return 0.0
    total_roles = len(_roles_present(comp))
    if total_roles == 0:
        return 0.0
    full = sum(1 for row in energy if row.active_voices >= total_roles)
    return round(full / len(energy), 3)


def composition_metrics(comp: Composition, arr: Arrangement) -> ProducerMetrics:
    """Measure the composition against its chart — the facts the Producer judges. Pure."""
    energy = _section_energy(comp, arr)
    peak, resolves, is_flat = _peak_and_resolution(energy)
    return ProducerMetrics(
        energy=energy,
        peak_index=peak,
        resolves=resolves,
        is_flat=is_flat,
        motif_share=_motif_share(comp, arr),
        lead_riff_overlap=_lead_riff_overlap(comp),
        register_overlaps=_register_overlaps(comp),
        always_on_fraction=_always_on_fraction(energy, comp))


# --------------------------------------------------------------------------- #
# Facts -> prompt text. The Producer reads these numbers and JUDGES them.       #
# --------------------------------------------------------------------------- #

def render_metrics(metrics: ProducerMetrics) -> str:
    """Render the computed facts as a compact grounding block for the Producer prompt."""
    curve = "  ".join(f"{r.kind}:{r.energy:g}" for r in metrics.energy) or "(no sections)"
    lines = [
        f"  dynamics curve (energy per section): {curve}",
    ]
    if metrics.energy:
        peak_kind = metrics.energy[metrics.peak_index].kind
        arc = "FLAT — energy barely moves across the piece" if metrics.is_flat else (
            f"peaks at section {metrics.peak_index + 1} ({peak_kind}); "
            + ("resolves afterwards" if metrics.resolves else "does NOT resolve after the peak"))
        lines.append(f"  arc: {arc}")
        lines.append("  active voices per section: "
                     + " ".join(f"{r.kind}={r.active_voices}" for r in metrics.energy))
    lines.append(f"  motif_share (lead notes drawn from the motif): {metrics.motif_share:.0%}")
    lines.append(f"  lead/riff overlap (lead swaras also in the riff): {metrics.lead_riff_overlap:.0%}")
    lines.append(f"  everyone-playing sections: {metrics.always_on_fraction:.0%}")
    if metrics.register_overlaps:
        pairs = ", ".join(f"{a}+{b}" for a, b in metrics.register_overlaps)
        lines.append(f"  register overlaps (voices sharing an octave band): {pairs} "
                     f"(bass+rhythm at the low end is normal)")
    else:
        lines.append("  register overlaps: none — the voices sit in distinct octaves")
    return "\n".join(lines)
