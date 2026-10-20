// Speech bubbles over the 3D scene, and the story-step caption. Plain DOM over the canvas, so
// text renders in the deck's fonts; positions come from projecting each speaker's head.
// Sized for where the clip plays: slide 10 shows it at ~0.62 scale, and nothing on the deck's LED
// wall may read below 32 px — so text is 52 px here, and the speaker is a colour stripe, not a
// name label (a legal-size label would double every bubble).
import * as THREE from "three";

const ACCENT = { sitar: "#c98a14", guitar: "#d9702a", bass: "#3f8aa3", drums: "#d26f5d", producer: "#e0247a" };
const INDIGO = "#33357D", CARD = "#FEFCFA", INK = "#2a2a3a";
const W = 1920, EDGE = 24, LIFT = 46, POP_S = 0.16, FADE_S = 0.25;

function css(el, style) { Object.assign(el.style, style); return el; }

export class Overlay {
  constructor() {
    this.layer = css(document.createElement("div"), { position: "absolute", inset: "0", pointerEvents: "none",
      fontFamily: "Mulish, sans-serif" });
    document.body.appendChild(this.layer);
    this.caption = css(document.createElement("div"), { position: "absolute", right: "48px", top: "40px",
      background: INDIGO, color: CARD, borderRadius: "999px", padding: "16px 36px", fontSize: "52px",
      fontWeight: "700", letterSpacing: "0.5px", boxShadow: "0 6px 0 rgba(0,0,0,0.18)", display: "none" });
    this.layer.appendChild(this.caption);
    this.bubbles = new Map();
    this.v = new THREE.Vector3();
  }

  /** Show the step caption (or hide it). */
  step(step) {
    if (!step) { this.caption.style.display = "none"; return; }
    this.caption.style.display = "block";
    // The term the talk uses for this step (Sujit, 2026-10-20: name the mukhada, the riff... in the clip itself),
    // on its own line under the step, at the same legal size.
    const term = step.term ? `<div style="color:#E0AA55;font-weight:800;margin-top:6px">${step.term}</div>` : "";
    this.caption.style.borderRadius = step.term ? "32px" : "999px";
    this.caption.innerHTML = `<span style="color:#E0AA55">${step.n}</span>&nbsp;&nbsp;${step.label}${term}`;
  }

  /** Place one bubble per visible line over its speaker's head. */
  draw(visible, heads, camera) {
    const live = new Set(visible.map((b) => b.k));
    for (const [k, el] of this.bubbles) if (!live.has(k)) { el.remove(); this.bubbles.delete(k); }
    for (const b of visible) {
      const el = this.bubbles.get(b.k) || this.make(b);
      heads[b.who].getWorldPosition(this.v);
      this.v.y += LIFT;
      this.v.project(camera);
      const x = (this.v.x + 1) / 2 * W, y = (1 - this.v.y) / 2 * 1080;
      const width = el.offsetWidth, left = Math.max(EDGE, Math.min(W - EDGE - width, x - width / 2));
      const pop = Math.min(1, b.age / POP_S), fade = Math.min(1, b.left / FADE_S);
      css(el, { left: `${left}px`, top: `${y}px`, opacity: String(fade),
                transform: `translateY(-100%) scale(${0.7 + 0.3 * pop})`, transformOrigin: `${x - left}px 100%` });
      css(el.tail, { left: `${x - left - 14}px` });
    }
  }

  make(b) {
    const el = css(document.createElement("div"), { position: "absolute", maxWidth: "860px", background: CARD,
      border: `5px solid ${INDIGO}`, borderLeft: `18px solid ${ACCENT[b.who]}`, borderRadius: "24px",
      padding: "16px 30px 20px", color: INK, boxShadow: "0 8px 0 rgba(51,53,125,0.25)" });
    el.innerHTML = `<div style="font-size:52px;font-weight:700;line-height:1.18">${b.text}</div>`;
    el.tail = css(document.createElement("div"), { position: "absolute", bottom: "-20px", width: "0", height: "0",
      borderLeft: "14px solid transparent", borderRight: "14px solid transparent", borderTop: `20px solid ${INDIGO}` });
    el.appendChild(el.tail);
    this.layer.appendChild(el);
    this.bubbles.set(b.k, el);
    return el;
  }
}
