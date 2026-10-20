// High-fidelity pixel sprites (48x64 personas, large instruments) in the demo UI's palette.
// Draw into a pixel grid, auto-outline the silhouette, emit run-merged SVG rects.
import { writeFileSync, mkdirSync } from "node:fs";
import { PERSONAS } from "./personas.mjs";
const OUT_DIR = new URL("./svg/", import.meta.url).pathname;
mkdirSync(OUT_DIR, { recursive: true });

const OUTLINE = "#4a3f6b", SHADOW = "SHADOW";
function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const cl = (v) => Math.max(0, Math.min(255, v));
  const r = cl((n >> 16) + amt), g = cl(((n >> 8) & 255) + amt), b = cl((n & 255) + amt);
  return "#" + ((r << 16) | (g << 8) | b).toString(16).padStart(6, "0");
}

class Grid {
  constructor(w, h) { this.w = w; this.h = h; this.px = new Array(w * h).fill(null); }
  set(x, y, c) { x = Math.round(x); y = Math.round(y); if (x < 0 || y < 0 || x >= this.w || y >= this.h) return; this.px[y * this.w + x] = c; }
  get(x, y) { if (x < 0 || y < 0 || x >= this.w || y >= this.h) return null; return this.px[y * this.w + x]; }
  clear(x, y) { if (x >= 0 && y >= 0 && x < this.w && y < this.h) this.px[y * this.w + x] = null; }
  rect(x, y, w, h, c) { for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) this.set(i, j, c); }
  ellipse(cx, cy, rx, ry, c) {
    for (let y = Math.floor(cy - ry); y <= Math.ceil(cy + ry); y++)
      for (let x = Math.floor(cx - rx); x <= Math.ceil(cx + rx); x++)
        if (((x - cx) ** 2) / (rx * rx) + ((y - cy) ** 2) / (ry * ry) <= 1) this.set(x, y, c);
  }
  line(x0, y0, x1, y1, c, t = 1) {
    const n = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) || 1;
    for (let k = 0; k <= n; k++) { const x = x0 + (x1 - x0) * k / n, y = y0 + (y1 - y0) * k / n; this.rect(Math.round(x - (t - 1) / 2), Math.round(y - (t - 1) / 2), t, t, c); }
  }
  poly(pts, c) {
    const ys = pts.map(p => p[1]); const y0 = Math.floor(Math.min(...ys)), y1 = Math.ceil(Math.max(...ys));
    for (let y = y0; y <= y1; y++) {
      const xs = []; const yy = y + 0.5;
      for (let i = 0; i < pts.length; i++) {
        const [ax, ay] = pts[i], [bx, by] = pts[(i + 1) % pts.length];
        if ((ay <= yy && by > yy) || (by <= yy && ay > yy)) xs.push(ax + (yy - ay) * (bx - ax) / (by - ay));
      }
      xs.sort((a, b) => a - b);
      for (let k = 0; k + 1 < xs.length; k += 2) for (let x = Math.ceil(xs[k] - 0.5); x <= Math.floor(xs[k + 1] - 0.5); x++) this.set(x, y, c);
    }
  }
  outline(c = OUTLINE) {
    const add = [];
    for (let y = 0; y < this.h; y++) for (let x = 0; x < this.w; x++) {
      if (this.get(x, y) !== null) continue;
      const n = [this.get(x - 1, y), this.get(x + 1, y), this.get(x, y - 1), this.get(x, y + 1)];
      if (n.some(v => v !== null && v !== SHADOW)) add.push([x, y]);
    }
    add.forEach(([x, y]) => this.set(x, y, c));
  }
  under(fn) { // draw only into empty pixels (ground shadows)
    const g = new Grid(this.w, this.h); fn(g);
    g.px.forEach((v, i) => { if (v !== null && this.px[i] === null) this.px[i] = v; });
  }
  svg() {
    let r = "";
    for (let y = 0; y < this.h; y++) {
      let x = 0;
      while (x < this.w) {
        const c = this.get(x, y); if (c === null) { x++; continue; }
        let e = x; while (e + 1 < this.w && this.get(e + 1, y) === c) e++;
        r += c === SHADOW ? `<rect x="${x}" y="${y}" width="${e - x + 1}" height="1" fill="#000" fill-opacity=".35"/>`
                          : `<rect x="${x}" y="${y}" width="${e - x + 1}" height="1" fill="${c}"/>`;
        x = e + 1;
      }
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${this.w} ${this.h}" shape-rendering="crispEdges">${r}</svg>`;
  }
}

