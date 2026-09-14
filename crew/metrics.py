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
  * per-section ornament_rate         -> climax (an expressive peak), idiom cross-check
  * motif_share                       -> motif (developed vs abandoned vs never-varied)
  * motif_recurrence                  -> repetition, motif (is the theme brought back?)
  * section_variety                   -> repetition (through-composed vs recurring sections)
  * riff_recurrence / riff_variety    -> hook, repetition, structure (does the main riff RETURN?)
  * lead_riff_overlap                 -> independence (a lead that just doubles the riff)
  * bass_riff_overlap                 -> independence (a bass that just doubles the riff)
  * drums_tabla_overlap               -> independence (kit and tabla playing in lockstep)
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
_RHYTHM_ROLE: Final = "rhythm"

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
    ornament_rate: float        # fraction of the section's pitched notes carrying a kan/meend
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
    motif_recurrence: float     # fraction of sections whose melody states the motif (theme return)
    section_variety: float      # distinct section kinds / total (1.0 = through-composed, low = repeats)
    riff_recurrence: float      # fraction of rhythm sections that REPLAY a riff (the hook returning)
    riff_variety: float         # distinct riffs / rhythm sections (1.0 = every riff unique, low = reuse)
    riff_slots: list[tuple[str, int]]  # (slot, how many rhythm sections play it), first-seen order
    lead_riff_overlap: float    # fraction of the lead's swaras that also appear in the riff
    bass_riff_overlap: float    # fraction of the bass's swaras that also appear in the riff
    drums_tabla_overlap: float  # fraction of tabla hits that land on a kit hit (lockstep percussion)
    register_overlaps: list[tuple[str, str]]  # melodic voice pairs sharing an octave band
    always_on_fraction: float   # fraction of sections where EVERY present voice plays
    # PERFORMANCE — how the score behaves when musicians PLAY it, as opposed to how it reads.
    # No agent hears audio, so a piece can be compositionally excellent and still arrive as a
    # string of clicks in dead air. `verify_riff` polices these per CYCLE; these are the
    # piece-level views it cannot see.
    rhythm_ring_share: float    # share of the rhythm guitar's sounding time in OPEN notes >= 1 beat
    rhythm_chug_share: float    # share of its notes marked palm_mute (the chug ground)
    rhythm_silence_share: float # share of the rhythm's span with nothing sounding (hollowness)
    flat_chug_runs: int         # runs of 4+ chugs at ONE velocity (the programmed tell)
    accompaniment_grinds: int   # sustained accompaniment tones clashing with a settled melody note


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


def _role_swaras_in(comp: Composition, role: str, start: float, end: float) -> list[str]:
    """A role's swaras whose onset lands in [start, end), in time order."""
    notes = [n for ly in comp.layers if ly.role == role
             for n in (ly.notes or []) if start <= n.start < end]
    return [n.swara for n in sorted(notes, key=lambda x: x.start)]


def _hit_onsets(comp: Composition, role: str) -> set[float]:
    """The distinct onset beats of a percussion role's hits."""
    return {round(h.start, 4) for ly in comp.layers if ly.role == role for h in (ly.hits or [])}


def _contains(sequence: list[str], phrase: list[str]) -> bool:
    """True iff `phrase` occurs as a contiguous run inside `sequence` (octave-agnostic).
    (Reimplemented here rather than imported from rasik.py, which pulls in crewai — this
    module stays LLM-free.)"""
    n = len(phrase)
    if not phrase or n > len(sequence):
        return False
    return any(sequence[i:i + n] == phrase for i in range(len(sequence) - n + 1))


def _overlap_fraction(subject: set[str], reference: set[str]) -> float:
    """Fraction of `subject`'s members that also appear in `reference` (0 if either empty)."""
    if not subject or not reference:
        return 0.0
    return round(len(subject & reference) / len(subject), 3)


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
        ornamented = sum(1 for n in pitched if n.grace or n.meend_swara)
        ornament_rate = round(ornamented / len(pitched), 3) if pitched else 0.0
        energy = round(active * mean_vel / 127, 3)
        rows.append(SectionEnergy(kind=span.section.kind.value, active_voices=active,
                                  notes_per_beat=density, mean_vel=mean_vel,
                                  ornament_rate=ornament_rate, energy=energy))
    return rows


def _motif_recurrence(comp: Composition, arr: Arrangement) -> float:
    """Fraction of SECTIONS whose lead or riff states the motif as a contiguous run — the
    theme being brought back (reinforcement), the flip side of motif_share. Low means the
    motif is stated once and never returns; high means it recurs as a hook."""
    spans = section_spans(arr)
    if not spans:
        return 0.0
    hits = sum(1 for span in spans
               if _contains(_role_swaras_in(comp, "lead", span.start, span.end), arr.motif)
               or _contains(_role_swaras_in(comp, "rhythm", span.start, span.end), arr.motif))
    return round(hits / len(spans), 3)


