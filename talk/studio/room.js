// The studio room as a cut-away diorama: wood floor on a base, two walls (back and left) dressed
// with acoustic panels, a control-room window and a REC light, and a rug under the band.
import { box, group, shade, slab } from "./voxel.js";

export const ROOM = { x0: -230, x1: 270, z0: -150, z1: 210, wall: 230 };
const INDIGO = "#33357D", PURPLE = "#715397", TERRA = "#D26F5D", MUSTARD = "#E0AA55", SKY = "#79B8CC";

export function room() {
  const g = group();
  const { x0, x1, z0, z1, wall } = ROOM, w = x1 - x0, d = z1 - z0, cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
  g.add(slab(w + 8, 13, d + 8, "#4a3a5a", cx - 4, -14, cz - 4));               // the diorama base (top below the planks)
  for (let z = z0, k = 0; z < z1; z += 14, k++) {                               // floor planks
    g.add(slab(w, 1, 14, k % 2 ? "#a0703f" : "#946638", cx, -1, z + 7));
  }
  g.add(slab(w + 6, wall, 6, INDIGO, cx - 3, -1, z0 - 3));                      // back wall
  g.add(slab(6, wall, d + 6, shade(INDIGO, -14), x0 - 3, -1, cz - 3));           // left wall
  backPanels(g);
  leftWall(g);
  g.add(slab(250, 0.8, 150, TERRA, 0, 0, -25));                                 // the rug
  g.add(slab(236, 1, 136, shade(TERRA, -18), 0, 0.1, -25));
  g.add(slab(220, 1.2, 120, TERRA, 0, 0.2, -25));
  for (const x of [-105, 105]) g.add(slab(9, 1.4, 120, MUSTARD, x, 0.3, -25));
  return g;
}

/** Acoustic foam tiles in two tones. */
function backPanels(g) {
  const { z0 } = ROOM;
  for (let x = -205, i = 0; x <= 210; x += 40, i++) {
    for (let y = 26, j = 0; y < 210; y += 40, j++) {
      const c = (i + j) % 2 ? PURPLE : shade(INDIGO, 18);
      g.add(slab(34, 34, 4, c, x, y, z0 + 2));
      g.add(slab(26, 26, 2, shade(c, 14), x, y + 4, z0 + 5));
    }
  }
}

/** The control-room window (sky glass, a desk lamp glow beyond) and the REC light. */
function leftWall(g) {
  const { x0 } = ROOM;
  g.add(slab(4, 64, 110, "#2a2138", x0 + 2, 44, -60));
  g.add(slab(3, 56, 102, SKY, x0 + 4, 48, -60));
  g.add(slab(3.4, 56, 3, "#2a2138", x0 + 4, 48, -60));                            // the mullion
  g.add(slab(3.6, 16, 18, shade(SKY, 30), x0 + 4.2, 80, -88));                     // glare
  g.add(box(4, 10, 28, "#1a1520", x0 + 3, 126, -60));
  const rec = box(4.4, 7, 22, "#e8433a", x0 + 3.4, 126, -60);                      // REC
  g.add(rec);
  g.userData.rec = rec;                                                            // lit while a take runs
  for (let z = 15; z < 110; z += 40) for (let y = 26; y < 210; y += 40) {
    g.add(slab(4, 34, 34, (z + y) % 80 ? shade(INDIGO, 10) : PURPLE, x0 + 2, y, z));
  }
}
