/* Side by side: one recorded session, two systems. Data from demo/make_compare.py; no model is called here. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const secs = (s) => s >= 10 ? s.toFixed(0) + " s" : s >= 1 ? s.toFixed(1) + " s" : s >= 0.0995 ? s.toFixed(2) + " s" : Math.max(1, Math.round(s * 1000)) + " ms";
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  let D = null, shown = 0, changed = false;

  // an answer: a ranking as its ids, with the ids that are not in the correct list at that place marked
  function answer(a, gold, mark) {
    if (a.kind !== "ranking") return `<div class="cmp-num">${esc(a.value == null ? "no answer" : a.value)}</div>`;
    const g = gold.kind === "ranking" ? gold.nodes : [];
    return `<ol class="cmp-rank">${a.nodes.map((n, i) => `<li class="${mark && g[i] !== n ? "off" : ""}">${esc(n)}</li>`).join("")}</ol>`;
  }
  function verdict(r) {
    if (r.correct) return [`ok`, `Correct`, ``];
    if (r.stale) return [`stale`, `Stale`, `This is the correct answer for the file as it was before the change.`];
    return [`wrong`, `Wrong`, changed ? `It does not match the file as it is now.` : `It does not match the file.`];
  }
  function how(sys, r, i) {
    if (r.code != null) {
      const ev = r.evidence ? `<div class="cmp-ev"><span>from its code</span><code>${esc(r.evidence)}</code></div>` : "";
      return `${ev}<button class="ghost small" data-code="${i}" data-sys="${sys}">Its code</button>`;
    }
    const parts = [];
    if (r.flags.includes("data_changed")) parts.push(`<b>Noticed that the file changed</b> and dropped every stored result.`);
    if (!r.llm_calls) parts.push(`Plan replayed from the earlier turn with the same words; no model call.`);
    parts.push(r.steps_reused && !r.steps_executed ? `All ${plural(r.steps_reused, "step")} reused.` : r.steps_reused ? `${plural(r.steps_reused, "step")} reused, ${r.steps_executed} executed.` : `${plural(r.steps_executed, "step")} executed, none reused.`);
    return `<div class="cmp-how">${parts.join(" ")}</div><div class="cmp-steps">${(r.steps || []).map((s) => `<span>${esc(s.op)}</span>`).join("→")}</div>`;
  }
  function cell(k, i) {
    const s = D.systems[k], r = s.turns[i], t = D.turns[i], [cls, word, why] = verdict(r);
    return `<div class="cmp-cell ${cls}"><span class="cmp-sys">${esc(s.label)}</span><div class="cmp-v"><span class="verdict ${cls}">${word}</span><span class="cmp-cost">${secs(r.compute_seconds + r.setup_seconds)} compute · ${plural(r.llm_calls, "model call")}</span></div>
      ${why ? `<div class="cmp-why">${why}</div>` : ""}${answer(r.answer, t.gold, !r.correct)}${how(k, r, i)}</div>`;
  }
  function row(i) {
    const t = D.turns[i], bad = D.systems.some((s) => !s.turns[i].correct);
    let html = "";
    if (t.event) { changed = true; html += `<section class="card event"><span class="ev-ic" aria-hidden="true">+</span><div><b>The data changed</b><div>${esc(t.event)}</div></div></section>`; }
    html += `<section class="card cmp-row" id="row-${i}"><div class="cmp-q"><span class="turn-no">${esc(t.turn)}</span><div>${esc(t.question)}</div></div>
      <div class="cmp-cells">${cell(0, i)}${cell(1, i)}</div>
      ${bad && t.gold.kind === "ranking" ? `<div class="cmp-gold">Correct on the file as it is at this turn: <span class="mono">${t.gold.nodes.map(esc).join(", ")}</span></div>` : bad ? `<div class="cmp-gold">Correct on the file as it is at this turn: <b>${esc(t.gold.value)}</b></div>` : ""}</section>`;
    return html;
  }
  function totals() {
    const c = (s) => { const T = s.totals; return `<div class="cmp-cell"><b>${esc(s.label)}</b>
      <div class="kv"><span class="k">correct</span><span class="v">${T.correct} of ${T.turns}</span><span class="k">stale</span><span class="v">${T.stale}</span>
      <span class="k">compute</span><span class="v">${secs(T.compute_seconds)}, loading included</span><span class="k">model</span><span class="v">${plural(T.llm_calls, "call")} · $${T.cost_usd.toFixed(3)}</span></div></div>`; };
    const [a, b] = D.systems;
    $("#cmp-total").innerHTML = `<h2>The whole session</h2><div class="cmp-cells">${c(a)}${c(b)}</div>
      <p class="muted">One run of each system on ${esc(a.model)}; runs ${esc(a.run)} (job ${esc(a.job)}) and ${esc(b.run)} (job ${esc(b.job)}), code at commit ${esc(b.commit)}. "Correct" and "stale" are the benchmark harness's checks, not either system's own claim. Other runs and models are in the paper's tables: the result for the agent depends on the model and on whether it is warned.</p>`;
    $("#cmp-total").classList.remove("hidden");
  }
  function step() {
    if (shown >= D.turns.length) return;
    $("#rows").insertAdjacentHTML("beforeend", row(shown)); shown++;
    $$("#rows [data-code]").forEach((b) => b.onclick = () => code(+b.dataset.sys, +b.dataset.code));
    $("#rows").lastElementChild.scrollIntoView({ behavior: "smooth", block: "nearest" });
    prompt();
  }
  function prompt() {
    const t = D.turns[shown];
    if (!t) { $("#next-q").innerHTML = `<span class="muted">End of the session.</span>`; $("#next").disabled = true; $("#all").disabled = true; totals(); $("#cmp-total").scrollIntoView({ behavior: "smooth", block: "nearest" }); return; }
    $("#next-q").innerHTML = `<span class="muted">${t.event ? "The file changes, then turn" : "Turn"} ${esc(t.turn)} of ${D.turns.length}:</span> ${esc(t.question)}`;
  }
  function code(k, i) {
    const s = D.systems[k], r = s.turns[i];
    $("#modal-title").textContent = `${s.label}, turn ${D.turns[i].turn}: the code it wrote and ran`;
    $("#modal-body").innerHTML = `<p class="muted">Unedited. The process that ran it was the same one as in the earlier turns, so names defined there (the graph, the scores) still exist.</p><pre class="code">${r.code.split("\n").map((ln) => ln.trim() === r.evidence ? `<mark>${esc(ln)}</mark>` : esc(ln)).join("\n")}</pre>`;
    $("#modal").classList.remove("hidden");
  }
  function start(d) {
    D = d; shown = 0; changed = false;
    const [a, b] = D.systems;
    $("#cmp-intro").innerHTML = `<h2>${esc(D.title)}</h2><p>The same ${D.turns.length} questions were put to two systems on <span class="mono">${esc(D.file)}</span>, with ${esc(a.model)}. Part-way through, rows are appended to the edge file and neither system is told. Each answer is checked by the benchmark harness against the file as it is at that turn. This is a recording; nothing is computed on this page.</p>`;
    $("#cmp-head").innerHTML = D.systems.map((s) => `<div><b>${esc(s.label)}</b><span>${esc(s.what)}</span></div>`).join("");
    $("#rows").innerHTML = ""; $("#cmp-total").classList.add("hidden"); $("#next").disabled = false; $("#all").disabled = false; prompt();
  }

  function applyTheme(t) { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("t2a_theme", t); } catch {} }
  const isDark = () => { const t = document.documentElement.getAttribute("data-theme"); return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; };
  try { const t = localStorage.getItem("t2a_theme"); if (t) applyTheme(t); } catch {}
  $("#btn-theme").onclick = () => applyTheme(isDark() ? "light" : "dark");
  $("#next").onclick = step;
  $("#all").onclick = () => { while (shown < D.turns.length) step(); };
  $("#modal-close").onclick = () => $("#modal").classList.add("hidden");
  $("#modal").addEventListener("click", (e) => { if (e.target === $("#modal")) $("#modal").classList.add("hidden"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#modal").classList.add("hidden"); });
  (async () => {
    let recs = [];
    try { recs = await (await fetch("/api/compare")).json(); if (!Array.isArray(recs)) recs = []; } catch { recs = []; }
    if (!recs.length) { try { const idx = await (await fetch("../compare/index.json")).json(); recs = await Promise.all(idx.map(async (f) => (await fetch("../compare/" + f)).json())); } catch { recs = []; } }
    if (recs.length) start(recs[0]); else $("#cmp-intro").innerHTML = `<p class="muted">No side-by-side record found. Build one with <span class="mono">demo/make_compare.py</span>.</p>`;
  })();
})();
