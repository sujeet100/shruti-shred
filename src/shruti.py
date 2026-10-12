"""
THE 22 SHRUTIS — the Hindustani microtonal grid a swara's intonation is taken from.

Sujit, 2026-10-12: "the calculation for notes is as per the 22 shruti system (Hindustani, not
Carnatic)". The table below is the standard Hindustani 22-shruti scheme in 5-limit just
intonation — the shruti names, ratios and the swara each conventionally carries — as listed on
the Sinhala Wikipedia "Shruti (music)" page (the full named table); the English Wikipedia
"Shruti (music)" article describes the same 22-tone 5-limit scheme and names Darbari's ati-komal
gandhar its best-known example. FLAG (both pages say it): there is no single standardised set of
shruti sizes, and performers vary — so a raga's shruti choice is data, sourced per raga.

Each komal swara has TWO shrutis — the lower is its ati-komal form (Ga: Dayavanti 32/27, 294 c,
below Ranjani 6/5, 316 c). Pure data and arithmetic: no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Final



@dataclass(frozen=True)
class Shruti:
    number: int
    name: str
    ratio: Fraction

    @property
    def cents(self) -> float:
        return 1200 * math.log2(float(self.ratio))


SHRUTIS: Final = (
    Shruti(1, "Kshobhini", Fraction(1, 1)),       # Sa
    Shruti(2, "Tivra", Fraction(256, 243)),       # komal Re
    Shruti(3, "Kumdavati", Fraction(16, 15)),
    Shruti(4, "Manda", Fraction(10, 9)),
    Shruti(5, "Chandovati", Fraction(9, 8)),      # shuddha Re
    Shruti(6, "Dayavanti", Fraction(32, 27)),     # komal Ga — the lower, ati-komal shruti
    Shruti(7, "Ranjani", Fraction(6, 5)),
    Shruti(8, "Raktika", Fraction(5, 4)),         # shuddha Ga
    Shruti(9, "Rudri", Fraction(81, 64)),
    Shruti(10, "Krodhi", Fraction(4, 3)),         # shuddha Ma
    Shruti(11, "Vajrika", Fraction(27, 20)),
    Shruti(12, "Prasarini", Fraction(45, 32)),    # tivra Ma
    Shruti(13, "Priti", Fraction(729, 512)),
    Shruti(14, "Marjani", Fraction(3, 2)),        # Pa
    Shruti(15, "Kshiti", Fraction(128, 81)),      # komal Dha — the lower, ati-komal shruti
    Shruti(16, "Rakta", Fraction(8, 5)),
    Shruti(17, "Sandipini", Fraction(5, 3)),
    Shruti(18, "Alapini", Fraction(27, 16)),      # shuddha Dha
    Shruti(19, "Madni", Fraction(16, 9)),         # komal Ni
    Shruti(20, "Rohini", Fraction(9, 5)),
    Shruti(21, "Ramya", Fraction(15, 8)),
    Shruti(22, "Ugra", Fraction(243, 128)),       # shuddha Ni
)
SOURCES: Final = ("Sinhala Wikipedia 'Shruti (music)' — the named 22-shruti table (ratios, cents, swaras)",
                  "English Wikipedia 'Shruti (music)' — the 22-tone 5-limit scheme; Darbari's ati-komal Ga")


def shruti(number: int) -> Shruti:
    return SHRUTIS[number - 1]


def offset_cents(semitone: int, number: int) -> float:
    """How far the shruti sits from the equal-tempered pitch `semitone` steps above Sa, in cents
    (negative = lower)."""
    return round(shruti(number).cents - 100 * semitone, 2)


def check_shrutis() -> list[str]:
    """Data hygiene: 22 shrutis, numbered in order, rising strictly inside one octave."""
    problems = []
    if len(SHRUTIS) != 22 or [s.number for s in SHRUTIS] != list(range(1, 23)):
        problems.append("there must be 22 shrutis numbered 1-22")
    cents = [s.cents for s in SHRUTIS]
    if cents != sorted(cents) or cents[0] != 0 or cents[-1] >= 1200:
        problems.append("shrutis must rise strictly from Sa inside one octave")
    return problems
