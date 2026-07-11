# Prompts

Agent prompts live here as **external config**, one markdown file per agent —
deliberately NOT inline in Python. Keeping them as files makes them reviewable,
diffable, and swappable without touching code (a best practice from the CrewAI
research; see CLAUDE.md).

Planned files (added as each agent is built, Phase 2):

| File | Agent | Role |
|---|---|---|
| `raga_grammar.md` | RagaGrammar | generator — melodic line, seeded by pakad/chalan |
| `metal_riff.md`   | MetalRiff   | generator — riff in the subgenre's feel/register |
| `tala.md`         | Tala        | generator — maps subgenre meter ↔ tala, places the groove |
| `ustad.md`        | Ustad       | critic — legality/theory; calls `validate_composition` |
| `rasik.md`        | Rasik       | critic — aesthetic taste; checks the pakad is present |
| `conductor.md`    | Conductor   | arbiter — bounded debate, issues accept/revise |

Prompt hygiene (from CLAUDE.md): tight role/goal, `{placeholders}` for dynamic
raga/tala/subgenre facts injected from the data libraries, and critics anchored
to explicit rubrics grounded in the encoded pakad/chalan (criteria, not vibes).