// ------------------------------------------------------------------ personas
function person(s) {
  const g = new Grid(48, 64);
  const skin = s.skin, skSh = shade(skin, -26), skHi = shade(skin, 14);
  const coat = s.coat, cSh = shade(coat, -22), cHi = shade(coat, 18);
  const hair = s.hair, hSh = shade(hair, -18), hHi = shade(hair, 30);
  const pants = s.pants || "#2a2438", shoe = "#1a1520";
  const long = !!s.robe;

  // legs + shoes
  if (!long) {
    g.rect(17, 50, 6, 9, pants); g.rect(25, 50, 6, 9, pants);
    g.rect(22, 50, 1, 9, shade(pants, -16)); g.rect(30, 50, 1, 9, shade(pants, -16));
  }
  g.rect(16, 58, 7, 3, shoe); g.rect(25, 58, 7, 3, shoe); g.rect(16, 58, 6, 1, "#2e2838"); g.rect(25, 58, 6, 1, "#2e2838");

  // torso (+ robe skirt)
  const bottom = long ? 57 : 50;
  g.rect(13, 30, 22, bottom - 30, coat);
  if (long) g.rect(12, 46, 24, bottom - 46, coat);
  g.clear(13, 30); g.clear(34, 30);
  g.rect(14, 31, 1, bottom - 32, cHi);                     // light from the left
  g.rect(33, 31, 2, bottom - 32, cSh);                     // shadow side
  g.rect(13, bottom - 1, 22, 1, cSh);
  if (long) { g.rect(19, 47, 1, 9, cSh); g.rect(28, 48, 1, 8, cSh); }   // robe folds

  // collar / shirt front
  if (s.shirtFront) { g.rect(21, 30, 6, 14, s.shirtFront); g.rect(23, 31, 2, 12, shade(s.shirtFront, -14)); }
  else { g.set(22, 30, skin); g.set(23, 30, skin); g.set(24, 30, skin); g.set(25, 30, skin); g.set(23, 31, skin); g.set(24, 31, skin); }
  if (s.bowtie) { g.rect(21, 30, 2, 2, OUTLINE); g.rect(25, 30, 2, 2, OUTLINE); g.rect(23, 30, 2, 2, "#241a2e"); }
  if (s.buttons) for (let y = 34; y < bottom - 2; y += 4) g.set(24, y, s.buttons);
  if (s.zip) g.rect(24, 31, 1, bottom - 32, "#9a94a8");
  if (s.drawstrings) { g.rect(21, 31, 1, 5, "#e8e2d0"); g.rect(26, 31, 1, 5, "#e8e2d0"); }
  if (s.tee) { g.rect(19, 36, 10, 6, s.tee); g.rect(21, 38, 6, 2, shade(s.tee, -40)); }

  // trim: sash (diagonal stole), belt, or stripe in the role accent
  if (s.trim === "sash") g.line(15, 31, 32, 48, s.accent, 2);
  else if (s.trim === "belt") { g.rect(13, 44, 22, 2, s.accent); g.rect(23, 44, 2, 2, "#ffd97a"); }
  else g.rect(13, 34, 22, 1, s.accent);

  // arms
  const sleeve = s.sleeve || coat;
  g.rect(9, 31, 4, 14, sleeve); g.rect(9, 31, 1, 14, shade(sleeve, 16)); g.rect(12, 32, 1, 13, shade(sleeve, -20));
  g.rect(9, 45, 4, 4, skin); g.rect(12, 45, 1, 4, skSh);
  if (s.pose === "baton" || s.pose === "horns") {
    g.rect(35, 17, 4, 14, sleeve); g.rect(38, 17, 1, 14, shade(sleeve, -20));
    g.rect(35, 13, 4, 4, skin); g.rect(38, 13, 1, 4, skSh);
    if (s.pose === "baton") g.line(38, 12, 45, 1, "#efe7d2", 1);
    else { g.rect(35, 10, 1, 3, skin); g.rect(38, 10, 1, 3, skin); }
  } else {
    g.rect(35, 31, 4, 14, sleeve); g.rect(38, 32, 1, 13, shade(sleeve, -20));
    g.rect(35, 45, 4, 4, skin); g.rect(38, 45, 1, 4, skSh);
  }

  // neck + head
  g.rect(21, 27, 6, 4, skSh);
  g.rect(15, 9, 18, 19, skin);
  [[15, 9], [32, 9], [15, 27], [32, 27], [16, 27], [31, 27]].forEach(([x, y]) => g.clear(x, y));
  g.rect(31, 11, 2, 15, skSh); g.rect(17, 26, 14, 1, skSh); g.rect(16, 10, 2, 6, skHi);
  g.rect(14, 17, 1, 4, skin); g.rect(33, 17, 1, 4, skSh);              // ears

  // face
  const browC = shade(hair, -10);
  if (s.eyesClosed) {
    [[18, 19], [19, 18], [20, 18], [21, 19], [26, 19], [27, 18], [28, 18], [29, 19]].forEach(([x, y]) => g.set(x, y, "#241a2e"));
  } else {
    g.rect(19, 17, 2, 3, "#141018"); g.rect(27, 17, 2, 3, "#141018");
    g.set(19, 17, "#f4efe2"); g.set(27, 17, "#f4efe2");                // catchlights
  }
  g.rect(18, 15, 4, 1, browC); g.rect(26, 15, 4, 1, browC);
  if (s.frown) { g.set(21, 14, browC); g.set(26, 14, browC); }
  g.set(24, 21, skSh); g.set(24, 22, skSh); g.set(23, 22, skSh);       // nose
  g.set(18, 22, shade(skin, -6)); g.set(29, 22, shade(skin, -10));     // cheeks
  if (s.beard) {
    g.rect(17, 21, 14, 7, s.beard); g.rect(16, 18, 2, 6, s.beard); g.rect(30, 18, 2, 6, s.beard);
    g.rect(18, 27, 12, 2, s.beard); g.rect(17, 21, 14, 1, shade(s.beard, 16));
    g.rect(22, 24, 4, 1, shade(s.beard, -40));
  } else if (s.stubble) {
    for (let x = 18; x < 31; x += 2) g.set(x, 26, shade(skin, -40));
    g.rect(22, 24, 4, 1, shade(skin, -55));
  } else {
    g.rect(22, 24, 4, 1, shade(skin, -55)); g.set(21, 23, shade(skin, -40)); g.set(26, 23, shade(skin, -40));
  }
  if (s.glasses) {
    const f = "#e8e2d0";
    g.rect(17, 16, 6, 1, f); g.rect(17, 20, 6, 1, f); g.rect(17, 16, 1, 5, f); g.rect(22, 16, 1, 5, f);
    g.rect(25, 16, 6, 1, f); g.rect(25, 20, 6, 1, f); g.rect(25, 16, 1, 5, f); g.rect(30, 16, 1, 5, f);
    g.rect(23, 17, 2, 1, f);
  }
  if (s.tilak) { g.rect(24, 10, 1, 4, "#c0392b"); g.set(24, 14, "#f2b53c"); }

  // hair / headgear
  if (s.beanie) {
    g.rect(14, 4, 20, 9, s.beanie); for (let x = 15; x < 34; x += 2) g.rect(x, 4, 1, 6, shade(s.beanie, -16));
    g.rect(13, 10, 22, 3, shade(s.beanie, 22)); g.ellipse(24, 3, 3, 2, shade(s.beanie, 30));
  } else if (s.cap) {
    g.rect(14, 5, 19, 7, s.cap); g.rect(14, 5, 19, 1, shade(s.cap, 24)); g.rect(26, 10, 15, 3, shade(s.cap, -10));
    g.rect(21, 7, 3, 2, s.accent); g.rect(14, 12, 2, 5, hair); g.rect(31, 12, 2, 4, hair);
  } else {
    g.rect(14, 6, 20, 6, hair); g.clear(14, 6); g.clear(33, 6);
    g.rect(14, 12, 2, 7, hair); g.rect(32, 12, 2, 7, hair);
    [17, 20, 23, 27, 30].forEach(x => g.set(x, 12, hair));
    g.rect(17, 7, 10, 1, hHi); g.rect(30, 8, 3, 4, hSh);
    if (s.longhair) { g.rect(11, 12, 5, 26, hair); g.rect(32, 12, 5, 26, hair); g.rect(12, 14, 1, 22, hHi); g.rect(35, 14, 1, 22, hSh); }
    if (s.topknot) { g.ellipse(24, 3, 4, 3, hair); g.rect(22, 5, 5, 1, s.accent); g.set(23, 2, hHi); }
    if (s.receding) { g.rect(18, 6, 12, 3, null); g.rect(17, 6, 14, 2, skin); g.rect(18, 8, 12, 1, skin); g.rect(19, 6, 6, 1, skHi); }
  }
  if (s.headphones) {
    g.rect(15, 3, 18, 2, "#2a2138"); g.rect(14, 4, 2, 4, "#2a2138"); g.rect(32, 4, 2, 4, "#2a2138");
    g.rect(11, 14, 4, 9, s.accent); g.rect(33, 14, 4, 9, s.accent); g.rect(12, 16, 2, 5, shade(s.accent, -60)); g.rect(34, 16, 2, 5, shade(s.accent, -60));
  }

  if (s.prop) PROPS[s.prop](g, s);
  g.outline();
  g.under(sh => sh.ellipse(24, 61.5, 16, 2.2, SHADOW));
  return g.svg();
}

