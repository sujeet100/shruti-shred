// The band's instruments and the studio furniture, in the sprites' palette (gen_sprites.mjs).
// Each builder returns a group in its own local frame; studio.js places and poses it.
import { ball, box, cylinder, group, shade, slab } from "./voxel.js";

const GOLD = "#f2b53c", PALE = "#c9c2b0", STEEL = "#8c8399", BLACK = "#141019";

/** The sitar, gourd at the origin, neck rising along +y (tilt the group to hold it). */
export function sitar() {
  const wood = "#8a4a1a", light = "#c07a34", neck = "#6a3a14";
  const g = group();
  g.add(ball(10, wood, 0, 0, 0, 1, 0.95, 0.8));                    // the kaddu, the main gourd
  g.add(ball(7, light, 0, 0, 3.2, 1, 1, 0.45));                     // its face plate
  g.add(box(7, 1.4, 1.4, "#efe7d2", 0, -1, 7.4));                   // the jawari bridge
  g.add(slab(5, 62, 4, neck, 0, 6, 0));
  g.add(slab(1, 62, 4.2, shade(neck, 26), -2, 6, 0));
  for (let y = 12; y < 64; y += 4) g.add(box(5.6, 0.6, 1.2, PALE, 0, y, 2.2));       // curved frets
  g.add(slab(0.5, 70, 0.5, GOLD, -0.8, -2, 2.6));                   // the playing string
  g.add(slab(0.5, 70, 0.5, "#ffd97a", 0.8, -2, 2.6));
  g.add(ball(5, wood, 0, 52, -4, 1, 1, 0.9));                        // the tumba, the upper gourd
  g.add(slab(6, 9, 5, "#4a2810", 0, 68, 0));                         // pegbox
  for (const y of [70, 73, 76]) { g.add(box(3, 1.2, 1.2, light, -4, y, 0)); g.add(box(3, 1.2, 1.2, light, 4, y - 1.5, 0)); }
  return g;
}

/** A guitar (or bass), body at the origin facing +z, neck along +x. */
export function guitar({ color = "#b8262f", bass = false } = {}) {
  const g = group();
  const len = bass ? 46 : 34, strings = bass ? 4 : 6;
  g.add(box(20, 14, 4, color, 0, 0, 0));
  g.add(box(14, 7, 4, color, -1, 8, 0));                             // upper bout
  g.add(box(16, 6, 4, color, -2, -9, 0));                            // lower bout
  g.add(box(6, 4, 4, shade(color, 24), 9, 7, 0));                    // the horn
  if (bass) g.add(box(10, 9, 0.6, "#e9e3d4", -1, -3, 2.3));          // pickguard
  g.add(box(3, 6, 1, BLACK, 2, 0, 2.4)); g.add(box(3, 6, 1, BLACK, -4, 0, 2.4));       // pickups
  g.add(box(2, 7, 1, STEEL, -8, 0, 2.4));                            // bridge
  g.add(box(1.5, 1.5, 1, GOLD, -7, -7, 2.4)); g.add(box(1.5, 1.5, 1, GOLD, -4, -9, 2.4));
  g.add(box(len, 3, 2, "#3a2618", 10 + len / 2, 0, 0.5));
  for (let x = 14; x < 10 + len; x += bass ? 5 : 4) g.add(box(0.5, 3.2, 2.2, PALE, x, 0, 0.6));
  for (let k = 0; k < strings; k++) g.add(box(10 + len + 8, 0.25, 0.3, "#d8d0c0", (10 + len) / 2 - 4, -1.2 + (2.4 * k) / (strings - 1), 1.8));
  g.add(box(9, 5, 2, BLACK, 14 + len, 0, 0.5));                      // headstock
  for (let k = 0; k < strings / 2; k++) { g.add(box(1.5, 1.5, 1.5, PALE, 12 + len + k * 3, 3.2, 0.5)); g.add(box(1.5, 1.5, 1.5, PALE, 12 + len + k * 3, -3.2, 0.5)); }
  return g;
}

/** A drum kit around a throne at the origin; the drummer faces +z. */
export function drumKit() {
  const shell = "#2a2540", head = "#d8d0c0", kickRing = "#ff2e88";
  const g = group();
  g.add(cylinder(6, 15, BLACK, 0, 7.5, 0));                          // throne
  const kick = group([cylinder(12, 15, "#1b1626"), cylinder(9.5, 15.4, kickRing), cylinder(6, 15.8, "#120f1d")], 0, 12, 24);
  kick.rotation.x = Math.PI / 2;
  g.add(kick);
  g.add(drum(6, 5, shell, head, 8, 18, 12, 0.25));                   // snare (player's left)
  g.add(drum(5, 6, shell, head, -5, 28, 20, 0.45));                  // rack tom
  g.add(drum(5, 6, shell, head, 6, 28, 21, 0.45));
  g.add(slab(14, 15, 14, shell, -17, 0, 10)); g.add(cylinder(7, 1, head, -17, 15.5, 10));     // floor tom
  g.add(cymbal(7, 17, 25, 8, 0.05)); g.add(cymbal(7, 17, 23.6, 8, 0.05));                     // hi-hat
  g.add(cymbal(11, 20, 40, 20, 0.3)); g.add(cymbal(12, -24, 34, 16, -0.25));                   // crash, ride
  return g;
}

