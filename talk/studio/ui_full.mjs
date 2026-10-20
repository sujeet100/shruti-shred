import puppeteer from "puppeteer-core";
const [out] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const p = await b.newPage();
await p.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 2 });
await p.goto("http://127.0.0.1:8500", { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 1500));
const info = await p.evaluate(() => {
  const q = [...document.querySelectorAll("input,textarea,button")].map(e => ({tag: e.tagName, id: e.id, text: (e.value || e.innerText || e.placeholder || "").slice(0, 60), y: Math.round(e.getBoundingClientRect().top), x: Math.round(e.getBoundingClientRect().left)}));
  return {h: document.documentElement.scrollHeight, q};
});
console.log(JSON.stringify(info));
await p.screenshot({ path: out, fullPage: true });
await b.close();