const PROPS = {
  sitar(g) {
    const w = "#8a4a1a", wl = "#c07a34", wd = "#5e3110", neck = "#6a3a14";
    g.line(17, 44, 44, 5, neck, 4); g.line(16, 43, 43, 4, shade(neck, 26), 1);
    for (let k = 4; k < 36; k += 4) { const x = 17 + (27 * k) / 39, y = 44 - (39 * k) / 39; g.set(x + 1, y, "#c9c2b0"); g.set(x + 2, y + 1, "#c9c2b0"); }
    g.line(18, 44, 44, 6, "#f2b53c", 1);
    g.rect(41, 0, 6, 7, "#4a2810"); g.set(40, 2, "#f2b53c"); g.set(47, 3, "#f2b53c"); g.set(40, 5, "#f2b53c");
    g.ellipse(11, 50, 10, 8.5, w); g.ellipse(11, 50, 6, 5, wl); g.ellipse(8, 46, 3, 2, shade(wl, 20));
    g.rect(8, 51, 7, 1, "#e8e2d0");
    for (let a = 0; a < 6.28; a += 0.7) g.set(11 + 9 * Math.cos(a), 50 + 7.6 * Math.sin(a), "#f2b53c");
    g.rect(15, 41, 4, 4, "#e0b083");                                   // the plucking hand
  },
  guitar(g) {
    const red = "#b8262f";
    g.rect(2, 42, 28, 4, "#c9a46a"); g.rect(2, 42, 28, 1, "#e0c48a");
    for (let x = 6; x < 29; x += 3) g.rect(x, 42, 1, 4, "#7a5a30");
    g.rect(0, 39, 5, 10, "#141019"); g.set(1, 38, "#c9c2b0"); g.set(3, 38, "#c9c2b0"); g.set(1, 49, "#c9c2b0"); g.set(3, 49, "#c9c2b0");
    g.poly([[27, 37], [40, 35], [46, 38], [42, 44], [46, 50], [40, 53], [27, 51]], red);
    g.line(28, 37, 39, 36, shade(red, 40), 1);
    g.rect(31, 41, 6, 2, "#141019"); g.rect(31, 46, 6, 2, "#141019");
    g.set(32, 41, "#c9c2b0"); g.set(35, 41, "#c9c2b0"); g.set(32, 46, "#c9c2b0"); g.set(35, 46, "#c9c2b0");
    g.rect(5, 44, 33, 1, "#e8e2d0");
    g.set(40, 49, "#f2b53c"); g.set(42, 47, "#f2b53c");
    g.rect(34, 40, 4, 4, "#d9a679");                                   // strumming hand
  },
  rulebook(g, s) {
    g.rect(4, 39, 11, 14, "#2a2138"); g.rect(4, 39, 11, 1, shade("#2a2138", 30)); g.rect(14, 40, 2, 12, "#e8e2d0");
    g.rect(7, 43, 5, 5, s.accent); g.rect(8, 44, 3, 3, "#2a2138"); g.set(9, 45, s.accent);
  },
  mixer(g, s) {
    g.rect(3, 47, 42, 13, "#12151f"); g.rect(3, 47, 42, 2, "#2a3550"); g.rect(3, 59, 42, 1, "#0a0c14");
    for (let x = 7; x < 43; x += 5) { g.rect(x, 50, 1, 7, "#05060a"); g.rect(x - 1, 50 + ((x * 7) % 5), 3, 2, "#8c8399"); }
    ["#38e0cf", "#f2b53c", "#ff2e88"].forEach((c, i) => { for (let x = 5 + i * 2; x < 44; x += 6) g.set(x, 58, c); });
    g.set(44, 48, s.accent);
  },
  clipboard(g, s) {
    g.rect(33, 33, 12, 17, "#7a5230"); g.rect(34, 35, 10, 14, "#efe7d2"); g.rect(37, 32, 4, 2, "#9a94a8");
    for (let y = 37; y < 47; y += 3) g.rect(36, y, 6, 1, "#8c8399");
    g.set(36, 46, s.accent); g.set(37, 47, s.accent); g.set(38, 46, s.accent); g.set(39, 45, s.accent);
  },
  horn(g) {
    g.ellipse(39, 42, 7, 7, "#f2b53c"); g.ellipse(39, 42, 4, 4, "#8a5a10"); g.ellipse(39, 42, 2, 2, "#4a3008");
    g.rect(35, 36, 2, 2, "#ffd97a"); g.line(32, 42, 26, 32, "#d9a030", 2); g.rect(24, 30, 3, 2, "#c9c2b0");
  },
  rose(g) {
    g.line(37, 46, 41, 33, "#2f7d4a", 1); g.set(39, 39, "#3f9d5a"); g.set(40, 38, "#3f9d5a");
    g.ellipse(41, 31, 3, 3, "#ff2e88"); g.set(41, 31, "#a01858"); g.set(40, 30, "#ff7ab0");
  },
  scroll(g) {
    g.rect(4, 42, 12, 6, "#efe7d2"); g.rect(3, 41, 2, 8, "#a07040"); g.rect(15, 41, 2, 8, "#a07040");
    for (let x = 6; x < 14; x += 2) g.set(x, 44, "#5a1f36"); g.rect(6, 46, 7, 1, "#c9b58a");
  },
};

