document.querySelector("#btn-recorded").click(); await sleep(800);
for (let i = 0; i < 30; i++) {
  if (document.querySelector("[data-act=choose]")) break;
  const run = document.querySelector("#run");
  if (!run.disabled) run.click();
  await sleep(700);
}
document.querySelector("#ask-card").style.display = "none";
if (document.querySelector("#bar-more").classList.contains("hidden")) document.querySelector("#bar-toggle").click();
await sleep(400); window.scrollTo(0, 0); await sleep(200);
const R = (e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), width: Math.round(r.width), height: Math.round(r.height) }; };
const q = (s) => document.querySelector(s);
const t3 = q("#turn-3"), ev = q("#timeline .event"), t4 = q("#turn-4"), t5 = q("#turn-5");
const kids = (e) => [...e.querySelectorAll("*")].filter(x => /Verified|Use reading B|If chosen|Scope ambiguity/.test(x.textContent) && x.children.length < 6).map(x => x.tagName + "." + x.className + " " + JSON.stringify(R(x)) + " " + x.textContent.slice(0, 40)).slice(0, 14);
const rects = { bar: R(q("#session-bar")), t3: R(t3), ev: R(ev), t4: R(t4), t5: R(t5) };
const which = location.hash.slice(1);
let clip = null;
if (which === "ledger") { const l = q("#ledger-card"); l.style.width = "316px"; l.style.padding = "8px"; await sleep(300); clip = R(l); }
if (which === "left") { const f = [...t3.querySelectorAll("*")].filter(x => x.children.length && /^\s*Verified/.test(x.textContent)).pop(); const fy = R(f).y - 46; clip = { x: rects.t3.x - 6, y: fy, width: rects.t3.width + 12, height: rects.t4.y + rects.t4.height + 8 - fy }; }
if (which === "card") { const b = [...t5.querySelectorAll("[data-act=choose]")].pop(); const by = R(b).y + R(b).height + 14; clip = { x: rects.t5.x - 6, y: rects.t5.y - 6, width: rects.t5.width + 12, height: by - rects.t5.y + 6 }; }
return { log: JSON.stringify(rects) + "\n" + kids(t5).join("\n"), ...(clip || {}) };
