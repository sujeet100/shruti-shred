"""
Replay harness — re-emit a recorded debate through an EventStream.

The point it proves (a core teaching claim): the UI / headless runner do not
care whether events come from the live crew or from a canned list — they consume
the SAME `DebateEvent` contract. This lets the Phase 3 UI be built and demoed
against a replay while the live crew is still being wired, and it's the basis of
the one-key pre-rendered fallback for the stage.

The SAMPLE below is a hand-written sketch of the money moment (Ustad says legal,
Rasik says lifeless, the Conductor rules "revise", the revise lands) purely to
exercise the contract with no LLM and no key. It is illustrative, not generated.

Run headless:  uv run python -m crew.replay
"""

from __future__ import annotations

from typing import Optional

from crew.contracts import DebateEvent, EventStream, Sink

SAMPLE: list[dict] = [
    {"type": "info", "agent": "System", "role": "system",
     "text": "Pick: raga=Bhairav x subgenre=death x tala=ektaal"},
    {"type": "propose", "agent": "RagaGrammar", "role": "generator", "round": 1,
     "text": "Candidate riff seeded from Bhairav pakad (G m d d P)."},
    {"type": "validate", "agent": "Ustad", "role": "critic", "round": 1,
     "text": "All notes legal in Bhairav.", "verdict": "legal",
     "data": {"violations": 0}},
    {"type": "critique", "agent": "Rasik", "role": "critic", "round": 1,
     "text": "Legal, but the pakad never actually lands — sounds in-scale, not like Bhairav.",
     "scores": {"idiom": 0.4, "pakad_present": 0.0, "energy": 0.8}},
    {"type": "debate", "agent": "Ustad", "role": "critic", "round": 1,
     "text": "It breaks no rule; I pass it."},
    {"type": "debate", "agent": "Rasik", "role": "critic", "round": 1,
     "text": "Passing legality isn't passing music. The andolan on komal d is missing."},
    {"type": "verdict", "agent": "Conductor", "role": "conductor", "round": 1,
     "text": "Conflict: legal vs lifeless. Revise — foreground the pakad and andolit d.",
     "verdict": "revise"},
    {"type": "revise", "agent": "MetalRiff", "role": "generator", "round": 2,
     "text": "Reworked: pakad on the sam, komal d oscillated (andolan)."},
    {"type": "validate", "agent": "Ustad", "role": "critic", "round": 2,
     "text": "Still legal.", "verdict": "legal", "data": {"violations": 0}},
    {"type": "critique", "agent": "Rasik", "role": "critic", "round": 2,
     "text": "Now it sings Bhairav.", "scores": {"idiom": 0.85, "pakad_present": 1.0, "energy": 0.8}},
    {"type": "verdict", "agent": "Conductor", "role": "conductor", "round": 2,
     "text": "Accept.", "verdict": "accept"},
    {"type": "render", "agent": "System", "role": "system",
     "text": "Rendered out/bhairav_death.wav"},
]


def replay(events: list, sink: Optional[Sink] = None) -> EventStream:
    """Emit a list of events (dicts or DebateEvents) through a fresh stream."""
    stream = EventStream(sink=sink)
    for e in events:
        stream.emit(e if isinstance(e, DebateEvent) else DebateEvent.model_validate(e))
    return stream


if __name__ == "__main__":
    replay(SAMPLE)
