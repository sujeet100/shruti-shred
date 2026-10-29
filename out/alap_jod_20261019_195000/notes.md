# Alap then jod — A/B

jod enters at 22.0 s

## A — shipped (whole-alap pulse)
  - THE ALAP (the intro) — does it breathe like an alap, and walk the band in?
    22 s of alap; 31% of its sound on notes held 1 s or longer; 5 phrases, 3.2 s each on average, 5 standing on a held note; new swaras per phrase: 3 3 1 2 2; widest reach R. at 93%; then a 10.0 s jod at 0.1 notes/beat; its last phrases rest on the head's first swara, and it does not quote the head's opening figure
    how to read it: an alap is unmetred and mostly HELD (well over half its sound), each phrase standing on one held swara for seconds; it opens the raga one or two new swaras a phrase, reaches widest about three quarters through, then a short pulsed jod leads the band in, preparing the head without quoting it. Short busy phrases, a range opened all at once, or a quoted head read as an INTRO in tempo, not an alap.
-   0.0 s (alap): d-1[0.5s] n-1[0.5s] S[1.0s] -> rests on **S**
-   4.0 s (alap): S[0.5s] R[0.5s] g[1.0s] m[0.5s] g[0.5s] -> rests on **g**
-   8.0 s (alap): m[0.5s] P[0.5s] m[0.2s] g[0.2s] m[0.5s] R[1.0s] -> rests on **R**
-  12.0 s (alap): S[0.5s] d-1[0.5s] n-1[0.5s] P-1[1.0s] m-1[0.5s] P-1[0.5s] d-1[0.5s] -> rests on **d**
-  18.0 s (alap): n-1[0.5s] P-1[0.5s] m-1[0.2s] P-1[0.2s] g-1[0.5s] m-1[0.5s] R-1[0.5s] S[1.0s] -> rests on **S**
-  24.0 s (alap): S[2.0s] -> rests on **S**

## B — alap, then jod
  - THE ALAP (the intro) — does it breathe like an alap, and walk the band in?
    22 s of alap; 57% of its sound on notes held 1 s or longer; 4 phrases, 4.9 s each on average, 4 standing on a held note; new swaras per phrase: 3 3 1 3; widest reach g. at 95%; then a 10.0 s jod at 0.7 notes/beat; its last phrases rest on the head's first swara, and it does not quote the head's opening figure
    how to read it: an alap is unmetred and mostly HELD (well over half its sound), each phrase standing on one held swara for seconds; it opens the raga one or two new swaras a phrase, reaches widest about three quarters through, then a short pulsed jod leads the band in, preparing the head without quoting it. Short busy phrases, a range opened all at once, or a quoted head read as an INTRO in tempo, not an alap.
-   0.0 s (alap): S[2.0s] n-1[0.5s] d-1[0.5s] n-1[0.5s] S[1.5s] -> rests on **S**
-   6.0 s (alap): S[0.5s] R[0.8s] g[2.0s] m[0.5s] g[1.5s] -> rests on **g**
-  12.0 s (alap): m[0.5s] P[0.5s] m[0.5s] g[0.5s] m[0.5s] R[1.0s] S[1.0s] -> rests on **S**
-  17.0 s (alap): S[0.5s] d-1[0.5s] n-1[0.5s] P-1[1.0s] m-1[0.5s] P-1[0.5s] g-1[1.0s] -> rests on **g**
-  22.0 s (JOD): S[0.5s] R[0.5s] g[0.5s] R[0.5s] S[1.0s] d-1[0.5s] n-1[0.5s] P-1[1.0s] m-1[0.2s] P-1[0.2s] g-1[0.2s] m-1[0.2s] R-1[0.5s] S-1[2.0s] -> rests on **S**

## B's craft notes
- the head walks 5 swaras straight along the scale — open with a phrase only this raga would play (its pakad or chalan), not the scale
- the head opens on S, but your idea put R on the sam — open the head on it
- the head's stroke_line differs from your idea's — keep the idea's right hand unless the melody truly asks otherwise
- only 8% of the alap is silence (need >= 18%) — the space between phrases is part of the music, not leftover time; let each phrase end and BREATHE before the next
- alap phrase 2 opens 3 new swaras at once — reveal the raga ONE frontier at a time: reach one swara past the ground so far and hold it
- alap phrase 4 opens 3 new swaras at once — reveal the raga ONE frontier at a time: reach one swara past the ground so far and hold it
- the intro declares no usable motif (seed = S R g m R S) — phrase_plan.seed must name the ONE recurring idea, 2-5 swaras drawn from the mukhada head (or the pakad), that every phrase develops

## events
- EventType.INFO: gat composed as ONE object (mukhada) — the seed hook
- EventType.INFO: gat craft notes: mukhada — 3 reported, not enforced
- EventType.PROPOSE: alaap: 38 notes over 64 beats [sitar]
- EventType.INFO: gat verify: intro re-rolled (2 tries) -> clean
- EventType.PROPOSE: melody: 48 notes over 32 beats [sitar]
- EventType.INFO: the lead line is set across 2 section(s)
