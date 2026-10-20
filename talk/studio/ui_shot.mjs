// Screenshot the demo UI (ui/server.py, Demo mode) at slide size: node ui_shot.mjs <out.png> [wait-ms]
import puppeteer from "puppeteer-core";
const [out, wait = "1500"] = process.argv.slice(2);
const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
await page.goto("http://127.0.0.1:8500", { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, Number(wait)));
await page.screenshot({ path: out });
await browser.close();
