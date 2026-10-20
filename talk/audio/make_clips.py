"""Talk audio clips — deterministic, NO LLM.

Builds the short demonstration clips for the deck (A02-A10) from the repo's own
deterministic core: raga/tala facts from src/raga.py + src/talas.py, the band's voices
(crew.generators.VOICES), the product's double-track and tabla bol mapping, the same
soundfont routing the real band uses (soundfont.route_layers / present_extras /
base_soundfont), and the Phase-0 renderer (render.render). Post-processing (trim, fade,
loudness match, concat, MP4 + PNG) is ffmpeg.

Run from the repo root:
    uv run python talk/audio/make_clips.py

Outputs land in talk/audio/ (<id>.wav/.mp4/.png); intermediate renders in talk/audio/build/.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import crew  # noqa: E402,F401  (puts src/ on the path; no LLM at import)

from crew.contracts import Composition, DrumHit, Layer, Note  # noqa: E402
from crew.generators import VOICES, double_track  # noqa: E402
from crew.groove import _bol_voices, _tabla_vel  # noqa: E402
from raga import RAGAS, SWARAS, drone_swaras, validate_composition  # noqa: E402
from render import ANDOLAN_MIN_MS, render  # noqa: E402
from soundfont import base_soundfont, present_extras, route_layers  # noqa: E402
from talas import TALAS  # noqa: E402

OUT = ROOT / "talk" / "audio"
BUILD = OUT / "build"

SA = 64            # E4 — the talk's performance is in Sa = E
BPM = 128
RAGA = "bhairav"
BH = RAGAS[RAGA]
TEENTAAL = TALAS["teentaal"]

TARGET_LUFS = -18.0   # every clip lands here (A/B parts matched to each other)
PEAK_CEIL_DB = -1.0   # sample-peak ceiling after gain
SEC_PER_BEAT = 60.0 / BPM

BG = "0x08070d"
FG = "0xf2b53c"


# --------------------------------------------------------------------------- #
# Musical helpers — pitches come from the encoded raga data; rhythm is ours.  #
# --------------------------------------------------------------------------- #

def collapse(phrase: list[str]) -> list[str]:
    """Merge repeated adjacent swaras ("d d" -> one elongated d). The encoded pakad
    writes the dwelt-on andolit note twice; we render it as one held, oscillated note."""
    out: list[str] = []
    for sw in phrase:
        if not out or out[-1] != sw:
            out.append(sw)
    return out


def ladder(seq: list[str], start_oct: int, direction: int) -> list[tuple[str, int]]:
    """Assign octaves to a scale run: step the octave when the run wraps past Sa."""
    out: list[tuple[str, int]] = []
    octv = start_oct
    prev = None
    for sw in seq:
        if prev is not None:
            if direction > 0 and SWARAS[sw] <= SWARAS[prev]:
                octv += 1
            if direction < 0 and SWARAS[sw] >= SWARAS[prev]:
                octv -= 1
        out.append((sw, octv))
        prev = sw
    return out


def andolan_ok(swara: str, dur_beats: float) -> bool:
    """Code sets andolan (as the lead generator does): on the raga's own andolan swaras,
    and only where the hold is long enough in real time for the renderer to sway it."""
    return swara in BH["andolan"] and dur_beats * SEC_PER_BEAT * 1000 >= ANDOLAN_MIN_MS


def sitar_line(events: list[tuple], *, shaped: bool, start: float = 0.0, vel: int = 90) -> Layer:
    """events = [(swara, oct, dur) | ("-", None, dur)]; '-' is a rest."""
    notes: list[Note] = []
    t = start
    for sw, octv, dur in events:
        if sw != "-":
            notes.append(Note(swara=sw, oct=octv, start=round(t, 4), dur=dur, vel=vel,
                              andolan=True if shaped and andolan_ok(sw, dur) else None))
        t += dur
    if shaped:      # the product's expression pass: the raga's kan, and its andolan's turn and direction
        from crew.expression import with_andolan, with_kan
        notes = with_andolan(with_kan(notes, RAGA, BPM), RAGA)
    v = VOICES["sitar"]
    return Layer(role="lead", instrument=v.instrument, program=v.program, channel=v.channel,
                 pan=64, notes=notes)   # centred for the demo (product pans it left of centre)


def drone(length_beats: float, *, soft: bool = False) -> Layer:
    """The product's tanpura pad: Sa + the raga's companion (drone_swaras), GM strings, the
    lowest register. Velocities 55/45 as crew.generators.drone_layer; `soft` = lighter."""
    tones = drone_swaras(RAGA)
    vels = [40, 32] if soft else [55, 45]
    v = VOICES["drone"]
    notes = [Note(swara=sw, oct=-2, start=0.0, dur=length_beats, vel=vel)
             for sw, vel in zip(tones, vels)]
    return Layer(role="drone", instrument=v.instrument, program=v.program, channel=v.channel,
                 pan=v.pan, notes=notes)


def matra_kind(matra: int) -> str:
    """sam/tali/khali/beat for a 1-indexed matra, from the encoded teentaal."""
    if matra == TEENTAAL["sam"]:
        return "sam"
    if matra in TEENTAAL["tali"]:
        return "tali"
    if matra in TEENTAAL["khali"]:
        return "khali"
    return "beat"


def tabla(start: float, n_matras: int, *, sam_vel: int | None = None) -> Layer:
    """The teentaal theka, one bol per matra from talas.py, mapped to tabla strokes with the
    product's bol->stroke mapping and accent velocities (crew.groove)."""
    theka = TEENTAAL["theka"]
    hits: list[DrumHit] = []
    for k in range(n_matras):
        idx = k % TEENTAAL["matras"]
        kind = matra_kind(idx + 1)
        vel = sam_vel if (kind == "sam" and sam_vel) else _tabla_vel(kind)
        for voice in _bol_voices(theka[idx]):
            hits.append(DrumHit(drum=voice, start=round(start + k, 4), vel=vel))
    return Layer(role="tabla", channel=9, hits=hits)


