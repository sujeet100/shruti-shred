# Composing an Imdadkhani sitar gat — a guide for the composer agents

This guide collects what we know, with sources, about how a sitar gat is built in the
Imdadkhani / Etawah gharana (Imdad Khan → Enayat Khan → Vilayat Khan, Imrat Khan, and on to
Shujaat Khan, Shahid Parvez, Budhaditya Mukherjee and Arvind Parikh). It is written for the
Composer and Lead agents: what each line of the gat does, how the strokes carry the melody,
where silence and chikari go, which ornaments belong on the composed head and which belong to
improvisation, and how the cycle hands back to the mukhda. It merges three bodies of evidence:
the facts already verified and encoded in `src/gats.py` (2026-07-20 and 2026-10-12), a new
research pass on 2026-10-12, and Sujit's own practice and his guruji's teaching. The
GPT guide Sujit gathered separately has been compared with it rule by rule in §12, and the
Parikh pages it cited were read directly and folded into the body.

Every rule carries a grade, so an agent prompt or verifier can decide how hard to lean on it:

- **VERIFIED** means two or more independent, reliable Hindustani sources agree.
- **SINGLE** means one reliable source says it and nothing found contradicts it. Prompt it as
  a tendency, never as a hard rule.
- **FLAGGED** means the sources disagree or only weak sources say it. It is recorded so we
  know about it, not to be encoded.
- **GURUJI** marks Sujit's guruji's teaching (oral tradition). It counts as a practitioner
  source, cited as in `src/raga.py`.
- **ENGINE** marks our own engineering choice, not a sourced musical fact.

Section 11 lists honestly what no source settled. Nothing here was invented to fill a hole.

---

## 1. What a gat is in this gharana

A gat is a short, fixed instrumental composition in a tala cycle, the home the performer keeps
returning to between improvisations. In this gharana the cycle is **teentaal almost
exclusively** (VERIFIED: Deepak Raja says the gharana played almost entirely in teentaal, with
ektaal rare and reserved for khayal; Nad Sadhna says its gats rest on the Masitkhani style). So
the agents should assume 16 matras grouped 4+4+4+4, with the sam on matra 1, the tali on 5 and
13, and the khali on 9.

The gat has **four lines**, grouped in two pairs (VERIFIED: Parikh's FAQ and his article
"Bandish on the Instruments"). Parikh's structure note qualifies this with "barring some
exceptions", so a gat that drops or merges a line is still a gat, which is why `form: song`
can treat the gat as optional.

| Line | Belongs to | Job | Register |
|---|---|---|---|
| **Mukhda** (sthayi line 1) | sthayi | the home and the hook; its approach lands every sam | madhya, modest peak |
| **Manjha** (sthayi line 2) | sthayi | takes the melody *into* the lower octave and back | mandra ↔ madhya |
| **Antara** (antara line 1) | antara | rises to the upper octave and peaks there | madhya → taar |
| **Amad** (antara line 2) | antara | the composed descent back to where the mukhda starts | taar → madhya |

The whole gat spans **two and a half to three octaves** (Parikh). The register arc of
home, then low, then high, then home again is the gat's large-scale shape. The return is
*composed* into the gat (amad) rather than left to chance.

Two style facts shape everything below. Vilayat Khan composed gats **as vocal bandishes**
("you have to sing to be able to play"), and some of his gats began as khayals with lyrics
(VERIFIED: Parikh, Deepak Raja). That **gayaki ang** tilts the balance toward melody: "the
ratio of melodic density to stroke density had to be tilted sharply in favour of melodic
density" (Raja). Nad Sadhna adds that his left hand sustained "a note for a much longer
duration" (VERIFIED). In practice this means fewer, longer-ringing strokes, each carrying
more pitches through meend.

Vilayat Khan's gats fall into **three categories** (VERIFIED: Parikh's FAQ "Evolution of
gats", read directly on 2026-10-12, plus Ramprapanna Bhattacharya):

- **(a)** Right-hand bols are the main basis; the left hand plays a relatively simple role.
- **(b)** The two hands contribute about equally; vocal and instrumental style play "equal
  roles".
- **(c)** The left hand contributes "almost 70-80% of the gat compositions"; the right hand
  mainly supports the vocalised idiom.

All three belong to the gharana, so the composer can choose the category deliberately per
piece. His own "Vilayatkhani gat" sits in madhya laya, between vilambit and drut (SINGLE:
Ramprapanna). Parikh also traces the arc behind them. The early "purak baj" left hand stayed
on one note while the right hand filled gaps in qawwali. Imdad Khan's 1904 recordings still
show the right hand dominating. Enayat Khan brought the hands to near-equality, and his gats
"revealed a specific bol pattern, especially for drut gats".

---

## 2. The stroke frame: how the right hand makes the rhythm

The bol (stroke) pattern *is* the gat's identity. Parikh's own words: without the bol
pattern "they are just vilambit gats" (VERIFIED, already in `src/gats.py`). Two consequences
follow for the agents. The rhythm of a gat is fixed by its frame before a single swara is
chosen. And the melody is then laid onto that frame, with the left hand moving the pitch
while the right hand keeps the pattern.

### 2.1 The stroke vocabulary

- The sitar's language rests on **four basic strokes** (SINGLE, Parikh's "Origin of the
  Sitar", read directly; the GPT guide gives the same four): **da**, the inward stroke;
  **ra**, the outward stroke; **dir**, "the inward and outward strokes in quick succession";
  and **rda**, "the outward and inward in quick succession". Our `BOL_WORDS` comment says no
  source gives rda's stroke order, which is now out of date. Rda is `r` then `da`, 1:1.
- da is the strong stroke and ra the softer return. On sitar, da is the main stroke; sarod
  reverses this (SINGLE: Parikh FAQ).
- Sitar gats use **dir** extensively; sarod gats use **dra** (SINGLE: Parikh FAQ). That is
  why `dra` is deliberately left out of `BOL_WORDS`.
- The compound words are stroke patterns given as **ratios**, so that one word can fill a
  quarter, a half or a whole matra (Sujit, encoded in `gats.BOL_WORDS`):
  `dir` = di r (1:1), `dara` = da ra (1:1), `dar` = da r (2:1), `dadir` = da di r (2:1:1),
  `darada`, `daradara`.
- In drut gats the gharana keeps its bols honest at speed. "Dir-dir" is played cleanly, never
  faked by changing the original bol at top tempo (SINGLE: Ramprapanna).

### 2.2 The Masitkhani grid (VERIFIED)

