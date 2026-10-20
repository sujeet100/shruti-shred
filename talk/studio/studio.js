// The slide-10 studio: the band in one room, rendered deterministically — `renderAt(t)` draws
// the frame at t seconds, so capture.mjs can step through time and the audio can be laid on after.
import * as THREE from "three";
import { PERSONAS } from "../sprites/personas.mjs";
import { amp, desk, drumKit, guitar, micStand, sitar, stool, takht, tanpura } from "./instruments.js";
import { Overlay } from "./bubbles.js";
import { persona, setArm } from "./persona3d.js";
import { room, ROOM } from "./room.js";
import { bubbles, countIn, loadTimeline, playing, speaking, stepAt } from "./timeline.js";
import { box, group } from "./voxel.js";

const W = 1920, H = 1080, PAGE = "#F3F0EA";

// ---------------------------------------------------------------- the band, placed
function place(obj, x, z, rotY = 0, y = 0) { obj.position.set(x, y, z); obj.rotation.y = rotY; return obj; }

function buildBand(scene) {
  const band = {};

  scene.add(place(takht(), -172, 36, 0.4));
  band.lead = persona(PERSONAS.lead, { pose: "cross" });
  place(band.lead.root, -172, 40, 0.4, 10.4);
  const s = sitar(); s.scale.setScalar(0.92);
  s.position.set(-15, 17, 11); s.rotation.set(0.15, 0, -1.0);
  band.lead.hold.add(s);

  band.riff = persona(PERSONAS.riff);
  place(band.riff.root, -85, -5, 0.2);
  const gtr = guitar({ color: "#b8262f" });
  gtr.position.set(-4, 16, 9); gtr.rotation.set(0, -0.15, 0.32);
  band.riff.hold.add(gtr);

  band.bass = persona(PERSONAS.bassist);
  place(band.bass.root, 115, -5, -0.15);
  const bs = guitar({ color: "#2f3a6e", bass: true });
  bs.position.set(-4, 15, 9); bs.rotation.set(0, -0.15, 0.36);
  band.bass.hold.add(bs);

  scene.add(place(drumKit(), -55, -103, 0.1));
  band.drums = persona(PERSONAS.drummer, { pose: "chair", seat: 15 });
  place(band.drums.root, -55, -107, 0.1);
  for (const a of [band.drums.armR, band.drums.armL]) a.add(box(0.9, 0.9, 15, "#e8d8b0", 0, -17, 7));

  band.producer = persona(PERSONAS.producer, { pose: "chair", seat: 16 });
  const booth = group([stool(16), band.producer.root, desk()]);
  place(booth, 205, -42, -1.1);
  scene.add(booth);

  scene.add(place(amp("#ff2e88"), -150, -128, 0.15));
  scene.add(place(amp("#79b8cc"), 75, -128, -0.1));
  scene.add(place(micStand(40), -128, 82, -2.4));
  scene.add(place(tanpura(), -205, -125, 0.5));
  for (const k of ["lead", "riff", "bass", "drums"]) scene.add(band[k].root);
  return band;
}

// ---------------------------------------------------------------- motion, from the timeline
/** Everyone at t: a part that is in plays (arms on the subdivisions, heads on the beat), one
 * that is out rests on its instrument; whoever talks nods along; the producer raises a hand on
 * the stop; the drummer clicks the count-in. Pure in t. */
