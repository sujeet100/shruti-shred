// A persona in voxels, built from the SAME spec as its pixel sprite (talk/sprites/personas.mjs).
// Heights follow gen_sprites.mjs: sprite row y sits at height 61 - y (the soles at 0) and sprite
// column x at x - 24, so the figure is centred on x = 0 and faces +z. Its right hand is on -x,
// matching the sprite, whose image-left is the persona's right.
import { box, group, shade, slab } from "./voxel.js";

const OUTLINE = "#4a3f6b", SHOE = "#1a1520", DARK = "#141018", WHITE = "#f4efe2";
const HIP = 11;                     // height of the hips when standing (top of the legs)
const FACE = 8;                     // z of the face (the head is 16 deep)

/**
 * Build a persona. `pose`: "stand", "chair" (on a seat of height `seat`) or "cross" (cross-legged
 * on the floor or a platform). Returns the root and the parts a timeline animates: `body` (bobs),
 * `head` (nods, pivot at the neck), `armR` / `armL` (swing, pivot at the shoulder) and `hold`
 * (where an instrument attaches, in body space).
 */
export function persona(spec, { pose = "stand", seat = 16 } = {}) {
  const body = group();
  const legs = legsFor(spec, pose, seat);
  const hipY = pose === "stand" ? HIP : pose === "chair" ? seat : 5;
  body.position.y = hipY - HIP;

  torso(body, spec);
  const head = headGroup(spec);
  body.add(head);
  const armR = arm(spec, -13), armL = arm(spec, 13);
  body.add(armR, armL);
  const hold = group(); body.add(hold);

  const root = group([legs, body]);
  return { root, body, head, armR, armL, hold, baseY: body.position.y };
}

// ---------------------------------------------------------------- body
function torso(body, s) {
  const coat = s.coat, cHi = shade(coat, 18), cSh = shade(coat, -22);
  const long = !!s.robe;
  const bottom = long ? 4 : HIP;                                  // robe reaches the shins
  body.add(slab(22, 31 - bottom, 12, coat, 0, bottom, 0));
  if (long) body.add(slab(24, 11, 13, coat, 0, 4, 0));
  body.add(slab(1, 31 - bottom - 1, 12.2, cHi, -10.6, bottom + 1, 0));  // lit edge, as in the sprite
  body.add(slab(2, 31 - bottom - 1, 12.2, cSh, 10.2, bottom + 1, 0));
  body.add(slab(6, 4, 6, shade(s.skin, -26), 0, 30, 0));             // neck
  front(body, s, bottom);
}

/** Everything painted on the chest: shirt front, tee, trim, buttons, zip, drawstrings. */
function front(body, s, bottom) {
  const z = 6.2;
  if (s.shirtFront) body.add(slab(6, 14, 0.6, s.shirtFront, 0, 17, z));
  else body.add(slab(4, 2, 0.6, s.skin, 0, 29, z));                 // the open collar
  if (s.bowtie) body.add(slab(6, 2, 1, OUTLINE, 0, 29, z + 0.4));
  if (s.tee) { body.add(slab(10, 6, 0.6, s.tee, 0, 19, z)); body.add(slab(6, 2, 0.8, shade(s.tee, -40), 0, 21, z)); }
  if (s.zip) body.add(slab(1, 31 - bottom - 2, 0.7, "#9a94a8", 0, bottom + 1, z));
  if (s.buttons) for (let h = 27; h > bottom + 2; h -= 4) body.add(slab(1, 1, 0.8, s.buttons, 0, h, z));
  if (s.drawstrings) { body.add(slab(1, 5, 0.8, "#e8e2d0", -3, 25, z)); body.add(slab(1, 5, 0.8, "#e8e2d0", 2, 25, z)); }
  if (s.trim === "sash") {
    const sash = box(2.4, 26, 0.8, s.accent, 0, 21, z + 0.1);
    sash.rotation.z = -0.78;                                       // shoulder to hip, like the sprite
    body.add(sash);
  } else if (s.trim === "belt") {
    body.add(slab(22.2, 2, 12.4, s.accent, 0, 15, 0)); body.add(slab(2, 2, 1, "#ffd97a", 0, 15, z + 0.2));
  } else if (s.trim !== "none") body.add(slab(22.2, 1, 12.4, s.accent, 0, 26, 0));
}