for (const [name, s] of Object.entries(PERSONAS)) writeFileSync(OUT_DIR + `p-${name}.svg`, person(s));

// ------------------------------------------------------------------ instruments
function sitar() {
  const g = new Grid(160, 48), w = "#8a4a1a", wl = "#c07a34", neck = "#6a3a14";
  g.ellipse(120, 13, 9, 9, w); g.ellipse(117, 10, 3, 3, wl);                       // tumbi (upper gourd)
  g.rect(40, 21, 108, 7, neck); g.rect(40, 21, 108, 1, shade(neck, 30)); g.rect(40, 27, 108, 1, shade(neck, -24));
  for (let x = 46; x < 146; x += 6) { g.rect(x, 21, 1, 7, "#c9c2b0"); g.set(x + 1, 20, "#c9c2b0"); g.set(x + 1, 28, "#c9c2b0"); }
  g.rect(14, 23, 134, 1, "#f2b53c"); g.rect(14, 25, 134, 1, "#ffd97a");
  for (let x = 50; x < 146; x += 9) g.set(x, 30, "#d8c9a8");                        // sympathetic pegs
  g.rect(146, 18, 13, 13, "#4a2810");
  [148, 152, 156].forEach(x => { g.rect(x, 14, 2, 4, "#c07a34"); g.rect(x, 31, 2, 4, "#c07a34"); });
  g.ellipse(22, 27, 21, 18, w); g.ellipse(22, 27, 15, 12, wl); g.ellipse(15, 18, 6, 4, shade(wl, 22));
  for (let a = 0; a < 6.28; a += 0.4) g.set(22 + 19 * Math.cos(a), 27 + 16 * Math.sin(a), "#f2b53c");
  g.rect(16, 30, 12, 2, "#efe7d2");                                                  // jawari bridge
  g.outline(); return g.svg();
}
function guitar() {
  const g = new Grid(128, 48), white = "#e9e3d4", bev = "#b8b0a0", mag = "#ff2e88";
  g.poly([[2, 2], [13, 2], [52, 20], [44, 24]], white); g.poly([[2, 46], [13, 46], [52, 28], [44, 24]], white);
  g.poly([[38, 18], [56, 20], [56, 28], [38, 30]], white);
  g.line(3, 3, 44, 22, bev, 1); g.line(3, 45, 44, 26, mag, 1);
  g.rect(40, 20, 4, 8, "#141019"); g.rect(30, 21, 4, 6, "#141019");
  [41, 43].forEach(x => { g.set(x, 21, "#c9c2b0"); g.set(x, 26, "#c9c2b0"); });
  g.rect(56, 21, 56, 6, "#3a2618"); g.rect(56, 21, 56, 1, "#5a4030");
  for (let x = 60; x < 112; x += 5) g.rect(x, 21, 1, 6, "#c9c2b0");
  [70, 80, 90, 104].forEach(x => g.set(x - 2, 24, "#efe7d2"));
  g.poly([[112, 19], [127, 13], [127, 35], [112, 29]], "#141019");
  [[114, 16], [119, 14], [124, 12], [114, 32], [119, 34], [124, 36]].forEach(([x, y]) => g.rect(x, y, 2, 2, "#c9c2b0"));
  for (let y = 22; y <= 26; y += 2) g.rect(26, y, 86, 1, "#d8d0c0");
  g.rect(24, 21, 3, 7, "#8c8399"); g.rect(16, 36, 3, 3, "#f2b53c"); g.rect(22, 33, 3, 3, "#f2b53c");
  g.outline(); return g.svg();
}
function tabla() {
  const g = new Grid(80, 48), cu = "#b87333", wood = "#8a4a1a", skin = "#d8c9a8";
  g.ellipse(22, 30, 19, 15, cu); g.ellipse(16, 24, 6, 5, shade(cu, 40)); g.ellipse(22, 40, 15, 4, shade(cu, -30));
  g.ellipse(22, 17, 17, 5, skin); g.ellipse(26, 17, 6, 2, "#141019");
  g.poly([[48, 14], [72, 14], [74, 44], [46, 44]], wood); g.rect(48, 15, 2, 28, shade(wood, 30));
  for (let k = 0; k < 7; k++) g.line(50 + k * 3, 15, 47 + k * 4, 43, "#c9b58a", 1);
  [49, 55, 61, 67].forEach(x => g.rect(x, 37, 4, 5, "#c07a34"));
  g.ellipse(60, 14, 13, 4, skin); g.ellipse(60, 14, 4, 1.5, "#141019");
  g.ellipse(22, 45, 16, 2, "#3a3050"); g.ellipse(60, 45, 14, 2, "#3a3050");
  g.outline(); return g.svg();
}
function tanpura() {
  const g = new Grid(32, 120), w = "#7a4a1e";
  g.rect(12, 8, 8, 82, w); g.rect(12, 8, 2, 82, shade(w, 30)); g.rect(19, 8, 1, 82, shade(w, -24));
  [6, 10, 14].forEach(y => { g.rect(8, y, 4, 2, "#c07a34"); g.rect(20, y + 2, 4, 2, "#c07a34"); });
  g.rect(11, 2, 10, 6, "#4a2810");
  g.ellipse(16, 100, 15, 17, "#9a5a24"); g.ellipse(11, 92, 5, 6, "#c07a34"); g.ellipse(16, 110, 11, 4, shade(w, -20));
  g.rect(10, 96, 12, 2, "#efe7d2");
  [13, 15, 17, 19].forEach((x, i) => g.rect(x, 8, 1, 89, i === 0 ? "#ffd97a" : "#f2b53c"));
  g.outline(); return g.svg();
}
function drums() {
  const g = new Grid(112, 72);
  g.line(16, 14, 16, 70, "#3a3550", 2); g.line(98, 18, 98, 70, "#3a3550", 2);
  g.ellipse(16, 13, 15, 3, "#f2b53c"); g.ellipse(12, 12, 6, 1, "#ffd97a");
  g.ellipse(98, 17, 15, 3, "#f2b53c"); g.ellipse(94, 16, 6, 1, "#ffd97a");
  g.ellipse(40, 30, 11, 7, "#2a2540"); g.ellipse(40, 27, 11, 4, "#d8d0c0");
  g.ellipse(72, 30, 11, 7, "#2a2540"); g.ellipse(72, 27, 11, 4, "#d8d0c0");
  g.ellipse(56, 50, 21, 20, "#1b1626"); g.ellipse(56, 50, 17, 16, "#ff2e88"); g.ellipse(56, 50, 12, 11, "#120f1d");
  g.ellipse(51, 45, 4, 3, "#3a3050");
  g.rect(84, 44, 16, 22, "#2a2540"); g.ellipse(92, 44, 8, 3, "#d8d0c0");
  g.rect(14, 46, 14, 10, "#2a2540"); g.ellipse(21, 46, 7, 3, "#d8d0c0");
  g.outline(); return g.svg();
}
function amp() {
  const g = new Grid(64, 72);
  g.rect(4, 2, 56, 16, "#161320"); g.rect(4, 2, 56, 2, "#2a2540");
  for (let x = 10; x < 50; x += 6) g.ellipse(x, 12, 1.5, 1.5, "#f2b53c");
  g.rect(48, 8, 9, 3, "#ff2e88");
  g.rect(2, 20, 60, 50, "#161320");
  for (let y = 23; y < 67; y += 2) for (let x = 5 + (y % 4); x < 59; x += 4) g.set(x, y, "#221d2e");
  [[18, 35], [46, 35], [18, 56], [46, 56]].forEach(([x, y]) => { g.ellipse(x, y, 10, 10, "#0a0813"); g.ellipse(x, y, 4, 4, "#2a2540"); g.set(x - 2, y - 2, "#4a4560"); });
  [[2, 20], [58, 20], [2, 66], [58, 66]].forEach(([x, y]) => g.rect(x, y, 4, 4, "#8c8399"));
  g.outline(); return g.svg();
}
writeFileSync(OUT_DIR + "i-sitar.svg", sitar());
writeFileSync(OUT_DIR + "i-guitar.svg", guitar());
writeFileSync(OUT_DIR + "i-tabla.svg", tabla());
writeFileSync(OUT_DIR + "i-tanpura.svg", tanpura());
writeFileSync(OUT_DIR + "i-drums.svg", drums());
writeFileSync(OUT_DIR + "i-amp.svg", amp());
console.log("ok");
