"""
EXPRESSION — the gestures code stamps on a placed lead line, from raga facts and section role.

The LLM writes swaras, durations, kan and meend; it cannot hear, so it never asks for a sway or
a gamak. Those are facts about the raga (which swaras oscillate, and toward which neighbour)
and about the section (the alap glides slowly, the climax shakes), so code applies them after
placement and the renderer draws them:

  * ANDOLAN direction + turn — every andolit note gets `andolan_st`, the signed point where its
    sway TURNS (negative below, positive above, toward `raga.ANDOLAN_TOWARD`'s neighbour). The
    turn is where the pitch slows and the ear names it, so it must sit on pitch the raga owns.
    A neighbour a SEMITONE away (Darbari g->R, d->P; Bhairav r->S) leaves nothing between them:
    the sway reaches half way and touches the neighbour's periphery. A neighbour a WHOLE TONE
    away has a foreign swara in the middle — half way to Bageshree's Ma is shuddha Ga, to Todi's
    komal Ga is shuddha Re — so the sway stays inside its own swara (`ANDOLAN_SHALLOW_ST`).
    (fusion_20261013_081705_bageshree turned on shuddha Ga at +98 cents, three times in 20 s.)
    That shallow sway is a RESTING ornament: on a note that steps straight up into the neighbour
    it leans toward and stays there ("(m)g m"), it pre-empts the arrival, so it is left off.
  * SLOW MEEND — in the alap and the outro, a meend is the long, deliberate glide that holds
    its source and rests on the swaras it passes (the raga signposts).
  * KAN — where the raga encodes how a swara is APPROACHED (`raga["kan"]`: Darbari's g takes a
    Re touch rising and a Ma touch falling, its d a Pa / Ni touch), a held sitar note of that
    swara gets the touch for the direction the line arrives from. The data was only ever told
    to the LLM, which rarely wrote it; a GPT review of the 2026-10-12 Darbari render found the
    hook's g and d bare — "a straight g/d turns it into plain Asavari". A kan the LLM wrote wins.
  * GAMAK CELLS — a note the composer marked `gamak_with` a neighbour becomes a run of strokes
    (~250 ms apart, the measured pace), each swinging out to that neighbour and back at the
    measured speed (`gestures.gamak_stroke_path`). An illegal or non-adjacent partner, a khada
    raga, or a note shorter than one stroke plays plain.
  * GESTURE — where `src/gestures.py` holds a MEASURED figure for a swara (Darbari's komal Ga:
    a loop up to Ma, or a dip to Re when the line arrives from Ma — Sujit's guruji's recording),
    a note long enough to carry it gets the whole path instead of a kan: the gesture IS the
    approach, and the note holds steady after it. Gat sections only, unless a rule is marked
    `in_alap`: guruji's Darbari figures were measured in a fast gat; Bageshree's slow release
    of Ga from Ma (arriving from Ma) is an alap gesture as much as a gat one.
  * GAMAK — in the climax taan, notes long enough to carry it swing forcefully up to the next
    raga swara and back, with audible stops (ITC). Never in a khada raga (Marwa), and never on
    an ANDOLIT swara: the swara the raga defines by its slow sway must not inherit the same
    up-shake as Sa or Pa (that review measured 30 of the climax's 46 notes bent alike).
  * the LEAD GUITAR plays the line PLAIN: no sway, no gamak, quick glides only. A distorted
    guitar crawling through the same microtones in unison with the sitar was a likely cause of
    the out-of-tune andolan.

No source measures these gestures, so the shares below are inference for the ear to tune.
Pure — Note in, Note out.
"""

from __future__ import annotations

from typing import Final

from crew.contracts import Arrangement, Note, Section, SectionKind
from gestures import (
    SETTLE_MS,
    gamak_interval,
    gamak_stroke_beats,
    gamak_stroke_path,
    gesture_for,
    gesture_path,
)
from gats import is_vilambit
from render import counted_hold_ms
from raga import (ANDOLAN_DEPTH_ST, ANDOLAN_ONLY_IN, ANDOLAN_SWINGS, INTONATION, KHADA_RAGAS, RAGAS, SWARAS, andolan_neighbour_st,
                  ascent_step)

