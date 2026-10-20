// Voxel building blocks: flat-shaded boxes in the sprites' palette, one unit = one sprite pixel.
import * as THREE from "three";

const MATERIALS = new Map();

/** One shared flat-shaded material per colour (hundreds of boxes, a few dozen materials). */
export function material(color) {
  if (!MATERIALS.has(color)) {
    MATERIALS.set(color, new THREE.MeshLambertMaterial({ color, flatShading: true }));
  }
  return MATERIALS.get(color);
}

/** A box `w`×`h`×`d` centred at (x, y, z), casting and receiving shadows. */
export function box(w, h, d, color, x = 0, y = 0, z = 0) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material(color));
  mesh.position.set(x, y, z);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

/** A box resting on y = `y0` (its bottom), not centred — how the sprites measure height. */
export function slab(w, h, d, color, x, y0, z) {
  return box(w, h, d, color, x, y0 + h / 2, z);
}

/** A low-poly cylinder (drums, gourds, stands) with its axis along y. */
export function cylinder(r, h, color, x = 0, y = 0, z = 0, segments = 10) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, segments), material(color));
  mesh.position.set(x, y, z);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

/** A group holding `children`, at (x, y, z). */
export function group(children = [], x = 0, y = 0, z = 0) {
  const g = new THREE.Group();
  children.forEach((c) => g.add(c));
  g.position.set(x, y, z);
  return g;
}

/** The sprites' shade(): brighten or darken a hex colour by `amt` per channel. */
export function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const cl = (v) => Math.max(0, Math.min(255, v));
  const r = cl((n >> 16) + amt), g = cl(((n >> 8) & 255) + amt), b = cl((n & 255) + amt);
  return "#" + ((r << 16) | (g << 8) | b).toString(16).padStart(6, "0");
}

/** A faceted low-poly ball (gourds, pompoms): round enough to read, blocky enough to match. */
export function ball(r, color, x = 0, y = 0, z = 0, sx = 1, sy = 1, sz = 1) {
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 9, 7), material(color));
  mesh.position.set(x, y, z);
  mesh.scale.set(sx, sy, sz);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}