```
matra:  1   2   3   4    5   6    7   8  | 9   10  11  12   13  14   15  16
bol:    da  da  ra  dir  da  dir  da  ra | da  da  ra  dir  da  dir  da  ra
        X               2                 0                 3
                                                    └──── mukhda 12-16 ────┘→ sam
```

The 8-bol unit `dir da dir da ra | da da ra` appears twice, phase-locked so that `dir` falls
on matras 4, 6, 12 and 14. The **mukhda is a five-matra anacrusis**. It launches on matra 12,
inside the khali half of the cycle, and lands its arrival stroke ON the sam. That
anticipation and arrival is the hook mechanism of the whole form (Parikh, Vishwamohini,
Lokogandhar).

Parikh names the tension precisely: "the Masitkhani format answers to the 4-4-4-4 symmetry of
Teental with an asymmetric **5-3-5-3** stroke pattern, while incorporating the symmetry through
a cadentially synchronised use of the Da-Dir-Da-Ra stroke-set" (VERIFIED: Parikh's "Origin of
the Sitar" and the GPT guide citing it; the 5+3 split also matches our moving/settling groups,
§2.5). The strokes group in fives and threes while the tabla keeps fours, and the two
re-align at the sam. That re-alignment is the arrival the listener feels. The traditional
tempo was **about 60 bpm**, and Vilayat Khan slowed it to as low as 40 (SINGLE: Parikh).

The new research found a second notation source using exactly this grid: three textbook drut
gats (Yaman, Bhupali, Bhimpalasi) from the Sharada Kala Kendra (§3.5). Every one puts
`dir` on 12, 14, 4 and 6, with a five-matra pickup from 12 into the sam. The source's lineage
is unknown and its style is standard Bhatkhande teaching, so it confirms the *grid*, not
anything specifically Imdadkhani. It does raise an open question (§11): it labels these gats
**drut**, while our `frame_for_bpm` assigns the Masitkhani grid only below 90 bpm.

### 2.3 The Razakhani frame (VERIFIED vocabulary, no verified grid)

The Razakhani (drut) gat's bols are `da ra dir dir dar dar da, da dir dara da da ra`
(Parikh FAQ). Its pattern is "fixed but with slight variations permitted according to the
melodic mould of the related gat" (Parikh FAQ q56, read directly). Its mukhda may start on the
sam, on the khali, or "even" on matra 7. **No default is named** (VERIFIED: Parikh q56 and the
GPT guide). Our code calls matra 7 "the teaching default" (`src/gats.py`, lines 19 and 81),
and that claim has no source in reach, so it should be dropped. Typical drut figures:
`da dir dara`, `dir dir dara` (Shahid Parvez), `dara dara da dara` (Lalmani Misra). What
gives a Razakhani gat its drive is the *density* of `dir` doublings, "a weaker notion of
symmetry, and a higher stroke density" relative to Masitkhani (Parikh, "Origin of the
Sitar"). It is played from about **120-180 bpm**, accelerating in the appended jhala to
480-600 (SINGLE: Parikh). That range sits right inside metal tempi, and doom's 60-90 sits
on the Masitkhani side, so our `frame_for_bpm` split at 90 matches the tradition's own
tempi.

**A candidate Razakhani cycle (FLAGGED: one source, alignment inferred).** Parikh's "Origin
of the Sitar" prints the "most popular and most durable" Razakhani stroke format as two rows.
The first has 12 strokes, `Da Ra Dir Dir Da Rda Ra Dir Da Dir Da Ra`, and the second has
four, `Da – Da Ra`. Together they make 16. The column spacing in the page is unreliable:
even the Masitkhani rows drift several columns against the beat numbers. So only the order
and the count can be trusted. Reading it by the layout of the Masitkhani table beside it
(first row = the strokes leading into the sam, second row = from the sam), the cycle is:

```
matra:  1   2   3   4  | 5   6   7    8   | 9   10   11  12  | 13  14   15  16
bol:    Da  –   Da  Ra | Da  Ra  Dir  Dir | Da  Rda  Ra  Dir | Da  Dir  Da  Ra
```

Matras 12-16 come out as `Dir Da Dir Da Ra`, the Masitkhani mukhda shape exactly. There is a
real rest (–) on matra 2 after the sam stroke, and the khali opens on a Da. It is close
kin to the FAQ's `da ra dir dir dar dar da…`, as "slight variations permitted" would
predict. This would be our first Razakhani grid, but it must not be encoded until Sujit or
his guruji confirms the matra alignment.

**What a gat is called** (VERIFIED: Parikh q56 and the GPT guide). Masitkhani and Razakhani
are defined by their **bol patterns as well as their laya**. In Parikh's words, "I don't
call gats which don't follow M. Khani bol patterns as M. Khani gats. They are just Vilambit
gats", and gats that do not follow the Razakhani pattern "should be just called Drut gats".
A gayaki-ang gat of category (c) (§1) that floats free of both patterns is therefore a
**vilambit gat** or a **drut gat**. The engine should be able to say so rather than force
every head into one of the two frames.

### 2.4 How many strokes per note

This changed across the gharana's generations (SINGLE: Nad Sadhna; Parikh agrees on the first
step):

- **Imdad Khan**: a right-hand-driven style, with 2-3 or even 6 strokes per note, especially
  in drut-gat taans.
- **Enayat Khan**: "1 note, 1 bol" in fast sapat (straight) taans.
- **Vilayat Khan**: many notes per stroke, carried by meend.

So for the **head**, a Vilayat Khan-style gat restates a swara with 2-3 strokes where the
rhythm calls for it (often the arrival swara right after the sam), and lets one stroke carry
a meend across several swaras where the melody calls for it. For **taans**, one stroke per
note is the norm. Strokes per matra by laya are NOT sourced beyond the grids above (§11).

### 2.5 How the melody rides the strokes (from `gats.GAT_CRAFT`, with new corroboration)

- **The left hand moves the melody and the right hand makes the rhythm.** One swara often
  takes several strokes in a row, and after the sam arrival the arrival swara is usually
  restated before the line moves on (VERIFIED). All six textbook lines restate their sam
  swara on matras 1-3 (Yaman: `G G G`, Bhupali: `G G G`, Bhimpalasi: `P P P`), which
  strengthens this.
- **A `dir` is the same swara struck twice**, now and then a single step up into the next
  target, never a leap (VERIFIED: Vishwamohini plus Sujit, "dir is generally used on the same
  note"). The textbook gats agree. Every dir there is a doubled swara (`SASA`, `PAPA`,
  `R'R'`) except Bhimpalasi's pickup `S R`, a single step.
- **`dara` usually moves** across two swaras, and in **`dadir`** the da approaches while the
  dir doubles the arrival (COMMON: one notation).
