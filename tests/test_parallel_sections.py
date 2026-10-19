"""Pure tests for composing the alap, the long taan and the outro AT ONCE after the gat
(`lead._prefetch_sections`): they genuinely overlap, each still answers to its own checks, they
remember the gat but not each other, and the song comes out the same as in timeline order. No API."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_lead as T  # noqa: E402
from crew.contracts import Gat, LeadNote, LeadPhrase, PhrasePlan, SectionKind  # noqa: E402
from crew.lead import generate_lead  # noqa: E402


def _arr():
    return T._gat_arr((SectionKind.ALAAP, 2, "intro"), (SectionKind.ALAAP, 1, "mukhada"),
                      (SectionKind.TAAN, 1, "taan_long"), (SectionKind.OUTRO, 1, "outro"))


def _plain(swara: str, beats: float) -> LeadPhrase:
    plan = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat"], climax_and_sam="Sa")
    return LeadPhrase(phrase_plan=plan, notes=[LeadNote(swara=swara, dur=beats)])


class _Recorder:
    """A thread-safe gen_fn answering by section role, recording when each call ran and what it saw."""

    def __init__(self, delay: float = 0.15):
        self.calls, self.delay, self._lock = [], delay, threading.Lock()

    def __call__(self, span, arr, memory, *, feedback=None):
        start = time.monotonic()
        time.sleep(self.delay)
        role = span.section.form_role
        with self._lock:
            self.calls.append((role, start, time.monotonic(), [m.form_role for m in memory]))
        return {"intro": T._good_intro(), "taan_long": _plain("S", span.length),
                "outro": _plain("S", span.length)}.get(role, _plain("S", span.length))


def _gat_fn(arr, *, needs_manjha, needs_antara, needs_amad):
    return Gat(mukhada=T._good_head())


def _run(parallel: bool):
    rec = _Recorder()
    layers, events = generate_lead(_arr(), gen_fn=rec, gat_fn=_gat_fn, parallel=parallel)
    return rec, layers, events


def test_the_three_sections_run_at_the_same_time():
    rec, _, _ = _run(parallel=True)
    first = {}
    for role, start, end, _ in rec.calls:
        first.setdefault(role, (start, end))
    starts = [first[r][0] for r in ("intro", "taan_long", "outro")]
    ends = [first[r][1] for r in ("intro", "taan_long", "outro")]
    assert max(starts) < min(ends), "the first calls of the three sections should overlap"


def test_in_order_they_do_not_overlap():
    rec, _, _ = _run(parallel=False)
    spans = sorted((start, end) for _, start, end, _ in rec.calls)
    assert all(a_end <= b_start + 1e-3 for (_, a_end), (b_start, _) in zip(spans, spans[1:]))


def test_they_remember_the_gat_and_not_each_other():
    rec, _, _ = _run(parallel=True)
    seen = {role: mem for role, _, _, mem in rec.calls}
    assert seen["taan_long"] == ["mukhada"] and seen["outro"] == ["mukhada"]   # no alap, no taan
    assert "mukhada" in seen["intro"]


def test_the_song_comes_out_the_same_either_way():
    _, par, _ = _run(parallel=True)
    _, seq, _ = _run(parallel=False)
    notes = lambda layers: [[(n.swara, n.start, n.dur) for n in layer.notes] for layer in layers]  # noqa: E731
    assert notes(par) == notes(seq)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
