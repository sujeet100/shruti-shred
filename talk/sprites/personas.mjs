// The personas' looks, shared by the pixel sprites (gen_sprites.mjs) and the 3D studio scene
// (talk/studio): one spec per character, so the two never drift apart.
export const PERSONAS = {
  interpreter: { skin: "#e6b98a", coat: "#2f7d76", hair: "#241a2e", headphones: true, accent: "#38e0cf", trim: "stripe" },
  pandit:      { skin: "#e0b083", coat: "#efe7d2", hair: "#d8d0c2", beard: "#d8d0c2", tilak: true, robe: true, accent: "#f2b53c", trim: "sash", prop: "scroll" },
  riffsmith:   { skin: "#d9a679", coat: "#1a1724", hair: "#0d0a14", longhair: true, zip: true, tee: "#ff2e88", accent: "#ff2e88", trim: "none", pose: "horns", stubble: true, pants: "#20202a" },
  lead:        { skin: "#e0b083", coat: "#b8462a", hair: "#1c1526", topknot: true, robe: true, accent: "#f2b53c", trim: "sash", prop: "sitar" },
  riff:        { skin: "#d9a679", coat: "#1c1b26", hair: "#141019", cap: "#2a2838", tee: "#d9702a", accent: "#d9702a", trim: "none", prop: "guitar", pants: "#3a4a6a" },
  orchestra:   { skin: "#dcae80", coat: "#2a1622", hair: "#3a2a1e", shirtFront: "#efe7d2", bowtie: true, buttons: "#f2b53c", accent: "#d9702a", trim: "none", prop: "horn" },
  arranger:    { skin: "#e6b98a", coat: "#2a3550", hair: "#5a3a22", glasses: true, buttons: "#c9c2b0", accent: "#38e0cf", trim: "belt", prop: "clipboard" },
  ustad:       { skin: "#dcae80", coat: "#26202f", hair: "#9a9082", beard: "#b8b0a2", glasses: true, receding: true, robe: true, buttons: "#f2b53c", accent: "#38e0cf", trim: "none", prop: "rulebook", frown: true },
  rasik:       { skin: "#e0b083", coat: "#5a1f36", hair: "#241a2e", eyesClosed: true, robe: true, accent: "#ff2e88", trim: "sash", prop: "rose" },
  producer:    { skin: "#d9a679", coat: "#1d2740", hair: "#141019", beanie: "#ff2e88", drawstrings: true, accent: "#ff2e88", trim: "none", prop: "mixer", stubble: true },
  composer:    { skin: "#dcae80", coat: "#2f3a6e", hair: "#141019", longhair: true, tilak: true, tee: "#f2b53c", accent: "#f2b53c", trim: "none", prop: "scroll", stubble: true, pants: "#20202a" },
  // Pandit today (Sujit, 2026-10-20): one composer holding both priors — the elder's beard, tilak and kurta, in
  // metal black with a pink sash, long hair down, an electric guitar instead of the scroll.
  fusion:      { skin: "#e0b083", coat: "#1a1724", hair: "#e9e3d4", beard: "#e9e3d4", longhair: true, tilak: true, robe: true, accent: "#ff2e88", trim: "sash", prop: "guitar" },
  rhythm:      { skin: "#d9a679", coat: "#2a2f3a", hair: "#141019", beanie: "#79b8cc", tee: "#79b8cc", accent: "#79b8cc", trim: "none", prop: "guitar", pants: "#3a4a6a", stubble: true },
  bassist:     { skin: "#e0b083", coat: "#3a2a4a", hair: "#241a2e", stubble: true, tee: "#79b8cc", accent: "#79b8cc", trim: "none", pants: "#20202a" },
  drummer:     { skin: "#d9a679", coat: "#2a1622", hair: "#141019", headphones: true, tee: "#d26f5d", accent: "#d26f5d", trim: "none", pants: "#2a2438" },
  conductor:   { skin: "#e0b083", coat: "#123a3f", hair: "#e9e3d4", shirtFront: "#efe7d2", bowtie: true, accent: "#38e0cf", trim: "none", pose: "baton" },
};