- **Moving groups and settling groups** (VERIFIED for Masitkhani). The five-matra groups
  driven by dir (`dir da dir da ra`) carry the melody forward, and the three-matra groups
  (`da da ra`) settle it.
- **Move stepwise on the raga's own ladder** (the raga's skips count as steps). Inside a
  phrase the widest leap is about a third, and the one bigger leap is the arrival onto the
  sam (COMMON).

---

## 3. Composing each line

Each line is described below in the order a composer should think about it: what the line is
for, how its notes move, where it peaks and rests, and how it hands on to the next line. One
exemplar runs through the section. Rahul Bhattacharya's account of a Vilayat Khan teentaal
gat in Pilu describes the **texture** changing line by line (SINGLE, one gat). The mukhda runs
continuously, the manjha opens small gaps punctuated by one chikari, and the antara opens
wider gaps with two chikaris. That growth of space is a useful way to give each line its own
character beyond register, though it comes from a single gat and is not a gharana law.

### 3.1 Mukhda (sthayi, line 1): the home and the hook

**Purpose.** The mukhda is what the listener remembers. Its last five matras (the approach,
12-16 in Masitkhani) recur every time the gat comes round and after every improvisation, so
they must be identical every time and land the sam unmistakably.

**Instructions.**

1. **Choose the sam swara first.** It is the gat's home. Use a **nyas swara of the raga**:
   Sa, the vadi or the samvadi are the common choices, and ideally it is the note the pakad
   lands on. (VERIFIED as "Sa/vadi/samvadi" by Parikh and Vishwamohini. The broader rule is
   **already the engine's**: `raga.resting_swaras` replaced the Sa/vadi/samvadi list on
   2026-10-11 with "every permitted nyas, plus Sa", and `verify_mukhada` uses it. The textbook
   Bhimpalasi gat confirms that change: it puts **Pa** on the sam, and Bhimpalasi's vadi is
   Ma, but Pa is a permitted nyas. The GPT guide independently says the same: "sam is a
   rhythmic destination, not necessarily the tonic".)
2. **Write the approach (12-16) next**, because the rest of the cycle exists to set it up. It
   arrives on the sam swara **from below**, by step or by the raga's own skip (COMMON →
   now seen in all six textbook lines as well as Vishwamohini: Yaman `R → G`, Bhupali
   `S → G`, Bhimpalasi `m → P`, and the antaras `R' → G'`, `S' → g'`).
3. **Restate the arrival** on matras 1-3 (the `da da ra` settling group), then let the line
   move.
4. **Keep it mid-register with a modest peak.** The textbook sthayis peak at Pa or Dha
   (Yaman peaks on P, Bhupali on D, Bhimpalasi on P) and never reach taar Sa (SINGLE source,
   three gats). The heights belong to the antara.
5. **Breathe before the relaunch.** The line settles on a resting swara, usually Sa, on the
   soft `ra` of matra 11, the nyas that resets the phrase before matra 12 relaunches
   (VERIFIED: Lokogandhar, Vishwamohini; all six textbook lines end `G R S` / `g R S` on
   9-11).
6. **No chikari and no gaps in the mukhda line** (SINGLE: the Pilu exemplar). The head runs
   continuously; its "breath" is the soft ra on 11, not a rest. **Now HARD in the engine**
   (`gat_verifier.check_head_shape`, 2026-10-12), after `fusion_20261012_152048` planned
   `da ra dir chikari` four times and Sujit heard "three distinct phrases stitched together by
   rests"; a chikari token in a seed's head idea is read as a held matra.
