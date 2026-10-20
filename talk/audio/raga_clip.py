"""N4 / K4: Bhairav's AROHA (the way up), AVAROHA (the way down) and two CHALAN phrases (how it
really moves, with the slow sway on komal re and dha) — every note from the encoded raga data
(src/raga.py), Sa = C so the sound matches the drawn keyboard, rendered free (no LLM).

    uv run python talk/audio/raga_clip.py        # N4.wav, then K4.mp4/.png via keyboard_video
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_clips as mc  # noqa: E402

BH = mc.BH
# (index of the first event of each phase, its label) — drawn into the clip by keyboard_video
PHASES = [(0, "Aroha · the way up"), (9, "Avaroha · the way down"), (18, "Chalan · how it really moves")]


def n4_events() -> list[tuple]:
    up = mc.ladder(BH["aroha"], 0, +1)
    down = mc.ladder(BH["avaroha"], 1, -1)
    aroha = [(sw, o, 0.75) for sw, o in up[:-1]] + [(up[-1][0], up[-1][1], 1.5), ("-", None, 1.0)]
    avaroha = [(sw, o, 0.75) for sw, o in down[:-1]] + [(down[-1][0], down[-1][1], 1.5), ("-", None, 1.0)]
    c1, c3 = mc.collapse(BH["chalan"][0]), mc.collapse(BH["chalan"][2])     # S r S · d P G m r S
    assert c1 == ["S", "r", "S"] and c3 == ["d", "P", "G", "m", "r", "S"]
    chalan = [("S", 0, 0.5), ("r", 0, 2.25), ("S", 0, 1.5), ("-", None, 0.75),
              ("d", 0, 2.25), ("P", 0, 0.5), ("G", 0, 0.75), ("m", 0, 0.75), ("r", 0, 2.25), ("S", 0, 2.5)]
    events = aroha + avaroha + chalan
    assert len(aroha) + len(avaroha) == PHASES[2][0] and len(aroha) == PHASES[1][0]
    return events


def main() -> None:
    ev = n4_events()
    total = sum(d for *_, d in ev)
    c = mc.comp([mc.drone(total + 2, soft=True),
                 mc.sitar_line(ev, shaped=True, start=mc.NOTE_START_BEAT)]).model_copy(update={"sa": 60})
    wav = mc.render_comp(c, "N4_src")
    _, stats = mc.assemble("N4", [(wav, mc.NOTE_CUT_S, (total + 1.0) * mc.SEC_PER_BEAT + 0.6)], 0, fade_out=0.5)
    print("N4", stats)


if __name__ == "__main__":
    main()
