You are a creative director for conference talks, with deep taste in motion design, pixel-art game aesthetics, sound design, and live music performance. Help me make a 45-minute technical talk deck as memorable as possible through animation, graphics and audio, without making it gimmicky or risky on stage.

## The talk

**Title:** Shruti Shred: What Domain Knowledge Does to an Agentic System.
**Audience:** software engineers and engineering leaders at a tech conference. Most know LLMs and agents; almost none know Hindustani classical music; some are metalheads.
**Thesis:** asking an LLM to follow a domain's rules gets you output that is *technically correct but lifeless* — legal notes that don't sound like music. Getting to *good* takes three things the model can't supply alone: domain knowledge encoded as data, steering (verifiers, critics with rubrics, bounded debate, local repair), and agentic decomposition (one agent per decision). True for music, and equally for clinical coding, contract drafting, tax rules.

**The system:** eleven LLM agents (Interpreter, Pandit and Riffsmith the composers, Lead and Riff and Orchestra the generators, Arranger the repairer, Ustad/Rasik/Producer the three critics, Conductor the referee) compose Hindustani raga × metal fusion. Code owns legality; models own taste; critics debate on a clock; the Conductor rules.

## Run of show (45 min)

1. **Cold open (1 min):** I play live rhythm guitar over a 60-second generated piece — Raga Bhairav, heavy metal, teentaal (16-beat cycle), 128 BPM, Sa = E. Form: alap → gat → call-and-response between my guitar and the sitar → fast taan climax → tihai (a phrase three times landing on beat one) and a hard stop.
2. **Reveal:** "Eleven agents composed what you just heard. I played the riff they wrote."
3. **Vocabulary (≈4 min, 5 slides):** Hindustani music (drone, melody, cycle); raga and key (sargam Sa Re Ga Ma Pa Dha Ni, komal/tivra, pakad = signature phrase, andolan = slow oscillation on a note); tala and BPM (16-beat teentaal, sam = beat one, khali = the open wave); metal (riff, power chord, palm-mute chug, 8 subgenres with BPM ranges); sections of a piece (alap / gat / antara / taan / tihai mapped to intro / hook / bridge / solo / breakdown).
4. **The problem:** the experiment (LLM given the rules → legal notes, no music), a ladder (prompt → plausible; prompt + rules → correct; knowledge + steering + decomposition → music), "Following the rules gets you correct. It doesn't get you music."
5. **Part 1 — where does an agent belong:** proof vs argument (code vs model), knowledge as data, one agent per decision (15 → 11 agents; of 7 instruments only 2 are agents), the roster.
6. **Part 2 — eight patterns:** structured output, guardrail as a type (the critic has no verdict field), verifiers that turn a feeling into a budget, a shared blackboard where two agents build a section together, LLM-as-judge with rubrics, bounded debate with an arbiter ("Debate needs a referee and a clock"), local repair, refused patterns.
7. **Part 3 — war stories:** one complaint with four causes in four layers; the MIDI file that outvoted two reviewers; the prompt that documented a bug; the rule that was backwards (a practitioner corrected us); the framework that silently ignored our settings; testing a multi-agent flow with zero API calls.
8. **Live demo (5 min):** the audience voted a raga × subgenre at minute ~8, it composed in the background, now we open the trace and play the result.
9. **Close:** a decision matrix (code / one model / several agents) and a do/don't checklist.

## Visual identity (already decided)

Pixel-art, point-and-click-adventure look borrowed from the live demo UI: a recording studio with rooms (writers' room, live room, control room, conductor's riser). Every agent is a pixel persona sprite (chibi, 26×32 grid) — the Lead carries a sitar, the Riff a guitar, the Conductor a baton, the Ustad a rulebook. Pixel instruments: sitar, Flying-V, tabla, tanpura, drum kit, amp stack.
Palette: stage-black #08070d, panel #191426, temple gold #f2b53c, saffron #d9702a, neon magenta #ff2e88, drone cyan #38e0cf, ink #ece5d3. Roles are colour-coded: composers gold, generators saffron, critics magenta, conductor cyan.
Type: Press Start 2P for headlines, VT323 for body. Devanagari (स रे ग म प ध नि) rendered as pixel glyphs.

## What the medium can do (hard constraints)

- 16:9 HTML slides (1920×1080), presented from a browser; exports to PDF/PPTX where animation flattens.
- Slide transitions: fade, push, magic move (shared element morphs between slides).
- Build-ins per element on click: fade, rise, drop, left, right, scale, pop — with order.
- Live mini-pages ("embeds") on a slide: sandboxed HTML/CSS/JS, ≤16 KB each, ≤8 per slide, no network, no web fonts, **no clicks or keyboard inside them while presenting** — they run on their own (canvas, SVG, CSS animation, requestAnimationFrame). They cannot play audio reliably.
- Audio/video: short MP4 clips (≤20 MB) that play with sound, either automatically with the slide or on a click. So audio = pre-rendered clips with a visual track (waveform, piano roll, animated sprite).
- Audio I can render for free from our own deterministic engine (no LLM): any note sequence on sitar, distorted/clean/palm-muted guitar, bass, metal drum kit, tabla, tanpura drone, strings — at any tempo and key. The one-shot "just ask the LLM" sample costs one live call.
- I have the full live performance recording and the live demo UI (same pixel world) as fallbacks.

## What I want from you

1. **Signature moments (3–5):** the few animation/audio beats people will remember and retell. For each: what the audience sees and hears, which slide, why it lands the talk's argument (not just looks cool), and how it degrades if it fails.
2. **Per-section ideas:** for each part of the run of show, concrete ideas for animation, graphics and audio. Be specific: "the 16 beats light up around a circle at 128 BPM while a tabla clip plays one cycle; beat one flashes SAM in gold and the room claps on it" beats "add an animated tala."
3. **An audio script:** a numbered list of every audio clip worth making — length, content (notes/instruments/tempo), which slide, auto or on-click — plus the "A/B" pairs that make an argument by ear (e.g. scale run vs real taan; straight Re vs Re with andolan; melody-riff vs chug-riff; clipped palm-mute vs fixed).
4. **Persona storytelling:** how to use the agent sprites as recurring characters across the talk (entrances, speech bubbles, the debate as a scene, the Conductor's ruling), without turning it into a cartoon.
5. **Restraint:** where *not* to animate, and what would distract from the argument or eat the clock. Rank all ideas by impact ÷ effort, and flag anything risky on a conference projector or sound system.

Keep the music facts Hindustani (not Carnatic). Output as sections with tables where useful.