ANDOLAN_REACH: Final = 0.5       # a semitone neighbour: the sway turns half way, at its periphery
# A whole-tone neighbour: the sway turns inside its own swara, ~30 cents out — the shallow sway
# the AUTRIM/NCPA pitch graphs show (20-35 cents). Inference for the ear; no source gives cents.
ANDOLAN_SHALLOW_ST: Final = 0.30
# 220 ms let nearly every note of a slow taan swing (a 64-bpm sixteenth is 234 ms), so the
# gamak read as one shake on everything; 350 ms keeps it to the notes that carry weight.
GAMAK_MIN_MS: Final = 350        # shorter notes articulate cleanly — no room for a swing
KAN_MIN_MS: Final = 250          # a 60 ms touch needs a note long enough to land after it
_APPROACH_GAP_BEATS: Final = 1.0  # a note after a longer silence is a fresh attack, not approached
_GAMAK_VEL: Final = 1.08         # a gamak is played with force
_GAMAK_RESTRIKE_VEL: Final = 0.85  # strokes after the first in a gamak cell sit back a little
GAMAK_GESTURE: Final = "gamak"
_SLOW_MEEND_ROLES: Final = frozenset({"intro", "outro"})
_SLOW_MEEND_KINDS: Final = frozenset({SectionKind.ALAAP, SectionKind.OUTRO})
_GAMAK_ROLES: Final = frozenset({"taan_long"})


def express_section(sitar: list[Note], guitar: list[Note], section: Section,
                    arr: Arrangement) -> tuple[list[Note], list[Note]]:
    """Stamp the section's gestures on the sitar line and play the guitar line plain."""
    slow = section.form_role in _SLOW_MEEND_ROLES or section.kind in _SLOW_MEEND_KINDS
    line = with_andolan(sitar, arr.raga)
    if not slow:                     # the alap's ornament is slow — gamak belongs to the gat
        line = with_gamak_cells(line, arr.raga, arr.bpm)
    else:
        line = [n.model_copy(update={"gamak_with": None}) if n.gamak_with else n for n in line]
    composed_gamak = any(n.gesture == GAMAK_GESTURE for n in line)
    line = with_gestures(line, arr.raga, arr.bpm, alap=slow)
    line = with_kan(line, arr.raga, arr.bpm)
    if slow:
        line = [_slow_meend(n) for n in line]
    if section.form_role in _GAMAK_ROLES and arr.raga not in KHADA_RAGAS and not composed_gamak:
        andolit = frozenset(RAGAS[arr.raga].get("andolan", []))
        line = [_with_gamak(n, arr.raga, arr.bpm, andolit) for n in line]
    return with_intonation(line, arr.raga, arr.bpm), [_plain(n) for n in guitar]


def with_intonation(line: list[Note], raga: str, bpm: int) -> list[Note]:
    """Give every note of the raga its swara's shruti offset (`raga.INTONATION` — Darbari by the
    Hindustani 22-shruti system): a sitar's frets sit at the shrutis, so a fast note is as much
    in shruti as a held one. A note that already carries an intonation keeps it. Pure."""
    offsets = INTONATION.get(raga, {})
    if not offsets:
        return line
    return [n.model_copy(update={"cents": offsets[n.swara]})
            if n.cents is None and n.swara in offsets else n
            for n in line]


def with_gamak_cells(line: list[Note], raga: str, bpm: int) -> list[Note]:
    """Expand every note the composer marked `gamak_with` into its strokes. Pure."""
    out: list[Note] = []
    for n in line:
        out.extend(_gamak_strokes(n, raga, bpm) if n.gamak_with else [n])
    return out


def _gamak_strokes(n: Note, raga: str, bpm: int) -> list[Note]:
    interval = None if raga in KHADA_RAGAS else gamak_interval(raga, n.swara, n.gamak_with)
    stroke = gamak_stroke_beats(bpm)
    count = int(round(n.dur / stroke))
    if interval is None or count < 1 or n.chord or n.meend_swara is not None:
        return [n.model_copy(update={"gamak_with": None})]
    each = n.dur / count
    return [n.model_copy(update={
        "start": round(n.start + k * each, 4), "dur": round(each, 4),
        "vel": n.vel if k == 0 else max(1, round(n.vel * _GAMAK_RESTRIKE_VEL)),
        "grace": n.grace if k == 0 else None, "andolan": None, "andolan_st": None, "andolan_swings": None,
        "gesture": GAMAK_GESTURE,
        "pitch_path": gamak_stroke_path(each * 60000.0 / bpm, interval, seed=n.start + k * each)})
        for k in range(count)]