function perform(band, tl, t) {
  const beat = t / tl.beat, ph = (k) => Math.sin(2 * Math.PI * beat * k);
  const on = (part) => playing(tl, part, t);

  const lead = band.lead, sitarOn = on("sitar");
  setArm(lead.armR, 0.8 + (sitarOn ? 0.08 * ph(4) : 0), 0.35);
  setArm(lead.armL, 1.55 + (sitarOn ? 0.12 * Math.sin(t * 1.3) : 0), 0.55);
  lead.head.rotation.set(0.08, sitarOn ? 0.1 * Math.sin(t * 0.9) : 0, sitarOn ? 0.06 * Math.sin(t * 0.9) : 0);

  const riff = band.riff, gtrOn = on("guitar");
  setArm(riff.armR, 0.7 + (gtrOn ? 0.22 * ph(2) : 0), 0.5);
  setArm(riff.armL, 0.85, -0.85);
  riff.head.rotation.set(gtrOn ? 0.22 * Math.max(0, ph(1)) : 0, 0, 0);
  riff.body.position.y = riff.baseY - (gtrOn ? 0.6 * Math.abs(ph(1)) : 0);

  const bass = band.bass, bassOn = on("bass");
  setArm(bass.armR, 0.6 + (bassOn ? 0.12 * ph(1) : 0), 0.45);
  setArm(bass.armL, 0.8, -0.9);
  bass.head.rotation.set(bassOn ? 0.14 * Math.max(0, ph(0.5)) : 0, 0, 0);

  const dr = band.drums, click = countIn(tl, t);
  if (on("drums")) {
    setArm(dr.armR, 0.95 + 0.35 * Math.max(0, ph(2)), 0.25);
    setArm(dr.armL, 0.95 + 0.35 * Math.max(0, -ph(1)), -0.25);
    dr.head.rotation.set(0.16 * Math.max(0, ph(1)), 0, 0);
  } else if (click >= 0) {                                  // sticks up, clicking on each beat
    const hit = Math.max(0, Math.cos(2 * Math.PI * beat)) ** 6;
    setArm(dr.armR, 2.3 - 0.25 * hit, 0.35); setArm(dr.armL, 2.3 - 0.25 * hit, -0.35);
    dr.head.rotation.set(0.12 * hit, 0, 0);
  } else {
    setArm(dr.armR, 0.95, 0.25); setArm(dr.armL, 0.95, -0.25); dr.head.rotation.set(0, 0, 0);
  }

  const pr = band.producer, bandOn = sitarOn || gtrOn || bassOn;
  const stop = speaking(tl, "producer", t)?.line.text.startsWith("Hold on");
  setArm(pr.armR, 1.1 + 0.05 * Math.sin(t * 0.7), 0.2);
  setArm(pr.armL, 1.05, -0.2);
  pr.head.rotation.set(stop ? -0.12 : 0.1 + (bandOn ? 0.08 * Math.max(0, ph(1)) : 0), 0, 0);
  rec.visible = bandOn;                                      // REC lights while a take is running

  for (const [key, who] of Object.entries(WHO)) {           // talking: a quick nod and a tilt
    if (speaking(tl, who, t)) {
      band[key].head.rotation.x += 0.06 * Math.sin(t * 15);
      band[key].head.rotation.z = 0.05 * Math.sin(t * 4.5);
    }
  }
}

const WHO = { lead: "sitar", riff: "guitar", bass: "bass", drums: "drums", producer: "producer" };

// ---------------------------------------------------------------- scene, camera, light
function lights(scene) {
  scene.add(new THREE.HemisphereLight("#fff6e8", "#6a5a7a", 1.5));
  const sun = new THREE.DirectionalLight("#fff1dc", 2.2);
  sun.position.set(260, 420, 320);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  Object.assign(sun.shadow.camera, { left: -300, right: 300, top: 240, bottom: -240, near: 10, far: 1400 });
  sun.shadow.bias = -0.0006;
  scene.add(sun);
  const fill = new THREE.DirectionalLight("#cfd8ff", 0.5);
  fill.position.set(-300, 200, 200);
  scene.add(fill);
}

function camera() {
  const halfH = 126, halfW = halfH * (W / H);
  const cam = new THREE.OrthographicCamera(-halfW, halfW, halfH, -halfH, 1, 4000);
  cam.position.set(418, 389, 885);
  cam.lookAt(-4, 65, -20);
  return cam;
}

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(PAGE);
const studioRoom = room();
const rec = studioRoom.userData.rec;
scene.add(studioRoom);
lights(scene);
const band = buildBand(scene);
const cam = camera();
const tl = await loadTimeline();
const overlay = new Overlay();
const heads = Object.fromEntries(Object.entries(WHO).map(([key, who]) => [who, band[key].head]));

/** Draw the frame at `t` seconds (deterministic: no clock is read). */
window.renderAt = (t) => {
  perform(band, tl, t);
  renderer.render(scene, cam);
  overlay.step(stepAt(tl, t));
  overlay.draw(bubbles(tl, t), heads, cam);
};
window.ROOM = ROOM;
window.SESSION_END = tl.end;
await document.fonts.ready;
window.renderAt(0);
window.studioReady = true;
