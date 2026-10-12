# Shruti Shred: What Domain Knowledge Does to an Agentic System

**Subtitle:** Eleven agents compose metal in a classical raga on stage, and the design decisions behind them: what belongs to a model, what belongs to code, and where the rules come from.

## Abstract

Ask a capable model to compose metal in a Hindustani raga and it returns something
plausible that nobody can verify. The model has seen both traditions and knows the
rules of neither, so a listener who knows the raga hears errors the prompt gave you no
means to detect. Any domain with real rules produces the same failure, from clinical
coding to contract drafting. The system carries no representation of the domain, so
nothing inside it can separate correct output from plausible output.

This talk makes that argument with a system you can hear. Eleven agents compose a piece
of raga and metal fusion live on stage, and the patterns coordinating them are
domain-agnostic by design. Correctness is supplied by the domain knowledge encoded
around those patterns, in three forms the talk works through. Verified data gives the
deterministic code and the agents a single source for every rule, so a model reasons
over the rulebook and never authors it. Verifiers turn an aesthetic complaint such as
"this riff sounds light" into budgets a generator has to meet before its output is
accepted. Guardrails hold the rules an agent has no authority to overrule.

The second question is where an agent belongs at all. A question with a checkable
answer belongs in deterministic code, and a question whose answer is taste belongs to a
model. Most of this system sits in the hybrid between the two: code establishes
legality while an agent explains the violation, code measures the arrangement while an
agent evaluates it, code builds a menu of legal edits while an agent chooses one. The
same discipline decides the roster. An early design drew one agent per instrument and
reached about fifteen. Drawing one agent per decision produced eleven, each with a
responsibility you can state in a sentence.

The patterns are covered in the order the system uses them, with the foundations
assumed rather than explained: **prompt chaining**, **routing**, **ReAct** tool use,
**structured output** and **memory**. Above those, **multi-agent collaboration** in its
role-based form over a shared **blackboard** has two creative agents build on each
other's work instead of composing in isolation. The **evaluator-optimizer** loop, also
called **generator-critic** or **actor-critic**, separates judgment from generation,
while **cross-reflection** and **LLM-as-a-judge** grade the qualities code cannot
measure. When the judges disagree, **multi-agent debate** under bounded rounds and an
**arbitrator** ends the argument on a clock. The talk also covers the patterns this
system refuses, starting with **orchestrator-workers** and autonomous delegation, which
trade away control a live system cannot surrender.

You leave able to name the pattern your problem needs, decide which parts of your
system should not be agents, and encode your own domain's rules into the parts that
are. No knowledge of either musical tradition is required, and the composition plays at
the end.
