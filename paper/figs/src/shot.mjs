// node shot.mjs <url> <out.png> <width> <height> <scale> <steps.js>
// steps.js: body of an async function run in the page; returns {x,y,width,height} to clip, or null for the full page.
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, out, w, h, scale, stepsFile] = process.argv.slice(2);
const port = 9333 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "shot-"));
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "--hide-scrollbars", "--no-first-run", "--disable-gpu", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) {
  await sleep(200);
  try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {}
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const wait = new Map();
ws.onmessage = (m) => { const j = JSON.parse(m.data); if (j.id && wait.has(j.id)) { wait.get(j.id)(j); wait.delete(j.id); } };
const send = (method, params = {}) => new Promise((r) => { wait.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
try {
  await send("Emulation.setDeviceMetricsOverride", { width: +w, height: +h, deviceScaleFactor: +scale, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
  await send("Network.enable"); await send("Network.setCacheDisabled", { cacheDisabled: true });
  await send("Page.enable");
  await send("Page.navigate", { url });
  await sleep(1500);
  const body = readFileSync(stepsFile, "utf8");
  const r = await send("Runtime.evaluate", { expression: `(async () => { const sleep = (ms) => new Promise((r) => setTimeout(r, ms)); ${body} })()`, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) { console.error(JSON.stringify(r.result.exceptionDetails).slice(0, 2000)); process.exitCode = 1; }
  const v = r.result.result?.value;
  if (v && v.log) console.log(v.log);
  const clip = v && v.width ? { x: v.x, y: v.y, width: v.width, height: v.height, scale: 1 } : undefined;
  const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, ...(clip ? { clip } : {}) });
  writeFileSync(out, Buffer.from(shot.result.data, "base64"));
  console.log("wrote", out, clip ? JSON.stringify(clip) : "");
} finally { ws.close(); chrome.kill(); }
