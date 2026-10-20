"""K1–K3: the twelve-notes slides' keyboard, drawn by the clip itself in sync with its sound.

The deck can only start a clip with its slide, never on a build click, and sound beside a
separately animated keyboard drifts. So the keyboard is IN the clip: each key appears or lights
at its note's onset (times from make_clips.note_events, the same events the audio was rendered
from). Frames are the deck's own `keyboard()` drawing, screenshotted on the slide's background
and cropped to `KB_REGION`, so the clip sits seamlessly on the slide. The clip ends on a long
silent hold of its final frame, because the deck loops clips.

    uv run python talk/audio/make_clips.py N     # the audio (N1–N3) first
    uv run python talk/audio/keyboard_video.py   # then K1–K3 (.mp4 + first-frame .png)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "deck"))
import keyboard as kb  # noqa: E402  (the deck's keyboard drawing and geometry, Sahaj style)
import make_clips as mc  # noqa: E402  (the note events and timing the audio used)
import preview  # noqa: E402  (page wrapper + headless Chrome)

HOLD_S = 45.0            # silent hold on the final frame, so the deck's loop never restarts mid-talk
FRAMES = mc.BUILD / "keyboard_sahaj"
State = tuple[frozenset[str], str | None, bool, str]   # visible keys, lit key, achal ring, phase label
K4_REGION = (228, 282, 1460, 440)   # the keyboard plus the phase label under it


def key_of(swara: str) -> str:
    return swara   # swara letters are the key ids (S R G m P D N whites; r g d n M blacks)


def _label(i: int, phases: list[tuple[int, str]] | None) -> str:
    return next((lab for k, lab in reversed(phases or []) if i >= k), "")


def timeline(cid: str, events: list[tuple], start: frozenset[str],
             phases: list[tuple[int, str]] | None = None) -> list[tuple[float, State]]:
    """(onset seconds, keyboard state) for every change: a note lights its key (and reveals it),
    a rest unlights; N3's tail rings Sa and Pa as achal; `phases` names what is playing."""
    spb = mc.SEC_PER_BEAT
    visible, achal, beat = set(start), False, 0.0
    out: list[tuple[float, State]] = [(0.0, (frozenset(visible), None, False, _label(0, phases)))]
    for i, (sw, _octv, dur) in enumerate(events):
        t = (mc.NOTE_START_BEAT + beat) * spb - mc.NOTE_CUT_S
        if cid == "N3" and i >= mc.N3_ACHAL_FROM:
            achal = True
        lit = None if sw == "-" else key_of(sw)
        if lit:
            visible.add(lit)
        out.append((t, (frozenset(visible), lit, achal, _label(i, phases))))
        beat += dur
    end = (mc.NOTE_START_BEAT + beat) * spb - mc.NOTE_CUT_S
    out.append((end, (frozenset(visible), None, achal, _label(len(events) - 1, phases))))
    return out


def frame(state: State, blobs: dict[str, str], dim: frozenset[str] = frozenset()) -> Path:
    """Screenshot one keyboard state on the slide's background (cached by state)."""
    visible, lit, achal, label = state
    tag = "".join(ch for ch in label if ch.isalnum())[:12]
    name = f"{'-'.join(sorted(visible)) or 'none'}__{lit or 'off'}__{int(achal)}__{'-'.join(sorted(dim))}__{tag}.png"
    png = FRAMES / name
    if not png.exists():
        body = "".join(kb.keyboard(set(visible), lit, achal, dim=set(dim)))
        if label:
            body += (f'<p style="position:absolute;left:236px;top:654px;width:1440px;text-align:center;font-family:{kb.SANS};'
                     f'font-size:44px;font-weight:800;color:{kb.INDIGO}">{label}</p>')
        section = f'<section style="background:{kb.PAGE};font-family:{kb.SANS}">{body}</section>'
        src = FRAMES / "frame.html"
        src.write_text(preview.page(section, blobs))
        subprocess.run([preview.CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1920,1080", "--virtual-time-budget=4000", f"--screenshot={png}", src.as_uri()],
                       check=True, capture_output=True)
    return png


def video(cid: str, out_id: str, start: frozenset[str], events: list[tuple] | None = None,
          dim: frozenset[str] = frozenset(), phases: list[tuple[int, str]] | None = None,
          region: tuple[int, int, int, int] = kb.KB_REGION) -> dict:
    events = events if events is not None else mc.note_events()[cid]
    wav = mc.OUT / f"{cid}.wav"
    tl = timeline(cid, events, start, phases)
    total = mc.duration_s(wav) + HOLD_S
    blobs = preview.blob_map()
    lines: list[str] = []
    for (t, st), nxt in zip(tl, [t for t, _ in tl[1:]] + [total]):
        lines += [f"file '{frame(st, blobs, dim)}'", f"duration {max(nxt - t, 0.001):.4f}"]
    lines.append(f"file '{frame(tl[-1][1], blobs, dim)}'")
    lst = FRAMES / f"{out_id}.txt"
    lst.write_text("\n".join(lines) + "\n")
    x, y, w, h = region
    mp4, still = mc.OUT / f"{out_id}.mp4", mc.OUT / f"{out_id}.png"
    mc.ff("-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(wav),
          "-filter_complex", f"[0:v]crop={w}:{h}:{x}:{y},fps=30,format=yuv420p[v];[1:a]apad=whole_dur={total:.3f}[a]",
          "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-tune", "stillimage", "-crf", "18",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(mp4))
    mc.ff("-i", str(frame(tl[0][1], blobs, dim)), "-vf", f"crop={w}:{h}:{x}:{y}", "-frames:v", "1", str(still))
    return {"clip": out_id, "states": len({st for _, st in tl}), "seconds": round(total, 2)}


def main() -> None:
    FRAMES.mkdir(parents=True, exist_ok=True)
    whites, komal = kb.SHUDDHA, kb.KOMAL
    only = set(sys.argv[1:])
    for cid, out_id, start in (("N1", "K1", frozenset()), ("N2", "K2", whites), ("N3", "K3", whites | komal)):
        if not only or out_id in only:
            print(video(cid, out_id, start))
    if not only or "K4" in only:                     # Bhairav: aroha, avaroha, chalan (raga_clip.py)
        import raga_clip
        allowed = frozenset(raga_clip.BH["allowed"])
        print(video("N4", "K4", kb.ALL, events=raga_clip.n4_events(), dim=kb.ALL - allowed,
                    phases=raga_clip.PHASES, region=K4_REGION))


if __name__ == "__main__":
    main()