function arm(s, x) {
  const sleeve = s.sleeve || s.coat;
  const a = group([], x, 30, 0);                                   // pivot at the shoulder
  a.add(box(4, 14, 5, sleeve, 0, -7, 0));
  a.add(box(4, 4, 4, s.skin, 0, -16, 0.5));                         // the hand
  return a;
}

// ---------------------------------------------------------------- legs
function legsFor(s, pose, seat) {
  const pants = s.pants || "#2a2438";
  const g = group();
  if (pose === "stand") {
    for (const x of [-4, 4]) {
      if (!s.robe) g.add(slab(6, 9, 6, pants, x, 2, 0));
      g.add(slab(7, 3, 9, SHOE, x, 0, 1.5));
    }
  } else if (pose === "chair") {
    for (const x of [-5, 5]) {
      g.add(box(6, 6, 15, s.robe ? s.coat : pants, x, seat - 3, 5));          // thigh, forward
      g.add(slab(6, seat - 6, 6, s.robe ? s.coat : pants, x, 3, 10));        // shin, down
      g.add(slab(7, 3, 9, SHOE, x, 0, 12));
    }
  } else {                                                          // cross-legged
    const cloth = s.robe ? s.coat : pants;
    g.add(slab(30, 6, 18, cloth, 0, 0, 3));                          // the lap
    for (const [x, r] of [[-6, 0.35], [6, -0.35]]) {
      const shin = slab(6, 5, 22, shade(cloth, -12), x, 1, 7);
      shin.rotation.y = r;
      g.add(shin);
    }
    g.add(slab(6, 3, 6, s.skin, -12, 0, 13));                        // bare feet peek out
    g.add(slab(6, 3, 6, s.skin, 12, 0, 13));
  }
  return g;
}

// ---------------------------------------------------------------- head
function headGroup(s) {
  const skin = s.skin, skSh = shade(skin, -26), skHi = shade(skin, 14);
  const h = group([], 0, 33, 0);                                    // pivot at the neck
  const at = (y) => y - 33;                                         // body height -> head space
  h.add(slab(18, 19, 16, skin, 0, at(33), 0));
  h.add(slab(2, 6, 0.6, skHi, -6, at(45), FACE));                   // the lit cheekbone
  h.add(slab(1, 4, 4, skin, -9.5, at(40), 0));                      // ears
  h.add(slab(1, 4, 4, skSh, 9.5, at(40), 0));
  face(h, s, at);
  hair(h, s, at);
  return h;
}

