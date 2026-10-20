// Capture the studio scene: serve talk/ locally, drive the installed Chrome headless, and step
// `renderAt(t)` frame by frame. Stills for review, or a silent MP4 (the audio is laid on later).
//
//   node capture.mjs stills 0 2.5 5          -> out/studio_still_<t>.png
//   node capture.mjs video 8 [name]           -> out/<name>.mp4 (30 fps)
//   node capture.mjs video session [name]     -> the whole session (script.json), silent
import { spawnSync } from "node:child_process";
import { createReadStream, existsSync, mkdirSync, rmSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import puppeteer from "puppeteer-core";

const HERE = new URL(".", import.meta.url).pathname;
const TALK = resolve(HERE, "..");
const OUT = resolve(TALK, "..", "out");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const FPS = 30;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json" };

/** A static server rooted at talk/, so the scene can import ../sprites/personas.mjs. */
function serve() {
  const server = createServer((req, res) => {
    const path = normalize(join(TALK, decodeURIComponent(new URL(req.url, "http://x").pathname)));
    if (!path.startsWith(TALK) || !existsSync(path) || statSync(path).isDirectory()) { res.writeHead(404).end(); return; }
    res.writeHead(200, { "Content-Type": TYPES[extname(path)] || "application/octet-stream" });
    createReadStream(path).pipe(res);
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

async function open(port) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true,
    args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage();
  page.on("console", (m) => console.log("[page]", m.text()));
  page.on("pageerror", (e) => console.error("[page error]", e.message));
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(`http://127.0.0.1:${port}/studio/index.html`);
  await page.waitForFunction("window.studioReady === true", { timeout: 30000 });
  return { browser, page };
}

async function frame(page, t, path, type = "png") {
  await page.evaluate((x) => window.renderAt(x), t);
  await page.screenshot({ path, type, ...(type === "jpeg" ? { quality: 94 } : {}) });
}

async function main([mode, ...rest]) {
  mkdirSync(OUT, { recursive: true });
  const server = await serve();
  const { browser, page } = await open(server.address().port);
  try {
    if (mode === "stills") {
      for (const t of rest.map(Number)) await frame(page, t, join(OUT, `studio_still_${t}.png`));
    } else if (mode === "video") {
      const seconds = rest[0] === "session" ? await page.evaluate("window.SESSION_END") : Number(rest[0] || 8);
      const name = rest[1] || "studio_preview";
      const dir = join(HERE, "frames", name);
      rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
      const n = Math.round(seconds * FPS);
      for (let k = 0; k < n; k++) await frame(page, k / FPS, join(dir, `${String(k).padStart(5, "0")}.jpg`), "jpeg");
      const r = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", join(dir, "%05d.jpg"),
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", join(OUT, `${name}.mp4`)], { stdio: "inherit" });
      if (r.status !== 0) throw new Error("ffmpeg failed");
    } else throw new Error("mode: stills | video");
  } finally {
    await browser.close();
    server.close();
  }
}

await main(process.argv.slice(2));
