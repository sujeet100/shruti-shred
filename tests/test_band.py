"""
Tests for the full-band ASSEMBLY (`band_layers`) — pure, no key, no cost.

`band_layers` is the deterministic half of the full band: given the two creative
voices (the lead layer(s) and the riff), it derives the rest — drone from the chart,
bass and drums from the riff, tabla from the tala — and returns the stable layer
order. That collection logic is provable without the LLM; the live `compose_band`
render is the end-to-end confirmation.

Runs as a script (`uv run python tests/test_band.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.band import band_layers  # noqa: E402
from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import VOICES  # noqa: E402


def _arr(*sections: tuple[SectionKind, list[str]]) -> Arrangement:
    secs = [Section(kind=k, bars=1, layers=ls,
                    foreground="lead" if "lead" in ls else ls[0])
            for k, ls in sections]
    draft = ArrangementDraft(raga="darbari", subgenre="progressive", tala="teentaal",
                             bpm=120, motif=["S", "R", "g"], sections=secs)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _lead() -> list[Layer]:
    v = VOICES["sitar"]
    return [Layer(role="lead", instrument=v.instrument, program=v.program, channel=v.channel,
                  notes=[Note(swara="S", oct=0, start=0.0, dur=1.0)])]


def _rhythm() -> Layer:
    v = VOICES["rhythm"]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program, channel=v.channel,
                 notes=[Note(swara="S", oct=-2, start=0.0, dur=1.0, vel=110),
                        Note(swara="S", oct=-2, start=4.0, dur=1.0, vel=110)])


def test_band_layers_collects_every_voice():
    arr = _arr((SectionKind.RIFF, ["rhythm", "drums", "tabla", "drone"]))
    roles = [layer.role for layer in band_layers(arr, _lead(), _rhythm())]
    assert roles[0] == "drone"                                    # drone anchors the list
    assert {"drone", "lead", "rhythm", "bass", "drums", "tabla"} <= set(roles)


def test_band_without_a_riff_has_no_bass_or_drums():
    arr = _arr((SectionKind.ALAAP, ["lead", "tabla", "drone"]))
    roles = [layer.role for layer in band_layers(arr, _lead(), None)]
    assert "bass" not in roles and "drums" not in roles           # no riff -> no bass/drums
    assert {"drone", "lead", "tabla"} <= set(roles)               # tabla still plays the theka


def test_band_layers_derive_bass_and_drums_from_the_riff():
    arr = _arr((SectionKind.RIFF, ["rhythm", "drums", "drone"]))
    layers = band_layers(arr, [], _rhythm())                      # no lead this time
    roles = [layer.role for layer in layers]
    assert "lead" not in roles
    assert {"drone", "rhythm", "bass", "drums"} <= set(roles)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