function drum(r, h, shell, head, x, y, z, tilt) {
  const d = group([cylinder(r, h, shell), cylinder(r, 0.8, head, 0, h / 2 + 0.2, 0)], x, y, z);
  d.rotation.x = tilt;
  return d;
}

function cymbal(r, x, y, z, tilt) {
  const c = group([cylinder(r, 0.6, GOLD, 0, 0, 0, 14), cylinder(1.2, 1.4, "#ffd97a")], x, y, z);
  c.rotation.x = tilt;
  const stand = cylinder(0.6, y, STEEL, x, y / 2, z);
  return group([stand, c]);
}

/** The producer's desk: a console with faders and meters and two monitors. Faces -z, so a
 * producer seated at the origin facing +z looks over it. */
export function desk() {
  const g = group();
  g.add(slab(66, 2, 30, "#5a4030", 0, 22, 20));                       // the desk top
  for (const x of [-30, 30]) for (const z of [8, 32]) g.add(slab(2, 22, 2, "#3a2a20", x, 0, z));
  const console_ = group([box(56, 3, 22, "#12151f"), box(56, 0.6, 22, "#2a3550", 0, 1.6, 0)], 0, 25.5, 19);
  console_.rotation.x = 0.28;
  for (let x = -24; x <= 24; x += 4) {
    console_.add(box(1, 0.6, 12, "#05060a", x, 1.8, 2));
    console_.add(box(2.6, 1.6, 2, "#8c8399", x, 2.4, 2 + ((x * 7) % 9) - 4));        // fader caps
    const led = ["#38e0cf", GOLD, "#ff2e88"][((x + 24) / 4) % 3];
    console_.add(box(1.4, 1.4, 1.4, led, x, 2.2, -7));
  }
  g.add(console_);
  for (const x of [-26, 26]) {
    const mon = group([box(11, 15, 11, "#1a1724"), cylinder(3.5, 1, "#79b8cc", 0, -2, 5.6), cylinder(1.6, 1, "#79b8cc", 0, 4.5, 5.6)], x, 32, 30);
    mon.children[1].rotation.x = Math.PI / 2; mon.children[2].rotation.x = Math.PI / 2;
    mon.rotation.y = Math.PI + (x > 0 ? 0.35 : -0.35);                                    // turned to the chair
    g.add(mon);
  }
  return g;
}

/** A stool / chair seat at height `h`. */
export function stool(h = 16, color = "#2a2138") {
  return group([cylinder(7, 2, color, 0, h - 1, 0), cylinder(1.4, h - 2, STEEL, 0, (h - 2) / 2, 0), cylinder(5, 1, STEEL, 0, 0.5, 0)]);
}

/** An amp stack: head on a 4x12 cab. */
export function amp(accent = "#ff2e88") {
  const g = group();
  g.add(slab(38, 36, 18, "#161320", 0, 0, 0));
  for (let y = 4; y < 34; y += 3) g.add(slab(34, 1, 0.4, "#221d2e", 0, y, 9.1));               // grille cloth
  for (const [x, y] of [[-9, 9], [9, 9], [-9, 26], [9, 26]]) {
    const cone = cylinder(6.5, 0.8, "#0a0813", x, y, 9.2, 12); cone.rotation.x = Math.PI / 2; g.add(cone);
  }
  g.add(slab(40, 11, 18, "#161320", 0, 36, 0));
  g.add(slab(40, 1.4, 18.4, "#2a2540", 0, 46, 0));
  for (let x = -14; x <= 10; x += 4) g.add(box(1.6, 1.6, 1.4, GOLD, x, 41, 9.4));
  g.add(slab(7, 2.4, 0.6, accent, 13, 40, 9.3));
  return g;
}

/** A mic on a boom stand, the mic at height `h`, pointing along +z. */
export function micStand(h = 50) {
  const boom = group([box(1, 1, 18, STEEL, 0, 0, 9), box(3, 3, 6, BLACK, 0, 0, 19), box(3.4, 3.4, 2, "#4a4560", 0, 0, 22)], 0, h, 0);
  boom.rotation.x = 0.25;
  return group([cylinder(5, 1, STEEL, 0, 0.5, 0), cylinder(0.7, h, STEEL, 0, h / 2, 0), boom]);
}

/** The takht: a low platform with a white sheet and a bolster, where the sitarist sits. */
export function takht() {
  return group([slab(52, 9, 40, "#7a5230", 0, 0, 0), slab(50, 1.4, 38, "#efe7d2", 0, 9, 0),
                slab(46, 7, 7, "#d26f5d", 0, 10, -16), slab(46, 1, 7.2, "#e0aa55", 0, 13, -16)]);
}

/** A tanpura leaning on the wall: drone, the raga's ground. */
export function tanpura() {
  const g = group([ball(13, "#9a5a24", 0, 13, 0, 1, 1.05, 0.8), slab(6, 72, 5, "#7a4a1e", 0, 20, -1), slab(8, 6, 6, "#4a2810", 0, 92, -1)]);
  for (const x of [-1.5, -0.5, 0.5, 1.5]) g.add(slab(0.3, 80, 0.3, GOLD, x, 14, 1.8));
  g.rotation.z = 0.12; g.rotation.x = -0.12;
  return g;
}
