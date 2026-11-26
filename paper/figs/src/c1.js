for (let i = 0; i < 5; i++) { document.querySelector("#next").click(); await sleep(500); }
{ const bs=[...document.querySelectorAll("#rows .cmp-row:last-child button")].filter(b=>/Details/.test(b.textContent)); if (location.hash==="#open" && bs[0]) { bs[0].click(); await sleep(400);} }
const dock = document.querySelector("#next").closest("section,.dock,.panel"); if (dock) dock.style.display = "none";
window.scrollTo(0, 0); await sleep(600);
const R = (e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), width: Math.round(r.width), height: Math.round(r.height) }; };
const rows = [...document.querySelector("#rows").children];
const log = rows.map(e => e.className + " " + JSON.stringify(R(e))).join("\n") + "\nhead " + JSON.stringify(R(document.querySelector("#cmp-head")));
let clip = null;
if (location.hash === "#crop" || location.hash === "#open") { const a = R(rows[rows.length - 2]), b = R(rows[rows.length - 1]); const top = Math.min(a.y, b.y) - 6; clip = { x: b.x - 6, y: top, width: b.width + 12, height: b.y + b.height + 8 - top }; }
if (location.hash === "#head") { const h = R(document.querySelector("#cmp-head")); clip = { x: h.x - 6, y: h.y - 6, width: h.width + 12, height: h.height + 12 }; }
return { log, ...(clip || {}) };
