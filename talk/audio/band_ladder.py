"""The experiment slide's ladder at SONG level, from real model output (one cached call each).

    A — one prompt: "a heavy metal song in raga Bhairav" with sitar, guitar, bass and drums.
    B — the SAME prompt + Bhairav's grammar (ladder.grammar(), generated from src/raga.py).
    C — the full system: the same 16 beats' worth of the opening song (out/fusion_20261011_194039).

A and B are rendered from the model's notes exactly: pitches, lengths, loudness and chord voicings
as written (a chord's notes are played as separate notes, so our renderer's chord seating never
touches them), on the production voices and soundfonts, with the deck's usual left/right
double-track on the rhythm guitar. No drone is added: the model's band is what it wrote. The
LAST 24 beats of each are cut (endings are where coordination shows) and loudness-matched.

    uv run python talk/audio/band_ladder.py        # SA, SB (calls once each, then cached) and SC
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder  # noqa: E402  (pitch parsing, the grammar block, the Bhairav pitch names)
import make_clips as mc  # noqa: E402  (voices, render, loudness, visuals)

ROOT = Path(__file__).resolve().parents[2]
OPENING = ROOT / "out" / "fusion_20261011_194039"
C_END_BEAT = 128.0           # the opening song's last beat: the taan into its hard stop
WINDOW_BEATS = 24.0          # every clip is the LAST 24 beats: endings are where coordination shows (C: the taan landing, then the band to the hard stop)
TAIL_S = 1.5                 # let the last hit ring out, the same for all three
DRUM_NAMES = {"kick": "kick", "snare": "snare", "hihat": "hhat", "hhat": "hhat", "closed_hihat": "hhat", "open_hihat": "ohat",
              "ohat": "ohat", "crash": "crash", "ride": "ride", "china": "china", "tom": "tom_mid", "tom_hi": "tom_hi",
              "high_tom": "tom_hi", "tom_mid": "tom_mid", "mid_tom": "tom_mid", "tom_lo": "tom_lo", "low_tom": "tom_lo",
              "floor_tom": "tom_lo", "bell": "bell"}

BASE = ("Compose a heavy metal song in raga Bhairav at 128 BPM, in the key of E (Sa = E4), for four parts: sitar (the lead "
        "melody), distorted rhythm guitar, bass guitar and a drum kit. Make it about 30 seconds long (about 64 beats), with "
        "every part playing for the whole length. Return ONLY a JSON object with four keys, each a list of events in time "
        "order whose beats add up to the length of the song:\n"
        '  "sitar":  [{"note": "<scientific pitch like E4, or rest>", "beats": <duration>, "vel": <1-127>}]\n'
        '  "guitar": [{"notes": ["<pitch>", ...] (one pitch, a chord, or [] for a rest), "beats": <duration>, "vel": <1-127>}]\n'
        '  "bass":   [{"note": "<pitch or rest>", "beats": <duration>, "vel": <1-127>}]\n'
        '  "drums":  [{"hits": ["kick" | "snare" | "hihat" | "open_hihat" | "crash" | "ride" | "tom_hi" | "tom_mid" | "tom_lo", ...] '
        '([] for a rest), "beats": <duration>, "vel": <1-127>}]')
PROMPTS = {"A": BASE, "B": BASE + "\n" + ladder.grammar()}


def ask_once(key: str) -> dict:
    cache = mc.BUILD / f"band{key}_llm.txt"
    if not cache.exists():
        from crew.config import generator_llm, load_env
        load_env()
        reply = generator_llm().call(PROMPTS[key])
        (mc.BUILD / f"band{key}_prompt.txt").write_text(PROMPTS[key])
        cache.write_text(reply)
    reply = cache.read_text()
    return json.loads(reply[reply.index("{"): reply.rindex("}") + 1])


def _note(pitch: str, start: float, dur: float, vel: int) -> mc.Note:
    rel = ladder.midi(pitch) - mc.SA
    return mc.Note(swara=ladder.SWARA_OF[rel % 12], oct=rel // 12, start=round(start, 4), dur=dur, vel=vel)


def _vel(e: dict, default: int) -> int:
    return max(1, min(127, int(e.get("vel", default))))


def layers_of(song: dict, allowed: set[str] | None = None) -> tuple[list[mc.Layer], dict]:
    """The model's four parts as production layers, notes exactly as written, plus facts about them."""
    def voice(role: str, key: str) -> dict:
        v = mc.VOICES[key]
        return {"role": role, "instrument": v.instrument, "program": v.program, "channel": v.channel, "pan": v.pan}

    allowed = allowed or set(mc.BH["allowed"])
    facts: dict = {"illegal": [], "unknown_drums": [], "beats": {}}
    out: list[mc.Layer] = []
    for part, role, key, default in (("sitar", "lead", "sitar", 90), ("bass", "bass", "bass", 96)):
        t, notes = 0.0, []
        for e in song.get(part, []):
            d = float(e["beats"])
            if str(e.get("note", "rest")).lower() != "rest":
                n = _note(e["note"], t, d, _vel(e, default))
                notes.append(n)
                if n.swara not in allowed:
                    facts["illegal"].append(f"{part}:{e['note']}")
            t += d
        facts["beats"][part] = t
        out.append(mc.Layer(**voice(role, key), notes=notes))
    t, notes = 0.0, []
    for e in song.get("guitar", []):
        d = float(e["beats"])
        for pitch in e.get("notes", []):
            n = _note(pitch, t, d, _vel(e, 100))
            notes.append(n)
            if n.swara not in allowed:
                facts["illegal"].append(f"guitar:{pitch}")
        t += d
    facts["beats"]["guitar"] = t
    riff = mc.Layer(**voice("rhythm", "rhythm"), notes=notes)
    out += [riff, mc.double_track(riff)]
    t, hits = 0.0, []
    for e in song.get("drums", []):
        d = float(e["beats"])
        for h in e.get("hits", []):
            name = DRUM_NAMES.get(str(h).lower())
            if name:
                hits.append(mc.DrumHit(drum=name, start=round(t, 4), vel=_vel(e, 100)))
            else:
                facts["unknown_drums"].append(h)
        t += d
    facts["beats"]["drums"] = t
    out.append(mc.Layer(role="drums", channel=9, hits=hits))
    return out, facts


def clip(key: str) -> dict:
    layers, facts = layers_of(ask_once(key))
    wav = mc.render_comp(mc.comp(layers), f"S{key}_src", check_raga=False)
    spb = mc.SEC_PER_BEAT
    end = max(facts["beats"].values())                # the song ends when its LAST part does
    _, stats = mc.assemble(f"S{key}", [(wav, (end - WINDOW_BEATS) * spb, WINDOW_BEATS * spb + TAIL_S)], 0, fade_out=0.4)
    mc.visuals(f"S{key}")
    return {"clip": f"S{key}", **facts, "stats": stats}


def clip_c() -> dict:
    """C: the opening song itself, its last 16 beats, as cut for A and B."""
    spb = mc.SEC_PER_BEAT
    _, stats = mc.assemble("SC", [(OPENING.with_suffix(".wav"), (C_END_BEAT - WINDOW_BEATS) * spb, WINDOW_BEATS * spb + TAIL_S)], 0, fade_out=0.4)
    mc.visuals("SC")
    return {"clip": "SC", "from": OPENING.name, "window_beats": (C_END_BEAT - WINDOW_BEATS, C_END_BEAT), "stats": stats}


if __name__ == "__main__":
    for k in sys.argv[1:] or ["A", "B", "C"]:
        print(json.dumps(clip_c() if k == "C" else clip(k)))