def comp(layers: list[Layer]) -> Composition:
    return Composition(raga=RAGA, sa=SA, bpm=BPM,
                       tala={"name": "teentaal", "beats_per_bar": 16.0}, layers=layers)


def render_comp(c: Composition, name: str, *, check_raga: bool = True) -> Path:
    """Mirror crew.generators.render_composition: route voices exactly as the product does,
    stack every present extra soundfont over the preferred base, render via FluidSynth."""
    BUILD.mkdir(parents=True, exist_ok=True)
    payload = c.model_dump(exclude_none=True)
    if check_raga:
        bad = validate_composition(payload)
        if bad:
            raise SystemExit(f"{name}: raga violations {bad[:3]}")
    (BUILD / f"{name}.json").write_text(c.model_dump_json(exclude_none=True, indent=2))
    route_layers(payload["layers"], sa=payload["sa"])
    extras = [(str(e.path), e.bank_offset) for e in present_extras()]
    wav = BUILD / f"{name}.wav"
    render(payload, str(BUILD / f"{name}.mid"), str(wav), str(base_soundfont()),
           extra_soundfonts=extras)
    return wav


# --------------------------------------------------------------------------- #
# ffmpeg post-processing                                                      #
# --------------------------------------------------------------------------- #

def ff(*args: str) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {' '.join(args)}\n{r.stderr[-2000:]}")
    return r.stderr


