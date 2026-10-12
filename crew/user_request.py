"""
The user's request, rendered once for every agent that makes a musical decision.

The Interpreter extracts what the system can ENFORCE (raga, key, tala, bpm, ...), and the
composers turn that into a chart. Anything that has no field — the form the user wants, how
the piece should end, who will play over it — used to stop at the Interpreter. The request now
travels verbatim on the brief and the `Arrangement`, and each agent's task template frames it
for its own job; this module only quotes it, so all of them see exactly the same words.

Pure — no LLM, no I/O.
"""

from __future__ import annotations

from typing import Final

_NO_REQUEST: Final = "  (no free-text request — work from the chart alone)"


def render_request(request: str) -> str:
    """The request as an indented, quoted prompt block; a benign line when there is none.

    Contract: the text is never paraphrased or trimmed beyond surrounding whitespace, and a
    multi-line request keeps its line breaks, each indented so it reads as one quotation."""
    text = request.strip()
    if not text:
        return _NO_REQUEST
    return "\n".join(f"  | {line}" if line.strip() else "  |" for line in text.splitlines())