6a. **One idea: a fast figure, then a slow breather** (SUJIT, 2026-10-12, from the GPT guide he
   gathered: "a mukhada can have a fast section followed by a slow part which is the breather";
   "the entire mukhada should sound like an idea"). The head is one sentence: a quick figure,
   a held resting swara that breathes (the place for the raga's own andolan or meend), then the
   approach into the sam. This agrees with rule 5 (the settle on matra 11) and with the
   left-hand density Sujit's guruji's gat showed (a burst of a beat or two, then a ringing
   note). Not separately sourced from a published gat. The engine plans it as
   `PhrasePlan.head_shape` (figure → breather → response → approach, GPT's second review),
   measured against the notes as craft (`check_head_plan`); the breather itself (one note
   struck once and held at least 2 beats) is HARD for a gat head (`check_head_shape`), because
   a rest is not a breather.
6b. **Open with the raga, not the scale.** A head that opens by walking S R g m P is the
   scale (both reviews of `fusion_20261012_152048`); its first few swaras should be a phrase
   only the raga plays. Reported as craft (`check_head_shape`, more than 4 swaras straight).
7. **Write the vocal ornaments in.** Meend and slow murki belong in the head because the head
   is a sung line (VERIFIED: Parikh, "the bols of the bandish verbatim"; Raja). Krintan,
   gamak and fast ornaments do not (§5).

**Worked examples** (textbook drut gats, Sharada Kala Kendra; our sargam: `M` = tivra Ma,
`m` = shuddha Ma, lowercase = komal, `.` = mandra, `'` = taar; doubled swara = one matra
struck as `dir`). Octave marks were partly lost in extraction and are inferred from the
contour; the komal marks for Bhimpalasi were restored from the raga.

```
             m12  | m13 m14 m15 m16 | m1 m2 m3 m4 | m5 m6 m7 m8 | m9 m10 m11
bol:         dir  | da  dir da  ra  | da da ra dir| da dir da ra| da da  ra
Yaman:       GG   | R   SS  .N  R   | G  G  G  RR | G  MM  P  M | G  R   S
Bhupali:     GG   | R   SS  .D  S   | G  G  G  RR | G  PP  D  P | G  R   S
Bhimpalasi:  SR   | .n  SS  g   m   | P  P  P  PP | g  mm  P  m | g  R   S
```

### 3.2 Manjha (sthayi, line 2): the descent into mandra

**Purpose.** The manjha is formally the sthayi's **second line** (Parikh's article groups
mukhda + manjha as the sthayi). Its job is to "take the melody into the lower octave"
(VERIFIED: Parikh FAQ), giving the gat its low register before the antara climbs. The old
FLAG about a "middle" line versus a "lower" one is now resolved. Parikh's structure note says
the manjha was "originally called madhya, which means a middle line". The name describes
its *position* (between mukhda and antara), and its *register* is low.

**Instructions.**

1. **Go low.** Spend the line's weight in mandra and the bottom of madhya. *Not sourced*:
   whether the manjha *begins* in mandra or descends into it, and its typical entry swaras
   (§11). Prompt "takes the melody into the lower octave", not "starts there".
2. **Open the texture.** In the Pilu exemplar this is where punctuation first appears:
   **one chikari stroke closes each mini-phrase, leaving about a one-beat gap** between key
   phrases (SINGLE).
3. **Hand back to the mukhda.** The manjha returns to the head, so it should end near the
   head's opening. ENGINE (already built, `verify_manjha`): it fills to the sam, and its
   last note is within 2 ladder steps of the head's first swara. The composer guardrail
   allows a manjha only after the first mukhda and immediately followed by one.

### 3.3 Antara (antara, line 1): the climb to taar

**Purpose.** The antara takes the gat to the upper octave (VERIFIED: Parikh) and is the gat's
melodic peak.

**Instructions** (contour from the three textbook antaras, SINGLE source, plus Parikh for
register):

1. **Enter on matra 12 from the middle of the scale**, the Ga, Ma or Pa region (Yaman `G`,
   Bhupali `G`, Bhimpalasi `g`, each doubled with dir). It uses the same five-matra pickup
   shape as the mukhda, so the listener feels the familiar launch with new notes.
2. **Climb through Dha and Ni to taar Sa and taar Re across matras 13-16** and **put the
   peak on the sam**. All three textbook antaras land **taar Ga** on the sam (`G'`, `G'`,
   `g'`). A sarod antara (Amjad Ali Khan, SINGLE) reaches upper Sa from matra 9, so an
   earlier climb also occurs.
3. **Descend within the same cycle** stepwise back to madhya Sa on matra 11's soft `ra`,
   ready for the pickup. The textbook antaras compose their own homecoming in one cycle. In
   a longer antara section that homecoming is the amad's job (§3.4).
4. **Open the texture further.** In the Pilu exemplar, **two chikari strokes close each
   phrase, leaving about a two-beat gap** (SINGLE). Bhattacharya notes the line "veers off the
   main teentaal theka" enough to trouble tabla players. This is the gat's most spacious,
   rhythmically adventurous line.
5. **Tihai lives here, and only here.** Within the gat a tihai is an adjunct to a taan,
   played in the antara section, never in the sthayi (VERIFIED: Parikh; Enayat Khan brought
   the tihai to sitar, Nad Sadhna).

```
             m12  | m13 m14  m15 m16 | m1  m2    m3  m4 | m5 m6  m7 m8 | m9 m10 m11
Yaman:       GG   | M   DD   N   R'  | G'  R'R'  S'  N  | D  PP  M  G  | G  R   S
Bhupali:     GG   | P   DD   S'  R'  | G'  R'R'  S'  D  | S' DD  P  G  | G  R   S
Bhimpalasi:  gg   | m   PP   n   S'  | g'  R'R'  S'  n  | D  PP  m  g  | g  R   S
```

(Bhimpalasi's antara climbs `m P n S'`, skipping Re and Dha in ascent, and descends
`S' n D P m g`, exactly its aroha and avaroha. That is directional varjya respected
inside a composed line.)

### 3.4 Amad (antara, line 2): the composed way home

**Purpose.** The amad is the composed descent "down to the point where the composition
started" (VERIFIED: Parikh FAQ and article). It exists so the gat never has to *improvise*
its way back from taar to the mukhda.

**Instructions** (ENGINE, already built as `verify_amad`): open near where the antara peaked
or landed, descend overall, never re-peak (no more than 2 semitones above the opening), end
in madhya or lower, and seam into the head's first swara. Its exact matra shape is not
sourced beyond Parikh's description.

---

## 4. Chikari: the struck pulse that makes space

Chikari strings are the thin drone strings struck for rhythm and resonance, not melody. What
the sources agree on is their **function**. Inside a gat their **placement** is known from
only one exemplar.

**Function.**

- **The chikari is struck, not held.** Parikh: "playing chikari with a gliding stroke followed
  by pluck on the jod string ensures that a musical space is created". The chikari "sets
  the pace" and keeps the music from becoming hasty (SINGLE: Parikh FAQ, said of the alap).
  So render it as a short struck stroke. ENGINE: `_CHIKARI_MAX_DUR = 0.5` beat in
  `verify_intro` already enforces this.
- **The chikari fills silence**, between phrases, as a tanpura substitute (VERIFIED for the
  alap: Deepak Raja, Ramprapanna). Vilayat Khan filled the silences between lyrical phrases
  with jod, steel gandhar, chikari and taraf strings. Whether this carries into the gat
  rests on the Pilu exemplar alone.

**Placement in the gat** (SINGLE, Pilu exemplar; treat as a tendency):

| Line | Chikari | Gap |
|---|---|---|
| Mukhda | none | none: continuous |
| Manjha | one stroke closing each mini-phrase | ~1 beat |
| Antara | two strokes closing each phrase | ~2 beats |

- **A chikari can stand in for a melody note**, occupying a matra the melody would otherwise
  fill (SINGLE, from an old Pilu jangla gat in a sarod context, so not specifically
  Imdadkhani).
- In the **drut gat**, as tempo rises, right-hand strokes alternate between the main string
  and the chikari (SINGLE: Ramprapanna). This is the bridge toward jhala.

**Jhala** (for the climax, not the head): one `da` on the melody string, then `ra ra ra` on
the chikari per matra (SINGLE: Sharada notation, `SA . . . | DA RRR`). All four strokes are
equally loud to match the tabla theka (SINGLE: Parikh). **Ulta jhala**, which reverses this
into one chikari stroke then three on the main string, is the gharana's hallmark (VERIFIED:
hindustaniclassical.com; Ramprapanna).

**Tuning: an open question for Sujit.** Parikh says the two chikaris are both tuned to Sa,
with upper Sa on the smaller string, because "chikaris are meant to sustain this element"
(SINGLE: Parikh FAQ). Our `chikari_swaras` gives Bageshree `S S D m` (GURUJI). The two may
describe different strings (the chikaris proper versus the middle drone strings that
Vilayat Khan retuned per raga as a "chord-like filler", Raja), and so need not contradict.
Sujit/guruji should confirm which strings `S S D m` refers to before the multi-string chikari
stroke is built.

**FLAGGED, not to encode:** "the chikari is struck thrice in eight matras" (hindustaniclassical.com,
no context), and "chikari is absent in the Maihar style" (same weak source, and not literally
true, since Maihar jhala uses chikari).

---

## 5. Ornaments: which belong on the head, which on improvisation

