"""
The ENERGY arc + layer-by-function (step 3 of the gat-led campaign) — a deterministic,
post-assembly MIX pass over the finished voices.

No agent hears audio, so DYNAMICS (does the song build? does the foreground cut through the
wall?) can never be caught by the critic loop — they are code, applied here. Two jobs, both
decided PER SECTION and both driven by step 1's `form_role`, so the whole campaign hangs off one
spine:

  1. ENERGY ARC — scale every voice by the section's energy so the piece BUILDS: a soft intro, a
     rising mukhada/manjha/antara, a peak at the long taan, a strong final section, a settled
     outro — instead of one flat level. Energy is derived from `form_role` + position (universal:
     the composer guardrail requires a form_role on every section).

  2. LAYER-BY-FUNCTION — the section's FOREGROUND voice dominates and the others make room. In
     particular the double-tracked rhythm guitar DUCKS under a lead-foreground section so the
     sitar/gat cuts through (the wall was burying the lead — Sujit's note). The drone is exempt:
     it is a single note spanning the whole piece (a constant tonal anchor), not a voice that
     swells section to section.

Gated on `form_role`: a section without a declared gat form is left at its authored levels
(gain 1.0), so a form-less demo/fixture — and the entire existing test-suite — is unchanged,
exactly as the riff family gates. Pure: velocities in, velocities out; fully unit-tested.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Callable, Optional

from crew.contracts import Arrangement, Layer, Section
from crew.generators import section_spans

# Per-form-role target energy in [0, 1] — the arc's explicit spine. intro/outro sit low; the
# body rises; the long taan is the peak; a tihai/breakdown hits hard. Keyed by FormRole value.
_ENERGY: dict[str, float] = {
    "intro": 0.25,
    "mukhada": 0.60,
    "manjha": 0.62,
    "antara": 0.80,
    "taan_short": 0.72,
    "taan_long": 1.00,
    "breakdown": 0.88,
    "tihai": 0.92,
    "outro": 0.22,
}
_FINAL_FLOOR: float = 0.85   # the last section (unless an outro) lands strong — pairs with the riff `double`

# Energy -> velocity gain. A soft section sits at ~0.62 of its authored velocity, the peak a
# touch hotter than written — an audible dynamic swing without silencing the quiet sections.
_GAIN_FLOOR: float = 0.62
_GAIN_CEIL: float = 1.08

# Layer-by-function gains for a NON-foreground voice (the foreground itself is always 1.0):
# duck raised 0.55 -> 0.70 and the tabla bed 0.85 -> 0.95 (Sujit's live notes, 2026-07-16:
# "riff sounded quiet under the mukhada" / "tabla could be louder" — the old duck buried the
# chug, and the bed gain was shaving an already-quiet tabla).
_DUCK_RHYTHM_UNDER_LEAD: float = 0.70   # the riff makes room for the lead without vanishing
_LEAD_UNDER_RHYTHM: float = 0.90        # a background lead stays present but doesn't fight the riff
_BED: dict[str, float] = {"tabla": 0.95, "bass": 0.90, "drums": 0.90}  # support beds sit under
_BED_DEFAULT: float = 0.85

_DRONE_ROLE = "drone"


def _clamp_vel(v: float) -> int:
    return max(1, min(127, round(v)))


def section_energy(section: Section, *, is_final: bool) -> Optional[float]:
    """The section's target energy in [0, 1], or None when it declares no gat form (leave its
    levels untouched). The final non-outro section is floored high so the piece lands strong."""
    if section.form_role is None:
        return None
    energy = _ENERGY[section.form_role]
    if is_final and section.form_role != "outro":
        energy = max(energy, _FINAL_FLOOR)
    return energy


def _energy_gain(energy: float) -> float:
    return _GAIN_FLOOR + (_GAIN_CEIL - _GAIN_FLOOR) * energy


def _role_gain(role: str, foreground: str) -> float:
    """How loud a voice sits relative to the section's foreground — 'each layer one job'."""
    if role == foreground:
        return 1.0
    if role == "rhythm" and foreground == "lead":
        return _DUCK_RHYTHM_UNDER_LEAD
    if role == "lead":
        return _LEAD_UNDER_RHYTHM
    return _BED.get(role, _BED_DEFAULT)


def _gain_for(section: Section, role: str, *, is_final: bool) -> float:
    """The combined velocity gain for `role` in `section`: energy arc x layer balance. 1.0 when
    the section declares no gat form (untouched)."""
    energy = section_energy(section, is_final=is_final)
    if energy is None:
        return 1.0
    return _energy_gain(energy) * _role_gain(role, section.foreground)