def _section_variety(arr: Arrangement) -> float:
    """Distinct section KINDS over total sections. 1.0 = every section a different kind
    (through-composed, little structural repetition); low = kinds recur (verse/chorus-like)."""
    kinds = [s.kind.value for s in arr.sections]
    return round(len(set(kinds)) / len(kinds), 3) if kinds else 0.0


def _riff_slots(arr: Arrangement) -> list[tuple[str, int]]:
    """(slot, count) per distinct riff slot over the rhythm-active sections, first-seen order.

    The slot resolution mirrors `crew/riff._slot_for` (riff_slot, else the kind), reimplemented
    here so this module stays LLM-free — riff.py pulls in crewai."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for s in arr.sections:
        if _RHYTHM_ROLE not in s.layers:
            continue
        slot = s.riff_slot or s.kind.value
        if slot not in counts:
            counts[slot] = 0
            order.append(slot)
        counts[slot] += 1
    return [(slot, counts[slot]) for slot in order]


def _riff_form(arr: Arrangement) -> tuple[float, float, list[tuple[str, int]]]:
    """(recurrence, variety, slots). recurrence = the fraction of rhythm sections that REPLAY
    an already-heard riff (0 = nothing returns; high = a hook keeps coming back). variety =
    distinct riffs / rhythm sections (1.0 = every rhythm section its own riff, no repetition)."""
    slots = _riff_slots(arr)
    total = sum(count for _, count in slots)
    distinct = len(slots)
    if total == 0:
        return 0.0, 0.0, slots
    recurrence = round((total - distinct) / total, 3)
    variety = round(distinct / total, 3)
    return recurrence, variety, slots


def _drums_tabla_overlap(comp: Composition) -> float:
    """Fraction of tabla hits that land on the same beat as a kit hit — 1.0 means the two
    percussion voices move in lockstep (no independence). 0 when there is no tabla."""
    tabla = _hit_onsets(comp, "tabla")
    if not tabla:
        return 0.0
    drums = _hit_onsets(comp, "drums")
    return round(len(tabla & drums) / len(tabla), 3)


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
    return _overlap_fraction(set(_role_swaras(comp, "lead")), set(_role_swaras(comp, "rhythm")))


def _bass_riff_overlap(comp: Composition) -> float:
    """Fraction of the bass's DISTINCT swaras that also appear in the riff. A metal bass
    SHOULD track the riff's roots, so a high value here is often fine — the Producer judges
    whether it does anything of its own; code just supplies the number."""
    return _overlap_fraction(set(_role_swaras(comp, "bass")), set(_role_swaras(comp, "rhythm")))


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


# --------------------------------------------------------------------------- #
# Performance metrics — what the score DOES, not what it says. The critics read #
# symbols and hear nothing, so these are the numbers that stand in for ears.     #
# --------------------------------------------------------------------------- #

_RING_MIN_DUR: Final[float] = 1.0      # an open note this long actually rings
_FLAT_RUN_MIN: Final[int] = 4          # chugs in a row before one velocity reads as programmed


def _rhythm_notes(comp: Composition) -> list:
    """The PRIMARY rhythm take in time order — the double is the same performance."""
    takes = [ly for ly in comp.layers if ly.role == "rhythm" and ly.notes]
    layer = next((ly for ly in takes if ly.detune_cents is None), takes[0] if takes else None)
    return sorted(layer.notes, key=lambda n: n.start) if layer else []


def _ring_share(notes: list) -> float:
    """Share of sounding time in OPEN notes long enough to ring. A palm-muted note damps,
    so it can never ring however long it is written."""
    total = sum(n.dur for n in notes)
    if not total:
        return 0.0
    ringing = sum(n.dur for n in notes
                  if n.dur >= _RING_MIN_DUR and n.technique != "palm_mute")
    return round(ringing / total, 3)


def _silence_share(notes: list) -> float:
    """Share of the rhythm guitar's own span with nothing sounding — the piece's hollowness
    as written (the renderer can only add silence, never remove it)."""
    if not notes:
        return 0.0
    span = max(n.start + n.dur for n in notes) - notes[0].start
    if span <= 0:
        return 0.0
    sounding, edge = 0.0, notes[0].start
    for note in notes:                       # union of intervals: chords must not double-count
        start, end = max(note.start, edge), note.start + note.dur
        if end > start:
            sounding += end - start
            edge = end
    return round(max(0.0, 1 - sounding / span), 3)


def _flat_chug_runs(notes: list) -> int:
    """Runs of consecutive palm-muted notes at a SINGLE velocity — a picking hand accents."""
    runs, current = 0, []
    for note in notes + [None]:
        if note is not None and note.technique == "palm_mute":
            current.append(note)
            continue
        if len(current) >= _FLAT_RUN_MIN and len({n.vel for n in current}) == 1:
            runs += 1
        current = []
    return runs


def _accompaniment_grinds(comp: Composition, arr: Arrangement) -> int:
    """Sustained accompaniment tones clashing with what the melody settles on — the cluster
    assembled out of individually legal choices. Counted, never judged: whether it matters
    here is the Producer's call."""
    from crew.harmonic_guide import avoided_at, harmonic_guide
    leads = [ly for ly in comp.layers if ly.role == "lead"]
    guide = harmonic_guide(leads, arr)
    sustaining = [ly for ly in comp.layers
                  if ly.role in ("clean", "orch_strings", "orch_choir") and ly.notes]
    return sum(1 for ly in sustaining for n in ly.notes
               if n.dur >= _RING_MIN_DUR and n.swara in avoided_at(guide, n.start))