The organising principle is the gayaki ang. The head is a **sung line**, so it carries vocal
ornaments: meend, kan, and slow murki. The fast and percussive ornaments (krintan, gamak,
ghaseet) belong to the improvisations (fills, taans, jod) and to the alap (VERIFIED in
outline: Parikh, Raja, Ramprapanna). **Gamak is the exception Sujit corrected** (2026-10-12:
"gamak are also present in mukhada — use wisely"; his guruji's recorded Darbari gat opens on
one): it belongs on a head as an event, one or two at most, never on every note. The engine
reports more than two (`check_head_shape`); a run of strokes on one swara counts once.

| Ornament | On the composed head? | Where it belongs | Grade, source |
|---|---|---|---|
| **Meend** (fret pull) | **Yes**, written into the line | head; long meends in alap; big meends at taan climaxes | VERIFIED (Parikh, Raja, Nad Sadhna) |
| **Kan / sparsh** (grace touch) | Yes, sparingly: **one kan**, as in dhrupad | head and alap | SINGLE (Parikh, surbahar khayal-ang context) |
| **Murki** (wrap-around turn) | Yes, as a **meend-type turn under one stroke** | head; Vilayat Khan's khayal-ang passages | VERIFIED (Parikh ×2, Raja, Nad Sadhna; see below) |
| **Andolan** (slow swing) | Not sourced for gat placement | raga-specific swaras (our per-raga data) | per-raga data; GURUJI for Bageshree |
| **Krintan** (left-hand hammer cluster) | **No** | alap, jod, and drut-gat fill alankars | SINGLE (Ramprapanna; mechanics Parikh) |
| **Gamak** (heavy oscillation) | **Sparingly** (one or two) | gamak taans (vilambit and drut), jod; a head as an event | VERIFIED for taans (Nad Sadhna, Ramprapanna, Raja); GURUJI/SUJIT for the head |
| **Ghaseet** (slide, often across octaves) | No | alap octave jumps, jod, with meend and jhala | SINGLE (Ramprapanna; mechanics Parikh) |
| **Zamzama, khatka** | Not found | n/a | §11 |

**How each is physically made, with its span** (Parikh, "Origin of the Sitar", read
directly). These spans are the numbers a verifier or the renderer can use:

- **Meend**: "pulling the string from a single fret, and executing a phrase under the impact
  of a single stroke". Three-swara meends were common up to the 1930s, and the contemporary
  sitar delivers **five**.
- **Murki**: "a special type of meend, where the phrase involves a wrap-around execution with
  a jerky motion". The contemporary sitar supports **up to eight swaras under a single
  stroke**.
- **Gamak**: "a pulsating or quivering effect, a magnified vibrato, by repeatedly attacking a
  swara from a fret at a lower pitch". It spans **up to two, occasionally three, swaras**.
- **Krintan**: the first swara takes a right-hand stroke, and the following swaras are made
  by the second finger hammering the frets "without further right-hand stroke support". It
  covers **up to four swaras**. Parikh calls it unique to the sitar and essential to the
  tantkar ang.
- **Ghaseet**: drags the left-hand finger along the fretboard "over at least half a saptak
  under the impact of a single stroke", usually flat-out and in one direction, often a full
  saptak, with feather-touch pressure so it sounds fretless.

All five share one fact the GPT guide also stresses: **one stroke, many swaras**. Our note
contract cannot express that yet beyond a single meend target (§12).

**Meend range.** A Vilayat Khan-style line can pull **up to five swaras from one fret**
(VERIFIED: Raja and Nad Sadhna both credit Vilayat Khan with five-note meends). Enayat Khan's
range is given as 2-3 tones (Raja) or 3-4 (Nad Sadhna), a minor FLAGGED disagreement. The
five-swara meend (panch-swar meend) and the **reverse meend** (ulta meend) are alap devices,
especially in its closing (abhog) section (SINGLE: Ramprapanna). For the head, keep meends
shorter and at phrase joints. Our renderer's rule already matches this: fast notes articulate
cleanly, and a meend is a quick pull anchored on its target.

**Murki, now resolved.** Raja and Nad Sadhna credit Vilayat Khan with intricate seven- or
eight-tone khayal-ang murkis. Parikh, in a surbahar passage, says "murkis played on sitar
should be avoided. However, murkis could be executed in much slower meend like movements."
These looked contradictory until his "Origin of the Sitar" settled it. On sitar, a murki
*is* a meend: a wrap-around deflection of up to eight swaras **under a single stroke**. What
he warns against is the vocal murki of rapid separate articulations. So the encoding is
**one stroke, the turn made by the left hand**, never several plucks, which is already what
our renderer does.

**Andolan.** No source ties andolan to gat-versus-alap placement, so our per-raga, per-swara
andolan data (`crew/expression.py`) stands as the authority. Andolan is a property of
specific swaras (for example Darbari's komal ga and dha; in Todi the r-g interplay with a
nyas on the gandhar, Parrikar). Bageshree's **g swings UP toward m**, or m is released slowly
down onto g (GURUJI). The open question is whether an andolan belongs on the composed head at
all, or only in vistar.

**Gamak.** Gamak is improvisation's ornament: the **gamak taan** is part of Vilayat Khan's gat
repertoire, and gamak pairs with meend in drut-gat taans. Our current choice of gamak on the
climax taan only (`crew/expression.py`) matches the sources.

---

## 6. Silence, sustain and breath

The sources agree that silence is the music's breath (VERIFIED in spirit: Parikh, Ramprapanna,
Raja). Parikh says the space between two melodic phrases keeps a recital from becoming hasty
and tense. Ramprapanna compares the gaps to a singer's breath and lists "gap and volume
variation" as a technique, and Raja praises the "subtle use of silences". All three are
speaking of the alap or in general. For the gat, the usable shape is the Pilu exemplar's
**widening gaps**: none in the mukhda, about a beat in the manjha, about two in the antara
(SINGLE).

Sustain does the rest. Vilayat Khan's instrument and left hand were built for long-ringing
notes, and the `da` stroke is favoured for its sustained sound (Nad Sadhna; the latter only
from hindustaniclassical.com). So on held notes in the head, use a `da` and let it ring;
carry several pitches on it by meend rather than re-striking.

In the head, the "reset" is the soft `ra` on matra 11 that settles on Sa. Real silence is for
the manjha and antara, where chikari punctuates it.

---

## 7. Note choice: where to land, what to avoid

Most of note choice lives in each raga's encoded data, which remains the single source of
truth (`src/raga.py`: aroha/avaroha, pakad, chalan, `NYAS`, directional varjya). The gat
sources add a few placement rules on top.

**Land on:**

