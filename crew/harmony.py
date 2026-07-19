"""
The HARMONY layer — a clean electric guitar realising each section's `HarmonyPlan`.

DESIGN.md "song-quality campaign" #1 + #2, built together because they are one feature:
the COMPOSERS make a harmony DECISION per section (the `HarmonyPlan` on the chart — an
LLM choice, argued in the Pandit/Riffsmith dialogue), and CODE realises it on a CLEAN
guitar voice — arpeggiated voicings built up the raga's OWN ladder, so every tone is
legal by construction. No new agent: "the LLM decides, code derives" — the same split
as the bass and the drums.

The three modes, ordered by how much harmonic motion they dare (Hindustani music is
MELODIC; Sa's gravity is the music, so motion is rationed, never free):
  * `drone`        — no motion: the tanpura dyad (Sa + the raga's companion), broken
                     gently. Alaap / climax territory.
  * `modal_pedal`  — the raga-metal DEFAULT: a Sa pedal under CHANGING colour tones
                     (the composers' `roots`, else vadi/samvadi), one colour per
                     avartan. Motion without ever leaving home.
  * `progression`  — a short per-avartan root cycle (chorus-like sections only, by the
                     composer guardrail), always resolving back to Sa. Roots are raga
                     swaras and voicings are raga-ladder stacks, so a Western V-I
                     simply cannot be spelled.

Texture follows the section: an alaap/intro gets a slow, spacious broken chord; a
metered section gets a flowing eighth-note arpeggio (up-down); the long taan gets HELD
pads (thin under the climax — the sitar owns that space); and the taan's final-avartan
band-drop silences the clean guitar with the rest of the band (`dynamics`).

Pure — no LLM, no I/O (the `main` sound check at the bottom is the one shell edge);
fully unit-tested in tests/test_harmony.py.

Sound check (NO LLM, no API cost — the three modes over a drone):
  uv run python -m crew.harmony   ->  out/harmony_demo.wav
"""

from __future__ import annotations

from typing import Final

from crew.contracts import Arrangement, HarmonyPlan, Layer, Note, Section
from crew.generators import VOICES, SectionSpan, section_spans
from raga import RAGAS, ascent_step, directional_varjya, drone_swaras, scale_step_up

_CLEAN_ROLE: Final = "clean"

_ARP_VEL: Final = 72               # gentle — a shimmer under the band, never a lead voice
_ARP_SUBDIV: Final = 0.5           # metered sections: a flowing eighth-note arpeggio
_ALAAP_SUBDIV: Final = 1.0         # alaap/intro/outro: slow, spacious broken chords
_SPACIOUS_KINDS: Final = frozenset({"alaap", "outro"})
_PAD_ROLE: Final = "taan_long"     # under the climax the clean guitar HOLDS, not runs


def _seat_ascending(swara: str, oct_delta: int, raga: str) -> tuple[str, int]:
    """Seat a voicing tone so an ARPEGGIO may rise into it: a descent-only swara
    (directional varjya — Bageshree's P) is lifted to the next swara enterable from
    below, exactly as `ascent_step` seats a bend's apex. Any other tone keeps its seat."""
    if directional_varjya(raga).get(swara) != "avaroha":
        return swara, oct_delta
    sw, od = ascent_step(swara, raga)
    return sw, oct_delta + od


def voicing(root: str, raga: str) -> list[tuple[str, int]]:
    """The clean guitar's voicing on `root`: root, the raga's own third above it
    (seated ascendable), and the octave root — an open, shimmering stack that is legal
    by construction (every tone from the raga's ladder) and safe to arpeggiate upward
    (no tone entered from its forbidden side). (swara, octave-delta) pairs."""
    third, third_oct = _seat_ascending(*scale_step_up(root, raga, 2), raga)
    return [(root, 0), (third, third_oct), (root, 1)]


def _pedal_colours(plan: HarmonyPlan, raga: str) -> list[str]:
    """The modal pedal's rotating colour tones: the composer's `roots` when given,
    else the raga's vadi and samvadi (its two gravitational tones) — deduplicated,
    seated ascendable, never Sa itself (Sa is the pedal)."""
    r = RAGAS[raga]
    tones = plan.roots or [r["vadi"], r["samvadi"]]
    seated = [_seat_ascending(t, 0, raga)[0] for t in tones]
    return list(dict.fromkeys(t for t in seated if t != "S")) or [r["vadi"]]