def composition_metrics(comp: Composition, arr: Arrangement) -> ProducerMetrics:
    """Measure the composition against its chart — the facts the Producer judges. Pure."""
    energy = _section_energy(comp, arr)
    peak, resolves, is_flat = _peak_and_resolution(energy)
    riff_recurrence, riff_variety, riff_slots = _riff_form(arr)
    rhythm = _rhythm_notes(comp)
    return ProducerMetrics(
        energy=energy,
        peak_index=peak,
        resolves=resolves,
        is_flat=is_flat,
        motif_share=_motif_share(comp, arr),
        motif_recurrence=_motif_recurrence(comp, arr),
        section_variety=_section_variety(arr),
        riff_recurrence=riff_recurrence,
        riff_variety=riff_variety,
        riff_slots=riff_slots,
        lead_riff_overlap=_lead_riff_overlap(comp),
        bass_riff_overlap=_bass_riff_overlap(comp),
        drums_tabla_overlap=_drums_tabla_overlap(comp),
        register_overlaps=_register_overlaps(comp),
        always_on_fraction=_always_on_fraction(energy, comp),
        rhythm_ring_share=_ring_share(rhythm),
        rhythm_chug_share=round(sum(1 for n in rhythm if n.technique == "palm_mute")
                                / max(1, len(rhythm)), 3),
        rhythm_silence_share=_silence_share(rhythm),
        flat_chug_runs=_flat_chug_runs(rhythm),
        accompaniment_grinds=_accompaniment_grinds(comp, arr))


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
        lines.append("  ornament rate per section: "
                     + " ".join(f"{r.kind}={r.ornament_rate:.0%}" for r in metrics.energy))
    lines.append(f"  motif_share (lead notes drawn from the motif): {metrics.motif_share:.0%}")
    lines.append(f"  motif_recurrence (sections that restate the motif): {metrics.motif_recurrence:.0%}")
    lines.append(f"  section_variety (distinct kinds / total; high = through-composed, "
                 f"little repetition): {metrics.section_variety:.0%}")
    if metrics.riff_slots:
        layout = " ".join(f"{slot}x{n}" for slot, n in metrics.riff_slots)
        lines.append(f"  riff form ({len(metrics.riff_slots)} distinct riff(s), reuse shown): {layout}")
        lines.append(f"  riff_recurrence (rhythm sections replaying a riff — the hook returning): "
                     f"{metrics.riff_recurrence:.0%}")
        lines.append(f"  riff_variety (distinct riffs / rhythm sections; high = little riff repetition): "
                     f"{metrics.riff_variety:.0%}")
    lines.append(f"  lead/riff overlap (lead swaras also in the riff): {metrics.lead_riff_overlap:.0%}")
    lines.append(f"  bass/riff overlap (bass tracking the riff — often fine): {metrics.bass_riff_overlap:.0%}")
    if metrics.drums_tabla_overlap:
        lines.append(f"  drums/tabla lockstep (tabla hits on a kit hit): {metrics.drums_tabla_overlap:.0%}")
    lines.append(f"  everyone-playing sections: {metrics.always_on_fraction:.0%}")
    if metrics.register_overlaps:
        pairs = ", ".join(f"{a}+{b}" for a, b in metrics.register_overlaps)
        lines.append(f"  register overlaps (voices sharing an octave band): {pairs} "
                     f"(bass+rhythm at the low end is normal)")
    else:
        lines.append("  register overlaps: none — the voices sit in distinct octaves")
    lines.append("  HOW IT PLAYS (nobody in this pipeline hears audio — these stand in for ears):")
    lines.append(f"    rhythm guitar: {metrics.rhythm_chug_share:.0%} of its notes are chugs, "
                 f"{metrics.rhythm_ring_share:.0%} of its sounding time RINGS open, and "
                 f"{metrics.rhythm_silence_share:.0%} of its span is silent")
    lines.append(f"    flat chug runs (4+ chugs at one velocity — a machine, not a hand): "
                 f"{metrics.flat_chug_runs}")
    lines.append(f"    sustained accompaniment tones clashing with a settled melody note: "
                 f"{metrics.accompaniment_grinds}")
    return "\n".join(lines)