- **The sam**: a nyas swara of the raga (core or permitted; Sa/vadi/samvadi are the usual
  choices), ideally the pakad's landing (§3.1). Each line's sam note follows its job. The
  mukhda's is its home, the manjha lands low, and the antara peaks on taar (Sa, Re or Ga;
  taar Ga in all three textbook antaras).
- **Matra 11**: a resting swara, almost always Sa, on the soft `ra`, just before the
  relaunch (VERIFIED).
- **Phrase endings before silence**: a nyas swara (our `NYAS` data, already checked on lead
  phrase endings).

**Approach:**

- **The sam from below** (§3.1, now in seven notated lines).
- **Stepwise on the raga's own ladder**, with direction-sensitive swaras used only in their
  permitted direction (directional varjya, e.g. Bhimpalasi's Re and Dha only descending, as
  the textbook antara shows).

**Avoid:**

- Landing the sam, matra 11, or a phrase ending on a swara outside the raga's nyas set.
- Leaps wider than about a third inside a phrase. The one exception is the arrival onto the
  sam.
- Using a descent-only swara ascending, or the reverse.

No source found gives gat-specific rules on vibhag-start swaras or on how to treat weak
(durbal) swaras in a gat (§11). The per-raga `NYAS.avoid` lists are the authority there.

---

## 8. How the cycle connects back

The gat is a loop, and the hand-back to the mukhda is where the form's tension resolves. Four
mechanisms are sourced, and they can coexist.

1. **The mukhda as the return path (the Imdadkhani way).** An improvisation (a taan or a
   vistar phrase) runs from the sam through about matra 11. Then **the mukhda's own approach
   re-enters on matra 12** and lands the next sam (VERIFIED: Parikh). The reset sits at
   matra 11, the relaunch on 12, the arrival on the sam. ENGINE (built): taan fills take the
   *front* of the cycle and the head's approach re-enters at `approach_cut`. A small FLAGGED
   discrepancy: some sources give the return on matra 11 rather than 12.
2. **The textbook toda formula.** A toda (taan) starts on the sam, fills one or two whole
   cycles, and ends with a **fixed four-matra closing figure on matras 13-16** that lands on
   the next sam. The mukhda's pickup does not carry it home (SINGLE: Sharada notation,
   lineage unknown). It is a real second hand-back mode, though less characteristic of this
   gharana. Bhupali toda 1, two swaras per matra:
   ```
   X: SR GG RG PP | 2: GP DD PD S'S' | 0: S'S' DP GR S | 3: SR GS RG SR | → X
   ```
3. **The tihai.** A phrase played three times, its last stroke exactly on the sam, as an
   adjunct to a taan in the antara section only (VERIFIED). Tihais may also land off the sam
   (samapad and vishamapad, SINGLE: Ramprapanna), but our engine lands on the sam.
4. **The aochar into the antara.** Vilayat Khan's taankari climbed to the taar saptak and
   ended in an "aochar" that set up the gat's antara, which he would "catch" in different
   ways (SINGLE: Ramprapanna). So a climbing improvisation can hand over to the antara
   rather than the mukhda.

Ramprapanna also describes the large-scale development (SINGLE). After the chhand and
layakari passages, Vilayat Khan played **the gat itself at double and triple speed** (dugun,
tigun), filled the gap with flexible taans and small tihais, and returned to the mukam (the
return point). His long prefixed tihais grew rarer later in his career.

The role of the **khali** in the return was not found. Apart from the Masitkhani mukhda
launching inside the khali half, no source says what the khali does there (§11).

---

## 9. A procedure for the composer

This is a synthesis of sections 1-8 into the order an agent should work in. Each step cites
the rules it applies.

1. **Pick the frame from the laya** (§2). Masitkhani with its fixed grid for slow tempi,
   Razakhani vocabulary with free dir density for fast ones (`frame_for_bpm`; see the open
   question in §11 about textbook "drut" gats on the Masitkhani grid).
2. **Pick the gat's home: the mukhda's sam swara** (§3.1, §7). It is a nyas swara of the
   raga, ideally the pakad's landing.
3. **Write the mukhda's approach first** (§3.1). Five matras (12-16) on `dir da dir da ra`,
   rising into the sam swara from below, built from a pakad or chalan fragment so the hook
   names the raga. It must be identical on every return.
4. **Fill matras 1-11 of the mukhda** (§2.5, §3.1). Restate the arrival on 1-3, move through
   a moving group (4-8) and a settling group, stay mid-register with a modest peak, and settle
   on Sa on the soft `ra` of matra 11. No chikari, no gaps. Write a meend or one kan where a
   singer would put it.
5. **Sing it.** If the line could not be sung (leaps, no breath, no shape), rewrite it. This
   is Vilayat Khan's own test (Parikh). A singability check is still deferred in the engine.
6. **Write the manjha** (§3.2). It takes the melody into mandra, closes each mini-phrase with
   one chikari and a ~1-beat gap, and ends near the head's opening swara so the mukhda can
   follow.
7. **Write the antara** (§3.3). Enter on matra 12 from the Ga, Ma or Pa region, climb to taar
   by 13-16, peak on the sam (taar Sa, Re or Ga), then descend. Close each phrase with two
   chikaris and a ~2-beat gap. Respect the raga's directional swaras on the way up and down.
8. **Write the amad** (§3.4). A composed descent from the antara's peak back to the mukhda's
   first swara, with no re-peak.
9. **Ornament pass** (§5). Meend (≤5 swaras per pull, shorter in the head), one kan, slow
   one-stroke murki, and the raga's own andolan swaras. No krintan or ghaseet on the head, and
   gamak only as one or two events; save the rest for fills and taans.
10. **Check the hand-backs** (§8). Every line ends where the next can start. Improvisations
    return either through the mukhda's approach at matra 12 or by a closing figure or tihai
    onto the sam, and tihais go only in the antara section.

---

## 10. What is checkable and what is craft

The redesign's rule is that code owns only real constraints, and every craft rule is a
measurement reported to the Producer, never a rejection. Read that way, this guide sorts as
follows. Nothing here has been built yet; it is for Sujit's review first.

- **Real constraints (already enforced, or natural as hard checks):** the frame fits the
  cycle; the mukhda's approach lands the sam; raga legality and directional varjya; the sam
  swara ∈ the raga's nyas set; the amad seams into the head; a tihai lands on the sam and only
  in the antara section; chikari is struck short.
- **Measurements worth reporting (craft, VERIFIED or SINGLE):** arrival from below;
  restatement on 1-3; rest on Sa at matra 11; mukhda peak below taar Sa; manjha's
  share of time in mandra; antara peak in taar on or near the sam; chikari/gap density
  per line (mukhda 0, manjha ~1, antara ~2); leap sizes; meend span; ornaments that
  belong elsewhere appearing on the head (krintan; gamak beyond one or two).
