// Turns a recording made by record.mjs into a video file, with the captions drawn in a band under the picture.
// No encoder needs to be installed: a headless Chrome page plays the frames onto a canvas in real time and its own
// MediaRecorder encodes them (H.264 in MP4 where Chrome offers it, otherwise WebM). Takes as long as the video lasts.
//
//   node compose.mjs <recording dir> <output file without extension>
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFileSync, writeFileSync, mkdtempSync, createReadStream, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, normalize } from "node:path";

const [REC, OUTBASE] = process.argv.slice(2);
if (!REC || !OUTBASE) { console.error("usage: node compose.mjs <recording dir> <output file without extension>"); process.exit(2); }
const manifest = JSON.parse(readFileSync(join(REC, "manifest.json"), "utf8"));
const BAND = 135, W = manifest.width, H = manifest.height + BAND;

const PAGE = `<!doctype html><meta charset="utf-8"><body style="margin:0;background:#000"><canvas id="c" width="${W}" height="${H}"></canvas><script>
(async () => {
  const M = await (await fetch("/rec/manifest.json")).json(), c = document.getElementById("c"), g = c.getContext("2d");
  const types = ["video/mp4;codecs=avc1.640028", "video/mp4", "video/webm;codecs=vp9", "video/webm"];
  const mime = types.find((t) => MediaRecorder.isTypeSupported(t));
  const load = (f) => new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = "/rec/" + f; });
  const cache = new Map(), ahead = async (k) => { for (let j = k; j < Math.min(k + 12, M.frames.length); j++) if (!cache.has(j)) cache.set(j, load(M.frames[j].f)); for (const key of cache.keys()) if (key < k - 1) cache.delete(key); };
  const FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif';
  function wrap(text, size, width) { g.font = "500 " + size + "px " + FONT; const lines = []; let line = "";
    for (const w of text.split(/\\s+/)) { const t = line ? line + " " + w : w; if (g.measureText(t).width > width && line) { lines.push(line); line = w; } else line = t; }
    if (line) lines.push(line); return lines; }
  function band(cap) {
    g.fillStyle = "#16201f"; g.fillRect(0, ${manifest.height}, ${W}, ${BAND});
    if (!cap) return;
    const tag = cap.tag || "", top = ${manifest.height};
    let size = 34, lines;
    for (const s of [34, 31, 28, 25]) { size = s; lines = wrap(cap.text, s, ${W} - 160); if (lines.length <= (tag ? 2 : 3)) break; }
    const lh = Math.round(size * 1.28), block = lines.length * lh + (tag ? 26 : 0);
    let y = top + (${BAND} - block) / 2;
    g.textAlign = "center"; g.textBaseline = "top";
    if (tag) { g.font = "600 17px " + FONT; g.fillStyle = "#8fd3c8"; g.fillText(tag, ${W} / 2, y); y += 26; }
    g.font = "500 " + size + "px " + FONT; g.fillStyle = "#ffffff";
    for (const l of lines) { g.fillText(l, ${W} / 2, y + (lh - size) / 2); y += lh; }
  }
  await ahead(0); const first = await cache.get(0);
  g.drawImage(first, 0, 0); band(M.captions[0]);
  const stream = c.captureStream(30), rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 7000000 }), parts = [];
  rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
  const done = new Promise((r) => (rec.onstop = r));
  rec.start(1000);
  const t0 = performance.now(); let k = 0, shown = -1, capShown = null, late = 0;
  while (true) {
    const t = (performance.now() - t0) / 1000;
    if (t >= M.end + 0.6) break;
    while (k + 1 < M.frames.length && M.frames[k + 1].t <= t) k++;
    const cap = M.captions.filter((x) => x.t <= t).pop() || null;
    if (k !== shown || cap !== capShown) {
      ahead(k); const img = await cache.get(k);
      if ((performance.now() - t0) / 1000 - t > 0.2) late++;
      g.drawImage(img, 0, 0); band(cap); shown = k; capShown = cap;
    } else { g.fillStyle = (Math.floor(t * 30) % 2) ? "#16201f" : "#162020"; g.fillRect(0, ${H} - 1, 1, 1); }   // keeps the stream producing frames while the picture is still
    await new Promise((r) => setTimeout(r, 1000 / 30));
  }
  rec.stop(); await done;
  const blob = new Blob(parts, { type: mime });
  await fetch("/upload?mime=" + encodeURIComponent(mime) + "&late=" + late, { method: "POST", body: blob });
  document.title = "done";
})().catch((e) => fetch("/upload?error=" + encodeURIComponent(String(e && e.stack || e)), { method: "POST", body: "" }));
</script>`;

let finish; const finished = new Promise((r) => (finish = r));
const server = createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  if (u.pathname === "/") { res.writeHead(200, { "content-type": "text/html" }); return res.end(PAGE); }
  if (u.pathname.startsWith("/rec/")) {
    const f = normalize(join(REC, decodeURIComponent(u.pathname.slice(5))));
    if (!f.startsWith(normalize(REC)) || !existsSync(f)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "content-type": f.endsWith(".json") ? "application/json" : "image/jpeg" }); return createReadStream(f).pipe(res);
  }
  if (u.pathname === "/upload" && req.method === "POST") {
    const chunks = []; req.on("data", (c) => chunks.push(c)); req.on("end", () => {
      res.writeHead(200); res.end("ok");
      if (u.searchParams.get("error")) return finish({ error: u.searchParams.get("error") });
      const mime = u.searchParams.get("mime"), out = OUTBASE + (mime.startsWith("video/mp4") ? ".mp4" : ".webm");
      writeFileSync(out, Buffer.concat(chunks)); finish({ out, mime, late: u.searchParams.get("late") });
    }); return;
  }
  res.writeHead(404); res.end();
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", `--user-data-dir=${mkdtempSync(join(tmpdir(), "cmp-"))}`, `--window-size=${W},${H}`, "--no-first-run", "--hide-scrollbars",
   "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--autoplay-policy=no-user-gesture-required", `--remote-debugging-port=0`, `http://127.0.0.1:${port}/`], { stdio: "ignore" });
console.log(`composing ${manifest.end} s of video (${manifest.frames.length} frames); this takes as long as the video`);
const r = await Promise.race([finished, new Promise((x) => setTimeout(() => x({ error: "timed out" }), (manifest.end + 120) * 1000))]);
chrome.kill(); server.close();
if (r.error) { console.error("FAILED:", r.error); process.exit(1); }
console.log(`wrote ${r.out} (${r.mime}); frames drawn late: ${r.late}`);