def bar_voicings(section: Section, raga: str) -> list[list[tuple[str, int]]]:
    """One voicing per avartan of the section, per its `HarmonyPlan` (None = the
    modal-pedal default). This is the TIME-VARYING harmony plan the old chart never
    had: which tones ring over each bar."""
    plan = section.harmony or HarmonyPlan()
    bars = section.bars
    if plan.mode == "drone":
        dyad = [(sw, 0) for sw in drone_swaras(raga)] + [("S", 1)]
        return [dyad] * bars
    if plan.mode == "progression" and plan.roots:
        # Stretch the root cycle evenly across the bars; the last root (Sa, by the
        # composer guardrail) lands on the final avartan — the cycle comes home.
        roots = [plan.roots[min(len(plan.roots) - 1, i * len(plan.roots) // bars)]
                 for i in range(bars)]
        return [voicing(r, raga) for r in roots]
    # modal_pedal (and a root-less progression degrades here): Sa pedal + one colour
    # tone per avartan, its raga-third above — home held, colour moving.
    colours = _pedal_colours(plan, raga)
    out: list[list[tuple[str, int]]] = []
    for bar in range(bars):
        colour = colours[bar % len(colours)]
        third, third_oct = _seat_ascending(*scale_step_up(colour, raga, 2), raga)
        out.append([("S", 0), (colour, 0), (third, third_oct)])
    return out


def arpeggio(tones: list[tuple[str, int]], *, start: float, beats: float, register: int,
             subdiv: float, vel: int = _ARP_VEL) -> list[Note]:
    """Walk a voicing as an UP-DOWN arpeggio across a window: the broken-chord figure
    (tone 0, 1, 2, 1, 0, 1, ...) at `subdiv`-beat steps, seated in `register`, the
    final note clipped at the window edge. Pure."""
    order = list(range(len(tones))) + list(range(len(tones) - 2, 0, -1))
    notes: list[Note] = []
    t, i = start, 0
    while t < start + beats - 1e-9:
        sw, od = tones[order[i % len(order)]]
        dur = min(subdiv, start + beats - t)
        notes.append(Note(swara=sw, oct=register + od, start=round(t, 4),
                          dur=round(dur, 4), vel=vel))
        t += subdiv
        i += 1
    return notes


def _held_pad(tones: list[tuple[str, int]], *, start: float, beats: float,
              register: int) -> list[Note]:
    """The voicing HELD as one soft pad across the window — the thin texture under a
    taan (the sitar owns the motion there; the clean guitar just rings)."""
    return [Note(swara=sw, oct=register + od, start=round(start, 4),
                 dur=round(beats, 4), vel=_ARP_VEL)
            for sw, od in tones]


def _section_notes(span: SectionSpan, raga: str, register: int,
                   cycle_beats: float) -> list[Note]:
    """One section's clean-guitar notes: its per-avartan voicings, arpeggiated (or
    held, under the long taan) bar by bar."""
    section = span.section
    voicings = bar_voicings(section, raga)
    subdiv = _ALAAP_SUBDIV if section.kind.value in _SPACIOUS_KINDS else _ARP_SUBDIV
    notes: list[Note] = []
    for bar, tones in enumerate(voicings):
        bar_start = span.start + bar * cycle_beats
        if section.form_role == _PAD_ROLE:
            notes.extend(_held_pad(tones, start=bar_start, beats=cycle_beats,
                                   register=register))
        else:
            notes.extend(arpeggio(tones, start=bar_start, beats=cycle_beats,
                                  register=register, subdiv=subdiv))
    return notes


def clean_layer(arr: Arrangement) -> Layer | None:
    """The clean electric guitar layer for a chart — every section that lists the
    `clean` role, realised per its harmony plan. None when no section asks for it
    (every existing chart/fixture: fully backward compatible). Pure."""
    register = arr.registers.get(_CLEAN_ROLE, 0)
    notes: list[Note] = []
    for span in section_spans(arr):
        if _CLEAN_ROLE not in span.section.layers:
            continue
        notes.extend(_section_notes(span, arr.raga, register, arr.beats_per_bar))
    if not notes:
        return None
    voice = VOICES[_CLEAN_ROLE]
    return Layer(role=_CLEAN_ROLE, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


# --------------------------------------------------------------------------- #
# The imperative edge — a deterministic sound check (NO LLM).                  #
# --------------------------------------------------------------------------- #

def _demo_arrangement() -> Arrangement:
    """A hand-authored chart hearing all THREE harmony modes over a drone: a broken
    drone dyad, the Sa pedal with rotating colours, then a root cycle coming home.
    Malkauns on purpose (no Pa — the drone dyad is Sa-ma)."""
    from crew.contracts import ArrangementDraft, CompositionBrief, SectionKind, build_arrangement
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=90,
        motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.ALAAP, bars=1, layers=["clean", "drone"],
                    foreground="clean", harmony=HarmonyPlan(mode="drone")),
            Section(kind=SectionKind.MELODY, bars=2, layers=["clean", "drone"],
                    foreground="clean", harmony=HarmonyPlan(mode="modal_pedal")),
            Section(kind=SectionKind.MELODY, bars=2, layers=["clean", "drone"],
                    foreground="clean",
                    harmony=HarmonyPlan(mode="progression", roots=["m", "d", "S"])),
        ])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def main() -> int:
    import shutil
    from pathlib import Path

    from crew.generators import assemble_composition, drone_layer, render_composition

    root = Path(__file__).resolve().parents[1]
    arr = _demo_arrangement()
    comp = assemble_composition(arr, [drone_layer(arr), clean_layer(arr)])
    soundfont = root / "soundfonts" / "GeneralUser-GS.sf2"
    if shutil.which("fluidsynth") and soundfont.exists():
        wav = render_composition(comp, out_dir=root / "out", name="harmony_demo",
                                 soundfont=soundfont)
        print(f"-> rendered {wav.relative_to(root)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