- **New relative to the engine today:** the per-line chikari and gap texture; the antara
  contour (enter at 12 mid-scale, taar on the sam); the ornament-placement table and
  Parikh's ornament spans as measurements; the toda closing-formula hand-back as a second
  return mode; `rda` in `BOL_WORDS`; an explicit "free" vilambit/drut gat beside the two
  frames; and the GPT-derived items in §12. The nyas-set sam rule is *not* new. It shipped on
  2026-10-11.

---

## 11. Open questions: what no source settled

These are holes, best answered by Sujit's guruji or an offline method book. They stay holes
until then.

1. **Chikari placement in the gat** beyond the single Pilu exemplar. Is "mukhda none,
   manjha one, antara two" a general Imdadkhani habit, or one gat's design?
2. **Chikari tuning.** Do Parikh's "both chikaris on Sa" and guruji's Bageshree `S S D m`
   describe different strings (§4)?
3. **Strokes per matra by laya** (vilambit, madhya, drut) beyond the grids.
4. **Andolan on the head.** Does a gat head carry andolan on the raga's andolan swaras, or is
   andolan reserved for vistar? Zamzama and khatka placement were not found at all.
5. **The manjha's entry.** Does it begin in mandra or descend into it, and on which swaras?
6. **Memorability.** No teacher guidance was found on hooks or repetition-with-variation
   beyond the mukhda's fixed approach and Vilayat Khan's practice of trying "every phrase of a
   raga in a variety of ways until it delivered the desired melodic and acoustic result"
   (Raja).
7. **The khali's role** in the return, and gat-specific rules for vibhag-start swaras and
   durbal swaras.
8. **Masitkhani grid at drut tempo (partly resolved).** By Parikh's naming rule (§2.3),
   Masitkhani means *both* the bol pattern and vilambit laya. The textbook's fast gats on
   that pattern are therefore simply "drut gats", and `frame_for_bpm`'s tempo split stands.
   Still open is whether a drut gat should *borrow* the Masitkhani stroke grid.
9. **A lineage-verified, matra-by-matra Razakhani or Imdadkhani drut gat.** Still not found
   online. The Sharada PDF has a Malkauns Masitkhani and a "Rajakhani" gat, but text
   extraction lost their alignment and octave and komal marks, so they need reading from the
   PDF itself.
10. **"dir dir" / "dar dar" pairs**: how they sit melodically (carried over from 2026-10-12).
11. **The Razakhani cycle's matra alignment** (§2.3). Does Parikh's `Da – Da Ra` row sit on
   matras 1-4, making `Dir Da Dir Da Ra` land on 12-16?

---

## 12. Against the GPT guide: agreements, additions, cautions

Sujit gathered a second guide from GPT on the same question (2026-10-12). The four Parikh
pages it cites that our first pass could not reach were read directly the same day. Its
verifiable claims held up, and its main value is in system design rather than new musical
facts. In brief: it agrees with this guide on every sourced point, it fixes two of our
claims (rda has a defined stroke order, and matra 7 is no Razakhani default), it adds
several design ideas worth taking, and it needs one notation fix before any of its phrases
go near a prompt.

### Where the two agree (independently)

- The four-line circuit, mukhda → manjha (low) → antara (high) → amad (home), held as a
  reference model and not a requirement ("barring some exceptions", Parikh).
- The Masitkhani grid, matra for matra, including the five-matra pickup from matra 12 and
  the 5-3-5-3 asymmetry against teentaal's 4-4-4-4.
- The sam is a rhythmic destination chosen from the raga's resting notes, not always Sa.
  This is already the engine's rule.
- Razakhani gats may start on the sam, the khali or matra 7, with no default.
- Andolan is a property of specific swaras in specific ragas, never a generic vibrato. Our
  per-swara andolan data (`crew/expression.py`) is built this way.
- A tihai is one way home, not a requirement, and its landing is arithmetic that code
  should check. GPT's formula, last attack at `start + 3d + 2r − 1`, is correct, and
  `make_tihai` already sizes its gaps this way.
- The architecture. One composer owns the whole gat, because splitting sections across
  agents breaks coherence. Code checks what is checkable and a judge handles the rest. Debate
  is reserved for real artistic alternatives. These are the redesign's own rules
  (DESIGN.md "THE REDESIGN"; the seed debate is parked until gats vary).

### What it adds that is worth taking

1. **One stroke is not one note.** GPT says to store the swara sequence separately from the
   mizrab events, and Parikh's spans make the point concrete: meend up to 5 swaras, murki up
   to 8, krintan up to 4, ghaseet half a saptak or more, each under a single stroke. Our
   `LeadNote` carries one swara, one optional meend target and an optional murki/khatka
   flick, so a five-swara meend or a krintan run is unrepresentable. Of all the gaps either
   guide exposes, this is the one that most limits gayaki-ang (category c) heads.
2. **Reconstruct before you generate.** Before trusting the composer, check that the
   contract can faithfully represent real gats and that our verifiers *pass* them. We now
   have four notated gats (Vishwamohini's Bhimpalasi plus the three textbook gats in
   §3.1/§3.3). Encoding them as pure test fixtures costs nothing and calibrates every
   verifier: if a real gat fails `verify_mukhada`, the verifier is wrong, not the gat. The
   old Sa/vadi/samvadi rule would have failed the textbook Bhimpalasi, which is exactly the
   kind of error this catches.
3. **The refrain is not the opening line.** "Mukhda" names both the first line and the
   recurring phrase into the sam. GPT suggests `opening_theme` and `sam_refrain`. The engine
   already has the second concept (the approach from `approach_cut`) but not the name.
4. **Motif transformations must respect raga grammar.** Inversion, retrograde and arbitrary
   transposition are not valid by default. Rhythmic variation, expansion with characteristic
   phrases, idiomatic register shifts and fragmentation are safe. This agrees with
   `src/chalan.py` and the 2026-09-14 SEQUENCE-prompt fix, and it belongs in the composer
   prompt as one line.
5. **Per-line questions for the judge.** Is the mukhda worth repeating? Does the manjha keep
   the opening's identity in the low register? Does the antara's ascent feel earned? Does the
   amad sound composed rather than constructed? Is chikari expressive or merely filling
   space? These map straight onto Producer rubric criteria for a gat.
6. **Four kinds of space.** A sustained note, a ringing decay, a melodic rest and a chikari
   fill are different events and should not share one representation. This sharpens §6.
   GPT's chikari levels (sparse / moderate / jhala) are compatible with the per-line texture
   in §4, which is more specific but rests on one gat.
