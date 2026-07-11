"""
The agentic layer — CrewAI Flow, agents, and the contracts that bind them.

Phase 2 lives here. This __init__ does one job: put the deterministic core
(`src/`) on the import path so crew modules can `from raga import ...` /
`from render import ...`, matching the flat-layout idiom the rest of the repo
uses (see demo.py, tests/). Nothing here touches an LLM or the network at
import time — that stays true for the whole `crew` package until an agent is
actually run.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