def lufs(path: Path) -> float:
    err = ff("-nostats", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-")
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def peak_db(path: Path) -> float:
    err = ff("-i", str(path), "-af", "volumedetect", "-f", "null", "-")
    return float(re.search(r"max_volume:\s*(-?[\d.]+) dB", err).group(1))


def mean_db(path: Path) -> float:
    err = ff("-i", str(path), "-af", "volumedetect", "-f", "null", "-")
    return float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", err).group(1))


def cut(src: Path, dst: Path, start_s: float, dur_s: float,
        fade_in: float = 0.005, fade_out: float = 0.3) -> Path:
    af = (f"atrim=start={start_s}:duration={dur_s},asetpts=PTS-STARTPTS,"
          f"afade=t=in:st=0:d={fade_in},afade=t=out:st={dur_s - fade_out:.3f}:d={fade_out},"
          "aformat=sample_fmts=s16:sample_rates=44100:channel_layouts=stereo")
    ff("-i", str(src), "-af", af, "-c:a", "pcm_s16le", str(dst))
    return dst


def assemble(clip_id: str, parts: list[tuple[Path, float, float]], gap_s: float,
             fade_out: float = 0.3) -> tuple[Path, list[dict]]:
    """Cut each (src, start_s, dur_s) part, match their integrated loudness (all to the same
    target, lowered together if any part would exceed the peak ceiling), join with silence."""
    cuts = [cut(src, BUILD / f"{clip_id}_part{i}.wav", s, d, fade_out=fade_out)
            for i, (src, s, d) in enumerate(parts)]
    stats = [{"lufs": lufs(p), "peak": peak_db(p)} for p in cuts]
    target = min([TARGET_LUFS] + [PEAK_CEIL_DB - (st["peak"] - st["lufs"]) for st in stats])
    gains = [target - st["lufs"] for st in stats]
    inputs: list[str] = []
    chains: list[str] = []
    labels: list[str] = []
    for i, (p, g) in enumerate(zip(cuts, gains)):
        inputs += ["-i", str(p)]
        chains.append(f"[{i}:a]volume={g:.2f}dB[a{i}]")
        if i:
            chains.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={gap_s}[g{i}]")
            labels.append(f"[g{i}]")
        labels.append(f"[a{i}]")
    n = len(labels)
    graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={n}:v=0:a=1[out]"
    dst = OUT / f"{clip_id}.wav"
    ff(*inputs, "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le",
       "-ar", "44100", str(dst))
    for st, g in zip(stats, gains):
        st["gain_db"] = round(g, 2)
    return dst, stats


def duration_s(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def visuals(clip_id: str) -> None:
    """<id>.png — the whole clip's waveform, drawn at 320x80 and blown up with
    nearest-neighbour scaling (pixel look), gold on the deck background.
    <id>.mp4 — that same picture with a gold playhead sweeping left->right in time with
    the audio; the not-yet-played part is dimmed. Duration = the audio's duration."""
    wav = OUT / f"{clip_id}.wav"
    png = OUT / f"{clip_id}.png"
    graph_png = (f"[0:a]showwavespic=s=320x80:colors={FG}:scale=sqrt:draw=full,"
                 "scale=1280:320:flags=neighbor[w];"
                 f"color=c={BG}:s=1280x320[bg];[bg][w]overlay=shortest=1,format=rgb24[v]")
    ff("-i", str(wav), "-filter_complex", graph_png, "-map", "[v]", "-frames:v", "1", str(png))
    d = duration_s(wav)
    x = f"W*t/{d:.4f}"
    graph = (f"color=c={BG}@0.72:s=1280x320:r=30,format=rgba[dim];"
             f"color=c={FG}:s=4x320:r=30,format=rgba[ph];"
             f"[0:v]format=rgba[pic];"
             f"[pic][dim]overlay=x='{x}':y=0:eval=frame[a];"
             f"[a][ph]overlay=x='{x}-2':y=0:eval=frame,format=yuv420p[v]")
    ff("-loop", "1", "-framerate", "30", "-t", f"{d:.4f}", "-i", str(png), "-i", str(wav),
       "-filter_complex", graph, "-map", "[v]", "-map", "1:a",
       "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
       "-c:a", "aac", "-b:a", "192k", "-t", f"{d:.4f}", "-movflags", "+faststart",
       str(OUT / f"{clip_id}.mp4"))


# --------------------------------------------------------------------------- #
# The clips                                                                   #
# --------------------------------------------------------------------------- #

def beats(sec: float) -> float:
    return sec / SEC_PER_BEAT


def a02() -> dict:
    """Stem build: drone 0-4 s; sitar (pakad 1 then pakad 2) from ~4 s; tabla theka on its
    sam at ~8 s, landing with the sitar's andolit komal Re."""
    p1, p2 = collapse(BH["pakad"][0]), collapse(BH["pakad"][1])   # G m d P | G m r S
    assert p1 == ["G", "m", "d", "P"] and p2 == ["G", "m", "r", "S"]
    sitar_start = 8.5                                             # 3.98 s
    ev = [(p1[0], 0, 1.0), (p1[1], 0, 0.75), (p1[2], 0, 3.25), (p1[3], 0, 2.0),
          ("-", None, 0.5),
          (p2[0], 0, 0.5), (p2[1], 0, 0.5), (p2[2], 0, 3.0), (p2[3], 0, 6.5)]
    tabla_start = 17.0                                            # 7.97 s — the sam
    total = 26.5
    c = comp([drone(total + 2), sitar_line(ev, shaped=True, start=sitar_start),
              tabla(tabla_start, int(total - tabla_start) + 1)])
    wav = render_comp(c, "A02_full")
    dst, stats = assemble("A02", [(wav, 0.0, 12.4)], 0, fade_out=0.8)
    return {"stats": stats, "sitar_s": sitar_start * SEC_PER_BEAT,
            "tabla_s": tabla_start * SEC_PER_BEAT}


def aroha_run(dur: float) -> list[tuple]:
    return [(sw, o, dur) for sw, o in ladder(BH["aroha"], 0, +1)]


def a03() -> dict:
    """A: the encoded aroha, even quarter notes. B: pakad 1 + pakad 2 with varied durations,
    andolan on r/d, landing on Sa. Same sitar, register, velocity, drone."""
    flat = aroha_run(1.0)                                            # S r G m P d N S'
    p1, p2 = collapse(BH["pakad"][0]), collapse(BH["pakad"][1])
    shaped = [(p1[0], 0, 0.5), (p1[1], 0, 0.5), (p1[2], 0, 2.5), (p1[3], 0, 0.75),
              (p2[0], 0, 0.5), (p2[1], 0, 0.25), (p2[2], 0, 2.5), (p2[3], 0, 1.75)]
    wa = render_comp(comp([drone(11), sitar_line(flat, shaped=False)]), "A03_a")
    wb = render_comp(comp([drone(11), sitar_line(shaped, shaped=True)]), "A03_b")
    _, stats = assemble("A03", [(wa, 0, 4.0), (wb, 0, 4.25)], 1.0)
    return {"stats": stats}


def a04() -> dict:
    """A held komal Re, plain then with the renderer's andolan. Identical note otherwise."""
    held = [("-", None, 0.5), ("r", 0, 5.0)]
    wa = render_comp(comp([drone(7), sitar_line(held, shaped=False)]), "A04_a")
    wb = render_comp(comp([drone(7), sitar_line(held, shaped=True)]), "A04_b")
    _, stats = assemble("A04", [(wa, 0, 2.75), (wb, 0, 2.75)], 0.5)
    return {"stats": stats}


def a05() -> dict:
    """Exactly one teentaal cycle (16 matras = 7.5 s at 128) of the theka, sam accented."""
    c = comp([drone(18, soft=True), tabla(0.0, 16, sam_vel=112)])
    wav = render_comp(c, "A05_full")
    _, stats = assemble("A05", [(wav, 0.0, 16 * SEC_PER_BEAT)], 0, fade_out=0.15)
    return {"stats": stats}


def a06() -> dict:
    """b: legal but aimless — every note in Bhairav, but even 0.75-beat notes, leaps with no
    phrase, no repeated idea, no andolan, ending on Ni with no homecoming (what our early
    generators actually wrote). c: pakad 1 + the descent
    chalan, varied rhythm, andolan on d/r, rests, Sa landing on the sam. Both clips begin at
    matra 6 of a teentaal cycle so that c's Sa falls on the next sam (beat 11 = 5.16 s)."""
    wander = [("m", 0), ("N", -1), ("P", 0), ("r", 1), ("G", 0), ("d", 0), ("S", 1), ("m", 0),
              ("r", 0), ("N", 0), ("G", 1), ("P", 0), ("d", -1), ("m", 1), ("G", 0), ("N", 0)]
    assert all(sw in BH["allowed"] for sw, _ in wander)           # legal, note for note
    flat = [(sw, o, 0.75) for sw, o in wander]                    # 16 even notes, no landing
    p1 = collapse(BH["pakad"][0])                                 # G m d P
    ch = collapse(BH["chalan"][2])                                # d P G m r S
    assert ch == ["d", "P", "G", "m", "r", "S"]
    shaped = [(p1[0], 0, 0.5), (p1[1], 0, 0.5), (p1[2], 0, 2.5), (p1[3], 0, 1.0),
              ("-", None, 0.5),
              (ch[0], 0, 0.5), (ch[1], 0, 0.5), (ch[2], 0, 0.5), (ch[3], 0, 0.5),
              (ch[4], 0, 3.25), ("-", None, 0.75),
              (ch[5], 0, 2.0)]                                    # Sa at beat 11 = the sam
    wb = render_comp(comp([drone(15), sitar_line(flat, shaped=False)]), "A06b_src")
    wc = render_comp(comp([drone(15), sitar_line(shaped, shaped=True)]), "A06c_src")
    # Level-match b and c to EACH OTHER, then write them as separate clips.
    _, stats = assemble("A06bc_pair", [(wb, 0, 6.0), (wc, 0, 6.0)], 0.5)
    pair = OUT / "A06bc_pair.wav"
    n6 = int(round(6.0 * 44100))
    ff("-i", str(pair), "-af", f"atrim=end_sample={n6}", "-c:a", "pcm_s16le",
       str(OUT / "A06b.wav"))
    ff("-i", str(pair), "-af", f"atrim=start_sample={n6 + int(0.5 * 44100)}",
       "-c:a", "pcm_s16le", str(OUT / "A06c.wav"))
    pair.unlink()
    # One player per slide: the deck can't stop one clip when another starts, so the
    # experiment slide plays B, a 1 s pause, then C from a single file.
    ff("-i", str(OUT / "A06b.wav"), "-i", str(OUT / "A06c.wav"), "-filter_complex",
       "[0:a]apad=pad_dur=1.0[b];[b][1:a]concat=n=2:v=0:a=1[o]", "-map", "[o]",
       "-c:a", "pcm_s16le", str(OUT / "A06bc.wav"))
    return {"stats": stats}


def a09() -> dict:
    """Same composition before/after the palm-mute gate fix; an identical 4 s window."""
    before = ROOT / "out" / "fusion_20260720_183403.wav"
    after = ROOT / "out" / "gatefix_183403.wav"
    # beats 152-160 at 120 bpm: a riff-only stretch (10 palm-muted chugs, 8 of them written
    # >= an 8th, no lead notes) — exactly where the old fixed 80 ms gate clipped every chug.
    start, dur = 76.0, 4.0
    _, stats = assemble("A09", [(before, start, dur), (after, start, dur)], 1.0, fade_out=0.2)
    return {"stats": stats, "window_s": (start, start + dur)}


def _riff_layer(events: list[tuple]) -> Layer:
    v = VOICES["rhythm"]
    notes: list[Note] = []
    t = 0.0
    for sw, dur, vel, chord, tech in events:
        if sw != "-":
            notes.append(Note(swara=sw, oct=-2, start=round(t, 4), dur=dur, vel=vel,
                              chord=chord, technique=tech))
        t += dur
    return Layer(role="rhythm", instrument=v.instrument, program=v.program,
                 channel=v.channel, pan=v.pan, notes=notes)


def _bass_from(riff: Layer, n_beats: int) -> Layer:
    """Bass follows the riff's on-beat roots an octave below (the product's rule)."""
    v = VOICES["bass"]
    notes = []
    for b in range(n_beats):
        sounding = [n for n in riff.notes if n.start <= b < n.start + n.dur]
        if sounding:
            notes.append(Note(swara=sounding[0].swara, oct=-3, start=float(b), dur=0.5, vel=96))
    return Layer(role="bass", instrument=v.instrument, program=v.program, channel=v.channel,
                 pan=v.pan, notes=notes)


def _drums(n_beats: int) -> Layer:
    """One plain metal beat, identical under both riffs (isolates the guitar)."""
    hits = [DrumHit(drum="crash", start=0.0, dur=1.0, vel=100)]
    for b in range(0, n_beats, 2):
        hits += [DrumHit(drum="kick", start=float(b), vel=104),
                 DrumHit(drum="kick", start=b + 0.5, vel=92)]
    for b in range(1, n_beats, 2):
        hits.append(DrumHit(drum="snare", start=float(b), vel=110))
    for k in range(n_beats * 2):
        hits.append(DrumHit(drum="hhat", start=k * 0.5, vel=72 if k % 2 else 84))
    return Layer(role="drums", channel=9, hits=hits)


def a10() -> dict:
    """Same tempo, same Bhairav pitch set (S r G m P d, low register): a melody-riff that
    changes pitch on every 8th, vs a grounded chug riff on low Sa — palm-muted chugs,
    power-chord accents on Sa and the komal-Re (r+d) chord, two short silences."""
    seq = ["S", "r", "G", "m", "P", "m", "G", "r", "S", "r", "G", "P", "d", "P", "G", "r"]
    melody = [(sw, 0.5, 100, None, None) for sw in seq]
    pm, pc = "palm_mute", ["P"]
    chug = [("S", 0.5, 118, pc, None),
            ("S", 0.25, 96, None, pm), ("S", 0.25, 82, None, pm),
            ("S", 0.5, 104, None, pm),
            ("S", 0.25, 92, None, pm), ("S", 0.25, 80, None, pm),
            ("r", 0.75, 122, ["d"], None), ("-", 0.25, 0, None, None),
            ("S", 0.25, 100, None, pm), ("S", 0.25, 84, None, pm),
            ("S", 0.25, 96, None, pm), ("S", 0.25, 82, None, pm),
            ("S", 0.5, 118, pc, None),
            ("S", 0.25, 96, None, pm), ("S", 0.25, 82, None, pm),
            ("S", 0.5, 104, None, pm),
            ("S", 0.25, 92, None, pm), ("S", 0.25, 80, None, pm),
            ("-", 0.5, 0, None, None),
            ("S", 0.25, 104, None, pm), ("S", 0.25, 86, None, pm),
            ("r", 1.25, 124, ["d"], None)]
    out = {}
    for tag, events in (("a", melody), ("b", chug)):
        riff = _riff_layer(events)
        layers = [riff, double_track(riff), _bass_from(riff, 8), _drums(9)]
        c = comp(layers)
        out[tag] = render_comp(c, f"A10_{tag}")
        changes = sum(1 for x, y in zip(riff.notes, riff.notes[1:]) if x.swara != y.swara)
        out[f"{tag}_pitch_changes"] = f"{changes}/{len(riff.notes) - 1}"
    _, stats = assemble("A10", [(out["a"], 0, 4.0), (out["b"], 0, 4.0)], 0.75, fade_out=0.2)
    return {"stats": stats, "pitch_changes": (out["a_pitch_changes"], out["b_pitch_changes"])}


NOTE_START_BEAT = 1.0   # the sitar enters one beat into each N clip...
NOTE_CUT_S = 0.2        # ...and the clip is cut from 0.2 s, so note i sounds at (start + beats before i) * spb - cut
N3_ACHAL_FROM = 7       # N3 events from this index on are the achal tail (Sa, Pa, upper Sa)


def note_events() -> dict[str, list[tuple]]:
    """The twelve-notes clips, as (swara, oct, beats) events ('-' = rest). Shared with the
    keyboard video (keyboard_video.py), which draws each key as its note sounds.
    N1: the seven shuddha notes up and down. N2: each shuddha note then its komal. N3: shuddha
    Ma then tivra Ma (resolving to Pa), then the two achal notes, Sa and Pa, and upper Sa."""
    up = ladder(["S", "R", "G", "m", "P", "D", "N", "S"], 0, +1)
    down = ladder(["S", "N", "D", "P", "m", "G", "R", "S"], 1, -1)
    n1 = [(sw, o, 0.75) for sw, o in up[:-1]] + [(up[-1][0], up[-1][1], 1.5)] + [(sw, o, 0.75) for sw, o in down[1:-1]] + [("S", 0, 2.5)]
    n2: list[tuple] = []
    for hi, lo in (("R", "r"), ("G", "g"), ("D", "d"), ("N", "n")):
        n2 += [(hi, 0, 1.0), (lo, 0, 1.25), ("-", None, 0.75)]
    n3 = [("m", 0, 1.5), ("M", 0, 2.0), ("-", None, 1.0), ("m", 0, 1.5), ("M", 0, 1.5), ("P", 0, 2.5), ("-", None, 1.0),
          ("S", 0, 1.25), ("P", 0, 1.25), ("S", 1, 2.5)]
    assert n3[N3_ACHAL_FROM][0] == "S"
    return {"N1": n1, "N2": n2, "N3": n3}


def n_clips() -> dict:
    """Render the twelve-notes clips, Sa = C so the sound matches the drawn keyboard.
    Chromatic by design, so the raga check is off."""
    stats = {}
    for cid, ev in note_events().items():
        total = sum(d for *_, d in ev)
        c = comp([drone(total + 2, soft=True), sitar_line(ev, shaped=False, start=NOTE_START_BEAT)]).model_copy(update={"sa": 60})
        wav = render_comp(c, f"{cid}_src", check_raga=False)
        _, stats[cid] = assemble(cid, [(wav, NOTE_CUT_S, (total + 1.0) * SEC_PER_BEAT + 0.6)], 0, fade_out=0.5)
        visuals(cid)
    return stats


CLIPS = {"A02": a02, "A03": a03, "A04": a04, "A05": a05, "A06": a06, "A09": a09, "A10": a10, "N": n_clips}


def main() -> None:
    import sys
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    only = set(sys.argv[1:])
    for cid, fn in CLIPS.items():
        if only and cid not in only:
            continue
        report[cid] = fn()
        print(cid, report[cid])
    for cid in ("A02", "A03", "A04", "A05", "A06b", "A06c", "A06bc", "A09", "A10"):
        if not only or cid.rstrip("bc") in only or cid[:3] in only:
            visuals(cid)
    print("soundfonts: base =", base_soundfont().name,
          "| extras =", [e.name for e in present_extras()])


if __name__ == "__main__":
    main()