7. **A richer per-raga phrase grammar** (opening gestures, cadential and return movements,
   upper and lower development). This is the right direction, and `pakad`, `chalan` and
   `src/chalan.py` are its seed. But every new field is raga *knowledge* and needs ≥2
   Hindustani sources per raga under the project's accuracy rule, so it is a sourcing
   campaign, not a coding task.

### Cautions before using any of it

- **Notation clash (important).** GPT writes `M` for *shuddha* Ma ("`S R g M P D n`,
  shuddha notes except komal Ga and Ni"). In our sargam `M` is **tivra** Ma and shuddha Ma is
  `m`. Every GPT phrase must be converted before it touches a prompt or a fixture. Its
  Bageshree `D n D M` is our `D n D m`, and pasted raw it would ask for a tivra Ma that
  Bageshree does not have.
- **Its Bageshree phrases are illustrations, not data.** They happen to agree with our
  sourced pakad and chalan (`m D n D m g R S`, `m P D m g`), and those stay the authority.
  GPT also assumes Sujit is learning a Pa-varjya Bageshree. Our data, from Parrikar and
  Tanarang, has Pa varjit ascending and touched in the descent through `m P D m g`. Only
  Sujit can say which version his guruji teaches.
- **Numeric score weights (raga identity 25%, coherence 20%, …) are rejected.** They are
  arbitrary, and GPT itself says hard violations must sit outside any aesthetic score. The
  Producer's anchored rubric plus code-owned constraints already does that.
- **Unverified claims.** That Parikh "notes some modern performances omit the antara" is not
  on his structure page; the nearest is "barring some exceptions". That Vilayat Khan's
  instrument changes limit the low register is plausible and matters for the manjha's
  playability, but Parikh's instrument article does not state it. Ask Sujit before encoding
  any range limit.
- **Three proposed style labels** (`traditional_masitkhani`, `gayaki_ang`,
  `hybrid_imdadkhani`). GPT presents these as software categories. They map onto Parikh's
  verified (a)/(b)/(c), so use his categories and his naming rule (§2.3) instead.

### What this would change in the engine (proposals only, nothing built)

| Change | Kind | Effort |
|---|---|---|
| Add `rda` (`r`, `da`, 1:1) to `BOL_WORDS`; fix its comment | knowledge, verified | tiny |
| Drop "matra 7 = teaching default" from `src/gats.py` | correction | tiny |
| Encode the four notated gats as reconstruction fixtures | pure tests | small |
| Explicit gat category (a/b/c) and a "free" vilambit/drut gat beside the two frames | contract + prompt | medium |
| Ornament spans (meend ≤5, murki ≤8, krintan ≤4, gamak ≤2-3 swaras) as measurements | measurement | small |
| Several swaras under one stroke (meend path, krintan run) | contract + renderer | large |
| Per-line gat questions in the Producer rubric | prompt | small |
| Razakhani candidate cycle | knowledge, FLAGGED | waits on Sujit |

---

## Sources and how much to trust them

**Strong.**

- Pandit Arvind Parikh (Vilayat Khan's disciple for six decades): FAQ,
  https://panditarvindparikh.org/faq/, and "Bandish on the Instruments",
  https://panditarvindparikh.org/articles/music-related/bandish-on-the-instruments/ (also
  the Nad Sadhna copy).
- Parikh, read directly 2026-10-12 (via the GPT guide's citations): "Origin of the Sitar"
  (four strokes incl. rda, 5-3-5-3, Masitkhani and Razakhani formats and tempi, ornament
  mechanics and spans), https://panditarvindparikh.org/articles/music-related/origin-of-the-sitar/;
  FAQ q56 (naming rule, Razakhani starts), https://panditarvindparikh.org/frequently_asked_que/q56/;
  "Note on structure of bandishes" (four lines, manjha = madhya),
  https://panditarvindparikh.org/frequentlyaskedquest/2-note-on-structure-of-bandishes/;
  "Evolution of gats" (categories a/b/c),
  https://panditarvindparikh.org/frequentlyaskedquest/1-evolution-of-gats/
- Deepak Raja, "Ustad Vilayat Khan: the orthodox revolutionary",
  http://swaratala.blogspot.com/2007/04/ustad-vilayat-khan-orthodox.html
- Vishwamohini, Masitkhani gat in Bhimpalasi (notation),
  https://vishwamohini.com/music/music.php?id=1152
- Rajan Parrikar, raga pages (e.g. https://www.parrikar.org/hindustani/todi/).

**Middling.**

- Ramprapanna Bhattacharya, "Sitar Repertoire of Ustad Vilayat Khan" (studied with Parikh
  and Kashinath Mukherjee; personal blog),
  http://ramprapanna.blogspot.com/2010/05/sitar-repertoire-of-ustad-vilayat-khan.html
- Nad Sadhna, Vilayatkhani-Itawa gharana (institute page, no named author),
  https://nadsadhna.com/indian-music/sitar-gharanas/vilayatkhani-itawa-gharana/
- Lokogandhar, "Evolution and Structure of the Masidkhani Gat and Baaj",
  https://lokogandhar.com/the-evolution-and-structure-of-the-masidkhani-gat-and-baaj/
- Ustad Shahid Parvez, Free Press Journal interview; Lalmani Misra's drut bol tables
  (omenad.net). Both cited in `src/gats.py`.

**Weak (exemplars and leads, not authority).**

- Rahul Bhattacharya (sarod; student of Shahid Parvez and Amjad Ali Khan), the Vilayat Khan
  Pilu gat: https://sarod.com.au/raga-pilu/ and
  https://sarod.com.au/raga-pilu-some-old-compositions/
- Sharada Kala Kendra, *Sitar Notation 1* (Radhey Shyam Gupta; lineage unknown, Bhatkhande-style
  textbook), https://www.sharda.org/wp-content/uploads/2015/12/Sitar_Notation_1.pdf
- hindustaniclassical.com, Imdadkhani and Maihar gharana pages.

**Practitioner.** Sujit's sitar practice and his guruji's teaching (oral tradition): "dir is
generally used on the same note"; Bageshree chikari tuning `S S D m`; Bageshree's g swinging
up toward m.

**Unreachable in this pass:** Martin Clayton, "Two gat forms" (403); Stephen Slawek, *Sitar
Technique in Nibaddh Forms* (no excerpts online); Parikh's teaching material (login or CD-ROM);
shodhganga theses; interviews with Shujaat Khan and Budhaditya Mukherjee.
