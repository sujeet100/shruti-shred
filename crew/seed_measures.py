"""
What code MEASURES about a song seed — the facts every party to the seed debate reads before it
argues (`crew/seed_debate.py`): the two composers, each about its own and its rival's seed, and the
selector choosing between them. "Code measures, the LLM evaluates" — the same discipline as the
Producer's metrics: an argument has to answer to the numbers, not to a vibe.

The seed is rendered as its NOTES (the hook as swara:bol(beats), the riff's cycle) and as the
measures that matter to a gat head over a metal riff:
  * the gat's strokes — bol coverage, the STROKE MOTIF (the recurring bol figure, often the gat's
    real motif — Sujit, 2026-10-12) and the stroke-frame report;
  * the head's shape — the sam note, scalar runs, range, and the mukhada's craft notes;
  * the head and the riff together — how often the head sounds the riff's swara on its accents,
    and how many of the head's plucks land on a riff attack (the band and the sitar sharing one
    rhythm).

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from chalan import scalar_runs
from crew.anchor import hook_stroke_motif, lead_tokens, riff_accents, riff_tokens
from crew.composer import seed_arrangement
from crew.contracts import Arrangement, CompositionBrief, LeadPhrase, RiffPattern, SongSeed
from crew.gat_verifier import check_bol_frame, check_mukhada, riff_quote_share, stroke_onsets
from gats import BOL_WORDS, STROKE_HOLD, frame_for_bpm, is_compound, stroke_motif
from raga import semitone

_SCALAR_RUN: int = 6          # the taan's cap — a longer one-way run is the scale showing through


@dataclass(frozen=True)
class SeedMeasures:
    """The measured facts of one seed. Pure data."""
    form: str
    anchor: str
    bpm: int
    sam_note: str | None
    bol_share: float               # sounding notes carrying a bol
    compound_figures: int          # dir / dar / dara ... on the head
    stroke_motif: tuple[str, ...] | None
    long_scalar_runs: list[int]    # one-way stepwise runs past the cap, in notes
    range_semitones: int
    riff_quote_share: float        # the riff's accented roots the head sounds on their beats
    shared_attack_share: float     # the head's plucks that land on a riff attack
    frame_notes: list[str]         # the stroke-frame report (craft)
    head_notes: list[str]          # the mukhada's craft notes


def _sounding(hook: LeadPhrase) -> list:
    return [n for n in hook.notes if not n.rest]


def _pitch(note) -> int:
    return semitone(note.swara) + 12 * note.oct


def _riff_attacks(riff: RiffPattern) -> set[float]:
    attacks: set[float] = set()
    t = 0.0
    for n in riff.notes:
        if not n.rest:
            attacks.add(round(t, 3))
        t += n.dur
    return attacks


def _shared_attack_share(hook: LeadPhrase, riff: RiffPattern, cycle_beats: float) -> float:
    plucks = [round(t % cycle_beats, 3) for t in stroke_onsets(hook.notes)]
    if not plucks:
        return 0.0
    attacks = _riff_attacks(riff)
    return sum(p in attacks for p in plucks) / len(plucks)


def _idea_strokes(seed: SongSeed) -> list[str]:
    """The struck tokens of a gat seed's head-idea stroke line (holds dropped)."""
    line = seed.head.stroke_line if seed.head else None
    return [t for t in line or [] if t != STROKE_HOLD]


def _measure_idea(seed: SongSeed, arr: Arrangement) -> SeedMeasures:
    """A gat seed holds only its head's IDEA (Option A): what it fixes — the sam swara and the
    stroke line — is measured; the note-level facts wait for the composed head. Pure."""
    strokes = _idea_strokes(seed)
    return SeedMeasures(
        form=arr.form, anchor=arr.anchor, bpm=arr.bpm,
        sam_note=seed.head.sam_swara if seed.head else None, bol_share=0.0,
        compound_figures=sum(t in BOL_WORDS and is_compound(t) for t in strokes),
        stroke_motif=stroke_motif(strokes), long_scalar_runs=[], range_semitones=0,
        riff_quote_share=0.0, shared_attack_share=0.0, frame_notes=[],
        head_notes=["the seed holds only the head's idea — its notes are composed in the gat call"])