def with_gestures(line: list[Note], raga: str, bpm: int, *, alap: bool = False) -> list[Note]:
    """Play each note the raga holds a gesture for with that gesture, chosen by the swara the
    line arrives from (`gestures.gesture_for`; in the alap only the alap's gestures). A note too
    short to carry the path and settle, a glide, a chord, or a note with a kan of its own is
    left alone. Pure."""
    out: list[Note] = []
    prev: Note | None = None
    for n in line:
        out.append(_gestured(n, _approach(prev, n), raga, bpm, alap))
        prev = n
    return out


def _approach(prev: Note | None, n: Note) -> str | None:
    """The swara the line arrives from: the previous note's resting swara when it sounded just
    before and within a tritone of this one; None after a silence or a leap."""
    if prev is None or n.start - (prev.start + prev.dur) > _APPROACH_GAP_BEATS:
        return None
    if abs(_resting_pitch(prev) - (SWARAS[n.swara] + 12 * n.oct)) > 6:
        return None
    return _resting_swara(prev)


def _sways_slowly(n: Note, raga: str, bpm: int) -> bool:
    """Whether a held andolit note SWAYS instead of taking guruji's gesture: in a vilambit piece,
    when the raga counts its andolan's swings and the note can carry the fewest of them. Guruji's
    gestures were measured on a 120 bpm gat; Sujit (2026-10-18): "for slower Darbari fusion multiple
    andolan should be possible and will actually add more weight". Pure."""
    swings = ANDOLAN_SWINGS.get(raga)
    return bool(n.andolan and swings and is_vilambit(bpm)
                and n.dur * 60000.0 / bpm >= counted_hold_ms(swings))


def _gestured(n: Note, approach: str | None, raga: str, bpm: int, alap: bool = False) -> Note:
    gesture = gesture_for(raga, n.swara, approach, alap=alap)
    if _sways_slowly(n, raga, bpm):
        return n                                   # keeps its counted sway (`with_andolan` stamped it)
    if (gesture is None or n.gesture is not None or n.grace or n.chord or n.meend_swara is not None
            or n.technique is not None
            or n.dur * 60000.0 / bpm < gesture.length_ms + SETTLE_MS):
        return n
    # the gesture REPLACES the sway: after the loop, guruji's Ga holds steady (52.0 s); a sway
    # bolted on after it read as two unrelated movements (GPT, 2026-10-12)
    return n.model_copy(update={"gesture": gesture.name, "andolan": None, "andolan_st": None, "andolan_swings": None,
                                "pitch_path": gesture_path(gesture, n.swara, seed=n.start)})


def with_kan(line: list[Note], raga: str, bpm: int) -> list[Note]:
    """Give each held note of a kan-bearing swara the raga's approach touch for the direction
    the line arrives from (from below -> the aroha kan, from above -> the avaroha kan). A note
    with no previous pitch, a repeat of the same pitch, a glide, a chord, or a kan of its own
    is left alone. Pure."""
    rules = RAGAS[raga].get("kan", {})
    if not rules:
        return line
    out: list[Note] = []
    prev: int | None = None
    for n in line:
        out.append(_kan_for(n, prev, rules.get(n.swara), bpm))
        prev = _resting_pitch(n)
    return out


def _resting_pitch(n: Note) -> int:
    sw = _resting_swara(n)
    octave = n.meend_oct if n.meend_swara is not None and n.meend_oct is not None else n.oct
    return SWARAS[sw] + 12 * octave


def _kan_for(n: Note, prev: int | None, rule: dict[str, str] | None, bpm: int) -> Note:
    if (rule is None or prev is None or n.grace or n.chord or n.meend_swara is not None
            or n.gesture is not None or n.dur * 60000.0 / bpm < KAN_MIN_MS):
        return n
    here = SWARAS[n.swara] + 12 * n.oct
    if here == prev:
        return n
    touch = rule.get("aroha" if prev < here else "avaroha")
    return n.model_copy(update={"grace": [touch]}) if touch else n


def _resting_swara(n: Note) -> str:
    return n.meend_swara if n.meend_swara is not None else n.swara