function face(h, s, at) {
  const skin = s.skin, browC = shade(s.hair, -10), z = FACE + 0.3;
  if (s.eyesClosed) {
    for (const x of [-4, 4]) h.add(slab(4, 1, 0.6, "#241a2e", x, at(42), z));
  } else {
    for (const x of [-4, 4]) {
      h.add(slab(2, 3, 0.6, DARK, x, at(41), z));
      h.add(slab(1, 1, 0.8, WHITE, x - 0.5, at(43), z + 0.1));     // catchlight
    }
  }
  for (const x of [-4, 4]) h.add(slab(4, 1, 0.6, browC, x, at(46), z));
  if (s.frown) { h.add(slab(1, 1, 0.6, browC, -2.5, at(47), z)); h.add(slab(1, 1, 0.6, browC, 2.5, at(47), z)); }
  h.add(slab(2, 2, 1.6, shade(skin, -26), 0, at(39), z + 0.5));      // nose
  if (s.beard) {
    h.add(slab(14, 7, 1.4, s.beard, 0, at(33), z));
    h.add(slab(2, 6, 14, s.beard, -8.2, at(37), 0)); h.add(slab(2, 6, 14, s.beard, 8.2, at(37), 0));
    h.add(slab(4, 1, 1.6, shade(s.beard, -40), 0, at(37), z + 0.2));
  } else {
    h.add(slab(4, 1, 0.6, shade(skin, -55), 0, at(37), z));         // mouth
    if (s.stubble) h.add(slab(13, 2, 0.4, shade(skin, -30), 0, at(34), z));
  }
  if (s.glasses) {
    const f = "#e8e2d0";
    for (const x of [-4, 4]) {
      h.add(slab(6, 1, 0.6, f, x, at(45), z + 0.4)); h.add(slab(6, 1, 0.6, f, x, at(40), z + 0.4));
      h.add(slab(1, 5, 0.6, f, x - 2.5, at(40), z + 0.4)); h.add(slab(1, 5, 0.6, f, x + 2.5, at(40), z + 0.4));
    }
    h.add(slab(2, 1, 0.6, f, 0, at(44), z + 0.4));
  }
  if (s.tilak) { h.add(slab(1, 4, 0.6, "#c0392b", 0, at(47), z)); h.add(slab(1, 1, 0.7, "#f2b53c", 0, at(47), z + 0.1)); }
}

function hair(h, s, at) {
  const hair = s.hair, hHi = shade(hair, 30);
  if (s.beanie) {
    h.add(slab(20, 9, 18, s.beanie, 0, at(48), 0));
    h.add(slab(22, 3, 19, shade(s.beanie, 22), 0, at(48), 0));
    h.add(slab(5, 4, 5, shade(s.beanie, 30), 0, at(57), 0));
  } else if (s.cap) {
    h.add(slab(19, 7, 18, s.cap, 0, at(49), 0));
    h.add(slab(17, 1.6, 9, shade(s.cap, -10), 0, at(49), 12));     // the brim, forward
    h.add(slab(3, 2, 0.6, s.accent, 0, at(52), 9.2));
    h.add(slab(2, 5, 12, hair, -9.5, at(44), -1)); h.add(slab(2, 4, 12, hair, 9.5, at(45), -1));
  } else {
    h.add(slab(20, 6, 18, hair, 0, at(49), -0.5));
    h.add(slab(10, 1, 6, hHi, -2, at(55), 4));
    h.add(slab(2, 7, 16, hair, -9.5, at(42), -0.5)); h.add(slab(2, 7, 16, hair, 9.5, at(42), -0.5));
    h.add(slab(20, 14, 2, hair, 0, at(41), -8.6));                  // back of the head
    if (s.longhair) {
      h.add(slab(22, 26, 3, hair, 0, at(23), -9.5));
      h.add(slab(3, 24, 10, hair, -11, at(24), -3)); h.add(slab(3, 24, 10, hair, 11, at(24), -3));
    }
    if (s.topknot) { h.add(slab(7, 5, 7, hair, 0, at(55), -1)); h.add(slab(7.4, 1, 7.4, s.accent, 0, at(56), -1)); }
    if (s.receding) h.add(slab(12, 3, 1, s.skin, 0, at(49), FACE + 1.2));
  }
  if (s.headphones) {
    h.add(slab(18, 2, 4, "#2a2138", 0, at(57), 0));
    for (const x of [-11, 11]) { h.add(slab(2, 10, 3, "#2a2138", x * 0.9, at(48), 0)); h.add(slab(4, 9, 7, s.accent, x, at(38), 0)); }
  }
}

/** Swing helpers the timeline uses: rotations in radians about the shoulder or neck. */
export function setArm(a, forward, out = 0) { a.rotation.set(-forward, 0, out); }
export function nod(p, amount) { p.head.rotation.x = amount; }