def measure_seed(seed: SongSeed, brief: CompositionBrief) -> SeedMeasures:
    """Measure one seed against the chart it describes. Pure."""
    arr = seed_arrangement(seed, brief)
    if seed.hook is None:
        return _measure_idea(seed, arr)
    hook, riff = seed.hook, seed.main_riff
    sounding = _sounding(hook)
    pitches = [_pitch(n) for n in sounding]
    seq = [(n.swara, n.oct) for n in sounding if n.bol != "chikari"]
    frame = frame_for_bpm(arr.bpm)
    cycle = arr.beats_per_bar
    return SeedMeasures(
        form=arr.form, anchor=arr.anchor, bpm=arr.bpm,
        sam_note=sounding[0].swara if sounding else None,
        bol_share=sum(n.bol is not None for n in sounding) / len(sounding) if sounding else 0.0,
        compound_figures=sum(n.bol in BOL_WORDS and is_compound(n.bol) for n in sounding),
        stroke_motif=hook_stroke_motif(hook),
        long_scalar_runs=[r for r in scalar_runs(seq, arr.raga) if r > _SCALAR_RUN],
        range_semitones=max(pitches) - min(pitches) if pitches else 0,
        riff_quote_share=riff_quote_share(hook, riff_accents(riff, arr)),
        shared_attack_share=_shared_attack_share(hook, riff, cycle),
        frame_notes=list(check_bol_frame(hook, cycle_beats=cycle, frame=frame).craft),
        head_notes=list(check_mukhada(hook, cycle_beats=cycle, raga=arr.raga).craft))


def _render_measures(m: SeedMeasures) -> list[str]:
    runs = ", ".join(map(str, m.long_scalar_runs)) or "none"
    lines = [
        f"    form {m.form}, anchor {m.anchor}, {m.bpm} bpm; the head lands {m.sam_note} on the sam",
        f"    strokes: {m.bol_share:.0%} of the head's notes carry a bol, {m.compound_figures} "
        f"compound figure(s); stroke motif: {' '.join(m.stroke_motif) if m.stroke_motif else 'none recurs'}",
        f"    shape: range {m.range_semitones} semitones; one-way scalar runs past "
        f"{_SCALAR_RUN} notes: {runs}",
        f"    with the riff: sounds the riff's swara on {m.riff_quote_share:.0%} of its accents; "
        f"{m.shared_attack_share:.0%} of the head's plucks land on a riff attack",
    ]
    lines += [f"    note: {n}" for n in m.frame_notes + m.head_notes]
    return lines


def _similarity(a: list, b: list) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _hook_line(seed: SongSeed) -> list[str]:
    if seed.hook is None:
        return list(seed.head.cell) if seed.head else []
    return [f"{n.swara}{n.oct}" for n in seed.hook.notes if not n.rest]


def _hook_rhythm(seed: SongSeed) -> list[float]:
    if seed.hook is None:
        return []
    return [n.dur for n in seed.hook.notes]


def _hook_bols(seed: SongSeed) -> list[str]:
    if seed.hook is None:
        return list(seed.head.stroke_line or []) if seed.head else []
    return [n.bol or "-" for n in seed.hook.notes if not n.rest]


def _riff_line(seed: SongSeed) -> list[str]:
    return [f"{n.swara}{n.oct}:{n.dur:g}" for n in seed.main_riff.notes if not n.rest]


def diversity(seeds: list[SongSeed]) -> dict[str, float | int]:
    """How different independent seeds are — the debate's PREMISE (drafts that already agree
    give it nothing to argue about). Mean pairwise similarity (1.0 = identical) of the hook's
    swaras, its rhythm, its bols and the riff, plus how many distinct forms/talas/tempos. Pure."""
    pairs = [(a, b) for i, a in enumerate(seeds) for b in seeds[i + 1:]]
    def mean(part) -> float:
        return round(sum(_similarity(part(a), part(b)) for a, b in pairs) / len(pairs), 2) if pairs else 1.0
    return {"hook_swaras": mean(_hook_line), "hook_rhythm": mean(_hook_rhythm),
            "hook_bols": mean(_hook_bols), "riff": mean(_riff_line),
            "forms": len({s.chart.form for s in seeds}), "talas": len({s.chart.tala for s in seeds}),
            "tempos": len({s.chart.bpm for s in seeds})}


def _sitar_line(seed: SongSeed) -> str:
    """The seed's sitar part as the debate reads it: the hook's notes, or the gat head's idea."""
    if seed.hook is not None:
        return f"    hook (one avartan, swara:bol(beats)): {lead_tokens(seed.hook.notes)}"
    head = seed.head
    if head is None:
        return "    (no sitar part)"
    return (f"    head idea: sam {head.sam_swara}; cell {' '.join(head.cell)}; strokes "
            f"{' '.join(head.stroke_line or []) or '(none)'} — {head.idea.strip() or '(not stated)'}")


def render_seed(label: str, seed: SongSeed, brief: CompositionBrief) -> str:
    """One labelled seed as the debate and the selector read it: its idea in the composer's own
    words, its notes, and code's measurements. Pure."""
    arr: Arrangement = seed_arrangement(seed, brief)
    sections = " → ".join(s.form_role or s.kind.value for s in arr.sections)
    lines = [f"  SEED {label} — {arr.raga}, {arr.tala}; {sections}",
             f"    the idea: {seed.reasoning.strip() or '(not stated)'}",
             f"    main riff (one cycle, swara(beats)): {riff_tokens(seed.main_riff.notes)}",
             _sitar_line(seed)]
    return "\n".join(lines + _render_measures(measure_seed(seed, brief)))
