// The session's timeline, read from script.json (shared with session_music.py) and the voices'
// real durations (voices/voices.json). Pure lookups by time t, in seconds.

export const PART_OF = { lead: "sitar", riff: "guitar", bass: "bass", drums: "drums" };
const LINGER_S = 0.6;                 // a bubble stays this long after its line ends

export async function loadTimeline() {
  const script = await (await fetch("/studio/script.json")).json();
  let voices = [];
  try { voices = await (await fetch("/studio/voices/voices.json")).json(); } catch { /* no voices yet */ }
  const beat = 60 / script.bpm, span = script.avartan_beats * beat, leadIn = script.lead_in_beats * beat;
  // a count-in is spoken word by word on its clicks: its bubble lasts until the last word
  const lines = script.lines.map((l, k) => ({ ...l, dur: l.on_beats ? l.on_beats.at(-1) - l.at + 0.45
                                                         : voices[k]?.dur ?? 0.07 * l.text.length }));
  return { script, beat, span, leadIn, lines, steps: script.steps || [],
           end: leadIn + script.avartans.length * span + (script.tail_s || 0) };
}

/** The avartan playing at t, and how far into it (seconds), or null outside the music. */
function slotAt(tl, t) {
  const k = Math.floor((t - tl.leadIn) / tl.span);
  if (k < 0 || k >= tl.script.avartans.length) return null;
  return { k, slot: tl.script.avartans[k], into: t - tl.leadIn - k * tl.span };
}

/** Whether `part` (sitar | guitar | bass | drums) is sounding at t. */
export function playing(tl, part, t) {
  const s = slotAt(tl, t);
  if (!s || !s.slot.parts.includes(part)) return false;
  const stop = s.slot.stop_at_beat;
  return stop == null || s.into < stop * tl.beat;
}

/** The count-in click the drummer is making at t (0-3), or -1. */
export function countIn(tl, t) {
  const s = slotAt(tl, t);
  if (!s || !s.slot.count_in) return -1;
  const fromEnd = tl.span - s.into;                     // clicks on the last four beats
  return fromEnd <= 4 * tl.beat ? Math.min(3, Math.floor((4 * tl.beat - fromEnd) / tl.beat)) : -1;
}

/** The line being spoken at t (with its progress), or null. */
export function speaking(tl, who, t) {
  const line = tl.lines.find((l) => l.who === who && t >= l.at && t < l.at + l.dur);
  return line ? { line, u: (t - line.at) / line.dur } : null;
}

/** Every line whose bubble shows at t, with its age (for the pop and the fade). */
export function bubbles(tl, t) {
  return tl.lines.map((l, k) => ({ ...l, k, age: t - l.at, left: l.at + l.dur + LINGER_S - t }))
    .filter((b) => b.age >= 0 && b.left > 0);
}

/** The story step shown at t. */
export function stepAt(tl, t) {
  return [...tl.steps].reverse().find((s) => t >= s.at) || null;
}
