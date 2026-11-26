// Records the demo video's picture: drives the demo pages in headless Chrome (DevTools protocol), with a drawn cursor,
// and stores the screen as timed frames plus the caption shown at each moment. compose.mjs turns that into a video file.
//
//   node record.mjs <out dir> [--live http://localhost:8772] [--only title,session,live,compare,end]
//
// Needs the demo pages on http://localhost:8771 (python3 -m http.server 8771 --directory prototype/demo) and, for the
// live scene, the demo server reachable at the --live address (slurm/demo_server.sbatch plus an SSH tunnel).
// Waiting for the live server is cut from the recording; the caption band says so.
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const OUT = args[0]; if (!OUT) { console.error("usage: node record.mjs <out dir> [--live URL] [--only a,b]"); process.exit(2); }
const opt = (k) => { const i = args.indexOf(k); return i < 0 ? null : args[i + 1]; };
const LIVE = opt("--live"), ONLY = (opt("--only") || "title,session,live,compare,end").split(",");
const PAGES = "http://localhost:8771/static", HERE = dirname(fileURLToPath(import.meta.url));
// 1920 x 945 of picture (compose.mjs adds a 135 px caption band), the pages at 150% zoom: a 1280 x 630 window. The screen
// capture ignores a device scale factor, so the zoom is set in the page.
const W = 1920, H = 945, ZOOM = 1.5;
mkdirSync(join(OUT, "frames"), { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const port = 9400 + Math.floor(Math.random() * 400);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), "rec-"))}`, `--window-size=${W},${H}`,
   "--hide-scrollbars", "--no-first-run", "--allow-file-access-from-files", "about:blank"], { stdio: "ignore" });
let target;
for (let i = 0; i < 50 && !target; i++) { await sleep(200); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {} }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });

// ---- timeline: frames and captions, on a clock that stops during cuts
const frames = [], captions = [], t0 = Date.now();
let cutAt = null, cutTotal = 0, nFrame = 0;
const now = () => ((cutAt ?? Date.now()) - t0 - cutTotal) / 1000;
ws.onmessage = (m) => {
  const j = JSON.parse(m.data);
  if (j.id && pending.has(j.id)) { pending.get(j.id)(j); pending.delete(j.id); return; }
  if (j.method === "Page.screencastFrame") {
    send("Page.screencastFrameAck", { sessionId: j.params.sessionId });
    if (cutAt !== null) return;
    const f = `frames/${String(++nFrame).padStart(5, "0")}.jpg`;
    writeFileSync(join(OUT, f), Buffer.from(j.params.data, "base64"));
    frames.push({ t: +now().toFixed(3), f });
  }
};
const cut = () => { if (cutAt === null) cutAt = Date.now(); };
const uncut = async () => { if (cutAt === null) return; await ev("void 0"); cutTotal += Date.now() - cutAt; cutAt = null; await nudge(); };
let tag = "";
const caption = (text) => captions.push({ t: +now().toFixed(3), text, tag });

// ---- page helpers
async function ev(expression) {
  const r = await Promise.race([send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }),
    new Promise((_, bad) => setTimeout(() => bad(new Error("no reply from the page for: " + expression.slice(0, 160))), 20000))]);
  if (r.result.exceptionDetails) throw new Error(`${expression.slice(0, 120)} -> ${JSON.stringify(r.result.exceptionDetails).slice(0, 400)}`);
  return r.result.result?.value;
}
const CURSOR = `(() => { if (window.__cur) return; const Z = ${ZOOM};
  const c = document.createElement("div"); c.id = "__cursor";
  c.style.cssText = "position:fixed;left:640px;top:400px;width:22px;height:22px;z-index:2147483647;pointer-events:none;transition:left .45s cubic-bezier(.3,.1,.2,1),top .45s cubic-bezier(.3,.1,.2,1)";
  c.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2 L3 17 L7.2 13.4 L10 19.6 L12.6 18.4 L9.8 12.4 L15.4 12.2 Z" fill="#111" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  const ring = document.createElement("div"); ring.style.cssText = "position:fixed;width:34px;height:34px;margin:-14px 0 0 -14px;border-radius:50%;border:3px solid #c2410c;opacity:0;z-index:2147483646;pointer-events:none";
  const add = () => { document.body.append(c, ring); }; document.body ? add() : addEventListener("DOMContentLoaded", add);
  window.__cur = (x, y) => { c.style.left = x / Z + "px"; c.style.top = y / Z + "px"; };
  window.__ring = (x, y) => { ring.style.transition = "none"; ring.style.left = x / Z + "px"; ring.style.top = y / Z + "px"; ring.style.opacity = "0.9"; ring.style.transform = "scale(.5)";
    requestAnimationFrame(() => { ring.style.transition = "opacity .5s, transform .5s"; ring.style.opacity = "0"; ring.style.transform = "scale(1.3)"; }); };
})()`;
// the screencast sends a frame only when the picture changes; a one-pixel repaint makes sure the current state is stored
const nudge = () => ev(`(() => { const c = document.getElementById("__cursor"); if (c) { c.style.opacity = c.style.opacity === "0.99" ? "1" : "0.99"; } })()`);
async function goto(url, cursor = true) {
  await send("Page.navigate", { url }); await sleep(1200);
  if (cursor) await ev(CURSOR); await nudge(); await sleep(300);
}
/** el: a JavaScript expression for the element. Brings it into view, moves the drawn cursor there, clicks. */
async function click(el, { pause = 350 } = {}) {
  // hit: whether the point really belongs to the element (a docked box or a dialog can lie over it)
  const pos = `(() => { const e = ${el}; if (!e) return null; const r = e.getBoundingClientRect(); if (!r.width || !r.height) return null;
    const x = r.left + r.width / 2, y = r.top + r.height / 2, at = document.elementFromPoint(x, y);
    return { x, y, h: innerHeight, w: innerWidth, hit: !!at && (e.contains(at) || at.contains(e)) }; })()`;
  let p = await ev(pos); if (!p) throw new Error("no visible element: " + el);
  if (!p.hit || p.y < 90 || p.y > p.h - 40 || p.x < 10 || p.x > p.w - 10) { await ev(`(${el}).scrollIntoView({ behavior: "smooth", block: "center", inline: "center" })`); await sleep(900); p = await ev(pos); }
  await ev(`__cur(${p.x}, ${p.y})`); await sleep(600);
  await ev(`__ring(${p.x}, ${p.y})`);
  if (p.hit) for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) await send("Input.dispatchMouseEvent", { type, x: p.x, y: p.y, button: type === "mouseMoved" ? "none" : "left", clickCount: 1 });
  else await ev(`(${el}).click()`);                       // still covered: the cursor is drawn there, the click is sent to the element
  await sleep(pause);
}
async function type(el, text) {
  await click(el, { pause: 150 });
  await ev(`(() => { const e = ${el}; e.value = ""; e.dispatchEvent(new Event("input", { bubbles: true })); })()`);
  for (const ch of text) { await send("Input.insertText", { text: ch }); await sleep(28); }
  await sleep(250);
}
const scroll = async (dy, el = null) => { await ev(`(${el || "window"}).scrollBy({ top: ${dy}, behavior: "smooth" })`); await sleep(900); };
async function waitFor(cond, seconds = 90) {
  for (let i = 0; i < seconds * 4; i++) { if (await ev(`!!(${cond})`)) return true; await sleep(250); }
  throw new Error("timed out waiting for: " + cond);
}
/** One caption and what happens under it; stays on screen at least as long as the caption takes to read. */
async function beat(text, fn = async () => {}, extra = 0) {
  caption(text); const start = now(); console.log(`  ${start.toFixed(1)} s  ${text.slice(0, 70)}`);
  await fn();
  const read = Math.max(2.6, text.split(/\s+/).length * 0.34 + 0.6) + extra;
  await sleep(Math.max(700, (read - (now() - start)) * 1000));
}
async function closeModal() {
  await ev(`document.querySelector(".modal-box").scrollTo({ top: 0, behavior: "smooth" })`); await sleep(800);
  await click(`document.querySelector("#modal-close")`); await sleep(300);
  const closed = () => ev(`document.querySelector("#modal").classList.contains("hidden")`);
  if (!(await closed())) { await ev(`document.querySelector("#modal-close").click()`); await sleep(300); }   // the drawn cursor is on the button; the synthetic mouse click does not always reach it
  if (!(await closed())) throw new Error("the dialog did not close");
}
const last = `document.querySelector("#timeline").lastElementChild`;
const btn = (text, root = "document") => `[...${root}.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(${JSON.stringify(text)}))`;

// ---- scenes
const scenes = {
  async title() {
    tag = "";
    await goto(`file://${HERE}/cards.html?card=title`, false);
    await beat("An assistant that answers questions about a graph usually keeps state between questions. That is where a session can go wrong without any sign of it.");
    await beat("The data file grows, or the follow-up reads the graph differently, and an old result is used again.");
    await beat("GraphAudit puts a typed plan between the question and the computation. The model writes the plan; the engine owns the loading, the result store and every check.", () => goto(`file://${HERE}/cards.html?card=arch`, false), 1.5);
  },
  async session() {
    tag = "RECORDED SESSION";
    const play = () => click(`document.querySelector("#run")`, { pause: 900 });
    await beat("This is the Pokec social network: 1.6 million users and 30.6 million friendship links. We ask who the ten most influential users are.", async () => { await goto(`${PAGES}/session.html`); await sleep(2500); await play(); });
    await beat("Before the answer is trusted, the page shows how the question was read, the plan, and the measure chosen for “influential”: PageRank.", async () => {
      await click(`${last}.querySelector("[data-act=more]")`); await sleep(1200); await scroll(300); await sleep(1500); await scroll(320);
    }, 1);
    await click(`${last}.querySelector("[data-act=more]")`); await sleep(300);
    await beat("Which region is each of them from? The ranking is not computed again: two steps are marked reused, because they carry the same key as before, and one lookup runs.", play);
    await beat("Show the top twenty instead. Only the final cut runs. It is taken from the stored scores, not from the earlier list of ten.", play);
    await beat("Now the edge file grows by 27,466 rows, as it would after a nightly load. Nobody tells the system.", play);
    await beat("We ask the first question again, word for word. The plan is replayed with no planning call.", play);
    await beat("But nothing computed on the old file is reused: the engine noticed the change from the file itself, and says so. Two users who gained links now lead the ranking.");
    await beat("The most influential users within one region. This request has two readings, and nothing runs until one is chosen.", play);
    await beat("Reading A ranks the whole network and lists the members of the region. Reading B ranks again inside the region alone. Each contract shows what it would reuse.", async () => { await sleep(2500); await scroll(230); });
    await beat("We choose B.", () => click(btn("Use reading B", last), { pause: 1200 }));
    await beat("Then we open A beside it. The two top-ten lists share only four users.", play, 1);
    await beat("Among the top twenty, what is the largest group in which every two are friends? No operator computes that, and the system says so.", play);
    await beat("It prepares the twenty-user subgraph with checked steps, then has two functions written separately. They agree on a group of five, so the value is shown, marked as an answer by code.");
    await beat("The task statement and both functions are one click away.", async () => {
      await click(`${last}.querySelector("[data-act=more]")`); await sleep(500);
      await click(`${last}.querySelector("[data-act=code]")`); await sleep(2200);
      await scroll(420, `document.querySelector(".modal-box")`); await sleep(1600); await scroll(520, `document.querySelector(".modal-box")`); await sleep(1600);
      await closeModal();
    });
    await beat("The ledger is the session's bill: six steps reused, twenty executed, one turn replayed, fifteen model calls, about one cent.", async () => {
      await ev(`scrollTo({ top: 0, behavior: "smooth" })`); await sleep(900);
      await click(`document.querySelector("#bar-toggle")`); await waitFor(`!document.querySelector("#bar-more").classList.contains("hidden")`, 5); await sleep(2500); await scroll(210);
    }, 1);
    await beat("The audit record holds every plan, every reuse decision with its key, and every check.", async () => {
      await click(`document.querySelector("#btn-audit")`); await sleep(1800); await scroll(380, `document.querySelector(".modal-box")`); await sleep(1500);
    }, 1);
    await closeModal();
  },
  async live() {
    if (!LIVE) { console.log("no --live address: live scene left out"); return; }
    tag = "LIVE SERVER · waiting time cut";
    const q = `document.querySelector("#question")`, q1 = "Who are the 10 most influential users?";
    const turns = `document.querySelectorAll("#timeline > .turn").length`, idle = `!document.querySelector("#run").disabled`;
    await beat("The same system, running live against a server that holds the graph. A visitor picks the graph and types a question.", async () => {
      await goto(`${LIVE}/session.html`);
      if (await ev(`document.querySelector("#bar-more").classList.contains("hidden")`)) await click(`document.querySelector("#bar-toggle")`);
      await sleep(800); await click(btn("pokec")); await sleep(700);
      cut(); await waitFor(`/1,632,803/.test(document.querySelector("#bar-summary").innerText) && ${idle}`, 120); await uncut(); await sleep(900);
      await type(q, q1); await click(`document.querySelector("#run")`); await sleep(700);
      cut(); await waitFor(`${turns} === 1 && ${idle}`); await uncut();
    }, 1.5);
    await beat("This button appends rows to the file on disk and tells the session nothing.", async () => {
      await click(btn("Change the data file", `document.querySelector("#ask-card")`)); await sleep(700);
      cut(); await waitFor(`document.querySelector("#timeline .event") && ${idle}`); await uncut();
    }, 1);
    await beat("On the next question, the change is reported and the answer is computed on the new file.", async () => {
      await type(q, q1); await click(`document.querySelector("#run")`); await sleep(700);
      cut(); await waitFor(`${turns} === 2 && ${idle}`); await uncut();
    }, 2.5);
  },
  async compare() {
    tag = "STORED RUNS · one run of each system, small model";
    const next = `document.querySelector("#next")`;
    await beat("The same ten questions for GraphAudit and for a code-writing agent that keeps its variables.", async () => { await goto(`${PAGES}/compare.html`); await sleep(1500); for (let i = 0; i < 4; i++) await click(next, { pause: 800 }); });
    await beat("After the file grows, the agent answers from its stored PageRank vector. The page quotes the line of its own code that does it.", async () => {
      await click(next, { pause: 1800 });
      await click(`document.querySelector("#rows").lastElementChild.querySelector("[data-more]")`); await sleep(1200); await scroll(170);
    }, 1.5);
    await beat("In this run the agent is correct on five of ten turns and stale on three. GraphAudit is correct on all ten.", async () => { await click(`document.querySelector("#all")`); await sleep(1200); await ev(`document.querySelector("#cmp-total").scrollIntoView({ behavior: "smooth", block: "center" })`); await sleep(1200); }, 1.5);
    await beat("An agent can get this right, with a larger model, a warning, and recomputation. GraphAudit gets it right by construction.");
  },
  async end() {
    tag = "";
    await beat("GraphAudit: what was assumed, what was reused, and what was not checked is on screen for every answer.", () => goto(`file://${HERE}/cards.html?card=end`, false), 1.5);
  },
};

let failed = null;
try {
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send("Page.addScriptToEvaluateOnNewDocument", { source: `addEventListener("DOMContentLoaded", () => { document.documentElement.style.zoom = "${ZOOM}"; })` });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
  await send("Network.enable"); await send("Network.setCacheDisabled", { cacheDisabled: true });
  await send("Page.enable");
  await send("Page.startScreencast", { format: "jpeg", quality: 92, everyNthFrame: 1 });
  for (const name of ONLY) { console.log("scene", name, "at", now().toFixed(1), "s"); await scenes[name](); }
} catch (e) { failed = e; console.error("FAILED:", e.message); }
finally {
  const end = +now().toFixed(3);
  writeFileSync(join(OUT, "manifest.json"), JSON.stringify({ width: W, height: H, end, cut_seconds: +(cutTotal / 1000).toFixed(1), frames, captions }));
  console.log(`${frames.length} frames, ${captions.length} captions, ${end} s, ${(cutTotal / 1000).toFixed(1)} s cut`);
  ws.close(); chrome.kill();
}
process.exit(failed ? 1 : 0);