def _balance_layer(layer: Layer, gain_at: Callable[[float, str], float]) -> Layer:
    """Scale a layer's note/hit velocities by the gain of the section each event falls in. The
    drone is returned unchanged (a constant anchor, not a section-by-section voice)."""
    if layer.role == _DRONE_ROLE:
        return layer
    if layer.notes:
        notes = [n.model_copy(update={"vel": _clamp_vel(n.vel * gain_at(n.start, layer.role))})
                 for n in layer.notes]
        return layer.model_copy(update={"notes": notes})
    if layer.hits:
        hits = [h.model_copy(update={"vel": _clamp_vel(h.vel * gain_at(h.start, layer.role))})
                for h in layer.hits]
        return layer.model_copy(update={"hits": hits})
    return layer


def apply_dynamics(layers: list[Layer], arr: Arrangement) -> list[Layer]:
    """Balance the assembled layers: scale each voice per section by the energy arc and its
    layer-by-function role. Pure — returns new layers, mutating nothing. A chart with no
    declared gat form comes back unchanged."""
    spans = section_spans(arr)
    starts = [s.start for s in spans]
    final_index = spans[-1].index if spans else None

    def gain_at(start: float, role: str) -> float:
        span = spans[max(0, bisect_right(starts, start) - 1)]   # the section this event sits in
        return _gain_for(span.section, role, is_final=(span.index == final_index))

    return [_balance_layer(layer, gain_at) for layer in layers]


# --- THE TAAN EXPOSURE — the band-drop window (Sujit's own Yaman fusion, 2026-07-16) --------
# Measured on his track: its most dramatic moments are the ones where rhythm/bass/drums vanish
# and the sitar plays exposed, the band slamming back in. Made structural: in the FINAL avartan
# of every long taan (the piece's peak), the metal band — rhythm (and its double), bass, kit —
# drops out: ONE stop hit on that avartan's sam (clamped to ring at most a beat), then true
# silence, while the sitar's taan (with its tihai), the drone, and the TABLA carry the cycle
# alone (sitar+tabla is the classic Hindustani exposure, and the theka keeps the tala audible so
# the re-entry sam is FELT). The band re-enters on the next section's downbeat, which the drums'
# band-entrance machinery already marks with a crash. Notes struck BEFORE the window keep their
# tails — a chord rings INTO the exposure, exactly like the guitar tails on Sujit's track.
_EXPOSED_ROLES: frozenset[str] = frozenset({"rhythm", "bass", "drums"})
_TAAN_LONG_ROLE: str = "taan_long"
_EXPOSURE_MIN_BARS: int = 2     # a 1-bar taan has no band statement to drop out FROM
_STOP_HIT_RING: float = 1.0     # the sam stop hit rings at most this long before the silence
_EPS: float = 1e-6


def taan_exposure_windows(arr: Arrangement) -> list[tuple[float, float]]:
    """The [start, end) beat windows where the band drops out: the FINAL avartan of every
    `taan_long` section of at least `_EXPOSURE_MIN_BARS` bars. Pure."""
    return [(span.end - arr.beats_per_bar, span.end)
            for span in section_spans(arr)
            if span.section.form_role == _TAAN_LONG_ROLE
            and span.section.bars >= _EXPOSURE_MIN_BARS]


def _exposure_keep(start: float, dur: float,
                   windows: list[tuple[float, float]]) -> tuple[bool, float]:
    """(keep, dur) for one event of an EXPOSED role. An event before a window keeps its tail
    (the ring-in); the event ON a window's sam is the stop hit (its ring clamped); anything
    later inside the window is dropped."""
    for a, b in windows:
        if a - _EPS <= start < b - _EPS:
            if start <= a + _EPS:
                return True, min(dur, _STOP_HIT_RING)
            return False, dur
    return True, dur


def apply_taan_exposure(layers: list[Layer], arr: Arrangement) -> list[Layer]:
    """Drop the metal band (rhythm, bass, drums) out of every long taan's final avartan — the
    exposure window — leaving the lead, drone and tabla to carry the peak alone. Pure —
    returns new layers, mutating nothing. A chart with no qualifying taan comes back unchanged."""
    windows = taan_exposure_windows(arr)
    if not windows:
        return layers
    exposed: list[Layer] = []
    for layer in layers:
        if layer.role not in _EXPOSED_ROLES:
            exposed.append(layer)
        elif layer.notes:
            notes = []
            for n in layer.notes:
                keep, dur = _exposure_keep(n.start, n.dur, windows)
                if keep:
                    notes.append(n if dur == n.dur else n.model_copy(update={"dur": dur}))
            exposed.append(layer.model_copy(update={"notes": notes}))
        elif layer.hits:
            hits = [h for h in layer.hits if _exposure_keep(h.start, h.dur, windows)[0]]
            exposed.append(layer.model_copy(update={"hits": hits}))
        else:
            exposed.append(layer)
    return exposed