def andolan_turn_st(raga: str, swara: str) -> float:
    """Where this andolit swara's sway turns, in signed semitones from it: a measured depth where
    the data has one (`ANDOLAN_DEPTH_ST`, Bhairav), else half way to a semitone neighbour (its
    periphery — nothing lies between), or `ANDOLAN_SHALLOW_ST` toward a whole-tone neighbour
    (half way would be a foreign swara). Pure."""
    gap = andolan_neighbour_st(raga, swara)
    if raga in ANDOLAN_DEPTH_ST:
        return ANDOLAN_DEPTH_ST[raga] if gap > 0 else -ANDOLAN_DEPTH_ST[raga]
    if abs(gap) == 1:
        return ANDOLAN_REACH * gap
    return ANDOLAN_SHALLOW_ST if gap > 0 else -ANDOLAN_SHALLOW_ST


def with_andolan(line: list[Note], raga: str) -> list[Note]:
    """Give each andolit note its turn (`andolan_turn_st`), and take the sway off a note that
    steps straight on into the neighbour it leans toward and stays there, or that is approached
    against the direction the raga's andolan belongs to (`ANDOLAN_ONLY_IN`: Bhairav's r/d sway in
    descent; rising, they are plain). Pure."""
    out: list[Note] = []
    prev: Note | None = None
    for n, nxt in zip(line, line[1:] + [None]):
        out.append(_off_direction(n, prev, nxt, raga) or _with_andolan_turn(n, nxt, raga))
        prev = n
    return out


def _off_direction(n: Note, prev: Note | None, nxt: Note | None, raga: str) -> Note | None:
    """The note made plain when the line PASSES THROUGH it against the direction its andolan
    belongs to (Bhairav: rising into it and on out of it, `S r G`), else None. A turn (`S r S`), a
    note after a leap or a rest, or one the line comes down to keeps its sway: the sources show it
    on held r/d in descent and do not forbid it elsewhere (flagged in the research)."""
    only = ANDOLAN_ONLY_IN.get(raga)
    if not (n.andolan and only and prev is not None and nxt is not None):
        return None
    here = _resting_pitch(n)
    through_up = _resting_pitch(prev) < here < _resting_pitch(nxt)
    through_down = _resting_pitch(prev) > here > _resting_pitch(nxt)
    if (only == "avaroha" and through_up) or (only == "aroha" and through_down):
        return n.model_copy(update={"andolan": None, "andolan_st": None, "andolan_swings": None})
    return None


def _with_andolan_turn(n: Note, nxt: Note | None, raga: str) -> Note:
    if not n.andolan:
        return n
    swara = _resting_swara(n)
    gap = andolan_neighbour_st(raga, swara)
    if abs(gap) > 1 and _steps_into(n, nxt, gap):
        return n.model_copy(update={"andolan": None, "andolan_st": None, "andolan_swings": None})
    return n.model_copy(update={"andolan_st": round(andolan_turn_st(raga, swara), 3),
                                "andolan_swings": ANDOLAN_SWINGS.get(raga)})


def _steps_into(n: Note, nxt: Note | None, gap: int) -> bool:
    """The next note follows at once, IS the neighbour `gap` semitones away, and is held at
    least as long — the line arrives there, so this note is its approach."""
    if nxt is None or nxt.start - (n.start + n.dur) > _APPROACH_GAP_BEATS:
        return False
    return _resting_pitch(nxt) == _resting_pitch(n) + gap and nxt.dur >= n.dur


def _slow_meend(n: Note) -> Note:
    return n.model_copy(update={"meend_style": "slow"}) if n.meend_swara is not None else n


def _with_gamak(n: Note, raga: str, bpm: int, andolit: frozenset[str]) -> Note:
    """A gamak on a note long enough to swing, not of an andolit swara, and not already
    carrying a gesture of its own."""
    if (n.andolan or n.swara in andolit or n.meend_swara is not None or n.grace
            or n.gesture is not None or n.technique is not None
            or n.dur * 60000.0 / bpm < GAMAK_MIN_MS):
        return n
    up, octave = ascent_step(n.swara, raga)
    st = SWARAS[up] + 12 * octave - SWARAS[n.swara]
    return n.model_copy(update={"gamak_st": st, "vel": min(127, round(n.vel * _GAMAK_VEL))})


def _plain(n: Note) -> Note:
    if not (n.andolan or n.andolan_st or n.gamak_st or n.meend_style or n.pitch_path):
        return n
    return n.model_copy(update={"andolan": None, "andolan_st": None, "andolan_swings": None, "gamak_st": None,
                                "meend_style": None, "gesture": None, "pitch_path": None})
